"""Role catalog, staffing and card-bound invocations (ADR-0006)."""

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
    verify,
)
from aew.util import dump_yaml

TRIAGER = {
    "schema": "aew/role/v1", "role": "vulnerability_triager", "display_name": "Vulnerability Triager",
    "version": 1, "extends": "investigator",
    "purpose": "Triage candidate vulnerability evidence.",
    "use_when": ["sanitizer crash", "suspected duplicate"],
    "skills": ["revelations/finding-triage"],
    "required_capabilities": ["candidate_finding_query", "exact_code_search"],
    "optional_capabilities": ["binary_analysis"],
    "outputs": ["vulnerability_triage_report"],
}
CALC_ENGINEER = {
    "schema": "aew/role/v1", "role": "calc_engineer", "display_name": "Calc Engineer", "version": 1,
    "extends": "implementer", "purpose": "Implement calculator features.",
    "responsibilities": ["keep functions pure"], "skills": ["calc-style"],
    "required_capabilities": ["source_mutation", "targeted_test_execution"],
}
STRICT_VERIFIER = {
    "schema": "aew/role/v1", "role": "strict_verifier", "display_name": "Strict Verifier", "version": 1,
    "extends": "verifier", "purpose": "Second, independent acceptance verification.",
}
SUBMIT_ONLY_VERIFIER = {
    "schema": "aew/role/v1", "role": "submit_only_verifier", "display_name": "Submit-only Verifier", "version": 1,
    "extends": "verifier", "purpose": "Verifies from existing evidence only.",
    "restrict": {"operations": ["submit.verification", "context.read"]},
}


def add_cards(p, *cards):
    catalog = p.root / ".aew/roles"
    catalog.mkdir(exist_ok=True)
    for c in cards:
        (catalog / f"{c['role']}.yaml").write_text(dump_yaml(c), encoding="utf-8", newline="\n")


@pytest.fixture
def calc(tmp_path):
    p = sample_project(tmp_path)
    add_cards(p, TRIAGER, CALC_ENGINEER, STRICT_VERIFIER, SUBMIT_ONLY_VERIFIER)
    return p


def fail(res, code):
    assert res.returncode != 0, res.stdout
    assert res.error["code"] == code, res.error
    return res.error


def test_catalog_lists_builtin_and_project_cards(calc):
    listing = calc.ok("role", "list")
    by_id = {c["id"]: c for c in listing["cards"]}
    assert by_id["vulnerability_triager"]["source"] == "project"
    assert by_id["vulnerability_triager"]["use_when"] == ["sanitizer crash", "suspected duplicate"]
    assert by_id["security_reviewer"]["specialty"] == "security"
    assert listing["problems"] == []
    add_cards(calc, {**TRIAGER, "role": "rogue_lead", "extends": "lead"})
    res = calc.aew("role", "validate")
    assert res.returncode == 1 and res.json["ok"] is False
    assert res.json["problems"] == ["roles/rogue_lead.yaml: cards cannot extend 'lead' (not a dispatchable authority class)"]
    assert "rogue_lead" not in {c["id"] for c in calc.ok("role", "list")["cards"]}


