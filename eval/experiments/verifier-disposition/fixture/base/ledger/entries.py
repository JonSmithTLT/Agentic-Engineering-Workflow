"""Ledger entries, loaded from a CSV file with the columns date, amount, category, memo."""

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger.money import parse_amount


@dataclass(frozen=True)
class Entry:
    day: date
    amount: Decimal
    category: str
    memo: str = ""


def load_entries(path: str) -> list[Entry]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [Entry(date.fromisoformat(row["date"].strip()), parse_amount(row["amount"]),
                      row["category"].strip(), (row.get("memo") or "").strip())
                for row in csv.DictReader(fh)]
