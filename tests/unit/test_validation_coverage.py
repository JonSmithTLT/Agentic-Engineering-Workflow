"""Execution facts, gaps and unknowns are separate; disclosure cannot establish a wider result."""

from __future__ import annotations

import copy

import pytest

from aew.engine import coverage as CV
from aew.errors import IntegrityError
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
                               "items": [{"name": "tests/test_consumer.py", "ran": False}]}
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
                     complete=False)
    assert value["configured_not_run"] == []
    assert "execution_completion_not_recorded" in value["observation_limits"]


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
    assert "legacy record" in CV.for_unit(tmp_path, {}, full=True)["summary"]["headline"]
