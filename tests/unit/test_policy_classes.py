"""Policy field classes and the two digests (the pre-F15.2 amendment A3 §8 and §9; M4-E plan §2.5, slice E1)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from aew.policy import classes
from aew.schemas import schema

GATES: dict[str, Any] = {
    "schema": "aew/gates/v1", "local_checks": ["unit"], "risk_paths": {str(c): ["accepted_plan"] for c in range(5)},
    "post_integration": {"verification": True, "checks": ["unit"], "validation_deadline_s": 600},
    "history_audit": {"max_unverified_entries": 5},
}
CHECKS: dict[str, Any] = {"schema": "aew/checks/v1",
                          "checks": {"unit": {"configured": True, "command": ["pytest"], "timeout_s": 60}}}


def _digests(gates: dict[str, Any] = GATES, checks: dict[str, Any] = CHECKS, **extra: Any) -> dict[str, str]:
    return classes.digests({"policy/gates.yaml": ("gates", gates), "policy/checks.yaml": ("checks", checks), **extra})


def _changed(base: dict[str, Any], edit: Any) -> dict[str, Any]:
    out = copy.deepcopy(base)
    edit(out)
    return out


@pytest.mark.parametrize("name", classes.CLASSIFIED)
def test_every_policy_property_is_classified(name):
    assert classes.unclassified(schema(name)) == []


def test_an_unclassified_property_fails_validation():
    bad = {"type": "object", "properties": {"schema": {"x-aew-class": "operational"}, "new_knob": {"type": "integer"},
                                            "odd": {"x-aew-class": "maybe"}}}
    assert classes.unclassified(bad) == ["/new_knob", "/odd (unknown class 'maybe')"]


def test_an_unclassified_schema_is_refused_when_digesting(monkeypatch):
    monkeypatch.setattr("aew.schemas.schema", lambda name: {"type": "object", "properties": {"x": {}}})
    with pytest.raises(ValueError, match="unclassified properties"):
        _digests()


def test_operational_change_never_changes_the_legality_digest():
    """A3 §9: a timing or reporting threshold changes only the operational digest."""
    before = _digests()
    for gates, checks in (
            (_changed(GATES, lambda g: g["post_integration"].update(validation_deadline_s=900)), CHECKS),
            (_changed(GATES, lambda g: g["history_audit"].update(max_unverified_entries=9)), CHECKS),
            (GATES, _changed(CHECKS, lambda c: c["checks"]["unit"].update(timeout_s=120)))):
        after = _digests(gates, checks)
        assert after["legality_digest"] == before["legality_digest"]
        assert after["operational_digest"] != before["operational_digest"]


def test_legality_change_changes_the_legality_digest():
    """A3 §9: a gate or a check's definition is legality-affecting."""
    before = _digests()
    for gates, checks in (
            (_changed(GATES, lambda g: g["risk_paths"]["2"].append("review_r1")), CHECKS),
            (GATES, _changed(CHECKS, lambda c: c["checks"]["unit"].update(command=["pytest", "-x"]))),
            (GATES, _changed(CHECKS, lambda c: c["checks"].update(lint={"configured": False})))):
        assert _digests(gates, checks)["legality_digest"] != before["legality_digest"]


def test_a_policy_file_without_a_classified_schema_is_legality_in_full():
    before = _digests(**{"policy/extra.yaml": ("extra", {"knob": 1})})
    after = _digests(**{"policy/extra.yaml": ("extra", {"knob": 2})})
    assert after["legality_digest"] != before["legality_digest"]
    assert after["operational_digest"] == before["operational_digest"]


def test_execution_profiles_classify_through_the_profile_definition():
    execution = {"schema": "aew/execution/v1", "configured": True, "routing": {"default": "p"},
                 "profiles": {"p": {"provider": "x", "model": "m", "deadline_s": 60}}}
    found = {pointer: cls for pointer, cls, _ in classes.leaves(schema("execution"), execution)}
    assert found["/profiles/p/model"] == classes.LEGALITY
    assert found["/profiles/p/deadline_s"] == classes.OPERATIONAL
    assert found["/routing/default"] == classes.LEGALITY
