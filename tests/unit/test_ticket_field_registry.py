"""The Ticket field-group registry (register F4, slice S1; E19-B §2.3; plan §3.3; ADR-0016 §1).

Every revision-governed Ticket input belongs to exactly one field group, an unclassified one fails closed into the
acceptance group, and no unit key or record field goes unclassified: this file walks both schemas, and invariant 50
(``tests/helpers/invariants.py``) walks every unit of every walk and integration test that checks the invariants.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from invariants import control_violations, ticket_field_violations

from aew.engine import ticket_fields as TF
from aew.errors import ValidationFailed
from aew.knowledge.records import Record, work_unit_record
from aew.schemas import schema
from aew.util import sha256_text


def registry_doc() -> dict[str, Any]:
    text = resources.files("aew.schemas").joinpath("ticket-field-registry.v1.json").read_text(encoding="utf-8")
    return json.loads(text)


def ticket(meta_extra: dict[str, Any] | None = None, *, body: str = "Implement subtract.\n") -> tuple[dict, str]:
    record = work_unit_record(
        unit_id="T-0001", kind="ticket", title="Add subtract()", created_at="2026-10-09T00:00:00Z",
        created_by={"kind": "lead", "session_label": "lead", "generation": 1}, risk_class=1, mutating=True,
        scope_paths=["src/calc/*.py"], goal_backwards=["subtract(a, b) returns a - b"],
        contract=["subtract is exported from calc"], body=body)
    text = Record({**record.meta, **(meta_extra or {})}, record.body).render()
    unit = {"kind": "ticket", "title": "Add subtract()", "record": "work/T-0001/ticket.md",
            "record_sha256": sha256_text(text), "parent": None, "state": "BLOCKED", "state_reason": "created",
            "risk_class": 1, "mutating": True, "depends_on": [], "policy": None, "created_at": "2026-10-09T00:00:00Z",
            "plan": None, "plans": []}
    return {"work": {"T-0001": unit}}, text


def schema_paths(node: dict[str, Any], prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    return [((*prefix, k), v) for k, v in node.get("properties", {}).items()]


def test_every_ticket_field_is_classified():
    reg = TF.load_registry()
    record_paths = set(reg.record_paths())
    unclassified: list[str] = []
    # The record schema: each property is a classified field, provenance, or a container whose properties are.
    pending = schema_paths(schema("work-unit"))
    while pending:
        path, node = pending.pop()
        if path in record_paths or (len(path) == 1 and path[0] in reg.provenance):
            continue
        if reg.classifies_record(path):
            pending += schema_paths(node, path)
        else:
            unclassified.append(f"record:{'.'.join(path)}")
    # The control state's unit definition (open: the walks below see the keys it does not declare).
    unit_def = schema("control")["$defs"]["work_unit"]
    unclassified += [f"control:{k}" for k in unit_def["properties"] if not reg.classifies_control(k)]
    assert unclassified == [], (
        "classify each in src/aew/schemas/ticket-field-registry.v1.json (plan §3.3, §9.2): an input in its group, "
        "anything else as provenance or bookkeeping")
    # Every unit of every walk: the oracle's rule 50 is part of control_violations, which every walk step checks.
    assert "ticket_field_violations(root, state)" in inspect.getsource(control_violations)


def test_the_walks_refuse_an_unclassified_unit_key_or_record_field(tmp_path: Path):
    state, text = ticket({"notes": "also handle negatives"})
    state["work"]["T-0001"]["revision_hint"] = 2
    record = tmp_path / ".aew" / "work" / "T-0001" / "ticket.md"
    record.parent.mkdir(parents=True)
    record.write_text(text, encoding="utf-8")
    problems = ticket_field_violations(tmp_path, state)
    assert problems == ["T-0001: unit keys the Ticket field registry does not classify: ['revision_hint']",
                        "T-0001: record fields the Ticket field registry does not classify: ['notes']"]
    clean, text = ticket()
    record.write_text(text, encoding="utf-8")
    assert ticket_field_violations(tmp_path, clean) == []


def test_an_unknown_record_field_hashes_into_acceptance():
    base_state, base_text = ticket()
    base = TF.live_digests(base_state, "T-0001", base_text)
    cases = {
        "a top-level field": {"notes": "also handle negatives"},
        "a field inside acceptance": {"acceptance": {"goal_backwards": ["subtract(a, b) returns a - b"],
                                                     "contract": ["subtract is exported from calc"],
                                                     "edge_cases": ["negatives"]}},
        "a field inside scope": {"scope": {"paths": ["src/calc/*.py"], "except": ["src/calc/legacy.py"]}},
        "a frontmatter key named like the body": {"body": "also handle negatives"},
    }
    for name, extra in cases.items():
        state, text = ticket(extra)
        digests = TF.live_digests(state, "T-0001", text)
        assert TF.changed_groups(base, digests) == {"acceptance"}, name
        payload = TF.group_payloads(state, "T-0001", text)["acceptance"]
        assert any(k.startswith("record:?") for k in payload), name
    # A control-state key the registry does not classify fails closed the same way (the meta-test refuses it too).
    state, text = ticket()
    state["work"]["T-0001"]["acceptance_note"] = "also handle negatives"
    assert TF.changed_groups(base, TF.live_digests(state, "T-0001", text)) == {"acceptance"}


def test_the_registry_identity_is_its_canonical_json_whatever_the_file_bytes():
    doc = registry_doc()
    reg = TF.load_registry()
    assert reg.identity == TF.registry_from_doc(json.loads(json.dumps(doc, indent=4).replace("\n", "\r\n"))).identity
    assert reg.identity == f"aew/ticket-field-registry/v1@{hashlib.sha256(TF.canonical_json(doc)).hexdigest()}"
    changed = copy.deepcopy(doc)
    changed["groups"]["card"]["description"] += "."
    assert TF.registry_from_doc(changed).identity != reg.identity
    assert reg.material_groups == {"acceptance", "check_definition", "scope", "gate_set", "dependencies", "kind"}
    assert reg.unassigned == "acceptance"


@pytest.mark.parametrize("breakage", ["classified_twice", "undeclared_group", "unassigned_not_material",
                                      "derived_value_missing", "input_and_bookkeeping", "v1_with_moves",
                                      "via_unknown_derived"])
def test_a_registry_that_could_leave_an_input_unbound_is_refused(breakage: str):
    doc = registry_doc()
    if breakage == "classified_twice":
        doc["record"].append({"field": "title", "group": "acceptance", "rule": "text"})
    elif breakage == "undeclared_group":
        doc["record"][0]["group"] = "objective"
    elif breakage == "unassigned_not_material":
        doc["unassigned"] = "card"
    elif breakage == "derived_value_missing":
        doc["derived"] = [d for d in doc["derived"] if d["field"] != "inherited_mandatory_gates"]
    elif breakage == "input_and_bookkeeping":
        doc["bookkeeping"].append("risk_class")
    elif breakage == "v1_with_moves":
        doc["moves"] = [{"field": "record:title", "from": "card", "to": "acceptance"}]
    else:
        doc["control"][2]["via"] = ["effective_scope"]
    with pytest.raises(ValidationFailed):
        TF.registry_from_doc(doc)


def test_a_dotted_frontmatter_key_is_never_the_nested_field(tmp_path: Path):
    """Review F1: a literal key ``"scope.paths"`` is not ``scope: {paths: ...}``. Paths match key by key, and a key that
    contains ``.`` is unclassified wherever it appears: it hashes into acceptance and invariant 50 reports it."""
    twin = {"scope.paths": ["docs/**"]}
    # The reviewer's repro: two records that differ only in the nested scope.paths, both carrying the dotted twin.
    narrow, narrow_text = ticket({**twin, "scope": {"paths": ["src/calc/*.py"]}})
    wide, wide_text = ticket({**twin, "scope": {"paths": ["src/**"]}})
    a, b = TF.live_digests(narrow, "T-0001", narrow_text), TF.live_digests(wide, "T-0001", wide_text)
    assert TF.changed_groups(a, b) == {"scope"}
    payloads = TF.group_payloads(narrow, "T-0001", narrow_text)
    assert payloads["scope"] == {"record:scope.paths": ["src/calc/*.py"]}
    assert payloads["acceptance"]['record:?["scope.paths"]'] == ["docs/**"]
    # Alone or beside its nested twin, the dotted key is reported unclassified, and it changes acceptance only.
    base_state, base_text = ticket()
    base = TF.live_digests(base_state, "T-0001", base_text)
    alone, alone_text = ticket(twin)
    assert TF.changed_groups(base, TF.live_digests(alone, "T-0001", alone_text)) == {"acceptance"}
    assert TF.unclassified_record_paths({"scope.paths": ["y"]}) == ['["scope.paths"]']
    assert TF.unclassified_record_paths({"scope": {"paths": ["x"]}, "scope.paths": ["y"]}) == ['["scope.paths"]']
    assert TF.unclassified_record_paths({"acceptance": {"checks.unit": ["x"]}}) == ['["acceptance","checks.unit"]']
    reg = TF.load_registry()
    assert reg.classifies_record(("scope", "paths")) and reg.classifies_record(("scope",))
    assert not reg.classifies_record(("scope.paths",)) and not reg.classifies_record(("acceptance", "checks.unit"))
    # A dotted key and the nested path it spells are two inputs, never one payload entry.
    dotted, dotted_text = ticket({"notes.extra": "x"})
    nested, nested_text = ticket({"notes": {"extra": "x"}})
    assert TF.changed_groups(TF.live_digests(dotted, "T-0001", dotted_text),
                             TF.live_digests(nested, "T-0001", nested_text)) == {"acceptance"}
    # Invariant 50 refuses it, alone and beside the nested field.
    record = tmp_path / ".aew" / "work" / "T-0001" / "ticket.md"
    record.parent.mkdir(parents=True)
    for state, text in ((alone, alone_text), (narrow, narrow_text)):
        record.write_text(text, encoding="utf-8")
        assert ticket_field_violations(tmp_path, state) == [
            """T-0001: record fields the Ticket field registry does not classify: ['["scope.paths"]']"""]
