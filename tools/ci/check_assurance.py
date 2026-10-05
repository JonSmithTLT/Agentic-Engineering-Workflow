#!/usr/bin/env python3
"""Merge-blocking assurance check over CI lane reports (docs/implementation/testing-and-ci-strategy.md).

For every required platform it proves, from the lane reports written by ``pytest --lane-report``, that:

* every job collected the same test set;
* every collected test ran exactly once across all lanes and shards;
* every shard of a sharded lane reported (a dropped shard is a problem even before its tests show as missing);
* no session failed (including the isolation guard) and no test failed or errored;
* the skipped tests are exactly the pinned platform skips (``tests/platform-skips.yaml``);
* no xfail/xpass occurred unless pinned there.

It also writes a Markdown summary (per-lane counts and timings, slowest tests).

    python tools/ci/check_assurance.py REPORT_DIR --skips tests/platform-skips.yaml --require linux,win32
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

REPORT_SCHEMA = "aew/lane-report/v1"
SKIPS_SCHEMA = "aew/platform-skips/v1"


def load_reports(root: Path) -> list[dict[str, Any]]:
    reports = []
    for path in sorted(root.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") == REPORT_SCHEMA:
            data["_source"] = str(path.relative_to(root))
            reports.append(data)
    return reports


def load_expectations(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("schema") != SKIPS_SCHEMA:
        raise SystemExit(f"{path}: expected schema {SKIPS_SCHEMA}")
    return data


def _label(r: dict[str, Any]) -> str:
    return f"{r['platform']}/{r.get('lane') or 'all'}" + (f" shard {r['shard']}" if r.get("shard") else "")


def shard_gaps(group: list[dict[str, Any]]) -> list[str]:
    """Shards that are missing or disagree about the shard count, per lane (``k/N`` specs from the reports)."""
    specs: dict[str | None, list[str]] = defaultdict(list)
    for r in group:
        if r.get("shard"):
            specs[r.get("lane")].append(r["shard"])
    gaps = []
    for lane, listed in sorted(specs.items(), key=lambda kv: kv[0] or ""):
        parsed = [tuple(int(x) for x in spec.split("/")) for spec in listed]
        counts = sorted({n for _, n in parsed})
        name = lane or "all"
        if len(counts) > 1:
            gaps.append(f"{name}: shard reports disagree on the shard count ({', '.join(sorted(listed))})")
            continue
        gaps += [f"{name}: shard {k}/{counts[0]} has no report (its job did not run, failed to start or did not upload)"
                 for k in range(1, counts[0] + 1) if k not in {k for k, _ in parsed}]
    return gaps


def check(reports: list[dict[str, Any]], expectations: dict[str, Any],
          required: list[str]) -> tuple[list[str], dict[str, Any]]:
    """Return (problems, per-platform facts). No problems means the platform's assurance envelope is complete."""
    problems: list[str] = []
    facts: dict[str, Any] = {}
    by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in reports:
        by_platform[r["platform"]].append(r)
    for platform in required:
        if platform not in by_platform:
            problems.append(f"{platform}: no lane reports (a job did not run or did not upload its report)")
    for platform, group in sorted(by_platform.items()):
        pinned_skips = (expectations.get("skipped") or {}).get(platform) or {}
        pinned_xfail = (expectations.get("xfail") or {}).get(platform) or {}
        problems += [f"{platform}: {gap}" for gap in shard_gaps(group)]
        collected_sets = {frozenset(r["collected"]) for r in group}
        if len(collected_sets) > 1:
            sizes = ", ".join(f"{_label(r)}={len(r['collected'])}" for r in group)
            problems.append(f"{platform}: jobs collected different test sets ({sizes})")
        collected = set().union(*collected_sets)
        runs = Counter(nid for r in group for nid in r["results"])
        for r in group:
            if r.get("exitstatus") != 0:
                problems.append(f"{platform}: session {_label(r)} exited {r.get('exitstatus')} "
                                "(failed tests, a usage error, or the isolation guard)")
        for nid in sorted(collected - set(runs)):
            problems.append(f"{platform}: never ran: {nid}")
        for nid in sorted(set(runs) - collected):
            problems.append(f"{platform}: ran but was not collected: {nid}")
        for nid, n in sorted(runs.items()):
            if n > 1:
                problems.append(f"{platform}: ran {n} times: {nid}")
        outcomes: dict[str, str] = {}
        for r in group:
            for nid, res in r["results"].items():
                outcomes[nid] = res["outcome"]
                if res["outcome"] in ("failed", "error"):
                    problems.append(f"{platform}: {res['outcome']}: {nid} ({_label(r)})")
                elif res["outcome"] == "skipped" and nid not in pinned_skips:
                    problems.append(f"{platform}: unexpected skip: {nid} (pin it in platform-skips.yaml with a reason, "
                                    "or make it run)")
                elif res["outcome"] in ("xfailed", "xpassed") and nid not in pinned_xfail:
                    problems.append(f"{platform}: {res['outcome']} but not pinned: {nid}")
        for nid in sorted(pinned_skips):
            if nid not in collected:
                problems.append(f"{platform}: pinned skip no longer exists: {nid}")
            elif outcomes.get(nid) not in (None, "skipped"):
                problems.append(f"{platform}: pinned skip now {outcomes[nid]}: {nid} "
                                "(remove it from platform-skips.yaml)")
        facts[platform] = {"collected": len(collected), "ran": sum(runs.values()),
                           "outcomes": Counter(outcomes.values()), "jobs": group}
    return problems, facts


