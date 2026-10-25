"""The second, independently written detector for the dashboard server (STG-12 S12-2, family 6; the hand-off's standard
item for a recogniser that feeds an enforced check).

``interfaces_dashboard.py`` reads the server module with ``ast``. This module reads the same file as text and shares
no code with it: only ``re`` and the two tuple types it answers with. The two must agree on the server and on every
planted case (``tests/integration/test_reference_dashboard_routes.py``); what both miss is pinned there, one probe per
item. Text is the cruder reading (it cannot tell a name from its mention in a string, so a line that is only a comment
is skipped and a definition at the start of a line is not a use), so it is the cross-check and the AST reading is the
source.
"""

from __future__ import annotations

import re

from reference_families.interfaces_dashboard import Branch, Reading

_IF = re.compile(r"^(\s*)if\s+(not\s+)?url\.path\.startswith\(\s*([^)]*?)\s*\)\s*:")
_SELF_CALL = re.compile(r"\bself\.(\w+)\(")
_ASSIGNED_SELF_CALL = re.compile(r"^\s*[\w, ]+=\s*self\.(\w+)\(")
_DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)")
_DO = re.compile(r"\bdef\s+do_([A-Z]+)\(")
_TABLE = re.compile(r"\b(ROUTES|CONDITIONAL_HANDLERS)\b")
_ASSIGNED = re.compile(r"^(\w+)\s*(?::[^=]*)?=(?!=)")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def read(text: str, constants: dict[str, str], owner: str = "DashboardServer", handle: str = "_handle") -> Reading:
    lines = text.split("\n")
    stack: list[tuple[int, str]] = []
    refs: list[tuple[str, str]] = []
    in_handle: list[int] = []
    for number, line in enumerate(lines):
        body = line.strip()
        if not body or body.startswith("#"):
            continue
        indent = _indent(line)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        opened = _DEF.match(body)
        if opened:
            stack.append((indent, opened.group(1) or opened.group(2)))
        symbol = ".".join(name for _, name in stack)
        assigned = _ASSIGNED.match(body) if indent == 0 else None
        if assigned and not stack:  # a module-level assignment is the scope of its right-hand side (as in the AST)
            symbol = assigned.group(1)
        if symbol == f"{owner}.{handle}":
            in_handle.append(number)
        if not (indent == 0 and _TABLE.match(body)):  # a definition at the start of a line is not a use
            refs += [(m.group(1), symbol) for m in _TABLE.finditer(body)]
    branches: list[Branch] = []
    fallthrough: str | None = None
    if in_handle:
        first_if_indent: int | None = None
        for number in in_handle:
            found = _IF.match(lines[number])
            if not found:
                continue
            indent = len(found.group(1))
            first_if_indent = indent if first_if_indent is None else first_if_indent
            arg = found.group(3)
            quoted = re.fullmatch(r"""["']([^"']*)["']""", arg)
            prefix = quoted.group(1) if quoted else constants.get(arg)
            handler = None
            for later in lines[number + 1:]:
                if later.strip() and _indent(later) <= indent:
                    break
                call = _SELF_CALL.search(later)
                if call and later.strip().startswith("self."):
                    handler = call.group(1)
                    break
            branches.append(Branch(prefix, bool(found.group(2)), handler))
        if first_if_indent is not None:
            for number in in_handle:
                line = lines[number]
                call = _ASSIGNED_SELF_CALL.match(line)
                if call and _indent(line) == first_if_indent:
                    fallthrough = call.group(1)
    methods = sorted(set(_DO.findall(text)))
    return Reading(branches, fallthrough, methods, sorted(set(refs)))
