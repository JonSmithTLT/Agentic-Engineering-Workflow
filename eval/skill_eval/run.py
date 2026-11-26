"""The schedule, cell by cell, under the preregistered budget (skill evaluation guide §5, steps 4 to 7).

:func:`run` walks the frozen schedule in order and gives each cell that still needs an attempt to F19's runner
(:func:`aew_eval.runner.run_cell`), which registers it before any provider action and finalizes it once. It is
resumable: what has run is the ledger's, so a second call continues where the first stopped.

* **Budget.** Every attempt is charged: its reported cost, or its arm's ``cap_usd`` when the cost is unknown or the
  attempt was lost (``aew_eval.raw.charged``). A cell starts only while what is spent, plus the caps of every cell its
  block still needs, fits ``budget_usd``; otherwise the walk stops with nothing started, so a pair is never begun
  that the budget cannot finish.
* **Retries** are the frozen policy's, which the ledger enforces: a cell whose latest attempt is valid, or whose
  policy allows no further one, is left as it is. A model's failure is an outcome, never retried into a pass.
* **A lane error stops the walk.** An attempt that measured the host and not the model (:data:`LANE_ERRORS`) would
  repeat in every later cell, so the walk ends there and says why, as the lower-bound lane's does.
* **Names.** A run is named for its place in the schedule (``r007``), which is drawn at random inside each block, so
  neither a run's id nor its folder names its arm.
* **The evaluator's material.** A contained arm (Linux) is refused unless every evaluator path is hidden by its
  layout; the lane's record (``lane.json``) says whether it was, and a lane where it was not is a pilot (README).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aew_eval import raw, runner
from aew_eval.ledger import Attempt, AttemptLedger
from aew_eval.schemas import Invalid

from skill_eval import arms, plan

LANE = "aew/skill-eval-lane/v1"
LANE_FILE = "lane.json"
# Why an attempt cannot count that every later cell would meet too (``raw.raw_invalid``'s host-side reasons, and the
# runner's own for a model that is not the pinned one): the host or the key needs fixing, not another attempt.
LANE_ERRORS = ("CONTAINMENT_FAILED", "HARNESS_MISMATCH", "NO_MODEL_STEP", "PROVIDER_KEY_RETAINED", "PROFILE_MISMATCH")


def run_name(entry: dict[str, Any], attempts: int) -> str:
    return f"r{entry['order_index'] + 1:03d}" + (f"-retry{attempts}" if attempts else "")


def record_of(ledger: AttemptLedger, attempt: Attempt) -> dict[str, Any] | None:
    """A finalized attempt's result, or None while it has none (a lost runner)."""
    if attempt.finalized is None:
        return None
    return json.loads((ledger.runs / (attempt.run_id.split("/", 1)[1] + ".json")).read_text(encoding="utf-8"))


def charged(record: dict[str, Any] | None, cap: float) -> float:
    """What an attempt is charged against the budget: its charged cost, else its reported cost, else its cap."""
    cost = (record or {}).get("cost") or {}
    if cost.get("charged_usd") is not None:
        return float(cost["charged_usd"])
    return raw.charged(cost.get("provider_reported_usd"), cap)


def spent(ledger: AttemptLedger, caps: dict[str, float]) -> float:
    return sum(charged(record_of(ledger, a), caps[a.registered["arm"]]) for a in ledger.attempts().values())


def of_cell(ledger: AttemptLedger, cell: str) -> list[Attempt]:
    """A cell's attempts in the ledger's own order, so the last is its latest (never by their time stamps)."""
    return [a for a in ledger.attempts().values() if a.registered["assignment"]["cell"] == cell]


def needs_attempt(ledger: AttemptLedger, cell: str, policy: dict[str, Any]) -> bool:
    attempts = of_cell(ledger, cell)
    if not attempts:
        return True
    latest = attempts[-1]
    return latest.status != "valid" and latest.status in policy["allowed_for"] \
        and len(attempts) - 1 < int(policy["max_retries"])


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
    # every public candidate's oracle is in this checkout, whatever else the caller names
    material = [*evaluator, *(p for p in (runner.ROOT / "docs" / "skills",) if p.exists())]
    seen = arms.readable_inside(material, work / "r000", binary=raw.harness_binary())
    if seen:
        raise Invalid(f"a contained arm could read the evaluator's material at {', '.join(seen)}: keep it under the "
                      "home directory, outside the lane's work directory, where the arm's layout hides it")
    return True


def run(frozen: dict[str, Any], *, cases: dict[str, Path], lane: Path, evaluator: list[Path] | None = None,
        deadline_s: float = 3600.0, limit: int | None = None) -> dict[str, Any]:
    """Run the cells of ``frozen`` that still need an attempt, in schedule order; at most ``limit`` attempts.

    ``lane`` holds the experiment's ledger (``ledger/``) and scratch (``work/``), outside every git work tree;
    ``evaluator`` names what no arm may read (the key's directory, the cases' source). Returns what happened:
    ``stopped`` is ``done``, ``limit``, ``budget`` or ``lane_error``. Raises :class:`aew_eval.schemas.Invalid` before
    anything is registered when the preregistration is not a paired skill evaluation, and F19's ``Refused`` when its
    runner refuses a cell."""
    pair = plan.shape(frozen)
    ledger_dir, work = lane / "ledger", lane / "work"
    mark = claim(lane, frozen, hidden_from_arms(frozen, work, list(evaluator or [])))
    ledger = AttemptLedger(ledger_dir, frozen)
    policy = frozen["validity_rules"]["retry_policy"]
    budget, caps = float(frozen["profiles"]["budget_usd"]), pair["caps"]
    ran: list[dict[str, Any]] = []

    def out(stopped: str, **more: Any) -> dict[str, Any]:
        return {"stopped": stopped, "ran": ran, "spent_usd": round(spent(ledger, caps), 6), "budget_usd": budget,
                "evaluator_material_hidden": mark["evaluator_material_hidden"], **more}

    with arms.installed():
        for block in plan.blocks(frozen):
            for entry in block:
                cell = entry["cell"]
                while needs_attempt(ledger, cell, policy):
                    if limit is not None and len(ran) >= limit:
                        return out("limit", next_cell=cell)
                    owed = sum(caps[e["arm"]] for e in block if needs_attempt(ledger, e["cell"], policy))
                    if spent(ledger, caps) + owed > budget:
                        return out("budget", next_cell=cell)
                    attempts = of_cell(ledger, cell)
                    record = runner.run_cell(frozen, ledger_dir=ledger_dir, cell=cell, cases=cases, work=work,
                                             run_name=run_name(entry, len(attempts)),
                                             retry_of=attempts[-1].run_id if attempts else None,
                                             deadline_s=deadline_s, defer_scoring=True)
                    ran.append({"run_id": record["run_id"], "validity": record["validity"],
                                "charged_usd": charged(record, caps[entry["arm"]])})
                    if record["validity"]["reason_code"] in LANE_ERRORS:
                        return out("lane_error", reason_code=record["validity"]["reason_code"], cell=cell)
    return out("done")
