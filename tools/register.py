#!/usr/bin/env python3
"""The future-work register as structured data (register E30; architecture review §9).

``docs/implementation/future-work.yaml`` is the source: the register's preamble, its sections and every row as a
mapping from column name to cell text. ``docs/implementation/future-work.md`` is the rendered view, regenerated from
the YAML by this tool and kept identical to it by ``tests/unit/test_register.py``. Readers, the ledger's tests and the
dashboard keep reading the markdown; triage tooling reads the YAML.

    python tools/register.py render            # normalize the YAML (§Closed in id order), rewrite future-work.md
    python tools/register.py check             # exit 1 if either file is not what render would write
    python tools/register.py resolve           # after a merge stopped on the register: re-merge the YAML, render
    python tools/register.py import            # rebuild future-work.yaml from future-work.md
    python tools/register.py summary           # open rows by section and target
    python tools/register.py due               # print the decisions-due view

**Decisions due.** ``docs/implementation/decisions-due.yaml`` lists what the operator or the designer still owes the
register: each item names its register row, what is needed (a decision, a design, or the adoption of one), its owner,
the point it is due by (``DUE_ORDER``) and the rows it blocks. ``render`` writes ``decisions-due.md`` from it, soonest
first, with the blocked rows beside what they wait for. ``check`` keeps it current: an item whose row or blocked row
has closed is stale; one row has at most one item; every open question (§4) must have its own item, and every open row
targeted **Designer** must have one or be blocked by one (it then waits for that item's decision).

The markdown gives every row its own block, never a table line: a ``### <id>`` heading (the row's first cell), then
one paragraph per non-empty cell, ``**<column>:** <text>``, each between blank lines. Each section names its columns in
an HTML comment (``<!-- columns: # | Work | ... -->``, invisible on GitHub) so the page parses back to the YAML. A cell
never holds a blank line, which would end its paragraph (``problems`` reports one). Rows are kept exactly as written:
the YAML holds text, not interpretation; a row's id is its first cell and its target is read from the column named in
``target_column``.

Merges. Git's three-way merge conflicts where two changes touch the same or neighbouring lines, and merges them when
at least one unchanged line lies between. A table put each row on one line, so changes to neighbouring rows always
conflicted in the markdown even when the YAML merged cleanly (PR #142 against main, 2026-10-09). Now a row's heading
and the blank lines around it separate it from its neighbours on the page, and in both YAML files a blank line follows
every row and every item (``dump``), so changes to different rows merge in all four files, including a row added
next to a row that another change edits, and GitHub's merge button (which runs no local merge driver) sees no conflict
(``tests/unit/test_docs_merge.py`` proves it with real merges). The exception is two insertions at one place, which
git conflicts on whatever the layout: two rows closed into the same gap of §Closed's id order (nothing closed sorts
between F15.2 and F15.3, say), two new rows appended at one place (both took the next free id, which they must settle
anyway), two new decisions-due items in one (due, row) gap. ``resolve`` settles all of these with one command. The
files also keep nothing that every change edits: the preamble carries no per-change log (the history is ``git log`` on
the YAML; each row carries its own dates), and §Closed is kept in id order rather than closing order, so closings in
different gaps insert at different places; ``decisions-due.yaml`` is kept the same way, in (due, row) order, and two
branches that add an item for the same row at different due points merge into a duplicate that ``check`` refuses.
After every sync with main run ``render``, conflict or not: a clean merge can still leave §Closed or the items
unsorted and the markdown stale, which only ``check`` (CI) catches. When a merge does conflict, run ``resolve``: it
merges the YAML again from its three sides row by row and cell by cell (not line by line), and renders, so only the
same cell changed on both sides is left, marked in the YAML. The markdown is derived and is never merged by hand.
"""

from __future__ import annotations

import argparse
import copy
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "implementation" / "future-work.md"
YAML = ROOT / "docs" / "implementation" / "future-work.yaml"
DUE_YAML = ROOT / "docs" / "implementation" / "decisions-due.yaml"
DUE_MD = ROOT / "docs" / "implementation" / "decisions-due.md"
DUE_SCHEMA = "aew/decisions-due/v1"
# The points a decision can be due by, soonest first: the gates and M4 phases in their order (docs/README.md), then the
# later milestones and the register's open-ended targets.
DUE_ORDER = ("M4-D", "Gate: before F15.2 ships", "M4-E", "M4-F", "M4-G", "M4-H", "M4", "Gate: before internal alpha",
             "M5", "M6", "Evaluation", "Unscheduled")
