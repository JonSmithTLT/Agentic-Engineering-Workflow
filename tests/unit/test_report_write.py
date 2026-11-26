"""E157 Lead reports cross the typed door and stay outside workflow records."""

from __future__ import annotations

import json

import pytest
from aewflow import (
    PROPOSAL,
    allow_weaker_lead,
    assign,
    create_investigation,
    create_planned_ticket,
    dispatch,
    implement,
    sample_project,
    submit_record,
)

from aew.engine import reports
from aew.engine.api import Engine
from aew.engine.faults import InjectedFault
from aew.engine.store import ControlStore
from aew.errors import GateUnsatisfied, IntegrityError, NotFound, UsageError, ValidationFailed
from aew.knowledge import evidence
from aew.knowledge.records import read_record
from aew.surface import readable, run
from aew.surface.context import NORMAL, SurfaceContext
from aew.surface.validate import AdapterInputError

BODY = "A durable answer. The body never comes back automatically."


@pytest.fixture
def lab(tmp_path):
    p = sample_project(tmp_path)
    return p, Engine.discover(p.root)


def write(p, engine, *, context=None, **args):
    return run.run_tool(engine, context or SurfaceContext.outside_session(), "report_write",
                        {"expect_rev": p.rev(), "title": "An answer", "body": BODY, **args}, token=p.token)


def test_report_write_assigns_its_id_and_path_and_commits_no_work_transition(lab):
    p, engine = lab
    before = engine.store.current()
    result = write(p, engine)
    assert result["ok"] and result["stage_intent_id"] is None
    assert [step["primitive"] for step in result["completed_steps"]] == ["report.write"]
    report_id = result["result"]["id"]
    after = engine.store.current()
    assert after["revision"] == before["revision"] + 1
    for key in ("work", "lead", "invocations", "next_action"):
        assert after.get(key) == before.get(key), key
    [path] = after["last_transition"]["refs"]
    assert path == f"reports/{report_id}.json"
    record = json.loads((engine.aew_root / path).read_text(encoding="utf-8"))
    assert record["id"] == report_id and record["kind"] == "lead_report"
    assert record["generation"] == after["lead"]["generation"]


@pytest.mark.parametrize("input_name", ["id", "path", "session_id"])
def test_report_write_refuses_lead_chosen_identity_or_storage(lab, input_name):
    p, engine = lab
    rev = p.rev()
    with pytest.raises(AdapterInputError) as error:
        write(p, engine, **{input_name: "chosen"})
    assert error.value.code == "INVALID_ARGUMENTS"
    assert input_name in str(error.value.to_dict()) and p.rev() == rev
    assert not (engine.aew_root / "reports").exists()


def test_report_body_is_shown_only_on_explicit_read_and_terminal_controls_are_escaped(lab):
    p, engine = lab
    body = BODY + "\n\x1b[31mred\x1b[0m\n\x9b2J\n<script>x()</script>\n![remote](https://example.invalid/x)"
    result = write(p, engine, body=body)
    assert result["ok"]
    payload = result["result"]
    report_id = payload["id"]
    summary = {"label": reports.LABEL, "items": [{"id": report_id, "title": "An answer"}]}
    assert result["projection"]["reports"] == summary
    assert engine.resume()["reports"] == summary
    assert BODY not in json.dumps(result) and BODY not in json.dumps(engine.resume())
    assert payload["show"] == f"aew report show {report_id}"
    view = engine.report_show(report_id)
    assert view["body"] == body and view["format"] == "text"
    shown = reports.render(view)
    assert reports.LABEL in shown and BODY in shown
    assert "\\u001b[31m" in shown and "\\u009b2J" in shown
    assert "\x1b" not in shown and "\x9b" not in shown


