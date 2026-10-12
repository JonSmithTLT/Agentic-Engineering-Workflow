"""The flight recorder (the hang-and-flake diagnosis plan, G3 H2): a per-process ring of the test helpers' last events.

Always on and cheap, so the evidence exists before anyone knows it is needed. Each process (the test process, an
xdist worker, every helper child started through ``childdiag``) keeps its own ring of the last :data:`CAPACITY`
events. It records subprocess spawns and exits, bounded waits and how they ended, mailbox and chat reads and writes
with their ``OSError`` and ``winerror`` codes, renames and replaces, and actor events.

The ring is flushed (one JSON object per line) on a failure, a watchdog fire and the session deadline, by the test
process's autopsy; a child flushes its own at exit and on an uncaught exception. The test process's flush goes through
``harness_diagnostics`` (redacted, capped, never ``.json``); a child writes its raw ring into its private diagnostics
directory, outside the report directory, and the autopsy copies it from there the same way.

This module imports nothing from AEW: helper children load it before anything else.
"""

from __future__ import annotations

import collections
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

CAPACITY = 4000
FIELD_CHARS = 400  # a recorded value is a summary, never a whole payload

_ring: collections.deque[dict[str, Any]] = collections.deque(maxlen=CAPACITY)
_lock = threading.Lock()
_seq = 0


def _short(value: Any) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= FIELD_CHARS else text[:FIELD_CHARS] + " …"


def record(kind: str, **facts: Any) -> None:
    """One event: its kind, the wall and monotonic time, the thread, and short facts."""
    global _seq
    with _lock:
        _seq += 1
        _ring.append({"seq": _seq, "t": round(time.time(), 3), "mono": round(time.monotonic(), 3), "pid": os.getpid(),
                      "thread": threading.current_thread().name, "kind": kind,
                      **{k: _short(v) for k, v in facts.items()}})


def os_error(exc: BaseException) -> dict[str, Any]:
    """The codes of a failed I/O: ``errno`` and, on Windows, ``winerror`` (32 and 33 are sharing violations)."""
    return {"error": type(exc).__name__, "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None), "message": str(exc)}


def io(op: str, path: str | os.PathLike[str], exc: BaseException | None = None, **facts: Any) -> None:
    """A file operation in a helper (read, write, rename, replace); a failed one keeps its path for the autopsy's
    file-holder lookup."""
    record("io", op=op, path=str(path), ok=exc is None, **(os_error(exc) if exc is not None else {}), **facts)


def spawned(argv: list[str], pid: int, **facts: Any) -> None:
    record("spawn", argv=" ".join(str(a) for a in argv[:8]), child=pid, **facts)


def exited(pid: int, returncode: int | None, duration_s: float, **facts: Any) -> None:
    record("exit", child=pid, returncode=returncode, duration_s=round(duration_s, 3), **facts)


def wait(name: str, bound_s: float, ended: str, waited_s: float, **facts: Any) -> None:
    """A bounded wait and how it ended (``ok``, ``timeout``, ``gone``, ``error``)."""
    record("wait", name=name, bound_s=bound_s, ended=ended, waited_s=round(waited_s, 3), **facts)


def snapshot() -> list[dict[str, Any]]:
    with _lock:
        return list(_ring)


def failed_paths(limit: int = 10) -> list[str]:
    """The paths of the most recent failed I/O, newest first, without repeats: what the autopsy asks the file-holder
    lookup about."""
    seen: list[str] = []
    for event in reversed(snapshot()):
        if event.get("kind") == "io" and event.get("ok") is False and event.get("path") not in seen:
            seen.append(str(event["path"]))
            if len(seen) >= limit:
                break
    return seen


def lines() -> str:
    return "".join(json.dumps(e, default=str) + "\n" for e in snapshot())


def flush_raw(directory: Path) -> Path | None:
    """A child's own flush, into its private diagnostics directory (never the report directory): the autopsy copies
    it from there, redacted. Never raises: it runs at exit and from an exception hook."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"recorder-{os.getpid()}.jsonl"
        path.write_text(lines(), encoding="utf-8")
        return path
    except OSError:
        return None


def clear() -> None:
    with _lock:
        _ring.clear()
