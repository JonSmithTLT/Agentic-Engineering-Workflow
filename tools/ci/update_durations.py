#!/usr/bin/env python3
"""Refresh tests/durations.json from lane reports (docs/implementation/testing-and-ci-strategy.md).

Durations only balance shards; they never decide which tests run. Prefer the nightly serial `reference`
reports (no xdist contention). Entries for tests no longer collected are dropped.

    python tools/ci/update_durations.py REPORT_DIR [REPORT_DIR ...] --out tests/durations.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DURATIONS_SCHEMA = "aew/test-durations/v1"
REPORT_SCHEMA = "aew/lane-report/v1"


def merge(current: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    platforms: dict[str, dict[str, float]] = {k: dict(v) for k, v in (current.get("platforms") or {}).items()}
    collected: dict[str, set[str]] = {}
    for r in reports:
        table = platforms.setdefault(r["platform"], {})
        collected.setdefault(r["platform"], set()).update(r["collected"])
        for nid, res in r["results"].items():
            if res["outcome"] != "skipped":
                table[nid] = round(float(res["duration"]), 2)
    for platform, ids in collected.items():
        platforms[platform] = {n: d for n, d in platforms[platform].items() if n in ids}
    return {"schema": DURATIONS_SCHEMA,
            "platforms": {p: dict(sorted(t.items())) for p, t in sorted(platforms.items())}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reports", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    reports = [json.loads(p.read_text(encoding="utf-8")) for d in args.reports for p in sorted(d.rglob("*.json"))]
    reports = [r for r in reports if r.get("schema") == REPORT_SCHEMA]
    current = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    args.out.write_text(json.dumps(merge(current, reports), indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{args.out}: {', '.join(sorted({r['platform'] for r in reports}))} updated from {len(reports)} report(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
