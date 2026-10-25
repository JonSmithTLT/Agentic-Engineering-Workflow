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


PAGE = "modules.md"
TOP = PACKAGE  # the group of the package's own modules that sit directly under it, and of the package itself


def group_of(name: str, packages: frozenset[str]) -> str:
    """The package a module is listed under: its second-level package (``aew.engine`` for ``aew.engine.store``), else
    the top (a module that sits directly under it, or the top itself)."""
    second = ".".join(name.split(".")[:2])
    return second if second in packages else TOP


def _names(names: list[str]) -> str:
    return ", ".join(f"`{n}`" for n in names) or "-"


def page(mods: list[Module]) -> str:
    """The human page of the family, drawn from the modules alone: the import graph by package, each module's imports
    and importers (the inverse of its ``imports``), and the dynamic imports the graph cannot follow."""
    packages = frozenset(m.name for m in mods if m.is_package)
    importers: dict[str, list[str]] = {m.name: [] for m in mods}
    for m in mods:
        for target in m.imports:
            importers[target].append(m.name)
    groups: dict[str, list[Module]] = {}
    for m in sorted(mods, key=lambda m: m.name):
        groups.setdefault(group_of(m.name, packages), []).append(m)
    group_of_name = {m.name: g for g, members in groups.items() for m in members}
    toward: dict[str, set[str]] = {g: set() for g in groups}  # package -> the other packages it imports from
    away: dict[str, set[str]] = {g: set() for g in groups}  # package -> the other packages that import from it
    for m in mods:
        for target in m.imports:
            if group_of_name[m.name] != group_of_name[target]:
                toward[group_of_name[m.name]].add(group_of_name[target])
                away[group_of_name[target]].add(group_of_name[m.name])
    edges = sum(len(m.imports) for m in mods)
    lines = [
        "# Modules", "",
        "The import graph of `src/aew`, from the source alone: one record per module (`modules:<module>`), whose "
        "`imports` are the AEW modules it imports, in whatever scope the import sits. Generated by `python "
        "tools/reference.py render`; do not edit. Nothing is imported to read it, so the graph is static and every "
        "record is **lower-bound**: a call that imports by a computed name, or loads code by file path, is a dynamic "
        "import this graph cannot follow, and is listed at the end (also in [gaps.md](gaps.md)). `from aew.engine "
        "import store` is an edge to `aew.engine.store` when that module exists, else to the package. **Imported "
        "by** is the inverse of **Imports**, computed from the same records.", "",
        f"{len(mods)} modules in {len(groups)} groups, {edges} import edges.", "",
        "## Packages", "",
        "A group is a second-level package, or `aew` for the top and the modules directly under it. The columns are "
        "the other groups it imports from and the other groups that import from it.", "",
        "| Group | Modules | Imports from | Imported by |", "|---|---|---|---|"]
    for g, members in groups.items():
        lines.append(f"| `{g}` | {len(members)} | {_names(sorted(toward[g]))} | {_names(sorted(away[g]))} |")
    lines.append("")
    for g, members in groups.items():
        lines += [f"## `{g}` ({len(members)})", "", "| Module | Imports | Imported by |", "|---|---|---|"]
        lines += [f"| `{m.name}` | {_names(list(m.imports))} | {_names(sorted(importers[m.name]))} |" for m in members]
        lines.append("")
    dynamic = sorted((u["module"], u["symbol"] or "", u["why"]) for m in mods for u in m.unresolved)
    lines += ["## Dynamic imports this graph cannot follow", ""]
    lines += [f"- `{mod}:{sym}`: {why}" if sym else f"- `{mod}`: {why}" for mod, sym, why in dynamic] or ["None."]
    return "\n".join(lines).rstrip("\n") + "\n"


def build(ctx: C.Context) -> C.Built:
    mods = scan(ctx)
    records = [C.Record(FAMILY, m.name, m.name, None, "static", C.lower_bound(m.unresolved),
                        {"path": m.path, "package": m.is_package}, list(m.imports)) for m in mods]
    return C.Built(records=records, pages={PAGE: page(mods)})
