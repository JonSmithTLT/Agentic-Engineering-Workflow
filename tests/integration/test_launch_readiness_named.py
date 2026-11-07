"""A launch that cannot work is refused up front, naming the cause and the fix, and `aew doctor` names the same before
any launch (ADR-0010 amendment 2026-10-11; the M4 user acceptance test): a provider variable the policy names that is
not set where AEW launches, and a model id that maps to no provider/model pair. Synthetic names and ids only; the fake
harness runs every launch."""

from __future__ import annotations

import json
import sys
from typing import Any

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
    assert f"set {KEY} in the terminal you start AEW from" in res.error["message"], res.error
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


def test_a_launch_carries_each_readiness_row_it_does_not_refuse_on_with_its_fix_and_none_when_all_pass(lab, tmp_path):
    """E125: a launch that starts still says what a launch from here would meet elsewhere (here another profile's
    model maps to no pair: doctor's `model-refs` FAIL, which refuses only a dispatch with that profile), in its
    result's ``readiness``, with the fix; a launch that meets every check carries none. No new refusal."""
    lab.script("default", [])
    wid = create_planned_ticket(lab.project, tmp_path)
    env = {KEY: "synthetic-value"}
    inv = lab.lead("work", "assign", wid, env=env)["invocation"]
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    clean = lab.lead("harness", "launch", inv, env=env)
    assert "readiness" not in clean, clean
    policy = load_yaml((lab.aew_root / "policy/execution.yaml").read_text(encoding="utf-8"))
    edit_policy(lab, profiles={**policy["profiles"], "broken": {"provider": "fakeprov", "model": "elsewhere/x"}})
    row = doctor(lab, env=env)["model-refs"]
    assert row["status"] == "FAIL" and "profiles.broken.model" in row["detail"], row
    out = lab.lead("harness", "launch", inv, "--replace", env=env)
    assert out["readiness"] == [f"readiness FAIL (model-refs): {row['detail']}"], out


def test_a_launch_with_the_provider_variable_set_starts(lab, tmp_path):
    lab.script("R-INV-0001-1", [])
    wid = create_planned_ticket(lab.project, tmp_path)
    out = lab.lead("work", "assign", wid, "--launch", env={KEY: "synthetic-value"})
    assert out["launch"]["run"] == "R-INV-0001-1" and runs(lab) == ["R-INV-0001-1"]


def test_doctor_names_an_unset_provider_variable_and_the_fix_and_never_a_value(lab):
    found = doctor(lab)["provider-env"]
    assert found["status"] == "FAIL", found
    assert f"set {KEY} in the terminal you start AEW from" in found["detail"]
    assert "export" in found["detail"] and f"$env:{KEY}" in found["detail"]
    found = doctor(lab, env={KEY: "synthetic-secret-value"})["provider-env"]
    assert found["status"] == "PASS" and KEY in found["detail"] and "synthetic-secret-value" not in found["detail"]


def test_doctor_exits_1_with_a_fail_line_in_both_output_modes_and_0_without(lab):
    """The exit status never depends on the output format (review of PR #214, F1): any FAIL line exits 1; WARN lines
    (Windows' platform line, containment) leave it 0."""
    for args in (("doctor",), ("doctor", "--json")):
        failing = lab.aew(*args)
        assert failing.returncode == 1 and "provider-env" in failing.stdout, (args, failing.stdout)
        passing = lab.aew(*args, env={KEY: "x"})
        assert passing.returncode == 0, (args, passing.stdout)


def test_doctor_says_a_running_lead_session_keeps_the_environment_it_started_with(lab):
    for env in (None, {KEY: "x"}):
        detail = doctor(lab, env=env)["provider-env"]["detail"]
        assert "keeps the environment it started with" in detail, detail


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
    assert res.returncode != 0 and f"set {KEY} in the terminal you start AEW from" in res.error["message"], res.error


# ------------------------------------------------------------- the provider key (the operator's decision, 2026-11-06)

LINUX = sys.platform.startswith("linux")


def keyless_lab(tmp_path, provider_env: list[str]) -> HarnessLab:
    """A project whose runs use the real OpenCode adapter (it calls its provider itself, so on Linux's default
    `proxy_only` its runs are on the relay route) with a paid openai profile. Nothing is launched by these tests."""
    policy = {**POLICY, "harness": "opencode", "provider_env": provider_env,
              "profiles": {"standard": {"provider": "openai", "model": "synthetic-paid-model"}}}
    return HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy)


