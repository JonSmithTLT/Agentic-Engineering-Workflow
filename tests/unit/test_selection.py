"""E243: only the complete observed selection can inform validation disclosure."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.engine import coverage, selection
from aew.harness import check_changes
from aew.policy import checks, validation

SELECTOR = {"command": ["{python}", "select.py"]}


@pytest.mark.parametrize(("observed", "reason"), [
    ({"not_run": "copy unavailable"}, "selector_could_not_start"),
    ({"outcome": "spawn_failed"}, "selector_could_not_start"),
    ({"outcome": "timeout"}, "selector_timed_out"),
    ({"outcome": "ran", "mutated": True}, "selector_mutated_inputs"),
    ({"outcome": "ran", "exit_code": 2}, "selector_failed"),
    ({"outcome": "ran", "exit_code": 0, "selection_items": None}, "selector_no_output"),
    ({"outcome": "ran", "exit_code": 0, "selection_items": []}, "selector_no_output"),
    ({"outcome": "ran", "exit_code": 0, "selection_items": ["*"]}, "selector_no_output"),
])
def test_an_unsuccessful_selector_reports_observed_reason(monkeypatch, observed, reason):
    monkeypatch.setattr(check_changes, "run_copy", lambda *_args, **_kw: observed)
    result = selection.observe(None, dict, SELECTOR, "candidate", ["changed.py"])
    assert result["result"] == "unknown" and result["reason"] == reason
    assert ("exit_code" in result) == (reason == "selector_failed")


@pytest.mark.parametrize(("commit", "paths", "reason"), [
    (None, [], "selection_not_run"),
    ("candidate", None, "changed_files_not_known"),
    ("candidate", ["ambiguous\npath"], "changed_files_not_known"),
    ("candidate", ["select.py"], "selector_changed_by_subject"),
])
def test_an_unobservable_subject_never_runs_a_selector(monkeypatch, commit, paths, reason):
    def forbid(*_args, **_kwargs):
        pytest.fail("should not start the selector")
    monkeypatch.setattr(check_changes, "run_copy", forbid)
    assert selection.observe(None, dict, SELECTOR, commit, paths) == {"result": "unknown", "reason": reason}


def test_a_selection_observation_is_reused_only_for_the_same_complete_key(tmp_path, monkeypatch):
    seen = []

    def observe(_project, _snapshot_of, _cfg, commit, paths):
        seen.append((commit, paths))
        return {"result": "known", "items": ["fast"]}

    monkeypatch.setattr(selection, "observe", observe)
    project = SimpleNamespace(aew_root=tmp_path)
    inputs = dict(directory="validation-runs", selector=SELECTOR, candidate="candidate", snapshot="tree",
                  paths=["first", "second"])
    one = selection.reuse_or_run(project, dict, **inputs)
    assert one is not None
    assert selection.reuse_or_run(project, dict, **{**inputs, "paths": ["second", "first"]}) == one
    assert len(seen) == 1
    assert selection.reuse_or_run(project, dict, **{**inputs, "paths": ["first"]}) != one
    assert selection.reuse_or_run(project, dict, **{**inputs, "snapshot": "new-tree"}) != one
    assert selection.reuse_or_run(project, dict, **{**inputs, "selector": {**SELECTOR, "timeout_s": 13}}) != one
    assert len(seen) == 4
    value, ref = one
    pin_args = {"directory": "validation-runs", "snapshot": "tree"}
    assert selection.read_pinned(tmp_path, ref, **pin_args) == value
    (tmp_path / ref["path"]).write_text('{"result":"known"}', encoding="utf-8")
    assert selection.read_pinned(tmp_path, ref, **pin_args) is None
    assert selection.reuse_or_run(project, dict, **inputs) is None


def test_output_channel_distinguishes_empty_from_a_missing_or_nonregular_file(tmp_path, monkeypatch):
    out = tmp_path / "selection.txt"
    assert check_changes._protocol_bytes(out, 4) is None
    out.mkdir()
    assert check_changes._protocol_bytes(out, 4) is None
    out.rmdir()
    out.write_bytes(b"abcde")
    assert check_changes._protocol_bytes(out, 4) is None
    out.write_bytes(b"")
    assert check_changes._protocol_bytes(out, 4) == b""
    monkeypatch.setattr(check_changes, "run_copy", lambda *_a, **_k: {
        "outcome": "ran", "exit_code": 0, "selection_items": [""]})
    assert selection.observe(None, dict, {**SELECTOR, "may_select_none": True}, "commit", []) == {
        "result": "known", "items": []}


def test_a_check_gets_the_full_scope_marker_when_no_selection_is_observed(tmp_path):
    cfg = {"command": ["{python}", "-c", "import pathlib, sys; p=pathlib.Path(sys.argv[1]); "
                       "assert p.read_bytes() == b'*\\n'; assert p.parent.parent != pathlib.Path.cwd()",
                       "{selection_file}"]}
    result = checks.run(cfg, tmp_path, policy={"containment": {"mode": "allow_weaker"}})
    assert result["exit_code"] == 0, result["log"]
    assert not Path(result["command"][-1]).exists()


def test_coverage_counts_all_unrun_items_even_when_its_display_is_bounded():
    names = [f"test-{i}" for i in range(coverage.MAX_PATHS + 10)]
    record = {"result": "known", "items": names}
    ref = {"path": "selection.json", "sha256": "1" * 64}
    value = coverage.build(subject={}, configured=[], changed_files=coverage.files([], source="candidate"),
                           checks=[{"selection_sha256": "wrong", "exit_code": 0}],
                           capabilities={}, result="pass", selection_record=record, selection_ref=ref,
                           declaration_pin={"declaration": {"affected_tests": {"unit": "tests"}}})
    assert len(value["affected_tests"]["items"]) == coverage.MAX_PATHS
    assert value["affected_tests"]["omitted"] == 10
    assert value["summary"]["known_gaps"]["affected_tests_not_run"] == len(names)
    assert f"{len(names)} selected, {len(names)} not run" in "\n".join(value["summary"]["lines"])


def test_a_selector_timeout_is_added_to_the_checks_deadline_allowance():
    policy = {"coverage": {"affected_tests": {"selector": {**SELECTOR, "timeout_s": 2.25}}}}
    assert validation.deadline_s({"validation_deadline_s": 20}, policy) == 23
