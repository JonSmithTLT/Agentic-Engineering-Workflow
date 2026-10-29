"""No test deletes one of a module's own table entries in place (nightly 2026-10-26..28; PR 215 before it).

``monkeypatch.delitem(module.TABLE, key)`` is undone by ``TABLE[key] = value``, which puts the key back at the table's
END: for the rest of that pytest process the table iterates in another order than in a fresh one. The escalation
test's plant on ``transitions.RULES`` reordered the Lead guide's moves for every later test in its process, and the
OpenCode Lead tests, which compare an in-process guide with a fresh `aew`'s, failed whenever a shard or an xdist worker
ran them after it; PR 215's deleted ``contract.TOOLS`` key broke test_surface_mcp the same way. A plant that removes an
entry swaps in a copy without it (``monkeypatch.setattr(module, "TABLE", {...})``, where the code reads the table
through its module) or goes through test_surface_map's ``Ablator``, which restores a table in its order. Deleting a key
the test planted itself is no such plant: undoing both leaves the table as it was.

What this sees: a call ``<m>.delitem(<module>.<NAME>, <key>)``, ``<m>`` being the ``monkeypatch`` fixture or a name
bound by ``with pytest.MonkeyPatch.context() as <m>`` or ``<m> = pytest.MonkeyPatch()``, ``<module>`` a name the file
binds to a module by an import, and ``<key>`` in the live table (or not a literal, so not shown to be the test's own).
What it misses: a table reached another way (an alias, a function's return, an instance's table, which dies with the
test), a ``del``, ``pop`` or ``clear`` written out, and a MonkeyPatch bound or passed under another spelling; each is a
defect the reviewer reads for.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parents[1]


def _modules(tree: ast.Module) -> dict[str, str]:
    """Each name the file binds by an import, and the dotted name it was imported as."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def _patchers(tree: ast.Module) -> set[str]:
    """The names a MonkeyPatch is bound to: the fixture, a context's target, an instance assigned."""
    out = {"monkeypatch"}
    for node in ast.walk(tree):
        if isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name) \
                and "MonkeyPatch" in ast.unparse(node.context_expr):
            out.add(node.optional_vars.id)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and ast.unparse(node.value.func).endswith("MonkeyPatch"):
            out.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return out


def _table(expr: ast.expr, modules: dict[str, str]) -> tuple[str, Any] | None:
    """``(module.NAME, the live table)`` when ``expr`` is a table of a module the file imported, else None."""
    if not isinstance(expr, ast.Attribute):
        return None
    dotted = ast.unparse(expr.value).split(".")
    if dotted[0] not in modules:
        return None
    try:
        module = importlib.import_module(".".join([modules[dotted[0]], *dotted[1:]]))
    except ImportError:
        return None  # an attribute of a module, not a module: not a table this sees
    table = getattr(module, expr.attr, None)
    return (f"{module.__name__}.{expr.attr}", table) if isinstance(table, Mapping) else None


def in_place_deletions(source: str) -> list[tuple[int, str]]:
    """(line, the table) of each deletion of a module table's own entry, in place, through a MonkeyPatch."""
    tree = ast.parse(source)
    modules, patchers = _modules(tree), _patchers(tree)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "delitem"
                and isinstance(node.func.value, ast.Name) and node.func.value.id in patchers and len(node.args) >= 2):
            continue
        hit = _table(node.args[0], modules)
        if hit is None:
            continue
        try:
            key = ast.literal_eval(node.args[1])
        except ValueError:
            found.append((node.lineno, hit[0]))  # not shown to be a key the test planted
            continue
        if key in hit[1]:
            found.append((node.lineno, hit[0]))
    return sorted(found)


def test_no_test_deletes_a_module_tables_own_entry_in_place():
    found = [f"{p.relative_to(TESTS).as_posix()}:{line}: {table}" for p in sorted(TESTS.rglob("*.py"))
             for line, table in in_place_deletions(p.read_text(encoding="utf-8"))]
    assert not found, ("these delete an entry of a live module table, and monkeypatch puts it back at the table's end; "
                       "swap in a copy without it (monkeypatch.setattr) instead:\n" + "\n".join(found))


PLANTED = '''
import pytest
from aew.engine import transitions as T
import aew.surface.stage as stage
from aew.surface import contract

def test_planted(monkeypatch, engine, key):
    monkeypatch.delitem(T.RULES, ("RUNNING", "REVIEW_PENDING"))              # 8: the nightly's plant
    monkeypatch.delitem(stage.STEP_RUNNERS, "checkpoint")                   # 9: an authored key
    monkeypatch.delitem(contract.TOOLS, key)                                # 10: a key not shown to be planted
    with pytest.MonkeyPatch.context() as mp:
        mp.delitem(stage.STAGES, "ticket_draft")                            # 12: through a context
    m = pytest.MonkeyPatch()
    m.delitem(T.RULES, ("READY", "ASSIGNED"))                               # 14: through an instance
    monkeypatch.setitem(stage.STAGES, "probe", lambda a: [])
    monkeypatch.delitem(stage.STAGES, "probe")                              # the test's own key
    monkeypatch.setattr(T, "RULES", {e: r for e, r in T.RULES.items() if e != ("READY", "ASSIGNED")})
    monkeypatch.delitem(engine._units.guards._queries, ("q", "k"))           # an instance's table
    ab.delitem(T.RULES, ("READY", "ASSIGNED"))                              # the Ablator restores in order
'''


def test_the_scan_sees_each_spelling_it_claims_and_passes_the_safe_ones():
    assert in_place_deletions(PLANTED) == [
        (8, "aew.engine.transitions.RULES"), (9, "aew.surface.stage.STEP_RUNNERS"),
        (10, "aew.surface.contract.TOOLS"), (12, "aew.surface.stage.STAGES"), (14, "aew.engine.transitions.RULES")]
