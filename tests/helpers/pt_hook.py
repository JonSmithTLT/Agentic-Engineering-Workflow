"""The pack-truth provenance hook (the pack-truth plan, reviewed CLEAR, §2.1–§2.3): test-time only; the product never
loads it.

A ``sys.meta_path`` finder rewrites the AST of the hook modules as they are imported, inside the hook functions only
(§2.2, V10-6): every string constant in an output position that contains a space becomes
``U+E000 text U+E001 <unit id> U+E002`` (V11-1's space rule), and every interpolation beside such a constant (an
f-string's value, a ``+`` operand) becomes ``U+E003 value U+E004 <expression id> U+E005``. A name bound to string
constants in an output position (a module constant resolved by import, or a local assigned only constants) and the
leaves of a module-level display a hook function reads are wrapped as the units of those constants. Data: the role
archetype and card YAML prose leaves are units; the pack's authored inputs are fenced values. Under the hook, the
hashing helpers, ``knowledge.context._size`` and argparse's ``HelpFormatter._split_lines``/``_fill_text`` measure
stripped text, so every hash, budget cut and help line break equals the unhooked render's (V10-2, V12-1). The id comes
after the text, so comparing or sorting two wrapped strings compares their texts first.

After rendering, :func:`trace` walks the markers: each span of the pattern (``pt_pattern``) lies inside exactly one
innermost marker, which is its source; a span outside every marker, or across a marker boundary, is untraced.

Nodes are keyed by ``(line, column)`` inside one parse; calls and names are resolved by import; an unreadable input
fails closed.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.abc
import importlib.machinery
import re
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pt_pattern

UNIT_OPEN, UNIT_ID, UNIT_CLOSE = "\ue000", "\ue001", "\ue002"
VALUE_OPEN, VALUE_ID, VALUE_CLOSE = "\ue003", "\ue004", "\ue005"
MARKER_CHARS = frozenset(UNIT_OPEN + UNIT_ID + UNIT_CLOSE + VALUE_OPEN + VALUE_ID + VALUE_CLOSE)
MARKER_BYTES = tuple(c.encode("utf-8") for c in sorted(MARKER_CHARS))
_IDS = re.compile("[\ue001\ue004][^\ue000-\ue005]*[\ue002\ue005]")
_OPENS = re.compile("[\ue000\ue003]")

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = SRC / "aew"


def hook_functions() -> dict[tuple[str, str], str]:
    """The hook functions (§2.1, V11-1), (module, qualified name) -> kind: derived from the tree by the render-set scan
    and the producer dispositions (``pt_scan``), never listed by hand."""
    import pt_scan

    return pt_scan.hook_functions()


ALLOWED_KINDS = frozenset({"renderer", "producer:worker text", "producer:fenced", "manual-delivery", "parser-builder",
                           "result-method"})

# The position classes (§2.2; the hook scan's part 1, first match wins). Only `output` constants with a space are
# wrapped.
LOOKUP = frozenset({"get", "startswith", "endswith", "split", "rsplit", "replace", "setdefault", "pop", "index",
                    "count", "removeprefix", "removesuffix", "match", "search", "sub", "fullmatch"})
LOGGING = frozenset({"debug", "info", "warning", "error", "exception", "critical", "log"})
PARSER_CALLS = frozenset({"add_parser", "add_argument", "add_subparsers", "add_argument_group", "ArgumentParser"})
HELP_KEYWORDS = frozenset({"help", "description", "epilog", "metavar", "usage"})
ORDER = ("docstring", "raise", "log", "semantic", "dict-key", "output")


class HookError(Exception):
    """The hook cannot be applied soundly (an unreadable module, a hook function missing from its module)."""


# ------------------------------------------------------------------------------------------------ markers and stripping


def strip(text: str) -> str:
    """``text`` with every marker and marker id removed: what the unhooked render would have printed."""
    return _OPENS.sub("", _IDS.sub("", text))


def strip_bytes(data: bytes) -> bytes:
    if not any(b in data for b in MARKER_BYTES):
        return data
    return strip(data.decode("utf-8")).encode("utf-8")


def has_marker_chars(text: str) -> bool:
    return any(c in MARKER_CHARS for c in text)


def wrap_unit(text: str, uid: str) -> str:
    return f"{UNIT_OPEN}{text}{UNIT_ID}{uid}{UNIT_CLOSE}"


def wrap_value(text: str, vid: str) -> str:
    return f"{VALUE_OPEN}{text}{VALUE_ID}{vid}{VALUE_CLOSE}"


def wrap_core(text: str, wrap: Callable[[str], str]) -> str:
    """``text`` with only its core wrapped, leading and trailing whitespace left outside the marker, so a renderer's
    ``strip()`` of a data value still strips it (all-whitespace text is left unwrapped: it holds no span)."""
    core = text.strip()
    if not core:
        return text
    start = text.index(core)
    return text[:start] + wrap(core) + text[start + len(core):]


@dataclass
class Marker:
    kind: str  # "unit" or "value"
    ident: str
    start: int  # in stripped coordinates
    end: int
    parent: Marker | None = None
    children: list[Marker] = field(default_factory=list)


class UnbalancedMarkers(Exception):
    """A marker opened and never closed, closed without opening, or closed by the other kind: fails closed (v9)."""


def parse(text: str) -> tuple[str, list[Marker]]:
    """The stripped text and the marker forest over it. Raises :class:`UnbalancedMarkers` on any malformed marker."""
    out: list[str] = []
    roots: list[Marker] = []
    stack: list[Marker] = []
    pos = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in (UNIT_OPEN, VALUE_OPEN):
            m = Marker("unit" if c == UNIT_OPEN else "value", "", pos, -1, stack[-1] if stack else None)
            (stack[-1].children if stack else roots).append(m)
            stack.append(m)
            i += 1
        elif c in (UNIT_ID, VALUE_ID):
            if not stack or (stack[-1].kind == "unit") != (c == UNIT_ID):
                raise UnbalancedMarkers(f"an id separator with no open marker of its kind at {i}")
            close = UNIT_CLOSE if c == UNIT_ID else VALUE_CLOSE
            j = text.find(close, i + 1)
            if j < 0 or has_marker_chars(text[i + 1:j]):
                raise UnbalancedMarkers(f"an unterminated marker id at {i}")
            m = stack.pop()
            m.ident, m.end = text[i + 1:j], pos
            i = j + 1
        elif c in (UNIT_CLOSE, VALUE_CLOSE):
            raise UnbalancedMarkers(f"a marker close with no id at {i}")
        else:
            out.append(c)
            pos += 1
            i += 1
    if stack:
        raise UnbalancedMarkers(f"{len(stack)} marker(s) never closed")
    return "".join(out), roots


def _innermost(markers: list[Marker], start: int, end: int) -> Marker | None:
    for m in markers:
        if m.start <= start and end <= m.end:
            inner = _innermost(m.children, start, end)
            return inner or m
    return None


def span_source(roots: list[Marker], start: int, end: int) -> tuple[Marker | None, str]:
    """The innermost marker holding the whole span, and why it is not a source when it is not: a span that crosses a
    child marker's boundary belongs to neither (``straddles``); a span outside every marker is ``unmarked``."""
    m = _innermost(roots, start, end)
    if m is None:
        return None, "unmarked"
    for ch in m.children:
        if ch.start < end and start < ch.end:  # overlaps a child it is not inside
            return None, "straddles"
    return m, ""


