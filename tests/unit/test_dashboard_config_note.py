"""The configuration read's change note against the contract and the engine (register F46.1, slice F1b; the note's
§3.2 and §6).

Appendix A must compile and, merged into the accepted 0.1.3 (vendored), pass the compatibility check with every 0.1.3
path covered; against the accepted contract it is checked in the mode its status line sets, as the 0.1.3 note is.
There is no engine-side schema for the projection, so every open enum and every bound in the appendix is pinned here
to the engine constant that owns it: the note cannot restate a vocabulary the code has moved past. The shapes against
the projection's real output are `tests/integration/test_dashboard_config_note_shapes.py`.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from dashboard_contract import (
    CONFIG_NOTE_REL,
    ROOT,
    adopted,
    config_base_contract,
    note_problems,
    note_text,
    proposed,
)

from aew.dashboard import contract as CT
from aew.dashboard.contract import Contract
from aew.engine import configuration as C
from aew.engine import steering as S
from aew.harness import agentenv, models
from aew.policy import config_paths as P
from aew.policy import execution as X
from aew.schemas import schema

ROUTES = {"/configuration", "/configuration/execution"}
ENVELOPES = {"ConfigurationIndexResponse": "ConfigurationIndex",
             "ConfigurationExecutionResponse": "ExecutionConfiguration"}


def text() -> str:
    return note_text(rel=CONFIG_NOTE_REL)


@pytest.fixture(scope="module")
def base() -> dict[str, Any]:
    return config_base_contract()


@pytest.fixture(scope="module")
def mine(base) -> dict[str, Any]:
    return proposed(text(), base)


@pytest.fixture(scope="module")
def contract(mine) -> Contract:
    return Contract(raw=yaml.safe_dump(mine, sort_keys=False).encode("utf-8"))


def at(node: Any, *keys: str) -> Any:
    for key in keys:
        node = node[key]
    return node


def test_the_note_agrees_with_the_accepted_contract(base):
    accepted = Contract(ROOT / CT.CONTRACT_REL).document
    assert note_problems(text(), accepted, base) == []


def test_the_appendix_compiles_and_only_adds_to_0_1_3(base, mine):
    assert CT.compile_problems(mine) == []
    assert CT.compatibility(base, mine, set(base["paths"])) == []  # every 0.1.3 path covered
    assert mine["info"]["version"] == "0.1.4" and CT.in_series(mine["info"]["version"])
    assert set(mine["paths"]) - set(base["paths"]) == ROUTES
    for envelope, data in ENVELOPES.items():
        props = mine["components"]["schemas"][envelope]["properties"]
        assert props["schema_version"]["const"] == "0.1.4", envelope
        assert props["data"]["$ref"] == f"#/components/schemas/{data}"
    assert mine["components"]["schemas"]["Capabilities"]["properties"]["configuration"]["$ref"] == CT.CAPABILITY_REF
    assert mine["info"]["description"] == base["info"]["description"]  # the compatibility rule is unchanged


def test_the_routes_stay_pending_until_f1c_serves_them():
    """F1b serves nothing: the two routes are not served or conditional, and have no response schema entry yet."""
    from aew.dashboard.server import CONDITIONAL_ROUTES
    from aew.dashboard.server import ROUTES as SERVED

    assert not ROUTES & (set(SERVED) | set(CONDITIONAL_ROUTES)) and not ROUTES & set(CT.RESPONSE_SCHEMAS)
    assert adopted(text()) is None  # proposed: the adopted line is F1c's to write


def x_aew_classes() -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("x-aew-class"), str):
                found.add(node["x-aew-class"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema("execution"))
    return found


EXECUTION = ("ExecutionConfiguration", "properties")
PROFILE = ("ExecutionProfile", "properties")
IDENTITY_ERROR = (*PROFILE, "identity_error", "anyOf", 0, "properties")
OBSERVED = (*EXECUTION, "observed", "properties")


def known_values() -> list[tuple[tuple[Any, ...], Any]]:
    """Every open enum of the appendix and the engine owner of its values."""
    return [
        (("ConfigurationDocumentState",), list(C.STATES)),
        (("ConfigurationIndex", "properties", "manifest", "properties", "state"), [C.ADOPTED, C.DRIFTED]),
        (("ConfigurationIndex", "properties", "activities", "items", "properties", "activity"),
         [a for a, _state, _reason in C.ACTIVITIES]),
        (("FieldValue", "properties", "withheld"), list(C.WITHHELD_REASONS)),
        (("FieldValue", "properties", "effective_source"), list(C.EFFECTIVE_SOURCES)),
        (("FieldValue", "properties", "class"), sorted(x_aew_classes())),
        (("FieldValue", "properties", "edit"), list(C.EDIT_SCOPES)),
        (("Violation", "properties", "code"), sorted(C.DATA_CODES - {C.YAML_SYNTAX})),
        ((*EXECUTION, "routing", "properties", "resolution_order", "items"), list(C.RESOLUTION_ORDER)),
        ((*OBSERVED, "checked_in"), list(C.OBSERVED_CAPTIONS)),
        ((*OBSERVED, "provider_env", "items", "properties", "problem", "anyOf", 0),
         list(agentenv.PROVIDER_ENV_PROBLEMS)),
        ((*EXECUTION, "controls", "properties", "steering", "properties", "effective", "properties", "source"),
         list(S.EFFECTIVE_SOURCES)),
        ((*PROFILE, "identity_rule"), list(C.IDENTITY_RULES)),
        ((*IDENTITY_ERROR, "code"), [*models.REFUSAL_REASONS, C.FIELD_WITHHELD]),
        ((*IDENTITY_ERROR, "withheld_reason", "anyOf", 0), list(C.WITHHELD_REASONS)),
    ]


@pytest.mark.parametrize("where,owner", known_values(), ids=lambda v: "/".join(map(str, v)) if isinstance(
    v, tuple) else None)
def test_every_open_enum_is_its_engine_owners_set(mine, where, owner):
    node = at(mine["components"]["schemas"], *where)
    assert node["type"] == "string" and "enum" not in node  # open: an unknown value is shown with a warning
    listed = node["x-known-values"]
    if where in (("ConfigurationDocumentState",), (*EXECUTION, "routing", "properties", "resolution_order", "items")):
        assert listed == owner  # an order the page shows: precedence, resolution order
    else:
        assert sorted(listed) == sorted(owner) and len(set(listed)) == len(listed)


def test_the_closed_values_are_the_engines(mine):
    s = mine["components"]["schemas"]
    assert s["FieldValue"]["properties"]["state"]["enum"] == ["SET", "NULL", "ABSENT"]
    assert s["YamlError"]["properties"]["code"]["const"] == C.YAML_SYNTAX
    controls = at(s, *EXECUTION, "controls", "properties")
    assert controls["containment"]["properties"]["effective"]["const"] == C.NOT_SUPPLIED
    connection = s["Connection"]["properties"]
    assert connection["endpoint"]["const"] == connection["credential_sources"]["properties"]["saved_login"][
        "const"] == C.NOT_SUPPLIED
    assert s["ConnectionId"]["pattern"] == r"^conn-[0-9a-f]{16}$" and C.connection_id("p", "h", "v").startswith("conn-")


def bounds() -> list[tuple[tuple[Any, ...], str, int]]:
    """Every list's maxItems and every string's maxLength, against the engine's cap."""
    shown, model_id = P.SHOWN_KEY_MAX_BYTES, C.MODEL_ID_MAX_BYTES
    return [
        (("ConfigurationIndex", "properties", "documents"), "maxItems", C.MAX_DOCUMENTS),
        ((*EXECUTION, "document", "properties", "violations"), "maxItems", C.MAX_VIOLATIONS),
        ((*EXECUTION, "profiles"), "maxItems", C.MAX_PROFILES),
        (("RouteTable", "properties", "entries"), "maxItems", C.MAX_ROUTE_ENTRIES),
        ((*PROFILE, "routed_by"), "maxItems", C.MAX_ROUTED_BY),
        ((*EXECUTION, "connections"), "maxItems", C.MAX_CONNECTIONS),
        (("Connection", "properties", "profiles"), "maxItems", C.MAX_CONNECTION_PROFILES),
        ((*EXECUTION, "provider_env", "properties", "entries"), "maxItems", C.MAX_PROVIDER_ENV),
        ((*OBSERVED, "provider_env"), "maxItems", C.MAX_PROVIDER_ENV),
        (("FieldValue", "properties", "allowed"), "maxItems", C.MAX_ALLOWED),
        ((*EXECUTION, "controls", "properties", "switches"), "maxItems", C.MAX_SWITCHES),
        ((*EXECUTION, "routing", "properties", "resolution_order"), "maxItems", len(C.RESOLUTION_ORDER)),
        (("FieldValue", "properties", "value"), "maxLength", C.MAX_STRING_BYTES),
        (("FieldValue", "properties", "effective"), "maxLength", C.MAX_STRING_BYTES),
        (("FieldValue", "properties", "description"), "maxLength", C.MAX_DESCRIPTION_BYTES),
        (("FieldValue", "properties", "allowed", "items"), "maxLength", C.MAX_STRING_BYTES),
        ((*EXECUTION, "provider_env", "properties", "entries", "items", "properties", "name", "anyOf", 0),
         "maxLength", C.MAX_STRING_BYTES),
        ((*OBSERVED, "provider_env", "items", "properties", "name", "anyOf", 0), "maxLength", C.MAX_STRING_BYTES),
        (("ConfigurationDocument", "properties", "document", "anyOf", 0), "maxLength", shown),
        ((*PROFILE, "name", "anyOf", 0), "maxLength", shown),
        (("RouteTable", "properties", "entries", "items", "properties", "key", "anyOf", 0), "maxLength", shown),
        (("Violation", "properties", "extra_key", "anyOf", 0), "maxLength", shown),
        (("Connection", "properties", "harness"), "maxLength", C.HARNESS_NAME_MAX_BYTES),
        (("Connection", "properties", "provider"), "maxLength", model_id),
        (("ModelIdentity", "properties", "catalog_id"), "maxLength", model_id),
        (("ModelIdentity", "properties", "provider"), "maxLength", model_id),
        (("ModelIdentity", "properties", "model"), "maxLength", model_id),
        (("ModelIdentity", "properties", "harness_ref"), "maxLength", 2 * model_id + len(models.SEP)),
        ((*IDENTITY_ERROR, "suggestion", "anyOf", 0), "maxLength", model_id),
    ]


