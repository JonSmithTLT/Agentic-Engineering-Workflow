"""Local, deletable run records: ``.aew/local/harness/runs/<run>/`` (KC §5.3; ADR-0009).

A run directory holds the run record (``run.json``, schema ``aew/harness-run/v1``), the supervisor's
heartbeat and log, the harness's event log, the delivered prompt, Lead requests to the supervisor, and
the harness's private state. None of it is project authority and no gate reads it: deleting a run
directory loses a conversation and telemetry, never engineering state. No file here ever holds an AEW
credential; the supervisor scans the directory for one when the run ends.
"""

from __future__ import annotations

import calendar
import errno
import json
import os
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any

from aew.harness import contract as K
from aew.util import atomic_write, utc_now

RUNS_REL = "local/harness/runs"
HEARTBEAT_S = 1.0
# A supervisor that has not beaten for this long has stopped supervising (tests shorten it).
STALE_AFTER_S = float(os.environ.get("AEW_RUN_STALE_S", "10"))


def run_dir(aew_root: Path, run: str) -> Path:
    return aew_root / RUNS_REL / run


# A run record's own bound: its timeline and the bridge's request list grow with the run, but never near this. A file
# past it is not a record the supervisor wrote, and is not read whole under the control lock (#137 re-review).
MAX_RECORD_BYTES = 16 << 20


def _read_regular(path: Path) -> bytes:
    """A regular file's bytes, at most ``MAX_RECORD_BYTES``. The run directory is writable by the run's own user,
    and a Lead transaction reads it under the control lock (the usage copy, F25 R5), the supervisor's watchdog its
    request queue: a symlink is not followed, a FIFO or device never blocks the open or the read, and a file past the
    bound is refused, each as an ``OSError``."""
    if os.name == "nt":  # no O_NOFOLLOW: refuse a link or a non-file before opening it
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
        data = f.read(MAX_RECORD_BYTES + 1)
    if len(data) > MAX_RECORD_BYTES:
        raise OSError(errno.EFBIG, "past the bound of a run file", str(path))
    return data


def _read_text(path: Path) -> str | None:
    """None only when the file does not exist. On Windows a reader can briefly collide with a writer's atomic
    replace (a sharing violation): that is retried, never mistaken for absence. Elsewhere a permission error is
    final: retrying it would only hold the control lock longer."""
    deadline = time.monotonic() + 5.0
    while True:
        try:
            return _read_regular(path).decode("utf-8")
        except FileNotFoundError:
            return None
        except PermissionError:
            if os.name != "nt" or time.monotonic() > deadline:
                raise
            time.sleep(0.02)


def read_record(directory: Path) -> dict[str, Any] | None:
    try:
        text = _read_text(directory / "run.json")
        record = json.loads(text) if text is not None else None
    except (OSError, ValueError, RecursionError):  # nesting past the parser's depth is no record (#137 re-review, F1)
        return None
    # The run directory is writable by the run's own user (the supervisor's note on local/): a record that is not an
    # object is no record, so no reader of it (a cancel's usage copy among them) fails on its shape (#137 review, F1).
    return record if isinstance(record, dict) else None


def write_record(directory: Path, record: dict[str, Any]) -> None:
    record["updated_at"] = utc_now()
    atomic_write(directory / "run.json", K.redact(json.dumps(record, indent=1, sort_keys=True, default=str)) + "\n")
    # A changed run record wakes waiters (ADR-0012 D4; advisory). ``directory`` is <aew root>/local/harness/runs/<run>.
    aew_root = directory.parents[len(Path(RUNS_REL).parts)]
    if directory.parent == aew_root / RUNS_REL:
        from aew.engine.outbox import bump_wake

        bump_wake(aew_root)


def beat(directory: Path) -> None:
    """The heartbeat is the modification time of ``heartbeat``: touching it never collides with a reader.

    The supervisor runs as the operator, and an uncontained run can write its own run directory: a beat never
    follows a link (it would create or touch a file wherever the link points) and never blocks on a FIFO. A heartbeat
    that is not a regular file is replaced by one; one that cannot be replaced (a directory) is left, and the run
    reads as ``lost``, which is what a supervisor that cannot beat is. A beat never raises."""
    path = directory / "heartbeat"
    try:
        if sys.platform != "win32":  # utime on a descriptor (os.supports_fd) is POSIX
            flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK
            try:
                fd = os.open(path, flags, 0o644)
            except OSError:  # a link (ELOOP), a FIFO with no reader (ENXIO), a directory (EISDIR)
                fd = None
            if fd is not None:
                try:
                    if stat.S_ISREG(os.fstat(fd).st_mode):
                        os.utime(fd)
                        return
                finally:
                    os.close(fd)
            mode = os.lstat(path).st_mode
        else:  # Windows: no O_NOFOLLOW; touch only what lstat shows is a regular file
            try:
                mode = os.lstat(path).st_mode
            except FileNotFoundError:
                path.touch()
                return
            if stat.S_ISREG(mode):
                os.utime(path)
                return
        if stat.S_ISDIR(mode):  # never replaceable; on Windows each attempt retries for seconds (#138 review, F2)
            return
        atomic_write(path, "")  # replaces the link or FIFO itself, never what it points to
    except OSError:
        pass


def heartbeat_age(directory: Path) -> float | None:
    """The heartbeat's age, or None when there is none. Only a regular file beats: the file is not followed, and a
    link, a directory or one that cannot be read is no heartbeat (the run reads as ``lost``), never an error that
    fails the reader (#137 re-review: the run's own user can replace it)."""
    try:
        info = os.lstat(directory / "heartbeat")
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return max(0.0, time.time() - info.st_mtime)


