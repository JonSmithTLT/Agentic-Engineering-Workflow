"""The operator notifier: the endpoint's watcher and its delivery (M4-E plan v3 §2.8 and E7, operator decision 1;
amendment 1, E7a).

**Who delivers.** ``aew operator serve`` (:class:`Watcher`, started and stopped with the endpoint): it is
attachment-independent and supervisor-side, so what matters most while no Lead or broker is alive still reaches the
operator (N3). Nothing here grants, moves or commits anything: a notification is attention, never authority.

**What it watches,** in one pass every ``POLL_S`` and at each commit (``outbox.wait_for`` on the wake file):

- control state, read with the store's lock-free reader (``read_committed``; the watcher commits nothing): the Lead
  generation ending by ``takeover``, ``handoff`` or ``release`` (from the transition log after the watcher's cursor),
  the Lead's open requests (``raise_requested``, ``confirmation_requested``), the validation circuit breaker and the
  relaunch breaker opening (``breaker_tripped``, its ``subject`` naming the breaker; M4-E E8b), an open high anomaly
  (``anomaly_high``, M4-E E7b) and a lease marked for reconciliation (``custodian_lost``);
- the broker's liveness record (``harness.broker_liveness``): ``generation_ended`` with ``crash`` or ``stale``, judged
  only for the current generation, and ``broker_gone`` while Run is effective, whatever the cause (``crash``,
  ``stale``, or ``closed`` for a clean end with the seat still held; R3-m1);
- the event spool (``harness.event_spool``): ``hard_deadline`` and ``launch_failed`` (with its closed ``reason_code``,
  M4-E E8b) from each run's supervisor, untrusted, at most :data:`RATE_PER_MINUTE` deliveries per writer per minute.

**Once per occurrence.** Each event has a key naming its occurrence; the delivery log
(``.aew/local/notify/deliveries.jsonl``) records it once, delivered, failed or dropped, and a key it holds is never
delivered again, across passes and endpoint restarts. An event leaves the watcher's outstanding set only once that
log records it, so stopping the endpoint loses nothing.

**Delivery** (decision 1) on one thread serving two lanes (control state and liveness first; :class:`Watcher`),
never holding the endpoint's ``_authorizing`` or ``_engine_lock`` (a slow notifier never delays a challenge),
through an engine of its own: the adopted execution
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
SPOOL_QUEUE_MAX = 64  # spool events waiting for the delivery thread; past it a spool event is dropped and counted
RATE_PER_MINUTE = 10  # deliveries per spool writer, and of liveness events, per minute (amendment 1, m9)
SPOOL_PER_MINUTE = 30  # spool deliveries per minute across every writer: many writers cannot flood together
SPOOL_ALL = "*spool"  # the rate window shared by every spool writer
LIVENESS = "*liveness"  # the rate window of the (forgeable) liveness record's events
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
    """What ``status`` and the dashboard show: deliveries and failures, the last failure, what was dropped, and a
    watcher source that keeps failing. ``attention`` is true while the latest delivery failed or the latest pass had a
    failing source (a later success clears it; the counts stay). ``None``
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
    out["consecutive_pass_failures"] = count(data.get("consecutive_pass_failures"))
    pass_error = _dict(data.get("last_pass_error"))
    if out["consecutive_pass_failures"] and pass_error:
        listed = pass_error.get("sources")
        sources: list[Any] = listed if isinstance(listed, list) else []
        out["pass_error"] = {"sources": [event_spool.clean(x, 32) for x in sources[:8]],
                             "error": event_spool.clean(pass_error.get("error")),
                             "at": event_spool.clean(pass_error.get("at"), 40)}
    out["attention"] = out["consecutive_failures"] > 0 or out["consecutive_pass_failures"] > 0
    return out


# ---------------------------------------------------------------------------------------------- the watcher