@pytest.mark.parametrize("where,keyword,cap", bounds(), ids=lambda v: "/".join(map(str, v)) if isinstance(
    v, tuple) else None)
def test_every_bound_is_the_engines_cap(mine, where, keyword, cap):
    assert at(mine["components"]["schemas"], *where)[keyword] == cap


def test_the_loose_bounds_hold_every_value_the_engine_can_write(mine):
    """The few bounds without an engine cap of their own are at least the longest value the engine writes there."""
    s = mine["components"]["schemas"]
    controls = at(s, *EXECUTION, "controls", "properties")
    steering_modes = schema("execution")["properties"]["steering"]["properties"]["mode"]["enum"]
    effective_mode = controls["steering"]["properties"]["effective"]["properties"]["mode"]["anyOf"][0]["maxLength"]
    assert effective_mode >= max(map(len, steering_modes))
    switch_default = controls["switches"]["items"]["properties"]["default"]["maxLength"]
    assert switch_default >= max(len(allowed[0]) for allowed in X.STRING_SWITCHES.values())
    assert len(C.ACTIVITIES) <= at(s, "ConfigurationIndex", "properties", "activities", "maxItems")


def unclosed(node: Any, where: str = "") -> list[str]:
    """Every object schema (one with `properties`) under `node` not closed with `additionalProperties: false`."""
    out: list[str] = []
    if isinstance(node, dict):
        if "properties" in node and node.get("additionalProperties") is not False:
            out.append(where or "/")
        for key, value in node.items():
            if key not in ("if", "then", "else"):  # conditions on the (closed) parent, not shapes the engine emits
                out += unclosed(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out += unclosed(value, f"{where}/{i}")
    return out


def test_every_object_the_appendix_adds_or_changes_is_closed(base, mine):
    """The note says every object is closed (§5, §6): an open one would let the engine add a field the web developer's
    parser then never sees declared. Walks every schema the appendix adds, and the `Capabilities` it changes."""
    schemas = mine["components"]["schemas"]
    added = {n: s for n, s in schemas.items() if n not in base["components"]["schemas"]}
    assert added and unclosed(added) == []
    # Capabilities is open by 0.1.3's own design (the compatibility check's exception); what 0.1.4 changes in it is one
    # `configuration` property, a $ref to the shared Capability schema, which is tested above.
    assert unclosed(schemas["Capability"]) == [] and set(schemas["Capabilities"]["properties"]) - set(
        base["components"]["schemas"]["Capabilities"]["properties"]) == {"configuration"}
    assert unclosed({"X": {"properties": {"a": {"type": "string"}}, "additionalProperties": True}}) == ["/X"]
    assert unclosed({"X": {"properties": {"a": {"type": "string"}}}}) == ["/X"]


# Bounds the engine does not enforce: the contract states them, and the values the engine writes are shown to fit.
CONTRACT_ONLY = [
    (("ConfigurationPath",), "maxLength", 256),
    ((*PROFILE, "routed_by", "items"), "maxLength", 256),
    ((*IDENTITY_ERROR, "hint"), "maxLength", 512),
    ((*OBSERVED, "caption"), "maxLength", 512),
    ((*EXECUTION, "pins_note"), "maxLength", 512),
    (("Violation", "properties", "expected", "anyOf", 0), "maxLength", 512),
]


@pytest.mark.parametrize("where,keyword,bound", CONTRACT_ONLY, ids=lambda v: "/".join(map(str, v)) if isinstance(
    v, tuple) else None)
def test_the_contract_only_bounds_are_the_notes_and_named_there(mine, where, keyword, bound):
    assert at(mine["components"]["schemas"], *where)[keyword] == bound
    assert "contract-only bounds" in text() and "`ConfigurationPath`" in text()


def schema_side(node: Any) -> list[str]:
    """What `configuration._expected` can render for a schema keyword: a scalar, or a type/enum/required list joined."""
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("description", "title") or key.startswith("x-"):
                continue
            if key in ("type", "enum", "required") and isinstance(value, list):
                out.append("|".join(map(str, value)))
            elif isinstance(value, (str, int, float, bool)):
                out.append(str(value))
            out += schema_side(value)
    elif isinstance(node, list):
        for value in node:
            out += schema_side(value)
    return out


def test_the_values_the_engine_writes_fit_the_contract_only_bounds(mine):
    s = mine["components"]["schemas"]
    longest_name = max(len(k) for k in _property_names(schema("execution")))
    key = "k" * P.SHOWN_KEY_MAX_BYTES  # a shown key is at most 128 bytes
    assert P.shown_key(key)
    worst_path = max(len(P.encode(("profiles", key, "x" * longest_name), {"profiles": {key: {}}})),
                     len(P.encode(("routing", "cards", key), {"routing": {"cards": {key: 0}}})),
                     len(P.encode(("profiles", "p", "x" * longest_name), {"profiles": {"p": {}}})))
    assert worst_path <= s["ConfigurationPath"]["maxLength"]
    assert len("card:" + key) <= at(s, *PROFILE, "routed_by", "items")["maxLength"]
    assert len(C.MODEL_ID_HINT) <= at(s, *IDENTITY_ERROR, "hint")["maxLength"]
    assert max(map(len, C.OBSERVED_CAPTIONS.values())) <= at(s, *OBSERVED, "caption")["maxLength"]
    assert len(C.PINS_NOTE) <= at(s, *EXECUTION, "pins_note")["maxLength"]
    assert max(map(len, schema_side(schema("execution")))) <= at(
        s, "Violation", "properties", "expected", "anyOf", 0)["maxLength"]


def _property_names(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            found |= set(node["properties"])
        for value in node.values():
            found |= _property_names(value)
    elif isinstance(node, list):
        for value in node:
            found |= _property_names(value)
    return found


COMPLETE = {"activities", "allowed", "resolution_order", "switches", "reasons"}  # the note's §5.3


def unclassified(node: Any, where: str = "") -> list[str]:
    """Every array property of the appendix's schemas with neither a boolean truncation flag beside it nor a place in
    the note's complete-by-invariant list."""
    out: list[str] = []
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for name, prop in props.items():
                if isinstance(prop, dict) and prop.get("type") == "array" and name not in COMPLETE:
                    flag = props.get(f"{name}_truncated") or props.get("truncated")
                    if not (isinstance(flag, dict) and flag.get("type") == "boolean"):
                        out.append(f"{where}/{name}")
        for key, value in node.items():
            out += unclassified(value, f"{where}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out += unclassified(value, f"{where}/{i}")
    return out


def test_every_list_of_the_appendix_is_complete_or_flagged(base, mine):
    """D4 (the proposal's §3.5), against the schemas themselves: every array the appendix adds has a truncation flag
    beside it or is complete by an invariant; the check fails on an unflagged list."""
    added = {n: s for n, s in mine["components"]["schemas"].items() if n not in base["components"]["schemas"]}
    assert unclassified(added) == []
    assert unclassified({"X": {"properties": {"items": {"type": "array"}}}}) == ["/X/items"]


FOUR_CASES = {
    "set_withheld": {"path": "/profiles/@0/model", "state": "SET", "withheld": "credential_shaped",
                     "class": "legality_affecting", "edit": "F46.2", "editable": False},
    "null": {"path": "/profiles/x/effort", "state": "NULL", "value": None, "class": "legality_affecting",
             "edit": "F46.2", "editable": False},
    "absent": {"path": "/profiles/x/max_steps", "state": "ABSENT", "class": "legality_affecting", "edit": "F46.2",
               "editable": False},
    "supplied_effective": {"path": "/steering/envelope/repetition_n", "state": "ABSENT", "effective": 2,
                           "effective_source": "default", "class": "operational", "edit": "later",
                           "editable": False},
}
BROKEN = {
    "set_withheld_with_null": FOUR_CASES["set_withheld"] | {"value": None},
    "set_shown_without_value": {k: v for k, v in FOUR_CASES["set_withheld"].items() if k != "withheld"},
    "set_shown_null": {k: v for k, v in FOUR_CASES["set_withheld"].items() if k != "withheld"} | {"value": None},
    "null_withheld": FOUR_CASES["null"] | {"withheld": "credential_shaped"},
    "null_without_value": {k: v for k, v in FOUR_CASES["null"].items() if k != "value"},
    "absent_with_value": FOUR_CASES["absent"] | {"value": 3},
    "absent_withheld": FOUR_CASES["absent"] | {"withheld": "not_a_name"},
    "unknown_state": FOUR_CASES["absent"] | {"state": "MISSING"},
}


@pytest.mark.parametrize("case", sorted(FOUR_CASES))
def test_fieldvalue_four_cases_validate(contract, case):
    """D2 (the proposal's §3.1), the schema half: each of the four cases is valid."""
    assert contract.violations("FieldValue", FOUR_CASES[case]) == []


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_fieldvalue_outside_the_four_cases_fails(contract, case):
    """A withheld SET carrying `value: null` (and every other mix of the cases) fails the schema, so a withheld value
    can never read as a configured null."""
    assert contract.violations("FieldValue", BROKEN[case]) != []


def test_a_yaml_error_without_a_mark_is_null_and_a_mark_is_one_based(contract):
    """The proposal's web 2, the schema half: no mark is `line: null, column: null`; a mark is one-based."""
    assert contract.violations("YamlError", C.yaml_error(None)) == []
    assert contract.violations("YamlError", {"code": C.YAML_SYNTAX, "line": 3, "column": 1}) == []
    assert contract.violations("YamlError", {"code": C.YAML_SYNTAX, "line": 0, "column": 1}) != []


def test_a_path_with_an_at_segment_is_a_valid_locator_but_never_an_identity(contract):
    """D3: `@i` is a display-only extension; the schema admits it as a locator, and `config_paths` never takes it for
    an identity (the edit target F46.2 refuses)."""
    for path in ("", "/profiles/@0/model", "/routing/cards/@2", "/a~1b/a~0b"):
        assert contract.validator("ConfigurationPath").is_valid(path), path
    assert not contract.validator("ConfigurationPath").is_valid("profiles/x")
    assert not P.is_identity("/profiles/@0/model") and P.is_identity("/profiles/x/model")
