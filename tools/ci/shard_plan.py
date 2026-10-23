#!/usr/bin/env python3
"""How many shards each lane of the merge gate runs, computed for every run (docs/implementation/
testing-and-ci-strategy.md §8, "Runtime budgets"; register E44).

Nobody writes the `lanes` job's matrix by hand. The `tier` job computes it here from the rolling history of `main`'s
green push runs (``update_durations.py --history``). Each lane on each platform gets the fewest shards whose slowest
shard fits the lanes job's session deadline on a runner :data:`RUNNER_VARIANCE` times slower than the ones the
history was measured on. A shard is estimated as ``lanes.partition`` will cut it, from the same table the shards
balance on (the history's medians):
- its tests' seconds over the platform's xdist workers, or its longest test if that is more;
- plus the lane's time outside its tests (the median of its kept runs).
The tests are the ones each lane held on `main`'s last kept run, so a pull request's new tests count from the first
green `main` run after it merges.

With no usable history (a first run, or the cache gone) it falls back to :data:`FALLBACK_SHARDS` and the committed
table, and says so. It writes:
- the matrix (``--github-output``: ``lanes_matrix``);
- the table the run's shards balance on (``--durations-out``), uploaded once, so every shard of a lane cuts the same
  partition;
- a summary.

Nothing here gates a change. A lane that cannot fit is a warning, and it gets the shards that come closest:
- one test too long for the deadline alone;
- or more than :data:`MAX_SHARDS` shards needed (E42, E52).
(E51: the operator, 2026-10-06: a wall-clock gate must never fail a correct change for runner speed.)

    python tools/ci/shard_plan.py --history history.json --seed tests/durations.json --durations-out durations.json \
        [--github-output "$GITHUB_OUTPUT"] [--summary "$GITHUB_STEP_SUMMARY"]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_durations  # noqa: E402  (tools/ci: the history's owner)

# Measured, testing-and-ci-strategy.md §12: "Runner-to-runner variation is up to 2x for CPU-bound jobs".
RUNNER_VARIANCE = 2.0
# Tripwire: an unreadable or inflated history must not start dozens of jobs. A lane that needs more is a warning that
# the suite has outgrown sharding (register E42, shared setup; E52, module fixtures rebuilt in every shard).
MAX_SHARDS = 16
# The account's limit on concurrent jobs (GitHub Pro, from 2026-10-07): a full run past it queues behind itself.
CONCURRENT_JOBS = 40
# Measured: the most time outside its tests of 150 green sessions, 2026-10-09 to 10-23 (Linux acceptance, 214 s;
# Windows integration at most 154 s of 128). For a lane the history has no run of yet.
DEFAULT_OUTSIDE_S = 215.0
# The lanes the `lanes` job runs, per runner, with the Python each platform tests on (the `core` job's, which a test
# keeps equal): Linux the Rocky Linux 8 AppStream / SPT wheelhouse target, Windows the developer workstation.
LANE_JOBS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("ubuntu-latest", "3.11", "linux", ("integration", "acceptance", "regression", "adversarial")),
    ("windows-latest", "3.13", "win32", ("integration", "acceptance", "regression", "adversarial")),
)
# Without a history, the counts this sizer computed from `main`'s green run at a3b33e3a (2026-10-23), seeded as the
# first history would be; a test keeps the keys equal to LANE_JOBS.
FALLBACK_SHARDS: dict[tuple[str, str], int] = {
    ("linux", "integration"): 6, ("linux", "acceptance"): 1, ("linux", "regression"): 3, ("linux", "adversarial"): 1,
    ("win32", "integration"): 7, ("win32", "acceptance"): 1, ("win32", "regression"): 3, ("win32", "adversarial"): 1,
}


def _lanes_module() -> Any:
    helpers = str(ROOT / "tests" / "helpers")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)
    import lanes  # tests/helpers/lanes.py: the partition the shards cut, and the durations' platform fill

    return lanes


def lanes_deadline_s(workflows: Path) -> float:
    """The session deadline of the `lanes` job's pytest command in ci.yml, read where it is set."""
    helpers = str(ROOT / "tests" / "helpers")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)
    import bounds  # tests/helpers/bounds.py: every pytest invocation of every workflow, with its bounds

    found = {lane.deadline_s for lane in bounds.workflow_lanes(workflows)
             if lane.workflow == "ci.yml" and lane.job == "lanes"}
    if len(found) != 1 or None in found:
        raise SystemExit(f"ci.yml's lanes job must run one pytest command with --session-deadline, found {found}")
    return float(found.pop())  # type: ignore[arg-type]


