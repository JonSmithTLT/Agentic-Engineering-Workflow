"""Helpers for the operator notifier's tests (M4-E E7a): a recording notifier, adopting a policy with a notifier, the
operator's raise as the endpoint commits it, seeding control state, a bounded wait that can say why it timed out, and
the wait on a Lead broker's watchdog with what to say."""

from __future__ import annotations

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
from aew.engine.store import Transition
from aew.harness import broker_liveness, procs

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
