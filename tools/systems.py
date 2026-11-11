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
  ``$HOME``), nor a private folder's sub-folder named alone (``build-board-2026-11-06/FORMAT.md``); a reviewer reads
  the file for those, and for names.

``render`` writes ``systems.md`` with priority read from the Now list; ``check`` also refuses a stale page.
``show SYS-NN`` prints an entry as stored and its derived priority, without writing anything.
``check`` also checks table-owned switch defaults and evidence, decidable on_by_default pairs, wired reference
records, stale remaining slices and FORMAT.md rule 1's count. A count above wip_limit requires the operator's covering
wip_allowance; the allowance is stale once the count recovers. A system ``awaiting_signoff`` (built, wired and on by
default, with no slices left, not yet tested and signed off by the operator) is not counted. ``on_and_used`` requires
the operator's ``signoff`` (a quoted date and their words), and a sign-off on any other state is refused. The lag rule:
a system with no own slices left that is still partly_built, built_off, built_not_wired or staged is refused unless
its recommendation is freeze, cut or keep. The operator's words and their extra conditions are reviewed, not
authenticated or interpreted by the tool. Defaults outside the tables and lead_text/pack wiring remain
hand-kept and are labelled. Render labels the evidence citations; check validates their table ownership. Render
imports neither the policy tables nor the as-built reference.
Not here yet: deriving board_state or built, serves, lanes or a dashboard view.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import importlib.util
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SYSTEMS = "docs/implementation/systems.yaml"
MARKDOWN = "docs/implementation/systems.md"
REGISTER = "docs/implementation/future-work.yaml"
SCHEMA = "aew/systems/v1"

SYSTEM_ID_RE = re.compile(r"^SYS-\d{2}$")
HOLD_RE = re.compile(r"^HOLD-\d{2}$")
ROW_OWED = "row owed"  # a ``remaining`` slice whose register row is still to be filed

# The file's fields. Each entry's required fields, then its optional ones; nested mappings name theirs.
TOP_FIELDS = ("schema", "wip_limit", "unowned", "systems", "wip_allowance")
ALLOWANCE_FIELDS = ("count", "operator", "date")
GATE_SOURCE = "src/aew/knowledge/manifest.py:DEFAULT_GATES"
SWITCH_SOURCE = "src/aew/policy/execution.py:STRING_SWITCHES"
WIRED_RECORDS = {"cli": "cli-commands", "dashboard": "dashboard-routes", "tool": "tools"}
HAND_WIRED = ("lead_text", "pack")
REQUIRED = ("id", "name", "purpose", "design", "register", "as_built", "touches", "depends_on", "state",
            "finish_line", "remaining", "decision", "recommendation", "who", "reason", "evidence")
OPTIONAL = ("serves_claims", "serves_pending", "design_unpublished", "touches_new", "switch", "signoff")
LISTS = ("design", "register", "as_built", "touches", "depends_on", "evidence", "serves_pending",
         "design_unpublished", "touches_new")
TEXTS = ("id", "name", "purpose", "finish_line", "decision", "recommendation", "who", "reason")
STATE_FIELDS = ("board_state", "built", "wired", "on_by_default", "used_in_default_flow")
SWITCH_FIELDS = ("key", "default", "default_evidence", "owner", "turning_on_changes")
SLICE_FIELDS = ("slice", "row", "estimate")
CLAIM_FIELDS = ("closing_works", "extra")
SIGNOFF_FIELDS = ("date", "words")
# The operator's sign-off (the operator, 2026-11-10): a system built, wired and on by default with no slices left is
# awaiting_signoff until the operator has tested it and signed it off; only then is it on_and_used, carrying the
# sign-off's date and words. Awaiting sign-off is not counted toward wip_limit.
AWAITING = "awaiting_signoff"
AWAITING_LABEL = "built, awaiting your sign-off"
SIGNED = "on_and_used"
# The states FORMAT.md rule 1 counts, and that a system with no own slices left must have moved out of (the lag rule).
BUILDING = ("partly_built", "built_off", "built_not_wired", "staged")
# The recommendations that take a system out of the count and out of the lag rule.
NOT_COUNTED = ("freeze", "cut", "keep")
ENUMS = {
    ("state", "board_state"): (SIGNED, AWAITING, *BUILDING, "designed_only"),
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
    now_order: dict[str, int] = field(default_factory=dict)  # row -> lowest open Now item number
    gate_defaults: dict[str, Any] = field(default_factory=dict)
    string_switches: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)


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
    try:
        reference = _tool("reference")
        common = reference._families()[0]
    except (ImportError, OSError) as exc:
        raise SystemsError(f"the as-built reference cannot be imported: {exc}") from exc
    try:
        files = reference.render_files(root)
        return frozenset(json.loads(files[reference.INDEX])["records"])
    except (common.ReferenceError, ImportError, OSError, KeyError, ValueError) as exc:
        raise SystemsError(f"the as-built reference cannot be rendered: {exc}") from exc


