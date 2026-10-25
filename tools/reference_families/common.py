"""The shared plumbing of the generated as-built reference (STG-12 S12-2): the record, the index, the deterministic
writer, and the checks every family's output must pass.

A family module exposes ``build(ctx) -> Built`` and nothing else the generator needs. It reads its owners (a runtime
registry it imports, a declared table, or the source tree it parses) and returns records and the page text for
its own family. Nothing here knows a family.

Determinism is by construction: every mapping is dumped with sorted keys, every list a family returns is sorted by the
family before it gets here, paths are POSIX and relative to the repository root, there is no clock and no absolute path,
and files are written as bytes with ``\\n`` line ends. Two renders of one tree are byte-identical on Windows and
Linux; ``tests/unit/test_reference.py`` proves it, including across hash seeds.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "aew/reference-index/v1"
MODULES = "modules"  # the family whose records the trace follows by `anchor.module` (addendum 1)
BASES = ("enumerated", "declared", "static", "observed")
COMPLETE, LOWER, UNKNOWN = "complete-by-construction", "lower-bound", "unknown"
LABELS = (COMPLETE, LOWER, UNKNOWN)
RENDER_COMMAND = "python tools/reference.py render"
CHECK_COMMAND = "python tools/reference.py check"


class ReferenceError(Exception):
    """The reference cannot be generated (an owner is unreadable or the output breaks a rule): never a silent result."""


def shown(items: Sequence[str], limit: int = 20) -> list[str]:
    """The first ``limit`` lines of a refusal's list, and how many were left out: a message cut short says so."""
    return [*items[:limit], *([f"... and {len(items) - limit} more"] if len(items) > limit else [])]


PACKAGE = "aew"


@dataclass(frozen=True)
class Source:
    """One module of the package, read once. ``tree`` is None (and ``error`` says why) for a file that does not parse:
    an unreadable module is listed as such, never dropped."""

    name: str
    path: Path
    is_package: bool
    text: str
    tree: ast.Module | None
    error: str | None


@dataclass
class Context:
    root: Path  # the repository root; the source tree is ``root / "src"``
    _sources: dict[str, Source] | None = None
    _indexes: dict[str, Index] = field(default_factory=dict)

    @property
    def src(self) -> Path:
        return self.root / "src"

    def sources(self) -> dict[str, Source]:
        """Every module of the package on disk, by dotted name, sorted: parsed once for all families."""
        if self._sources is None:
            package = self.src / PACKAGE
            if not package.is_dir():
                raise ReferenceError(f"no {PACKAGE} package directory under the source root")
            found: dict[str, Source] = {}
            for file in sorted(package.rglob("*.py")):
                if "__pycache__" in file.parts:
                    continue
                parts = list(file.relative_to(self.src).with_suffix("").parts)
                is_package = parts[-1] == "__init__"
                if is_package:
                    parts.pop()
                text = read_source(file)
                try:
                    tree, error = ast.parse(text), None
                except SyntaxError as exc:
                    tree, error = None, exc.msg
                found[".".join(parts)] = Source(".".join(parts), file, is_package, text, tree, error)
            self._sources = found
        return self._sources

    def index(self, name: str) -> Index:
        """The one-pass index of a parsed module (its imports, calls and sequences), built once for all families."""
        if name not in self._indexes:
            src = self.sources()[name]
            if src.tree is None:
                raise ReferenceError(f"{name} does not parse")
            self._indexes[name] = index_of(src.tree, name, src.is_package)
        return self._indexes[name]


@dataclass(frozen=True)
class Record:
    family: str
    key: str  # taken from the family's owner (a table key, a dotted module, `from->to`), never an ordinal or a line
    module: str  # the anchor: a dotted module, and the symbol in it (None only for the modules family)
    symbol: str | None
    basis: str
    coverage: dict[str, Any]
    fact: dict[str, Any] | None = None
    imports: list[str] | None = None  # the modules family only: the AEW modules it imports, statically
    # How complete each list fact a detector found is, keyed by the fact's name, in `coverage`'s vocabulary (addendum
    # 3). It is on the record beside `coverage`, not inside `fact`: it describes facts, as `coverage` describes the
    # record. Passed by keyword.
    fact_coverage: dict[str, dict[str, Any]] | None = None

    @property
    def id(self) -> str:
        return f"{self.family}:{self.key}"

    def as_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"family": self.family, "anchor": {"module": self.module, "symbol": self.symbol},
                               "basis": self.basis, "coverage": self.coverage}
        if self.fact is not None:
            out["fact"] = self.fact
        if self.fact_coverage is not None:
            out["fact_coverage"] = self.fact_coverage
        if self.imports is not None:
            out["imports"] = self.imports
        return out