NEEDS = ("decision", "design", "adoption")
OWNERS = ("operator", "designer", "operator and designer")
SCHEMA = "aew/register/v1"
TARGETS = ("Gate", "M4", "M5", "M6", "Hierarchy revision", "M4 candidate", "Designer", "Evaluation",
           "On measured need", "Unscheduled")
TARGET_RE = re.compile(r"^\*\*(Gate: [^*]+|M4|M5|M6|Hierarchy revision|M4 candidate|Designer|Evaluation|"
                       r"On measured need|Unscheduled)")
SECTION_RE = re.compile(r"^## (\d+)\. (.+)$")
COLUMNS_RE = re.compile(r"^<!-- columns: (.+) -->$")
ROW_RE = re.compile(r"^### (.+)$")
BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
ID_RE = re.compile(r"^[A-Z][0-9]+(?:\.[0-9]+)?$")
ID_KEY_RE = re.compile(r"^([A-Z]+)([0-9]+)((?:\.[0-9]+)*)")
CHANGELOG_RE = re.compile(r"\*?Last updated:", re.IGNORECASE)


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    if "\n" in value:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_Dumper.add_representer(str, _str)


# ------------------------------------------------------------------------------------------------------- import

def _field(line: str, columns: list[str]) -> tuple[str, str] | None:
    """The cell a ``**<column>:** <text>`` paragraph opens, if its column is one of ``columns``."""
    for column in columns:
        prefix = f"**{column}:** "
        if line.startswith(prefix):
            return column, line[len(prefix):]
    return None


def _skip_blank(lines: list[str], i: int) -> int:
    while i < len(lines) and not lines[i]:
        i += 1
    return i


def parse_markdown(text: str) -> dict[str, Any]:
    """The YAML's data from the rendered page: the inverse of ``render_markdown``."""
    lines = text.split("\n")
    first = next(i for i, ln in enumerate(lines) if SECTION_RE.match(ln))
    title = lines[0].removeprefix("# ")
    preamble = "\n".join(lines[1:first]).strip("\n")
    sections: list[dict[str, Any]] = []
    i = first
    while i < len(lines):
        m = SECTION_RE.match(lines[i])
        assert m, lines[i]
        number, heading = int(m.group(1)), m.group(2)
        i += 1
        intro: list[str] = []
        while not (cols := COLUMNS_RE.match(lines[i])):
            assert not SECTION_RE.match(lines[i]), f"§{number} has no columns comment"
            intro.append(lines[i])
            i += 1
        columns = [c.strip() for c in cols.group(1).split(" | ")]
        i += 1
        rows: list[dict[str, str]] = []
        while (j := _skip_blank(lines, i)) < len(lines) and (head := ROW_RE.match(lines[j])):
            row = {c: "" for c in columns} | {columns[0]: head.group(1)}
            i, rest = j + 1, columns[1:]
            # each cell is a paragraph, in column order; an empty cell has none
            while (j := _skip_blank(lines, i)) < len(lines) and (found := _field(lines[j], rest)):
                column, value = found
                j += 1
                while j < len(lines) and lines[j]:  # a cell written over several lines
                    value += "\n" + lines[j]
                    j += 1
                row[column] = value
                i, rest = j, rest[rest.index(column) + 1:]
            rows.append(row)
        trailing: list[str] = []
        while i < len(lines) and not SECTION_RE.match(lines[i]):
            trailing.append(lines[i])
            i += 1
        section: dict[str, Any] = {"number": number, "title": heading, "columns": columns}
        intro_text = "\n".join(intro).strip("\n")
        if intro_text:
            section["intro"] = intro_text
        target_column = next((c for c in columns if c in ("Belongs to or gated by", "Target and notes", "When")),
                             None)
        if target_column:
            section["target_column"] = target_column
        section["rows"] = rows
        trailing_text = "\n".join(trailing).strip("\n")
        if trailing_text:
            section["after"] = trailing_text
        sections.append(section)
    return {"schema": SCHEMA, "title": title, "preamble": preamble, "sections": sections}


# ------------------------------------------------------------------------------------------------------- render

