"""The control-keys family of the generated reference (STG-12 S12-2), on planted owners.

``tools/reference_families/control_keys.py`` reads the control schema, the Ticket field registry and the source for the
constants the code names its state keys by. Every rule has its planted right case, wrong case and missing case; the
tree-wide guarantees (the schema is closed and validated on every load and commit; the records equal the owners) are in
``tests/integration/test_reference_control_keys.py``.
"""

from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path
from typing import Any

import pytest

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

SCHEMA = {"properties": {"alpha": {}, "beta_slot": {}, "gamma": {}, "delta": {}}, "required": ["alpha"],
          "additionalProperties": False,
          "$defs": {"work_unit": {"properties": {"title": {}, "coordination": {}}, "required": ["title"]}}}
INIT = "def make():\n    return {'alpha': 1, 'gamma': 2, 'extra': 3}\n"


def trees(sources: dict[str, str]) -> dict[str, ast.Module]:
    return {name: ast.parse(text) for name, text in sources.items()}


def inputs(sources: dict[str, str] | None = None, *, schema: Any = SCHEMA, v2_only: tuple[str, ...] = ("delta",),
           registry: dict[str, str] | None = None, bookkeeping: frozenset[str] = frozenset({"state", "coordination"})
           ) -> Any:
    return K.Inputs(schema, v2_only, {"title": "card"} if registry is None else registry, bookkeeping,
                    trees(sources if sources is not None else {"m.init": INIT}))


def by_key(records: list[Any]) -> dict[str, Any]:
    return {r.key: r for r in records}


def anchor(record: Any) -> tuple[str, str | None]:
    return record.module, record.symbol


# --------------------------------------------------------------------------------------- where a key is anchored

def test_a_constant_named_key_whose_value_is_the_key_is_where_the_code_defines_it():
    got = by_key(K.records_of(inputs({"m.init": INIT, "m.layout": "SLOT_KEY = 'beta_slot'\n"})))
    assert anchor(got["beta_slot"]) == ("m.layout", "SLOT_KEY")


def test_a_constant_not_named_key_is_not_the_name_of_a_key():
    got = by_key(K.records_of(inputs({"m.init": INIT, "m.layout": "SLOT_DIR = 'beta_slot'\n"})))
    assert anchor(got["beta_slot"]) == K.SCHEMAS, "falls back to the schema registry"


def test_a_constant_named_key_whose_value_is_no_state_key_makes_no_record():
    records = K.records_of(inputs({"m.init": INIT, "m.layout": "OTHER_KEY = 'not_a_state_key'\n"}))
    assert "not_a_state_key" not in {(r.fact or {}).get("key") for r in records}
    assert K.key_constants(trees({"m.layout": "OTHER_KEY = 'x'\nNOT = 'y'\n"})) == {"x": [("m.layout", "OTHER_KEY")]}


def test_the_anchor_falls_through_constant_then_initial_names_then_v2_registry_then_constructor_then_schemas():
    sources = {"m.base": "PINS = 'gamma'\n",
               "m.init": "from m.base import PINS\n\ndef make():\n    return {'alpha': 1, PINS: 2}\n"}
    got = by_key(K.records_of(inputs(sources)))
    assert anchor(got["gamma"]) == ("m.base", "PINS"), "a name for the key in the initial state is its constant"
    assert anchor(got["delta"]) == K.V2_ONLY, "v2-only without a name of its own"
    assert anchor(got["alpha"]) == ("m.init", "make"), "in the initial state, no name: the function that makes it"
    assert anchor(got["beta_slot"]) == K.SCHEMAS, "in none of them: the schema registry"


def test_the_constant_wins_over_every_other_anchor():
    sources = {"m.init": INIT, "m.layout": "ALPHA_KEY = 'alpha'\nDELTA_KEY = 'delta'\n"}
    got = by_key(K.records_of(inputs(sources)))
    assert anchor(got["alpha"]) == ("m.layout", "ALPHA_KEY") and anchor(got["delta"]) == ("m.layout", "DELTA_KEY")


def test_a_unit_key_is_anchored_at_its_constant_else_the_field_registry():
    got = by_key(K.records_of(inputs({"m.init": INIT, "m.layout": "UNIT_KEY = 'coordination'\n"})))
    assert anchor(got["unit:coordination"]) == ("m.layout", "UNIT_KEY")
    assert anchor(got["unit:title"]) == K.REGISTRY


