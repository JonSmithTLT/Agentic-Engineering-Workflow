"""The interface families of the generated reference (STG-12 S12-2, family 6): the typed Lead tools, the JSON schemas,
the SQLite tables and the CLI commands (``tools/reference_families/interfaces*.py``). The dashboard's routes are in
``tests/integration/test_reference_dashboard_routes.py``.

A static enumeration that feeds a label is asserted equal to the registry it models, in both directions: the tool
records to ``TOOLS`` (and ``TOOLS`` to its one constructor), the schema records to ``SCHEMAS`` and to the directory,
the SQLite records to the DDL by two independent readings (``interfaces_sqlite.py``, which runs the statements, and
``interfaces_sqlite_text.py``, which reads the table names from the text), and the command records to the live parser
and to the surface map. The records are built in memory; the planted controls of the pure rules are in
``tests/unit/test_reference_interface_controls.py``.

The heavy lanes run this because it imports the product: a pull request that changes a tool, a schema, a table or a
command changes ``src`` and so runs the full gate.
"""

from __future__ import annotations

import ast
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from aew import schemas
from aew.surface import contract

ROOT = Path(__file__).resolve().parents[2]


def _tool_modules():
    """The generator's family modules, with ``tools/`` on the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import (
            common,
            interfaces,
            interfaces_cli,
            interfaces_schemas,
            interfaces_sqlite,
            interfaces_sqlite_text,
        )
    finally:
        sys.path.remove(here)
    return common, interfaces, interfaces_cli, interfaces_schemas, interfaces_sqlite, interfaces_sqlite_text


C, IFACE, CLI, SCH, SQL, SQL_TEXT = _tool_modules()
CTX = C.Context(ROOT)


@cache
def records(family: str) -> dict[str, dict[str, Any]]:
    build = {"tools": lambda: IFACE.tool_records(), "schemas": lambda: SCH.build(CTX),
             "sqlite-tables": lambda: SQL.build(CTX),
             "cli-commands": lambda: CLI.build(CTX)}[family]
    return {r.key: r.as_json() for r in build()}


# ------------------------------------------------------------------------------------------------------ the tools

def test_the_tool_records_are_the_catalog_both_ways():
    found = records("tools")
    assert set(found) == set(contract.TOOLS) and len(found) == len(contract.TOOLS)
    for name, tool in contract.TOOLS.items():
        r = found[name]
        properties = tool.input_schema.get("properties") or {}
        want: dict[str, Any] = {"name": name, "kind": tool.kind, "class": tool.base_class, "status": tool.status,
                                "mutates": tool.mutates, "dispatches": tool.dispatches, "progression": tool.progression,
                                "profiles": list(tool.profiles), "arguments": sorted(properties)}
        for key, value in (("expands_to", list(tool.expands_to)), ("required_judgments", list(tool.required_judgments)),
                           ("promotes", list(tool.promotes)),
                           ("required_arguments", list(tool.input_schema.get("required") or []))):
            if value:
                want[key] = value
        assert r["fact"] == want, name
        assert (r["anchor"]["module"], r["anchor"]["symbol"], r["basis"]) == (
            "aew.surface.contract", "TOOLS", "enumerated")
        assert r["coverage"]["label"] == "complete-by-construction"
        assert set(r["fact_coverage"]) == {k for k, v in want.items() if isinstance(v, list)}


def contract_tree() -> ast.Module:
    tree = CTX.sources()["aew.surface.contract"].tree
    assert tree is not None
    return tree


def test_the_catalog_is_built_only_by_its_one_constructor():
    """``TOOLS`` is assigned once, from ``_catalog(...)``, and a ``Tool`` is constructed only as an argument of that
    call (the owner's constructor refuses a duplicate or an unknown value); no other module calls ``Tool``, found by
    where the callee was imported from. The finders are the generator's (:func:`catalog_problems`); their planted
    controls are in ``tests/unit/test_reference_interface_controls.py``. What they do not see is in the module's
    docstring: a ``Tool`` made by ``_replace`` or ``_make``, an alias, a second catalog."""
    others = {name: CTX.index(name) for name, src in CTX.sources().items()
              if name != "aew.surface.contract" and src.tree is not None}
    assert IFACE.catalog_problems(contract_tree(), others) == []
    shape = IFACE.catalog_shape(contract_tree())
    assert (shape.assignments, shape.from_catalog) == (1, 1) and shape.outside == []
    assert len(shape.inside) == len(contract.TOOLS)  # one construction for each tool the catalog holds


def test_the_catalog_refuses_a_duplicate_and_an_unknown_kind():
    one = contract.Tool("planted", contract.QUERY, contract.MECHANICAL, "a planted tool", {"type": "object"})
    assert list(contract._catalog(one)) == ["planted"]  # right
    with pytest.raises(ValueError, match="declared twice"):
        contract._catalog(one, one)  # wrong: a duplicate
    with pytest.raises(ValueError, match="unknown kind"):
        contract._catalog(one._replace(name="other", kind="nonsense"))  # wrong: an unknown kind
    with pytest.raises(ValueError, match="unknown profile"):
        contract._catalog(one._replace(profiles=("nowhere",)))
    assert list(contract._catalog()) == []  # missing: no tool is a catalog without one


# ---------------------------------------------------------------------------------------------------- the schemas

def test_the_schema_records_are_the_registry_and_the_directory_both_ways():
    found = records("schemas")
    directory = sorted(p.name for p in (ROOT / "src" / "aew" / "schemas").glob("*.schema.json"))
    assert directory == sorted(schemas.SCHEMAS.values()), "a schema file is unregistered, or a registered file is gone"
    assert set(found) == set(schemas.SCHEMAS)
    others = sorted(p.name for p in (ROOT / "src" / "aew" / "schemas").iterdir()
                    if p.is_file() and p.suffix == ".json" and not p.name.endswith(".schema.json"))
    assert others == sorted(SCH.DATA_FILES), "a JSON file beside the schemas is neither a schema nor declared data"
    for name, file in schemas.SCHEMAS.items():
        r = found[name]
        assert r["fact"]["file"] == file and r["fact"]["registered"] is True
        assert r["fact"]["id"] == schemas.schema(name).get("$id")
        assert (r["anchor"]["module"], r["anchor"]["symbol"], r["basis"]) == ("aew.schemas", "SCHEMAS", "enumerated")
        assert r["coverage"]["label"] == "complete-by-construction"


def test_every_registered_schema_flattens_with_its_unresolved_items_named():
    """The flattened paths of each real schema, its cross-file references included. A schema whose flattening leaves
    something out says what, as a lower-bound item of its properties and required lists; none does today."""
    for name, r in records("schemas").items():
        facts = r["fact"]
        assert facts["properties"], name
        label = r["fact_coverage"]["properties"]["label"]
        assert label == r["fact_coverage"]["required"]["label"]
        assert (label == "lower-bound") is bool(r["fact_coverage"]["properties"].get("unresolved")), name
        assert set(facts["required"]) <= set(facts["properties"]), name
    control = records("schemas")["control"]["fact"]["properties"]
    # the control state's `last_transition` is a transition record in another schema, resolved by `$id`
    assert any(p.startswith("last_transition.") for p in control), "a cross-file reference was not followed"


# ----------------------------------------------------------------------------------------------------- SQLite

def test_the_sqlite_records_are_the_ddl_read_back_in_memory():
    found = records("sqlite-tables")
    assert found, "no table was found"
    names = {(r["fact"]["module"], r["fact"]["table"]) for r in found.values()}
    assert len(names) == len(found)
    for key, r in found.items():
        fact = r["fact"]
        assert key == f"{fact['module']}:{fact['table']}" and fact["columns"], key
        assert fact["scope"] in ("store", "transient") and fact["kind"] in ("table", "virtual")
        assert r["basis"] == "observed" and r["fact_coverage"]["columns"]["label"] == "complete-by-construction"
        assert r["coverage"]["label"] == "lower-bound"
    transient = {k for k, r in found.items() if r["fact"]["scope"] == "transient"}
    assert transient == {"aew.engine.recall:m"}, "an in-memory table the product builds to match text"


def test_the_two_sqlite_detectors_agree_on_the_tree():
    """The tables the executed DDL gives, per module, are the table names the text of the module spells; and a module
    that imports ``sqlite3`` either has records or is an unresolved item of every record."""
    ours: dict[str, set[str]] = {}
    for r in records("sqlite-tables").values():
        ours.setdefault(r["fact"]["module"], set()).add(r["fact"]["table"])
    theirs: dict[str, set[str]] = {}
    importers = set()
    for name, src in CTX.sources().items():
        if names := SQL_TEXT.table_names(src.text):
            theirs[name] = set(names)
        if SQL_TEXT.imports_sqlite(src.text):
            importers.add(name)
    assert ours == theirs
    unresolved = {i["module"] for i in next(iter(records("sqlite-tables").values()))["coverage"]["unresolved"]}
    assert importers == set(ours) | unresolved, (sorted(importers ^ (set(ours) | unresolved)))
    tables, _ = SQL.tables_of(CTX)
    assert {(t.module, t.name) for t in tables} == {(m, t) for m, ts in ours.items() for t in ts}


# ------------------------------------------------------------------------------------------------------ the CLI

def live_leaves() -> set[str]:
    """The parser's commands, found independently of the family module: every parser that has no sub-parsers."""
    import argparse

    from aew.cli.main import build_parser

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> set[str]:
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            return {" ".join(path)}
        return set().union(*(walk(child, (*path, name)) for a in subs for name, child in a.choices.items()))

    return walk(build_parser(recall_search=True, coordination_reads=True), ())


def test_every_surface_map_command_links_to_a_live_command_and_back():
    """The surface map owns the commands (``test_surface_map`` holds it to the parser); this holds the links: each
    record is an entry of the map's ``commands`` section and a leaf of the parser, and there is no entry or leaf
    without one."""
    doc = yaml.safe_load((ROOT / "docs" / "implementation" / "surface-map.yaml").read_text(encoding="utf-8"))
    entries = [e["name"] for e in doc["commands"]]
    assert len(entries) == len(set(entries))
    live = live_leaves()
    found = records("cli-commands")
    assert set(found) == set(entries) == live, (sorted(set(entries) ^ live))
    for name, r in found.items():
        assert r["fact"] == {"command": name, "live": True, "surface_map": {
            "file": "docs/implementation/surface-map.yaml", "section": "commands", "name": name}}
        assert r["coverage"]["label"] == "complete-by-construction" and r["basis"] == "declared"
        module = __import__(r["anchor"]["module"], fromlist=["x"])
        assert hasattr(module, r["anchor"]["symbol"].split(".")[0]), name


def test_a_command_without_an_entry_and_an_entry_without_a_command_are_named_not_dropped(monkeypatch):
    live = CLI.live_commands()
    real = CLI.entries(CTX)
    monkeypatch.setattr(CLI, "live_commands", lambda: {**live, "planted-command": CLI.PARSER})
    monkeypatch.setattr(CLI, "entries", lambda ctx: [*real, "planted-entry"])
    built = {r.key: r for r in CLI.build(CTX)}
    assert [i["why"] for i in built["planted-command"].coverage["unresolved"]] == [
        "planted-command is a command of the parser and has no entry in the surface map"]
    assert built["planted-command"].fact["surface_map"] is None and built["planted-command"].fact["live"] is True
    assert [i["why"] for i in built["planted-entry"].coverage["unresolved"]] == [
        "planted-entry has an entry in the surface map and is not a command of the parser"]
    assert built["planted-entry"].fact["live"] is False


def test_a_live_command_with_no_anchorable_handler_is_named_not_anchored_at_the_parser(monkeypatch):
    live = CLI.live_commands()
    real = CLI.entries(CTX)
    monkeypatch.setattr(CLI, "live_commands", lambda: {**live, "planted-bare": None})
    monkeypatch.setattr(CLI, "entries", lambda ctx: [*real, "planted-bare"])
    built = {r.key: r for r in CLI.build(CTX)}
    bare = built["planted-bare"]
    assert [i["why"] for i in bare.coverage["unresolved"]] == [
        "planted-bare has no handler this reading can anchor (it is not a function with a module and a name)"]
    assert bare.coverage["label"] == "lower-bound" and bare.fact["live"] is True
    assert built[next(iter(live))].coverage["label"] == "complete-by-construction"  # a real command is unaffected


def test_the_parser_is_built_with_every_switch_it_takes():
    """``live_commands`` builds the parser with both switches on. A third parameter would leave its commands out of the
    walk, so the parameters are pinned here and the reference fails loudly when one is added."""
    import inspect

    from aew.cli.main import build_parser

    assert set(inspect.signature(build_parser).parameters) == {"recall_search", "coordination_reads"}


# ------------------------------------------------------------------------------------------------------- the page

def test_the_page_states_the_limit_bounds_and_the_conditions_and_restates_no_refusal():
    """A route with a limit parameter shows its bounds (its own, or the server's default, so that ``-`` never reads as
    "no limit"); the two paths outside the API say what they are answered only while; and the page does not restate the
    status the server answers an unsupported method with (the server owns it)."""
    page = IFACE.build(CTX).pages["interfaces.md"]
    rows = {line.split("|")[1].strip(" `"): [c.strip() for c in line.split("|")[2:-1]]
            for line in page.splitlines() if line.startswith("| `/")}
    assert rows["/activity"][-1] == "100 to 250 (server default)"
    assert rows["/history/search"][-1] == "100 to 250 (server default)"
    assert rows["/maps/structural"][-1] == "20 to 50"  # the route's own bounds
    assert rows["/overview"][-1] == "-"  # a route with no limit parameter
    assert "answered only while the server has `sessions`" in page and "`static_root`" in page
    assert "405" not in page and "refused" not in page
