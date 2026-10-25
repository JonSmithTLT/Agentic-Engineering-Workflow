"""Where a path expression points: the value-flow reading behind the ``writers`` family (STG-12 S12-2, DOC-01).

A write primitive names its destination as an expression (``root / STORE_REL``, ``path``, ``self.path``,
``cold_rel(subject)``). This module evaluates such an expression to the set of values it can take, reading the source
with ``ast`` and nothing else: no module is imported and nothing runs. A value is one of

* ``ROOT``: the ``.aew`` directory itself;
* ``TPL``: a path under it, as a template (``state/log``, ``work/{}/completion.md``: ``{}`` is a computed segment);
* ``STR``: a plain string that is not (yet) known to be a path under ``.aew``;
* ``OUT``: a path known to be outside it (a temporary directory, the device null, a console);
* ``UNK``: unknown, with the reason. Never a guess.

What it follows, each to a bounded depth: a name bound in the function (every assignment, so a union), a module
constant (its own, or the owner's by import source), a ``self`` attribute (every ``self.x = ...`` in the class), a
parameter (the arguments of every static call of the function, and of the class's constructor for ``__init__``), and a
call of an AEW function (the function's ``return`` expressions, with the arguments bound). A computed first segment, a
call on an object whose class is unknown, a name nothing binds and an expression this module does not model are
``UNK``: the caller lists them.

``.aew`` is recognised from the root expression, not from the string alone: a name or attribute spelled ``aew_root``,
or any path joined with a string that evaluates to ``.aew`` (the owner's ``AEW_DIR``). A relative string is a path
under ``.aew`` only where the primitive's own meaning makes it one (the store transaction's ``write(path, ...)``).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import NamedTuple

from reference_families import common as C

ROOT, TPL, STR, OUT, UNK = "root", "tpl", "str", "out", "unk"
AEW_DIRECTORY = ".aew"
ROOT_NAME = "aew_root"  # the repository's spelling of the .aew directory (checked by the family's convention test)
REPO_NAME = "repo_root"  # the repository's working tree: a path under it is outside `.aew`
WORKSPACES_NAME = "workspaces_root"  # the directory of the task workspaces (a method of the kernel): outside `.aew`
# The caps of the reading. Each bounds how far one thing is followed, and past it the reading takes one of two arms
# (addendum 7): a marked item (a value is UNK with the cap in its reason, so the site is an unresolved write; a call is
# not followed, so a writer reached only through it carries the no-chain item; the roles reader counts a registration as
# run by every role) or, where what the cap bounds can carry no mark, it fails `check` and `render` with an error that
# names the cap. `caps()` is the one list, with the arm of each, written on the page. A tree test doubles every cap and
# holds the generated reference unchanged (no record is lost to a cap), and another finds every cap or slice of the
# generator that is not listed (the sweep).
# The measured caps are measured over the whole render, every family that runs the evaluator (writers, layout,
# concurrency, ...), and not over the writers family alone: `reference.py` runs them under one `measuring()`, the
# writers page prints the figures, and a tree test holds each cap to at least twice its figure (review of #267, C-1).
# Calls and parameters followed in a chain (the run directory a supervisor is handed through the harness, and the
# layout's reads). It was 14 while a depth cut under a join read as a computed segment and hid how deep the tree goes
# (addendum 6).
DEPTH = 32
CALLERS = 24  # call sites of one function that are evaluated; more is UNK
# Distinct values one expression may take before it is UNK, so a set that grows toward the cap is a decision and not a
# record silently lost. 64 since CAP-1 (STG-15): its schema made `aew.schemas.SCHEMAS`' file names the largest set,
# 31, and the tree test holds the cap to twice that.
VALUES = 64
PLACEHOLDER = "{}"
# Receivers typed through receivers (`self.a.b.run()`, `Class().m().n()`): a call edge past it would be dropped as if
# the receiver were unknown, so the reading fails instead (addendum 7). A receiver whose typing needs itself is a cycle
# and is unknown, not a depth.
TYPING_DEPTH = 24
# Base classes followed from a class to find where an attribute or method is defined; past it the reading fails
# (addendum 7).
MRO_DEPTH = 6
# Alternatives of one f-string piece (`f"{kind}.md"` with `kind` one of N strings) expanded into N templates; more is
# unknown, with the cap in its reason (review of the placement pull request, F2).
FSTRING_LIMIT = 8
# Assignments followed through names to see whether a sibling's name is made by the process (`_process_computed`).
# Chosen: the tree follows none, so nothing measures it (review of #267, C-7).
ASSIGNMENT_DEPTH = 3
UTIL_MODULE = "aew.util"

# Callees that return their argument's path unchanged, or a sibling of it: by where they were imported from.
SAME_PATH_CALLS = frozenset({"pathlib.Path", "pathlib.PurePath", "pathlib.PurePosixPath", "pathlib.PosixPath",
                             "pathlib.PureWindowsPath", "pathlib.WindowsPath", "Path", "str", "os.fspath",
                             "os.path.abspath", "os.path.realpath", "os.path.normpath", "os.path.expanduser",
                             "os.path.expandvars"})
JOIN_CALLS = frozenset({"os.path.join", "posixpath.join", "ntpath.join"})
# These return the path itself.
SAME_PATH_METHODS = frozenset({"resolve", "absolute", "expanduser", "as_posix"})
# A sibling whose name is made by the process (a temporary file named by its process id) is taken as the same path:
# it is part of the write protocol of the path it came from. A sibling with a fixed name (`with_name("endpoint.lock")`,
# `.name + ".queue"`, `with_suffix(".tmp")`) is a file of its own and is evaluated as one. Any other is unplaced.
SIBLING_PART = {"with_name": "name", "with_suffix": "suffix", "with_stem": "stem"}  # the part of a path each replaces
SIBLING_METHODS = frozenset(SIBLING_PART)
# Callees whose result is made by the process, so a name built from one is a temporary of the path it came from.
PROCESS_CALLS = frozenset({"os.getpid", "threading.get_ident", "threading.get_native_id", "uuid.uuid1", "uuid.uuid4",
                           "time.time", "time.time_ns", "time.monotonic", "time.monotonic_ns", "random.getrandbits",
                           "secrets.token_hex", "secrets.token_urlsafe"})
TEMP_CALLS = frozenset({"tempfile.mkdtemp", "tempfile.gettempdir", "tempfile.mkstemp", "tempfile.TemporaryDirectory",
                        "tempfile.NamedTemporaryFile", "tempfile.mktemp"})
# Strings that name a place outside `.aew` and are not absolute paths.
OUTSIDE_LITERALS = {"CONOUT$": "the Windows console", "CONIN$": "the Windows console", "nul": "the Windows null device",
                    ":memory:": "an in-memory database"}


class Val(NamedTuple):
    kind: str
    text: str  # the template (ROOT: ""), or for OUT and UNK the reason


Values = frozenset[Val]


def unk(why: str) -> Values:
    return frozenset({Val(UNK, why)})


def one(kind: str, text: str = "") -> Values:
    return frozenset({Val(kind, text)})


class Cut(Exception):
    """A cap was reached where nothing can hold the mark (the functions an expression can be, not a value): whoever
    asked turns it into an unknown value with this reason."""


CAP_MARK = " (cap `"  # every reason a cap makes carries it: `cap_reason` writes it, `is_cap` reads it


def cap_reason(name: str, detail: str) -> str:
    """The reason of a value a cap stopped: what was cut, then the cap, its number and where the number comes from
    (from :func:`caps`). A reason that said only "computed" where a cap stopped the reading would name a false cause
    (the designer's addendum 6 to the S12-2 hand-off)."""
    cap = next(c for c in caps() if c.name == f"writers_flow.{name}")
    return f"{detail}{CAP_MARK}{cap.name}` = {cap.value}: {cap.source})"


def is_cap(reason: str) -> bool:
    return CAP_MARK in reason


def depth_reason() -> str:
    return cap_reason("DEPTH", f"resolution depth limit: more than {DEPTH} calls or parameters to follow")


def depth_limit() -> Values:
    return unk(depth_reason())


def cap_unknowns(values: Values | set[Val]) -> set[Val]:
    """The values among ``values`` that a cap stopped. A join, a sum or a format that turns an unknown part into a
    computed one keeps these, so the reason stays the cap's and not "computed"."""
    return {v for v in values if v.kind == UNK and is_cap(v.text)}


_peak: dict[str, int] | None = None
# What `measuring()` records: the figure of each measured cap.
MEASURED = ("depth", "values", "alternatives", "mro", "typing", "assignments")


@contextmanager
def measuring() -> Iterator[dict[str, int]]:
    """Record, while the block runs, the largest figure of each measured cap (the figures the page and the tree tests
    report): the size of a value set, of the alternatives of an f-string piece, the longest chain of bases, the longest
    chain of assignments. A block inside another records into the outer one."""
    global _peak
    if _peak is not None:
        yield _peak
        return
    _peak = dict.fromkeys(MEASURED, 0)
    try:
        yield _peak
    finally:
        _peak = None


def _note(figure: str, size: int) -> None:
    if _peak is not None:
        _peak[figure] = max(_peak[figure], size)


def capped(values: set[Val] | Values) -> Values:
    _note("values", len(values))
    if len(values) > VALUES:
        return unk(cap_reason("VALUES", f"more than {VALUES} possible values of one expression"))
    return frozenset(values)


MARKED, FAILS = "a marked item", "fails check"  # the two arms past a cap (addendum 7); a cap takes exactly one


class Cap(NamedTuple):
    name: str  # the constant
    value: int
    bounds: str  # what it bounds
    source: str  # where the number comes from
    past: str  # what the reading does past it
    measured: int | None = None  # the largest the tree reaches, where the reading measures it
    arm: str = MARKED  # MARKED: an item says so; FAILS: `check` and `render` stop with an error that names the cap


def caps(peaks: Mapping[str, int] | None = None) -> tuple[Cap, ...]:
    """The caps of the value flow and the call graph, from the constants themselves."""

    def peak(figure: str) -> int | None:
        return None if peaks is None else peaks[figure]

    return (
        Cap("writers_flow.DEPTH", DEPTH, "the calls and parameters one value is followed through",
            "measured over the whole render, held to twice the deepest question", "the value is unknown, with the "
            "reason `resolution depth limit` and this cap; the keys of a mapping a callback returns are unknown with "
            "the same reason", peak("depth")),
        Cap("writers_flow.CALLERS", CALLERS,
            "the call sites of one function whose parameter, mapping keys or callback is read", "chosen",
            "the parameter is unknown, with a reason that says `more than N call sites` and names this cap (the roles "
            "reader counts the registration as run by every role)"),
        Cap("writers_flow.VALUES", VALUES, "the distinct values one expression may take",
            "measured over the whole render, held to twice the largest", "the expression is unknown, with a reason "
            "that says `more than N possible values` and names this cap", peak("values")),
        Cap("writers_flow.TYPING_DEPTH", TYPING_DEPTH,
            "the receivers typed through receivers (`self.a.b.run()`)",
            "measured over the whole render, held to twice the deepest typing",
            "a dropped call edge would read as an unknown receiver and can carry no mark, so the reading stops: "
            "`check` and `render` fail with an error that names this cap, its source and its bound", peak("typing"),
            FAILS),
        Cap("writers_flow.MRO_DEPTH", MRO_DEPTH,
            "the base classes followed from a class to find where an attribute or a method is defined",
            "measured over the whole render, held to twice the longest chain",
            "a list of classes can carry no mark, so the reading stops: `check` and `render` fail with an error that "
            "names this cap, its source and its bound, and a tree test warns before the tree needs half of it",
            peak("mro"), FAILS),
        Cap("writers_flow.FSTRING_LIMIT", FSTRING_LIMIT,
            "the alternatives of one f-string piece that are expanded into templates",
            "measured over the whole render, held to twice the largest",
            "the expression is unknown, with a reason that says `more than N alternatives of one f-string piece` and "
            "names this cap", peak("alternatives")),
        Cap("writers_flow.ASSIGNMENT_DEPTH", ASSIGNMENT_DEPTH,
            "the assignments followed through names to see whether a sibling's name is made by the process",
            "chosen: the tree follows none",
            "the sibling is an unresolved write, with a reason that says `more than N assignments` and names this "
            "cap"),
    )


# ------------------------------------------------------------------------------------------------------ the program

@dataclass(eq=False)
class Func:
    module: str
    qual: str  # `Class.method`, `outer.inner` or `name`
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda  # a ClassDef: a dataclass's `__init__`
    cls: str | None  # the innermost enclosing class, for `self`
    parent: Func | None  # the enclosing function, for a closure
    params: list[str]
    assigns: dict[str, list[ast.expr]] = field(default_factory=dict)
    opaque: set[str] = field(default_factory=set)  # names bound by `with ... as`, an unpacking, `except ... as`
    loops: dict[str, list[ast.expr]] = field(default_factory=dict)  # `for name in <iterable>`
    withs: dict[str, list[ast.expr]] = field(default_factory=dict)  # `with <context> as name`
    appends: dict[str, list[ast.expr]] = field(default_factory=dict)  # `name.append(<element>)`
    subkeys: dict[str, list[ast.expr]] = field(default_factory=dict)  # `name[<key>] = ...`
    augs: dict[str, list[ast.expr]] = field(default_factory=dict)  # `name |= value`, `name += value`
    unpacks: dict[str, list[tuple[int, ast.expr]]] = field(default_factory=dict)  # `for a, b in <literal>`: (index, it)
    key_loops: dict[str, list[ast.expr]] = field(default_factory=dict)  # `for name, _ in <mapping>.items()`
    returns: list[ast.expr] = field(default_factory=list)
    calls: list[ast.Call] = field(default_factory=list)
    defaults: dict[str, ast.expr] = field(default_factory=dict)
    annotations: dict[str, ast.expr] = field(default_factory=dict)  # parameter name -> its annotation
    returns_annotation: ast.expr | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.module, self.qual)