@pytest.mark.skipif(not LINUX, reason="the relay route is Linux's (proxy_only); Windows has no network containment")
def test_a_relay_route_launch_whose_provider_would_get_no_key_is_refused_before_anything_is_committed(
        tmp_path, monkeypatch):
    """Wrong: the policy names no key variable for its provider. The launch is refused with `provider_key_missing`,
    naming the variable, quoting the published rule; nothing is dispatched or recorded. `aew doctor` names the same
    beforehand. Right: the variable named and set passes doctor."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    lab = keyless_lab(tmp_path, [])
    try:
        found = doctor(lab)["provider-key"]
        assert found["status"] == "FAIL" and "openai (OPENAI_API_KEY), for profile(s) standard" in found["detail"]
        assert "provider_key_missing" in found["detail"] and "https://opencode.ai/docs/zen/" in found["detail"]
        wid = create_planned_ticket(lab.project, tmp_path)
        rev = lab.project.rev()
        res = lab.lead_res("work", "assign", wid, "--launch")
        assert res.returncode != 0 and res.error["code"] == "HARNESS_INCOMPATIBLE", res.error
        assert res.error["details"]["reason"] == "provider_key_missing", res.error
        assert res.error["details"]["variable"] == "OPENAI_API_KEY"
        assert "Free-tier chat models require OpenCode" in res.error["message"]
        assert lab.project.rev() == rev and runs(lab) == []
        edit_policy(lab, provider_env=["OPENAI_API_KEY"])
        found = doctor(lab, env={"OPENAI_API_KEY": "sk-synthetic-value"})["provider-key"]
        assert found["status"] == "PASS" and "sk-synthetic-value" not in found["detail"]
    finally:
        lab.cleanup()


def test_doctor_judges_no_provider_key_off_the_relay_route(tmp_path):
    """Missing: a harness that never calls its provider itself (the fake), and on Windows any harness, has no relay
    route, so doctor has no `provider-key` line to give."""
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy={
        **POLICY, "profiles": {"standard": {"provider": "openai", "model": "synthetic-paid-model"}}})
    try:
        assert "provider-key" not in doctor(lab)
    finally:
        lab.cleanup()
    if not LINUX:
        lab = keyless_lab(tmp_path / "opencode", [])
        try:
            assert "provider-key" not in doctor(lab)
        finally:
            lab.cleanup()


def test_aew_init_says_at_first_use_that_aew_needs_a_provider_key(tmp_path):
    from aew.harness.containment import netns

    assert "AEW needs a provider key" in netns.FIRST_USE_LINE
    line = netns.FIRST_USE_LINE
    assert "does not use OpenCode's free models" in line and netns.FREE_TIER_RULE in line


def test_a_runs_refused_egress_targets_reach_no_lead_read(lab, tmp_path):
    """The designer's ruling of 2026-11-06, point 1: the refused targets are in the run's record (`egress_refused`),
    never in what the Lead reads of it (`harness status`, `harness wait`: CS-4 addendum 4's relayed reads)."""
    lab.script("R-INV-0001-1", [])
    wid = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", wid, "--launch", env={KEY: "synthetic-value"})["launch"]["run"]
    lab.wait(run)
    directory = runlog.run_dir(lab.aew_root, run)
    record = runlog.read_record(directory) or {}
    record["egress_refused"] = {"targets": [{"target": "secret-plan.example:443", "reasons": ["not_allowlisted"],
                                             "count": 1}], "more": 0}
    runlog.write_record(directory, record)
    for args in (("harness", "status"), ("harness", "status", record["invocation"]), ("harness", "wait", run)):
        res = lab.aew(*args)
        # The label's self-test row 1 has an `egress_refused` key of its own (its planted probe target, CS-4 A2):
        # what must not reach the read is the record's, by its value and by its shape.
        assert "secret-plan" not in res.stdout and '"targets"' not in res.stdout, (args, res.stdout)
        assert not_carried(json.loads(res.stdout)), args


def not_carried(value: Any) -> bool:
    """Whether no ``egress_refused`` in ``value`` has the run record's shape (a ``targets`` list)."""
    if isinstance(value, dict):
        found = value.get("egress_refused")
        if isinstance(found, dict) and "targets" in found:
            return False
        return all(not_carried(v) for v in value.values())
    if isinstance(value, list):
        return all(not_carried(v) for v in value)
    return True
