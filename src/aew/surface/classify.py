"""Effective operation class and auto-run eligibility (typed-lead-surface-design-v0.2 §3.2, §3.3, §3.5, §12.7).

A catalog row has a base class; every invocation has an effective one, computed here and only here. It never drops
below the base, any judgment input promotes it to ``JUDGMENT_BEARING``, and whatever cannot be classified fails
closed to ``JUDGMENT_BEARING`` (an unknown tool, an undeclared primitive).

``auto_runnable`` is a separate fact from availability (legality) and from whether a caller can call the tool (its
profile): it means a stage runner may advance the workflow with this action without a Lead judgment. Queries, waits,
the checkpoint and the recovery escape are never auto-runnable, and the caller's profile is never an input.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aew.engine.guards import AVAILABLE, BLOCKED, UNKNOWN
from aew.engine.primitives import JUDGMENT_BEARING, MECHANICAL, POLICY_RESOLVED, spec_for
from aew.surface.contract import Tool

__all__ = ["AVAILABLE", "BLOCKED", "RANK", "RUN_AUTO_RUN", "UNKNOWN", "auto_run_set", "auto_runnable",
           "effective_class"]  # availability: one source
RANK = {MECHANICAL: 0, POLICY_RESOLVED: 1, JUDGMENT_BEARING: 2}


def _max(*classes: str) -> str:
    return max(classes, key=lambda c: RANK.get(c, RANK[JUDGMENT_BEARING]))


def effective_class(t: Tool | None, arguments: dict[str, Any] | None = None) -> str:
    """The operation class of one invocation of ``t`` with ``arguments``."""
    if t is None:
        return JUDGMENT_BEARING
    out = t.base_class
    if t.required_judgments or any(arguments and name in arguments for name in t.promotes):
        out = _max(out, JUDGMENT_BEARING)
    for primitive in t.expands_to:
        out = _max(out, spec_for(primitive).operation_class)  # undeclared: JUDGMENT_BEARING (fail closed)
    return out


# Register E83 (R01-38; the operator's R-DEC-04, 2026-10-25): the only shipped stages a stage runner may auto-run, and
# only under Run (Walk confirms both: each changes more than control state). ``auto_run_set`` derives the set from
# the contract by ``auto_runnable``'s own rule; a test holds the two equal, so a stage joining or leaving it is a
# decision, never a side effect of a contract edit.
RUN_AUTO_RUN = frozenset({"ticket_start", "ticket_request_review"})


def auto_run_set(tools: Mapping[str, Tool]) -> frozenset[str]:
    """The tools of ``tools`` that ``auto_runnable`` can ever admit: built progression rows whose class with no
    arguments is not judgment-bearing (an argument can only promote a class, never lower it)."""
    return frozenset(name for name, t in tools.items()
                     if t.progression and t.built and effective_class(t) != JUDGMENT_BEARING)


def auto_runnable(t: Tool | None, availability: str, operation_class: str) -> bool:
    """Eligible for the stage runner to execute without judgment: a built progression row, legal now, not
    judgment-bearing. The profile is deliberately not a parameter."""
    return (t is not None and t.progression and t.built and availability == AVAILABLE
            and operation_class != JUDGMENT_BEARING)
