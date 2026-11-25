"""MS5's transport and continuation cross the real coordination store and run launch boundary."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest
from fake_harness import credential_hits
from harness_conformance import FakeOpenCodeDriver
from invariants import coordination_violations
from racing_read import read_text_or_none
from test_coordination_store import world
from test_worker_messages import launch, send

from aew.engine.api import Engine
from aew.engine.authority import token_id_of
from aew.errors import IllegalTransition
from aew.harness import contract, procs, runlog, worker_messages
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
    w = world(tmp_path, model="fakeprov/fake-model")
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
        item = self.offers.setdefault(body["id"], {"id": body["id"], "payload": {"text": body["text"]}})
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
        w.e.lead_takeover(expect_rev=w.rev(), reason="the seat was lost", session_label="lead-b")
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
        item = {"id": body["id"], "payload": {"text": body["text"]}}
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


def test_a_successor_carries_only_unanswered_messages_and_records_only_its_confirmed_prompt(worker):
    w, keys = worker
    delivery, session, first = transport(worker)
    w.send("Earlier unconfirmed")
    delivery.tick(select=True)
    replied = w.send("Omit this answered message")["message"]["id"]
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
    assert "DELIVERED" not in facts(w)[1]
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
    delivery.final_check()
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
        delivery.final_check()
    finally:
        let_reply.set()
    assert returned.wait(2)
    assert facts(w) == [["RECORDED", "POSTED"]]
    with pytest.raises(IllegalTransition, match="already recorded"):
        w.e.message_final_check(credential=keys[run], run=run, admitted={})


@pytest.mark.parametrize("blocked", ["lock", "storage"])
def test_a_failed_final_admission_write_never_blocks_the_run_teardown(worker, tmp_path, monkeypatch, blocked):
    w, keys = worker
    delivery, _, run = transport(worker)
    w.send()
    delivery.tick(select=True)
    w.lead("harness_launch", invocation=w.inv, replace=True)
    sup = Supervisor(tmp_path, {"run": run, "invocation": w.inv, "credential": keys[run],
                               "repo_root": str(w.root), "aew_root": str(w.e.aew_root)}, ack=None)
    sup.messaging, sup.messages, sup.adapter = True, delivery, delivery.owner.adapter
    delivery.owner = sup
    ended = threading.Event()
    monkeypatch.setattr(sup, "_end", lambda *_: ended.set())
    monkeypatch.setattr(worker_messages, "_FINAL_CHECK_S", 0.2)

    if blocked == "storage":
        def fail_write(**_: object) -> None:
            raise OSError(5, "simulated storage failure")

        monkeypatch.setattr(sup.engine, "message_final_check", fail_write)
        sup._finish(contract.TERMINATED, "revoked")
        assert ended.is_set()
    else:
        finishing = threading.Thread(target=sup._finish, args=(contract.TERMINATED, "revoked"), daemon=True)
        with w.e.store.session():
            finishing.start()
            ended_while_locked = ended.wait(2)
        finishing.join(2)
        assert ended_while_locked and not finishing.is_alive()
    assert facts(w) == [["RECORDED", "POSTED"]]


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
    mid = send(live_lab, "Check the shutdown edge before your next step.")["message"]["id"]

    def observed():
        result = engine.message_thread("INV-0001")["messages"]
        return [fact for message in result if message["id"] == mid for fact in message["facts"]]

    live_lab.until(lambda: len(event_rows("opencode.session.inbox.enqueued")) >= 2,
                   "watchdog", what="OpenCode enqueued the live offer during the second step")
    prompt = event_rows("opencode.session.inbox.enqueued")[1]["inboxID"]
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
    (sync / "end").touch()
    live_lab.wait(run)
