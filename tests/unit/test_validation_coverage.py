"""Execution facts, gaps and unknowns are separate; disclosure cannot establish a wider result."""

from __future__ import annotations

import ast
import copy
import json
import sys
from pathlib import Path

import pytest

from aew.engine import coverage as CV
from aew.engine.base import Kernel, check_policy_bytes
from aew.errors import IntegrityError, ValidationFailed
from aew.schemas import validate_property
from aew.util import dump_yaml, sha256_file


def observed():
    return CV.build(subject={"work_id": "T-1", "scope": "integration"}, configured=[], checks=[],
                    changed_files=CV.files([], source="candidate diff"),
                    capabilities={"IV-1": {"recorded": True, "tools_recorded": True, "skills_recorded": True,
                                            "missing_tools": [], "missing_skills": []}}, result="pass")


@pytest.mark.parametrize("gap,unknown", [(True, False), (False, True), (True, True), (False, False)])
def test_known_gap_unknown_both_and_neither_have_one_verdict_rule(gap, unknown):
    value = observed()
    if not unknown:
        for key in ("affected_tests", "ci_tools"):
            value[key] = {"known": True, "source": "synthetic complete source", "items": []}
    if gap:
        value["configured_not_run"] = [{"check_id": "lint", "definition_sha256": "a" * 64, "reason": "not run"}]
    summary = CV.summarize(value)
    assert summary["verdict"] == ("validated within its scope" if gap or unknown else "validated")
    assert summary["known_gaps"]["configured_checks_not_run"] == int(gap)
    assert any("Affected tests: not known" in line for line in summary["lines"]) is unknown


def test_known_unrun_consumer_qualifies_a_pass():
    value = observed()
    value["affected_tests"] = {"known": True, "source": "synthetic selector",
                               "items": [{"name": "tests/test_consumer.py", "ran": False,
                                          "reasons": ["not_run_in_this_validation"]}]}
    value["ci_tools"] = {"known": True, "source": "synthetic CI source", "items": []}
    summary = CV.summarize(value)
    assert summary["verdict"] == "validated within its scope"
    assert summary["known_gaps"]["affected_tests_not_run"] == 1


def test_unknown_is_not_an_empty_inventory():
    value = observed()
    for key in ("affected_tests", "ci_tools"):
        assert value[key] == {"known": False, "reason": "no_project_source"}
        assert f"{key}_not_run" not in value["summary"]["known_gaps"]
    validate_property("evidence", "coverage", value, source="synthetic coverage")


def test_unknowns_do_not_change_known_gap_counts():
    value = observed()
    value["configured_not_run"] = [{"check_id": "lint", "reason": "not run"}]
    unknown = CV.summarize(value)
    for key in ("affected_tests", "ci_tools"):
        value[key] = {"known": True, "source": "synthetic complete source", "items": []}
    known = CV.summarize(value)
    for key in ("configured_checks_not_run", "missing_run_tools", "missing_run_skills"):
        assert unknown["known_gaps"][key] == known["known_gaps"][key]
    assert unknown["known_gaps"]["configured_checks_not_run"] == 1


@pytest.mark.parametrize("result", ["fail", "blocked", "inconclusive", "advisory", "abandoned", "unavailable"])
def test_only_an_actual_pass_has_positive_validation_wording(result):
    value = observed()
    value["result"] = result
    assert "validated" not in CV.summarize(value)["verdict"]


def test_incomplete_execution_does_not_label_unobserved_checks_as_unrun():
    value = CV.build(subject={}, configured=[{"check_id": "unit", "definition_sha256": "a" * 64}], checks=[],
                     changed_files=CV.files(None, source="unavailable"), capabilities={}, result="abandoned",
                     declaration_pin={"sha256": "f" * 64, "declaration": {"ci_tools": [
                         {"name": "ruff", "covered_by": []}]}}, complete=False)
    assert value["configured_not_run"] == []
    assert "execution_completion_not_recorded" in value["observation_limits"]
    for key in ("ci_tools", "affected_tests"):
        assert value[key] == {"known": False, "reason": "execution_completion_not_recorded"}