def render_markdown(data: dict[str, Any]) -> str:
    """The page: each row a ``### <first cell>`` heading and one paragraph per non-empty cell, blank lines between,
    so no line of one row touches a line of another (the module's *Merges*)."""
    out = [f"# {data['title']}", "", data["preamble"], ""]
    for section in data["sections"]:
        out += [f"## {section['number']}. {section['title']}", ""]
        if section.get("intro"):
            out += [section["intro"], ""]
        columns = section["columns"]
        out += [f"<!-- columns: {' | '.join(columns)} -->", ""]
        for row in section["rows"]:
            out += [f"### {row[columns[0]]}", ""]
            for column in columns[1:]:
                if row[column]:
                    out += [f"**{column}:** {row[column]}", ""]
        if section.get("after"):
            out += [section["after"], ""]
    text = "\n".join(out)
    return text.rstrip("\n") + "\n"


def load() -> dict[str, Any]:
    return yaml.safe_load(YAML.read_text(encoding="utf-8"))


def dump(data: dict[str, Any]) -> str:
    return _apart(yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=118))


# The block sequences whose entries ``_apart`` separates: the register's rows (``  rows:``, entries ``  - ``, their
# lines indented further) and the decisions-due items (``items:``, entries ``- ``).
_LISTS = {"  rows:": "  - ", "items:": "- "}


def _apart(text: str) -> str:
    """A blank line after every row of the register and every decisions-due item, as on the page: without one, the last
    line of a row touches the first line of whatever follows, so a row added after a row that another change edits
    conflicts in the YAML (the module's *Merges*). YAML reads the blank line as nothing."""
    out: list[str] = []
    entry: str | None = None
    for line in text.split("\n"):
        if entry is not None and line and not line.startswith((entry, " " * len(entry))):
            entry = None  # a line indented less than the entries ends the list, after a blank line
            out.append("")
        if entry is not None and line.startswith(entry) and out[-1] not in _LISTS:
            out.append("")
        out.append(line)
        entry = _LISTS.get(line, entry)
    if entry is not None:  # the file ends in the list: its last entry is followed by a blank line too
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------------- order

def id_key(value: str) -> tuple[Any, ...]:
    """The natural order of a row id: its letters, then each numeric part as a number, then any suffix. So ``E8`` <
    ``E10``, ``F20`` < ``F20.1`` < ``F20.2``, and ``Q9 (decisions)`` sorts with ``Q9``."""
    m = ID_KEY_RE.match(value)
    if m is None:
        return (1, value)
    parts = tuple(int(x) for x in m.group(3).split(".") if x)
    return (0, m.group(1), int(m.group(2)), parts, value[m.end():])


def closed_order(section: dict[str, Any]) -> list[dict[str, Any]]:
    """§Closed as it is kept: the ``Gate`` rows first, in the order they closed, then every id in natural order. A row
    closed today lands next to its neighbours by id, not at the end where every other change also appends."""
    gates = [r for r in section["rows"] if next(iter(r.values())) == "Gate"]
    if "Closed" in section["columns"]:
        gates.sort(key=lambda r: r["Closed"])
    others = sorted((r for r in section["rows"] if next(iter(r.values())) != "Gate"),
                    key=lambda r: id_key(next(iter(r.values()))))
    return gates + others


def _settled(value: Any) -> Any:
    """A cell or field without trailing newlines. A YAML literal block (``Notes: |``) ends in one, which the page
    cannot carry (its paragraph ends there), and two or more make ``dump`` write a keep-chomping scalar that grows by
    one newline on every ``render`` (review of PR #151, 4)."""
    return value.rstrip("\n") if isinstance(value, str) else value


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    """The data as ``render`` writes it: no cell ends in a newline, and every Closed section is in ``closed_order``."""
    for section in data["sections"]:
        section["rows"] = [{column: _settled(cell) for column, cell in row.items()} for row in section["rows"]]
        if section["title"].startswith("Closed"):
            section["rows"] = closed_order(section)
    return data


# ------------------------------------------------------------------------------------------------------- queries

def rows(data: dict[str, Any], *, open_only: bool = True) -> list[dict[str, Any]]:
    """Every row with its section, id and target (the bold prefix of the target column, or None)."""
    found = []
    for section in data["sections"]:
        if open_only and section["title"].startswith("Closed"):
            continue
        tcol = section.get("target_column")
        for row in section["rows"]:
            first = next(iter(row.values()))
            m = TARGET_RE.match(row[tcol]) if tcol else None
            found.append({"section": section["number"], "id": first if ID_RE.match(first) or first == "Gate" else None,
                          "target": m.group(1) if m else None, "row": row})
    return found


