"""Regressions from the operator's TUI acceptance session, 2026-09-30 (an investigation of SPT).

UAT-1. An accepted plan promised "independent report reviewer and verifier will run before final acceptance", but the
plan was free text and the Ticket's gates (a non-mutating Ticket's path: an accepted plan and an execute record) did
not require either: AEW would have accepted the report on the investigator's own result. The Lead noticed and staffed
the review by hand. Every plan now declares its assurance (operator decision: required and explicit); accepting the
plan makes the declared cards required gates, and only a new plan revision changes them.

Policy consistency (operator P0, from the Q7 shakedown the same day). `gates.yaml` named a check `unit` that
`checks.yaml` did not define; every mutating Ticket then blocked with `unit` MISSING, and nothing said why. AEW now
reports contradictions between the policy files in `aew doctor` and in the next actions of `aew status` and resume,
and the gate itself names the cause.

UAT-2 (the Lead's own debrief). After a verifier's run, AEW's next action offered its guardrail check result for
`aew verify ingest` alongside the verification: the filter compared the evidence kind with `check`, the short form
used in evidence ids, rather than `check_result`. A check result is never ingested.

UAT-3. Every role's briefing said to use `aew check run <check>`, including reviewers, who may not run checks: the
first reviewer run tried `aew check run guardrails`, was refused, read six files and gave up without a review.

U8 (the Lead's debrief). A run that ended without its expected output came back from `aew harness wait` as a normal
result: exit 0, status `ended_without_evidence`, a reason and a relaunch action, easy to read past. `wait` now exits
with its own documented status for it, and the result starts with a one-line headline; the typed surface's
`harness_wait` result keeps its shape and carries the same headline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aewflow import SUBTRACT_PATCH, Role, create_planned_ticket, create_unit, dispatch, sample_project, submit_record
from conftest import run_aew
from fake_harness import IMPL_REPORT, HarnessLab, credential_hits
from invariants import assert_control_invariants

IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]
REVIEW = {"claim": "independent review", "producer": {"model": "fake-model"},
          "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}
VERIFY = {"claim": "the change meets its goal", "producer": {"model": "fake-model"},
          "verification": {"scope": "ticket", "claims": [
              {"type": "goal_backwards", "claim": "subtract works", "result": "pass", "checks": []},
              {"type": "contract", "claim": "contracts hold", "result": "pass", "checks": []}]}}


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path)


def refused(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def investigation(p, cls: int = 1) -> str:
    return create_unit(p, "ticket", "Assess calc.core", cls=cls,
                       extra=("--non-mutating", "--goal", "calc.core is assessed", "--scope", "calc/**"))


def plan_file(tmp_path: Path, name: str,
              text: str = "Read calc/core.py; report. Independent review will run.\n") -> str:
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return str(f)


def test_a_plan_must_declare_its_assurance(tmp_path):
    p = sample_project(tmp_path)
    wid = investigation(p)
    missing = refused(p, "plan", "propose", wid, "--file", plan_file(tmp_path, "a.md"))
    assert missing["code"] == "USAGE" and "--assurance none" in missing["message"], missing
    both = refused(p, "plan", "propose", wid, "--file", plan_file(tmp_path, "b.md"), "--assurance", "none",
                   "--review", "default")
    assert both["code"] == "USAGE", both
    wrong_slot = refused(p, "plan", "propose", wid, "--file", plan_file(tmp_path, "c.md"), "--review", "verifier")
    assert wrong_slot["code"] == "USAGE", wrong_slot  # a verifier card cannot fill the review slot
    unknown = refused(p, "plan", "propose", wid, "--file", plan_file(tmp_path, "d.md"), "--verify", "no_such_card")
    assert unknown["code"] == "NOT_FOUND", unknown
    assert show(p, wid)["plans"] == []
    assert_control_invariants(p)


def test_an_accepted_plans_review_and_verification_are_required_gates(tmp_path):
    """The UAT case: the plan's promise binds, so the record cannot be accepted until review and verification pass."""
    p = sample_project(tmp_path)
    wid = investigation(p)
    rev = p.lead("plan", "propose", wid, "--file", plan_file(tmp_path, "v1.md"), "--review", "default",
                 "--verify", "default")["revision_number"]
    p.lead("plan", "accept", wid, "--revision", str(rev))
    roles = p.ok("work", "roles", wid)
    assert roles["plan_gates"] == {"review_card:code_reviewer": "accepted plan v1",
                                   "verify_card:verifier": "accepted plan v1"}, roles["plan_gates"]
    # Only a new plan revision changes them: the role plan cannot drop or forbid them.
    assert refused(p, "work", "staff", wid, "--remove", "review=code_reviewer")["code"] == "PERMISSION_DENIED"
    assert refused(p, "work", "staff", wid, "--forbid", "verifier", "--reason", "x")["code"] == "PERMISSION_DENIED"

    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    blocked = refused(p, "work", "accept", wid)
    assert blocked["code"] == "GATE_UNSATISFIED", blocked
    gates = p.ok("gate", "show", wid)
    assert gates["obligations"]["sources"]["review_card:code_reviewer"] == ["accepted plan v1"], gates["obligations"]

    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    rv = p.lead("invoke", "create", wid, "--role", "reviewer")
    reviewer = Role(p, rv["invocation_token"], Path(rv["observation"]["path"]))
    ev = reviewer.submit("review", {"claim": "facts are supported", "review": {
        "independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}})["evidence"]
    p.lead("review", "ingest", wid, "--evidence", ev)
    assert show(p, wid)["state"] == "REVIEW_PASSED"
    assert refused(p, "work", "accept", wid)["code"] == "GATE_UNSATISFIED"  # verification is still required

    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    vo = p.lead("invoke", "create", wid, "--role", "verifier")
    verifier = Role(p, vo["invocation_token"], Path(vo["observation"]["path"]))
    claims = [{"type": "goal_backwards", "claim": "calc.core is assessed", "result": "pass", "checks": []},
              {"type": "contract", "claim": "the record meets its contract", "result": "pass", "checks": []}]
    ve = verifier.submit("verification", {"claim": "the record is complete", "verification": {
        "scope": "ticket", "claims": claims}})["evidence"]
    p.lead("verify", "ingest", wid, "--evidence", ve)
    p.lead("work", "accept", wid)
    assert show(p, wid)["state"] == "DONE"
    assert_control_invariants(p)


def test_a_new_plan_revision_changes_what_the_plan_requires(tmp_path):
    p = sample_project(tmp_path)
    wid = investigation(p)
    v1 = p.lead("plan", "propose", wid, "--file", plan_file(tmp_path, "v1.md"), "--review", "default")
    p.lead("plan", "accept", wid, "--revision", str(v1["revision_number"]))
    p.lead("work", "staff", wid, "--verify", "verifier")  # the Lead's own selection is not the plan's
    assert set(p.ok("work", "roles", wid)["plan_gates"]) == {"review_card:code_reviewer", "verify_card:verifier"}
    v2 = p.lead("plan", "propose", wid, "--file", plan_file(tmp_path, "v2.md", "Read only.\n"), "--assurance", "none",
                "--reason", "no review needed after all")
    p.lead("plan", "accept", wid, "--revision", str(v2["revision_number"]))
    plan_gates = p.ok("work", "roles", wid)["plan_gates"]
    assert plan_gates == {"verify_card:verifier": "role plan (lead)"}, plan_gates  # the plan's review is released
    p.lead("work", "staff", wid, "--remove", "verify=verifier")  # and the Lead's own entry is the Lead's again
    assert p.ok("work", "roles", wid)["plan_gates"] == {}
    assert_control_invariants(p)


def test_a_plan_cannot_require_a_forbidden_card(tmp_path):
    p = sample_project(tmp_path)
    wid = investigation(p)
    p.lead("work", "staff", wid, "--forbid", "code_reviewer", "--reason", "conflict of interest")
    res = refused(p, "plan", "propose", wid, "--file", plan_file(tmp_path, "v1.md"), "--review", "code_reviewer")
    assert res["code"] == "PERMISSION_DENIED", res
    assert_control_invariants(p)


def test_after_a_verifier_run_the_next_action_never_offers_its_check_results_for_ingest(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    lab.wait("R-INV-0001-1")
    lab.lead("work", "transition", wid, "--to", "RUNNING")
    lab.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    lab.script("R-INV-0002-1", [{"do": "submit", "kind": "review", "meta": REVIEW}])
    lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")
    [review] = lab.wait("R-INV-0002-1")["evidence"]
    lab.lead("review", "ingest", wid, "--evidence", review)
    lab.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    lab.script("R-INV-0003-1", [{"do": "check", "id": "unit"},
                                {"do": "submit", "kind": "verification", "meta": VERIFY}])
    lab.lead("invoke", "create", wid, "--role", "verifier", "--launch")
    out = lab.wait("R-INV-0003-1")
    assert out["status"] == "ended_with_evidence", out
    checks = [e for e in out["evidence"] if "-check-" in e]
    [verification] = [e for e in out["evidence"] if "-verify-" in e]
    assert checks, out
    advice = [a for a in lab.ok("status", "--json")["next_actions"] if "R-INV-0003-1" in a]
    advice.append(out.get("next_action") or "")
    assert not any(f"--evidence {c}" in a for a in advice for c in checks), advice  # listed, never offered
    assert f"aew verify ingest {wid} --evidence {verification}" in advice[0], advice
    lab.lead("verify", "ingest", wid, "--evidence", verification)  # the advice is a legal step
    assert lab.ok("work", "show", wid)["control"]["state"] == "VERIFIED"
    assert_control_invariants(lab.project)


def test_a_gate_naming_an_undefined_check_is_reported_everywhere_the_lead_looks(tmp_path):
    p = sample_project(tmp_path, checks={"schema": "aew/checks/v1", "baseline_failures": [], "checks": {
        "syntax": {"configured": True, "command": ["{python}", "-c", "print('ok')"], "cwd": ".", "timeout_s": 60,
                   "description": "a project-specific check, with no `unit`"}}})
    res = p.aew("doctor", "--json")
    assert res.returncode != 0  # a FAIL fails the doctor
    doctor = {c["check"]: c for c in res.json["checks"]}
    assert doctor["policy:consistency"]["status"] == "FAIL", doctor["policy:consistency"]
    assert "names check `unit`, which policy/checks.yaml does not define" in doctor["policy:consistency"]["detail"]
    actions = p.ok("status", "--json")["next_actions"]
    assert any(a.startswith("fix the policy: policy/gates.yaml local_checks names check `unit`")
               for a in actions), actions
    assert any("post_integration.checks names check `unit`" in a for a in p.ok("resume", "--json")["next_actions"])

    wid = create_planned_ticket(p, tmp_path, cls=0)  # the gate says why it can never pass
    local = p.ok("gate", "show", wid)["gates"]["local_checks"]
    assert local["checks"]["unit"]["reason"].startswith("check `unit` is not defined and configured"), local


def test_a_consistent_policy_reports_nothing(tmp_path):
    p = sample_project(tmp_path)
    doctor = {c["check"]: c for c in p.ok("doctor", "--json")["checks"]}
    assert doctor["policy:consistency"]["status"] == "PASS", doctor["policy:consistency"]
    assert not any(a.startswith("fix the policy") for a in p.ok("status", "--json")["next_actions"])


def test_a_role_is_told_only_the_aew_commands_it_may_use():
    from aew.harness.contract import LaunchContract, preamble

    base = dict(run="R-INV-0007-1", invocation="INV-0007", work_unit="T-0005", scope="observation", card=None,
                execution_profile={}, workspace="/w", pack_path="/p", pack_sha256="0" * 64, pack_text="",
                continuation=None, run_dir="/r")
    reviewer = preamble(LaunchContract(role="reviewer", expected_kinds=["review"],
                                       operations=["context.read", "submit.review"], **base))
    verifier = preamble(LaunchContract(role="verifier", expected_kinds=["verification"],
                                       operations=["check.run", "submit.verification", "context.read"], **base))
    assert "aew check run" not in reviewer and "`aew submit --kind <kind> --file <file>`" in reviewer, reviewer
    assert "`aew check run <check>`" in verifier, verifier


def test_a_run_that_ended_without_its_expected_output_is_conspicuous_in_wait(lab, tmp_path):
    from aew.cli.work_commands import WAIT_NO_EVIDENCE_EXIT
    from aew.engine.api import Engine
    from aew.surface import run as surface_run
    from aew.surface.context import SurfaceContext

    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [{"do": "exit", "code": 0}])  # the agent stops without submitting anything
    lab.lead("work", "assign", wid, "--launch")
    res = run_aew("-C", str(lab.root), "harness", "wait", "R-INV-0001-1", "--timeout", "120", env=lab.env, timeout=240)
    assert res.returncode == WAIT_NO_EVIDENCE_EXIT == 20, (res.returncode, res.stderr)  # not an error's (1-10)
    out = res.json  # printed as for any other ending: callers that read the result still read it
    assert list(out)[0] == "headline" and len(out["headline"].splitlines()) == 1, out
    headline = out["headline"]
    assert headline.startswith("R-INV-0001-1 ENDED WITHOUT EVIDENCE") and "implementation_report" in headline, out
    assert out["status"] == "ended_without_evidence" and out["evidence"] == [] and not out["timed_out"], out
    assert out["reason"] and "aew harness launch INV-0001" in out["next_action"], out
    assert "error" not in res.stderr and not res.stderr.strip(), res.stderr  # an outcome, not a refusal
    # the typed surface: the same StageResult as any call, its result carrying the headline (no new field elsewhere)
    engine = Engine.discover(lab.root)
    typed = surface_run.run_tool(engine, SurfaceContext.outside_session(), "harness_wait",
                                 {"runs": ["R-INV-0001-1"], "timeout_s": 5})
    status = surface_run.run_tool(engine, SurfaceContext.outside_session(), "status", {})
    assert set(typed) == set(status) and typed["ok"], typed
    assert typed["result"]["headline"] == out["headline"] and typed["result"]["status"] == "ended_without_evidence"

    # A run that ended with its evidence exits 0, with no headline: nothing else changes.
    lab.script("R-INV-0001-2", IMPLEMENT)
    lab.lead("harness", "launch", "INV-0001")
    res = run_aew("-C", str(lab.root), "harness", "wait", "R-INV-0001-2", "--timeout", "120", env=lab.env, timeout=240)
    assert res.returncode == 0 and res.json["status"] == "ended_with_evidence", res.stdout
    assert "headline" not in res.json and list(res.json)[0] == "run", res.json
    # a timed-out wait on a run still going is not an ending: exit 0, as before
    lab.script("R-INV-0001-3", [{"do": "hang"}])
    lab.lead("harness", "launch", "INV-0001")
    res = run_aew("-C", str(lab.root), "harness", "wait", "R-INV-0001-3", "--timeout", "1", env=lab.env, timeout=240)
    assert res.returncode == 0 and res.json["timed_out"] and "headline" not in res.json, res.stdout
    lab.ok("harness", "stop", "R-INV-0001-3", "--reason", "test over", "--token", lab.project.token)
    assert_control_invariants(lab.project)
