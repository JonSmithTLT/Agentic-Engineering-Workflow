"""Totals for reports."""

from collections import defaultdict
from decimal import Decimal

from ledger.dates import in_month
from ledger.entries import Entry


def totals_by_category(entries: list[Entry]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for entry in entries:
        totals[entry.category] += entry.amount
    return dict(sorted(totals.items()))


def month_entries(entries: list[Entry], year: int, month: int) -> list[Entry]:
    return [e for e in entries if in_month(e.day, year, month)]


def monthly_summary(entries: list[Entry], year: int, month: int) -> dict:
    chosen = month_entries(entries, year, month)
    totals = totals_by_category(chosen)
    return {"month": f"{year:04d}-{month:02d}", "entries": len(chosen), "totals": totals,
            "total": sum(totals.values(), Decimal("0"))}
