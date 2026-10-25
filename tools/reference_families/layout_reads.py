"""The read side of the ``.aew`` layout: which function reads which path (STG-12 S12-2, DOC-04's readers).

The mirror of the writers family's write sites. A **read site** is a call of a read primitive, identified by where its
callee was imported from (``os.stat``, ``aew.util.read_yaml``) or, for a method that has no import source, by what it
is (``Path.read_text``, ``Path.exists``, ``Path.glob``, ``open`` in a read mode). The destination expression is
evaluated by the same value flow as a write's (:mod:`reference_families.writers_flow`); a value that is a path under
``.aew`` whose first entry is declared becomes a *read* of that path's directory, and the reader is the function the
call is in. ``aew.util`` is the read mechanism (its callers are the readers), as it is the write mechanism.

A lower bound, and a different one from the writers': a read through an API (``store.read()``) is attributed to the
store function that makes it, not to its callers; a read of a path this reading could not place under ``.aew`` or
provably outside it is listed as unplaced (any of them may read any entry). A second detector over tokens
(:mod:`reference_families.layout_reads_text`) finds the same calls, and the two must agree per module.
"""

from __future__ import annotations

import ast
from collections import Counter
from typing import NamedTuple

from reference_families import common as C
from reference_families import writers as W
from reference_families import writers_flow as F

UTIL = W.UTIL
# callee (by import source) -> (label, index of the path argument)
READ_CALLS: dict[str, tuple[str, int]] = {
    "os.stat": ("os.stat", 0), "os.lstat": ("os.lstat", 0), "os.listdir": ("os.listdir", 0),
    "os.scandir": ("os.scandir", 0), "os.path.exists": ("os.path.exists", 0), "os.path.isfile": ("os.path.isfile", 0),
    "os.path.isdir": ("os.path.isdir", 0), "os.path.getsize": ("os.path.getsize", 0),
    "os.path.getmtime": ("os.path.getmtime", 0), "os.path.islink": ("os.path.islink", 0),
    "shutil.copy": ("shutil.copy", 0), "shutil.copy2": ("shutil.copy2", 0), "shutil.copyfile": ("shutil.copyfile", 0),
    "shutil.copytree": ("shutil.copytree", 0),
    f"{UTIL}.read_yaml": ("read_yaml", 0), f"{UTIL}.sha256_file": ("sha256_file", 0),
}
# Path methods that read their receiver, by name (a method has no import source): the limit is the family's, listed.
RECEIVER_READS = frozenset({"read_text", "read_bytes", "exists", "is_file", "is_dir", "is_symlink", "stat", "lstat",
                            "iterdir", "glob", "rglob"})

# What this reading does not see, one entry per class: (a name the tests' probes are keyed by, how the page says it).
# The page is written from this tuple and each entry has a probe, both ways (tests/unit/test_reference_layout_rules.py).
CANNOT_SEE: tuple[tuple[str, str], ...] = (
    ("subprocess", "a read by a subprocess"),
    ("computed-method", "a method named by a computed attribute, `getattr(path, name)()`"),
    ("local-name-primitive", "a primitive bound to a local name and called by it"),
    ("other-openers", "a read by a library that opens the path itself (`codecs.open`, `tarfile.open`, "
     "`sqlite3.connect`, `zipfile.ZipFile`), and a read through a handle that was opened elsewhere (`fh.read()`)"),
    ("update-mode", "a file opened for update, `open(path, 'r+')`: the writers family has it as a write, and it is not "
     "counted as a read"),
    ("unreadable-mode", "an `open` whose mode is not a literal this reading can read (the writers family lists it as "
     "an unresolved write)"),
    ("directory-walk", "a directory walk, `os.walk`, and the reads by a primitive this reading does not name "
     "(`os.fstat`, `os.access`, `os.readlink`, `os.path.lexists`, `os.path.realpath`); the tree has live ones under "
     "`.aew` (the store's mode check walks `state`; `control_key` walks `policy`)"),
)


class ReadSite(NamedTuple):
    module: str
    symbol: str
    primitive: str
    values: F.Values


