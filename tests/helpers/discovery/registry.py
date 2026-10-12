"""The page's D2 tables, read as data (docs/implementation/vertical-uat.md §8.3 and §8.4): the per-rule modes, and the
code registry O-CODE judges by. The caller passes the page's text: the page is read only by the fast lane's tests,
which every tier runs."""

from __future__ import annotations

import re

MODES_MARKER = "### 8.3 The modes, the allow-list and the ratchet"
REGISTRY_MARKER = "### 8.4 The code registry"
OWNERS = ("operator", "Lead", "engine")


def _table(text: str, marker: str) -> list[list[str]]:
    """The rows of the first Markdown table after ``marker``: cells stripped, header and rule dropped."""
    lines = text[text.index(marker):].splitlines()
    rows: list[list[str]] = []
    started = False
    for line in lines[1:]:
        if line.startswith("|"):
            started = True
            rows.append([c.strip() for c in line.strip().strip("|").split(" | ")])
        elif started:
            break
    return rows[2:]


def doc_modes(text: str) -> dict[str, str]:
    return {row[0]: row[1].strip("`") for row in _table(text, MODES_MARKER)}


def rows(text: str) -> list[dict[str, object]]:
    """Each registry row: ``code``, ``meaning``, ``causes`` (a set) and ``owner``."""
    out = []
    for row in _table(text, REGISTRY_MARKER):
        code, meaning, causes, owner = row
        out.append({"code": code.strip("`"), "meaning": meaning,
                    "causes": frozenset(re.findall(r"`([a-z_]+)`", causes)), "owner": owner})
    return out


def load(text: str) -> dict[str, frozenset[str]]:
    """``code -> allowed causes``: what O-CODE checks a known cause against."""
    return {str(r["code"]): r["causes"] for r in rows(text)}  # type: ignore[misc]
