"""Opaque cursors (design note §4.5 and §4.6).

Three kinds, for three sequences:

* a **pinned cursor** walks an append-only sequence downwards from the point where paging started (the history
  manifest's ``seq``, the transition log's revision): ``pin`` is the newest number the pagination session may see,
  ``before`` the lowest number already served. Later appends never enter the session and never invalidate it, so a
  pinned cursor never needs a ``409``;
* a **hot cursor** pages a projection of hot state by id (keyset: ``after`` is the last id served) at one control
  revision; when the revision changed the page is gone (``409 CURSOR_EXPIRED``, "restart this bounded query");
* a **keyset cursor** pages data outside control state (the stored maps by root, a map's inputs by position) with no
  revision at all, so a control commit never expires it (register F20.8).

Cursors are base64url JSON, unsigned, and validated against the request they return to: ``route``, ``project``,
``filters`` and ``limit`` must match, the numbers must be in range. A forged cursor can only pick a page of a
read-only, bounded projection, so signing would add nothing (R12).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

MAX_CURSOR_LEN = 1024
VERSION = 1


class CursorError(Exception):
    """A cursor that cannot be used: ``code`` is ``CURSOR_INVALID`` (400) or ``CURSOR_EXPIRED`` (409)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def encode(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode(cursor: str) -> dict[str, Any]:
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= MAX_CURSOR_LEN:
        raise CursorError("CURSOR_INVALID", "the cursor is empty or too long")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise CursorError("CURSOR_INVALID", "the cursor does not decode") from None
    if not isinstance(payload, dict) or payload.get("v") != VERSION:
        raise CursorError("CURSOR_INVALID", "the cursor is not one this server issued")
    return payload


def _check_scope(payload: dict[str, Any], *, route: str, project: str, filters: dict[str, Any], limit: int) -> None:
    if payload.get("route") != route:
        raise CursorError("CURSOR_INVALID", "the cursor belongs to another route")
    if payload.get("project") != project:
        raise CursorError("CURSOR_INVALID", "the cursor belongs to another project")
    if payload.get("filters") != _normal(filters):
        raise CursorError("CURSOR_INVALID", "the cursor was taken with different filters")
    if payload.get("limit") != limit:
        raise CursorError("CURSOR_INVALID", "the cursor was taken with a different limit")


def _normal(filters: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in sorted(filters.items()) if v is not None}


def _int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CursorError("CURSOR_INVALID", f"the cursor's {key} is not a sequence number")
    return value


@dataclass(frozen=True)
class Pinned:
    """A pinned cursor (R11): the next page holds numbers ``< before`` and ``<= pin``."""

    route: str
    project: str
    pin: int
    before: int
    filters: dict[str, Any]
    limit: int

    def encode(self) -> str:
        return encode({"v": VERSION, **asdict(self), "filters": _normal(self.filters)})

    @classmethod
    def parse(cls, cursor: str, *, route: str, project: str, filters: dict[str, Any], limit: int,
              current: int) -> Pinned:
        """Validate a cursor against the request and the sequence's current length (``current``): a pin above it is
        another project's cursor or a corrupted one (a history cannot shrink), and ``before`` must lie in ``1..pin``."""
        payload = decode(cursor)
        _check_scope(payload, route=route, project=project, filters=filters, limit=limit)
        pin, before = _int(payload, "pin"), _int(payload, "before")
        if pin > current:
            raise CursorError("CURSOR_INVALID", "the cursor pins more entries than this history has")
        if not 1 <= before <= pin:
            raise CursorError("CURSOR_INVALID", "the cursor's position is outside the pinned range")
        return cls(route, project, pin, before, _normal(filters), limit)

    @classmethod
    def start(cls, *, route: str, project: str, filters: dict[str, Any], limit: int, current: int) -> Pinned:
        """The first page: pinned at the sequence's current length, nothing served yet."""
        return cls(route, project, current, current + 1, _normal(filters), limit)

    def advanced(self, lowest_served: int) -> Pinned | None:
        """The cursor for the page after one whose lowest number was ``lowest_served``; None at the end."""
        if lowest_served <= 1:
            return None
        return Pinned(self.route, self.project, self.pin, lowest_served, self.filters, self.limit)


@dataclass(frozen=True)
class Hot:
    """A hot cursor (R14): keyset paging by id within one control revision."""

    route: str
    project: str
    rev: int
    filters: dict[str, Any]
    limit: int
    after: str

    def encode(self) -> str:
        return encode({"v": VERSION, **asdict(self), "filters": _normal(self.filters)})

    @classmethod
    def parse(cls, cursor: str, *, route: str, project: str, filters: dict[str, Any], limit: int,
              revision: int) -> Hot:
        payload = decode(cursor)
        _check_scope(payload, route=route, project=project, filters=filters, limit=limit)
        rev = _int(payload, "rev")
        after = payload.get("after")
        if not isinstance(after, str) or not after:
            raise CursorError("CURSOR_INVALID", "the cursor has no position")
        if rev != revision:
            raise CursorError("CURSOR_EXPIRED", f"the control revision moved from {rev} to {revision}")
        return cls(route, project, rev, _normal(filters), limit, after)


@dataclass(frozen=True)
class Keyset:
    """A keyset cursor over data that is not control state (register F20.8; the change note §4.2): the stored maps by
    root (``after`` is the last root served) or a map's inputs by position (``after`` is the next position). It
    carries no revision, so a control commit never expires it; ``filters`` bind it to its scope (an inputs cursor
    names its root, so it is ``CURSOR_INVALID`` on another map). It never carries a path, so it stays far below
    :data:`MAX_CURSOR_LEN` whatever the repository's names are."""

    route: str
    project: str
    filters: dict[str, Any]
    limit: int
    after: str | int

    def encode(self) -> str:
        return encode({"v": VERSION, **asdict(self), "filters": _normal(self.filters)})

    @classmethod
    def parse(cls, cursor: str, *, route: str, project: str, filters: dict[str, Any], limit: int,
              position: bool = False) -> Keyset:
        """``position``: ``after`` is an integer position (checked against the list by the caller); otherwise a
        64-digit lower-case hex root."""
        payload = decode(cursor)
        _check_scope(payload, route=route, project=project, filters=filters, limit=limit)
        if set(payload) != {"v", "route", "project", "filters", "limit", "after"}:
            raise CursorError("CURSOR_INVALID", "the cursor is not one this server issued")
        after = payload.get("after")
        if position:
            after = _int(payload, "after")
        elif not isinstance(after, str) or not ROOT_RE.fullmatch(after):
            raise CursorError("CURSOR_INVALID", "the cursor's position is not a map root")
        return cls(route, project, _normal(filters), limit, after)


ROOT_RE = re.compile(r"[0-9a-f]{64}")


def page_by_id(items: list[dict[str, Any]], *, after: str | None, limit: int,
               ) -> tuple[list[dict[str, Any]], str | None]:
    """One page of items already sorted by ``id``: those after ``after``, at most ``limit``; and the id to continue
    from (None when the page is the last)."""
    rest = [i for i in items if after is None or i["id"] > after]
    page = rest[:limit]
    return page, (page[-1]["id"] if len(rest) > limit else None)
