"""A Ticket's scheduling priority (register E227): the order the steering loop starts eligible Tickets in.

The operator, 2026-11-08: the steering loop under `RUN` is "95% what I meant" by a scheduler, and the rest is priority,
a field with three levels. It is the Lead's judgment, set when the Ticket is drafted (`ticket_draft`, `aew work create
--priority`) and fixed after that (the operator, 2026-11-10: it is "not a field that would cause us to have to throw a
ticket away if its wrong"); changing it later is a register row of its own.

This module owns the levels, a unit's level, and the order the loop's ``select`` takes Tickets in. The priority is
scheduling, never legality: no guard, gate, transition, dispatch or ingest reads it, and the Ticket field registry
puts it in a group of its own that is not material, so it never stales a Ticket's evidence (registry v2).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from aew.engine import hierarchy
from aew.schemas import schema

# The control schema owns the levels, highest first (``work_unit.priority.level``), so the Lead's tool, which the MCP
# process serves without the engine, derives them from the same place. The loop starts a `low` Ticket only when no
# `critical` or `normal` one is eligible.
LEVELS: tuple[str, ...] = tuple(
    schema("control")["$defs"]["work_unit"]["properties"]["priority"]["properties"]["level"]["enum"])
DEFAULT = "normal"


def of(unit: Mapping[str, Any]) -> dict[str, Any]:
    """A unit's priority as ``{"level", "reason"}``: a Ticket drafted before priorities existed, or with none given,
    is ``normal`` with no reason."""
    found = unit.get("priority") or {}
    return {"level": found.get("level") or DEFAULT, "reason": found.get("reason")}


def unblocks(state: dict[str, Any]) -> dict[str, int]:
    """How many live units each unit unblocks: the live units with an effective dependency edge on it (own or
    inherited from an ancestor, ``hierarchy.effective_edges``), derived from the graph each time, never kept."""
    out: dict[str, int] = {}
    for wid, unit in state["work"].items():
        if unit.get("state") in hierarchy.TERMINAL:
            continue
        for target in {e["id"] for e in hierarchy.effective_edges(state, wid)}:
            out[target] = out.get(target, 0) + 1
    return out


def order(state: dict[str, Any]) -> dict[str, tuple[int, int, str]]:
    """Each Ticket's place in the loop's order: by level (``critical`` first), then by how many live units it
    unblocks (more first), then by id. A lower tuple comes first."""
    counts = unblocks(state)
    return {wid: (LEVELS.index(of(unit)["level"]), -counts.get(wid, 0), wid)
            for wid, unit in state["work"].items() if unit.get("kind") == "ticket"}


def age(unit: Mapping[str, Any], now: dt.datetime) -> str | None:
    """How long a Ticket has waited since it was drafted, for a `low` one in `status` (E227): whole days, else hours,
    else minutes. None when its creation time can't be read."""
    try:
        created = dt.datetime.fromisoformat(str(unit.get("created_at")).replace("Z", "+00:00"))
    except ValueError:
        return None
    seconds = max(0, int((now - created).total_seconds()))
    if seconds >= 86400:
        return f"{seconds // 86400}d"
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"
