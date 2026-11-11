"""Coverage is frozen by the engine and follows real validation to status and completion without changing gates."""

from __future__ import annotations

import copy
import shutil
import sys
from pathlib import Path

import pytest
from aewflow import Role, sample_project, to_commit_ready
from invariants import assert_control_invariants
from test_validation_checks import SMOKE, control, engine, integ, policy, prepared, py, record_of, validate
from test_validation_checks import contained as contained

from aew.engine import coverage as CV
from aew.engine import validation_ops as VO
from aew.knowledge import evidence as E
from aew.policy import checks as C
from aew.surface import readable
from aew.util import dump_yaml, load_yaml, parse_frontmatter, sha256_file


def declare(p, *tools, affected_tests=None):
    path = p.root / ".aew/policy/checks.yaml"
    data = load_yaml(path.read_text(encoding="utf-8"))
    data["coverage"] = {"ci_tools": [{"name": name, "covered_by": covering} for name, covering in tools]}
    if affected_tests is not None:
        data["coverage"]["affected_tests"] = affected_tests
    path.write_text(dump_yaml(data), encoding="utf-8", newline="\n")
    p.adopt_policy()
    return sha256_file(path)


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
    assert forged.returncode != 0 and "coverage" in forged.stdout + forged.stderr
    submitted = role.submit("verification", meta)
    value = submitted["coverage"]
    assert value["checks"][0]["evidence"] == checked["evidence"] and value["checks"][0]["cited"]
    assert value["checks"][0]["command"] == checked["coverage"]["checks"][0]["command"]
    assert value["checks"][0]["cwd"] == checked["coverage"]["checks"][0]["cwd"]
    assert checked["coverage"]["summary"]["headline"].startswith("Check: pass within its recorded scope;")
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
    for key in ("ci_tools", "affected_tests"):
        assert coverage[key] == {"known": False, "reason": "no_project_source"}
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
    workspace = integ(p, wid)["workspace"]
    accepted = p.lead("integrate", "publish", wid)
    assert accepted["state"] == "DONE" and accepted["coverage"] == coverage
    completion = p.root / ".aew/work" / wid / "completion.md"
    meta, body = parse_frontmatter(completion.read_text(encoding="utf-8"))
    assert meta["coverage"] == coverage and coverage["summary"]["headline"] in body
    assert workspace not in body
    assert all(c["command"][0] not in body for c in coverage["checks"] if Path(c["command"][0]).is_absolute())
    assert engine(p).status(wid)["coverage"] == coverage  # archived, after workspace cleanup
    assert_control_invariants(p)


def test_a_new_ticket_is_not_a_legacy_validation_record(tmp_path):
    from aewflow import create_planned_ticket

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    eng = engine(p)
    value = eng.status(wid)["coverage"]["summary"]
    assert value["headline"] == "Validation: not yet validated" and value["lines"] == []
    assert eng.status()["validation_coverage"][wid]["summary"] == value


def test_coverage_consumers_use_the_runners_cwd_not_a_second_calculation(tmp_path, contained, monkeypatch):
    from aew.policy import checks as C

    p = sample_project(tmp_path)
    wid = prepared(p, tmp_path)
    inv = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    role = Role(p, inv["invocation_token"], Path(integ(p, wid)["workspace"]))
    original = C.run
    marker = "synthetic-runner-cwd-provenance"

    def run(*args, **kwargs):
        # Real execution, but plant distinct returned provenance to catch either consumer recalculating cfg.cwd.
        return {**original(*args, **kwargs), "cwd": marker}

    monkeypatch.setattr(C, "run", run)
    # Engine calls in-process so the planted runner boundary, not a child interpreter, is exercised.
    checked = engine(p).check_run(invocation_token=role.token, check_id="unit")
    assert checked["coverage"]["checks"][0]["cwd"] == marker
    p.lead("invoke", "cancel", inv["invocation"], "--reason", "exercise checks-mode runner provenance next")
    policy(p, checks=SMOKE)
    out = engine(p).integrate_validate(token=p.token, expect_rev=p.rev(), work_id=wid)
    assert out["coverage"]["checks"][0]["cwd"] == marker


def test_coverage_uses_the_pinned_inventory_when_unrelated_policy_changes_during_execution(
        tmp_path, contained, monkeypatch):
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE)
    digest = declare(p, ("pytest", ["smoke"]))
    wid = prepared(p, tmp_path)
    eng = engine(p)
    original = eng._validation._execute

    def execute(work_id, run):
        policy(p, checks={"added-after-pin": {"configured": True, "command": ["{python}", "-c", "pass"]}})
        declare(p, ("replacement", ["added-after-pin"]))
        return original(work_id, run)

    monkeypatch.setattr(eng._validation, "_execute", execute)
    out = eng.integrate_validate(token=p.token, expect_rev=p.rev(), work_id=wid)
    assert out["result"] == "pass"
    assert "added-after-pin" not in {c["check_id"] for c in out["coverage"]["configured_not_run"]}
    pin = integ(p, wid)[VO.CURRENT]["coverage_inputs"]
    inputs = load_yaml((p.root / ".aew" / pin["path"]).read_text(encoding="utf-8"))
    assert "added-after-pin" not in {c["check_id"] for c in inputs["configured"]}
    assert inputs["declaration_pin"]["sha256"] == digest
    assert out["coverage"]["ci_tools"] == {"known": True, "source": f"declared:{digest}",
                                           "items": [{"name": "pytest", "ran": True, "reasons": []}]}


