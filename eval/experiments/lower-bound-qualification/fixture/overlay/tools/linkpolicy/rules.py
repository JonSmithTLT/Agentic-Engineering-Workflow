"""
The documentation's link rules (see `tools/linkpolicy/__init__.py`).
"""

from __future__ import annotations

from typing import NamedTuple


class Verdict(NamedTuple):
    keep: bool
    reason: str


def scheme_of(url: str) -> str | None:
    """ The URL's scheme, lower-cased, or `None` for a relative URL. """
    head, sep, _ = url.strip().partition(':')
    if not sep or not head or any(c in head for c in '/?#'):
        return None
    return head.lower()


def classify(url: str, *, blocked_schemes: tuple[str, ...] = ('javascript', 'vbscript', 'data', 'http')) -> Verdict:
    """ Whether the documentation may link to `url`: never to a blocked scheme, and only to `https` sites. """
    scheme = scheme_of(url)
    if scheme is None:
        return Verdict(True, 'relative')
    if scheme in blocked_schemes:
        return Verdict(False, f'blocked-scheme:{scheme}')
    return Verdict(True, 'allowed')
