"""The second detector for the concurrency family's lock sites (STG-12 S12-2; the standard item for a recogniser).

``concurrency.py`` finds a ``FileLock`` construction by where its callee was imported from, and the callers of an opener
by the call graph. This module reads the same files as a token stream, by the spelling of the call, and shares no code
with it: it imports nothing of the package, and a test holds it to that (it does share the token helpers of
:mod:`reference_families.writers_text`, the write side's token reading and not the AST one). The two must agree per
module (``tests/integration/test_reference_concurrency.py``): how many ``FileLock(`` constructions and how many calls
named like an opener each module has. What neither sees is the family's ``cannot see`` list, each item pinned by a
probe.
"""

from __future__ import annotations

import tokenize
from collections import Counter
from collections.abc import Iterable

from reference_families import writers_text as T

LOCK = "FileLock"


def counts(text: str, names: Iterable[str]) -> Counter[str]:
    """How many times each of ``FileLock`` and ``names`` is called in the module's code (a definition is not a call)."""
    wanted = {LOCK, *names}
    tokens = T.tokens(text)
    found: Counter[str] = Counter()
    for i, t in enumerate(tokens):
        if t.type != tokenize.NAME or t.string not in wanted or i + 1 >= len(tokens) or tokens[i + 1].string != "(":
            continue
        if i > 0 and tokens[i - 1].string in ("def", "class"):
            continue
        found[t.string] += 1
    return found
