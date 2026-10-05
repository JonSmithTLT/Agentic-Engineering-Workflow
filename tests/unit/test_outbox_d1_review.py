"""Regressions for the independent review of M4-D slice D1 (ADR-0012), on the store model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from store_model import init, make_store  # noqa: E402

from aew.engine.store import Transition  # noqa: E402
from aew.errors import ValidationFailed  # noqa: E402


def declared(n: int, bad_at: int) -> list[dict]:
    events = [{"kind": "handoff.recorded", "id": f"H-{i:04d}"} for i in range(n)]
    events[bad_at] = {"kind": "made.up", "id": "X"}
    return events


@pytest.mark.parametrize("bad_at", [0, 69])
def test_f1_a_malformed_event_fails_the_commit_wherever_it_falls_in_an_overflowing_list(tmp_path, bad_at):
    """Review F1: the hot list was validated with control.yaml, the overflow payload never, so the same malformed
    event was refused at position 1 and committed at position 70. Now both fail closed, leaving no trace."""
    store = init(tmp_path)
    with pytest.raises(ValidationFailed), store.session() as s:
        s.state["counters"]["n"] = 1
        s.commit(Transition(op="test.declared", actor={"kind": "test"}, events=declared(70, bad_at)))
    assert make_store(tmp_path).read()["revision"] == 0
    assert not list((tmp_path / "state/log").glob("*.events.yaml"))
    assert not list((tmp_path / "state").glob("txn/*.yaml"))


def test_f4_every_wake_bump_changes_the_mark_even_within_one_timestamp_tick(tmp_path):
    """Review F4: two bumps inside one filesystem timestamp tick left the same (mtime, inode ^ size) mark for a fifth
    to two fifths of back-to-back pairs, so a waiter that looked between them slept until the coarse check. Each bump
    now replaces the file, giving it a new identity."""
    from aew.engine import outbox

    collisions = 0
    for _ in range(1000):
        outbox.bump_wake(tmp_path, 10)
        a = outbox.wake_mark(tmp_path)
        outbox.bump_wake(tmp_path, 10)
        b = outbox.wake_mark(tmp_path)
        collisions += a == b
    assert collisions == 0
    assert not list((tmp_path / "local").glob(".wake.*.tmp"))


@pytest.mark.parametrize("windows", [True, False])
def test_pr60_item3_a_refused_read_is_absence_only_on_windows(tmp_path, monkeypatch, windows):
    """PR #60 review item 3: on Windows a PermissionError opening a log file is a deletion still pending (sealing),
    so the reader looks in the segment; on POSIX it is a real permissions problem and must surface as one, not as
    'incomplete history'."""
    from aew.engine import outbox

    path = tmp_path / "000001.yaml"
    path.write_text("revision: 1\n", encoding="utf-8")

    def refused(self):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(outbox, "IS_WINDOWS", windows, raising=False)
    monkeypatch.setattr(Path, "read_bytes", refused)
    if windows:
        assert outbox.read_optional(path) is None
    else:
        with pytest.raises(PermissionError):
            outbox.read_optional(path)


def test_pr60_item4_a_crash_mid_bump_leaves_at_most_one_temp_file_per_process(tmp_path, monkeypatch):
    """PR #60 review item 4: `local/` is not swept by recovery, so a bump that dies between writing its temp file and
    renaming it must not leave a new leftover each time: the temp name is fixed per process."""
    import os

    from aew.engine import outbox
    from aew.engine.faults import InjectedFault

    def crash(src, dst):
        raise InjectedFault("between the write and the rename")

    monkeypatch.setattr(os, "replace", crash)
    for _ in range(3):
        with pytest.raises(InjectedFault):
            outbox.bump_wake(tmp_path, 1)
    monkeypatch.undo()
    assert [p.name for p in (tmp_path / "local").glob(".wake.*.tmp")] == [f".wake.{os.getpid()}.tmp"]
    outbox.bump_wake(tmp_path, 2)  # the next bump reuses it and leaves none
    assert not list((tmp_path / "local").glob(".wake.*.tmp"))
    assert (tmp_path / "local/wake").read_text(encoding="utf-8").startswith("2 ")
