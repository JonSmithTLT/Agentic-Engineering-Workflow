"""MS5b report finality at the control transaction and its read-only advice."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from aewflow import (
    Role,
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    implement,
    parent_review,
    parent_verify,
    plan_unit,
    review,
    sample_project,
    stand_in_containment,
    submit_record,
    to_commit_ready,
    verify,
)
from test_coordination_store import CP, OPERATOR, set_messaging, world

from aew.engine import coordination_ops as coordination
from aew.engine.api import Engine
from aew.errors import PendingLeadMessage, ValidationFailed
from aew.harness import contract, runlog
from aew.knowledge import evidence as E
from aew.knowledge.manifest import DEFAULT_GATES
from aew.policy import execution as X
from aew.surface import run as surface
from aew.surface.context import SurfaceContext
from aew.util import dump_yaml, load_yaml, utc_now


@pytest.fixture
def implementation(tmp_path, monkeypatch):
    stand_in_containment(monkeypatch, {"guarantee": "dev", "effective": "workdir_separation_only"})
    w = world(tmp_path, checks=True, model="fakeprov/fake-model")
    for rel, text in CP.PATCH.items():
        (w.workspace / rel).write_text(text, encoding="utf-8", newline="\n")
    w.e.check_run(invocation_token=w.worker, check_id="unit")
    return w


def submit(w, *, token=None, admitted=None, continued=None):
    return w.e.submit(invocation_token=token or w.worker, kind="implementation_report", text=CP.submission(CP.REPORT),
                      admitted=admitted, continued=continued)


def evidence_of(w, name):
    return next(e for e in E.scan(w.e.aew_root, w.wid)[0] if e["id"] == name)


def _capture_launch_credentials(engine, monkeypatch):
    credentials = {}

    def spawn(_invocation, run, credential):
        credentials[run] = credential
        return {"run": run, "status": contract.RUNNING}

    monkeypatch.setattr(engine._harness, "_spawn_run", spawn)
    return credentials


_TRANSITIONS = {"implementation-review": "REVIEW_PENDING", "implementation-verify": "VERIFY_PENDING",
                "implementation-commit": "COMMIT_READY"}
_INGESTS = {"ticket-review": "review.ingest", "ticket-verify": "verify.ingest",
            "integration-verify": "verify.ingest.integration", "integration-verify-fail": "verify.ingest.integration",
            "executor-record": "evidence.ingest",
            "observation-review": "review.ingest", "observation-verify": "verify.ingest",
            "parent-review": "review.ingest", "parent-verify": "verify.ingest"}


def _prepare_report_case(p, tmp_path, route: str) -> tuple[str, Callable[[], Any]]:
    if route in ("parent-review", "parent-verify"):
        story = create_unit(p, "story", "Acceptance")
        plan_unit(p, tmp_path, story)
        complete_investigation(p, create_investigation(p, tmp_path, parent=story))
        if route == "parent-review":
            return story, lambda: parent_review(p, story)
        p.lead("review", "ingest", story, "--evidence", parent_review(p, story))
        return story, lambda: parent_verify(p, story)
    if route in ("executor-record", "observation-review", "observation-verify"):
        wid = create_investigation(p, tmp_path)
        role, _ = dispatch(p, wid)
        if route == "executor-record":
            return wid, lambda: submit_record(role, "discovery_record")
        p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
        review_route = route == "observation-review"
        p.lead("work", "transition", wid, "--to", "REVIEW_PENDING" if review_route else "VERIFY_PENDING")
        actor = p.lead("invoke", "create", wid, "--role", "reviewer" if review_route else "verifier")
        reporter = Role(p, actor["invocation_token"], Path(actor["observation"]["path"]))
        if review_route:
            return wid, lambda: reporter.submit("review", CP.REVIEW)

        def observation_verify():
            check = reporter.check("unit")["evidence"]
            claims = [{"type": kind, "claim": "the observation supports the claim", "result": "pass",
                       "checks": [check]} for kind in ("goal_backwards", "contract")]
            return reporter.submit("verification", {"claim": "verified", "verification": {"claims": claims}})

        return wid, observation_verify
    if route.startswith("integration-verify"):
        wid, _ = to_commit_ready(p, tmp_path)
        p.lead("integrate", "prepare", wid)
        goal_result = "fail" if route.endswith("fail") else "pass"
        return wid, lambda: verify(p, wid, scope="integration", goal_result=goal_result)
    wid = create_planned_ticket(p, tmp_path)
    role = assign(p, wid)
    if route in _TRANSITIONS:
        return wid, lambda: implement(role)
    implement(role)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    if route == "ticket-review":
        return wid, lambda: review(p, wid)
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    return wid, lambda: verify(p, wid)


@pytest.mark.parametrize("route", [*_TRANSITIONS, *_INGESTS])
@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_every_result_writer_refuses_pending_messages_and_pins_only_the_replacement(tmp_path, monkeypatch, route,
                                                                                    when):
    gates = deepcopy(DEFAULT_GATES)
    if route in ("implementation-verify", "implementation-commit"):
        drop = ("review_", "verification_") if route == "implementation-commit" else ("review_",)
        gates["risk_paths"]["1"] = [gate for gate in gates["risk_paths"]["1"] if not gate.startswith(drop)]
    if route == "observation-review":
        gates["non_mutating_paths"]["1"].append("review_r1")
    if route == "observation-verify":
        gates["non_mutating_paths"]["1"].extend(("verification_goal_backwards", "verification_contract"))
    p = sample_project(tmp_path, gates=gates)
    execution = p.root / ".aew" / X.REL_PATH
    policy = load_yaml(execution.read_text(encoding="utf-8"))
    policy["configured"] = True
    policy["profiles"] = {"standard": {"model": "fakeprov/fake-model"}}
    policy["routing"]["default"] = "standard"
    execution.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    p.pin_policy()
    engine = Engine.discover(p.root)
    stand_in_containment(monkeypatch, {"guarantee": "dev", "effective": "workdir_separation_only"})
    monkeypatch.setattr(Role, "check", lambda role, key: engine.check_run(invocation_token=role.token, check_id=key))
    wid, report = _prepare_report_case(p, tmp_path, route)
    captured: dict[str, Any] = {}

    def submit_after_message(role, kind, meta, body="", *, expect_ok=True):
        assert expect_ok
        inv = engine.invocation_whoami(invocation_token=role.token)["invocation"]
        message = engine.message_record_lead(token=p.token, to=inv, body="Follow-up", when=when)
        text = CP.submission(meta) + body
        evidence = engine.submit(invocation_token=role.token, kind=kind, text=text)
        captured.update(inv=inv, message=message["message"]["id"], kind=kind, text=text, evidence=evidence)
        return evidence

    monkeypatch.setattr(Role, "submit", submit_after_message)
    report()
    original = captured["evidence"]
    assert original["pending_lead_messages"] == 1
    report_path = Path(original["path"])
    old_bytes = report_path.read_bytes()
    primitive = _INGESTS.get(route, "work.transition")

    def arguments(evidence):
        return {"to": _TRANSITIONS[route]} if route in _TRANSITIONS else {"evidence": evidence}

    def ingest(evidence):
        args: dict[str, Any] = {"token": p.token, "work_id": wid}
        if route in _TRANSITIONS:
            prior = engine.prior_value("work_transition", wid)
            return engine.work_transition(**args, to=_TRANSITIONS[route], prior_value=prior)
        if primitive.startswith("verify.ingest"):
            return engine.verify_ingest(**args, evidence_id=evidence,
                                        scope="integration" if primitive == "verify.ingest.integration" else None)
        if primitive == "review.ingest":
            return engine.review_ingest(**args, evidence_id=evidence)
        return engine.evidence_ingest(**args, evidence_id=evidence)

    state = engine.store.read_committed()
    prediction = engine.guard_query(primitive, wid, arguments(original["evidence"]))
    with pytest.raises(PendingLeadMessage) as refused:
        ingest(original["evidence"])
    assert prediction["reason_codes"] == ["PENDING_LEAD_MESSAGE"]
    assert prediction["blocking_conditions"][0]["details"] == refused.value.details
    stage = _stage_for_route(route, state["work"][wid], original["evidence"])
    if stage:
        name, stage_arguments = stage
        explained = surface.run_tool(engine, SurfaceContext.outside_session(), "explain",
                                     {"stage": name, "work_id": wid, "arguments": stage_arguments})["result"]
        assert explained["availability"] == "BLOCKED"
        assert "PENDING_LEAD_MESSAGE" in explained["reason_codes"]
    assert engine.store.read_committed() == state and report_path.read_bytes() == old_bytes

    creds = _capture_launch_credentials(engine, monkeypatch)
    invocation = captured["inv"]
    run = engine.harness_launch(token=p.token, invocation=invocation,
                                prior_value=engine.prior_value("harness_launch", invocation))["run"]
    credential = creds[run]
    posted = engine.message_next_post(credential=credential, run=run, permit=lambda: True)
    assert posted["message"]["id"] == captured["message"]
    engine.message_confirm_delivery(credential=credential, run=run, ids=[captured["message"]],
                                    via="live", transport_ref="confirmed-prompt")
    replacement = engine.submit(invocation_token=credential, kind=captured["kind"], text=captured["text"])
    new_id = replacement["evidence"]
    assert replacement["pending_lead_messages"] == 0 and new_id != original["evidence"]
    assert engine.guard_query(primitive, wid, arguments(new_id))["availability"] == "AVAILABLE"
    assert ingest(new_id)["ok"]
    assert report_path.read_bytes() == old_bytes
    if route == "integration-verify-fail":
        assert engine.store.read_committed()["work"][wid]["state"] == "VERIFICATION_FAILED"
    if route == "executor-record":
        observed = engine.approval_subject(wid, "work.accept")
        assert observed is not None and observed["subject"]["record"]["id"] == new_id
        assert engine.work_accept(token=p.token, work_id=wid, binding=observed["digest"])["ok"]


def _stage_for_route(route: str, unit: dict[str, Any], evidence: str) -> tuple[str, dict[str, Any]] | None:
    if route == "implementation-review":
        return "ticket_request_review", {"prior_value": unit["state"]}
    if route == "ticket-review":
        return "ticket_request_verification", {"review_evidence": evidence}
    if route == "ticket-verify":
        return "ticket_prepare", {"verification_evidence": evidence}
    if route == "integration-verify":
        return "integration_publish", {"prepared_candidate": unit["integration"]["candidate"],
                                       "verification_evidence": evidence}
    return None


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
    w.e.lead_takeover(reason="resume the work", session_label="new")
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


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
@pytest.mark.parametrize("delivered", [False, True], ids=["unconfirmed", "delivered-after-report"])
def test_takeover_releases_only_an_unconfirmed_post(implementation, monkeypatch, when, delivered):
    import aew.operator

    w = implementation
    keys = _capture_launch_credentials(w.e, monkeypatch)
    run = w.lead("harness_launch", invocation=w.inv)["run"]
    credential = keys[run]
    mid = w.send(when=when)["message"]["id"]
    posted = w.e.message_next_post(credential=credential, run=run, permit=lambda: True)
    assert posted["message"]["id"] == mid
    first = submit(w, token=credential)
    assert first["pending_lead_messages"] == 1
    if delivered:
        w.e.message_confirm_delivery(credential=credential, run=run, ids=[mid], via="live",
                                     transport_ref="admitted-transport")
    monkeypatch.setattr(aew.operator, "authorize", lambda *_args, **_kwargs: OPERATOR)
    takeover = w.e.lead_takeover(reason="take over the disconnected seat", session_label="next")
    w.token = takeover["token"]
    assert w.inv in takeover["interrupted_invocations"]
    w.lead("work_reconcile", work_id=w.wid, to="RUNNING", reason="inspected the report and workspace")
    before = w.control_bytes()
    if delivered:
        with pytest.raises(PendingLeadMessage) as held:
            w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
        assert held.value.details["report"] == first["evidence"]
        assert held.value.details["messages"] == [{"id": mid, "when": when, "state": "delivered_after_submission"}]
        assert w.control_bytes() == before
    else:
        assert w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")["ok"]


def test_pending_report_recovery_restores_the_disabled_delivery_lane_before_resubmission(implementation, monkeypatch):
    w = implementation
    keys = _capture_launch_credentials(w.e, monkeypatch)
    original = w.lead("harness_launch", invocation=w.inv)["run"]
    mid = w.send()["message"]["id"]
    first = submit(w, token=keys[original])
    set_messaging(w.root, "disabled")
    w.lead("manifest_adopt", reason="temporarily turn delivery off", authorization=OPERATOR)
    runlog.write_record(runlog.run_dir(w.e.aew_root, original), {"status": contract.ENDED_WITH_EVIDENCE})

    with pytest.raises(PendingLeadMessage) as held:
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    assert held.value.details["report"] == first["evidence"]
    next_step = held.value.details["next"]
    assert f"operator re-enable coordination messaging. Relaunch {w.inv}" in next_step and mid in next_step
    assert w.e._coordination.continuation_messages(w.e.store.read(), w.inv)[0] == []

    set_messaging(w.root, "enabled")
    w.lead("manifest_adopt", reason="resume message delivery", authorization=OPERATOR)
    successor = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    continuation = w.e.harness_contract(w.e.store.read(), w.inv, successor).continuation
    assert continuation["messages"] == [mid]
    last = submit(w, token=keys[successor], continued=("confirmed-launch", continuation["messages"]))
    assert last["pending_lead_messages"] == 0
    assert w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")["ok"]


def test_an_answered_message_delivered_after_a_report_requests_a_new_report_without_repeating_delivery(
        implementation, monkeypatch):
    w = implementation
    keys = _capture_launch_credentials(w.e, monkeypatch)
    original = w.lead("harness_launch", invocation=w.inv)["run"]
    mid = w.send()["message"]["id"]
    first = submit(w, token=keys[original])
    w.e.message_deliver_wait(invocation_token=keys[original], after="", send=lambda _: None)
    w.reply(mid, invocation_token=keys[original])
    runlog.write_record(runlog.run_dir(w.e.aew_root, original), {"status": contract.ENDED_WITH_EVIDENCE})
    with pytest.raises(PendingLeadMessage) as held:
        w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    assert held.value.details["report"] == first["evidence"]
    assert f"Relaunch {w.inv}." in held.value.details["next"]
    assert f"accounting for the delivered messages {mid}" in held.value.details["next"]
    successor = w.lead("harness_launch", invocation=w.inv, replace=True)["run"]
    continuation = w.e.harness_contract(w.e.store.read(), w.inv, successor).continuation
    assert not continuation.get("messages")
    assert submit(w, token=keys[successor])["pending_lead_messages"] == 0
    assert w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")["ok"]


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_a_legacy_report_uses_the_threads_first_timestamp_only_without_its_own_watermark(implementation, monkeypatch,
                                                                                        offset):
    from aew.engine import evidence_ops

    w = implementation
    first_message_at = "2026-11-24T11:00:01Z"
    monkeypatch.setattr(coordination, "utc_now", lambda: first_message_at)
    monkeypatch.setattr(evidence_ops, "utc_now", lambda: f"2026-11-24T11:00:0{1 + offset}Z")
    with monkeypatch.context() as legacy:
        legacy.setattr(w.e._coordination, "report_snapshot", lambda *_: None)
        submitted = submit(w)
    old = evidence_of(w, submitted["evidence"])
    assert "coordination_through" not in old
    assert w.e._coordination.report_finality(w.e.store.read(), old) == (None, [])
    mid = w.send()["message"]["id"]
    error, advisory = w.e._coordination.report_finality(w.e.store.read(), old)
    if offset < 0:
        assert error is None and advisory == [{"id": mid, "when": "next-step", "state": "undelivered"}]
    else:
        assert error is not None and error.details["messages"][0]["id"] == mid and advisory == []


@pytest.mark.parametrize("messaging", [None, "disabled"])
def test_a_never_enabled_report_keeps_the_same_bytes_as_before_finality(tmp_path, monkeypatch, messaging):
    from aew.engine import evidence_ops

    w = world(tmp_path, messaging=messaging)
    monkeypatch.setattr(evidence_ops, "utc_now", lambda: "2026-11-24T11:00:00Z")
    before = w.control_bytes()
    actual = submit(w)
    path = Path(actual["path"])
    record = path.read_bytes()
    path.unlink()
    with monkeypatch.context() as legacy:
        legacy.setattr(w.e._coordination, "report_snapshot", lambda *_: None)
        previous = submit(w)
    assert actual == previous and Path(previous["path"]).read_bytes() == record
    assert w.control_bytes() == before and not w.thread_path().exists()


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
        assert "aew message lost" in resumed["note"]
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
