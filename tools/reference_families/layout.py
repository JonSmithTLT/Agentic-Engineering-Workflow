"""The ``layout`` family (DOC-04): the ``.aew`` directory tree, who writes and reads each entry, whether git keeps it,
and whether a contained process sees it (STG-12 S12-2).

The set of entries is derived, not declared: the entries directly under ``.aew`` (``writers.TOP_LEVEL``, which the
writers family pins to what the code writes) and every directory above a path the writers family places or the readers
(:mod:`reference_families.layout_reads`) read. A record is keyed by the entry's ``.aew``-relative prefix
(``layout:local/harness``; ``{}`` is a computed segment), and anchored at the constant that spells it
(``aew.history.manifest:HISTORY_DIR``), else the first function that writes in it, else the first that reads it.

* **Writers** (DOC-01) are the functions that write a path directly in the entry, or the entry itself; **readers** the
  functions that read one. Both are lower bounds: the writers' unresolved writes and the readers' unplaced reads may
  touch any entry, and each record points at them.
* **Git-ignored** is derived from ``AEW_GITIGNORE``, the one owner of what git does not keep; a line of it this reading
  does not understand (a glob, a negation) is refused, never guessed.
* **Named by** are the module-level constants the writers family finds: used to build a path (an operand of ``/``, a
  part of an f-string, an argument of ``Path`` or ``os.path.join`` or of a write primitive) and whose value is exactly
  the entry. A constant spelled another way, or one that holds the same text for another purpose, is not found (the
  list is a lower bound, with nothing listed unresolved: review of the layout pull request, N-12).
* **Store** is ``aew.engine.store.STORE_REL`` and what is under it. **Masked by containment** is an entry the
  containment layout masks with an empty tmpfs (the names ``hide_runs`` is built from that evaluate to a path under
  ``.aew``). It is a fact about the mask and not about what one run sees: ``for_run`` binds the run's own scratch,
  harness and private-git directories back into the mask, writable, and that run sees them (review of the layout pull
  request, N-1). Which entries those are is not derived here: they are named by arguments of ``for_run`` that the value
  flow does not follow to a place (a command-line value), so the exception is stated, and the tree test builds a layout
  with a run directory inside ``.aew`` to hold that every bound-back directory lies in a masked entry.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from reference_families import common as C
from reference_families import layout_reads as L
from reference_families import writers as W
from reference_families import writers_flow as F

FAMILY = "layout"
CONTAINMENT = ("aew.harness.containment.layout", "hide_runs")  # the module and the keyword of the hidden directories
GLOB_CHARS = frozenset("*?[!")
READS_POINTER = ("read sites whose path this reading could not place under `.aew` (a path from a parameter, the "
                 "command line or the environment) are listed on the page and are not records; any of them may read "
                 "this entry")
FACT_KEYS = {"prefix", "git_ignored", "store", "masked_by_containment", "named_by", "writers", "readers"}
FLAGS = ("git_ignored", "store", "masked_by_containment")  # each holds for everything under an entry that has it
LISTS = ("named_by", "writers", "readers")

Fn = tuple[str, str]  # (module, symbol)


@dataclass(frozen=True)
class Inputs:
    """What the family reads, so a planted case can stand in for each owner."""

    top_level: tuple[str, ...]
    writers: Mapping[str, Iterable[Fn]]  # template -> the functions that write it
    reads: Mapping[str, Iterable[Fn]]  # template -> the functions that read it
    named: Mapping[str, list[Fn]]  # path text -> the constants that spell it exactly
    gitignore: str  # AEW_GITIGNORE
    store: str  # aew.engine.store.STORE_REL
    hidden: frozenset[str]  # the entries a contained process cannot see


def parent(template: str) -> str:
    return template.rpartition("/")[0]


def ancestors(template: str) -> list[str]:
    parts = template.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def within(prefix: str, roots: Iterable[str]) -> bool:
    return any(prefix == r or prefix.startswith(r + "/") for r in roots)


def ignored_prefixes(gitignore: str) -> list[str]:
    """The paths a ``.gitignore`` names (``local/``), as prefixes. A pattern other than a plain path is refused: the
    reading does not guess what a glob, a negation or an anchored pattern ignores."""
    out = []
    for line in gitignore.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if GLOB_CHARS & set(line) or line.startswith("/"):
            raise C.ReferenceError(f"AEW_GITIGNORE has a line this reading does not understand: {line!r}")
        out.append(line.rstrip("/"))
    return out


def hidden_dirs(program: F.Program, evaluator: F.Evaluator, top_level: frozenset[str]) -> set[str]:
    """The ``.aew``-relative entries the containment layout hides: the names the ``hide_runs`` keyword is built from
    (followed through the list they are put in) that evaluate to a path under ``.aew``."""
    module, keyword = CONTAINMENT
    mod = program.modules[module]
    found: set[str] = set()
    seen = False
    for func in mod.funcs.values():
        for call in func.calls:
            for kw in call.keywords:
                if kw.arg != keyword:
                    continue
                seen = True
                exprs: list[ast.expr] = [kw.value]
                for name in {n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)}:
                    exprs += func.assigns.get(name, []) + func.appends.get(name, [])
                for expr in exprs:
                    for leaf in ast.walk(expr):
                        if isinstance(leaf, ast.Name):
                            for kind, text in evaluator.value(mod, func, leaf):
                                if kind == F.TPL and text.split("/")[0] in top_level:
                                    found.add(text)
    if not seen:
        raise C.ReferenceError(f"{module} no longer builds a layout with a `{keyword}` keyword: the hidden entries "
                               "cannot be read")
    if not found:  # the layout hides `.aew/local` by design, so a reading that finds none has lost the path
        raise C.ReferenceError(f"{module} builds `{keyword}` from no path this reading can place under `.aew`: the "
                               "hidden entries cannot be read")
    return found


def reads_pointer() -> dict[str, Any]:
    return C.unresolved_item("aew", None, READS_POINTER)


def _items(pairs: Iterable[Fn]) -> list[dict[str, str]]:
    return [{"module": m, "symbol": s} for m, s in sorted(set(pairs))]


def anchor_of(prefix: str, groups: Iterable[Iterable[Fn]]) -> Fn:
    """The first group with a function in it names the anchor (by sorted order): the constants that spell the entry,
    the functions that write it, those that read it, then those that do either below it."""
    for group in groups:
        found = sorted(set(group))
        if found:
            return found[0]
    raise C.ReferenceError(f"the entry {prefix!r} is declared, and nothing names, writes or reads it")


def records_of(inp: Inputs) -> list[C.Record]:
    ignored = ignored_prefixes(inp.gitignore)
    templates = set(inp.writers) | set(inp.reads)
    prefixes = set(inp.top_level) | {a for t in templates for a in ancestors(t)}
    records = []
    for prefix in sorted(prefixes):
        direct = [t for t in templates if t == prefix or parent(t) == prefix]
        wrote = [f for t in direct for f in inp.writers.get(t, ())]
        read = [f for t in direct for f in inp.reads.get(t, ())]
        below = [f for t in templates if t.startswith(prefix + "/")
                 for f in (*inp.writers.get(t, ()), *inp.reads.get(t, ()))]
        named = inp.named.get(prefix, [])
        module, symbol = anchor_of(prefix, (named, wrote, read, below))
        fact = {
            "prefix": prefix,
            "git_ignored": within(prefix, ignored),
            "store": within(prefix, [inp.store]),
            "masked_by_containment": within(prefix, inp.hidden),
            "named_by": [{"module": m, "symbol": n} for m, n in sorted(named)],
            "writers": _items(wrote),
            "readers": _items(read),
        }
        pointers = [W.pointer_item(), reads_pointer()]
        records.append(C.Record(FAMILY, prefix, module, symbol, "static", C.lower_bound(pointers), fact,
                                fact_coverage={"named_by": C.lower_bound(),
                                               "writers": C.lower_bound([W.pointer_item()]),
                                               "readers": C.lower_bound([reads_pointer()])}))
    return records


def problems(records: Mapping[str, Any]) -> list[str]:
    """The family's own invariants over its records as JSON: the key is the prefix; the facts are the seven; a flag that
    holds for an entry holds for what is under it; every list fact has its coverage and is sorted; the record points at
    the unresolved writes and the unplaced reads."""
    out: list[str] = []
    mine = {rid.removeprefix(f"{FAMILY}:"): r for rid, r in records.items() if r.get("family") == FAMILY}
    for key, r in sorted(mine.items()):
        rid, fact = f"{FAMILY}:{key}", r.get("fact") or {}
        if set(fact) != FACT_KEYS:
            out.append(f"{rid}: the fact is not {sorted(FACT_KEYS)}")
            continue
        if fact["prefix"] != key:
            out.append(f"{rid}: the prefix is not the key")
        above = mine.get(parent(key))
        for flag in FLAGS:
            if not isinstance(fact[flag], bool):
                out.append(f"{rid}: {flag} is not a boolean")
            elif above is not None and above["fact"].get(flag) and not fact[flag]:
                out.append(f"{rid}: {flag} holds for {parent(key)!r} and not for what is under it")
        for name in LISTS:
            if name not in (r.get("fact_coverage") or {}):
                out.append(f"{rid}: no fact_coverage for {name}")
            if fact[name] != sorted(fact[name], key=lambda i: (i["module"], i["symbol"])):
                out.append(f"{rid}: {name} is not sorted")
        listed = (r.get("coverage") or {}).get("unresolved", [])
        if W.pointer_item() not in listed or reads_pointer() not in listed:
            out.append(f"{rid}: it does not point at the unresolved writes and the unplaced reads")
    return out


def _fns(items: list[dict[str, str]]) -> str:
    """The functions of a list fact, grouped by module."""
    by_module: dict[str, list[str]] = {}
    for i in items:
        by_module.setdefault(i["module"], []).append(f"`{i['symbol']}`")
    return "; ".join(f"`{m}`: {', '.join(s)}" for m, s in by_module.items()) or "none"


def page(records: list[C.Record], placed: L.Placed) -> str:
    lines = [
        "# Layout", "",
        "The `.aew` directory tree. Generated by `python tools/reference.py render`; do not edit. An entry is a record "
        "keyed by its `.aew`-relative prefix (`{}` is a computed segment). **Git-ignored** is what `AEW_GITIGNORE` "
        "keeps out of git; the rest git keeps. **Named by** are the module-level constants that are used to build a "
        "path (an operand of `/`, a part of an f-string, an argument of `Path`, `os.path.join` or a write primitive) "
        "and whose value is exactly the entry; a constant spelled another way, or holding the same text for another "
        "purpose, is not found. **Store** is the entry "
        "`aew.engine.store.STORE_REL` names and what is under it. **Masked** is an entry the containment layout masks "
        "with an empty tmpfs, so what the host keeps there is not seen by a contained process; the run's own scratch, "
        "harness and private-git directories under a masked entry are bound back into the mask, writable, and that "
        "run sees them (which entries those are is not derived here). **Written by** is from [writers.md](writers.md): "
        "the functions that write a path directly in the entry. **Read by** is the functions that read one, by the "
        "primitives listed at the end; a read through an API is the API function's, not its callers'.", "",
        "Both lists are lower bounds. The writes the writers family could not place, and the reads this page could not "
        f"(below), may touch any entry. Read sites found: {placed.sites}; placed under `.aew`: "
        f"{placed.placed_sites}; followed to a place outside it or the directory itself: {placed.outside_sites}; "
        f"not placed: {placed.unplaced_sites}.", ""]
    for top in (r for r in records if "/" not in r.key):
        lines += [f"## `{top.key}`", ""]
        for r in (x for x in records if x.key == top.key or x.key.startswith(top.key + "/")):
            f = r.fact or {}
            flags = [name for name, on in (("git-ignored", f["git_ignored"]), ("store", f["store"]),
                                           ("masked by containment", f["masked_by_containment"])) if on]
            named = f"; named by {_fns(f['named_by'])}" if f["named_by"] else ""
            lines.append(f"- `{f['prefix']}` ({', '.join(flags) or 'kept in git'}){named}; written by "
                         f"{_fns(f['writers'])}; read by {_fns(f['readers'])}")
        lines.append("")
    lines += ["## Reads this reading could not place", "",
              "Read sites whose path is not followed to a path under `.aew` or to a place outside it, listed so that "
              "nothing is dropped unseen. Any of them may read any entry above.", ""]
    by_module: dict[str, list[str]] = {}
    for module, symbol, primitive in placed.unplaced:
        by_module.setdefault(module, []).append(f"`{symbol}` ({primitive})")
    lines += [f"- `{module}`: {', '.join(found)}" for module, found in sorted(by_module.items())] or ["None."]
    lines += ["", "## What the reading does not see", "",
              "A method named like a read primitive is counted as a read of its receiver, whatever the receiver is "
              "(an entry's reader may be a read of something that is not a path), and a read of a path built where it "
              "is not used is listed above and not placed. Not seen at all:", ""]
    lines += [f"- {text}" for _, text in L.CANNOT_SEE]
    lines += ["", "The primitives it reads: " + ", ".join(f"`{p}`" for p in L.read_labels()) + "."]
    return "\n".join(lines).rstrip("\n") + "\n"


def build(ctx: C.Context) -> C.Built:
    from aew.engine import api, store  # the owners at run time (reference.py checked that aew is this tree's)

    trees = {name: (src.tree, src.is_package) for name, src in ctx.sources().items() if src.tree is not None}
    program, top = F.Program.of(trees), frozenset(W.TOP_LEVEL)
    evaluator = F.Evaluator(program)
    analysis = W.analyse(program, top)  # no roots: the layout does not use the entry points' reach
    placed = L.place(L.read_sites(program, evaluator), top)
    writers = {t: [(w.module, w.symbol) for w in ws] for t, ws in analysis.writers.items()}
    inp = Inputs(W.TOP_LEVEL, writers, placed.reads, analysis.named, api.AEW_GITIGNORE, store.STORE_REL,
                 frozenset(hidden_dirs(program, evaluator, top)))
    records = records_of(inp)
    bad = problems({r.id: r.as_json() for r in records})
    if bad:
        raise C.ReferenceError("the layout records break their own rules:\n  " + "\n  ".join(C.shown(bad)))
    return C.Built(records=records, pages={"layout.md": page(records, placed)})
