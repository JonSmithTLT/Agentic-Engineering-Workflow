#!/usr/bin/env python3
"""Coverage ratchet over CI's coverage data (register E2 and E23; testing-and-ci-strategy.md §3, "Coverage").

Combines the coverage data files the Linux and Windows lanes upload (every `aew` CLI, supervisor, broker and xdist
worker each write one), reports line and branch coverage of ``src/aew`` in total and per package, and fails when the
total line or branch coverage falls below the committed baseline (``tests/coverage-baseline.json``) by more than the
tolerance. Coverage may rise freely; raising the baseline is a deliberate commit (``--update``), never automatic.

Each job's data sits in a directory named ``coverage-<lane>-<shard>-<OS>`` (``Linux`` or ``Windows``). The total
combines both operating systems and excludes neither OS's marked code, because a block marked
``# pragma: windows-only`` or ``# pragma: posix-only`` runs, and is measured, on its own OS. The summary also reports
each OS alone with the other OS's marked code excluded, and lists every file that holds marked code. Data that is not
split by OS (a local run) is measured as one view with the configured exclusion (``AEW_COVERAGE_OTHER_OS``).

    python tools/ci/coverage_gate.py DATA_DIR --baseline tests/coverage-baseline.json [--summary FILE] [--update]
        [--require Linux,Windows]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import coverage

SCHEMA = "aew/coverage-baseline/v1"
TOLERANCE = 0.3  # percentage points: subprocess timing makes a few branches nondeterministic
PLATFORMS = ("Linux", "Windows")
OTHER_OS_ENV = "AEW_COVERAGE_OTHER_OS"  # read by [tool.coverage.report] exclude_also in pyproject.toml
OTHER_OS = {"Linux": "windows", "Windows": "posix"}  # the marker each OS's own view excludes
NEITHER = "none"  # matches no marker: the combined view excludes nothing
MARKER = re.compile(r"# pragma: (windows|posix)-only")
MEASURED = {
    ("Linux", "Windows"): "Linux and Windows lanes combined (fast, integration, acceptance, regression, adversarial); "
                          "serial runs without coverage",
    (): "Linux lanes (fast, integration, acceptance, regression, adversarial); serial runs without coverage",
}


def platform_of(path: Path, data_dir: Path) -> str | None:
    """The OS a data file came from, read from the name of its artifact directory (``coverage-...-Linux``)."""
    parts = path.relative_to(data_dir).parts
    for platform in PLATFORMS:
        if len(parts) > 1 and parts[0].endswith(f"-{platform}"):
            return platform
    return None


def data_files(data_dir: Path) -> dict[str | None, list[Path]]:
    found: dict[str | None, list[Path]] = defaultdict(list)
    for p in sorted(data_dir.rglob(".coverage*")):
        if p.is_file() and not p.name.startswith(".coverage.combined"):
            found[platform_of(p, data_dir)].append(p)
    return found


def combine(files: list[Path], name: str, workdir: Path, rcfile: Path, other_os: str | None) -> coverage.Coverage:
    """Combine ``files`` into one data file. ``other_os`` is the marker the report excludes (None: as configured)."""
    if not files:
        raise SystemExit(f"no coverage data for {name}")
    previous = os.environ.get(OTHER_OS_ENV)
    if other_os is not None:
        os.environ[OTHER_OS_ENV] = other_os
    try:  # coverage reads its exclusion patterns, with the environment in them, when it is created
        cov = coverage.Coverage(data_file=str(workdir / f".coverage.combined-{name}"), config_file=str(rcfile))
    finally:
        if previous is None:
            os.environ.pop(OTHER_OS_ENV, None)
        else:
            os.environ[OTHER_OS_ENV] = previous
    cov.combine([str(f) for f in files], keep=True)
    cov.save()
    return cov


def measure(cov: coverage.Coverage, workdir: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Line and branch numbers of src/aew: in total and per package, and per file (coverage's public JSON report)."""
    out = workdir / f"coverage-{name}.json"
    cov.json_report(outfile=str(out), ignore_errors=True)
    files = json.loads(out.read_text(encoding="utf-8"))["files"]
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # statements, covered, branches, covered
    per_file: dict[str, list[int]] = {}
    for filename, info in files.items():
        norm = filename.replace("\\", "/")
        rel = norm.split("src/aew/", 1)[1] if "src/aew/" in norm else None
        if rel is None:
            continue
        package = "aew/" + (rel.split("/", 1)[0] if "/" in rel else "(top)")
        s = info["summary"]
        counts = [s["num_statements"], s["covered_lines"], s.get("num_branches", 0), s.get("covered_branches", 0)]
        per_file[rel] = counts
        for key in (package, "TOTAL"):
            t = totals[key]
            for i, n in enumerate(counts):
                t[i] += n

    def pct(covered: int, total: int) -> float:
        return round(100.0 * covered / total, 2) if total else 100.0

    def shape(table: dict[str, list[int]]) -> dict[str, Any]:
        return {name: {"line": pct(c, s), "branch": pct(cb, b), "statements": s, "branches": b}
                for name, (s, c, b, cb) in sorted(table.items())}

    return shape(totals), shape(per_file)