def read_of(mod: F.Module, call: ast.Call, func: F.Func | None = None) -> tuple[str, ast.expr] | None:
    """(the primitive's label, the path expression) when the call is a read site, else None."""
    callee = mod.aliases.resolve(call.func)
    if callee is not None and (callee in mod.funcs or callee in mod.classes):
        callee = f"{mod.name}.{callee}"  # a function or class of this module, called by its bare name
    if callee in READ_CALLS:
        label, index = READ_CALLS[callee]
        if len(call.args) > index and not any(isinstance(a, ast.Starred) for a in call.args[: index + 1]):
            return label, call.args[index]
        return None
    if callee in ("open", "io.open"):
        mode = call.args[1] if len(call.args) > 1 else W._keyword(call, "mode")
        if not call.args:
            return None
        return ("open", call.args[0]) if W.mode_verdict(func, mode) == W.READ else None
    if callee == "os.open":
        flags = call.args[1] if len(call.args) > 1 else W._keyword(call, "flags")
        if not call.args:
            return None
        return ("os.open", call.args[0]) if W.flags_verdict(mod, func, flags) == W.READ else None
    if not isinstance(call.func, ast.Attribute):
        return None
    method, receiver = call.func.attr, call.func.value
    if method in RECEIVER_READS:
        return f"Path.{method}", receiver
    if method == "open":
        keyword = W._keyword(call, "mode")
        arg = keyword if keyword is not None else (call.args[0] if call.args else None)
        return ("Path.open", receiver) if W.mode_verdict(func, arg) == W.READ else None
    return None


def read_labels() -> list[str]:
    """The read primitives the reading knows, by label: one list for the page."""
    labels = {label for label, _ in READ_CALLS.values()}
    return sorted(labels | {f"Path.{m}" for m in RECEIVER_READS} | {"open", "os.open", "Path.open"})


def read_counts(program: F.Program) -> dict[str, Counter[str]]:
    """Every read-primitive call of every module (the mechanism too), by module and label: what the text reading is
    held to. No destination is read."""
    counts: dict[str, Counter[str]] = {}
    for name, mod in program.modules.items():
        scopes = [(None, mod.module_calls), *[(f, f.calls) for f in mod.funcs.values()]]
        counts[name] = Counter(hit[0] for func, calls in scopes for c in calls
                               if (hit := read_of(mod, c, func)) is not None)
    return counts


def read_sites(program: F.Program, evaluator: F.Evaluator) -> list[ReadSite]:
    found = []
    for name, mod in program.modules.items():
        if name in W.MECHANISM_MODULES:
            continue
        scopes: list[tuple[F.Func | None, list[ast.Call]]] = [(None, mod.module_calls)]
        scopes += [(f, f.calls) for f in mod.funcs.values()]
        for func, calls in scopes:
            for call in calls:
                hit = read_of(mod, call, func)
                if hit is None:
                    continue
                if func is None:
                    raise C.ReferenceError(
                        f"{name} reads at import time ({hit[0]}), outside any function, so the read has nothing to "
                        "anchor to: put it in a function, or extend the layout family to read module-level reads")
                found.append(ReadSite(name, func.qual, hit[0], evaluator.value(mod, func, hit[1])))
    return sorted(found, key=lambda s: (s.module, s.symbol, s.primitive))


class Placed(NamedTuple):
    """Where the read sites read: by function, the templates under ``.aew`` (first entry declared); the functions (and
    primitives) with a site whose path this reading could not place under ``.aew`` or provably outside it; and the
    sites by class, which add up to ``sites``: all values placed under ``.aew``, all outside it (or the directory
    itself), and some value not placed."""

    reads: dict[str, set[tuple[str, str]]]  # template -> the (module, symbol) that read it
    unplaced: list[tuple[str, str, str]]  # (module, symbol, primitive)
    sites: int
    placed_sites: int
    outside_sites: int
    unplaced_sites: int


def place(sites: list[ReadSite], top_level: frozenset[str]) -> Placed:
    reads: dict[str, set[tuple[str, str]]] = {}
    unplaced: set[tuple[str, str, str]] = set()
    placed_sites = outside_sites = unplaced_sites = 0
    for site in sites:
        complete, under = True, False
        for kind, text in site.values:
            if kind == F.TPL and text.split("/")[0] in top_level:  # a computed first entry is `{}`, never declared
                reads.setdefault(text, set()).add((site.module, site.symbol))
                under = True
            elif kind not in (F.OUT, F.ROOT):  # outside `.aew`, or the directory itself: neither is unplaced
                complete = False
        if not complete:
            unplaced.add((site.module, site.symbol, site.primitive))
            unplaced_sites += 1
        elif under:
            placed_sites += 1
        else:
            outside_sites += 1
    return Placed(reads, sorted(unplaced), len(sites), placed_sites, outside_sites, unplaced_sites)
