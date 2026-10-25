"""The interface families of the generated reference (STG-12 S12-2, family 6): ``dashboard-routes``, ``tools``,
``schemas``, ``sqlite-tables`` and ``cli-commands``, on one page.

Each family is read from its owner and has its own module: the dashboard server's route tables
(``interfaces_dashboard.py``), the typed Lead tools (below), the JSON schemas (``interfaces_schemas.py``), the SQLite
DDL (``interfaces_sqlite.py``) and the CLI's links into the surface map (``interfaces_cli.py``). A family whose
reading is a recogniser has a second, independently written detector, and
``tests/integration/test_reference_interfaces.py`` and ``tests/integration/test_reference_dashboard_routes.py`` hold
them to each other and to their registries; the planted controls of every recogniser are in
``tests/unit/test_reference_interface_controls.py``.

**``tools``.** Owner: ``aew.surface.contract.TOOLS``, the Lead's typed tools, imported at run time (basis
``enumerated``). Complete-by-construction because the catalog has one constructor: ``_catalog`` builds the table,
refuses a duplicate name, an unknown kind, class, status or profile, and a ``produced_by`` that does not fit. The pin
(:func:`catalog_shape`, :func:`catalog_problems`) holds that ``TOOLS`` is assigned once at the contract's top level from
a ``_catalog(...)`` call, that every ``Tool(`` call of the contract is an argument of that call, and that no other
module calls ``Tool`` (a call identified by where its callee was imported from). It does not see a ``Tool`` made by
``_replace`` or ``_make``, an alias of ``Tool``, a mutation of ``TOOLS`` from another module, or a second catalog. A
record states the tool's own flags and the names of its arguments, not its description or its argument schema (the
owner's presentation, which a reader takes from the catalog).
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any, NamedTuple

from reference_families import common as C
from reference_families import interfaces_cli, interfaces_dashboard, interfaces_schemas, interfaces_sqlite

TOOLS = "tools"
CONTRACT = "aew.surface.contract"
TOOLS_REGISTRY = f"{CONTRACT}:TOOLS"
_TESTS = "tests/integration/test_reference_interfaces.py"
TOOL_TESTS = (
    f"{_TESTS}::test_the_tool_records_are_the_catalog_both_ways",
    f"{_TESTS}::test_the_catalog_is_built_only_by_its_one_constructor",
    f"{_TESTS}::test_the_catalog_refuses_a_duplicate_and_an_unknown_kind",
)


class CatalogShape(NamedTuple):
    assignments: int  # module-level assignments to ``TOOLS``
    from_catalog: int  # of those, the ones made from a ``_catalog(...)`` call
    inside: list[tuple[int, int]]  # (line, column) of every ``Tool(`` call inside that call
    outside: list[tuple[int, int]]  # (line, column) of every ``Tool(`` call elsewhere in the module


def catalog_shape(tree: ast.Module) -> CatalogShape:
    """How the contract builds ``TOOLS``: its assignments, and where its ``Tool(`` calls are."""
    assigned = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                and C.dotted(n.target if isinstance(n, ast.AnnAssign) else n.targets[0]) == "TOOLS"]
    made = [n for n in assigned if isinstance(n.value, ast.Call) and C.dotted(n.value.func) == "_catalog"]
    covered = {(n.lineno, n.col_offset) for a in made if a.value is not None for n in ast.walk(a.value)
               if isinstance(n, ast.expr)}
    calls = sorted((c.lineno, c.col_offset) for c in ast.walk(tree)
                   if isinstance(c, ast.Call) and C.dotted(c.func) == "Tool")
    return CatalogShape(len(assigned), len(made), [p for p in calls if p in covered],
                        [p for p in calls if p not in covered])


def foreign_constructions(index: C.Index) -> int:
    """How many calls of a module construct the contract's ``Tool``, by where the callee was imported from."""
    return sum(1 for call, _ in index.calls if index.aliases.resolve(call.func) == f"{CONTRACT}.Tool")


def catalog_problems(contract_tree: ast.Module, others: Mapping[str, C.Index]) -> list[str]:
    """What the pin refuses: a ``TOOLS`` not assigned once from ``_catalog(...)``, a ``Tool(`` outside that call, or a
    construction of a ``Tool`` in another module (``others``: module name -> its index)."""
    shape = catalog_shape(contract_tree)
    problems = []
    if shape.assignments != 1 or shape.from_catalog != 1:
        problems.append(f"TOOLS is assigned {shape.assignments} time(s) at the top level, {shape.from_catalog} from "
                        "a _catalog(...) call; it is assigned once, from one")
    if not shape.inside:
        problems.append("the _catalog(...) call that TOOLS is assigned from holds no Tool(...) call")
    problems += [f"a Tool(...) call at line {line} is not an argument of that call" for line, _ in shape.outside]
    problems += [f"{name} constructs a Tool" for name, index in sorted(others.items()) if foreign_constructions(index)]
    return problems


def tool_records() -> list[C.Record]:
    from aew.surface import contract

    records = []
    for name, tool in sorted(contract.TOOLS.items()):
        properties = tool.input_schema.get("properties") or {}
        fact: dict[str, Any] = {"name": name, "kind": tool.kind, "class": tool.base_class, "status": tool.status,
                                "mutates": tool.mutates, "dispatches": tool.dispatches, "progression": tool.progression,
                                "profiles": list(tool.profiles), "arguments": sorted(properties)}
        # a list fact is on the record when the tool has one, each with how complete it is (addendum 3)
        optional = {"expands_to": list(tool.expands_to), "required_judgments": list(tool.required_judgments),
                    "promotes": list(tool.promotes),
                    "required_arguments": list(tool.input_schema.get("required") or [])}
        fact.update({k: v for k, v in optional.items() if v})
        cov = C.complete(TOOLS_REGISTRY, TOOL_TESTS)
        fact_coverage = {k: cov for k, v in fact.items() if isinstance(v, list)}
        records.append(C.Record(TOOLS, name, CONTRACT, "TOOLS", "enumerated", cov, fact, fact_coverage=fact_coverage))
    return records


def build(ctx: C.Context) -> C.Built:
    records = [*interfaces_dashboard.build(ctx), *tool_records(), *interfaces_schemas.build(ctx),
               *interfaces_sqlite.build(ctx), *interfaces_cli.build(ctx)]
    return C.Built(records=records, pages={"interfaces.md": page(records)})


def page(records: list[C.Record]) -> str:
    by: dict[str, list[C.Record]] = {}
    for r in records:
        by.setdefault(r.family, []).append(r)

    def words(items: Any) -> str:
        shown = [f"`{i}`" for i in items]
        return ", ".join(shown) if shown else "-"

    routes = by.get(interfaces_dashboard.FAMILY, [])
    methods = next(((r.fact or {})["methods"] for r in routes), [])
    lines = ["# Interfaces", "",
             "What the product exposes, each read from its owner: the dashboard's routes, the Lead's typed tools, the "
             "JSON schemas of the durable artifacts (flattened), the SQLite tables the product creates, and the `aew` "
             "commands (linked into the surface map, which owns them). Generated by "
             "`python tools/reference.py render`; do not edit. An unresolved item of any family is in "
             "[gaps.md](gaps.md).", "",
             "## Dashboard routes", "",
             "The API routes are every key of `ROUTES` and `CONDITIONAL_HANDLERS` of `aew.dashboard.server`; the "
             "server also answers two paths that are not the API, read from `_handle`. Every route answers "
             f"{words(methods)}. The reading counts every read of the request path in `_handle` and `_respond`, so a "
             "route served by a branch of its own is a difference; a test of the path inside a function they call "
             "is not read. A route's limit bounds are what the server normalises its limit parameter with: its own, or "
             "the server's default.", "",
             "| Route | Conditional | Query parameters | Repeatable | Limit bounds |", "|---|---|---|---|---|"]
    for r in routes:
        f = r.fact or {}
        if f.get("api") is False:
            continue
        limit = f.get("limit")
        shown = "-"
        if limit:
            note = "" if limit["source"] == "route" else " (server default)"
            shown = f"{limit['default']} to {limit['max']}{note}"
        lines.append(f"| `{f['route']}` | {'yes' if f['conditional'] else 'no'} | {words(f['query'])} | "
                     f"{words(f.get('repeatable', []))} | {shown} |")
    lines += ["", "Outside the API:", ""]
    for f in (r.fact or {} for r in routes):
        if f.get("api") is not False:
            continue
        where = f"under `{f['under']}`" if "under" in f else "outside " + words(f["outside"])
        needs = f"; answered only while the server has `{f['needs']}`" if f.get("needs") else ""
        lines.append(f"- `{f['route']}`: handled by `{f['handler']}`, {where}{needs}.")
    lines += ["", "## Tools", "",
              "| Tool | Kind | Class | Status | Mutates | Dispatches | Expands to |", "|---|---|---|---|---|---|---|"]
    for r in by.get(TOOLS, []):
        f = r.fact or {}
        lines.append(f"| `{f['name']}` | {f['kind']} | {f['class']} | {f['status']} | "
                     f"{'yes' if f['mutates'] else 'no'} | "
                     f"{'yes' if f['dispatches'] else 'no'} | {words(f.get('expands_to', []))} |")
    lines += ["", "## Schemas", "",
              "Flattened: a path is `a.b` for a property, `a[]` for items, `a.*` for the values of an "
              "`additionalProperties` schema. The paths and their types are in `index.json`; a path with no type is a "
              "key the schema requires and gives no type.", "",
              "| Schema | File | Paths | Required |", "|---|---|---|---|"]
    for r in by.get(interfaces_schemas.FAMILY, []):
        f = r.fact or {}
        lines.append(f"| `{f['name']}` | `{f['file']}` | {len(f.get('properties', {}))} | "
                     f"{len(f.get('required', []))} |")
    lines += ["", "## SQLite tables", "",
              "Created from the DDL the product holds, executed in memory and read back. `transient` is a table the "
              "product builds in memory to match text, never a store. DDL built at run time is not found.", "",
              "| Module | Table | Kind | Scope | Columns | Indexes |", "|---|---|---|---|---|---|"]
    for r in by.get(interfaces_sqlite.FAMILY, []):
        f = r.fact or {}
        lines.append(f"| `{f['module']}` | `{f['table']}` | {f['kind']} | {f['scope']} | "
                     f"{words(c['name'] for c in f['columns'])} | {words(i['name'] for i in f['indexes'])} |")
    commands = by.get(interfaces_cli.FAMILY, [])
    lines += ["", "## CLI commands", "",
              f"{len(commands)} commands, each linked to its entry in the `commands` section of "
              f"`{interfaces_cli.SURFACE_MAP}`, which owns what each is for. Nothing of the entry is copied here.", "",
              words((r.fact or {})["command"] for r in commands)]
    return "\n".join(lines).rstrip("\n") + "\n"
