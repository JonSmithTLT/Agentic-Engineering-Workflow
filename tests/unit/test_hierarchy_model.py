"""Hierarchy semantics as pure functions over control state (ADR-0007): derived parent state, attention,
inherited edges, cycle refusal, the children digest, and what a move may not lower (EW-U05.g)."""

from __future__ import annotations

import pytest

from aew.engine import hierarchy as H
from aew.engine import transitions as T
from aew.engine.hierarchy_ops import FINAL, inherited_obligations, lowered_obligations


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


def test_a_move_keeps_each_required_integration_verifier():
    """``validation.obligation`` reads each ancestor's floor on its own (a class mapping need not be monotonic), so a
    required integration verifier is an obligation of its own, compared apart from the effective class and the
    gates."""
    gates_policy = {"post_integration": {"validation": {"by_class": {"2": "checks"}, "default": "verifier"}}}
    s = graph(E_1=unit("epic", "IN_PROGRESS", policy={"min_descendant_class": 1, "rationale": "r"}),
              E_2=unit("epic", "IN_PROGRESS", policy=None),
              E_3=unit("epic", "IN_PROGRESS", policy={"min_descendant_class": 1, "rationale": "r"}),
              T_1=unit("ticket", "READY", "E-1", risk_class=2, mutating=True))
    before = inherited_obligations(s, ["T-1"], gates_policy)
    sources = ["E-1 minimum descendant class 1, whose validation is verifier"]
    assert before["T-1"]["validation"] == {"mode": "verifier", "sources": sources}
    for parent, lost in (("E-3", {}), ("E-2", {"T-1": {"integration_verifier": sources}}),
                         (None, {"T-1": {"integration_verifier": sources}})):
        s["work"]["T-1"]["parent"] = parent
        after = inherited_obligations(s, ["T-1"], gates_policy)
        assert after["T-1"]["effective_class"] == before["T-1"]["effective_class"] == 2  # compared on its own
        assert lowered_obligations(before, after) == lost


@pytest.mark.parametrize("kind", ["ticket", "story"])
def test_a_move_leaves_out_exactly_the_states_the_machine_never_leaves(kind):
    """The comparison's exclusion is read from the live machine, both ways: a unit is left out if and only if no rule
    leaves its state. A Story's phase is derived; its final phases are its recorded closeout and cancellation, the same
    states, which are also the only ones the archive takes."""
    no_exit = {s for s in T.STATES if not T.allowed_from(s)}
    assert FINAL == no_exit == T.TERMINAL == H.TERMINAL
    for state in (T.STATES if kind == "ticket" else H.PARENT_STATES):
        s = graph(E_1=unit("epic", "IN_PROGRESS", policy={"min_descendant_class": 2, "rationale": "r"}),
                  X_1=unit(kind, state, "E-1", risk_class=1, mutating=False))
        assert ("X-1" not in inherited_obligations(s, ["X-1"], {})) == (state in no_exit), state


def test_a_move_compares_only_work_still_to_be_proven_and_names_each_loss():
    s = graph(E_1=unit("epic", "IN_PROGRESS", policy={"min_descendant_class": 3, "rationale": "r",
                                                       "mandatory_gates": ["review_security"]}),
              S_1=unit("story", "IN_PROGRESS", "E-1", risk_class=1),
              T_1=unit("ticket", "DONE", "S-1", risk_class=1, mutating=True),
              T_2=unit("ticket", "CANCELLED", "S-1", risk_class=1, mutating=True),
              T_3=unit("ticket", "BLOCKED", "S-1", risk_class=1, mutating=False))
    moved = ["S-1", "T-1", "T-2", "T-3"]
    before = inherited_obligations(s, moved, {})
    assert set(before) == {"S-1", "T-3"}  # finished work proves nothing more
    s["work"]["S-1"]["parent"] = None
    assert lowered_obligations(before, inherited_obligations(s, moved, {})) == {
        w: {"effective_class": {"before": 3, "after": 1}, "non_waivable_gates": ["review_security"]}
        for w in ("S-1", "T-3")}
