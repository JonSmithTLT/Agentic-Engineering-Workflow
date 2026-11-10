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
    """The tools on ``profile`` that commit a step of the workflow, in catalog order, as the guide reads them."""
    return tuple(guide.Stage(t.name, t.description, _steps(t), SA.STARTS_AT.get(t.name, {}))
                 for t in contract.exposed(profile, switches) if t.expands_to)


def render(gates_policy: dict[str, Any], checks_policy: dict[str, Any]) -> str:
    """The guide for a policy, with the normal profile's stages (the file `docs/guides/lead-guide.md` holds)."""
    return guide.render(gates_policy, checks_policy, stages())


def guide_for(engine: Any) -> str:
    """The guide for this project's own policy (`aew guide`, and the Lead's system text)."""
    from aew.surface.context import switches_for

    return str(engine.lead_guide(stages(switches=switches_for(engine))))