def code_tables(root: Path = ROOT) -> tuple[dict[str, Any], dict[tuple[str, str], tuple[str, ...]]]:
    """The code's tables, never defaults copied into this tool. Check reads them after the reference. Rendering uses
    the evidence citations instead; switch_problems validates those citations against these tables."""
    try:
        manifest = __import__("aew.knowledge.manifest", fromlist=["DEFAULT_GATES"])
        execution = __import__("aew.policy.execution", fromlist=["STRING_SWITCHES"])
        for module in (manifest, execution):
            if (root / "src").resolve() not in Path(module.__file__).resolve().parents:
                raise SystemsError("policy tables are not imported from this checkout; set absolute PYTHONPATH to src")
        gates, switches = manifest.DEFAULT_GATES, execution.STRING_SWITCHES
    except (ImportError, AttributeError, OSError) as exc:
        raise SystemsError(f"the policy tables cannot be read: {exc}") from exc
    if not isinstance(gates, dict) or not isinstance(switches, dict):
        raise SystemsError("DEFAULT_GATES and STRING_SWITCHES must be mappings")
    if any(not (isinstance(key, tuple) and len(key) == 2 and all(isinstance(k, str) for k in key)
                and isinstance(values, tuple) and values and all(isinstance(v, str) for v in values))
           for key, values in switches.items()):
        raise SystemsError("STRING_SWITCHES must map (block, key) pairs to nonempty tuples of string values")
    return dict(gates), dict(switches)


