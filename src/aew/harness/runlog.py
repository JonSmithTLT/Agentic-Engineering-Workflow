"""Local, deletable run records: ``.aew/local/harness/runs/<run>/`` (KC §5.3; ADR-0009).

A run directory holds the run record (``run.json``, schema ``aew/harness-run/v1``), the supervisor's
heartbeat and log, the harness's event log, the delivered prompt, Lead requests to the supervisor, and
the harness's private state. None of it is project authority and no gate reads it: deleting a run
directory loses a conversation and telemetry, never engineering state. No file here ever holds an AEW
credential; the supervisor scans the directory for one when the run ends.
"""

from __future__ import annotations

import calendar
import json
import os
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


def _read_text(path: Path) -> str | None:
    """None only when the file does not exist. On Windows a reader can briefly collide with a writer's atomic
    replace (a sharing violation): that is retried, never mistaken for absence."""
    deadline = time.monotonic() + 5.0
    while True:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.02)


def read_record(directory: Path) -> dict[str, Any] | None:
    try:
        text = _read_text(directory / "run.json")
        return json.loads(text) if text is not None else None
    except (OSError, ValueError):
        return None


def write_record(directory: Path, record: dict[str, Any]) -> None:
    record["updated_at"] = utc_now()
    atomic_write(directory / "run.json", K.redact(json.dumps(record, indent=1, sort_keys=True, default=str)) + "\n")


def beat(directory: Path) -> None:
    """The heartbeat is the modification time of ``heartbeat``: touching it never collides with a reader."""
    path = directory / "heartbeat"
    try:
        os.utime(path)
    except FileNotFoundError:
        path.touch()


def heartbeat_age(directory: Path) -> float | None:
    try:
        return max(0.0, time.time() - (directory / "heartbeat").stat().st_mtime)
    except FileNotFoundError:
        return None


def observed_status(directory: Path) -> tuple[str, dict[str, Any] | None]:
    """What local evidence says about a run: its recorded status, or ``unconfirmed`` / ``lost``."""
    record = read_record(directory)
    if record is None:
        return K.UNCONFIRMED, None
    status = record.get("status")
    if status in K.TERMINAL:
        return status, record
    age = heartbeat_age(directory)
    if age is None or age > STALE_AFTER_S:
        return K.LOST, record
    return status or K.STARTING, record


def may_be_live(directory: Path, launched_at: str | None, *, grace_s: float = 30.0) -> bool:
    """Could a supervisor for this run still hold custody? Conservative: an unconfirmed run launched
    moments ago may be between its launch commit and its first heartbeat."""
    status, _ = observed_status(directory)
    if status in (K.STARTING, K.RUNNING):
        return True
    if status == K.UNCONFIRMED and launched_at:
        try:
            launched = calendar.timegm(time.strptime(launched_at, "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            return False
        return time.time() - launched < grace_s
    return False


def request(directory: Path, kind: str, payload: dict[str, Any] | None = None) -> Path:
    """Queue a Lead request (stop, send, interrupt) for the run's supervisor."""
    queue = directory / "requests"
    queue.mkdir(parents=True, exist_ok=True)
    path = queue / f"{time.time_ns()}-{os.getpid()}-{kind}.json"
    atomic_write(path, json.dumps({"kind": kind, "at": utc_now(), **(payload or {})}))
    return path


def take_requests(directory: Path) -> list[dict[str, Any]]:
    queue = directory / "requests"
    out = []
    for path in sorted(queue.glob("*.json")) if queue.is_dir() else []:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        try:
            path.unlink()
        except OSError:
            pass
    return out


class EventLog:
    """Append-only JSON lines: harness telemetry (never chain-of-thought, never a credential).

    Several threads of one supervisor append (its own, an adapter's monitor and event reader). Appends through
    separate handles are not atomic on Windows, so they are serialized: every line stays whole."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def __call__(self, event: dict[str, Any]) -> None:
        line = K.redact(json.dumps({"at": utc_now(), **event}, default=str))
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


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
