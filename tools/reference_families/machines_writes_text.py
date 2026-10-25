"""The second, independently written detector for the state-write sites (STG-12 S12-2, family 5; the hand-off's standard
item for a recogniser that feeds an enforced check).

``machines_writes.py`` reads the source with ``ast``. This module reads the same files as text and shares no code with
it: only ``re`` and the tuple type of a site. The two must agree on the tree and on every planted case
(``tests/integration/test_reference_machine_writes.py``); what both miss is pinned there, one probe per item. Text is
the cruder reading (it cannot follow an alias, so the table is asked by the two spellings the package uses for the
module, and it cannot tell a comment from code unless told, so a line that is only a comment is skipped), so it is the
cross-check and the AST reading is the source.
"""

from __future__ import annotations

import re

from reference_families.machines_writes import ASSIGN, SET_STATE, StateWrite

_SET_STATE = re.compile(r"\.set_state\(")
_ASSIGN = re.compile(r"""\[\s*["']state["']\s*\]\s*=(?!=)""")
_DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)")
_CHECK = re.compile(r"\b(?:transitions|T)\.check\(")


def writes(text: str, module: str) -> list[StateWrite]:
    stack: list[tuple[int, str]] = []  # (indent, name) of the defs and classes the line is inside
    found: list[tuple[str | None, str]] = []
    checked: set[str | None] = set()
    for line in text.split("\n"):
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        opened = _DEF.match(body)
        symbol = ".".join(name for _, name in stack) or None
        if opened:
            stack.append((indent, opened.group(1) or opened.group(2)))
            symbol = ".".join(name for _, name in stack)
        found += [(symbol, SET_STATE)] * len(_SET_STATE.findall(body))
        found += [(symbol, ASSIGN)] * len(_ASSIGN.findall(body))
        if _CHECK.search(body):
            checked.add(symbol)
    return [StateWrite(module, symbol, form, symbol in checked) for symbol, form in found]
