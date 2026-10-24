"""The ``writers`` family (DOC-01): each path under ``.aew`` that AEW code writes, and the module and function that
writes it (STG-12 S12-2).

Owner: the source tree, read with ``ast`` (basis ``static``, label ``lower-bound``): nothing is imported. The reading
runs from the write end. A **write site** is a call of a write primitive, identified by where the callee was imported
from (``aew.util.atomic_write``, ``os.replace``, ``shutil.rmtree``, ``sqlite3.connect``) or, for a method that has no
import source, by what it is (``Path.write_text``, a one-argument ``.replace(target)``, ``open`` in a write mode, a
store transaction's ``session.write(path, content)``). The destination expression is evaluated by
:mod:`reference_families.writers_flow`; a value that is a path under ``.aew`` whose first entry is one of
:data:`TOP_LEVEL` becomes a record, keyed by the path as a template (``work/{}/completion.md``: ``{}`` is a computed
segment), with its writers: the module and function, the mechanism (``store-transaction`` or ``direct``) and the
primitives. ``aew.util`` and the store's own ``write_file`` are the write mechanism, not writers: their callers are.

A destination that is not provably under ``.aew`` and not provably outside it is **unresolved**: the site is a record of
its own, ``unresolved:<module>:<symbol>:<primitive>``, with the reason, and every path record's list of writers carries
one pointer item to them (any of them may write that path). A destination provably outside ``.aew`` (a temporary
directory, the console, the repository's working tree) is listed on the page and is no record.

Each writer carries the entry points that reach it (:mod:`reference_families.writers_reach`), as a lower bound (a chain
of resolved calls, and nothing more); a writer with no chain is unresolved on the records it appears in. The CLI's roles
share one declaring function, and the command decides the role, so they are cut by the parser
(:mod:`reference_families.writers_roles`): a handler is reached by the role of its command. A handler whose command
cannot be read is reached by every role, and the writers behind it say so, with an unresolved item anchored at the
function that registers it. The role the environment selects reaches nothing by the call graph: a writer that the
general handlers reach and that role is not given carries an item that says so, and that a write a non-writer may not
make is refused there (`process_kind.require_writer`, tested at run time and not proved here). A second detector,
:mod:`reference_families.writers_text`, finds the write-primitive calls by tokens, and the two must agree per module.

What it does not see is the family's ``cannot see`` list, pinned by probes in the tests: a path built in one function
and written in another through a value this reading cannot follow (a command-line argument, an environment variable, a
callback), a write by a subprocess, a method of an object whose class is not evident, ``chmod`` and ``fsync_dir``
(not writes), and a write at module level (refused, so that no fake anchor is made).
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from reference_families import common as C
from reference_families import writers_flow as F
from reference_families import writers_reach as R
from reference_families import writers_roles as ROLES

FAMILY = "writers"
STORE_TRANSACTION, DIRECT = "store-transaction", "direct"
LOCAL = "local"  # the top-level directory of rebuildable runtime data, kept out of git (`AEW_GITIGNORE`)
# The live case of the reach's `with` limit that the page names (a tree test holds it true): the function that takes a
# lock by `with`, and the records of the lock's files, which the reach attributes to the roles that call `__enter__`.
WITH_CASE = ("aew.dashboard.service", "Service.start", ("local/dashboard/endpoint.lock",
                                                       "local/dashboard/endpoint.lock.queue"))

# The entries directly under `.aew` (directories, and the two files `.gitignore` and `project.yaml`). The code has no
# single owner of this set (the project manifest names some of them), so it is declared here, pinned both ways by the
# tests: every first entry a write resolves to is in it (else the write is unresolved: a new directory is a decision),
# and every entry is the first entry of a record. The layout family reuses this table.
TOP_LEVEL: tuple[str, ...] = (".gitignore", "coordination", "decisions", "evidence", "history", "knowledge", "local",
                              "policy", "pricing", "project.yaml", "records", "roles", "state", "work")

# `aew.util` is the write mechanism: its callers are the writers, so a path written inside it is its caller's. So is the
# store's own `write_file` (every write into the store goes through it: its docstring says so).
MECHANISM_MODULES = frozenset({"aew.util"})
MECHANISM_FUNCTIONS = frozenset({("aew.engine.store", "write_file")})
STORE = "aew.engine.store"

UTIL = "aew.util"
# callee (by import source) -> (label, index of the destination argument)
CALL_PRIMITIVES: dict[str, tuple[str, int]] = {
    f"{UTIL}.atomic_write": ("atomic_write", 0),
    f"{UTIL}.create_exclusive": ("create_exclusive", 0),
    f"{UTIL}.write_temp": ("write_temp", 0),
    f"{UTIL}.replace_with_retry": ("replace_with_retry", 1),
    "os.replace": ("os.replace", 1), "os.rename": ("os.rename", 1), "os.link": ("os.link", 1),
    "os.symlink": ("os.symlink", 1), "os.remove": ("os.remove", 0), "os.unlink": ("os.unlink", 0),
    "os.rmdir": ("os.rmdir", 0), "os.mkdir": ("os.mkdir", 0), "os.makedirs": ("os.makedirs", 0),
    "os.truncate": ("os.truncate", 0),
    "shutil.copy": ("shutil.copy", 1), "shutil.copy2": ("shutil.copy2", 1), "shutil.copyfile": ("shutil.copyfile", 1),
    "shutil.copytree": ("shutil.copytree", 1), "shutil.move": ("shutil.move", 1), "shutil.rmtree": ("shutil.rmtree", 0),
    "sqlite3.connect": ("sqlite3.connect", 0),
    f"{STORE}.write_file": ("write_file", 1),
}
# Path methods that write their receiver, by name (a method has no import source): the limit is the family's, listed.
RECEIVER_METHODS = frozenset({"write_text", "write_bytes", "mkdir", "unlink", "touch", "rmdir", "symlink_to",
                              "hardlink_to"})
WRITE_MODES = frozenset("wax+")
WRITE_FLAGS = frozenset({"os.O_WRONLY", "os.O_RDWR", "os.O_CREAT", "os.O_APPEND", "os.O_TRUNC"})
# What this reading does not see, one entry per class: (a name the tests' probes are keyed by, how the page says it).
# The page is written from this tuple and each entry has a probe, both ways (tests/unit/test_reference_writers_flow.py).
CANNOT_SEE: tuple[tuple[str, str], ...] = (
    ("cross-function-path", "a path built in one function and written in another through a value this reading cannot "
     "follow (a command-line argument, an environment variable, a callback, a renderer)"),
    ("conditional-callee", "a primitive called through a conditional expression, `(a if x else b)(path)` (the store's "
     "own `write_file` does this)"),
    ("local-name-primitive", "a primitive bound to a local name and called by it"),
    ("computed-method", "a method named by a computed attribute, `getattr(path, name)(...)`"),
    ("subprocess", "a write by a subprocess"),
    ("other-openers", "an opener other than `open` and `Path.open`, such as `codecs.open`"),
    ("tempfile-in-aew", "a file kept under `.aew` by `tempfile.NamedTemporaryFile(dir=...)` or `mkstemp(dir=...)`"),
    ("keyword-target", "a `rename` or `replace` whose target is a keyword argument"),
    ("other-session-spelling", "a store transaction's `write` on a receiver not spelled `session`"),
    ("positional-open-mode", "a `.open(x)` whose positional argument is not a literal mode, which another API's "
     "`.open` also has (a mode in `mode=` that cannot be read is an unresolved write)"),
    ("metadata-calls", "`chmod`, `os.utime`, `fsync_dir` and other calls that change a file's metadata or durability "
     "and not its content (not writes)"),
    ("handler-by-name", "a command handler that calls an engine method by a name held in a variable, "
     "`getattr(engine, name)(...)` (the `integrate` commands' handlers, for one): the writers behind it are not "
     "attributed to the command's role"),
)


class Site(NamedTuple):
    module: str
    symbol: str
    primitive: str
    mechanism: str
    expr: str  # the destination expression as source text (for the reasons, never for a key)
    values: F.Values


READ, WRITE, UNREADABLE = "read", "write", "unreadable"
UNREADABLE_MARK = "?"  # a primitive label with this suffix: whether the call writes is not decided
UNREADABLE_WHY = "its mode or flags are not a literal this reading can read, so whether it writes is not decided"


def _combine(verdicts: Iterable[str]) -> str:
    found = set(verdicts)
    return WRITE if WRITE in found else UNREADABLE if UNREADABLE in found else READ


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _bound_values(func: F.Func | None, name: str) -> list[ast.expr] | None:
    """Every expression a local name is bound to in the function (assignments and `|=`), or None when it is bound to
    nothing the function shows (a parameter, a global, a name that is only augmented: what it started as is not shown)
    or by a loop or an unpacking."""
    if func is None or name in func.opaque and name not in func.augs or name in func.loops:
        return None
    assigned = func.assigns.get(name, [])
    return [*assigned, *func.augs.get(name, [])] if assigned else None


def mode_verdict(func: F.Func | None, node: ast.expr | None, seen: frozenset[str] = frozenset()) -> str:
    """Whether an `open` mode writes: a string literal decides it, as does a local name bound to literals, or a
    conditional of them. Anything else (a parameter, a call) is UNREADABLE, never READ. No mode is `r`."""
    if node is None:
        return READ
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return WRITE if any(c in WRITE_MODES for c in node.value) else READ
    if isinstance(node, ast.IfExp):
        return _combine([mode_verdict(func, node.body, seen), mode_verdict(func, node.orelse, seen)])
    if isinstance(node, ast.Name) and node.id not in seen:
        bound = _bound_values(func, node.id)
        if bound is not None:
            return _combine(mode_verdict(func, v, seen | {node.id}) for v in bound)
    return UNREADABLE


def flags_verdict(mod: F.Module, func: F.Func | None, node: ast.expr | None, seen: frozenset[str] = frozenset()) -> str:
    """Whether `os.open` flags write: any `os.O_*` write flag in the expression decides WRITE (names resolved by import,
    so `from os import O_CREAT` counts; `getattr(os, "O_NOFOLLOW", 0)` names `os.O_NOFOLLOW`; a local name is followed
    through its assignments and `|=`). Flags made only of `os.O_*` names and integers without a write flag are READ.
    Anything else in the expression (a parameter, a call) is UNREADABLE unless a write flag is already there."""
    names: set[str] = set()
    unreadable = False

    def collect(expr: ast.expr, guard: frozenset[str]) -> None:
        nonlocal unreadable
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            collect(expr.left, guard)
            collect(expr.right, guard)
        elif isinstance(expr, ast.Constant) and isinstance(expr.value, int):
            return
        elif isinstance(expr, (ast.Name, ast.Attribute)):
            dotted = mod.aliases.resolve(expr)
            if dotted is not None and dotted.startswith("os.O_"):
                names.add(dotted)
            elif isinstance(expr, ast.Name) and expr.id not in guard:
                bound = _bound_values(func, expr.id)
                if bound is None and expr.id in mod.consts:
                    bound = [mod.consts[expr.id]]
                if bound is None:
                    unreadable = True
                for value in bound or []:
                    collect(value, guard | {expr.id})
            else:
                unreadable = True
        elif (isinstance(expr, ast.Call) and mod.aliases.resolve(expr.func) == "getattr" and len(expr.args) >= 2
              and mod.aliases.resolve(expr.args[0]) == "os" and isinstance(expr.args[1], ast.Constant)
              and isinstance(expr.args[1].value, str) and expr.args[1].value.startswith("O_")):
            names.add(f"os.{expr.args[1].value}")
        else:
            unreadable = True

    if node is None:
        return READ
    collect(node, seen)
    return WRITE if names & WRITE_FLAGS else UNREADABLE if unreadable else READ


def primitive_of(mod: F.Module, call: ast.Call, func: F.Func | None = None) -> tuple[str, str, ast.expr] | None:
    """(the primitive's label, its mechanism, the destination expression) when the call is a write site, else None.
    A call whose mode or flags cannot be read has the label with `?` appended: whether it writes is not decided."""
    callee = mod.aliases.resolve(call.func)
    if callee is not None and (callee in mod.funcs or callee in mod.classes):
        callee = f"{mod.name}.{callee}"  # a function or class of this module, called by its bare name
    if callee in CALL_PRIMITIVES:
        label, index = CALL_PRIMITIVES[callee]
        if len(call.args) > index and not any(isinstance(a, ast.Starred) for a in call.args[: index + 1]):
            return label, DIRECT, call.args[index]
        return None
    if callee in ("open", "io.open"):
        mode = call.args[1] if len(call.args) > 1 else _keyword(call, "mode")
        if not call.args:
            return None
        verdict = mode_verdict(func, mode)
        return None if verdict == READ else ("open" + (UNREADABLE_MARK if verdict == UNREADABLE else ""), DIRECT,
                                             call.args[0])
    if callee == "os.open":
        flags = call.args[1] if len(call.args) > 1 else _keyword(call, "flags")
        if not call.args:
            return None
        verdict = flags_verdict(mod, func, flags)
        return None if verdict == READ else ("os.open" + (UNREADABLE_MARK if verdict == UNREADABLE else ""), DIRECT,
                                             call.args[0])
    if not isinstance(call.func, ast.Attribute):
        return None
    method, receiver = call.func.attr, call.func.value
    if method in RECEIVER_METHODS:
        return f"Path.{method}", DIRECT, receiver
    if (method in ("rename", "replace") and len(call.args) == 1 and not call.keywords
            and not isinstance(call.args[0], ast.Starred)):
        # `str.replace` takes two arguments and `datetime.replace` keywords only: one positional is a `Path` move
        return f"Path.{method}", DIRECT, call.args[0]
    if method == "open":
        # a mode in a keyword is `Path.open`'s; a first positional that is not a literal may be another API's `.open(x)`
        # (a URL opener's), so only a positional the function shows to be a mode string is read
        keyword = _keyword(call, "mode")
        arg = keyword if keyword is not None else (call.args[0] if call.args else None)
        verdict = mode_verdict(func, arg)
        if verdict == UNREADABLE and keyword is None:
            return None
        return None if verdict == READ else ("Path.open" + (UNREADABLE_MARK if verdict == UNREADABLE else ""), DIRECT,
                                             receiver)
    if method == "write" and len(call.args) >= 2 and (C.dotted(receiver) or "").split(".")[-1] == "session":
        return "session.write", STORE_TRANSACTION, call.args[0]
    return None


def primitive_labels() -> list[str]:
    """The write primitives the reading knows, by the label a writer's `via` carries: one list for the page."""
    labels = {label for label, _ in CALL_PRIMITIVES.values()}
    labels |= {f"Path.{m}" for m in RECEIVER_METHODS} | {"open", "os.open", "Path.open", "Path.rename", "Path.replace",
                                                          "session.write"}
    return sorted(labels)


def primitive_counts(program: F.Program) -> dict[str, Counter[str]]:
    """Every write-primitive call of every module (the mechanism too), by module and label: what the text reading is
    held to. No destination is read."""
    counts: dict[str, Counter[str]] = {}
    for name, mod in program.modules.items():
        scopes = [(None, mod.module_calls), *[(f, f.calls) for f in mod.funcs.values()]]
        counts[name] = Counter(hit[0] for func, calls in scopes for c in calls
                               if (hit := primitive_of(mod, c, func)) is not None)
    return counts


def sites_of(program: F.Program, evaluator: F.Evaluator) -> list[Site]:
    found = []
    for name, mod in program.modules.items():
        if name in MECHANISM_MODULES:
            continue
        scopes: list[tuple[F.Func | None, list[ast.Call]]] = [(None, mod.module_calls)]
        scopes += [(f, f.calls) for f in mod.funcs.values()]
        for func, calls in scopes:
            if func is not None and (name, func.qual) in MECHANISM_FUNCTIONS:
                continue
            for call in calls:
                hit = primitive_of(mod, call, func)
                if hit is None:
                    continue
                label, mechanism, dest = hit
                if func is None:
                    raise C.ReferenceError(
                        f"{name} writes at import time ({label}), outside any function, so the write has nothing to "
                        "anchor to: put it in a function, or extend the writers family to read module-level writes")
                values = evaluator.value(mod, func, dest)
                found.append(Site(name, func.qual, label, mechanism, ast.unparse(dest), values))
    return sorted(found, key=lambda s: (s.module, s.symbol, s.primitive, s.expr))


class Destination(NamedTuple):
    """What a site's destination values come to: the templates under ``.aew`` that it writes (by first directory:
    declared or not), whether any value is outside it, and why anything else could not be resolved."""

    templates: tuple[str, ...]  # under `.aew`, first directory declared
    undeclared: tuple[str, ...]  # under `.aew`, the first directory not in the declared set (its name)
    computed: bool  # under `.aew`, but the first directory is computed
    outside: tuple[str, ...]  # reasons
    unresolved: tuple[str, ...]  # reasons
    root: bool  # the `.aew` directory itself


def destination(site: Site, top_level: frozenset[str]) -> Destination:
    templates: set[str] = set()
    undeclared: set[str] = set()
    outside: set[str] = set()
    unresolved: set[str] = set()
    computed = root = False
    for v in sorted(site.values):
        kind, text = v
        if kind == F.STR and site.mechanism == STORE_TRANSACTION:
            kind = F.TPL  # a store transaction's path is relative to `.aew` by construction
        if kind == F.TPL:
            first = text.split("/")[0]
            if F.PLACEHOLDER in first:
                computed = True
            elif first in top_level:
                templates.add(text)
            else:
                undeclared.add(first)
        elif kind == F.ROOT:
            root = True
        elif kind == F.OUT:
            outside.add(text)
        elif kind == F.STR:
            unresolved.add(f"a relative path, `{text}`, with no root this reading can name")
        else:
            unresolved.add(text)
    return Destination(tuple(sorted(templates)), tuple(sorted(undeclared)), computed, tuple(sorted(outside)),
                       tuple(sorted(unresolved)), root)


# ------------------------------------------------------------------------------------------------------------ records

UNRESOLVED_KEY = "unresolved"  # `writers:unresolved:<module>:<symbol>:<primitive>`: a write not placed under `.aew`
POINTER_SYMBOL = None
NO_CHAIN = "no static call chain from any entry point's declaring function reaches this writer"
POINTER = ("write sites whose destination this reading could not place under `.aew` are records of this family keyed "
           "`unresolved:<module>:<symbol>:<primitive>`; any of them may write this path")


def why_unplaced(primitive: str, reason: str) -> str:
    """The one sentence an unresolved write is listed under, on its record and in ``record_problems``."""
    if primitive.endswith(UNREADABLE_MARK):
        return f"{primitive[:-1]} that may write: {reason}"
    return f"{primitive} of a path this reading cannot place: {reason}"


def _const_ref(program: F.Program, mod: F.Module, node: ast.AST) -> tuple[str, str] | None:
    """The module-level constant a name or attribute refers to: (its module, its name), by import source."""
    if isinstance(node, ast.Name) and node.id in mod.consts:
        return mod.name, node.id
    dotted = mod.aliases.resolve(node) if isinstance(node, (ast.Name, ast.Attribute)) else None
    located = program.split(dotted) if dotted else None
    if located and located[1] in program.modules[located[0]].consts:
        return located
    return None


def path_constants(program: F.Program) -> set[tuple[str, str]]:
    """The module-level constants that are used to build a path: an operand of ``/``, a part of an f-string, an argument
    of ``Path`` or ``os.path.join`` or of a write primitive. A constant that merely holds the same text (a key, a label)
    is not one."""
    used: set[tuple[str, str]] = set()
    for mod in program.modules.values():
        for node in ast.walk(mod.tree):
            roots: list[ast.AST] = []
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                roots = [node.left, node.right]
            elif isinstance(node, ast.JoinedStr):
                roots = list(node.values)
            elif isinstance(node, ast.Call):
                callee = mod.aliases.resolve(node.func)
                if callee in F.SAME_PATH_CALLS or callee in F.JOIN_CALLS or primitive_of(mod, node) is not None:
                    roots = list(node.args)
            for root in roots:
                for sub_node in ast.walk(root):
                    ref = _const_ref(program, mod, sub_node)
                    if ref is not None:
                        used.add(ref)
    return used


def named_by(program: F.Program, evaluator: F.Evaluator, top_level: frozenset[str]) -> dict[str, list[tuple[str, str]]]:
    """The module-level constants that spell a path under ``.aew`` exactly, by that path: (module, constant name)."""
    found: dict[str, list[tuple[str, str]]] = {}
    used = path_constants(program)
    for name, mod in program.modules.items():
        for const, rhs in mod.consts.items():
            if (name, const) not in used:
                continue
            values = evaluator.value(mod, None, rhs)
            if len(values) != 1:
                continue
            (kind, text), = values
            if kind in (F.STR, F.TPL) and text.split("/")[0] in top_level and text and not text.startswith("/"):
                found.setdefault(text, []).append((name, const))
    return {k: sorted(v) for k, v in found.items()}


class Writer(NamedTuple):
    module: str
    symbol: str
    mechanism: str
    via: tuple[str, ...]


class Analysis(NamedTuple):
    writers: dict[str, list[Writer]]  # template -> its writers
    unresolved: dict[tuple[str, str, str], tuple[str, str]]  # (module, symbol, primitive) -> (mechanism, reason)
    outside: dict[str, list[tuple[str, str, str]]]  # reason -> (module, symbol, primitive)
    root_sites: list[tuple[str, str, str]]  # sites that write the `.aew` directory itself
    named: dict[str, list[tuple[str, str]]]
    sites: list[Site]
    reach: dict[tuple[str, str], set[str]]  # (module, symbol) -> entry-point keys whose root reaches it
    undecided: dict[tuple[str, str], set[tuple[str, str]]]  # (module, symbol) -> the registrars of handlers reaching it
    kinds: dict[str, str]  # entry-point key -> its kind
    roles: ROLES.Roles | None  # the CLI's roles (None: the program has no CLI)
    cut: ROLES.Cut | None  # the CLI cut per role


def analyse(program: F.Program, top_level: frozenset[str], roots: dict[tuple[str, str], set[str]] | None = None,
            kinds: dict[str, str] | None = None, cli: tuple[set[tuple[str, str]], ROLES.Roles, ROLES.Cut] | None = None
            ) -> Analysis:
    """``cli`` is what cuts the CLI's roles: the functions that declare them, the roles, and the cut (``None`` when the
    program has no CLI: every root then reaches by calls alone)."""
    evaluator = F.Evaluator(program)
    sites = sites_of(program, evaluator)
    grouped: dict[str, dict[tuple[str, str, str], set[str]]] = {}
    unresolved: dict[tuple[str, str, str], tuple[str, set[str]]] = {}
    outside: dict[str, set[tuple[str, str, str]]] = {}
    root_sites: set[tuple[str, str, str]] = set()
    for site in sites:
        if site.primitive.endswith(UNREADABLE_MARK):  # whether it writes is not decided: unresolved, placed nowhere
            entry = unresolved.setdefault((site.module, site.symbol, site.primitive), (site.mechanism, set()))
            entry[1].add(UNREADABLE_WHY)
            continue
        d = destination(site, top_level)
        for template in d.templates:
            grouped.setdefault(template, {}).setdefault((site.module, site.symbol, site.mechanism), set()).add(
                site.primitive)
        reasons = [*d.unresolved]
        reasons += [f"under `.aew` in `{first}`, which is not in the declared set" for first in d.undeclared]
        if d.computed:
            reasons.append("under `.aew`, but its first directory or file name is computed")
        for reason in reasons:
            entry = unresolved.setdefault((site.module, site.symbol, site.primitive), (site.mechanism, set()))
            entry[1].add(reason)
        for reason in d.outside:
            outside.setdefault(reason, set()).add((site.module, site.symbol, site.primitive))
        if d.root:
            root_sites.add((site.module, site.symbol, site.primitive))
    writers = {t: [Writer(m, s, mech, tuple(sorted(via))) for (m, s, mech), via in sorted(by.items())]
               for t, by in sorted(grouped.items())}
    cli_roots, roles, cut = cli if cli is not None else (set(), None, ROLES.Cut([], {}, {}))
    reached = R.reached_from(program, roots or {}, cli_roots, cut)
    return Analysis(writers, {k: (m, "; ".join(sorted(r))) for k, (m, r) in sorted(unresolved.items())},
                    {k: sorted(v) for k, v in sorted(outside.items())}, sorted(root_sites),
                    named_by(program, evaluator, top_level), sites, reached.entry_points, reached.undecided,
                    dict(kinds or {}), roles, cut if cli is not None else None)


def derived_top_level(sites: list[Site]) -> set[str]:
    """The first entries of the paths under ``.aew`` that the sites write (a computed first entry is not one): what
    :data:`TOP_LEVEL` is held to, both ways."""
    return {first for site in sites if not site.primitive.endswith(UNREADABLE_MARK)
            for first in destination(site, frozenset()).undeclared}


UNDECIDED_WHY = ("a handler registered here is of a command this reading cannot read from the parser, so which of the "
                 "CLI's roles runs the writers it reaches is not decided, and it counts as run by every role")
GATE_SYMBOL = ("aew.process_kind", "require_writer")


def store_class(directory: str, mechanism: str) -> bool:
    """Whether a write is to the store: staged by the store's transaction, or direct under a directory other than
    ``local/`` (the rebuildable data kept out of git). A path prefix and a mechanism tell them apart; no field says
    it."""
    return mechanism == STORE_TRANSACTION or directory != LOCAL


def gated(keys: Iterable[str], roles: ROLES.Roles | None) -> bool:
    """Whether the worker role may reach this writer without the call graph saying so: the general handlers reach it
    and the worker role (chosen by the environment, not by a command) is not already given it. The call graph gives
    that role nothing, so its absence from ``entry_points`` is no evidence, whatever the writer writes."""
    return roles is not None and roles.general in set(keys) and roles.worker not in set(keys)


# The run-time test of the gate, in tests/integration/test_non_writer_reads.py (a tree test holds that it exists).
GATE_TEST = "test_no_command_a_worker_can_run_writes_under_aew_or_takes_the_lock"


def gate_item(roles: ROLES.Roles) -> dict[str, Any]:
    return C.unresolved_item(*GATE_SYMBOL, (
        f"the role `{roles.worker}` is chosen by an environment variable and not by a command, so the call graph "
        "attributes no handler to it, and its absence from `entry_points` says nothing; a write a non-writer process "
        "may not make is refused by `process_kind.require_writer` (at the control lock, and before an operation whose "
        f"purpose is such a write), tested at run time by `{GATE_TEST}` and not proved here"))


def undecided_item(registrar: tuple[str, str]) -> dict[str, Any]:
    return C.unresolved_item(registrar[0], registrar[1] or None, UNDECIDED_WHY)


def pointer_item() -> dict[str, Any]:
    return C.unresolved_item("aew", POINTER_SYMBOL, POINTER)


def records_of(analysis: Analysis) -> list[C.Record]:
    records = []
    pointer = pointer_item()
    for template, writers in analysis.writers.items():
        owners = analysis.named.get(template, [])
        anchor_module, anchor_symbol = owners[0] if owners else (writers[0].module, writers[0].symbol)
        items = []
        unreached = []
        for w in writers:
            keys = sorted(analysis.reach.get((w.module, w.symbol), ()))
            items.append({"module": w.module, "symbol": w.symbol, "mechanism": w.mechanism, "via": list(w.via),
                          "entry_points": keys, "entry_kinds": sorted({analysis.kinds[k] for k in keys})})
            if not keys:
                unreached.append(C.unresolved_item(w.module, w.symbol, NO_CHAIN))
            unreached += [undecided_item(r) for r in sorted(analysis.undecided.get((w.module, w.symbol), ()))]
            if analysis.roles is not None and gated(keys, analysis.roles):
                unreached.append(gate_item(analysis.roles))
        fact = {
            "prefix": template,
            "directory": template.split("/")[0],
            "named_by": [{"module": m, "symbol": n} for m, n in owners],
            "writers": items,
        }
        records.append(C.Record(FAMILY, template, anchor_module, anchor_symbol, "static", C.lower_bound([pointer]),
                                fact, fact_coverage={"named_by": C.lower_bound(),
                                                     "writers": C.lower_bound([pointer, *unreached])}))
    for (module, symbol, primitive), (mechanism, reason) in analysis.unresolved.items():
        item = C.unresolved_item(module, symbol, why_unplaced(primitive, reason))
        records.append(C.Record(FAMILY, f"{UNRESOLVED_KEY}:{module}:{symbol}:{primitive}", module, symbol, "static",
                                C.lower_bound([item]),
                                {"primitive": primitive, "mechanism": mechanism, "reason": reason}))
    return records


WRITER_KEYS = {"module", "symbol", "mechanism", "via", "entry_points", "entry_kinds"}


def record_problems(records: Mapping[str, Any], kinds: Mapping[str, str], roles: ROLES.Roles | None = None,
                    undecided: Mapping[tuple[str, str], Iterable[tuple[str, str]]] | None = None) -> list[str]:
    """The family's own invariants over its records as JSON (``Record.as_json`` keyed by id), which the index checks do
    not know: a writer's mechanism is one of two, its primitives are named, its entry points are rows of the owner's
    table and its kinds are theirs, a writer that the general CLI handlers reach and the worker role is not given
    says on its record that the call graph gives that role nothing, a writer behind a handler of a command not read
    says which function registers it, and every path record points at the unresolved ones. ``kinds`` is the owner's
    table (entry-point key -> kind), ``roles`` the CLI's roles and ``undecided`` the registering functions that reach
    each writer function."""
    problems: list[str] = []
    pointer = pointer_item()
    for rid, r in sorted(records.items()):
        if r.get("family") != FAMILY:
            continue
        fact, anchor = r.get("fact") or {}, r.get("anchor") or {}
        key = rid.removeprefix(f"{FAMILY}:")
        if key.startswith(UNRESOLVED_KEY + ":"):
            expect = f"{UNRESOLVED_KEY}:{anchor.get('module')}:{anchor.get('symbol')}:{fact.get('primitive')}"
            if key != expect:
                problems.append(f"{rid}: the key is not {expect}")
            if set(fact) != {"primitive", "mechanism", "reason"} or not all(
                    isinstance(v, str) and v for v in fact.values()):
                problems.append(f"{rid}: an unresolved write has a primitive, a mechanism and a reason, all non-empty")
                continue
            if fact["mechanism"] not in (STORE_TRANSACTION, DIRECT):
                problems.append(f"{rid}: mechanism {fact['mechanism']!r} is not one of the two")
            item = C.unresolved_item(anchor.get("module", ""), anchor.get("symbol"),
                                     why_unplaced(fact["primitive"], fact["reason"]))
            if (r.get("coverage") or {}).get("unresolved") != [item]:
                problems.append(f"{rid}: its coverage does not carry its own reason as the one unresolved item")
            continue
        if fact.get("prefix") != key or fact.get("directory") != key.split("/")[0]:
            problems.append(f"{rid}: prefix and directory are not the key and its first entry")
        writers = fact.get("writers")
        if not isinstance(writers, list) or not writers:
            problems.append(f"{rid}: a path record has at least one writer")
            continue
        for w in writers:
            if not isinstance(w, dict) or set(w) != WRITER_KEYS:
                problems.append(f"{rid}: a writer is not {sorted(WRITER_KEYS)}: {w!r}")
                continue
            if w["mechanism"] not in (STORE_TRANSACTION, DIRECT):
                problems.append(f"{rid}: {w['module']}:{w['symbol']} has mechanism {w['mechanism']!r}")
            if not w["via"] or w["via"] != sorted(set(w["via"])):
                problems.append(f"{rid}: {w['module']}:{w['symbol']} names no primitives, or not sorted")
            if w["entry_points"] != sorted(set(w["entry_points"])) or any(k not in kinds for k in w["entry_points"]):
                problems.append(f"{rid}: {w['module']}:{w['symbol']} names an entry point that is not in the table")
            elif w["entry_kinds"] != sorted({kinds[k] for k in w["entry_points"]}):
                problems.append(f"{rid}: {w['module']}:{w['symbol']} has entry kinds that are not its entry points'")
        for name in ("named_by", "writers"):
            if name not in (r.get("fact_coverage") or {}):
                problems.append(f"{rid}: no fact_coverage for {name}")
        listed = ((r.get("fact_coverage") or {}).get("writers") or {}).get("unresolved", [])
        if pointer not in listed:
            problems.append(f"{rid}: its writers do not point at the unresolved writes")
        for w in writers:
            if not isinstance(w, dict) or set(w) != WRITER_KEYS:
                continue
            where = f"{rid}: {w['module']}:{w['symbol']}"
            for registrar in sorted((undecided or {}).get((w["module"], w["symbol"]), ())):
                if undecided_item(registrar) not in listed:
                    problems.append(f"{where} is behind a handler registered in {registrar[0]}:{registrar[1]} for a "
                                    "command this reading could not read, and the record does not say so")
            if roles is not None and gated(w["entry_points"], roles):
                if gate_item(roles) not in listed:
                    problems.append(f"{where} is reached by the general handlers and not the worker role, and the "
                                    "record does not say that the call graph gives that role nothing")
        if (r.get("coverage") or {}).get("unresolved") != [pointer]:
            problems.append(f"{rid}: its coverage does not point at the unresolved writes")
    return problems


# ---------------------------------------------------------------------------------------------------------- the page

def _anchor(module: str, symbol: str | None) -> str:
    return f"`{module}:{symbol}`" if symbol else f"`{module}`"


NON_WRITER = "non_writer"


def role_reach(analysis: Analysis, records: list[C.Record]
               ) -> tuple[dict[str, set[tuple[str, str]]], dict[str, set[tuple[str, str]]]]:
    """Per entry point, the writer functions it reaches that write the store, and those that write only under ``local/``
    (a function is in the first when any of its writes is a store write)."""
    store: dict[str, set[tuple[str, str]]] = {key: set() for key in sorted(analysis.kinds)}
    local: dict[str, set[tuple[str, str]]] = {key: set() for key in sorted(analysis.kinds)}
    for r in records:
        for w in (r.fact or {}).get("writers", []):
            for key in w["entry_points"]:
                (store if store_class((r.fact or {})["directory"], w["mechanism"]) else local)[key].add(
                    (w["module"], w["symbol"]))
    return store, {key: found - store[key] for key, found in local.items()}


def reach_lines(analysis: Analysis, records: list[C.Record]) -> list[str]:
    store, local = role_reach(analysis, records)
    writer_functions = {(w["module"], w["symbol"]) for r in records for w in (r.fact or {}).get("writers", [])}
    reached = {fn for found in (*store.values(), *local.values()) for fn in found}
    non_writers = [key for key in sorted(analysis.kinds) if analysis.kinds[key] == NON_WRITER]
    flagged = sorted({fn for key in non_writers for fn in store[key]})
    permitted = sorted({fn for key in non_writers for fn in local[key]})
    lines = ["## Which entry points reach the writers", "",
             "A chain of resolved calls from the function where an entry point declares itself (see "
             "[entry-points.md](entry-points.md)), so a writer's `entry_points` is a lower bound: a callback, or a "
             "call on an object whose class is not evident, is not followed. The CLI declares its roles in one "
             "function and the command decides which runs, so the parser cuts them: the handler a command registers "
             "is reached by the role of that command (what `process_kind.cli_entry_point` says of its words), and the "
             "calls the CLI's function makes itself, which every command shares, by all of them. The role the "
             "environment selects is no command's: the call graph gives it nothing, and a write a non-writer may "
             "not make is refused there by `process_kind.require_writer`, a gate tested at run time and not proved "
             "here.", "",
             "A `with` statement's implicit `__enter__` and `__exit__` calls are not followed either, so what a "
             "context manager writes is attributed only to the roles that call it by name: the dashboard server takes "
             f"its own lock file by `with self._lock():` (`{WITH_CASE[0]}:{WITH_CASE[1]}`), and "
             + " and ".join(f"`{key}`" for key in WITH_CASE[2])
             + " are listed under `aew` alone. The counts of writer functions reached below are lower bounds.", ""]
    cut = analysis.cut
    if cut is not None and analysis.roles is not None:
        roles = analysis.roles
        named = ", ".join(f"`{role}`: {len(cut.handlers.get(role, ()))}" for role in sorted(roles.all - {roles.worker}))
        undecided = sorted(cut.undecided)
        nameless = sorted({r.registrar for r in cut.registrations if not r.handlers})

        def where(found: list[tuple[str, str]]) -> str:
            return ", ".join(_anchor(m, s or None) for m, s in found) if found else "none"

        lines += [f"The parser cut: {len(cut.registrations)} registrations of a command handler; handlers by role "
                  f"({named}; `{roles.worker}`: none, by the environment). Registrations of a command this reading "
                  f"cannot read: {where(undecided)}"
                  + (" (their handlers count as run by every role, and the writers behind them say so)"
                     if undecided else "")
                  + f". Registrations whose handler is no function this reading can name: {where(nameless)}.", ""]
    lines += [f"Writer functions with a store-transaction or direct write placed under `.aew`: "
              f"{len(writer_functions)}; reached from at least one entry point: {len(reached)}.", ""]
    for key in sorted(analysis.kinds):
        lines.append(f"- `{key}` ({analysis.kinds[key]}): {len(store[key] | local[key])} writer functions "
                     f"({len(store[key])} write the store, {len(local[key])} only under `local/`)")
    found = "none." if not flagged else ", ".join(_anchor(m, s) for m, s in flagged)
    allowed = "none." if not permitted else ", ".join(_anchor(m, s) for m, s in permitted)
    lines += ["", "**Checked:** a store write (a store-transaction writer, or a direct writer under a directory other "
              "than `local/`) reached from an entry point of kind `non_writer` ("
              + ", ".join(f"`{k}`" for k in non_writers) + f"): {found}",
              "**Permitted:** writers under `local/` reached from those entry points. `local/` is rebuildable "
              "runtime data kept out of git (`AEW_GITIGNORE`), and the check is keyed on the path prefix and the "
              f"mechanism: {allowed}",
              "**Not checked:** a handler that calls its engine method by a name held in a variable, and a `with` "
              "statement's implicit calls, are not followed, so the writers behind them are not attributed to the "
              "role that runs them; and what the worker role may write is "
              "`process_kind.require_writer`'s to refuse (above), not this reading's to prove.", ""]
    return lines


def cap_lines(caps: Iterable[F.Cap]) -> list[str]:
    lines = ["## Caps of the reading", "",
             "Each cap bounds how far one thing is followed, and names where its number comes from. Past a cap the "
             "reading says so: the reason is on the unresolved write, or the writer carries the no-chain item, or the "
             "registration counts as run by every role. A tree test doubles every cap and holds this page and "
             "`index.json` unchanged, so no record of this tree is lost to a cap. A refusal that lists problems is cut "
             "at a number of lines and says how many it left out, and an expression quoted in a reason is cut with "
             "`...`: those are not caps on what the reading follows.", ""]
    for cap in caps:
        measured = "" if cap.measured is None else f" The largest in this tree: {cap.measured}."
        lines.append(f"- `{cap.name}` = {cap.value}: {cap.bounds}; source: {cap.source}; "
                     f"past it: {cap.past}.{measured}")
    return [*lines, ""]


def page(analysis: Analysis, records: list[C.Record], top_level: tuple[str, ...],
         caps: Iterable[F.Cap] | None = None) -> str:
    lines = [
        "# Writers", "",
        "Every path under `.aew` that AEW code writes, and the module and function that writes it. Generated by "
        "`python tools/reference.py render`; do not edit. Read from the source with `ast` and run nowhere (`static`): "
        "a write is a call of a write primitive whose destination this reading follows to a path under `.aew` "
        "(through assignments, constants, `self` attributes, parameters and the functions that build paths). A path is "
        "a template: `{}` is a segment computed at run time. `named_by` lists the module-level constants that spell "
        "the path exactly. A writer's `mechanism` is `store-transaction` (it stages the file in the control store's "
        "transaction, which the store applies under the control lock) or `direct`; `via` names the primitives.", "",
        "The list is a lower bound. A write whose destination this reading could not place is its own record, below "
        "and in [gaps.md](gaps.md), and any of those may write any path here. A call whose `open` mode or `os.open` "
        "flags cannot be read is one of those records too (its primitive ends in `?`): whether it writes is not "
        "decided. The primitives it reads: " + ", ".join(f"`{label}`" for label in primitive_labels()) + ". "
        "What this reading does not see: " + "; ".join(text for _, text in CANNOT_SEE) + ".", "",
        "A sibling of a path (`with_name`, `with_suffix`, `with_stem`) is a path of its own when its name is a fixed "
        "string, or the path's own name, suffix or stem with a fixed string added "
        "(`p.with_name(p.name + \".queue\")`). A name made by the process (a process or thread id, a clock, a random "
        "value, `tempfile`) is part of the write protocol of its path and is taken as that path, as is an f-string "
        "that starts with the path (`f\"{path}.tmp\"`). Any other name is a write this reading cannot place.", ""]
    by_dir: dict[str, list[C.Record]] = {}
    for r in records:
        if r.fact and r.fact.get("prefix"):
            by_dir.setdefault(r.fact["directory"], []).append(r)
    for directory in top_level:
        items = sorted(by_dir.get(directory, []), key=lambda r: r.key)
        if not items:
            continue
        lines += [f"## `{directory}`", ""]
        for r in items:
            fact = r.fact or {}
            named = ", ".join(_anchor(n["module"], n["symbol"]) for n in fact["named_by"])
            who = "; ".join(f"{_anchor(w['module'], w['symbol'])} ({w['mechanism']}: {', '.join(w['via'])})"
                            for w in fact["writers"])
            lines.append(f"- `{r.key}`" + (f", named by {named}" if named else "") + f": written or removed by {who}")
        lines.append("")
    lines += reach_lines(analysis, records)
    lines += cap_lines((*F.caps(), *ROLES.caps()) if caps is None else caps)
    unresolved = sorted((r for r in records if r.key.startswith(UNRESOLVED_KEY + ":")), key=lambda r: r.key)
    lines += ["## Writes this reading could not place", ""]
    if unresolved:
        for r in unresolved:
            fact = r.fact or {}
            lines.append(f"- {_anchor(r.module, r.symbol)} ({fact['mechanism']}: {fact['primitive']}): "
                         f"{fact['reason']}")
    else:
        lines.append("None.")
    lines += ["", "## Writes outside `.aew`", "",
              "Write sites whose destination this reading follows to a place outside `.aew`: listed so that nothing is "
              "dropped unseen. A site that also writes a path under `.aew` is a record there too.", ""]
    for reason, sites in analysis.outside.items():
        lines.append(f"- {reason}: " + ", ".join(f"{_anchor(m, s)} ({p})" for m, s, p in sites))
    if analysis.root_sites:
        lines += ["", "The `.aew` directory itself (a directory is created or its parent listed, not a path under it): "
                  + ", ".join(f"{_anchor(m, s)} ({p})" for m, s, p in analysis.root_sites)]
    return "\n".join(lines).rstrip("\n") + "\n"


def build(ctx: C.Context) -> C.Built:
    from aew import process_kind  # the owner of the entry points' kinds, at run time (reference.py checked the tree)

    trees = {name: (src.tree, src.is_package) for name, src in ctx.sources().items() if src.tree is not None}
    kinds = {key: kind for key, (kind, _why) in process_kind.ENTRY_POINTS.items()}
    program = F.Program.of(trees)
    with F.measuring() as peaks:
        analysis = analyse(program, frozenset(TOP_LEVEL), R.roots_of(ctx, set(kinds)), kinds, R.cli_of(ctx, program))
    records = records_of(analysis)
    problems = record_problems({r.id: r.as_json() for r in records}, kinds, analysis.roles, analysis.undecided)
    if problems:
        raise C.ReferenceError("the writers records break their own rules:\n  " + "\n  ".join(C.shown(problems)))
    caps = (*F.caps(peaks), *ROLES.caps())
    return C.Built(records=records, pages={"writers.md": page(analysis, records, TOP_LEVEL, caps)})