def owners(root: Path = ROOT) -> Owners:
    try:
        rows, open_rows, now_rows = register_owners((root / REGISTER).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SystemsError(f"{REGISTER} cannot be read: {exc}") from exc
    records = reference_records(root)
    gates, switches = code_tables(root)
    return Owners(root, rows, open_rows, now_rows, records, now_order(root), gates, switches)


def now_order(root: Path) -> dict[str, int]:
    """Read only the register, through its Now reader; never render the as-built reference."""
    register = _tool("register")
    try:
        data = register._load((root / REGISTER).read_text(encoding="utf-8"))
        order: dict[str, int] = {}
        for number, ids in register.now_list(data):
            for rid in ids:
                order[rid] = min(number, order.get(rid, number))
        return order
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise SystemsError(f"{REGISTER} cannot be read: {exc}") from exc


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
    if "wip_allowance" in data:
        allowance = data["wip_allowance"]
        if not isinstance(allowance, dict) or set(allowance) != set(ALLOWANCE_FIELDS):
            bad("wip_allowance", "an allowance has exactly count, operator and date")
        else:
            count, words, when = (allowance[k] for k in ALLOWANCE_FIELDS)
            if (not isinstance(count, int) or isinstance(count, bool)
                    or not isinstance(data.get("wip_limit"), int) or count <= data["wip_limit"]):
                bad("wip_allowance", "count must be an integer above wip_limit")
            if not isinstance(words, str) or not words.strip():
                bad("wip_allowance", "operator must be the operator's non-empty words, verbatim")
            if not _is_date(when):
                bad("wip_allowance", "date must be a quoted YYYY-MM-DD string naming a real date")
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
        if isinstance(entry.get("state"), dict):
            state = entry["state"]
            if not isinstance(state.get("on_by_default"), bool):
                bad(where, "state.on_by_default is a boolean")
            if not isinstance(state.get("wired"), list) or not all(isinstance(v, str) for v in state["wired"]):
                bad(where, "state.wired is a list of text")
        if isinstance(entry.get("switch"), dict):
            for key in ("key", "default", "default_evidence"):
                if key in entry["switch"] and not isinstance(entry["switch"][key], str):
                    bad(where, f"switch.{key} is text")
        if "signoff" in entry:
            signoff = entry["signoff"]
            if not isinstance(signoff, dict) or set(signoff) != set(SIGNOFF_FIELDS):
                bad(where, "signoff has exactly date and words")
            else:
                if not _is_date(signoff["date"]):
                    bad(where, "signoff.date must be a quoted YYYY-MM-DD string naming a real date")
                if not isinstance(signoff["words"], str) or not signoff["words"].strip():
                    bad(where, "signoff.words must be the operator's non-empty words, verbatim")
    return out


def _is_date(value: Any) -> bool:
    """A quoted YYYY-MM-DD naming a real date (an unquoted one loads as a date, not text)."""
    try:
        return (isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
                and bool(datetime.date.fromisoformat(value)))
    except ValueError:
        return False


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
    """No fact another file owns, restated in hand-kept text: a Now position, a pull request number, a register line.
    A sign-off is the operator's words, verbatim, as the allowance is: exempt from the lint, never from the public
    guard."""
    places = [(e["id"], _strings({k: v for k, v in e.items() if k not in ("id", "signoff")}, ""))
              for e in _entries(data)]
    unowned = data.get("unowned") if isinstance(data, dict) else None
    if isinstance(unowned, dict):
        places.append(("unowned", _strings({str(k): v for k, v in unowned.items()}, "")))
    out = []
    for where, strings in places:
        for field_name, text in strings:
            for pattern, why in LINT.items():
                for m in re.finditer(pattern, text):
                    out.append(Problem("lint", where, f"{field_name} says {m.group(0)!r}: {why}"))
    return out


def public_problems(text: str) -> list[Problem]:
    """Nothing private in the file's text, its comments included."""
    out = []
    for pattern, why in PUBLIC.items():
        for m in re.finditer(pattern, text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(Problem("public", f"line {line}", f"{m.group(0)!r}: {why}"))
    return out


def switch_source(switch: dict[str, Any], switches: dict[tuple[str, str], tuple[str, ...]]) -> str | None:
    """Recognize table-owned namespaces, including misspellings within them; suffix text is explanatory only."""
    key = switch.get("key", "").split(" ", 1)[0]
    block = key.split(".", 1)[0]
    if key.startswith("gates."):
        return GATE_SOURCE
    return SWITCH_SOURCE if block in {b for b, _ in switches} else None


def switch_problems(data: dict[str, Any], own: Owners) -> list[Problem]:
    out = []
    for e in data["systems"]:
        switch = e.get("switch")
        if not switch:
            continue
        source = switch_source(switch, own.string_switches)
        if source is None:
            if switch.get("default_evidence") in (GATE_SOURCE, SWITCH_SOURCE):
                out.append(Problem("default", e["id"], f"switch.key {switch['key']} is hand-kept, not owned by "
                                   "the cited code table; replace default_evidence with its hand-kept source"))
            continue
        key = switch["key"].split(" ", 1)[0]
        block, _, name = key.partition(".")
        allowed = own.string_switches.get((block, name)) if source == SWITCH_SOURCE else None
        if source == GATE_SOURCE:
            known = name in own.gate_defaults
            value = own.gate_defaults.get(name)
        else:
            known = allowed is not None
            value = allowed[0] if allowed else None
        if not known:
            out.append(Problem("default", e["id"], f"switch.key {key} is not in {source}; fix the key"))
            continue
        if not isinstance(value, (str, int, float, bool, type(None))):
            out.append(Problem("default", e["id"], f"{key} is not a scalar default in {source}; "
                                                 "do not claim it as a switch"))
            continue
        if switch.get("default") != str(value):
            out.append(Problem("default", e["id"], f"switch.default for {key} must be {str(value)!r} from {source}"))
        if switch.get("default_evidence") != source:
            out.append(Problem("default", e["id"], f"switch.default_evidence for {key} must be {source}, "
                                                 "not a line cite"))
        if allowed and len(allowed) == 2 and {"off", "disabled"} & set(allowed):
            on = value not in ("off", "disabled")
            if e["state"]["on_by_default"] is not on:
                out.append(Problem("on_by_default", e["id"], f"state.on_by_default for {key} must be {on} "
                                                            f"from {source}"))
    return out


def wired_problems(data: dict[str, Any], own: Owners) -> list[Problem]:
    out = []
    for e in data["systems"]:
        for claim in e["state"]["wired"]:
            if claim in HAND_WIRED:
                continue
            prefix, _, name = claim.partition(":")
            family = WIRED_RECORDS.get(prefix)
            if family is None:
                out.append(Problem("wired", e["id"], f"unknown wired claim {claim!r}; use cli:, dashboard:, tool:, "
                                                    "lead_text or pack"))
            elif f"{family}:{name}" not in own.records:
                out.append(Problem("wired", e["id"], f"wired {claim!r} has no {family}:{name} reference record; "
                                                    "correct or remove the claim"))
    return out


def stale_slice_problems(data: dict[str, Any], own: Owners) -> list[Problem]:
    return [Problem("stale_slice", e["id"], f"remaining slice {s['slice']!r} names closed row {s['row']}; "
                    "remove completed work or re-point work still owed to its open row or 'row owed'")
            for e in data["systems"] for s in e["remaining"]
            if s["row"] in own.rows - own.open_rows and not HOLD_RE.match(s["row"])]


def signoff_problems(data: dict[str, Any]) -> list[Problem]:
    """on_and_used carries the operator's sign-off, and only on_and_used does (the operator, 2026-11-10). The words
    are reviewed, not authenticated, as the allowance's are."""
    out = []
    for e in data["systems"]:
        state, signed = e["state"]["board_state"], "signoff" in e
        if state == SIGNED and not signed:
            out.append(Problem("signoff", e["id"], f"{e['id']} is {SIGNED} with no sign-off on record: add signoff "
                               f"with the operator's date and words, or move it to {AWAITING}"))
        elif signed and state != SIGNED:
            out.append(Problem("signoff", e["id"], f"{e['id']} carries a sign-off but is {state}: a sign-off belongs "
                               f"to {SIGNED} only, so move it there or remove the sign-off"))
    return out


def lag_problems(data: dict[str, Any]) -> list[Problem]:
    """A system with no own slices left has left the building states, unless it is frozen, cut or kept (the operator,
    2026-11-10): the pull request that lands a system's last slice moves its state in the same pull request."""
    return [Problem("lag", e["id"], f"{e['id']} has no own slices left but is still {e['state']['board_state']}: move "
                    f"it to {AWAITING}, or to {SIGNED} with the operator's sign-off")
            for e in data["systems"]
            if e["state"]["board_state"] in BUILDING and e["recommendation"] not in NOT_COUNTED
            and not own_slices(e, data)]


def limit_problems(data: dict[str, Any]) -> list[Problem]:
    """No count above N without the operator's covering allowance; a recovered count cannot retain that allowance.
    The words and any extra conditions they state are reviewed by the operator/Lead, not verified by this tool."""
    ids, limit = counted_systems(data), data["wip_limit"]
    allowance = data.get("wip_allowance")
    if len(ids) <= limit:
        return ([Problem("allowance", "wip_allowance", "stale at or under wip_limit: remove the allowance and render")]
                if allowance is not None else [])
    if allowance is not None and len(ids) <= allowance["count"]:
        return []
    ceiling = (f"the operator's allowance of {allowance['count']} (wip_limit {limit})" if allowance is not None
               else f"wip_limit {limit}")
    remedy = "a revised" if allowance is not None else "a covering"
    return [Problem("wip", "file", f"limit's count {len(ids)} exceeds {ceiling}: {', '.join(ids)}; "
                    f"finish or freeze work, or obtain {remedy} operator wip_allowance, then render")]


# Keys, titles, and membership rules live together. View 3 deliberately overlaps the partition.
VIEWS = (
    ("soon", "Finish and switch on soon", lambda e, n: e["recommendation"] == "switch_on"
     or (e["recommendation"] == "finish" and n <= 2)),
    ("more", "Finish, with more to build", lambda e, n: e["recommendation"] == "finish" and n > 2),
    ("questions", "The operator's open questions", lambda e, n: e["decision"] != "none"
     and not e["decision"].startswith("decided:")),
    ("done", "Done", lambda e, n: e["recommendation"] == "done"),
    ("not_counted", "Not counted", lambda e, n: e["recommendation"] in NOT_COUNTED),
)


def counted_systems(data: dict[str, Any]) -> list[str]:
    """FORMAT.md rule 1's count, computed once and enforced by limit_problems. A system awaiting the operator's
    sign-off is not counted (the operator, 2026-11-10)."""
    return sorted(e["id"] for e in data["systems"]
                  if e["state"]["board_state"] in BUILDING and e["recommendation"] in ("finish", "switch_on"))


def priority(entry: dict[str, Any], order: dict[str, int]) -> int | None:
    return min((order[r] for r in entry["register"] if r in order), default=None)


def own_slices(entry: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    """A slice riding on another system's row is its owner's work, not this system's."""
    others = {r for e in data["systems"] if e["id"] != entry["id"] for r in e["register"]}
    return [s for s in entry["remaining"] if s["row"] not in others]


def views(data: dict[str, Any], order: dict[str, int]) -> dict[str, list[dict[str, Any]]]:
    ordered = sorted(data["systems"], key=lambda e: (priority(e, order) is None, priority(e, order), e["id"]))
    return {key: [e for e in ordered if rule(e, len(own_slices(e, data)))] for key, _, rule in VIEWS}


def _members(ids: list[str]) -> str:
    return f"{len(ids)} — {', '.join(ids) or 'none'}"


def _line(text: str) -> str:
    return " ".join(text.splitlines())


def declared_switch_source(switch: dict[str, Any]) -> str | None:
    """Render the evidence's declared provenance without importing any checkout's policy tables. switch_problems
    checks that the cited table really owns the key, including in planted trees with their own Owners tables."""
    evidence = switch.get("default_evidence")
    return evidence if evidence in (GATE_SOURCE, SWITCH_SOURCE) else None


def render_markdown(data: dict[str, Any], order: dict[str, int]) -> str:
    """Each field is one line, separated by blanks. A number shares its members' line so git cannot merge it stale."""
    out = ["# The systems build board", "Generated from [systems.yaml](systems.yaml). Do not edit; run "
           "`python tools/register.py render` (or `python tools/systems.py render`). Priority comes from "
           "[the register's Now list](future-work.md#1-now-the-milestones-and-the-gates-in-order). "
           "Count definition: FORMAT.md rule 1. Switch defaults are checked against the code's tables; board_state "
           "and built remain hand-kept. A PR that closes a row named in a slice, or changes what counts, re-runs "
           "`python tools/systems.py check` against current main before it merges (no merge queue).",
           "## Totals"]
    for state in ENUMS[("state", "board_state")]:
        ids = sorted(e["id"] for e in data["systems"] if e["state"]["board_state"] == state)
        out.append(f"**{state}{f' ({AWAITING_LABEL})' if state == AWAITING else ''}:** {_members(ids)}")
    waiting = sorted(e["id"] for e in data["systems"] if e["state"]["board_state"] == AWAITING)
    out.append(f"**Waiting on your sign-off:** {_members(waiting)}")
    out.append(f"**Limit's count / wip_limit:** {len(counted_systems(data))} / {data['wip_limit']} — "
               f"{', '.join(counted_systems(data)) or 'none'}")
    allowance = data.get("wip_allowance")
    if allowance is not None:
        out.append(f"**Operator allowance:** up to {allowance['count']} — {_line(allowance['operator'])} — "
                   f"{allowance['date']} (only the cap and staleness are checked; "
                   "the words' conditions are not checked)")
    hand_switches = [e for e in data["systems"] if e.get("switch") and not declared_switch_source(e["switch"])]
    details = "; ".join(f"{e['id']}: {_line(e['switch']['key'])}" for e in hand_switches)
    out.append(f"**Switch defaults not read from the code:** {_members([e['id'] for e in hand_switches])}"
               + (f" — {details}" if details else ""))
    hand_wired = [e for e in data["systems"] if set(e["state"]["wired"]) & set(HAND_WIRED)]
    details = "; ".join(f"{e['id']}: {', '.join(w for w in e['state']['wired'] if w in HAND_WIRED)}"
                        for e in hand_wired)
    out.append(f"**Hand-kept wiring (no reference record):** {_members([e['id'] for e in hand_wired])}"
               + (f" — {details}" if details else ""))
    selected = views(data, order)
    for key, title, _ in VIEWS:
        entries = selected[key]
        out += [f"## {title}", f"**Members:** {_members([e['id'] for e in entries])}"]
        if key == "questions":
            decided = sorted(e["id"] for e in data["systems"] if e["decision"].startswith("decided:"))
            out.append(f"**Decided:** {_members(decided)}")
        for e in entries:
            sid, name = e["id"], _line(e["name"])
            if key == "not_counted":
                out.append(f"**{sid} — {name}:** {e['recommendation']}")
                continue
            out.append(f"### {sid} — {name}")
            if key in ("soon", "more"):
                number = priority(e, order)
                out += [f"**Board state:** {e['state']['board_state']}", f"**Who:** {_line(e['who'])}",
                        f"**Now:** {number if number is not None else 'not on the Now list'}"]
                slices = own_slices(e, data)
                next_slice = (f"{_line(slices[0]['slice'])} — {slices[0]['row']} — {_line(slices[0]['estimate'])}"
                              if slices else "none")
                slice_members = "; ".join(f"{_line(s['slice'])} ({s['row']})" for s in slices) or "none"
                out.append(f"**Own slices left:** {len(slices)} — {slice_members} — **Next:** {next_slice}")
                if e.get("switch"):
                    source = declared_switch_source(e["switch"])
                    provenance = f"checked against {source}" if source else "not read from the code"
                    out.append(f"**Switch:** {_line(e['switch']['key'])} — default: "
                               f"{_line(e['switch'].get('default', 'not stated'))} — {provenance}")
                out.append("**Wired:** " + (", ".join(e["state"]["wired"]) or "none"))
            elif key == "questions":
                out.append(f"**Decision:** {_line(e['decision'])}")
    return "\n\n".join(out) + "\n"


def read_board(root: Path) -> dict[str, Any]:
    try:
        data = load((root / SYSTEMS).read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemsError(f"{SYSTEMS} cannot be read: {exc}") from exc
    invalid = schema_problems(data)
    if invalid:
        raise SystemsError("; ".join(map(str, invalid)))
    return data


def render(root: Path = ROOT) -> None:
    text = render_markdown(read_board(root), now_order(root))
    (root / MARKDOWN).write_text(text, encoding="utf-8", newline="\n")


def rendered_problems(root: Path, data: dict[str, Any], order: dict[str, int]) -> list[Problem]:
    try:
        actual = (root / MARKDOWN).read_bytes()
    except FileNotFoundError:
        actual = None
    if actual != render_markdown(data, order).encode("utf-8"):
        return [Problem("rendered", MARKDOWN, "missing or stale: run `python tools/systems.py render`")]
    return []


def show(sid: str, root: Path = ROOT) -> str | None:
    data = read_board(root)
    entry = next((e for e in data["systems"] if e["id"] == sid), None)
    if entry is None:
        return None
    return yaml.safe_dump({**entry, "priority": priority(entry, now_order(root))}, sort_keys=False,
                          allow_unicode=True)


def problems(text: str, own: Owners) -> list[Problem]:
    """Every problem of the file's text against its owners, in a stable order."""
    data = load(text)
    found = (schema_problems(data) + generated_problems(data) + existence_problems(data, own)
             + dependency_problems(data) + owner_problems(data) + reverse_problems(data, own) + hold_problems(data, own)
              + lint_problems(data) + public_problems(text))
    if not schema_problems(data):
        found += switch_problems(data, own) + wired_problems(data, own) + stale_slice_problems(data, own)
        found += limit_problems(data) + signoff_problems(data) + lag_problems(data)
        found += rendered_problems(own.root, data, own.now_order)
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
    ap.add_argument("command", choices=("check", "render", "show"))
    ap.add_argument("id", nargs="?", help="show: the system's id (SYS-NN)")
    args = ap.parse_args(argv)
    if (args.command == "show") != (args.id is not None):
        ap.error("only show takes one system id")
    try:
        if args.command == "render":
            render()
            print(f"rendered {MARKDOWN}")
            return 0
        if args.command == "show":
            shown = show(args.id)
            if shown is None:
                print(f"unknown system id: {args.id}", file=sys.stderr)
                return 1
            print(shown, end="")
            return 0
        found = check()
    except SystemsError as exc:
        print(f"cannot {args.command} {SYSTEMS}: {exc}", file=sys.stderr)
        return 2
    if found:
        print("\n".join(map(str, found)), file=sys.stderr)
        print(f"{len(found)} problem(s) in {SYSTEMS}", file=sys.stderr)
        return 1
    print(f"{SYSTEMS} holds to its owners")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
