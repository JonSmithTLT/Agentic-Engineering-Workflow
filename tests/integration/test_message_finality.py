"""MS5b report finality at the control transaction and its read-only advice."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from aewflow import stand_in_containment
from test_coordination_store import CP, OPERATOR, world

from aew.engine import coordination_ops as coordination
from aew.errors import PendingLeadMessage, ValidationFailed
from aew.knowledge import evidence as E
from aew.util import utc_now


@pytest.fixture
def implementation(tmp_path, monkeypatch):
    stand_in_containment(monkeypatch, {"guarantee": "dev", "effective": "workdir_separation_only"})
    w = world(tmp_path, checks=True)
    for rel, text in CP.PATCH.items():
        (w.workspace / rel).write_text(text, encoding="utf-8", newline="\n")
    w.e.check_run(invocation_token=w.worker, check_id="unit")
    return w


def submit(w, *, token=None, admitted=None):
    return w.e.submit(invocation_token=token or w.worker, kind="implementation_report", text=CP.submission(CP.REPORT),
                      admitted=admitted)


def evidence_of(w, name):
    return next(e for e in E.scan(w.e.aew_root, w.wid)[0] if e["id"] == name)


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_a_pre_submission_lead_message_blocks_ingest_and_all_read_only_answers(implementation, when):
    w = implementation
    message = w.send("A shutdown case needs to be checked.", when=when)["message"]["id"]
    report = submit(w)
    assert report["pending_lead_messages"] == 1
    evidence = evidence_of(w, report["evidence"])
    assert evidence["coordination_through"] == 1 and evidence["coordination_rev"] == w.rev()
    before = w.control_bytes()
    with pytest.raises(PendingLeadMessage) as refused:
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    assert refused.value.message.startswith(PendingLeadMessage.definition)
    assert refused.value.details["messages"] == [{"id": message, "when": when, "state": "undelivered"}]
    answer = w.e.guard_query("work.transition", w.wid, {"to": "REVIEW_PENDING"})
    assert answer["reason_codes"] == ["PENDING_LEAD_MESSAGE"]
    assert answer["blocking_conditions"][0]["details"] == refused.value.details
    assert w.e.work_show(w.wid)["report_finality"][0]["not_final"] == "PENDING_LEAD_MESSAGE"
    resumed = w.e.resume()
    assert resumed["report_finality"][0]["report"] == report["evidence"]
    assert message in resumed["next_actions"][0]
    assert w.control_bytes() == before


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_a_message_recorded_after_submission_stays_final_and_is_listed_if_ingest_loses_it(
        implementation, monkeypatch, when):
    import aew.operator

    w = implementation
    report = submit(w)
    assert report["pending_lead_messages"] == 0
    assert evidence_of(w, report["evidence"])["coordination_through"] == 0
    message = w.send("Follow up after the report.", when=when)["message"]["id"]
    expected = [{"id": message, "when": when, "state": "undelivered"}]
    assert w.e.guard_query("work.transition", w.wid, {"to": "REVIEW_PENDING"})[
        "post_report_message_pending"] == expected
    result = w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    assert result["post_report_message_pending"] == expected
    before = w.control_bytes(), w.thread_path().read_bytes()
    lost = w.e.resume()["lost_lead_messages"]["messages"]
    assert [record["id"] for record in lost] == [message]
    assert w.e.message_lost()["messages"] == lost
    assert before == (w.control_bytes(), w.thread_path().read_bytes())
    monkeypatch.setattr(aew.operator, "authorize", lambda *_args, **_kw: OPERATOR)
    w.e.lead_takeover(expect_rev=w.rev(), reason="resume the work", session_label="new")
    assert w.e.message_lost()["messages"] == lost
    assert before[1] == w.thread_path().read_bytes()


@pytest.mark.parametrize("field", ["coordination_through", "coordination_rev"])
def test_worker_cannot_supply_the_report_watermark(implementation, field):
    w = implementation
    with pytest.raises(ValidationFailed, match="recorded by the engine"):
        w.e.submit(invocation_token=w.worker, kind="implementation_report",
                   text=CP.submission({**CP.REPORT, field: 0}))


def test_replying_after_a_read_never_prevents_the_worker_obtaining_a_delivery_receipt(implementation):
    w = implementation
    mid = w.send()["message"]["id"]
    assert w.e.message_read_worker(invocation_token=w.worker)["messages"][0]["id"] == mid
    w.reply(mid)
    initial = submit(w)
    assert initial["pending_lead_messages"] == 1
    receipts = []
    w.e.message_deliver_wait(invocation_token=w.worker, after="", send=receipts.append)
    assert receipts[0]["messages"][0]["id"] == mid
    with pytest.raises(PendingLeadMessage) as refused:
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    assert refused.value.details["messages"][0]["state"] == "delivered_after_submission"
    replacement = submit(w)
    assert replacement["pending_lead_messages"] == 0
    assert w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")["ok"]


@pytest.mark.parametrize("resume,cap", [(True, 500), (False, 10_000)])
def test_the_lost_message_walk_never_examines_more_than_its_limit(implementation, monkeypatch, resume, cap):
    w = implementation
    scanned = []
    state = w.e.store.read() | {"revision": 12_000}
    now = utc_now()

    def newest(_root, _state):
        for revision in range(state["revision"], 0, -1):
            scanned.append(revision)
            yield {"revision": revision, "at": now, "refs": [], "events": []}

    monkeypatch.setattr(coordination.outbox, "newest_transitions", newest)
    result = w.e._coordination.message_lost(state, resume=resume)
    assert len(scanned) == result["walk_limit"] == cap
    assert result["messages"] == [] and result["note"]


@pytest.mark.parametrize("per_seal", [10, 11])
def test_resume_stops_reading_older_commits_after_twenty_lost_messages(implementation, monkeypatch, per_seal):
    w = implementation
    reader = w.e._coordination
    seen = []
    state = w.e.store.read() | {"revision": 12_000}
    now = utc_now()

    def newest(_root, _state):
        for offset in range(3):
            revision = state["revision"] - offset
            seen.append(revision)
            yield {"revision": revision, "at": now, "events": [],
                   "refs": [f"work/{w.wid}/coordination/INV-{offset + 1}.seal-{revision:012x}.yaml"]}

    monkeypatch.setattr(coordination.outbox, "newest_transitions", newest)
    monkeypatch.setattr(reader, "_pinned", lambda _s, path, *_ids: int(Path(path).stem.rsplit("-", 1)[1], 16))
    monkeypatch.setattr(reader, "_sealed", lambda _work, _inv, rev: ({"closed_rev": rev}, None))
    monkeypatch.setattr(reader, "_unit_lead_messages", lambda *_: [])
    monkeypatch.setattr(reader, "_lost_messages", lambda seal, _: [
        {"id": f"{seal['closed_rev']}-{i}"} for i in range(per_seal)])

    resumed = reader.message_lost(state, resume=True)
    assert seen == [12_000, 11_999]
    assert len(resumed["messages"]) == 20
    if per_seal == 10:
        assert "aew message lost" in resumed["note"]
    else:
        assert resumed["omitted"] == {"at_least": 2}
    seen.clear()
    listed = reader.message_lost(state)
    assert seen == [12_000, 11_999, 11_998]
    assert len(listed["messages"]) == 3 * per_seal and "note" not in listed


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_a_concurrent_record_and_submit_are_ordered_by_the_thread_watermark(implementation, when):
    w = implementation
    start = Barrier(2)

    def send():
        start.wait(timeout=15)
        return w.send(when=when)["message"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        sent = pool.submit(send)
        start.wait(timeout=15)
        reply = submit(w)
        message = sent.result(timeout=15)
    report = evidence_of(w, reply["evidence"])
    earlier = message["seq"] <= report["coordination_through"]
    assert reply["pending_lead_messages"] == int(earlier)
    reader = w.e.guard_query("work.transition", w.wid, {"to": "REVIEW_PENDING"})
    if earlier:
        assert reader["reason_codes"] == ["PENDING_LEAD_MESSAGE"]
    else:
        assert reader["post_report_message_pending"][0]["id"] == message["id"]


@pytest.mark.parametrize("record", [{"when": "turn-end"}, {"origin": "harness_send"}])
def test_a_pre_ms5b_schema_reports_new_delivery_fields_as_damaged(implementation, monkeypatch, record):
    import json

    from jsonschema import Draft202012Validator

    w = implementation
    if "origin" in record:
        with w.e.store.session() as session:
            w.e._coordination.record_harness_send(session.state, {"generation": 1}, w.inv, "Keep going",
                                                  when="next-step", idempotency_id=None)
    else:
        w.send(when=record["when"])
    path = Path(__file__).resolve().parents[1] / "fixtures/baseline/pre-ms5b-coordination-message.json"
    old_validator = Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))
    validate = coordination.validate

    def old_validate(name, value, **kwargs):
        if name == "coordination-message" and not old_validator.is_valid(value):
            raise ValidationFailed("the previous closed message schema refuses this record")
        return validate(name, value, **kwargs)

    monkeypatch.setattr(coordination, "validate", old_validate)
    with pytest.raises(ValidationFailed):
        coordination.read_thread(w.e.aew_root, w.wid, w.inv)
    thread, raw, verified = coordination.scan_thread(w.e.aew_root, w.wid, w.inv)
    assert raw and verified == 0 and thread.messages == []