# ------------------------------------------------------------------------------------------ the constructor

def test_the_initial_state_is_the_one_dict_that_names_every_required_key():
    module, symbol, keys, node = K.initial_state(trees({"m.init": INIT}), frozenset(), {"alpha"})
    assert (module, symbol, set(keys)) == ("m.init", "make", {"alpha", "gamma", "extra"})
    assert isinstance(node, ast.Dict)


CREATE = ("class Store:\n    def create(self, state, files):\n        state['outbox'] = 0\n"
          "        state.setdefault('marker', 1)\n        other['ignored'] = 2\n\n"
          "def make():\n    state = {'alpha': 1}\n    Store().create(state, {})\n    Store().create({'z': 1}, {})\n")


def test_the_keys_a_function_adds_to_the_state_it_is_handed_are_found_where_it_adds_them():
    """`ControlStore.create` adds `outbox` to the state `Engine.initialize` hands it: it is in the initial state."""
    parsed = trees({"m.init": CREATE})
    module, symbol, _, literal = K.initial_state(parsed, frozenset(), {"alpha"})
    created = K.created_keys(parsed, frozenset(), module, symbol, literal)
    assert created == {"outbox": ("m.init", "Store.create"), "marker": ("m.init", "Store.create")}


def test_a_key_the_callee_adds_to_something_else_is_not_the_states():
    parsed = trees({"m.init": CREATE})
    _, _, _, literal = K.initial_state(parsed, frozenset(), {"alpha"})
    assert "ignored" not in K.created_keys(parsed, frozenset(), "m.init", "make", literal)


def test_a_key_added_to_the_initial_state_is_initial_and_anchored_at_the_function_that_adds_it():
    schema = copy.deepcopy(SCHEMA)
    schema["properties"].update({"outbox": {}, "marker": {}})
    got = by_key(K.records_of(inputs({"m.init": CREATE}, schema=schema)))
    assert got["outbox"].fact["initial"] is True and anchor(got["outbox"]) == ("m.init", "Store.create")
    assert got["beta_slot"].fact["initial"] is False


@pytest.mark.parametrize("source", [
    "def make():\n    return {'gamma': 1}\n",                                            # none names every required key
    INIT + "\ndef again():\n    return {'alpha': 1}\n",                                    # two do
])
def test_a_constructor_that_is_not_exactly_one_is_refused_not_guessed(source):
    with pytest.raises(C.ReferenceError):
        K.initial_state(trees({"m.init": source}), frozenset(), {"alpha"})


# ---------------------------------------------------------------------------------------------------- the facts

def test_a_control_key_says_whether_it_is_required_v2_only_and_in_the_initial_state():
    got = by_key(K.records_of(inputs()))
    assert got["alpha"].fact == {"key": "alpha", "scope": "control", "required": True, "v2_only": False,
                                 "initial": True}
    assert got["delta"].fact == {"key": "delta", "scope": "control", "required": False, "v2_only": True,
                                 "initial": False}


def test_a_unit_key_is_classified_by_the_registry_and_says_whether_the_schema_declares_it():
    got = by_key(K.records_of(inputs()))
    assert got["unit:title"].fact == {"key": "title", "scope": "unit", "classification": "input:card",
                                      "in_schema": True, "required": True}
    assert got["unit:state"].fact["classification"] == "bookkeeping" and got["unit:state"].fact["in_schema"] is False
    assert got["unit:coordination"].fact["in_schema"] is True


def test_a_unit_key_the_schema_declares_and_the_registry_does_not_is_stated_unclassified_and_refused():
    records = K.records_of(inputs(registry={}, bookkeeping=frozenset()))
    assert by_key(records)["unit:title"].fact["classification"] == "unclassified"
    bad = K.problems({r.id: r.as_json() for r in records})
    assert any("does not classify" in p for p in bad), bad


def test_the_two_key_spaces_do_not_collide_on_a_shared_name():
    schema = copy.deepcopy(SCHEMA)
    schema["properties"]["state"] = {}
    got = by_key(K.records_of(inputs(schema=schema)))
    assert {"state", "unit:state"} <= set(got) and got["state"].fact["scope"] == "control"


