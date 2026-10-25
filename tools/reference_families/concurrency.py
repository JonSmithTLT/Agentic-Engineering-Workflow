"""The ``concurrency`` family (DOC-03): who takes which lock, and who works without the control lock (STG-12 S12-2).

Two kinds of record, keyed by what the code names:

* ``concurrency:lock:<path>``: a lock file, by its ``.aew``-relative path (``concurrency:lock:local/control.lock``). It
  is every ``FileLock`` construction (found by import source, the path followed by the writers family's value flow),
  with the **opener** (the function that constructs it), the **takers** (the functions that hold it: the opener's
  callers when it returns the lock, else the opener itself, each with the operation name it passes) and, for each
  taker, the entry points that reach it and their kinds. ``refused_in_non_writer`` says whether the opener calls
  ``process_kind.require_writer`` before it constructs the lock. The **control lock** is the lock on the path the
  engine's store owns (``aew.engine.store.LOCK_REL``): its opener is one function by construction (the store's
  ``control_lock``, held by a tree test), so the record is complete-by-construction and its takers are a lower bound.
* ``concurrency:lock-free:<module>:<symbol>``: a function or class that works without the control lock, and what the
  code says it may observe. The members are the ones ``aew.process_kind`` names in its module docstring (parsed from
  it, not restated) and six this module declares: the compactor's build, re-read and prune, because its module
  docstring says they run without the lock, and the wake mark's writer, reader and waiter, because the wake signal is
  advisory (their docstrings say nothing of a lock, so ``takes_no_lock`` is the only support there). Each carries the
  first sentence of its own docstring as ``observes``, the
  sentences of its own or its module's docstring that say it is lock-free as ``says`` (a docstring's design citations
  are elided: the reference holds no such id), and whether its static call closure reaches a function that takes a
  lock (``takes_no_lock``; the closure is the call graph the reach uses).

Everything is lower-bound except the control lock's opener: a lock taken another way (an in-process ``threading`` lock,
SQLite's, ``os.O_EXCL``), a call the call graph does not resolve, and a function that works without the lock and is
neither named by ``process_kind`` nor declared here are not seen, and the page says so.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from reference_families import common as C
from reference_families import writers as W
from reference_families import writers_flow as F
from reference_families import writers_reach as R

FAMILY = "concurrency"
LOCK_FREE = "lock-free"  # the key prefix of a record of a function that works without the control lock
LOCK = ("aew.engine.lock", "FileLock")  # the one class that takes a lock file
LOCK_CALLEE = ".".join(LOCK)
GATE = ("aew.process_kind", "require_writer")
CONTROL_CHECKS = (
    "tests/integration/test_non_writer_reads.py::test_nothing_but_the_store_names_the_control_locks_path",
    "tests/integration/test_reference_concurrency.py::test_the_control_locks_only_opener_is_the_stores_and_its_takers"
    "_are_the_functions_that_call_it",
)
NON_WRITER_MARK = "reads only lock-free:"  # in process_kind's docstring: what follows names the lock-free readers
NON_WRITER_END = "These take no lock"
SAYS = re.compile(r"without the (control )?lock|no (control )?lock is taken|takes? no (control )?lock|lock-?free|"
                  r"lockless|needs no lock", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z*`(])")
PARENTHETICAL = re.compile(r"\s*\([^()]*\)")
# A design citation in a docstring: a decision label (`D3`), a register row (`F20.2`), an ADR or a stage id.
CITATION = re.compile(r"\b(?:[A-Z]{1,4}\d+(?:\.\d+)?[a-z]?|[A-Z]{2,}-\d+[a-z]?)\b")
# Members this family declares because the code works without the control lock there and process_kind does not name
# them: (module, symbol, why, the words by which the module's docstring names this member's own work). The compactor's
# module docstring says its build, re-read and prune run without the lock, and a sentence of it is quoted for a member
# only if it names that member's work (the same docstring says its readers are lockless, which is not the build's).
# The wake mark's own docstrings say nothing of locks (a stat and a rename; the signal is advisory), so for those the
# closure check is the only support, the words are empty and `says` is empty.
DECLARED: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("aew.engine.log_compact", "build_segment", "the compactor's build of a segment from the unsealed files",
     ("build",)),
    ("aew.engine.log_compact", "verify_against_unsealed",
     "the compactor's check of a segment against the unsealed files", ("re-read",)),
    ("aew.engine.log_compact", "_unlink", "the compactor's prune of the unsealed files", ("prune",)),
    ("aew.engine.outbox", "bump_wake", "the wake mark's writer", ()),
    ("aew.engine.outbox", "wake_mark", "the wake mark's reader", ()),
    ("aew.engine.outbox", "wait_for", "a waiter on the wake mark", ()),
)
OPENERS_ITEM = ("a lock taken another way than a `FileLock` construction (an in-process `threading` lock, SQLite's "
                "own, an `os.O_EXCL` file), a `FileLock` reached under another name, and a call of an opener this "
                "reading does not resolve are not seen")
MEMBERS_ITEM = ("a function that works without the control lock and is neither named by `aew.process_kind` nor "
                "declared by this family is not listed; a call the call graph does not resolve is not followed")

Key = tuple[str, str]


@dataclass(frozen=True)
class Site:
    """A ``FileLock`` construction: where, on which path, with what timeout."""

    module: str
    symbol: str
    path: str | None  # the `.aew`-relative template; None when this reading could not place it
    why: str | None  # why it could not
    timeout: str | None  # the source of the `timeout=` keyword; None: the class's default
    gated: bool  # the opener calls process_kind.require_writer before it constructs the lock
    returned: bool  # the construction is the value the opener returns: its callers hold the lock


@dataclass(frozen=True)
class Taker:
    module: str
    symbol: str
    operation: str | None  # the first argument of the call that took the lock, when it is a string literal
    opener: Key


@dataclass(frozen=True)
class Member:
    module: str
    symbol: str
    source: str  # "process_kind" or "declared"
    why: str
    observes: str  # the first sentence of the symbol's own docstring, without its design citations
    says: list[str]  # the sentences of the own docstring (else the module's) that say it is lock-free
    says_in: str | None  # "symbol", "module" or None
    takes_no_lock: bool
    lock_takers: list[Key]  # functions of its call closure that take a lock


@dataclass(frozen=True)
class Inputs:
    """What the family reads, so a planted case can stand in for each owner."""

    sites: list[Site]
    takers: list[Taker]
    control_path: str  # aew.engine.store.LOCK_REL
    members: list[Member]
    reach: Mapping[Key, set[str]]  # function -> the entry-point keys whose root reaches it
    kinds: Mapping[str, str]  # entry-point key -> its kind
    classes: Mapping[Key, list[Key]]  # a class member -> its methods (the reach and the closure start there)


def sentences(doc: str | None) -> list[str]:
    """A docstring's sentences, whitespace collapsed, with the design citations left out (:func:`plain`)."""
    found = []
    for para in (doc or "").strip().split("\n\n"):
        for sentence in SENTENCE_END.split(" ".join(para.split())):
            if sentence:
                found.append(sentence)
    return found


