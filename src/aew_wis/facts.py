"""WIS-03, the WIS fact rule: the only place a work unit's WIS facts are computed.

The issuer applies it to the control state whose bytes it verified (WIS-02), and carriers copy its output and never
compute it (WIS-08). The control-state fields behind each row are the engine's own (the profile leaves them to the
build): a unit's ``kind`` and ``state``; its accepted plan revision, ``plan.accepted``, an integer the engine sets when
the Lead accepts a plan; and its ``blocked_by``, the readiness blockers ``aew.engine.dependencies.recompute_readiness``
writes, each a mapping whose ``id`` names the work unit it waits on (a plan blocker names none).

Two of the rule's mappings are also derived today by STG-02's backend (``aew.stg02.world.WAITING_STATES`` and
``aew.stg02.reads._revision``), which WIS-03 moves into the issuer and WIS-C's carrier will copy from the attestation
(WIS-08). Until then a test requires the two derivations to agree for every engine state, and ``eligible`` to be the
engine's own dispatch rule (the states ``aew.engine.transitions.RULES`` lets ``assign`` leave).
"""

from __future__ import annotations

import re
from typing import Any

# WIS-03's ``cause`` mapping, the one the STG-02 backend uses today: BLOCKED is a dependency; ESCALATED and
# REPLAN_REQUIRED wait on the operator or the Lead; the review and verification failures wait on a required result;
# anything else is unknown.
CAUSE = {"BLOCKED": "dependency", "ESCALATED": "operator_need", "REPLAN_REQUIRED": "operator_need",
         "REVIEW_FAILED": "mandatory_result", "VERIFICATION_FAILED": "mandatory_result",
         "VERIFICATION_INCONCLUSIVE": "mandatory_result"}
# The C18 WIS axis: ``ok`` when the unit is eligible to continue (the states the engine dispatches from), ``blocked``
# in the three waiting states WIS-03 names, else ``unknown``.
ELIGIBLE = frozenset({"READY"})
AXIS_BLOCKED = frozenset({"BLOCKED", "ESCALATED", "REPLAN_REQUIRED"})
KINDS = frozenset({"ticket", "story", "epic"})
STATE = re.compile(r"[A-Z][A-Z_]{0,40}")  # the wire's WisFact.state pattern


class NotAFact(ValueError):
    """A work unit the rule cannot derive facts from: the control state is not one the issuer may attest (WIS-02's
    ``STORE_UNREADABLE``, which changes nothing)."""


def work_revision(unit: dict[str, Any]) -> str | None:
    """``work.revision``: the accepted plan revision as ``plan-<n>``, or None when no plan is accepted."""
    accepted = (unit.get("plan") or {}).get("accepted")
    if accepted is None:
        return None
    if isinstance(accepted, bool) or not isinstance(accepted, int) or accepted < 1:
        raise NotAFact(f"plan.accepted is {accepted!r}, not a revision number")
    return f"plan-{accepted}"


def blocked_by(unit: dict[str, Any]) -> list[str]:
    """``blocked_by``: the ids of the work units the unit's readiness blockers name, sorted and unique."""
    raw = unit.get("blocked_by") or []
    if not isinstance(raw, list):
        raise NotAFact("blocked_by is not a list")
    ids = set()
    for b in raw:
        if not isinstance(b, dict):
            raise NotAFact("a blocked_by entry is not a mapping")
        wid = b.get("id")
        if wid is None:
            continue  # a plan blocker: it names no work unit
        if not isinstance(wid, str) or not 1 <= len(wid) <= 128:
            raise NotAFact(f"a blocked_by id is {wid!r}")
        ids.add(wid)
    return sorted(ids)


def unit_facts(work_id: str, unit: Any) -> dict[str, Any]:
    if not isinstance(unit, dict):
        raise NotAFact(f"work unit {work_id!r} is not a mapping")
    kind, state = unit.get("kind"), unit.get("state")
    if kind not in KINDS:
        raise NotAFact(f"work unit {work_id!r} has kind {kind!r}")
    if not isinstance(state, str) or not STATE.fullmatch(state):
        raise NotAFact(f"work unit {work_id!r} has state {state!r}")
    return {"work_id": work_id, "kind": kind, "revision": work_revision(unit), "state": state,
            "blocked_by": blocked_by(unit), "cause": CAUSE.get(state, "unknown"),
            "axis_state": "ok" if state in ELIGIBLE else "blocked" if state in AXIS_BLOCKED else "unknown"}


def facts(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """WIS-03: every work unit's facts, keyed by work id, from a verified control state."""
    work = state.get("work")
    if not isinstance(work, dict):
        raise NotAFact("the control state has no work units mapping")
    out = {}
    for wid in sorted(work):
        if not isinstance(wid, str) or not 1 <= len(wid) <= 128:
            raise NotAFact(f"a work id is {wid!r}")
        out[wid] = unit_facts(wid, work[wid])
    return out
