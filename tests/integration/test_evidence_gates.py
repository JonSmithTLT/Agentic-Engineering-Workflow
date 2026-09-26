"""Evidence, gates, review/verification ingest and role separation (WC §9-§12; KC §11, §16)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aewflow import (
    SUBTRACT_PATCH,
    Role,
    assign,
    create_planned_ticket,
    implement,
    review,
    sample_project,
    to_verified,
    verify,
)
from conftest import run_aew


@pytest.fixture
def calc(tmp_path):
    return sample_project(tmp_path)


def fail(res, code: str, exit_code: int | None = None) -> dict:
    assert res.returncode != 0, res.stdout
    err = res.error
    assert err["code"] == code, err
    if exit_code is not None:
        assert res.returncode == exit_code
    return err


def test_smoke_to_verified(calc, tmp_path):
    wid, _ = to_verified(calc, tmp_path)
    gates = calc.ok("gate", "show", wid)
    assert gates["unmet"] == {}
    assert gates["obligations"]["effective_class"] == 1


# ------------------------------------------------------------------ stale evidence (AT-3 core)


def test_relevant_uncommitted_change_makes_evidence_stale_but_keeps_history(calc, tmp_path):
    wid, impl = to_verified(calc, tmp_path)
    ev_dir = calc.root / f".aew/evidence/{wid}"
    verification = sorted(ev_dir.glob("*-verify-*.md"))[-1]
    snapshot_bytes = verification.read_bytes()
    before = calc.ok("gate", "show", wid)

    # Writing AEW's own artifacts never invalidates the engineering snapshot.
    (calc.root / ".aew/knowledge/NOTES.md").write_text("Lead notes\n")
    (Path(impl.workspace) / ".aew").mkdir(exist_ok=True)
    (Path(impl.workspace) / ".aew/scratch.md").write_text("workspace-local AEW scratch\n")
    same = calc.ok("gate", "show", wid)
    assert same["snapshot"]["relevant_inputs_fingerprint"] == before["snapshot"]["relevant_inputs_fingerprint"]
    assert same["unmet"] == {}
    (Path(impl.workspace) / ".aew/scratch.md").unlink()

    # A relevant uncommitted engineering input changes after verification.
    core = Path(impl.workspace) / "calc/core.py"
    core.write_text(core.read_text() + "\n# tweak after verification\n", encoding="utf-8", newline="\n")
    stale = calc.ok("gate", "show", wid)
    assert stale["snapshot"]["relevant_inputs_fingerprint"] != before["snapshot"]["relevant_inputs_fingerprint"]
    for gate in ("local_checks", "self_review", "review_r1", "verification_goal_backwards", "verification_contract"):
        assert stale["unmet"][gate] == "STALE", stale["unmet"]
    err = fail(calc.aew("work", "transition", wid, "--to", "COMMIT_READY", "--token", calc.token,
                        "--expect-rev", str(calc.rev())), "GATE_UNSATISFIED")
    assert set(err["details"]["unmet"]) >= {"review_r1", "verification_goal_backwards"}
    # History is preserved untouched and still listed.
    assert verification.read_bytes() == snapshot_bytes
    assert verification.stem in stale["evidence_ids"]

    # Revalidating the new snapshot restores the gates (and needs re-review, not just re-verify).
    calc.lead("work", "transition", wid, "--to", "RUNNING", "--reason", "evidence stale after edit")
    impl2 = Role(calc, calc.lead("invoke", "create", wid, "--role", "implementer")["invocation_token"]
                 if calc.ok("invoke", "show", calc.ok("work", "show", wid)["control"]["implementer_invocation"])
                 ["status"] != "active" else impl.token, impl.workspace)
    implement(impl2, {"calc/core.py": core.read_text()})
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid))
    calc.lead("work", "transition", wid, "--to", "COMMIT_READY")
    assert calc.ok("work", "show", wid)["control"]["state"] == "COMMIT_READY"


def test_stale_review_cannot_be_ingested(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    ev = review(calc, wid)
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "\n# late edit\n"})
    err = fail(calc.aew("review", "ingest", wid, "--evidence", ev, "--token", calc.token,
                        "--expect-rev", str(calc.rev())), "GATE_UNSATISFIED")
    assert "stale" in err["message"]


# ------------------------------------------------------------------ role separation (AT-5)


def test_role_separation_negatives(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)

    # An implementer cannot submit a review of its own work.
    res = impl.submit("review", {"review": {"independence": "R1", "disposition": "pass", "findings": []}},
                      expect_ok=False)
    fail(res, "PERMISSION_DENIED", 4)
    # An invocation credential cannot drive control transitions.
    res = run_aew("-C", str(calc.root), "work", "transition", wid, "--to", "REVIEW_PENDING",
                  "--token", impl.token, "--expect-rev", str(calc.rev()))
    fail(res, "PERMISSION_DENIED", 4)
    # Engine-owned bindings cannot be supplied by a role.
    res = impl.submit("implementation_report", {"result": "pass", "evaluated_snapshot": {"relevant_inputs_fingerprint": "x"}},
                      expect_ok=False)
    fail(res, "VALIDATION_FAILED")

    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    rev_out = calc.lead("invoke", "create", wid, "--role", "reviewer")
    reviewer = Role(calc, rev_out["invocation_token"], impl.workspace)
    # Reviewers are read-only with respect to checks.
    fail(reviewer.aew("check", "run", "unit"), "PERMISSION_DENIED")
    # R0 is never independent review.
    fail(reviewer.submit("review", {"review": {"independence": "R0", "disposition": "pass", "findings": []}},
                         expect_ok=False), "VALIDATION_FAILED")
    calc.lead("review", "ingest", wid, "--evidence", reviewer.submit(
        "review", {"review": {"independence": "R1", "disposition": "pass", "findings": []}})["evidence"])
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")

    ver_out = calc.lead("invoke", "create", wid, "--role", "verifier")
    verifier = Role(calc, ver_out["invocation_token"], impl.workspace)
    unit_ev = verifier.check("unit")["evidence"]
    # A Verifier may not choose the remediation path.
    res = verifier.submit("verification", {
        "classification": "LOCAL_IMPLEMENTATION_DEFECT",
        "verification": {"scope": "ticket", "claims": []}}, expect_ok=False)
    fail(res, "PERMISSION_DENIED", 4)
    # Both goal-backwards and contract claims are required.
    res = verifier.submit("verification", {"verification": {"scope": "ticket", "claims": [
        {"type": "goal_backwards", "claim": "works", "result": "pass", "checks": [unit_ev]}]}}, expect_ok=False)
    fail(res, "VALIDATION_FAILED")
    # A Verifier may not cite the implementer's checks as its own evidence.
    impl_check = [e for e in calc.ok("gate", "show", wid)["evidence_ids"] if "-check-unit-" in e][0]
    res = verifier.submit("verification", {"verification": {"scope": "ticket", "claims": [
        {"type": "goal_backwards", "claim": "works", "result": "pass", "checks": [impl_check]},
        {"type": "contract", "claim": "ok", "result": "pass", "checks": [unit_ev]}]}}, expect_ok=False)
    fail(res, "VALIDATION_FAILED")
    # The Lead cannot declare VERIFIED; only ingesting the Verifier's result can.
    err = fail(calc.aew("work", "transition", wid, "--to", "VERIFIED", "--token", calc.token,
                        "--expect-rev", str(calc.rev())), "ILLEGAL_TRANSITION")
    assert err["details"]["required_operation"] == "verify.ingest"


# ------------------------------------------------------------------ verification failure classification (AT-6)


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        ("LOCAL_IMPLEMENTATION_DEFECT", "RUNNING"),
        ("PLAN_OR_DESIGN_DEFECT", "REPLAN_REQUIRED"),
        ("CONTRACT_VIOLATION", "REPLAN_REQUIRED"),
        ("ENVIRONMENT_OR_EVIDENCE_BLOCKED", "VERIFICATION_INCONCLUSIVE"),
    ],
)
def test_lead_classifies_verification_failures(calc, tmp_path, classification, expected):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    ev = verify(calc, wid, goal_result="fail")
    out = calc.lead("verify", "ingest", wid, "--evidence", ev)
    assert out["transition"]["to"] == "VERIFICATION_FAILED"
    # Nothing but classification (or cancellation) leaves VERIFICATION_FAILED.
    fail(calc.aew("work", "transition", wid, "--to", "RUNNING", "--reason", "just fix it", "--token", calc.token,
                  "--expect-rev", str(calc.rev())), "ILLEGAL_TRANSITION")
    res = calc.lead("verify", "classify", wid, "--as", classification, "--reason", "analysed failure evidence")
    assert res["to"] == expected
    decision = (calc.root / f".aew/decisions/{res['decision']}.md").read_text()
    assert classification in decision and ev in decision
    assert calc.ok("work", "show", wid)["control"]["state"] == expected


# ------------------------------------------------------------------ findings, triggered reviews, checks


def test_blocking_findings_fail_review_and_must_be_resolved(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    bad = review(calc, wid, disposition="changes_required",
                 findings=[{"id": "F1", "severity": "major", "summary": "missing negative test", "required": True}])
    assert calc.lead("review", "ingest", wid, "--evidence", bad)["transition"]["to"] == "REVIEW_FAILED"
    calc.lead("work", "transition", wid, "--to", "RUNNING")  # allowed: findings recorded
    implement(impl, {"tests/test_subtract.py": SUBTRACT_PATCH["tests/test_subtract.py"]
                     + "\n\ndef test_subtract_negative():\n    from calc.core import subtract\n"
                       "    assert subtract(1, 3) == -2\n"})
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    # A passing review that does not resolve F1 leaves it open -> still failed.
    unresolved = review(calc, wid)
    assert calc.lead("review", "ingest", wid, "--evidence", unresolved)["transition"]["to"] == "REVIEW_FAILED"
    calc.lead("work", "transition", wid, "--to", "RUNNING")
    implement(impl, {"tests/test_subtract.py": (impl.workspace / "tests/test_subtract.py").read_text()})
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    good = review(calc, wid, resolved=[f"{bad}#F1"])
    assert calc.lead("review", "ingest", wid, "--evidence", good)["transition"]["to"] == "REVIEW_PASSED"


def test_guardrail_trigger_requires_specialist_review(tmp_path):
    calc = sample_project(tmp_path, guardrails={
        "schema": "aew/guardrails/v1", "protected_paths": ["vendor/**"], "generated_paths": [],
        "ticket_scope_enforcement": True, "dependency_rules": [],
        "review_triggers": [{"name": "security", "paths": ["calc/crypto*.py"]}],
    })
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl, {**SUBTRACT_PATCH, "calc/crypto_util.py": "KEY_BITS = 256\n"})
    assert "review_security" in calc.ok("gate", "show", wid)["obligations"]["gates"]
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    out = calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    assert out["transition"] is None and "review_security" in out["pending_reviews"]
    out = calc.lead("review", "ingest", wid, "--evidence", review(calc, wid, specialty="security"))
    assert out["transition"]["to"] == "REVIEW_PASSED"


def test_guardrail_violation_blocks_progress(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl, {**SUBTRACT_PATCH, "vendor/lib.py": "VENDORED = False\n"})
    err = fail(calc.aew("work", "transition", wid, "--to", "REVIEW_PENDING", "--token", calc.token,
                        "--expect-rev", str(calc.rev())), "GATE_UNSATISFIED")
    assert err["details"]["violations"][0]["path"] == "vendor/lib.py"
    assert impl.check("guardrails")["result"] == "fail"


def test_check_that_mutates_inputs_is_inconclusive(tmp_path):
    calc = sample_project(tmp_path, checks={
        "schema": "aew/checks/v1", "baseline_failures": [],
        "checks": {
            "unit": {"configured": True, "command": ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                                     "tests"]},
            "codegen": {"configured": True,
                        "command": ["{python}", "-c", "open('calc/generated.py','w').write('X=1\\n')"]},
        },
    })
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    out = impl.check("codegen")
    assert out["result"] == "inconclusive" and out["mutated_inputs"] is True


def test_unconfigured_check_blocks_instead_of_guessing(tmp_path):
    calc = sample_project(tmp_path, checks={"schema": "aew/checks/v1", "baseline_failures": [],
                                            "checks": {"unit": {"configured": False, "command": None}}})
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    fail(impl.aew("check", "run", "unit"), "GATE_UNSATISFIED")
