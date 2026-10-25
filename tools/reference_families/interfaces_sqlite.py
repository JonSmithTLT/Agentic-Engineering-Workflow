"""The ``sqlite-tables`` family (STG-12 S12-2, family 6): the SQLite tables the product creates.

Owner: the DDL the modules hold. A module-level constant whose value contains ``CREATE`` (found by ``ast``) is read by
importing the module, so a statement built with an f-string is the text the product runs; its statements are executed
in a fresh ``:memory:`` database and the tables are read back with ``PRAGMA`` (basis ``observed``). A statement built
inside a function (``recall._Matcher``'s throwaway full-text table) is read from the function's own string, its
f-string placeholders resolved from the module, and recorded with scope ``transient``: an in-memory table the product
builds to match text, never a store. A full-text table's shadow tables (``<table>_data`` and the like) belong to it
and are not records.

The reading is lower-bound: DDL built any other way (a name held in a variable, a string assembled at run time) is in
no constant and no literal, so it is not found. Two things bound that, and both are items of the records: a module
that imports ``sqlite3`` and holds no DDL (it opens a database another module created) is named, and a statement that
cannot be executed here is named. ``interfaces_sqlite_text.py`` is the second, independently written detector: it
reads the table names from the source text, and the two agree on the tree
(``tests/integration/test_reference_interfaces.py``).
"""

from __future__ import annotations

import ast
import importlib
import re
import sqlite3
from typing import Any, NamedTuple

from reference_families import common as C

FAMILY = "sqlite-tables"
_TESTS = "tests/integration/test_reference_interfaces.py"
TESTS = (
    f"{_TESTS}::test_the_sqlite_records_are_the_ddl_read_back_in_memory",
    f"{_TESTS}::test_the_two_sqlite_detectors_agree_on_the_tree",
)
DDL = re.compile(r"\bCREATE\s+(?:UNIQUE\s+|VIRTUAL\s+|TEMP\s+|TEMPORARY\s+)?(?:TABLE|INDEX)\b", re.IGNORECASE)


class Table(NamedTuple):
    module: str
    symbol: str  # the constant, or the function, that holds the DDL
    name: str
    kind: str  # "table" or "virtual"
    scope: str  # "store" (a module-level constant) or "transient" (built in a function)
    columns: list[dict[str, Any]]
    indexes: list[dict[str, Any]]


def holds_ddl(node: ast.AST) -> bool:
    """Whether any string in the expression (an f-string's literal parts included) contains DDL."""
    return any(isinstance(n, ast.Constant) and isinstance(n.value, str) and DDL.search(n.value) for n in ast.walk(node))


def ddl_constants(tree: ast.Module) -> list[str]:
    """The module-level names assigned an expression that holds DDL."""
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name, value = node.target.id, node.value
        else:
            continue
        if holds_ddl(value):
            found.append(name)
    return found


def statements_of(value: Any) -> list[str] | None:
    """The statements a constant holds: a string (one script) or a tuple or list of strings; None for anything else."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


class _Transient(C.Scoped):
    """The ``execute`` and ``executescript`` calls inside a function whose first argument holds DDL, with their
    symbol."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, ast.expr]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if (self.symbol and isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executescript")
                and node.args and holds_ddl(node.args[0])):
            self.found.append((self.symbol, node.args[0]))
        self.generic_visit(node)


