"""A launch that cannot work is refused up front, naming the cause and the fix, and `aew doctor` names the same before
any launch (ADR-0010 amendment 2026-10-11; the M4 user acceptance test): a provider variable the policy names that is
not set where AEW launches, and a model id that maps to no provider/model pair. Synthetic names and ids only; the fake
harness runs every launch."""

from __future__ import annotations

import pytest
from aewflow import create_planned_ticket, sample_project
from fake_harness import POLICY, HarnessLab

from aew.harness import runlog
from aew.util import dump_yaml, load_yaml

KEY = "AEWTEST_PROVIDER_KEY"  # synthetic: never a real provider's variable


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy={**POLICY, "provider_env": [KEY]})
    yield lab
    lab.cleanup()


def edit_policy(lab: HarnessLab, **changes) -> None:
    path = lab.aew_root / "policy/execution.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    policy.update(changes)
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    lab.project.pin_policy()


def doctor(lab: HarnessLab, env: dict[str, str] | None = None) -> dict[str, dict[str, str]]:
    res = lab.aew("doctor", "--json", env=env)
    return {c["check"]: c for c in res.json["checks"]}


def runs(lab: HarnessLab) -> list[str]:
    parent = runlog.run_dir(lab.aew_root, "x").parent
    return sorted(d.name for d in parent.glob("R-*")) if parent.is_dir() else []


def test_a_launch_with_an_unset_provider_variable_is_refused_naming_it_before_anything_is_committed(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    rev = lab.project.rev()
    res = lab.lead_res("work", "assign", wid, "--launch")
    assert res.returncode != 0 and res.error["code"] == "HARNESS_INCOMPATIBLE", res.error
    assert f"set {KEY} in the terminal you launch AEW from" in res.error["message"], res.error
    assert res.error["details"]["reason"] == "provider_env" and res.error["details"]["variables"] == [KEY]
    assert lab.project.rev() == rev and runs(lab) == []  # nothing dispatched, no run recorded or started
    assert lab.ok("work", "show", wid)["control"]["state"] == "READY"
    # a relaunch is refused the same way: dispatched without a launch, then `harness launch`
    inv = lab.lead("work", "assign", wid)["invocation"]
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    rev = lab.project.rev()
    res = lab.lead_res("harness", "launch", inv)
    assert res.error["code"] == "HARNESS_INCOMPATIBLE" and KEY in res.error["message"], res.error
    assert lab.project.rev() == rev and runs(lab) == [] and not lab.ok("invoke", "show", inv).get("runs")


def test_a_launch_with_the_provider_variable_set_starts(lab, tmp_path):
    lab.script("R-INV-0001-1", [])
    wid = create_planned_ticket(lab.project, tmp_path)
    out = lab.lead("work", "assign", wid, "--launch", env={KEY: "synthetic-value"})
    assert out["launch"]["run"] == "R-INV-0001-1" and runs(lab) == ["R-INV-0001-1"]


def test_doctor_names_an_unset_provider_variable_and_the_fix_and_never_a_value(lab):
    found = doctor(lab)["provider-env"]
    assert found["status"] == "FAIL", found
    assert f"set {KEY} in the terminal you launch AEW from" in found["detail"]
    assert "export" in found["detail"] and f"$env:{KEY}" in found["detail"]
    found = doctor(lab, env={KEY: "synthetic-secret-value"})["provider-env"]
    assert found["status"] == "PASS" and KEY in found["detail"] and "synthetic-secret-value" not in found["detail"]


def test_doctor_shows_each_profile_model_as_the_harness_is_given_it(lab):
    edit_policy(lab, profiles={"standard": {"provider": "fakeprov", "model": "fakeprov/fake-model"},
                               "bare": {"model": "fakeprov/other-model"}})
    found = doctor(lab, env={KEY: "x"})["model-refs"]
    assert found == {"check": "model-refs", "status": "PASS",
                     "detail": "the harness is given bare: fakeprov/other-model; standard: fakeprov/fake-model"}


def test_a_conflicting_model_prefix_fails_doctor_and_dispatch_naming_the_field_and_the_fix(lab, tmp_path):
    edit_policy(lab, profiles={"standard": {"provider": "fakeprov", "model": "elsewhere/fake-model"}})
    found = doctor(lab, env={KEY: "x"})["model-refs"]
    assert found["status"] == "FAIL", found
    assert "profiles.standard.model" in found["detail"] and "Did you mean elsewhere/fake-model" in found["detail"]
    wid = create_planned_ticket(lab.project, tmp_path)
    rev = lab.project.rev()
    res = lab.lead_res("work", "assign", wid)
    assert res.error["code"] == "VALIDATION_FAILED" and res.error["details"]["field"] == "profiles.standard.model"
    assert lab.project.rev() == rev


def test_a_policy_without_provider_variables_reports_none_to_check(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    try:
        checks = doctor(lab)
        assert "provider-env" not in checks and checks["model-refs"]["status"] == "PASS"
    finally:
        lab.cleanup()


def test_the_lead_session_refuses_the_same_way_for_its_own_provider_variable(lab):
    res = lab.aew("opencode", "--provider-env", KEY, "--print-config")
    assert res.returncode != 0 and f"set {KEY} in the terminal you launch AEW from" in res.error["message"], res.error