def chain(m: Marker | None) -> list[Marker]:
    out = []
    while m is not None:
        out.append(m)
        m = m.parent
    return out


# --------------------------------------------------------------------------------------- the inventory's unit identity


def norm(text: str) -> str:
    return " ".join(text.split())


def key_hash(text: str) -> str:
    """The inventory's key hash: of the full normalised text, never a prefix (§2.6)."""
    return hashlib.sha256(norm(text).encode("utf-8")).hexdigest()[:16]


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(SRC).with_suffix("").parts).removesuffix(".__init__")


def _module_constants(tree: ast.Module) -> dict[str, str]:
    consts = {}
    for st in tree.body:
        if isinstance(st, ast.Assign) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
            for t in st.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = st.value.value
    return consts


_CONSTS: dict[str, dict[str, str]] | None = None
_CONST_LINES: dict[str, dict[str, int]] | None = None


def all_constant_lines() -> dict[str, dict[str, int]]:
    """Module dotted name -> the line of each of its module-level string constants (a name's last assignment)."""
    global _CONST_LINES
    if _CONST_LINES is None:
        out: dict[str, dict[str, int]] = {}
        for p in sorted(PKG.rglob("*.py")):
            lines = out.setdefault(_module_name(p), {})
            for st in ast.parse(_read(p)).body:
                if isinstance(st, ast.Assign) and isinstance(st.value, ast.Constant) and \
                        isinstance(st.value.value, str):
                    for t in st.targets:
                        if isinstance(t, ast.Name):
                            lines[t.id] = st.lineno
        _CONST_LINES = out
    return _CONST_LINES


def all_constants() -> dict[str, dict[str, str]]:
    """Module dotted name -> its module-level string constants, for resolving an f-string's names across imports."""
    global _CONSTS
    if _CONSTS is None:
        out = {}
        for p in sorted(PKG.rglob("*.py")):
            out[_module_name(p)] = _module_constants(ast.parse(_read(p)))
        _CONSTS = out
    return _CONSTS


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # fail closed: an unreadable input is never skipped
        raise HookError(f"cannot read {path}: {exc}") from exc


def _import_map(tree: ast.Module, mod: str) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    consts = all_constants()
    names: dict[str, tuple[str, str]] = {}
    mods: dict[str, str] = {}
    for st in ast.walk(tree):
        if isinstance(st, ast.ImportFrom) and st.module:
            base = st.module
            if st.level:
                base = ".".join(mod.split(".")[:-st.level] + [st.module])
            for a in st.names:
                full = f"{base}.{a.name}"
                if full in consts:
                    mods[a.asname or a.name] = full
                else:
                    names[a.asname or a.name] = (base, a.name)
        elif isinstance(st, ast.Import):
            for a in st.names:
                mods[a.asname or a.name.split(".")[0]] = a.name
    return names, mods


def _render_fstring(node: ast.JoinedStr, text: str, local: dict[str, str], names: dict[str, tuple[str, str]],
                    mods: dict[str, str]) -> str:
    """The inventory's rendering of an f-string unit: constant parts as written, a name bound to a module constant
    (resolved by import) as its value, anything else as ``{source}``."""
    consts = all_constants()
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(str(v.value))
        elif isinstance(v, ast.FormattedValue):
            e = v.value
            sub = None
            if isinstance(e, ast.Name):
                sub = local.get(e.id)
                if sub is None and e.id in names:
                    m, n = names[e.id]
                    sub = consts.get(m, {}).get(n)
            elif isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id in mods:
                sub = consts.get(mods[e.value.id], {}).get(e.attr)
            parts.append(sub if sub is not None else "{" + (ast.get_source_segment(text, e) or "?") + "}")
    return "".join(parts)


def _outer_scopes(tree: ast.Module) -> dict[tuple[int, int], str]:
    """(line, column) of every node -> the outermost enclosing definition (``Class.method`` or a function), else
    ``<module>``: the inventory's scope."""
    out: dict[tuple[int, int], str] = {}

    def visit(node: ast.AST, scope: str, cls: str | None) -> None:
        for ch in ast.iter_child_nodes(node):
            s, c = scope, cls
            if scope == "<module>" and isinstance(ch, ast.ClassDef):
                c = ch.name
            elif isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) and scope == "<module>":
                s = f"{cls}.{ch.name}" if cls else ch.name
            if hasattr(ch, "lineno"):
                out.setdefault((ch.lineno, ch.col_offset), s)  # type: ignore[attr-defined]
            visit(ch, s, c if isinstance(ch, ast.ClassDef) or c else None)

    visit(tree, "<module>", None)
    return out


