"""The planted controls of the STG-02 families of the generated reference (STG-12 S12-2, family 6b): the routes the
slice's server serves, the actions its command path admits and the causes it refuses with
(``tools/reference_families/stg02*.py``).

Every rule has its planted right case, wrong case and missing case, so a rule that stopped working would fail. That
the records equal the vendored files they are read from, that the two detectors of each recogniser agree on the real
source, and that a request to every route reaches the owners the reading says it does, is in
``tests/integration/test_reference_stg02.py``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, stg02_commands, stg02_commands_text, stg02_server, stg02_server_text
    finally:
        sys.path.remove(here)
    return common, stg02_commands, stg02_commands_text, stg02_server, stg02_server_text


C, K, KT, S, ST = _tools()

# ------------------------------------------------------------------------------------------------ the server's routes

SERVER = '''
COMMANDS = "/o01/v0/command-sets"
OWNER_GET = re.compile(r"/o01/v0/owner-operations/([^/]*)/([^/]*)")


def handle(s, method, raw_path, headers, body):
    path = raw_path
    if path.startswith("/v1/read/"):
        return _read(s, method, path)
    if path == COMMANDS:
        return 1
    if path.startswith("/o01/v0/owner-operations/"):
        return 2
    if s.test_routes and method == "POST" and path in ("/_test/read-entitlement", "/_test/engine-outage"):
        return 3
    return 4


def _read(s, method, path):
    if path == "/v1/read/waiting":
        return 5
    for prefix, call, lo, hi in (("/v1/read/runs/", s.reads.run, 1, 300),
                                 ("/v1/read/continuation-state/", s.reads.continuation, 2, 256)):
        if path.startswith(prefix) and "/" not in path[len(prefix):]:
            return call


def _owner_get(s, path):
    m = OWNER_GET.fullmatch(path)
    return m
'''
VALUES = {"COMMANDS": "/o01/v0/command-sets",
          "OWNER_GET": re.compile(r"/o01/v0/owner-operations/([^/]*)/([^/]*)")}
TEMPLATES = ["/v1/read/waiting", "/v1/read/runs/{execution_id}", "/v1/read/continuation-state/{work_id}",
             "/v1/read/work/{work_kind}/{work_id}",
             "/o01/v0/owner-operations/{owner}/{operation_ref}", "/o01/v0/command-sets"]


def both(source: str):
    return S.read(ast.parse(source), VALUES), ST.read(source, VALUES)


def test_both_readings_find_the_exact_routes_the_prefixes_the_pattern_and_the_test_routes():
    ours, theirs = both(SERVER)
    assert ours == theirs
    assert ours.exact == ["/_test/engine-outage", "/_test/read-entitlement", "/o01/v0/command-sets", "/v1/read/waiting"]
    assert ours.prefixes == ["/o01/v0/owner-operations/", "/v1/read/", "/v1/read/continuation-state/",
                             "/v1/read/runs/"]
    assert ours.patterns == ["/o01/v0/owner-operations/([^/]*)/([^/]*)"]
    assert ours.test_methods == {"/_test/engine-outage": "POST", "/_test/read-entitlement": "POST"}


def test_a_substring_test_is_not_a_route():
    """``"/" not in rest`` compares nothing with a path: a literal on the left of ``in`` is not a route."""
    ours, theirs = both('def f(path, rest):\n    return "/" not in rest and path == "/v1/read/waiting"\n')
    assert ours == theirs and ours.exact == ["/v1/read/waiting"]


def test_the_routes_are_tied_to_the_matrix_by_exact_literal_prefix_and_pattern():
    result = S.tie(TEMPLATES, both(SERVER)[0])
    assert result.served == {"/v1/read/waiting", "/v1/read/runs/{execution_id}", "/o01/v0/command-sets",
                             "/v1/read/continuation-state/{work_id}",
                             "/o01/v0/owner-operations/{owner}/{operation_ref}"}
    assert "/v1/read/work/{work_kind}/{work_id}" not in result.served  # the matrix route nothing serves
    # a prefix that selects a handler serves no route
    assert result.family >= {"/v1/read/", "/o01/v0/owner-operations/"}
    assert result.unresolved == []
    assert result.test_only == {"/_test/engine-outage": "POST", "/_test/read-entitlement": "POST"}


@pytest.mark.parametrize(("extra", "fragment"), [
    ("\n\ndef extra(path):\n    return path == '/v1/read/nowhere'\n", "'/v1/read/nowhere', which is no route"),
    ("\n\ndef extra(path):\n    return path.startswith('/zzz/')\n", "'/zzz/', which starts no route"),
    ("\n\ndef extra(path):\n    return re.compile(r'/v1/read/(.*)').fullmatch(path)\n", None),
])
def test_a_route_shaped_string_the_matrix_does_not_explain_is_unresolved_not_dropped(extra, fragment):
    values = {**VALUES, "BAD": re.compile(r"/v1/read/other/([^/]*)")}
    source = SERVER + extra.replace("re.compile(r'/v1/read/(.*)')", "BAD")
    ours, theirs = S.read(ast.parse(source), values), ST.read(source, values)
    assert ours == theirs
    unresolved = S.tie(TEMPLATES, ours).unresolved
    if fragment:
        assert any(fragment in u for u in unresolved), unresolved
    else:
        assert any("matches a path with the pattern" in u for u in unresolved), unresolved


def test_a_source_that_compares_nothing_serves_nothing():
    ours, theirs = both("def handle(s):\n    return 1\n")
    assert ours == theirs and S.tie(TEMPLATES, ours).served == set()


def test_a_route_that_is_in_a_variable_is_in_neither_reading():
    """Pinned: a path held in a local variable and compared there is not seen (one probe per item of the 'cannot
    see')."""
    for source in ("def f(path):\n    r = '/v1/read/waiting'\n    return path == r\n",
                   "def f(path):\n    return {'/v1/read/waiting': 1}[path]\n"):
        ours, theirs = both(source)
        assert ours == theirs and ours.exact == []


def test_the_text_reading_sees_the_front_of_a_concatenated_route_and_the_ast_reading_does_not():
    """They differ on purpose: text cannot tell a literal from the front of an expression, so it reports the fragment
    (which the matrix then explains or does not); the AST reading is the source."""
    ours, theirs = both("def f(path):\n    return path == '/v1/read/' + 'waiting'\n")
    assert ours.exact == [] and theirs.exact == ["/v1/read/"]


def test_a_placeholder_is_written_as_the_server_writes_it_in_a_pattern():
    written = S.as_pattern("/o01/v0/owner-operations/{owner}/{operation_ref}")
    assert written == "/o01/v0/owner-operations/([^/]*)/([^/]*)"
    assert S.as_pattern("/v1/read/waiting") == "/v1/read/waiting"


def test_the_matrix_routes_are_distinct_method_route_pairs_and_one_route_has_one_api():
    rows = [{"method": "get", "route": "/a", "api": "D01"}, {"method": "get", "route": "/a", "api": "D01"},
            {"method": "post", "route": "/b", "api": "O01"}]
    assert S.matrix_routes(rows) == {("GET", "/a"): "D01", ("POST", "/b"): "O01"}
    with pytest.raises(C.ReferenceError, match="two APIs"):
        S.matrix_routes([*rows, {"method": "get", "route": "/a", "api": "O01"}])


# ------------------------------------------------------------------------------------------------- the command path

COMMANDS = '''
SLICE_OWNER_REASONS = {}


def refusal(action, cause, *, allocated=False):
    reason = TABLE[action][cause]
    if reason == "SOURCE_UNAVAILABLE":
        return {"outcome": "HELD", "reason_code": reason, "owner_reason": cause}
    return {"outcome": "REFUSED", "reason_code": reason, "owner_reason": cause}


class Carrier:
    def _member(self, req, i, t, now):
        action = i["action"]
        r = REGISTRY[action]
        if r["origin"] != "CURRENT_DELEGATED_GRANT":
            return refusal(action, "ORIGIN_NOT_ESTABLISHED")
        e = self._delegation(req, i, now)
        if e:
            return refusal(action, e)
        if action != "CONTINUE_ELIGIBLE_WORK":
            return refusal(action, "NOT_MODELLED")
        return self._heb_continue(i, t)

    def _delegation(self, req, i, now):
        if i is None:
            return "DELEGATED_GRANT_UNVERIFIED"
        if now is None:
            return "DELEGATION_EXPIRED"
        return None

    def _heb_continue(self, i, t):
        if i is None:
            return refusal(i["action"], "HEB_STATE_UNKNOWN")
        return {"outcome": "EFFECT_CONFIRMED", "reason_code": None, "owner_reason": None}

    def _result(self, i, m):
        return {"reason_code": m["reason_code"]}
'''


def both_commands(source: str):
    return K.read(ast.parse(source)), KT.read(source)


def test_both_readings_find_the_origin_the_action_the_causes_and_the_builders():
    ours, theirs = both_commands(COMMANDS)
    assert ours == theirs
    assert (ours.origin, ours.action) == ("CURRENT_DELEGATED_GRANT", "CONTINUE_ELIGIBLE_WORK")
    assert ours.delegation == ["DELEGATED_GRANT_UNVERIFIED", "DELEGATION_EXPIRED"]
    assert ours.causes == ["DELEGATED_GRANT_UNVERIFIED", "DELEGATION_EXPIRED", "HEB_STATE_UNKNOWN", "NOT_MODELLED",
                           "ORIGIN_NOT_ESTABLISHED"]
    assert ours.unreadable == []
    assert set(ours.builders) == {("refusal", "name"), ("Carrier._heb_continue", "none"),
                                  ("Carrier._result", "subscript")}


def test_a_refusal_whose_cause_cannot_be_read_is_reported_not_dropped():
    source = COMMANDS + "\n\ndef elsewhere(action, x):\n    return refusal(action, x.cause())\n"
    ours, theirs = both_commands(source)
    assert ours == theirs and ours.unreadable == ["elsewhere"]


def test_a_second_builder_of_a_reason_code_is_a_builder_the_declared_set_does_not_have():
    source = COMMANDS + "\n\ndef sneak(reason):\n    return {'outcome': 'REFUSED', 'reason_code': reason}\n"
    ours, theirs = both_commands(source)
    assert ours == theirs
    assert set(ours.builders) - K.BUILDERS == {("sneak", "name")}
    other = COMMANDS + "\n\ndef sneak():\n    return {'reason_code': 'MADE_UP'}\n"
    assert set(both_commands(other)[0].builders) - K.BUILDERS == {("sneak", "other")}


def test_a_source_without_the_member_function_has_no_origin_and_no_action():
    ours, theirs = both_commands("def refusal(action, cause):\n    return {'reason_code': cause}\n")
    assert ours == theirs and (ours.origin, ours.action) == (None, None)


def test_a_cause_in_the_code_that_no_table_names_is_unresolved_on_every_refusal_record(monkeypatch):
    real = K.read(ast.parse(COMMANDS))
    monkeypatch.setattr(K, "read", lambda tree: real._replace(causes=[*real.causes, "MADE_UP_CAUSE"]))
    records = [r for r in K.build(C.Context(ROOT)) if r.family == K.REFUSALS]
    assert records and all(r.coverage["label"] == "lower-bound" for r in records)
    assert any("MADE_UP_CAUSE" in i["why"] for i in records[0].coverage["unresolved"])


def test_an_action_with_causes_that_the_registry_lacks_is_named_and_one_the_refusal_map_lacks_too(monkeypatch):
    from aew.stg02 import commands as module

    monkeypatch.setattr(module, "SLICE_OWNER_REASONS", {**module.SLICE_OWNER_REASONS, "UNLISTED_ACTION": {"X": "Y"}})
    records = [r for r in K.build(C.Context(ROOT)) if r.family == K.REFUSALS]
    why = " ".join(i["why"] for i in records[0].coverage["unresolved"])
    assert "UNLISTED_ACTION has refusal causes and is no action of the registry" in why
    monkeypatch.undo()
    from aew.stg02 import adopted

    real = adopted.refusals()
    monkeypatch.setattr(adopted, "refusals", lambda: {k: v for k, v in real.items() if k != "SUSPEND_GRANT"})
    records = [r for r in K.build(C.Context(ROOT)) if r.family == K.REFUSALS]
    assert any("SUSPEND_GRANT is an action of the registry and has no entry" in i["why"]
               for i in records[0].coverage["unresolved"])


def test_a_cause_both_tables_name_is_one_record_and_the_vendored_one(monkeypatch):
    from aew.stg02 import adopted
    from aew.stg02 import commands as module

    both_name = {"CONTINUE_ELIGIBLE_WORK": {"NOT_MODELLED": "SOURCE_UNAVAILABLE"}}
    monkeypatch.setattr(module, "SLICE_OWNER_REASONS", both_name)
    found = [r for r in K.build(C.Context(ROOT)) if r.id == "command-refusals:CONTINUE_ELIGIBLE_WORK:NOT_MODELLED"]
    assert len(found) == 1 and found[0].fact is not None and found[0].fact["source"] == "vendored"
    assert adopted.refusals()["CONTINUE_ELIGIBLE_WORK"]["NOT_MODELLED"] == "SOURCE_UNAVAILABLE"


def test_reaches_owner_is_null_with_an_unresolved_item_when_the_member_shape_is_not_found(monkeypatch):
    monkeypatch.setattr(K, "read", lambda tree: K.Reading(None, None, [], [], [], sorted(K.BUILDERS)))
    commands = [r for r in K.build(C.Context(ROOT)) if r.family == K.COMMANDS]
    assert commands and all((r.fact or {})["reaches_owner"] is None for r in commands)
    assert all(r.coverage["label"] == "lower-bound" and r.coverage["unresolved"] for r in commands)
