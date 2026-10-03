#!/usr/bin/env python3
"""Coverage ratchet over CI's coverage data (register E2; testing-and-ci-strategy.md §3, "Coverage").

Combines the coverage data files the Linux lanes upload (every `aew` CLI, supervisor, broker and xdist worker each
write one), reports line and branch coverage of ``src/aew`` in total and per package, and fails when the total line
or branch coverage falls below the committed baseline (``tests/coverage-baseline.json``) by more than the tolerance.
Coverage may rise freely; raising the baseline is a deliberate commit (``--update``), never automatic.

    python tools/ci/coverage_gate.py DATA_DIR --baseline tests/coverage-baseline.json [--summary FILE] [--update]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import coverage

SCHEMA = "aew/coverage-baseline/v1"
TOLERANCE = 0.3  # percentage points: subprocess timing makes a few branches nondeterministic


def combine(data_dir: Path, rcfile: Path) -> coverage.Coverage:
    files = [str(p) for p in sorted(data_dir.rglob(".coverage*")) if p.is_file()]
    if not files:
        raise SystemExit(f"no coverage data under {data_dir}")
    cov = coverage.Coverage(data_file=str(data_dir / ".coverage.combined"), config_file=str(rcfile))
    cov.combine(files, keep=True)
    cov.save()
    return cov


def measure(cov: coverage.Coverage, workdir: Path) -> dict[str, Any]:
    """Line and branch numbers of src/aew in total and per package, from coverage's public JSON report."""
    out = workdir / "coverage.json"
    cov.json_report(outfile=str(out), ignore_errors=True)
    files = json.loads(out.read_text(encoding="utf-8"))["files"]
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # statements, covered, branches, covered
    for filename, info in files.items():
        norm = filename.replace("\\", "/")
        rel = norm.split("src/aew/", 1)[1] if "src/aew/" in norm else None
        if rel is None:
            continue
        package = "aew/" + (rel.split("/", 1)[0] if "/" in rel else "(top)")
        s = info["summary"]
        for key in (package, "TOTAL"):
            t = totals[key]
            t[0] += s["num_statements"]
            t[1] += s["covered_lines"]
            t[2] += s.get("num_branches", 0)
            t[3] += s.get("covered_branches", 0)

    def pct(covered: int, total: int) -> float:
        return round(100.0 * covered / total, 2) if total else 100.0

    return {name: {"line": pct(c, s), "branch": pct(cb, b), "statements": s, "branches": b}
            for name, (s, c, b, cb) in sorted(totals.items())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--rcfile", type=Path, default=Path("pyproject.toml"))
    ap.add_argument("--summary", type=Path)
    ap.add_argument("--update", action="store_true", help="write the measured totals as the new baseline")
    args = ap.parse_args()

    numbers = measure(combine(args.data_dir, args.rcfile), args.data_dir)
    total = numbers["TOTAL"]
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else None
    problems = []
    if baseline:
        for kind in ("line", "branch"):
            if total[kind] + TOLERANCE < baseline[kind]:
                problems.append(f"{kind} coverage {total[kind]:.2f}% is below the baseline {baseline[kind]:.2f}%")

    lines = ["## Coverage (Linux lanes, src/aew, subprocesses included)", "",
             "| Package | Line | Branch | Statements | Branches |", "|---|---|---|---|---|"]
    for name, n in numbers.items():
        lines.append(f"| {name} | {n['line']:.1f}% | {n['branch']:.1f}% | {n['statements']} | {n['branches']} |")
    if baseline:
        lines += ["", f"Baseline: line {baseline['line']:.2f}%, branch {baseline['branch']:.2f}% "
                      f"(tolerance {TOLERANCE} points)."]
    lines += [""] + ([f"**Coverage dropped:** {p}" for p in problems] or ["Coverage holds the baseline."])
    text = "\n".join(lines) + "\n"
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(text)
    if args.update:
        args.baseline.write_text(json.dumps({"schema": SCHEMA, "line": total["line"], "branch": total["branch"],
                                             "measured": "Linux lanes (fast, integration, acceptance, regression, "
                                                         "adversarial); serial runs without coverage"},
                                            indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {args.baseline}")
        return 0
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
