"""The operator notifier: the endpoint's watcher and its delivery (M4-E plan v3 §2.8 and E7, operator decision 1;
amendment 1, E7a).

**Who delivers.** ``aew operator serve`` (:class:`Watcher`, started and stopped with the endpoint): it is
attachment-independent and supervisor-side, so what matters most while no Lead or broker is alive still reaches the
operator (N3). Nothing here grants, moves or commits anything: a notification is attention, never authority.

**What it watches,** in one pass every ``POLL_S`` and at each commit (``outbox.wait_for`` on the wake file):

- control state, read with the store's lock-free reader (``read_committed``; the watcher commits nothing): the Lead
  generation ending by ``takeover``, ``handoff`` or ``release`` (from the transition log after the watcher's cursor),
  the Lead's open requests (``raise_requested``, ``confirmation_requested``), the validation circuit breaker opening
  (``breaker_tripped``) and a lease marked for reconciliation (``custodian_lost``);
- the broker's liveness record (``harness.broker_liveness``): ``generation_ended`` with ``crash`` or ``stale``, judged
  only for the current generation, and ``broker_gone`` while Run is effective, whatever the cause (``crash``,
  ``stale``, or ``closed`` for a clean end with the seat still held; R3-m1);
- the event spool (``harness.event_spool``): ``hard_deadline`` and ``launch_failed`` from each run's supervisor,
  untrusted, at most :data:`RATE_PER_MINUTE` deliveries per writer per minute.

**Once per occurrence.** Each event has a key naming its occurrence; the delivery log
(``.aew/local/notify/deliveries.jsonl``) records it once, delivered, failed or dropped, and a key it holds is never
delivered again, across passes and endpoint restarts.

**Delivery** (decision 1) on one thread with a bounded queue, never holding the endpoint's ``_authorizing`` or
``_engine_lock`` (a slow notifier never delays a challenge), through an engine of its own: the adopted execution
policy's ``notify.command`` as an argv with no shell, the event as JSON on stdin, the sanitized environment
(:func:`sanitized_env`), ``CREATE_NO_WINDOW`` on Windows and a new session on POSIX (``procs.ProcessTree``),
``close_fds=True`` (the child inherits no endpoint lock or listener handle). Past ``timeout_s`` the process tree is
killed; output past ``max_output_bytes`` is discarded and counted, and no output is kept. A non-zero exit, a timeout, a
spawn failure or a notifier that is not configured or not executable is a delivery failure: recorded in the log,
summarized in ``state.json`` for ``status`` and the dashboard's attention (:func:`summary`), with no workflow effect.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import queue
import re
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from aew.harness import broker_liveness, event_spool, procs, runlog
from aew.harness import contract as K
from aew.harness.agentenv import POSIX_KEEP, WINDOWS_KEEP
from aew.util import replace_with_retry, utc_now

NOTIFY_REL = "local/notify"
DELIVERIES = "deliveries.jsonl"
STATE = "state.json"
PAYLOAD_SCHEMA = "aew/notify-event/v1"
STATE_SCHEMA = "aew/notify-state/v1"
DEFAULT_TIMEOUT_S = 10
DEFAULT_MAX_OUTPUT_BYTES = 65536
QUEUE_MAX = 64  # events waiting for the delivery thread; past it an event is dropped and counted
RATE_PER_MINUTE = 10  # deliveries per spool writer per minute (amendment 1, m9)
MAX_CATCHUP = 1024  # transitions read per pass; a watcher further behind skips the older ones, counted
LOG_MAX_BYTES = 1 << 20
LOG_KEEP = 2  # rotated delivery logs kept: deliveries.1.jsonl, deliveries.2.jsonl
STATE_MAX_BYTES = 1 << 20
REAP_S = 5.0  # how long a delivery waits for its pipes and process tree after the notifier ended or was killed
# The Lead generation ends by these operations, read from the transition log (plan v3 §2.8; crash and stale come from
# the broker's liveness record).
GENERATION_OPS = {"lead.takeover": "takeover", "lead.handoff.accept": "handoff", "lead.release": "release"}
# Names of variables that carry a provider key or another secret: never passed to the notifier, even when a keep-list
# name matches (plan v3 E7: the run bridge's curated keep-list minus every AEW_* and provider-key variable).
SECRET_NAME = re.compile(r"(API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.I)

log = logging.getLogger(__name__)


def notify_dir(aew_root: Path) -> Path:
    return Path(aew_root) / NOTIFY_REL


# ---------------------------------------------------------------------------------------------- the payload


def payload(*, event: str, project_id: str, subject: str | None, reason: str | None, ref: str | None,
            revision: int | None, source: str, authenticated: bool, reason_code: str | None = None) -> dict[str, Any]:
    """One ``aew/notify-event/v1`` object, validated (every string capped and cleaned of control characters)."""
    from aew import schemas

    out: dict[str, Any] = {"schema": PAYLOAD_SCHEMA, "event": event, "project_id": str(project_id),
                           "subject": event_spool.clean(subject), "reason": event_spool.clean(reason),
                           "ref": event_spool.clean(ref), "revision": revision, "at": utc_now(), "source": source,
                           "authenticated": authenticated}
    if reason_code is not None:
        out["reason_code"] = event_spool.clean(reason_code, 64)
    schemas.validate("notify-event", out, source=f"notification {event}")
    return out


# ---------------------------------------------------------------------------------------------- delivery


def sanitized_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The notifier's environment: the run bridge's curated keep-list (``agentenv``: the operating system's basics,
    ``LC_*`` on POSIX, ``PATH``), minus every ``AEW_*`` variable, every provider-key or secret name, and any variable
    whose value holds an AEW credential (plan v3 E7). Nothing else the endpoint's shell held reaches it."""
    source = dict(os.environ) if base is None else dict(base)
    keep = WINDOWS_KEEP if sys.platform == "win32" else POSIX_KEEP
    env = {k: v for k, v in source.items()
           if k.upper() in keep or k.upper() == "PATH" or (sys.platform != "win32" and k.startswith("LC_"))}
    env = {k: v for k, v in env.items() if not k.upper().startswith("AEW_") and not SECRET_NAME.search(k)}
    return K.scrub_credentials(env)


