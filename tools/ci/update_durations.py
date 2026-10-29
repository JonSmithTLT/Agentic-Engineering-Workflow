#!/usr/bin/env python3
"""The durations shards balance on (docs/implementation/testing-and-ci-strategy.md §7; register E44).

Durations only balance shards; they never decide which tests run.

With ``--history`` (the merge gate's own use), it keeps the rolling history: every green push run on `main` adds its
reports (overlapping runs can lose some: strategy §7), each test keeps its last :data:`KEEP` durations, and ``--out``
is written as the median of them, the table the shards balance on. The history also keeps what ``shard_plan.py`` sizes
the lanes from: the lane each test ran in, each platform's xdist workers, each lane's time outside its tests, and how
much of the job's deadline its sessions started with. When the history is missing, unreadable or not of a history's
shape, it starts from ``--seed`` (the committed table). The committed table, tests/durations.json, is refreshed by
copying a green `main` run's ``shard-durations`` artifact over it (``shard_plan.py`` writes it, with each lane's shard
count).

    python tools/ci/update_durations.py REPORT_DIR --history history.json --seed tests/durations.json \
        --out durations.json --run-label "<run id>/<attempt> <sha>"

The nightly keeps a history of its own the same way, from its reference shards (``--passed-only``, no seed): one
process per shard measures a test's serial time, which the merge gate's xdist workers (and coverage, on Linux) do not
(``shard_plan.py --reference``).

Without ``--history``, it merges lane reports into the table at ``--out`` directly, for a table made from runs that are
not `main`'s: its shard counts are kept and its ``sized_from`` dropped, and entries for tests no longer collected are
dropped.

    python tools/ci/update_durations.py REPORT_DIR [REPORT_DIR ...] --out durations.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_assurance import latest_attempts  # noqa: E402  (tools/ci/check_assurance.py)

DURATIONS_SCHEMA = "aew/test-durations/v1"
HISTORY_SCHEMA = "aew/test-durations-history/v1"
REPORT_SCHEMA = "aew/lane-report/v1"
AUTOPSY_DIR = "autopsy"  # a hang's autopsy in a report directory is never a lane report (check_assurance.py)
ALL_LANES = "all"  # what a session of no one lane (the nightly's reference shards) is kept under (check_assurance's)
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
    # the lanes' shard counts are kept; `sized_from` names the run the table came from, which a merge makes untrue
    others = {k: v for k, v in current.items() if k not in ("schema", "platforms", "sized_from")}
    return {"schema": DURATIONS_SCHEMA,
            "platforms": {p: dict(sorted(t.items())) for p, t in sorted(platforms.items())}, **others}


def seed_history(seed: dict[str, Any]) -> dict[str, Any]:
    """A history whose one observation per test is the committed table's: the start, before any run is kept."""
    return {"schema": HISTORY_SCHEMA, "runs": [],
            "platforms": {p: {n: [float(d)] for n, d in t.items()} for p, t in (seed.get("platforms") or {}).items()},
            "lanes": {}, "workers": {}, "overhead": {}, "job_remaining": {}}


def _number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _nested(value: Any, leaf: Callable[[Any], bool]) -> bool:
    """``value`` is ``{platform: {name: leaf}}``."""
    return isinstance(value, dict) and all(
        isinstance(t, dict) and all(isinstance(n, str) and leaf(x) for n, x in t.items()) for t in value.values())


def _series(x: Any) -> bool:
    return isinstance(x, list) and all(_number(d) for d in x)


# Each key a history holds, and its shape (the ones a history from before a key existed lacks are optional).
_SHAPES: dict[str, Callable[[Any], bool]] = {
    "runs": lambda v: isinstance(v, list) and all(isinstance(r, str) for r in v),
    "platforms": lambda v: _nested(v, _series),
    "lanes": lambda v: _nested(v, lambda x: isinstance(x, str)),
    "workers": lambda v: isinstance(v, dict) and all(isinstance(n, int) and not isinstance(n, bool) and n > 0
                                                     for n in v.values()),
    "overhead": lambda v: _nested(v, _series),
    "job_remaining": lambda v: _nested(v, _series),
}
_REQUIRED = ("runs", "platforms")


def history_problem(data: Any) -> str | None:
    """Why ``data`` is not a history this module could have written, or None. A file that parses and names the
    schema but has another shape (a writer's bug, a shape change later reverted) must start again too, never fail a
    run (CRD-13; review of #235, F2)."""
    if not isinstance(data, dict) or data.get("schema") != HISTORY_SCHEMA:
        return f"it is not a {HISTORY_SCHEMA} document"
    missing = [k for k in _REQUIRED if k not in data]
    if missing:
        return f"it has no {', '.join(missing)}"
    wrong = [k for k, ok in _SHAPES.items() if k in data and not ok(data[k])]
    return f"its {', '.join(wrong)} {'is' if len(wrong) == 1 else 'are'} not of a history's shape" if wrong else None


