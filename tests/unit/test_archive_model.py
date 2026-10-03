"""ADR-0011 P2b pure model: the pinned children accumulator and digest (plan R3), and derivation from summaries."""

from __future__ import annotations

from aew.engine import hierarchy as H
from aew.engine.archive_ops import add_leaf, child_leaf

ZERO = "0" * 64


def test_the_child_leaf_and_accumulator_are_pinned_by_golden_vectors():
    # Parent evidence binds to the children digest, which binds to these values: a construction change is a schema
    # change, never a refactor.
    leaf_done = child_leaf("T-0001", "DONE", "a" * 64)
    leaf_cancelled = child_leaf("T-0002", "CANCELLED", None)
    assert f"{leaf_done:064x}" == "c66c168ae92418fe267ff1bc9eacd37099944e6f7d4e99628ea41bc87e7df5b2"
    assert f"{leaf_cancelled:064x}" == "44b77a3e4f05171b12d46b34a2f3a3168346e0dad169bd8c2c338545872c0907"
    acc = add_leaf(add_leaf(ZERO, leaf_done), leaf_cancelled)
    assert acc == "0b2390c93829301939545cf141a076871cdb2f4a4eb856eebad7a10e05a9feb9"
    assert add_leaf(add_leaf(ZERO, leaf_cancelled), leaf_done) == acc  # order-free: archival order never matters
    assert add_leaf(acc, leaf_done, -1) == add_leaf(ZERO, leaf_cancelled)  # a move subtracts exactly its leaf


def test_the_v2_children_digest_is_pinned_and_covers_archived_children():
    state = {"schema": "aew/control/v2", "work": {
        "S-0001": {"kind": "story", "archived_children": {"done": 1, "cancelled": 1,
                                                          "acc": "0b2390c93829301939545cf141a076871cdb2f4a4eb856eebad7a10e05a9feb9"}},
        "T-0003": {"kind": "ticket", "parent": "S-0001", "state": "RUNNING"}}}
    digest = H.children_digest(state, "S-0001", {"T-0003": None})
    assert digest == "5aed861291c86db775af700c3249297562900e2e339828a28d7857af544944b7"
    state["work"]["S-0001"]["archived_children"]["done"] = 2  # another archived child changes it
    assert H.children_digest(state, "S-0001", {"T-0003": None}) != digest


def test_derivation_reads_hot_children_and_the_summary():
    base = {"schema": "aew/control/v2", "work": {"S-1": {"kind": "story", "state": "PLANNING"}}}
    assert H.derive_parent(base, "S-1")["state"] == "PLANNING"
    base["work"]["S-1"]["archived_children"] = {"done": 1, "cancelled": 0}
    assert H.derive_parent(base, "S-1")["state"] == "ACCEPTANCE_PENDING"  # every child finished and archived
    base["work"]["T-2"] = {"kind": "ticket", "parent": "S-1", "state": "RUNNING"}
    assert H.derive_parent(base, "S-1")["state"] == "IN_PROGRESS"


def test_descendants_walk_one_children_map():
    state = {"work": {"E": {"kind": "epic"}, "S": {"kind": "story", "parent": "E"},
                      "T1": {"kind": "ticket", "parent": "S"}, "T2": {"kind": "ticket", "parent": "E"}}}
    assert H.children_map(state) == {"E": ["S", "T2"], "S": ["T1"]}
    assert H.descendants(state, "E") == ["S", "T2", "T1"]  # breadth-first, as before


def test_upstream_reads_archived_refs_shaped_like_a_unit():
    state = {"work": {}, "archived_refs": {"T-9": {"kind": "ticket", "mutating": True, "state": "DONE",
                                                   "integration_commit": "c" * 40, "refs": 1,
                                                   "bundle_sha256": "b" * 64}}}
    up = H.upstream(state, "T-9")
    assert up["state"] == "DONE" and up["integration"]["commit"] == "c" * 40 and up["archived"] is True
    assert H.upstream(state, "T-404") is None
