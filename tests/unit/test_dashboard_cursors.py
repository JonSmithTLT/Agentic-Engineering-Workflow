"""The dashboard's opaque cursors (design note §4.5, §4.6): pinned cursors survive appends and never 409; hot cursors
expire with the control revision; every cursor is validated against the request it returns to."""

from __future__ import annotations

import base64
import json

import pytest

from aew.dashboard import cursors as C

SCOPE = {"route": "history", "project": "calc", "filters": {"kind": "unit", "since": None}, "limit": 50}


def test_a_pinned_cursor_round_trips_and_walks_downwards():
    first = C.Pinned.start(current=120, **SCOPE)
    assert (first.pin, first.before) == (120, 121)  # nothing served yet: the page holds seq <= 120
    nxt = first.advanced(71)
    assert nxt is not None and (nxt.pin, nxt.before) == (120, 71)
    parsed = C.Pinned.parse(nxt.encode(), current=120, **SCOPE)
    assert parsed == nxt
    assert first.advanced(1) is None  # the oldest entry was served: no next page


def test_appends_never_invalidate_a_pinned_cursor():
    cursor = C.Pinned.start(current=10, **SCOPE).advanced(6)
    assert cursor is not None
    later = C.Pinned.parse(cursor.encode(), current=10_000, **SCOPE)  # 9,990 entries appended meanwhile
    assert (later.pin, later.before) == (10, 6)


@pytest.mark.parametrize("change, message", [
    ({"route": "work"}, "another route"),
    ({"project": "other"}, "another project"),
    ({"filters": {"kind": "audit"}}, "different filters"),
    ({"limit": 10}, "different limit"),
])
def test_a_pinned_cursor_from_another_scope_is_invalid_not_expired(change, message):
    cursor = C.Pinned.start(current=10, **SCOPE).encode()
    with pytest.raises(C.CursorError) as exc:
        C.Pinned.parse(cursor, current=10, **{**SCOPE, **change})
    assert exc.value.code == "CURSOR_INVALID" and message in exc.value.message


def test_a_pin_above_the_current_count_is_invalid():
    cursor = C.Pinned("history", "calc", 50, 30, {"kind": "unit"}, 50).encode()
    with pytest.raises(C.CursorError) as exc:
        C.Pinned.parse(cursor, current=40, **SCOPE)  # a history cannot shrink: not this project's cursor
    assert exc.value.code == "CURSOR_INVALID"


def test_a_position_outside_the_pinned_range_is_invalid():
    for before in (0, 51):
        cursor = C.Pinned("history", "calc", 50, before, {"kind": "unit"}, 50).encode()
        with pytest.raises(C.CursorError):
            C.Pinned.parse(cursor, current=60, **SCOPE)


def test_a_hot_cursor_expires_when_the_revision_moves():
    hot = C.Hot("work", "calc", 7, {"state": "READY"}, 100, "T-0003")
    same = C.Hot.parse(hot.encode(), route="work", project="calc", filters={"state": "READY"}, limit=100, revision=7)
    assert same.after == "T-0003"
    with pytest.raises(C.CursorError) as exc:
        C.Hot.parse(hot.encode(), route="work", project="calc", filters={"state": "READY"}, limit=100, revision=8)
    assert exc.value.code == "CURSOR_EXPIRED"


def test_filters_normalize_so_absent_and_null_filters_are_the_same_scope():
    a = C.Hot("work", "calc", 7, {"state": None, "kind": "ticket"}, 100, "T-1")
    parsed = C.Hot.parse(a.encode(), route="work", project="calc", filters={"kind": "ticket"}, limit=100, revision=7)
    assert parsed.filters == {"kind": "ticket"}


@pytest.mark.parametrize("bad", ["", "not base64 at all!", "x" * 2000,
                                 base64.urlsafe_b64encode(b"[1,2]").decode(),
                                 base64.urlsafe_b64encode(json.dumps({"v": 99}).encode()).decode(),
                                 base64.urlsafe_b64encode(json.dumps({"v": 1, "route": "history", "project": "calc",
                                                                      "filters": {"kind": "unit"}, "limit": 50,
                                                                      "pin": "ten", "before": 3}).encode()).decode()])
def test_malformed_cursors_are_invalid(bad):
    with pytest.raises(C.CursorError) as exc:
        C.Pinned.parse(bad, current=10, **SCOPE)
    assert exc.value.code == "CURSOR_INVALID"


def test_keyset_paging_by_id_never_skips_or_repeats():
    items = [{"id": f"T-{n:04d}"} for n in range(1, 8)]
    page, after = C.page_by_id(items, after=None, limit=3)
    assert [i["id"] for i in page] == ["T-0001", "T-0002", "T-0003"] and after == "T-0003"
    page, after = C.page_by_id(items, after=after, limit=3)
    assert [i["id"] for i in page] == ["T-0004", "T-0005", "T-0006"] and after == "T-0006"
    page, after = C.page_by_id(items, after=after, limit=3)
    assert [i["id"] for i in page] == ["T-0007"] and after is None
    page, after = C.page_by_id(items[:3], after=None, limit=3)  # exactly one page: no empty trailing page
    assert len(page) == 3 and after is None