def test_report_size_refusal_names_the_byte_limit_and_commits_nothing(lab):
    p, engine = lab
    title = "An answer"
    exact = "é" * ((reports.MAX_BYTES - len(title)) // 2) + "x" * ((reports.MAX_BYTES - len(title)) % 2)
    assert write(p, engine, title=title, body=exact)["ok"]
    rev = p.rev()
    refused = write(p, engine, title=title, body=exact + "x")
    assert refused["stopped"]["error"]["code"] == "USAGE"
    assert refused["stopped"]["error"]["details"] == {
        "reason": "report_size", "limit": reports.MAX_BYTES, "size": reports.MAX_BYTES + 1}
    assert refused["completed_steps"] == [] and p.rev() == rev


def test_resume_bounds_recent_titles_without_reading_report_files_or_duplicating_the_list(lab, monkeypatch):
    p, engine = lab
    older = write(p, engine)["result"]["id"]
    generation = engine.store.current()["lead"]["generation"]
    context = SurfaceContext({"holds": True, "generation": generation, "session_id": "LS-0123456789ab"}, generation,
                             profile=NORMAL, ingress="mcp")
    title = "😀" * reports.MAX_TITLE
    newest = []
    for _ in range(reports.MAX_PER_SESSION):
        result = write(p, engine, context=context, title=title)
        assert result["ok"], result["stopped"]
        newest.insert(0, result["result"]["id"])
    assert [entry["id"] for entry in engine.store.read_committed()[reports.RECENT_KEY]] == newest

    def no_report_read(*args):
        pytest.fail("an automatic view opened a report file")

    with monkeypatch.context() as patch:
        patch.setattr(reports, "read", no_report_read)
        resumed = run.run_tool(engine, context, "resume", {})
        summary = resumed["projection"]["reports"]
        assert "reports" not in resumed["result"] and engine.resume()["reports"] == summary
        assert 0 < len(summary["items"]) < len(newest)
        assert [item["id"] for item in summary["items"]] == newest[:len(summary["items"])]
        assert all(item["title"] == title for item in summary["items"])
        assert len(json.dumps(summary).encode("ascii")) <= reports.SUMMARY_BYTES
        assert len(readable.render(resumed).encode("utf-8")) < readable.CUT_BYTES
    assert engine.report_show(older)["body"] == BODY


def test_the_backend_report_view_checks_the_supplied_snapshot_and_reads_plain_text(lab, monkeypatch):
    p, engine = lab
    before = p.rev()
    text = "<img src='https://example.invalid/report'>\n![remote](https://example.invalid/report)"
    result = write(p, engine, body=text)
    report_id = result["result"]["id"]
    current = p.rev()

    def forbid_lock(*args, **kwargs):
        pytest.fail("the report view tried to take the control lock")

    monkeypatch.setattr(engine.store, "control_lock", forbid_lock)
    with pytest.raises(NotFound) as old:
        reports.read_view(engine.aew_root, report_id, before)
    assert old.value.details["reason"] == "report_not_found"
    with pytest.raises(NotFound) as path:
        reports.read_view(engine.aew_root, f"../reports/{report_id}.json", current)
    assert path.value.details["reason"] == "report_not_found"
    assert reports.read_view(engine.aew_root, report_id, current) == {
        "id": report_id, "title": "An answer", "body": text, "format": "text", "label": reports.LABEL}


def test_the_read_only_view_reports_a_pending_apply_and_the_status_command_recovers_it(lab, monkeypatch):
    p, engine = lab
    revision = p.rev()
    with monkeypatch.context() as patch:
        patch.setenv("AEW_FAULT", "txn.after_replace")
        patch.setenv("AEW_FAULT_MODE", "raise")
        with pytest.raises(InjectedFault):
            engine.report_write(token=p.token, expect_rev=revision, title="An answer", body=BODY)
    state = engine.store.read_committed()
    assert state["revision"] == revision + 1
    [entry] = state[reports.RECENT_KEY]
    report_id = entry["id"]
    assert not (engine.aew_root / "reports" / f"{report_id}.json").exists()

    def forbid_lock(*args, **kwargs):
        pytest.fail("the report view tried to take the control lock")

    with monkeypatch.context() as patch:
        patch.setattr(ControlStore, "control_lock", forbid_lock)
        with pytest.raises(IntegrityError) as pending:
            reports.read_view(engine.aew_root, report_id, state["revision"])
    assert pending.value.details["reason"] == "report_pending_apply"
    assert "aew status" in pending.value.message
    p.ok("status", "--json")
    assert reports.read_view(engine.aew_root, report_id, state["revision"])["body"] == BODY


def test_report_count_refusal_names_the_session_limit_and_a_new_session_has_its_own(lab, monkeypatch):
    p, engine = lab
    monkeypatch.setattr(reports, "MAX_PER_SESSION", 2)
    generation = engine.store.current()["lead"]["generation"]

    def session(name):
        return SurfaceContext({"holds": True, "generation": generation, "session_id": name}, generation,
                              profile=NORMAL, ingress="mcp")

    first, second = session("LS-0123456789ab"), session("LS-abcdef012345")
    assert write(p, engine, context=first)["ok"]
    assert write(p, engine, context=first)["ok"]
    rev = p.rev()
    refused = write(p, engine, context=first)
    assert refused["stopped"]["error"]["code"] == "USAGE"
    assert refused["stopped"]["error"]["details"] == {"reason": "report_count", "limit": 2}
    assert refused["completed_steps"] == [] and p.rev() == rev
    assert write(p, engine, context=second)["ok"]


def test_the_report_and_its_id_are_refused_as_workflow_evidence(lab, tmp_path):
    p, engine = lab
    ticket = create_investigation(p, tmp_path)
    dispatch(p, ticket)
    report_id = write(p, engine)["result"]["id"]
    rev = p.rev()
    path = engine.aew_root / engine.store.current()["last_transition"]["refs"][0]
    with pytest.raises(ValidationFailed):
        evidence.read(path)
    assert evidence.scan(engine.aew_root, ticket) == ([], [])
    with pytest.raises(NotFound, match=report_id):
        engine.evidence_ingest(token=p.token, expect_rev=rev, work_id=ticket, evidence_id=report_id)
    assert p.rev() == rev


def test_a_report_cannot_be_adopted_as_a_plan_or_acknowledged_as_a_work_input(lab, tmp_path):
    p, engine = lab
    source = create_investigation(p, tmp_path, card="planner")
    planner, _ = dispatch(p, source)
    proposal = submit_record(planner, "plan_proposal", PROPOSAL)["evidence"]
    p.lead("evidence", "ingest", source, "--evidence", proposal)
    p.lead("work", "accept", source)
    target = create_planned_ticket(p, tmp_path, title="A separate Ticket")
    report_id = write(p, engine)["result"]["id"]
    rev = p.rev()
    report_path = engine.aew_root / engine.store.current()["last_transition"]["refs"][0]
    with pytest.raises(ValidationFailed):
        read_record(report_path, "plan")
    with pytest.raises(UsageError, match=report_id):
        engine.plan_adopt(token=p.token, expect_rev=rev, work_id=target, evidence_id=report_id, source=source,
                          no_assurance=True)
    with pytest.raises(UsageError, match=report_id):
        engine.work_acknowledge_input(token=p.token, expect_rev=rev, work_id=target, evidence_id=report_id,
                                      source=source, reason="try the report reference")
    assert p.rev() == rev


def test_a_report_is_refused_by_review_verification_and_gate_resolvers(lab, tmp_path):
    p, engine = lab
    allow_weaker_lead(p)  # containment is independent of the evidence and gate resolvers under test
    target = create_planned_ticket(p, tmp_path, cls=1)
    role = assign(p, target)
    implement(role)
    p.lead("work", "transition", target, "--to", "REVIEW_PENDING")
    report_id = write(p, engine)["result"]["id"]
    rev = p.rev()
    for ingest in (engine.review_ingest, engine.verify_ingest):
        with pytest.raises(NotFound, match=report_id):
            ingest(token=p.token, expect_rev=rev, work_id=target, evidence_id=report_id)
    with pytest.raises(GateUnsatisfied, match=report_id):
        engine.waive(token=p.token, expect_rev=rev, work_id=target, reason="try this report", gate=report_id)
    assert report_id not in engine.gate_show(target)["gates"] and p.rev() == rev


def test_a_report_never_enters_a_worker_pack_or_derived_knowledge(lab, tmp_path):
    p, engine = lab
    work = create_investigation(p, tmp_path)
    report_id = write(p, engine)["result"]["id"]
    _, assigned = dispatch(p, work)
    pack = json.dumps(engine.context_pack(assigned["invocation"]))
    assert report_id not in pack and BODY not in pack
    derived = json.dumps(engine.resume()["derived_knowledge"])
    assert report_id not in derived and BODY not in derived


def test_work_show_preserves_the_direct_answer_and_explain_mode(lab, tmp_path):
    p, engine = lab
    work = create_planned_ticket(p, tmp_path)
    ctx = SurfaceContext.outside_session(ingress="direct")
    plain = run.run_tool(engine, ctx, "work_show", {"work_id": work})
    explain = run.run_tool(engine, ctx, "work_show", {"work_id": work, "explain": True})
    missing = run.run_tool(engine, ctx, "work_show", {"work_id": "T-9999", "explain": True})
    assert plain["result"] == engine.work_show(work)
    assert explain["result"] == engine.dispatch_explain(work)
    assert missing["stopped"]["error"]["code"] == "NOT_FOUND"
    assert plain["revision"] == explain["revision"] == missing["revision"] == p.rev()
    with pytest.raises(AdapterInputError, match="work_show: name a work_id"):
        run.run_tool(engine, ctx, "work_show", {"explain": True})