def qualnames(tree: ast.Module, *, strict: bool = True) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Qualified name -> definition, for every function and method (``f.<locals>.g`` for nested ones). A name defined
    twice (a platform branch) fails when ``strict``; otherwise the later one is named ``<name>#2``."""
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def visit(node: ast.AST, prefix: list[str]) -> None:
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.ClassDef):
                visit(ch, [*prefix, ch.name])
            elif isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = ".".join([*prefix, ch.name])
                if q in out:
                    if strict:
                        raise HookError(f"two definitions named {q}")
                    q = next(f"{q}#{i}" for i in range(2, 100) if f"{q}#{i}" not in out)
                out[q] = ch
                visit(ch, [*prefix, ch.name, "<locals>"])
            else:
                visit(ch, prefix)

    visit(tree, [])
    return out


# ---------------------------------------------------------------------------------------- position classification


Key = tuple[Any, ...]


def node_keys(root: ast.AST) -> dict[int, Key]:
    """id(node) -> the node's key, for every positioned node under ``root``, within this one parse (ids are never
    compared across parses). A node's key is its ``(line, column, end line, end column, type)``. Inside an f-string,
    Python before 3.12 places every part (a constant, an interpolation, a format spec) at the f-string's own position,
    so a part's key is its f-string's key plus its index, and a format spec's is its interpolation's key plus "spec":
    the same keys on every supported Python."""
    keys: dict[int, Key] = {}

    def fstring(js: ast.JoinedStr, base: Key) -> None:
        keys[id(js)] = base
        for i, v in enumerate(js.values):
            k = (*base, "part", i)
            keys[id(v)] = k
            if isinstance(v, ast.FormattedValue) and isinstance(v.format_spec, ast.JoinedStr):
                fstring(v.format_spec, (*k, "spec"))

    for n in ast.walk(root):
        if id(n) in keys or not hasattr(n, "lineno"):
            continue
        base = (n.lineno, n.col_offset, n.end_lineno, n.end_col_offset, type(n).__name__)  # type: ignore[attr-defined]
        if isinstance(n, ast.JoinedStr):
            fstring(n, base)
        else:
            keys[id(n)] = base
    return keys


def _strings(node: ast.AST, keys: dict[int, Key] | None = None) -> list[Key]:
    keys = keys if keys is not None else node_keys(node)
    return [keys[id(k)] for k in ast.walk(node) if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def positions(fn: ast.AST) -> dict[Key, str]:
    """Every string constant in ``fn`` -> its position class (§2.2), first match wins; an `output` constant without
    a space is `output-spaceless` (V11-1) and is not wrapped."""
    keys = node_keys(fn)

    def k(x: ast.AST) -> Key:
        return keys[id(x)]

    def strings(x: ast.AST) -> set[Key]:
        return set(_strings(x, keys))

    cls: dict[str, set[Key]] = {c: set() for c in ORDER}
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant):
            cls["docstring"] |= strings(n.body[0].value)
        if isinstance(n, ast.Raise):
            cls["raise"] |= strings(n)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in LOGGING:
            for a in n.args:
                cls["log"] |= strings(a)
        if isinstance(n, ast.Subscript):
            cls["semantic"] |= strings(n.slice)
        if isinstance(n, ast.Compare):
            for x in (n.left, *n.comparators):
                cls["semantic"] |= strings(x)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in LOOKUP and n.args:
            cls["semantic"] |= strings(n.args[0])
        if isinstance(n, ast.Dict):
            for key in n.keys:
                if key is not None:
                    cls["dict-key"] |= strings(key)
            for v in n.values:
                cls["output"] |= strings(v)
        if isinstance(n, ast.JoinedStr):
            cls["output"] |= {k(v) for v in n.values if isinstance(v, ast.Constant)}
        if isinstance(n, (ast.List, ast.Tuple)):
            cls["output"] |= {k(e) for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            cls["output"] |= {k(x) for x in (n.left, n.right) if isinstance(x, ast.Constant)}
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "join":
                for x in (n.func.value, *n.args):
                    if isinstance(x, ast.Constant):
                        cls["output"].add(k(x))
            if n.func.attr in ("append", "extend", "insert"):
                cls["output"] |= {k(a) for a in n.args if isinstance(a, ast.Constant)}
        if isinstance(n, ast.Call) and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) in PARSER_CALLS:
            for kw in n.keywords:
                if kw.arg in HELP_KEYWORDS:
                    cls["output"] |= strings(kw.value)
        if isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add) and isinstance(n.value, ast.Constant):
            cls["output"].add(k(n.value))
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant):
            cls["output"].add(k(n.value))
    value = {k(c): c.value for c in ast.walk(fn) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
    out = {}
    for p in _strings(fn, keys):
        c = next((name for name in ORDER if p in cls[name]), "other")
        out[p] = "output-spaceless" if c == "output" and " " not in value[p] else c
    return out


# ---------------------------------------------------------------------------------------------------- the rewrite


@dataclass
class Registry:
    """What the hooked process wrapped: unit ids and expression ids, with their sources (emitted beside the render)."""

    units: dict[str, dict[str, Any]] = field(default_factory=dict)
    values: dict[str, dict[str, Any]] = field(default_factory=dict)

    def unit(self, info: dict[str, Any]) -> str:
        uid = f"u{len(self.units)}"
        self.units[uid] = info
        return uid

    def value(self, info: dict[str, Any]) -> str:
        vid = f"v{len(self.values)}"
        self.values[vid] = info
        return vid


REGISTRY = Registry()


def hook_modules() -> dict[str, list[str]]:
    """Module file (relative to src/aew) -> the qualified names of its hook functions."""
    out: dict[str, list[str]] = {}
    for (rel, qual) in hook_functions():
        out.setdefault(rel, []).append(qual)
    return out


@dataclass(frozen=True)
class Plan:
    """What a module's rewrite does, decided before any node changes (so the classification sees the original). Its
    ``keys`` belong to the one parse it was made from, which the rewrite then transforms."""

    keys: dict[int, Key]
    wrapped: dict[Key, str]  # an output constant -> its unit id
    values: dict[Key, str]  # an interpolated expression -> its expression id
    refs: dict[Key, dict[str, str]]  # a name bound to constants -> {constant text: unit id}
    data: dict[str, tuple[ast.expr, dict[Key, str]]]  # a module display a hook function reads -> its leaves' unit ids
    counts: dict[str, int]
    nodes: list[ast.AST]  # every original node, kept alive so no id in ``keys`` is ever reused
    ref_sites: dict[Key, tuple[str, str, int]] = field(default_factory=dict)  # a ref -> (function, expression, line)


def _const_choices(expr: ast.expr) -> list[ast.Constant] | None:
    """The string constants ``expr`` can evaluate to, when it can evaluate only to one of them."""
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [expr]
    if isinstance(expr, ast.IfExp):
        a, b = _const_choices(expr.body), _const_choices(expr.orelse)
        return a + b if a is not None and b is not None else None
    return None


def _bindings(fn: ast.AST, name: str) -> list[ast.expr] | None:
    """The values assigned to ``name`` in ``fn`` when every binding of it there is a plain ``name = <value>``; None when
    any binding is another kind (a parameter, a loop or ``with`` target, an augmented or unpacking assignment)."""
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = fn.args
        if name in {x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs, *([a.vararg] if a.vararg else []),
                                    *([a.kwarg] if a.kwarg else [])]}:
            return None
    parents = {id(ch): p for p in ast.walk(fn) for ch in ast.iter_child_nodes(p)}  # one parse: ids are stable here
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del)):
            p = parents.get(id(n))
            if not (isinstance(p, ast.Assign) and len(p.targets) == 1 and p.targets[0] is n):
                return None
            out.append(p.value)
    return out


