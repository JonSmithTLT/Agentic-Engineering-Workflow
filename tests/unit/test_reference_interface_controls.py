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
            interfaces_cli,
            interfaces_dashboard,
            interfaces_dashboard_text,
            interfaces_schemas,
            interfaces_sqlite,
            interfaces_sqlite_text,
        )
    finally:
        sys.path.remove(here)
    return (interfaces_cli, interfaces_dashboard, interfaces_dashboard_text, interfaces_schemas, interfaces_sqlite,
            interfaces_sqlite_text)


CLI, DASH, DASH_TEXT, SCHEMAS, SQL, SQL_TEXT = _tools()

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
    assert ours.branches == [DASH.Branch("/session/", False, "_exchange"), DASH.Branch("/api/", True, "_static")]
    assert ours.fallthrough == "_respond" and ours.methods == ["GET", "HEAD"]
    assert ours.references == [("CONDITIONAL_HANDLERS", "DashboardServer._respond"),
                               ("ROUTES", "DashboardServer._respond"), ("ROUTES", "pending_routes")]


def test_a_branch_testing_a_prefix_the_reading_cannot_resolve_is_reported_not_dropped():
    ours, theirs = both(SERVER, constants={})  # SESSION_PREFIX is unknown
    assert ours == theirs
    assert ours.branches[0] == DASH.Branch(None, False, "_exchange")


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


@pytest.mark.parametrize("keyword", ["dependentSchemas", "unevaluatedProperties", "unevaluatedItems", "additionalItems",
                                     "contentSchema", "$dynamicRef", "$recursiveRef"])
def test_a_keyword_that_defines_paths_and_is_not_walked_is_an_unresolved_item(keyword):
    result = flat({"properties": {"p": {keyword: {}}}})
    assert len(result.unresolved) == 1 and keyword in result.unresolved[0] and "p" in result.unresolved[0]


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