def deliver(command: list[str], event: dict[str, Any], *, timeout_s: float, max_output_bytes: int,
            cwd: str | None = None, env: dict[str, str] | None = None,
            tree: procs.ProcessTree | None = None) -> dict[str, Any]:
    """Run the notifier once for ``event``: argv, no shell, the event as JSON on stdin. Returns the outcome
    (``delivered`` or ``failed`` with its reason) and the counts the delivery log records; it never raises."""
    data = (json.dumps(event, sort_keys=True) + "\n").encode("utf-8")
    tree = tree if tree is not None else procs.ProcessTree()
    started = time.monotonic()
    out: dict[str, Any] = {"outcome": "failed", "reason": None, "exit_code": None, "timed_out": False,
                           "output_bytes": 0, "discarded_bytes": 0}
    try:
        # ProcessTree: CREATE_NO_WINDOW in a kill-on-close job on Windows, a new session on POSIX, so the whole tree
        # is killed past the timeout. close_fds: the child inherits only its three pipes, never the endpoint's lock
        # or listener (amendment 1, m9).
        proc = tree.spawn(list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          env=sanitized_env() if env is None else env, cwd=cwd, close_fds=True)
    except (OSError, ValueError) as exc:
        tree.close(REAP_S)
        out.update(reason="spawn_failed", detail=event_spool.clean(f"{type(exc).__name__}: {exc}"),
                   duration_ms=int((time.monotonic() - started) * 1000))
        return out
    assert proc.stdin is not None and proc.stdout is not None
    stdout_fd = proc.stdout.fileno()

    def pump() -> None:  # read everything the notifier writes; keep a count only, never the bytes
        while True:
            try:
                chunk = os.read(stdout_fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            keep = max(0, min(len(chunk), max_output_bytes - out["output_bytes"]))
            out["output_bytes"] += keep
            out["discarded_bytes"] += len(chunk) - keep

    def feed() -> None:
        try:
            assert proc.stdin is not None
            proc.stdin.write(data)
            proc.stdin.close()
        except (OSError, ValueError):
            pass  # a notifier that never reads its stdin

    reader = threading.Thread(target=pump, name="aew-notify-output", daemon=True)
    writer = threading.Thread(target=feed, name="aew-notify-input", daemon=True)
    reader.start()
    writer.start()
    try:
        out["exit_code"] = proc.wait(timeout_s)
    except subprocess.TimeoutExpired:
        out["timed_out"] = True
        tree.kill()  # the whole tree: whatever the notifier started goes with it
        try:
            out["exit_code"] = proc.wait(REAP_S)
        except subprocess.TimeoutExpired:
            pass
    finally:
        tree.close(REAP_S)  # nothing the notifier started outlives its delivery
    writer.join(REAP_S)
    reader.join(REAP_S)
    if not reader.is_alive():
        proc.stdout.close()
    if out["timed_out"]:
        out["reason"] = "timeout"
    elif out["exit_code"] != 0:
        out["reason"] = "exit_code"
    else:
        out["outcome"] = "delivered"
    out["duration_ms"] = int((time.monotonic() - started) * 1000)
    return out


# ---------------------------------------------------------------------------------------------- the delivery log


class DeliveryLog:
    """``deliveries.jsonl``: one line per occurrence (delivered, failed or dropped), keyed; bounded and rotated like
    the typed-tool log. The keys of every kept file are loaded once, so a restarted endpoint delivers nothing twice."""

    def __init__(self, aew_root: Path) -> None:
        self.dir = notify_dir(aew_root)
        self.path = self.dir / DELIVERIES
        self._mu = threading.Lock()
        self.keys: set[str] = set()
        for p in [*(self._rotated(n) for n in range(LOG_KEEP, 0, -1)), self.path]:
            for line in _lines(p):
                if isinstance(line.get("key"), str):
                    self.keys.add(line["key"])

    def _rotated(self, n: int) -> Path:
        return self.dir / f"deliveries.{n}.jsonl"

    def seen(self, key: str) -> bool:
        with self._mu:
            return key in self.keys

    def record(self, entry: dict[str, Any]) -> None:
        text = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        with self._mu:
            self.keys.add(entry["key"])
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
                try:
                    full = self.path.stat().st_size + len(text) > LOG_MAX_BYTES
                except FileNotFoundError:
                    full = False
                if full:
                    for n in range(LOG_KEEP - 1, 0, -1):
                        if self._rotated(n).exists():
                            os.replace(self._rotated(n), self._rotated(n + 1))
                    os.replace(self.path, self._rotated(1))
                with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            except OSError as exc:
                log.warning("the notifier's delivery log %s could not be written: %s", self.path, exc)


def _lines(path: Path) -> list[dict[str, Any]]:
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for raw in text.splitlines():
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        if isinstance(line, dict):
            out.append(line)
    return out


def deliveries(aew_root: Path) -> list[dict[str, Any]]:
    """Every kept delivery-log line, oldest first (for tests and diagnosis)."""
    d = notify_dir(aew_root)
    return [x for p in [*(d / f"deliveries.{n}.jsonl" for n in range(LOG_KEEP, 0, -1)), d / DELIVERIES]
            for x in _lines(p)]


# ---------------------------------------------------------------------------------------------- status


def summary(aew_root: Path) -> dict[str, Any] | None:
    """What ``status`` and the dashboard show: deliveries and failures, the last failure, and what was dropped.
    ``attention`` is true while the latest delivery failed (a later success clears it; the counts stay). ``None``
    when the endpoint has never watched this project. Read from the watcher's ``state.json``, checked field by
    field: a local file, never trusted for anything but display."""
    path = notify_dir(aew_root) / STATE
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > STATE_MAX_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("schema") != STATE_SCHEMA:
        return None

    def count(value: Any) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    last = _dict(data.get("last_failure")) or None
    dropped = _dict(data.get("dropped"))
    out: dict[str, Any] = {"delivered": count(data.get("delivered")), "failed": count(data.get("failed")),
                           "consecutive_failures": count(data.get("consecutive_failures")),
                           "dropped": {str(k)[:32]: count(v) for k, v in list(dropped.items())[:16] if count(v)},
                           "updated_at": event_spool.clean(data.get("updated_at"), 40)}
    if last is not None:
        out["last_failure"] = {k: event_spool.clean(last.get(k)) for k in ("event", "at", "reason", "detail")}
    out["attention"] = out["consecutive_failures"] > 0
    return out


# ---------------------------------------------------------------------------------------------- the watcher


class Watcher:
    """The endpoint's watcher (the endpoint starts and stops it). It reads, derives and delivers; it never commits.
    It runs on its own engine for the project, so it shares no object with the endpoint's operations."""

    def __init__(self, repo_root: Path, aew_root: Path) -> None:
        from aew.engine.api import Engine

        self.engine = Engine(Path(repo_root), Path(aew_root))
        self.aew_root = Path(aew_root)
        self.log = DeliveryLog(self.aew_root)
        self._mu = threading.Lock()  # the counts, the pending sets and the cursor snapshot
        self._save_mu = threading.Lock()  # one state.json write at a time
        self._pass_mu = threading.Lock()  # one pass at a time: a pass owns the cursors
        self._closed = threading.Event()
        self._queue: queue.Queue[tuple[str, dict[str, Any], str | None]] = queue.Queue(QUEUE_MAX)
        self._pending: set[str] = set()
        self._pending_writers: collections.Counter[str] = collections.Counter()
        self._rate: dict[str, collections.deque[float]] = {}
        self._tree: procs.ProcessTree | None = None
        self._watch_thread: threading.Thread | None = None
        self._deliver_thread: threading.Thread | None = None
        saved = _saved_state(self.aew_root)
        self.control_rev: int | None = saved.get("control_rev") if isinstance(saved.get("control_rev"), int) else None
        cursors, dropped = _dict(saved.get("cursors")), _dict(saved.get("dropped"))
        self.cursors: dict[str, dict[str, Any]] = {
            str(w): {"offset": max(0, c["offset"]), "head": c.get("head") if isinstance(c.get("head"), str) else None,
                     "skip": c.get("skip") is True}
            for w, c in cursors.items()
            if isinstance(c, dict) and event_spool.WRITER_RE.match(str(w)) and isinstance(c.get("offset"), int)}
        self._cursor_snapshot: dict[str, dict[str, Any]] = json.loads(json.dumps(self.cursors))
        self.stats: dict[str, Any] = {
            "delivered": _count(saved.get("delivered")), "failed": _count(saved.get("failed")),
            "consecutive_failures": _count(saved.get("consecutive_failures")),
            "last_failure": _dict(saved.get("last_failure")) or None,
            "last_delivery_at": saved.get("last_delivery_at"),
            "dropped": {str(k)[:32]: _count(v) for k, v in dropped.items()}}

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._deliver_thread = threading.Thread(target=self._deliver_loop, name="aew-notify-delivery", daemon=True)
        self._watch_thread = threading.Thread(target=self._watch_loop, name="aew-notify-watch", daemon=True)
        self._deliver_thread.start()
        self._watch_thread.start()

    def close(self, timeout: float = 5.0) -> None:
        """Stop watching; a delivery in flight is killed (its tree with it). Bounded: closing never waits on a
        notifier."""
        self._closed.set()
        tree = self._tree
        if tree is not None:
            tree.kill()
        for t in (self._watch_thread, self._deliver_thread):
            if t is not None and t.is_alive() and t is not threading.current_thread():
                t.join(timeout)
        self._save()

    def drain(self, timeout: float = 30.0) -> bool:
        """For tests: wait until every queued event is delivered or recorded."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._queue.all_tasks_done:
                if not self._queue.unfinished_tasks:
                    return True
            time.sleep(0.02)
        return False

    def _watch_loop(self) -> None:
        from aew.engine import outbox
        from aew.harness import lead_broker

        seen = [self.engine.store.control_identity()]

        def changed() -> bool:  # a commit, or closing, ends the wait early
            return self._closed.is_set() or self.engine.store.control_identity() != seen[0]

        while not self._closed.is_set():
            try:
                self.pass_once()
            except Exception:  # noqa: BLE001  a pass that fails is logged; the next one tries again
                log.exception("the notifier's watcher pass failed")
            seen[0] = self.engine.store.control_identity()
            outbox.wait_for(changed, self.aew_root, timeout=lead_broker.POLL_S)

    # ------------------------------------------------------------------ one pass

    def pass_once(self) -> None:
        """Derive this pass's events and queue the ones no delivery-log line holds. Reads only."""
        with self._pass_mu:
            self._pass()

    def _pass(self) -> None:
        state = self.engine.store.read_committed()
        events: list[tuple[str, dict[str, Any], str | None]] = []
        events += self._generation_events(state)
        events += self._level_events(state)
        events += self._liveness_events(state)
        events += self._spool_events(state)
        for key, body, writer in events:
            self._offer(key, body, writer)
        self._retire_spool()
        with self._mu:
            self._cursor_snapshot = json.loads(json.dumps(self.cursors))
        self._save()

    def _payload(self, state: dict[str, Any], event: str, *, subject: Any, reason: Any, ref: Any, source: str,
                 authenticated: bool, revision: int | None = None) -> dict[str, Any]:
        def text(value: Any) -> str | None:
            return None if value is None else str(value)

        return payload(event=event, project_id=str(self.engine.project_id), subject=text(subject),
                       reason=text(reason), ref=text(ref),
                       revision=int(state["revision"]) if revision is None else revision, source=source,
                       authenticated=authenticated)

    def _generation_events(self, state: dict[str, Any]) -> list[tuple[str, dict[str, Any], str | None]]:
        """``generation_ended`` by takeover, handoff or release, from the transition log after the cursor. The
        first pass the endpoint ever makes starts the cursor at the current revision."""
        from aew.engine import outbox

        rev = int(state["revision"])
        if self.control_rev is None or rev < self.control_rev:
            self.control_rev = rev
            return []
        since, out = self.control_rev, []
        if rev - since > MAX_CATCHUP:
            self._dropped("catchup", rev - since - MAX_CATCHUP)
            since = rev - MAX_CATCHUP
        try:
            for record in outbox.read_transitions(self.aew_root, since, rev, outbox=state.get("outbox")):
                reason = GENERATION_OPS.get(record.get("op") or "")
                if reason is None:
                    continue
                ended = next((e.get("from") for e in record.get("events") or [] if e.get("kind") == "lead.generation"),
                             None)
                if ended is None:  # a release keeps the generation number: the releasing Lead's
                    ended = (record.get("actor") or {}).get("generation", state["lead"]["generation"])
                key = f"generation_ended:{ended}:{reason}:{record['revision']}"
                out.append((key, self._payload(state, "generation_ended", subject=f"lead generation {ended}",
                                               reason=reason, ref=record.get("op"), source="control_state",
                                               authenticated=True, revision=int(record["revision"])), None))
        except Exception as exc:  # noqa: BLE001  a log the watcher cannot read: counted, never fatal
            log.warning("the notifier could not read transitions %s..%s: %s", since, rev, exc)
            self._dropped("unreadable_transitions")
        self.control_rev = rev
        return out

    def _level_events(self, state: dict[str, Any]) -> list[tuple[str, dict[str, Any], str | None]]:
        """Open conditions in control state, each an occurrence by its own record: the Lead's requests (the current
        generation's; they grant nothing), the validation breaker's opening, a lease's reconcile mark."""
        out: list[tuple[str, dict[str, Any], str | None]] = []
        generation = int(state["lead"]["generation"])
        for r in (state.get("steering") or {}).get("requests") or []:
            if r.get("generation") != generation:
                continue
            event = "raise_requested" if r.get("kind") == "raise" else "confirmation_requested"
            out.append((f"{event}:{r['id']}", self._payload(
                state, event, subject=r["id"], reason=r.get("rationale"),
                ref=r.get("mode") if r.get("kind") == "raise" else r.get("action_ref"), source="control_state",
                authenticated=True), None))
        queue_state = state.get("queue") or {}
        opened = (queue_state.get("validation_breaker") or {}).get("open")
        if opened:
            out.append((f"breaker_tripped:validation:{opened.get('at')}", self._payload(
                state, "breaker_tripped", subject="validation_breaker",
                reason="infrastructure failures: " + ", ".join(map(str, opened.get("codes") or [])),
                ref=", ".join(map(str, opened.get("runs") or [])), source="control_state", authenticated=True), None))
        lease = queue_state.get("lease") or {}
        mark = lease.get("reconcile")
        if mark:
            out.append((f"custodian_lost:reconcile:{lease.get('entry')}:{lease.get('custodian')}:{mark.get('at')}",
                        self._payload(state, "custodian_lost", subject=lease.get("custodian"),
                                      reason=mark.get("reason"), ref=lease.get("entry"), source="control_state",
                                      authenticated=True), None))
        return out

    def _liveness_events(self, state: dict[str, Any]) -> list[tuple[str, dict[str, Any], str | None]]:
        from aew.engine.steering import effective
        from aew.harness import lead_broker

        generation = int(state["lead"]["generation"])
        verdict = broker_liveness.judge(broker_liveness.read(self.aew_root), generation=generation,
                                        poll_s=lead_broker.POLL_S)
        if verdict is None:
            return []
        out: list[tuple[str, dict[str, Any], str | None]] = []
        subject = f"lead generation {generation}"
        if verdict.reason != "closed":  # a closed record is a clean end, not a generation ending
            out.append((f"generation_ended:{generation}:{verdict.reason}:{verdict.occurrence}", self._payload(
                state, "generation_ended", subject=subject, reason=verdict.reason, ref=broker_liveness.REL,
                source="liveness", authenticated=False), None))
        if effective(state)["mode"] == "run":  # plan v3 §2.8: while Run is effective, whatever the cause
            out.append((f"broker_gone:{generation}:{verdict.reason}:{verdict.occurrence}", self._payload(
                state, "broker_gone", subject=subject, reason=verdict.reason, ref=broker_liveness.REL,
                source="liveness", authenticated=False), None))
        return out

    def _spool_events(self, state: dict[str, Any]) -> list[tuple[str, dict[str, Any], str | None]]:
        reader = event_spool.Reader(self.aew_root, self.cursors)
        found = reader.scan()
        for why, n in found.dropped.items():
            self._dropped(why, n)
        return [(f"{line.event}:{line.key}", self._payload(
            state, line.event, subject=line.subject, reason=line.reason, ref=line.ref,
            source=f"spool:{line.writer}", authenticated=False), line.writer) for line in found.lines]

    def _retire_spool(self) -> None:
        """Delete a run's spool file once the run is terminal and every line in it is delivered or dropped."""
        reader = event_spool.Reader(self.aew_root, self.cursors)
        for writer in reader.writers():
            if not writer.startswith(event_spool.RUN_PREFIX) or reader.unread(writer):
                continue
            with self._mu:
                if self._pending_writers[writer]:
                    continue
            directory = runlog.run_dir(self.aew_root, writer[len(event_spool.RUN_PREFIX):])
            status, _ = runlog.observed_status(directory)
            if status in K.TERMINAL or not directory.exists():
                reader.retire(writer)

    # ------------------------------------------------------------------ queueing and delivery

    def _offer(self, key: str, body: dict[str, Any], writer: str | None) -> None:
        with self._mu:
            if key in self._pending or self.log.seen(key):
                return
        if writer is not None and not self._within_rate(writer):
            self._record(key, body, {"outcome": "dropped", "reason": "rate"})
            self._dropped("rate")
            return
        with self._mu:
            try:
                self._queue.put_nowait((key, body, writer))
            except queue.Full:
                full = True
            else:
                full = False
                self._pending.add(key)
                if writer is not None:
                    self._pending_writers[writer] += 1
        if full:
            self._record(key, body, {"outcome": "dropped", "reason": "queue_full"})
            self._dropped("queue_full")

    def _within_rate(self, writer: str) -> bool:
        now = time.monotonic()
        window = self._rate.setdefault(writer, collections.deque())
        while window and now - window[0] >= 60.0:
            window.popleft()
        if len(window) >= RATE_PER_MINUTE:
            return False
        window.append(now)
        return True

    def _deliver_loop(self) -> None:
        while not self._closed.is_set():
            try:
                key, body, writer = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if not self._closed.is_set():
                    self._deliver_one(key, body)
            except Exception:  # noqa: BLE001  one delivery's defect never stops the next
                log.exception("the notifier failed to deliver %s", key)
            finally:
                with self._mu:
                    self._pending.discard(key)
                    if writer is not None:
                        self._pending_writers[writer] -= 1
                self._queue.task_done()

    def _deliver_one(self, key: str, body: dict[str, Any]) -> None:
        from aew.engine.steering import notifier_problem

        try:
            policy, _ = self.engine.execution_policy()
        except Exception as exc:  # noqa: BLE001  a drifted or unreadable policy is a failed delivery, never a crash
            outcome: dict[str, Any] = {"outcome": "failed", "reason": "policy_unreadable",
                                       "detail": event_spool.clean(f"{type(exc).__name__}: {exc}")}
        else:
            config = (policy or {}).get("notify") or {}
            problem = notifier_problem(policy)
            if problem:
                outcome = {"outcome": "failed", "reason": "not_configured" if not config.get("command")
                           else "not_executable", "detail": problem}
            else:
                self._tree = procs.ProcessTree()
                try:
                    outcome = deliver(list(config["command"]), body,
                                      timeout_s=float(config.get("timeout_s") or DEFAULT_TIMEOUT_S),
                                      max_output_bytes=int(config.get("max_output_bytes") or DEFAULT_MAX_OUTPUT_BYTES),
                                      cwd=str(self.engine.repo_root), tree=self._tree)
                finally:
                    self._tree = None
        self._record(key, body, outcome)

    def _record(self, key: str, body: dict[str, Any], outcome: dict[str, Any]) -> None:
        entry = {"key": key, "event": body["event"], "source": body["source"], "at": utc_now(), **outcome}
        self.log.record(entry)
        with self._mu:
            if outcome["outcome"] == "delivered":
                self.stats["delivered"] += 1
                self.stats["consecutive_failures"] = 0
                self.stats["last_delivery_at"] = entry["at"]
            elif outcome["outcome"] == "failed":
                self.stats["failed"] += 1
                self.stats["consecutive_failures"] += 1
                self.stats["last_failure"] = {"key": key[:200], "event": body["event"], "at": entry["at"],
                                              "reason": outcome.get("reason"), "detail": outcome.get("detail")}
        self._save()

    def _dropped(self, why: str, n: int = 1) -> None:
        with self._mu:
            self.stats["dropped"][why] = self.stats["dropped"].get(why, 0) + n

    def _save(self) -> None:
        """Write ``state.json``: the cursors as the last pass left them, and the counts. Both threads save; one
        lock serializes the writes, and the cursors are the watch thread's snapshot, never its working copy."""
        with self._save_mu:
            with self._mu:
                text = json.dumps({"schema": STATE_SCHEMA, "updated_at": utc_now(), "control_rev": self.control_rev,
                                   "cursors": self._cursor_snapshot, **self.stats}, sort_keys=True, default=str)
            self._write_state(text + "\n")

    def _write_state(self, text: str) -> None:
        path = notify_dir(self.aew_root) / STATE
        tmp = path.with_name(f".state.{os.getpid()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            replace_with_retry(tmp, path)
        except OSError as exc:
            log.warning("the notifier's state %s could not be written: %s", path, exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def _dict(value: Any) -> dict[Any, Any]:
    return value if isinstance(value, dict) else {}


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _saved_state(aew_root: Path) -> dict[str, Any]:
    path = notify_dir(aew_root) / STATE
    try:
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > STATE_MAX_BYTES:
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) and data.get("schema") == STATE_SCHEMA else {}