@dataclass(eq=False)
class Module:
    name: str
    is_package: bool
    tree: ast.Module
    aliases: C.Aliases
    consts: dict[str, ast.expr] = field(default_factory=dict)
    funcs: dict[str, Func] = field(default_factory=dict)
    classes: set[str] = field(default_factory=set)
    bases: dict[str, list[ast.expr]] = field(default_factory=dict)
    handlers: dict[int, Func] = field(default_factory=dict)  # a `set_defaults(handler=lambda ...)`, by the lambda's id
    attrs: dict[tuple[str, str], list[tuple[Func | None, ast.expr]]] = field(default_factory=dict)
    module_calls: list[ast.Call] = field(default_factory=list)  # calls outside any function
    argv_lists: list[tuple[Func | None, ast.List]] = field(default_factory=list)  # list literals holding a `--flag`


def _is_flag(node: ast.expr) -> bool:
    """A string literal that spells a command-line flag (``--run-dir``)."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith("--")


def _targets(node: ast.expr) -> list[ast.Name]:
    if isinstance(node, ast.Name):
        return [node]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [n for e in node.elts for n in _targets(e)]
    if isinstance(node, ast.Starred):
        return _targets(node.value)
    return []


class _Scan(ast.NodeVisitor):
    """One walk of a module: its constants, functions (with their assignments, returns and calls), classes and the
    ``self`` attributes each class assigns."""

    def __init__(self, mod: Module) -> None:
        self.mod = mod
        self.func: Func | None = None
        self.cls: list[str] = []
        self.handler_count: dict[str, int] = {}  # function -> the handler lambdas numbered so far

    # -- scopes
    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        outer = self.func
        qual = ".".join([*self.cls, node.name]) if outer is None else f"{outer.qual}.{node.name}"
        a = node.args
        positional = [x.arg for x in (*a.posonlyargs, *a.args)]
        params = [*positional, *([a.vararg.arg] if a.vararg else []), *[x.arg for x in a.kwonlyargs],
                  *([a.kwarg.arg] if a.kwarg else [])]
        defaults = dict(zip(reversed(positional), reversed(a.defaults), strict=False))
        defaults.update({x.arg: d for x, d in zip(a.kwonlyargs, a.kw_defaults, strict=True) if d is not None})
        func = Func(self.mod.name, qual, node, self.cls[-1] if self.cls and outer is None else
                    (outer.cls if outer else None), outer, params, defaults=defaults,
                    annotations={x.arg: x.annotation for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)
                                 if x.annotation is not None},
                    returns_annotation=node.returns)
        self.mod.funcs[qual] = func
        self.func = func
        for stmt in node.body:
            self.visit(stmt)
        self.func = outer

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.func is None and not self.cls:
            self.mod.classes.add(node.name)
        else:
            self.mod.classes.add(".".join([*self.cls, node.name]))
        self.mod.bases[".".join([*self.cls, node.name])] = list(node.bases)
        self.cls.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self._dataclass_init(node)
        self.cls.pop()

    def _dataclass_init(self, node: ast.ClassDef) -> None:
        """A ``@dataclass`` without its own ``__init__``: the fields are the constructor's parameters, in order, and
        each ``self.field`` is the parameter of that name."""
        mod = self.mod
        qual = ".".join(self.cls)
        decorated = any((C.dotted(d.func if isinstance(d, ast.Call) else d) or "").split(".")[-1] == "dataclass"
                        for d in node.decorator_list)
        if not decorated or f"{qual}.__init__" in mod.funcs:
            return
        fields = [(s.target.id, s.value) for s in node.body
                  if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
        init = Func(mod.name, f"{qual}.__init__", node, qual, None, ["self", *[n for n, _ in fields]],
                    defaults={n: v for n, v in fields if v is not None})
        mod.funcs[init.qual] = init
        for name, _ in fields:
            kept: list[tuple[Func | None, ast.expr]] = [(src, rhs) for src, rhs in mod.attrs.get((qual, name), [])
                                                        if src is not None]
            kept.append((init, ast.Name(id=name, ctx=ast.Load())))
            mod.attrs[(qual, name)] = kept

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        if any(_is_flag(e) for e in node.elts):
            self.mod.argv_lists.append((self.func, node))
        self.generic_visit(node)

    # -- bindings
    def _bind(self, target: ast.expr, value: ast.expr | None) -> None:
        func = self.func
        if (isinstance(target, (ast.Tuple, ast.List)) and value is not None
                and not any(isinstance(t, ast.Starred) for t in target.elts)):
            # `a, b = x, y` binds each target to its element; `a, b = f(...)` binds target i to `f(...)[i]`, which the
            # evaluator reads from the returns of `f` (a node made here lives as long as the assignment it is in)
            if (isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts)
                    and not any(isinstance(v, ast.Starred) for v in value.elts)):
                for t, v in zip(target.elts, value.elts, strict=True):
                    self._bind(t, v)
                return
            if isinstance(value, ast.Call):
                for i, t in enumerate(target.elts):
                    self._bind(t, ast.copy_location(
                        ast.Subscript(value=value, slice=ast.Constant(value=i), ctx=ast.Load()), value))
                return
        if isinstance(target, ast.Name):
            if func is not None:
                if value is None:
                    func.opaque.add(target.id)
                else:
                    func.assigns.setdefault(target.id, []).append(value)
            elif not self.cls and value is not None:
                self.mod.consts[target.id] = value
        elif (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"
              and self.cls and value is not None):
            self.mod.attrs.setdefault((self.cls[-1], target.attr), []).append((func, value))
        else:
            for name in _targets(target):
                if func is not None:
                    func.opaque.add(name.id)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and self.func is not None:
                self.func.subkeys.setdefault(target.value.id, []).append(target.slice)
            self._bind(target, node.value if isinstance(target, (ast.Name, ast.Attribute, ast.Tuple, ast.List))
                       else None)
        if self.func is None and self.cls and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.mod.attrs.setdefault((self.cls[-1], node.targets[0].id), []).append((None, node.value))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._bind(node.target, node.value)
            if self.func is None and self.cls and isinstance(node.target, ast.Name):
                self.mod.attrs.setdefault((self.cls[-1], node.target.id), []).append((None, node.value))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            if self.func is not None:
                self.func.opaque.add(node.target.id)
                self.func.augs.setdefault(node.target.id, []).append(node.value)
        self.generic_visit(node)

    def _loop(self, target: ast.expr, iterable: ast.expr) -> None:
        if self.func is None:
            return
        if isinstance(target, ast.Name):
            self.func.loops.setdefault(target.id, []).append(iterable)
        elif (isinstance(target, ast.Tuple) and target.elts and isinstance(target.elts[0], ast.Name)
              and isinstance(iterable, ast.Call) and isinstance(iterable.func, ast.Attribute)
              and iterable.func.attr == "items" and not iterable.args):
            self.func.key_loops.setdefault(target.elts[0].id, []).append(iterable.func.value)
            self.func.opaque.update(n.id for n in _targets(target) if n.id != target.elts[0].id)
        else:
            if isinstance(target, ast.Tuple) and isinstance(iterable, (ast.Tuple, ast.List)):
                for index, e in enumerate(target.elts):
                    if isinstance(e, ast.Name):
                        self.func.unpacks.setdefault(e.id, []).append((index, iterable))
            self.func.opaque.update(n.id for n in _targets(target))

    def visit_For(self, node: ast.For) -> None:
        self._loop(node.target, node.iter)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._loop(node.target, node.iter)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._loop(node.target, node.iter)
        self.generic_visit(node)

    def _with(self, items: list[ast.withitem]) -> None:
        for item in items:
            if item.optional_vars is not None and self.func is not None:
                if isinstance(item.optional_vars, ast.Name):
                    self.func.withs.setdefault(item.optional_vars.id, []).append(item.context_expr)
                else:
                    self.func.opaque.update(n.id for n in _targets(item.optional_vars))

    def visit_With(self, node: ast.With) -> None:
        self._with(node.items)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._with(node.items)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name and self.func is not None:
            self.func.opaque.add(node.name)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if self.func is not None:
            self.func.opaque.add(node.target.id)
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        if self.func is not None and node.value is not None:
            self.func.returns.append(node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        (self.func.calls if self.func is not None else self.mod.module_calls).append(node)
        f = node.func
        if (self.func is not None and isinstance(f, ast.Attribute) and f.attr == "append"
                and isinstance(f.value, ast.Name) and len(node.args) == 1):
            self.func.appends.setdefault(f.value.id, []).append(node.args[0])
        for child in ast.iter_child_nodes(node):
            if (isinstance(child, ast.keyword) and isinstance(child.value, ast.Lambda) and child.arg == "handler"
                    and isinstance(f, ast.Attribute) and f.attr == "set_defaults" and self.func is not None):
                self._handler_lambda(child.value)
            else:
                self.visit(child)

    def _handler_lambda(self, node: ast.Lambda) -> None:
        """``parser.set_defaults(handler=lambda a: ...)``: the lambda is the command's handler, called by the CLI's
        dispatch and not by the function that registers it, so its calls are its own and not the registering
        function's (else the whole engine would be on the path every command shares)."""
        outer = self.func
        assert outer is not None
        a = node.args
        positional = [x.arg for x in (*a.posonlyargs, *a.args)]
        params = [*positional, *([a.vararg.arg] if a.vararg else []), *[x.arg for x in a.kwonlyargs],
                  *([a.kwarg.arg] if a.kwarg else [])]
        defaults = dict(zip(reversed(positional), reversed(a.defaults), strict=False))
        ordinal = self.handler_count[outer.qual] = self.handler_count.get(outer.qual, 0) + 1
        func = Func(self.mod.name, f"{outer.qual}.<handler{ordinal}>", node, outer.cls, outer, params,
                    defaults=defaults)
        self.mod.funcs[func.qual] = func
        self.mod.handlers[id(node)] = func
        self.func = func
        self.visit(node.body)
        self.func = outer


