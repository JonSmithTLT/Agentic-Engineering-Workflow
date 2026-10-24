"""Which entry points can reach a writer: a static call graph from where each entry point declares itself (STG-12
S12-2, DOC-01's "that writer's entry-point kind").

Roots are derived, not restated: an entry point's root is the function that declares it
(``entry_points.declare_sites_from``, the reading the ``entry-points`` family already makes), so a table row with no
root is a gap there and not a guess here. An edge is

* a call that resolves to an AEW function (by import source, ``self`` through the class and its bases, a class to its
  ``__init__``, ``super()``, a method of a receiver whose class is evident);
* a call of a function defined inside the calling function (or one that encloses it) by its name;
* the CLI's dispatch: ``parser.set_defaults(handler=<function>)`` registers a command's handler, and the CLI function
  that declares its roles with ``cli_entry_point`` calls whichever the arguments select, so each registered handler is
  reachable from it.

A name that is not called is not an edge (``Engine.__init__`` names the collaborators it wires and defines callbacks it
hands over, and following those would make every entry point that builds an engine reach everything). So a chain here
is a chain of calls, and the list of entry points is a lower bound: a callback or a registry entry other than the
CLI's is not followed. What it cannot follow is a call on an object whose class is not evident (not ``self``, an
annotated parameter, a constructed local, or a function whose returns build one class), a function called through a
name this reading cannot resolve, and a call made by another process (a subprocess runs the entry point it names: the
entry-points family lists those starts). The CLI's four roles share one root, so a writer reached from it is reached
from all four; which role runs it is decided by the process's arguments and environment, and this reading does not
decide it.
"""

from __future__ import annotations

import ast
from collections import defaultdict

from reference_families import common as C
from reference_families import entry_points as E
from reference_families import writers_flow as F

Key = tuple[str, str]


def roots_of(ctx: C.Context, table_keys: set[str]) -> dict[Key, set[str]]:
    """Root function (module, symbol) -> the entry-point keys it declares. A declaration through ``cli_entry_point`` is
    every key ``cli_entry_point`` can give, which the ``entry-points`` family reads from the owner."""
    from aew import process_kind  # the owner at run time, as the entry-points family does

    cli = E.cli_roles(ctx, dict(process_kind.ENTRY_POINTS))
    roots: dict[Key, set[str]] = defaultdict(set)
    for name in ctx.sources():
        if ctx.sources()[name].tree is None:
            continue
        for d in E.declare_sites_from(ctx.index(name), name):
            if d.symbol is None:
                continue
            if d.via == "literal" and d.entry_point in table_keys:
                roots[(d.module, d.symbol)].add(d.entry_point)
            elif d.via == "cli_entry_point":
                roots[(d.module, d.symbol)] |= cli
    return dict(roots)


def _handlers(program: F.Program) -> set[Key]:
    """Every function registered with ``set_defaults(handler=...)``: a name, an attribute, or the functions a lambda
    names."""
    found: set[Key] = set()
    for mod in program.modules.values():
        calls = [(None, c) for c in mod.module_calls] + [(f, c) for f in mod.funcs.values() for c in f.calls]
        for func, call in calls:
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "set_defaults"):
                continue
            for kw in call.keywords:
                if kw.arg != "handler":
                    continue
                for node in ast.walk(kw.value):
                    if isinstance(node, (ast.Name, ast.Attribute)):
                        target = program.target(mod, func, node)
                        if target is not None:
                            found.add(target.key)
    return found


def graph(program: F.Program, dispatchers: set[Key]) -> dict[Key, set[Key]]:
    edges: dict[Key, set[Key]] = defaultdict(set)
    for callee, sites in program.callers.items():
        for caller, _mod, _call in sites:
            if caller is not None:
                edges[caller.key].add(callee)
    handlers = _handlers(program)
    for d in dispatchers:
        edges[d] |= handlers
    return edges


def reach(edges: dict[Key, set[Key]], start: Key) -> set[Key]:
    seen: set[Key] = set()
    stack = [start]
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        stack.extend(edges.get(k, ()))
    return seen


def reached_from(program: F.Program, roots: dict[Key, set[str]], dispatchers: set[Key]) -> dict[Key, set[str]]:
    """Function -> the entry-point keys whose root statically reaches it (only functions some root reaches)."""
    edges = graph(program, dispatchers)
    out: dict[Key, set[str]] = defaultdict(set)
    for root, keys in roots.items():
        for k in reach(edges, root):
            out[k] |= keys
    return dict(out)


def dispatchers_of(ctx: C.Context) -> set[Key]:
    """The functions that declare the CLI's roles: where the CLI's registered handlers are called from."""
    out: set[Key] = set()
    for name in ctx.sources():
        if ctx.sources()[name].tree is None:
            continue
        for d in E.declare_sites_from(ctx.index(name), name):
            if d.via == "cli_entry_point" and d.symbol:
                out.add((d.module, d.symbol))
    return out
