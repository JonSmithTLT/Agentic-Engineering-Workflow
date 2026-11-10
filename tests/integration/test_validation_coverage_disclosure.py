"""Coverage is frozen by the engine and follows real validation to status and completion without changing gates."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from aewflow import Role, sample_project, to_commit_ready
from invariants import assert_control_invariants
from test_validation_checks import SMOKE, control, engine, integ, policy, prepared, record_of, validate
from test_validation_checks import contained as contained

from aew.engine import coverage as CV
from aew.engine import validation_ops as VO
from aew.knowledge import evidence as E
from aew.surface import readable
from aew.util import load_yaml, parse_frontmatter


def test_verifier_coverage_is_engine_owned_bound_to_its_checks_and_preserved_in_verifier_mode(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    inv = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    role = Role(p, inv["invocation_token"], Path(integ(p, wid)["workspace"]))
    checked = role.check("unit")
    meta = {"claim": "scripted verification", "verification": {"scope": "integration", "claims": [
        {"type": "goal_backwards", "claim": "unit observed", "result": "pass", "checks": [checked["evidence"]]}]}}
    forged = role.submit("verification", {**meta, "coverage": {"summary": {"verdict": "validated"}}}, expect_ok=False)
    assert forged.returncode != 0
    submitted = role.submit("verification", meta)
    value = submitted["coverage"]
    assert value["checks"][0]["evidence"] == checked["evidence"] and value["checks"][0]["cited"]
    assert value["checks"][0]["command"] == checked["coverage"]["checks"][0]["command"]
    assert value["checks"][0]["cwd"] == checked["coverage"]["checks"][0]["cwd"]
    ingested = p.lead("verify", "ingest", wid, "--evidence", submitted["evidence"])
    assert ingested["coverage"] == value and engine(p).status(wid)["coverage"] == value
    assert p.lead("integrate", "publish", wid)["coverage"] == value
    assert_control_invariants(p)


def test_the_same_record_reaches_every_verdict_surface_and_disclosure_does_not_change_acceptance(
        tmp_path, contained):
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE, post=["smoke", "guardrails"])
    wid = prepared(p, tmp_path)
    out = validate(p, wid)
    assert out["ok"] and out["result"] == "pass" and out["integration"] == "validated"
    coverage = out["coverage"]
    assert [c["check_id"] for c in coverage["checks"]] == ["smoke", "guardrails"]
    assert all(c["cwd"] and c["definition_sha256"] for c in coverage["checks"])
    assert coverage["summary"]["verdict"] == "validated within its scope"
    run = integ(p, wid)[VO.CURRENT]
    assert record_of(p, run)["coverage"] == coverage
    assert validate(p, wid)["coverage"] == coverage  # cached/noop uses the same pin
    eng = engine(p)
    status = eng.status(wid)
    assert status["coverage"] == coverage
    assert coverage["summary"]["headline"] in eng.render_status(status)
    text = readable.render({"tool": "status", "result": status})
    assert "Affected tests: not known" in text.split(readable.JSON_MARKER)[0]
    assert "Project CI tools: not known" in text.split(readable.JSON_MARKER)[0]
    project = eng.status()
    assert project["validation_coverage"][wid]["summary"] == coverage["summary"]
    for eid in out["evidence"]:
        meta = next(e for e in E.scan(p.root / ".aew", wid)[0] if e["id"] == eid)
        assert meta["coverage"] == coverage
    accepted = p.lead("integrate", "publish", wid)
    assert accepted["state"] == "DONE" and accepted["coverage"] == coverage
    completion = p.root / ".aew/work" / wid / "completion.md"
    meta, body = parse_frontmatter(completion.read_text(encoding="utf-8"))
    assert meta["coverage"] == coverage and coverage["summary"]["headline"] in body
    assert engine(p).status(wid)["coverage"] == coverage  # archived, after workspace cleanup
    assert_control_invariants(p)


def test_coverage_uses_the_pinned_inventory_when_unrelated_policy_changes_during_execution(
        tmp_path, contained, monkeypatch):
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE)
    wid = prepared(p, tmp_path)
    eng = engine(p)
    original = eng._validation._execute

    def execute(work_id, run):
        policy(p, checks={"added-after-pin": {"configured": True, "command": ["{python}", "-c", "pass"]}})
        return original(work_id, run)

    monkeypatch.setattr(eng._validation, "_execute", execute)
    out = eng.integrate_validate(token=p.token, expect_rev=p.rev(), work_id=wid)
    assert out["result"] == "pass"
    assert "added-after-pin" not in {c["check_id"] for c in out["coverage"]["configured_not_run"]}
    pin = integ(p, wid)[VO.CURRENT]["coverage_inputs"]
    inputs = load_yaml((p.root / ".aew" / pin["path"]).read_text(encoding="utf-8"))
    assert "added-after-pin" not in {c["check_id"] for c in inputs["configured"]}


@pytest.mark.parametrize("kind", ["advisory", "unavailable", "abandoned"])
def test_every_terminal_record_keeps_coverage_without_manufacturing_a_validation_pass(tmp_path, contained, kind):
    p = sample_project(tmp_path)
    checks = SMOKE if kind != "unavailable" else {
        "smoke": {"configured": True, "command": ["aew-fixture-no-such-executable-coverage"]}}
    policy(p, checks=checks)
    wid = prepared(p, tmp_path)
    if kind == "abandoned":
        eng = engine(p)
        run = eng._validation._pin(VO.Principal(VO.LEAD, p.token), p.rev(), wid, attempt=1, diagnostic=False)
        eng._validation._abandon(VO.Principal(VO.LEAD, p.token), p.rev(), wid, run["id"],
                                 "VALIDATION_INTERRUPTED", "synthetic executor interruption after the real pin")
    else:
        validate(p, wid, diagnostic=kind == "advisory")
    run = integ(p, wid)[VO.DIAGNOSTIC if kind == "advisory" else VO.CURRENT]
    assert run["state"] == kind
    value = record_of(p, run)["coverage"]
    assert value["summary"]["verdict"] != "validated"
    assert value["affected_tests"] == {"known": False, "reason": "no_project_source"}
    if kind != "advisory":
        assert "execution_completion_not_recorded" in value["observation_limits"]
    assert_control_invariants(p)


def test_coverage_is_display_data_not_an_input_to_the_gate_result(tmp_path, contained, monkeypatch):
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE)
    wid = prepared(p, tmp_path)
    original = CV.build

    def extra_gaps(**kwargs):
        value = original(**kwargs)
        value["configured_not_run"].append({"check_id": "synthetic-extra-gap", "definition_sha256": "0" * 64,
                                            "reason": "not run"})
        value["summary"] = CV.summarize(value)
        return value

    before = copy.deepcopy(control(p)["work"][wid]["commit_ready_snapshot"])
    with monkeypatch.context() as patch:
        patch.setattr(CV, "build", extra_gaps)
        out = validate(p, wid)
    assert out["result"] == "pass" and out["integration"] == "validated"
    assert control(p)["work"][wid]["commit_ready_snapshot"] == before
    assert out["coverage"]["summary"]["known_gaps"]["configured_checks_not_run"] >= 1
    assert p.lead("integrate", "publish", wid)["state"] == "DONE"
    assert_control_invariants(p)


def test_the_finalizer_records_superseded_coverage_without_claiming_the_unobserved_checks_ran(tmp_path, contained):
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE)
    wid = prepared(p, tmp_path)
    eng = engine(p)
    eng._validation._pin(VO.Principal(VO.LEAD, p.token), p.rev(), wid, attempt=1, diagnostic=False)
    p.lead("integrate", "defer", wid, "--reason", "retire the candidate before execution")
    retired = control(p)["work"][wid]["integration_history"][-1][VO.CURRENT]
    assert retired["state"] == "abandoned" and retired["reason"] == "SUPERSEDED"
    value = record_of(p, retired)["coverage"]
    assert value["checks"] == [] and value["configured_not_run"] == []
    assert "execution_completion_not_recorded" in value["observation_limits"]
    assert value["summary"]["verdict"] == "abandoned"
    assert_control_invariants(p)