def transient_sites(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    visitor = _Transient()
    visitor.visit(tree)
    return visitor.found


def render(node: ast.expr, module: Any) -> str | None:
    """The text of a string literal or f-string, a placeholder that is a module-level name taken from the module; None
    when a placeholder is anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.Constant):
                parts.append(str(part.value))
            elif (isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name) and part.format_spec is None
                  and part.conversion == -1 and hasattr(module, part.value.id)):
                parts.append(str(getattr(module, part.value.id)))
            else:
                return None
        return "".join(parts)
    return None


Row = tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]  # name, kind, columns, indexes


def read_back(statements: list[str]) -> tuple[list[Row], str | None]:
    """Execute the statements in a fresh in-memory database and read the tables back: (name, kind, columns, indexes)
    for each table, sorted, and the error if a statement did not run."""
    conn = sqlite3.connect(":memory:")
    try:
        for statement in statements:
            conn.executescript(statement)
        rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite\\_%' "
                            "ESCAPE '\\'").fetchall()
        virtual = {name for name, sql in rows if (sql or "").upper().startswith("CREATE VIRTUAL")}
        out = []
        for name, _sql in sorted(rows):
            if any(name.startswith(f"{v}_") for v in virtual):  # a full-text table's own shadow tables
                continue
            columns = [{"name": c[1], "type": c[2], "notnull": bool(c[3]), "default": c[4], "pk": c[5]}
                       for c in conn.execute(f'PRAGMA table_info("{name}")')]
            indexes = []
            for _, index, unique, origin, _partial in conn.execute(f'PRAGMA index_list("{name}")'):
                if origin == "c":  # created by CREATE INDEX; the automatic ones belong to a key
                    names = [c[2] for c in conn.execute(f'PRAGMA index_info("{index}")')]
                    indexes.append({"name": index, "unique": bool(unique), "columns": names})
            kind = "virtual" if name in virtual else "table"
            out.append((name, kind, columns, sorted(indexes, key=lambda i: i["name"])))
        return out, None
    except sqlite3.Error as exc:
        return [], f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()


def imports_sqlite(index: C.Index) -> bool:
    for node in index.imports:
        if isinstance(node, ast.Import) and any(a.name == "sqlite3" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.module == "sqlite3":
            return True
    return False


def tables_of(ctx: C.Context) -> tuple[list[Table], list[dict[str, Any]]]:
    """Every table the product's DDL creates, and the unresolved items of the reading."""
    tables: list[Table] = []
    unresolved: list[dict[str, Any]] = []
    for name, src in ctx.sources().items():
        if src.tree is None:
            continue
        constants = ddl_constants(src.tree)
        sites = transient_sites(src.tree)
        found_here = False
        module: Any = None
        if constants or sites:
            try:
                module = importlib.import_module(name)
            except ImportError as exc:
                unresolved.append(C.unresolved_item(name, None, f"holds DDL and cannot be imported ({exc})"))
                continue
        for const in constants:
            statements = statements_of(getattr(module, const, None))
            if statements is None:
                unresolved.append(C.unresolved_item(name, const, "holds DDL in a value that is not a string or a "
                                                    "sequence of strings"))
                continue
            rows, error = read_back(statements)
            if error:
                unresolved.append(C.unresolved_item(name, const, f"its DDL did not run in memory ({error})"))
                continue
            found_here = True
            tables += [Table(name, const, n, kind, "store", cols, idx) for n, kind, cols, idx in rows]
        for symbol, node in sites:
            text = render(node, module)
            if text is None:
                unresolved.append(C.unresolved_item(name, symbol,
                                                    "builds DDL from a value this reading cannot resolve"))
                continue
            rows, error = read_back([text])
            if error:
                unresolved.append(C.unresolved_item(name, symbol, f"its DDL did not run in memory ({error})"))
                continue
            found_here = True
            tables += [Table(name, symbol, n, kind, "transient", cols, idx) for n, kind, cols, idx in rows]
        if not found_here and imports_sqlite(ctx.index(name)):
            unresolved.append(C.unresolved_item(name, None, "imports sqlite3 and holds no DDL: it opens a database "
                                                "another module creates"))
    return sorted(tables, key=lambda t: (t.module, t.name, t.symbol)), unresolved


def build(ctx: C.Context) -> list[C.Record]:
    tables, unresolved = tables_of(ctx)
    records = []
    for t in tables:
        registry = f"{t.module}:{t.symbol}"
        fact = {"module": t.module, "table": t.name, "kind": t.kind, "scope": t.scope, "columns": t.columns,
                "indexes": t.indexes}
        read = C.complete(registry, TESTS)
        records.append(C.Record(FAMILY, f"{t.module}:{t.name}", t.module, t.symbol, "observed",
                                C.lower_bound(unresolved), fact, fact_coverage={"columns": read, "indexes": read}))
    return records
