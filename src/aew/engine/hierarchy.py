"""Epic/Story/Ticket hierarchy semantics (WC §7, §8; KC §9; ADR-0007). Pure functions over control state.

* Parent (Story/Epic) state is **derived**, never hand-maintained (WC §8): the phase follows from the
  children plus two recorded Lead decisions (closeout, cancellation).
* Child failure or blocking never changes the parent's phase; it shows as derived ``attention`` and
  ``blocked`` facts that resume/status surface to the Lead.
* Dependencies may point at any unit and are inherited by descendants; cycles are refused on a
  "waits-for" graph that includes inherited edges and parents waiting on their descendants.
"""

from __future__ import annotations

import hashlib
from typing import Any

PARENT_KINDS = {"ticket": {"story", "epic"}, "story": {"epic"}, "epic": set()}
PARENT_STATES = ("PLANNING", "IN_PROGRESS", "ACCEPTANCE_PENDING", "DONE", "CANCELLED")
TERMINAL = frozenset({"DONE", "CANCELLED"})
# Child states that need a Lead decision; surfaced on every ancestor.
ATTENTION_STATES = frozenset({"REPLAN_REQUIRED", "VERIFICATION_FAILED", "INTERRUPTED", "ESCALATED"})


def is_parent(unit: dict[str, Any]) -> bool:
    return unit["kind"] != "ticket"


def children(state: dict[str, Any], work_id: str) -> list[str]:
    return sorted(wid for wid, u in state["work"].items() if u.get("parent") == work_id)


def descendants(state: dict[str, Any], work_id: str) -> list[str]:
    out: list[str] = []
    stack = children(state, work_id)
    while stack:
        wid = stack.pop(0)
        out.append(wid)
        stack.extend(children(state, wid))
    return out


def ancestors(state: dict[str, Any], work_id: str) -> list[str]:
    out = []
    parent = state["work"][work_id].get("parent")
    while parent:
        out.append(parent)
        parent = state["work"][parent].get("parent")
    return out


def depth(state: dict[str, Any], work_id: str) -> int:
    return len(ancestors(state, work_id))


def derive_parent(state: dict[str, Any], work_id: str) -> dict[str, Any]:
    """The derived phase, attention list and blocked flag of a Story/Epic."""
    unit = state["work"][work_id]
    kids = children(state, work_id)
    if unit.get("cancellation"):
        phase = "CANCELLED"
    elif unit.get("closeout"):
        phase = "DONE"
    elif not kids:
        phase = "PLANNING"
    elif all(state["work"][k]["state"] in TERMINAL for k in kids):
        phase = "ACCEPTANCE_PENDING"
    else:
        phase = "IN_PROGRESS"
    attention = []
    open_tickets = []
    for wid in descendants(state, work_id):
        u = state["work"][wid]
        if u["state"] in ATTENTION_STATES:
            attention.append(f"{wid} is {u['state']}")
        if u["kind"] == "ticket" and u["state"] not in TERMINAL:
            open_tickets.append(u["state"])
    failed = (unit.get("parent_verification") or {}).get("awaiting_classification")
    if failed:
        attention.append(f"parent verification {failed} failed: classify it (`aew verify classify {work_id}`)")
    blocked = bool(open_tickets) and all(s == "BLOCKED" for s in open_tickets)
    return {"state": phase, "attention": attention, "blocked": blocked}


def recompute_parents(state: dict[str, Any], *, at: str) -> list[str]:
    """Bring every parent's stored (derived) state up to date. Part of every Lead commit."""
    changed = []
    parents = sorted((wid for wid, u in state["work"].items() if is_parent(u)),
                     key=lambda w: -depth(state, w))
    for wid in parents:
        unit = state["work"][wid]
        derived = derive_parent(state, wid)
        unit["attention"] = derived["attention"]
        unit["blocked_descendants"] = derived["blocked"]
        if unit["state"] != derived["state"]:
            unit.setdefault("history", []).append(
                {"from": unit["state"], "to": derived["state"], "at": at, "reason": "derived from child work"})
            unit["state"] = derived["state"]
            unit["state_reason"] = "derived from child work"
            changed.append(wid)
    return changed


def children_digest(state: dict[str, Any], work_id: str, completion_sha: dict[str, str | None]) -> str:
    """Identity of a parent's child set: ids, states and completion-record hashes (parent snapshot)."""
    h = hashlib.sha256()
    for wid in children(state, work_id):
        h.update(f"{wid}\0{state['work'][wid]['state']}\0{completion_sha.get(wid) or '-'}\n".encode())
    return h.hexdigest()


def effective_edges(state: dict[str, Any], work_id: str) -> list[dict[str, Any]]:
    """A unit's own dependency edges plus every edge declared on its ancestors (inherited)."""
    edges = [dict(e, inherited_from=None) for e in state["work"][work_id].get("depends_on", [])]
    for anc in ancestors(state, work_id):
        edges += [dict(e, inherited_from=anc) for e in state["work"][anc].get("depends_on", [])]
    return edges


def waits_for(state: dict[str, Any], work_id: str) -> set[str]:
    """Units that must complete before ``work_id`` can: its effective edges, and (for a parent) its children."""
    out = {e["id"] for e in effective_edges(state, work_id)}
    if is_parent(state["work"][work_id]):
        out.update(children(state, work_id))
    return out


def find_cycle(state: dict[str, Any]) -> list[str] | None:
    """A cycle in the waits-for graph (direct, inherited and hierarchical waits), or None."""
    color: dict[str, int] = {}
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = 1
        path.append(node)
        for nxt in sorted(waits_for(state, node)):
            if nxt not in state["work"]:
                continue
            if color.get(nxt) == 1:
                return path[path.index(nxt):] + [nxt]
            if color.get(nxt) is None:
                found = visit(nxt)
                if found:
                    return found
        path.pop()
        color[node] = 2
        return None

    for wid in sorted(state["work"]):
        if color.get(wid) is None:
            found = visit(wid)
            if found:
                return found
    return None
