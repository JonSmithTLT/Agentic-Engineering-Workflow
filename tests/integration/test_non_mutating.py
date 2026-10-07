"""Non-mutating Tickets through the CLI (ADR-0008): executor pinning, read-only observation, authority
denials, the output-kind contract, record review and acceptance, concurrency with mutating work."""

from __future__ import annotations

from pathlib import Path

from aewflow import (
    PROPOSAL,
    Role,
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    dispatch,
    integrate,
    sample_project,
    submit_record,
    to_commit_ready,
)
from conftest import git
from invariants import assert_control_invariants

from aew.util import dump_yaml, load_yaml


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def refused(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def test_dispatch_pins_the_executor_and_its_output_kind(tmp_path):
    """Operator review #5: an unstaffed Ticket becomes an investigation deliberately and visibly."""
    p = sample_project(tmp_path)
    default = create_investigation(p, tmp_path, title="Unstaffed")
    research = create_investigation(p, tmp_path, title="Library capability", card="researcher")
    _, out = dispatch(p, default)
    assert out["execution"]["archetype"] == "investigator"
    assert out["execution"]["expected_kind"] == "discovery_record"
    assert out["execution"]["selected_by"] == "workflow-default"
    role, out = dispatch(p, research)
    assert out["execution"]["expected_kind"] == "research_record" and out["execution"]["selected_by"] == "lead"
    wrong = submit_record(role, "discovery_record", expect_ok=False)  # a researcher cannot write a discovery
    assert wrong.error["code"] == "PERMISSION_DENIED"
    rec = submit_record(role, "research_record")["evidence"]
    p.lead("evidence", "ingest", research, "--evidence", rec)
    p.lead("work", "accept", research)
    completion = (p.root / ".aew" / show(p, research)["completion_record"]).read_text(encoding="utf-8")
    assert "expected_kind: research_record" in completion and "selected_by: lead" in completion
    assert_control_invariants(p)


def test_changing_the_executor_between_attempts_pins_a_new_contract(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, _ = dispatch(p, wid)
    out = p.lead("work", "redispatch", wid, "--card", "planner", "--reason", "this needs a plan, not a survey")
    assert out["execution"]["attempt"] == 2 and out["execution"]["expected_kind"] == "plan_proposal"
    planner = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    rec = submit_record(planner, "plan_proposal", PROPOSAL)["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    assert p.ok("gate", "show", wid)["gates"]["execute_record"]["status"] == "CURRENT"
    assert_control_invariants(p)


def test_read_only_observation_runs_beside_mutating_work(tmp_path):
    """WC §8.1: read-only work may run while the serial mutation slot is busy, and it observes the
    authoritative source, never another Ticket's unintegrated workspace."""
    p = sample_project(tmp_path)
    mutating = create_planned_ticket(p, tmp_path)
    impl = assign(p, mutating)
    (impl.workspace / "calc/core.py").write_text("def add(a, b):\n    return b + a\n# in flight\n", encoding="utf-8",
                                                  newline="\n")
    first = create_investigation(p, tmp_path, title="One")
    second = create_investigation(p, tmp_path, title="Two")
    r1, o1 = dispatch(p, first)
    r2, o2 = dispatch(p, second)
    assert len({o1["observation"]["path"], o2["observation"]["path"], str(impl.workspace)}) == 3
    authoritative = git("rev-parse", "refs/heads/main", cwd=p.root)
    assert o1["observation"]["commit"] == o2["observation"]["commit"] == authoritative
    assert "in flight" not in (r1.workspace / "calc/core.py").read_text(encoding="utf-8")
    assert show(p, mutating)["workspace"]["status"] == "active"  # the mutation slot is untouched
    for role, wid in ((r1, first), (r2, second)):
        p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
        p.lead("work", "accept", wid)
    assert [show(p, w)["state"] for w in (first, second)] == ["DONE", "DONE"]
    assert show(p, first)["workspace"] is None and show(p, first)["integration"] is None
    assert_control_invariants(p)


def test_read_only_roles_cannot_act_beyond_their_archetype(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, out = dispatch(p, wid)
    impl_report = role.submit("implementation_report", {"claim": "x", "result": "pass",
                                                          "implementation": {"files_changed": []}}, expect_ok=False)
    assert impl_report.error["code"] == "PERMISSION_DENIED"
    as_review = role.submit("review", {"claim": "x", "review": {"independence": "R1", "disposition": "pass",
                                                               "findings": []}}, expect_ok=False)
    assert as_review.error["code"] == "PERMISSION_DENIED"
    as_lead = p.aew("work", "transition", wid, "--to", "REVIEW_PENDING", "--token", out["invocation_token"],
                    "--expect-rev", str(p.rev()))
    assert as_lead.error["code"] == "PERMISSION_DENIED"  # an invocation credential never drives control state
    assert refused(p, "work", "assign", wid)["code"] == "ILLEGAL_TRANSITION"
    assert refused(p, "integrate", "prepare", wid)["code"] == "ILLEGAL_TRANSITION"
    assert refused(p, "work", "staff", wid, "--execute", "engineer")["code"] == "USAGE"  # never an implementer
    # A read-only executor that changes its observation cannot submit (source mutation is not its authority).
    (role.workspace / "calc/core.py").write_text("tampered\n", encoding="utf-8", newline="\n")
    mutated = submit_record(role, "discovery_record", expect_ok=False)
    assert mutated.error["code"] == "OBSERVATION_MUTATED" and "calc/core.py" in mutated.error["details"]["changed"]
    assert_control_invariants(p)


def test_a_record_under_review_binds_the_review_to_it(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path, cls=2)
    p.lead("work", "staff", wid, "--review", "code_reviewer")
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    assert refused(p, "work", "accept", wid)["code"] == "GATE_UNSATISFIED"  # the planned review is required
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    rv = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    assert rv["subject"]["id"] == rec
    reviewer = Role(p, rv["invocation_token"], Path(rv["observation"]["path"]))
    ev = reviewer.submit("review", {"claim": "facts are supported", "review": {
        "independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}})["evidence"]
    p.lead("review", "ingest", wid, "--evidence", ev)
    assert show(p, wid)["state"] == "REVIEW_PASSED"
    p.lead("work", "accept", wid)
    assert show(p, wid)["state"] == "DONE"
    assert refused(p, "work", "transition", wid, "--to", "COMMIT_READY")["code"] == "ILLEGAL_TRANSITION"
    assert_control_invariants(p)


def test_external_research_never_goes_stale_on_source_changes(tmp_path):
    p = sample_project(tmp_path)
    research = create_investigation(p, tmp_path, title="pytest capability", card="researcher")
    complete_investigation(p, research, kind="research_record")
    wid = create_planned_ticket(p, tmp_path, extra=("--depends-on", f"{research}:evidence"))
    other, _ = to_commit_ready(p, tmp_path, title="Unrelated change")  # changes calc/ on integration
    integrate(p, other)
    out = p.lead("work", "assign", wid)
    inputs = p.ok("invoke", "show", out["invocation"])["inputs"]
    assert [(i["kind"], i["freshness"], i["basis"]) for i in inputs] == [("research_record", "UNKNOWN", "external")]
    assert_control_invariants(p)


def test_non_mutating_concurrency_policy_is_enforced_at_dispatch(tmp_path):
    p = sample_project(tmp_path, gates=None)
    gates_path = p.root / ".aew/policy/gates.yaml"
    gates = load_yaml(gates_path.read_text(encoding="utf-8"), source="gates")
    gates["non_mutating_concurrency"] = 1
    gates_path.write_text(dump_yaml(gates), encoding="utf-8", newline="\n")
    p.pin_policy()
    a = create_investigation(p, tmp_path, title="A")
    b = create_investigation(p, tmp_path, title="B")
    dispatch(p, a)
    assert refused(p, "work", "dispatch", b)["code"] == "CONCURRENCY_LIMIT"


def test_role_plan_rules_apply_to_the_execute_slot(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    p.as_operator("work_staff", work_id=wid, execute=["researcher"], selected_by="operator", pin=True)
    denied = refused(p, "work", "dispatch", wid, "--card", "investigator")
    assert denied["code"] == "PERMISSION_DENIED" and "pinned" in denied["message"]
    p.lead("work", "staff", wid, "--forbid", "planner")
    _, out = dispatch(p, wid)
    assert out["execution"]["card"]["id"] == "researcher" and out["execution"]["selected_by"] == "operator"
    assert_control_invariants(p)
