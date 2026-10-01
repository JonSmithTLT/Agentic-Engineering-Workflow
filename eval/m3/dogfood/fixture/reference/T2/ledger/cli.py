"""The `ledger` command line: `python -m ledger summary FILE [--month YYYY-MM] [--category NAME]`."""

import argparse
import sys
from decimal import Decimal

from ledger.dates import parse_month
from ledger.entries import load_entries
from ledger.money import format_amount
from ledger.report import monthly_summary, totals_by_category


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger", description="Summaries of a ledger CSV file.")
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summary", help="totals per category")
    summary.add_argument("file", help="the ledger CSV (date, amount, category, memo)")
    summary.add_argument("--month", help="only this month's entries (YYYY-MM)")
    summary.add_argument("--category", help="only this category's entries (any case)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    entries = load_entries(args.file)
    if args.category:
        known = sorted({e.category for e in entries})
        wanted = args.category.casefold()
        if wanted not in {c.casefold() for c in known}:
            print(f"ledger: unknown category {args.category!r}; known: {', '.join(known)}", file=sys.stderr)
            return 2
        entries = [e for e in entries if e.category.casefold() == wanted]
    if args.month:
        try:
            year, month = parse_month(args.month)
        except ValueError as exc:
            parser.error(str(exc))
        summary = monthly_summary(entries, year, month)
        title = f"Summary for {summary['month']} ({summary['entries']} entries)"
        totals, total = summary["totals"], summary["total"]
    else:
        totals = totals_by_category(entries)
        total = sum(totals.values(), Decimal("0"))
        title = f"Summary ({len(entries)} entries)"
    print(title)
    for category, amount in totals.items():
        print(f"  {category}: {format_amount(amount)}")
    print(f"  Total: {format_amount(total)}")
    return 0
