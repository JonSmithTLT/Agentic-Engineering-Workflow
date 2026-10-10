"""Effective operation class and auto-run eligibility (typed-lead-surface-design-v0.2 §3.2, §3.3, §3.5, §12.7).

A catalog row has a base class; every invocation has an effective one, computed here and only here. It never drops
below the base, any judgment input promotes it to ``JUDGMENT_BEARING``, and whatever cannot be classified fails
closed to ``JUDGMENT_BEARING`` (an unknown tool, an undeclared primitive).

``auto_runnable`` is a separate fact from availability (legality) and from whether a caller can call the tool (its
profile): it means a stage runner may advance the workflow with this action without a Lead judgment. Queries, waits,
the checkpoint and the recovery escape are never auto-runnable, and the caller's profile is never an input.
"""

from __future__ import annotations

from typing import Any

from aew.engine.guards import AVAILABLE, BLOCKED, UNKNOWN
from aew.engine.primitives import JUDGMENT_BEARING, MECHANICAL, POLICY_RESOLVED, spec_for
from aew.surface.contract import Tool

__all__ = ["AVAILABLE", "BLOCKED", "RANK", "UNKNOWN", "auto_runnable", "effective_class"]  # availability: one source
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


def auto_runnable(t: Tool | None, availability: str, operation_class: str) -> bool:
    """Eligible for the stage runner to execute without judgment: a built progression row, legal now, not
    judgment-bearing. The profile is deliberately not a parameter."""
    return (t is not None and t.progression and t.built and availability == AVAILABLE
            and operation_class != JUDGMENT_BEARING)
