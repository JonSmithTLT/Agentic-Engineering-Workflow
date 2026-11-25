"""The plan assessor's entrypoint (E160 slice 2a; SYS-43): `aew plan assess <W>` dispatches a reviewer invocation at
scope ``plan_assessment`` for a Ticket's or a parent's accepted plan revision, pinned to that revision, with its own
read-only observation and a pack of its own. Only that dispatch may submit a plan assessment, a code reviewer never;
and once an assessment of the revision counts (the first one recorded, ruling 4 as built), no further assessor of that
revision is dispatched. The Lead session's route to the command is its typed tool (slice 2b): here the command runs
with the Lead credential."""

from __future__ import annotations

from pathlib import Path

from aewflow import Role, create_planned_ticket, create_unit, implement, plan_unit, sample_project
from conftest import run_aew
from invariants import assert_control_invariants

from aew.knowledge import evidence as E


def assessment(**overrides):
    base = {"requirement_trace": [{"requirement": "subtract(5, 3) == 2", "status": "covered",
                                   "plan_reference": "step 1"}],
            "premises_challenged": [{"premise": "calc/core.py holds the arithmetic", "source": "plan",
                                     "challenge": "read calc/core.py", "outcome": "holds",
                                     "evidence": ["calc/core.py:1"]}],
            "findings": []}
    base.update(overrides)
    return {"claim": "the plan covers the requirement", "producer": {"model": "scripted-assessor"},
            "assessment": base}


def assess(p, wid, *args):
    out = p.lead("plan", "assess", wid, *args)
    return Role(p, out["invocation_token"], Path(out["observation"]["path"])), out


