"""A Ticket's scheduling priority (register E227): the order the steering loop starts eligible Tickets in.

The operator, 2026-11-08: the steering loop under `RUN` is "95% what I meant" by a scheduler, and the rest is priority,
a field with three levels. It is the Lead's judgment, set when the Ticket is drafted (`ticket_draft`, `aew work create
--priority`) and fixed after that (the operator, 2026-11-10: it is "not a field that would cause us to have to throw a
ticket away if its wrong"); changing it later is a register row of its own.

This module owns the levels, a unit's level, and the order the loop's ``select`` takes Tickets in. The priority is
scheduling, never legality: no guard, gate, transition, dispatch or ingest reads it, and the Ticket field registry
puts it in a group of its own, `scheduling`, that is not material, so it never stales a Ticket's evidence.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from aew.engine import hierarchy
from aew.priority_levels import DEFAULT, LEVELS, LOWEST

__all__ = ["DEFAULT", "LEVELS", "LOWEST", "WAITING", "age", "of", "order", "unblocks", "waiting_age"]

# A Ticket that has not started yet: the only one `status` says is waiting (review of the priority PR, m2).
WAITING = frozenset({"READY", "BLOCKED"})


def of(unit: Mapping[str, Any]) -> dict[str, Any]:
    """A unit's priority as ``{"level", "reason"}``: a Ticket drafted before priorities existed, or with none given,
    is ``normal`` with no reason."""
    found = unit.get("priority") or {}
    return {"level": found.get("level") or DEFAULT, "reason": found.get("reason")}


def unblocks(state: dict[str, Any]) -> dict[str, int]:
    """How many live Tickets each unit unblocks (E227: "how many Tickets each unblocks"): the live Tickets with an
    effective dependency edge on it, their own or inherited from an ancestor (``hierarchy.effective_edges``), derived
    from the graph each time, never kept. Stories and Epics are not counted, so the hierarchy's depth never changes the
    order. The limit: an edge to a Story credits none of the Story's Tickets, so a Ticket inside a Story that others
    wait on counts nothing for it."""
    out: dict[str, int] = {}
    for wid, unit in state["work"].items():
        if unit.get("kind") != "ticket" or unit.get("state") in hierarchy.TERMINAL:
            continue
        for target in {e["id"] for e in hierarchy.effective_edges(state, wid)}:
            out[target] = out.get(target, 0) + 1
    return out


def order(state: dict[str, Any]) -> dict[str, tuple[int, int, str]]:
    """Each Ticket's place in the loop's order: by level (``critical`` first), then by how many live Tickets it
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


def waiting_age(unit: Mapping[str, Any], now: dt.datetime) -> str | None:
    """How long a lowest-priority Ticket that has not started has waited (E227: "each `low` Ticket's age"), or None:
    a Ticket of another level, one that has started or finished, or one whose creation time can't be read."""
    if of(unit)["level"] != LOWEST or unit.get("state") not in WAITING:
        return None
    return age(unit, now)
