"""Persistence core: atomic commits, CAS, recovery, integrity (WC §5, §8.2; KC §12.3)."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from store_model import check_invariants, init, make_store, one_transaction  # noqa: E402

from aew.engine.faults import InjectedFault  # noqa: E402
from aew.engine.store import Transition  # noqa: E402
from aew.errors import IntegrityError, ProjectNotFound, StaleRevision  # noqa: E402

FAULT_POINTS = [
    "txn.before_stage",
    "txn.after_stage",
    "txn.before_replace",
    "txn.after_replace",
    "txn.mid_apply",
    "txn.after_apply",
    "txn.after_log",
    "txn.after_render",
]
BEFORE_COMMIT = {"txn.before_stage", "txn.after_stage", "txn.before_replace"}


def test_initial_create_and_commits(tmp_path):
    store = init(tmp_path)
    assert check_invariants(tmp_path) == 0
    for _ in range(3):
        one_transaction(store)
    assert check_invariants(tmp_path) == 3
    with pytest.raises(IntegrityError):
        store.create({}, {})  # already initialized


def test_missing_project(tmp_path):
    with pytest.raises(ProjectNotFound):
        make_store(tmp_path).read()


def test_stale_expected_revision_rejected(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    before = (tmp_path / "state/control.yaml").read_bytes()
    with pytest.raises(StaleRevision) as exc:
        one_transaction(store, expect_rev=0)
    assert exc.value.details == {"expected": 0, "current": 1}
    assert (tmp_path / "state/control.yaml").read_bytes() == before
    assert check_invariants(tmp_path) == 1


def test_immutable_record_never_overwritten(tmp_path):
    store = init(tmp_path)
    (tmp_path / "records").mkdir()
    (tmp_path / "records/item-1.md").write_text("planted by someone else\n")
    with pytest.raises(IntegrityError):
        one_transaction(store)
    assert store.read()["revision"] == 0
    assert (tmp_path / "records/item-1.md").read_text() == "planted by someone else\n"
    assert not list((tmp_path / "state").glob("txn/*.yaml"))


@pytest.mark.parametrize("point", FAULT_POINTS)
def test_injected_fault_each_point_in_process(tmp_path, monkeypatch, point):
    store = init(tmp_path)
    one_transaction(store)
    monkeypatch.setenv("AEW_FAULT", point)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        one_transaction(make_store(tmp_path))
    monkeypatch.delenv("AEW_FAULT")
    n = check_invariants(tmp_path)
    assert n == (1 if point in BEFORE_COMMIT else 2)
    one_transaction(make_store(tmp_path))  # and the store keeps working
    assert check_invariants(tmp_path) == n + 1


def test_the_windowed_oracle_sees_the_newest_transaction_and_the_full_one_all_history(tmp_path):
    """The randomized run checks a window every iteration and the whole store periodically: the window must catch a
    fault in the newest transaction, and only the full check is trusted with older ones."""
    store = init(tmp_path)
    for _ in range(5):
        one_transaction(store)
    assert check_invariants(tmp_path, window=2) == 5 and check_invariants(tmp_path) == 5
    newest, oldest = tmp_path / "records/item-5.md", tmp_path / "records/item-1.md"
    saved = newest.read_bytes()
    newest.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        check_invariants(tmp_path, window=2)
    newest.write_bytes(saved)
    oldest.write_text("tampered\n", encoding="utf-8")
    assert check_invariants(tmp_path, window=2) == 5  # outside the window, by design
    with pytest.raises(AssertionError):
        check_invariants(tmp_path)


def test_the_windowed_oracle_checks_the_newest_log_records_and_their_chain_link(tmp_path, monkeypatch):
    """The log half of the window (PR #101 review): the newest transition records and the chain link into them (the
    record before the window) are checked; an older record is left to the full check; and the window reads the log
    from that link only, never the whole history."""
    import store_model

    from aew.engine import outbox
    from aew.util import dump_yaml, load_yaml

    store = init(tmp_path)
    for _ in range(6):
        one_transaction(store)

    def tamper(revision: int):
        path = tmp_path / outbox.record_path(revision)
        saved = path.read_bytes()
        record = load_yaml(path.read_text(encoding="utf-8"))
        record["h"] = "0" * 64
        path.write_text(dump_yaml(record), encoding="utf-8", newline="\n")
        return lambda: path.write_bytes(saved)

    for revision in (6, 4):  # the newest record; the chain link just before the window (window 2: revisions 5, 6)
        restore = tamper(revision)
        with pytest.raises(AssertionError):
            check_invariants(tmp_path, window=2)
        restore()
    restore = tamper(1)
    assert check_invariants(tmp_path, window=2) == 6  # outside the window and its link, by design
    with pytest.raises(AssertionError):
        check_invariants(tmp_path)
    restore()
    ranges: list[tuple[int, int]] = []
    real = outbox.read_transitions

    def spy(root, since, through, **kw):
        ranges.append((since, through))
        return real(root, since, through, **kw)

    monkeypatch.setattr(store_model.outbox, "read_transitions", spy)
    assert check_invariants(tmp_path, window=2) == 6
    assert ranges == [(4, 6)]  # from the link, not from the start of history


def test_randomized_crash_iterations(tmp_path, monkeypatch):
    # Merge gate: seed 20260925, 200 iterations. The nightly crash-extended job rotates the seed and raises the count.
    rng = random.Random(int(os.environ.get("AEW_CRASH_SEED", "20260925")))
    init(tmp_path)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    expected = 0
    iterations = int(os.environ.get("AEW_CRASH_ITERATIONS", "200"))
    for i in range(iterations):
        point = rng.choice(FAULT_POINTS + [None, None])
        if point:
            monkeypatch.setenv("AEW_FAULT", point)
        else:
            monkeypatch.delenv("AEW_FAULT", raising=False)
        try:
            one_transaction(make_store(tmp_path))
            expected += 1
        except InjectedFault:
            if point not in BEFORE_COMMIT:
                expected += 1
        monkeypatch.delenv("AEW_FAULT", raising=False)
        # A crash touches only its own transaction: its window every iteration, the whole store every 32 and at the
        # end (proving nothing older changed). The full check every iteration made the run quadratic.
        full = i % 32 == 0 or i == iterations - 1
        assert check_invariants(tmp_path, window=None if full else 2) == expected


def test_truncated_control_state_fails_closed(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    control = tmp_path / "state/control.yaml"
    lines = control.read_text().splitlines(keepends=True)
    control.write_text("".join(lines[: len(lines) // 2]))
    with pytest.raises(IntegrityError):
        store.read()


def test_edited_control_state_fails_closed(tmp_path):
    store = init(tmp_path)
    control = tmp_path / "state/control.yaml"
    control.write_text(control.read_text().replace("generation: 0", "generation: 9"))
    with pytest.raises(IntegrityError) as exc:
        store.read()
    assert "checksum" in exc.value.message


def test_out_of_band_edit_during_apply_fails_closed(tmp_path, monkeypatch):
    store = init(tmp_path)
    one_transaction(store)
    monkeypatch.setenv("AEW_FAULT", "txn.after_replace")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        one_transaction(make_store(tmp_path))
    monkeypatch.delenv("AEW_FAULT")
    # Someone edits a target between commit and roll-forward: never clobber it.
    (tmp_path / "manifest.txt").write_text("hand edit\n")
    with pytest.raises(IntegrityError) as exc:
        make_store(tmp_path).read()
    assert exc.value.details["path"] == "manifest.txt"
    assert (tmp_path / "manifest.txt").read_text() == "hand edit\n"


def test_an_edit_after_a_finished_apply_is_not_a_transition_in_progress(tmp_path):
    """Area 5 F1 (P1): once a transaction's writes are all applied, a later edit of a file it staged is an ordinary
    out-of-band edit (the pin checks report it), not "modified while a transition was being applied" on every read."""
    store = init(tmp_path)
    one_transaction(store)
    (tmp_path / "manifest.txt").write_text("reviewed hand edit\n")
    state = make_store(tmp_path).read()  # a fresh process: recovery has nothing to redo
    assert state["revision"] == 1
    assert (tmp_path / "manifest.txt").read_text() == "reviewed hand edit\n"
    one_transaction(make_store(tmp_path))  # and the next transition proceeds from the edited file
    assert check_invariants(tmp_path) == 2


def test_write_outside_root_refused(tmp_path):
    store = init(tmp_path / "aew")
    with pytest.raises(IntegrityError):
        with store.session() as s:
            s.write("../escape.txt", "x")
            s.commit(Transition(op="escape", actor={"kind": "test"}))
    assert not (tmp_path / "escape.txt").exists()


def test_derived_views_rebuilt_after_deletion(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    (tmp_path / "state/CURRENT.md").unlink()
    (tmp_path / "state/log/000001.yaml").unlink()
    check_invariants(tmp_path)  # read() repairs the log and the render


@pytest.mark.skipif(sys.platform == "win32", reason="Windows refuses to remove an open file")
def test_a_holder_whose_lock_file_was_removed_commits_nothing(tmp_path):
    """Area 5 F2 (P2): deleting ``local/`` under a running process lets another process lock a new file at the same
    path. The holder notices before it writes and refuses, so two writers never both commit a revision."""
    store = init(tmp_path)
    one_transaction(store)
    before = (tmp_path / "state/control.yaml").read_bytes()
    with store.session() as s:
        s.state["counters"]["n"] += 1
        s.write("records/item-x.md", "x\n")
        (tmp_path / "local/control.lock").unlink()
        rival = make_store(tmp_path)
        with rival.session():  # a second process takes the lock at once: the holder's lock excludes no one now
            pass
        with pytest.raises(IntegrityError, match="removed or replaced"):
            s.commit(Transition(op="bump", actor={"kind": "test"}))
    assert (tmp_path / "state/control.yaml").read_bytes() == before
    assert not (tmp_path / "records/item-x.md").exists()
    assert check_invariants(tmp_path) == 1
    one_transaction(store)  # the next session locks the file now at the path and commits normally
    assert check_invariants(tmp_path) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="Windows refuses to remove an open file")
def test_a_taker_whose_lock_file_is_replaced_while_it_waits_locks_the_new_file(tmp_path):
    """P2: a process that locks a file that was removed after it opened it must not proceed on that lock."""
    from aew.engine.lock import FileLock

    path = tmp_path / "control.lock"
    lock = FileLock(path, timeout=5)
    opened = []
    real_open = lock._open

    def open_then_replace():  # the first open sees the old file, which is then removed and recreated
        fh = real_open()
        if not opened:
            path.unlink()
            path.write_bytes(b"")
        opened.append(fh)
        return fh

    lock._open = open_then_replace
    with lock:
        assert len(opened) == 2 and lock.intact()
        held = os.fstat(lock._fh.fileno())
        assert (held.st_ino, held.st_dev) == (path.stat().st_ino, path.stat().st_dev)
