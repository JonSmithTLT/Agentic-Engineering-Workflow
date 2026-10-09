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


def promptly(fn, within: float = 10):
    """``fn()`` within ``within`` seconds, from a daemon thread: a read that blocks fails the test instead of hanging
    it."""
    out: list = []
    worker = threading.Thread(target=lambda: out.append(fn()), daemon=True)
    worker.start()
    worker.join(within)
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


def test_a_beat_on_a_heartbeat_that_is_a_directory_never_raises_or_waits(directory):
    """#138 review, F2: a directory is never replaceable, and on Windows each replace retries for seconds; the beat
    leaves it at once, and the run reads as lost."""
    (directory / "heartbeat").mkdir()
    promptly(lambda: runlog.beat(directory), within=1)
    assert (directory / "heartbeat").is_dir() and runlog.heartbeat_age(directory) is None


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


@POSIX_ONLY
def test_a_request_queue_that_is_a_link_is_not_read_or_emptied(directory, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "a.json").write_text('{"kind": "stop"}', encoding="utf-8")
    os.symlink(elsewhere, directory / "requests")
    assert runlog.take_requests(directory) == []
    assert (elsewhere / "a.json").exists()


def test_the_event_log_appends_whole_lines(directory):
    log = runlog.EventLog(directory / "events.jsonl")
    log({"event": "one"})
    log({"event": "two"})
    lines = (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines] == ["one", "two"]


def test_an_event_log_write_that_fails_never_raises_into_the_supervisor(directory, monkeypatch):
    """#138 re-review, F3: the open succeeds and the write fails (a full disk, a file size limit, a byte-range lock
    on Windows); the thread that logged carries on."""
    path = directory / "events.jsonl"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(runlog, "_open_append", lambda p: os.open(p, os.O_RDONLY))  # a write to it fails
    runlog.EventLog(path)({"event": "x"})
    assert path.read_text(encoding="utf-8") == ""


@POSIX_ONLY
def test_the_event_log_never_blocks_on_a_fifo_or_writes_through_a_link(directory, tmp_path):
    """The supervisor's threads append under one lock: a log that blocked would stall them all, the watchdog
    included."""
    os.mkfifo(directory / "events.jsonl")
    promptly(lambda: runlog.EventLog(directory / "events.jsonl")({"event": "x"}))
    os.remove(directory / "events.jsonl")
    target = tmp_path / "target.txt"
    target.write_text("", encoding="utf-8")
    os.symlink(target, directory / "events.jsonl")
    runlog.EventLog(directory / "events.jsonl")({"event": "x"})
    assert target.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------- the credential scan at a run's end

TOKEN = "aew1.tk_" + "0" * 16 + "." + "A" * 43  # built here: no credential-shaped string sits in any file


def test_the_credential_scan_finds_a_credential_wherever_chunks_split_it(directory, monkeypatch):
    """The scan reads in overlapping chunks so a large file is never held whole; a credential that any chunk boundary
    cuts is still found."""
    monkeypatch.setattr(runlog, "SCAN_CHUNK", 32)
    harness = directory / "harness"
    harness.mkdir()
    for offset in range(0, 80):
        f = harness / f"log-{offset}.txt"
        f.write_text("x" * offset + TOKEN + "\n", encoding="utf-8")
        assert runlog.credential_scan(directory) == {"clean": False, "files": [str(f)]}, offset
        f.unlink()
    (harness / "clean.txt").write_text("x" * 500, encoding="utf-8")
    assert runlog.credential_scan(directory) == {"clean": True, "files": []}
    assert runlog.credential_scan(harness / "clean.txt") == {"clean": True, "files": []}  # a file as the root


def test_a_scan_past_its_budget_is_unscanned_never_clean(directory, monkeypatch):
    """#139 review, finding 1: one scan reads a bounded amount; what it could not read makes it incomplete, and an
    incomplete scan is not clean."""
    harness = directory / "harness"
    harness.mkdir()
    (harness / "a.txt").write_text("x" * 100, encoding="utf-8")
    (harness / "b.txt").write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(runlog, "SCAN_BUDGET_BYTES", 150)
    assert runlog.credential_scan(directory) == {"clean": False, "files": [], "unscanned": 1}
    monkeypatch.setattr(runlog, "SCAN_BUDGET_BYTES", 1 << 20)
    monkeypatch.setattr(runlog, "SCAN_MAX_ENTRIES", 1)
    assert runlog.credential_scan(directory)["unscanned"] >= 1


def test_a_sparse_file_costs_what_it_stores(directory, monkeypatch):
    """#139 review, finding 1: a file of holes (`truncate -s 16T`) is not read as zeros. Where the platform cannot say
    where the holes are, the budget still bounds it."""
    harness = directory / "harness"
    harness.mkdir()
    sparse = harness / "sparse"
    with open(sparse, "wb") as f:
        f.truncate(1 << 30)  # 1 GiB of holes
        f.seek((1 << 30) - len(TOKEN))
        f.write(TOKEN.encode())
    monkeypatch.setattr(runlog, "SCAN_BUDGET_BYTES", 1 << 24)  # 16 MiB: enough for the data, never for the holes
    result = promptly(lambda: runlog.credential_scan(directory), within=30)
    if runlog._data_ranges(os.open(sparse, os.O_RDONLY)) == [(0, 1 << 30)]:
        assert result == {"clean": False, "files": [], "unscanned": 1}  # no hole information: bounded, not clean
    else:
        assert result == {"clean": False, "files": [str(sparse)]}


def test_a_deep_tree_is_walked_without_recursion(directory):
    """#139 review, finding 4: Python 3.11's rglob recursed per level, and a run's deep tree raised RecursionError out
    of the supervisor before it saved the final record."""
    levels = [directory / "harness"]
    levels[0].mkdir()
    for _ in range(1100):
        try:
            (levels[-1] / "d").mkdir()
        except OSError:  # a path-length limit (Windows): deep enough
            break
        levels.append(levels[-1] / "d")
    leak = levels[-1] / "leak.txt"
    leak.write_text(TOKEN, encoding="utf-8")
    try:
        assert runlog.credential_scan(directory)["files"] == [str(leak)]
    finally:  # removed deepest first: Python 3.11's shutil.rmtree recurses, and pytest's cleanup would hit the limit
        leak.unlink()
        for level in reversed(levels):
            level.rmdir()


@POSIX_ONLY
def test_the_credential_scan_never_reads_through_a_link_or_blocks_on_a_fifo(directory, tmp_path):
    """The supervisor scans as the operator a directory the run could write (its harness/ even when contained): a FIFO
    never stalls the run's end, /dev/zero is never read, and a link (to a file or a directory) is not followed, nor
    a root that is itself a link."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text(TOKEN, encoding="utf-8")
    harness = directory / "harness"
    harness.mkdir()
    os.mkfifo(harness / "pipe")
    os.symlink("/dev/zero", harness / "zero")
    os.symlink(outside / "secret.txt", harness / "linked.txt")
    os.symlink(outside, harness / "linked-dir")
    leaked = harness / "leaked.txt"
    leaked.write_text(TOKEN, encoding="utf-8")
    assert promptly(lambda: runlog.credential_scan(directory)) == {"clean": False, "files": [str(leaked)]}
    os.symlink(outside, tmp_path / "root-link")
    assert runlog.credential_scan(tmp_path / "root-link") == {"clean": True, "files": []}
