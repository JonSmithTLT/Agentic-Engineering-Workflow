#!/usr/bin/env python3
"""Refresh tests/durations.json from lane reports (docs/implementation/testing-and-ci-strategy.md).

Durations only balance shards; they never decide which tests run. Prefer the nightly serial `reference`
reports (no xdist contention); a full green `main` run's lane reports do when the nightly is stale.
Entries for tests no longer collected are dropped.

    python tools/ci/update_durations.py REPORT_DIR [REPORT_DIR ...] --out tests/durations.json

With ``--history``, it keeps the rolling history instead (register E44): every green push run on `main` adds its
reports, each test keeps its last :data:`KEEP` durations, and ``--out`` is written as the median of them, the table
the shards balance on. The history also keeps what ``shard_plan.py`` sizes the lanes from: the lane each test ran in,
each platform's xdist workers, and each lane's time outside its tests. When the history is missing or unreadable it
starts from ``--seed`` (the committed table).

    python tools/ci/update_durations.py REPORT_DIR --history history.json --seed tests/durations.json \
        --out durations.json --run-label "<run id>/<attempt> <sha>"
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

DURATIONS_SCHEMA = "aew/test-durations/v1"
HISTORY_SCHEMA = "aew/test-durations-history/v1"
REPORT_SCHEMA = "aew/lane-report/v1"
AUTOPSY_DIR = "autopsy"  # a hang's autopsy in a report directory is never a lane report (check_assurance.py)
# How many green `main` runs a test's duration is the median of: enough that one slow runner does not move the
# table, few enough that a test made slower or faster shows within a working day of pushes (E44).
KEEP = 5


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


def seed_history(seed: dict[str, Any]) -> dict[str, Any]:
    """A history whose one observation per test is the committed table's: the start, before any run is kept."""
    return {"schema": HISTORY_SCHEMA, "runs": [],
            "platforms": {p: {n: [float(d)] for n, d in t.items()} for p, t in (seed.get("platforms") or {}).items()},
            "lanes": {}, "workers": {}, "overhead": {}}


def load_history(path: Path, seed: dict[str, Any]) -> dict[str, Any]:
    """The history at ``path``, or one seeded from ``seed`` when it is missing, unreadable or of another schema: a
    history only balances shards, so starting again is always safe."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return seed_history(seed)
    if not isinstance(data, dict) or data.get("schema") != HISTORY_SCHEMA:
        return seed_history(seed)
    return data


def outside_tests_s(report: dict[str, Any]) -> float | None:
    """A session's wall clock less the time its tests account for: their seconds over its xdist workers, or its
    longest test if that is more. Collection, worker start and an uneven tail are what is left."""
    durations = [float(res["duration"]) for res in report["results"].values()]
    if not durations or report.get("wall_s") is None:
        return None
    workers = report.get("xdist_workers") or 1
    return max(0.0, float(report["wall_s"]) - max(sum(durations) / workers, max(durations)))


def merge_history(history: dict[str, Any], reports: list[dict[str, Any]], label: str = "",
                  keep: int = KEEP) -> dict[str, Any]:
    """Add one green run's ``reports`` to ``history``: each test's duration (skips excepted) joins its last ``keep``;
    tests no longer collected on a platform are dropped; the lanes, workers and time outside the tests are this run's.
    """
    out = json.loads(json.dumps(history))  # a deep copy: the caller's history is left as it was
    out["schema"] = HISTORY_SCHEMA
    out["runs"] = ([*out.get("runs", []), label] if label else list(out.get("runs", [])))[-keep:]
    collected: dict[str, set[str]] = {}
    lanes: dict[str, dict[str, str]] = {}
    workers: dict[str, int] = {}
    outside: dict[str, dict[str, float]] = {}
    for r in reports:
        platform = r["platform"]
        table = out.setdefault("platforms", {}).setdefault(platform, {})
        collected.setdefault(platform, set()).update(r["collected"])
        lanes.setdefault(platform, {}).update(r.get("lanes") or {})
        if r.get("xdist_workers"):
            workers[platform] = max(workers.get(platform, 0), int(r["xdist_workers"]))
        spent = outside_tests_s(r)
        if spent is not None:
            per_lane = outside.setdefault(platform, {})
            per_lane[r["lane"]] = max(per_lane.get(r["lane"], 0.0), spent)
        for nid, res in r["results"].items():
            if res["outcome"] != "skipped":
                table[nid] = [*table.get(nid, []), round(float(res["duration"]), 2)][-keep:]
    for platform, ids in collected.items():
        out["platforms"][platform] = {n: d for n, d in out["platforms"][platform].items() if n in ids}
        if lanes.get(platform):
            out.setdefault("lanes", {})[platform] = dict(sorted(lanes[platform].items()))
    for platform, n in workers.items():
        out.setdefault("workers", {})[platform] = n
    for platform, per_lane in outside.items():
        kept = out.setdefault("overhead", {}).setdefault(platform, {})
        for lane, spent in per_lane.items():
            kept[lane] = [*kept.get(lane, []), round(spent, 1)][-keep:]
    out["platforms"] = {p: dict(sorted(t.items())) for p, t in sorted(out["platforms"].items())}
    return out


def table(history: dict[str, Any]) -> dict[str, Any]:
    """The durations table the shards balance on: each test's median over its kept durations."""
    return {"schema": DURATIONS_SCHEMA,
            "platforms": {p: {n: round(statistics.median(d), 2) for n, d in sorted(t.items()) if d}
                          for p, t in sorted((history.get("platforms") or {}).items())}}


def load_reports(dirs: list[Path]) -> list[dict[str, Any]]:
    reports = [json.loads(p.read_text(encoding="utf-8")) for d in dirs for p in sorted(d.rglob("*.json"))
               if AUTOPSY_DIR not in p.relative_to(d).parts]
    return [r for r in reports if r.get("schema") == REPORT_SCHEMA]


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("reports", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--history", type=Path, help="the rolling history to add this run to (read, then rewritten)")
    ap.add_argument("--seed", type=Path, help="the table a missing history starts from (tests/durations.json)")
    ap.add_argument("--run-label", default="", help="recorded in the history's last runs")
    args = ap.parse_args(argv)
    reports = load_reports(args.reports)
    platforms = ", ".join(sorted({r["platform"] for r in reports}))
    if args.history:
        seed = json.loads(args.seed.read_text(encoding="utf-8")) if args.seed else {}
        history = merge_history(load_history(args.history, seed), reports, args.run_label)
        write_json(args.history, history)
        write_json(args.out, table(history))
        print(f"{args.history}: {platforms} added from {len(reports)} report(s); {len(history['runs'])} run(s) kept")
        return 0
    current = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    write_json(args.out, merge(current, reports))
    print(f"{args.out}: {platforms} updated from {len(reports)} report(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
