"""The pairs, the blinded grading packets and the three measures (skill evaluation guide §5, steps 8 and 9; §6; §7).

Everything here reads the lane's ledger and F19's run records; nothing is measured again. A cell's counted attempt is
its latest. A **pair** is one case and repetition's two counted runs, and it is *complete* when both are valid and
each had its arm's frozen exposure; every other pair is listed with why, never dropped (guide §5, step 9).

* **Cost** (the row's third question) is the candidate arm's usage minus the baseline's, pair by pair: the first
  step's input tokens (what the listing, and anything the arm was told, added to what the model first received),
  every token category the harness reported, the reported cost, the steps and the wall time; all pairs, then split
  by whether the candidate run loaded the candidate. An unknown value makes that pair's difference unknown: it is
  counted as missing, never as zero (guide §7). ``loads`` counts the candidate's loads and the bytes of its
  ``SKILL.md`` they brought in, a lower bound on what a load costs.
* **Selection** (the second) sets each candidate run's ``loaded`` beside the case's expected activation from the
  evaluator's key: a load where the oracle says ``skip`` or ``abstain`` is a false activation, none where it says
  ``use`` is a missed one. Loads of the other exposed skills, and ``skill`` calls that loaded nothing, are counted for
  both arms. Whether a run that should have abstained went on regardless is a grader's judgement (below).
* **Benefit** (the first) needs grades, which no code here produces: :func:`packets` writes what a grader may see,
  with the arm, the exposure, the loads and the cost removed, and :func:`report` joins the grader's file
  (``{"run_id", "task_correct"}`` per line) into paired counts: both right, the candidate alone, the baseline alone,
  neither.

No interval, threshold or verdict is computed: the uncertainty method and the decision rule are the preregistration's
to state and the operator's to adopt (README, "What the runner leaves open").
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from aew_eval import fixture
from aew_eval.ledger import AttemptLedger

from skill_eval import plan
from skill_eval.run import LANE_FILE, charged, of_cell, record_of

REPORT = "aew/skill-eval-report/v1"
PACKET = "aew/skill-eval-packet/v1"


def _flat(value: Any, prefix: str = "") -> dict[str, float]:
    """A usage mapping's numbers by dotted name (``cache.read``); anything that is not a number is left out."""
    out: dict[str, float] = {}
    for key, item in (value.items() if isinstance(value, dict) else ()):
        name = f"{prefix}{key}"
        if isinstance(item, dict):
            out.update(_flat(item, name + "."))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            out[name] = float(item)
    return out


