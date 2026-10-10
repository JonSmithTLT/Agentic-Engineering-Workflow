# Python Markdown
# A Python implementation of John Gruber's Markdown.
# Documentation: https://python-markdown.github.io/
# License: BSD (see LICENSE.md for details).
"""
The link policy's rules: what a link's URL is, and whether the policy keeps it.

Pure functions over strings; nothing here knows about Markdown or the element tree.
"""

from __future__ import annotations

from typing import NamedTuple
from urllib.parse import urlsplit


class Verdict(NamedTuple):
    keep: bool
    reason: str


def scheme_of(url: str) -> str | None:
    """ The URL's scheme (`https` for `https://example.com/`), or `None` for a relative URL. """
    head, sep, _ = url.partition(':')
    if not sep or not head or any(c in head for c in '/?#'):
        return None
    return head


def is_external(url: str, internal_hosts: list[str]) -> bool:
    """
    Whether a link leaves the site: an `http`, `https` or protocol-relative (`//host/...`) URL whose host is not
    one of `internal_hosts`.
    """
    scheme = scheme_of(url)
    if scheme is None and not url.startswith('//'):
        return False
    if scheme is not None and scheme.lower() not in ('http', 'https'):
        return False
    host = urlsplit(url).hostname
    return host is not None and host.lower() not in {h.lower() for h in internal_hosts}


def classify(url: str, *, blocked_schemes: list[str], allow_relative: bool) -> Verdict:
    """ Whether the policy keeps a link to `url`, and why. """
    scheme = scheme_of(url)
    if scheme is None:
        return Verdict(allow_relative, 'relative' if allow_relative else 'relative-not-allowed')
    if scheme in blocked_schemes:
        return Verdict(False, f'blocked-scheme:{scheme}')
    return Verdict(True, 'allowed')