def plan_module(rel: str, source: str, *, plants: dict[Key, str] | None = None,
                registry: Registry | None = None) -> tuple[ast.Module, Plan]:
    """Classify the module's hook functions and allocate an id for everything the hook wraps there:
    - an output-position constant with a space: a unit (the inventory's key: the outermost f-string, else itself);
    - an interpolation beside such a constant (an f-string's value, or a ``+`` operand): a value;
    - a name in an output position that is bound to string constants (a module constant, resolved by import, or a
      local assigned only constants): a unit of the constant it holds, checked at run time;
    - a module-level display of constants that a hook function reads: its leaves, as units, after the module runs."""
    reg = registry if registry is not None else REGISTRY
    tree = ast.parse(source)
    keys = node_keys(tree)

    def key(n: ast.AST) -> Key:
        return keys[id(n)]

    defs = qualnames(tree)
    quals = hook_modules().get(rel, [])
    pos: dict[Key, str] = {}
    counts: dict[str, int] = {}
    for q in quals:
        fn = defs.get(q)
        if fn is None:
            raise HookError(f"hook function {rel}:{q} is not in the module")
        p = positions(fn)
        for v in p.values():
            counts[v] = counts.get(v, 0) + 1  # per function, as the scan counts (a nested function counts twice)
        pos.update(p)
    mod = _module_name(PKG / rel)
    local = _module_constants(tree)
    names, mods = _import_map(tree, mod)
    scopes = _outer_scopes(tree)
    file = f"src/aew/{rel}"
    constants = {key(n): n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    # The inventory's unit for a constant inside an f-string is the outermost f-string.
    owner: dict[Key, ast.JoinedStr] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr):
            for m in ast.walk(n):
                if isinstance(m, ast.Constant) and key(m) not in owner:
                    owner[key(m)] = n
    wrapped: dict[Key, str] = {}
    for p, c in sorted(pos.items(), key=lambda item: repr(item[0])):
        if c != "output":
            continue
        node = constants[p]
        js = owner.get(p)
        unit_text = _render_fstring(js, source, local, names, mods) if js is not None else node.value
        at = (js.lineno, js.col_offset) if js is not None else (node.lineno, node.col_offset)
        wrapped[p] = reg.unit({"kind": "code", "file": file, "line": at[0], "col": at[1],
                               "scope": scopes.get(at, "<module>"), "hash": key_hash(unit_text),
                               "planted": (plants or {}).get(p)})

    module_assign = {t.id: st for st in tree.body if isinstance(st, ast.Assign) for t in st.targets
                     if isinstance(t, ast.Name)}

    def module_constant(e: ast.expr) -> tuple[str, int, str] | None:
        """(file, line, text) of the module-level string constant ``e`` names, resolved by import."""
        if isinstance(e, ast.Name) and e.id in local:
            return file, module_assign[e.id].lineno, local[e.id]
        consts, lines = all_constants(), all_constant_lines()
        if isinstance(e, ast.Name) and e.id in names:
            m, n = names[e.id]
            if n in consts.get(m, {}):
                return f"src/{m.replace('.', '/')}.py", lines[m][n], consts[m][n]
        if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id in mods:
            m = mods[e.value.id]
            if e.attr in consts.get(m, {}):
                return f"src/{m.replace('.', '/')}.py", lines[m][e.attr], consts[m][e.attr]
        return None

    values: dict[Key, str] = {}
    refs: dict[Key, dict[str, str]] = {}
    ref_sites: dict[Key, tuple[str, str, int]] = {}
    data: dict[str, tuple[ast.expr, dict[Key, str]]] = {}

    def ref_choices(fn: ast.AST, e: ast.expr) -> dict[str, str] | None:
        found = module_constant(e)
        if found is not None:
            f, line, text = found
            if " " not in text:
                return None
            return {text: reg.unit({"kind": "code", "file": f, "line": line, "col": 0, "scope": "<module>",
                                    "hash": key_hash(text), "planted": None, "via": "name"})}
        if not isinstance(e, ast.Name):
            return None
        binds = _bindings(fn, e.id)
        if binds is None or not binds:
            return None
        choices: list[ast.Constant] = []
        for value in binds:
            got = _const_choices(value)
            if got is None:
                return None
            choices += got
        if not choices or not all(" " in c.value for c in choices):
            return None
        out = {}
        for c in choices:
            out[c.value] = reg.unit({"kind": "code", "file": file, "line": c.lineno, "col": c.col_offset,
                                     "scope": scopes.get((c.lineno, c.col_offset), "<module>"),
                                     "hash": key_hash(c.value), "planted": None, "via": "local"})
        return out

    def interpolate(fn: ast.AST, q: str, e: ast.expr) -> None:
        s = key(e)
        if s in values or s in refs or isinstance(e, (ast.Constant, ast.Starred)):
            return
        choices = ref_choices(fn, e)
        expr = ast.get_source_segment(source, e) or ast.unparse(e)
        if choices is not None:
            refs[s] = choices
            ref_sites[s] = (q, expr, e.lineno)
            return
        values[s] = reg.value({"file": file, "line": e.lineno, "col": e.col_offset, "function": q, "expr": expr,
                               "kind": "operand"})

    def is_prose(e: ast.expr) -> bool:
        if isinstance(e, ast.Constant):
            return key(e) in wrapped
        if isinstance(e, ast.JoinedStr):
            return any(key(v) in wrapped for v in e.values if isinstance(v, ast.Constant))
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
            return is_prose(e.left) or is_prose(e.right)
        return False

    for q in quals:
        fn = defs[q]
        for n in ast.walk(fn):
            if isinstance(n, ast.JoinedStr) and is_prose(n):
                for v in n.values:
                    if isinstance(v, ast.FormattedValue):
                        if v.conversion == -1 and v.format_spec is None and ref_choices(fn, v.value) is not None:
                            interpolate(fn, q, v.value)
                        elif key(v) not in values:
                            values[key(v)] = reg.value({  # the expression's own position: the same on every Python
                                "file": file, "line": v.value.lineno, "col": v.value.col_offset, "function": q,
                                "expr": ast.get_source_segment(source, v.value) or ast.unparse(v.value),
                                "kind": "fstring"})
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add) and (is_prose(n.left) or is_prose(n.right)):
                for side in (n.left, n.right):
                    if not is_prose(side):
                        interpolate(fn, q, side)
            if isinstance(n, ast.Call) and (getattr(n.func, "attr", None) or getattr(n.func, "id", None)) in \
                    PARSER_CALLS:
                for kw in n.keywords:
                    if kw.arg in HELP_KEYWORDS and ref_choices(fn, kw.value) is not None:
                        interpolate(fn, q, kw.value)
            if isinstance(n, (ast.List, ast.Tuple)):
                for e in n.elts:
                    if not isinstance(e, ast.Constant) and ref_choices(fn, e) is not None:
                        interpolate(fn, q, e)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in module_assign and \
                    isinstance(module_assign[n.id].value, (ast.Dict, ast.List, ast.Tuple)) and n.id not in data \
                    and _bindings(fn, n.id) == []:
                leaves = {}
                display = module_assign[n.id].value
                dict_keys = {id(k) for d in ast.walk(display) if isinstance(d, ast.Dict) for k in d.keys}
                in_fstring = {id(m) for d in ast.walk(display) if isinstance(d, ast.JoinedStr) for m in ast.walk(d)}
                for c in ast.walk(display):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and " " in c.value and \
                            id(c) not in dict_keys and id(c) not in in_fstring:
                        leaves[key(c)] = reg.unit({
                            "kind": "code", "file": file, "line": c.lineno, "col": c.col_offset, "scope": "<module>",
                            "hash": key_hash(c.value), "planted": (plants or {}).get(key(c)),
                            "via": f"module data {n.id}"})
                if leaves:
                    data[n.id] = (display, leaves)
    return tree, Plan(keys, wrapped, values, refs, data, counts, list(ast.walk(tree)), ref_sites)


