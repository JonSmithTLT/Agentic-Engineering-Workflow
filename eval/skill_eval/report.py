"""A skill evaluation's report: the shared paired report (:mod:`skill_eval.paired`), with what a skill evaluation
reads from the same pairs (skill evaluation guide §5, steps 8 and 9; §6; §7).

The pairs, their usage differences, the blind packets and the paired grades are the shared part's. This module adds
the three things that are about a skill:

* **A run counts only with its arm's frozen exposure.** A valid run whose delivered skills are not the ones its arm
  pinned is ``EXPOSURE_MISMATCH``, and its pair is incomplete.
* **Cost** (the row's third question) splits the pairs' usage differences by whether the candidate run loaded the
  candidate, and ``loads`` counts the candidate's loads and the bytes of its ``SKILL.md`` they brought in, a lower
  bound on what a load costs. The first step's input tokens are what the listing, and anything the arm was told,
  added to what the model first received.
* **Selection** (the second) sets each candidate run's ``loaded`` beside the case's expected activation from the
  evaluator's key: a load where the oracle says ``skip`` or ``abstain`` is a false activation, none where it says
  ``use`` is a missed one. Loads of the other exposed skills, and ``skill`` calls that loaded nothing, are counted for
  both arms. Whether a run that should have abstained went on regardless is a grader's judgement.

**Benefit** (the first) needs grades, which no code here produces. No interval, threshold or verdict is computed: the
uncertainty method and the decision rule are the preregistration's to state and the operator's to adopt (README,
"What the runner leaves open").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_eval import paired, plan
from skill_eval.paired import load_grades  # noqa: F401 (the grader's file is read the shared way)
from skill_eval.run import LANE_FILE

REPORT = "aew/skill-eval-report/v1"


def sides(pair: dict[str, Any]) -> dict[str, str]:
    """The pair's two arms as the shared report names them: the baseline is the reference side."""
    return {"baseline": pair["baseline"], "candidate": pair["candidate_arm"]}


def _exposure(record: dict[str, Any]) -> dict[str, Any]:
    seen = (record.get("harness") or {}).get("exposure")
    return seen if isinstance(seen, dict) else {}


def exposure_problem(record: dict[str, Any], arm: dict[str, Any]) -> str | None:
    """Why a valid run cannot count: what it delivered is not what its arm froze."""
    delivered = {d.get("name"): d.get("sha256") for d in _exposure(record).get("delivered") or []}
    return None if delivered == arm["config"].get("skill_sha256", {}) else "EXPOSURE_MISMATCH"


