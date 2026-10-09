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
import re
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO

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


def _open_regular(path: Path) -> BinaryIO:
    """A regular file opened for reading. The run directory is writable by the run's own user: a symlink is not
    followed and a FIFO or device never blocks the open, each refused as an ``OSError``."""
    if os.name == "nt":  # no O_NOFOLLOW: refuse a link or a non-file before opening it
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    f = os.fdopen(os.open(path, flags), "rb")
    try:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
    except BaseException:
        f.close()
        raise
    return f


def _read_regular(path: Path) -> bytes:
    """A regular file's bytes, at most ``MAX_RECORD_BYTES`` (``_open_regular``). A Lead transaction reads the run
    directory under the control lock (the usage copy, F25 R5), the supervisor's watchdog its request queue: a file
    past the bound is refused, as an ``OSError``."""
    with _open_regular(path) as f:
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
            try:  # the log is telemetry: one that cannot be opened or written never stops the supervisor
                with os.fdopen(_open_append(self.path), "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:  # a full disk, a file size limit, a byte-range lock on Windows (#138 re-review, F3)
                return


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


SCAN_CHUNK = 1 << 20
# A credential is recognized from its first 45 characters (``aew1.tk_``, 16 hex digits, a dot and 20 more), so chunks
# that overlap by more than that never split one past recognition.
SCAN_OVERLAP = 64
# What one scan reads at most: the data (never the holes) of every regular file, and the entries it walks. A run's own
# state is far below both; past them, the rest is reported unscanned rather than clean (#139 review, finding 1).
SCAN_BUDGET_BYTES = 4 << 30
SCAN_MAX_ENTRIES = 200_000
_CREDENTIAL_BYTES = re.compile(K.CREDENTIAL_RE.pattern.encode("ascii"))
# An entry that vanished between the listing and its read holds nothing: not a reason to call the scan incomplete.
_GONE = (FileNotFoundError, NotADirectoryError)


def credential_scan(*roots: Path) -> dict[str, Any]:
    """The files under ``roots`` holding an AEW credential string (custody property 4), as the run record keeps it:
    ``{"clean", "files"}``, and ``unscanned`` when something could not be read whole.

    The supervisor scans as the operator, at the end of a run, a directory the run's own user could write (its
    ``harness/`` even under containment), so the walk and every read are defensive:

    - the walk is iterative (a deep tree never exhausts the stack) and never enters a link or, on Windows, any other
      reparse point (a junction): only the run's own directories are walked;
    - only regular files are read, never through a link and never blocking on a FIFO or device (``_open_regular``);
    - a file is read in overlapping chunks with its holes skipped (a sparse file costs what it stores), within one
      budget of bytes and entries for the whole scan.

    Anything the scan could not read (a file or directory it cannot open, the rest past the budget) is counted in
    ``unscanned``, and then ``clean`` is false: clean means scanned and clean. A link, FIFO, socket or device stores
    nothing of the run's, so skipping one leaves nothing unscanned."""
    found: list[str] = []
    budget = {"bytes": SCAN_BUDGET_BYTES, "entries": SCAN_MAX_ENTRIES, "unscanned": 0}
    for root in roots:
        try:
            top = os.lstat(root)
        except OSError:
            continue
        if stat.S_ISREG(top.st_mode):
            _scan_file(root, found, budget)
        elif stat.S_ISDIR(top.st_mode):
            _walk(root, found, budget)
    out: dict[str, Any] = {"clean": not found and not budget["unscanned"], "files": found}
    if budget["unscanned"]:
        out["unscanned"] = budget["unscanned"]
    return out


def _walk(root: Path, found: list[str], budget: dict[str, int]) -> None:
    stack = [root]
    while stack:
        directory = stack.pop()
        listed = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:  # the cap holds while listing: one huge directory is never listed whole
                    if len(listed) >= budget["entries"]:
                        budget["unscanned"] += 1 + len(stack)
                        return
                    listed.append(entry)
        except _GONE:  # removed or replaced since it was listed: it holds nothing now (#139 re-review, F2)
            continue
        except OSError:  # unreadable
            budget["unscanned"] += 1
            continue
        budget["entries"] -= len(listed)
        for entry in sorted(listed, key=lambda e: e.name):
            try:
                info = entry.stat(follow_symlinks=False)
            except _GONE:
                continue
            except OSError:
                budget["unscanned"] += 1
                continue
            if stat.S_ISDIR(info.st_mode):
                # A junction or mount point is a directory that is a reparse point: not the run's own (Windows). A
                # reparse point that is a file (a cloud or deduplicated file) is read like any other (F3).
                if not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    stack.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                _scan_file(Path(entry.path), found, budget)


def _scan_file(path: Path, found: list[str], budget: dict[str, int]) -> None:
    try:
        hit = _contains_credential(path, budget)
    except _GONE:  # renamed or removed since it was listed (an atomic write's temporary file): nothing to read
        return
    except OSError:
        budget["unscanned"] += 1
        return
    if hit is None:
        budget["unscanned"] += 1
    elif hit:
        found.append(str(path))


def _contains_credential(path: Path, budget: dict[str, int]) -> bool | None:
    """Whether ``path`` holds a credential; None when the budget ran out before it was read whole."""
    with _open_regular(path) as f:
        fd = f.fileno()
        for start, end in _data_ranges(fd):
            os.lseek(fd, start, os.SEEK_SET)
            tail, left = b"", end - start
            while left > 0:
                if budget["bytes"] <= 0:
                    return None
                chunk = os.read(fd, min(SCAN_CHUNK, left, budget["bytes"]))
                if not chunk:
                    break
                left -= len(chunk)
                budget["bytes"] -= len(chunk)
                text = tail + chunk
                if _CREDENTIAL_BYTES.search(text):
                    return True
                tail = text[-SCAN_OVERLAP:]
    return False


def _data_ranges(fd: int) -> list[tuple[int, int]]:
    """The byte ranges of a file that hold data: holes read as zeros and can hold no credential. The whole file where
    the platform or filesystem cannot say."""
    size = os.fstat(fd).st_size
    seek_data, seek_hole = getattr(os, "SEEK_DATA", None), getattr(os, "SEEK_HOLE", None)
    if seek_data is None or seek_hole is None:
        return [(0, size)]
    ranges, pos = [], 0
    try:
        while pos < size:
            try:
                start = os.lseek(fd, pos, seek_data)
            except OSError as exc:
                if exc.errno == errno.ENXIO:  # no data past pos
                    break
                raise
            end = os.lseek(fd, start, seek_hole)
            ranges.append((start, end))
            pos = end
    except OSError:
        return [(0, size)]
    return ranges