def test_build_sites_are_exhaustive():
    source = Path(CV.__file__).resolve().parents[1]
    counts = {}
    for path in source.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "CV" not in text:
            continue
        calls = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == "build"
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == "CV"]
        if calls:
            counts[path.relative_to(source).as_posix()] = len(calls)
    assert counts == {"engine/evidence_ops.py": 2, "engine/integration_ops.py": 2, "engine/validation_ops.py": 3}
    assert sum(counts.values()) == 7


@pytest.mark.parametrize("check_id", ["unit", "guardrails", "unknown"])
def test_coverage_policy_names_configured_ids_or_builtin(check_id):
    policy = {"schema": "aew/checks/v1", "checks": {"unit": {"configured": False}}, "coverage": {
        "ci_tools": [{"name": "pytest", "covered_by": [check_id]}],
        "affected_tests": {"selector": {"command": ["selector"]}, "unit": "lanes"}}}
    raw = dump_yaml(policy).encode()
    if check_id == "unknown":
        with pytest.raises(ValidationFailed, match="covered_by.*unknown checks"):
            check_policy_bytes("checks", raw, source="checks.yaml")
    else:
        assert check_policy_bytes("checks", raw, source="checks.yaml") == policy


@pytest.mark.parametrize("ci_signal", ["none", "workflows", "map-role"])
def test_doctor_checks_each_declaration_and_names_uncovered_tools(tmp_path, monkeypatch, ci_signal):
    from types import SimpleNamespace

    from aew.workspace import git

    if ci_signal == "workflows":
        (tmp_path / ".github/workflows").mkdir(parents=True)
    stdout = b"config/.circleci/config.yml\0" if ci_signal == "map-role" else b"README.md\0"
    monkeypatch.setattr(git, "git", lambda *args, **kwargs: SimpleNamespace(stdout=stdout))
    policy = {"checks": {"lint": {"configured": False}}, "coverage": {"ci_tools": [
        {"name": "ruff", "covered_by": ["lint"]}, {"name": "guardrails", "covered_by": ["guardrails"]}]}}
    tools, selection, uncovered = CV.doctor_rows(policy, policy["coverage"], tmp_path)
    assert tools == ("PASS", "Project CI tools: declared")
    assert selection[0] == ("PASS" if ci_signal == "none" else "WARN")
    assert "Affected tests" in selection[1] and "not known" in selection[1]
    assert uncovered == ("WARN", "CI runs ruff; no configured check runs it")
    missing_tools, missing_selection = CV.doctor_rows({"checks": {}}, {}, tmp_path)
    assert missing_tools[0] == missing_selection[0] == selection[0]


def test_legacy_unpinned_checks_policy_is_not_a_declaration_source(tmp_path, monkeypatch):
    checks = "policy/checks.yaml"
    raw = b"schema: aew/checks/v1\nchecks: {}\ncoverage: {ci_tools: []}\n"
    kernel = Kernel(tmp_path, tmp_path)
    monkeypatch.setattr(Kernel, "manifest", property(lambda self: {"policy": {"checks": checks}}))
    monkeypatch.setattr(kernel, "_pins_in_force", lambda: None)
    (tmp_path / "policy").mkdir()
    (tmp_path / checks).write_bytes(raw)
    policy, declaration = CV.checks_at_pin(kernel)
    assert policy["coverage"] == {"ci_tools": []}
    assert declaration is None


def test_a_bounded_summary_keeps_unknowns_after_long_observed_lists_and_sanitizes_values():
    value = observed()
    value["checks"] = [{"check_id": "unit", "command": ["界" * 2000 + "\x1b\nforged"], "cwd": ".",
                        "evaluated_snapshot": {"relevant_inputs_fingerprint": "snapshot"}, "result": "pass"}] * 100
    summary = CV.summarize(value)
    assert len([li for li in summary["lines"] if li.startswith("Check ")]) == CV.SUMMARY_ITEMS
    assert any("90 more" in li for li in summary["lines"])
    assert any("Affected tests: not known" in li for li in summary["lines"])
    assert any("Project CI tools: not known" in li for li in summary["lines"])
    assert all("\n" not in li and "\x1b" not in li for li in summary["lines"])