def problems(data: dict[str, Any]) -> list[str]:
    """What a consumer would stumble on: duplicate ids, open rows without a recognised target."""
    out = []
    ids = Counter(r["id"] for r in rows(data, open_only=False) if r["id"] and r["id"] != "Gate")
    out += [f"id {i} appears {n} times" for i, n in sorted(ids.items()) if n > 1]
    for r in rows(data):
        if r["section"] not in (1, 4) and r["target"] is None:
            out.append(f"§{r['section']} {r['id'] or '?'}: its target column does not start with a bold target")
    for section in data["sections"]:
        for row in section["rows"]:
            first = next(iter(row.values()))
            if not first.strip() or "\n" in first:
                out.append(f"§{section['number']}: a row's first cell is its heading, so it is one non-empty line: "
                           f"{first[:40]!r}")
            out += [f"§{section['number']} {first[:20]}: its {column} holds a blank line, which would end its paragraph"
                    for column, value in row.items() if BLANK_LINE_RE.search(value)]
        if section["title"].startswith("Closed") and section["rows"] != closed_order(section):
            out.append(f"§{section['number']} {section['title']} is not in id order (run `python tools/register.py "
                       "render`): rows appended in closing order collide on every merge")
    if CHANGELOG_RE.search(data["preamble"]):
        out.append("the preamble carries a 'Last updated' change log: every change edits that line, so every pair of "
                   "changes conflicts; the history is `git log` on the YAML and each row's own dates")
    return out


