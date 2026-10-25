"""The second, independently written detector for the dashboard server (STG-12 S12-2, family 6; the hand-off's standard
item for a recogniser that feeds an enforced check).

``interfaces_dashboard.py`` reads the server module with ``ast``. This module reads the same file as text and shares no
code with it: only ``re`` and the tuple types it answers with. The two must agree on the server and on every planted
case (``tests/integration/test_reference_dashboard_routes.py``,
``tests/unit/test_reference_interface_controls.py``); what both miss is pinned in the second, one probe per item. Text
is the cruder reading (it cannot tell a name from its mention in a string, so a line that is only a comment is skipped
and a definition at the start of a line is not a use; it reads a path's consumer from the words around it, so an
expression it cannot take apart is ``<expr>``), so it is the cross-check and the AST reading is the source.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from reference_families.interfaces_dashboard import BASES, CHECKED, Branch, Reading, norm

_IF = re.compile(r"^(\s*)if\s+(not\s+)?url\.path\.startswith\(\s*([^)]*?)\s*\)\s*:")
_SELF_CALL = re.compile(r"\bself\.(\w+)\(")
_ASSIGNED_SELF_CALL = re.compile(r"^\s*[\w, ]+=\s*self\.(\w+)\(")
_DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+(\w+)")
_DO = re.compile(r"\bdef\s+do_([A-Z]+)\(")
_TABLE = re.compile(r"\b(ROUTES|CONDITIONAL_HANDLERS)\b")
_ASSIGNED = re.compile(r"^(\w+)\s*(?::[^=]*)?=(?!=)")
_NEEDS = re.compile(r"^\s*if\s+self\.(\w+)\s+is\s+None\s*:")
_PATH = re.compile(r"\b(url|h)\.path\b")
_STARTSWITH = re.compile(r"\.startswith\(([^()]*)\)")
_CALLEE = re.compile(r"([\w.]+)\([^()]*$")
_COMPARE_AFTER = re.compile(r"^\s*(==|!=|not in|in)\s+(\S.*)$")
_COMPARE_BEFORE = re.compile(r"(\S+)\s+(==|!=|not in|in)\s+$")
_OPERATORS = {"==": "Eq", "!=": "NotEq", "in": "In", "not in": "NotIn"}
_PLAIN = re.compile(r"""^(?:[A-Za-z_][\w.]*|'[^']*'|"[^"]*")""")
_ENDS = re.compile(r"^\s*(?:$|[:),]|\b(?:and|or|if|else)\b)")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _slice_end(rest: str) -> int:
    """The index just past the ``]`` that closes the ``[`` rest starts with."""
    depth = 0
    for i, ch in enumerate(rest):
        depth += ch == "["
        depth -= ch == "]"
        if depth == 0:
            return i + 1
    return len(rest)


def _other(text: str) -> str:
    """The other side of a comparison, from the text that follows its operator: a name, dotted name or literal when that
    is all of it, else ``<expr>``."""
    got = _PLAIN.match(text)
    if got and _ENDS.match(text[got.end():]):
        return norm(got.group(0))
    return "<expr>"


def _consumer(before: str, rest: str) -> str:
    """What consumes a path read: the call it is an argument of, the comparison it is an operand of, the assignment it
    is the value of; ``other`` when none can be told from the words around it."""
    call = _CALLEE.search(before)
    if call:
        return f"call:{norm(call.group(1))}"
    after = _COMPARE_AFTER.match(rest)
    if after:
        return f"compare:{_OPERATORS[after.group(1)]}:{_other(after.group(2))}"
    prior = _COMPARE_BEFORE.search(before)
    if prior:
        return f"compare:{_OPERATORS[prior.group(2)]}:{_other(prior.group(1) + ' ')}"
    if re.search(r"(?<![=!<>])=\s*$", before):
        return "assign"
    return "other"


def read(text: str, constants: Mapping[str, str], owner: str = "DashboardServer", handle: str = "_handle") -> Reading:
    lines = text.split("\n")
    stack: list[tuple[int, str]] = []
    refs: list[tuple[str, str]] = []
    where: dict[str, list[int]] = {}  # qualified symbol -> its line numbers (a def's own line included)
    reads: list[tuple[str, str, str, str]] = []
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
        for part in range(1, len(stack) + 1):  # a line belongs to every def it is inside
            where.setdefault(".".join(name for _, name in stack[:part]), []).append(number)
        assigned = _ASSIGNED.match(body) if indent == 0 else None
        if assigned and not stack:  # a module-level assignment is the scope of its right-hand side (as in the AST)
            symbol = assigned.group(1)
        if not (indent == 0 and _TABLE.match(body)):  # a definition at the start of a line is not a use
            refs += [(m.group(1), symbol) for m in _TABLE.finditer(body)]
        if symbol in {f"{owner}.{name}" for name in CHECKED}:
            for m in _PATH.finditer(line):
                base, rest, before = f"{m.group(1)}.path", line[m.end():], line[:m.start()]
                if base not in BASES:
                    continue
                if rest.startswith(".startswith("):
                    arg = _STARTSWITH.match(rest)
                    reads.append((symbol, base, "startswith", norm(arg.group(1)) if arg else "<expr>"))
                elif rest.startswith("["):
                    reads.append((symbol, base, "slice", _consumer(before, rest[_slice_end(rest):])))
                elif rest.startswith(".") or before.rstrip().endswith("["):  # another use, or the path as an index
                    reads.append((symbol, base, "any", "other"))
                else:
                    reads.append((symbol, base, "bare", _consumer(before, rest)))
    branches: list[Branch] = []
    fallthrough: str | None = None
    own = where.get(f"{owner}.{handle}", [])
    first_if_indent: int | None = None
    for number in own:
        found = _IF.match(lines[number])
        if not found:
            continue
        indent = len(found.group(1))
        first_if_indent = indent if first_if_indent is None else first_if_indent
        arg = found.group(3)
        quoted = re.fullmatch(r"""["']([^"']*)["']""", arg)
        prefix = quoted.group(1) if quoted else constants.get(arg)
        handler = None
        needs = None
        for later in lines[number + 1:]:
            if later.strip() and _indent(later) <= indent:
                break
            call = _SELF_CALL.search(later)
            if call and later.strip().startswith("self.") and handler is None:
                handler = call.group(1)
            hit = _NEEDS.match(later)
            if hit and needs is None:
                needs = hit.group(1)
        if needs is None and handler:  # the handler's own first `if self.x is None`
            for n in where.get(f"{owner}.{handler}", []):
                hit = _NEEDS.match(lines[n])
                if hit:
                    needs = hit.group(1)
                    break
        branches.append(Branch(prefix, bool(found.group(2)), handler, needs))
    if first_if_indent is not None:
        for number in own:
            line = lines[number]
            call = _ASSIGNED_SELF_CALL.match(line)
            if call and _indent(line) == first_if_indent:
                fallthrough = call.group(1)
    methods = sorted(set(_DO.findall(text)))
    return Reading(branches, fallthrough, methods, sorted(set(refs)), sorted(reads))
