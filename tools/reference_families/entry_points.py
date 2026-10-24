"""The ``entry-points`` family (DOC-02): every AEW process entry point, its kind, where it declares itself, and every
product site that starts it (STG-12 S12-2).

Owner: ``aew.process_kind.ENTRY_POINTS``, imported at run time (basis ``enumerated``). One record per key. The record's
anchor is the place the process declares itself (``process_kind.declare`` or ``declared_as``), found by reading the
source: a call is identified by where its callee was imported from, not by its name. The CLI plays four roles and
declares whichever ``cli_entry_point`` gives, so those four share one anchor, ``aew.cli.main:_main``.

Coverage is complete-by-construction: the table is the registry, the records are generated from it, and what stops code
bypassing it is the existing table test (every module that runs as a process is a row, and every row is one) with the
two tests of this family, which read the source by two independent detectors (``entry_points_text.py`` is the second):

* every ``python -m aew...`` spawn site in the product names a listed entry point (D-CS1-12);
* every row declares itself at a site, and every site declares a row.

``spawn_sites`` are the ``-m`` forms only. The console script ``aew`` run from a ``PATH`` the product builds, and an
argv that starts with ``aew``, are not ``-m`` forms and no detector here sees them: each is listed in ``gaps.md`` by
anchor, as the sites that start the CLI in a way this reading cannot follow. A shell string (``"python -m aew..."``)
is not seen either, and an argv that builds its module name is reported as unreadable; both are pinned by probes.
"""

from __future__ import annotations

import ast
from typing import Any, NamedTuple

from reference_families import common as C

FAMILY = "entry-points"
REGISTRY = "aew.process_kind:ENTRY_POINTS"
PROCESS_KIND = "aew.process_kind"
CHECKS = (
    "tests/integration/test_non_writer_reads.py::"
    "test_every_module_that_runs_as_a_process_is_in_the_entry_point_table_and_every_row_is_one",
    "tests/integration/test_reference_entry_points.py::test_every_python_dash_m_aew_spawn_site_names_a_listed_entry_point",
    "tests/integration/test_reference_entry_points.py::test_every_entry_point_declares_itself_and_every_declaration_is_one",
)
# `python -m aew` runs `aew/__main__.py`, which calls the CLI's `main`; `python -m aew.__main__` is the same module.
CLI_ENTRY = "aew"
CLI_MODULES = frozenset({"aew", "aew.__main__"})


class DeclareSite(NamedTuple):
    module: str
    symbol: str | None
    entry_point: str | None  # the literal name; None for `via` cli_entry_point or an unreadable argument
    via: str  # "literal", "cli_entry_point" or "unreadable"


class SpawnSite(NamedTuple):
    module: str
    symbol: str | None
    target: str | None  # the `-m` module; None when it is not a plain string in an argv that runs this interpreter


def declare_sites_from(index: C.Index, module: str) -> list[DeclareSite]:
    """Where a module declares which entry point its process is. ``aew.process_kind`` defines the calls; it declares
    nothing itself."""
    if module == PROCESS_KIND:
        return []
    sites = []
    for call, symbol in index.calls:
        if index.aliases.resolve(call.func) not in (f"{PROCESS_KIND}.declare", f"{PROCESS_KIND}.declared_as"):
            continue
        arg = call.args[0] if call.args else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            sites.append(DeclareSite(module, symbol, arg.value, "literal"))
        elif isinstance(arg, ast.Call) and index.aliases.resolve(arg.func) == f"{PROCESS_KIND}.cli_entry_point":
            sites.append(DeclareSite(module, symbol, None, "cli_entry_point"))
        else:
            sites.append(DeclareSite(module, symbol, None, "unreadable"))
    return sites