def summary(data: dict[str, Any]) -> str:
    lines = []
    for section in data["sections"]:
        if section["title"].startswith("Closed"):
            continue
        these = [r for r in rows(data) if r["section"] == section["number"]]
        counts = Counter(r["target"] or "(none)" for r in these)
        lines.append(f"§{section['number']} {section['title']}: {len(these)} rows; "
                     + ", ".join(f"{t} {n}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------------- decisions due

def load_due() -> dict[str, Any]:
    return yaml.safe_load(DUE_YAML.read_text(encoding="utf-8"))


def due_key(item: dict[str, Any]) -> tuple[Any, ...]:
    """Items are kept soonest first, then by row id, in the YAML as on the page: a new item lands among its neighbours,
    not at the end where every other change also appends (the register's merge rule)."""
    due = item.get("due")
    return (DUE_ORDER.index(due) if due in DUE_ORDER else len(DUE_ORDER), id_key(str(item.get("row") or "")))


def normalize_due(due: dict[str, Any]) -> dict[str, Any]:
    """The items as ``render`` writes them: in (due, row) order, no field ending in a newline."""
    due["items"] = sorted(({k: _settled(v) for k, v in item.items()} for item in due.get("items") or []), key=due_key)
    return due


def due_problems(data: dict[str, Any], due: dict[str, Any]) -> list[str]:
    """Why the decisions-due list no longer matches the register: an item on a closed or unknown row, a blocked row that
    closed, a field outside its vocabulary, two items for one row, items out of order, an open question with no item of
    its own, or a **Designer** row that neither has an item nor is blocked by one."""
    out: list[str] = []
    if due.get("schema") != DUE_SCHEMA:
        out.append(f"{DUE_YAML.name}: schema is not {DUE_SCHEMA}")
    open_ids = {r["id"] for r in rows(data) if r["id"]}
    all_ids = {r["id"] for r in rows(data, open_only=False) if r["id"]}
    own: Counter[str] = Counter()
    blocked_by_an_item: set[str] = set()
    items = due.get("items") or []
    if items != sorted(items, key=due_key):
        out.append(f"{DUE_YAML.name} is not in (due, row) order: run `python tools/register.py render`")
    for n, item in enumerate(items, 1):
        where = f"{DUE_YAML.name} item {n} ({item.get('row', '?')})"
        if item.get("row"):
            own[item["row"]] += 1  # an incomplete item is still that row's item (review of PR #104, B)
        missing = [k for k in ("row", "needs", "owner", "due", "what") if not item.get(k)]
        if missing:
            out.append(f"{where}: missing {', '.join(missing)}")
            continue
        if item["row"] not in open_ids:
            out.append(f"{where}: register row {item['row']} is " + ("closed: remove the item, or reopen the row"
                       if item["row"] in all_ids else "not in the register"))
        for blocked in item.get("blocks") or []:
            if blocked not in open_ids:
                out.append(f"{where}: blocks {blocked}, which is " + ("closed" if blocked in all_ids else "not in the "
                           "register"))
        if item["needs"] not in NEEDS:
            out.append(f"{where}: needs is one of {', '.join(NEEDS)}")
        if item["owner"] not in OWNERS:
            out.append(f"{where}: owner is one of {', '.join(OWNERS)}")
        if item["due"] not in DUE_ORDER:
            out.append(f"{where}: due is one of {', '.join(DUE_ORDER)}")
        blocked_by_an_item |= set(item.get("blocks") or [])
    out += [f"{DUE_YAML.name}: {row} has {n} items; one row, one item" for row, n in sorted(own.items()) if n > 1]
    for r in rows(data):
        if not r["id"] or r["id"] in own:
            continue
        if r["section"] == 4:
            out.append(f"register {r['id']} is an open question with no item of its own in {DUE_YAML.name}")
        elif r["target"] == "Designer" and r["id"] not in blocked_by_an_item:
            out.append(f"register {r['id']} waits for the designer (**Designer**) but has no item in {DUE_YAML.name}, "
                       "and no item blocks it")
    return out


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "/")


def render_due(due: dict[str, Any]) -> str:
    """The decisions-due view: what is owed, by whom and by when, soonest first; then each blocked row and what it
    waits for."""
    items = sorted(due.get("items") or [], key=due_key)
    out = ["# Decisions due", "",
           "*Generated by `python tools/register.py render` from `decisions-due.yaml`; edit the YAML, never this page. "
           "Each item points to its row in the [future-work register](future-work.md), which holds the detail.*", "",
           str(due.get("intro") or "").strip(), "",
           "## Owed, soonest first", ""]
    for i in items:  # one block per item, like the register's rows, so changes to different items merge
        out += [f"### {i.get('row')}", "",
                f"**Due by:** {i.get('due')} · **Owner:** {i.get('owner')} · **Needs:** {i.get('needs')}", "",
                f"**What:** {_cell(i.get('what', ''))}", "",
                f"**Blocks:** {', '.join(i.get('blocks') or []) or '-'}", ""]
    blocked: dict[str, list[str]] = {}
    for i in items:
        for row in i.get("blocks") or []:
            blocked.setdefault(row, []).append(
                f"{i.get('row')} ({i.get('needs')}, {i.get('owner')}, by {i.get('due')})")
    out += ["## Blocked until then", ""]
    for row in sorted(blocked, key=id_key):
        out += [f"- **{row}** waits for {'; '.join(blocked[row])}", ""]
    return "\n".join(out).rstrip("\n") + "\n"


# ------------------------------------------------------------------------------------------------------- files

def _paths(root: Path) -> tuple[Path, Path, Path, Path]:
    """The register's YAML and page, then the decisions-due YAML and page, in the checkout at ``root``."""
    return tuple(root / p.relative_to(ROOT) for p in (YAML, MD, DUE_YAML, DUE_MD))  # type: ignore[return-value]


def render(root: Path = ROOT) -> None:
    """Normalize both YAML files and write both pages from them."""
    yaml_path, md, due_yaml, due_md = _paths(root)
    data = normalize(yaml.safe_load(yaml_path.read_text(encoding="utf-8")))
    due = normalize_due(yaml.safe_load(due_yaml.read_text(encoding="utf-8")))
    for path, text in ((due_yaml, dump(due)), (yaml_path, dump(data))):
        if text != path.read_text(encoding="utf-8"):
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"normalized {path.relative_to(root)}")
    due_md.write_text(render_due(due), encoding="utf-8", newline="\n")
    md.write_text(render_markdown(data), encoding="utf-8", newline="\n")
    print(f"rendered {md.relative_to(root)}")


# ------------------------------------------------------------------------------------------------------- resolve

def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


_ABSENT: Any = object()  # a key or row one side does not have
# The lists merged entry by entry, and what identifies an entry: a section by its number, a row by its first cell (its
# id), a decisions-due item by its row. Every other list (columns, blocks) is one value.
_KEYED: dict[str, Any] = {"sections": lambda s: s.get("number"), "rows": lambda r: next(iter(r.values()), None),
                          "items": lambda i: i.get("row")}
_MARKER_RE = re.compile(r"^(<{7}|>{7})( |$)|^={7}$", re.M)


