#!/usr/bin/env python3
"""The per-run CI cost record (CI redesign v0.2 P4, register E43 and E45; docs/implementation/testing-and-ci-strategy.md
§8 and §12).

Reads the lane reports `assurance` already downloads and, when given, the run's jobs from the GitHub API, and writes
what the run cost: queue delay and end-to-end wall clock, runner-minutes, wall time per lane and shard against the
strategy's budgets, total pytest time, the slowest 20 tests, each test's share of its lane, `aew` CLI calls per test,
the share of collected tests that `tests/durations.json` covers, and, for a pull request, the cost of the tests in the
test files it changes.

It reports; it never fails the gate (operator, 2026-10-06: runner speed never fails a correct change; the job timeout
is the only hard bound). CI-health findings are warnings:

* a lane job over 20 minutes warns, over 25 minutes is a CI-health violation (CRD-11);
* a test over 25% of its lane's test time, or a fast-lane test over 30 seconds, is a CI-health violation (E45).

    python tools/ci/cost_record.py REPORT_DIR [--jobs JOBS.json] [--durations tests/durations.json]
        [--changed-files PATHS.txt] [--summary FILE] [--out cost-record.json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_assurance import load_reports  # noqa: E402  (tools/ci/check_assurance.py)

SCHEMA = "aew/ci-cost-record/v1"
JOB_WARN_S = 20 * 60  # CRD-11: a shard over 20 minutes warns ...
JOB_VIOLATION_S = 25 * 60  # ... over 25 is a CI-health violation; the 30-minute job timeout stays the hard bound
TEST_SHARE_VIOLATION = 0.25  # E45: one test over a quarter of its lane's test time
FAST_TEST_VIOLATION_S = 30.0  # E45: a fast-lane test over 30 s (the lane's whole budget is 3 minutes, §8)
# testing-and-ci-strategy.md §8's budgets, reported as warnings (CCI-01): the first CI signal (Linux `core`) within
# 3 minutes, the fast lane's test time within 3 minutes, and the whole run (created to the last job done) within 15
CORE_BUDGET_S = 3 * 60
FAST_LANE_BUDGET_S = 3 * 60
RUN_BUDGET_S = 15 * 60
SLOWEST = 20
# A lane job's name in ci.yml: "integration 2/5 (ubuntu-latest)"; core is "core (windows-latest)".
JOB_NAME = re.compile(r"^(?P<lane>[a-z]+)(?: (?P<shard>\d+/\d+))? \((?P<os>[a-z0-9.-]+)\)$")


def _time(stamp: str | None) -> datetime | None:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None


def _seconds(start: str | None, end: str | None) -> float | None:
    a, b = _time(start), _time(end)
    return (b - a).total_seconds() if a and b else None


def job_facts(jobs: list[dict[str, Any]], run: dict[str, Any] | None = None) -> dict[str, Any]:
    """Queue delay, run time and runner-minutes from the GitHub jobs API (``GET .../runs/{id}/jobs``) and, when given,
    the run itself (``GET .../runs/{id}``). Only this attempt counts: on a re-run, jobs carried over from an earlier
    attempt (started before this attempt's ``run_started_at``) are listed as carried over and count toward nothing. A
    job that has not completed yet (the one writing this record) counts toward nothing but the list of jobs still
    running; a skipped job, which never ran, counts toward nothing.

    ``assurance_s`` is §8's measure (the attempt's first job created to its last job done); ``wall_clock_s`` also
    counts the time the attempt waited as pending before its first job existed, reported as a fact."""
    attempt_start = _time((run or {}).get("run_started_at")) or _time((run or {}).get("created_at"))
    rows, running, carried = [], [], []
    counted = []
    for j in jobs:
        if j.get("conclusion") == "skipped":
            continue
        started_at = _time(j.get("started_at"))
        if attempt_start and started_at and started_at < attempt_start:
            carried.append(j.get("name", "?"))
            continue
        run_s = _seconds(j.get("started_at"), j.get("completed_at"))
        if run_s is None:
            running.append(j.get("name", "?"))
            continue
        counted.append(j)
        queue = _seconds(j.get("created_at"), j.get("started_at"))
        rows.append({"name": j.get("name", "?"), "queue_s": None if queue is None else max(queue, 0.0),
                     "run_s": max(run_s, 0.0), "conclusion": j.get("conclusion"),
                     "os": (j.get("labels") or [None])[0]})
    created = [t for j in counted if (t := _time(j.get("created_at")))]
    completed = [t for j in counted if (t := _time(j.get("completed_at")))]
    started = [t for j in counted if (t := _time(j.get("started_at")))]
    minutes: dict[str, float] = defaultdict(float)
    for r in rows:
        minutes[r["os"] or "unknown"] += r["run_s"] / 60
    queues = [r["queue_s"] for r in rows if r["queue_s"] is not None]
    return {
        "jobs": sorted(rows, key=lambda r: r["name"]),
        "still_running": sorted(running),
        "carried_over": sorted(carried),
        "assurance_s": (max(completed) - min(created)).total_seconds() if created and completed else None,
        "wall_clock_s": ((max(completed) - min([*created, *([attempt_start] if attempt_start else [])])).total_seconds()
                         if created and completed else None),
        "queue_s": {"max": max(queues), "total": sum(queues)} if queues else None,
        "run_pending_s": (max((min(started) - attempt_start).total_seconds(), 0.0)
                          if attempt_start and started else None),
        "runner_minutes": {k: round(v, 1) for k, v in sorted(minutes.items())},
    }


def lane_job_health(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CRD-11 over the jobs that ran tests (core and the lane shards), and §8's first-signal budget for Linux core."""
    out = []
    for r in jobs:
        if not JOB_NAME.match(r["name"]):
            continue
        if r["name"] == "core (ubuntu-latest)" and r["run_s"] > CORE_BUDGET_S:
            out.append({"level": "warning", "kind": "budget", "job": r["name"], "seconds": round(r["run_s"]),
                        "detail": f"the first CI signal is over §8's {CORE_BUDGET_S // 60}-minute budget"})
        if r["run_s"] > JOB_VIOLATION_S:
            out.append({"level": "violation", "kind": "job_time", "job": r["name"], "seconds": round(r["run_s"]),
                        "detail": f"over {JOB_VIOLATION_S // 60} minutes (the timeout is 30)"})
        elif r["run_s"] > JOB_WARN_S:
            out.append({"level": "warning", "kind": "job_time", "job": r["name"], "seconds": round(r["run_s"]),
                        "detail": f"over {JOB_WARN_S // 60} minutes"})
    return out