def plain(sentence: str) -> str | None:
    """The sentence without its design citations: a parenthetical that names one is elided, and a sentence that still
    names one is left out (None). The reference states what the code is and holds no requirement or register id
    (``tests/unit/test_reference.py``), and a docstring cites its decisions."""
    kept = PARENTHETICAL.sub(lambda m: "" if CITATION.search(m.group()) else m.group(), sentence).strip()
    if CITATION.search(kept):
        return None
    if kept.endswith(":"):  # it introduces a list: cut at its last comma (the clause that points at the list), or out
        cut = last_comma_outside(kept[:-1])
        return kept[:cut] + "." if cut else None
    return kept


def last_comma_outside(text: str) -> int | None:
    """The index of the last comma of ``text`` that is in no bracket and no code span, or None. A comma inside
    ``(a stat, a read)`` is part of an aside, not the clause that points at a list (review of #267, Q-3)."""
    found, depth, code, before = None, 0, False, ""
    for i, ch in enumerate(text):
        if ch == "`":  # a run of backticks (a span written ``like this``) opens or closes once
            code = code if before == "`" else not code
        elif not code:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(depth - 1, 0)
            elif ch == "," and depth == 0:
                found = i
        before = ch
    return found


def says_of(doc: str | None) -> list[str]:
    return [p for p in (plain(s) for s in sentences(doc) if SAYS.search(s)) if p]