class _Rewrite(ast.NodeTransformer):
    """Applies a plan to the parse it was made from. Only original nodes are ever looked up (a replacement is never
    visited), and the plan keeps every original alive, so an id always names the node it was taken from."""

    def __init__(self, plan: Plan, plants: dict[Key, str]) -> None:
        self.plan = plan
        self.plants = plants

    def key(self, node: ast.AST) -> Key | None:
        return self.plan.keys.get(id(node))

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        uid = self.plan.wrapped.get(self.key(node))  # type: ignore[arg-type]
        if uid is None or not isinstance(node.value, str):
            return node
        text = node.value
        token = self.plants.get(self.key(node))
        if token:
            text = f"{text} {token} "
        return ast.copy_location(ast.Constant(wrap_unit(text, uid)), node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> ast.AST:
        vid = self.plan.values.get(self.key(node))  # type: ignore[arg-type]
        self.generic_visit(node)
        if vid is None:
            return node
        spec: ast.expr = node.format_spec if node.format_spec is not None else ast.Constant(None)
        call = ast.Call(ast.Name("_pt_hook_fv", ast.Load()), [node.value, ast.Constant(node.conversion), spec,
                                                              ast.Constant(vid)], [])
        return ast.copy_location(ast.FormattedValue(ast.copy_location(call, node), -1, None), node)

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.expr) and not isinstance(node, ast.FormattedValue):
            s = self.plan.keys.get(id(node))
            if s is not None and (s in self.plan.values or s in self.plan.refs):
                inner = super().visit(node)
                if s in self.plan.refs:
                    choices = ast.Dict([ast.Constant(k) for k in self.plan.refs[s]],
                                       [ast.Constant(v) for v in self.plan.refs[s].values()])
                    call = ast.Call(ast.Name("_pt_hook_ref", ast.Load()), [inner, choices], [])
                else:
                    call = ast.Call(ast.Name("_pt_hook_value", ast.Load()), [inner, ast.Constant(self.plan.values[s])],
                                    [])
                return ast.copy_location(call, node)
        return super().visit(node)


def _fv(value: Any, conversion: int, spec: str | None, vid: str) -> str:
    """An interpolation, formatted exactly as the f-string would, then wrapped as a value."""
    if conversion == ord("r"):
        value = repr(value)
    elif conversion == ord("s"):
        value = str(value)
    elif conversion == ord("a"):
        value = ascii(value)
    text = format(value, spec or "")
    return wrap_value(text, vid) if text else text


def _value(value: Any, vid: str) -> Any:
    """A ``+`` operand: a non-empty string is wrapped as a value; anything else is returned unchanged."""
    return wrap_core(value, lambda core: wrap_value(core, vid)) if isinstance(value, str) else value


