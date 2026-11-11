"""``aew.policy.consistency``: contradictions between the policy files, and what the engine can evaluate."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from aew.engine.gates import Catalogue
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.policy.consistency import problems
from aew.util import load_yaml


def catalogue(*specialties: str, cards: tuple[str, ...] = ()) -> Catalogue:
    """The role catalogue's facts: one card per specialty named, and any other cards."""
    return Catalogue(cards=frozenset({*cards, *(f"{s}_reviewer" for s in specialties)}),
                     specialties={s: (f"{s}_reviewer",) for s in specialties}, checks={}, local_checks=())


def test_the_default_policy_is_consistent():
    """The defaults that Engine.init writes to policy/gates.yaml and policy/checks.yaml."""
    assert problems(DEFAULT_GATES, DEFAULT_CHECKS, catalogue()) == []


def test_the_old_project_policy_is_consistent():
    path = Path(__file__).resolve().parents[1] / "fixtures/switch-offer-old-project/gates.yaml"
    assert problems(load_yaml(path.read_text(encoding="utf-8")), DEFAULT_CHECKS, catalogue()) == []


@pytest.mark.parametrize(("table", "gate"), [
    ("risk_paths", "review_r1"),
    ("non_mutating_paths", "execute_record"),
    ("parent_paths", "children_complete"),
])
def test_a_risk_raise_cannot_drop_a_gate(table, gate):
    gates = {**DEFAULT_GATES, table: {"3": [], "2": [gate]}}
    assert problems(gates, DEFAULT_CHECKS, catalogue()) == [
        f"policy/gates.yaml {table}[3] lacks gate `{gate}`, which {table}[2] requires: "
        "raising a unit to class 3 would drop it."
    ]


def test_missing_gate_is_reported_for_each_higher_class_even_past_a_gap():
    gates = {**DEFAULT_GATES, "risk_paths": {"4": [], "0": ["local_checks"], "2": []}}
    assert problems(gates, DEFAULT_CHECKS, catalogue()) == [
        f"policy/gates.yaml risk_paths[{cls}] lacks gate `local_checks`, which risk_paths[0] requires: "
        f"raising a unit to class {cls} would drop it."
        for cls in (2, 4)
    ]


def test_missing_gate_names_the_first_class_that_requires_it():
    gates = {**DEFAULT_GATES, "risk_paths": {"4": [], "2": ["review_r1"], "1": ["review_r1"]}}
    assert problems(gates, DEFAULT_CHECKS, catalogue()) == [
        "policy/gates.yaml risk_paths[4] lacks gate `review_r1`, which risk_paths[1] requires: "
        "raising a unit to class 4 would drop it."
    ]


def test_extra_path_keys_are_checked_for_evaluators_but_do_not_enter_class_order():
    paths = {**DEFAULT_GATES["risk_paths"], "default": ["review_security"], "5": []}
    gates = {**DEFAULT_GATES, "risk_paths": paths}
    assert problems(gates, DEFAULT_CHECKS, catalogue("security")) == []
    found = problems(gates, DEFAULT_CHECKS, catalogue())
    assert len(found) == 1
    assert found[0].startswith("policy/gates.yaml risk_paths[default] requires gate `review_security`")


@pytest.mark.parametrize("paths", [
    {"4": ["review_r1", "local_checks"], "0": ["local_checks"], "2": ["local_checks", "review_r1"]},
    {"3": ["review_r1"]},
])
def test_sparse_consistent_paths_have_no_false_positives(paths):
    gates = {**DEFAULT_GATES, "risk_paths": paths}
    assert problems(gates, DEFAULT_CHECKS, catalogue()) == []


def test_a_gate_check_missing_from_checks_yaml_is_named_with_its_place():
    found = problems(DEFAULT_GATES, {"checks": {"lint": {}}}, catalogue())
    assert any("local_checks names check `unit`" in f for f in found), found
    assert any("post_integration.checks names check `unit`" in f for f in found), found


def test_a_gate_with_no_evaluator_for_its_unit_type_is_reported():
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["non_mutating_paths"]["4"] = ["accepted_plan", "execute_record", "local_checks"]  # never evaluated there
    gates["risk_paths"]["4"] = [*gates["risk_paths"]["4"], "review_security"]
    found = problems(gates, DEFAULT_CHECKS, catalogue())
    assert any("non_mutating_paths[4] requires gate `local_checks`" in f and "no gate of that kind" in f
               for f in found), found
    assert any("risk_paths[4] requires gate `review_security`" in f and "specialty `security`" in f
               for f in found), found
    with_card = problems(gates, DEFAULT_CHECKS, catalogue("security"))  # a security reviewer card satisfies it
    assert with_card == [f for f in found if "non_mutating_paths" in f], with_card


def test_a_path_table_gate_whose_suffix_does_not_resolve_is_reported():
    """ITEMS 55, addendum 1: a card gate needs the card, and `check:<id>` needs the check defined and configured, as
    `work create` judges it (review F3): `unit` is defined in the default checks.yaml but not configured."""
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["risk_paths"]["4"] = [*gates["risk_paths"]["4"], "review_card:nobody", "check:lint", "check:unit"]
    found = problems(gates, DEFAULT_CHECKS, catalogue(cards=("someone",)))
    assert any("`review_card:nobody`" in f and "no card `nobody`" in f and "review_card:someone" not in f
               for f in found), found
    assert any("`check:lint`" in f and "not defined and configured" in f for f in found), found
    assert any("`check:unit`" in f and "not defined and configured" in f for f in found), found
    configured = catalogue(cards=("someone",))._replace(checks={"unit": "sha-unit"})
    assert not any("`check:unit`" in f for f in problems(gates, DEFAULT_CHECKS, configured))


def test_a_guardrail_review_trigger_that_can_never_be_satisfied_is_reported():
    triggers = {"review_triggers": [{"name": "auth", "paths": ["src/auth/**"]},
                                    {"name": "x", "card": "ghost", "paths": ["x/**"]},
                                    {"name": "security", "paths": ["src/**"]}]}
    found = problems(DEFAULT_GATES, DEFAULT_CHECKS, catalogue("security"), triggers)
    assert [f.split(" requires")[0] for f in found] == [
        "policy/guardrails.yaml review_triggers `auth`", "policy/guardrails.yaml review_triggers `x`"], found


def test_a_waivable_gate_that_does_not_exist_is_reported():
    gates = dict(DEFAULT_GATES, waivable_gates=["review_r1", "made_up", "check:unit"])
    assert problems(gates, DEFAULT_CHECKS, catalogue()) == [
        "policy/gates.yaml waivable_gates lists `made_up`, which is not a gate AEW evaluates.",
        "policy/gates.yaml waivable_gates lists `check:unit`, which can never be satisfied: check `unit` is not "
        "defined and configured in policy/checks.yaml."]
    # judged by the same predicate as the path tables (review F3): a configured `unit` makes `check:unit` one
    configured = catalogue()._replace(checks={"unit": "sha-unit"})
    assert [f for f in problems(gates, DEFAULT_CHECKS, configured) if "check:unit" in f] == []