def observes_of(doc: str | None) -> str:
    """The first sentence of the docstring that carries no bare citation: what the symbol is and may observe."""
    return next((p for p in (plain(s) for s in sentences(doc)) if p), "")


def _short(qual: str) -> str:
    return qual.rsplit(".", 1)[-1]


def lock_sites(program: F.Program, evaluator: F.Evaluator) -> list[Site]:
    """Every ``FileLock`` construction of the program, by import source."""
    found = []
    for name, mod in sorted(program.modules.items()):
        for func in mod.funcs.values():
            for call in func.calls:
                if mod.aliases.resolve(call.func) != LOCK_CALLEE:
                    continue
                values = evaluator.value(mod, func, call.args[0]) if call.args else frozenset()
                templates = sorted(v.text for v in values if v.kind == F.TPL)
                path = templates[0] if len(templates) == 1 and len(values) == 1 else None
                why = None if path else "; ".join(sorted({v.text for v in values if v.kind == F.UNK} or {"not placed"}))
                keyword = next((k.value for k in call.keywords if k.arg == "timeout"), None)
                timeout = keyword if keyword is not None else (call.args[1] if len(call.args) > 1 else None)
                gate_lines = [c.lineno for c in func.calls
                              if mod.aliases.resolve(c.func) == ".".join(GATE) and c.lineno < call.lineno]
                # `return FileLock(...)`, or `lock = FileLock(...)` and then `return lock`
                returned = any(r is call or (isinstance(r, ast.Name)
                                             and any(a is call for a in func.assigns.get(r.id, [])))
                               for r in func.returns)
                found.append(Site(name, func.qual, path, why, ast.unparse(timeout) if timeout is not None else None,
                                  bool(gate_lines), returned))
    return found


def takers_of(program: F.Program, sites: Iterable[Site]) -> list[Taker]:
    """Who holds each lock: the callers of an opener that returns the lock (the operation they pass is their first
    argument, when a string literal), else the opener itself."""
    out = []
    for site in sites:
        key = (site.module, site.symbol)
        if not site.returned:
            out.append(Taker(site.module, site.symbol, None, key))
            continue
        for caller, _mod, call in program.callers.get(key, []):
            if caller is None:
                continue
            first = call.args[0] if call.args else None
            operation = first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
            out.append(Taker(caller.module, caller.qual, operation, key))
    return sorted(set(out), key=lambda t: (t.module, t.symbol, t.operation or "", t.opener))


def call_counts(program: F.Program, names: Iterable[str]) -> dict[str, Counter[str]]:
    """Per module, how many calls name each of ``names`` (a method, a function, a constructor) whatever the receiver:
    what the token reading is held to. The ``FileLock`` constructions are the calls that resolve to it by import
    source."""
    wanted = set(names)
    counts: dict[str, Counter[str]] = {}
    for name, mod in program.modules.items():
        found: Counter[str] = Counter()
        scopes = [(None, mod.module_calls), *[(f, f.calls) for f in mod.funcs.values()]]
        for _func, calls in scopes:
            for call in calls:
                target = call.func.attr if isinstance(call.func, ast.Attribute) else (
                    call.func.id if isinstance(call.func, ast.Name) else None)
                if mod.aliases.resolve(call.func) == LOCK_CALLEE:
                    found[LOCK[1]] += 1
                elif target in wanted:
                    found[target] += 1
        counts[name] = found
    return counts


def process_kind_names(doc: str) -> list[str]:
    """The names ``aew.process_kind``'s docstring gives its non-writers' lock-free reads
    (``ControlStore.read_committed``)."""
    start = doc.find(NON_WRITER_MARK)
    end = doc.find(NON_WRITER_END, start)
    if start < 0 or end < 0:
        raise C.ReferenceError(f"aew.process_kind's docstring no longer says what a non-writer reads lock-free "
                               f"(`{NON_WRITER_MARK}` ... `{NON_WRITER_END}`): the lock-free members cannot be read")
    names = re.findall(r"``([A-Za-z_][\w.]*)``", doc[start:end])
    if not names:
        raise C.ReferenceError("aew.process_kind's docstring names no lock-free reader after its marker")
    return names