def _ref(value: Any, choices: dict[str, str]) -> Any:
    """A name bound to string constants: wrapped as the unit of the constant it holds; any other value (not one of
    them) is returned unchanged, so its spans stay untraced."""
    return wrap_unit(value, choices[value]) if isinstance(value, str) and value in choices else value


def wrap_data(obj: Any, display: ast.expr, leaves: dict[Key, str], keys: dict[int, Key]) -> Any:
    """A module-level display's runtime value with each prose leaf wrapped as its constant's unit, walked beside the
    display's AST; a value that does not match its display is returned unchanged (fail closed: it stays untraced)."""
    if isinstance(display, ast.Constant):
        uid = leaves.get(keys[id(display)])
        return wrap_unit(obj, uid) if uid and isinstance(obj, str) and obj == display.value else obj
    if isinstance(display, ast.Dict) and isinstance(obj, dict) and \
            all(isinstance(k, ast.Constant) for k in display.keys):
        names = [k.value for k in display.keys]  # type: ignore[union-attr]
        if names != list(obj):
            return obj
        return {k: wrap_data(obj[k], v, leaves, keys) for k, v in zip(names, display.values, strict=True)}
    if isinstance(display, (ast.List, ast.Tuple)) and isinstance(obj, (list, tuple)) and len(obj) == len(display.elts):
        out = [wrap_data(o, d, leaves, keys) for o, d in zip(obj, display.elts, strict=True)]
        return tuple(out) if isinstance(obj, tuple) else out
    return obj


def rewrite(rel: str, source: str, *, plants: dict[Key, str] | None = None,
            registry: Registry | None = None) -> tuple[ast.Module, Plan]:
    tree, plan = plan_module(rel, source, plants=plants, registry=registry)
    tree = _Rewrite(plan, plants or {}).visit(tree)
    ast.fix_missing_locations(tree)
    return tree, plan


# ------------------------------------------------------------------------------------------------------ YAML data


