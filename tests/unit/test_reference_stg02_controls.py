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
    # the front of a matrix route compared exactly is no family prefix (those are given to startswith)
    ("\n\ndef extra(path):\n    return path == '/v1/read'\n", "'/v1/read', which is no route"),
    ("\n\ndef extra(path):\n    return path == '/v1/read/runs/'\n", "'/v1/read/runs/', which is no route"),
    # a test route needs the method test the server uses beside it
    ("\n\ndef extra(path):\n    return path == '/_test/zzz'\n", "'/_test/zzz', a test route without the method test"),
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


@pytest.mark.parametrize(("name", "extra"), [
    ("a match statement", "\n\ndef f(path):\n    match path:\n        case '/v1/read/work/x':\n            return 1\n"),
    ("a regex written inline at the call site",
     "\n\ndef f(path):\n    return re.fullmatch(r'/v1/read/work/([^/]*)/([^/]*)', path)\n"),
    ("a module-level collection compared by name",
     "\n\nOTHER = ('/v1/read/work/x',)\n\n\ndef f(path):\n    return path in OTHER\n"),
    ("a literal handed to a helper that compares it",
     "\n\ndef same(path, route):\n    return path == route\n\n\n"
     "def f(path):\n    return same(path, '/v1/read/work/x')\n"),
    ("a segment comparison", "\n\ndef f(path):\n    return path.split('/')[-1] == 'waiting'\n"),
    ("endswith", "\n\ndef f(path):\n    return path.endswith('/waiting')\n"),
    ("removeprefix", "\n\ndef f(path):\n    return path.removeprefix('/v1/read/') == 'work'\n"),
])
def test_what_neither_server_reading_sees_is_pinned_one_probe_each(name, extra):
    """The list of the module's docstring and of the page: each shape is in neither reading, so the served set (a lower
    bound) does not move; the observed request test is what would show it."""
    ours, theirs = both(SERVER + extra)
    assert ours == theirs == both(SERVER)[0], name


def test_served_is_read_per_route_and_not_per_method(monkeypatch):
    """A route with two methods in the matrix shows both as served, or neither: the matrix has one method for each
    route today, and the reading ties a route, not a (method, route)."""
    from aew.stg02 import adopted

    rows = adopted.matrix()
    waiting = next(r for r in rows if r["route"] == "/v1/read/waiting")
    monkeypatch.setattr(adopted, "matrix", lambda: [*rows, {**waiting, "method": "post"}])
    served = {r.key: (r.fact or {})["served"] for r in S.build(C.Context(ROOT))}
    assert served["GET /v1/read/waiting"] is True and served["POST /v1/read/waiting"] is True


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
    assert set(ours.builders) == {("refusal", "literal", "name"), ("Carrier._heb_continue", "literal", "none"),
                                  ("Carrier._result", "literal", "subscript")}


def test_a_refusal_whose_cause_cannot_be_read_is_reported_not_dropped():
    source = COMMANDS + "\n\ndef elsewhere(action, x):\n    return refusal(action, x.cause())\n"
    ours, theirs = both_commands(source)
    assert ours == theirs and ours.unreadable == ["elsewhere"]


@pytest.mark.parametrize("extra", [
    "def elsewhere(action):\n    return refusal(action, cause='MADE_UP')\n",
    "def elsewhere(action):\n    return refusal(action)\n",
])
def test_a_refusal_with_its_cause_as_a_keyword_or_missing_is_reported_not_skipped(extra):
    ours, theirs = both_commands(COMMANDS + "\n\n" + extra)
    assert ours == theirs and ours.unreadable == ["elsewhere"], extra


def test_a_cause_from_a_helper_that_returns_something_but_a_constant_is_reported_not_dropped():
    """The right case is the helper that returns string constants and None (``_delegation``); the wrong one also
    returns a variable, so the causes read from it would be incomplete."""
    assert both_commands(COMMANDS)[0].unreadable == []
    tail = "\n\n    def _heb_continue"
    source = COMMANDS.replace("        return None" + tail, "        return req" + tail)
    assert source != COMMANDS
    ours, theirs = both_commands(source)
    assert ours == theirs and ours.unreadable == ["_member"]
    assert ours.delegation == ["DELEGATED_GRANT_UNVERIFIED", "DELEGATION_EXPIRED"]  # the constants are still read


