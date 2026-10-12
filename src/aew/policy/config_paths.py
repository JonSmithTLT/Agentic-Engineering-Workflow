"""Configuration paths: the one encoder and resolver of every locator the configuration projection emits (register
F46.1, proposal §3.1a).

A field's identity is its location in the parsed policy document, written as an **RFC 6901 JSON Pointer**: ``/``
separates segments, and a key's ``~`` and ``/`` are escaped as ``~0`` and ``~1``. So any key has exactly one encoding,
and dotted forms are not used.

* A mapping key that may be shown (it passes :func:`shown_key`: rule 5's shape, at most 128 bytes, and no credential
  shape, rule 8) is its escaped key.
* A key that may not be shown, and **every non-string key** (YAML ``1:``, ``true:``, ``null:``), is the segment
  ``@i``: its index in that mapping, in document order. No shown key can produce it, since a shown key starts with a
  letter or a digit.
* A list element is its index.

**What ``@i`` is.** A display-only, masked extension to RFC 6901. A path containing one is not an ordinary, persistent
JSON Pointer identity: a standard resolver would read ``@i`` as a literal key, it is valid only under the document
digest it was rendered with (inserting a key shifts the indices), and it is never stored, compared across digests or
used as an edit target. Only ``@``-free paths are field identities (:func:`is_identity`).

Every locator the projection writes (``FieldValue.path``, ``Violation.path``, ``identity_error.field_path``, the
``routed_by`` entries, a violation's ``extra_key``) is built here; nothing else formats a path.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

from aew.harness.contract import credential_shaped

# Rule 5's shape for a key or a name that may be shown (profile names, route keys, card ids, logical document names).
SHOWN_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
SHOWN_KEY_MAX_BYTES = 128
MASK = "@"

Location = tuple[Any, ...]


def shown_key(key: Any) -> bool:
    """Whether a mapping key may be echoed: a string of rule 5's shape, at most 128 bytes, with no credential shape."""
    return (isinstance(key, str) and SHOWN_KEY.fullmatch(key) is not None
            and len(key.encode("utf-8")) <= SHOWN_KEY_MAX_BYTES and not credential_shaped(key))


def escape(key: str) -> str:
    """A raw key as one RFC 6901 reference token: ``~`` is ``~0`` and ``/`` is ``~1`` (in that order)."""
    return key.replace("~", "~0").replace("/", "~1")


def unescape(token: str) -> str:
    """The raw key of one RFC 6901 reference token (``~1`` before ``~0``, as RFC 6901 §4 requires)."""
    return token.replace("~1", "/").replace("~0", "~")


def pointer(tokens: Iterable[str]) -> str:
    """The pointer of already-escaped reference tokens (``""`` for the document itself)."""
    return "".join("/" + t for t in tokens)


def tokens(path: str) -> list[str]:
    """The reference tokens of a pointer, still escaped."""
    if path == "":
        return []
    if not path.startswith("/"):
        raise ValueError("a JSON Pointer is empty or starts with '/'")
    return path[1:].split("/")


def masked(index: int) -> str:
    return f"{MASK}{index}"


def segment(container: dict[Any, Any], key: Any) -> str:
    """The reference token of ``key`` in the mapping ``container``: the escaped key when it may be shown, else ``@i``
    (its index in document order)."""
    if shown_key(key):
        return escape(key)
    return masked(list(container).index(key))


def label(container: dict[Any, Any], key: Any) -> str:
    """How a key is shown on its own (a name, a route key, ``card:<id>``): the key itself, or ``@i``."""
    return key if shown_key(key) else masked(list(container).index(key))


def encode(location: Sequence[Any], document: Any) -> str:
    """The locator of ``location`` (the keys and list indices from the document's root) in ``document``.

    The walk follows the document, so a mapping key is told from a list index by its container. Where the location
    leaves the document (a key the document lacks: a field that is ABSENT), the remaining keys are encoded as keys
    with no container, so an unshown one cannot be indexed and is refused."""
    out: list[str] = []
    node: Any = document
    for step in location:
        if isinstance(node, dict) and step in node:
            out.append(segment(node, step))
            node = node[step]
        elif isinstance(node, list) and isinstance(step, int) and not isinstance(step, bool) and 0 <= step < len(node):
            out.append(str(step))
            node = node[step]
        else:
            if not isinstance(step, str) or not shown_key(step):  # a schema's name for an absent field is shown
                raise ValueError("an absent location's key must have a shown key's shape")
            out.append(escape(step))
            node = None
    return pointer(out)


def resolve(document: Any, path: str) -> Location:
    """The location ``path`` names in ``document``. An ``@i`` segment is the ``i``-th key of that mapping, for display
    only (it is valid only under the digest the path was rendered with). Raises ``KeyError`` when the path does not
    resolve."""
    out: list[Any] = []
    node: Any = document
    for token in tokens(path):
        if isinstance(node, dict):
            if token.startswith(MASK) and token[1:].isdigit():
                keys = list(node)
                i = int(token[1:])
                if i >= len(keys):
                    raise KeyError(path)
                key = keys[i]
            else:
                key = unescape(token)
                if key not in node:
                    raise KeyError(path)
            out.append(key)
            node = node[key]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            out.append(int(token))
            node = node[int(token)]
        else:
            raise KeyError(path)
    return tuple(out)


def is_identity(path: str) -> bool:
    """Whether ``path`` is a field identity: no ``@`` segment. A path with one is display-only and never an edit
    target (F46.1 proposal §4.3 condition 8)."""
    return not any(t.startswith(MASK) for t in tokens(path))
