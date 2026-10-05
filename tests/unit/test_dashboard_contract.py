"""Contract 0.1.2 as the dashboard's tests see it: the accepted document loads, its digest is the one the acceptance
record pins, every response schema compiles, and every reason code the server can emit is registered."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aew.dashboard import contract as CT
from aew.dashboard import reasons as R
from aew.dashboard.server import QUERY_PARAMETERS, ROUTES, error_body, match_route

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)


def test_the_contract_is_the_accepted_one():
    approval = json.loads((ROOT / CT.APPROVAL_REL).read_text(encoding="utf-8"))
    assert approval["status"] == "ACCEPTED"
    assert CONTRACT.version == approval["contract_version"] == CT.SCHEMA_VERSION
    assert CONTRACT.sha256 == approval["sha256"], (
        "the contract changed: re-conform the server and the record together (its C0 review renews)")


def test_every_route_of_the_contract_is_served_and_nothing_else():
    assert set(CONTRACT.paths) == set(ROUTES) == set(CT.RESPONSE_SCHEMAS)
    for route in CONTRACT.paths:
        assert set(CONTRACT.paths[route]) == {"get", "head"}, route


def test_every_response_schema_compiles_and_rejects_an_empty_body():
    for name in list(CT.RESPONSE_SCHEMAS.values()) + [CT.ERROR_SCHEMA]:
        CONTRACT.validator(name)
        assert CONTRACT.violations(name, {}) != []


def test_the_query_parameters_served_are_the_contracts():
    for route in CONTRACT.paths:
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
