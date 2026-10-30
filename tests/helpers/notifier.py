"""Helpers for the operator notifier's tests (M4-E E7a): a recording notifier, adopting a policy with a notifier, the
operator's raise as the endpoint commits it, seeding control state, a bounded wait that can say why it timed out, the
wait on a Lead broker's watchdog with what to say, and a Lead broker whose watchdog and beat the test steps on a clock
it moves."""

from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew.engine import steering
from aew.engine.api import Engine
from aew.engine.steering import OperatorPrincipal
from aew.engine.store import ControlStore, Transition
from aew.harness import broker_liveness, lead_broker, procs

IS_WINDOWS = sys.platform == "win32"

RECORDER = """\
import sys
data = sys.stdin.read()
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(data if data.endswith("\\n") else data + "\\n")
"""


def script(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return str(path)


def recorder(tmp_path: Path) -> tuple[list[str], Path]:
    """A notifier that appends each event it receives to ``notified.jsonl``: its argv, and that file."""
    out = tmp_path / "notified.jsonl"
    return [sys.executable, "-I", script(tmp_path, "recorder", RECORDER), str(out)], out


def received(out: Path) -> list[dict[str, Any]]:
    if not out.exists():
        return []
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]


def adopt(project: Any, *, mode: str | None = "crawl", command: list[str] | None = None, **notify_cfg: Any) -> Engine:
    """Adopt an execution policy with a steering mode and a notifier, as the operator would."""
    path = project.root / ".aew" / "policy" / "execution.yaml"
    text = path.read_text(encoding="utf-8").split("\n# --- e7a test ---\n")[0]
    extra = f"steering:\n  mode: {mode}\n" if mode else ""
    if command:
        extra += "notify:\n  command: " + json.dumps(command) + "\n"
        extra += "".join(f"  {k}: {v}\n" for k, v in notify_cfg.items())
    path.write_text(text + "\n# --- e7a test ---\n" + extra, encoding="utf-8")
    project.adopt_policy()
    return Engine.discover(project.root)


def raise_to(engine: Engine, mode: str) -> None:
    """The operator's raise, as the endpoint commits it after its challenge (E2's tests make it the same way)."""
    principal = OperatorPrincipal(uid=os.getuid() if hasattr(os, "getuid") else None, method="peer_credentials",
                                  endpoint_pid=os.getpid(), endpoint_started_at="2026-10-10T00:00:00Z")
    bound = engine.steering_raise_preview(mode)
    engine.steering_raise(principal, mode=mode, generation=bound["generation"],
                          legality_digest=bound["legality_digest"])


def seed(project: Any, mutate: Any) -> None:
    """Put a condition into control state with one plain commit (the engine paths that make these conditions need a
    validation run or a custodian; the watcher only reads the state they leave)."""
    engine = Engine.discover(project.root)
    with engine.store.session() as s:
        mutate(s.state)
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="seeded for the notifier tests"))


def hidden() -> dict[str, Any]:
    """Popen arguments that never open a console window (Windows) and detach the child's session (POSIX)."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"], **hidden())
    proc.wait(30)
    assert not procs.pid_alive(proc.pid)
    return proc.pid


def until(predicate: Any, timeout: float = 30.0, what: str = "the condition", *,
          describe: Callable[[], str] | None = None) -> Any:
    """``predicate``'s first truthy result within ``timeout`` seconds, or AssertionError. On a timeout, ``describe``
    (when given) says what the chain being waited on was doing at that moment, so a rare failure names the link that
    broke; a describer that raises is reported in the message, never in place of the timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    message = f"timed out waiting for {what}"
    if describe is not None:
        try:
            message += f"; at the timeout:\n{describe()}"
        except Exception as exc:  # the timeout is the failure: a broken describer must not hide it  # noqa: BLE001
            message += f"; the describer failed: {type(exc).__name__}: {exc}"
    raise AssertionError(message)


def thread_stack(thread: threading.Thread) -> str:
    """One thread's current stack, as ``autopsy.thread_stacks`` gives every thread's, or why there is none. A thread
    that has ended has none: its identifier may already name a newer thread (review of #276, N3)."""
    frame = sys._current_frames().get(thread.ident) if thread.is_alive() and thread.ident is not None else None
    if frame is None:
        return "(no stack: the thread is not running)"
    return "".join(traceback.format_stack(frame))


