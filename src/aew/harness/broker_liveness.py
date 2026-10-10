"""The Lead broker's liveness record (M4-E plan v3 §2.8, N3; amendment 1, M2, R2-m3, R3-n2, R4-m1).

The operator endpoint tells the operator when the Lead's broker is gone (``generation_ended`` with reason ``crash`` or
``stale``, and ``broker_gone`` while Run is effective). It learns that from ``.aew/local/lead/broker.json``, which the
broker keeps current:

- **A beat thread of its own** (:class:`Beat`), started and stopped with the broker's watchdog, writes
  ``{pid, process_started, generation, beat_at, watchdog_tick_at, wedge_after_s}`` atomically every ``POLL_S``. It
  never reads the store, so a watchdog iteration waiting on the control lock never stops the beat (R2-m3).
- ``watchdog_tick_at`` is when the watchdog loop last completed an iteration, read from memory. A beat whose tick is
  older than the wedge threshold, ``store.lock_timeout + 2 × POLL_S`` of the broker's own engine store, is a wedged
  watchdog: past any lock wait it can legitimately be in (R3-n2, R4-m1). The broker records the threshold, so the
  watcher in another process follows the broker's own (possibly injected) lock timeout.
- ``close()``, and the watchdog's return on supersession, write ``closed_at``: a clean end, never a crash.

**Judged** (:func:`judge`) only for a record whose ``generation`` is the current Lead generation: ``closed`` when it
has ``closed_at``; ``crash`` when its process is gone, by the endpoint locator's own pid-and-start-time check; ``stale``
when it is alive with no beat for 2 × ``POLL_S``, or its watchdog is wedged.

**Trust.** The record is local state under ``.aew/local/``, never control state. A same-uid process can forge it (the
residual of plan v3 §2.1): it only ever notifies, and grants and moves nothing.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.harness import procs
from aew.util import replace_with_retry

REL = "local/lead/broker.json"
SCHEMA = "aew/broker-liveness/v1"
MAX_BYTES = 4096  # a record is about 250 bytes; a file past this is not one the broker wrote
MAX_WEDGE_S = 3600.0  # a recorded threshold is clamped: a forged one cannot hide a wedge for longer

log = logging.getLogger(__name__)


def path(aew_root: Path) -> Path:
    return Path(aew_root) / REL


def wedge_threshold_s(lock_timeout: float, poll_s: float) -> float:
    """``store.lock_timeout + 2 × POLL_S``: a watchdog iteration waiting on the control lock is never stale (R4-m1)."""
    return float(lock_timeout) + 2.0 * float(poll_s)


class Beat:
    """The broker's beat thread. :meth:`tick` is the watchdog's: it records a completed iteration (memory only)."""

    def __init__(self, aew_root: Path, *, generation: int, poll_s: float, wedge_after_s: float) -> None:
        self.aew_root = Path(aew_root)
        self.generation = generation
        self.poll_s = poll_s
        self.wedge_after_s = wedge_after_s
        self.pid = os.getpid()
        self.process_started = procs.started_at(self.pid)
        self._tick_at = time.time()
        self._stop = threading.Event()
        self._mu = threading.Lock()  # a beat and the closing write never interleave
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="aew-lead-broker-beat", daemon=True)

    def tick(self) -> None:
        self._tick_at = time.time()

    def start(self) -> None:
        self._write(None)
        self._thread.start()

    def close(self) -> None:
        """Stop beating and write ``closed_at``, unless the record now names another broker (a newer generation's
        broker may already beat into the same file: a superseded broker never overwrites it)."""
        self._stop.set()
        with self._mu:
            if self._closed:
                return
            self._closed = True
            current = read(self.aew_root)
            if current is None or (current["pid"], current["process_started"]) == (self.pid, self.process_started):
                self._write_locked(time.time())
        if self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(max(1.0, 2 * self.poll_s))

    def _run(self) -> None:
        while not self._stop.wait(self.poll_s):
            self._write(None)

    def _write(self, closed_at: float | None) -> None:
        with self._mu:
            if not self._closed:
                self._write_locked(closed_at)

    def _write_locked(self, closed_at: float | None) -> None:
        record: dict[str, Any] = {"schema": SCHEMA, "pid": self.pid, "process_started": self.process_started,
                                  "generation": self.generation, "beat_at": time.time(),
                                  "watchdog_tick_at": self._tick_at, "wedge_after_s": self.wedge_after_s}
        if closed_at is not None:
            record["closed_at"] = closed_at
        write(self.aew_root, record)


def write(aew_root: Path, record: dict[str, Any]) -> None:
    """Replace the record atomically (no fsync: liveness, not durability). Never raises: a beat that cannot be
    written is a broker that reads as stale, which is what it is to the watcher."""
    target = path(aew_root)
    tmp = target.with_name(f".broker.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        replace_with_retry(tmp, target)
    except OSError as exc:
        log.warning("the broker liveness record %s could not be written: %s", target, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def read(aew_root: Path) -> dict[str, Any] | None:
    """The record, or ``None`` when there is none or it is not one the broker wrote (a link, a directory, an oversize
    or malformed file): untrusted local data, checked field by field."""
    target = path(aew_root)
    try:
        info = os.lstat(target)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            return None
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    if not (isinstance(data.get("pid"), int) and not isinstance(data["pid"], bool) and data["pid"] > 0
            and isinstance(data.get("generation"), int) and not isinstance(data["generation"], bool)
            and all(_number(data.get(k)) for k in ("beat_at", "watchdog_tick_at", "wedge_after_s"))
            and (data.get("process_started") is None or _number(data["process_started"]))
            and (data.get("closed_at") is None or _number(data["closed_at"]))):
        return None
    return data


@dataclass(frozen=True)
class Verdict:
    """What the record says about the current generation's broker. ``occurrence`` identifies this occurrence, so
    the watcher delivers each once (the delivery log keys it)."""

    reason: str  # "closed", "crash" or "stale"
    occurrence: str
    detail: str


def judge(record: dict[str, Any] | None, *, generation: int, poll_s: float,
          now: float | None = None) -> Verdict | None:
    """The verdict on ``record`` for the current Lead ``generation``, or ``None`` (no record, another generation's, or
    a live broker that beats and whose watchdog completes its iterations)."""
    from aew.harness.operator_client import same_process

    if record is None or record["generation"] != generation:
        return None
    process = f"{record['pid']}@{record.get('process_started')}"
    if record.get("closed_at") is not None:
        return Verdict("closed", f"{process}:closed:{record['closed_at']}", "the broker ended cleanly")
    if not same_process(record):
        return Verdict("crash", f"{process}:crash", f"the broker's process ({record['pid']}) is gone and it never "
                                                    "recorded a clean end")
    now = time.time() if now is None else now
    beat_age = now - float(record["beat_at"])
    if beat_age > 2.0 * poll_s:
        return Verdict("stale", f"{process}:beat:{record['beat_at']}",
                       f"the broker's process is alive but has not beaten for {beat_age:.1f}s")
    wedge = min(max(float(record["wedge_after_s"]), 2.0 * poll_s), MAX_WEDGE_S)
    tick_age = now - float(record["watchdog_tick_at"])
    if tick_age > wedge:
        return Verdict("stale", f"{process}:tick:{record['watchdog_tick_at']}",
                       f"the broker's watchdog has not completed an iteration for {tick_age:.1f}s (past "
                       f"{wedge:.1f}s, its lock timeout plus 2 x POLL_S)")
    return None