def observed_status(directory: Path) -> tuple[str, dict[str, Any] | None]:
    """What local evidence says about a run: its recorded status, or ``unconfirmed`` / ``lost``."""
    record = read_record(directory)
    if record is None:
        return K.UNCONFIRMED, None
    status = record.get("status")
    if not isinstance(status, str):
        status = None
    if status in K.TERMINAL:
        return status, record
    age = heartbeat_age(directory)
    if age is None or age > STALE_AFTER_S:
        return K.LOST, record
    return status or K.STARTING, record


UNCONFIRMED_GRACE_S = 30.0


def possibly_live(status: str, launched_at: str | None, *, grace_s: float = UNCONFIRMED_GRACE_S) -> bool:
    """Could a supervisor for a run in ``status`` still hold custody? Conservative: an unconfirmed run launched
    moments ago may be between its launch commit and its first record."""
    if status in (K.STARTING, K.RUNNING):
        return True
    if status == K.UNCONFIRMED and launched_at:
        try:
            launched = calendar.timegm(time.strptime(launched_at, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            return False
        return time.time() - launched < grace_s
    return False


def may_be_live(directory: Path, launched_at: str | None, *, grace_s: float = UNCONFIRMED_GRACE_S) -> bool:
    """:func:`possibly_live` for the run's observed status now."""
    status, _ = observed_status(directory)
    return possibly_live(status, launched_at, grace_s=grace_s)


def new_request(kind: str, payload: dict[str, Any] | None = None) -> tuple[str, str]:
    """A Lead request (stop, send, interrupt) for a run's supervisor: its file name and text.

    The run directory is model-writable, so a request file alone authorizes nothing: the Lead operation records the
    name and digest in control state first (``harness_ops``), then delivers the file with :func:`deliver_request`,
    and the supervisor acts only on a file that matches a recorded request (independent review R1)."""
    name = f"{time.time_ns()}-{os.getpid()}-{kind}.json"
    return name, json.dumps({"kind": kind, "at": utc_now(), **(payload or {})})


def deliver_request(directory: Path, name: str, text: str) -> Path:
    queue = directory / "requests"
    queue.mkdir(parents=True, exist_ok=True)
    path = queue / name
    atomic_write(path, text)
    return path


def take_requests(directory: Path) -> list[tuple[str, str]]:
    """Every queued request file as (name, text), removed from the queue. Nothing here is trusted."""
    queue = directory / "requests"
    out = []
    try:  # a queue that is a link is not the run's queue: its target's files are never read or removed
        is_queue = stat.S_ISDIR(os.lstat(queue).st_mode)
    except OSError:
        is_queue = False
    for path in sorted(queue.glob("*.json")) if is_queue else []:
        try:
            # Read as a run record is: no link followed, no FIFO blocked on, bounded. The watchdog loop takes the
            # queue, so a request that could block it would stop the deadline and every later Lead request.
            out.append((path.name, _read_regular(path).decode("utf-8", errors="replace")))
        except OSError:
            pass
        try:
            path.unlink()
        except OSError:
            pass
    return out


def end_supervisor(directory: Path) -> bool:
    """Kill a run's supervisor process, if it is still the one that took custody (pids are reused). Its job object
    or process group then ends the harness tree. For teardown by the operator's own tooling, which can end any of
    its processes anyway; it needs no request and leaves no state behind (the run shows as lost)."""
    from aew.harness import procs

    record = read_record(directory) or {}
    pid, custody = record.get("supervisor_pid"), record.get("custody_at")
    if record.get("ended_at") or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 \
            or not isinstance(custody, str):
        return False  # a record the supervisor did not write names no process to end
    try:
        custody_epoch = calendar.timegm(time.strptime(custody, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return False
    if not procs.same_process(pid, custody_epoch):
        return False
    procs.kill_pid(pid)
    return True


class EventLog:
    """Append-only JSON lines: harness telemetry (never chain-of-thought, never a credential).

    Several threads of one supervisor append (its own, an adapter's monitor and event reader). Appends through
    separate handles are not atomic on Windows, so they are serialized: every line stays whole."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def __call__(self, event: dict[str, Any]) -> None:
        line = K.redact(json.dumps({"at": utc_now(), **event}, default=str))
        with self._lock:
            try:
                fd = _open_append(self.path)
            except OSError:  # the log is telemetry: one that cannot be appended to never stops the supervisor
                return
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def _open_append(path: Path) -> int:
    """A descriptor appending to a regular file, created if absent. The supervisor's threads append under one lock,
    so a FIFO or a link in the run directory must neither block that lock nor redirect the write."""
    if sys.platform != "win32":
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644)
    else:
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                raise OSError(errno.EINVAL, "not a regular file", str(path))
        except FileNotFoundError:
            pass
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_BINARY, 0o644)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
    except BaseException:
        os.close(fd)
        raise
    return fd


def scan_for_credentials(*roots: Path) -> list[str]:
    """Files under ``roots`` containing an AEW credential string (custody property 4)."""
    found = []
    for root in roots:
        if not root.exists():
            continue
        for path in [root] if root.is_file() else root.rglob("*"):
            try:
                if path.is_file() and K.CREDENTIAL_RE.search(path.read_bytes().decode("latin-1")):
                    found.append(str(path))
            except OSError:
                continue
    return found
