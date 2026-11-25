"""The Lead's guide with its stages, from the catalog (E130; the operator, 2026-11-04: nobody keeps this text by hand).

The guide (:mod:`aew.engine.guide`) renders the Ticket path, and the engine never imports this package, so what it says
about the typed tools is handed to it as data. This module builds that data from the two owners of a stage's contract:
the catalog row (:mod:`aew.surface.contract`: its name, description and ``expands_to``) and the migrated stage table
(:data:`aew.surface.availability.STAGES`: each step's guard arguments, which say a transition's target and a dispatch's
role and scope). A stage added to the catalog takes over the steps of the path it covers with no edit here or there.
"""

from __future__ import annotations

from typing import Any

from aew.engine import guide
from aew.surface import availability as SA
from aew.surface import contract
from aew.surface.context import NORMAL

# Standing in for the call's arguments, to read what a step's guard arguments say about the step.
_PROBE = {"work_id": "<T>"}


def _qualifier(args: dict[str, Any] | None) -> str | None:
    """What tells this step from another of the same primitive: a transition's target, a dispatch's scope or role."""
    if not args:
        return None
    return args.get("to") or args.get("scope") or args.get("role")


def _steps(t: contract.Tool) -> tuple[guide.StageStep, ...]:
    builders = SA.STAGES.get(t.name)
    applies = SA.APPLIES.get(t.name, {})
    starts = SA.STARTS_AT.get(t.name, {})
    if builders is None:  # not migrated: its primitives are all the catalog says about its steps
        return tuple(guide.StageStep(p) for p in t.expands_to)
    # A step skipped only by a later start is not optional: `Stage.starts` says from which states it is skipped.
    return tuple(guide.StageStep(p, _qualifier(build(_PROBE)), build(_PROBE) is None
                                 or (n in applies and not any(n < at for at in starts.values())))
                 for n, (p, build) in enumerate(zip(t.expands_to, builders, strict=True), start=1))


def stages(profile: str = NORMAL, switches: frozenset[str] = frozenset()) -> tuple[guide.Stage, ...]:
    """The tools on ``profile`` with standard descriptions, independent of MCP's budgeted presentation.

    Coordination is not a Ticket-path move; its on-only guidance comes from the shared harness guide owner.
    """
    return tuple(guide.Stage(t.name, t.description, _steps(t), SA.STARTS_AT.get(t.name, {}))
                 for t in contract.exposed(profile, switches) if t.expands_to)


# When the Lead reaches for each typed tool that is not a step of the Ticket path (E231: the core's map of the tools).
# The path's stages need no line here: the core derives them from the transition table. A test fails when a tool the
# Lead is offered is named nowhere in the core, or a line here names no tool in the catalog.
WHEN = {
    "status": "the state and your next actions, or one unit's control record",
    "resume": "first, after any restart",
    "work_show": "one unit in full: its plans, evidence, gates and integration",
    "explain": "why a dispatch or a stage's step is blocked now, before you retry it",
    "harness_status": "a run's record; for a lost run, the way to relaunch it",
    "harness_wait": "to wait on runs; never poll",
    "checkpoint": "before a pause or a handoff",
    "steering": "to lower your steering mode, or to ask the operator to raise it or to confirm an action",
    "message_send": "to steer a running worker",
}


def uses(profile: str = NORMAL, switches: frozenset[str] = frozenset()) -> tuple[guide.ToolUse, ...]:
    """The tools on ``profile`` that have a line in :data:`WHEN`, in catalog order."""
    return tuple(guide.ToolUse(t.name, WHEN[t.name]) for t in contract.exposed(profile, switches) if t.name in WHEN)


def document(gates_policy: dict[str, Any], checks_policy: dict[str, Any], *,
             switches: frozenset[str] = frozenset()) -> guide.Guide:
    """The guide for a policy, core and sections, with the normal profile's stages and tools for the supplied
    switches."""
    return guide.document(gates_policy, checks_policy, stages(switches=switches),
                          messaging=contract.MESSAGING in switches, uses=uses(switches=switches))


def render(gates_policy: dict[str, Any], checks_policy: dict[str, Any], *,
           switches: frozenset[str] = frozenset()) -> str:
    """The guide's core for a policy: what the Lead's system text carries."""
    return document(gates_policy, checks_policy, switches=switches).core


def document_for(engine: Any, *, switches: frozenset[str] | None = None) -> guide.Guide:
    """The guide for this project's own policy, core and sections (`aew guide`)."""
    from aew.surface.context import switches_for

    selected = switches_for(engine) if switches is None else switches
    return engine.lead_guide_document(stages(switches=selected), uses=uses(switches=selected),
                                      **({"messaging": True} if contract.MESSAGING in selected else {}))


def guide_for(engine: Any, *, switches: frozenset[str] | None = None) -> str:
    """The guide's core for this project's own policy: the Lead's system text carries it."""
    return str(document_for(engine, switches=switches).core)