def _keys(entries: list[Any], key: Any) -> list[tuple[Any, int]]:
    """Each entry's key with its occurrence, so the repeated first cells (``Gate``, a gate's name) stay apart."""
    seen: Counter[Any] = Counter()
    out = []
    for entry in entries:
        k = key(entry) if isinstance(entry, dict) else repr(entry)
        out.append((k, seen[k]))
        seen[k] += 1
    return out


def _merge3(base: Any, ours: Any, theirs: Any, where: str, conflicts: list[str], field: str = "") -> tuple[Any, ...]:
    """A three-way merge of the register's data, by key rather than by line: the merged value as each side should see
    it, ``(ours, base, theirs)``. The three agree wherever the merge is clean; where both sides changed the same value
    differently they keep their own, and ``where`` is recorded in ``conflicts``. Mappings merge key by key (a row cell
    by cell), the keyed lists entry by entry, so two rows closed into the same gap of §Closed, or added to the same
    place, are two independent entries; normalizing afterwards puts them in order."""
    if ours == theirs:
        return ours, ours, ours
    if ours == base:
        return theirs, theirs, theirs
    if theirs == base:
        return ours, ours, ours
    if isinstance(ours, dict) and isinstance(theirs, dict) and (base is _ABSENT or isinstance(base, dict)):
        b = {} if base is _ABSENT else base
        views: tuple[dict[str, Any], ...] = ({}, {}, {})
        for k in [*ours, *(k for k in theirs if k not in ours), *(k for k in b if k not in ours and k not in theirs)]:
            merged = _merge3(b.get(k, _ABSENT), ours.get(k, _ABSENT), theirs.get(k, _ABSENT), f"{where} {k}".strip(),
                             conflicts, k)
            for view, value in zip(views, merged, strict=True):
                if value is not _ABSENT:
                    view[k] = value
        return views
    if field in _KEYED and all(isinstance(v, list) for v in (base, ours, theirs)):
        key = _KEYED[field]
        b, o, t = ({k: e for k, e in zip(_keys(side, key), side, strict=True)} for side in (base, ours, theirs))
        order = list(o)
        for i, k in enumerate(t):  # an entry only theirs has goes after its predecessor there
            if k not in order:
                before = next((p for p in reversed(list(t)[:i]) if p in order), None)
                order.insert(order.index(before) + 1 if before is not None else 0, k)
        order += [k for k in b if k not in order]
        views_l: tuple[list[Any], ...] = ([], [], [])
        for k in order:
            name = k[0] if not k[1] else f"{k[0]} ({k[1] + 1})"
            merged = _merge3(b.get(k, _ABSENT), o.get(k, _ABSENT), t.get(k, _ABSENT), f"{where} {name}", conflicts)
            for view, value in zip(views_l, merged, strict=True):
                if value is not _ABSENT:
                    view.append(value)
        return views_l
    conflicts.append(where or "the whole file")
    return ours, base, theirs


def merge_data(base: Any, ours: Any, theirs: Any, canonical: Any) -> tuple[str | None, list[str], tuple[str, ...]]:
    """The merged YAML text when the sides merge cleanly by key, else None with the conflicts, and the three views'
    canonical texts (each side's own value only where it conflicts) for a text merge that marks just those."""
    conflicts: list[str] = []
    views = _merge3(base if base is not None else _ABSENT, ours, theirs, "", conflicts)
    texts = tuple(canonical(copy.deepcopy(v)) for v in views)
    return (None if conflicts else texts[0]), conflicts, texts