def loads_of(candidate: str) -> paired.Facts:
    """What a run says it loaded: ``None`` wherever the session could not be read, never an empty count."""
    def facts(record: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
        exposure = _exposure(record)
        counted = exposure.get("loaded")
        loaded: dict[str, Any] | None = counted if isinstance(counted, dict) else None
        size = next((d.get("bytes") for d in exposure.get("delivered") or [] if d.get("name") == candidate), None)
        return {"loaded": loaded, "skill_other": exposure.get("skill_other"),
                "candidate_loaded": None if loaded is None else bool(loaded.get(candidate)),
                "candidate_bytes": size}
    return facts


def pairs(frozen: dict[str, Any], ledger_dir: Path) -> list[dict[str, Any]]:
    """Every block of the schedule as a baseline and candidate pair, in schedule order. The pair is read from the
    frozen record and the runs, never from today's install, so a lane stays reportable after a skill's text changes."""
    pair = plan.shape(frozen, installed=False)
    return paired.pairs(frozen, ledger_dir, sides(pair), problem=exposure_problem, facts=loads_of(pair["candidate"]))


def cost(found: list[dict[str, Any]], pair: dict[str, Any]) -> dict[str, Any]:
    complete = [p for p in found if p["complete"]]
    loaded = [p for p in complete if p["candidate"]["candidate_loaded"] is True]
    not_loaded = [p for p in complete if p["candidate"]["candidate_loaded"] is False]
    loads = [int(p["candidate"]["loaded"].get(pair["candidate"], 0)) for p in complete
             if p["candidate"]["loaded"] is not None]
    # the candidate's SKILL.md size as the runs that had it recorded it; unknown when none did
    size = next((p["candidate"]["candidate_bytes"] for p in complete
                 if isinstance(p["candidate"]["candidate_bytes"], int)), None)
    return {**paired.cost(found, sides(pair)),
            "when_the_candidate_was_loaded": {"pairs": len(loaded), **paired.deltas(loaded)},
            "when_it_was_not": {"pairs": len(not_loaded), **paired.deltas(not_loaded)},
            "loads": {"runs_with_loaded_known": len(loads), "loads": sum(loads),
                      "skill_md_bytes": size,
                      "loaded_bytes_lower_bound": None if size is None else sum(loads) * size}}


def selection(found: list[dict[str, Any]], pair: dict[str, Any], key: dict[str, Any] | None) -> dict[str, Any]:
    classes: dict[str, dict[str, int]] = {}
    others: dict[str, dict[str, int]] = {"baseline": {}, "candidate": {}}
    calls: dict[str, int] = {"baseline": 0, "candidate": 0}
    for p in found:
        for side in ("baseline", "candidate"):
            run = p[side]
            if not run["counts"]:
                continue
            for name in sorted(run["loaded"] or {}):
                if name != pair["candidate"]:
                    others[side][name] = others[side].get(name, 0) + 1
            calls[side] += int(run["skill_other"] or 0)
        run = p["candidate"]
        if not run["counts"]:
            continue
        expected = ((key or {}).get("cases") or {}).get(p["case"], {}).get("activation") or "unknown"
        row = classes.setdefault(expected, {"loaded": 0, "not_loaded": 0, "unknown": 0})
        did = run["candidate_loaded"]
        row["unknown" if did is None else "loaded" if did else "not_loaded"] += 1
    return {"candidate_runs_by_expected_activation": dict(sorted(classes.items())),
            "false_activations": sum(classes.get(c, {}).get("loaded", 0) for c in ("skip", "abstain")),
            "missed_activations": classes.get("use", {}).get("not_loaded", 0),
            "runs_that_loaded_another_exposed_skill": others, "skill_calls_that_loaded_nothing": calls}


def packets(frozen: dict[str, Any], ledger_dir: Path, cases: dict[str, Path]) -> list[dict[str, Any]]:
    """The blind grading packets of each complete pair: the shared ones, which carry no arm, exposure, load or cost."""
    return paired.packets(frozen, ledger_dir, cases, pairs(frozen, ledger_dir),
                          sides(plan.shape(frozen, installed=False)))


def report(frozen: dict[str, Any], lane: Path, *, key: dict[str, Any] | None = None,
           grades: dict[str, Any] | None = None) -> dict[str, Any]:
    """The lane's report. ``pilot`` is always true today: the only cases a model arm can run are public ones, whose
    oracles anyone can read, and F19 refuses a held-out case on a model arm. A pilot qualifies the instrument and
    decides nothing (guide §5). ``evaluator_material_hidden`` says what the lane's record knows of the filesystem."""
    pair = plan.shape(frozen, installed=False)
    found = pairs(frozen, lane / "ledger")
    mark = json.loads((lane / LANE_FILE).read_text(encoding="utf-8")) if (lane / LANE_FILE).exists() else {}
    hidden = bool(mark.get("evaluator_material_hidden"))
    return {"schema": REPORT, "experiment": frozen["experiment"],
            "preregistration_sha256": frozen["canonical_sha256"],
            "pair": {k: pair[k] for k in ("baseline", "candidate_arm", "candidate", "mode", "kind", "also_exposed",
                                          "told_differs")},
            "pilot": True, "evaluator_material_hidden": hidden,
            "pairs": paired.summary(found), "cost": cost(found, pair), "selection": selection(found, pair, key),
            "benefit": paired.benefit(found, grades, sides(pair)), "decision": None, "runs": found}
