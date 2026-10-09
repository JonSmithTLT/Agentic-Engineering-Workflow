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
