"""The launch census (G3 addendum 7, ruling 1's class guard; the designer's DV-2 and DV-5): every process start in
``src/`` and ``eval/``, found by two detectors written apart, for ``tests/unit/test_launch_census.py`` to hold to the
pinned table ``tests/launch-census.yaml``.

* :func:`by_ast` resolves each call by import: ``import subprocess as sp``, ``from subprocess import run``, a module's
  own definitions and a plain alias (``run = subprocess.run``) all name their origin, so a start is found whatever its
  local name, and a ``run(`` that is not ``subprocess.run`` is not one. It also lists every ``except`` that can catch
  ``ContainmentUnavailable`` (by its name, or a class it inherits from, or a bare one) with what its body does.
* :func:`by_tokens` reads the token stream alone, no import resolution: a start is a call of a known name, plain or
  after a dot. It sees forms the first cannot resolve (a method that wraps one, ``self.establish(``), and misses
  what only an import says (``from subprocess import run`` then ``run(``).

Each site is ``(path, scope, name)``: the file, the enclosing ``Class.function`` (``<module>`` at the top) and the
called name's last part, counted. A file that cannot be read or parsed is returned as unreadable, never as "no
starts". What both detectors miss is :data:`CANNOT_SEE`, each form pinned by a probe.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

ROOTS = ("src", "eval")
# Excluded by name, with the record's reason (addendum 7; the designer, 2026-11-01, confirming the Lead's reading).
EXCLUDED = {
    "eval/reviews/": "the frozen review probes; it holds no lane (addendum 7)",
    "eval/m3/spike/": "frozen probes, kept as they ran in M3; it holds no lane (the designer, 2026-11-01, confirming "
                      "the Lead's reading; no change to addendum 7's text)",
}
# Every process-starting call, by its origin (the addendum's list).
STARTS = frozenset({
    *(f"subprocess.{n}" for n in ("run", "call", "check_call", "check_output", "Popen", "getoutput",
                                    "getstatusoutput")),
    *(f"os.{n}" for n in ("system", "popen", "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
                          "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp",
                          "spawnvpe", "posix_spawn", "posix_spawnp", "fork", "forkpty", "startfile")),
    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell", "pty.spawn",
    "concurrent.futures.ProcessPoolExecutor", "multiprocessing.Process", "multiprocessing.Pool",
    "multiprocessing.get_context",
    "aew.harness.procs.ProcessTree", "aew.harness.procs.run_session_tree", "aew.harness.procs.spawn_detached",
    "aew.harness.lead_broker.run_session", "aew.harness.containment.establish",
    "aew.harness.containment.bwrap_argv", "aew.harness.containment.layout.bwrap_argv",
})
NAMES = frozenset(s.rsplit(".", 1)[1] for s in STARTS)
# What can catch ContainmentUnavailable: the class itself and every class it inherits from (aew.errors).
CATCHES = frozenset({"ContainmentUnavailable", "HarnessError", "AEWError", "Exception", "BaseException"})
# The register's writer: a weaker outcome's owner calls one of these (ruling 1: one helper writes every entry).
REGISTERS = frozenset({"aew.harness.weaker_register.enter", "aew.harness.weaker_register.enter_if_weaker",
                       "aew.harness.weaker_register.context", "aew.harness.lead_broker.WeakerLead"})
CONTAINS = frozenset({"aew.harness.containment.establish", "aew.harness.containment.bwrap_argv",
                      "aew.harness.containment.layout.bwrap_argv"})

# What neither detector can see, each pinned by a probe in the test: a call through a name only a value carries.
CANNOT_SEE = {
    "getattr(subprocess, 'run')(...)": "the callee is a string at run time",
    "importlib.import_module('subprocess').run(...)": "the module is a string at run time",
    "__import__('subprocess').run(...)": "the module is a string at run time",
}


@dataclass
class FileResult:
    sites: Counter[tuple[str, str]] = field(default_factory=Counter)  # (scope, name)
    origins: dict[tuple[str, str], set[str]] = field(default_factory=dict)  # (scope, name) -> resolved origins
    handlers: list[dict[str, object]] = field(default_factory=list)
    calls: dict[str, set[str]] = field(default_factory=dict)  # scope -> every resolved call origin in it


@dataclass
class Census:
    files: dict[str, FileResult] = field(default_factory=dict)
    unreadable: dict[str, str] = field(default_factory=dict)

    def sites(self) -> Counter[tuple[str, str, str]]:
        out: Counter[tuple[str, str, str]] = Counter()
        for path, res in self.files.items():
            for (scope, name), n in res.sites.items():
                out[(path, scope, name)] += n
        return out


def excluded(rel: str) -> str | None:
    return next((p for p in EXCLUDED if rel.startswith(p)), None)


def sources(repo: Path, roots: Iterable[str] = ROOTS) -> list[tuple[str, Path]]:
    out = []
    for root in roots:
        for path in sorted((repo / root).rglob("*.py")):
            rel = path.relative_to(repo).as_posix()
            if not excluded(rel):
                out.append((rel, path))
    return out


def _module_name(rel: str) -> str:
    parts = rel[:-3].split("/")
    if parts[0] in ROOTS:  # src/aew/... is `aew`, eval/aew_eval/... is `aew_eval` (eval/ is on its path)
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


# ------------------------------------------------------------------------------------------------- detector 1: AST

class _Walker(ast.NodeVisitor):
    def __init__(self, module: str, package: str) -> None:
        self.module, self.package = module, package
        self.scopes: list[str] = []
        self.bindings: list[dict[str, str]] = [{}]
        self.result = FileResult()

    # names -> origins
    def _bind(self, name: str, origin: str) -> None:
        self.bindings[-1][name] = origin

    def _lookup(self, name: str) -> str | None:
        for frame in reversed(self.bindings):
            if name in frame:
                return frame[name]
        return None

    def resolve(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self._lookup(node.id)
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    @property
    def scope(self) -> str:
        return ".".join(self.scopes) or "<module>"

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.asname:
                self._bind(a.asname, a.name)
            else:
                top = a.name.split(".")[0]
                self._bind(top, top)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        base = node.module or ""
        if node.level:
            pkg = self.package.split(".")
            pkg = pkg[:len(pkg) - node.level + 1] if node.level > 1 else pkg
            base = ".".join([*pkg, *([node.module] if node.module else [])])
        for a in node.names:
            self._bind(a.asname or a.name, f"{base}.{a.name}" if base else a.name)

    def _define(self, name: str) -> None:
        if len(self.scopes) == 0:
            self._bind(name, f"{self.module}.{name}")

    def _enter(self, node: ast.AST, name: str) -> None:
        self._define(name)
        self.scopes.append(name)
        self.bindings.append({})
        self.generic_visit(node)
        self.bindings.pop()
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node, node.name)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node, node.name)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            origin = self.resolve(node.value)
            if origin:
                self._bind(node.targets[0].id, origin)

    def visit_Call(self, node: ast.Call) -> None:
        origin = self.resolve(node.func)
        if origin:
            self.result.calls.setdefault(self.scope, set()).add(origin)
            if origin in STARTS:
                key = (self.scope, origin.rsplit(".", 1)[1])
                self.result.sites[key] += 1
                self.result.origins.setdefault(key, set()).add(origin)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        """A handler of ``ContainmentUnavailable`` by name, always; a broader one (a class it inherits from, or a bare
        ``except``) where its ``try`` starts a process or builds a sandbox itself (DV-5)."""
        guarded = {self.resolve(c.func) for s in node.body for c in ast.walk(s) if isinstance(c, ast.Call)}
        starts = bool(guarded & (STARTS | CONTAINS | {"aew.policy.checks.run"}))
        for h in node.handlers:
            names = self._caught(h.type)
            if "ContainmentUnavailable" in names or ((names & CATCHES or h.type is None) and starts):
                self.result.handlers.append({"scope": self.scope, "catches": sorted(names) or ["<bare>"],
                                             "does": _disposition(h)})
        self.generic_visit(node)

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def _caught(self, node: ast.AST | None) -> set[str]:
        if node is None:
            return set()
        if isinstance(node, ast.Tuple):
            return set().union(*(self._caught(e) for e in node.elts))
        origin = self.resolve(node)
        if origin is None:
            return {node.id} if isinstance(node, ast.Name) and node.id in CATCHES else set()
        leaf = origin.rsplit(".", 1)[-1]
        return {leaf} if leaf in CATCHES and (origin.startswith("aew.") or leaf in ("Exception", "BaseException")
                                              or origin == leaf) else set()


def _disposition(handler: ast.ExceptHandler) -> str:
    """What an ``except`` body does with what it caught: re-raises (``raise``, or raises another), returns, or goes
    on (falls through to what follows)."""
    kinds = {type(n) for n in ast.walk(ast.Module(body=handler.body, type_ignores=[]))}
    if ast.Raise in kinds:
        return "raises"
    if ast.Return in kinds:
        return "returns"
    return "goes_on"


def by_ast(repo: Path, roots: Iterable[str] = ROOTS) -> Census:
    census = Census()
    for rel, path in sources(repo, roots):
        try:
            tree = ast.parse(path.read_bytes(), filename=rel)
        except (OSError, SyntaxError, ValueError) as exc:
            census.unreadable[rel] = f"{type(exc).__name__}: {exc}"
            continue
        module = _module_name(rel)
        package = module if rel.endswith("__init__.py") else module.rpartition(".")[0]
        walker = _Walker(module, package)
        walker.visit(tree)
        census.files[rel] = walker.result
    return census


# ---------------------------------------------------------------------------------------------- detector 2: tokens

_DEF = {"def", "class"}
# Detector 2's own rule, from the text alone: a start name no other call shares, called anywhere; or a common one
# (``run``, ``call``, ``spawn``, ``system``) called on a name spelled as its module is.
DISTINCT = frozenset({"Popen", "check_output", "getoutput", "getstatusoutput", "create_subprocess_exec",
                      "create_subprocess_shell", "ProcessPoolExecutor", "posix_spawn", "posix_spawnp", "forkpty",
                      "ProcessTree", "run_session_tree", "run_session", "spawn_detached", "establish", "bwrap_argv",
                      *(n for n in NAMES if n.startswith(("exec", "spawn")) and n != "spawn")})
MODULE_TEXTS = frozenset({"subprocess", "os", "asyncio", "pty", "multiprocessing", "futures"})


def by_tokens(repo: Path, roots: Iterable[str] = ROOTS) -> Census:
    """Every call of a known start name in the token stream (strings and comments are tokens of their own, so never
    read as code). Scope comes from ``def``/``class`` lines and indentation."""
    census = Census()
    for rel, path in sources(repo, roots):
        try:
            toks = list(tokenize.tokenize(io.BytesIO(path.read_bytes()).readline))
        except (OSError, tokenize.TokenError, SyntaxError) as exc:
            census.unreadable[rel] = f"{type(exc).__name__}: {exc}"
            continue
        res = FileResult()
        stack: list[tuple[int, str]] = []  # (indent column, name)
        line_start_col: int | None = None
        prev: list[tokenize.TokenInfo] = []
        for i, tok in enumerate(toks):
            if tok.type in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.ENCODING):
                if tok.type in (tokenize.NEWLINE,):
                    line_start_col = None
                continue
            if tok.type in (tokenize.INDENT, tokenize.DEDENT):
                continue
            if line_start_col is None:
                line_start_col = tok.start[1]
                while stack and stack[-1][0] >= line_start_col:
                    stack.pop()
            if tok.type == tokenize.NAME and tok.string in _DEF and i + 1 < len(toks):
                nxt = toks[i + 1]
                if nxt.type == tokenize.NAME:
                    stack.append((line_start_col, nxt.string))
            if (tok.type == tokenize.NAME and tok.string in NAMES and i + 1 < len(toks)
                    and toks[i + 1].string == "(" and not (prev and prev[-1].string in _DEF)):
                dotted = len(prev) >= 2 and prev[-1].string == "." and prev[-2].type == tokenize.NAME
                if tok.string in DISTINCT or (dotted and prev[-2].string in MODULE_TEXTS):
                    scope = ".".join(n for _, n in stack) or "<module>"
                    res.sites[(scope, tok.string)] += 1
            prev.append(tok)
        census.files[rel] = res
    return census


# --------------------------------------------------------------------------------------------- the table's check

CLASSES = ("contained", "weaker_registered", "not_agent_context")
# Contained through establish, or through the layout check eval uses in its place (raw.verify_layout runs AEW's
# launch self-test on the layout).
CONTAINED_BY = CONTAINS | {"aew_eval.raw.verify_layout"}


def check(repo: Path, table: dict, *, roots: Iterable[str] = ROOTS) -> list[str]:
    """Every problem with ``table`` against the code under ``repo``: the census's whole test, so a planted tree can be
    checked like the real one. Empty when the table holds."""
    first, second = by_ast(repo, roots), by_tokens(repo, roots)
    problems = [f"unreadable: {p} ({why})" for p, why in sorted({**first.unreadable, **second.unreadable}.items())]
    found = first.sites()
    rows = {(r["site"].split("::", 1)[0], r["site"].split("::", 1)[1], r["call"]): r for r in table.get("starts", [])}
    for key in sorted(set(found) - set(rows)):
        problems.append(f"an unclassified start: {'::'.join(key[:2])} calls {key[2]} ({found[key]}x)")
    for key in sorted(set(rows) - set(found)):
        problems.append(f"a table row with no start in the code: {'::'.join(key[:2])} {key[2]}")
    for key, row in sorted(rows.items()):
        classes = row.get("classes") or []
        if key in found and len(classes) != found[key]:
            problems.append(f"{'::'.join(key[:2])} calls {key[2]} {found[key]}x, classified {len(classes)}x")
        if not row.get("reason"):
            problems.append(f"{'::'.join(key[:2])} {key[2]}: no reason")
        for cls in classes:
            if cls not in CLASSES:
                problems.append(f"{'::'.join(key[:2])} {key[2]}: unknown class {cls!r}")
        needs = [("registered_by", REGISTERS)] if "weaker_registered" in classes else []
        if "contained" in classes:
            needs.append(("contained_by", CONTAINED_BY))
        if row.get("weaker_registered_by"):
            needs.append(("weaker_registered_by", REGISTERS))
        for field_name, wanted in needs:
            owners = row.get(field_name) or []
            if not owners:
                problems.append(f"{'::'.join(key[:2])} {key[2]}: {field_name} names no owner")
            for owner in owners:
                path, _, scope = owner.partition("::")
                calls = first.files.get(path, FileResult()).calls.get(scope, set())
                if not calls & wanted:
                    problems.append(f"{'::'.join(key[:2])} {key[2]}: {owner} ({field_name}) calls none of "
                                    f"{sorted(wanted)}")
    # Both detectors agree, both ways, apart from the pinned differences.
    second_found = second.sites()
    only_first = {k: n - second_found.get(k, 0) for k, n in found.items() if n > second_found.get(k, 0)}
    only_second = {k: n - found.get(k, 0) for k, n in second_found.items() if n > found.get(k, 0)}
    pinned_first = {_key(d): d["count"] for d in table.get("ast_only", [])}
    pinned_second = {_key(d): d["count"] for d in table.get("token_only", [])}
    if only_first != pinned_first:
        problems.append(f"only the AST detector sees {only_first}, pinned {pinned_first}")
    if only_second != pinned_second:
        problems.append(f"only the token detector sees {only_second}, pinned {pinned_second}")
    # Every handler that can catch ContainmentUnavailable re-raises or refuses; one that goes on is pinned, with its
    # reason, and is never in src/ (under `required` a containment failure refuses; eval has no policy).
    seen_handlers = Counter((p, h["scope"], tuple(h["catches"]), h["does"])
                            for p, res in first.files.items() for h in res.handlers)
    pinned = Counter((h["site"].split("::", 1)[0], h["site"].split("::", 1)[1], tuple(h["catches"]), h["does"])
                     for h in table.get("handlers", []))
    if seen_handlers != pinned:
        problems.append(f"handlers in the code but not the table: {sorted((seen_handlers - pinned).elements())}; "
                        f"in the table but not the code: {sorted((pinned - seen_handlers).elements())}")
    for h in table.get("handlers", []):
        if h["does"] == "goes_on" and (h["site"].startswith("src/") or not h.get("reason")):
            problems.append(f"a containment failure goes on at {h['site']} ({h['catches']})"
                            + (": src/ refuses under required" if h["site"].startswith("src/") else ": no reason"))
    return problems


def _key(d: dict) -> tuple[str, str, str]:
    path, _, scope = d["site"].partition("::")
    return (path, scope, d["call"])


# ------------------------------------------------------------------------------------------- the exclusions' guard

GUARDED = ("src", "eval", "tests", "tools", ".github/workflows", "docs/guides")
GUARD_SUFFIXES = (".py", ".yml", ".yaml", ".sh", ".ps1", ".md", ".toml", ".cfg", ".ini", ".txt")


def excluded_refs(repo: Path, *, skip: Iterable[str] = ()) -> list[str]:
    """Every reference to a program in an excluded path from the guarded places (the designer, 2026-11-01): the
    path of one of its files (a ``.py`` or ``.sh``), its dotted module, or an import of one of its modules. A link to
    its notes (``.md``) is no reference: nothing runs a note. Each is ``"<file>:<line>: <what>"``."""
    code = [p.relative_to(repo).as_posix() for prefix in EXCLUDED for p in (repo / prefix).rglob("*")
            if p.is_file() and p.suffix in (".py", ".sh")]
    stems = {Path(c).stem for c in code if c.endswith(".py")}
    pats = [re.compile(re.escape(prefix) + r"[\w./-]*\.(?:py|sh)\b") for prefix in EXCLUDED]
    pats += [re.compile(r"\b" + re.escape(prefix.rstrip("/").replace("/", ".")) + r"\b") for prefix in EXCLUDED]
    imports = re.compile(r"^\s*(?:from\s+(\w+)|import\s+(\w+))", re.M)
    skipped = set(skip)
    out = []
    for place in GUARDED:
        base = repo / place
        for path in sorted(base.rglob("*")) if base.is_dir() else []:
            rel = path.relative_to(repo).as_posix()
            if not path.is_file() or path.suffix not in GUARD_SUFFIXES or excluded(rel) or rel in skipped:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                out.append(f"{rel}: unreadable ({type(exc).__name__})")
                continue
            for n, line in enumerate(text.splitlines(), 1):
                hits = [m.group(0) for p in pats for m in p.finditer(line)]
                if path.suffix == ".py":
                    hits += [f"import {m}" for g in imports.findall(line) for m in g if m and m in stems]
                out += [f"{rel}:{n}: {h}" for h in hits]
    return out
