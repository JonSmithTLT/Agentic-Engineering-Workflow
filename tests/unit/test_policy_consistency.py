"""``aew.policy.consistency``: contradictions between the policy files, and what the engine can evaluate."""

from __future__ import annotations

import copy

from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.policy.consistency import problems


def test_the_default_policy_is_consistent():
    assert problems(DEFAULT_GATES, DEFAULT_CHECKS, set()) == []


def test_a_gate_check_missing_from_checks_yaml_is_named_with_its_place():
    found = problems(DEFAULT_GATES, {"checks": {"lint": {}}}, set())
    assert any("local_checks names check `unit`" in f for f in found), found
    assert any("post_integration.checks names check `unit`" in f for f in found), found


def test_a_gate_with_no_evaluator_for_its_unit_type_is_reported():
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["non_mutating_paths"]["2"] = ["accepted_plan", "execute_record", "local_checks"]  # never evaluated there
    gates["risk_paths"]["3"] = [*gates["risk_paths"]["3"], "review_security"]
    found = problems(gates, DEFAULT_CHECKS, set())
    assert any("non_mutating_paths[2] requires gate `local_checks`" in f and "no evaluator" in f for f in found), found
    assert any("risk_paths[3] requires gate `review_security`" in f and "specialty `security`" in f
               for f in found), found
    with_card = problems(gates, DEFAULT_CHECKS, {"security"})  # a security reviewer card satisfies review_security
    assert with_card == [f for f in found if "non_mutating_paths" in f], with_card


def test_a_waivable_gate_that_does_not_exist_is_reported():
    gates = dict(DEFAULT_GATES, waivable_gates=["review_r1", "made_up"])
    assert problems(gates, DEFAULT_CHECKS, set()) == [
        "policy/gates.yaml waivable_gates lists `made_up`, which is not a gate AEW evaluates."]
