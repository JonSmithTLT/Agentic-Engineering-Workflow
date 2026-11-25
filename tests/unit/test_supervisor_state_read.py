"""The supervisor's watch loop reads the control state lock-free, and a failed read never ends a live run (#366).

The loop beats the run's heartbeat, so it never waits on the control lock (#366: a lock held elsewhere stalled the
beat and a live run read as `lost`). A lock-free read can meet a writer's replace, which the locked read never could:
such a failure is unknown for that tick, the loop reads again on the next, and a Lead request already taken from the
queue is kept for the next tick, never refused (#366 review, M1 and M2). These stand-ins run the real methods with a
store whose locked reads fail the test."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import errors
from aew.harness import contract as K
from aew.harness import runlog
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.supervisor import REQUEST_ORDER_WAIT_TICKS, Supervisor
from aew.harness.worker_messages import WorkerMessages
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
    sup._unread_reported, sup._request_order_waits = set(), {}
    sup._control_seen, sup.stop_reason, sup._watching = None, None, threading.Event()
    sup.deadline_s = None  # the deadline start() decides at custody: none for these runs
    sup.messaging = False  # start() would supply the adopted launch snapshot
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


def test_a_kept_request_is_never_replaced_by_a_later_file_of_the_same_name(tmp_path):
    """N3: the run directory is model-writable, so a file written under a kept request's name after it was taken never
    replaces the Lead's request."""
    entry = recorded_request(tmp_path, "stop", reason="the Lead's stop")
    sup = stand_in(tmp_path, LockFreeOnly([errors.ProjectNotFound("mid-replace"), state([entry])]))
    assert sup._authorized_requests() == []
    runlog.deliver_request(tmp_path, entry["file"], json.dumps({"kind": "stop", "reason": "a forged reason"}))
    assert [(r["kind"], r["reason"]) for r in sup._authorized_requests()] == [("stop", "the Lead's stop")]


def test_kept_requests_are_judged_with_later_ones_in_the_order_the_lead_issued_them(tmp_path):
    """N4: a request kept over an unreadable state was issued before any taken at a later tick, so it is acted on
    first, never after a later one."""
    first = recorded_request(tmp_path, "send", text="first")
    sup = stand_in(tmp_path, LockFreeOnly([errors.ProjectNotFound("mid-replace")]))
    assert sup._authorized_requests() == []
    second = recorded_request(tmp_path, "send", text="second")
    assert first["file"] < second["file"]  # names start with their issue time: name order is issue order
    sup.engine.store.script = [state([first, second])]
    assert [r["text"] for r in sup._authorized_requests()] == ["first", "second"]


def test_an_earlier_issued_request_delivered_late_is_still_judged_first(tmp_path):
    """N4, the case only the sort covers (#369 review, m1): a request issued first is delivered after a later one,
    which a tick whose state read fails takes and keeps. Issue order is name order, so the earlier one is acted on
    first."""
    first_name, first_text = runlog.new_request("send", {"text": "first"})  # issued first, not yet delivered
    second = recorded_request(tmp_path, "send", text="second")  # issued and delivered later
    assert first_name < second["file"]
    sup = stand_in(tmp_path, LockFreeOnly([errors.ProjectNotFound("mid-replace")]))
    assert sup._authorized_requests() == []  # `second` taken and kept
    runlog.deliver_request(tmp_path, first_name, first_text)  # the late delivery
    first = {"file": first_name, "kind": "send", "sha256": sha256_text(first_text)}
    sup.engine.store.script = [state([first, second])]
    assert [r["text"] for r in sup._authorized_requests()] == ["first", "second"]


def test_two_requests_of_one_kind_issued_on_one_clock_tick_are_both_acted_on_in_order(tmp_path, monkeypatch):
    """The earlier test's name order, on the clock it failed on: one that repeats a value (a nightly on Windows and
    Python 3.11). With one name for both, the second's file replaced the first's, and the first was lost."""
    frozen = time.time_ns()
    monkeypatch.setattr(time, "time_ns", lambda: frozen)
    first = recorded_request(tmp_path, "send", text="first")
    second = recorded_request(tmp_path, "send", text="second")
    sup = stand_in(tmp_path, LockFreeOnly([state([first, second])]))
    assert [r["text"] for r in sup._authorized_requests()] == ["first", "second"]


def block_request(monkeypatch, name, blocked):
    real = runlog._read_regular

    def read(path):
        if path.name == name and blocked():
            raise PermissionError(13, "Permission denied")
        return real(path)

    monkeypatch.setattr(runlog, "IS_WINDOWS", True)
    monkeypatch.setattr(runlog, "_read_regular", read)


def test_an_unread_request_reports_its_error_codes_once_per_name(tmp_path, monkeypatch):
    entry = recorded_request(tmp_path, "interrupt")
    sup = stand_in(tmp_path, LockFreeOnly([state([entry])]))
    block_request(monkeypatch, entry["file"], lambda: True)
    assert sup._authorized_requests() == []
    assert sup._authorized_requests() == []
    assert [{key: value for key, value in e.items() if key != "at"} for e in events(tmp_path)] == [
        {"event": "request_unread", "file": entry["file"], "errno": 13, "winerror": None},
    ]


