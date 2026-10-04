"""Independent P2a review reproductions, confined to disposable repositories."""
from pathlib import Path
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path.cwd() / "tests/helpers"))
from history_model import archive, init, read_root
from store_model import make_store
from aew.engine.faults import InjectedFault
from aew.engine.store import Transition
from aew.history.store import History, bundle_rel
from aew.history.index import HistoryIndex
from aew.history import manifest as M
from aew.util import dump_yaml, load_yaml


def record(name, **result):
    print(json.dumps({"probe": name, **result}), flush=True)


with tempfile.TemporaryDirectory(prefix="aew-p2a-independent-") as td:
    base = Path(td)
    # Positive control: sealed lookup and verification agree on untampered history.
    store = init(base / "lookup")
    archive(store, 260)
    root = read_root(store.root)
    history = History(store.root)
    assert history.entry(root, 7)["id"] == "T-0007" and history.verify(root).ok
    path = store.root / M.segment_rel(1)
    doc = load_yaml(path.read_text(encoding="utf-8"))
    doc["entries"][6]["id"] = "T-7777"
    path.write_text(dump_yaml(doc), encoding="utf-8")
    entry = history.entry(root, 7)
    report = history.verify(root)
    record("sealed_lookup", returned_id=entry["id"], full_verify_ok=report.ok,
           problems=report.problems)
    assert entry["id"] == "T-7777" and not report.ok

    # Audit should report malformed on-disk bytes, as it reports other corruption.
    store = init(base / "decode")
    archive(store, 1)
    root = read_root(store.root)
    assert History(store.root).verify(root).ok
    (store.root / M.TAIL_REL).write_bytes(b"\xff\xfe\x80")
    try:
        report = History(store.root).verify(root)
        record("invalid_utf8", raised=None, ok=report.ok, problems=report.problems)
    except Exception as exc:
        record("invalid_utf8", raised=type(exc).__name__, message=str(exc))
        assert isinstance(exc, UnicodeDecodeError)

    # Prewritten immutable objects are pinned, but are absent from recovery's checks.
    for damage in ("edit", "delete", "none"):
        store = init(base / f"prewritten-{damage}")
        os.environ["AEW_FAULT"] = "txn.after_replace"
        os.environ["AEW_FAULT_MODE"] = "raise"
        try:
            archive(store, 2, prewritten=True)
        except InjectedFault:
            pass
        else:
            raise AssertionError("crash point did not fire")
        finally:
            os.environ.pop("AEW_FAULT")
            os.environ.pop("AEW_FAULT_MODE")
        path = store.root / bundle_rel("T-0001")
        if damage == "edit":
            path.write_text("changed after commit before recovery\n", encoding="utf-8")
        elif damage == "delete":
            path.unlink()
        state = make_store(store.root).read()
        report = History(store.root).verify(read_root(store.root))
        record("prewritten_recovery", damage=damage, recovered_revision=state["revision"],
               full_verify_ok=report.ok, problems=report.problems)
        assert state["revision"] == 1 and report.ok == (damage == "none")

    # Valid SQLite with unusable cache metadata should also be disposable.
    for damage in ("missing_h", "invalid_count"):
        store = init(base / f"index-{damage}")
        archive(store, 4)
        index = HistoryIndex(store.root)
        root = read_root(store.root)
        assert index.sync(root)["added"] == 4
        with sqlite3.connect(index.path) as conn:
            if damage == "missing_h":
                conn.execute("DELETE FROM meta WHERE key = 'h'")
            else:
                conn.execute("UPDATE meta SET value = 'broken' WHERE key = 'count'")
        conn.close()
        try:
            result = index.sync(root)
            record("index_metadata", damage=damage, raised=None, result=result)
        except Exception as exc:
            record("index_metadata", damage=damage, raised=type(exc).__name__, message=str(exc))
            assert isinstance(exc, (KeyError, ValueError))
        index.path.unlink()
        assert index.sync(root) == {"mode": "rebuilt", "added": 4}
        assert len(index.list()) == 4

    # A mutable tail must prove where it starts, not merely where it ends.
    store = init(base / "tail-start")
    archive(store, 3)
    root = read_root(store.root)
    history = History(store.root)
    assert history.verify(root).ok
    with store.session() as s:
        s.commit(Transition(op="unrelated", actor={"kind": "test"}))
    tail_path = store.root / M.TAIL_REL
    tail_doc = load_yaml(tail_path.read_text(encoding="utf-8"))
    tail_doc["start"] = {"count": root["count"], "h": root["head_h"]}
    tail_doc["entries"] = []
    tail_path.write_text(dump_yaml(tail_doc), encoding="utf-8")
    accepted_tail = history.tail(root)
    archive(store, 1)
    report = history.verify(read_root(store.root))
    record("tail_prefix_truncation", accepted_entries=len(accepted_tail["entries"]),
           committed_revision=store.read()["revision"], full_verify_ok=report.ok, problems=report.problems)
    assert not report.ok and store.read()["revision"] == 3

    # Instrument the benchmark's real sync to count entries, rather than timings.
    sys.path.insert(0, str(Path.cwd() / "tools/perf"))
    import control_plane
    original_sync = HistoryIndex.sync
    sync_results = []
    def tracked_sync(self, root):
        result = original_sync(self, root)
        sync_results.append(result)
        return result
    HistoryIndex.sync = tracked_sync
    try:
        control_plane.coldwrite([1000], base / "perf", reps=3)
    finally:
        HistoryIndex.sync = original_sync
    added = [r["added"] for r in sync_results if r["mode"] == "caught_up"]
    record("benchmark_index_catchup", added_per_sample=added, documented_entries_per_sample=3)
    assert added == [25, 256, 256]
