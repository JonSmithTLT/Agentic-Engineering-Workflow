"""The dashboard contract as the dashboard's tests see it: the accepted document loads, its digest is the one the
acceptance record pins, its version is in the series this server speaks, every served route's envelope carries its
schema's version, every response schema compiles, every reason code the server can emit is registered, and the
compatibility check that keeps a minor version additive holds element by element (register F20.8; the change note
``docs/design/proposals/dashboard-maps-and-history-search-v0.1.md``, §3)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from dashboard_contract import base_contract, note_text, proposed

from aew.dashboard import contract as CT
from aew.dashboard import projections as P
from aew.dashboard import reasons as R
from aew.dashboard.server import CONDITIONAL_ROUTES, QUERY_PARAMETERS, ROUTES, error_body, match_route, pending_routes

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
SERVED = set(ROUTES) | CONDITIONAL_ROUTES


def test_the_contract_is_the_accepted_one():
    approval = json.loads((ROOT / CT.APPROVAL_REL).read_text(encoding="utf-8"))
    assert approval["status"] == "ACCEPTED"
    assert CONTRACT.version == approval["contract_version"]
    assert CONTRACT.sha256 == approval["sha256"], (
        "the contract changed: re-conform the server and the record together (its C0 review renews)")
    assert CT.in_series(CONTRACT.version), f"this server speaks 0.1.x from {CT.BASE_VERSION}, not {CONTRACT.version}"


def test_every_served_routes_envelope_carries_its_schemas_version():
    """An envelope's ``schema_version`` is the contract version that defined that response's schema: the 0.1.2 routes
    keep emitting 0.1.2 under a later minor version, and a route a minor version adds emits that version."""
    assert set(P.ENVELOPE_VERSION) == SERVED
    for route in SERVED:
        schema = CONTRACT.response_schema(route)
        assert CONTRACT.envelope_version(schema) == P.ENVELOPE_VERSION[route], route
        assert CT.in_series(P.ENVELOPE_VERSION[route])
        assert CT.parse_version(P.ENVELOPE_VERSION[route]) <= CT.parse_version(CONTRACT.version), route


def test_every_served_route_is_in_the_contract_and_the_rest_are_pending():
    """Served and conditional routes are contract routes with GET and HEAD; whatever else the accepted contract holds
    is pending, derived and never listed, so a route a new contract version adds or renames needs no edit here."""
    assert SERVED <= set(CONTRACT.paths)
    assert set(CT.RESPONSE_SCHEMAS) == SERVED
    assert not set(ROUTES) & CONDITIONAL_ROUTES
    for route in SERVED:
        assert set(CONTRACT.paths[route]) >= {"get", "head"}, route
    assert pending_routes(CONTRACT.paths) == set(CONTRACT.paths) - SERVED


def test_the_routes_the_note_adds_are_pending_and_none_is_served():
    """S0 serves none of the six routes; each answers as this server answers without it, which today's routing
    decides: no template matches a maps route, and ``/history/search`` matches the ``/history/{id}`` template."""
    added = set(proposed(note_text(), base_contract())["paths"]) - set(base_contract()["paths"])
    assert added == {"/maps", "/maps/structural", "/maps/structural/{root}", "/maps/structural/{root}/inputs",
                     "/maps/diff", "/history/search"}
    assert pending_routes(set(CONTRACT.paths) | added) >= added
    for route in added - {"/history/search"}:
        assert match_route(route.replace("{root}", "0" * 64)) is None, route
    assert match_route("/history/search") == ("/history/{id}", {"id": "search"})


def test_every_response_schema_compiles_and_rejects_an_empty_body():
    for name in list(CT.RESPONSE_SCHEMAS.values()) + [CT.ERROR_SCHEMA]:
        CONTRACT.validator(name)
        assert CONTRACT.violations(name, {}) != []
    assert CT.compile_problems(CONTRACT.document) == []


def test_the_query_parameters_served_are_the_contracts():
    for route in SERVED:
        declared = set(CONTRACT.query_parameters(route))
        served = set(QUERY_PARAMETERS.get(route, frozenset()))
        extra = served - declared
        # The only addition: paging a record's annotations, which the contract's HistoryDetail cursor implies.
        assert extra <= ({"annotations_cursor", "annotations_limit"} if route == "/history/{id}" else set()), route
        assert declared <= served, (route, declared - served)


def test_routes_match_by_template():
    assert match_route("/work") == ("/work", {})
    assert match_route("/work/T-0001") == ("/work/{id}", {"id": "T-0001"})
    assert match_route("/history/integrity") == ("/history/integrity", {})
    assert match_route("/history/AU-0001") == ("/history/{id}", {"id": "AU-0001"})
    assert match_route("/work/") is None and match_route("/work/a/b") is None and match_route("/queue") is None


def test_error_bodies_conform_and_use_registered_codes():
    for code in R.REASONS:
        body = error_body(code)
        assert CONTRACT.violations(CT.ERROR_SCHEMA, body) == []
    with pytest.raises(KeyError):
        R.reason("MADE_UP")


def test_codes_in_finds_every_nested_reason():
    body = {"code": "NOT_FOUND", "message": "x", "reasons": [{"code": "A", "message": None}],
            "data": {"items": [{"health": {"reasons": [{"code": "B", "message": "m"}]}}]}}
    assert R.codes_in(body) == {"NOT_FOUND", "A", "B"}


# ---------------------------------------------------------------------------------------------- the version rule

@pytest.mark.parametrize("version", ["0.1.2", "0.1.3", "0.1.10", "0.1.99"])
def test_a_later_minor_version_is_accepted_without_an_edit(version):
    assert CT.in_series(version)


@pytest.mark.parametrize("version", ["0.1.1", "0.1.0", "0.2.0", "1.1.2", "0.1.x", "0.1", "v0.1.2", "0.1.2 ",
                                     "0.01.2", "0.1.02", "0.1.2\n", "\n0.1.2", ""])
def test_a_version_outside_the_series_or_unparsable_is_refused(version):
    assert not CT.in_series(version)


def test_versions_compare_as_integers_not_strings():
    assert CT.parse_version("0.1.10") > CT.parse_version("0.1.2")
    assert "0.1.10" < "0.1.2"  # what a string comparison would have concluded
    with pytest.raises(ValueError):
        CT.parse_version("0.1.x")


# ---------------------------------------------------------------------------------------------- the check itself
# Unit cases on scratch contracts, each against 0.1.2 with every 0.1.2 path covered (change note §3.1).

@pytest.fixture(scope="module")
def base() -> dict[str, Any]:
    return base_contract()


def check(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    return CT.compatibility(old, new, set(old["paths"]))


def test_the_proposed_additions_pass_and_the_unchanged_contract_passes(base):
    assert check(base, base) == []
    assert check(base, proposed(note_text(), base)) == []


def test_an_optional_property_added_to_an_existing_response_object_fails(base):
    new = copy.deepcopy(base)
    new["components"]["schemas"]["Invocation"]["properties"]["extra"] = {"type": "string"}
    assert "#/components/schemas/Invocation changed" in check(base, new)


def test_a_new_enum_value_in_an_existing_response_schema_fails(base):
    """0.1.2 closes its values with ``const`` (every envelope's ``schema_version``) and leaves the rest open with
    ``x-known-values``; widening a closed value set breaks a strict client either way."""
    widened = copy.deepcopy(base)
    version = widened["components"]["schemas"]["WorkResponse"]["properties"]["schema_version"]
    del version["const"]
    version["enum"] = ["0.1.2", "0.1.3"]
    assert check(base, widened) == ["#/components/schemas/WorkResponse changed"]
    closed = copy.deepcopy(base)
    closed["components"]["schemas"]["WorkState"]["enum"] = ["READY", "RUNNING"]
    more = copy.deepcopy(closed)
    more["components"]["schemas"]["WorkState"]["enum"].append("PARKED")
    assert "#/components/schemas/WorkState changed" in check(closed, more)


def test_a_changed_bound_and_a_removed_field_fail(base):
    bound = copy.deepcopy(base)
    bound["components"]["schemas"]["Reason"]["properties"]["code"]["maxLength"] = 10
    assert "#/components/schemas/Reason changed" in check(base, bound)
    removed = copy.deepcopy(base)
    del removed["components"]["schemas"]["Invocation"]["properties"]["role"]
    assert check(base, removed) != []


def test_descriptions_and_extension_keys_are_not_compared(base):
    new = copy.deepcopy(base)
    integration = new["components"]["schemas"]["Integration"]
    integration["description"] = "reworded"
    for prop in integration["properties"].values():
        if "x-known-values" in prop:
            prop["x-known-values"] = [*prop["x-known-values"], "integrated"]  # F20's note: an annotation only
    assert check(base, new) == []


def test_a_property_named_description_is_a_field_not_a_keyword():
    old = {"paths": {"/a": {"get": {"responses": {"200": {"$ref": "#/components/schemas/A"}}}}},
           "components": {"schemas": {"A": {"type": "object", "properties": {"description": {"type": "string"}}}}}}
    new = copy.deepcopy(old)
    new["components"]["schemas"]["A"]["properties"]["description"] = {"type": "integer"}
    assert check(old, new) == ["#/components/schemas/A changed"]
    del new["components"]["schemas"]["A"]["properties"]["description"]
    assert check(old, new) == ["#/components/schemas/A changed"]


def _work_parameter(**fields: Any) -> dict[str, Any]:
    return {"name": "extra", "in": "query", "schema": {"type": "string"}, **fields}


def test_a_new_optional_query_parameter_on_work_passes(base):
    new = copy.deepcopy(base)
    for method in ("get", "head"):
        new["paths"]["/work"][method]["parameters"].append(_work_parameter())
    assert check(base, new) == []


def test_a_new_required_query_parameter_on_work_fails(base):
    new = copy.deepcopy(base)
    new["paths"]["/work"]["get"]["parameters"].append(_work_parameter(required=True))
    assert check(base, new) == ["/work GET: new parameter extra (query) is required"]


def test_an_existing_parameter_changed_or_removed_fails(base):
    changed = copy.deepcopy(base)
    limit = next(p for p in changed["paths"]["/work"]["get"]["parameters"] if p["name"] == "limit")
    limit["schema"]["maximum"] = 100
    assert "/work GET: parameter limit (query) changed" in check(base, changed)
    removed = copy.deepcopy(base)
    removed["paths"]["/work"]["get"]["parameters"] = [
        p for p in removed["paths"]["/work"]["get"]["parameters"] if p["name"] != "limit"]
    assert "/work GET: parameter limit (query) removed" in check(base, removed)


def test_a_capability_key_may_be_added_and_nothing_else_about_capabilities_may_change(base):
    added = copy.deepcopy(base)
    added["components"]["schemas"]["Capabilities"]["properties"]["maps"] = {"$ref": CT.CAPABILITY_REF,
                                                                            "description": "the maps pages"}
    assert check(base, added) == []
    for change in ({"type": "string"}, {"$ref": CT.CAPABILITY_REF, "deprecated": True}):
        other = copy.deepcopy(base)
        other["components"]["schemas"]["Capabilities"]["properties"]["maps"] = change
        assert check(base, other) == ["#/components/schemas/Capabilities changed"], change
    required = copy.deepcopy(added)
    required["components"]["schemas"]["Capabilities"]["required"] = ["maps"]
    assert check(base, required) == ["#/components/schemas/Capabilities changed"]
    removed = copy.deepcopy(base)
    del removed["components"]["schemas"]["Capabilities"]["properties"]["queue"]
    assert check(base, removed) == ["#/components/schemas/Capabilities changed"]


def test_a_covered_path_that_loses_head_or_disappears_fails(base):
    no_head = copy.deepcopy(base)
    del no_head["paths"]["/work"]["head"]
    assert check(base, no_head) == ["/work: HEAD removed"]
    gone = copy.deepcopy(base)
    del gone["paths"]["/activity"]
    assert "/activity: removed" in check(base, gone)


def test_a_new_path_with_new_schemas_passes(base):
    new = copy.deepcopy(base)
    new["components"]["schemas"]["Thing"] = {"type": "object", "additionalProperties": False}
    new["paths"]["/things"] = {"get": {"responses": {"200": {"description": "x", "content": {"application/json": {
        "schema": {"$ref": "#/components/schemas/Thing"}}}}}}, "head": {"responses": {"200": {"description": "x"}}}}
    assert check(base, new) == []


def test_a_changed_response_status_set_fails(base):
    new = copy.deepcopy(base)
    new["paths"]["/project"]["get"]["responses"]["418"] = {"description": "new"}
    assert check(base, new) == ["/project GET: responses changed"]


def test_paths_outside_the_covered_set_are_never_compared(base):
    new = copy.deepcopy(base)
    del new["paths"]["/work"]["head"]
    assert CT.compatibility(base, new, {"/project"}) == []
    assert CT.compatibility(base, new, set()) == []