def test_workflow_defaults_fill_required_slots(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    eff = calc.ok("work", "roles", wid)["effective"]
    assert [(e["card"], e["selected_by"]) for e in eff["execute"]] == [("engineer", "workflow")]
    assert [(e["card"], e["selected_by"]) for e in eff["review"]] == [("code_reviewer", "workflow")]
    assert [(e["card"], e["selected_by"]) for e in eff["verify"]] == [("verifier", "workflow")]


def test_invocation_pins_card_identity_and_pack(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    calc.lead("work", "staff", wid, "--execute", "calc_engineer")
    out = calc.lead("work", "assign", wid)
    assert out["role_card"] == "calc_engineer"
    inv = calc.ok("invoke", "show", out["invocation"])
    assert inv["card"]["id"] == "calc_engineer" and inv["card"]["version"] == 1 and len(inv["card"]["sha256"]) == 64
    pack_path = calc.root / ".aew" / inv["pack"]["path"]
    pack = pack_path.read_text(encoding="utf-8")
    assert "Calc Engineer" in pack and "calc-style" in pack and "keep functions pure" in pack
    impl = Role(calc, out["invocation_token"], Path(out["workspace"]["path"]))
    check = impl.check("unit")["evidence"]
    ev = (calc.root / f".aew/evidence/{wid}/{check}.md").read_text(encoding="utf-8")
    assert "id: calc_engineer" in ev
    # Editing the project card later changes neither the invocation's pin nor its pack.
    card_file = calc.root / ".aew/roles/calc_engineer.yaml"
    card_file.write_text(dump_yaml({**CALC_ENGINEER, "version": 2, "purpose": "Changed purpose."}),
                         encoding="utf-8", newline="\n")
    assert calc.ok("invoke", "show", out["invocation"])["card"]["sha256"] == inv["card"]["sha256"]
    regen = calc.ok("context", "pack", out["invocation"])
    assert regen["matches_recorded"] is True and "Changed purpose." not in Path(regen["path"]).read_text()


def test_multiple_review_cards_each_required(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    calc.lead("work", "staff", wid, "--review", "code_reviewer", "--review", "security_reviewer")
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    # Without --card the next pending planned card is dispatched, in plan order.
    first = review(calc, wid)
    out = calc.lead("review", "ingest", wid, "--evidence", first)
    assert out["transition"] is None and "review_card:security_reviewer" in out["pending_reviews"]
    second = calc.lead("invoke", "create", wid)
    assert second["role_card"] == "security_reviewer"
    reviewer = Role(calc, second["invocation_token"], impl.workspace)
    ev = reviewer.submit("review", {"review": {"independence": "R1", "disposition": "pass", "findings": []}})
    assert calc.lead("review", "ingest", wid, "--evidence", ev["evidence"])["transition"]["to"] == "REVIEW_PASSED"


def test_multiple_verify_cards_each_required(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    calc.lead("work", "staff", wid, "--verify", "verifier", "--verify", "strict_verifier")
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    out = calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, card="verifier"))
    assert out["transition"] is None and "verify_card:strict_verifier" in out["pending_verifications"]
    out = calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, card="strict_verifier"))
    assert out["transition"]["to"] == "VERIFIED"


def test_policy_trigger_requires_named_card(tmp_path):
    calc = sample_project(tmp_path, guardrails={
        "schema": "aew/guardrails/v1", "protected_paths": ["vendor/**"], "generated_paths": [],
        "ticket_scope_enforcement": True, "dependency_rules": [],
        "review_triggers": [{"name": "crypto", "paths": ["calc/crypto*.py"], "card": "security_reviewer"}],
    })
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl, {**SUBTRACT_PATCH, "calc/crypto_util.py": "KEY_BITS = 256\n"})
    roles_view = calc.ok("work", "roles", wid)
    policy = [e for e in roles_view["effective"]["review"] if e["selected_by"] == "policy"]
    assert policy == [{"card": "security_reviewer", "selected_by": "policy", "reason": "guardrail trigger crypto"}]
    assert "review_card:security_reviewer" in calc.ok("gate", "show", wid)["obligations"]["gates"]


def test_forbidden_and_pinned_cards(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    calc.lead("work", "staff", wid, "--forbid", "python_engineer", "--by", "operator", "--reason", "not Python")
    fail(calc.aew("work", "staff", wid, "--execute", "python_engineer", "--token", calc.token,
                  "--expect-rev", str(calc.rev())), "PERMISSION_DENIED")
    calc.lead("work", "staff", wid, "--execute", "c_engineer", "--by", "operator", "--pin")
    fail(calc.aew("work", "staff", wid, "--execute", "calc_engineer", "--token", calc.token,
                  "--expect-rev", str(calc.rev())), "PERMISSION_DENIED")
    out = calc.lead("work", "staff", wid, "--execute", "calc_engineer", "--reason", "calc_engineer fits better")
    decision = (calc.root / f".aew/decisions/{out['decision']}.md").read_text()
    assert "role_plan_change" in decision and "overrode operator pins" in decision
    fail(calc.aew("invoke", "create", wid, "--card", "python_engineer", "--token", calc.token,
                  "--expect-rev", str(calc.rev())), "ILLEGAL_TRANSITION")  # READY: nothing to dispatch yet
    calc.lead("work", "assign", wid)
    calc.lead("work", "transition", wid, "--to", "RUNNING")


@pytest.mark.acceptance("AT-5")
def test_card_restriction_narrows_the_credential(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    out = calc.lead("invoke", "create", wid, "--card", "submit_only_verifier")
    narrow = Role(calc, out["invocation_token"], impl.workspace)
    fail(narrow.aew("check", "run", "unit"), "PERMISSION_DENIED")


def test_slot_archetype_mismatch_rejected(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    fail(calc.aew("work", "staff", wid, "--review", "c_engineer", "--token", calc.token,
                  "--expect-rev", str(calc.rev())), "USAGE")
    fail(calc.aew("work", "staff", wid, "--execute", "vulnerability_triager", "--token", calc.token,
                  "--expect-rev", str(calc.rev())), "USAGE")  # mutating Ticket needs an implementer card