def spawn_sites_from(index: C.Index, module: str) -> list[SpawnSite]:
    """Every ``[..., "-m", "aew...", ...]`` argv in a module: where it starts one of AEW's entry points. A list or a
    tuple whose ``-m`` is followed by something that is not a plain string, in an argv that runs this interpreter, is a
    site with an unreadable module name (``target`` None): reported, never passed over."""
    sites = []
    for node, symbol in index.seqs:
        elts = node.elts
        runs_this_python = any(index.aliases.resolve(e) == "sys.executable" for e in elts)
        for a, b in zip(elts, elts[1:], strict=False):
            if not (isinstance(a, ast.Constant) and a.value == "-m"):
                continue
            if isinstance(b, ast.Constant) and isinstance(b.value, str):
                if b.value == C.PACKAGE or b.value.startswith(C.PACKAGE + "."):
                    sites.append(SpawnSite(module, symbol, b.value))
            elif runs_this_python:
                sites.append(SpawnSite(module, symbol, None))
    return sites


def console_script_sites_from(index: C.Index) -> list[tuple[str | None, str]]:
    """Where the CLI is started by its console script, which is not a ``-m`` form (listed in ``gaps.md``): the
    interpreter's own directory put on a child's PATH, which is how a harness run finds ``aew``, and an argv list that
    starts with ``aew`` (a list: ``("aew", "aew.exe")`` is a pair of names)."""
    found = []
    for call, symbol in index.calls:
        if (index.aliases.resolve(call.func) == "os.path.dirname" and call.args
                and index.aliases.resolve(call.args[0]) == "sys.executable"):
            found.append((symbol, "the interpreter's directory, put on a child's PATH so it can run the console "
                                  "script `aew`"))
    for node, symbol in index.seqs:
        first = node.elts[0] if node.elts else None
        if (isinstance(node, ast.List) and len(node.elts) >= 2 and isinstance(first, ast.Constant)
                and first.value == "aew"):
            found.append((symbol, "an argv list that starts with the console script `aew` (whether it is run as a "
                                  "process is not decided here)"))
    return found


def declare_sites(tree: ast.Module, module: str, is_package: bool) -> list[DeclareSite]:
    """:func:`declare_sites_from` for a parsed tree on its own (the planted cases of the tests)."""
    return declare_sites_from(C.index_of(tree, module, is_package), module)


def spawn_sites(tree: ast.Module, module: str, is_package: bool) -> list[SpawnSite]:
    return spawn_sites_from(C.index_of(tree, module, is_package), module)


def console_script_sites(tree: ast.Module, module: str, is_package: bool) -> list[tuple[str | None, str]]:
    return console_script_sites_from(C.index_of(tree, module, is_package))


def cli_roles(ctx: C.Context, table: dict[str, tuple[str, str]]) -> set[str]:
    """The rows ``cli_entry_point`` can give: the string literals of its body that are keys of the table."""
    src = ctx.sources().get(PROCESS_KIND)
    if src is None or src.tree is None:
        raise C.ReferenceError(f"{PROCESS_KIND} cannot be read")
    for node in ast.walk(src.tree):
        if isinstance(node, ast.FunctionDef) and node.name == "cli_entry_point":
            body = node.body[1:] if node.body and isinstance(node.body[0], ast.Expr) else node.body
            return {c.value for stmt in body for c in ast.walk(stmt)
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value in table}
    raise C.ReferenceError("aew.process_kind.cli_entry_point is not defined")


def entry_for(target: str) -> str:
    """The row a ``-m`` module starts: the CLI for ``aew`` itself, else the module's own dotted name."""
    return CLI_ENTRY if target in CLI_MODULES else target