def test_facts(reports: list[dict[str, Any]], durations: dict[str, Any] | None,
               changed: set[str] | None) -> dict[str, Any]:
    by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in reports:
        by_platform[r["platform"]].append(r)
    out: dict[str, Any] = {}
    for platform, group in sorted(by_platform.items()):
        lane_time: dict[str, float] = defaultdict(float)
        tests: list[dict[str, Any]] = []
        shards = []
        for r in group:
            lane = r.get("lane") or "all"
            test_time = sum(v["duration"] for v in r["results"].values())
            lane_time[lane] += test_time
            shards.append({"lane": lane, "shard": r.get("shard"), "tests": len(r["results"]),
                           "test_s": round(test_time, 1), "session_wall_s": r.get("wall_s"),
                           "xdist_workers": r.get("xdist_workers")})
            calls = r.get("cli_calls") or {}
            tests += [{"id": nid, "lane": lane, "seconds": v["duration"], "cli_calls": calls.get(nid, 0)}
                      for nid, v in r["results"].items()]
        for t in tests:
            t["share_of_lane"] = round(t["seconds"] / lane_time[t["lane"]], 4) if lane_time[t["lane"]] else 0.0
        collected = set().union(*(set(r["collected"]) for r in group))
        known = set((durations or {}).get("platforms", {}).get(platform, {}))
        facts: dict[str, Any] = {
            "pytest_s": round(sum(lane_time.values()), 1),
            "lanes": {lane: round(s, 1) for lane, s in sorted(lane_time.items())},
            "shards": sorted(shards, key=lambda s: (s["lane"], s["shard"] or "")),
            "slowest": sorted(tests, key=lambda t: -t["seconds"])[:SLOWEST],
            "cli_calls": {"total": sum(t["cli_calls"] for t in tests),
                          "most": sorted((t for t in tests if t["cli_calls"]), key=lambda t: -t["cli_calls"])[:10]},
            "durations_coverage": round(len(collected & known) / len(collected), 4) if collected else None,
            "health": [],
        }
        if changed is not None:
            # CCI-06: the cost of the tests a change adds or edits, by the test files its diff touches (a test's node
            # id starts with its file); exact, where a stale durations file would count old tests as new
            touched = [t for t in tests if t["id"].split("::", 1)[0] in changed]
            # the change's new tests: in a touched file and unknown to the durations file (a test merely sharing a file
            # with an edit is not new)
            new = [t for t in touched if t["id"] not in known]
            facts["changed_tests"] = {"count": len(touched), "seconds": round(sum(t["seconds"] for t in touched), 1),
                                      "slowest": sorted(touched, key=lambda t: -t["seconds"])[:10],
                                      "new": {"count": len(new), "seconds": round(sum(t["seconds"] for t in new), 1),
                                              "slowest": sorted(new, key=lambda t: -t["seconds"])[:10]}}
        if platform == "linux" and lane_time.get("fast", 0.0) > FAST_LANE_BUDGET_S:  # §8 budgets the Linux lane
            facts["health"].append({"level": "warning", "kind": "budget", "test": "fast lane",
                                    "seconds": round(lane_time["fast"], 1),
                                    "detail": "the fast lane's test time is over §8's "
                                              f"{FAST_LANE_BUDGET_S // 60}-minute budget"})
        for t in tests:
            if t["lane"] == "fast" and t["seconds"] > FAST_TEST_VIOLATION_S:
                facts["health"].append({"level": "violation", "kind": "fast_test_time", "test": t["id"],
                                        "seconds": round(t["seconds"], 1),
                                        "detail": f"a fast-lane test over {FAST_TEST_VIOLATION_S:.0f} s"})
            if t["share_of_lane"] > TEST_SHARE_VIOLATION and lane_time[t["lane"]] >= 60:
                facts["health"].append({"level": "violation", "kind": "test_share", "test": t["id"],
                                        "seconds": round(t["seconds"], 1), "share": t["share_of_lane"],
                                        "detail": f"{t['share_of_lane']:.0%} of the {t['lane']} lane's test time"})
        out[platform] = facts
    return out


