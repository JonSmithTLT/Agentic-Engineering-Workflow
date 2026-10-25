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

import pytest

from aew.dashboard import projections as P
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
        if set(want["query"]) & set(server.LIMIT_PARAMETERS):  # every route with a limit parameter has bounds
            default, maximum = server.ROUTE_LIMITS.get(route, (P.LIMIT_DEFAULT, P.LIMIT_MAX))
            want["limit"] = {"default": default, "max": maximum,
                             "source": "route" if route in server.ROUTE_LIMITS else "server default"}
        assert r["fact"] == want, route
        assert r["coverage"]["label"] == "complete-by-construction" and r["basis"] == "enumerated"
        assert (r["anchor"]["module"], r["anchor"]["symbol"]) == (
            "aew.dashboard.server", "CONDITIONAL_HANDLERS" if want["conditional"] else "ROUTES")
        assert set(r["fact_coverage"]) == {k for k, v in want.items() if isinstance(v, list)}


def test_a_limit_the_record_states_is_the_one_the_server_normalises_with():
    """The bounds are observed, not re-derived: the server's own normaliser answers the default with no value, accepts
    the maximum, and refuses one above it."""
    for route, r in records().items():
        limit = r["fact"].get("limit")
        if not r["fact"].get("api", True):
            continue
        keys = sorted(set(r["fact"]["query"]) & set(server.LIMIT_PARAMETERS))
        assert (limit is not None) == bool(keys), route
        for key in keys:
            assert server.DashboardServer._normalized({key: None}, route) == {key: limit["default"]}, route
            assert server.DashboardServer._normalized({key: str(limit["max"])}, route) == {key: limit["max"]}, route
            with pytest.raises(P.InvalidRequest):
                server.DashboardServer._normalized({key: str(limit["max"] + 1)}, route)


def test_the_records_outside_the_api_are_the_branches_of_the_request_handler():
    others = {k: r for k, r in records().items() if r["fact"].get("api") is False}
    assert set(others) == {"/session/{rest}", "/{file}"}
    session, static = others["/session/{rest}"]["fact"], others["/{file}"]["fact"]
    assert (session["under"], session["handler"]) == (server.SESSION_PREFIX, "_exchange")
    assert static["handler"] == "_static" and static["outside"] == sorted({"/api/", server.SESSION_PREFIX})
    for r in others.values():
        assert r["basis"] == "static" and r["coverage"] == {"label": "lower-bound", "unresolved": []}


def test_a_path_outside_the_api_that_needs_a_part_of_the_server_says_which():
    """``/session/`` is no route while the server has no session table, and the static frontend is answered only while
    it has a static root (the server's own guards, which the record names)."""
    others = {k: r["fact"] for k, r in records().items() if r["fact"].get("api") is False}
    assert (others["/session/{rest}"]["conditional"], others["/session/{rest}"]["needs"]) == (True, "sessions")
    assert (others["/{file}"]["conditional"], others["/{file}"]["needs"]) == (True, "static_root")
    text = (ROOT / "src" / "aew" / "dashboard" / "server.py").read_text(encoding="utf-8")
    assert "if self.sessions is None:" in text and "if self.static_root is None:" in text
    assert hasattr(server.DashboardServer, "_exchange") and hasattr(server.DashboardServer, "_static")


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
    assert D.dispatch_calls(tree()) == [ast.unparse(calls[0].func)]  # the generator's own finder says the same


def test_every_read_of_the_request_path_in_the_handler_and_the_dispatch_is_a_declared_one():
    """A route reaches a handler by the dispatch, the branches of ``_handle`` or a read of the request path that is
    neither, so every read of ``url.path`` and ``h.path`` in those two methods is held to :data:`PATH_READS`, in both
    directions and by count. The other reading (``re`` on the text) finds the same reads."""
    src = CTX.sources()[D.SERVER]
    assert src.tree is not None
    reading = D.read(src.tree, CONSTANTS)
    assert D.path_read_problems(reading) == []
    assert sorted(reading.path_reads) == sorted(D.PATH_READS)
    assert sorted(T.read(src.text, CONSTANTS).path_reads) == sorted(D.PATH_READS)
    assert {s for s, *_ in reading.path_reads} == {f"{D.OWNER_CLASS}.{name}" for name in D.CHECKED}


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
    blind = D.Reading([], None, [], [], [])
    monkeypatch.setattr(D, "read", lambda tree, constants: blind)
    assert D.read(src.tree, CONSTANTS) != T.read(src.text, CONSTANTS)
    monkeypatch.undo()
    monkeypatch.setattr(T, "read", lambda text, constants, **kw: blind)
    assert D.read(src.tree, CONSTANTS) != T.read(src.text, CONSTANTS)


def test_a_stray_read_of_the_request_path_or_a_second_dispatch_makes_the_api_routes_lower_bound(monkeypatch):
    """The end of the proof: the label is earned only while the reads and the dispatch are the declared ones. Plant a
    read the declaration does not have, then a second call out of a table, and the API records stop being
    complete-by-construction and say why; the records outside the API are unaffected."""
    def api():
        return [r for r in D.build(CTX) if r.fact.get("api", True)]

    assert {r.coverage["label"] for r in api()} == {"complete-by-construction"}
    real = D.read

    def with_stray_read(tree, constants):
        reading = real(tree, constants)
        return reading._replace(path_reads=[*reading.path_reads,
                                            ("DashboardServer._respond", "url.path", "bare", "compare:Eq:'/health'")])

    monkeypatch.setattr(D, "read", with_stray_read)
    planted = api()
    assert {r.coverage["label"] for r in planted} == {"lower-bound"}
    assert any("'/health'" in i["why"] for i in planted[0].coverage["unresolved"])
    monkeypatch.undo()
    monkeypatch.setattr(D, "dispatch_calls", lambda tree: ["ROUTES.get(route)", "ROUTES['/x']"])
    planted = api()
    assert {r.coverage["label"] for r in planted} == {"lower-bound"}
    assert any("2 calls out of a route table" in i["why"] for i in planted[0].coverage["unresolved"])