def resolve_name(program: F.Program, dotted: str) -> Key:
    """``ControlStore.read_committed`` (a class of one module, then its method) or ``outbox.LogView`` (a module by its
    last word, then the name in it). A name that is neither is an error, never a guess."""
    head, _, rest = dotted.partition(".")
    owners = sorted(m for m, mod in program.modules.items() if head in mod.classes)
    if len(owners) == 1:
        return owners[0], dotted
    modules = sorted(m for m in program.modules if m.rsplit(".", 1)[-1] == head)
    if len(modules) == 1 and rest:
        return modules[0], rest
    raise C.ReferenceError(f"aew.process_kind names `{dotted}`, which is not a class of exactly one module nor a "
                           f"name in exactly one module (found {owners or modules})")


def _node(program: F.Program, key: Key) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef:
    """The function or class a (module, symbol) names."""
    mod = program.modules.get(key[0])
    if mod is None:
        raise C.ReferenceError(f"{key[0]} is not a module of the tree")
    if key[1] in mod.funcs and not isinstance(mod.funcs[key[1]].node, ast.Lambda):
        return mod.funcs[key[1]].node  # type: ignore[return-value]
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.ClassDef) and node.name == key[1].rsplit(".", 1)[-1] and "." not in key[1]:
            return node
    raise C.ReferenceError(f"{key[0]}:{key[1]} is neither a function nor a class of the module")


def methods_of(program: F.Program, key: Key) -> list[Key]:
    """A class member's methods (its reach and its closure start there); a function is its own."""
    mod = program.modules[key[0]]
    if key[1] in mod.funcs:
        return [key]
    return sorted((key[0], q) for q in mod.funcs if q.startswith(key[1] + "."))


def members_of(program: F.Program, pk_doc: str, takers: Iterable[Key]) -> list[Member]:
    edges = R.graph(program)
    taking = set(takers)
    wanted: dict[Key, tuple[str, str, tuple[str, ...]]] = {}
    for dotted in process_kind_names(pk_doc):
        wanted[resolve_name(program, dotted)] = ("process_kind", f"named by aew.process_kind: `{dotted}`", ())
    for module, symbol, why, words in DECLARED:
        wanted.setdefault((module, symbol), ("declared", why, words))
    out = []
    for key, (source, why, words) in sorted(wanted.items()):
        node = _node(program, key)
        own = ast.get_docstring(node, clean=True)
        module_doc = ast.get_docstring(program.modules[key[0]].tree, clean=True)
        of_module = [s for s in says_of(module_doc) if any(w in s.lower() for w in words)]
        own_says = says_of(own)
        says, says_in = (own_says, "symbol") if own_says else ((of_module, "module") if of_module else ([], None))
        reached = R.reach(edges, methods_of(program, key))
        locking = sorted(reached & taking)
        out.append(Member(key[0], key[1], source, why, observes_of(own), says, says_in, not locking, locking))
    return out


def entry_points(reach: Mapping[Key, set[str]], kinds: Mapping[str, str], keys: Iterable[Key]
                 ) -> tuple[list[str], list[str]]:
    """The entry points that reach any of ``keys`` and their kinds. A closure (``compact.control_lock``, passed down and
    called by the function it is defined in) has no call edge of its own: it is attributed what reaches the function
    that defines it."""
    found: set[str] = set()
    for module, qual in keys:
        here = reach.get((module, qual))
        if not here and "." in qual:
            here = reach.get((module, qual.rsplit(".", 1)[0]))
        found |= here or set()
    return sorted(found), sorted({kinds[k] for k in found})


def _unreached_items(module: str, symbol: str, why: str = W.NO_CHAIN) -> dict[str, Any]:
    return C.unresolved_item(module, symbol, why)