def build(reports: list[dict[str, Any]], jobs: list[dict[str, Any]] | None, durations: dict[str, Any] | None,
          changed: set[str] | None = None, run: dict[str, Any] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {"schema": SCHEMA, "platforms": test_facts(reports, durations, changed)}
    if jobs is not None:
        record["run"] = job_facts(jobs, run)
        record["health"] = lane_job_health(record["run"]["jobs"])
        took = record["run"]["assurance_s"]
        if took is not None and took > RUN_BUDGET_S:
            record["health"].append({"level": "warning", "kind": "budget", "job": "the run", "seconds": round(took),
                                     "detail": f"first job created to last job done is over §8's {RUN_BUDGET_S // 60}-"
                                               "minute budget"})
    else:
        record["health"] = []
    return record


def _m(seconds: float | None) -> str:
    return "-" if seconds is None else f"{seconds / 60:.1f} min"


def summary(record: dict[str, Any]) -> str:
    lines = ["## Cost record", "",
             "Reported, never gated: the job timeout is the only hard bound (CI redesign P4; strategy §8)."]
    health = record["health"] + [h | {"platform": p} for p, f in record["platforms"].items() for h in f["health"]]
    if health:
        lines += ["", f"**CI health: {sum(h['level'] == 'violation' for h in health)} violation(s), "
                      f"{sum(h['level'] == 'warning' for h in health)} warning(s).**", ""]
        lines += [f"- {h['level']}: {h.get('job') or '`' + h['test'] + '`'}"
                  f"{' (' + h['platform'] + ')' if 'platform' in h else ''}: {h['detail']} ({h['seconds']} s)"
                  for h in health]
    run = record.get("run")
    if run:
        q = run["queue_s"] or {}
        lines += ["", f"Run: {_m(run['assurance_s'])} from its first job (§8's measure), {_m(run['wall_clock_s'])} "
                      "with the time pending before it; pending "
                      f"{_m(run.get('run_pending_s'))}; longest job queue {_m(q.get('max'))}; runner minutes "
                      + ", ".join(f"{k} {v}" for k, v in run["runner_minutes"].items()) + ".", "",
                  "<details><summary>jobs</summary>", "", "| job | queued | ran | result |", "|---|---|---|---|"]
        lines += [f"| {j['name']} | {_m(j['queue_s'])} | {_m(j['run_s'])} | {j['conclusion']} |" for j in run["jobs"]]
        lines += ["", "</details>"]
    for platform, f in record["platforms"].items():
        lines += ["", f"### {platform}: {f['pytest_s'] / 60:.1f} min of pytest time, "
                      f"{f['cli_calls']['total']} `aew` calls through the test helper (`conftest.run_aew`; direct "
                      "`python -m aew` starts and fake agents' calls are not counted), durations file covers "
                      + (f"{f['durations_coverage']:.0%}" if f["durations_coverage"] is not None else "-")
                      + " of collected tests", ""]
        if "changed_tests" in f:
            n = f["changed_tests"]
            lines += [f"New tests (in the files this change touches, unknown to `tests/durations.json`): "
                      f"{n['new']['count']}, {n['new']['seconds']:.0f} s in all."]
            lines += [f"- {t['seconds']:.1f}s ({t['share_of_lane']:.0%} of {t['lane']}) `{t['id']}`"
                      for t in n["new"]["slowest"]]
            lines += [f"All tests in the test files this change touches: {n['count']}, {n['seconds']:.0f} s in all."]
            lines += [f"- {t['seconds']:.1f}s ({t['share_of_lane']:.0%} of {t['lane']}) `{t['id']}`"
                      for t in n["slowest"]]
            lines.append("")
        lines += ["<details><summary>slowest tests</summary>", "", "| s | share of lane | aew calls (helper) | test |",
                  "|---|---|---|---|"]
        lines += [f"| {t['seconds']:.1f} | {t['share_of_lane']:.1%} {t['lane']} | {t['cli_calls']} | `{t['id']}` |"
                  for t in f["slowest"]]
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def _json(path: Path | None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("reports", type=Path, help="directory searched recursively for lane reports")
    ap.add_argument("--jobs", type=Path, help="the run's jobs as the GitHub API returns them ({'jobs': [...]})")
    ap.add_argument("--run", type=Path, help="the run itself as the GitHub API returns it (its created_at)")
    ap.add_argument("--durations", type=Path, help="tests/durations.json")
    ap.add_argument("--changed-files", type=Path,
                    help="the change's changed paths, one per line (a pull request's diff against its base)")
    ap.add_argument("--summary", type=Path, help="append the Markdown summary here (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--out", type=Path, help="write the JSON record here")
    args = ap.parse_args(argv)
    jobs = _json(args.jobs)
    changed = ({line.strip() for line in args.changed_files.read_text(encoding="utf-8").splitlines() if line.strip()}
               if args.changed_files and args.changed_files.is_file() else None)
    record = build(load_reports(args.reports), jobs.get("jobs") if isinstance(jobs, dict) else None,
                   _json(args.durations), changed, _json(args.run))
    text = summary(record)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    if args.out:
        args.out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(text)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        found = record["health"] + [h for f in record["platforms"].values() for h in f["health"]]
        for h in found[:10]:  # GitHub keeps at most 10 warnings per step
            print(f"::warning title=CI health ({h['level']})::{h.get('job') or h.get('test')}: {h['detail']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