# ---------------------------------------------------------------------------------------------- the coverage

def test_a_closed_schema_is_complete_by_construction_and_an_open_one_is_a_lower_bound():
    closed = by_key(K.records_of(inputs()))["alpha"].coverage
    assert closed["label"] == C.COMPLETE and closed["registry"] == "aew.schemas:SCHEMAS" and closed["check"]
    open_schema = {**copy.deepcopy(SCHEMA), "additionalProperties": True}
    opened = by_key(K.records_of(inputs(schema=open_schema)))["alpha"].coverage
    assert opened["label"] == C.LOWER and "allows keys it does not declare" in opened["unresolved"][0]["why"]


def test_a_unit_key_is_always_a_lower_bound_whose_item_says_what_the_registry_check_cannot_reach():
    coverage = by_key(K.records_of(inputs()))["unit:title"].coverage
    assert coverage["label"] == C.LOWER and coverage["unresolved"] == [
        C.unresolved_item(K.REGISTRY[0], K.REGISTRY[1], K.UNIT_OPEN)]


# ------------------------------------------------------------------------------- the family's own record rules

def records_json() -> dict[str, dict[str, Any]]:
    return {r.id: r.as_json() for r in K.records_of(inputs())}


def test_sound_records_have_no_problem():
    assert K.problems(records_json()) == []


FAULTS = [
    ("a control key whose record key is another", "control-keys:alpha", ["fact", "key"], "beta", "the key is not"),
    ("a unit key whose record key lacks the scope", "control-keys:unit:title", ["fact", "key"], "name",
     "the key is not"),
    ("a scope that is neither", "control-keys:alpha", ["fact", "scope"], "other", "neither control nor unit"),
    ("a control fact without its flag", "control-keys:alpha", ["fact", "v2_only"], Ellipsis, "with its booleans"),
    ("a flag that is not a boolean", "control-keys:alpha", ["fact", "required"], "yes", "with its booleans"),
    ("a unit fact with a control flag", "control-keys:unit:title", ["fact", "initial"], True, "with its booleans"),
]


@pytest.mark.parametrize(("what", "rid", "path", "value", "fragment"), FAULTS, ids=[f[0] for f in FAULTS])
def test_each_planted_fault_in_a_record_is_refused_by_its_own_rule(what, rid, path, value, fragment):
    records = copy.deepcopy(records_json())
    node = records[rid]
    for step in path[:-1]:
        node = node[step]
    if value is Ellipsis:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    found = K.problems(records)
    assert found and any(fragment in p for p in found), (what, found)


# ------------------------------------------------------------------------------------------------- the page

def test_the_page_lists_each_key_with_its_flags_and_anchor_and_the_constants_that_are_not_state_keys():
    records = K.records_of(inputs())
    text = K.page(records, [("m.bridge", "ENV_KEY", "AEW_AGENT_KEY")])
    assert "`alpha` (required, initial): `m.init:make`" in text
    assert "`delta` (v2-only): `aew.engine.base:V2_ONLY_KEYS`" in text
    assert "`title` (input:card, in the schema, required)" in text
    assert "`m.bridge:ENV_KEY` = `AEW_AGENT_KEY`" in text
    assert "None." in K.page(records, [])


# ------------------------------------------------------------- orderings of the anchor (review of #261, N-10)

def test_a_key_named_in_the_initial_state_by_a_constant_keeps_that_constant_though_it_is_also_v2_only():
    sources = {"m.base": "PINS = 'delta'\n",
               "m.init": "from m.base import PINS\n\ndef make():\n    return {'alpha': 1, 'gamma': 2, PINS: 3}\n"}
    got = by_key(K.records_of(inputs(sources)))
    assert got["delta"].fact["v2_only"] and anchor(got["delta"]) == ("m.base", "PINS")


def test_two_constants_that_hold_one_key_anchor_it_at_the_first_by_module_whatever_the_order_given():
    sources = {"m.init": INIT, "m.b": "Y_KEY = 'beta_slot'\n", "m.a": "X_KEY = 'beta_slot'\n"}
    assert anchor(by_key(K.records_of(inputs(sources)))["beta_slot"]) == ("m.a", "X_KEY")
