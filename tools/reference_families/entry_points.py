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

The two list facts of a record, ``declared_at`` and ``starts``, are what detectors found, so each carries its own
coverage in the record's ``fact_coverage``, beside ``coverage`` (lower-bound, with what it could not resolve; the
designer's addendum 3). ``starts``
is one list of every place the product starts the entry point, each item with its ``form`` and ``attribution``:

* ``-m``: a ``python -m aew...`` spawn, attributed by the module it names;
* ``console-script-argv``: an argv list that starts with ``aew``, attributed by the owner's own ``cli_entry_point``
  applied to its words; whether it is run is not decided here, so it is also an unresolved item of the list;
* ``console-script-on-PATH``: the interpreter's directory put on a child's ``PATH``, which makes the CLI startable and
  starts none, so it is listed on every role of the CLI, unattributed.

A ``-m`` whose module name is not a plain string is a site with an unreadable name, reported and never passed over (in a
list or tuple always; in a call's arguments when the call also passes ``sys.executable``, since git's own ``-m`` is
passed as a call argument). What no reading here sees (a shell string, an argv built by ``append``, ``-c`` payloads, an
interpreter named without ``sys.executable``) is pinned by probes, one each, in
``tests/integration/test_reference_entry_points.py``.
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
    """Where a module declares which entry point its process is. Inside ``aew.process_kind``, which defines the calls,
    a bare ``declare(...)`` is the module's own, and only a literal counts: ``declared_as`` forwards its parameter to
    ``declare``, which is the machinery and not a declaration. A literal there is a declaration like any other (the
    forgotten-mask rule: the defining module is not exempt)."""
    own = module == PROCESS_KIND
    sites = []
    for call, symbol in index.calls:
        callee = index.aliases.resolve(call.func)
        if own and callee in ("declare", "declared_as"):
            callee = f"{PROCESS_KIND}.{callee}"
        if callee not in (f"{PROCESS_KIND}.declare", f"{PROCESS_KIND}.declared_as"):
            continue
        arg = call.args[0] if call.args else None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            sites.append(DeclareSite(module, symbol, arg.value, "literal"))
        elif own:
            continue
        elif isinstance(arg, ast.Call) and index.aliases.resolve(arg.func) == f"{PROCESS_KIND}.cli_entry_point":
            sites.append(DeclareSite(module, symbol, None, "cli_entry_point"))
        else:
            sites.append(DeclareSite(module, symbol, None, "unreadable"))
    return sites


