"""Request values the dashboard projections accept (F20.2 review, 2026-10-05): timestamps as the frontend sends them,
parsed as real dates; and the history capability's reason carrying no storage detail."""

from __future__ import annotations

import logging

import pytest

from aew.dashboard import projections as P
from aew.dashboard.reasons import REASONS


@pytest.mark.parametrize("value, expected", [
    ("2026-10-04T00:00:00Z", "2026-10-04T00:00:00Z"),
    ("2026-10-04T00:00:00.000Z", "2026-10-04T00:00:00Z"),  # the frontend's fractional form
    ("2026-10-04T23:59:59.999Z", "2026-10-04T23:59:59Z"),  # an upper bound keeps its second
    ("2026-10-04T23:59:59.123456789Z", "2026-10-04T23:59:59Z"),
    ("2024-02-29T12:00:00Z", "2024-02-29T12:00:00Z"),  # a leap day
])
def test_valid_utc_timestamps_are_accepted_and_normalized(value, expected):
    assert P.check_timestamp("until", value) == expected


def test_a_fractional_lower_bound_moves_up_to_the_next_second_and_a_whole_one_does_not():
    assert P.check_timestamp("since", "2026-10-04T00:00:00.500Z", lower_bound=True) == "2026-10-04T00:00:01Z"
    assert P.check_timestamp("since", "2026-10-04T00:00:00.000Z", lower_bound=True) == "2026-10-04T00:00:00Z"
    assert P.check_timestamp("since", "2026-10-04T23:59:59.1Z", lower_bound=True) == "2026-10-05T00:00:00Z"
    assert P.check_timestamp("since", "2026-10-04T00:00:00Z", lower_bound=True) == "2026-10-04T00:00:00Z"
    assert P.check_timestamp("since", None) is None


@pytest.mark.parametrize("value", [
    "2026-02-30T00:00:00Z", "2026-13-01T00:00:00Z", "2026-00-10T00:00:00Z", "2026-10-04T24:00:00Z",
    "2026-10-04T00:60:00Z", "2026-10-04T00:00:60Z", "2023-02-29T00:00:00Z",  # impossible dates and times
    "2026-10-04T00:00:00", "2026-10-04T00:00:00+00:00", "2026-10-04 00:00:00Z", "2026-10-04T00:00:00.Z",
    "2026-10-04T00:00:00.1234567890Z", "yesterday", "", "2026-10-04T00:00:00Z\n", " 2026-10-04T00:00:00Z",
])
def test_impossible_or_foreign_timestamps_are_invalid_requests(value):
    with pytest.raises(P.InvalidRequest):
        P.check_timestamp("since", value)


def test_the_history_capability_reason_names_no_storage_path(caplog):
    class Archive:
        def index(self, state):
            raise PermissionError(13, "Permission denied", "/home/someone/project/.aew/local/history.sqlite")

    class Projector(P.Projector):  # only the two attributes `_history_state` reads
        def __init__(self) -> None:
            from aew.engine.archive_ops import V2

            self.state = {"schema": V2, "cold": {}}
            self.archive = Archive()

    caplog.set_level(logging.WARNING, logger="aew.dashboard")
    state, reasons = Projector()._history_state()  # noqa: SLF001 (the function under review)
    assert state == P.UNAVAILABLE
    assert reasons == [{"code": "HISTORY_INDEX_UNAVAILABLE", "message": REASONS["HISTORY_INDEX_UNAVAILABLE"]}]
    assert "history.sqlite" not in str(reasons) and "someone" not in str(reasons)
    assert "history.sqlite" in caplog.text and "PermissionError" in caplog.text  # the detail went to the server log
