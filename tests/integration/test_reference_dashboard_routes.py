"""The dashboard-routes family of the generated reference (STG-12 S12-2, family 6): the routes the dashboard server
answers, read from its route tables and from the source of its request path by two independently written detectors.

The API routes are complete-by-construction because the server calls a route table in one place and names the tables in
three functions (the dispatch, the matcher and the pending-route derivation). The records are held to the tables in both
directions, the references to the declared set in both directions, and the two detectors (``interfaces_dashboard.py`` on
``ast``, ``interfaces_dashboard_text.py`` on ``re``) to each other on the server. What both miss is pinned in
``tests/unit/test_reference_interface_controls.py``, one probe each.

The heavy lanes run this because it reads ``src`` only: a pull request that adds a route changes ``src`` and so runs the
full gate.
"""

from __future__ import annotations

import ast
import sys
from functools import cache
from pathlib import Path
from typing import Any

from aew.dashboard import server

ROOT = Path(__file__).resolve().parents[2]


def _tool_modules():
    """The generator's family modules, with ``tools/`` on the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, interfaces_dashboard, interfaces_dashboard_text
    finally:
        sys.path.remove(here)
    return common, interfaces_dashboard, interfaces_dashboard_text


C, D, T = _tool_modules()
CTX = C.Context(ROOT)
CONSTANTS = {n: v for n, v in vars(server).items() if isinstance(v, str) and n.isupper()}


@cache
def records() -> dict[str, dict[str, Any]]:
    return {r.key: r.as_json() for r in D.build(CTX)}


def test_the_route_records_are_the_server_tables_both_ways():
    """One record per key of ``ROUTES`` and ``CONDITIONAL_HANDLERS`` and no other API route; each carries the tables'
    own parameters. Every table keyed by a route names only routes the server has."""
    found = {k: r for k, r in records().items() if r["fact"].get("api", True)}
    assert set(found) == set(server.ROUTES) | set(server.CONDITIONAL_HANDLERS)
    routes = set(found)
    for table in (server.QUERY_PARAMETERS, server.REPEATABLE_PARAMETERS, server.ROUTE_LIMITS, server.PRECHECKS):
        assert set(table) <= routes, sorted(set(table) - routes)
    assert server.CONDITIONAL_ROUTES == set(server.CONDITIONAL_HANDLERS)
    for route, r in found.items():
        want = {"route": route, "path": server.API_PREFIX + route, "methods": ["GET", "HEAD"],
                "conditional": route in server.CONDITIONAL_HANDLERS, "prechecked": route in server.PRECHECKS,
                "query": sorted(server.QUERY_PARAMETERS.get(route, ()))}
        if route in server.REPEATABLE_PARAMETERS:
            want["repeatable"] = sorted(server.REPEATABLE_PARAMETERS[route])
        if route in server.ROUTE_LIMITS:
            want["limit"] = dict(zip(("default", "max"), server.ROUTE_LIMITS[route], strict=True))
        assert r["fact"] == want, route
        assert r["coverage"]["label"] == "complete-by-construction" and r["basis"] == "enumerated"
        assert (r["anchor"]["module"], r["anchor"]["symbol"]) == (
            "aew.dashboard.server", "CONDITIONAL_HANDLERS" if want["conditional"] else "ROUTES")
        assert set(r["fact_coverage"]) == {k for k, v in want.items() if isinstance(v, list)}


def test_the_records_outside_the_api_are_the_branches_of_the_request_handler():
    others = {k: r for k, r in records().items() if r["fact"].get("api") is False}
    assert set(others) == {"/session/{rest}", "/{file}"}
    session, static = others["/session/{rest}"]["fact"], others["/{file}"]["fact"]
    assert (session["under"], session["handler"]) == (server.SESSION_PREFIX, "_exchange")
    assert static["handler"] == "_static" and static["outside"] == sorted({"/api/", server.SESSION_PREFIX})
    for r in others.values():
        assert r["basis"] == "static" and r["coverage"] == {"label": "lower-bound", "unresolved": []}


def tree() -> ast.Module:
    tree = CTX.sources()[D.SERVER].tree
    assert tree is not None
    return tree


def test_the_route_tables_are_named_only_where_the_dispatch_and_the_matcher_are():
    """The tables are complete-by-construction because nothing else names them: a function that served a route from a
    table would have to name it. The declared set is held to the reading in both directions, and the one place a table
    is called is the dispatch expression of ``_respond``."""
    reading = D.read(tree(), CONSTANTS)
    declared = {(table, symbol) for table, symbols in D.REFERENCES.items() for symbol in symbols}
    assert set(reading.references) == declared, (sorted(set(reading.references) ^ declared))
    methods = ("get", "items", "keys", "values")  # reading a table is not calling a route out of it
    calls = [node for node in ast.walk(tree()) if isinstance(node, ast.Call)
             and any(isinstance(n, ast.Name) and n.id in D.TABLES for n in ast.walk(node.func))
             and not (isinstance(node.func, ast.Attribute) and node.func.attr in methods
                      and isinstance(node.func.value, ast.Name) and node.func.value.id in D.TABLES)]
    assert len(calls) == 1, [ast.unparse(c) for c in calls]
    assert ast.unparse(calls[0].func) == "ROUTES.get(route) or CONDITIONAL_HANDLERS[route]"


def test_a_planted_second_dispatch_is_a_reference_the_declared_set_does_not_have():
    planted = ast.parse(ast.unparse(tree()) + "\n\ndef extra(p, q, m):\n    return ROUTES['/work'](p, q, m)\n")
    reading = D.read(planted, CONSTANTS)
    extra = set(reading.references) - {(t, s) for t, ss in D.REFERENCES.items() for s in ss}
    assert extra == {("ROUTES", "extra")}


def test_the_two_dashboard_detectors_agree_on_the_server():
    src = CTX.sources()[D.SERVER]
    assert src.tree is not None
    ours = D.read(src.tree, CONSTANTS)
    assert ours == T.read(src.text, CONSTANTS)
    assert ours.fallthrough == "_respond" and len(ours.branches) == 2 and ours.methods == ["GET", "HEAD"]


def test_a_detector_made_blind_makes_the_agreement_test_fail(monkeypatch):
    """The control of the agreement test itself: with either reading blind, the server no longer agrees."""
    src = CTX.sources()[D.SERVER]
    assert src.tree is not None
    assert D.read(src.tree, CONSTANTS) == T.read(src.text, CONSTANTS)
    blind = D.Reading([], None, [], [])
    monkeypatch.setattr(D, "read", lambda tree, constants: blind)
    assert D.read(src.tree, CONSTANTS) != T.read(src.text, CONSTANTS)
    monkeypatch.undo()
    monkeypatch.setattr(T, "read", lambda text, constants, **kw: blind)
    assert D.read(src.tree, CONSTANTS) != T.read(src.text, CONSTANTS)
