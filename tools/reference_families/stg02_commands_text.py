"""The second, independently written detector for STG-02's command path (STG-12 S12-2, family 6b; the hand-off's
standard item for a recogniser that feeds an enforced check).

``stg02_commands.py`` reads ``aew/stg02/commands.py`` with ``ast``. This module reads the same file as text and shares
no code with it: only ``re`` and the tuple type it answers with. The two must agree on the source and on every planted
case (``tests/integration/test_reference_stg02.py``, ``tests/unit/test_reference_stg02_controls.py``). Text is the
cruder reading (it follows the file's own spellings, ``refusal(<action>, "CAUSE")``, ``r["origin"] != "X"`` and
``action != "Y"``, skips a line that is only a comment, and finds a function's body by its indentation), so it is the
cross-check and the AST reading is the source.
"""

from __future__ import annotations

import re

from reference_families.stg02_commands import Reading

_ORIGIN = re.compile(r"""\[\s*["']origin["']\s*\]\s*!=\s*["']([A-Z_0-9]+)["']""")
_ACTION = re.compile(r"""\baction\s*!=\s*["']([A-Z_0-9]+)["']""")
_REFUSAL = re.compile(r"""\brefusal\(\s*([^,()]*(?:\[[^\]]*\])?[^,()]*)\s*,\s*"""
                      r"""(?:["']([A-Z_0-9]+)["']|([^,)\s]+(?:\([^)]*\))?))""")
_ASSIGNED = re.compile(r"^\s*(\w+)\s*=\s*self\.(\w+)\(")
_DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)")
_RETURN_STR = re.compile(r"""^\s*return\s+["']([A-Z_0-9]+)["']""")
_REASON = re.compile(r"""["']reason_code["']\s*:\s*([^,}\n]+)""")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _kind(value: str) -> str:
    value = value.strip()
    if value == "None":
        return "none"
    if re.fullmatch(r"[A-Za-z_]\w*", value):
        return "name"
    if re.fullmatch(r"[A-Za-z_]\w*\[.*\]", value):
        return "subscript"
    return "other"


def read(text: str) -> Reading:
    lines = text.split("\n")
    stack: list[tuple[int, str]] = []
    symbols: list[str] = []  # the qualified symbol each line is in
    for line in lines:
        body = line.strip()
        if body and not body.startswith("#"):
            indent = _indent(line)
            while stack and stack[-1][0] >= indent:
                stack.pop()
            opened = _DEF.match(body)
            if opened:
                stack.append((indent, opened.group(1) or opened.group(2)))
        symbols.append(".".join(name for _, name in stack))
    returns: dict[str, list[str]] = {}
    for line, symbol in zip(lines, symbols, strict=True):
        found = _RETURN_STR.match(line)
        if found:
            returns.setdefault(symbol, []).append(found.group(1))
    method_returns = {symbol.rsplit(".", 1)[-1]: sorted(set(v)) for symbol, v in returns.items() if "." in symbol}
    origin = action = None
    causes: set[str] = set()
    unreadable: set[str] = set()
    builders: set[tuple[str, str]] = set()
    assigned_in: dict[str, dict[str, str]] = {}
    for line, symbol in zip(lines, symbols, strict=True):
        if line.strip().startswith("#"):
            continue
        if symbol.endswith("._member"):
            if (hit := _ORIGIN.search(line)) is not None:
                origin = hit.group(1)
            if (hit := _ACTION.search(line)) is not None:
                action = hit.group(1)
        got = _ASSIGNED.match(line)
        if got:
            assigned_in.setdefault(symbol, {})[got.group(1)] = got.group(2)
        calls = [] if line.lstrip().startswith(("def ", "async def ")) else _REFUSAL.findall(line)
        for _first, literal, name in calls:
            if literal:
                causes.add(literal)
            elif name in assigned_in.get(symbol, {}) and assigned_in[symbol][name] in method_returns:
                causes.update(method_returns[assigned_in[symbol][name]])
            else:
                unreadable.add(symbol.split(".")[-1])
        for value in _REASON.findall(line):
            builders.add((symbol, _kind(value)))
    delegation = method_returns.get("_delegation", [])
    return Reading(origin, action, sorted(causes), sorted(unreadable), delegation, sorted(builders))