def read_history(path: Path, of: str = "green `main` runs") -> tuple[dict[str, Any] | None, str]:
    """(the history at ``path``, "") or (None, why there is none to use); ``of`` names the runs it keeps."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"no history of {of} (a first run, or the cache gone)"
    except (OSError, ValueError) as exc:
        return None, f"the history could not be read ({type(exc).__name__})"
    problem = history_problem(data)
    return (None, f"the history was set aside: {problem}") if problem else (data, "")


def load_history(path: Path, seed: dict[str, Any]) -> dict[str, Any]:
    """The history at ``path``, or one seeded from ``seed`` when there is none to use (:func:`read_history`): a
    history only balances shards, so starting again is always safe, and the next green run replaces a bad one."""
    data, _ = read_history(path)
    return data if data is not None else seed_history(seed)


def run_id(label: str) -> str:
    """The run a history label names (``<run id>/<attempt> <sha>``)."""
    return label.split("/", 1)[0].split(" ", 1)[0]


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
    tests no longer collected on a platform are dropped; the lanes, workers and time outside the tests are this run's,
    and so is the least of the job's deadline any of a lane's sessions started with (its slowest setup). A run already
    in the history is not added again: re-running main's assurance job after it saved must not count one runner's
    timings twice (review of #235, F5)."""
    out = json.loads(json.dumps(history))  # a deep copy: the caller's history is left as it was
    out["schema"] = HISTORY_SCHEMA
    if label and run_id(label) in {run_id(r) for r in out.get("runs", [])}:
        return out
    out["runs"] = ([*out.get("runs", []), label] if label else list(out.get("runs", [])))[-keep:]
    collected: dict[str, set[str]] = {}
    lanes: dict[str, dict[str, str]] = {}
    workers: dict[str, int] = {}
    outside: dict[str, dict[str, float]] = {}
    remaining: dict[str, dict[str, float]] = {}
    for r in reports:
        platform, lane = r["platform"], r.get("lane") or ALL_LANES
        table = out.setdefault("platforms", {}).setdefault(platform, {})
        collected.setdefault(platform, set()).update(r["collected"])
        lanes.setdefault(platform, {}).update(r.get("lanes") or {})
        if r.get("xdist_workers"):
            workers[platform] = max(workers.get(platform, 0), int(r["xdist_workers"]))
        spent = outside_tests_s(r)
        if spent is not None:
            per_lane = outside.setdefault(platform, {})
            per_lane[lane] = max(per_lane.get(lane, 0.0), spent)
        if _number(r.get("job_remaining_s")):
            left = remaining.setdefault(platform, {})
            left[lane] = min(left.get(lane, float("inf")), float(r["job_remaining_s"]))
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
    for platform, per_lane in remaining.items():
        kept = out.setdefault("job_remaining", {}).setdefault(platform, {})
        for lane, left in per_lane.items():
            kept[lane] = [*kept.get(lane, []), round(left, 1)][-keep:]
    out["platforms"] ={p: dict(sorted(t.items())) for p, t in sorted(out["platforms"].items())}
    return out


def table(history: dict[str, Any]) -> dict[str, Any]:
    """The durations table the shards balance on: each test's median over its kept durations."""
    return {"schema": DURATIONS_SCHEMA,
            "platforms": {p: {n: round(statistics.median(d), 2) for n, d in sorted(t.items()) if d}
                          for p, t in sorted((history.get("platforms") or {}).items())}}


def load_reports(dirs: list[Path]) -> list[dict[str, Any]]:
    """Each directory's lane reports (one run's), its shards' latest attempts only: a re-run shard's earlier report
    adds no timings of its own (check_assurance.latest_attempts)."""
    reports = []
    for d in dirs:
        found = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.rglob("*.json"))
                 if AUTOPSY_DIR not in p.relative_to(d).parts]
        reports += latest_attempts([r for r in found if r.get("schema") == REPORT_SCHEMA])
    return reports


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
    ap.add_argument("--passed-only", action="store_true",
                    help="add only the reports of sessions that passed (the nightly's reference shards: a red night "
                         "still records its green shards, and a failed or killed one never moves a duration)")
    args = ap.parse_args(argv)
    reports = load_reports(args.reports)
    if args.passed_only:
        reports = [r for r in reports if r.get("exitstatus") == 0]
        if not reports:
            print("no session passed: nothing added")
            return 0
    platforms = ", ".join(sorted({r["platform"] for r in reports}))
    if args.history:
        seed = json.loads(args.seed.read_text(encoding="utf-8")) if args.seed else {}
        _, why = read_history(args.history)
        before = load_history(args.history, seed)
        history = merge_history(before, reports, args.run_label)
        write_json(args.history, history)
        write_json(args.out, table(history))
        if why:
            print(f"{args.history}: started again from the committed table: {why}")
        if history == before:
            print(f"{args.history}: run {run_id(args.run_label)} is in the history already; nothing added")
        else:
            print(f"{args.history}: {platforms} added from {len(reports)} report(s); {len(history['runs'])} run(s) "
                  "kept")
        return 0
    current = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
    write_json(args.out, merge(current, reports))
    print(f"{args.out}: {platforms} updated from {len(reports)} report(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
