"""The dogfood's hidden tests: each task's objective, checked independently of anything a model wrote or ran.

Never inside a repository a model works in. Run as ``python hidden.py <task> <tree>`` (the tree is the project to
judge: the integrated commit in AEW mode, the working tree in raw mode). Prints one JSON object:
``{"task", "passed", "checks": [{"name", "ok", "detail"}], "project_tests": bool}``. ``passed`` is every check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import traceback
from decimal import Decimal
from pathlib import Path

NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
D = Decimal


def cli(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(tree), "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, "-m", "ledger", *args], cwd=tree, capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=60, stdin=subprocess.DEVNULL, **NO_WINDOW)


def csv_file(rows: list[str]) -> str:
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="\n")
    fh.write("date,amount,category,memo\n" + "\n".join(rows) + "\n")
    fh.close()
    return fh.name


def t1(tree: Path):
    from ledger.money import format_amount as fmt
    yield "negative amount", fmt(D("-5")) == "-$5.00", fmt(D("-5"))
    yield "negative with thousands", fmt(D("-1234.5")) == "-$1,234.50", fmt(D("-1234.5"))
    yield "positive unchanged", fmt(D("1234.5")) == "$1,234.50", fmt(D("1234.5"))
    yield "zero", fmt(D("0")) == "$0.00", fmt(D("0"))
    refund = csv_file(["2026-03-02,-15.00,Groceries,Refund"])
    out = cli(tree, "summary", refund).stdout
    yield "report shows -$15.00", "Groceries: -$15.00" in out and "Total: -$15.00" in out, out[-300:]
    mixed = csv_file(["2026-03-01,40.00,Groceries,Market", "2026-03-02,-15.00,Groceries,Refund"])
    out = cli(tree, "summary", mixed).stdout
    yield "mixed report", "Groceries: $25.00" in out, out[-300:]


def t2(tree: Path):
    sample = str(tree / "data" / "sample.csv")
    res = cli(tree, "summary", sample, "--category", "groceries")
    yield ("category filter", res.returncode == 0 and "Groceries: $118.69" in res.stdout and
           "Total: $118.69" in res.stdout and "Rent" not in res.stdout, (res.returncode, res.stdout[-300:]))
    res = cli(tree, "summary", sample, "--month", "2026-01", "--category", "GROCERIES")
    yield ("with --month, any case", res.returncode == 0 and "Groceries: $54.50" in res.stdout and
           "Total: $54.50" in res.stdout, (res.returncode, res.stdout[-300:]))
    res = cli(tree, "summary", sample, "--category", "nope")
    yield ("unknown category: exit 2, known ones named", res.returncode == 2 and "Groceries" in res.stderr and
           "Rent" in res.stderr, (res.returncode, res.stderr[-300:]))
    res = cli(tree, "summary", sample)
    yield "unfiltered report unchanged", res.returncode == 0 and "Total: $4,754.94" in res.stdout, res.stdout[-300:]
    readme = (tree / "README.md").read_text(encoding="utf-8") if (tree / "README.md").exists() else ""
    yield "documented in README.md", "--category" in readme, None


def t3(tree: Path):
    from datetime import date

    from ledger.dates import in_month
    from ledger.entries import load_entries
    from ledger.report import monthly_summary
    for day in (date(2026, 1, 31), date(2025, 12, 31), date(2024, 2, 29), date(2026, 2, 28)):
        yield f"last day {day} is in its month", in_month(day, day.year, day.month), None
    yield "first of next month is not", not in_month(date(2026, 2, 1), 2026, 1), None
    yield "last day of previous month is not", not in_month(date(2025, 12, 31), 2026, 1), None
    entries = load_entries(str(tree / "data" / "sample.csv"))
    months = [monthly_summary(entries, y, m)["total"] for y, m in ((2025, 12), (2026, 1), (2026, 2))]
    yield "monthly totals add up to all rows", sum(months) == D("4754.94"), [str(m) for m in months]
    yield "January total", months[1] == D("1618.25"), str(months[1])


def t4(tree: Path):
    from ledger.money import parse_amount as parse
    for text, want in (("23.4", "23.40"), ("12.5", "12.50"), ("-0.5", "-0.50"), ("1,234.56", "1234.56"),
                       ("$7", "7.00"), ("-3.25", "-3.25")):
        got = parse(text)
        yield f"parse {text!r}", got == D(want), str(got)
    sample = str(tree / "data" / "sample.csv")
    out = cli(tree, "summary", sample, "--month", "2026-01").stdout
    yield "January report", "Groceries: $54.50" in out and "Total: $1,618.25" in out, out[-300:]
    out = cli(tree, "summary", sample).stdout
    yield "whole-file total", "Total: $4,754.94" in out, out[-300:]


def t5(tree: Path):
    from ledger.money import split_amount as split
    cent = D("0.01")
    yield "10.00 into 3", split(D("10.00"), 3) == [D("3.34"), D("3.33"), D("3.33")], split(D("10.00"), 3)
    yield "0.05 into 2", split(D("0.05"), 2) == [D("0.03"), D("0.02")], split(D("0.05"), 2)
    yield "0.01 into 3", split(D("0.01"), 3) == [D("0.01"), D("0.00"), D("0.00")], split(D("0.01"), 3)
    yield "one part", split(D("5.00"), 1) == [D("5.00")], split(D("5.00"), 1)
    for total, parts in ((D("100.00"), 7), (D("1234.56"), 9), (D("0.00"), 4), (D("9.00"), 3)):
        shares = split(total, parts)
        yield (f"{total} into {parts} adds up, whole cents", len(shares) == parts and sum(shares) == total
               and all(s == s.quantize(cent) for s in shares), [str(s) for s in shares])
    try:
        split(D("1.00"), 0)
        raised = False
    except ValueError:
        raised = True
    yield "parts < 1 raises ValueError", raised, None


TASKS = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t2}


def main() -> int:
    task, tree = sys.argv[1], Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(tree))
    os.chdir(tree)
    checks = []
    try:
        for name, ok, detail in TASKS[task](tree):
            checks.append({"name": name, "ok": bool(ok), "detail": None if ok else str(detail)[-300:]})
    except Exception:  # noqa: BLE001 - a crash is a failed check, with its traceback
        checks.append({"name": "no crash", "ok": False, "detail": traceback.format_exc()[-600:]})
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], cwd=tree,
                           capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL, **NO_WINDOW)
    print(json.dumps({"task": task, "passed": bool(checks) and all(c["ok"] for c in checks), "checks": checks,
                      "project_tests": tests.returncode == 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