def test_a_second_different_origin_or_action_test_makes_the_shape_not_found_not_the_last_one():
    """Two different literals make the one the reading takes ambiguous; the same literal twice does not."""
    again = COMMANDS.replace('        r = REGISTRY[action]\n', '        r = REGISTRY[action]\n'
                             '        if r["origin"] != "CURRENT_DELEGATED_GRANT":\n            pass\n')
    ours, theirs = both_commands(again)
    assert ours == theirs and (ours.origin, ours.action) == ("CURRENT_DELEGATED_GRANT", "CONTINUE_ELIGIBLE_WORK")
    other_origin = COMMANDS.replace('        r = REGISTRY[action]\n', '        r = REGISTRY[action]\n'
                                    '        if r["origin"] != "ANOTHER_ORIGIN":\n            pass\n')
    ours, theirs = both_commands(other_origin)
    assert ours == theirs and (ours.origin, ours.action) == (None, "CONTINUE_ELIGIBLE_WORK")
    other_action = COMMANDS.replace('        r = REGISTRY[action]\n', '        r = REGISTRY[action]\n'
                                    '        if action != "ANOTHER_ACTION":\n            pass\n')
    ours, theirs = both_commands(other_action)
    assert ours == theirs and (ours.origin, ours.action) == ("CURRENT_DELEGATED_GRANT", None)


def test_a_second_builder_of_a_reason_code_is_a_builder_the_declared_set_does_not_have():
    source = COMMANDS + "\n\ndef sneak(reason):\n    return {'outcome': 'REFUSED', 'reason_code': reason}\n"
    ours, theirs = both_commands(source)
    assert ours == theirs
    assert set(ours.builders) - K.BUILDERS == {("sneak", "literal", "name")}
    other = COMMANDS + "\n\ndef sneak():\n    return {'reason_code': 'MADE_UP'}\n"
    assert set(both_commands(other)[0].builders) - K.BUILDERS == {("sneak", "literal", "other")}


@pytest.mark.parametrize(("name", "extra", "builder"), [
    ("a subscript store", "\n\ndef sneak(m, code):\n    m['reason_code'] = code\n    return m\n",
     ("sneak", "store", "name")),
    ("a store of a literal", "\n\ndef sneak(m):\n    m['reason_code'] = 'MADE_UP'\n", ("sneak", "store", "other")),
    ("an update with the keyword", "\n\ndef sneak(m, code):\n    m.update(reason_code=code)\n    return m\n",
     ("sneak", "keyword", "name")),
    ("a dict made with the keyword", "\n\ndef sneak(reason):\n    return dict(outcome='REFUSED', reason_code=reason)\n",
     ("sneak", "keyword", "name")),
    ("a constructor with the keyword", "\n\ndef sneak(reason):\n    return Result(reason_code=reason)\n",
     ("sneak", "keyword", "name")),
])
def test_a_reason_code_made_by_a_store_or_a_keyword_is_a_builder_the_declared_set_does_not_have(name, extra, builder):
    """The wrong cases of the builder rule beside the dict literal: each of the other two spellings of making a
    ``reason_code`` is found by both readings, and is not one of the declared places."""
    ours, theirs = both_commands(COMMANDS + extra)
    assert ours == theirs, name
    assert set(ours.builders) - K.BUILDERS == {builder}, name


@pytest.mark.parametrize("extra", [
    "\n\ndef reads(m):\n    return m['reason_code']\n",
    "\n\ndef compares(m):\n    return m['reason_code'] == 'X' and m['reason_code'] != 'Y'\n",
    "\n\ndef shaped(reason_code=None):\n    return reason_code\n",
])
def test_a_use_of_a_reason_code_that_makes_none_is_not_a_builder(extra):
    """The missing cases: a read, a comparison and a parameter of that name make no result."""
    ours, theirs = both_commands(COMMANDS + extra)
    assert ours == theirs and set(ours.builders) == set(both_commands(COMMANDS)[0].builders)