def _in_progress(root: Path) -> bool:
    return any(_git(root, "rev-parse", "-q", "--verify", ref).returncode == 0
               for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD"))


def resolve(root: Path = ROOT) -> int:
    """Finish a merge that stopped on the register. Each YAML file still in conflict is merged again from its three
    sides (the merge base, ours and theirs) by key (``_merge3``): rows and items added, changed or closed on one side
    apply, cell by cell, wherever they land, so the conflicts git reports for two insertions at one place (two rows
    closed into the same gap of §Closed, say) and for layout or order go away. Then both pages are rendered. Only a
    real conflict, the same cell or field changed differently on both sides, stays: marked in the YAML, with nothing
    else marked, to fix by hand before ``render``. The pages are never merged: they are rendered.

    It refuses outside a merge (or a cherry-pick, revert or rebase), and it never overwrites a resolution: a conflicted
    YAML file with no conflict markers left was resolved by hand, and is kept."""
    if not _in_progress(root):
        print("no merge in progress: `resolve` finishes a merge that stopped on the register; outside one, use "
              "`python tools/register.py render`", file=sys.stderr)
        return 2
    yaml_path, _, due_yaml, _ = _paths(root)
    left = 0
    for path, canonical in ((yaml_path, lambda d: dump(normalize(d))), (due_yaml, lambda d: dump(normalize_due(d)))):
        rel = path.relative_to(root).as_posix()
        ours, base, theirs = (_git(root, "show", f":{stage}:{rel}") for stage in (2, 1, 3))
        if ours.returncode or theirs.returncode:
            continue  # not in conflict
        if path.exists() and not _MARKER_RE.search(path.read_text(encoding="utf-8")):
            print(f"{rel}: already resolved (no conflict markers), kept: `git add` it once it is right")
            continue
        try:
            sides = [yaml.safe_load(s.stdout) if s.returncode == 0 else None for s in (base, ours, theirs)]
        except yaml.YAMLError as e:
            print(f"{rel}: a side is not valid YAML, nothing written: {e}", file=sys.stderr)
            return 2
        text, conflicts, views = merge_data(*sides, canonical=canonical)
        if text is None:
            with tempfile.TemporaryDirectory() as tmp:
                files = [Path(tmp) / name for name in ("ours", "base", "theirs")]
                for f, view in zip(files, views, strict=True):
                    f.write_text(view, encoding="utf-8", newline="\n")
                merged = _git(root, "merge-file", "-p", "-L", "ours", "-L", "base", "-L", "theirs", *map(str, files))
            if merged.returncode < 0 or merged.returncode > 127 or not merged.stdout:  # 255: git failed, wrote nothing
                print(f"{rel}: git merge-file failed (exit {merged.returncode}), nothing written: "
                      f"{merged.stderr.strip()}", file=sys.stderr)
                return 2
            text = merged.stdout
            if merged.returncode:
                left += len(conflicts)
                print(f"{rel}: {len(conflicts)} conflict(s) left, marked: " + "; ".join(conflicts))
            else:  # the conflicting values differ on different lines of their text, which git merges line by line
                print(f"{rel}: merged (line by line within " + "; ".join(conflicts) + ")")
        else:
            print(f"{rel}: merged")
        path.write_text(text, encoding="utf-8", newline="\n")
    if left:
        print("fix the marked conflicts in the YAML, then run `python tools/register.py render`")
        return 1
    render(root)
    print("resolved: `git add` the register's YAML and pages, then commit the merge")
    return 0


# ------------------------------------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["render", "check", "resolve", "import", "summary", "due"])
    args = ap.parse_args(argv)
    if args.command == "import":
        data = parse_markdown(MD.read_text(encoding="utf-8"))
        YAML.write_text(dump(data), encoding="utf-8", newline="\n")
        rendered = render_markdown(yaml.safe_load(YAML.read_text(encoding="utf-8")))
        if rendered != MD.read_text(encoding="utf-8"):
            print("imported, but the YAML does not render back to the markdown byte for byte", file=sys.stderr)
            return 1
        print(f"imported {sum(len(s['rows']) for s in data['sections'])} rows into {YAML.relative_to(ROOT)}")
        return 0
    if args.command == "render":
        render()
        return 0
    if args.command == "resolve":
        return resolve()
    data = normalize(load())
    due = load_due()
    if args.command == "due":
        print(render_due(due), end="")
        return 0
    if args.command == "summary":
        print(summary(data))
        for p in problems(data) + due_problems(data, due):
            print("problem:", p)
        return 0
    ok = md_ok = render_markdown(data) == MD.read_text(encoding="utf-8")
    if not md_ok:  # each line names what is out of step, never the register for a decisions-due problem (PR #104, A)
        print(f"{MD.relative_to(ROOT)} differs from what {YAML.relative_to(ROOT)} renders")
    for problem in due_problems(data, due):  # first: a malformed item is named, not a crash in the renderer
        ok = False
        print("problem:", problem)
    if render_due(due) != DUE_MD.read_text(encoding="utf-8"):
        ok = False
        print(f"{DUE_MD.relative_to(ROOT)} differs from what {DUE_YAML.relative_to(ROOT)} renders")
    if dump(data) != YAML.read_text(encoding="utf-8"):
        ok = False
        print(f"{YAML.relative_to(ROOT)} is not normalized (§Closed in id order, canonical layout)")
    print("in sync" if ok else "run `python tools/register.py render`, and fix any problem it cannot")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
