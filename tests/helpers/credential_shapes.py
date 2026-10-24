"""Synthetic credential-shaped values, built at run time from the patterns' one home (`aew.harness.contract`).

No real key, and no complete key-shaped literal in the source: each value is assembled from a pattern's own literal
prefix and an obviously synthetic filler, then checked to match that pattern whole, so a changed pattern fails here
rather than silently testing nothing (register F46.1, proposal §9).
"""

from __future__ import annotations

import re

# A pattern's literal prefix: its leading letters, `_` and `-`, and lower-case classes such as `[pos]` (`gh[pos]_`).
PREFIX = re.compile(r"(?:[A-Za-z_-]|\[[a-z]+\])+")
FILLER = "Synthetic0Test1Value2Only3Not4A5Real6Key7Ever8"  # mixed case and digits: matches every body class


def prefix(pattern: str) -> str:
    m = PREFIX.match(pattern)
    assert m, pattern
    return m.group(0)


def synthetic(pattern: str) -> str:
    """A synthetic value matching ``pattern`` whole: its prefix (a class becomes its first letter), then a filler body
    restricted to the body's characters and cut to a length the pattern accepts."""
    head = re.sub(r"\[([a-z])[a-z]*\]", r"\1", prefix(pattern))
    for n in range(10, 60):
        for body in (FILLER, FILLER.upper(), FILLER.lower(), FILLER.replace("e", "-")):
            for i in range(len(body) - 1):
                candidate = head + (body[i:] + body)[:n]
                if re.fullmatch(pattern, candidate):
                    return candidate
    raise AssertionError(f"no synthetic value for {pattern}")