def test_record_pins_survive_workspace_removal_and_project_summaries_do_not_read_records(tmp_path):
    value = observed()
    path = tmp_path / "run.yaml"
    path.write_text(dump_yaml({"coverage": value}), encoding="utf-8")
    pin = CV.pin("run.yaml", sha256_file(path), value)
    unit = {"integration": {"coverage": pin}}
    assert CV.for_unit(tmp_path, unit, full=True) == value
    summary = copy.deepcopy(CV.for_unit(tmp_path, unit))
    path.unlink()
    assert CV.for_unit(tmp_path, unit) == summary
    with pytest.raises(IntegrityError):
        CV.for_unit(tmp_path, unit, full=True)
    assert CV.for_unit(tmp_path, {}, full=True)["summary"]["headline"] == "Validation: not yet validated"
    assert "legacy record" in CV.for_unit(tmp_path, {"last_verification": {"result": "pass"}}, full=True)["summary"][
        "headline"]


@pytest.mark.parametrize("kind", ["tools", "skills"])
def test_unknown_delivery_never_prints_a_known_zero_or_counts_unrecorded_lists(kind):
    value = observed()
    value["run_capabilities"]["IV-1"][f"{kind}_recorded"] = False
    value["run_capabilities"]["IV-1"][f"missing_{kind}"] = [{"untrusted": "not a recorded fact"}]
    summary = CV.summarize(value)
    assert f"missing_run_{kind}" not in summary["known_gaps"]
    assert f"missing run {kind}: not known" in summary["headline"]
    value["run_capabilities"] = {}
    summary = CV.summarize(value)
    assert "missing_run_tools" not in summary["known_gaps"]
    assert "missing_run_skills" not in summary["known_gaps"]
    assert "missing run tools: not known; missing run skills: not known" in summary["headline"]


def test_partial_delivery_keeps_recorded_gaps_without_claiming_a_complete_count():
    value = observed()
    value["run_capabilities"]["IV-1"]["missing_tools"] = [{"command": "rg", "got": "stub", "why": "declined"}]
    value["run_capabilities"]["IV-2"] = {"tools_recorded": False, "skills_recorded": False}
    summary = CV.summarize(value)
    assert summary["known_gaps"]["missing_run_tools"] == 1
    assert "missing run tools: not known (recorded gaps: 1)" in summary["headline"]


def test_total_summary_utf8_budget_preserves_the_inventory_unknowns():
    value = observed()
    long = "界" * 2000
    value["checks"] = [{"check_id": long, "result": long, "command": [long], "cwd": long,
                        "evaluated_snapshot": {"relevant_inputs_fingerprint": long}}] * 100
    value["configured_not_run"] = [{"check_id": long, "reason": long}] * 100
    summary = CV.summarize(value)
    assert len(json.dumps(summary, ensure_ascii=False).encode("utf-8")) <= CV.SUMMARY_BYTES
    assert any("byte budget" in line for line in summary["lines"])
    assert any("Affected tests: not known" in line for line in summary["lines"])
    assert any("Project CI tools: not known" in line for line in summary["lines"])


def test_summary_uses_no_host_local_argv_or_cwd_and_single_checks_are_not_ticket_validation(tmp_path):
    value = observed()
    value["subject"]["scope"] = "check"
    value["checks"] = [{"check_id": "unit", "result": "pass", "command": [sys.executable, str(tmp_path / "test.py")],
                        "cwd": str(tmp_path), "evaluated_snapshot": {}}]
    summary = CV.summarize(value)
    assert summary["headline"].startswith("Check: pass within its recorded scope;")
    assert sys.executable not in str(summary) and str(tmp_path) not in str(summary)
    assert f"Python {sys.version.split()[0]}" in str(summary)


def test_missing_changed_paths_have_a_reason_not_the_source_label():
    assert CV.files(None, source="candidate_diff_from:abc", reason="candidate_diff_not_recorded") == {
        "known": False, "reason": "candidate_diff_not_recorded"}
