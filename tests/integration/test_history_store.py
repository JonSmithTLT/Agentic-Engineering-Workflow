"""The cold history store (ADR-0011 P2a): appending, sealing, verification, the derived index, pre-written records,
and crashes at each history fault point (in-process; ``test_store_processes`` kills real processes)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from history_model import ROOT_REL, archive, bundle, check, fields, init, read_root  # noqa: E402

from aew.engine.faults import InjectedFault  # noqa: E402
from aew.engine.store import Transition  # noqa: E402
from aew.errors import IntegrityError  # noqa: E402
from aew.history import manifest as M  # noqa: E402
from aew.history.index import INDEX_REL, HistoryIndex  # noqa: E402
from aew.history.store import History, annotation_rel, bundle_rel, prewrite  # noqa: E402
from aew.util import dump_yaml, load_yaml, sha256_file  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return init(tmp_path)


def last_txn(store):
    txn = store.read()["last_transition"]["txn"]
    return txn, load_yaml((store.root / txn["path"]).read_text(encoding="utf-8")) if txn else None


# ---------------------------------------------------------------------------------------------- appending

def test_appends_seal_full_segments_and_keep_a_short_tail(store):
    for _ in range(3):
        archive(store, 1)
    archive(store, 300)  # crosses one seal inside a single transaction
    archive(store, 1)
    root = read_root(store.root)
    assert root["count"] == 304 and root["sealed_head"]["seq"] == 1
    assert root["sealed_head"]["sha256"] == sha256_file(store.root / M.segment_rel(1))
    tail = History(store.root).tail(root)
    assert tail["seq"] == 2 and tail["start"]["count"] == 256 and len(tail["entries"]) == 48
    assert check(store.root) == 304


def test_one_archival_writes_only_its_records_and_the_tail(store):
    archive(store, 255)
    txn, record = last_txn(store)
    assert {w["path"] for w in txn["writes"]} == {M.TAIL_REL, ROOT_REL} | {bundle_rel(f"T-{k:04d}")
                                                                          for k in range(1, 256)}
    archive(store, 1)  # the 256th entry seals: the record, the sealed segment and a new empty tail
    txn, _ = last_txn(store)
    assert [w["path"] for w in txn["writes"]] == [bundle_rel("T-0256"), M.segment_rel(1), M.TAIL_REL, ROOT_REL]
    archive(store, 1)
    txn, _ = last_txn(store)
    assert [w["path"] for w in txn["writes"]] == [bundle_rel("T-0257"), M.TAIL_REL, ROOT_REL]


def test_an_entry_is_found_by_its_sequence_number(store):
    archive(store, 260)
    root = read_root(store.root)
    history = History(store.root)
    assert history.entry(root, 1)["id"] == "T-0001"
    assert history.entry(root, 256)["id"] == "T-0256"
    assert history.entry(root, 260)["id"] == "T-0260"
    with pytest.raises(IntegrityError):
        history.entry(root, 261)


@pytest.mark.parametrize("change,message", [("edited", "hash chain"), ("truncated", "does not end at the hot root")])
def test_an_append_refuses_a_tail_that_does_not_end_at_the_root(store, change, message):
    archive(store, 3)
    root = read_root(store.root)
    with store.session() as s:  # a later transaction: recovery no longer re-checks the tail it does not touch
        s.commit(Transition(op="x", actor={"kind": "test"}))
    tail = store.root / M.TAIL_REL
    doc = load_yaml(tail.read_text(encoding="utf-8"))
    if change == "edited":
        doc["entries"][2]["id"] = "T-0099"
    else:
        doc["entries"].pop()
    tail.write_text(dump_yaml(doc), encoding="utf-8")
    with store.session() as s:
        with pytest.raises(IntegrityError, match=message):
            History(store.root).append(s, root, [fields(4, "b" * 64)])


def test_a_record_is_immutable(store):
    archive(store, 1)
    with store.session() as s:
        History(store.root).write_record(s, bundle_rel("T-0001"), "other content\n")
        with pytest.raises(IntegrityError, match="immutable"):
            s.commit(Transition(op="x", actor={"kind": "test"}))


# ---------------------------------------------------------------------------------------------- verification

def test_full_and_incremental_verification(store):
    archive(store, 10)
    earlier = read_root(store.root)
    archive(store, 300)
    root = read_root(store.root)
    history = History(store.root)
    full = history.verify(root)
    assert full.ok and full.entries == 310 and full.through == {"count": 310, "h": root["head_h"]}
    incremental = history.verify(root, {"count": earlier["count"], "h": earlier["head_h"]})
    assert incremental.ok and incremental.entries == 300  # proportional to what was appended since


def test_an_earlier_root_that_is_not_on_the_chain_is_reported(store):
    archive(store, 5)
    report = History(store.root).verify(read_root(store.root), {"count": 3, "h": "0" * 64})
    assert not report.ok and "not on the current history" in report.problems[0]


@pytest.mark.parametrize("damage", ["record", "record_missing", "segment_entry", "segment_missing", "tail_missing",
                                    "root"])
def test_damage_is_reported_not_raised(store, damage):
    archive(store, 300)
    root = read_root(store.root)
    seg = store.root / M.segment_rel(1)
    if damage == "record":
        (store.root / bundle_rel("T-0007")).write_text("changed\n", encoding="utf-8")
    elif damage == "record_missing":
        (store.root / bundle_rel("T-0007")).unlink()
    elif damage == "segment_entry":
        seg.write_text(seg.read_text(encoding="utf-8").replace("id: T-0007\n", "id: T-7777\n"), encoding="utf-8")
    elif damage == "segment_missing":
        seg.unlink()
    elif damage == "tail_missing":
        (store.root / M.TAIL_REL).unlink()
    else:
        root = dict(root, head_h="0" * 64)
    report = History(store.root).verify(root)
    assert not report.ok and report.problems
    if damage.startswith("record"):
        assert report.through is not None and "T-0007" in report.problems[0]  # the chain itself still holds
    else:
        assert report.through is None


def test_a_sealed_segment_that_differs_from_the_root_is_reported(store):
    archive(store, 300)
    root = dict(read_root(store.root), sealed_head={"seq": 1, "sha256": "0" * 64})
    report = History(store.root).verify(root)
    assert report.through is None and "newest sealed segment" in report.problems[0]


# ---------------------------------------------------------------------------------------------- the index

def test_the_index_rebuilds_catches_up_and_answers_lookups(store):
    archive(store, 5)
    index = HistoryIndex(store.root)
    assert index.sync(read_root(store.root)) == {"mode": "rebuilt", "added": 5}
    assert index.sync(read_root(store.root)) == {"mode": "current", "added": 0}
    archive(store, 300)
    assert index.sync(read_root(store.root)) == {"mode": "caught_up", "added": 300}  # only what was appended
    assert [e["seq"] for e in index.by_id("T-0042")] == [42]
    assert [e["id"] for e in index.list(kind="unit", limit=3)] == ["T-0305", "T-0304", "T-0303"]
    assert index.list(kind="audit") == []
    assert len(index.list(since="2026-10-02T00:00:00Z", until="2026-10-02T00:00:00Z")) == 305
    assert {"from": "T-0042", "rel": "depends_on", "to": "T-0041"} in index.links("T-0042")
    assert {"from": "T-0043", "rel": "depends_on", "to": "T-0042"} in index.links("T-0042")
    assert len(index.paths()) == 305


@pytest.mark.parametrize("loss", ["deleted", "damaged", "foreign_root"])
def test_a_lost_damaged_or_foreign_index_is_rebuilt(store, loss):
    archive(store, 4)
    index = HistoryIndex(store.root)
    index.sync(read_root(store.root))
    path = store.root / INDEX_REL
    if loss == "deleted":
        path.unlink()
    elif loss == "damaged":
        path.write_bytes(b"not a database" * 100)
    else:  # an index built against a history this root does not extend: other entries, so another chain
        other = init(store.root.parent / "other")
        history = History(other.root)
        with other.session() as s:
            root = history.append(s, read_root(other.root), [dict(fields(k, "c" * 64), id=f"X-{k}") for k in range(1, 7)])
            s.write(ROOT_REL, dump_yaml(root), immutable=False)
            s.commit(Transition(op="x", actor={"kind": "test"}))
        HistoryIndex(other.root).sync(read_root(other.root))
        path.write_bytes((other.root / INDEX_REL).read_bytes())
    assert index.sync(read_root(store.root)) == {"mode": "rebuilt", "added": 4}
    assert [e["id"] for e in index.list()] == ["T-0004", "T-0003", "T-0002", "T-0001"]


def append_entries(store, items: list[dict]) -> dict:
    """Append ``items`` (entry fields without ``sha256``), each with a small record; the new root."""
    history = History(store.root)
    with store.session() as s:
        items = [{**f, "sha256": history.write_record(s, f["path"], f"schema: test\nid: {f['id']}\n")} for f in items]
        root = history.append(s, read_root(store.root), items)
        s.write(ROOT_REL, dump_yaml(root), immutable=False)
        s.commit(Transition(op="x", actor={"kind": "test"}))
    return root


def unit_entry(k: int, parent: str | None = None, depends_on: tuple[str, ...] = ()) -> dict:
    return {"kind": "unit", "id": f"T-{k:04d}", "path": bundle_rel(f"T-{k:04d}"), "at": "2026-10-02T00:00:00Z",
            "state": "DONE", "parent": parent, "source": "engine",
            "links": {"depends_on": list(depends_on)} if depends_on else {}}


def test_every_query_of_an_index_ahead_of_the_root_stops_at_that_root(store):
    earlier = append_entries(store, [unit_entry(1, parent="S-0001")])
    later = append_entries(store, [
        unit_entry(2, parent="S-0001", depends_on=("T-0001",)),
        {"kind": "annotation", "id": "AN-0001", "path": annotation_rel("T-0001", 1), "at": "2026-10-02T01:00:00Z",
         "subject": "T-0001", "rel": "moved_to", "source": "engine", "links": {"moved_to": ["S-0009"]}}])
    HistoryIndex(store.root).sync(later)  # another process indexed the later root
    index = HistoryIndex(store.root)
    assert index.sync(earlier) == {"mode": "ahead", "added": 0}
    assert [e["id"] for e in index.list(limit=1)] == ["T-0001"]  # the bound applies before the limit
    assert [e["id"] for e in index.list()] == ["T-0001"]
    assert index.by_id("T-0002") == []
    assert [e["id"] for e in index.units("DONE")] == ["T-0001"]
    assert [e["id"] for e in index.children("S-0001")] == ["T-0001"]
    assert index.linked("depends_on", "T-0001") == []
    assert index.annotations("T-0001") == [] and index.moves() == {}
    assert index.links("T-0001") == []
    assert index.paths() == {bundle_rel("T-0001")}
    assert index.sync(later) == {"mode": "current", "added": 0}  # synced forward, the same index sees it all
    assert [e["id"] for e in index.list(limit=1)] == ["AN-0001"]
    assert [e["id"] for e in index.children("S-0001")] == ["T-0001", "T-0002"]
    assert [e["id"] for e in index.linked("depends_on", "T-0001")] == ["T-0002"]
    assert index.moves() == {"T-0001": "S-0009"}
    assert index.links("T-0001") == [{"from": "T-0002", "rel": "depends_on", "to": "T-0001"}]
    assert len(index.paths()) == 3


def test_annotations_are_entries_about_a_subject(store):
    archive(store, 2)
    history = History(store.root)
    with store.session() as s:
        rel = annotation_rel("T-0001", 1)
        sha = history.write_record(s, rel, "schema: aew/annotation/v1\nrel: moved_to\n")
        root = history.append(s, read_root(store.root), [{
            "kind": "annotation", "id": "AN-0001", "path": rel, "sha256": sha, "at": "2026-10-02T01:00:00Z",
            "subject": "T-0001", "rel": "moved_to", "source": "engine", "links": {"moved_to": ["S-0007"]}}])
        s.write(ROOT_REL, dump_yaml(root), immutable=False)
        s.commit(Transition(op="x", actor={"kind": "test"}))
    index = HistoryIndex(store.root)
    index.sync(read_root(store.root))
    assert [a["id"] for a in index.annotations("T-0001")] == ["AN-0001"]
    assert index.annotations("T-0002") == []
    assert sha256_file(store.root / bundle_rel("T-0001")) == index.by_id("T-0001")[0]["sha256"]  # never rewritten


# ---------------------------------------------------------------------------------------------- pre-written records

def test_prewritten_records_are_referenced_by_hash_only(store):
    archive(store, 300, prewritten=True)
    txn, record = last_txn(store)
    assert txn["prewritten"]["count"] == 300
    assert {w["path"] for w in txn["writes"]} == {M.segment_rel(1), M.TAIL_REL, ROOT_REL}  # no bundle content
    assert len(record["prewritten"]) == 300 and all(set(p) == {"path", "sha256"} for p in record["prewritten"])
    assert check(store.root) == 300


def test_a_prewritten_record_must_hold_its_declared_content(store):
    rel = bundle_rel("T-0001")
    sha = prewrite(store.root, rel, bundle(1))
    assert prewrite(store.root, rel, bundle(1)) == sha  # a retry with identical bytes is fine
    with pytest.raises(IntegrityError, match="immutable"):
        prewrite(store.root, rel, "other\n")
    (store.root / rel).write_text("changed\n", encoding="utf-8")
    with store.session() as s:
        s.prewritten(rel, sha)
        with pytest.raises(IntegrityError, match="pre-written"):
            s.commit(Transition(op="x", actor={"kind": "test"}))
    assert store.read()["revision"] == 0


def test_an_unreferenced_prewritten_record_is_benign_and_reported(store):
    archive(store, 1)
    prewrite(store.root, bundle_rel("T-0002"), bundle(2))  # a migration that never committed
    assert check(store.root, unreferenced=(bundle_rel("T-0002"),)) == 1
    archive(store, 1, prewritten=True)  # the retry rewrites the same bytes and references them
    assert check(store.root) == 2


# ---------------------------------------------------------------------------------------------- crashes

@pytest.mark.parametrize("point,units,committed", [
    ("history.after_bundle", 1, True),
    ("history.mid_seal", 1, True),
    ("history.after_tail", 1, True),
    ("txn.mid_apply", 1, True),
    ("txn.after_stage", 1, False),
    ("txn.before_replace", 1, False),
])
def test_a_crash_at_each_history_point_leaves_the_old_or_the_new_history(store, monkeypatch, point, units, committed):
    archive(store, 255)  # the next append seals segment 1, so every point is on the path
    monkeypatch.setenv("AEW_FAULT", point)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        archive(store, units)
    monkeypatch.delenv("AEW_FAULT")
    assert check(store.root) == (256 if committed else 255)
    archive(store, 2)
    assert check(store.root) == (258 if committed else 257)


def test_a_crash_after_prewriting_leaves_only_benign_records(store, monkeypatch):
    archive(store, 1)
    monkeypatch.setenv("AEW_FAULT", "history.after_prewrite")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        archive(store, 3, prewritten=True)
    monkeypatch.delenv("AEW_FAULT")
    assert check(store.root, unreferenced=(bundle_rel("T-0002"),)) == 1
    archive(store, 3, prewritten=True)
    assert check(store.root) == 4
