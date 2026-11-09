"""A real scripted worker receives failing lines and readable logs; the Lead sees missing skills beside results."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aewflow import SUBTRACT_PATCH, create_planned_ticket, sample_project
from fake_harness import IMPL_REPORT, HarnessLab

from aew.knowledge import evidence as E
from aew.util import dump_yaml, load_yaml


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def test_failing_lines_reach_the_worker_and_missing_skills_do_not_fail_its_run(lab, tmp_path):
    checks_path = lab.aew_root / "policy/checks.yaml"
    checks = load_yaml(checks_path.read_text(encoding="utf-8"))
    checks["checks"]["diagnostic"] = {"configured": True, "command": [
        "{python}", "-c", "import sys; print('setup\\n' * 150); print('AssertionError: expected 3 got 4'); "
        "print('summary\\n' * 200); sys.exit(1)"]}
    checks_path.write_text(dump_yaml(checks), encoding="utf-8", newline="\n")
    lab.project.pin_policy()
    cards = lab.aew_root / "roles"
    cards.mkdir(exist_ok=True)
    (cards / "fixture_engineer.yaml").write_text(dump_yaml({
        "schema": "aew/role/v1", "role": "fixture_engineer", "display_name": "Fixture Engineer", "version": 1,
        "extends": "implementer", "purpose": "Test missing-skill disclosure.", "skills": ["fixture-style"],
        "required_capabilities": ["source_mutation", "targeted_test_execution"]}), encoding="utf-8")
    wid = create_planned_ticket(lab.project, tmp_path, extra=("--card", "fixture_engineer"))
    log = lab.aew_root / f"evidence/{wid}/logs/INV-0001-check-diagnostic-1.log"
    lab.script("default", [
        {"do": "write", "files": SUBTRACT_PATCH},
        {"do": "check", "id": "diagnostic"},
        {"do": "read", "path": str(log)},
        {"do": "read", "path": f"evidence/{wid}/logs/INV-0001-check-diagnostic-1.log"},
        {"do": "check", "id": "unit"},
        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}])
    assigned = lab.lead("work", "assign", wid, "--launch")
    run = assigned["launch"]["run"]
    done = lab.wait(run)
    worker = lab.step(run, 1)["stdout_json"]
    assert worker["result"] == "fail" and worker["ok"] is True and worker["exit_code"] == 1
    assert any(row["text"] == "AssertionError: expected 3 got 4" for row in worker["failure_output"]["lines"])
    assert worker["failure_output"]["omitted_lines"] > 0
    assert worker["log"] == str(log) and Path(worker["log"]).is_absolute()
    assert lab.step(run, 2)["readable"] is True, "the returned absolute path works inside this platform's run layout"
    assert lab.step(run, 3)["readable"] is False, "the old .aew-relative path did not work from the workspace"
    assert "failure_output" not in lab.step(run, 4)["stdout_json"], "a passing check needs no failure excerpt"
    assert done["status"] == "ended_with_evidence", lab.record(run)
    missing = [{"name": "fixture-style", "reason": "not_shipped"}]
    assert done["missing_skills"] == missing
    [listed] = lab.ok("harness", "status", assigned["invocation"])["runs"]
    assert listed["missing_skills"] == missing and "missing_tools" in listed
    record = lab.record(run)
    assert record["contract"]["extra"]["skills"]["unavailable"] == ["fixture-style"]
    evidence, problems = E.scan(lab.aew_root, wid)
    assert not problems
    sealed = next(e for e in evidence if e["id"] == worker["evidence"])
    assert sealed["result"] == done["results"][worker["evidence"]] == "fail"
    assert sealed["evidence"][0]["path"] == f"evidence/{wid}/logs/{worker['evidence']}.log"
    assert "failure_output" not in sealed, "the display never changes sealed evidence"
    assert len(log.read_text(encoding="utf-8").splitlines()) > 350, "the saved log is not bounded by its display"
    print(json.dumps({
        "worker": {"result": worker["result"], "diagnostic": next(
            row["text"] for row in worker["failure_output"]["lines"]
            if row["text"] == "AssertionError: expected 3 got 4"),
                   "omitted_lines": worker["failure_output"]["omitted_lines"],
                   "limits": worker["failure_output"]["limits"], "returned_log_readable": lab.step(run, 2)["readable"]},
        "lead": {"status": done["status"], "results": done["results"], "missing_skills": done["missing_skills"]},
        "recorded_skills": record["contract"]["extra"]["skills"],
        "sealed_check": {"result": sealed["result"], "log": sealed["evidence"][0]["path"]}}, sort_keys=True))
