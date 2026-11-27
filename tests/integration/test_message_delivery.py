"""MS5's transport and continuation cross the real coordination store and run launch boundary."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from aewflow import stand_in_containment
from fake_harness import credential_hits
from harness_conformance import FakeOpenCodeDriver
from invariants import coordination_violations
from racing_read import read_text_or_none
from test_coordination_store import CP, world
from test_worker_messages import launch, send

from aew.coordination import layout as L
from aew.engine.api import Engine
from aew.engine.authority import token_id_of
from aew.errors import IllegalTransition
from aew.harness import bridge, contract, procs, runlog, worker_messages
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable
from aew.harness.supervisor import Supervisor
from aew.harness.worker_messages import WorkerMessages


@pytest.fixture
def live_lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path)


@pytest.fixture
def worker(tmp_path, monkeypatch):
    return worker_with_credentials(world(tmp_path, model="fakeprov/fake-model"), monkeypatch)


def worker_with_credentials(w, monkeypatch):
    credentials = {}

    def spawn(invocation, run, credential):
        credentials[run] = credential
        return {"run": run, "status": contract.RUNNING}

    monkeypatch.setattr(w.e._harness, "_spawn_run", spawn)
    return w, credentials


class Session:
    def __init__(self):
        self.offers = {}
        self.admitted = {}
        self.posts = []
        self.before_post = None
        self.lose_response = False
        self.confirm_interrupt = True
        self.observations = []

    def post(self, path, body=None, *, timeout, params=None):
        if path == "/api/session/session-for-test/interrupt":
            assert params == {"resume": "false"}
            self.observations.append("interrupt")
            return {}
        assert path == "/api/session/session-for-test/prompt"
        if self.before_post:
            self.before_post()
        self.posts.append(body)
        item = self.offers.setdefault(body["id"], {"id": body["id"], "payload": {"text": body["text"]},
                                                  "delivery": body["delivery"]})
        if self.lose_response:
            raise OpenCodeUnavailable("lost response")
        return {"data": item}

    def get(self, path, *, timeout):
        if path == "/api/session/active":
            self.observations.append("active")
            return {"data": {} if self.confirm_interrupt else {"session-for-test": {}}}
        self.observations.append("admission")
        if path.rsplit("/", 1)[-1] not in self.admitted:
            raise OpenCodeError("GET", path, 404, {"_tag": "MessageNotFoundError"})
        return {"data": self.admitted[path.rsplit("/", 1)[-1]]}

    def admit_all(self):
        self.admitted.update({mid: {"id": mid, "text": item["payload"]["text"]} for mid, item in self.offers.items()})


def transport(worker):
    w, keys = worker
    run = w.lead("harness_launch", invocation=w.inv)["run"]
    events = []
    adapter = OpenCodeAdapter(procs.ProcessTree(), runlog.run_dir(w.e.aew_root, run), events.append)
    session = Session()
    adapter.client, adapter.session, adapter.turn = session, "session-for-test", "running"

    class Owner:
        engine, _credential, inv_id = w.e, keys[run], w.inv

        def _authority(self):
            state = w.e.store.read_committed()
            return True, w.e.run_authority_problem(state, w.inv, run, token_id_of(keys[run]))

        def require_message_authority(self):
            assert w.e.messaging_enabled()

    owner = Owner()
    owner.adapter, owner.run, owner.events = adapter, run, events.append
    return WorkerMessages(owner), session, run


def facts(w):
    return [[fact["kind"] for fact in message["facts"]] for message in w.e.message_thread(w.inv)["messages"]]


def test_live_messages_are_posted_in_order_and_record_admission_only_after_get(worker):
    w, _ = worker
    delivery, session, _ = transport(worker)
    first = w.send("First")["message"]["id"]
    second = w.send("Second")["message"]["id"]
    session.before_post = lambda: (
        "POSTED" in facts(w)[len(session.posts)] or pytest.fail("the POST ran before the fact was durable"))
    before = w.control_bytes()
    delivery.tick(select=True)
    delivery.tick(select=True)
    assert facts(w) == [["RECORDED", "POSTED"], ["RECORDED", "POSTED"]]
    assert [post["metadata"]["aew_message"] for post in session.posts] == [first, second]
    assert [post["delivery"] for post in session.posts] == ["steer", "steer"]
    session.admit_all()
    delivery.tick(select=True)
    assert facts(w) == [["RECORDED", "POSTED", "DELIVERED"], ["RECORDED", "POSTED", "DELIVERED"]]
    assert w.control_bytes() == before


def test_a_lost_post_response_is_reconciled_without_posting_the_id_twice(worker):
    w, _ = worker
    delivery, session, _ = transport(worker)
    w.send()
    session.lose_response = True
    delivery.tick(select=True)
    session.admit_all()
    delivery.tick(select=True)
    assert len(session.posts) == 1
    assert facts(w) == [["RECORDED", "POSTED", "DELIVERED"]]


def test_a_lead_rotation_after_the_durable_offer_never_posts_to_the_old_run(worker, monkeypatch):
    import aew.operator

    w, _ = worker
    delivery, session, _ = transport(worker)
    w.send()
    select = w.e.message_next_post
    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **kw: {"authorized_by": "operator-tty (test)"})

    def rotate_after_selection(**kwargs):
        result = select(**kwargs)
        assert result["message"] is not None and facts(w) == [["RECORDED", "POSTED"]]
        w.e.lead_takeover(reason="the seat was lost", session_label="lead-b")
        return result

    monkeypatch.setattr(w.e, "message_next_post", rotate_after_selection)
    delivery.tick(select=True)
    assert session.posts == []
    assert facts(w) == [["RECORDED", "POSTED"]]


def test_a_held_session_stages_a_message_without_scheduling_an_execution(worker):
    w, _ = worker
    delivery, session, _ = transport(worker)
    delivery.owner.adapter.turn = "held"
    w.send()
    delivery.tick(select=True)
    assert session.posts[0]["resume"] is False
    assert delivery.owner.adapter.sent == []
    assert delivery.owner.adapter.inspect()["turn"] == "held"
    assert facts(w) == [["RECORDED", "POSTED"]]


def test_a_pending_steer_never_prevents_an_interrupted_session_from_being_held(tmp_path, monkeypatch):
    adapter = OpenCodeAdapter(procs.ProcessTree(), tmp_path, lambda event: None)
    adapter.session, adapter.server, adapter.turn = "target", SimpleNamespace(alive=lambda: True), "running"
    adapter.sent = ["launch"]
    queued = []
    active = True

    def post(path, body=None, *, timeout=None, params=None):
        nonlocal active
        if path.endswith("/interrupt"):
            assert params == {"resume": "false"}
            active = False
            return {}
        assert path.endswith("/prompt")
        item = {"id": body["id"], "payload": {"text": body["text"]}, "delivery": body["delivery"]}
        queued.append(item)
        active = active or body.get("resume", True)
        return {"data": item}

    def get(path, params=None, *, timeout=None):
        if path.endswith("/permission") or path.endswith("/form"):
            return {"data": []}
        if path.endswith("/active"):
            return {"data": {adapter.session: {}} if active else {}}
        if path.endswith("/message/first"):
            raise OpenCodeError("GET", path, 404, {"_tag": "MessageNotFoundError"})
        if path.endswith("/message"):
            return {"data": [{"type": "idle", "id": "idle", "outcome": "interrupted"}]}
        assert path.endswith("/inbox")
        return {"data": queued}

    adapter.client = SimpleNamespace(post=post, get=get)
    monkeypatch.setattr(adapter, "_take_snapshot", lambda: None)
    assert adapter.coordination_post("first", "before interrupt", {}, retry=False) == "offered"
    adapter.interrupt()
    adapter._poll()
    adapter._poll()
    assert adapter.inspect()["turn"] == "held"
    assert adapter.sent == ["launch"]
    assert adapter.coordination_post("second", "after interrupt", {}, retry=False) == "offered"
    assert not active
    adapter.send("wake", "steer")
    assert active and adapter.inspect()["turn"] == "running"
    assert adapter.sent == ["launch", "first", "second", queued[-1]["id"]]
    assert [item["id"] for item in queued] == adapter.sent[1:]


def test_a_successor_omits_received_and_answered_messages_and_records_only_its_confirmed_prompt(worker):
    w, keys = worker
    delivery, session, first = transport(worker)
    w.send("Earlier unconfirmed")
    delivery.tick(select=True)
    replied = w.send("Omit this answered message")["message"]["id"]
    received = []
    w.e.message_deliver_wait(invocation_token=keys[first], after="", send=received.append)
    assert [message["id"] for message in received[0]["messages"]] == [replied]
    w.reply(replied, invocation_token=keys[first])
    pending = w.send("Current undelivered")["message"]["id"]
    next_run = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    assert next_run != first
    context = w.e.harness_contract(w.e.store.read(), w.inv, next_run)
    assert context.continuation["messages"] == [pending, session.posts[0]["metadata"]["aew_message"]]
    assert "Earlier unconfirmed" in context.prompt
    assert "Current undelivered" in context.prompt
    assert "Omit this answered message" not in context.prompt
    assert "Earlier unconfirmed" not in str(context.to_record())
    w.e.message_confirm_delivery(credential=keys[next_run], run=next_run,
                                 ids=context.continuation["messages"], via="continuation", transport_ref="msg_launch")
    assert facts(w)[1].count("DELIVERED") == 1
    assert all("DELIVERED" in facts(w)[index] for index in (0, 3))


@pytest.mark.parametrize("step", ["same_second", "wrong_id", "paired"])
def test_a_wait_delivery_needs_its_own_later_completed_step_to_leave_failed_turn(worker, step):
    w, keys = worker
    _, _, run = transport(worker)
    mid = w.send()["message"]["id"]
    w.e.message_deliver_wait(invocation_token=keys[run], after="", send=lambda _: None)
    receipt = w.e.message_thread(w.inv)["messages"][0]["facts"][-1]
    directory = runlog.run_dir(w.e.aew_root, run)
    directory.mkdir(parents=True, exist_ok=True)
    event = runlog.EventLog(directory / "events.jsonl")
    second = receipt["at"][:19] + ".900000Z"
    later = "2100-01-01T00:00:00Z"
    event({"event": "opencode.session.step.started", "assistantMessageID": "own", "at": receipt["at"]})
    event({"event": "opencode.session.step.started", "assistantMessageID": "next",
           "at": second if step == "same_second" else later})
    event({"event": "opencode.session.step.ended", "assistantMessageID": "own" if step == "wrong_id" else "next",
           "at": later})
    successor = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    context = w.e.harness_contract(w.e.store.read(), w.inv, successor)
    assert context.continuation["message_categories"] == {mid: "unresolved" if step == "paired" else "failed_turn"}


def test_c5_refuses_failed_turn_after_a_later_step_and_reports_an_absent_log(worker):
    w, _ = worker
    delivery, session, run = transport(worker)
    mid = w.send()["message"]["id"]
    delivery.tick(select=True)
    session.admit_all()
    delivery.tick(select=True)
    receipt = w.e.message_thread(w.inv)["messages"][0]["facts"][-1]
    directory = runlog.run_dir(w.e.aew_root, run)
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "events.jsonl"
    event = runlog.EventLog(log)
    event({"event": "opencode.session.step.ended", "at": receipt["at"][:19] + ".900000Z"})
    successor = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    launched = runlog.run_dir(w.e.aew_root, successor)
    launched.mkdir(parents=True, exist_ok=True)
    state = w.e.store.read_committed()
    context = w.e.harness_contract(state, w.inv, successor)
    assert context.continuation["message_categories"] == {mid: "failed_turn"}
    runlog.write_record(launched, {"contract": context.to_record()})
    assert coordination_violations(w.root, state, state) == []

    event({"event": "opencode.session.inbox.delivered", "inboxID": receipt["transport_ref"], "at": receipt["at"]})
    event({"event": "opencode.session.step.ended", "at": receipt["at"]})
    assert any("follows a completed worker step" in p for p in coordination_violations(w.root, state, state))

    log.unlink()
    assert any("unverifiable" in p and mid in p for p in coordination_violations(w.root, state, state))


def test_final_check_accepts_only_the_revoked_runs_posted_ids_and_records_once(worker):
    w, keys = worker
    delivery, session, first = transport(worker)
    posted = w.send("Posted")["message"]["id"]
    delivery.tick(select=True)
    never_posted = w.send("Not posted")["message"]["id"]
    w.lead("harness_launch", invocation=w.inv, replace=True)
    w.e.message_final_check(credential=keys[first], run=first,
                             admitted={posted: session.posts[0]["id"], never_posted: "msg_unowned"})
    assert facts(w) == [["RECORDED", "POSTED", "DELIVERED"], ["RECORDED"]]
    actual = w.e.store.read_committed()
    assert coordination_violations(w.root, actual, actual) == []
    with pytest.raises(IllegalTransition, match="already recorded"):
        w.e.message_final_check(credential=keys[first], run=first, admitted={})


@pytest.mark.parametrize("confirmed", [True, False])
def test_the_final_check_halts_the_session_before_checking(worker, confirmed):
    w, _ = worker
    delivery, session, _ = transport(worker)
    w.send()
    delivery.tick(select=True)
    session.confirm_interrupt = confirmed
    session.admit_all()
    w.lead("harness_launch", invocation=w.inv, replace=True)
    delivery.stop()
    delivery.record_final_admissions(delivery.capture_final_admissions())
    assert session.observations == ["interrupt", "active", "admission"]
    assert facts(w) == [["RECORDED", "POSTED", "DELIVERED"]]


def test_the_final_admission_check_never_records_a_reply_after_its_deadline(worker, monkeypatch):
    w, keys = worker
    delivery, _, run = transport(worker)
    w.send()
    delivery.tick(select=True)
    w.lead("harness_launch", invocation=w.inv, replace=True)
    let_reply, returned = threading.Event(), threading.Event()

    def admit_after_check(*args, **kwargs):
        if let_reply.wait(3):
            returned.set()
            return "admitted"
        return "unknown"

    monkeypatch.setattr(worker_messages, "_FINAL_CHECK_S", 0.2)
    monkeypatch.setattr(delivery.owner.adapter, "coordination_admission", admit_after_check)
    delivery.stop()
    try:
        admissions = delivery.capture_final_admissions()
    finally:
        let_reply.set()
    assert returned.wait(2)
    delivery.record_final_admissions(admissions)
    assert facts(w) == [["RECORDED", "POSTED"]]
    with pytest.raises(IllegalTransition, match="already recorded"):
        w.e.message_final_check(credential=keys[run], run=run, admitted={})


@pytest.mark.parametrize("blocked", ["lock", "recovery", "storage"])
def test_final_admission_persistence_never_delays_run_teardown(worker, tmp_path, monkeypatch, blocked):
    w, keys = worker
    delivery, session, run = transport(worker)
    w.send()
    delivery.tick(select=True)
    w.lead("harness_launch", invocation=w.inv, replace=True)
    sup = Supervisor(tmp_path, {"run": run, "invocation": w.inv, "credential": keys[run],
                               "repo_root": str(w.root), "aew_root": str(w.e.aew_root)}, ack=None)
    sup.messaging, sup.messages, sup.adapter = True, delivery, delivery.owner.adapter
    delivery.owner = sup
    closed, terminated, killed = threading.Event(), threading.Event(), threading.Event()
    sup.bridge = SimpleNamespace(close=closed.set, wait_stopped=closed.is_set, requests=0, refused=0, outcomes={})
    sup.record["bridge"] = {}
    monkeypatch.setattr(sup.adapter, "terminate", terminated.set)
    kill_tree = sup.tree.kill

    def kill():
        kill_tree()
        killed.set()

    monkeypatch.setattr(sup.tree, "kill", kill)
    monkeypatch.setattr(worker_messages, "_FINAL_CHECK_S", 0.2)

    if blocked == "storage":
        def fail_write(**_: object) -> None:
            raise OSError(5, "simulated storage failure")

        monkeypatch.setattr(sup.engine, "message_final_check", fail_write)
        sup._finish(contract.TERMINATED, "revoked")
    elif blocked == "lock":
        finishing = threading.Thread(target=sup._finish, args=(contract.TERMINATED, "revoked"), daemon=True)
        with w.e.store.session():
            finishing.start()
            killed_while_locked = killed.wait(2)
            finishing.join(2)
            assert killed_while_locked and not finishing.is_alive()
    else:
        session.admit_all()
        in_recovery, release = threading.Event(), threading.Event()
        recover = sup.engine.store._recover

        def slow_recovery():
            assert sup.engine.store.held
            in_recovery.set()
            assert release.wait(5)
            return recover()

        monkeypatch.setattr(sup.engine.store, "_recover", slow_recovery)
        finishing = threading.Thread(target=sup._finish, args=(contract.TERMINATED, "revoked"), daemon=True)
        try:
            finishing.start()
            assert in_recovery.wait(3)
            assert closed.is_set() and terminated.is_set() and killed.is_set()
        finally:
            release.set()
            finishing.join(2)
        assert not finishing.is_alive()
    assert closed.is_set() and terminated.is_set() and killed.is_set()
    assert sup.record["status"] == contract.TERMINATED
    observed = ["RECORDED", "POSTED", "DELIVERED"] if blocked == "recovery" else ["RECORDED", "POSTED"]
    assert facts(w) == [observed]


def test_a_worker_wait_can_consume_a_message_before_the_transport_is_allowed_to_post_it(worker):
    w, keys = worker
    delivery, session, run = transport(worker)
    delivery._pending = 1
    sent = w.send()
    delivery.tick(select=True)
    assert not session.posts
    replies = []
    w.e.message_deliver_wait(invocation_token=keys[run], after="", send=replies.append)
    delivery._pending = 0
    delivery.tick(select=True)
    assert replies[0]["messages"][0]["id"] == sent["message"]["id"]
    assert facts(w) == [["RECORDED", "DELIVERED"]]
    assert not session.posts


def test_an_active_wait_holds_next_step_but_never_consumes_or_holds_turn_end(worker):
    w, keys = worker
    delivery, session, run = transport(worker)
    queued = w.send("Follow up after the turn.", when="turn-end")["message"]["id"]
    next_step = w.send("Look at the current step.")["message"]["id"]
    assert [m["id"] for m in w.e.message_waiting(invocation_token=keys[run], after="")["messages"]] == [next_step]
    delivery._pending = 1
    delivery.tick(select=True)
    assert [(p["metadata"]["aew_message"], p["delivery"]) for p in session.posts] == [(queued, "queue")]


@pytest.mark.parametrize("when,mode", [("next-step", "steer"), ("turn-end", "queue")])
def test_a_recorded_harness_send_wakes_a_held_agent_and_retains_staging_order(worker, when, mode):
    w, _ = worker
    delivery, session, run = transport(worker)
    delivery.owner.adapter.turn = "held"
    directory = runlog.run_dir(w.e.aew_root, run)
    runlog.write_record(directory, {"status": contract.RUNNING})
    runlog.beat(directory)
    w.send("Stay staged until resumed.")
    delivery.tick(select=True)
    snap = w.control_bytes()
    result = w.e.harness_send(token=w.token, run=run, text="Wake the held run.", when=when)
    assert result["message"]["origin"] == "harness_send" and result["message"]["run"] == run
    assert result["revision"] == w.rev() and w.control_bytes() == snap
    assert not list(runlog.run_dir(w.e.aew_root, run).glob("requests/*"))
    delivery.tick(select=True)
    assert [(p["delivery"], p["resume"]) for p in session.posts] == [("steer", False), (mode, True)]
    assert delivery.owner.adapter.inspect()["turn"] == "running"
    assert delivery.owner.adapter.sent == [p["id"] for p in session.posts]


@pytest.mark.parametrize("admitted", [False, True])
def test_a_waking_send_with_a_lost_response_retries_only_if_not_yet_admitted(worker, admitted):
    w, _ = worker
    delivery, session, run = transport(worker)
    delivery.owner.adapter.turn = "held"
    directory = runlog.run_dir(w.e.aew_root, run)
    runlog.write_record(directory, {"status": contract.RUNNING})
    runlog.beat(directory)
    w.e.harness_send(token=w.token, run=run, text="Continue after that", when="turn-end")
    session.lose_response = True
    delivery.tick(select=True)
    assert delivery.owner.adapter.inspect()["turn"] == "held"
    session.lose_response = False
    if admitted:
        session.admit_all()
    delivery.tick(select=True)
    assert len(session.posts) == (1 if admitted else 2)
    assert all(post["resume"] is True for post in session.posts)
    assert delivery.owner.adapter.inspect()["turn"] == "running"
    assert ("DELIVERED" in facts(w)[0]) is admitted


def _submit_through_run_bridge(w, keys, run, delivery):
    directory = runlog.run_dir(w.e.aew_root, run)
    sup = Supervisor(directory, {"run": run, "invocation": w.inv, "credential": keys[run],
                                 "repo_root": str(w.root), "aew_root": str(w.e.aew_root)}, ack=None)
    sup.messaging, sup.messages, sup.adapter = True, delivery, delivery.owner.adapter
    delivery.owner = sup
    bridge_server = bridge.BridgeServer(sup.handle)
    sup.bridge = bridge_server
    bridge_server.start()
    try:
        out = bridge.call("submit", {"kind": "implementation_report", "text": CP.submission(CP.REPORT)},
                          endpoint=bridge_server.address, key=bridge_server.key_hex)
        assert bridge_server.outcomes == {"submit": {"ok": 1}}
        return out
    finally:
        bridge_server.close()
        assert bridge_server.wait_stopped()


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_submit_settles_admission_before_the_next_delivery_tick(worker, when):
    w, keys = worker
    delivery, session, run = transport(worker)
    w.send(when=when)
    delivery.tick(select=True)
    assert facts(w) == [["RECORDED", "POSTED"]]
    session.admit_all()
    out = _submit_through_run_bridge(w, keys, run, delivery)
    assert out["pending_lead_messages"] == 0
    assert session.observations[-1] == "admission" and "interrupt" not in session.observations
    assert facts(w) == [["RECORDED", "POSTED", "DELIVERED"]]


@pytest.mark.parametrize("final_check", [False, True], ids=["submit", "revoked"])
def test_settlement_can_confirm_every_post_after_replies_free_send_slots(worker, final_check):
    w, keys = worker
    delivery, session, run = transport(worker)
    messages = []
    for index in range(L.MAX_UNDELIVERED_LEAD + 1):
        mid = w.send(f"Follow-up {index}", when="turn-end")["message"]["id"]
        messages.append(mid)
        delivery.tick(select=True)
        w.reply(mid, invocation_token=keys[run])

    assert len(session.posts) == len(messages)
    session.admit_all()
    if final_check:
        w.lead("harness_launch", invocation=w.inv, replace=True)
        delivery.stop()
        captured = delivery.capture_final_admissions()
        assert list(captured.admitted) == messages
        delivery.record_final_admissions(captured)
    else:
        admitted, continued = delivery.submit_admissions()
        assert list(admitted) == messages and continued is None
        result = w.e.submit(invocation_token=keys[run], kind="implementation_report", text=CP.submission(CP.REPORT),
                            admitted=admitted)
        assert result["pending_lead_messages"] == 0

    entries = w.e.message_thread(w.inv)["messages"]
    assert [m["id"] for m in entries if any(f["kind"] == L.DELIVERED for f in m["facts"])] == messages


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_the_first_successor_report_captures_an_admitted_continuation_before_the_tick(tmp_path, monkeypatch, when):
    stand_in_containment(monkeypatch, {"guarantee": "dev", "effective": "workdir_separation_only"})
    w, keys = worker_with_credentials(world(tmp_path, checks=True, model="fakeprov/fake-model"), monkeypatch)
    delivery, session, _ = transport((w, keys))
    mid = w.send("Carry this into the successor", when=when)["message"]["id"]
    run = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    carried = w.e.harness_contract(w.e.store.read(), w.inv, run).continuation
    assert carried["messages"] == [mid]
    delivery.owner.run, delivery.owner._credential = run, keys[run]
    delivery.owner.adapter._coordination_launch_id = "launch-prompt"
    delivery.launched(carried)
    session.admitted["launch-prompt"] = {"id": "launch-prompt", "text": "Admitted launch with continuation"}
    assert facts(w) == [["RECORDED"]]

    for rel, text in CP.PATCH.items():
        (w.workspace / rel).write_text(text, encoding="utf-8", newline="\n")
    w.e.check_run(invocation_token=keys[run], check_id="unit")
    submitted = _submit_through_run_bridge(w, keys, run, delivery)
    assert submitted["pending_lead_messages"] == 0
    assert facts(w) == [["RECORDED", "DELIVERED"]]
    assert w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")["ok"]


def test_continuation_recovers_a_replied_but_unconfirmed_message_without_repeating_a_delivered_reply(worker):
    w, keys = worker
    delivery, session, run = transport(worker)
    unconfirmed = w.send("First", when="turn-end")["message"]["id"]
    delivery.tick(select=True)
    w.reply(unconfirmed, invocation_token=keys[run])
    confirmed = w.send("Second")["message"]["id"]
    delivery.tick(select=True)
    offer = session.posts[-1]
    session.admitted[offer["id"]] = {"id": offer["id"], "text": offer["text"]}
    delivery.tick(select=False)
    w.reply(confirmed, invocation_token=keys[run])
    successor = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    contract = w.e.harness_contract(w.e.store.read(), w.inv, successor)
    assert contract.continuation["message_categories"] == {unconfirmed: "unconfirmed"}
    assert "after you finish your main task" in contract.coordination_text[0]


def test_a_lead_message_reaches_the_worker_at_the_next_step_boundary(live_lab, tmp_path):
    run, sync = launch(live_lab, tmp_path, [], live=True)
    engine = Engine.discover(live_lab.root)
    events = runlog.run_dir(live_lab.aew_root, run) / "events.jsonl"

    def event_rows(event=None):
        trace = read_text_or_none(events) or ""
        rows = [json.loads(line) for line in trace.splitlines(keepends=True) if line.endswith("\n")]
        return [row for row in rows if row["event"] == event] if event else rows

    live_lab.until(lambda: len(event_rows("opencode.session.step.started")) >= 2,
                   "watchdog", what="worker blocked in its second step")
    second = event_rows("opencode.session.step.started")[1]["assistantMessageID"]
    queued = engine.message_record_lead(token=live_lab.project.token, to="INV-0001", body="Follow up after your turn.",
                                        when="turn-end")
    engine.message_record_lead(token=live_lab.project.token, to="INV-0001", body="Also document the follow-up.",
                               when="turn-end")
    mid = send(live_lab, "Check the shutdown edge before your next step.")["message"]["id"]

    def observed():
        result = engine.message_thread("INV-0001")["messages"]
        return [fact for message in result if message["id"] == mid for fact in message["facts"]]

    live_lab.until(lambda: len(event_rows("opencode.session.inbox.enqueued")) >= 4,
                   "watchdog", what="OpenCode enqueued all three live offers during the second step")
    queued_prompt, next_queued, prompt = [r["inboxID"] for r in event_rows("opencode.session.inbox.enqueued")[1:4]]
    assert [fact["kind"] for fact in observed()] == ["RECORDED", "POSTED"]
    (sync / "go").touch()
    live_lab.until(lambda: len(observed()) == 3, "watchdog", what="confirmed next-step admission")
    delivered = observed()[-1]
    assert (delivered["kind"], delivered["transport_ref"]) == ("DELIVERED", prompt)
    live_lab.until(lambda: len(event_rows("opencode.session.step.started")) >= 3,
                   "watchdog", what="the worker starts the third step")
    rows = event_rows()
    second_end = next(i for i, row in enumerate(rows) if row["event"] == "opencode.session.step.ended"
                      and row["assistantMessageID"] == second)
    admitted = next(i for i, row in enumerate(rows) if row["event"] == "opencode.session.inbox.delivered"
                    and row["inboxID"] == prompt)
    third_start = [i for i, row in enumerate(rows) if row["event"] == "opencode.session.step.started"][2]
    assert second_end < admitted < third_start
    assert not any(r.get("inboxID") == queued_prompt for r in event_rows("opencode.session.inbox.delivered"))
    (sync / "end").touch()
    live_lab.wait(run)
    rows = event_rows()
    third = rows[third_start]["assistantMessageID"]
    third_end = next(i for i, r in enumerate(rows) if r["event"] == "opencode.session.step.ended"
                     and r["assistantMessageID"] == third)
    queued_at = next(i for i, r in enumerate(rows) if r["event"] == "opencode.session.inbox.delivered"
                     and r["inboxID"] == queued_prompt)
    queued_again_at = next(i for i, r in enumerate(rows) if r["event"] == "opencode.session.inbox.delivered"
                           and r["inboxID"] == next_queued)
    assert third_end < queued_at < queued_again_at
    assert any(r["event"] == "opencode.session.step.ended" for r in rows[queued_at + 1:queued_again_at])
    assert any(r["event"] == "opencode.prompt" and r["message"] == queued_prompt and r["delivery"] == "queue"
               for r in rows)
    assert engine.message_thread("INV-0001")["messages"][0]["id"] == queued["message"]["id"]