def observation(record: dict[str, Any] | None, arm: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    """What one counted run says, for the pair: its validity, its exposure against its arm's frozen one, what it
    loaded, and its usage. ``None`` wherever the run did not say."""
    if record is None:
        return {"run_id": None, "counts": False, "why": "runner_lost"}
    harness, outcome = record.get("harness") or {}, record.get("outcome") or {}
    seen, cost = harness.get("exposure"), record.get("cost") or {}
    exposure: dict[str, Any] = seen if isinstance(seen, dict) else {}
    delivered = {d.get("name"): d.get("sha256") for d in exposure.get("delivered") or []}
    as_frozen = delivered == arm["config"].get("skill_sha256", {})
    counted = exposure.get("loaded")
    loaded: dict[str, Any] | None = counted if isinstance(counted, dict) else None
    status = record["validity"]["status"]
    if status != "valid":
        why = record["validity"]["reason_code"] or status
    else:
        why = None if as_frozen else "EXPOSURE_MISMATCH"
    usage = {f"tokens.{k}": v for k, v in _flat(cost.get("tokens")).items()}
    for name, value in (("first_step_input_tokens", harness.get("first_step_input_tokens")),
                        ("cost_usd", cost.get("provider_reported_usd")), ("steps", outcome.get("model_steps")),
                        ("wall_s", record.get("wall_s"))):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            usage[name] = float(value)
    return {"run_id": record["run_id"], "counts": why is None, "why": why,
            "truncated": outcome.get("truncated"), "loaded": loaded, "skill_other": exposure.get("skill_other"),
            "candidate_loaded": None if loaded is None else bool(loaded.get(pair["candidate"])),
            "usage": usage, "charged_usd": charged(record, pair["caps"][arm["id"]])}


def pairs(frozen: dict[str, Any], ledger_dir: Path) -> list[dict[str, Any]]:
    """Every block of the schedule as a pair, in schedule order."""
    pair = plan.shape(frozen)
    ledger = AttemptLedger(ledger_dir, frozen)
    by_arm = {a["id"]: a for a in frozen["arms"]}
    out = []
    for block in plan.blocks(frozen):
        seen: dict[str, dict[str, Any]] = {}
        for entry in block:
            attempts = of_cell(ledger, entry["cell"])
            seen[entry["arm"]] = (observation(record_of(ledger, attempts[-1]), by_arm[entry["arm"]], pair)
                                  if attempts else {"run_id": None, "counts": False, "why": "not_run"})
        a, b = seen[pair["baseline"]], seen[pair["candidate_arm"]]
        complete = a["counts"] and b["counts"]
        delta = {name: b["usage"][name] - a["usage"][name]
                 for name in sorted(a["usage"].keys() & b["usage"].keys())} if complete else {}
        out.append({"case": block[0]["case"], "repetition": block[0]["repetition"], "complete": complete,
                    "why": None if complete else {"baseline": a["why"], "candidate": b["why"]},
                    "baseline": a, "candidate": b, "delta": delta})
    return out


def _stats(values: list[float], of: int) -> dict[str, Any]:
    """Descriptive only: how many pairs gave the value and how many did not, then its mean, median and range."""
    if not values:
        return {"n": 0, "missing": of, "mean": None, "median": None, "min": None, "max": None}
    return {"n": len(values), "missing": of - len(values), "mean": statistics.fmean(values),
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def _deltas(found: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted({name for p in found for name in p["delta"]})
    return {name: _stats([p["delta"][name] for p in found if name in p["delta"]], len(found)) for name in names}


def cost(found: list[dict[str, Any]], pair: dict[str, Any]) -> dict[str, Any]:
    complete = [p for p in found if p["complete"]]
    loaded = [p for p in complete if p["candidate"]["candidate_loaded"] is True]
    not_loaded = [p for p in complete if p["candidate"]["candidate_loaded"] is False]
    loads = [int(p["candidate"]["loaded"].get(pair["candidate"], 0)) for p in complete
             if p["candidate"]["loaded"] is not None]
    return {"complete_pairs": len(complete), "candidate_minus_baseline": _deltas(complete),
            "when_the_candidate_was_loaded": {"pairs": len(loaded), **_deltas(loaded)},
            "when_it_was_not": {"pairs": len(not_loaded), **_deltas(not_loaded)},
            "loads": {"runs_with_loaded_known": len(loads), "loads": sum(loads),
                      "skill_md_bytes": pair["candidate_bytes"],
                      "loaded_bytes_lower_bound": sum(loads) * pair["candidate_bytes"]},
            "counted_runs_charged_usd": {side: sum(p[side].get("charged_usd") or 0.0 for p in found)
                                         for side in ("baseline", "candidate")}}


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


def benefit(found: list[dict[str, Any]], grades: dict[str, Any] | None) -> dict[str, Any]:
    if grades is None:
        return {"graded": False, "note": "no grades were given: write the packets, grade them blind, and pass the "
                                         "grades file"}
    counts = {"both_correct": 0, "candidate_only": 0, "baseline_only": 0, "neither": 0, "ungraded": 0}
    for p in found:
        if not p["complete"]:
            continue
        a, b = (grades.get(p[side]["run_id"]) for side in ("baseline", "candidate"))
        if not isinstance(a, bool) or not isinstance(b, bool):
            counts["ungraded"] += 1
        else:
            counts["both_correct" if a and b else "candidate_only" if b else "baseline_only" if a else "neither"] += 1
    return {"graded": True, "complete_pairs": counts}


def load_grades(path: Path) -> dict[str, Any]:
    """The grader's file: one ``{"run_id", "task_correct"}`` object per line. A run graded twice is refused."""
    out: dict[str, Any] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["run_id"] in out:
            raise ValueError(f"{path} line {n}: {entry['run_id']} is graded twice")
        out[entry["run_id"]] = entry.get("task_correct")
    return out


def packets(frozen: dict[str, Any], ledger_dir: Path, cases: dict[str, Path]) -> list[dict[str, Any]]:
    """What a grader may see of each complete pair's two runs, in run-id order: the case's task, the exported final
    tree and its hash, the changed paths, and whether the run was cut short. Never the arm, its exposure, what was
    loaded or what it cost: a run's id names its place in the schedule only."""
    out = []
    ledger = AttemptLedger(ledger_dir, frozen)
    records = {a.run_id: record_of(ledger, a) for a in ledger.attempts().values()}
    for p in pairs(frozen, ledger_dir):
        if not p["complete"]:
            continue
        task = fixture.load(cases[p["case"]]).manifest.get("task")
        for side in ("baseline", "candidate"):
            record = records[p[side]["run_id"]] or {}
            scoring = (record.get("outcome") or {}).get("scoring") or {}
            out.append({"schema": PACKET, "run_id": record["run_id"], "case": p["case"], "task": task,
                        "export": scoring.get("export"), "export_sha256": scoring.get("export_sha256"),
                        "changed_paths": record["outcome"].get("changed_paths"),
                        "truncated": record["outcome"].get("truncated")})
    return sorted(out, key=lambda packet: packet["run_id"])


def report(frozen: dict[str, Any], lane: Path, *, key: dict[str, Any] | None = None,
           grades: dict[str, Any] | None = None) -> dict[str, Any]:
    """The lane's report. ``pilot`` is true unless the lane's record says the evaluator's material was hidden from
    every arm: a pilot qualifies the instrument and decides nothing (guide §5)."""
    pair = plan.shape(frozen)
    found = pairs(frozen, lane / "ledger")
    mark = json.loads((lane / LANE_FILE).read_text(encoding="utf-8")) if (lane / LANE_FILE).exists() else {}
    hidden = bool(mark.get("evaluator_material_hidden"))
    return {"schema": REPORT, "experiment": frozen["experiment"],
            "preregistration_sha256": frozen["canonical_sha256"],
            "pair": {k: pair[k] for k in ("baseline", "candidate_arm", "candidate", "mode", "kind", "also_exposed")},
            "pilot": pair["kind"] != "raw" or not hidden, "evaluator_material_hidden": hidden,
            "pairs": {"planned": len(found), "complete": sum(p["complete"] for p in found),
                      "incomplete": [{"case": p["case"], "repetition": p["repetition"], "why": p["why"]}
                                     for p in found if not p["complete"]]},
            "cost": cost(found, pair), "selection": selection(found, pair, key), "benefit": benefit(found, grades),
            "decision": None, "runs": found}