def platform_code(source: Path) -> dict[str, set[str]]:
    """Files under src/aew that hold code marked for one operating system, and which markers they hold."""
    marked: dict[str, set[str]] = {}
    for path in sorted(source.rglob("*.py")):
        kinds = set(MARKER.findall(path.read_text(encoding="utf-8", errors="replace")))
        if kinds:
            marked[path.relative_to(source).as_posix()] = kinds
    return marked


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header), *("| " + " | ".join(r) + " |" for r in rows)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--rcfile", type=Path, default=Path("pyproject.toml"))
    ap.add_argument("--source", type=Path, default=Path("src/aew"), help="the package, for its platform markers")
    ap.add_argument("--summary", type=Path)
    ap.add_argument("--require", default="", help="comma-separated OSes whose data must be present (Linux,Windows)")
    ap.add_argument("--update", action="store_true", help="write the measured totals as the new baseline")
    args = ap.parse_args(argv)

    found = data_files(args.data_dir)
    if not found:
        raise SystemExit(f"no coverage data under {args.data_dir}")
    problems = [f"{p}: no coverage data (a {p} job did not run or did not upload it)"
                for p in (x for x in args.require.split(",") if x) if not found.get(p)]
    by_os = {p: found[p] for p in PLATFORMS if found.get(p)}
    workdir = args.data_dir
    if by_os:
        everything = [f for files in found.values() for f in files]
        combined, files_all = measure(combine(everything, "all", workdir, args.rcfile, NEITHER), workdir, "all")
        views = {p: measure(combine(fs, p, workdir, args.rcfile, OTHER_OS[p]), workdir, p) for p, fs in by_os.items()}
        measured = MEASURED[tuple(by_os)] if tuple(by_os) in MEASURED else MEASURED[()]
        title = f"Coverage ({' and '.join(by_os)} lanes combined, src/aew, subprocesses included)"
    else:  # data that is not split by OS: one view, as configured
        everything = found[None]
        combined, files_all = measure(combine(everything, "all", workdir, args.rcfile, None), workdir, "all")
        views, measured = {}, MEASURED[()]
        title = "Coverage (src/aew, subprocesses included)"

    total = combined["TOTAL"]
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else None
    if baseline:
        for kind in ("line", "branch"):
            if total[kind] + TOLERANCE < baseline[kind]:
                problems.append(f"{kind} coverage {total[kind]:.2f}% is below the baseline {baseline[kind]:.2f}%")

    lines = [f"## {title}", ""]
    lines += table(["Package", "Line", "Branch", "Statements", "Branches"],
                   [[name, f"{n['line']:.1f}%", f"{n['branch']:.1f}%", str(n["statements"]), str(n["branches"])]
                    for name, n in combined.items()])
    if views:
        lines += ["", "### Each OS alone, the other OS's marked code excluded", ""]
        header = ["Package", *(f"{p} line" for p in views), *(f"{p} branch" for p in views)]
        rows = []
        for name in combined:
            rows.append([name, *(f"{v[0][name]['line']:.1f}%" if name in v[0] else "-" for v in views.values()),
                         *(f"{v[0][name]['branch']:.1f}%" if name in v[0] else "-" for v in views.values())])
        lines += table(header, rows)
        marked = platform_code(args.source)
        if marked:
            lines += ["", "### Files with Windows-only or POSIX-only code", ""]
            lines += table(["File", "Marked for", "Combined line", *(f"{p} line" for p in views)],
                           [[f"`{rel}`", ", ".join(sorted(kinds)),
                             f"{(files_all.get(rel) or {'line': 0.0})['line']:.1f}%",
                             *(f"{(v[1].get(rel) or {'line': 0.0})['line']:.1f}%" for v in views.values())]
                            for rel, kinds in marked.items()])
    if baseline:
        lines += ["", f"Baseline: line {baseline['line']:.2f}%, branch {baseline['branch']:.2f}% "
                      f"(tolerance {TOLERANCE} points; {baseline.get('measured', 'measured as above')})."]
    lines += [""] + ([f"**Coverage dropped:** {p}" for p in problems] or ["Coverage holds the baseline."])
    text = "\n".join(lines) + "\n"
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(text)
    if args.update:
        args.baseline.write_text(json.dumps({"schema": SCHEMA, "line": total["line"], "branch": total["branch"],
                                             "measured": measured}, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {args.baseline}")
        return 0
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
