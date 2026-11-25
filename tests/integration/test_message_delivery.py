"""MS5's transport and continuation cross the real coordination store and run launch boundary."""

from __future__ import annotations

import pytest
from fake_harness import credential_hits
from harness_conformance import FakeOpenCodeDriver
from test_coordination_store import world
from test_worker_messages import launch, send

from aew.engine.api import Engine
from aew.errors import IllegalTransition
from aew.harness import contract, procs, runlog
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable
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

    def post(self, path, body, *, timeout):
        assert path == "/api/session/session-for-test/prompt"
        if self.before_post:
            self.before_post()
        self.posts.append(body)
        item = self.offers.setdefault(body["id"], {"id": body["id"], "payload": {"text": body["text"]}})
        if self.lose_response:
            raise OpenCodeUnavailable("lost response")
        return {"data": item}

    def get(self, path, *, timeout):
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

    class Supervisor:
        engine, _credential, inv_id = w.e, keys[run], w.inv

        def _authority(self):
            return True, None

        def require_message_authority(self):
            assert w.e.messaging_enabled()

    owner = Supervisor()
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
    with pytest.raises(IllegalTransition, match="already recorded"):
        w.e.message_final_check(credential=keys[first], run=first, admitted={})


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
    live_lab.until(lambda: runlog.read_regular(events).count(b'"opencode.session.step.started"') >= 2,
                   "watchdog", what="worker blocked in its second step")
    mid = send(live_lab, "Check the shutdown edge before your next step.")["message"]["id"]

    def observed():
        result = engine.message_thread("INV-0001")["messages"]
        return [f["kind"] for message in result if message["id"] == mid for f in message["facts"]]

    live_lab.until(lambda: "POSTED" in observed(), "watchdog", what="recorded live offer")
    assert observed() == ["RECORDED", "POSTED"]
    (sync / "go").touch()
    live_lab.until(lambda: "DELIVERED" in observed(), "watchdog", what="confirmed next-step admission")
    (sync / "end").touch()
    live_lab.wait(run)