@dataclass
class Sizing:
    platform: str
    lane: str
    shards: int
    tests: int
    slowest_s: float  # the estimated slowest shard on the history's runners
    budget_s: float  # the deadline over RUNNER_VARIANCE
    warning: str = ""


def weights(nodeids: Sequence[str], durations: Mapping[str, float]) -> dict[str, float]:
    """Each test's weight as ``lanes.partition`` gives it: its duration, or the mean of the recorded ones."""
    known = [durations[n] for n in nodeids if n in durations]
    default = statistics.fmean(known) if known else 1.0
    return {n: float(durations.get(n, default)) for n in nodeids}


def slowest_shard_s(nodeids: Sequence[str], durations: Mapping[str, float], shards: int, workers: int,
                    outside_s: float) -> float:
    """The estimated wall clock of the slowest of ``shards`` shards, cut by ``lanes.partition``."""
    weight = weights(nodeids, durations)
    worst = 0.0
    for bin_ in _lanes_module().partition(list(nodeids), durations, shards):
        if bin_:
            loads = [weight[n] for n in bin_]
            worst = max(worst, max(sum(loads) / workers, max(loads)))
    return worst + outside_s


def size_lane(platform: str, lane: str, nodeids: Sequence[str], durations: Mapping[str, float], workers: int,
              outside_s: float, deadline_s: float) -> Sizing:
    """The fewest shards whose slowest one fits ``deadline_s`` on a runner RUNNER_VARIANCE times slower."""
    budget = deadline_s / RUNNER_VARIANCE
    estimates: dict[int, float] = {}
    for n in range(1, MAX_SHARDS + 1):
        estimates[n] = slowest_shard_s(nodeids, durations, n, workers, outside_s)
        if estimates[n] <= budget:
            return Sizing(platform, lane, n, len(nodeids), estimates[n], budget)
    weight = weights(nodeids, durations)
    longest = max(weight, key=lambda n: (weight[n], n)) if weight else ""
    if longest and weight[longest] + outside_s > budget:
        floor = weight[longest] + outside_s  # no shard count can go below its longest test
        n = min((k for k, e in estimates.items() if e <= floor * 1.05), default=MAX_SHARDS)
        why = (f"{longest} alone is estimated at {weight[longest]:.0f} s, more than the {budget:.0f} s budget: make "
               "it cheaper or split it")
    else:
        n = MAX_SHARDS
        why = (f"even {MAX_SHARDS} shards are estimated at {estimates[n]:.0f} s, over the {budget:.0f} s budget: the "
               "lane has outgrown sharding (register E42, E52)")
    return Sizing(platform, lane, n, len(nodeids), estimates[n], budget, why)


def plan(history: dict[str, Any] | None, seed: dict[str, Any], deadline_s: float
         ) -> tuple[list[Sizing], dict[str, Any], str]:
    """(each lane's sizing, the durations table the run's shards balance on, where the sizing came from)."""
    lanes_by_platform = (history or {}).get("lanes") or {}
    usable = bool(history and history.get("runs")
                  and all(lanes_by_platform.get(p) and (history.get("workers") or {}).get(p)
                          for _, _, p, _ in LANE_JOBS))
    if not usable:
        sizings = [Sizing(p, lane, FALLBACK_SHARDS[(p, lane)], 0, 0.0, deadline_s / RUNNER_VARIANCE,
                          "no usable history: the fallback shard count")
                   for _, _, p, lanes in LANE_JOBS for lane in lanes]
        return sizings, seed, "fallback: no history of green `main` runs (a first run, or the cache gone)"
    assert history is not None
    durations_table = update_durations.table(history)
    lanes_module = _lanes_module()
    sizings = []
    for _, _, platform, lanes in LANE_JOBS:
        durations = lanes_module.durations_for(platform, durations_table)
        workers = int(history["workers"][platform])
        for lane in lanes:
            nodeids = sorted(n for n, ln in lanes_by_platform[platform].items() if ln == lane)
            kept = ((history.get("overhead") or {}).get(platform) or {}).get(lane) or []
            outside = statistics.median(kept) if kept else DEFAULT_OUTSIDE_S
            sizings.append(size_lane(platform, lane, nodeids, durations, workers, outside, deadline_s))
    runs = history.get("runs") or []
    return sizings, durations_table, f"the median of {len(runs)} green `main` run(s), the last {runs[-1]}"


