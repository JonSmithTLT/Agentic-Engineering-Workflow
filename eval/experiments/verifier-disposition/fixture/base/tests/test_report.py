from datetime import date
from decimal import Decimal

from ledger.dates import in_month, parse_month
from ledger.entries import Entry
from ledger.report import monthly_summary, totals_by_category

ENTRIES = [
    Entry(date(2026, 1, 1), Decimal("1500.00"), "Rent"),
    Entry(date(2026, 1, 12), Decimal("31.10"), "Groceries"),
    Entry(date(2026, 1, 15), Decimal("20.00"), "Groceries"),
    Entry(date(2026, 2, 1), Decimal("1500.00"), "Rent"),
]


def test_totals_by_category():
    assert totals_by_category(ENTRIES) == {"Groceries": Decimal("51.10"), "Rent": Decimal("3000.00")}


def test_monthly_summary():
    summary = monthly_summary(ENTRIES, 2026, 1)
    assert summary["entries"] == 3
    assert summary["total"] == Decimal("1551.10")


def test_in_month():
    assert in_month(date(2026, 1, 1), 2026, 1)
    assert in_month(date(2026, 1, 15), 2026, 1)
    assert not in_month(date(2026, 2, 1), 2026, 1)


def test_parse_month():
    assert parse_month("2026-01") == (2026, 1)