def records_of(inp: Inputs) -> list[C.Record]:
    records = []
    by_path: dict[str, list[Site]] = {}
    for site in inp.sites:
        by_path.setdefault(site.path or f"unplaced:{site.module}:{site.symbol}", []).append(site)
    for path, sites in sorted(by_path.items(), key=lambda kv: (kv[0] != inp.control_path, kv[0])):
        openers = sorted({(s.module, s.symbol) for s in sites})
        control = path == inp.control_path
        if control and len(openers) != 1:
            raise C.ReferenceError(f"the control lock {path} is opened in {len(openers)} places {openers}: it is "
                                   "opened in one, the store's `control_lock` (a tree test refuses any other)")
        takers = [t for t in inp.takers if t.opener in openers]
        items, listed = [], []
        for t in takers:
            eps, kinds = entry_points(inp.reach, inp.kinds, [(t.module, t.symbol)])
            listed.append({"module": t.module, "symbol": t.symbol, "operation": t.operation, "entry_points": eps,
                           "entry_kinds": kinds})
            if not eps:
                items.append(_unreached_items(t.module, t.symbol))
        first = sites[0]
        fact: dict[str, Any] = {
            "lock": path, "control": control, "refused_in_non_writer": all(s.gated for s in sites),
            "timeout": ";".join(sorted({s.timeout or "the class default" for s in sites})),
            "openers": [{"module": m, "symbol": s} for m, s in openers],
            "takers": listed,
        }
        if first.path is None:
            fact["unplaced_why"] = first.why
        coverage = (C.complete(f"{openers[0][0]}:{openers[0][1]}", CONTROL_CHECKS) if control
                    else C.lower_bound([C.unresolved_item(first.module, first.symbol, OPENERS_ITEM)]))
        records.append(C.Record(FAMILY, f"lock:{path}", first.module, first.symbol, "static", coverage, fact,
                                fact_coverage={"openers": C.lower_bound([C.unresolved_item(first.module, first.symbol,
                                                                                           OPENERS_ITEM)]),
                                               "takers": C.lower_bound([C.unresolved_item(first.module, first.symbol,
                                                                                          OPENERS_ITEM), *items])}))
    pointer = C.unresolved_item(GATE[0], None, MEMBERS_ITEM)
    for m in inp.members:
        key = (m.module, m.symbol)
        eps, kinds = entry_points(inp.reach, inp.kinds, inp.classes.get(key, [key]))
        fact = {"module": m.module, "symbol": m.symbol, "source": m.source, "why": m.why, "observes": m.observes,
                "says": m.says, "says_in": m.says_in, "takes_no_lock": m.takes_no_lock,
                "lock_takers": [{"module": a, "symbol": b} for a, b in m.lock_takers],
                "entry_points": eps, "entry_kinds": kinds}
        unreached = [] if eps else [_unreached_items(m.module, m.symbol)]
        records.append(C.Record(FAMILY, f"{LOCK_FREE}:{m.module}:{m.symbol}", m.module, m.symbol, "static",
                                C.lower_bound([pointer]), fact,
                                fact_coverage={"says": C.lower_bound([pointer]),
                                               "lock_takers": C.lower_bound([pointer]),
                                               "entry_points": C.lower_bound([pointer, *unreached]),
                                               "entry_kinds": C.lower_bound([pointer, *unreached])}))
    return records


LOCK_KEYS = {"lock", "control", "refused_in_non_writer", "timeout", "openers", "takers", "unplaced_why"}
FREE_KEYS = {"module", "symbol", "source", "why", "observes", "says", "says_in", "takes_no_lock", "lock_takers",
             "entry_points", "entry_kinds"}


