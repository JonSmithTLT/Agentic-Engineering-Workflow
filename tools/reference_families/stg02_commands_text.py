"""The second, independently written detector for STG-02's command path (STG-12 S12-2, family 6b; the hand-off's
standard item for a recogniser that feeds an enforced check).

``stg02_commands.py`` reads ``aew/stg02/commands.py`` with ``ast``. This module reads the same file as text and shares
no code with it: only ``re`` and the tuple type it answers with. The two must agree on the source and on every planted
case (``tests/integration/test_reference_stg02.py``, ``tests/unit/test_reference_stg02_controls.py``). Text is the
cruder reading (it follows the file's own spellings, ``refusal(<action>, "CAUSE")``, ``r["origin"] != "X"`` and
``action != "Y"``, and for a ``reason_code`` the three spellings ``"reason_code": v``, ``["reason_code"] = v`` and
``reason_code=v``, and the steps of ``_member`` as the lines ``if r["origin"] != "X":``, ``if <name>:``,
``if action != "Y":`` and ``return self.<method>(``; it skips a line that is only a comment and finds a function's body
by its indentation), so it is the cross-check and the AST reading is the source.
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
_REFUSAL_SHORT = re.compile(r"""\brefusal\(\s*[^,()]*\)""")
_RETURN_STR = re.compile(r"""^\s*return\s+["']([A-Z_0-9]+)["']""")
_RETURN_ANY = re.compile(r"""^\s*return\s+(\S.*)$""")
_IF_ORIGIN = re.compile(r"""^\s*if\s+\w+\[\s*["']origin["']\s*\]\s*!=\s*["']([A-Z_0-9]+)["']\s*:""")
_IF_STATE = re.compile(r"""^\s*if\s+(\w+)\s*:\s*(?:#.*)?$""")
_IF_ACTION = re.compile(r"""^\s*if\s+action\s*!=\s*["']([A-Z_0-9]+)["']\s*:""")
_RETURN_REFUSAL = re.compile(r"""^\s*return\s+refusal\(\s*[^,()]*(?:\[[^\]]*\])?[^,()]*\s*,\s*"""
                             r"""(?:["']([A-Z_0-9]+)["']|([^,)\s]+(?:\([^)]*\))?))""")
_RETURN_SELF = re.compile(r"""^\s*return\s+self\.(\w+)\(""")
_REASON = re.compile(r"""["']reason_code["']\s*:\s*([^,}\n]+)""")
_STORE = re.compile(r"""\[\s*["']reason_code["']\s*\]\s*=(?!=)\s*([^\n]+)""")
_KEYWORD = re.compile(r"""\breason_code\s*=(?!=)\s*([^,)\n]+)""")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _kind(value: str) -> str:
    value = value.split("#")[0].strip()
    if value == "None":
        return "none"
    if re.fullmatch(r"[A-Za-z_]\w*", value):
        return "name"
    if re.fullmatch(r"[A-Za-z_]\w*\[.*\]", value):
        return "subscript"
    return "other"


def _steps(lines: list[str], symbols: list[str],
           assigned_in: dict[str, dict[str, str]]) -> list[tuple[str, str, str, str]]:
    """The steps of ``_member`` as its lines give them, in order: an ``if`` on the origin, on a name a helper's call
    was assigned to, or on the action, whose next line returns a refusal; and the ``return self.<method>(`` that hands
    on."""
    member = next((s for s in dict.fromkeys(symbols) if s.endswith("._member")), None)
    if member is None:
        return []
    rows = [line for line, s in zip(lines, symbols, strict=True)
            if s == member and line.strip() and not line.strip().startswith(("#", "def "))]
    held = assigned_in.get(member, {})
    steps: list[tuple[str, str, str, str]] = []
    for k, line in enumerate(rows):
        following = rows[k + 1] if k + 1 < len(rows) else ""
        kind = literal = None
        if (hit := _IF_ORIGIN.match(line)) is not None:
            kind, literal = "origin-test", hit.group(1)
        elif (hit := _IF_STATE.match(line)) is not None and hit.group(1) in held:
            kind, literal = "state-test", ""
        elif (hit := _IF_ACTION.match(line)) is not None:
            kind, literal = "action-test", hit.group(1)
        if kind is not None and literal is not None:
            ref = _RETURN_REFUSAL.match(following)
            if ref is not None:
                name = ref.group(2)
                steps.append((member, kind, literal, ref.group(1) or (f"${held[name]}" if name in held else "?")))
        elif (hit := _RETURN_SELF.match(line)) is not None:
            steps.append((member, "hand-on", hit.group(1), ""))
    return steps


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
    other_returns: set[str] = set()  # methods that return something but a string constant or None
    for line, symbol in zip(lines, symbols, strict=True):
        got_return = _RETURN_ANY.match(line)
        if got_return and "." in symbol and not _RETURN_STR.match(line) and got_return.group(1).strip() != "None":
            other_returns.add(symbol.rsplit(".", 1)[-1])
    origins: set[str] = set()
    actions: set[str] = set()
    causes: set[str] = set()
    unreadable: set[str] = set()
    builders: set[tuple[str, str, str]] = set()
    inventory: list[tuple[str, str, str]] = []
    assigned_in: dict[str, dict[str, str]] = {}
    for line, symbol in zip(lines, symbols, strict=True):
        if line.strip().startswith("#"):
            continue
        if symbol.endswith("._member"):
            if (hit := _ORIGIN.search(line)) is not None:
                origins.add(hit.group(1))
            if (hit := _ACTION.search(line)) is not None:
                actions.add(hit.group(1))
        got = _ASSIGNED.match(line)
        if got:
            assigned_in.setdefault(symbol, {})[got.group(1)] = got.group(2)
        is_def = line.lstrip().startswith(("def ", "async def "))
        calls = [] if is_def else _REFUSAL.findall(line)
        for first, literal, name in calls:
            helper = assigned_in.get(symbol, {}).get(name)
            if literal:
                causes.add(literal)
            elif helper in method_returns and helper not in other_returns:
                causes.update(method_returns[helper])
            else:
                unreadable.add(symbol.split(".")[-1])
            if "=" not in name:  # a keyword for the cause is unreadable and no call of the inventory
                ref = literal or (f"${helper}" if helper else "?")
                inventory.append((symbol, first.strip().replace('"', "'"), ref))
        if not is_def:
            for _short in _REFUSAL_SHORT.findall(line):
                unreadable.add(symbol.split(".")[-1])
            for value in _REASON.findall(line):
                builders.add((symbol, "literal", _kind(value)))
            for value in _STORE.findall(line):
                builders.add((symbol, "store", _kind(value)))
            for value in _KEYWORD.findall(line):
                builders.add((symbol, "keyword", _kind(value)))
    delegation = method_returns.get("_delegation", [])
    steps = _steps(lines, symbols, assigned_in)
    # two different literals make the one the reading takes ambiguous: not found
    origin = next(iter(origins)) if len(origins) == 1 else None
    action = next(iter(actions)) if len(actions) == 1 else None
    return Reading(origin, action, sorted(causes), sorted(unreadable), delegation, sorted(builders),
                   sorted(inventory), steps)
