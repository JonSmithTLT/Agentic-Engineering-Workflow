"""The supervisor's watch loop reads the control state lock-free, and a failed read never ends a live run (#366).

The loop beats the run's heartbeat, so it never waits on the control lock (#366: a lock held elsewhere stalled the
beat and a live run read as `lost`). A lock-free read can meet a writer's replace, which the locked read never could:
such a failure is unknown for that tick, the loop reads again on the next, and a Lead request already taken from the
queue is kept for the next tick, never refused (#366 review, M1 and M2). These stand-ins run the real methods with a
store whose locked reads fail the test."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import errors
from aew.harness import runlog
from aew.harness.supervisor import Supervisor
from aew.util import sha256_text

INV, RUN, TOKEN = "INV-0001", "R-INV-0001-1", "tok-1"


class LockFreeOnly:
    """A store whose lock-free reads follow a script (a state, or an exception to raise), and whose locked reads fail
    the test: the watch loop must never take the control lock."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.reads = 0

    def read_committed(self) -> dict[str, Any]:
        self.reads += 1
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, BaseException):
            raise step
        return step

    def _locked(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the watch loop took the control lock")

    read = current = session = control_lock = _locked


def state(requests: list[dict[str, Any]] | None = None, problem: str | None = None) -> dict[str, Any]:
    run = {"run": RUN, "requests": requests or []}
    return {"invocations": {INV: {"runs": [run]}}, "problem": problem}


def stand_in(tmp_path: Path, store: LockFreeOnly) -> Supervisor:
    sup = Supervisor.__new__(Supervisor)  # only the loop's reads: no run, no process
    sup.run_dir, sup.run, sup.inv_id, sup.token_id = tmp_path, RUN, INV, TOKEN
    sup.events = runlog.EventLog(tmp_path / "events.jsonl")
    sup.record = {"timeline": []}
    sup._handled, sup._deferred, sup._state_unreadable = set(), {}, False
    sup._control_seen, sup.stop_reason, sup._watching = None, None, threading.Event()
    sup.engine = SimpleNamespace(store=store, aew_root=tmp_path,
                                 run_authority_problem=lambda s, inv, run, tok: s["problem"])
    return sup


def recorded_request(tmp_path: Path, kind: str, **payload: Any) -> dict[str, Any]:
    """Deliver a request file as a Lead operation does, and return the entry that operation records for it."""
    name, text = runlog.new_request(kind, payload)
    runlog.deliver_request(tmp_path, name, text)
    return {"file": name, "kind": kind, "sha256": sha256_text(text)}


def events(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]


UNREADABLE = [errors.ProjectNotFound("no control state (a Windows replace in progress)"),
              PermissionError(13, "a sharing violation outlasting its retries"), OSError(5, "an I/O error")]


def test_a_recorded_request_is_authorized_from_the_lock_free_read(tmp_path):
    """M1: `_authorized_requests` reads lock-free, as `authority_problem` does: the store fails the test on a locked
    read."""
    store = LockFreeOnly([])
    store.script = [state([recorded_request(tmp_path, "send", text="go on")])]
    sup = stand_in(tmp_path, store)
    assert [r["kind"] for r in sup._authorized_requests()] == ["send"]
    assert sup.authority_problem() is None and store.reads == 2


@pytest.mark.parametrize("failure", UNREADABLE, ids=type)
def test_a_request_taken_while_the_state_is_unreadable_is_kept_for_the_next_tick(tmp_path, failure):
    """M2: the request files are taken from the queue before the state is read, so a failed read once refused a
    recorded `stop` for good, or (an `OSError`) crashed the run. Now the request waits for a readable state."""
    entry = recorded_request(tmp_path, "stop", reason="the Lead's stop")
    sup = stand_in(tmp_path, LockFreeOnly([failure, state([entry])]))
    assert sup._authorized_requests() == []
    assert list((tmp_path / "requests").iterdir()) == []  # taken from the queue, and kept
    assert [(r["kind"], r["reason"]) for r in sup._authorized_requests()] == [("stop", "the Lead's stop")]
    assert sup._authorized_requests() == []  # acted on once
    seen = events(tmp_path)
    assert [e["event"] for e in seen] == ["state_unreadable"], seen


@pytest.mark.parametrize("failure", UNREADABLE, ids=type)
def test_an_unreadable_state_never_ends_a_live_run_and_is_read_again_on_the_next_tick(tmp_path, monkeypatch,
                                                                                       failure):
    """M2: in the watch loop, a failed authority read is unknown for that tick, not a crash: the loop beats on and reads
    again at the next tick, and a revocation committed meanwhile still ends the run. The failure is logged once."""
    from aew.harness import supervisor

    # The loop's first tick reads because the control file is new to it; after that, only an unread state is read
    # again before the poll, which never comes: the adapter exits at its 20th tick.
    monkeypatch.setattr(supervisor, "STATE_POLL_S", 3600.0)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "control.yaml").write_text("")
    store = LockFreeOnly([failure, failure, failure, state(problem="revoked")])
    sup = stand_in(tmp_path, store)
    ticks = iter(range(20))
    sup.adapter = SimpleNamespace(inspect=lambda: {"alive": next(ticks, None) is not None})
    ended: list[tuple[str, str]] = []
    monkeypatch.setattr(sup, "_finish", lambda status, reason, **kw: ended.append((status, reason)), raising=False)
    monkeypatch.setattr(sup, "_finish_exited", lambda status: ended.append(("exited", "")), raising=False)
    sup.watch()
    assert ended == [("terminated", "authority ended: revoked")], ended
    assert store.reads == 4  # one read a tick until one succeeds
    assert runlog.heartbeat_age(tmp_path) is not None
    assert [e["event"] for e in events(tmp_path)] == ["state_unreadable"]


def test_a_failed_authority_read_at_the_bridge_leaves_the_engine_as_the_gate(tmp_path):
    """The bridge's own check is a fast path: an unreadable state is no problem found, and the engine re-checks the
    credential under the lock before anything is written."""
    sup = stand_in(tmp_path, LockFreeOnly([errors.ProjectNotFound("mid-replace")]))
    assert sup.authority_problem() is None
    assert sup._authority() == (False, None)