def test_a_temporarily_unreadable_interrupt_still_precedes_the_send(tmp_path, monkeypatch):
    interrupt = recorded_request(tmp_path, "interrupt")
    send = recorded_request(tmp_path, "send", text="resume")
    sup = stand_in(tmp_path, LockFreeOnly([state([interrupt, send])]))
    blocked = True
    block_request(monkeypatch, interrupt["file"], lambda: blocked)
    assert sup._authorized_requests() == []
    blocked = False
    assert [r["kind"] for r in sup._authorized_requests()] == ["interrupt", "send"]
    assert sup._authorized_requests() == []


def test_a_permanently_unreadable_request_only_holds_later_requests_for_the_order_bound(tmp_path, monkeypatch):
    interrupt = recorded_request(tmp_path, "interrupt")
    send = recorded_request(tmp_path, "send", text="resume")
    sup = stand_in(tmp_path, LockFreeOnly([state([interrupt, send])]))
    block_request(monkeypatch, interrupt["file"], lambda: True)
    for _ in range(REQUEST_ORDER_WAIT_TICKS):
        assert sup._authorized_requests() == []
    assert [r["kind"] for r in sup._authorized_requests()] == ["send"]
    later = recorded_request(tmp_path, "send", text="later")
    sup.engine.store.script = [state([interrupt, send, later])]
    assert [r["text"] for r in sup._authorized_requests()] == ["later"]
    bypasses = [e for e in events(tmp_path) if e["event"] == "request_order_bypassed"]
    assert [(e["file"], e["ticks"]) for e in bypasses] == [(interrupt["file"], REQUEST_ORDER_WAIT_TICKS)]


def test_an_unrecorded_unreadable_file_cannot_hold_a_lead_request(tmp_path, monkeypatch):
    unrecorded = recorded_request(tmp_path, "interrupt")
    send = recorded_request(tmp_path, "send", text="resume")
    sup = stand_in(tmp_path, LockFreeOnly([state([send])]))
    block_request(monkeypatch, unrecorded["file"], lambda: True)
    assert [r["kind"] for r in sup._authorized_requests()] == ["send"]


@pytest.mark.parametrize("failure", UNREADABLE, ids=type)
def test_an_unreadable_state_never_ends_a_live_run_and_is_read_again_on_the_next_tick(tmp_path, monkeypatch,
                                                                                       failure):
    """M2: in the watch loop, a failed authority read is unknown for that tick, not a crash: the loop beats on and reads
    again at the next tick, and a revocation committed meanwhile still ends the run. The failure is logged once."""
    from aew.harness import supervisor

    # The loop's first tick reads because the control file is new to it; after that, only an unread state is read
    # again, since the poll never comes (whatever the host's uptime: time.monotonic() counts from boot, #366 quick
    # check F1). The adapter exits at its 20th tick.
    monkeypatch.setattr(supervisor, "STATE_POLL_S", float("inf"))
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


def test_a_run_stays_live_while_opencode_answers_a_steering_request(tmp_path, monkeypatch):
    entry = recorded_request(tmp_path, "send", text="continue")
    sup = stand_in(tmp_path, LockFreeOnly([state([entry])]))
    (tmp_path / "run.json").write_text(json.dumps({"status": K.RUNNING}), encoding="utf-8")
    renewed = threading.Event()
    aged = threading.Event()
    real_beat = runlog.beat

    def beat(directory):
        real_beat(directory)
        if aged.is_set():
            renewed.set()

    def send(text, delivery):
        assert (text, delivery) == ("continue", "steer")
        old = time.time() - runlog.STALE_AFTER_S - 1
        os.utime(tmp_path / "heartbeat", (old, old))
        aged.set()
        assert renewed.wait(5), "the supervisor stopped beating while send was in flight"
        assert runlog.observed_status(tmp_path)[0] == K.RUNNING

    monkeypatch.setattr(runlog, "beat", beat)
    sup.adapter = SimpleNamespace(STEERING_BOUND_S=OpenCodeAdapter.STEERING_BOUND_S, send=send,
                                  inspect=lambda: {"alive": False})
    ended = []
    monkeypatch.setattr(sup, "_finish_exited", ended.append)
    sup.watch()
    assert ended == [{"alive": False}]


