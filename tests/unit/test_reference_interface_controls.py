"""The planted controls of the interface families of the generated reference (STG-12 S12-2, family 6): the dashboard
server's routes, the schema flattener, the SQLite reader and the CLI anchors
(``tools/reference_families/interfaces*.py``).

Every rule has its planted right case, wrong case and missing case, so a rule that stopped working would fail. That the
records equal the registries they are read from, and the two detectors of each recogniser agree on the tree, is in
``tests/integration/test_reference_interfaces.py`` and ``tests/integration/test_reference_dashboard_routes.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import (
            common,
            interfaces,
            interfaces_cli,
            interfaces_dashboard,
            interfaces_dashboard_text,
            interfaces_schemas,
            interfaces_sqlite,
            interfaces_sqlite_text,
        )
    finally:
        sys.path.remove(here)
    return (common, interfaces, interfaces_cli, interfaces_dashboard, interfaces_dashboard_text, interfaces_schemas,
            interfaces_sqlite, interfaces_sqlite_text)


C, IFACE, CLI, DASH, DASH_TEXT, SCHEMAS, SQL, SQL_TEXT = _tools()

# ------------------------------------------------------------------------------------------ the dashboard server

SERVER = '''
SESSION_PREFIX = "/session/"
ROUTES = {"/a": 1}
CONDITIONAL_HANDLERS = {}


def pending_routes(paths):
    return set(paths) - set(ROUTES)


class DashboardServer:
    def __init__(self):
        class Handler:
            def do_GET(self):
                pass

            def do_HEAD(self):
                pass

    def _handle(self, h, *, head):
        try:
            url = urlsplit(h.path)
            self._admit(h, url)
            if url.path.startswith(SESSION_PREFIX):
                if self.sessions is None:
                    raise Refusal()
                self._exchange(h, url.path, head=head)
                return
            if not url.path.startswith("/api/"):
                self._static(h, url.path, head=head)
                return
            status, body, tag = self._respond(h, url)
        except Exception:
            pass

    def _respond(self, h, url):
        return (ROUTES.get(url) or CONDITIONAL_HANDLERS[url])(1, 2, 3)
'''
CONSTANTS = {"SESSION_PREFIX": "/session/"}


def both(source: str, constants: dict[str, str] | None = None):
    given = CONSTANTS if constants is None else constants
    return DASH.read(ast.parse(source), given), DASH_TEXT.read(source, given)


def test_both_readings_find_the_branches_the_fall_through_the_methods_and_the_references():
    ours, theirs = both(SERVER)
    assert ours == theirs
    assert ours.branches == [DASH.Branch("/session/", False, "_exchange", "sessions"),
                             DASH.Branch("/api/", True, "_static", None)]
    assert ours.fallthrough == "_respond" and ours.methods == ["GET", "HEAD"]
    assert ours.references == [("CONDITIONAL_HANDLERS", "DashboardServer._respond"),
                               ("ROUTES", "DashboardServer._respond"), ("ROUTES", "pending_routes")]


def test_a_branch_testing_a_prefix_the_reading_cannot_resolve_is_reported_not_dropped():
    ours, theirs = both(SERVER, constants={})  # SESSION_PREFIX is unknown
    assert ours == theirs
    assert ours.branches[0] == DASH.Branch(None, False, "_exchange", "sessions")


def test_a_function_that_names_a_route_table_is_a_reference_in_both_readings():
    ours, theirs = both(SERVER + "\n\ndef other(route):\n    return ROUTES[route]\n")
    assert ours == theirs
    assert ("ROUTES", "other") in ours.references


def test_an_alias_of_a_table_is_reported_at_the_place_it_is_made():
    ours, theirs = both(SERVER + "\n\nHANDLERS = ROUTES\n")
    assert ours == theirs and ("ROUTES", "HANDLERS") in ours.references


@pytest.mark.parametrize("extra", [
    "\n\ndef other(route):\n    return getattr(sys.modules[__name__], 'ROU' + 'TES')[route]\n",
    "\n\ndef other(route, name):\n    return vars(sys.modules[__name__])[name][route]\n",
])
def test_what_both_readings_miss_of_the_tables_is_pinned_one_probe_each(extra):
    ours, theirs = both(SERVER + extra)
    base, _ = both(SERVER)
    assert ours.references == theirs.references == base.references


def test_the_text_reading_counts_a_table_named_in_a_string_and_the_ast_reading_does_not():
    """They differ on purpose: the text reading cannot tell a name from its mention, so it reports a mention (a false
    alarm that asks for a look, never a miss); the AST reading is the source."""
    ours, theirs = both(SERVER + "\n\ndef other(route):\n    return globals()['ROUTES'][route]\n")
    assert ("ROUTES", "other") in theirs.references and ("ROUTES", "other") not in ours.references


def test_a_source_without_the_handler_has_no_branches_and_no_fall_through():
    ours, theirs = both("ROUTES = {}\n\n\nclass DashboardServer:\n    pass\n")
    assert ours == theirs and ours.branches == [] and ours.fallthrough is None


def test_a_definition_at_the_start_of_a_line_is_not_a_use_but_a_use_in_a_function_is():
    ours, theirs = both("ROUTES = {}\nCONDITIONAL_HANDLERS = {}\n\n\ndef f():\n    return CONDITIONAL_HANDLERS\n")
    assert ours == theirs and ours.references == [("CONDITIONAL_HANDLERS", "f")]


def test_a_branch_records_the_attribute_of_the_server_it_is_answered_only_while_set():
    ours, theirs = both(SERVER)
    assert ours == theirs and [b.needs for b in ours.branches] == ["sessions", None]
    # the need may be in the handler the branch calls rather than in the branch
    moved = SERVER.replace("                if self.sessions is None:\n                    raise Refusal()\n", "") \
        + "\n\nclass Other:\n    pass\n"
    moved = moved.replace("    def _respond(self, h, url):",
                          "    def _exchange(self, h, path, *, head):\n        if self.sessions is None:\n"
                          "            raise Refusal()\n\n    def _respond(self, h, url):")
    ours, theirs = both(moved)
    assert ours == theirs and ours.branches[0].needs == "sessions"
    gone = SERVER.replace("                if self.sessions is None:\n                    raise Refusal()\n", "")
    ours, theirs = both(gone)
    assert ours == theirs and ours.branches[0].needs is None  # missing: no guard, no need


# --- the reads of the request path

RESPOND = "    def _respond(self, h, url):\n"


def reads_of(source: str):
    ours, theirs = both(source)
    assert ours == theirs, (ours.path_reads, theirs.path_reads)  # the two readings agree on every planted case
    return ours


def declared_of(source: str = SERVER):
    return tuple(reads_of(source).path_reads)


def test_the_reads_of_the_request_path_are_classified_by_form_and_consumer_in_both_readings():
    assert declared_of() == (
        ("DashboardServer._handle", "h.path", "bare", "call:urlsplit"),
        ("DashboardServer._handle", "url.path", "bare", "call:self._exchange"),
        ("DashboardServer._handle", "url.path", "bare", "call:self._static"),
        ("DashboardServer._handle", "url.path", "startswith", "'/api/'"),
        ("DashboardServer._handle", "url.path", "startswith", "SESSION_PREFIX"))
    assert DASH.path_read_problems(reads_of(SERVER), declared_of()) == []  # right: the declared reads are the reads


@pytest.mark.parametrize(("name", "old", "new", "read"), [
    ("an equality branch in the handler", "            status, body, tag = self._respond(h, url)\n",
     "            if url.path == '/health':\n                self._health(h)\n                return\n"
     "            status, body, tag = self._respond(h, url)\n",
     ("DashboardServer._handle", "url.path", "bare", "compare:Eq:'/health'")),
    ("an early return in the dispatch", RESPOND, RESPOND + "        if url.path == '/x':\n            return 1\n",
     ("DashboardServer._respond", "url.path", "bare", "compare:Eq:'/x'")),
    ("a branch on the raw target", "            self._admit(h, url)\n",
     "            self._admit(h, url)\n            if h.path == '/raw':\n                self._raw(h)\n"
     "                return\n",
     ("DashboardServer._handle", "h.path", "bare", "compare:Eq:'/raw'")),
    ("a third table consulted in the dispatch", RESPOND,
     RESPOND + "        if url.path in EXTRA:\n            return EXTRA[url.path](1, 2, 3)\n",
     ("DashboardServer._respond", "url.path", "bare", "compare:In:EXTRA")),
    ("a lookup keyed by the path", RESPOND, RESPOND + "        return EXTRA[url.path]\n",
     ("DashboardServer._respond", "url.path", "any", "other")),
])
def test_a_route_served_around_the_dispatch_is_a_read_of_the_request_path_nobody_declared(name, old, new, read):
    declared = declared_of()
    planted = reads_of(SERVER.replace(old, new, 1))
    assert read in planted.path_reads, name
    problems = DASH.path_read_problems(planted, declared)
    assert problems and any(read[3] in p for p in problems), (name, problems)


def test_a_declared_read_the_source_no_longer_has_is_named():
    declared = declared_of()
    branch = "            if url.path.startswith(SESSION_PREFIX):"
    gone = reads_of(SERVER.replace(branch, "            if self.flag:", 1))
    [problem] = DASH.path_read_problems(gone, declared)
    assert "declared to read the request path" in problem and "SESSION_PREFIX" in problem and "reads it 0" in problem


def test_two_reads_of_a_kind_are_counted_not_merged():
    declared = declared_of()
    admit = "            self._admit(h, url)\n"
    twice = reads_of(SERVER.replace(RESPOND, RESPOND + "        a = h.path\n", 1).replace(
        admit, admit + "            b = h.path\n            c = h.path\n", 1))
    problems = DASH.path_read_problems(twice, declared)
    assert any("2 time(s); 0 are declared" in p and "assign" in p for p in problems)
    # a read the declaration has once, read twice: a presence test would pass it, a count does not
    static = "            if not url.path.startswith(\"/api/\"):\n"
    doubled = reads_of(SERVER.replace(static, "            self._static(h, url.path, head=head)\n" + static, 1))
    [problem] = DASH.path_read_problems(doubled, declared)
    assert "(url.path, bare, call:self._static) 2 time(s); 1 are declared" in problem


ADMIT = "            self._admit(h, url)\n"
DO_GET = "            def do_GET(self):\n                pass\n"
IN_TRY = " " * 12  # the indentation of a statement in the handler's try block


def plant(*pairs: tuple[str, str]) -> str:
    source = SERVER
    for old, new in pairs:
        assert source.count(old) == 1, old
        source = source.replace(old, new, 1)
    return source


def sneaky(test: str, before: str = "") -> str:
    """A branch on ``test`` in the request handler, right after the admission (``before``: a line it needs)."""
    return ADMIT + before + f"{IN_TRY}if {test}:\n{IN_TRY}    return\n"


def method(name: str, arguments: str, test: str) -> str:
    """A method of the server that tests ``test``, placed before ``_respond``."""
    return f"    def {name}({arguments}):\n        if {test}:\n            return\n\n" + RESPOND


# Every shape of a route served around the dispatch that the reading does not see, by what it is: a test inside a
# function the two checked methods call (a new one included), the path read under another spelling, a branch before
# the handler is reached, and a read replaced by another of the same form and consumer.
NOT_SEEN = {
    "a test in a function the two call": plant((RESPOND, method("_admit", "self, h, url", "url.path == '/sneaky'"))),
    "a test in a new method that the handler calls": plant(
        (ADMIT, ADMIT + f"{IN_TRY}self._preflight(url)\n"),
        (RESPOND, method("_preflight", "self, url", "url.path == '/sneaky'"))),
    "a test in a method that is not checked": plant((RESPOND, method("_other", "self, h, url", "url.path == '/z'"))),
    "raw_target(h)": plant((ADMIT, sneaky("raw_target(h) == '/sneaky'"))),
    "h.requestline": plant((ADMIT, sneaky("h.requestline.startswith('GET /sneaky')"))),
    "url[2]": plant((ADMIT, sneaky("url[2] == '/sneaky'"))),
    "url.geturl()": plant((ADMIT, sneaky("url.geturl() == '/sneaky'"))),
    "an alias of the parsed url": plant((ADMIT, sneaky("u.path == '/sneaky'", f"{IN_TRY}u = url\n"))),
    "an unpacking of the parsed url": plant(
        (ADMIT, sneaky("route == '/sneaky'", f"{IN_TRY}scheme, netloc, route, *rest = url\n"))),
    "getattr(url, 'path')": plant((ADMIT, sneaky("getattr(url, 'path') == '/sneaky'"))),
    "a branch in the nested handler's do_GET": plant(
        (DO_GET, "            def do_GET(self):\n                if self.path == '/sneaky':\n"
                 "                    return\n")),
    "a branch in DashboardServer.handle": plant((RESPOND, method("handle", "self, h", "h.path == '/sneaky'"))),
    "a read replaced by another of the same form and consumer (a quote-style change)": SERVER.replace(
        'url.path.startswith("/api/")', "url.path.startswith('/api/')", 1),
}


@pytest.mark.parametrize("name", sorted(NOT_SEEN))
def test_what_the_path_reads_do_not_see_is_pinned_one_probe_each(name):
    """Each shape is in neither reading (they agree), so the declared reads still equal the reads: the limit the module,
    the page and the note state. A reading widened to see one of them fails its probe here, and the probe moves."""
    declared = declared_of()
    assert NOT_SEEN[name] != SERVER
    assert DASH.path_read_problems(reads_of(NOT_SEEN[name]), declared) == [], name


def test_the_dispatch_is_the_one_call_out_of_a_route_table():
    assert DASH.dispatch_calls(ast.parse(SERVER)) == ["ROUTES.get(url) or CONDITIONAL_HANDLERS[url]"]  # right
    second = SERVER + "\n\ndef extra(p, q, m):\n    return ROUTES['/a'](p, q, m)\n"
    assert len(DASH.dispatch_calls(ast.parse(second))) == 2  # wrong: a second call out of a table
    assert DASH.dispatch_calls(ast.parse(SERVER.replace("(ROUTES.get(url) or CONDITIONAL_HANDLERS[url])(1, 2, 3)",
                                                        "1"))) == []  # missing: none
    reading = ast.parse(SERVER + "\n\ndef scan():\n    return [ROUTES.get('/a'), list(ROUTES.items()), "
                        "CONDITIONAL_HANDLERS.keys()]\n")
    assert len(DASH.dispatch_calls(reading)) == 1  # reading a table is not calling a route out of it


def test_a_limit_is_the_routes_own_bounds_or_the_servers_default_and_none_without_a_limit_parameter():
    from types import SimpleNamespace

    server = SimpleNamespace(LIMIT_PARAMETERS=frozenset({"limit", "annotations_limit"}), ROUTE_LIMITS={"/own": (5, 50)})
    from aew.dashboard import projections

    default = {"default": projections.LIMIT_DEFAULT, "max": projections.LIMIT_MAX, "source": "server default"}
    assert DASH.limit_bounds(server, "/own", ["limit"]) == {"default": 5, "max": 50, "source": "route"}
    assert DASH.limit_bounds(server, "/other", ["limit"]) == default
    assert DASH.limit_bounds(server, "/other", ["annotations_limit", "term"]) == default
    assert DASH.limit_bounds(server, "/own", ["term"]) is None  # missing: a route with no limit parameter has none


# ------------------------------------------------------------------------------------------ the tool catalog

CONTRACT = '''
from typing import NamedTuple


class Tool(NamedTuple):
    name: str


def _catalog(*tools):
    return {t.name: t for t in tools}


TOOLS = _catalog(
    Tool("a"),
    Tool("b"),
)
'''


def catalog(source: str, others: dict[str, str] | None = None) -> list[str]:
    indexes = {name: C.index_of(ast.parse(text), name, False) for name, text in (others or {}).items()}
    return IFACE.catalog_problems(ast.parse(source), indexes)


def test_a_catalog_assigned_once_from_its_constructor_with_every_tool_inside_it_has_no_problem():
    shape = IFACE.catalog_shape(ast.parse(CONTRACT))
    assert (shape.assignments, shape.from_catalog, len(shape.inside), shape.outside) == (1, 1, 2, [])
    assert catalog(CONTRACT) == []
    assert catalog(CONTRACT, {"aew.other": "x = 1\n"}) == []  # a module that makes no Tool


@pytest.mark.parametrize(("name", "source", "why"), [
    ("a tool made beside the catalog", CONTRACT + '\nEXTRA = Tool("c")\n', "is not an argument of that call"),
    ("a second assignment", CONTRACT + '\nTOOLS = _catalog(Tool("c"))\n', "assigned 2 time(s)"),
    ("a table not made by the constructor", CONTRACT.replace("_catalog(\n    Tool", "dict(\n    Tool"),
     "0 from a _catalog(...) call"),
    ("a mutation by assignment of an annotated name", CONTRACT + '\nTOOLS: dict = {}\n', "assigned 2 time(s)"),
])
def test_a_table_not_built_once_by_the_constructor_is_a_problem(name, source, why):
    assert any(why in p for p in catalog(source)), (name, catalog(source))


def test_a_catalog_with_no_table_and_one_with_no_tool_are_problems_not_empty_results():
    assert any("assigned 0 time(s)" in p for p in catalog(CONTRACT.replace("TOOLS = ", "OTHER = ")))
    empty = CONTRACT.replace('    Tool("a"),\n    Tool("b"),\n', "")
    assert any("holds no Tool(...) call" in p for p in catalog(empty))


@pytest.mark.parametrize("source", [
    'from aew.surface.contract import Tool\nx = Tool("z")\n',
    'from aew.surface.contract import Tool as T\nx = T("z")\n',
    'from aew.surface import contract\nx = contract.Tool("z")\n',
    'import aew.surface.contract as c\nx = c.Tool("z")\n',
])
def test_a_tool_constructed_in_another_module_is_found_by_where_its_callee_was_imported_from(source):
    assert catalog(CONTRACT, {"aew.other": source}) == ["aew.other constructs a Tool"]


def test_a_class_of_the_same_name_that_is_not_the_contracts_is_not_its_tool():
    assert catalog(CONTRACT, {"aew.other": 'class Tool:\n    pass\n\n\nx = Tool()\n'}) == []
    assert catalog(CONTRACT, {"aew.other": 'from elsewhere import Tool\nx = Tool("z")\n'}) == []


@pytest.mark.parametrize("source", [
    'from aew.surface.contract import TOOLS\nx = TOOLS["a"]._replace(name="z")\n',  # made by ``_replace``
    'from aew.surface.contract import Tool\nx = Tool._make(["z"])\n',  # made by ``_make``
    'from aew.surface import contract\nx = getattr(contract, "Tool")("z")\n',  # reached through ``getattr``
    'from aew.surface.contract import Tool\nAlias = Tool\nx = Alias("z")\n',  # an alias of ``Tool``
    'from aew.surface.contract import TOOLS, _catalog\nMORE = _catalog(*TOOLS.values())\n',  # a second catalog
    'from aew.surface.contract import TOOLS\nTOOLS["z"] = TOOLS["a"]\n',  # a mutation of ``TOOLS`` elsewhere
])
def test_what_the_catalog_pin_does_not_see_is_pinned_one_probe_each(source):
    """The module's docstring says these are not seen; each probe would fail if one started to be, so the docstring and
    the pin are changed together."""
    assert catalog(CONTRACT, {"aew.other": source}) == []


# ------------------------------------------------------------------------------------------ the schema flattener

EMPTY = Registry()


def flat(schema: dict[str, Any], registry: Registry = EMPTY):
    return SCHEMAS.flatten(schema, registry, "planted")


def test_a_nested_schema_is_flattened_by_path_with_its_types_and_unconditional_requirements():
    result = flat({"type": "object", "required": ["a"], "properties": {
        "a": {"type": "object", "required": ["b"],
              "properties": {"b": {"type": "string"}, "c": {"type": ["null", "integer"]}}},
        "d": {"enum": [1, 2]}, "e": {"const": 3}}})
    assert result.properties == {"a": "object", "a.b": "string", "a.c": "integer|null", "d": "enum", "e": "const"}
    assert result.required == ["a", "a.b"] and result.unresolved == []


def test_items_additional_properties_positional_items_and_pattern_properties_have_their_own_paths():
    result = flat({"type": "object", "properties": {
        "list": {"type": "array", "items": {"type": "string"}},
        "map": {"type": "object", "additionalProperties": {"type": "integer"}},
        "pair": {"type": "array", "prefixItems": [{"type": "string"}, {"type": "integer"}]},
        "named": {"type": "object", "patternProperties": {"^x": {"type": "boolean"}}}}})
    assert result.properties == {"list": "array", "list[]": "string", "map": "object", "map.*": "integer",
                                 "pair": "array", "pair[0]": "string", "pair[1]": "integer", "named": "object",
                                 "named.<^x>": "boolean"}


def test_a_local_reference_is_resolved_and_the_path_takes_the_type_of_its_target():
    result = flat({"$defs": {"x": {"type": "integer"}}, "properties": {"n": {"$ref": "#/$defs/x"}}})
    assert result.properties == {"n": "integer"} and result.unresolved == []


def test_a_reference_to_another_schema_resolves_through_the_registry_relative_to_the_id():
    other = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "aew/other/v1", "type": "object",
             "properties": {"z": {"type": "boolean"}}}
    registry = Registry().with_resource("aew/other/v1", Resource.from_contents(other))
    main = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "aew/main/v1",
            "properties": {"p": {"$ref": "../other/v1"}}}
    result = flat(main, registry)
    assert result.properties == {"p": "object", "p.z": "boolean"} and result.unresolved == []


def test_a_reference_that_does_not_resolve_and_one_that_recurses_are_named_not_followed():
    missing = flat({"properties": {"p": {"$ref": "#/$defs/nope"}}})
    assert missing.properties == {"p": ""} and len(missing.unresolved) == 1
    assert "does not resolve" in missing.unresolved[0] and "#/$defs/nope" in missing.unresolved[0]
    node = {"type": "object", "properties": {"next": {"$ref": "#/$defs/n"}}}
    loop = flat({"$defs": {"n": node}, "$ref": "#/$defs/n"})
    assert "next" in loop.properties and any("recurses" in why for why in loop.unresolved)


def test_a_requirement_under_a_choice_or_a_condition_is_not_unconditional():
    result = flat({"type": "object", "required": ["always"], "properties": {"always": {}, "maybe": {}},
                   "allOf": [{"required": ["also"], "properties": {"also": {}}}],
                   "oneOf": [{"required": ["maybe"]}], "anyOf": [{"required": ["never"], "properties": {"never": {}}}],
                   "if": {"properties": {"gate": {}}, "required": ["gate"]},
                   "then": {"required": ["then_only"], "properties": {"then_only": {}}}})
    assert result.required == ["also", "always"]
    assert set(result.properties) == {"always", "maybe", "also", "never", "then_only"}  # `if` names no path


def test_a_path_reached_twice_has_the_union_of_its_types():
    result = flat({"oneOf": [{"properties": {"v": {"type": "string"}}}, {"properties": {"v": {"type": "integer"}}}]})
    assert result.properties == {"v": "integer|string"}


@pytest.mark.parametrize("keyword", ["contains", "dependentSchemas", "dependencies", "unevaluatedProperties",
                                     "unevaluatedItems", "additionalItems", "contentSchema", "$dynamicRef",
                                     "$recursiveRef", "$dynamicAnchor"])
def test_a_keyword_that_defines_paths_and_is_not_walked_is_an_unresolved_item(keyword):
    result = flat({"properties": {"p": {keyword: {}}}})
    assert len(result.unresolved) == 1 and keyword in result.unresolved[0] and "p" in result.unresolved[0]


@pytest.mark.parametrize("node", [
    {"type": "string", "minLength": 1, "pattern": "^a", "format": "date-time"},
    {"type": "object", "propertyNames": {"pattern": "^k"}, "minProperties": 1, "dependentRequired": {"a": ["b"]}},
    {"title": "t", "description": "d", "default": 1, "examples": [1], "x-note": {"free": "form"}, "$comment": "c"},
    {"not": {"type": "null"}, "if": {"type": "string"}, "then": {"minLength": 1}},
])
def test_a_keyword_that_constrains_or_annotates_and_names_no_path_is_not_an_unresolved_item(node):
    result = flat({"properties": {"p": node}})
    assert result.unresolved == [] and "p" in result.properties


def test_a_keyword_this_reading_has_not_classified_is_an_unresolved_item_not_silence():
    result = flat({"properties": {"p": {"type": "string", "futureKeyword": 1}}})
    assert len(result.unresolved) == 1 and "futureKeyword" in result.unresolved[0] and "p" in result.unresolved[0]
    assert "futureKeyword" in flat({"futureKeyword": 1}).unresolved[0]  # at the root too


def test_array_form_items_are_an_unresolved_item_and_a_schema_form_is_walked():
    listed = flat({"properties": {"p": {"type": "array", "items": [{"type": "string"}]}}})
    assert len(listed.unresolved) == 1 and "items is a list" in listed.unresolved[0]
    assert flat({"properties": {"p": {"type": "array", "items": {"type": "string"}}}}).unresolved == []


def test_a_required_key_nothing_declares_is_typed_by_the_schema_that_would_validate_it():
    by_additional = flat({"type": "object", "required": ["k"], "additionalProperties": {"type": "integer"}})
    assert by_additional.properties == {"k": "integer", "*": "integer"} and by_additional.required == ["k"]
    by_pattern = flat({"type": "object", "required": ["x1"], "patternProperties": {"^x": {"type": "boolean"}},
                       "additionalProperties": {"type": "integer"}})
    assert by_pattern.properties["x1"] == "boolean"  # a pattern that matches wins over additionalProperties
    both_patterns = flat({"type": "object", "required": ["xa"], "patternProperties": {
        "^x": {"type": "boolean"}, "a$": {"type": "string"}}})
    assert both_patterns.properties["xa"] == "boolean|string"  # every pattern that matches types it
    declared = flat({"type": "object", "required": ["k"], "properties": {"k": {"type": "string"}},
                     "additionalProperties": {"type": "integer"}})
    assert declared.properties["k"] == "string"  # a declared key keeps its own type


def test_a_required_key_nothing_types_is_a_path_with_no_type_and_a_conditional_one_is_not_typed_here():
    assert flat({"type": "object", "required": ["k"]}).properties == {"k": ""}  # missing: nothing to type it by
    miss = flat({"type": "object", "required": ["k"], "patternProperties": {"^x": {"type": "boolean"}}})
    assert miss.properties["k"] == ""  # a pattern the key does not match
    conditional = flat({"type": "object",
                        "oneOf": [{"required": ["k"], "additionalProperties": {"type": "integer"}}]})
    assert "k" not in conditional.required and "k" not in conditional.properties  # typed only if required for sure


def test_a_pattern_the_flattener_cannot_read_is_an_unresolved_item():
    result = flat({"type": "object", "required": ["k"], "patternProperties": {"(": {"type": "string"}}})
    assert any("cannot be read" in why for why in result.unresolved)


def test_a_schema_with_no_id_is_registered_under_a_name_so_its_local_references_resolve():
    result = flat({"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": {"t": {"type": "string"}},
                   "properties": {"a": {"$ref": "#/$defs/t"}}})
    assert result.properties == {"a": "string"}


# ------------------------------------------------------------------------------------------ the SQLite reader

def test_a_table_and_its_index_are_read_back_with_their_columns_and_flags():
    rows, error = SQL.read_back(["CREATE TABLE t (a INTEGER PRIMARY KEY, b TEXT NOT NULL DEFAULT 'x');"
                                 "CREATE UNIQUE INDEX t_b ON t (b);"])
    assert error is None
    [(name, kind, columns, indexes)] = rows
    assert (name, kind) == ("t", "table")
    assert columns == [{"name": "a", "type": "INTEGER", "notnull": False, "default": None, "pk": 1},
                       {"name": "b", "type": "TEXT", "notnull": True, "default": "'x'", "pk": 0}]
    assert indexes == [{"name": "t_b", "unique": True, "columns": ["b"]}]


def test_a_full_text_table_is_virtual_and_its_shadow_tables_are_not_records():
    rows, error = SQL.read_back(["CREATE VIRTUAL TABLE v USING fts5(x)", "CREATE TABLE plain (a)"])
    assert error is None
    assert [(n, k) for n, k, _, _ in rows] == [("plain", "table"), ("v", "virtual")]


def test_a_statement_that_does_not_run_is_an_error_not_an_empty_result():
    rows, error = SQL.read_back(["CREATE TABEL t (a)"])
    assert rows == [] and error is not None and "OperationalError" in error


def test_ddl_is_found_in_module_level_constants_of_every_shape_and_nowhere_else():
    tree = ast.parse("\n".join([
        "A = 'CREATE TABLE a (x)'",
        "B = ('CREATE TABLE b (x)', f\"CREATE INDEX i ON b ({COL})\")",
        "C: str = '''create virtual table c using fts5(x)'''",
        "D = 'SELECT 1'",
        "E = 'we created tables here'",
        "def f():\n    F = 'CREATE TABLE inside (x)'",
    ]))
    assert SQL.ddl_constants(tree) == ["A", "B", "C"]


def test_statements_of_takes_a_string_or_a_sequence_of_strings_only():
    assert SQL.statements_of("x") == ["x"] and SQL.statements_of(("a", "b")) == ["a", "b"]
    assert SQL.statements_of(["a"]) == ["a"] and SQL.statements_of(3) is None and SQL.statements_of(("a", 1)) is None


def test_ddl_built_inside_a_function_is_found_with_its_symbol_and_an_fstring_placeholder_is_resolved_from_the_module():
    tree = ast.parse("class K:\n    def __init__(self, c):\n        c.execute(f\"CREATE VIRTUAL TABLE m USING fts5(t, "
                     "tokenize='{TOK}')\")\n\n\nc.execute('CREATE TABLE top (x)')\n")
    [(symbol, node)] = SQL.transient_sites(tree)  # the module-level execute is not in a function
    assert symbol == "K.__init__"

    class Module:
        TOK = "porter"

    assert SQL.render(node, Module) == "CREATE VIRTUAL TABLE m USING fts5(t, tokenize='porter')"
    assert SQL.render(node, object()) is None  # a placeholder the module does not have
    assert SQL.render(ast.parse("f\"{a.b}\"", mode="eval").body, Module) is None  # not a plain name


def test_the_text_detector_reads_table_names_and_the_import_and_skips_comments():
    text = ("import sqlite3\n# CREATE TABLE commented (x)\nA = 'CREATE TABLE IF NOT EXISTS one (x)'\n"
            "B = f\"CREATE VIRTUAL TABLE two USING fts5(x)\"\nC = 'create table `three` (x)'\n")
    assert SQL_TEXT.table_names(text) == ["one", "three", "two"]
    assert SQL_TEXT.imports_sqlite(text) and not SQL_TEXT.imports_sqlite("x = 'import sqlite3'\n")
    assert SQL_TEXT.imports_sqlite("from sqlite3 import connect\n")


# ------------------------------------------------------------------------------------------ the CLI anchors

def _named(args):
    return args


def _register():
    return lambda args: args


class _Handlers:
    def method(self):
        return None


def test_a_handler_is_anchored_at_its_function_and_a_lambda_at_the_function_that_registers_it():
    assert CLI.anchor_of(_named) == (__name__, "_named")
    assert CLI.anchor_of(_register()) == (__name__, "_register")  # `_register.<locals>.<lambda>` has no name of its own
    assert CLI.anchor_of(_Handlers.method) == (__name__, "_Handlers.method")
    assert CLI.anchor_of(None) is None and CLI.anchor_of(3) is None  # a leaf with no handler has no anchor