class Watcher:
    """The endpoint's watcher (the endpoint starts and stops it). It reads, derives and delivers; it never commits.
    It runs on its own engine for the project, so it shares no object with the endpoint's operations.

    **Sources are isolated.** Each pass derives and offers its sources one at a time (the transition log, the open
    control-state conditions, the liveness record, the spool), each in its own ``try``: a source that fails is
    counted and shown in ``status`` (``last_pass_error``), and never stops the others.

    **Two lanes.** Control-state and liveness events go to the urgent lane, which the delivery thread always serves
    first, and are never recorded with a non-final outcome: they are bounded by the state they come from (the
    transition catch-up bound, the open conditions; liveness is rate-bounded). Spool events, untrusted, go to a
    bounded lane, rate-bounded per writer and across writers; past those bounds a line is dropped, recorded and
    counted.

    **Nothing is lost at a restart.** An event leaves the outstanding set only once the delivery log records it. The
    persisted transition cursor never passes an unrecorded transition event (a restart derives it again from the
    hash-chained log); the lines of outstanding spool events are persisted, then parsed and checked again exactly as
    fresh lines; liveness and the open conditions are derived again while they hold. A delivery that ``close()``
    kills is not recorded, so it is not a failure: it stays outstanding."""

    def __init__(self, repo_root: Path, aew_root: Path) -> None:
        from aew.engine.api import Engine

        self.engine = Engine(Path(repo_root), Path(aew_root))
        self.aew_root = Path(aew_root)
        self.log = DeliveryLog(self.aew_root)
        self._mu = threading.Lock()  # the counts, the lanes, the outstanding set and the cursor snapshot
        self._cv = threading.Condition(self._mu)
        self._save_mu = threading.Lock()  # one state.json write at a time
        self._pass_mu = threading.Lock()  # one pass at a time: a pass owns the cursors
        self._closed = threading.Event()
        self._urgent: collections.deque[str] = collections.deque()
        self._spool: collections.deque[str] = collections.deque()
        self._outstanding: dict[str, dict[str, Any]] = {}  # offered, not yet recorded: {body, writer, lane, rev}
        self._busy = 0
        self._rate: dict[str, collections.deque[float]] = {}
        self._tree: procs.ProcessTree | None = None
        self._watch_thread: threading.Thread | None = None
        self._deliver_thread: threading.Thread | None = None
        saved = _saved_state(self.aew_root)
        rev = saved.get("control_rev")
        self.control_rev: int | None = rev if isinstance(rev, int) and not isinstance(rev, bool) else None
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
            "consecutive_pass_failures": _count(saved.get("consecutive_pass_failures")),
            "last_pass_error": _dict(saved.get("last_pass_error")) or None,
            "dropped": {str(k)[:32]: _count(v) for k, v in dropped.items()}}
        self._reoffer = _saved_spool_lines(saved.get("outstanding"))

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._deliver_thread = threading.Thread(target=self._deliver_loop, name="aew-notify-delivery", daemon=True)
        self._watch_thread = threading.Thread(target=self._watch_loop, name="aew-notify-watch", daemon=True)
        self._deliver_thread.start()
        self._watch_thread.start()

    def close(self, timeout: float = 5.0) -> None:
        """Stop watching; a delivery in flight is killed (its tree with it) and stays outstanding, unrecorded.
        Bounded: closing never waits on a notifier."""
        self._closed.set()
        with self._cv:
            self._cv.notify_all()
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
        with self._cv:
            while self._urgent or self._spool or self._busy:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self._cv.wait(min(left, 0.1))
        return True

    def _watch_loop(self) -> None:
        from aew.engine import outbox
        from aew.harness import lead_broker

        seen = [self.engine.store.control_identity()]

        def changed() -> bool:  # a commit, or closing, ends the wait early
            return self._closed.is_set() or self.engine.store.control_identity() != seen[0]

        while not self._closed.is_set():
            try:
                self.pass_once()
            except Exception:  # noqa: BLE001  a pass's own defect is logged; each source is isolated within it
                log.exception("the notifier's watcher pass failed")
            seen[0] = self.engine.store.control_identity()
            outbox.wait_for(changed, self.aew_root, timeout=lead_broker.POLL_S)

    # ------------------------------------------------------------------ one pass

    def pass_once(self) -> None:
        """Derive this pass's events and queue the ones no delivery-log line holds. Reads only."""
        with self._pass_mu:
            self._pass()

    def _pass(self) -> None:
        failed: list[str] = []
        error = ""
        try:
            state: dict[str, Any] | None = self.engine.store.read_committed()
        except Exception as exc:  # noqa: BLE001  the control file unreadable now: the spool still delivers
            state, error = None, f"control_state: {type(exc).__name__}: {exc}"
            failed.append("control_state")
        reoffer, self._reoffer = self._reoffer, []
        for writer, raw in reoffer:  # spool lines outstanding at the last save: never lost at a restart, and
            line = event_spool.parse_line(writer, raw.encode("utf-8"))  # checked exactly as a fresh line is
            if line is None:
                self._dropped("invalid")
            else:
                self._offer_spool_line(state, line)
        sources = [("spool", self._spool_source)]
        if state is not None:
            sources = [("transitions", self._transition_source), ("conditions", self._condition_source),
                       ("liveness", self._liveness_source), *sources]
        for name, source in sources:
            try:
                source(state)
            except Exception as exc:  # noqa: BLE001  one source never stops another (counted, shown in status)
                log.warning("the notifier's %s source failed: %s: %s", name, type(exc).__name__, exc)
                failed.append(name)
                error = error or f"{name}: {type(exc).__name__}: {exc}"
                self._dropped(f"{name}_failed")
        try:
            self._retire_spool()
        except Exception as exc:  # noqa: BLE001
            log.warning("the notifier could not retire spool files: %s", exc)
        with self._mu:
            self._cursor_snapshot = json.loads(json.dumps(self.cursors))
            if failed:
                self.stats["consecutive_pass_failures"] += 1
                self.stats["last_pass_error"] = {"sources": failed, "error": event_spool.clean(error),
                                                 "at": utc_now()}
            else:
                self.stats["consecutive_pass_failures"] = 0
        self._save()

    def _payload(self, state: dict[str, Any] | None, event: str, *, subject: Any, reason: Any, ref: Any,
                 source: str, authenticated: bool, revision: int | None = None,
                 reason_code: str | None = None) -> dict[str, Any]:
        def text(value: Any) -> str | None:
            return None if value is None else str(value)

        if revision is None and state is not None:
            revision = int(state["revision"])
        return payload(event=event, project_id=str(self.engine.project_id), subject=text(subject),
                       reason=text(reason), ref=text(ref), revision=revision, source=source,
                       authenticated=authenticated, reason_code=reason_code)

    def _transition_source(self, state: dict[str, Any] | None) -> None:
        """``generation_ended`` by takeover, handoff or release, from the transition log after the cursor. The
        first pass the endpoint ever makes starts the cursor at the current revision. The cursor moves only once
        the transitions read are offered; a log that cannot be read leaves it where it was."""
        from aew.engine import outbox

        assert state is not None
        rev = int(state["revision"])
        if self.control_rev is None or rev < self.control_rev:
            self.control_rev = rev
            return
        since = self.control_rev
        if rev - since > MAX_CATCHUP:
            self._dropped("catchup", rev - since - MAX_CATCHUP)
            since = rev - MAX_CATCHUP
        found = []
        for record in outbox.read_transitions(self.aew_root, since, rev, outbox=state.get("outbox")):
            reason = GENERATION_OPS.get(record.get("op") or "")
            if reason is None:
                continue
            ended = next((e.get("from") for e in record.get("events") or [] if e.get("kind") == "lead.generation"),
                         None)
            if ended is None:  # a release keeps the generation number: the releasing Lead's
                ended = (record.get("actor") or {}).get("generation", state["lead"]["generation"])
            revision = int(record["revision"])
            found.append((f"generation_ended:{ended}:{reason}:{revision}", self._payload(
                state, "generation_ended", subject=f"lead generation {ended}", reason=reason, ref=record.get("op"),
                source="control_state", authenticated=True, revision=revision), revision))
        for key, body, revision in found:
            self._offer(key, body, lane="urgent", rev=revision)
        self.control_rev = rev

    def _condition_source(self, state: dict[str, Any] | None) -> None:
        """Open conditions in control state, each an occurrence by its own record: the Lead's requests (the current
        generation's; they grant nothing), the validation breaker's opening, a high anomaly (M4-E E7b, from E5b's
        `anomalies`), a lease's reconcile mark."""
        assert state is not None
        generation = int(state["lead"]["generation"])
        for r in (state.get("steering") or {}).get("requests") or []:
            if r.get("generation") != generation:
                continue
            event = "raise_requested" if r.get("kind") == "raise" else "confirmation_requested"
            self._offer(f"{event}:{r['id']}", self._payload(
                state, event, subject=r["id"], reason=r.get("rationale"),
                ref=r.get("mode") if r.get("kind") == "raise" else r.get("action_ref"), source="control_state",
                authenticated=True), lane="urgent")
        queue_state = state.get("queue") or {}
        opened = (queue_state.get("validation_breaker") or {}).get("open")
        if opened:
            self._offer(f"breaker_tripped:validation:{opened.get('at')}", self._payload(
                state, "breaker_tripped", subject="validation_breaker",
                reason="infrastructure failures: " + ", ".join(map(str, opened.get("codes") or [])),
                ref=", ".join(map(str, opened.get("runs") or [])), source="control_state", authenticated=True),
                lane="urgent")
        # The relaunch breaker (M4-E E8b; amendment 1, nit 4): the same event, with `subject` naming the breaker and
        # `ref` its scope; one occurrence per opening.
        for scope, breaker in sorted(((state.get("recovery") or {}).get("breakers") or {}).items()):
            tripped = (breaker or {}).get("open")
            if tripped:
                codes = list(map(str, tripped.get("reason_codes") or []))
                self._offer(f"breaker_tripped:relaunch:{scope}:{tripped.get('at')}", self._payload(
                    state, "breaker_tripped", subject="relaunch_breaker",
                    reason=f"eligible launch failures in {scope}: " + ", ".join(codes), ref=scope,
                    source="control_state", authenticated=True, reason_code=codes[-1] if codes else None),
                    lane="urgent")
        for an, anomaly in sorted((state.get("anomalies") or {}).items()):  # M4-E E7b: a high anomaly is opened
            if anomaly.get("severity") == "high":
                self._offer(f"anomaly_high:{an}", self._payload(
                    state, "anomaly_high", subject=anomaly.get("subject") or "project", reason=anomaly.get("detail"),
                    ref=an, source="control_state", authenticated=True), lane="urgent")
        lease = queue_state.get("lease") or {}
        mark = lease.get("reconcile")
        if mark:
            self._offer(f"custodian_lost:reconcile:{lease.get('entry')}:{lease.get('custodian')}:{mark.get('at')}",
                        self._payload(state, "custodian_lost", subject=lease.get("custodian"),
                                      reason=mark.get("reason"), ref=lease.get("entry"), source="control_state",
                                      authenticated=True), lane="urgent")

    def _liveness_source(self, state: dict[str, Any] | None) -> None:
        from aew.engine.steering import effective
        from aew.harness import lead_broker

        assert state is not None
        generation = int(state["lead"]["generation"])
        verdict = broker_liveness.judge(broker_liveness.read(self.aew_root), generation=generation,
                                        poll_s=lead_broker.POLL_S)
        if verdict is None:
            return
        subject = f"lead generation {generation}"
        if verdict.reason != "closed":  # a closed record is a clean end, not a generation ending
            self._offer(f"generation_ended:{generation}:{verdict.reason}:{verdict.occurrence}", self._payload(
                state, "generation_ended", subject=subject, reason=verdict.reason, ref=broker_liveness.REL,
                source="liveness", authenticated=False), writer=LIVENESS, lane="urgent")
        if effective(state)["mode"] == "run":  # plan v3 §2.8: while Run is effective, whatever the cause
            self._offer(f"broker_gone:{generation}:{verdict.reason}:{verdict.occurrence}", self._payload(
                state, "broker_gone", subject=subject, reason=verdict.reason, ref=broker_liveness.REL,
                source="liveness", authenticated=False), writer=LIVENESS, lane="urgent")

    def _spool_source(self, state: dict[str, Any] | None) -> None:
        reader = event_spool.Reader(self.aew_root, self.cursors)
        found = reader.scan()
        for why, n in found.dropped.items():
            self._dropped(why, n)
        for line in found.lines:
            self._offer_spool_line(state, line)

    def _offer_spool_line(self, state: dict[str, Any] | None, line: event_spool.Line) -> None:
        """Offer one validated spool line (fresh, or saved and parsed again): a run's line only while the run's
        directory exists, always unauthenticated, its payload built from the line."""
        if line.writer.startswith(event_spool.RUN_PREFIX):
            if not runlog.run_dir(self.aew_root, line.writer[len(event_spool.RUN_PREFIX):]).is_dir():
                self._dropped("unknown_run")  # a supervisor writes only for a run whose directory its launcher made
                return
        self._offer(f"{line.event}:{line.key}", self._payload(
            state, line.event, subject=line.subject, reason=line.reason, ref=line.ref,
            source=f"spool:{line.writer}", authenticated=False, reason_code=line.reason_code), writer=line.writer,
            lane="spool", line=line.raw)

    def _retire_spool(self) -> None:
        """Delete a run's spool file once the run is terminal and every line in it is delivered or dropped. The
        status is read first: a supervisor appends before it writes its terminal record, so once the run reads
        terminal, a file with nothing unread after that is final."""
        reader = event_spool.Reader(self.aew_root, self.cursors)
        for writer in reader.writers():
            if not writer.startswith(event_spool.RUN_PREFIX):
                continue
            directory = runlog.run_dir(self.aew_root, writer[len(event_spool.RUN_PREFIX):])
            status, _ = runlog.observed_status(directory)
            if (status not in K.TERMINAL and directory.exists()) or reader.unread(writer):
                continue
            with self._mu:
                if any(o["writer"] == writer for o in self._outstanding.values()):
                    continue
            reader.retire(writer)

    # ------------------------------------------------------------------ queueing and delivery

    def _offer(self, key: str, body: dict[str, Any], *, lane: str, writer: str | None = None,
               rev: int | None = None, line: str | None = None) -> None:
        with self._mu:
            if key in self._outstanding or self.log.seen(key):
                return
        if writer is not None and not self._within_rate(writer, RATE_PER_MINUTE):
            self._record(key, body, {"outcome": "dropped", "reason": "rate"})
            self._dropped("rate")
            return
        if lane == "spool" and not self._within_rate(SPOOL_ALL, SPOOL_PER_MINUTE):
            self._record(key, body, {"outcome": "dropped", "reason": "spool_rate"})
            self._dropped("spool_rate")
            return
        with self._cv:
            if lane == "spool" and len(self._spool) >= SPOOL_QUEUE_MAX:
                full = True
            else:
                full = False
                self._outstanding[key] = {"body": body, "writer": writer, "lane": lane, "rev": rev, "line": line}
                (self._urgent if lane == "urgent" else self._spool).append(key)
                self._cv.notify_all()
        if full:  # only an untrusted spool event is ever dropped for room, and then for good, recorded and counted
            self._record(key, body, {"outcome": "dropped", "reason": "queue_full"})
            self._dropped("queue_full")

    def _within_rate(self, writer: str, limit: int) -> bool:
        now = time.monotonic()
        window = self._rate.setdefault(writer, collections.deque())
        while window and now - window[0] >= 60.0:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    def _next(self) -> str | None:
        with self._cv:
            while not self._closed.is_set() and not self._urgent and not self._spool:
                self._cv.wait(0.2)
            if self._closed.is_set():
                return None
            self._busy += 1
            return (self._urgent or self._spool).popleft()  # control state and liveness first

    def _deliver_loop(self) -> None:
        while not self._closed.is_set():
            key = self._next()
            if key is None:
                return
            try:
                with self._mu:
                    item = self._outstanding.get(key)
                if item is not None:
                    self._deliver_one(key, item["body"])
            except Exception:  # noqa: BLE001  one delivery's defect never stops the next
                log.exception("the notifier failed to deliver %s", key)
            finally:
                with self._cv:
                    self._busy -= 1
                    self._cv.notify_all()

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
        if self._closed.is_set():
            return  # killed by close(), or finished as it closed: not a failure; it stays outstanding
        self._record(key, body, outcome)

    def _record(self, key: str, body: dict[str, Any], outcome: dict[str, Any]) -> None:
        entry = {"key": key, "event": body["event"], "source": body["source"], "at": utc_now(), **outcome}
        self.log.record(entry)
        with self._mu:
            self._outstanding.pop(key, None)
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
        """Write ``state.json``: the cursors as the last pass left them, the counts, and what is outstanding. The
        transition cursor saved never passes an unrecorded transition event; outstanding spool events are saved to
        be offered again. Both threads save; one lock serializes the writes."""
        with self._save_mu:
            with self._mu:
                held = [o["rev"] for o in self._outstanding.values() if o["rev"] is not None]
                control_rev = min(held) - 1 if held else self.control_rev
                spool = [{"writer": o["writer"], "line": o["line"]}  # the line itself, parsed again when offered
                         for o in self._outstanding.values() if o["lane"] == "spool" and o["line"] is not None]
                text = json.dumps({"schema": STATE_SCHEMA, "updated_at": utc_now(), "control_rev": control_rev,
                                   "cursors": self._cursor_snapshot, "outstanding": spool, **self.stats},
                                  sort_keys=True, default=str)
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


def _saved_spool_lines(value: Any) -> list[tuple[str, str]]:
    """The spool lines whose events were outstanding at the last save, as ``(writer, line)``. ``state.json`` is a
    local file, so nothing in it is taken as an event: each line is parsed and checked again exactly as a fresh spool
    line is (``event_spool.parse_line``), and its key and payload are rebuilt from it (review of PR #184)."""
    out: list[tuple[str, str]] = []
    for item in (value if isinstance(value, list) else [])[:SPOOL_QUEUE_MAX]:
        if isinstance(item, dict) and isinstance(item.get("writer"), str) and isinstance(item.get("line"), str):
            out.append((item["writer"], item["line"]))
    return out


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