def watchdog_wait_s(record: dict[str, Any], poll_s: float) -> float:
    """How long a test waits for a Lead broker's watchdog to act on a commit (main's run at f41b001e, whose literal
    10 s was below this). One watchdog iteration may take the broker's own recorded bound, ``wedge_after_s``
    (``broker_liveness.wedge_threshold_s``: ``store.lock_timeout + 2 x POLL_S``), because its read waits out the
    control lock, and ``judge`` never calls it stale before then. A read that times out is "still the Lead"
    (``LeadBroker._authority_lost``), so the next iteration acts: ``2 x POLL_S`` more covers its start, its read and
    the write that follows. Past this window, the stall has outlasted one timed-out read plus the next iteration's
    start. That is not a stale broker: a timed-out read still ticks, so ``judge`` calls the broker live while each
    iteration stays inside ``wedge_after_s``, and the swallowed ``LockTimeout`` is what hides the supersession (review
    of #276, F1)."""
    return float(record["wedge_after_s"]) + 2 * poll_s


def broker_chain(broker: Any, aew_root: Path) -> Callable[[], str]:
    """A describer (``until(..., describe=)``) for a wait on a Lead broker's watchdog: each link from a commit to the
    broker's liveness record, as it stands at the timeout.

    - ``broker.superseded``: whether the watchdog has seen its authority go.
    - The watchdog thread, alive or ended, and its stack. In ``FileLock._wait``, its read is waiting out the control
      lock, and a ``LockTimeout`` there is swallowed as "still the Lead". In ``Beat.close``, ``_mu`` or
      ``replace_with_retry``, the closing write is slow. Anywhere else, the cause is something new.
    - The record's ``beat_at`` and ``watchdog_tick_at`` ages: the last signs of life of the beat thread and the
      watchdog."""

    def describe() -> str:
        now, record, watch = time.time(), broker_liveness.read(aew_root), broker._watch
        lines = [f"broker.superseded: {broker.superseded!r}",
                 f"the watchdog thread: {'alive' if watch.is_alive() else 'ended'}; its stack:\n{thread_stack(watch)}"]
        if record is None:
            lines.append("the liveness record: none at this moment (absent, or racing its rewrite)")
        else:
            lines.append(f"the liveness record: beat_at {now - record['beat_at']:.2f}s ago, watchdog_tick_at "
                         f"{now - record['watchdog_tick_at']:.2f}s ago, closed_at {record.get('closed_at')!r}, "
                         f"wedge_after_s {record['wedge_after_s']}")
        return "\n".join(lines)

    return describe


def loop_chain(broker: Any) -> Callable[[], str]:
    """A describer for a wait on a Lead broker's steering loop (#281 at 8e71cc4c: its first activation timed out with
    no word on where): what it has run, its last recorded stop, and the loop thread's and the watchdog's stacks, as
    they stand at the timeout. The loop thread in a stage's run is an activation still working (``close()`` then waits
    for it); in ``FileLock._wait``, it waits on the control lock; in the history index, on another connection."""

    def describe() -> str:
        loop = broker.loop
        recorded = loop.aew_root / steering.LOOP_REL
        try:
            stop = json.loads(recorded.read_text(encoding="utf-8")).get("stop")
        except (OSError, ValueError):
            stop = "(no loop.json, or racing its rewrite)"
        thread = loop._thread
        lines = [f"loop.executed: {[x['action'] for x in loop.executed]}", f"loop.json's stop: {stop!r}",
                 "the loop thread: " + ("not started" if thread is None else
                                        f"{'alive' if thread.is_alive() else 'ended'}; its stack:\n"
                                        f"{thread_stack(thread)}"),
                 f"the watchdog thread's stack:\n{thread_stack(broker._watch)}"]
        return "\n".join(lines)

    return describe


LOOK_S = 0.05  # how often a wait for a stepped thread looks whether the thread has ended, which notifies nothing


def step_guard_s() -> float:
    """How long a test waits for one stepped iteration to come back: a hang guard, never a timing assertion. It is one
    watchdog iteration's own bound (``broker_liveness.wedge_threshold_s``) at the control store's default lock timeout,
    the longest wait an iteration makes in production, whatever lock timeout a test injects; a stepped iteration starts
    when the test releases it, so no stop wait comes first."""
    default = inspect.signature(ControlStore).parameters["lock_timeout"].default
    return broker_liveness.wedge_threshold_s(default, lead_broker.POLL_S)


class Clock:
    """A wall clock the test moves (``LeadBroker(clock=)``). It starts at the real time, so the record's stamps are
    ones ``broker_liveness.read`` takes, and moves only when the test advances it."""

    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