def matrix(sizings: Sequence[Sizing]) -> dict[str, Any]:
    """The `lanes` job's matrix: per runner and lane, shards 1..N of N."""
    count = {(s.platform, s.lane): s.shards for s in sizings}
    return {"include": [{"os": os_, "python": python, "lane": lane, "shard": k, "of": count[(platform, lane)]}
                        for os_, python, platform, lanes in LANE_JOBS for lane in lanes
                        for k in range(1, count[(platform, lane)] + 1)]}


def other_jobs(workflows: Path) -> int:
    """At least how many jobs a full run of ci.yml starts besides the `lanes` matrix (a job calling a local reusable
    workflow counts that workflow's jobs)."""
    import yaml

    def count(path: Path, skip: str = "") -> int:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        total = 0
        for name, job in (doc.get("jobs") or {}).items():
            if name == skip:
                continue
            uses = str(job.get("uses") or "")
            if uses.startswith("./.github/workflows/"):
                total += count(workflows / Path(uses).name)
            else:
                include = ((job.get("strategy") or {}).get("matrix") or {}).get("include")
                total += len(include) if isinstance(include, list) else 1
        return total

    return count(workflows / "ci.yml", skip="lanes")


def summary(sizings: Sequence[Sizing], source: str, deadline_s: float, extra_jobs: int) -> tuple[str, list[str]]:
    lane_jobs = sum(s.shards for s in sizings)
    lines = ["## Shards (tools/ci/shard_plan.py)", "",
             f"Sized from {source}. Each shard is budgeted {deadline_s / RUNNER_VARIANCE / 60:.1f} min on the "
             f"history's runners: the {deadline_s / 60:.0f} min session deadline over a runner {RUNNER_VARIANCE:g}x "
             "slower.", "",
             "| Platform | Lane | Shards | Tests | Slowest shard (est.) |", "|---|---|---|---|---|"]
    for s in sizings:
        est = f"{s.slowest_s / 60:.1f} min" if s.tests else "-"
        lines.append(f"| {s.platform} | {s.lane} | {s.shards} | {s.tests or '-'} | {est} |")
    warnings = [f"{s.platform} {s.lane}: {s.warning}" for s in sizings if s.warning and s.tests]
    if lane_jobs + extra_jobs > CONCURRENT_JOBS:
        warnings.append(f"a full run starts {lane_jobs} lane jobs and at least {extra_jobs} others, more than the "
                        f"account's {CONCURRENT_JOBS} concurrent jobs: it queues behind itself (register E42, E52)")
    lines += ["", f"{lane_jobs} lane jobs."]
    if warnings:
        lines += ["", "### Warnings (reported, never gating)", ""] + [f"- {w}" for w in warnings]
    return "\n".join(lines) + "\n", warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--history", type=Path, required=True, help="the rolling history (may be missing)")
    ap.add_argument("--seed", type=Path, required=True, help="the committed table (tests/durations.json)")
    ap.add_argument("--durations-out", type=Path, required=True, help="the table this run's shards balance on")
    ap.add_argument("--workflows", type=Path, default=ROOT / ".github" / "workflows")
    ap.add_argument("--github-output", type=Path, help="append lanes_matrix=<json> here")
    ap.add_argument("--summary", type=Path, help="append the Markdown summary here")
    args = ap.parse_args(argv)
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    history = update_durations.load_history(args.history, seed) if args.history.exists() else None
    deadline = lanes_deadline_s(args.workflows)
    sizings, durations_table, source = plan(history, seed, deadline)
    update_durations.write_json(args.durations_out, durations_table)
    text, warnings = summary(sizings, source, deadline, other_jobs(args.workflows))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"lanes_matrix={json.dumps(matrix(sizings), separators=(',', ':'))}\n")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    for w in warnings:
        print(f"::warning title=shards::{w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
