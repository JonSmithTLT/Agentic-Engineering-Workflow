"""Epic/Story/Ticket hierarchy semantics (WC §7, §8; KC §9; ADR-0007). Pure functions over control state.

* Parent (Story/Epic) state is **derived**, never hand-maintained (WC §8): the phase follows from the
  children plus two recorded Lead decisions (closeout, cancellation).
* Child failure or blocking never changes the parent's phase; it shows as derived ``attention`` and
  ``blocked`` facts that resume/status surface to the Lead.
* Dependencies may point at any unit and are inherited by descendants; cycles are refused on a
  "waits-for" graph that includes inherited edges and parents waiting on their descendants.

ADR-0011 (control state v2): finished units leave the hot state. A parent's archived children are counted in its
``archived_children`` summary (plan R3), so derivation reads hot children and that summary, never the history; an
edge to an archived unit reads the facts kept in ``archived_refs`` through ``upstream`` (R4).
"""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any

PARENT_KINDS = {"ticket": {"story", "epic"}, "story": {"epic"}, "epic": set()}
PARENT_STATES = ("PLANNING", "IN_PROGRESS", "ACCEPTANCE_PENDING", "DONE", "CANCELLED")
TERMINAL = frozenset({"DONE", "CANCELLED"})
# Child states that need a Lead decision; surfaced on every ancestor.
ATTENTION_STATES = frozenset({"REPLAN_REQUIRED", "VERIFICATION_FAILED", "INTERRUPTED", "ESCALATED"})


def is_parent(unit: dict[str, Any]) -> bool:
    return unit["kind"] != "ticket"


def children_map(state: dict[str, Any]) -> dict[str, list[str]]:
    """Every hot parent's children, sorted: one pass over the units (a walk calling ``children`` per node would scan
    every unit once per descendant)."""
    out: dict[str, list[str]] = {}
    for wid in sorted(state["work"]):
        parent = state["work"][wid].get("parent")
        if parent:
            out.setdefault(parent, []).append(wid)
    return out


def children(state: dict[str, Any], work_id: str) -> list[str]:
    return sorted(wid for wid, u in state["work"].items() if u.get("parent") == work_id)


def descendants(state: dict[str, Any], work_id: str, kids: dict[str, list[str]] | None = None) -> list[str]:
    """Breadth-first, as before; ``kids`` (``children_map``) lets a caller that walks several parents build it once."""
    kids = children_map(state) if kids is None else kids
    out: list[str] = []
    queue = deque(kids.get(work_id, []))
    while queue:
        wid = queue.popleft()
        out.append(wid)
        queue.extend(kids.get(wid, []))
    return out


def is_v2(state: dict[str, Any]) -> bool:
    return state.get("schema") == "aew/control/v2"


def archived_summary(unit: dict[str, Any]) -> dict[str, Any]:
    """A parent's archived children (R3): counts, the DONE Tickets anywhere below, and the digest accumulator."""
    return {"done": 0, "cancelled": 0, "done_tickets_subtree": 0, "cancelled_tickets_subtree": 0, "acc": "0" * 64,
            **(unit.get("archived_children") or {})}


def upstream(state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
    """The unit a dependency edge names: hot, or the facts ``archived_refs`` keeps for an archived one (R4), shaped like
    a unit for what edges read (kind, state, mutating, integration commit, accepted record, integration frontier)."""
    unit = state["work"].get(work_id)
    if unit is not None:
        return unit
    ref = (state.get("archived_refs") or {}).get(work_id)
    if ref is None:
        return None
    return {"kind": ref["kind"], "state": ref["state"], "mutating": ref.get("mutating"), "archived": True,
            "integration": {"commit": ref["integration_commit"]} if ref.get("integration_commit") else None,
            "execution": {"record": ref["record"]} if ref.get("record") else None,
            "integration_frontier": ref.get("integration_frontier") or {},
            "completion_sha256": ref.get("completion_sha256")}


def ancestors(state: dict[str, Any], work_id: str) -> list[str]:
    out = []
    parent = state["work"][work_id].get("parent")
    while parent:
        out.append(parent)
        parent = state["work"][parent].get("parent")
    return out


def depth(state: dict[str, Any], work_id: str) -> int:
    return len(ancestors(state, work_id))


def derive_parent(state: dict[str, Any], work_id: str, kid_map: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """The derived phase, attention list and blocked flag of a Story/Epic. Archived children are counted in its
    summary: they are finished, so they never need attention and never block (R3)."""
    unit = state["work"][work_id]
    kid_map = children_map(state) if kid_map is None else kid_map
    kids = kid_map.get(work_id, [])
    archived = archived_summary(unit)
    if unit.get("cancellation"):
        phase = "CANCELLED"
    elif unit.get("closeout"):
        phase = "DONE"
    elif not kids and not (archived["done"] or archived["cancelled"]):
        phase = "PLANNING"
    elif all(state["work"][k]["state"] in TERMINAL for k in kids):
        phase = "ACCEPTANCE_PENDING"
    else:
        phase = "IN_PROGRESS"
    attention = []
    open_tickets = []
    for wid in descendants(state, work_id, kid_map):
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
    kid_map = children_map(state)  # parent links do not change here, only derived states
    for wid in parents:
        unit = state["work"][wid]
        derived = derive_parent(state, wid, kid_map)
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
    """Identity of a parent's child set: ids, states and completion-record hashes (parent snapshot).

    v2 (R3): the archived children enter through the parent's summary, ``SHA-256("aew-children-v2\0" || done || "\0"
    || cancelled || "\0" || acc || "\0" || the v1 lines over the hot children)``, so the digest never reads the
    history and still changes with any archived child (counts and the pinned accumulator)."""
    h = hashlib.sha256()
    if is_v2(state):
        s = archived_summary(state["work"][work_id])
        h.update(f"aew-children-v2\0{s['done']}\0{s['cancelled']}\0{s['acc']}\0".encode())
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
