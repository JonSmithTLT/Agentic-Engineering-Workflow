"""The ``modules`` family: one record per module under ``src/aew``, with the AEW modules it imports (STG-12 S12-2).

Owner: the source tree. The accessor is :func:`scan`, which reads every file under ``src/aew`` with ``ast``; nothing is
imported, so the graph is static and the label is ``lower-bound``. An import is resolved to the AEW module it names
(``from aew.engine import store`` is an edge to ``aew.engine.store`` when that module exists, else to the package), in
whatever scope it sits. What cannot be resolved is listed, by module and symbol, never guessed: a call that imports
by a computed name (``importlib.import_module``, ``__import__``) or loads code by file path, which is a dynamic import
this graph cannot follow.

The trace follows ``imports`` from the module of every record (addendum 1), so every family's anchors need a record
here; ``tools/reference.py`` refuses an index with an anchor that has none.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from reference_families import common as C

FAMILY = C.MODULES
PACKAGE = C.PACKAGE

# Calls that import by a name or a path the graph cannot read statically, by where the callee was imported from.
DYNAMIC_BY_NAME = ("importlib.import_module", "__import__", "importlib.__import__")
DYNAMIC_BY_PATH = ("importlib.util.spec_from_file_location", "runpy.run_module", "runpy.run_path")


@dataclass(frozen=True)
class Module:
    name: str
    path: str  # POSIX, relative to the repository root
    is_package: bool
    imports: tuple[str, ...]
    unresolved: tuple[dict[str, Any], ...]


def _is_aew(name: str) -> bool:
    return name == PACKAGE or name.startswith(PACKAGE + ".")


def _longest_known(dotted_name: str, known: frozenset[str]) -> str:
    parts = dotted_name.split(".")
    while parts and ".".join(parts) not in known:
        parts.pop()
    return ".".join(parts)


def edges_from(index: C.Index, module: str, is_package: bool, known: frozenset[str]
               ) -> tuple[set[str], list[dict[str, Any]]]:
    """(the AEW modules a module imports, the dynamic imports it makes that this reading cannot resolve)."""
    edges: set[str] = set()
    for node in index.imports:
        if isinstance(node, ast.Import):
            edges.update(_longest_known(a.name, known) for a in node.names if _is_aew(a.name))
            continue
        base = C.absolute_base(node, module, is_package)
        if base is None or not _is_aew(base):
            continue
        for a in node.names:
            if a.name != "*" and f"{base}.{a.name}" in known:
                edges.add(f"{base}.{a.name}")
            else:
                edges.add(_longest_known(base, known))
    unresolved = []
    for call, symbol in index.calls:
        callee = index.aliases.resolve(call.func)
        if callee in DYNAMIC_BY_NAME:
            arg = call.args[0] if call.args else None
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if _is_aew(arg.value) and _longest_known(arg.value, known) == arg.value:
                    edges.add(arg.value)  # a constant AEW module name is read like an import
                elif _is_aew(arg.value) or arg.value.startswith("."):
                    unresolved.append(C.unresolved_item(module, symbol,
                                                        f"{callee} of a name this graph cannot resolve"))
                # a constant name outside AEW is not an edge of this graph
            else:
                unresolved.append(C.unresolved_item(module, symbol, f"{callee} with a computed module name"))
        elif callee in DYNAMIC_BY_PATH:
            unresolved.append(C.unresolved_item(module, symbol, f"{callee} loads code by file path or name"))
    edges.discard(module)
    return {e for e in edges if e in known}, unresolved


def edges_of(tree: ast.Module, module: str, is_package: bool, known: frozenset[str]
             ) -> tuple[set[str], list[dict[str, Any]]]:
    """:func:`edges_from` for a parsed tree on its own (the planted cases of the tests)."""
    return edges_from(C.index_of(tree, module, is_package), module, is_package, known)


def scan(ctx: C.Context) -> list[Module]:
    sources = ctx.sources()
    known = frozenset(sources)
    out = []
    for name, src in sources.items():
        if src.tree is None:
            # Unreadable input is a marked value, never "no imports": the module is listed and so is why.
            edges, unresolved = set(), [C.unresolved_item(name, None, f"the module does not parse: {src.error}")]
        else:
            edges, unresolved = edges_from(ctx.index(name), name, src.is_package, known)
        out.append(Module(name, src.path.relative_to(ctx.root).as_posix(), src.is_package, tuple(sorted(edges)),
                          tuple(unresolved)))
    return out


def build(ctx: C.Context) -> C.Built:
    mods = scan(ctx)
    records = [C.Record(FAMILY, m.name, m.name, None, "static", C.lower_bound(m.unresolved),
                        {"path": m.path, "package": m.is_package}, list(m.imports)) for m in mods]
    return C.Built(records=records, pages={})