@pytest.mark.parametrize("extra", [
    "\n\ndef sneak(m, key, code):\n    m[key] = code\n",
    "\n\ndef sneak(m, code):\n    setattr(m, 'reason_code', code)\n",
    "\n\ndef sneak(base):\n    return {**base}\n",
])
def test_what_the_builder_readings_do_not_see_is_pinned_one_probe_each(extra):
    """A computed key, ``setattr`` and a ``**`` of a dict built elsewhere are not seen (the module says so)."""
    ours, theirs = both_commands(COMMANDS + extra)
    assert ours == theirs and set(ours.builders) == set(both_commands(COMMANDS)[0].builders)


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
    monkeypatch.setattr(K, "read", lambda tree: K.Reading(None, None, [], [], [], sorted(K.BUILDERS), [], []))
    commands = [r for r in K.build(C.Context(ROOT)) if r.family == K.COMMANDS]
    assert commands and all((r.fact or {})["reaches_owner"] is None for r in commands)
    assert all(r.coverage["label"] == "lower-bound" and r.coverage["unresolved"] for r in commands)


# ---------------------------------------------------------------------------------------------- who returns a pair

REGISTRY = {"PROTECTED": {"origin": "PROTECTED_G3"}, "DELEGATED": {"origin": "CURRENT_DELEGATED_GRANT"},
            "CONTINUE_ELIGIBLE_WORK": {"origin": "CURRENT_DELEGATED_GRANT"}}
NAMED = {("PROTECTED", "ORIGIN_NOT_ESTABLISHED"), ("PROTECTED", "NEVER_RETURNED"),
         ("DELEGATED", "DELEGATED_GRANT_UNVERIFIED"), ("DELEGATED", "DELEGATION_EXPIRED"),
         ("DELEGATED", "NOT_MODELLED"), ("CONTINUE_ELIGIBLE_WORK", "DELEGATED_GRANT_UNVERIFIED"),
         ("CONTINUE_ELIGIBLE_WORK", "DELEGATION_EXPIRED"), ("CONTINUE_ELIGIBLE_WORK", "HEB_STATE_UNKNOWN")}
MEMBER, HEB = "Carrier._member", "Carrier._heb_continue"


def test_both_readings_find_the_steps_of_the_member_and_every_refusal_call():
    ours, theirs = both_commands(COMMANDS)
    assert ours == theirs
    assert ours.steps == [(MEMBER, "origin-test", "CURRENT_DELEGATED_GRANT", "ORIGIN_NOT_ESTABLISHED"),
                          (MEMBER, "state-test", "", "$_delegation"),
                          (MEMBER, "action-test", "CONTINUE_ELIGIBLE_WORK", "NOT_MODELLED"),
                          (MEMBER, "hand-on", "_heb_continue", "")]
    assert ours.calls == [(HEB, "i['action']", "HEB_STATE_UNKNOWN"), (MEMBER, "action", "$_delegation"),
                          (MEMBER, "action", "NOT_MODELLED"), (MEMBER, "action", "ORIGIN_NOT_ESTABLISHED")]


def test_the_steps_are_replayed_over_the_actions_each_step_taking_what_it_refuses():
    """The right case: each pair is returned by the site whose action and cause are both possible there, and a cause in
    a table that no step returns (``NEVER_RETURNED``) is in no pair."""
    pairs, problems = K.emitted(both_commands(COMMANDS)[0], REGISTRY, NAMED)
    assert problems == []
    assert pairs == {
        ("PROTECTED", "ORIGIN_NOT_ESTABLISHED"): [MEMBER],
        ("DELEGATED", "DELEGATED_GRANT_UNVERIFIED"): [MEMBER], ("DELEGATED", "DELEGATION_EXPIRED"): [MEMBER],
        ("DELEGATED", "NOT_MODELLED"): [MEMBER],
        ("CONTINUE_ELIGIBLE_WORK", "DELEGATED_GRANT_UNVERIFIED"): [MEMBER],
        ("CONTINUE_ELIGIBLE_WORK", "DELEGATION_EXPIRED"): [MEMBER],
        ("CONTINUE_ELIGIBLE_WORK", "HEB_STATE_UNKNOWN"): [HEB]}
    assert ("PROTECTED", "NEVER_RETURNED") not in pairs  # in a table, returned by no path: an empty list on its record


def test_the_replay_follows_the_order_of_the_steps_not_a_fixed_order():
    """Taking the action test before the delegation test leaves the delegation test only the action that goes on."""
    swapped = COMMANDS.replace(
        '        e = self._delegation(req, i, now)\n        if e:\n            return refusal(action, e)\n'
        '        if action != "CONTINUE_ELIGIBLE_WORK":\n            return refusal(action, "NOT_MODELLED")\n',
        '        if action != "CONTINUE_ELIGIBLE_WORK":\n            return refusal(action, "NOT_MODELLED")\n'
        '        e = self._delegation(req, i, now)\n        if e:\n            return refusal(action, e)\n')
    assert swapped != COMMANDS
    ours, theirs = both_commands(swapped)
    assert ours == theirs
    pairs, problems = K.emitted(ours, REGISTRY, NAMED)
    assert problems == [] and ("DELEGATED", "DELEGATION_EXPIRED") not in pairs
    assert pairs[("CONTINUE_ELIGIBLE_WORK", "DELEGATION_EXPIRED")] == [MEMBER]


