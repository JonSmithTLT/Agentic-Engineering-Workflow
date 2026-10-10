#!/usr/bin/env python3
"""The coverage premise of the ``fast`` tier, measured in the same run (CI plan v7 §5).

The ratchet's total is the Linux fast lane plus the Linux heavy lanes. In the ``fast`` tier the heavy lanes'
footprint is unchanged (``src``, helpers, fixtures and every heavy test module are identical in the tested tree and
its base, and the guards in ``tests/unit/test_ci_tools.py`` keep heavy tests from reading anything a ``fast``-tier
change may touch), so the total can fall only through the fast lane: a fast test deleted, skipped, narrowed, moved to
``serial`` (which runs without coverage) or fed different input.

``fastbase`` runs the whole fast lane at the base tip (``GITHUB_SHA^1``) under coverage; ``core (ubuntu-latest)``
runs it at the merge commit. Each side is combined with ``coverage_gate.combine``, which applies
``[tool.coverage.paths]``, and keyed by its repository-relative path under ``src/aew``. Every base line and arc must be
covered by this run's fast lane; an empty difference proves that the fast lane's footprint, and so the ratchet's
total, did not fall. A base that did not pass or left no data means the premise is unknown.

    python tools/ci/coverage_premise.py --base fastbase-data --head coverage-data/coverage-core-Linux
        [--base-result success] [--rcfile pyproject.toml] [--summary FILE] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage_gate  # noqa: E402  (tools/ci/coverage_gate.py: the ratchet's combine, with the path remapping)

SCHEMA = "aew/coverage-premise/v1"
PACKAGE = "src/aew/"
UNKNOWN = "base footprint unknown ({why}): add `full-ci`, then Re-run all jobs."
LOSS = ("this change may lower coverage: add `full-ci`, then Re-run all jobs; the full run's ratchet decides.")

Footprint = dict[str, tuple[set[int], set[tuple[int, int]]]]


class Unknown(Exception):
    """The premise cannot be evaluated: the comparison needs both sides' data."""


def repo_relative(filename: str) -> str | None:
    """``src/aew/<module>`` for a measured file, wherever it was recorded (a runner checkout, the base worktree
    under ``$RUNNER_TEMP/base``, a Windows path); ``None`` for a file outside the package."""
    norm = filename.replace("\\", "/")
    at = norm.find(PACKAGE)
    return None if at < 0 else norm[at:]


def footprint(data_dir: Path, rcfile: Path) -> Footprint:
    """The lines and arcs each ``src/aew`` file has in the data under ``data_dir``, after remapping. The data are
    copied first: ``combine`` writes its result next to its inputs, and the ratchet later reads the same directory."""
    files = [p for p in sorted(data_dir.rglob(".coverage*")) if p.is_file()] if data_dir.is_dir() else []
    if not files:
        raise Unknown(f"no coverage data under {data_dir}")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows: SQLite
        work = Path(tmp)
        for i, f in enumerate(files):
            shutil.copyfile(f, work / f".coverage.{i}.{f.name.lstrip('.')}")
        data = coverage_gate.combine(work, rcfile).get_data()
        result: Footprint = {}
        for measured in data.measured_files():
            rel = repo_relative(measured)
            if rel is None:
                continue
            lines, arcs = result.setdefault(rel, (set(), set()))
            lines.update(data.lines(measured) or ())
            arcs.update(data.arcs(measured) or ())
    return result


def lost(base: Footprint, head: Footprint) -> dict[str, dict[str, list[Any]]]:
    """What the base covered and this run does not, per file."""
    missing: dict[str, dict[str, list[Any]]] = {}
    for rel, (lines, arcs) in sorted(base.items()):
        head_lines, head_arcs = head.get(rel, (set(), set()))
        gone_lines, gone_arcs = sorted(lines - head_lines), sorted(arcs - head_arcs)
        if gone_lines or gone_arcs:
            missing[rel] = {"lines": gone_lines, "arcs": [list(a) for a in gone_arcs]}
    return missing


def evaluate(base_dir: Path, head_dir: Path, rcfile: Path, base_result: str | None = None) -> dict[str, Any]:
    """The premise's result: ``holds``, ``loss`` (with what was lost) or ``unknown`` (with why)."""
    if base_result is not None and base_result != "success":
        return {"schema": SCHEMA, "result": "unknown", "message": UNKNOWN.format(why=f"`fastbase`: {base_result}")}
    try:
        base = footprint(base_dir, rcfile)
    except (Unknown, SystemExit) as exc:
        return {"schema": SCHEMA, "result": "unknown", "message": UNKNOWN.format(why=f"`fastbase`: {exc}")}
    try:
        head = footprint(head_dir, rcfile)
    except (Unknown, SystemExit) as exc:
        return {"schema": SCHEMA, "result": "unknown",
                "message": f"this run's fast-lane coverage is missing ({exc}): add `full-ci`, then Re-run all jobs."}
    missing = lost(base, head)
    if missing:
        return {"schema": SCHEMA, "result": "loss", "message": LOSS, "lost": missing}
    return {"schema": SCHEMA, "result": "holds", "files": len(base)}


def _ranges(numbers: list[int]) -> str:
    groups: list[list[int]] = []
    for n in numbers:
        if groups and groups[-1][1] == n - 1:
            groups[-1][1] = n
        else:
            groups.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in groups)


def summary(result: dict[str, Any]) -> str:
    lines = ["## Coverage premise (the `fast` tier; plan v7 §5)", ""]
    if result["result"] == "holds":
        lines.append(f"**HOLDS**: every line and arc the base's fast lane covered in {result['files']} file(s) of "
                     "`src/aew` is covered by this run's fast lane.")
    else:
        lines.append(f"**{result['result'].upper()}**: {result['message']}")
        for rel, gone in sorted((result.get("lost") or {}).items())[:40]:
            lines.append(f"- `{rel}`: lines {_ranges(gone['lines']) or '-'}; arcs "
                         + (", ".join(f"{a}->{b}" for a, b in gone["arcs"][:20]) or "-"))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--base", type=Path, required=True, help="fastbase's coverage data (artifact fastbase-coverage)")
    ap.add_argument("--head", type=Path, required=True, help="this run's Linux fast-lane data (coverage-core-Linux)")
    ap.add_argument("--base-result", help="the fastbase job's result: anything but success means unknown")
    ap.add_argument("--rcfile", type=Path, default=Path("pyproject.toml"))
    ap.add_argument("--summary", type=Path, help="append the Markdown summary here (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--out", type=Path, help="write the result as JSON here")
    args = ap.parse_args(argv)
    result = evaluate(args.base, args.head, args.rcfile, args.base_result)
    text = summary(result)
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return 0 if result["result"] == "holds" else 1


if __name__ == "__main__":
    sys.exit(main())
