"""A run directory is writable by the run's own user, and since F25 slice 2a a Lead transaction reads it under the
control lock (the usage copy, design v0.2 R5). Whatever the run leaves there, reading it ends promptly, never raises
and never reads without bound: a record that cannot be read is no record (``unconfirmed``), and a heartbeat that is not
a regular file is no heartbeat (``lost``) (#137 re-review)."""

from __future__ import annotations

import json
import os
import threading

import pytest
from conftest import IS_WINDOWS

from aew.harness import contract as K
from aew.harness import runlog

POSIX_ONLY = pytest.mark.skipif(IS_WINDOWS, reason="needs POSIX symlinks and FIFOs")


@pytest.fixture
def directory(tmp_path):
    d = tmp_path / "R-INV-0001-1"
    d.mkdir()
    return d


def record(directory, status=K.RUNNING):
    (directory / "run.json").write_text(json.dumps({"run": directory.name, "status": status}), encoding="utf-8")


def promptly(fn):
    """``fn()`` within 10 s, from a daemon thread: a read that blocks fails the test instead of hanging it."""
    out: list = []
    worker = threading.Thread(target=lambda: out.append(fn()), daemon=True)
    worker.start()
    worker.join(10)
    assert out, "the read blocked"
    return out[0]


def test_a_heartbeat_or_record_that_is_a_directory_is_none(directory):
    record(directory)
    (directory / "heartbeat").mkdir()
    assert runlog.heartbeat_age(directory) is None
    assert runlog.observed_status(directory)[0] == K.LOST
    os.replace(directory / "run.json", directory / "kept.json")
    (directory / "run.json").mkdir()
    assert runlog.read_record(directory) is None
    assert runlog.observed_status(directory)[0] == K.UNCONFIRMED


def test_a_record_past_its_bound_is_not_read(directory, monkeypatch):
    record(directory)
    assert runlog.read_record(directory) is not None
    monkeypatch.setattr(runlog, "MAX_RECORD_BYTES", 16)
    assert runlog.read_record(directory) is None


@POSIX_ONLY
def test_a_heartbeat_that_is_a_link_is_none_and_never_raises(directory):
    record(directory)
    os.symlink("heartbeat", directory / "heartbeat")  # a loop: stat would raise ELOOP
    assert runlog.heartbeat_age(directory) is None
    assert runlog.observed_status(directory)[0] == K.LOST
    os.remove(directory / "heartbeat")
    (directory / "beat-file").touch()
    os.symlink("beat-file", directory / "heartbeat")  # a fresh file behind a link is still not a heartbeat
    assert runlog.heartbeat_age(directory) is None
    os.remove(directory / "heartbeat")
    os.symlink("run.json/x", directory / "heartbeat")  # ENOTDIR
    assert runlog.heartbeat_age(directory) is None


@POSIX_ONLY
def test_a_record_that_is_a_fifo_a_device_or_a_link_is_none_and_never_blocks(directory):
    (directory / "real.json").write_text(json.dumps({"status": K.CRASHED}), encoding="utf-8")
    os.mkfifo(directory / "run.json")
    assert promptly(lambda: runlog.read_record(directory)) is None
    os.remove(directory / "run.json")
    os.symlink("/dev/zero", directory / "run.json")
    assert promptly(lambda: runlog.read_record(directory)) is None
    os.remove(directory / "run.json")
    os.symlink("real.json", directory / "run.json")
    assert runlog.read_record(directory) is None


# ---------------------------------------------------------------- the supervisor's own reads and writes


def test_a_beat_on_a_heartbeat_that_is_a_directory_never_raises(directory):
    (directory / "heartbeat").mkdir()
    runlog.beat(directory)  # the supervisor's beat thread must survive it; the run reads as lost
    assert runlog.heartbeat_age(directory) is None


@POSIX_ONLY
def test_a_beat_never_follows_a_link_or_blocks_on_a_fifo(directory, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside / "created", directory / "heartbeat")  # dangling: a followed touch would create it
    runlog.beat(directory)
    assert not (outside / "created").exists()
    assert runlog.heartbeat_age(directory) is not None  # the link was replaced by a heartbeat of its own
    os.remove(directory / "heartbeat")
    (outside / "kept").write_text("x", encoding="utf-8")
    os.utime(outside / "kept", (0, 0))
    os.symlink(outside / "kept", directory / "heartbeat")
    runlog.beat(directory)
    assert os.stat(outside / "kept").st_mtime == 0  # never touched through the link
    os.remove(directory / "heartbeat")
    os.mkfifo(directory / "heartbeat")
    promptly(lambda: runlog.beat(directory))
    assert runlog.heartbeat_age(directory) is not None


def test_a_request_past_the_bound_is_dropped(directory, monkeypatch):
    queue = directory / "requests"
    queue.mkdir()
    (queue / "a.json").write_text('{"kind": "stop"}', encoding="utf-8")
    (queue / "b.json").write_text("x" * 64, encoding="utf-8")
    monkeypatch.setattr(runlog, "MAX_RECORD_BYTES", 32)
    assert runlog.take_requests(directory) == [("a.json", '{"kind": "stop"}')]
    assert not list(queue.iterdir())  # taken or dropped, never read again


@POSIX_ONLY
def test_the_request_queue_never_blocks_on_a_fifo_or_follows_a_link(directory):
    """The watchdog loop takes the queue: a request that blocked it would stop the deadline and every later Lead
    request."""
    queue = directory / "requests"
    queue.mkdir()
    os.mkfifo(queue / "a.json")
    os.symlink("/dev/zero", queue / "b.json")
    (queue / "c.json").write_text('{"kind": "stop"}', encoding="utf-8")
    assert promptly(lambda: runlog.take_requests(directory)) == [("c.json", '{"kind": "stop"}')]
    assert not list(queue.iterdir())


@pytest.mark.parametrize("record", [
    {"supervisor_pid": 1, "custody_at": ["2026-10-09T00:00:00Z"]},
    {"supervisor_pid": 1, "custody_at": "yesterday"},
    {"supervisor_pid": "1", "custody_at": "2026-10-09T00:00:00Z"},
    {"supervisor_pid": True, "custody_at": "2026-10-09T00:00:00Z"},
], ids=["custody-not-a-string", "custody-not-a-time", "pid-not-an-int", "pid-a-bool"])
def test_teardown_never_acts_on_a_record_the_supervisor_did_not_write(directory, monkeypatch, record):
    from aew.harness import procs

    monkeypatch.setattr(procs, "kill_pid", lambda pid: pytest.fail(f"killed {pid}"))
    (directory / "run.json").write_text(json.dumps(record), encoding="utf-8")
    assert runlog.end_supervisor(directory) is False