@dataclass
class Program:
    """The parsed package: every module's constants, functions and class attributes, and every static call."""

    modules: dict[str, Module]
    callers: dict[tuple[str, str], list[tuple[Func | None, Module, ast.Call]]] = field(default_factory=dict)
    _typing_active: set[int] = field(default_factory=set)  # nodes whose typing is in progress (a cycle is unknown)
    _returned: dict[tuple[str, str], tuple[Module, str]] = field(default_factory=dict)
    _returning: set[tuple[str, str]] = field(default_factory=set)

    @classmethod
    def of(cls, trees: dict[str, tuple[ast.Module, bool]]) -> Program:
        modules = {}
        for name, (tree, is_package) in sorted(trees.items()):
            index = C.index_of(tree, name, is_package)
            mod = Module(name, is_package, tree, index.aliases)
            _Scan(mod).visit(tree)
            modules[name] = mod
        program = cls(modules)
        program._index_callers()
        return program

    # -- names
    def split(self, dotted: str) -> tuple[str, str] | None:
        """``aew.x.NAME`` as (module ``aew.x``, ``NAME``): the longest module prefix the program holds."""
        parts = dotted.split(".")
        for cut in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:cut])
            if module in self.modules:
                return module, ".".join(parts[cut:])
        return None

    def target(self, mod: Module, func: Func | None, callee: ast.expr) -> Func | None:
        """The function a call statically names: a name of this module or imported, a method on ``self``, or a class
        (its ``__init__``). None when the callee is anything else (a method of an object whose class is not known)."""
        if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name) and callee.value.id in ("self",
                                                                                                           "cls"):
            if func is not None and func.cls:
                return self.method(mod, func.cls, callee.attr)
            return None
        if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Call):
            inner = callee.value.func
            if isinstance(inner, ast.Name) and inner.id == "super":
                if func is not None and func.cls:
                    return self.method(mod, func.cls, callee.attr, skip_own=True)
                return None
            if not self._enter_typing(callee):
                return None
            try:  # `Class(...).method(...)`, `f(...).method(...)` with `f` typed `-> Class` or building one
                klass = self._call_class(mod, func, callee.value, TYPING_DEPTH)
            finally:
                self._typing_active.discard(id(callee))
            if klass is not None:
                return self.method(klass[0], klass[1], callee.attr)
            return None
        if isinstance(callee, ast.Attribute) and isinstance(callee.value, (ast.Name, ast.Attribute)):
            if not self._enter_typing(callee):  # typing a receiver names callees, which type their receivers
                return None
            try:
                klass = self.receiver_class(mod, func, callee.value, TYPING_DEPTH)
            finally:
                self._typing_active.discard(id(callee))
            if klass is not None:
                return self.method(klass[0], klass[1], callee.attr)
        dotted = mod.aliases.resolve(callee)
        if dotted is None:
            return None
        if func is not None and isinstance(callee, ast.Name):  # a function defined inside this one or an enclosing one
            scope: Func | None = func
            while scope is not None:
                nested = mod.funcs.get(f"{scope.qual}.{dotted}")
                if nested is not None:
                    return nested
                scope = scope.parent
        found = self._local(mod, dotted)  # a name of this module (`helper`, `Class`, `Class.method`)
        if found is not None:
            return found
        located = self.split(dotted)
        if located is None:
            return None
        module, name = located
        return self._local(self.modules[module], name)

    def _local(self, mod: Module, name: str) -> Func | None:
        if name in mod.funcs:
            return mod.funcs[name]
        if name in mod.classes:
            return self.method(mod, name, "__init__")
        return None

    def _enter_typing(self, callee: ast.expr) -> bool:
        """One more receiver typed through receivers; False when the receiver's own typing needs itself (a cycle: the
        receiver is not known, which is not the cap's doing). Past ``TYPING_DEPTH`` the call edge would be dropped, and
        an edge can carry no mark (it reads as "the receiver is not known"), so the reading fails, naming the cap
        (addendum 7)."""
        if id(callee) in self._typing_active:
            return False
        level = len(self._typing_active) + 1
        _note("typing", level)
        if level > TYPING_DEPTH:
            raise C.ReferenceError(cap_reason("TYPING_DEPTH", f"the receiver of `{_src(callee)}` is typed through more "
                                                              f"than {TYPING_DEPTH} receivers, and the call would not "
                                                              "be followed") + ": raise the cap, and say why")
        self._typing_active.add(id(callee))
        return True

    @staticmethod
    def _level(depth: int, what: ast.expr | str) -> None:
        """The next hop of typing a receiver or the class a function returns (``depth`` counts down from the cap): the
        same arm as :meth:`_enter_typing` when the hop would be one past ``TYPING_DEPTH``."""
        _note("typing", TYPING_DEPTH - depth + 1)
        if depth <= 0:
            where = what if isinstance(what, str) else _src(what)
            raise C.ReferenceError(cap_reason("TYPING_DEPTH", f"`{where}` is typed through more than {TYPING_DEPTH} "
                                                              "hops, and what it names would not be followed")
                                   + ": raise the cap, and say why")

    def receiver_class(self, mod: Module, func: Func | None, expr: ast.expr, depth: int) -> tuple[Module, str] | None:
        """The class of a receiver when it is evident: ``self`` (the function's class), a parameter annotated with a
        class, a local assigned a call of a class (or of a function annotated ``-> Class``), and a ``self`` attribute
        that every assignment in the class gives such a class. None otherwise (never a guess)."""
        if isinstance(expr, ast.Name):
            if expr.id in ("self", "cls") and func is not None and func.cls:
                return mod, func.cls
            scope = func
            while scope is not None:
                if expr.id in scope.annotations and expr.id not in scope.assigns:
                    return self.class_of(self.modules[scope.module], scope.annotations[expr.id])
                if expr.id in scope.assigns:
                    if id(expr) in self._typing_active:
                        return None  # a local whose class needs itself: a cycle
                    self._level(depth, expr)
                    self._typing_active.add(id(expr))
                    try:
                        built = {self._call_class(self.modules[scope.module], scope, rhs, depth - 1)
                                 for rhs in scope.assigns[expr.id]}
                    finally:
                        self._typing_active.discard(id(expr))
                    return next(iter(built)) if len(built) == 1 and None not in built else None
                scope = scope.parent
            return None
        if isinstance(expr, ast.Attribute):
            if id(expr) in self._typing_active:
                return None  # an attribute whose class needs itself: a cycle
            self._level(depth, expr)
            self._typing_active.add(id(expr))
            try:
                owner = self.receiver_class(mod, func, expr.value, depth - 1)
                if owner is None:
                    return None
                kinds: set[tuple[Module, str] | None] = set()
                for m, k in self.mro(owner[0], owner[1]):
                    for source, rhs in m.attrs.get((k, expr.attr), []):
                        holder = self.modules[source.module] if source else m
                        if isinstance(rhs, ast.Name) and source is not None and rhs.id in source.annotations:
                            kinds.add(self.class_of(holder, source.annotations[rhs.id]))
                        elif isinstance(rhs, (ast.Name, ast.Attribute)):
                            kinds.add(self.receiver_class(holder, source, rhs, depth - 1))
                        else:
                            kinds.add(self._call_class(holder, source, rhs, depth - 1))
            finally:
                self._typing_active.discard(id(expr))
            return next(iter(kinds)) if len(kinds) == 1 and None not in kinds else None
        return None

    def _call_class(self, mod: Module, func: Func | None, expr: ast.expr, depth: int) -> tuple[Module, str] | None:
        """The class a call expression yields: a constructor, or a function annotated ``-> Class``."""
        if not isinstance(expr, ast.Call):
            return None
        if isinstance(expr.func, ast.Name) and expr.func.id == "cls" and func is not None and func.cls:
            return mod, func.cls  # `cls(...)` in a classmethod builds the class
        built = self.constructed(mod, expr.func)  # the class itself, whether or not it defines `__init__`
        if built is not None:
            return built
        target = self.target(mod, func, expr.func)
        if target is None:
            return None
        if target.returns_annotation is not None:
            return self.class_of(self.modules[target.module], target.returns_annotation)
        return self._returned_class(target, depth)

    def _returned_class(self, target: Func, depth: int) -> tuple[Module, str] | None:
        """The one class every ``return`` expression of an unannotated function builds, or None."""
        if target.key in self._returned:
            return self._returned[target.key]
        if not target.returns or target.key in self._returning:
            return None  # a function that returns itself, through any chain, types as unknown
        self._level(depth, target.qual)
        self._returning.add(target.key)
        try:
            mod = self.modules[target.module]
            kinds = {self._call_class(mod, target, ret, depth - 1) for ret in target.returns}
        finally:
            self._returning.discard(target.key)
        result = next(iter(kinds)) if len(kinds) == 1 and None not in kinds else None
        if result is not None:  # only an answer is kept: an unknown may be the depth's, not the function's
            self._returned[target.key] = result
        return result

    def constructed(self, mod: Module, callee: ast.expr) -> tuple[Module, str] | None:
        """The program class a call's callee names (``Class(...)``), however its ``__init__`` is inherited or absent."""
        dotted = mod.aliases.resolve(callee) if isinstance(callee, (ast.Name, ast.Attribute)) else None
        if dotted is None:
            return None
        if dotted in mod.classes:
            return mod, dotted
        located = self.split(dotted)
        if located and located[1] in self.modules[located[0]].classes:
            return self.modules[located[0]], located[1]
        return None

    def class_of(self, mod: Module, annotation: ast.expr) -> tuple[Module, str] | None:
        """The program class a parameter's annotation names (``Thread``, ``mod.Thread``, ``Thread | None``)."""
        if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
            return self.class_of(mod, annotation.left) or self.class_of(mod, annotation.right)
        dotted = mod.aliases.resolve(annotation)
        if dotted is None:
            return None
        if dotted in mod.classes:
            return mod, dotted
        located = self.split(dotted)
        if located and located[1] in self.modules[located[0]].classes:
            return self.modules[located[0]], located[1]
        return None

    def mro(self, mod: Module, cls: str, _depth: int = 0) -> list[tuple[Module, str]]:
        """The class and its bases that the program holds, most derived first (a depth-first reading: enough to find
        where an attribute or a method is defined)."""
        out = [(mod, cls)]
        bases: list[tuple[Module, str]] = []
        for base in mod.bases.get(cls, []):
            dotted = mod.aliases.resolve(base)
            if dotted is None:
                continue
            owner, name = (mod, dotted) if dotted in mod.classes else (None, "")
            if owner is None:
                located = self.split(dotted)
                if located and located[1] in self.modules[located[0]].classes:
                    owner, name = self.modules[located[0]], located[1]
            if owner is not None:
                bases.append((owner, name))
        if bases and _depth >= MRO_DEPTH:  # MRO_DEPTH bases are followed; a list of classes can carry no mark
            raise C.ReferenceError(cap_reason("MRO_DEPTH", f"the bases of `{mod.name}.{cls}` go more than {MRO_DEPTH} "
                                                           "levels deep, and what they define would be lost")
                                   + ": raise the cap, and say why")
        for owner, name in bases:
            _note("mro", _depth + 1)
            for item in self.mro(owner, name, _depth + 1):
                if item not in out:
                    out.append(item)
        return out

    def prop(self, mod: Module, cls: str, name: str) -> Func | None:
        """``cls.name`` when it is a property (or cached property) of the class or its nearest base."""
        found = self.method(mod, cls, name)
        if found is None or not isinstance(found.node, ast.FunctionDef | ast.AsyncFunctionDef):
            return None
        decorated = any((C.dotted(d) or "").split(".")[-1] in ("property", "cached_property")
                        for d in found.node.decorator_list)
        return found if decorated else None

    def method(self, mod: Module, cls: str, name: str, *, skip_own: bool = False) -> Func | None:
        """``cls.name`` as the class or its nearest base defines it."""
        for owner, klass in self.mro(mod, cls)[1 if skip_own else 0:]:
            found = owner.funcs.get(f"{klass}.{name}")
            if found is not None:
                return found
        return None

    def argv_lists_of(self, flag: str, module: str) -> list[tuple[Func | None, ast.List]]:
        """The argument lists in the program that hold ``flag`` and ``module``'s dotted name: the starts of that process
        (``-m`` names the module), with the function that builds each."""
        return [(owner, lst) for mod in self.modules.values() for owner, lst in mod.argv_lists
                if any(isinstance(x, ast.Constant) and x.value == flag for x in lst.elts)
                and any(isinstance(x, ast.Constant) and x.value == module for x in lst.elts)]

    def _index_callers(self) -> None:
        for mod in self.modules.values():
            for func in mod.funcs.values():
                for call in func.calls:
                    callee = self.target(mod, func, call.func)
                    if callee is not None:
                        self.callers.setdefault(callee.key, []).append((func, mod, call))
            for call in mod.module_calls:
                callee = self.target(mod, None, call.func)
                if callee is not None:
                    self.callers.setdefault(callee.key, []).append((None, mod, call))