def problems(records: Mapping[str, Any], kinds: Mapping[str, str] | None = None) -> list[str]:
    """The family's own invariants over its records as JSON: shapes; the key is the lock path or the member; exactly one
    control lock, with one opener, and complete-by-construction; every other record is a lower bound; a member that
    takes no lock lists none and one that does lists them; an entry point is a row of the table."""
    out: list[str] = []
    controls = []
    for rid, r in sorted(records.items()):
        if r.get("family") != FAMILY:
            continue
        key, fact, cov = rid.removeprefix(f"{FAMILY}:"), r.get("fact") or {}, r.get("coverage") or {}
        if key.startswith("lock:"):
            if not LOCK_KEYS - {"unplaced_why"} <= set(fact) <= LOCK_KEYS:
                out.append(f"{rid}: a lock's fact is {sorted(LOCK_KEYS - {'unplaced_why'})}, and why it is unplaced")
                continue
            if fact["lock"] != key.removeprefix("lock:"):
                out.append(f"{rid}: the lock is not the key")
            if fact["control"]:
                controls.append(rid)
                if cov.get("label") != C.COMPLETE or len(fact["openers"]) != 1:
                    out.append(f"{rid}: the control lock is complete-by-construction with one opener")
            elif cov.get("label") != C.LOWER:
                out.append(f"{rid}: a lock that is not the control lock is a lower bound")
            if not fact["openers"]:
                out.append(f"{rid}: a lock has an opener")
            for t in fact["takers"]:
                if set(t) != {"module", "symbol", "operation", "entry_points", "entry_kinds"}:
                    out.append(f"{rid}: a taker is a module, a symbol, an operation and its entry points")
                elif kinds is not None and not set(t["entry_points"]) <= set(kinds):
                    out.append(f"{rid}: {t['module']}:{t['symbol']} names an entry point that is no row of the "
                               "table")
            if "takers" not in (r.get("fact_coverage") or {}):
                out.append(f"{rid}: no fact_coverage for takers")
        elif key.startswith(f"{LOCK_FREE}:"):
            if set(fact) != FREE_KEYS:
                out.append(f"{rid}: a lock-free member's fact is not {sorted(FREE_KEYS)}")
                continue
            if fact["takes_no_lock"] == bool(fact["lock_takers"]):
                out.append(f"{rid}: takes_no_lock and lock_takers disagree")
            if (fact["says_in"] is None) != (not fact["says"]):
                out.append(f"{rid}: says_in names where the paragraphs are and only then")
            if cov.get("label") != C.LOWER:
                out.append(f"{rid}: a lock-free member is a lower bound")
            if f"{fact['module']}:{fact['symbol']}" != key.removeprefix(f"{LOCK_FREE}:"):
                out.append(f"{rid}: the key is not the member")
        else:
            out.append(f"{rid}: neither a lock nor a lock-free member")
    if len(controls) != 1 and any(r.get("family") == FAMILY for r in records.values()):
        out.append(f"exactly one lock is the control lock, found {controls}")
    return out


def _fns(items: list[dict[str, Any]]) -> str:
    return "; ".join(f"`{i['module']}:{i['symbol']}`" for i in items) or "none"


