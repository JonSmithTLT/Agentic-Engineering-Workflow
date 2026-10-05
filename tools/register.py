#!/usr/bin/env python3
"""The future-work register as structured data (register E30; architecture review §9).

``docs/implementation/future-work.yaml`` is the source: the register's preamble, its sections and every row as a
mapping from column name to cell text. ``docs/implementation/future-work.md`` is the rendered view, regenerated from
the YAML by this tool and kept identical to it by ``tests/unit/test_register.py``. Readers, the ledger's tests and the
dashboard keep reading the markdown; triage tooling reads the YAML.

    python tools/register.py render            # normalize the YAML (§Closed in id order), rewrite future-work.md
    python tools/register.py check             # exit 1 if either file is not what render would write
    python tools/register.py import            # one-time: parse future-work.md into future-work.yaml
    python tools/register.py summary           # open rows by section and target

The markdown is plain GitHub tables, one per section, with optional prose before the table. A cell never contains a
literal ``|`` (the table would break), so cells split on it. Rows are kept exactly as written: the YAML holds text,
not interpretation; a row's id is its first cell and its target is read from the column named in ``target_column``.

Merges. Two changes to the register collide only where they touch the same lines, so the file keeps nothing that
every change edits: the preamble carries no per-change log (the history is ``git log`` on the YAML; each row carries
its own dates), and §Closed is kept in id order rather than closing order, so two changes that close different
entries insert at different places. After every sync with main run ``render``, conflict or not: a clean merge can
still leave §Closed unsorted and the markdown stale, which only ``check`` (CI) catches. When a merge does conflict,
resolve the YAML only and run ``render``: the markdown is derived and is never merged by hand.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "docs" / "implementation" / "future-work.md"
YAML = ROOT / "docs" / "implementation" / "future-work.yaml"
SCHEMA = "aew/register/v1"
TARGETS = ("Gate", "M4", "M5", "M6", "Hierarchy revision", "M4 candidate", "Designer", "Evaluation",
           "On measured need", "Unscheduled")
TARGET_RE = re.compile(r"^\*\*(Gate: [^*]+|M4|M5|M6|Hierarchy revision|M4 candidate|Designer|Evaluation|"
                       r"On measured need|Unscheduled)")
SECTION_RE = re.compile(r"^## (\d+)\. (.+)$")
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

def _split_row(line: str) -> list[str]:
    assert line.startswith("| ") and line.endswith(" |"), line[:80]
    return [c.strip() for c in line[2:-2].split(" | ")]


def parse_markdown(text: str) -> dict[str, Any]:
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
        while i < len(lines) and not lines[i].startswith("|"):
            intro.append(lines[i])
            i += 1
        columns = _split_row(lines[i])
        assert re.fullmatch(r"\|(---\|)+", lines[i + 1]), lines[i + 1]
        i += 2
        rows: list[dict[str, str]] = []
        while i < len(lines) and lines[i].startswith("|"):
            cells = _split_row(lines[i])
            assert len(cells) == len(columns), f"§{number} row has {len(cells)} cells, not {len(columns)}: {cells[0]}"
            rows.append(dict(zip(columns, cells, strict=True)))
            i += 1
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
    out = [f"# {data['title']}", "", data["preamble"], ""]
    for section in data["sections"]:
        out += [f"## {section['number']}. {section['title']}", ""]
        if section.get("intro"):
            out += [section["intro"], ""]
        columns = section["columns"]
        out.append("| " + " | ".join(columns) + " |")
        out.append("|" + "---|" * len(columns))
        for row in section["rows"]:
            out.append("| " + " | ".join(row[c] for c in columns) + " |")
        out.append("")
        if section.get("after"):
            out += [section["after"], ""]
    text = "\n".join(out)
    return text.rstrip("\n") + "\n"


def load() -> dict[str, Any]:
    return yaml.safe_load(YAML.read_text(encoding="utf-8"))


def dump(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=118)


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


def normalize(data: dict[str, Any]) -> dict[str, Any]:
    """The data as ``render`` writes it: every Closed section in ``closed_order``."""
    for section in data["sections"]:
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


# ------------------------------------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["render", "check", "import", "summary"])
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
    data = normalize(load())
    if args.command == "render":
        text = dump(data)
        if text != YAML.read_text(encoding="utf-8"):
            YAML.write_text(text, encoding="utf-8", newline="\n")
            print(f"normalized {YAML.relative_to(ROOT)}")
        MD.write_text(render_markdown(data), encoding="utf-8", newline="\n")
        print(f"rendered {MD.relative_to(ROOT)}")
        return 0
    if args.command == "summary":
        print(summary(data))
        for p in problems(data):
            print("problem:", p)
        return 0
    ok = render_markdown(data) == MD.read_text(encoding="utf-8")
    if dump(data) != YAML.read_text(encoding="utf-8"):
        ok = False
        print(f"{YAML.relative_to(ROOT)} is not normalized (§Closed in id order, canonical layout)")
    print("in sync" if ok else f"{MD.relative_to(ROOT)} differs from what {YAML.relative_to(ROOT)} renders; run "
          "`python tools/register.py render`")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