def refused(p, *args):
    res = p.aew(*args, "--expect-rev", str(p.rev()), env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode != 0, res.stdout
    return res.error


def test_a_plan_assessor_of_a_ticket_is_pinned_to_its_accepted_revision_and_records_a_bound_assessment(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    role, out = assess(p, wid)
    assert out["role"] == E.ASSESSOR_ARCHETYPE and out["role_card"] == E.ASSESSOR_CARD
    assert out["scope"] == E.ASSESSMENT_SCOPE and out["dispatch"]["entrypoint"] == "plan.assess"
    plan = p.ok("work", "show", wid)["control"]["plan"]
    assert out["plan_revision"] == E.plan_binding(plan)
    shown = p.ok("invoke", "show", out["invocation"])
    assert shown["dispatch"]["entrypoint"] == "plan.assess" and shown["plan_revision"] == E.plan_binding(plan)
    assert role.ok("whoami")["scope"] == E.ASSESSMENT_SCOPE
    rec = role.submit(E.PLAN_ASSESSMENT, assessment(), "Read the plan against the requirement.\n")
    assert rec["result"] == "pass" and rec["evaluated_snapshot"] == out["evaluated_snapshot"]
    sealed = [r for r in E.scan(p.root / ".aew", wid)[0] if r["id"] == rec["evidence"]][0]
    assert sealed["kind"] == E.PLAN_ASSESSMENT and sealed["plan_revision"] == E.plan_binding(plan)
    assert sealed["producer"]["role_card"]["id"] == E.ASSESSOR_CARD
    assert_control_invariants(p)


def test_a_parents_accepted_plan_is_assessed_too(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Add subtraction", cls=1)
    plan_unit(p, tmp_path, story, "Split into a Ticket per operation.\n")
    role, out = assess(p, story)
    rec = role.submit(E.PLAN_ASSESSMENT, assessment(findings=[{"id": "A1", "severity": "major",
                                                                "summary": "no Ticket owns the integration proof"}]))
    assert rec["result"] == "fail"  # a major finding is required, and fails the assessment
    assert_control_invariants(p)


def test_a_code_reviewer_run_may_never_submit_a_plan_assessment(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = Role(p, p.lead("work", "assign", wid)["invocation_token"],
                Path(p.ok("work", "show", wid)["control"]["workspace"]["path"]))
    p.lead("work", "transition", wid, "--to", "RUNNING")
    implement(impl)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    out = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    reviewer = Role(p, out["invocation_token"], Path(p.ok("work", "show", wid)["control"]["workspace"]["path"]))
    res = reviewer.submit(E.PLAN_ASSESSMENT, assessment(), expect_ok=False)
    assert res.returncode != 0
    assert res.error["code"] == "PERMISSION_DENIED"
    assert res.error["details"]["reason"] == "not_a_plan_assessment_dispatch"
    assert "plan assess command" in res.error["message"]  # what to do instead
    ok = reviewer.submit("review", {"claim": "c", "producer": {"model": "m"},
                                    "review": {"independence": "R1", "disposition": "pass", "findings": [],
                                               "resolved_findings": []}})
    assert ok["result"] == "pass"  # the same reviewer still submits its review


def test_a_plan_assessor_submits_only_its_assessment(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    role, _ = assess(p, wid)
    res = role.submit("review", {"claim": "c", "producer": {"model": "m"},
                                 "review": {"independence": "R1", "disposition": "pass", "findings": [],
                                            "resolved_findings": []}}, expect_ok=False)
    assert res.returncode != 0 and res.error["code"] == "PERMISSION_DENIED"  # the card narrows it to the assessment


def test_a_second_assessor_of_an_assessed_revision_is_refused_and_a_new_revision_is_assessed_afresh(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    role, _ = assess(p, wid)
    first = role.submit(E.PLAN_ASSESSMENT, assessment(findings=[{"id": "A1", "severity": "blocker",
                                                                  "summary": "the plan skips the test"}]))["evidence"]
    rev = p.rev()
    error = refused(p, "plan", "assess", wid)
    assert error["code"] == "ILLEGAL_TRANSITION"
    assert error["details"]["reason"] == "plan_revision_assessed" and error["details"]["counting"] == first
    assert error["details"]["result"] == "fail" and "aew plan propose" in error["message"]
    assert p.rev() == rev  # nothing committed
    explained = p.ok("dispatch", "explain", wid, "--entrypoint", "plan.assess")
    assert not explained["allowed"]  # the query equals the execution
    # A later submission by the same assessor is history: the first counts (ruling 4 as built).
    role.submit(E.PLAN_ASSESSMENT, assessment())
    plan = p.ok("work", "show", wid)["control"]["plan"]
    assert E.counting_assessment(E.scan(p.root / ".aew", wid)[0], plan)["id"] == first
    plan_unit(p, tmp_path, wid, "1. Add subtract(a, b).\n2. Add tests/test_subtract.py.\n", reason="a finding")
    again, out = assess(p, wid)
    assert out["plan_revision"]["revision"] == 2


def test_an_assessment_of_a_revision_replaced_after_dispatch_is_refused(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    role, _ = assess(p, wid)
    plan_unit(p, tmp_path, wid, "A revised plan.\n", reason="revised")
    res = role.submit(E.PLAN_ASSESSMENT, assessment(), expect_ok=False)
    assert res.returncode != 0 and res.error["code"] == "GATE_UNSATISFIED"
    assert res.error["details"]["reason"] == "plan_revision_changed"


def test_nothing_is_assessed_without_an_accepted_plan_and_a_code_reviewer_card_never_assesses(tmp_path):
    p = sample_project(tmp_path)
    wid = create_unit(p, "ticket", "Unplanned", extra=("--goal", "g", "--scope", "calc/**"))
    error = refused(p, "plan", "assess", wid)
    assert error["code"] == "ILLEGAL_TRANSITION" and error["details"]["reason"] == "no_accepted_plan"
    planned = create_planned_ticket(p, tmp_path)
    error = refused(p, "plan", "assess", planned, "--card", "code_reviewer")
    assert error["code"] == "USAGE" and error["details"]["reason"] == "card_not_an_assessor"


def test_the_assessors_pack_holds_the_plan_and_the_request_and_no_planner_reasoning(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Arithmetic", cls=1, extra=("--goal", "every operation is tested"))
    plan_unit(p, tmp_path, story, "One Ticket per operation.\n")
    wid = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    _, out = assess(p, story)
    pack = run_aew("-C", str(p.root), "context", "show", out["invocation"]).stdout
    assert "## Accepted plan" in pack and "One Ticket per operation." in pack
    assert "## Assessment scope" in pack and f"aew submit --kind {E.PLAN_ASSESSMENT}" in pack
    assert "## Open review findings" not in pack and "## Change under review" not in pack
    assert "## Consumed inputs" not in pack
    _, ticket = assess(p, wid)
    pack = run_aew("-C", str(p.root), "context", "show", ticket["invocation"]).stdout
    assert "## The request as recorded" in pack and "Story " + story in pack
    assert "every operation is tested" in pack
