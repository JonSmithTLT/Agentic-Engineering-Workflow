"""Calendar months."""

import calendar
from datetime import date


def parse_month(text: str) -> tuple[int, int]:
    """'2026-01' -> (2026, 1)."""
    year, sep, month = text.strip().partition("-")
    if not sep or not (year.isdigit() and month.isdigit()) or not 1 <= int(month) <= 12:
        raise ValueError(f"not a month (YYYY-MM): {text!r}")
    return int(year), int(month)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """The first and the last day of a month."""
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def in_month(day: date, year: int, month: int) -> bool:
    first, last = month_bounds(year, month)
    return first <= day <= last
