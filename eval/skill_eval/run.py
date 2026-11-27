"""A skill evaluation's lane: the shared walk (:mod:`aew_eval.walk`), with what a skill evaluation adds around it.

:func:`run` checks that the frozen preregistration is a paired skill evaluation (:func:`skill_eval.plan.shape`),
claims the lane for that one experiment, installs the two skill arms for the walk's duration, and walks the schedule
(guide §5, steps 4 to 7). The budget, the retries, the lane errors, the run names and the resumption are the walk's.

**The evaluator's material.** A contained arm (Linux) is refused unless every evaluator path is hidden by its layout;
the lane's record (``lane.json``) says whether it was. It covers the evaluator's paths only (README, Limits).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aew_eval import raw, walk
from aew_eval.schemas import Invalid

from skill_eval import arms, plan

LANE = "aew/skill-eval-lane/v1"
LANE_FILE = "lane.json"


def claim(lane: Path, frozen: dict[str, Any], hidden: bool) -> dict[str, Any]:
    """The lane's own record: the one experiment whose runs it holds, and whether the evaluator's material was hidden
    from every arm so far (once it was not, it stays so)."""
    path = lane / LANE_FILE
    mark = {"schema": LANE, "experiment": frozen["experiment"], "preregistration_sha256": frozen["canonical_sha256"],
            "evaluator_material_hidden": hidden}
    if path.exists():
        found = json.loads(path.read_text(encoding="utf-8"))
        if (found.get("experiment"), found.get("preregistration_sha256")) != (mark["experiment"],
                                                                           mark["preregistration_sha256"]):
            raise Invalid(f"{lane} holds the runs of {found.get('experiment')!r}: every experiment has a lane of its "
                          "own")
        mark["evaluator_material_hidden"] = bool(found.get("evaluator_material_hidden")) and hidden
    lane.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mark, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return mark


def hidden_from_arms(frozen: dict[str, Any], work: Path, evaluator: list[Path]) -> bool:
    """Whether every arm of this lane runs where it cannot read the evaluator's paths. A contained arm must (it is
    refused otherwise); an arm that is not contained, or not a model, can read whatever its user can."""
    if not all(a["config"].get("contain") is True for a in frozen["arms"]):
        return False
    if not evaluator:
        return False  # nothing was named, so nothing is known to be hidden
    seen = arms.readable_inside(evaluator, work / "r000", binary=raw.harness_binary())
    if seen:
        raise Invalid(f"a contained arm could read the evaluator's material at {', '.join(seen)}: keep it under the "
                      "home directory, outside the lane's work directory, where the arm's layout hides it")
    return True


def run(frozen: dict[str, Any], *, cases: dict[str, Path], lane: Path, evaluator: list[Path] | None = None,
        deadline_s: float = 3600.0, limit: int | None = None) -> dict[str, Any]:
    """Walk the schedule of a paired skill evaluation; at most ``limit`` attempts.

    ``lane`` holds the experiment's ledger (``ledger/``) and scratch (``work/``), outside every git work tree;
    ``evaluator`` names what no arm may read (the key's directory, the cases, and the directory their source file
    is in, which holds its oracles and rubric: the command line passes all three). Returns the walk's account
    (:func:`aew_eval.walk.walk`) with ``evaluator_material_hidden``. Raises :class:`aew_eval.schemas.Invalid` before
    anything is registered when the preregistration is not a paired skill evaluation."""
    plan.shape(frozen)
    ledger_dir, work = lane / "ledger", lane / "work"
    mark = claim(lane, frozen, hidden_from_arms(frozen, work, list(evaluator or [])))
    with arms.installed():
        out = walk.walk(frozen, cases=cases, ledger_dir=ledger_dir, work=work, deadline_s=deadline_s, limit=limit)
    return {**out, "evaluator_material_hidden": mark["evaluator_material_hidden"]}