class Steps(threading.Event):
    """The event a Lead broker's watchdog or beat thread waits on between iterations (``LeadBroker(idle=Steps)``),
    stepped by the test: each ``wait`` returns once the test releases one iteration, or once the event is set (the loop
    is to stop), never because time passed. An iteration is done when its loop is back in ``wait``, or its thread has
    ended (a superseded watchdog returns)."""

    def __init__(self) -> None:
        super().__init__()
        self._cv = threading.Condition()
        self._released = 0  # iterations released and not yet begun
        self._granted = 0  # iterations released in all: the n-th is done once ``_done`` reaches n
        self._done = 0
        self._running = False

    def wait(self, timeout: float | None = None) -> bool:
        """The loop's side. ``timeout`` (its POLL_S) is not waited out: the test steps the loop."""
        with self._cv:
            if self._running:
                self._running, self._done = False, self._done + 1
                self._cv.notify_all()
            self._cv.wait_for(lambda: self._released > 0 or self.is_set())
            if self.is_set():
                return True
            self._released -= 1
            self._running = True
            return False

    def set(self) -> None:
        super().set()
        with self._cv:
            self._cv.notify_all()

    def release(self) -> int:
        """Let the loop begin one iteration, and return its number, for :meth:`finish`."""
        with self._cv:
            self._released += 1
            self._granted += 1
            self._cv.notify_all()
            return self._granted

    def finish(self, n: int, thread: threading.Thread) -> None:
        """Wait until iteration ``n`` is done, within ``step_guard_s()``; past it, fail with the thread's stack."""
        guard = step_guard_s()
        deadline = time.monotonic() + guard
        with self._cv:
            while self._done < n and thread.is_alive():
                if time.monotonic() > deadline:
                    raise AssertionError(f"iteration {n} of {thread.name} did not come back within {guard} s (a hang "
                                         f"guard); its stack:\n{thread_stack(thread)}")
                self._cv.wait(LOOK_S)


class Stepped:
    """A Lead broker whose watchdog and beat thread iterate only when the test steps them, stamping the liveness record
    from a clock the test moves (``LeadBroker(clock=, idle=)``, the flake audit's seam #3). Nothing here waits for time
    to pass: each wait is for an iteration the test released, bounded by ``step_guard_s()``."""

    def __init__(self, engine: Engine, token: str) -> None:
        self.clock = Clock()
        self.broker = lead_broker.LeadBroker(engine, token, clock=self.clock, idle=Steps)
        self.root = Path(engine.aew_root)

    def _steps(self, event: threading.Event) -> Steps:
        assert isinstance(event, Steps)
        return event

    def begin_watchdog(self) -> int:
        """Release one watchdog iteration without waiting for it; :meth:`finish_watchdog` waits."""
        return self._steps(self.broker._stop).release()

    def finish_watchdog(self, n: int) -> None:
        self._steps(self.broker._stop).finish(n, self.broker._watch)

    def watchdog(self) -> None:
        """One watchdog iteration, waited for: back in its stop wait, or ended (superseded)."""
        self.finish_watchdog(self.begin_watchdog())

    def beat(self) -> dict[str, Any]:
        """One beat, waited for, and the record it wrote (no other writer runs meanwhile: a whole record)."""
        beat = self.broker._beat
        assert beat is not None
        steps = self._steps(beat._stop)
        steps.finish(steps.release(), beat._thread)
        record = broker_liveness.read(self.root)
        assert record is not None, "the beat wrote no record broker_liveness.read takes"
        return record

    def in_lock_wait(self) -> bool:
        """Whether the watchdog's read is waiting for the control lock (``FileLock._wait``)."""
        stack = thread_stack(self.broker._watch)
        return re.search(r'[\\/]engine[\\/]lock\.py", line \d+, in _wait\b', stack) is not None

    def loop_ended(self) -> None:
        """Wait for the broker's steering loop to end, as it does once it sees the takeover (``STALE_AUTHORITY``): from
        then on it takes the control lock no more."""
        loop = self.broker.loop
        assert loop is not None and loop._thread is not None
        loop._thread.join(step_guard_s())
        assert not loop._thread.is_alive(), f"the steering loop did not end; its stack:\n{thread_stack(loop._thread)}"


def takeover(project: Any, monkeypatch: Any) -> None:
    """The operator's takeover, its terminal channel substituted in-process (as the takeover tests do)."""
    import aew.operator

    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator-tty (test)"})
    project.token = Engine.discover(project.root).lead_takeover(expect_rev=project.rev(), reason="the test takes over",
                                                                session_label="operator")["token"]


def request(project: Any, kind: str) -> None:
    engine = Engine.discover(project.root)
    engine.steering_request(token=project.token, expect_rev=project.rev(), kind=kind, rationale="the test asks",
                            **({"mode": "walk"} if kind == "raise" else {"action_ref": "ticket_start:T-0001"}))


class Console:
    """The endpoint's console in-process: what it showed, and the last challenge code."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str) -> None:
        self.lines.append(text)

    def code(self) -> str:
        found = re.findall(r"confirmation code ([0-9A-F]{6})", "".join(self.lines))
        assert found, self.lines
        return found[-1]