def yaml_leaves(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """``(path, text)`` for every string leaf, in the inventory's path form (``a.b[0]``)."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from yaml_leaves(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from yaml_leaves(v, f"{path}[{i}]")


def wrap_yaml(obj: Any, rel: str, *, plants: dict[str, str] | None = None, registry: Registry | None = None,
              path: str = "") -> Any:
    """``obj`` with every prose leaf (a string with a space: never a key or an enumerated id) wrapped as a unit keyed
    ``(rel, path, hash)``, the inventory's data key."""
    reg = registry if registry is not None else REGISTRY
    if isinstance(obj, str):
        if " " not in obj:
            return obj
        token = (plants or {}).get(path)
        uid = reg.unit({"kind": "yaml", "file": rel, "scope": path, "hash": key_hash(obj), "planted": token})
        return wrap_core(f"{obj} {token}" if token else obj, lambda core: wrap_unit(core, uid))
    if isinstance(obj, dict):
        return {k: wrap_yaml(v, rel, plants=plants, registry=reg, path=f"{path}.{k}" if path else str(k))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [wrap_yaml(v, rel, plants=plants, registry=reg, path=f"{path}[{i}]") for i, v in enumerate(obj)]
    return obj


# -------------------------------------------------------------------------------------------- measuring stripped text


def _split_lines_stripped(original: Callable[[Any, str, int], list[str]]) -> Callable[[Any, str, int], list[str]]:
    def split(self: Any, text: str, width: int) -> list[str]:
        if not has_marker_chars(text):
            return original(self, text, width)
        return _project(text, original(self, strip(text), width))
    return split


def _fill_text_stripped(original: Callable[[Any, str, int, str], str]) -> Callable[[Any, str, int, str], str]:
    def fill(self: Any, text: str, width: int, indent: str) -> str:
        if not has_marker_chars(text):
            return original(self, text, width, indent)
        lines = original(self, strip(text), width, indent).split("\n")
        return "\n".join(_project(text, lines, indent=indent))
    return fill


def _project(marked: str, lines: list[str], *, indent: str = "") -> list[str]:
    """Re-insert ``marked``'s markers into ``lines``, the wrapping of its stripped text, so the visible text of the
    result is exactly ``lines``. Each visible character of a line is matched in order against ``marked``; whitespace
    the wrapper collapsed or dropped is skipped; markup before a character goes with it, and a marker id and close
    right after a line's last character stay on that line. A marker may span a line break. Anything that does not
    match fails closed."""
    out: list[str] = []
    i, n = 0, len(marked)

    def markup(*, opening: bool) -> str:
        nonlocal i
        got = []
        while i < n:
            c = marked[i]
            if c in (UNIT_ID, VALUE_ID):
                j = marked.find(UNIT_CLOSE if c == UNIT_ID else VALUE_CLOSE, i)
                if j < 0:
                    raise UnbalancedMarkers("an unterminated marker id in help text")
                got.append(marked[i:j + 1])
                i = j + 1
            elif opening and c in (UNIT_OPEN, VALUE_OPEN):
                got.append(c)
                i += 1
            else:
                break
        return "".join(got)

    for line in lines:
        prefix = indent if indent and line.startswith(indent) else ""
        buf = [prefix]
        for ch in line[len(prefix):]:
            while True:
                buf.append(markup(opening=True))
                if i < n and marked[i].isspace() and not ch.isspace():
                    i += 1  # whitespace the wrapper collapsed or dropped at a break
                    continue
                break
            if i >= n or (marked[i] != ch and not (ch.isspace() and marked[i].isspace())):
                raise UnbalancedMarkers(f"a wrapped help line does not match its text at {i}: {line!r}")
            buf.append(ch)
            i += 1
            if ch.isspace():  # the wrapper collapsed a run of whitespace (markup inside it is kept) to this one
                while i < n and (marked[i].isspace() or marked[i] in MARKER_CHARS):
                    if marked[i].isspace():
                        i += 1
                        continue
                    got = markup(opening=True)
                    if not got:
                        raise UnbalancedMarkers(f"a stray marker close in help text at {i}")
                    buf.append(got)
        buf.append(markup(opening=False))
        out.append("".join(buf))
    rest = []
    while i < n:  # whitespace and markup after the last line
        if marked[i].isspace():
            i += 1
        elif marked[i] in MARKER_CHARS:
            got = markup(opening=True)
            if not got:
                raise UnbalancedMarkers(f"a stray marker close in help text at {i}")
            rest.append(got)
        else:
            raise UnbalancedMarkers("a wrapped help text lost visible text")
    if out:
        out[-1] += "".join(rest)
    return out


# ------------------------------------------------------------------------------------------------------ the finder


class _Loader(importlib.machinery.SourceFileLoader):
    """Compiles a hook module from its rewritten AST (never from a cached ``.pyc``), then applies the module's patch."""

    rel: str = ""
    plants: dict[Key, str] = {}  # noqa: RUF012 (set per instance before use)
    after: Callable[[Any], None] | None = None
    plan: Plan | None = None

    def get_code(self, fullname: str) -> Any:
        path = self.get_filename(fullname)
        source = _read(Path(path))
        if not self.rel:
            return compile(source, path, "exec", dont_inherit=True)
        tree, self.plan = rewrite(self.rel, source, plants=self.plants)
        return compile(tree, path, "exec", dont_inherit=True)

    def exec_module(self, module: Any) -> None:
        module.__dict__.update(_pt_hook_fv=_fv, _pt_hook_value=_value, _pt_hook_ref=_ref)
        super().exec_module(module)
        for edit in MODULE_EDITS.get(module.__name__, ()):  # a negative control's import-time product edit
            edit(module)
        for name, (display, leaves) in (self.plan.data if self.plan else {}).items():
            module.__dict__[name] = wrap_data(module.__dict__[name], display, leaves, self.plan.keys)  # type: ignore[union-attr]
        if self.after is not None:
            self.after(module)


class Finder(importlib.abc.MetaPathFinder):
    def __init__(self, plants: dict[str, dict[Key, str]], patches: dict[str, Callable[[Any], None]]):
        self.modules = {"aew." + rel[:-3].replace("/", "."): rel for rel in hook_modules()}
        self.plants = plants
        self.patches = patches

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        if fullname not in self.modules and fullname not in self.patches and fullname not in MODULE_EDITS:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.origin is None:
            raise HookError(f"cannot find {fullname} to hook it")
        loader = _Loader(fullname, spec.origin)
        loader.rel = self.modules.get(fullname, "")
        loader.plants = self.plants.get(loader.rel, {})
        loader.after = self.patches.get(fullname)
        spec.loader = loader
        return spec


def _patch_util(module: Any) -> None:
    original = module.sha256_bytes

    def sha256_bytes(data: bytes) -> str:
        return original(strip_bytes(data))

    module.sha256_bytes = sha256_bytes  # sha256_text calls it through the module, so both measure stripped text


def _patch_context(module: Any) -> None:
    def _size(lines: list[str]) -> int:
        return sum(len(strip(line)) + 1 for line in lines)

    module._size = _size


def _patch_roles(yaml_plants: dict[str, dict[str, str]]) -> Callable[[Any], None]:
    """The role archetype loader wraps its YAML's prose leaves (§2.2, data)."""
    def patch(module: Any) -> None:
        original = module.load_yaml

        def load_yaml(text: str, *, source: str = "<yaml>") -> Any:
            data = original(text, source=source)
            if source.startswith("archetypes/"):
                rel = f"src/aew/roles/{source}"
                return wrap_yaml(data, rel, plants=yaml_plants.get(rel))
            return data

        module.load_yaml = load_yaml
    return patch


def pinned_card(card: dict[str, Any] | None) -> tuple[str, Any] | None:
    """A pinned built-in card's YAML file and its content, when the pin is provably that file: its sha256 is the file's
    and the pinned content equals the file's. Anything else is None (and its text stays unwrapped, so untraced)."""
    import yaml

    if not card or not str(card.get("path") or "").startswith("aew/roles/cards/"):
        return None
    path = SRC / card["path"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != card.get("sha256"):
        return None
    content = yaml.safe_load(raw.decode("utf-8"))
    if content != card.get("content"):
        return None
    return f"src/{card['path']}", content


# The pack's authored inputs (v8 §2.1: the requirement, plan, inlined guardrails, project configuration and included
# evidence records), fenced where they enter the pack: (field, the leaves fenced; "" for the field itself, "*" for every
# string leaf). A fenced span is attributed to the authored source, never judged as product text.
FENCED_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("",), "record_body": ("",), "record_meta": ("*",), "plan_text": ("",), "guardrails_text": ("",),
    "checks": ("*.description",), "authority": ("*.path",), "diff": ("",), "diffstat": ("",),
    "implementation_summary": ("*",), "open_findings": ("*.summary", "*.location"),
    "failure_evidence": ("claims.*.claim", "suspected_cause"), "hierarchy": ("*.title", "*.goal_backwards.*"),
    "subject": ("content", "body"), "children": ("*.title", "*.diff"), "aggregate_diffstat": ("",),
}


def fence(obj: Any, name: str, registry: Registry | None = None) -> Any:
    """Every non-empty string leaf of ``obj`` wrapped as a fenced value named ``name`` (and its path)."""
    reg = registry if registry is not None else REGISTRY
    if isinstance(obj, str):
        return wrap_core(obj, lambda core: wrap_value(core, reg.value({"fence": name, "kind": "fence"})))
    if isinstance(obj, dict):
        return {k: fence(v, f"{name}.{k}", reg) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fence(v, f"{name}[{i}]", reg) for i, v in enumerate(obj)]
    return obj


def _fence_path(obj: Any, path: list[str], name: str) -> Any:
    if not path or path == [""]:
        return fence(obj, name)
    head, rest = path[0], path[1:]
    if head == "*":
        if not rest:
            return fence(obj, name)
        if isinstance(obj, dict):
            return {k: _fence_path(v, rest, f"{name}.{k}") for k, v in obj.items()}
        if isinstance(obj, list):
            return [_fence_path(v, rest, f"{name}[{i}]") for i, v in enumerate(obj)]
        return obj
    if isinstance(obj, dict) and head in obj:
        return {**obj, head: _fence_path(obj[head], rest, f"{name}.{head}")}
    return obj


def fence_inputs(inputs: Any) -> None:
    for name, paths in FENCED_FIELDS.items():
        value = getattr(inputs, name)
        for path in paths:
            value = _fence_path(value, path.split(".") if path else [""], name)
        setattr(inputs, name, value)


def _patch_context_ops(yaml_plants: dict[str, dict[str, str]]) -> Callable[[Any], None]:
    """A dispatched card reaches the pack through the invocation's pin in control state, not through the card loader,
    so its prose leaves are wrapped where the pin enters the pack's inputs, keyed by the card's YAML file (§2.2, data);
    the authored inputs are fenced there too."""
    def patch(module: Any) -> None:
        cls = module.ContextPacks
        for name in ("_pack_inputs",):  # every pack's inputs pass through it (it calls _m2_pack_inputs itself)
            original = getattr(cls, name)

            def wrapped(self: Any, state: dict[str, Any], inv_id: str, *a: Any, _o: Any = original, **kw: Any) -> Any:
                inputs, sources = _o(self, state, inv_id, *a, **kw)
                for edit in INPUT_EDITS:  # a negative control's product edit, made where the product would make it
                    edit(inputs)
                pin = pinned_card(state["invocations"][inv_id].get("card"))
                if pin is not None and inputs.card is not None:
                    rel, _ = pin
                    inputs.card = wrap_yaml(inputs.card, rel, plants=yaml_plants.get(rel))
                fence_inputs(inputs)
                return inputs, sources

            setattr(cls, name, wrapped)
    return patch


# Negative controls (F4 of the prototype's review): product edits a control plants, each where the product itself would
# make it: an edit of a pack's inputs inside `_pack_inputs`, before the data boundary wraps them, and an edit of a
# module right after it runs, before its displays are wrapped. Empty unless a control installs them (pt_negatives).
INPUT_EDITS: list[Callable[[Any], None]] = []
MODULE_EDITS: dict[str, list[Callable[[Any], None]]] = {}

# What argparse generates itself, marked where it generates it (V11-2, made positional: F3 of the review). The kinds:
CLI_USAGE, CLI_INVOCATION, CLI_BUILTIN_HELP = "usage", "invocation", "argparse built-in help"


def _argparse_len(obj: Any) -> int:
    """argparse's ``len``: every width it measures is the stripped text's (V12-1)."""
    return len(strip(obj)) if isinstance(obj, str) and has_marker_chars(obj) else len(obj)


def _cli_value(kind: str) -> Callable[[str], str]:
    return lambda core: wrap_value(core, REGISTRY.value({"cli": kind, "kind": "cli"}))


def _patch_argparse() -> None:
    """Patch argparse to measure stripped text and to mark the text it generates: the usage line, each action's
    invocation (option strings, metavars, choices, subcommand names) and the help of its own -h and --version
    actions. Text it is given (help, description, epilog) is the hook's (units); nothing is matched by text."""
    import argparse

    fmt = argparse.HelpFormatter
    argparse.len = _argparse_len  # type: ignore[attr-defined]  (a module global shadows the builtin there)
    fmt._split_lines = _split_lines_stripped(fmt._split_lines)  # type: ignore[method-assign]
    fmt._fill_text = _fill_text_stripped(fmt._fill_text)  # type: ignore[method-assign]
    usage, action, expand = fmt._format_usage, fmt._format_action, fmt._expand_help

    def _format_usage(self: Any, *a: Any, **kw: Any) -> str:
        return wrap_core(usage(self, *a, **kw), _cli_value(CLI_USAGE))

    def _format_action(self: Any, act: Any) -> str:
        header = self._format_action_invocation(act)
        text = action(self, act)  # its sub-actions come back through this patch, marked
        at = self._current_indent
        if not header or text[at:at + len(header)] != header:
            return text  # not argparse's layout: left unmarked, so untraced
        return text[:at] + wrap_value(header, REGISTRY.value({"cli": CLI_INVOCATION, "kind": "cli"})) + \
            text[at + len(header):]

    def _expand_help(self: Any, act: Any) -> str:
        text = expand(self, act)
        if isinstance(act, (argparse._HelpAction, argparse._VersionAction)):
            return wrap_core(text, _cli_value(CLI_BUILTIN_HELP))
        return text

    subparsers = argparse.ArgumentParser.add_subparsers

    def add_subparsers(self: Any, **kw: Any) -> Any:
        # argparse formats a usage line to make its sub-commands' prog prefix: data, not output, so unmarked
        action = subparsers(self, **kw)
        action._prog_prefix = strip(action._prog_prefix)
        return action

    fmt._format_usage = _format_usage  # type: ignore[method-assign]
    fmt._format_action = _format_action  # type: ignore[method-assign]
    fmt._expand_help = _expand_help  # type: ignore[method-assign]
    argparse.ArgumentParser.add_subparsers = add_subparsers  # type: ignore[method-assign]


def install(*, plants: dict[str, dict[Key, str]] | None = None,
            yaml_plants: dict[str, dict[str, str]] | None = None) -> Finder:
    """Install the hook in this process (before ``aew`` is imported) and patch argparse."""
    if any(name == "aew" or name.startswith("aew.") for name in sys.modules):
        raise HookError("install the hook before anything imports aew")
    _patch_argparse()
    finder = Finder(plants or {}, {"aew.util": _patch_util, "aew.roles": _patch_roles(yaml_plants or {}),
                                   "aew.knowledge.context": _patch_context,
                                   "aew.engine.context_ops": _patch_context_ops(yaml_plants or {})})
    sys.meta_path.insert(0, finder)
    return finder


# --------------------------------------------------------------------------------------------------- tracing


@dataclass
class Span:
    text: str
    start: int
    end: int
    source: Marker | None
    why: str
    context: str


def trace(text: str) -> tuple[str, list[Span]]:
    """The stripped text and every pattern span in it, each with its source marker (or why it has none)."""
    stripped, roots = parse(text)
    out = []
    for s, e in pt_pattern.spans(stripped):
        m, why = span_source(roots, s, e)
        out.append(Span(stripped[s:e], s, e, m, why, stripped[max(0, s - 40):e + 40]))
    return stripped, out
