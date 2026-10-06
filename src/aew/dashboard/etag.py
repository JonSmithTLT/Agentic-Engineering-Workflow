"""Conditional requests: the strong validator and ``If-None-Match`` (design note §4.12, R19; F20.4).

``ETag: "<sha256-hex>"`` of ``scope + "\\n" + canonical_json(body without generated_at)``. The scope is the request
path, the project and the normalized query (filters, limit, cursor), so two scopes with equal bodies never share a
validator. ``control_revision`` and every telemetry field are in the body, so any change to either is a new validator.

The snapshot's time is the one thing excluded. The projections write it wherever they need "now" (the envelope's
``generated_at``, ``Health.observed_at``, and the fallbacks for a record that names no time of its own) as
:data:`SNAPSHOT_TIME`, a marker no engine value can equal; the validator is computed over the marked body, and
:func:`stamp` then writes the real time into every marker before the body is validated and sent. A ``304`` therefore
means exactly "the representation is unchanged except for the time it was read", and the client keeps the
``generated_at`` (and ``observed_at``) it has, as the contract says it must.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Sorts after every Timestamp (so ordering by a fallback time is what ordering by the real time was) and can never be
# an engine value: U+FFFF is a noncharacter.
SNAPSHOT_TIME = "￿snapshot-time"
GENERATED_AT = "generated_at"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def scope(path: str, project_id: str, query: dict[str, Any]) -> str:
    """The request scope: the path (with its id), the project, and the normalized query parameters."""
    return canonical_json({"path": path, "project": project_id, "query": dict(sorted(query.items()))})


def validator(scope_text: str, body: dict[str, Any]) -> str:
    """The strong ETag of a marked body (before :func:`stamp`) in its scope, quoted as the header carries it."""
    rest = {k: v for k, v in body.items() if k != GENERATED_AT}
    digest = hashlib.sha256((scope_text + "\n" + canonical_json(rest)).encode("utf-8")).hexdigest()
    return f'"{digest}"'


def stamp(value: Any, now: str) -> Any:
    """``value`` with every :data:`SNAPSHOT_TIME` marker replaced by the snapshot's real time."""
    if isinstance(value, dict):
        return {k: stamp(v, now) for k, v in value.items()}
    if isinstance(value, list):
        return [stamp(v, now) for v in value]
    if isinstance(value, str) and value == SNAPSHOT_TIME:
        return now
    return value


def matches(if_none_match: str | None, etag: str) -> bool:
    """Whether ``If-None-Match`` names ``etag`` with a strong match. The header is a comma-separated list; a weak
    validator (``W/"…"``) and ``*`` never match: a ``*`` would give a ``304`` for a representation never seen."""
    if not if_none_match:
        return False
    for member in if_none_match.split(","):
        member = member.strip()
        if member.startswith("W/") or member == "*":
            continue
        if member == etag:
            return True
    return False
