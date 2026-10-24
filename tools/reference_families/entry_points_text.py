"""The second, independently written detector for the entry-points family (STG-12 S12-2; the hand-off's standard item
for a recogniser that feeds an enforced check).

``entry_points.py`` reads the source with ``ast``. This module reads the same files as text and shares no code with it:
only ``re``. The two must agree on the tree and on every planted case
(``tests/integration/test_reference_entry_points.py``); what both miss is the "cannot see" list pinned there, one probe
per item. Text is the cruder reading (it cannot follow an alias or tell a comment from code), so it is the cross-check
and the AST reading is the source.
"""

from __future__ import annotations

import re

# `"-m", "aew.harness.supervisor"` in an argv list, on one line or several, with either quote.
_SPAWN = re.compile(r"""["']-m["']\s*,\s*["'](aew[\w.]*)["']""")
# `process_kind.declare("name")` or `declared_as("name")`, with a literal entry point as its first argument.
_DECLARE = re.compile(r"""\bdeclare(?:d_as)?\(\s*["']([^"']+)["']""")
# `declared_as(process_kind.cli_entry_point(...))`: the CLI declaring whichever role argv and the environment give.
_DECLARE_CLI = re.compile(r"""\bdeclare(?:d_as)?\(\s*(?:[\w.]*\.)?cli_entry_point\(""")


def spawn_targets(text: str) -> list[str]:
    return sorted(_SPAWN.findall(text))


def declared(text: str) -> list[str]:
    return sorted(_DECLARE.findall(text))


def declares_cli_roles(text: str) -> bool:
    return bool(_DECLARE_CLI.search(text))
