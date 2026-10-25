"""The second, independently written detector for the STG-02 server's routes (STG-12 S12-2, family 6b; the hand-off's
standard item for a recogniser that feeds an enforced check).

``stg02_server.py`` reads ``aew/stg02/server.py`` with ``ast``. This module reads the same file as text and shares no
code with it: only ``re`` and the tuple type it answers with (a module-level name, a constant or a compiled regex, is
resolved from the imported module in both, since it is an input). The two must agree on the server and on every
planted case (``tests/integration/test_reference_stg02.py``, ``tests/unit/test_reference_stg02_controls.py``). Text is
the cruder reading: it reads the forms the module uses (``path == "..."``, ``path in ("...", "...")``,
``.startswith("...")``, the tuple a loop iterates, ``NAME.fullmatch(...)``), skips a line that is only a comment, and
cannot tell a comparison from its spelling in a string, so it is the cross-check and the AST reading is the source.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from reference_families.stg02_server import TEST_PREFIX, Reading

_STR = r"""["'](/[^"']*)["']"""
_EQ_AFTER = re.compile(r"(?:==|!=)\s*" + _STR)
_EQ_BEFORE = re.compile(_STR + r"\s*(?:==|!=)")
_IN = re.compile(r"\b(?:not\s+)?in\s*[(\[{]\s*((?:" + _STR + r"\s*,?\s*)+)[)\]}]")
_NAME_EQ = re.compile(r"(?:==|!=)\s*([A-Za-z_]\w*)\b")
_STARTSWITH = re.compile(r"\.startswith\(\s*" + _STR + r"\s*\)")
_FOR_TUPLE = re.compile(r"^\s*for\s+(\w+)\s*,[^:]*\bin\s*\(\(")
_ROW = re.compile(r"\(\s*" + _STR + r"\s*,")
_MATCHED = re.compile(r"\b(\w+)\.(?:fullmatch|match|search)\(")
_TEST_ROUTE = re.compile(r"""method\s*==\s*["'](\w+)["'][^\n]*?\bin\s*\(\s*((?:["']/_test/[^"']*["']\s*,?\s*)+)\)""")


def _route(value: Any) -> str | None:
    return value if isinstance(value, str) and value.startswith("/") else None


def read(text: str, values: Mapping[str, Any]) -> Reading:
    lines = [line for line in text.split("\n") if not line.strip().startswith("#")]
    exact: set[str] = set()
    prefixes: set[str] = set()
    patterns: set[str] = set()
    test_methods: dict[str, str] = {}
    for number, line in enumerate(lines):
        exact.update(_EQ_AFTER.findall(line))
        exact.update(_EQ_BEFORE.findall(line))
        for group in _IN.findall(line):
            exact.update(re.findall(_STR, group[0]) if isinstance(group, tuple) else re.findall(_STR, group))
        for name in _NAME_EQ.findall(line):
            if (found := _route(values.get(name))) is not None:
                exact.add(found)
        prefixes.update(_STARTSWITH.findall(line))
        for name in _MATCHED.findall(line):
            if (found := _route(getattr(values.get(name), "pattern", None))) is not None:
                patterns.add(found)
        for method, group in _TEST_ROUTE.findall(line):
            for route in re.findall(_STR, group):
                if route.startswith(TEST_PREFIX):
                    test_methods[route] = method
        loop = _FOR_TUPLE.match(line)
        if loop:
            head = []
            for later in lines[number:]:
                head.append(later)
                if later.rstrip().endswith(":"):
                    break
            body = "\n".join(lines[number + len(head): number + len(head) + 12])
            if re.search(r"\.startswith\(\s*" + re.escape(loop.group(1)) + r"\s*\)", body):
                prefixes.update(_ROW.findall("\n".join(head)))
    return Reading(sorted(exact), sorted(prefixes), sorted(patterns), test_methods)
