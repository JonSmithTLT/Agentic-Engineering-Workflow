#!/usr/bin/env python3
"""The build board's data, ``docs/implementation/systems.yaml``: one entry per AEW system, checked against its owners.

    python tools/systems.py check    # exit 1 if the data breaks a rule below, one line per problem; exit 2 if the
                                     # data or one of its owners cannot be read

The board says, for every AEW system, what is built, wired, switched on and used, and what is left to finish it, so
that the operator's limit on partly built systems can be held. The file stores only what is kept by hand: each fact
another file owns is held there and named here by its id. ``check`` reads this checkout as it is (never a snapshot)
and holds the file to:

- **its schema.** A field the generator derives (``GENERATED``: ``serves``, its derivation, counts, priority, lanes)
  is refused, so nothing stored can go stale; so is any field the format does not name, and a value outside its enum.
- **its owners' ids.** Design paths are files under ``docs/``; register ids, ``remaining`` rows and ``serves_pending``
  holds are rows of ``future-work.yaml``; ``as_built`` ids are records of the as-built reference, rendered in memory
  as ``tools/reference.py check`` does (its index is not committed); ``touches`` globs match a file; a switch's
  ``default_evidence`` names a file; ``depends_on`` names known systems and has no cycle.
- **one owner per fact.** An ``as_built`` record, a register row other than a hold group, and a claimed closing work
  each belong to one system; another system that needs it names it in its text.
- **ownership the other way.** Every row the Now list names (``live_rows``) is in exactly one system's ``register``, or
  listed under ``unowned:`` with a reason. An ``unowned:`` entry that is owned, closed or unknown is stale.
- **no claimed hold.** A hold group (``HOLD-NN``) is a register row that holds work until its members are matched; a
  system names it in ``serves_pending``, never in ``register`` or among its claimed closing works (``HOLD_REFUSED``).
  A ``remaining`` slice and ``serves_pending`` may name an open hold; one naming a closed hold is stale.
- **the lint** (``LINT``) over every hand-kept string: no Now position, no pull request number and no register line
  number, each of which another file owns and which go stale; cite the row id or the code's symbol instead. Its
  limits, which a stricter lint takes up once the designer has re-pointed the cites (review of #346, m1): it does not
  see a pull request number of one or two digits (``#88``), a bare ``:NNNN`` register line after a row cite (48 in the
  first import), or a restated Now membership such as "on the Now list".
- **the public-text guard** (``PUBLIC``) over the whole file: no path into the operator's private working folders, no
  reference to the Lead's private list, no absolute path, no carriage return. A record outside this repository is
  cited by its file name only. Its limits (review of #346, n2): it does not see a ``~`` home path, ``/mnt``, ``/root``
  or ``/opt`` paths, a UNC path (``\\\\host\\share``) or one built from an environment variable (``%APPDATA%``,
  ``$HOME``); a reviewer reads the file for those, and for names.

Not here yet: ``render`` and ``systems.md`` (with priority read from the Now list), state read from the code
(``switch.default``, ``wired``) and the limit's count, and the derived ``serves``.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = "docs/implementation/systems.yaml"
REGISTER = "docs/implementation/future-work.yaml"
SCHEMA = "aew/systems/v1"

SYSTEM_ID_RE = re.compile(r"^SYS-\d{2}$")
HOLD_RE = re.compile(r"^HOLD-\d{2}$")
ROW_OWED = "row owed"  # a ``remaining`` slice whose register row is still to be filed

# The file's fields. Each entry's required fields, then its optional ones; nested mappings name theirs.
TOP_FIELDS = ("schema", "wip_limit", "unowned", "systems")
REQUIRED = ("id", "name", "purpose", "design", "register", "as_built", "touches", "depends_on", "state",
            "finish_line", "remaining", "decision", "recommendation", "who", "reason", "evidence")
OPTIONAL = ("serves_claims", "serves_pending", "design_unpublished", "touches_new", "switch")
LISTS = ("design", "register", "as_built", "touches", "depends_on", "evidence", "serves_pending",
         "design_unpublished", "touches_new")
TEXTS = ("id", "name", "purpose", "finish_line", "decision", "recommendation", "who", "reason")
STATE_FIELDS = ("board_state", "built", "wired", "on_by_default", "used_in_default_flow")
SWITCH_FIELDS = ("key", "default", "default_evidence", "owner", "turning_on_changes")
SLICE_FIELDS = ("slice", "row", "estimate")
CLAIM_FIELDS = ("closing_works", "extra")
ENUMS = {
    ("state", "board_state"): ("on_and_used", "partly_built", "built_off", "built_not_wired", "staged",
                               "designed_only"),
    ("state", "built"): ("yes", "partly", "no"),
    ("state", "used_in_default_flow"): ("yes", "partly", "no"),
    ("recommendation",): ("finish", "switch_on", "freeze", "cut", "keep", "done"),
}
# What the generator derives, never stored: the field, and who derives it.
GENERATED = {
    "serves": "the requirement ids, derived from serves_claims and as_built against the trace",
    "serves_derivation": "how serves was derived",
    "counts": "the counts, computed over the entries",
    "priority": "a row's place in the register's Now list",
    "lanes": "which slices can run beside which, computed from touches and depends_on",
}
# Where a hold group may not be named: a system that claims a hold claims work nobody has matched to it yet.
HOLD_REFUSED = ("register", "serves_claims.closing_works")
# The lint over hand-kept text: each pattern, and why its fact is not this file's.
LINT = {
    r"\bNow (?:items? )?\d+": "a Now position is the register's Now list's (cite the row id)",
    r"#\d{3,}": "a pull request's number and state are GitHub's (cite the row id or the code's symbol)",
    r"future-work\.yaml:\d+": "a register line number goes stale on the next register change (cite the row id)",
}
# The public-text guard over the whole file: each pattern, and what to write instead.
PUBLIC = {
    r"AEW-plans|AEW-reviews|AEW-architecture-workspace|aew-private": "a path into a private working folder (cite "
    "a record outside this repository by its file name only)",
    r"\bITEMS\b": "a reference to the Lead's private list (name the register row or the code's symbol)",
    r"\b[A-Za-z]:[\\/]|(?<![\w.])/(?:home|Users|tmp)/": "an absolute path (use a path relative to the repository)",
    "\r": "a carriage return (the file is LF only)",
}


class SystemsError(Exception):
    """The data or one of its owners cannot be read: exit 2, never 1."""


@dataclass(frozen=True)
class Problem:
    check: str  # which rule, so a planted case can name the one it breaks
    where: str  # a system id, ``unowned`` or a line of the file
    text: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.where}: {self.text}"


@dataclass(frozen=True)
class Owners:
    """What the board's ids are checked against, read from one checkout."""

    root: Path  # globs and paths resolve here
    rows: frozenset[str]  # every register row id, open or closed
    open_rows: frozenset[str]
    now_rows: frozenset[str]  # the open rows the Now list names
    records: frozenset[str]  # the as-built reference's record ids


