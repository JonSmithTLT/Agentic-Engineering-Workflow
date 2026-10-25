"""The control-keys family of the generated reference (STG-12 S12-2), on the tree: what holds for ``src/aew``.

* the control schema is closed and validated on every load and commit (what makes the control keys complete by
  construction), and its keys are the records, both ways;
* the unit keys are the registry's inventory joined with the schema's, and none is unclassified;
* a record anchored at a constant names the key that constant holds (a second derivation, by importing it);
* the keys the records call initial are the keys ``aew init`` writes.

The planted cases of each rule are in ``tests/unit/test_reference_control_keys.py``.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from conftest import make_git_repo  # noqa: E402
from store_model import initial_state  # noqa: E402

from aew import schemas  # noqa: E402
from aew.engine import base, ticket_fields  # noqa: E402
from aew.engine.api import Engine  # noqa: E402
from aew.errors import ValidationFailed  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, control_keys
    finally:
        sys.path.remove(here)
    return common, control_keys


C, K = _tools()
CTX = C.Context(ROOT)
RECORDS = K.build(CTX).records
CONTROL = {r.key: r for r in RECORDS if (r.fact or {})["scope"] == "control"}
UNIT = {r.key.removeprefix("unit:"): r for r in RECORDS if (r.fact or {})["scope"] == K.UNIT}


def test_the_control_schema_is_closed_and_refuses_a_key_it_does_not_declare():
    """The registry the control keys' coverage names: a schema that allows no other top-level key."""
    assert schemas.schema("control")["additionalProperties"] is False
    state = initial_state()
    schemas.validate("control", state, source="a sound state")
    with pytest.raises(ValidationFailed):
        schemas.validate("control", {**state, "not_a_control_key": 1}, source="a state with a key nothing declares")


def test_every_load_and_commit_of_the_control_state_is_validated():
    """The schema is the registry only if nothing reads or writes control state without it: the store validates the
    state it deserializes, the one it creates and the one each commit makes."""
    tree = ast.parse((ROOT / "src" / "aew" / "engine" / "store.py").read_text(encoding="utf-8"))

    class Validated(C.Scoped):
        def __init__(self) -> None:
            super().__init__()
            self.where: list[str | None] = []

        def visit_Call(self, node: ast.Call) -> None:
            if (isinstance(node.func, ast.Name) and node.func.id == "validate" and node.args
                    and isinstance(node.args[0], ast.Constant) and node.args[0].value == "control"):
                self.where.append(self.symbol)
            self.generic_visit(node)

    visitor = Validated()
    visitor.visit(tree)
    assert sorted(w for w in visitor.where if w) == ["ControlStore._commit_unprofiled", "ControlStore.create",
                                                     "deserialize_control"]


def test_the_control_key_records_are_the_schemas_top_level_properties_both_ways():
    schema = schemas.schema("control")
    assert set(CONTROL) == set(schema["properties"])
    assert {k for k, r in CONTROL.items() if r.fact["required"]} == set(schema["required"])
    assert {k for k, r in CONTROL.items() if r.fact["v2_only"]} == set(base.V2_ONLY_KEYS)


def test_the_v2_only_flag_is_what_the_v1_rule_of_the_schema_refuses():
    """A second derivation of the flag: the control schema's rule for a v1 document refuses exactly these keys."""
    schema = schemas.schema("control")
    [v1_rule] = [r for r in schema["allOf"]
                 if ((r["if"].get("properties") or {}).get("schema") or {}).get("const") == base.V1]
    refused = {key for alt in v1_rule["then"]["not"]["anyOf"] for key in alt["required"]}
    assert {k for k, r in CONTROL.items() if r.fact["v2_only"]} == refused


def test_the_unit_key_records_are_the_registrys_inventory_joined_with_the_schemas_properties_both_ways():
    registry = ticket_fields.load_registry()
    unit_def = schemas.schema("control")["$defs"]["work_unit"]
    assert set(UNIT) == set(registry.store("control")) | set(registry.bookkeeping) | set(unit_def["properties"])
    assert {k for k, r in UNIT.items() if r.fact["in_schema"]} == set(unit_def["properties"])
    assert {k for k, r in UNIT.items() if r.fact["required"]} == set(unit_def["required"])


def test_no_unit_key_is_unclassified():
    """The classification of a key is the registry's own; this is the existing meta-test's rule read off the records."""
    assert [k for k, r in UNIT.items() if r.fact["classification"] == "unclassified"] == []


def test_a_record_anchored_at_a_constant_names_the_key_that_constant_holds():
    """A second derivation of the anchor: import the module and read the constant."""
    seen = 0
    for r in RECORDS:
        if r.symbol and r.symbol.endswith(K.CONSTANT_SUFFIX):
            assert getattr(importlib.import_module(r.module), r.symbol) == r.fact["key"], r.id
            seen += 1
    assert seen >= 3, "the coordination keys and the unit key of dispositions are named by constants"


def test_the_keys_the_records_call_initial_are_the_keys_the_initial_state_has(tmp_path):
    engine = Engine.initialize(make_git_repo(tmp_path / "repo", {"README.md": "# ck\n"}), project_id="ck")
    written = set(engine.store.read_committed())
    assert {k for k, r in CONTROL.items() if r.fact["initial"]} == written


def test_the_constants_named_key_that_are_not_state_keys_are_listed_and_are_not_records():
    trees = {n: s.tree for n, s in CTX.sources().items() if s.tree is not None}
    skipped = {(m, name) for value, found in K.key_constants(trees).items() if value not in
               {r.fact["key"] for r in RECORDS} for m, name in found}
    assert ("aew.engine.disposition_ops", "POLICY_KEY") in skipped, "a policy key, not a control-state key"
    assert not any(r.symbol == "POLICY_KEY" for r in RECORDS)
