"""Stage availability, composed per step from queryable guards (M4-E E4; plan v3 E4; typed surface §3.3, §3.6).

A stage is legal now when each of its steps would be, in order. The composition asks the engine's guards
(:meth:`aew.engine.api.Engine.guard_query`, the same functions the steps' own commits evaluate) and never models
legality itself:

- **step 1** is queried on the current state;
- **a later step** is queried on the current state, with the inputs that earlier steps of the same stage produce
  (declared ``produced_by`` on the catalog row, ``aew.surface.contract``) taken as satisfied: the query sees them as
  the earlier step would leave them (:func:`_overlay`). A step whose only input is an earlier step's dispatch decision
  (``dispatch.launch``) is covered by that decision and not queried (plan v3 §1);
- **any other unmigrated input** (a guard with no query form) makes the step, and so the stage, ``UNKNOWN`` (frozen
  decision 3), never ``BLOCKED``. A step whose producer found nothing to produce (it is blocked) is ``UNKNOWN`` too.

The stage is ``BLOCKED`` when any step is (it would stop there, rule 3), else ``UNKNOWN`` when any step is, else
``AVAILABLE``. ``STAGES`` is the migrated stage table: each row's steps and how the call's arguments become each
step's guard arguments. A stage outside it is ``UNKNOWN``. Availability is legality only: ``auto_runnable`` stays the
classifier's (a judgment-bearing stage never is, m2).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from aew.engine.guards import AVAILABLE, BLOCKED, GUARD_NOT_QUERYABLE, UNKNOWN
from aew.surface import contract

INPUT_NOT_PRODUCED = "INPUT_NOT_PRODUCED"  # an earlier step's guard found nothing for this step to take as produced
PRODUCED_IMPLEMENTER = "<implementer from step {n}>"  # the placeholder id the overlay gives a produced implementer

StepArgs = Callable[[dict[str, Any]], "dict[str, Any] | None"]  # the call's arguments -> the guard's (None: unplanned)


def _same_unit(**fixed: Any) -> StepArgs:
    return lambda a: {"work_id": a.get("work_id"), **fixed}


def _create(a: dict[str, Any]) -> dict[str, Any]:
    """``ticket_draft``'s call as ``work.create``'s request (the CLI's names)."""
    return {"kind": "ticket", "title": a.get("title"), "risk_class": a.get("risk_class"),
            "mutating": not a.get("non_mutating", False), "parent": a.get("parent"),
            "depends_on": a.get("depends_on"), "scope_paths": a.get("scope"), "goal_backwards": a.get("goal"),
            "contract": a.get("contract"), "rationale": a.get("rationale"), "body": a.get("body") or "",
            "card": a.get("card")}


def _propose(a: dict[str, Any]) -> dict[str, Any] | None:
    """``ticket_draft``'s plan as ``plan.propose``'s request; no plan, no step."""
    plan = a.get("plan")
    if plan is None:
        return None
    assurance = plan.get("assurance")
    return {"body": plan.get("body") or "", "reason": plan.get("reason"), "affected_paths": plan.get("affected"),
            "review": None if assurance == "none" else (assurance or {}).get("review"),
            "verify": None if assurance == "none" else (assurance or {}).get("verify"),
            "no_assurance": assurance == "none"}


def _review_ingest(a: dict[str, Any]) -> dict[str, Any]:
    return {"work_id": a.get("work_id"), "evidence": a.get("review_evidence")}


# The migrated stage table (plan v3 E4, M4): per stage, each step's guard arguments, in ``expands_to`` order. Its
# ``produced_by`` is the catalog row's. E4b adds `ticket_prepare` and `integration_publish`.
STAGES: dict[str, tuple[StepArgs, ...]] = {
    "ticket_draft": (_create, _propose),
    "ticket_start": (_same_unit(launch=True), _same_unit(), _same_unit(to="RUNNING")),
    "ticket_request_review": (_same_unit(to="REVIEW_PENDING"), _same_unit(role="reviewer"), _same_unit()),
    "ticket_request_verification": (_review_ingest, _same_unit(to="VERIFY_PENDING"), _same_unit(role="verifier"),
                                    _same_unit()),
}


# ---------------------------------------------------------------------------------------------- produced inputs

def _product(name: str, primitive: str, args: dict[str, Any]) -> Any:
    """What step ``primitive`` (with ``args``, after its query) produces as input ``name``, or None when its query
    found nothing to produce."""
    found = args.get("found") or {}
    if name == contract.STATE:
        return {"work.transition": args.get("to"), "work.assign": "ASSIGNED"}.get(primitive, found.get("to"))
    if name == contract.UNIT:
        return (found["work_id"], found["unit"]) if "unit" in found else None
    if name == contract.EVIDENCE:
        return found.get("ref")
    if name == contract.IMPLEMENTER:
        return primitive == "work.assign" or None
    return None


def _overlay(state: dict[str, Any], work_id: str | None, inputs: list[tuple[str, int, Any]]) -> dict[str, Any]:
    """``state`` as a later step's guard sees it: each produced input applied to a copy (never to ``state``)."""
    scratch = dict(state)
    scratch["work"] = dict(state.get("work") or {})
    for name, n, value in inputs:
        if name == contract.UNIT:
            wid, unit = value
            scratch["work"][wid] = copy.deepcopy(unit)
            continue
        unit = scratch["work"].get(work_id or "")
        if unit is None:
            continue
        unit = scratch["work"][work_id or ""] = dict(unit)
        if name == contract.STATE:
            unit["state"] = value
        elif name == contract.EVIDENCE:
            unit["evidence"] = [*(r for r in unit.get("evidence") or [] if r["id"] != value["id"]), value]
        elif name == contract.IMPLEMENTER:
            inv = PRODUCED_IMPLEMENTER.format(n=n)
            scratch["invocations"] = {**(state.get("invocations") or {}),
                                      inv: {"status": "active", "role": "implementer", "work_unit": work_id}}
            unit["implementer_invocation"] = inv
    return scratch


# ---------------------------------------------------------------------------------------------- the composition

def migrated(stage: str) -> bool:
    return stage in STAGES


def stage_availability(engine: Any, stage: str, arguments: dict[str, Any], *,
                       state: dict[str, Any] | None = None) -> dict[str, Any]:
    """The availability of ``stage`` called with ``arguments`` now, with each step's answer."""
    t = contract.tool(stage)
    current: dict[str, Any] = engine.store.read() if state is None else state
    if t is None or stage not in STAGES:
        return {"stage": stage, "availability": UNKNOWN, "reason_codes": [GUARD_NOT_QUERYABLE], "blockers": [],
                "steps": []}
    done: dict[int, tuple[str, dict[str, Any]]] = {}  # step -> (primitive, its guard's arguments after its query)
    steps: list[dict[str, Any]] = []
    for n, (primitive, build) in enumerate(zip(t.expands_to, STAGES[stage], strict=True), start=1):
        args = build(arguments)
        produced = dict(t.produced_by[n - 1]) if t.produced_by else {}
        entry: dict[str, Any] = {"n": n, "primitive": primitive, "produced_by": produced}
        if args is None:
            steps.append({**entry, "planned": False})
            continue
        if contract.DISPATCH in produced:  # a launch: covered by that step's dispatch decision, nothing of its own
            covering = next(s for s in steps if s["n"] == produced[contract.DISPATCH])
            steps.append({**entry, "covered_by": covering["n"], "availability": covering["availability"],
                          "reason_codes": [], "blocking_conditions": []})
            done[n] = (primitive, args)
            continue
        inputs = [(name, m, _product(name, *done[m])) if m in done else (name, m, None)
                  for name, m in produced.items()]
        missing = [name for name, _m, value in inputs if value is None]
        work_id = args.get("work_id")
        unit_from = next((value for name, _m, value in inputs if name == contract.UNIT and value), None)
        if unit_from is not None:
            work_id = args["work_id"] = unit_from[0]
        if missing:
            steps.append({**entry, "availability": UNKNOWN, "reason_codes": [INPUT_NOT_PRODUCED],
                          "blocking_conditions": [], "not_produced": missing})
            done[n] = (primitive, args)
            continue
        scratch = _overlay(current, work_id, inputs) if inputs else current
        answer = engine.guard_query(primitive, work_id, args, state=scratch)
        steps.append({**entry, **{k: answer[k] for k in ("availability", "reason_codes", "blocking_conditions")},
                      **{k: answer[k] for k in ("not_queryable", "unanswered") if k in answer}})
        done[n] = (primitive, args)
    answers = [s["availability"] for s in steps if s.get("planned", True)]
    overall = BLOCKED if BLOCKED in answers else UNKNOWN if UNKNOWN in answers else AVAILABLE
    reasons = sorted({c for s in steps for c in s.get("reason_codes") or []})
    blockers = [b for s in steps for b in s.get("blocking_conditions") or []]
    return {"stage": stage, "availability": overall, "reason_codes": reasons, "blockers": blockers, "steps": steps}