def _is_dash_m(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "-m"


def _argv_sites(index: C.Index, module: str, symbol: str | None, elts: list[ast.expr], *, literal: bool
                ) -> list[SpawnSite]:
    """The ``-m`` sites in one run of elements: a list or tuple literal (``literal``), or a call's positional
    arguments. A ``-m`` before a module that is a plain string names an AEW module or does not. A ``-m`` before
    anything else is a site with an unreadable name (``target`` None), reported and never passed over: in a literal
    always (an argv list is an argv), in a call's arguments only when the call also passes ``sys.executable``, since
    git's own ``-m`` (a commit message) is passed that way. A literal that ends in ``-m`` takes its module later
    (``argv.append(name)``), so it is reported too."""
    runs_this_python = any(index.aliases.resolve(e) == "sys.executable" for e in elts)
    found = []
    for a, b in zip(elts, elts[1:], strict=False):
        if not _is_dash_m(a):
            continue
        if isinstance(b, ast.Constant) and isinstance(b.value, str):
            if b.value == C.PACKAGE or b.value.startswith(C.PACKAGE + "."):
                found.append(SpawnSite(module, symbol, b.value))
        elif literal or runs_this_python:
            found.append(SpawnSite(module, symbol, None))
    if literal and elts and _is_dash_m(elts[-1]):
        found.append(SpawnSite(module, symbol, None))
    return found


def spawn_sites_from(index: C.Index, module: str) -> list[SpawnSite]:
    """Every ``"-m", "aew..."`` in an argv list or tuple, or in the positional arguments of a call (``os.execl``): where
    a module starts one of AEW's entry points. See :func:`_argv_sites` for what is reported as unreadable."""
    sites = []
    for node, symbol in index.seqs:
        sites += _argv_sites(index, module, symbol, node.elts, literal=True)
    for call, symbol in index.calls:
        sites += _argv_sites(index, module, symbol, call.args, literal=False)
    return sites


DASH_M, PATH_FORM, ARGV_FORM = "-m", "console-script-on-PATH", "console-script-argv"
CONSOLE_WHY = {
    PATH_FORM: "puts the console script `aew` on a child's PATH (the interpreter's own directory), which makes an "
               "entry point startable and starts none",
    ARGV_FORM: "an argv list that starts with the console script `aew`; whether it is run as a process is not decided "
               "here",
}


class ConsoleStart(NamedTuple):
    symbol: str | None
    form: str  # PATH_FORM or ARGV_FORM
    words: tuple[str, ...]  # an argv list's string constants right after `aew` (empty for the PATH form)
    decided: bool  # an argv whose role its constants decide: two or more words, or an argv of constants only


def console_script_sites_from(index: C.Index) -> list[ConsoleStart]:
    """Where the product uses the CLI's console script, which is not a ``-m`` form. The interpreter's own directory put
    on a child's PATH is how a harness run finds ``aew``; an argv list that starts with ``aew`` is a list
    (``("aew", "aew.exe")`` is a pair of names). Each is an item of the CLI rows' ``starts``, with its form."""
    found = []
    for call, symbol in index.calls:
        if (index.aliases.resolve(call.func) == "os.path.dirname" and call.args
                and index.aliases.resolve(call.args[0]) == "sys.executable"):
            found.append(ConsoleStart(symbol, PATH_FORM, (), True))
    for node, symbol in index.seqs:
        first = node.elts[0] if node.elts else None
        if (isinstance(node, ast.List) and len(node.elts) >= 2 and isinstance(first, ast.Constant)
                and first.value == "aew"):
            words: list[str] = []
            for e in node.elts[1:]:
                if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
                    break
                words.append(e.value)
            found.append(ConsoleStart(symbol, ARGV_FORM, tuple(words),
                                      len(words) >= 2 or len(words) == len(node.elts) - 1))
    return found


def declare_sites(tree: ast.Module, module: str, is_package: bool) -> list[DeclareSite]:
    """:func:`declare_sites_from` for a parsed tree on its own (the planted cases of the tests)."""
    return declare_sites_from(C.index_of(tree, module, is_package), module)


def spawn_sites(tree: ast.Module, module: str, is_package: bool) -> list[SpawnSite]:
    return spawn_sites_from(C.index_of(tree, module, is_package), module)


def console_script_sites(tree: ast.Module, module: str, is_package: bool) -> list[ConsoleStart]:
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


def start_item(module: str, symbol: str | None, form: str, attribution: str) -> dict[str, Any]:
    """One start of an entry point. ``attribution`` is ``derived`` (from the module a ``-m`` names, or from
    ``cli_entry_point`` applied to an argv's words) or ``unattributed`` (a PATH that makes the CLI startable in any of
    its roles)."""
    return {"module": module, "symbol": symbol, "form": form, "attribution": attribution}


def build(ctx: C.Context) -> C.Built:
    from aew import process_kind  # the owner, at run time (reference.py has checked it is this tree's)

    table: dict[str, tuple[str, str]] = dict(process_kind.ENTRY_POINTS)
    roles = sorted(cli_roles(ctx, table))
    declares: list[DeclareSite] = []
    spawns: list[SpawnSite] = []
    consoles: list[tuple[str, ConsoleStart]] = []
    for name, src in ctx.sources().items():
        if src.tree is None:
            continue  # the modules family lists it as unreadable
        index = ctx.index(name)
        declares += declare_sites_from(index, name)
        spawns += spawn_sites_from(index, name)
        consoles += [(name, c) for c in console_script_sites_from(index)]

    # what could concern any entry point: a declaration or a `-m` this reading cannot attribute to a row
    anywhere_declared = [C.unresolved_item(d.module, d.symbol, "a process declaration whose entry point cannot be "
                                           "read or is not in the table")
                         for d in declares
                         if d.via == "unreadable" or (d.via == "literal" and d.entry_point not in table)]
    anywhere_started: list[dict[str, Any]] = []
    starts: dict[str, list[dict[str, Any]]] = {key: [] for key in table}
    started_unresolved: dict[str, list[dict[str, Any]]] = {key: [] for key in table}
    for s in spawns:
        if s.target is None:
            anywhere_started.append(C.unresolved_item(s.module, s.symbol, "a `-m` whose module name is not a plain "
                                                      "string"))
        elif entry_for(s.target) not in table:
            anywhere_started.append(C.unresolved_item(s.module, s.symbol, f"a `-m {s.target}` that names no listed "
                                                      "entry point"))
        else:
            starts[entry_for(s.target)].append(start_item(s.module, s.symbol, DASH_M, "derived"))
    for module, c in consoles:
        if c.form == PATH_FORM:
            for role in roles:
                starts[role].append(start_item(module, c.symbol, PATH_FORM, "unattributed"))
            continue
        role = process_kind.cli_entry_point(list(c.words), {}) if c.decided else None
        if role in table:  # the owner's own function decides which of the CLI's rows an argv is
            starts[role].append(start_item(module, c.symbol, ARGV_FORM, "derived"))
            started_unresolved[role].append(C.unresolved_item(module, c.symbol, CONSOLE_WHY[ARGV_FORM]))
        else:
            for row in roles:
                started_unresolved[row].append(C.unresolved_item(
                    module, c.symbol, f"{CONSOLE_WHY[ARGV_FORM]}; its constants do not decide which role it is"))

    records = []
    for key, (kind, reason) in sorted(table.items()):
        where = sorted({(d.module, d.symbol or "", d.via) for d in declares
                        if (d.via == "literal" and d.entry_point == key)
                        or (d.via == "cli_entry_point" and key in roles)})
        declared_unresolved = list(anywhere_declared)
        if not where:
            declared_unresolved.append(C.unresolved_item(PROCESS_KIND, "ENTRY_POINTS",
                                                         f"{key} is in the table but nothing declares itself as it"))
        anchor_module, anchor_symbol = (where[0][0], where[0][1]) if where else (PROCESS_KIND, "ENTRY_POINTS")
        distinct = {(i["module"], i["symbol"] or "", i["form"]): i for i in starts[key]}
        fact: dict[str, Any] = {
            "entry_point": key, "kind": kind, "reason": reason,
            "declared_at": [{"module": m, "symbol": s or None, "via": v} for m, s, v in where],
            "starts": [distinct[k] for k in sorted(distinct)],
        }
        # how complete each list fact is, in coverage's vocabulary, on the record beside `coverage`: a detector found
        # them, so both are lower-bound
        fact_coverage = {"declared_at": C.lower_bound(declared_unresolved),
                         "starts": C.lower_bound(started_unresolved[key] + anywhere_started)}
        records.append(C.Record(FAMILY, key, anchor_module, anchor_symbol, "enumerated",
                                C.complete(REGISTRY, CHECKS), fact, fact_coverage=fact_coverage))
    return C.Built(records=records, pages={"entry-points.md": page(records)})


def page(records: list[C.Record]) -> str:
    lines = ["# Entry points", "",
             "Every AEW process entry point, from `aew.process_kind.ENTRY_POINTS`: its kind, where it declares itself, "
             "and the places the product starts it. Generated by `python tools/reference.py render`; do not edit. A "
             "**store writer** takes the engine's control lock; a **non-writer** reads lock-free only and is refused a "
             "lock-taking operation before the lock opens. The set of entry points is complete-by-construction: the "
             "table is the registry, and the tests named in `index.json` stop code bypassing it. Each list of a record "
             "(`declared_at`, `starts`) is lower-bound, and its `fact_coverage` says what it could not resolve (also "
             "in [gaps.md](gaps.md)). A start has a form: `-m` (a `python -m` spawn), `console-script-argv` (an argv "
             "constant that starts with `aew`; whether it is run is not decided here) or `console-script-on-PATH` "
             "(makes the CLI startable and starts none, so it is listed for every role of the CLI).", ""]

    def anchors(items: list[dict[str, Any]]) -> str:
        return ", ".join(f"`{i['module']}:{i['symbol']}`" if i["symbol"] else f"`{i['module']}`" for i in items)

    for r in sorted(records, key=lambda r: r.key):
        fact = r.fact or {}
        lines += [f"### `{r.key}`", "", f"- **Kind:** {fact['kind']}", f"- **Why:** {fact['reason']}",
                  f"- **Declares itself at:** {anchors(fact['declared_at']) or 'nowhere (see gaps.md)'}"]
        for form in (DASH_M, ARGV_FORM, PATH_FORM):
            items = [i for i in fact["starts"] if i["form"] == form]
            if items:
                lines.append(f"- **Starts, `{form}`:** {anchors(items)}")
        if not fact["starts"]:
            lines.append("- **Starts:** none found")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"
