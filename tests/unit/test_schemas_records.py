from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator

from aew.errors import ValidationFailed
from aew.knowledge.records import (
    decision_record,
    format_id,
    plan_record,
    read_record,
    work_unit_record,
)
from aew.schemas import SCHEMAS, _validator, schema, validate

WHO = {"kind": "lead", "session_label": "lead-a", "generation": 1}


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_every_schema_is_valid_draft_2020_12(name):
    # The only metaschema check of AEW's schemas: runtime validators skip check_schema for speed.
    Draft202012Validator.check_schema(schema(name))  # raises SchemaError when the schema itself is malformed
    _validator(name)


def test_ids():
    assert format_id("T", 1) == "T-0001"
    assert format_id("D", 12345) == "D-12345"


def test_ticket_record_round_trip(tmp_path):
    rec = work_unit_record(
        unit_id="T-0001",
        kind="ticket",
        title="Add subtract()",
        created_at="2026-09-25T00:00:00Z",
        created_by=WHO,
        risk_class=1,
        mutating=True,
        scope_paths=["calc/**", "tests/**"],
        goal_backwards=["calc.subtract(5, 3) == 2"],
        contract=["no changes outside scope"],
        body="## Objective\n\nAdd a subtract function.\n",
    )
    path = tmp_path / "ticket.md"
    path.write_text(rec.render(), encoding="utf-8")
    back = read_record(path, "work-unit")
    assert back.meta == rec.meta
    assert back.body == rec.body


def test_ticket_record_rejects_bad_class():
    with pytest.raises(ValidationFailed) as exc:
        work_unit_record(
            unit_id="T-0001", kind="ticket", title="x", created_at="t", created_by=WHO,
            risk_class=7, mutating=True,
        )
    assert any("initial_risk_class" in v for v in exc.value.details["violations"])


def test_ticket_record_rejects_bad_id():
    with pytest.raises(ValidationFailed):
        work_unit_record(
            unit_id="TICKET-1", kind="ticket", title="x", created_at="t", created_by=WHO,
            risk_class=1, mutating=True,
        )


def test_plan_record():
    rec = plan_record(work_unit="T-0001", revision=1, created_at="t", author={"role": "lead"}, body="plan")
    assert rec.meta["supersedes"] is None
    with pytest.raises(ValidationFailed):
        plan_record(work_unit="T-0001", revision=0, created_at="t", author={"role": "lead"}, body="x")


def test_decision_record_classification_enum():
    rec = decision_record(
        decision_id="D-0001",
        decision_type="verification_failure_classification",
        decided_by=WHO,
        at="t",
        summary="classified",
        work_unit="T-0001",
        classification="LOCAL_IMPLEMENTATION_DEFECT",
    )
    assert rec.meta["classification"] == "LOCAL_IMPLEMENTATION_DEFECT"
    with pytest.raises(ValidationFailed):
        decision_record(
            decision_id="D-0002", decision_type="verification_failure_classification",
            decided_by=WHO, at="t", summary="x", classification="IMPLEMENTER_SAYS_FINE",
        )


def test_evidence_schema_requires_snapshot():
    evidence = {
        "schema": "aew/evidence/v1",
        "id": "INV-0001-review-1",
        "kind": "review",
        "work_unit": "T-0001",
        "producer": {"role": "reviewer", "invocation": "INV-0001"},
        "created_at": "t",
        "method": {},
        "claim": "c",
        "result": "pass",
    }
    with pytest.raises(ValidationFailed) as exc:
        validate("evidence", evidence, source="e")
    assert any("evaluated_snapshot" in v for v in exc.value.details["violations"])


def test_gates_schema_requires_all_risk_classes():
    with pytest.raises(ValidationFailed):
        validate(
            "gates",
            {"schema": "aew/gates/v1", "risk_paths": {"0": []}, "local_checks": [],
             "post_integration": {"verification": True, "checks": []}},
            source="gates",
        )


def test_the_v2_only_keys_are_defined_once():
    """Register E36: the control schema's v1 rule refuses exactly `V2_ONLY_KEYS`, and `as_v1` of a v2 state is a
    valid v1 document. A new v2 hot key added to one and not the other fails here, not in every fixture that fakes a
    v1 project."""
    import json
    from importlib import resources

    from aew.engine.base import V1, V2, V2_ONLY_KEYS, as_v1

    schema = json.loads(resources.files("aew.schemas").joinpath("control.schema.json").read_text(encoding="utf-8"))
    [v1_rule] = [r for r in schema["allOf"]
                 if ((r["if"].get("properties") or {}).get("schema") or {}).get("const") == V1]
    refused = {key for alt in v1_rule["then"]["not"]["anyOf"] for key in alt["required"]}
    assert refused == set(V2_ONLY_KEYS)
    assert set(V2_ONLY_KEYS) <= set(schema["properties"])
    state = {"schema": V2, "revision": 3, **{k: {} for k in V2_ONLY_KEYS}}
    assert as_v1(state) == {"schema": V1, "revision": 3} and state["schema"] == V2