def page(records: list[C.Record]) -> str:
    locks = [r for r in records if r.key.startswith("lock:")]
    free = [r for r in records if r.key.startswith(f"{LOCK_FREE}:")]
    lines = [
        "# Concurrency", "",
        "Which locks the code takes, and who works without the control lock. Generated by `python tools/reference.py "
        "render`; do not edit. A lock is a record keyed by its `.aew`-relative path, found as a `FileLock` "
        "construction (by import source) whose path the value flow places. **Opener** is the function that "
        "constructs it; **takers** are the functions that hold it (the opener's callers when it returns the lock, "
        "each with the operation name it passes, else the opener itself), with the entry points that reach them and "
        "their kinds (from the entry-points family). **Refused in a non-writer** says the opener calls "
        "`process_kind.require_writer` before it constructs the lock. The **control lock** is the lock on the path "
        "the engine's store owns: its opener is one function, held by a tree test, so that record is "
        "complete-by-construction; its takers are a lower bound.", "",
        "## Locks", ""]
    for r in locks:
        f = r.fact or {}
        tag = "control lock" if f["control"] else "lock"
        lines.append(f"### `{f['lock']}` ({tag})")
        lines.append("")
        lines.append(f"- opener {_fns(f['openers'])}; timeout: {f['timeout']}; refused in a non-writer: "
                     f"{'yes' if f['refused_in_non_writer'] else 'no'}")
        for t in f["takers"]:
            op = f" (`{t['operation']}`)" if t["operation"] else ""
            eps = ", ".join(f"`{e}`" for e in t["entry_points"]) or "no static chain from any entry point"
            lines.append(f"- taker `{t['module']}:{t['symbol']}`{op}: reached from {eps}")
        lines.append("")
    lines += [
        "## Works without the control lock", "",
        "The functions and classes that work without the control lock, and what the code says they may observe: "
        "**observes** is the first sentence of the symbol's own docstring, **says** the sentences of the docstring "
        "(its own, else its module's) that state it is lock-free; a design citation in either is elided, and a "
        "sentence that still names one is left out. The members are the ones `aew.process_kind` names in its module "
        "docstring and six this family declares: the compactor's build, re-read and prune, because its module "
        "docstring says they run without the lock, and the wake mark's writer, reader and waiter, because the wake "
        "signal is advisory (their docstrings say nothing of a lock, so **takes no lock** is the only support there). "
        "**Takes no lock** says the static call closure of the member reaches no function that takes a lock; a call "
        "this reading does not resolve, such as one through a receiver whose typing needs itself (`self.a = self.a`), "
        "is not followed.", ""]
    for r in free:
        f = r.fact or {}
        lines.append(f"### `{f['module']}:{f['symbol']}`")
        lines.append("")
        takes = "yes" if f["takes_no_lock"] else "NO: " + _fns(f["lock_takers"])
        reached = ", ".join("`" + e + "`" for e in f["entry_points"]) or "no entry point"
        lines.append(f"- {f['why']}; takes no lock: {takes}; reached from {reached}")
        if f["observes"]:
            lines.append(f"- observes: {f['observes']}")
        for p in f["says"]:
            lines.append(f"- says ({f['says_in']}): {p}")
        lines.append("")
    lines += ["## What the reading does not see", "",
              "A lock taken another way than a `FileLock` construction: an in-process `threading` lock or event, "
              "SQLite's own locking, a file created with `os.O_EXCL`; a `FileLock` reached under another name (the "
              "construction is found by import source, the token reading by spelling, and the two are held to equal "
              "counts, so a renamed import fails the agreement test until it is decided); a lock opener or a lock-free "
              "member called through a name this reading cannot resolve, or through a receiver whose typing needs "
              "itself (`self.a = self.a`); and a function that works without the control lock and is neither named by "
              "`aew.process_kind` nor declared here. Each is pinned by a probe: "
              + "; ".join(text for _, text in CANNOT_SEE) + "."]
    return "\n".join(lines).rstrip("\n") + "\n"


CANNOT_SEE: tuple[tuple[str, str], ...] = (
    ("thread-lock", "an in-process `threading.Lock`, `RLock`, `Condition` or `Event` (the dashboard and the harness "
     "have live ones)"),
    ("exclusive-create", "a file created with `os.O_EXCL` as a guard (the integration queue's checkout sync lock, "
     "`checkout_sync_lock_path` in `aew.engine.queue_ops`, is one that serialises a sync across processes)"),
    ("other-lock-class", "a lock class other than `aew.engine.lock.FileLock`"),
    ("computed-callee", "an opener called through `getattr`"),
    ("lock-in-a-variable", "a `FileLock` bound to another name and called by it"),
    ("cyclic-receiver", "a call through a receiver whose typing needs itself, such as `self.a = self.a` (it is not "
     "the typing cap, and the call is not followed)"),
)


def build(ctx: C.Context) -> C.Built:
    from aew import process_kind
    from aew.engine import store

    trees = {name: (src.tree, src.is_package) for name, src in ctx.sources().items() if src.tree is not None}
    program = F.Program.of(trees)
    kinds = {key: kind for key, (kind, _why) in process_kind.ENTRY_POINTS.items()}
    analysis = W.analyse(program, frozenset(W.TOP_LEVEL), R.roots_of(ctx, set(kinds)), kinds, R.cli_of(ctx, program))
    sites = lock_sites(program, F.Evaluator(program))
    takers = takers_of(program, sites)
    taking = {(t.module, t.symbol) for t in takers} | {(s.module, s.symbol) for s in sites}
    members = members_of(program, process_kind.__doc__ or "", taking)
    classes = {(m.module, m.symbol): methods_of(program, (m.module, m.symbol)) for m in members}
    records = records_of(Inputs(sites, takers, store.LOCK_REL, members, analysis.reach, kinds, classes))
    bad = problems({r.id: r.as_json() for r in records}, kinds)
    if bad:
        raise C.ReferenceError("the concurrency records break their own rules:\n  " + "\n  ".join(bad))
    return C.Built(records=records, pages={"concurrency.md": page(records)})