def _tool(name: str) -> ModuleType:
    """A sibling tool, imported by its path once."""
    key = f"{name}_tool"
    if key not in sys.modules:
        spec = importlib.util.spec_from_file_location(key, Path(__file__).resolve().parent / f"{name}.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]


def register_owners(text: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """The register's row ids, its open ones, and the open ones its Now list names, from ``future-work.yaml``'s text."""
    register = _tool("register")
    data = register._load(text)
    every, opened = set(), set()
    for row in register.rows(data, open_only=False):
        first = next(iter(row["row"].values()))
        if register.LABELLED_ID_RE.match(first):
            every.add(first.split(" (", 1)[0])
    for row in register.rows(data):
        if row["id"]:
            opened.add(row["id"])
    now = {rid for _, ids in register.now_list(data) for rid in ids}
    return frozenset(every), frozenset(opened), frozenset(now)


def reference_records(root: Path) -> frozenset[str]:
    """The as-built reference's record ids, rendered in memory from ``root``'s code."""
    reference = _tool("reference")
    common = reference._families()[0]
    try:
        files = reference.render_files(root)
    except common.ReferenceError as exc:
        raise SystemsError(f"the as-built reference cannot be rendered: {exc}") from exc
    return frozenset(json.loads(files[reference.INDEX])["records"])


def owners(root: Path = ROOT) -> Owners:
    try:
        rows, open_rows, now_rows = register_owners((root / REGISTER).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SystemsError(f"{REGISTER} cannot be read: {exc}") from exc
    return Owners(root, rows, open_rows, now_rows, reference_records(root))


def load(text: str) -> Any:
    """The file's data, refusing a repeated key (which a plain load keeps only the last of)."""
    try:
        return yaml.load(text, Loader=_tool("register")._StrictLoader)  # noqa: S506 - a SafeLoader
    except yaml.YAMLError as exc:
        raise SystemsError(f"{SYSTEMS} is not valid YAML: {exc}") from exc


def live_rows(own: Owners) -> frozenset[str]:
    """The rows that must each be owned by a system or listed as unowned: the open rows the Now list names (the
    format's draft 3; the Lead, 2026-11-06). Widening it to every open row is a later decision, not this check's: about
    60 open rows, mostly unscheduled, belong to no system today, and each would need its owner or its reason."""
    return own.now_rows


# ------------------------------------------------------------------------------------------------- the checks

def _strings(value: Any, where: str) -> list[tuple[str, str]]:
    """Every string under ``value``, with its place (``remaining[2].slice``)."""
    if isinstance(value, str):
        return [(where, value)]
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in _strings(v, f"{where}.{k}" if where else str(k))]
    if isinstance(value, list):
        return [s for i, v in enumerate(value) for s in _strings(v, f"{where}[{i}]")]
    return []


def _get(entry: dict[str, Any], path: tuple[str, ...]) -> Any:
    for key in path:
        entry = entry.get(key) if isinstance(entry, dict) else None  # type: ignore[assignment]
    return entry


def schema_problems(data: Any) -> list[Problem]:
    """The file's shape: the top-level fields, each entry's fields and types, the enums, distinct ids. A generated
    field is its own check (``generated_problems``)."""
    out: list[Problem] = []

    def bad(where: str, text: str) -> None:
        out.append(Problem("schema", where, text))

    if not isinstance(data, dict):
        return [Problem("schema", "file", f"the file is a mapping with the fields {', '.join(TOP_FIELDS)}")]
    for key in sorted(set(data) - set(TOP_FIELDS) - set(GENERATED)):
        bad("file", f"unknown top-level field {key!r}")
    if data.get("schema") != SCHEMA:
        bad("file", f"schema is {data.get('schema')!r}, not {SCHEMA!r}")
    if not (isinstance(data.get("wip_limit"), int) and not isinstance(data.get("wip_limit"), bool)):
        bad("file", "wip_limit (the operator's N) is a whole number")
    unowned = data.get("unowned")
    if not isinstance(unowned, dict):
        bad("unowned", "unowned is a mapping from a register row id to its reason")
    systems = data.get("systems")
    if not isinstance(systems, list):
        bad("file", "systems is a list of entries")
        return out
    seen: set[str] = set()
    for i, entry in enumerate(systems):
        if not isinstance(entry, dict):
            bad(f"systems[{i}]", "an entry is a mapping")
            continue
        sid = entry.get("id")
        where = sid if isinstance(sid, str) else f"systems[{i}]"
        if not (isinstance(sid, str) and SYSTEM_ID_RE.match(sid)):
            bad(where, f"id {sid!r} is not SYS-NN")
        elif sid in seen:
            bad(where, "the id is used by two entries")
        else:
            seen.add(sid)
        for key in REQUIRED:
            if key not in entry:
                bad(where, f"the required field {key!r} is missing")
        for key in sorted(set(entry) - set(REQUIRED) - set(OPTIONAL) - set(GENERATED)):
            bad(where, f"unknown field {key!r}")
        for key in LISTS:
            if key in entry and not (isinstance(entry[key], list) and all(isinstance(v, str) for v in entry[key])):
                bad(where, f"{key} is a list of text")
        for key in TEXTS:
            if key in entry and not isinstance(entry[key], str):
                bad(where, f"{key} is text")
        for name, fields, required in (("state", STATE_FIELDS, STATE_FIELDS), ("switch", SWITCH_FIELDS, ("key",)),
                                       ("serves_claims", CLAIM_FIELDS, ())):
            value = entry.get(name)
            if value is None and name not in REQUIRED:
                continue
            if not isinstance(value, dict):
                bad(where, f"{name} is a mapping of {', '.join(fields)}")
                continue
            for key in sorted(set(value) - set(fields)):
                bad(where, f"unknown field {name}.{key}")
            for key in required:
                if key not in value:
                    bad(where, f"the required field {name}.{key} is missing")
        for i_slice, item in enumerate(entry.get("remaining") or []):
            if not (isinstance(item, dict) and set(item) == set(SLICE_FIELDS)
                    and all(isinstance(v, str) for v in item.values())):
                bad(where, f"remaining[{i_slice}] is a mapping of exactly {', '.join(SLICE_FIELDS)}, each text")
        if not isinstance(entry.get("remaining", []), list):
            bad(where, "remaining is a list of slices")
        for path, allowed in ENUMS.items():
            value = _get(entry, path)
            if value is not None and value not in allowed:
                bad(where, f"{'.'.join(path)} is {value!r}, not one of {', '.join(allowed)}")
    return out


def generated_problems(data: Any) -> list[Problem]:
    """A field the generator derives is never stored: it would go stale the day it is written."""
    out = []
    places = [("file", data)] if isinstance(data, dict) else []
    for entry in _entries(data):
        places.append((entry.get("id", "?"), entry))
    for where, mapping in places:
        for key in sorted(set(mapping) & set(GENERATED)):
            out.append(Problem("generated", where, f"{key} is generated ({GENERATED[key]}), never stored: remove "
                                                   "it"))
    return out


def _entries(data: Any) -> list[dict[str, Any]]:
    systems = data.get("systems") if isinstance(data, dict) else None
    return [e for e in systems if isinstance(e, dict) and isinstance(e.get("id"), str)] if isinstance(systems,
                                                                                                         list) else []


def _list(entry: dict[str, Any], key: str) -> list[str]:
    value = entry.get(key)
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _slices(entry: dict[str, Any]) -> list[dict[str, Any]]:
    value = entry.get("remaining")
    return [s for s in value if isinstance(s, dict)] if isinstance(value, list) else []


def _claimed_works(entry: dict[str, Any]) -> list[str]:
    claims = entry.get("serves_claims")
    works = claims.get("closing_works") if isinstance(claims, dict) else None
    return [w for w in works if isinstance(w, str)] if isinstance(works, list) else []


def _matches(root: Path, pattern: str) -> bool:
    """A file under ``root`` matches the glob. ``glob.glob`` and not ``Path.glob``: before Python 3.13, ``Path.glob``
    reads a trailing ``**`` as directories only (review of #346, B1), and ``glob.glob`` reads it the same on every
    supported Python, as the board's first checker did."""
    if not pattern.strip() or pattern.startswith("/") or ".." in Path(pattern).parts or re.match(r"[A-Za-z]:",
                                                                                                    pattern):
        return False
    return any((root / p).is_file() for p in glob.glob(pattern, root_dir=root, recursive=True))


def existence_problems(data: Any, own: Owners) -> list[Problem]:
    """Every id the entries name is one its owner holds (``assemble.py``'s checks, run against this checkout)."""
    out = []
    for entry in _entries(data):
        sid = entry["id"]
        for path in _list(entry, "design"):
            if not (path.startswith("docs/") and (own.root / path).is_file()):
                out.append(Problem("design", sid, f"design path {path} is not a file under docs/"))
        for rid in _list(entry, "register"):
            if rid not in own.rows:
                out.append(Problem("register", sid, f"register id {rid} is not a row of {REGISTER}"))
        for hold in _list(entry, "serves_pending"):
            if not (HOLD_RE.match(hold) and hold in own.rows):
                out.append(Problem("register", sid, f"serves_pending {hold} is not a hold row of {REGISTER}"))
        for i, item in enumerate(_slices(entry)):
            row = item.get("row")
            if row != ROW_OWED and row not in own.rows:
                out.append(Problem("remaining", sid, f"remaining[{i}].row {row!r} is not a row of {REGISTER} (or "
                                                     f"{ROW_OWED!r})"))
        for rid in _list(entry, "as_built"):
            if rid not in own.records:
                out.append(Problem("as_built", sid, f"as_built {rid} is not a record of the as-built reference "
                                                    "(`python tools/reference.py render` lists them)"))
        for pattern in _list(entry, "touches"):
            if not pattern.strip():
                out.append(Problem("touches", sid, "touches holds an empty glob: remove it or name the files"))
            elif not _matches(own.root, pattern):
                out.append(Problem("touches", sid, f"touches {pattern} matches no file"))
        switch = entry.get("switch")
        evidence = switch.get("default_evidence") if isinstance(switch, dict) else None
        if isinstance(evidence, str):
            named = re.match(r"[^\s:]+", evidence)
            if not (named and (own.root / named.group(0)).is_file()):
                out.append(Problem("switch", sid, f"switch.default_evidence names no file: {evidence[:80]}"))
    return out


def dependency_problems(data: Any) -> list[Problem]:
    """``depends_on`` names known systems, and has no cycle (the first found from each system, once)."""
    entries = _entries(data)
    known = {e["id"] for e in entries}
    deps = {e["id"]: [d for d in _list(e, "depends_on") if d in known] for e in entries}
    out = [Problem("depends_on", e["id"], f"depends_on {d} is not a system of this file")
           for e in entries for d in _list(e, "depends_on") if d not in known]
    cycles: set[tuple[str, ...]] = set()
    state: dict[str, int] = {}  # 1 on the path, 2 done

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for dep in sorted(deps.get(node, [])):
            if state.get(dep) == 1:
                cycle = path[path.index(dep):]
                turn = cycle.index(min(cycle))
                cycles.add(tuple(cycle[turn:] + cycle[:turn]))
            elif dep not in state:
                visit(dep, [*path, dep])
        state[node] = 2

    for node in sorted(deps):
        if node not in state:
            visit(node, [node])
    out += [Problem("depends_on", c[0], "a cycle: " + " -> ".join([*c, c[0]])) for c in sorted(cycles)]
    return out


def owner_problems(data: Any) -> list[Problem]:
    """One owner per fact (the format's rule 4): an as_built record, a register row other than a hold, and a claimed
    closing work each belong to one system."""
    holders: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entry in _entries(data):
        for rid in _list(entry, "as_built"):
            holders[("as_built record", rid)].append(entry["id"])
        for rid in _list(entry, "register"):
            if not HOLD_RE.match(rid):
                holders[("register row", rid)].append(entry["id"])
        for work in _claimed_works(entry):
            holders[("closing work", work)].append(entry["id"])
    return [Problem("owner", ", ".join(ids), f"the {kind} {fact[:80]} is in {len(ids)} systems: keep it in one, and "
                    "name it in the others' text") for (kind, fact), ids in sorted(holders.items()) if len(ids) > 1]


def reverse_problems(data: Any, own: Owners) -> list[Problem]:
    """Ownership the other way: every live row (``live_rows``) is in exactly one system's register or listed as
    unowned, and every unowned entry is a live open row that no system owns, with its reason."""
    owned: dict[str, list[str]] = defaultdict(list)
    for entry in _entries(data):
        for rid in _list(entry, "register"):
            owned[rid].append(entry["id"])
    unowned = data.get("unowned") if isinstance(data, dict) else None
    unowned = unowned if isinstance(unowned, dict) else {}
    out = []
    for rid in sorted(live_rows(own) - set(owned) - set(unowned)):
        out.append(Problem("unowned", rid, f"the Now list names {rid}, which no system owns: add it to one system's "
                                           f"register, or list it under unowned: in {SYSTEMS} with the reason"))
    for rid, reason in sorted(unowned.items(), key=lambda kv: str(kv[0])):
        if rid in owned:
            out.append(Problem("unowned", str(rid), f"listed as unowned but {', '.join(owned[rid])} owns it: remove "
                                                    "it from unowned:"))
        elif rid not in own.open_rows:
            out.append(Problem("unowned", str(rid), f"listed as unowned but not an open row of {REGISTER}: remove "
                                                    "it from unowned:"))
        if not (isinstance(reason, str) and reason.strip()):
            out.append(Problem("unowned", str(rid), "an unowned row carries its reason"))
    return out


def hold_problems(data: Any, own: Owners) -> list[Problem]:
    """No system claims a hold group: it is named in ``serves_pending`` until the designer matches its members. A
    ``remaining`` slice may name an open hold as its row, the work it waits on; once the group closes, its work is
    carried by the member rows the match restored, so a slice still naming it is stale (the Lead, 2026-11-06)."""
    out = []
    for entry in _entries(data):
        places = {"register": _list(entry, "register"), "serves_claims.closing_works": _claimed_works(entry)}
        for place in HOLD_REFUSED:
            for value in places[place]:
                if HOLD_RE.match(value.split(",", 1)[0].split(" ", 1)[0]):
                    out.append(Problem("hold", entry["id"], f"{place} claims the hold group {value[:40]}: name it in "
                                                            "serves_pending instead"))
        for hold in _list(entry, "serves_pending"):  # a closed group holds nothing (review of #346, m2)
            if HOLD_RE.match(hold) and hold in own.rows and hold not in own.open_rows:
                out.append(Problem("hold", entry["id"], f"serves_pending names the hold group {hold}, which has "
                                                        "closed: name the member rows that now carry its work"))
        for i, item in enumerate(_slices(entry)):
            row = item.get("row")
            if isinstance(row, str) and HOLD_RE.match(row) and row in own.rows and row not in own.open_rows:
                out.append(Problem("hold", entry["id"], f"remaining[{i}] ({str(item.get('slice'))[:50]}) names the "
                                                        f"hold group {row}, which has closed: point the slice at the "
                                                        "member row that now carries its work"))
    return out


def lint_problems(data: Any) -> list[Problem]:
    """No fact another file owns, restated in hand-kept text: a Now position, a pull request number, a register line."""
    places = [(e["id"], _strings({k: v for k, v in e.items() if k != "id"}, "")) for e in _entries(data)]
    unowned = data.get("unowned") if isinstance(data, dict) else None
    if isinstance(unowned, dict):
        places.append(("unowned", _strings({str(k): v for k, v in unowned.items()}, "")))
    out = []
    for where, strings in places:
        for field, text in strings:
            for pattern, why in LINT.items():
                for m in re.finditer(pattern, text):
                    out.append(Problem("lint", where, f"{field} says {m.group(0)!r}: {why}"))
    return out


def public_problems(text: str) -> list[Problem]:
    """Nothing private in the file's text, its comments included."""
    out = []
    for pattern, why in PUBLIC.items():
        for m in re.finditer(pattern, text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(Problem("public", f"line {line}", f"{m.group(0)!r}: {why}"))
    return out


def problems(text: str, own: Owners) -> list[Problem]:
    """Every problem of the file's text against its owners, in a stable order."""
    data = load(text)
    found = (schema_problems(data) + generated_problems(data) + existence_problems(data, own)
             + dependency_problems(data) + owner_problems(data) + reverse_problems(data, own) + hold_problems(data, own)
             + lint_problems(data) + public_problems(text))
    return sorted(set(found), key=lambda p: (p.check, p.where, p.text))


def check(root: Path = ROOT, own: Owners | None = None) -> list[Problem]:
    try:
        text = (root / SYSTEMS).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemsError(f"{SYSTEMS} cannot be read: {exc}") from exc
    return problems(text, owners(root) if own is None else own)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a Windows console's code page must not break a message
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python tools/systems.py", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("command", choices=("check",))
    ap.parse_args(argv)
    try:
        found = check()
    except SystemsError as exc:
        print(f"cannot check {SYSTEMS}: {exc}", file=sys.stderr)
        return 2
    if found:
        print("\n".join(map(str, found)), file=sys.stderr)
        print(f"{len(found)} problem(s) in {SYSTEMS}", file=sys.stderr)
        return 1
    print(f"{SYSTEMS} holds to its owners")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