def test_adopting_coverage_is_operational_and_prepare_runs_no_checks(tmp_path):
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE)
    eng = engine(p)
    prior = eng._k.policy_digests()
    check = C.resolve(eng._k.policy("checks"), "smoke")
    declare(p, ("pytest", ["smoke"]),
            affected_tests={"selector": {"command": ["unused-selector"]}, "unit": "lanes"})
    after = eng._k.policy_digests()
    assert after["legality_digest"] == prior["legality_digest"]
    assert after["operational_digest"] != prior["operational_digest"]
    assert C.definition_digest(C.resolve(eng._k.policy("checks"), "smoke")) == C.definition_digest(check)
    wid = prepared(p, tmp_path)
    coverage = engine(p).status(wid)["coverage"]
    assert coverage["checks"] == []
    for key in ("ci_tools", "affected_tests"):
        assert coverage[key] == {"known": False, "reason": "no_checks_in_this_subject"}


def test_check_run_distinguishes_could_not_start_from_ran_and_unconfigured(tmp_path, contained):
    p = sample_project(tmp_path)
    policy(p, checks={"missing": {"configured": True, "command": ["aew-fixture-absent-e243"]},
                      "disabled": {"configured": False}})
    digest = declare(p, ("ruff", ["missing"]), ("pytest", ["unit"]), ("pyright", ["disabled"]))
    wid = prepared(p, tmp_path)
    inv = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    eng = engine(p)
    checked = eng.check_run(invocation_token=inv["invocation_token"], check_id="missing", label={})
    value = checked["coverage"]
    assert value["checks"][0]["outcome"] == "spawn_failed" and value["checks"][0]["exit_code"] is None
    assert value["ci_tools"] == {"known": True, "source": f"declared:{digest}", "items": [
        {"name": "ruff", "ran": False, "reasons": ["could_not_start"]},
        {"name": "pytest", "ran": False, "reasons": ["not_run_in_this_validation"]},
        {"name": "pyright", "ran": False, "reasons": ["not_configured"]}]}
    assert "ci tools not run: 3" in value["summary"]["headline"]
    assert any("1 not configured" in line for line in value["summary"]["lines"])
    assert any("pyright: not run (not configured)" in line for line in value["summary"]["lines"])
    evidence = next(e for e in E.scan(p.root / ".aew", wid)[0] if e["id"] == checked["evidence"])
    assert evidence["check"]["outcome"] == "spawn_failed"
    covered = eng.check_run(invocation_token=inv["invocation_token"], check_id="unit", label={})["coverage"]
    assert covered["ci_tools"]["items"][1] == {"name": "pytest", "ran": True, "reasons": []}
    assert any("per the project's declaration" in line and "pytest: ran (check unit)" in line
               for line in covered["summary"]["lines"])


def test_executor_timeout_is_a_known_tool_gap(tmp_path, contained):
    p = sample_project(tmp_path)
    policy(p, checks={"smoke": {"configured": True, "command": py("import time; time.sleep(10)"), "timeout_s": 1}})
    declare(p, ("pytest", ["smoke"]))
    wid = prepared(p, tmp_path)
    value = validate(p, wid)["coverage"]
    assert value["checks"][0]["outcome"] == "timeout" and value["checks"][0]["exit_code"] is None
    assert value["ci_tools"]["items"] == [{"name": "pytest", "ran": False, "reasons": ["not_completed"]}]


@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                    reason="Linux bubblewrap containment")
def test_plain_validated_requires_both_known_lists_and_all_items_run(tmp_path, monkeypatch):
    from aew.capability import records

    # The sandbox still measures delivery. Give this synthetic project no pinned tools to deliver.
    monkeypatch.setattr(records, "shipped", dict)
    p = sample_project(tmp_path)
    policy(p, checks=SMOKE, post=["unit", "smoke", "guardrails"])
    declare(p, ("pytest", ["unit"]), affected_tests={"selector": {"command": ["unused-selector"]}, "unit": "lanes"})
    wid = prepared(p, tmp_path)
    value = validate(p, wid)["coverage"]
    assert value["run_capabilities"] and all(c["tools_recorded"] and not c["missing_tools"]
                                             for c in value["run_capabilities"].values())
    assert value["ci_tools"]["items"] == [{"name": "pytest", "ran": True, "reasons": []}]
    assert value["affected_tests"] == {"known": False, "reason": "selection_not_run"}
    assert value["summary"]["verdict"] == "validated within its scope"
    # Supply only the PR 2 output shape. The rest of the observation comes from the contained executor.
    value["affected_tests"] = {"known": True, "source": "selection:synthetic", "unit": "lanes", "items": [
        {"name": "fast", "ran": True, "reasons": []}]}
    assert CV.summarize(value)["verdict"] == "validated"
    value["affected_tests"]["items"][0].update(ran=False, reasons=["not_run_in_this_validation"])
    assert CV.summarize(value)["verdict"] == "validated within its scope"


@pytest.mark.parametrize("kind", ["advisory", "unavailable", "abandoned"])
def test_every_terminal_record_keeps_coverage_without_manufacturing_a_validation_pass(tmp_path, contained, kind):
    p = sample_project(tmp_path)
    checks = SMOKE if kind != "unavailable" else {
        "smoke": {"configured": True, "command": ["aew-fixture-no-such-executable-coverage"]}}
    policy(p, checks=checks)
    if kind == "unavailable":
        declare(p, ("pytest", ["smoke"]))
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
    reason = "no_project_source" if kind == "advisory" else "execution_completion_not_recorded"
    for key in ("affected_tests", "ci_tools"):
        assert value[key] == {"known": False, "reason": reason}
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
