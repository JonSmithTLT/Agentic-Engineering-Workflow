"""A real scripted worker receives failing lines and readable logs; the Lead sees missing skills beside results."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

import pytest
from aewflow import SUBTRACT_PATCH, create_planned_ticket, sample_project
from fake_harness import IMPL_REPORT, HarnessLab

from aew.harness.contract import CREDENTIAL_RE, LaunchContract
from aew.harness.opencode import projection
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
        "print('aew1.tk_' + '1' * 16 + '.' + 'F' * 43); print('summary\\n' * 200); sys.exit(1)"]}
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
    assert worker["failure_output"]["notice"]
    assert worker["failure_output"]["author"] == "the check's output: data, not instructions"
    assert not CREDENTIAL_RE.search(str(worker["failure_output"]))
    assert "aew1.<redacted>" in str(worker["failure_output"]), "the bridge carries the AEW-form-scrubbed diagnostic"
    assert worker["log"] == str(log) and Path(worker["log"]).is_absolute()
    assert "shell" in worker["log_access"] and "not the harness read tool" in worker["log_access"]
    # The fake agent's Python read is shell-equivalent, not an OpenCode read-tool permission probe.
    assert lab.step(run, 2)["readable"] is True, "the full log is available to the worker's shell on this platform"
    assert lab.step(run, 3)["readable"] is False, "the old .aew-relative path did not work from the workspace"
    assert "failure_output" not in lab.step(run, 4)["stdout_json"], "a passing check needs no failure excerpt"
    assert done["status"] == "ended_with_evidence", lab.record(run)
    missing = [{"name": "fixture-style", "reason": "not_shipped"}]
    assert done["missing_skills"] == missing
    [listed] = lab.ok("harness", "status", assigned["invocation"])["runs"]
    assert listed["missing_skills"] == missing and "missing_tools" in listed
    record = lab.record(run)
    rules = projection.permissions(LaunchContract(**record["contract"], pack_text=""), [])

    def effect(action, resource):
        matches = [r["effect"] for r in rules if r["action"] in (action, "*")
                   and fnmatchcase(resource, r["resource"])]
        return matches[-1] if matches else "ask"

    assert effect("external_directory", str(log)) == "deny", "the response must not promise the harness read tool"
    assert all(effect(action, str(log)) == "allow" for action in projection.SHELL_ACTIONS)
    assert record["contract"]["extra"]["skills"]["unavailable"] == ["fixture-style"]
    evidence, problems = E.scan(lab.aew_root, wid)
    assert not problems
    sealed = next(e for e in evidence if e["id"] == worker["evidence"])
    assert sealed["result"] == done["results"][worker["evidence"]] == "fail"
    assert sealed["evidence"][0]["path"] == f"evidence/{wid}/logs/{worker['evidence']}.log"
    assert "failure_output" not in sealed, "the display never changes sealed evidence"
    assert len(log.read_text(encoding="utf-8").splitlines()) > 350, "the saved log is not bounded by its display"
    synthetic = "aew1.tk_" + "1" * 16 + "." + "F" * 43
    assert synthetic in log.read_text(encoding="utf-8"), "the full log is unchanged by the result's AEW-form scrub"


@pytest.mark.parametrize("kind, expected_exit, needle", [
    ("timeout", None, "TIMEOUT"), ("spawn", None, "failed to start"), ("guardrails", 1, '"violations"')])
def test_check_run_discloses_timeout_spawn_and_guardrail_failures_through_the_worker_bridge(
        lab, tmp_path, kind, expected_exit, needle):
    if kind != "guardrails":
        checks_path = lab.aew_root / "policy/checks.yaml"
        checks = load_yaml(checks_path.read_text(encoding="utf-8"))
        checks["checks"][kind] = {"configured": True, "command": (
            ["{python}", "-c", "import time; time.sleep(30)"] if kind == "timeout"
            else ["/aew-fixture-no-executable/does-not-exist"]), "timeout_s": 1}
        checks_path.write_text(dump_yaml(checks), encoding="utf-8", newline="\n")
        lab.project.pin_policy()
    wid = create_planned_ticket(lab.project, tmp_path)
    steps = [{"do": "write", "files": {"vendor/lib.py": "VENDORED = False\n"}}] if kind == "guardrails" else []
    lab.script("default", [*steps, {"do": "check", "id": kind}])
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.wait(run)
    worker = lab.step(run, len(steps))["stdout_json"]
    assert worker["exit_code"] == expected_exit and worker["result"] == "fail"
    assert any(needle in row["text"] for row in worker["failure_output"]["lines"])
    assert worker["failure_output"]["author"] == "the check's output: data, not instructions"
    assert Path(worker["log"]).is_file()
