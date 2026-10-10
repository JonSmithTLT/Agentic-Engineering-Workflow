"""The raw arm's configuration, the profile check and the profile records (register F19; agent-effectiveness adoption,
delta D3: the lower-bound qualification lane).

A raw cell is refused before anything is counted when its case has no task, its configuration is incomplete (a
session database kept with no retention window or no field list is refused: Revision C has no default), its
provider variable is missing, or it would run a model other than its role's pinned one. A model the run did not pin
makes the measurement invalid. A profile record's qualification state is derived, never asserted.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import arms, fixture, prereg, profiles, runner  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

RAW = {"role": "worker", "model": "fakeprov/fake-model", "steps": 5, "cap_usd": 0.5, "provider_env": [],
       "session_db": {"retain": True, "retention_days": 30, "fields": ["tool.name", "tool.input.path"]}}


def make_case(root: Path, *, task: str | None = "Fix add() in calc.py.") -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    manifest = {"schema": "aew/eval-case/v1", "id": "C1", "family": "demo", "fixture": {"base": "base"},
                "hidden_sha256": None, "control_of": None, **({"task": task} if task is not None else {})}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def plan_for(case_path: Path, config: dict, *, roles: dict | None = None, **over) -> dict:
    case = fixture.load(case_path)
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "lbq-demo", "question": "Does the profile show the behaviours?",
        "purpose": "qualification",
        "arms": [{"id": "raw", "kind": "raw", "description": "harness alone", "config": config}],
        "cases": [{"id": case.id, "family": "demo", "sha256": fixture.case_sha256(case), "hidden_sha256": None,
                   "control_of": None}],
        "profiles": {"roles": roles or {"worker": "fakeprov/fake-model"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "behaviours shown", "metrics": [{"name": "behaviours", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [],
        "scoring": {"hidden_channel": "none", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "n/a", "amendment_policy": "a change is a new id",
    }
    record.update(over)
    return prereg.freeze(record, by="tester")


def refused(tmp_path: Path, case_path: Path, f: dict, match: str) -> None:
    with pytest.raises(runner.Refused, match=match):
        runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                        cases={"C1": case_path}, work=tmp_path / "work", run_name="r1")
    assert not (tmp_path / "ledger" / "attempts.jsonl").exists()  # nothing counted


def without(config: dict, *path: str) -> dict:
    out = copy.deepcopy(config)
    node = out
    for key in path[:-1]:
        node = node[key]
    node.pop(path[-1])
    return out


def with_(config: dict, value, *path: str) -> dict:
    out = copy.deepcopy(config)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


def test_a_case_task_and_a_qualification_purpose_are_schema_fields():
    validate("aew/eval-case/v1", {"schema": "aew/eval-case/v1", "id": "C1", "family": "f", "task": "do it",
                                  "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None})
    with pytest.raises(Invalid):
        validate("aew/eval-case/v1", {"schema": "aew/eval-case/v1", "id": "C1", "family": "f", "task": "",
                                      "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None})


def test_a_task_is_hashed_with_the_case_so_a_changed_prompt_is_a_changed_case(tmp_path):
    a = fixture.case_sha256(fixture.load(make_case(tmp_path / "a", task="Fix add().")))
    b = fixture.case_sha256(fixture.load(make_case(tmp_path / "b", task="Fix add() and sub().")))
    assert a != b


def test_a_preregistration_purpose_is_qualification_or_treatment_effect_only(tmp_path):
    case_path = make_case(tmp_path / "case")
    assert plan_for(case_path, RAW)["purpose"] == "qualification"
    with pytest.raises(Invalid, match="purpose"):
        plan_for(case_path, RAW, purpose="exploration")


@pytest.mark.parametrize("config, match", [
    (with_(RAW, "fakeprov", "model"), "provider/model"),
    (with_(RAW, 2.5, "steps"), "whole number"),
    (with_(RAW, 0, "cap_usd"), "positive number"),
    (with_(RAW, "OPENAI_API_KEY", "provider_env"), "list of environment variable names"),
    (with_(RAW, ["AEW_LEAD_TOKEN"], "provider_env"), "never reach a harness"),
    (without(RAW, "role"), "names the role"),
    (with_(RAW, False, "session_db", "retain"), "keeps its harness session database"),
    (without(RAW, "session_db", "retention_days"), "retention window has no default"),
    (with_(RAW, [], "session_db", "fields"), "non-empty list"),
])
def test_an_incomplete_raw_configuration_is_refused_before_anything_is_counted(tmp_path, config, match):
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, config), match)


def test_a_raw_cell_whose_case_has_no_task_is_refused(tmp_path):
    case_path = make_case(tmp_path / "case", task=None)
    refused(tmp_path, case_path, plan_for(case_path, RAW), "has no task")


def test_a_missing_provider_variable_is_refused_and_its_value_is_never_needed_to_say_so(tmp_path, monkeypatch):
    monkeypatch.delenv("FAKEPROV_TEST_KEY", raising=False)
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, with_(RAW, ["FAKEPROV_TEST_KEY"], "provider_env")),
            "FAKEPROV_TEST_KEY is not set")


def test_a_raw_arm_never_runs_a_model_other_than_its_roles_pinned_one(tmp_path):
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, RAW, roles={"worker": "fakeprov/other-model"}),
            "pins worker to 'fakeprov/other-model'")


@pytest.mark.parametrize("observed, expected", [
    ([], None),
    ([{"role": "worker", "provider": "opencode", "model": "m-1", "effort": None}], False),
    ([{"role": "worker", "provider": "opencode", "model": "m-2", "effort": None}], True),
    ([{"role": "reviewer", "provider": "opencode", "model": "m-1", "effort": None}], True),
])
def test_a_model_the_preregistration_did_not_pin_is_a_mismatch(observed, expected):
    assert runner.profile_mismatch({"worker": "opencode/m-1"}, observed) is expected


def test_an_unreported_effort_never_matches_a_pinned_effort():
    pinned = {"worker": "openai/m#high"}
    assert runner.profile_mismatch(pinned, [{"role": "worker", "provider": "openai", "model": "m",
                                             "effort": "high"}]) is False
    assert runner.profile_mismatch(pinned, [{"role": "worker", "provider": "openai", "model": "m", "effort": None,
                                             "effort_unreported": True}]) is True


def test_a_mismatched_or_self_invalidated_raw_run_is_counted_but_not_valid(tmp_path, monkeypatch):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, RAW)
    outcomes = iter([arms.ArmResult(observed_profiles=[{"role": "worker", "provider": "fakeprov",
                                                        "model": "cheaper-model", "effort": None}]),
                     arms.ArmResult(observed_profiles=[{"role": "worker", "provider": "fakeprov",
                                                        "model": "fake-model", "effort": None}],
                                    invalid="PROVIDER_KEY_RETAINED")])
    seen_tasks = []

    def fake_run(self, repo, config, *, deadline_s, task=None):
        seen_tasks.append(task)
        return next(outcomes)

    monkeypatch.setattr(arms.RawArm, "run", fake_run)
    first = runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                            cases={"C1": case_path}, work=tmp_path / "work", run_name="r1")
    assert first["validity"] == {"status": "invalid_measurement", "reason_code": "PROFILE_MISMATCH"}
    assert first["profile"]["mismatch"] is True
    second = runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                             cases={"C1": case_path}, work=tmp_path / "work", run_name="r1b", retry_of="lbq-demo/r1")
    assert second["validity"] == {"status": "invalid_measurement", "reason_code": "PROVIDER_KEY_RETAINED"}
    assert second["profile"]["mismatch"] is False
    assert seen_tasks == ["Fix add() in calc.py."] * 2  # the case's task, verbatim


@pytest.mark.parametrize("leaked, steps, reason", [
    ([], 12, None), (["harness/x.log"], 12, "PROVIDER_KEY_RETAINED"), ([], 0, "NO_MODEL_STEP"),
    ([], None, "NO_MODEL_STEP"), (["harness/x.log"], 0, "PROVIDER_KEY_RETAINED")])
def test_a_raw_run_with_a_retained_secret_or_no_model_step_is_not_a_measurement(leaked, steps, reason):
    assert arms.raw_invalid(leaked=leaked, steps=steps) == reason


def test_retained_state_is_scanned_for_a_provider_value(tmp_path):
    (tmp_path / "harness" / "x").mkdir(parents=True)
    (tmp_path / "harness" / "x" / "log.txt").write_bytes(b"value=provider-value-under-test end")
    (tmp_path / "clean.txt").write_text("nothing here", encoding="utf-8")
    assert arms.files_holding(tmp_path, [b"provider-value-under-test"]) == ["harness/x/log.txt"]


# ---------------------------------------------------------------------------------------------- profile records

PROFILE = {
    "schema": "aew/eval-profile/v1", "id": "lb-demo", "class": "lower-bound", "ref": "opencode/demo-free",
    "provider": "opencode", "model": "demo-free", "effort": None, "plan_role": "primary", "twin_of": None,
    "harness": {"name": "opencode", "version": "2.0.18", "artifact_sha256": None},
    "effective_profile": {"context.orientation": None, "tools.presentation": None},
    "credential_env": [], "cost_per_mtok_usd": {"input": 0, "output": 0, "source": "catalog"},
    "availability": {"checked_at": "2026-10-10", "offered_by_pinned_harness": True},
    "floor": {"state": "not_run"}, "ceiling": {"state": "not_run"}, "qualification_state": "unqualified",
}


def profile(**over) -> dict:
    record = copy.deepcopy(PROFILE)
    for key, value in over.items():
        record[key] = value
    return record


@pytest.mark.parametrize("over, state", [
    ({}, "unqualified"),
    ({"availability": {"checked_at": None, "offered_by_pinned_harness": None}}, "unqualified"),
    ({"availability": {"checked_at": "2026-10-10", "offered_by_pinned_harness": False,
                       "catalog_status": "deprecated"}}, "unavailable"),
    ({"floor": {"state": "failed"}}, "floor_failed"),
    ({"floor": {"state": "passed"}}, "floor_passed"),
    ({"floor": {"state": "passed"}, "ceiling": {"state": "none_shown"}}, "not_a_lower_bound"),
    ({"floor": {"state": "passed"}, "ceiling": {"state": "behaviours_shown", "behaviours": ["repeated_exploration"]}},
     "qualified"),
    ({"class": "mid", "floor": {"state": "passed"}, "ceiling": {"state": "not_applicable"}}, "floor_passed"),
])
def test_a_profile_state_is_derived_from_its_availability_floor_and_ceiling(over, state):
    record = profile(**over, qualification_state=state)
    profiles.check(record)
    assert profiles.derive_state(record) == state


@pytest.mark.parametrize("over, match", [
    ({"qualification_state": "qualified"}, "establish unqualified"),
    ({"ceiling": {"state": "behaviours_shown", "behaviours": ["x"]}, "qualification_state": "qualified"},
     "needs a passed floor"),
    ({"floor": {"state": "passed"}, "ceiling": {"state": "behaviours_shown"}, "qualification_state": "qualified"},
     "names the behaviours"),
    ({"class": "mid", "floor": {"state": "passed"}, "ceiling": {"state": "none_shown"},
      "qualification_state": "floor_passed"}, "only a lower-bound profile"),
    ({"ref": "opencode/other-free"}, "is not its provider, model and effort"),
    ({"credential_env": ["sk-a-value"]}, "credential_env"),
])
def test_a_profile_record_that_contradicts_itself_is_refused(over, match):
    with pytest.raises(Invalid, match=match):
        profiles.check(profile(**over))


def test_a_profiles_file_has_unique_ids_and_known_twins(tmp_path):
    path = tmp_path / "profiles.yaml"
    twin = profile(id="lb-demo-paid", ref="opencode/demo", model="demo", plan_role="paid-twin", twin_of="lb-demo",
                   credential_env=["OPENCODE_API_KEY"])
    path.write_text(yaml.safe_dump([profile(), twin]), encoding="utf-8")
    assert [r["id"] for r in profiles.load(path)] == ["lb-demo", "lb-demo-paid"]
    path.write_text(yaml.safe_dump([twin]), encoding="utf-8")
    with pytest.raises(Invalid, match="twin of lb-demo"):
        profiles.load(path)
    path.write_text(yaml.safe_dump([profile(), profile()]), encoding="utf-8")
    with pytest.raises(Invalid, match="duplicate"):
        profiles.load(path)
