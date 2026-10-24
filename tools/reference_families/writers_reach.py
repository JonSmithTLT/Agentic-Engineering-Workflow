"""Which entry points can reach a writer: a static call graph from where each entry point declares itself (STG-12
S12-2, DOC-01's "that writer's entry-point kind").

Roots are derived, not restated: an entry point's root is the function that declares it
(``entry_points.declare_sites_from``, the reading the ``entry-points`` family already makes), so a table row with no
root is a gap there and not a guess here. An edge is

* a call that resolves to an AEW function (by import source, ``self`` through the class and its bases, a class to its
  ``__init__``, ``super()``, a method of a receiver whose class is evident);
* a call of a function defined inside the calling function (or one that encloses it) by its name.

A name that is not called is not an edge (``Engine.__init__`` names the collaborators it wires and defines callbacks it
hands over, and following those would make every entry point that builds an engine reach everything). So a chain here
is a chain of calls, and the list of entry points is a lower bound: a callback or a registry entry is not followed. What
it cannot follow is a call on an object whose class is not evident (not ``self``, an annotated parameter, a constructed
local, or a function whose returns build one class), a function called through a name this reading cannot resolve, and
a call made by another process (a subprocess runs the entry point it names: the entry-points family lists those
starts).

The CLI's one declaring function declares four roles, and the command decides which runs. Its own calls (the parser's
construction, the common path every command shares) are reached by all four. The handler each command registers
(``set_defaults(handler=...)``) is called through ``args.handler``, which no call names, so ``writers_roles`` cuts the
roles by the parser: a handler is reached by the role of its command, and only by that role. The role the environment
selects (``aew (worker run)``) is selected by no command, so the call graph attributes no handler to it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import NamedTuple

from reference_families import common as C
from reference_families import entry_points as E
from reference_families import writers_flow as F
from reference_families import writers_roles as W

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


def graph(program: F.Program) -> dict[Key, set[Key]]:
    edges: dict[Key, set[Key]] = defaultdict(set)
    for callee, sites in program.callers.items():
        for caller, _mod, _call in sites:
            if caller is not None:
                edges[caller.key].add(callee)
    return edges


def reach(edges: dict[Key, set[Key]], starts: Iterable[Key]) -> set[Key]:
    seen: set[Key] = set()
    stack = list(starts)
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        stack.extend(edges.get(k, ()))
    return seen


class Reach(NamedTuple):
    entry_points: dict[Key, set[str]]  # function -> the entry-point keys whose root reaches it
    undecided: dict[Key, set[Key]]  # function -> the registrars of the unread commands' handlers that reach it


def reached_from(program: F.Program, roots: dict[Key, set[str]], cli_roots: set[Key], cut: W.Cut) -> Reach:
    """Function -> the entry-point keys whose root statically reaches it (only functions some root reaches). At a
    CLI root, the common path is reached by every key the root declares, and a command's handlers by the role of the
    command only; a handler of a command this reading cannot read is reached by every key the root declares (fail
    closed), and its registering function is named."""
    edges = graph(program)
    out: dict[Key, set[str]] = defaultdict(set)
    undecided: dict[Key, set[Key]] = defaultdict(set)
    for root, keys in roots.items():
        for k in reach(edges, [root]):
            out[k] |= keys
        if root not in cli_roots:
            continue
        for role, handlers in cut.handlers.items():
            if role in keys:
                for k in reach(edges, handlers):
                    out[k].add(role)
        for registrar, handlers in cut.undecided.items():
            for k in reach(edges, handlers):
                out[k] |= keys
                undecided[k].add(registrar)
    return Reach(dict(out), dict(undecided))


def cli_roots_of(ctx: C.Context) -> set[Key]:
    """The functions that declare the CLI's roles (through ``cli_entry_point``)."""
    out: set[Key] = set()
    for name in ctx.sources():
        if ctx.sources()[name].tree is None:
            continue
        for d in E.declare_sites_from(ctx.index(name), name):
            if d.via == "cli_entry_point" and d.symbol:
                out.add((d.module, d.symbol))
    return out


def cli_of(ctx: C.Context, program: F.Program) -> tuple[set[Key], W.Roles, W.Cut]:
    """What cuts the CLI's roles, from the owner (``process_kind``) at run time: the functions that declare them, the
    roles, and the handlers of each role's commands."""
    from aew import process_kind

    table = dict(process_kind.ENTRY_POINTS)
    roles = W.roles_of(E.cli_roles(ctx, table), process_kind.cli_entry_point, process_kind.AGENT_ENDPOINT_ENV)
    cut = W.cut_of(program, lambda path: process_kind.cli_entry_point(list(path), {}))
    return cli_roots_of(ctx), roles, cut
