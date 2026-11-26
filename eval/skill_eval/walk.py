"""A frozen schedule walked block by block under its preregistered budget: the part of a lane that knows no skill.

Nothing here imports the skill evaluation: it reads a frozen ``aew/eval-prereg/v1`` record and F19's ledger, and gives
each cell that still needs an attempt to F19's runner (:func:`aew_eval.runner.run_cell`). It is written to be lifted
into ``eval/aew_eval`` as the shared walker for paired cells (the operator, 2026-11-26); :mod:`skill_eval.run` adds
what a skill evaluation needs around it.

* **Blocks.** A block is one case and repetition's cells, in their drawn order (:func:`blocks`).
* **Budget.** Every attempt is charged: its reported cost, or its arm's cap when the cost is unknown or the attempt
  was lost (``aew_eval.raw.charged``). A cell starts only while what is spent, plus the caps of every cell its block
  still needs, fits ``budget_usd``; otherwise the walk stops with nothing started, so a block is never begun that the
  budget cannot finish. Two limits: the charge is the cost the harness reports, so a reported 0 is charged 0, and a
  run's cap is enforced by the arm between polls, so one run can end somewhat above its cap.
* **Retries** are the frozen policy's, which the ledger enforces: a cell whose latest attempt is valid, or whose
  policy allows no further one, is left as it is. A model's failure is an outcome, never retried into a pass.
* **A lane error stops the walk.** An attempt that measured the host and not the model (:func:`lane_error`: the
  host-side reasons, an arm that raised, a runner error) would repeat in every later cell, so the walk ends there
  and says why, as the lower-bound lane's does. The attempt it stopped on is still counted, under the frozen policy.
* **Names.** A run is named for its place in the schedule (``r007``), so under a randomized order neither a run's
  id nor its folder names its arm.
* **Resumable.** What has run is the ledger's, so a second walk continues where the first stopped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aew_eval import raw, runner
from aew_eval.ledger import Attempt, AttemptLedger

# Why an attempt cannot count that every later cell would meet too (``raw.raw_invalid``'s host-side reasons, the
# runner's own for a model that is not the pinned one, and an arm or a runner that raised: ``ARM_ERROR`` and every
# ``RUNNER_ERROR:<type>``): the host or the key needs fixing, not another attempt. The walk resumes once it is.
LANE_ERRORS = ("CONTAINMENT_FAILED", "HARNESS_MISMATCH", "NO_MODEL_STEP", "PROVIDER_KEY_RETAINED", "PROFILE_MISMATCH",
               "ARM_ERROR")
RUNNER_ERROR = "RUNNER_ERROR:"  # the runner's prefix for an exception around the arm (aew_eval.runner.run_cell)


def lane_error(reason_code: str | None) -> bool:
    return bool(reason_code) and (reason_code in LANE_ERRORS or str(reason_code).startswith(RUNNER_ERROR))


def blocks(frozen: dict[str, Any]) -> list[list[dict[str, Any]]]:
    """The frozen schedule as its blocks: for each case and repetition, its cells in their drawn order."""
    out: list[list[dict[str, Any]]] = []
    for entry in frozen["assignment"]["order"]:
        if out and (out[-1][0]["case"], out[-1][0]["repetition"]) == (entry["case"], entry["repetition"]):
            out[-1].append(entry)
        else:
            out.append([entry])
    return out


def caps(frozen: dict[str, Any]) -> dict[str, float]:
    """Each arm's charge when an attempt's cost is unknown: its ``cap_usd``, or nothing for an arm that has none."""
    return {a["id"]: float(a["config"].get("cap_usd") or 0.0) for a in frozen["arms"]}


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


def spent(ledger: AttemptLedger, arm_caps: dict[str, float]) -> float:
    return sum(charged(record_of(ledger, a), arm_caps[a.registered["arm"]]) for a in ledger.attempts().values())


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


def walk(frozen: dict[str, Any], *, cases: dict[str, Path], ledger_dir: Path, work: Path,
         deadline_s: float = 3600.0, limit: int | None = None) -> dict[str, Any]:
    """Run the cells of ``frozen`` that still need an attempt, in schedule order; at most ``limit`` attempts.

    Returns what happened: ``stopped`` is ``done``, ``limit``, ``budget`` or ``lane_error``, with what ran and what
    is spent. Raises F19's ``Refused`` when its runner refuses a cell, with nothing registered by that call."""
    ledger = AttemptLedger(ledger_dir, frozen)
    policy = frozen["validity_rules"]["retry_policy"]
    budget, arm_caps = float(frozen["profiles"]["budget_usd"]), caps(frozen)
    ran: list[dict[str, Any]] = []

    def out(stopped: str, **more: Any) -> dict[str, Any]:
        return {"stopped": stopped, "ran": ran, "spent_usd": round(spent(ledger, arm_caps), 6), "budget_usd": budget,
                **more}

    for block in blocks(frozen):
        for entry in block:
            cell = entry["cell"]
            while needs_attempt(ledger, cell, policy):
                if limit is not None and len(ran) >= limit:
                    return out("limit", next_cell=cell)
                owed = sum(arm_caps[e["arm"]] for e in block if needs_attempt(ledger, e["cell"], policy))
                if spent(ledger, arm_caps) + owed > budget:
                    return out("budget", next_cell=cell)
                attempts = of_cell(ledger, cell)
                record = runner.run_cell(frozen, ledger_dir=ledger_dir, cell=cell, cases=cases, work=work,
                                         run_name=run_name(entry, len(attempts)),
                                         retry_of=attempts[-1].run_id if attempts else None,
                                         deadline_s=deadline_s, defer_scoring=True)
                ran.append({"run_id": record["run_id"], "validity": record["validity"],
                            "charged_usd": charged(record, arm_caps[entry["arm"]])})
                if lane_error(record["validity"]["reason_code"]):
                    return out("lane_error", reason_code=record["validity"]["reason_code"], cell=cell)
    return out("done")