def summary(problems: list[str], facts: dict[str, Any]) -> str:
    lines = ["## Test assurance", ""]
    lines.append("**PASS**: every collected test ran exactly once and passed (pinned platform skips excepted)."
                 if not problems else f"**FAIL**: {len(problems)} problem(s).")
    for platform, f in sorted(facts.items()):
        lines += ["", f"### {platform}: {f['collected']} collected, {f['ran']} run, "
                      + ", ".join(f"{n} {o}" for o, n in sorted(f["outcomes"].items())), "",
                  "| lane | shard | tests | test time (s) | session wall (s) | xdist | python |",
                  "|---|---|---|---|---|---|---|"]
        for r in sorted(f["jobs"], key=lambda r: (r.get("lane") or "", r.get("shard") or "")):
            test_time = sum(v["duration"] for v in r["results"].values())
            lines.append(f"| {r.get('lane') or 'all'} | {r.get('shard') or '-'} | {len(r['results'])} | "
                         f"{test_time:.0f} | {r.get('wall_s', 0):.0f} | {r.get('xdist_workers') or '-'} | "
                         f"{r.get('python')} |")
        slow = sorted(((v["duration"], nid) for r in f["jobs"] for nid, v in r["results"].items()), reverse=True)[:10]
        lines += ["", "<details><summary>slowest tests</summary>", ""]
        lines += [f"- {d:.1f}s `{nid}`" for d, nid in slow]
        lines += ["", "</details>"]
    if problems:
        lines += ["", "### Problems", ""] + [f"- {p}" for p in problems]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reports", type=Path, help="directory searched recursively for lane reports")
    ap.add_argument("--skips", type=Path, required=True, help="tests/platform-skips.yaml")
    ap.add_argument("--require", default="linux,win32", help="comma-separated platforms that must be present")
    ap.add_argument("--summary", type=Path, help="append the Markdown summary here (e.g. $GITHUB_STEP_SUMMARY)")
    args = ap.parse_args(argv)
    problems, facts = check(load_reports(args.reports), load_expectations(args.skips),
                            [p for p in args.require.split(",") if p])
    text = summary(problems, facts)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Annotations show on the pull request's checks page (GitHub keeps at most 10 errors per step).
        for platform, f in sorted(facts.items()):
            print(f"::notice title=assurance {platform}::{f['collected']} collected, {f['ran']} run, "
                  + ", ".join(f"{n} {o}" for o, n in sorted(f["outcomes"].items())))
        for p in problems[:9]:
            print(f"::error title=assurance::{p}")
        if len(problems) > 9:
            print(f"::error title=assurance::... and {len(problems) - 9} more problem(s); see the job summary")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