# ------------------------------------------------------------------------------------------------- the evaluation

@dataclass(frozen=True)
class Env:
    module: str
    func: tuple[str, str] | None  # the function's key, None at module level
    bindings: tuple[tuple[str, Values], ...] = ()  # parameters bound by the call being inlined


def _join(a: Val, b: Val) -> Val:
    """``a / b``. A path joined with the string ``.aew`` is the ``.aew`` directory (the owner's ``AEW_DIR``); a
    computed segment makes the template's tail (or, under the root, its first segment) a placeholder. A part a cap
    stopped is not a computed one: the join stays unknown with the cap's reason, and says so when the path before it was
    computed too (addendum 6)."""
    if a.kind == UNK:
        return a
    if b.kind == STR and b.text == AEW_DIRECTORY:
        return Val(ROOT, "")
    if a.kind == OUT:
        return a
    if b.kind == OUT:
        return b
    if b.kind == UNK:
        if is_cap(b.text):
            before = a.kind == TPL and PLACEHOLDER in a.text
            return Val(UNK, f"{b.text}; the path before it is also computed" if before else b.text)
        if a.kind == ROOT:
            return Val(TPL, PLACEHOLDER)
        return Val(a.kind, f"{a.text}/{PLACEHOLDER}" if a.text else PLACEHOLDER)
    if b.kind == ROOT:
        return b
    tail = b.text
    if a.kind == ROOT:
        return Val(TPL, tail)
    if not a.text:
        return Val(a.kind, tail)
    return Val(a.kind, f"{a.text}/{tail}" if tail else a.text)


def _parent(v: Val) -> Val:
    if v.kind == ROOT:
        return Val(OUT, "the repository's working tree")  # `.aew` sits directly in it
    if v.kind in (OUT, UNK):
        return v
    head, sep, _ = v.text.rpartition("/")
    if not sep:
        return Val(ROOT, "") if v.kind == TPL else Val(STR, "")
    return Val(v.kind, head)


