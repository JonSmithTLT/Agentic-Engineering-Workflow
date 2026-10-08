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
            (GATES, _changed(CHECKS, lambda c: c["checks"]["unit"].update(description="the unit suite")))):
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


def test_a_check_timeout_and_guardrails_notes_bind_legality():
    """PR #130 review, finding 1: a check's timeout and the guardrails notes are inputs to a check's definition
    digest (independent audit I1), so a change to either is a legality change."""
    before = _digests()
    after = _digests(GATES, _changed(CHECKS, lambda c: c["checks"]["unit"].update(timeout_s=600)))
    assert after["legality_digest"] != before["legality_digest"]
    g = {"policy/guardrails.yaml": ("guardrails", {"schema": "aew/guardrails/v1", "notes": "a"})}
    h = {"policy/guardrails.yaml": ("guardrails", {"schema": "aew/guardrails/v1", "notes": "b"})}
    assert _digests(**g)["legality_digest"] != _digests(**h)["legality_digest"]


def _other(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    return f"{value}-changed" if isinstance(value, str) else "changed"


def test_no_operational_field_is_an_input_to_a_check_definition():
    """PR #130 review, finding 1: what a check result proves (``definition_digest``) never depends on an operational
    field, so an operational edit can never unsatisfy a gate while ``legality_digest`` stays the same."""
    from aew.policy.checks import current_definitions

    checks = {"schema": "aew/checks/v1", "checks": {"unit": {"configured": True, "command": ["pytest"], "cwd": ".",
                                                            "timeout_s": 60, "description": "d"}}}
    guardrails = {"schema": "aew/guardrails/v1", "protected_paths": ["a/**"], "notes": "n"}
    base = current_definitions(checks, guardrails)
    operational = 0
    for name, data in (("checks", checks), ("guardrails", guardrails)):
        for pointer, cls, value in classes.leaves(schema(name), data):
            if cls != classes.OPERATIONAL or pointer == "/schema":  # a schema id is a const: it cannot be edited
                continue
            operational += 1
            edited = copy.deepcopy(data)
            *parents, leaf = pointer.strip("/").split("/")
            node = edited
            for part in parents:
                node = node[part]
            node[leaf] = _other(value)
            args = (edited, guardrails) if name == "checks" else (checks, edited)
            assert current_definitions(*args) == base, pointer
    assert operational  # the walk saw the operational fields it guards


def test_a_key_the_schema_does_not_name_binds_legality():
    """PR #130 review, finding 2: a key an open container accepts but the schema does not name (the engine reads
    ``builtin`` on a check entry) is digested as legality, never dropped (A3 §8, fail closed)."""
    before = _digests()
    builtin = _changed(CHECKS, lambda c: c["checks"]["unit"].update(builtin=True))
    after = _digests(GATES, builtin)
    assert after["legality_digest"] != before["legality_digest"]
    assert after["operational_digest"] == before["operational_digest"]
    found = {p: c for p, c, _ in classes.leaves(schema("checks"), builtin)}
    assert found["/checks/unit/builtin"] == classes.LEGALITY
    g = {"policy/guardrails.yaml": ("guardrails", {"schema": "aew/guardrails/v1"})}
    h = {"policy/guardrails.yaml": ("guardrails", {"schema": "aew/guardrails/v1", "future_knob": 1})}
    assert _digests(**g)["legality_digest"] != _digests(**h)["legality_digest"]


def test_an_unnamed_key_cannot_alias_a_named_field():
    """Pointers escape ``/`` and ``~`` (RFC 6901), so an unnamed key cannot collide with a classified field."""
    data = _changed(CHECKS, lambda c: c["checks"].update({"unit/timeout_s": 5}))
    pointers = [p for p, _, _ in classes.leaves(schema("checks"), data)]
    assert "/checks/unit~1timeout_s" in pointers and len(pointers) == len(set(pointers))


def test_a_non_string_policy_key_is_refused_not_a_crash():
    """PR #130 review, finding 3: YAML reads ``1:`` as an integer. That is refused with a typed error (so a projection
    reports it rather than failing whole), and the checks schema refuses it too."""
    from aew.errors import ValidationFailed
    from aew.schemas import validate

    data = _changed(CHECKS, lambda c: c["checks"].update({1: {"configured": False}}))
    with pytest.raises(ValidationFailed) as err:
        _digests(GATES, data)
    assert err.value.details["reason"] == "policy_key_not_string"
    with pytest.raises(ValidationFailed):
        validate("checks", {"schema": "aew/checks/v1", "checks": {1: {"configured": False}}}, source="checks.yaml")
