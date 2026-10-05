"""``ControlStore.read_committed`` (design note §4.8; ADR-0012 D3, invariant 4): the committed state without the
control lock and without recovery, for readers; ``control_identity`` changes with every commit."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from store_model import init, make_store, one_transaction  # noqa: E402

from aew.engine.lock import FileLock  # noqa: E402
from aew.engine.store import LOCK_REL, ControlStore  # noqa: E402
from aew.errors import LockTimeout, ProjectNotFound  # noqa: E402


def test_read_committed_is_the_committed_state_and_takes_no_lock(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    assert store.read_committed() == store.read()
    with FileLock(tmp_path / LOCK_REL, timeout=5):  # a writer holds the control lock
        committed = store.read_committed()  # a reader is not behind it
        assert committed["revision"] == 1
        with pytest.raises(LockTimeout):
            ControlStore(tmp_path, lock_timeout=0.2).read()  # the locked read is


def test_read_committed_returns_a_copy_the_caller_may_change(tmp_path):
    store = init(tmp_path)
    first = store.read_committed()
    first["revision"] = 999
    assert store.read_committed()["revision"] == 0


def test_control_identity_changes_with_every_commit_and_not_without(tmp_path):
    store = init(tmp_path)
    before = store.control_identity()
    assert before is not None and store.control_identity() == before
    one_transaction(store)
    after = store.control_identity()
    assert after is not None and after != before
    assert make_store(tmp_path / "nowhere").control_identity() is None


def test_read_committed_without_a_project_is_not_found(tmp_path):
    with pytest.raises(ProjectNotFound):
        make_store(tmp_path).read_committed()


def test_read_committed_sees_each_commit_as_a_whole(tmp_path):
    """Concurrent lock-free reads during commits never see a torn or stale-then-newer sequence: revisions are
    monotonic and every state parses and verifies (the file is replaced atomically)."""
    store = init(tmp_path)
    seen: list[int] = []
    errors: list[BaseException] = []
    stop = threading.Event()

    def reader():
        r = make_store(tmp_path)
        while not stop.is_set():
            try:
                seen.append(r.read_committed()["revision"])
            except BaseException as exc:  # noqa: BLE001 (collected for the assertion)
                errors.append(exc)
                return

    t = threading.Thread(target=reader)
    t.start()
    for _ in range(15):
        one_transaction(store)
    stop.set()
    t.join(30)
    assert errors == [] and seen == sorted(seen) and seen[-1] <= 15