def build(ctx: C.Context) -> C.Built:
    from aew import process_kind  # the owner, at run time (reference.py has checked it is this tree's)

    table: dict[str, tuple[str, str]] = dict(process_kind.ENTRY_POINTS)
    roles = cli_roles(ctx, table)
    declares: list[DeclareSite] = []
    spawns: list[SpawnSite] = []
    gaps: list[C.Gap] = []
    for name, src in ctx.sources().items():
        if src.tree is None:
            continue  # the modules family lists it as unreadable
        index = ctx.index(name)
        declares += declare_sites_from(index, name)
        spawns += spawn_sites_from(index, name)
        gaps += [C.Gap(FAMILY, name, symbol, f"{why}: not a `python -m` form, so no spawn site is recorded for it")
                 for symbol, why in console_script_sites_from(index)]
    for site in declares:
        if site.via == "unreadable" or (site.via == "literal" and site.entry_point not in table):
            gaps.append(C.Gap(FAMILY, site.module, site.symbol,
                              "a process declaration whose entry point cannot be read or is not in the table"))
    by_entry: dict[str, list[SpawnSite]] = {key: [] for key in table}
    for s in spawns:
        if s.target is None:
            gaps.append(C.Gap(FAMILY, s.module, s.symbol, "a `-m` spawn whose module name is not a plain string"))
        elif entry_for(s.target) not in table:
            gaps.append(C.Gap(FAMILY, s.module, s.symbol, f"a `-m {s.target}` spawn that names no listed entry point"))
        else:
            by_entry[entry_for(s.target)].append(s)

    records = []
    for key, (kind, reason) in sorted(table.items()):
        where = sorted({(d.module, d.symbol or "", d.via) for d in declares
                        if (d.via == "literal" and d.entry_point == key)
                        or (d.via == "cli_entry_point" and key in roles)})
        if not where:
            gaps.append(C.Gap(FAMILY, PROCESS_KIND, "ENTRY_POINTS",
                              f"{key} is in the table but nothing declares itself as it"))
        anchor_module, anchor_symbol = (where[0][0], where[0][1]) if where else (PROCESS_KIND, "ENTRY_POINTS")
        fact: dict[str, Any] = {
            "entry_point": key, "kind": kind, "reason": reason,
            "declared_at": [{"module": m, "symbol": s or None, "via": v} for m, s, v in where],
            "spawn_sites": [{"module": s.module, "symbol": s.symbol}
                            for s in sorted(by_entry[key], key=lambda s: (s.module, s.symbol or ""))],
        }
        records.append(C.Record(FAMILY, key, anchor_module, anchor_symbol, "enumerated",
                                C.complete(REGISTRY, CHECKS), fact))
    return C.Built(records=records, gaps=gaps, pages={"entry-points.md": page(records)})


def page(records: list[C.Record]) -> str:
    lines = ["# Entry points", "",
             "Every AEW process entry point, from `aew.process_kind.ENTRY_POINTS`: its kind, where it declares itself, "
             "and the product sites that start it with `python -m`. Generated by `python tools/reference.py render`; "
             "do not edit. A **store writer** takes the engine's control lock; a **non-writer** reads lock-free only "
             "and is refused a lock-taking operation before the lock opens. Coverage is complete-by-construction for "
             "the set of entry points: the table is the registry, and the tests named in `index.json` stop code "
             "bypassing it. `Started by` lists the `-m` forms only; the other ways the CLI is started are in "
             "[gaps.md](gaps.md).", ""]
    for r in sorted(records, key=lambda r: r.key):
        fact = r.fact or {}
        declared = ", ".join(f"`{d['module']}:{d['symbol']}`" if d["symbol"] else f"`{d['module']}`"
                             for d in fact["declared_at"]) or "nowhere (a gap)"
        started = ", ".join(f"`{s['module']}:{s['symbol']}`" if s["symbol"] else f"`{s['module']}`"
                            for s in fact["spawn_sites"]) or "no `python -m` site in the product"
        lines += [f"### `{r.key}`", "", f"- **Kind:** {fact['kind']}", f"- **Why:** {fact['reason']}",
                  f"- **Declares itself at:** {declared}", f"- **Started by:** {started}", ""]
    return "\n".join(lines).rstrip("\n") + "\n"
