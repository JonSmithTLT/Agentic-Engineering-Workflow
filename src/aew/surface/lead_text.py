"""Render the Lead guide and derive stage metadata from the typed surface for the E130 conformance check."""

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

    MS3 limit: message_send has no Ticket-path move, so the rendered guide does not name it even when selected here.
    Switch-aware guide/system guidance belongs to the reply/attention slice.
    """
    return tuple(guide.Stage(t.name, t.description, _steps(t), SA.STARTS_AT.get(t.name, {}))
                 for t in contract.exposed(profile, switches) if t.expands_to)


def render(gates_policy: dict[str, Any], checks_policy: dict[str, Any]) -> str:
    """The loaded guide for a policy."""
    return guide.render(gates_policy, checks_policy)


def guide_for(engine: Any) -> str:
    """The guide for this project's own policy (the CLI and the Lead's system text)."""
    return str(engine.lead_guide())


def guide_section_for(engine: Any, section: str) -> str:
    """One on-demand section, rendered from the project's adopted gates."""
    return guide.render_section(section, engine.policy("gates"))