@pytest.mark.parametrize(("name", "extra", "fragment"), [
    ("a refusal in a function the steps do not place",
     "\n\ndef sneak(action):\n    return refusal(action, 'NOT_MODELLED')\n",
     "sneak returns a refusal on a path this reading cannot place"),
    ("a refusal with a cause held in a variable of no method",
     "\n\nclass Other:\n    def go(self, action, c):\n        return refusal(action, c)\n",
     "Other.go returns a refusal on a path this reading cannot place"),
])
def test_a_refusal_call_no_step_places_is_named_not_dropped(name, extra, fragment):
    ours, theirs = both_commands(COMMANDS + extra)
    assert ours == theirs, name
    _, problems = K.emitted(ours, REGISTRY, NAMED)
    assert any(fragment in p for p in problems), (name, problems)


def test_a_pair_the_code_can_return_and_no_table_names_is_named_and_a_lost_shape_is_not_replayed():
    ours = both_commands(COMMANDS)[0]
    _, problems = K.emitted(ours, REGISTRY, NAMED - {("DELEGATED", "NOT_MODELLED")})
    assert any("can return NOT_MODELLED for DELEGATED, which no table names" in p for p in problems)
    pairs, problems = K.emitted(ours._replace(origin=None), REGISTRY, NAMED)
    assert pairs == {} and "steps of Carrier._member are not where this reading looks" in problems[0]


def test_a_cause_in_a_table_that_no_code_path_returns_has_an_empty_list_on_its_record(monkeypatch):
    from aew.stg02 import commands as module

    owner = module.SLICE_OWNER_REASONS
    monkeypatch.setattr(module, "SLICE_OWNER_REASONS", {
        **owner, "CONTINUE_ELIGIBLE_WORK": {**owner["CONTINUE_ELIGIBLE_WORK"], "NEVER_RETURNED": "SOURCE_UNAVAILABLE"}})
    records = {r.key: r for r in K.build(C.Context(ROOT)) if r.family == K.REFUSALS}
    never = records["CONTINUE_ELIGIBLE_WORK:NEVER_RETURNED"]
    assert never.fact is not None and never.fact["emitted_by"] == []  # the planted case
    assert never.fact_coverage is not None and never.fact_coverage["emitted_by"]["label"] == "complete-by-construction"
    # and in the real tables: NOT_MODELLED is a cause of seven actions and the slice returns it for one
    member = [{"module": K.COMMAND_MODULE, "symbol": MEMBER}]
    assert (records["CLOSE_ATTACHMENT:NOT_MODELLED"].fact or {})["emitted_by"] == []
    assert (records["DELEGATED_CANCEL:NOT_MODELLED"].fact or {})["emitted_by"] == member
    assert (records["CONTINUE_ELIGIBLE_WORK:HEB_STATE_UNKNOWN"].fact or {})["emitted_by"] == [
        {"module": K.COMMAND_MODULE, "symbol": HEB}]


def test_a_refusal_call_the_reading_cannot_place_makes_emitted_by_lower_bound_on_every_record(monkeypatch):
    src = C.Context(ROOT).sources()[K.COMMAND_MODULE]
    assert src.tree is not None
    real = K.read(src.tree)
    monkeypatch.setattr(K, "read", lambda tree: real._replace(calls=[*real.calls, ("sneak", "action", "NOT_MODELLED")]))
    records = [r for r in K.build(C.Context(ROOT)) if r.family == K.REFUSALS]
    assert records and all(r.fact_coverage is not None for r in records)
    for r in records:
        assert r.fact_coverage is not None and r.fact_coverage["emitted_by"]["label"] == "lower-bound"
        assert any("sneak returns a refusal on a path this reading cannot place" in i["why"]
                   for i in r.fact_coverage["emitted_by"]["unresolved"])
        assert r.coverage["label"] == "complete-by-construction"  # the record itself is unchanged