@dataclass
class Built:
    """What a family returns: its records (every unresolved item is on one, in ``coverage`` or in a list fact's
    ``fact_coverage``: nothing lives only in the index's ``gaps``, which is computed from them) and its pages."""

    records: list[Record] = field(default_factory=list)
    pages: dict[str, str] = field(default_factory=dict)  # file name under docs/reference -> its text


def unresolved_item(module: str, symbol: str | None, why: str) -> dict[str, Any]:
    return {"module": module, "symbol": symbol, "why": why}


def complete(registry: str, check: Iterable[str]) -> dict[str, Any]:
    """complete-by-construction: the registry the records are read from, and the tests that stop code bypassing it."""
    return {"label": COMPLETE, "registry": registry, "check": sorted(set(check))}


def lower_bound(unresolved: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """lower-bound: what was found is real, and what could not be resolved is listed (each item once)."""
    distinct = {(i["module"], i["symbol"] or "", i["why"]): dict(i) for i in unresolved}
    return {"label": LOWER, "unresolved": [distinct[k] for k in sorted(distinct)]}


def unknown() -> dict[str, Any]:
    return {"label": UNKNOWN}


def dumps(obj: Any) -> str:
    """The one serialization: sorted keys, two-space indent, ASCII, a final newline. LF only."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


# ---------------------------------------------------------------------------------------------------- the index

def unresolved_items(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every unresolved item a record carries: its own ``coverage.unresolved`` and those of its list facts
    (``fact_coverage``, on the record beside ``coverage``)."""
    items = list((record.get("coverage") or {}).get("unresolved") or [])
    for coverage in (record.get("fact_coverage") or {}).values():
        items += coverage.get("unresolved") or []
    return items


def gaps_of(records: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The index's ``gaps``: a summary computed from the records, each distinct unresolved item once, with its family.
    Nothing lives only here: the trace reads the records, and a test holds the summary to them."""
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records.values():
        for item in unresolved_items(record):
            key = (record["family"], item["module"], item["symbol"] or "", item["why"])
            seen[key] = {"family": record["family"], "module": item["module"], "symbol": item["symbol"],
                         "why": item["why"]}
    return [seen[k] for k in sorted(seen)]


def counts_of(rows: Iterable[tuple[str, str]], unresolved: int) -> dict[str, Any]:
    """The measured counts, from (family, coverage label) per record and the number of distinct unresolved items."""
    listed = list(rows)
    by_both: dict[str, dict[str, int]] = {}
    for family, label in listed:
        row = by_both.setdefault(family, {})
        row[label] = row.get(label, 0) + 1
    return {"records": len(listed), "by_family": dict(Counter(f for f, _ in listed)),
            "by_coverage": dict(Counter(label for _, label in listed)), "by_family_and_coverage": by_both,
            "unresolved": unresolved}


def digest_of(records: Mapping[str, Any], gaps: list[Any]) -> str:
    """A digest of every record and gap, kept in ``counts``. Several lines of the generated files are functions of more
    than one record (the totals), so two independent changes can each edit them to the same text, and git then merges
    them without a conflict into totals that are stale. This line differs between any two changes to the records, so
    two reference-changing pull requests always conflict on it, and the documented step (take either side, run
    ``render``) applies: a stale clean merge cannot happen."""
    return "sha256:" + hashlib.sha256(dumps({"gaps": gaps, "records": records}).encode("utf-8")).hexdigest()


def build_index(records: Iterable[Record]) -> dict[str, Any]:
    recs = sorted(records, key=lambda r: r.id)
    ids = [r.id for r in recs]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ReferenceError(f"record ids are not unique: {shown(dup, 5)}")
    as_records = {r.id: r.as_json() for r in recs}
    gaps = gaps_of(as_records)
    totals = {**counts_of(((r.family, r.coverage["label"]) for r in recs), len(gaps)),
              "digest": digest_of(as_records, gaps)}
    return {"schema": SCHEMA, "counts": totals, "gaps": gaps, "records": as_records}


def coverage_problems(where: str, cov: Any) -> list[str]:
    """One coverage object (a record's ``coverage``, or a list fact's entry in ``fact_coverage``): the label and what
    the label requires, in the vocabulary of addendum 1."""
    if not isinstance(cov, dict):
        return [f"{where}: coverage is not an object"]
    label = cov.get("label")
    problems = []
    if label == COMPLETE:
        if not isinstance(cov.get("registry"), str) or not cov["registry"]:
            problems.append(f"{where}: complete-by-construction without its registry")
        check = cov.get("check")
        if not (isinstance(check, list) and check and all(isinstance(c, str) for c in check)):
            problems.append(f"{where}: complete-by-construction without its check (a non-empty list of test ids)")
    elif label == LOWER:
        items = cov.get("unresolved")
        if not isinstance(items, list):
            problems.append(f"{where}: lower-bound without its unresolved list")
        else:
            for item in items:
                if not isinstance(item, dict) or set(item) != {"module", "symbol", "why"} or not item["why"]:
                    problems.append(f"{where}: an unresolved item is not {{module, symbol, why}}: {item!r}")
    elif label != UNKNOWN:
        problems.append(f"{where}: coverage label {label!r} is not one of {list(LABELS)}")
    return problems


def index_problems(index: Mapping[str, Any]) -> list[str]:
    """The consumer's interface (addenda 1 and 3) and the generator's own invariants. Empty when the index is sound."""
    problems: list[str] = []
    if index.get("schema") != SCHEMA:
        problems.append(f"schema is {index.get('schema')!r}, not {SCHEMA!r}")
    records = index.get("records")
    if not isinstance(records, dict) or not records:
        return [*problems, "no records object"]
    modules = {r["anchor"]["module"] for r in records.values() if r.get("family") == MODULES}
    for rid, r in records.items():
        family = r.get("family")
        if not family or not rid.startswith(f"{family}:"):
            problems.append(f"{rid}: the id does not start with its family")
        anchor = r.get("anchor") or {}
        if not anchor.get("module"):
            problems.append(f"{rid}: no anchor.module")
        elif anchor["module"] not in modules:
            problems.append(f"{rid}: its module {anchor['module']} has no modules record")
        if family != MODULES and not anchor.get("symbol"):
            problems.append(f"{rid}: no anchor.symbol")
        if family == MODULES:
            if anchor.get("symbol") is not None:
                problems.append(f"{rid}: a modules record's symbol must be null")
            imports = r.get("imports")
            if not isinstance(imports, list) or imports != sorted(set(imports)):
                problems.append(f"{rid}: imports is not a sorted list without repeats")
            else:
                problems += [f"{rid}: imports {m}, which has no modules record" for m in imports if m not in modules]
        elif "imports" in r:
            problems.append(f"{rid}: only a modules record has imports")
        if r.get("basis") not in BASES:
            problems.append(f"{rid}: basis {r.get('basis')!r} is not one of {list(BASES)}")
        problems += coverage_problems(rid, r.get("coverage"))
        fact = r.get("fact") or {}
        if "fact_coverage" in fact:  # it describes facts, so it is not one: it belongs on the record (addendum 3)
            problems.append(f"{rid}: fact_coverage is inside fact; it belongs on the record, beside coverage")
        fact_coverage = r.get("fact_coverage")
        if fact_coverage is not None and not isinstance(fact_coverage, dict):
            problems.append(f"{rid}: fact_coverage is not an object")
            fact_coverage = None
        for name, cov in (fact_coverage or {}).items():
            if name not in fact:
                problems.append(f"{rid}: fact_coverage for {name!r}, which is not a fact of the record")
            problems += coverage_problems(f"{rid} fact_coverage.{name}", cov)
        for name, value in fact.items():  # a list a detector found says how complete it is (addendum 3)
            if isinstance(value, list) and name not in (fact_coverage or {}):
                problems.append(f"{rid}: the list fact {name!r} has no fact_coverage entry")
    try:
        gaps = gaps_of(records)
    except (KeyError, TypeError, AttributeError):
        return [*problems, "an unresolved item is malformed, so the gaps cannot be computed from the records"]
    for gap in index.get("gaps", []):
        if not isinstance(gap, dict) or set(gap) != {"family", "module", "symbol", "why"} or not gap["why"]:
            problems.append(f"a gap is not {{family, module, symbol, why}}: {gap!r}")
    if index.get("gaps") != gaps:
        problems.append("gaps is not the summary of the records' unresolved items (nothing may live only in gaps)")
    rows = [(r.get("family", ""), r["coverage"]["label"]) for r in records.values()
            if isinstance(r.get("coverage"), dict) and r["coverage"].get("label") in LABELS]
    expected = {**counts_of(rows, len(gaps)), "digest": digest_of(records, gaps)}
    if index.get("counts") != expected:
        problems.append("counts (with its digest) is not what the records and gaps give")
    return problems


# ---------------------------------------------------------------------------------------------------- the files

_DRIVE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]")
_UNIX_HOME = re.compile(r"(?<![\w.~-])/(?:Users|home|root|tmp|var|etc|mnt|opt)/")
_TIMESTAMP = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def text_problems(name: str, text: str, home: Path | None = None) -> list[str]:
    """The structural privacy and format rules over one generated file (v0.2 R-5): LF only; no absolute path, no
    timestamp, nothing naming this machine's home directory. gitleaks scans the same files separately."""
    problems = []
    if "\r" in text:
        problems.append(f"{name}: has a carriage return (the files are LF only)")
    for pattern, what in ((_DRIVE, "a drive-letter path"), (_UNIX_HOME, "an absolute path"),
                          (_TIMESTAMP, "a timestamp")):
        found = pattern.search(text)
        if found:
            problems.append(f"{name}: has {what} ({text[max(0, found.start() - 12):found.end() + 12]!r})")
    if home is not None:
        spellings = {str(home), home.as_posix(), str(home).replace("\\", "\\\\")}
        problems += [f"{name}: names this machine's home directory" for s in sorted(spellings) if s and s in text]
    return problems


# ---------------------------------------------------------------------------------------------------- AST helpers

class Scoped(ast.NodeVisitor):
    """A visitor that knows its enclosing symbol: the qualified name of the function or class it is in, or, at module
    level, the name a simple assignment binds. Line numbers churn, so anchors are never lines."""

    def __init__(self) -> None:
        self.stack: list[str] = []

    @property
    def symbol(self) -> str | None:
        return ".".join(self.stack) or None

    def _scoped(self, node: ast.AST, name: str) -> None:
        self.stack.append(name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scoped(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scoped(node, node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scoped(node, node.name)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self.stack and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self._scoped(node, node.targets[0].id)
        else:
            self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self.stack and isinstance(node.target, ast.Name):
            self._scoped(node, node.target.id)
        else:
            self.generic_visit(node)


def dotted(node: ast.AST) -> str | None:
    """``a.b.c`` for a Name or an Attribute chain on a Name; None for anything else."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def read_source(path: Path) -> str:
    """A source file's text with LF line ends (a Windows checkout without the repository's attributes may differ)."""
    try:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReferenceError(f"{path.name} cannot be read as UTF-8 source: {exc}") from exc


@dataclass(frozen=True)
class Aliases:
    """What a file's imports bind, so a call is identified by where its callee was imported from, not by its name."""

    modules: dict[str, str]  # local name -> the dotted module it names (`import a.b as c`, or `import a.b` binding `a`)
    names: dict[str, str]  # local name -> `module.name` (`from a.b import c as d`)

    def resolve(self, node: ast.AST) -> str | None:
        d = dotted(node)
        if d is None:
            return None
        first, _, rest = d.partition(".")
        base = self.names.get(first) or self.modules.get(first)
        if base is None:
            return d
        return f"{base}.{rest}" if rest else base


def aliases_from(imports: list[ast.Import | ast.ImportFrom], module: str, is_package: bool) -> Aliases:
    """The names a whole file binds by import (scopes are ignored: a lower-bound reading, never a guess)."""
    modules: dict[str, str] = {}
    names: dict[str, str] = {}
    for node in imports:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    modules[a.asname] = a.name
                else:
                    modules[a.name.split(".")[0]] = a.name.split(".")[0]
        else:
            base = absolute_base(node, module, is_package)
            if base is None:
                continue
            for a in node.names:
                if a.name != "*":
                    names[a.asname or a.name] = f"{base}.{a.name}"
    return Aliases(modules, names)


@dataclass
class Index:
    """What every static family asks of a module, collected in one walk: its imports (and so its aliases), its calls
    and its list and tuple literals, each with the symbol it sits in."""

    aliases: Aliases
    imports: list[ast.Import | ast.ImportFrom]
    calls: list[tuple[ast.Call, str | None]]
    seqs: list[tuple[ast.List | ast.Tuple, str | None]]


class _Collect(Scoped):
    def __init__(self) -> None:
        super().__init__()
        self.imports: list[ast.Import | ast.ImportFrom] = []
        self.calls: list[tuple[ast.Call, str | None]] = []
        self.seqs: list[tuple[ast.List | ast.Tuple, str | None]] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append((node, self.symbol))
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self.seqs.append((node, self.symbol))
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self.seqs.append((node, self.symbol))
        self.generic_visit(node)


def index_of(tree: ast.Module, module: str, is_package: bool) -> Index:
    collect = _Collect()
    collect.visit(tree)
    return Index(aliases_from(collect.imports, module, is_package), collect.imports, collect.calls, collect.seqs)


def absolute_base(node: ast.ImportFrom, module: str, is_package: bool) -> str | None:
    """The dotted module a ``from ... import`` names, with a relative level resolved against ``module``."""
    if not node.level:
        return node.module
    package = module.split(".") if is_package else module.split(".")[:-1]
    keep = len(package) - (node.level - 1)
    if keep < 1:
        return None
    return ".".join([*package[:keep], *([node.module] if node.module else [])])
