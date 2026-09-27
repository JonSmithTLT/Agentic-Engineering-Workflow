"""Hierarchy semantics as pure functions over control state (ADR-0007): derived parent state, attention,
inherited edges, cycle refusal and the children digest."""

from __future__ import annotations

import pytest

from aew.engine import hierarchy as H


def unit(kind, state, parent=None, deps=(), **extra):
    return {"kind": kind, "state": state, "parent": parent, "depends_on": [{"id": d, "kind": "evidence"} for d in deps],
            **extra}


def graph(**units):
    return {"work": {wid.replace("_", "-"): u for wid, u in units.items()}}


def test_parent_phase_is_derived_from_children_and_recorded_decisions():
    s = graph(E_1=unit("epic", "PLANNING"))
    assert H.derive_parent(s, "E-1")["state"] == "PLANNING"
    s["work"]["S-1"] = unit("story", "PLANNING", "E-1")
    s["work"]["T-1"] = unit("ticket", "RUNNING", "S-1")
    s["work"]["T-2"] = unit("ticket", "DONE", "S-1")
    assert H.derive_parent(s, "S-1")["state"] == "IN_PROGRESS"
    s["work"]["T-1"]["state"] = "CANCELLED"
    assert H.derive_parent(s, "S-1")["state"] == "ACCEPTANCE_PENDING"  # children complete is not acceptance
    s["work"]["S-1"]["closeout"] = {"decision": "D-9"}
    assert H.derive_parent(s, "S-1")["state"] == "DONE"
    s["work"]["S-1"]["cancellation"] = {"decision": "D-10"}
    assert H.derive_parent(s, "S-1")["state"] == "CANCELLED"


def test_child_failure_never_changes_the_parent_phase_but_raises_attention():
    s = graph(S_1=unit("story", "IN_PROGRESS"), T_1=unit("ticket", "VERIFICATION_FAILED", "S-1"),
              T_2=unit("ticket", "BLOCKED", "S-1"))
    d = H.derive_parent(s, "S-1")
    assert d["state"] == "IN_PROGRESS" and d["attention"] == ["T-1 is VERIFICATION_FAILED"] and not d["blocked"]
    s["work"]["T-1"]["state"] = "DONE"
    assert H.derive_parent(s, "S-1")["blocked"]  # every open descendant is BLOCKED


def test_attention_bubbles_to_every_ancestor():
    s = graph(E_1=unit("epic", "IN_PROGRESS"), S_1=unit("story", "IN_PROGRESS", "E-1"),
              T_1=unit("ticket", "INTERRUPTED", "S-1"))
    assert H.derive_parent(s, "E-1")["attention"] == ["T-1 is INTERRUPTED"]


def test_recompute_parents_records_derived_changes_in_history():
    s = graph(S_1=unit("story", "PLANNING"), T_1=unit("ticket", "DONE", "S-1"))
    assert H.recompute_parents(s, at="t0") == ["S-1"]
    assert s["work"]["S-1"]["state"] == "ACCEPTANCE_PENDING"
    assert s["work"]["S-1"]["history"][-1] == {"from": "PLANNING", "to": "ACCEPTANCE_PENDING", "at": "t0",
                                               "reason": "derived from child work"}
    assert H.recompute_parents(s, at="t1") == []


def test_edges_are_inherited_from_ancestors():
    s = graph(S_1=unit("story", "IN_PROGRESS", deps=("S-0",)), S_0=unit("story", "PLANNING"),
              T_1=unit("ticket", "READY", "S-1", deps=("T-9",)), T_9=unit("ticket", "DONE"))
    assert [(e["id"], e["inherited_from"]) for e in H.effective_edges(s, "T-1")] == [("T-9", None), ("S-0", "S-1")]


@pytest.mark.parametrize(("edges", "cyclic"), [
    ({"T-1": ["T-2"], "T-2": ["T-1"]}, True),           # direct cycle
    ({"T-1": ["S-1"]}, True),                           # a Ticket depending on its own parent
    ({"S-1": ["T-1"]}, True),                           # a parent depending on its own child (inherited)
    ({"S-2": ["S-1"], "T-3": ["T-1"]}, False),          # S-2 after S-1, and a Ticket of S-2 after one of S-1
    ({"S-2": ["S-1"], "T-1": ["T-3"]}, True),           # deadlock: S-1 waits on T-1 -> T-3 -> (inherited) S-1
    ({"S-1": ["S-2"], "T-3": ["T-1"]}, True),           # T-1 inherits S-1 -> S-2, which waits on T-3 -> T-1
])
def test_cycles_are_found_across_edges_inheritance_and_hierarchy(edges, cyclic):
    s = graph(S_1=unit("story", "IN_PROGRESS"), S_2=unit("story", "IN_PROGRESS"),
              T_1=unit("ticket", "READY", "S-1"), T_2=unit("ticket", "READY", "S-1"),
              T_3=unit("ticket", "READY", "S-2"))
    for wid, deps in edges.items():
        s["work"][wid]["depends_on"] = [{"id": d, "kind": "evidence"} for d in deps]
    assert (H.find_cycle(s) is not None) == cyclic


def test_children_digest_tracks_ids_states_and_completion_records():
    s = graph(S_1=unit("story", "ACCEPTANCE_PENDING"), T_1=unit("ticket", "DONE", "S-1"))
    base = H.children_digest(s, "S-1", {"T-1": "aaa"})
    assert base == H.children_digest(s, "S-1", {"T-1": "aaa"})
    assert base != H.children_digest(s, "S-1", {"T-1": "bbb"})
    s["work"]["T-2"] = unit("ticket", "CANCELLED", "S-1")
    assert base != H.children_digest(s, "S-1", {"T-1": "aaa"})