def test_a_hung_steering_call_lets_the_heartbeat_go_stale_after_its_bound(tmp_path, monkeypatch):
    entry = recorded_request(tmp_path, "send", text="continue")
    sup = stand_in(tmp_path, LockFreeOnly([state([entry])]))
    (tmp_path / "run.json").write_text(json.dumps({"status": K.RUNNING}), encoding="utf-8")
    monkeypatch.setattr(runlog, "HEARTBEAT_S", 0.25)
    monkeypatch.setattr(runlog, "STALE_AFTER_S", 1.5)

    def send(_text, _delivery):
        time.sleep(4)  # past the one-second heartbeat bound and the freshness window
        assert runlog.observed_status(tmp_path)[0] == K.LOST, runlog.heartbeat_age(tmp_path)

    sup.adapter = SimpleNamespace(STEERING_BOUND_S=1.0, send=send, inspect=lambda: {"alive": False})
    monkeypatch.setattr(sup, "_finish_exited", lambda status: None)
    sup.watch()


def test_a_messaging_control_write_never_holds_the_supervisors_heartbeat(tmp_path, monkeypatch):
    sup = stand_in(tmp_path, LockFreeOnly([state()]))
    sup.messaging, sup._credential = True, TOKEN
    sup.messages = WorkerMessages(sup)
    sup.record["coordination_delivery"] = "live_pending"
    blocked = threading.Event()
    release = threading.Event()
    heartbeats = []
    until = time.monotonic() + 7

    def take_message(**kwargs):
        blocked.set()
        assert release.wait(5), "the heartbeat stopped while the thread awaited the coordination writer"
        return {"message": None, "refused": []}

    def beat(_directory):
        if blocked.is_set() and not release.is_set():
            heartbeats.append(time.monotonic())
            if len(heartbeats) == 2:
                release.set()

    sup.engine.message_next_post = take_message
    sup.adapter = SimpleNamespace(coordination_live=True,
                                  inspect=lambda: {"alive": not release.is_set() and time.monotonic() < until,
                                                   "turn": "running"})
    monkeypatch.setattr(runlog, "beat", beat)
    monkeypatch.setattr(runlog, "HEARTBEAT_S", 0)
    ended = []
    monkeypatch.setattr(sup, "_finish_exited", ended.append)
    try:
        sup.watch()
    finally:
        release.set()
        sup.messages.stop()
    assert len(heartbeats) == 2 and ended == [{"alive": False, "turn": "running"}]


def test_a_messaging_drain_never_changes_an_observed_exit_to_a_hard_deadline(tmp_path, monkeypatch):
    from aew.harness import supervisor

    sup = stand_in(tmp_path, LockFreeOnly([state()]))
    sup.messaging, sup.deadline_s = True, 1
    sup.record["coordination_delivery"] = "live_pending"
    drained = iter([False, False, True])
    sup.messages = SimpleNamespace(start=lambda deadline: None, drained=lambda: next(drained))
    status = {"alive": False, "exit_code": 0}
    sup.adapter = SimpleNamespace(coordination_live=True, inspect=lambda: status)
    clocks = iter([0, 0.5, 1.5, 2.5])
    monkeypatch.setattr(supervisor, "time", SimpleNamespace(monotonic=lambda: next(clocks), sleep=lambda _: None))
    ended = []
    monkeypatch.setattr(sup, "_finish_exited", ended.append)
    sup.watch()
    assert ended == [status]


@pytest.mark.parametrize("messaging, posted", [(False, False), (True, False)])
def test_a_revoked_run_without_posted_messages_stops_without_an_admission_check(tmp_path, monkeypatch,
                                                                                 messaging, posted):
    sup = stand_in(tmp_path, LockFreeOnly([state(problem="superseded")]))
    sup.messaging = messaging
    sup._lock = threading.Lock()
    sup.messages = SimpleNamespace(stop=lambda: None, has_posted=posted,
                                   final_check=lambda: pytest.fail("there is no recorded offer to check"))
    monkeypatch.setattr(sup, "_start_overdue", lambda: False)
    monkeypatch.setattr(sup, "_background_beats", lambda *args, **kwargs: threading.Event())
    ended = []
    monkeypatch.setattr(sup, "_end", lambda *args: ended.append(args))
    sup._finish(K.TERMINATED, "authority ended: superseded")
    assert ended == [(K.TERMINATED, "authority ended: superseded", None)]


def test_watch_refuses_a_run_whose_deadline_start_has_not_decided(tmp_path, monkeypatch):
    """A supervisor's deadline is UNDECIDED until ``start`` decides it at custody, and ``watch`` refuses it rather than
    read it as no deadline (the review of E228's fourth PR, n3, and its quick check, QC-2): no run is watched
    unbounded because ``start`` was skipped."""
    from aew.engine import api
    from aew.harness import supervisor

    monkeypatch.setattr(api, "Engine", lambda repo_root, aew_root: SimpleNamespace())
    monkeypatch.setattr(supervisor, "token_id_of", lambda credential: TOKEN)
    handoff = {"run": RUN, "invocation": INV, "credential": TOKEN, "repo_root": str(tmp_path),
               "aew_root": str(tmp_path)}
    sup = Supervisor(tmp_path, handoff, ack=None)
    with pytest.raises(errors.IllegalTransition, match="start has not run"):
        sup.watch()