class Evaluator:
    def __init__(self, program: Program) -> None:
        self.p = program
        self._memo: dict[tuple[int, Env, int], Values] = {}
        # The fixed end of an own-name sibling is a node made here, not read from the source. The memo is keyed by a
        # node's id, so such a node must outlive every lookup (a freed node's id is reused, and a stale answer is a
        # lost record): it is made once per argument and kept here.
        self._tails: dict[int, ast.expr | None] = {}

    # -- entry
    def value(self, mod: Module, func: Func | None, expr: ast.expr) -> Values:
        env = Env(mod.name, func.key if func else None)
        return self._ev(expr, env, DEPTH, frozenset()) or unk("nothing assigns it a path")

    def _func(self, env: Env) -> Func | None:
        return self.p.modules[env.module].funcs.get(env.func[1]) if env.func else None

    def _ev(self, e: ast.expr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        _note("depth", DEPTH - depth + 1)  # the hops this question is from the start (one past DEPTH: cut)
        memo_key = (id(e), env, depth)  # the depth left is part of the question: a deeper chain asked less
        if not seen and memo_key in self._memo:
            return self._memo[memo_key]
        out = capped(self._eval(e, env, depth, seen))
        if not seen:
            self._memo[memo_key] = out
        return out

    # -- the expression forms
    def _eval(self, e: ast.expr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        if isinstance(e, ast.Constant):
            return self._constant(e)
        if isinstance(e, ast.JoinedStr):
            return self._fstring(e, env, depth, seen)
        if isinstance(e, ast.Name):
            return self._name(e, env, depth, seen)
        if isinstance(e, ast.Attribute):
            return self._attribute(e, env, depth, seen)
        if isinstance(e, ast.BinOp):
            return self._binop(e, env, depth, seen)
        if isinstance(e, ast.Call):
            return self._call(e, env, depth, seen)
        if isinstance(e, ast.IfExp):
            return capped(set(self._ev(e.body, env, depth, seen)) | set(self._ev(e.orelse, env, depth, seen)))
        if isinstance(e, ast.BoolOp):
            merged: set[Val] = set()
            for v in e.values:
                merged |= self._ev(v, env, depth, seen)
            return capped(merged)
        if isinstance(e, ast.Subscript):
            return self._subscript(e, env, depth, seen)
        return unk(f"an expression this reading does not model, `{_src(e)}`")

    def _subscript(self, e: ast.Subscript, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """``f(...)[i]`` (what a destructuring assignment of a call binds): the ``i``-th element of each tuple ``f``
        returns. ``name["key"]``, ``f(...)["key"]``, ``f(...)[i]["key"]`` where the value is a dict literal (bound in
        the function, a module constant, or returned by a call): that key's value; with a computed key, the values of
        every key. Anything else is UNK."""
        key = e.slice
        if isinstance(e.value, ast.Call) and isinstance(key, ast.Constant) and isinstance(key.value, int):
            return self._call_element(e.value, key.value, env, depth, seen)
        try:
            sources = self._dict_sources(e.value, env, depth, seen)
        except Cut as cut:
            return unk(f"`{_src(e)}`: {cut}")
        if sources is None:
            return unk(f"`{_src(e)}`, from a value that is not a dict literal")
        out: set[Val] = set()
        for mapping, inner in sources:
            for k, v in zip(mapping.keys, mapping.values, strict=True):
                if k is None:
                    return unk(f"`{_src(e)}`, from a dict with a `**` unpacking")
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)) or (
                        isinstance(k, ast.Constant) and k.value == key.value):
                    out |= self._ev(v, inner, depth, seen)
        return capped(out)

    def _call_element(self, call: ast.Call, index: int, env: Env, depth: int, seen: frozenset[tuple[str, ...]]
                      ) -> Values:
        """The ``index``-th element of the tuple a call returns: of each ``return`` of the function it names, read in
        that function with the call's arguments bound."""
        if depth <= 0:
            return depth_limit()
        mod = self.p.modules[env.module]
        target = self.p.target(mod, self._func(env), call.func)
        if target is None:
            return unk(f"element {index} of `{_src(call.func)}(...)`, a callee this reading cannot name")
        args = self._bind_args(target, call, env, depth, seen)
        inner = Env(target.module, target.key, tuple(sorted(args.items(), key=lambda kv: kv[0])))
        out: set[Val] = set()
        for ret in target.returns:
            if (isinstance(ret, (ast.Tuple, ast.List)) and index < len(ret.elts)
                    and not any(isinstance(x, ast.Starred) for x in ret.elts[: index + 1])):
                out |= self._ev(ret.elts[index], inner, depth - 1, seen)
            else:
                out.add(Val(UNK, f"`{target.qual}` returns something other than a tuple literal"))
        return capped(out) if target.returns else unk(f"`{target.qual}` returns no expression")

    def _dict_sources(self, expr: ast.expr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]
                      ) -> list[tuple[ast.Dict, Env]] | None:
        """The dict literals ``expr`` can be, each with the environment to read its values in; None when any way it can
        be bound is not one (a parameter, an attribute, an unknown call). A dict literal; a name bound in the function
        to one (``x = None`` before is skipped); a module constant; a call, or the element of a call, whose function
        returns one. A chain deeper than ``DEPTH`` raises ``Cut``: it is the cap's, and not "not a dict literal"."""
        if depth <= 0:
            raise Cut(depth_reason())
        if isinstance(expr, ast.Dict):
            return [(expr, env)]
        mod = self.p.modules[env.module]
        func = self._func(env)
        if isinstance(expr, ast.Name):
            token = ("dict", env.module, str(env.func), expr.id)
            if token in seen:
                return []
            found: list[tuple[ast.Dict, Env]] = []
            if func is not None and expr.id in func.assigns:
                for rhs in func.assigns[expr.id]:
                    if isinstance(rhs, ast.Constant) and rhs.value is None:
                        continue
                    more = self._dict_sources(rhs, env, depth - 1, seen | {token})
                    if more is None:
                        return None
                    found += more
                return found
            if func is None and expr.id in mod.consts or (func is not None and expr.id not in func.params
                                                          and expr.id in mod.consts):
                return self._dict_sources(mod.consts[expr.id], Env(mod.name, None), depth - 1, seen | {token})
            return None
        call = expr.value if isinstance(expr, ast.Subscript) and isinstance(expr.value, ast.Call) else expr
        if isinstance(call, ast.Call):
            target = self.p.target(mod, func, call.func)
            if target is None or not target.returns:
                return None
            inner = Env(target.module, target.key)
            index = expr.slice.value if (isinstance(expr, ast.Subscript) and isinstance(expr.slice, ast.Constant)
                                         and isinstance(expr.slice.value, int)) else None
            found = []
            for ret in target.returns:
                if index is not None:
                    if not (isinstance(ret, (ast.Tuple, ast.List)) and index < len(ret.elts)):
                        return None
                    ret = ret.elts[index]
                more = self._dict_sources(ret, inner, depth - 1, seen)
                if more is None:
                    return None
                found += more
            return found
        return None

    def _constant(self, e: ast.Constant) -> Values:
        if e.value is None:
            return frozenset()  # `self.x = None` before it is set: the other assignments are the values
        if not isinstance(e.value, str):
            return unk("a constant that is not a string")
        text = e.value
        if text in OUTSIDE_LITERALS:
            return one(OUT, OUTSIDE_LITERALS[text])
        if text.startswith("/") or (len(text) > 1 and text[1] == ":" and text[0].isalpha()):
            return one(OUT, "an absolute path")
        return one(STR, text)

    def _fstring(self, e: ast.JoinedStr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        first = e.values[0] if e.values else None
        if isinstance(first, ast.FormattedValue):
            lead = self._ev(first.value, env, depth, seen)
            if lead and all(v.kind in (TPL, OUT) for v in lead):
                return lead  # `f"{path}.tmp"`, `f"{path}{suffix}"`: a sibling of `path`, taken as the same path
        parts = [""]
        stopped: set[Val] = set()  # what a cap stopped keeps its reason beside the computed segment it leaves
        for piece in e.values:
            if isinstance(piece, ast.Constant):
                parts = [p + str(piece.value) for p in parts]
                continue
            inner = self._ev(piece.value, env, depth, seen) if isinstance(piece, ast.FormattedValue) else unk("?")
            stopped |= cap_unknowns(inner)
            texts = sorted({v.text for v in inner if v.kind == STR})
            if inner and len(inner) == len(texts):
                _note("alternatives", len(texts))
            if inner and len(inner) == len(texts) and len(texts) <= FSTRING_LIMIT:
                parts = [p + t for p in parts for t in texts]
            else:
                if inner and len(inner) == len(texts):
                    stopped |= unk(cap_reason("FSTRING_LIMIT", f"more than {FSTRING_LIMIT} alternatives of one "
                                                               "f-string piece"))
                parts = [p + PLACEHOLDER for p in parts]
        return capped({Val(STR, p) for p in parts} | stopped)

    def _binop(self, e: ast.BinOp, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        if isinstance(e.op, ast.Div):
            left = self._ev(e.left, env, depth, seen) or unk("nothing assigns it a path")
            right = self._ev(e.right, env, depth, seen) or unk("nothing assigns it a path")
            return capped({_join(a, b) for a in left for b in right})
        if isinstance(e.op, ast.Add):
            left, right = self._ev(e.left, env, depth, seen), self._ev(e.right, env, depth, seen)
            out = set()
            for a in left:
                for b in right:
                    if a.kind == STR and b.kind == STR:
                        out.add(Val(STR, a.text + b.text))
                    elif a.kind == STR and b.kind == UNK:
                        out.add(Val(STR, a.text + PLACEHOLDER))
                        out |= cap_unknowns({b})
                    elif a.kind == UNK:
                        out.add(a)
                    else:
                        out.add(Val(UNK, f"a sum this reading does not model, `{_src(e)}`"))
            return capped(out)
        return unk(f"an operator this reading does not model, `{_src(e)}`")

    def _name(self, e: ast.Name, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        name = e.id
        for bound, values in env.bindings:
            if bound == name:
                return values
        if name == ROOT_NAME:
            return one(ROOT)
        if name == REPO_NAME:
            return one(OUT, "the repository's working tree")
        mod = self.p.modules[env.module]
        func = self._func(env)
        scope = func
        while scope is not None:
            token = ("name", scope.module, scope.qual, name)
            if (name in scope.assigns or name in scope.opaque or name in scope.params or name in scope.loops
                    or name in scope.withs or name in scope.key_loops or name in scope.unpacks):
                if token in seen:
                    return frozenset()
                out: set[Val] = set()
                inner_env = Env(env.module, scope.key, env.bindings if scope is func else ())
                for rhs in scope.assigns.get(name, []):
                    out |= self._ev(rhs, inner_env, depth, seen | {token})
                for iterable in scope.loops.get(name, []):
                    out |= self._element(iterable, inner_env, depth, seen | {token})
                for context in scope.withs.get(name, []):
                    out |= self._context(context, inner_env, name)
                for mapping in scope.key_loops.get(name, []):
                    out |= self._keys(mapping, inner_env, depth, seen | {token})
                for index, rows in scope.unpacks.get(name, []):
                    out |= self._row_elements(rows, index, inner_env, depth, seen | {token})
                if name in scope.opaque and name not in scope.unpacks:
                    out.add(Val(UNK, f"`{name}` is bound by a `with`, an unpacking or an `except`"))
                if name in scope.params:
                    out |= self._param(scope, name, depth, seen | {token})
                return capped(out)
            scope = scope.parent
        if name in mod.consts:
            token = ("const", mod.name, name)
            if token in seen:
                return frozenset()
            return self._ev(mod.consts[name], Env(mod.name, None), depth, seen | {token})
        imported = mod.aliases.names.get(name)
        if imported:
            located = self.p.split(imported)
            if located and located[1] in self.p.modules[located[0]].consts:
                owner = self.p.modules[located[0]]
                token = ("const", owner.name, located[1])
                if token in seen:
                    return frozenset()
                return self._ev(owner.consts[located[1]], Env(owner.name, None), depth, seen | {token})
        return unk(f"the name `{name}` is not bound to a value this reading can follow")

    def _attribute(self, e: ast.Attribute, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        if e.attr == ROOT_NAME:
            return one(ROOT)
        if e.attr == REPO_NAME:
            return one(OUT, "the repository's working tree")
        if e.attr == "parent":
            return capped({_parent(v) for v in self._ev(e.value, env, depth, seen)})
        mod = self.p.modules[env.module]
        func = self._func(env)
        if isinstance(e.value, ast.Name) and e.value.id == "self" and func is not None and func.cls:
            token = ("attr", env.module, func.cls, e.attr)
            if token in seen:
                return frozenset()
            chain = self.p.mro(mod, func.cls)
            sources = [(owner, rhs) for m, k in chain for owner, rhs in m.attrs.get((k, e.attr), [])]
            prop = self.p.prop(mod, func.cls, e.attr)  # a property: its return expressions are the value
            if not sources and prop is None:
                return unk(f"`self.{e.attr}` is not assigned in its class")
            out: set[Val] = set()
            for owner, rhs in sources:
                out |= self._ev(rhs, Env(owner.module if owner else env.module, owner.key if owner else None), depth,
                                seen | {token})
            if not sources and prop is not None:
                for ret in prop.returns:
                    out |= self._ev(ret, Env(prop.module, prop.key), depth, seen | {token})
            return capped(out)
        parsed = self._command_line(e, env, depth, seen)
        if parsed is not None:
            return parsed
        instance = self._instance_attribute(e, env, depth, seen)
        if instance is not None:
            return instance
        typed = self._typed_attribute(e, env, depth, seen)
        if typed is not None:
            return typed
        dotted = mod.aliases.resolve(e)
        if dotted == "os.devnull":
            return one(OUT, "the null device")
        if dotted == "os.sep" or dotted == "os.linesep":
            return unk("a separator")
        located = self.p.split(dotted) if dotted else None
        if located and located[1] in self.p.modules[located[0]].consts:
            owner = self.p.modules[located[0]]
            token = ("const", owner.name, located[1])
            if token in seen:
                return frozenset()
            return self._ev(owner.consts[located[1]], Env(owner.name, None), depth, seen | {token})
        return unk(f"the attribute `{_src(e)}` is not a value this reading can follow")

    def _call(self, e: ast.Call, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        mod = self.p.modules[env.module]
        func = self._func(env)
        callee = mod.aliases.resolve(e.func)
        if callee in SAME_PATH_CALLS or (callee and callee.split(".")[-1] in ("Path", "PurePath", "PurePosixPath")
                                         and callee.startswith("pathlib")):
            if not e.args:
                return unk("a path with no argument")
            values = self._ev(e.args[0], env, depth, seen)
            for extra in e.args[1:]:
                tail = self._ev(extra, env, depth, seen)
                values = capped({_join(a, b) for a in values for b in tail})
            return values
        if callee in JOIN_CALLS:
            values = self._ev(e.args[0], env, depth, seen) if e.args else unk("os.path.join with no argument")
            for extra in e.args[1:]:
                tail = self._ev(extra, env, depth, seen)
                values = capped({_join(a, b) for a in values for b in tail})
            return values
        if callee == f"{UTIL_MODULE}.write_temp" and e.args:  # returns the new temporary file, in its directory
            return capped({_join(v, Val(UNK, "a temporary file")) for v in self._ev(e.args[0], env, depth, seen)})
        if callee in TEMP_CALLS:
            return one(OUT, "a temporary directory")
        if (C.dotted(e.func) or "").split(".")[-1] == WORKSPACES_NAME:
            return one(OUT, "the task workspaces' directory")
        if isinstance(e.func, ast.Attribute):
            method = e.func.attr
            if method in SAME_PATH_METHODS:
                return self._ev(e.func.value, env, depth, seen)
            if method in SIBLING_METHODS:
                return self._sibling(e, method, env, depth, seen)
            if method == "joinpath":
                values = self._ev(e.func.value, env, depth, seen)
                for extra in e.args:
                    tail = self._ev(extra, env, depth, seen)
                    values = capped({_join(a, b) for a in values for b in tail})
                return values
            if method == "format" and isinstance(e.func.value, ast.Constant) and isinstance(e.func.value.value, str):
                return one(STR, _format_template(e.func.value.value))
        if depth <= 0:
            return depth_limit()
        target = self.p.target(mod, func, e.func)
        if target is None:
            return unk(f"the result of `{_src(e.func)}(...)`, a callee this reading cannot name")
        if not target.returns:
            return unk(f"`{target.qual}` returns no expression")
        args = self._bind_args(target, e, env, depth, seen)
        inner = Env(target.module, target.key, tuple(sorted(args.items(), key=lambda kv: kv[0])))
        out: set[Val] = set()
        for ret in target.returns:
            out |= self._ev(ret, inner, depth - 1, seen)
        return capped(out)

    def _context(self, context: ast.expr, env: Env, name: str) -> Values:
        """``with <context> as name``: a temporary directory is outside ``.aew``; any other context manager yields an
        object this reading does not follow."""
        mod = self.p.modules[env.module]
        callee = mod.aliases.resolve(context.func) if isinstance(context, ast.Call) else None
        if callee in TEMP_CALLS:
            return one(OUT, "a temporary directory")
        return unk(f"`{name}` is bound by `with {_src(context)}`")

    def _keys(self, mapping: ast.expr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """The keys of a mapping: those of a dict literal, or of every dict literal bound to the name in the function,
        plus each ``name[key] = ...``; for a parameter, those of the mapping every static call passes. A ``**``
        unpacking, or a mapping from anywhere else, is UNK."""
        if isinstance(mapping, ast.Dict):
            out: set[Val] = set()
            for key in mapping.keys:
                out |= self._ev(key, env, depth, seen) if key is not None else unk("a `**` unpacking in a mapping")
            return capped(out)
        if isinstance(mapping, ast.Call):  # the keys of the mapping a function returns, a callback included
            return self._keys_of_call(mapping, env, depth, seen)
        if not isinstance(mapping, ast.Name):
            return unk(f"the keys of `{_src(mapping)}`, a mapping this reading cannot read")
        func = self._func(env)
        if func is None:
            return unk(f"the keys of `{mapping.id}`, a mapping this reading cannot read")
        token = ("keys", func.module, func.qual, mapping.id)
        if token in seen or depth <= 0:
            return frozenset() if token in seen else depth_limit()
        out = set()
        for rhs in func.assigns.get(mapping.id, []):
            out |= self._keys(rhs, env, depth, seen | {token})
        for key in func.subkeys.get(mapping.id, []):
            out |= self._ev(key, env, depth, seen | {token})
        if mapping.id in func.params:
            sites = self.p.callers.get(func.key, [])
            if len(sites) > CALLERS:  # none is read: the first few would be a partial answer that looks complete
                out.add(Val(UNK, cap_reason("CALLERS", f"the keys of `{mapping.id}`, which has more than {CALLERS} "
                                                       "call sites")))
                sites = []
            for caller, caller_mod, call in sites:
                arg = _argument(func, mapping.id, call)
                if arg is not None:
                    out |= self._keys(arg, Env(caller_mod.name, caller.key if caller else None), depth - 1,
                                      seen | {token})
        if not out:
            out.add(Val(UNK, f"the keys of `{mapping.id}`, a mapping this reading cannot read"))
        return capped(out)

    def _keys_of_call(self, call: ast.Call, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """The keys of the mapping a call returns: those of each ``return`` of each function the call can name (see
        :meth:`_callables`)."""
        token = ("keys-call", env.module, str(env.func), str(id(call)))
        if token in seen or depth <= 0:
            return frozenset() if token in seen else depth_limit()
        try:
            targets = self._callables(call.func, env, depth - 1, seen | {token})
        except Cut as cut:
            return unk(f"the keys of `{_src(call)}`: {cut}")
        out: set[Val] = set()
        for target in targets:
            for ret in target.returns:
                out |= self._keys(ret, Env(target.module, target.key), depth - 1, seen | {token})
        if not out:
            out.add(Val(UNK, f"the keys of `{_src(call)}`, a mapping this reading cannot read"))
        return capped(out)

    def _callables(self, callee: ast.expr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> list[Func]:
        """The functions an expression can be when it is called: one a name, attribute or method statically resolves
        to; or a callback, a parameter or a ``self`` attribute that a constructor stored, followed to the functions
        its callers pass. (A value read, not an edge: the reach does not follow callbacks.) A cap reached on the way
        is a :class:`Cut`: the functions found so far would be a partial answer that looks complete."""
        if depth <= 0:
            raise Cut(depth_reason())
        mod = self.p.modules[env.module]
        func = self._func(env)
        static = self.p.target(mod, func, callee)
        if static is not None:
            return [static]
        found: list[Func] = []
        if isinstance(callee, ast.Name) and func is not None and callee.id in func.params:
            token = ("callable", func.module, func.qual, callee.id)
            if token in seen:
                return []
            sites = self.p.callers.get(func.key, [])
            if len(sites) > CALLERS:
                raise Cut(cap_reason("CALLERS", f"`{callee.id}` of `{func.qual}` has more than {CALLERS} call sites"))
            for caller, caller_mod, call in sites:
                arg = _argument(func, callee.id, call)
                if arg is not None:
                    found += self._callables(arg, Env(caller_mod.name, caller.key if caller else None), depth - 1,
                                             seen | {token})
        elif (isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name) and callee.value.id == "self"
              and func is not None and func.cls):
            token = ("callable-attr", env.module, func.cls, callee.attr)
            if token in seen:
                return []
            for m, k in self.p.mro(mod, func.cls):
                for owner, rhs in m.attrs.get((k, callee.attr), []):
                    found += self._callables(rhs, Env(owner.module if owner else m.name, owner.key if owner else None),
                                             depth - 1, seen | {token})
        return found

    def _element(self, iterable: ast.expr, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """What a ``for`` target takes from its iterable: a path under the receiver for ``glob``, ``rglob``,
        ``iterdir``, ``os.listdir`` and ``os.scandir``; through ``sorted``, ``list``, ``tuple``, ``set`` and
        ``reversed`` to their argument; the elements of a list, tuple or set literal. Anything else is UNK."""
        mod = self.p.modules[env.module]
        if isinstance(iterable, (ast.List, ast.Tuple, ast.Set)):
            out: set[Val] = set()
            for item in iterable.elts:
                if isinstance(item, ast.Starred):
                    out |= self._element(item.value, env, depth, seen)
                else:
                    out |= self._ev(item, env, depth, seen)
            return capped(out)
        if isinstance(iterable, ast.Name):
            return self._elements_of_name(iterable.id, env, depth, seen)
        if isinstance(iterable, ast.IfExp):  # `xs if cond else []`: the elements of either arm
            return capped(self._element(iterable.body, env, depth, seen)
                          | self._element(iterable.orelse, env, depth, seen))
        if isinstance(iterable, ast.Subscript) and isinstance(iterable.slice, ast.Slice):  # `xs[:n]`
            return self._element(iterable.value, env, depth, seen)
        if isinstance(iterable, ast.Call):
            callee = mod.aliases.resolve(iterable.func)
            if callee in ("sorted", "list", "tuple", "set", "reversed", "filter") and iterable.args:
                return self._element(iterable.args[-1], env, depth, seen)
            if callee in ("os.listdir", "os.scandir") and iterable.args:
                return capped({_join(v, Val(UNK, "a directory entry")) for v in self._ev(iterable.args[0], env, depth,
                                                                                         seen)})
            if isinstance(iterable.func, ast.Attribute) and iterable.func.attr in ("glob", "rglob", "iterdir"):
                return capped({_join(v, Val(UNK, "a directory entry"))
                               for v in self._ev(iterable.func.value, env, depth, seen)})
        return unk(f"a loop variable over `{_src(iterable)}`")

    def _row_elements(self, rows: ast.expr, index: int, env: Env, depth: int, seen: frozenset[tuple[str, ...]]
                      ) -> Values:
        """``for a, b in ((x, y), (z, w))``: what the ``index``-th target takes, the ``index``-th element of each row
        of a list or tuple literal. Anything else is UNK."""
        if not isinstance(rows, (ast.List, ast.Tuple)):
            return unk(f"a loop variable over `{_src(rows)}`, rows this reading cannot read")
        out: set[Val] = set()
        for row in rows.elts:
            if isinstance(row, (ast.Tuple, ast.List)) and index < len(row.elts):
                out |= self._ev(row.elts[index], env, depth, seen)
            else:
                out.add(Val(UNK, f"a row of `{_src(rows)}` that is not a tuple literal"))
        return capped(out)

    def _elements_of_name(self, name: str, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """The elements of a local list: those of every list, tuple or comprehension assigned to it, and every
        ``name.append(element)``. A list that comes from anywhere else (a parameter, a call) is UNK."""
        func = self._func(env)
        if func is not None and name in func.params and name not in func.assigns:
            return self._elements_of_param(func, name, depth, seen)
        if func is None or name not in func.assigns:
            return unk(f"a loop variable over `{name}`, a list this reading cannot read")
        token = ("elements", func.module, func.qual, name)
        if token in seen:
            return frozenset()
        out: set[Val] = set()
        for rhs in func.assigns[name]:
            if isinstance(rhs, (ast.List, ast.Tuple, ast.Set)):
                out |= self._element(rhs, env, depth, seen | {token})
            elif isinstance(rhs, ast.ListComp):
                out |= self._ev(rhs.elt, env, depth, seen | {token})
            else:
                out.add(Val(UNK, f"a loop variable over `{name}`, a list this reading cannot read"))
        for item in func.appends.get(name, []):
            out |= self._ev(item, env, depth, seen | {token})
        return capped(out)

    def _command_line(self, e: ast.Attribute, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values | None:
        """``args.run_dir`` where ``args = parser.parse_args(...)`` in the function: the value some start of this
        module's process spells after ``--run-dir`` in the argument list it builds (a list literal holding the flag and
        the module's dotted name, as ``[python, "-m", "aew.harness.supervisor", "--run-dir", str(directory)]`` does).
        None when the object is not parsed arguments. UNK when no start of the module passes the flag: it is named by
        whoever starts the process."""
        func = self._func(env)
        if func is None or not isinstance(e.value, ast.Name) or e.value.id not in func.assigns:
            return None

        def parsed(rhs: ast.expr) -> bool:
            call = rhs.value if isinstance(rhs, ast.Subscript) else rhs
            return (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr in ("parse_args", "parse_known_args"))

        if not all(parsed(rhs) for rhs in func.assigns[e.value.id]):
            return None
        flag, module = "--" + e.attr.replace("_", "-"), env.module
        out: set[Val] = set()
        for owner, lst in self.p.argv_lists_of(flag, module):
            at = next(i for i, x in enumerate(lst.elts) if isinstance(x, ast.Constant) and x.value == flag)
            if at + 1 < len(lst.elts):
                out |= self._ev(lst.elts[at + 1], Env(owner.module if owner else module, owner.key if owner else None),
                                depth - 1, seen)
        return capped(out) if out else unk(
            f"`{flag}` of `{module}`, which no AEW start of it passes: its starter names it")

    def _elements_of_param(self, func: Func, name: str, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """The elements of a list passed as an argument: those of the list every static call passes (a local list is
        read as ``_elements_of_name`` reads it, in the caller). A function nothing calls, or called from more places
        than the program reads, is UNK."""
        token = ("elements", func.module, func.qual, name)
        if token in seen or depth <= 0:
            return frozenset() if token in seen else depth_limit()
        sites = self.p.callers.get(func.key, [])
        if len(sites) > CALLERS:
            return unk(cap_reason("CALLERS", f"a loop variable over `{name}`, a list passed at more than {CALLERS} "
                                             "call sites"))
        if not sites:
            return unk(f"a loop variable over `{name}`, a list this reading cannot read")
        out: set[Val] = set()
        for caller, caller_mod, call in sites:
            arg = _argument(func, name, call)
            if arg is None:
                out.add(Val(UNK, f"a loop variable over `{name}`, which a call leaves out"))
            else:
                out |= self._element(arg, Env(caller_mod.name, caller.key if caller else None), depth - 1,
                                     seen | {token})
        return capped(out)

    def _typed_attribute(self, e: ast.Attribute, env: Env, depth: int, seen: frozenset[tuple[str, ...]]
                         ) -> Values | None:
        """``name.attr`` where ``name`` is a parameter annotated with an AEW class: that class's ``self.attr``, as every
        construction of it gives it. None when ``name`` is not such a parameter."""
        func = self._func(env)
        if not (isinstance(e.value, ast.Name) and func is not None and e.value.id in func.annotations):
            return None
        mod = self.p.modules[env.module]
        owner = self.p.class_of(mod, func.annotations[e.value.id])
        if owner is None:
            return None
        cmod, cls = owner
        token = ("typed", cmod.name, cls, e.attr)
        if token in seen or depth <= 0:
            return frozenset() if token in seen else depth_limit()
        sources = [(src, rhs) for m, k in self.p.mro(cmod, cls) for src, rhs in m.attrs.get((k, e.attr), [])]
        prop = self.p.prop(cmod, cls, e.attr)
        if not sources and prop is None:
            return unk(f"`{cls}.{e.attr}` is not assigned in its class")
        out: set[Val] = set()
        for source, rhs in sources:
            out |= self._ev(rhs, Env(source.module if source else cmod.name, source.key if source else None),
                            depth - 1, seen | {token})
        if not sources and prop is not None:
            for ret in prop.returns:
                out |= self._ev(ret, Env(prop.module, prop.key), depth - 1, seen | {token})
        return capped(out)

    def _instance_attribute(self, e: ast.Attribute, env: Env, depth: int, seen: frozenset[tuple[str, ...]]
                            ) -> Values | None:
        """``name.attr`` where ``name`` is bound in this function to a call of an AEW class: that class's ``self.attr``,
        with the constructor's arguments bound. None when ``name`` is not such a local."""
        func = self._func(env)
        if not (isinstance(e.value, ast.Name) and func is not None and e.value.id in func.assigns):
            return None
        mod = self.p.modules[env.module]
        out: set[Val] = set()
        for rhs in func.assigns[e.value.id]:
            if not isinstance(rhs, ast.Call):
                return None
            init = self.p.target(mod, func, rhs.func)
            if init is None or not init.cls or not init.qual.endswith(".__init__"):
                return None
            owner = self.p.modules[init.module]
            sources = [(src, rhs) for m, k in self.p.mro(owner, init.cls) for src, rhs in m.attrs.get((k, e.attr), [])]
            prop = self.p.prop(owner, init.cls, e.attr)
            if not sources and prop is None:
                return unk(f"`{init.cls}.{e.attr}` is not assigned in its class")
            token = ("instance", init.module, init.cls, e.attr)
            if token in seen:
                continue
            args = self._bind_args(init, rhs, env, depth, seen)
            bound = Env(init.module, init.key, tuple(sorted(args.items(), key=lambda kv: kv[0])))
            for source, value in sources:
                out |= self._ev(value, bound if source is not None and source.key == init.key else
                                Env(source.module if source else init.module, source.key if source else None),
                                depth - 1, seen | {token})
            if not sources and prop is not None:
                for ret in prop.returns:
                    out |= self._ev(ret, Env(init.module, prop.key, bound.bindings), depth - 1, seen | {token})
        return capped(out)

    def _sibling(self, e: ast.Call, method: str, env: Env, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """``path.with_name(x)``, ``.with_suffix(x)``, ``.with_stem(x)``. Three cases. A sibling named by a fixed
        string, or by the path's own name, suffix or stem plus a fixed string (``p.with_name(p.name + ".queue")``,
        ``p.with_name(f"{p.name}.queue")``, ``p.with_suffix(p.suffix + ".bak")``), is a path of its own. One whose name
        visibly comes from the process (a process or thread id, a clock, a random value, a temporary file) is part of
        the write protocol of its path and is taken as that path. Any other (a name held in a parameter or a call this
        reading cannot read) is a path this reading cannot place."""
        receiver = e.func.value  # type: ignore[attr-defined]
        base = self._ev(receiver, env, depth, seen)
        if not e.args:
            return base
        arg = e.args[0]
        if id(arg) not in self._tails:
            self._tails[id(arg)] = _own_part_tail(arg, SIBLING_PART[method], receiver)
        tail = self._tails[id(arg)]
        fixed = self._ev(arg if tail is None else tail, env, depth, seen)
        if not fixed or any(v.kind != STR or PLACEHOLDER in v.text for v in fixed):
            stopped = cap_unknowns(fixed)  # a cap that stopped the name keeps its reason beside the sibling's
            try:
                if self._process_computed(arg, env):
                    return base
            except Cut as cut:
                stopped |= unk(str(cut))
            why = (f"a sibling of `{_src(receiver)}` named by `{_src(arg)}`, which is neither fixed nor made by "
                   "the process")
            unplaced: set[Val] = set(stopped)
            for v in base:
                unplaced |= unk(why) if v.kind in (TPL, STR) else {v}
            return capped(unplaced)
        out: set[Val] = set()
        for v in base:
            if v.kind not in (TPL, STR):
                out.add(v)
                continue
            head, _, seg = v.text.rpartition("/")
            stem, dot, suffix = seg.rpartition(".")
            if not dot or not stem:  # `.hidden` and `name` have no suffix
                stem, suffix = seg, ""
            else:
                suffix = "." + suffix
            for f in fixed:
                if tail is not None:
                    new = stem + f.text + suffix if method == "with_stem" else seg + f.text
                elif method == "with_name":
                    new = f.text
                elif method == "with_suffix":
                    new = stem + f.text
                else:
                    new = f.text + suffix
                out.add(Val(v.kind, f"{head}/{new}" if _has_dir(v.text) else new))
        return capped(out)

    def _process_computed(self, expr: ast.expr, env: Env, depth: int = ASSIGNMENT_DEPTH) -> bool:
        """Whether a name visibly depends on the process: a call of ``PROCESS_CALLS`` (or of ``tempfile``) in the
        expression, or in an assignment of a name in it. A name assigned further back than ``ASSIGNMENT_DEPTH`` raises
        ``Cut``: the sibling is then an unresolved write that names the cap, and not one "neither fixed nor made"."""
        mod = self.p.modules[env.module]
        func = self._func(env)
        for node in ast.walk(expr):
            if isinstance(node, ast.Call):
                callee = mod.aliases.resolve(node.func)
                if callee in PROCESS_CALLS or callee in TEMP_CALLS:
                    return True
            elif isinstance(node, ast.Name) and func is not None and func.assigns.get(node.id):
                _note("assignments", ASSIGNMENT_DEPTH - depth + 1)
                if depth <= 0:
                    raise Cut(cap_reason("ASSIGNMENT_DEPTH", f"`{node.id}` is assigned from names more than "
                                                             f"{ASSIGNMENT_DEPTH} assignments deep"))
                if any(self._process_computed(rhs, env, depth - 1) for rhs in func.assigns[node.id]):
                    return True
        return False

    # -- parameters and arguments
    def _bind_args(self, target: Func, call: ast.Call, env: Env, depth: int, seen: frozenset[tuple[str, ...]]
                   ) -> dict[str, Values]:
        """The call's arguments, evaluated in the caller's environment, bound to the callee's parameter names."""
        params = list(target.params)
        if params and params[0] in ("self", "cls") and target.cls:
            params = params[1:]
        bound: dict[str, Values] = {}
        for param, arg in zip(params, call.args, strict=False):
            if not isinstance(arg, ast.Starred):
                bound[param] = self._ev(arg, env, depth, seen)
        for kw in call.keywords:
            if kw.arg and kw.arg in target.params:
                bound[kw.arg] = self._ev(kw.value, env, depth, seen)
        return bound

    def _param(self, func: Func, name: str, depth: int, seen: frozenset[tuple[str, ...]]) -> Values:
        """A parameter, read at the function's static call sites. A function nothing statically calls is UNK."""
        if depth <= 0:
            return depth_limit()
        if name == ROOT_NAME:
            return one(ROOT)
        sites = self.p.callers.get(func.key, [])
        if not sites:
            default = func.defaults.get(name)
            if default is not None:
                return self._ev(default, Env(func.module, None), depth - 1, seen)
            return unk(f"`{name}` of `{func.qual}`, which no static call binds")
        if len(sites) > CALLERS:
            return unk(cap_reason("CALLERS", f"`{name}` of `{func.qual}`, which has more than {CALLERS} call sites"))
        out: set[Val] = set()
        for caller, caller_mod, call in sites:
            inner = Env(caller_mod.name, caller.key if caller else None)
            arg = _argument(func, name, call)
            if arg is None:
                default = func.defaults.get(name)
                if default is None:
                    out.add(Val(UNK, f"`{name}` of `{func.qual}` is not passed at a call"))
                else:
                    out |= self._ev(default, Env(func.module, None), depth - 1, seen)
                continue
            out |= self._ev(arg, inner, depth - 1, seen)
        return capped(out)


def _argument(func: Func, name: str, call: ast.Call) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    params = list(func.params)
    if params and params[0] in ("self", "cls") and func.cls:
        params = params[1:]
    if name in params:
        i = params.index(name)
        if i < len(call.args) and not any(isinstance(a, ast.Starred) for a in call.args[: i + 1]):
            return call.args[i]
    return None


def _own_part_tail(arg: ast.expr, part: str, receiver: ast.expr) -> ast.expr | None:
    """The fixed end of ``<receiver>.<part> + tail`` or ``f"{<receiver>.<part>}tail"``, else None."""
    def is_part(node: ast.expr) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == part
                and ast.unparse(node.value) == ast.unparse(receiver))

    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Add) and is_part(arg.left):
        return arg.right
    if (isinstance(arg, ast.JoinedStr) and arg.values and isinstance(arg.values[0], ast.FormattedValue)
            and is_part(arg.values[0].value) and arg.values[0].conversion == -1 and arg.values[0].format_spec is None):
        return ast.JoinedStr(values=arg.values[1:]) if arg.values[1:] else ast.Constant("")
    return None


def _has_dir(text: str) -> bool:
    """Whether a template has a directory part (more than one segment)."""
    return "/" in text


def _src(node: ast.AST) -> str:
    text = ast.unparse(node)
    return text if len(text) <= 60 else text[:57] + "..."


def _format_template(text: str) -> str:
    """``"work/{}/{x}".format(...)`` as a template: every replacement field becomes a placeholder."""
    out, depth, field_open = [], 0, False
    for ch in text:
        if ch == "{":
            depth += 1
            if depth == 1:
                field_open = True
                out.append(PLACEHOLDER)
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                field_open = False
            continue
        if not field_open:
            out.append(ch)
    return "".join(out)
