"""The second, independently written detector for the SQLite tables (STG-12 S12-2, family 6; the hand-off's standard
item for a recogniser that feeds an enforced check).

``interfaces_sqlite.py`` finds DDL with ``ast``, runs it in memory and reads the tables back. This module reads the same
files as text and shares no code with it: only ``re``. It answers the one question both must agree on, which tables a
module's source creates (by the name after ``CREATE ... TABLE``), and whether the module imports ``sqlite3``
(``tests/integration/test_reference_interfaces.py``). Text is the cruder reading (it cannot run a statement, resolve a
placeholder or tell a docstring from code, so a line that is only a comment is skipped and a statement is read by its
words), so it is the cross-check, and the executed DDL is the source.
"""

from __future__ import annotations

import re

_TABLE = re.compile(r"""\bCREATE\s+(?:VIRTUAL\s+|TEMP\s+|TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?(\w+)""",
                    re.IGNORECASE)
_IMPORT = re.compile(r"^\s*(?:import\s+sqlite3\b|from\s+sqlite3\s+import\b)", re.MULTILINE)


def table_names(text: str) -> list[str]:
    code = "\n".join(line for line in text.split("\n") if not line.strip().startswith("#"))
    return sorted(set(_TABLE.findall(code)))


def imports_sqlite(text: str) -> bool:
    return bool(_IMPORT.search(text))
