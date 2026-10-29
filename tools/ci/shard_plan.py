#!/usr/bin/env python3
"""How many shards each lane of the merge gate runs, computed for every run (docs/implementation/
testing-and-ci-strategy.md §8, "Runtime budgets"; register E44).

Nobody writes the `lanes` job's matrix by hand. The `tier` job computes it here from the rolling history of `main`'s
green push runs (``update_durations.py --history``). Each lane on each platform needs the fewest shards whose slowest
shard fits on a runner :data:`RUNNER_VARIANCE` times slower than the ones the history was measured on: there the
job's setup and the session both stretch, and the session must end by its own deadline and by the job's, which the
setup came out of. A shard is estimated as ``lanes.partition`` will cut it, from the same table the shards balance on
(the history's medians):
- its tests' seconds over the platform's xdist workers, or its longest test if that is more;
- plus the lane's time outside its tests (the median of its kept runs).
The tests are the ones each lane held on `main`'s last kept run, so a pull request's new tests count from the first
green `main` run after it merges whose save is the newest (overlapping runs: strategy §7).

tests/durations.json, the committed table, holds each lane's count too (``shards``), and a run never gives a lane
fewer: a pull request that moves a lot of test time into one lane raises that lane's count there, so its own run
fits before `main` has measured it. With no usable history (a first run, the cache gone, or a history that is not of
a history's shape) each lane gets :data:`FALLBACK_MARGIN` times its committed count, so a stale committed table
cannot fail a run unless a lane has more than doubled since it was refreshed. A run with a history warns when the
committed table falls behind it (review of #235, F1). It writes:
- the matrix (``--github-output``: ``lanes_matrix``);
- the table the run's shards balance on (``--durations-out``), uploaded once, so every shard of a lane cuts the same
  partition. It carries each lane's count as the history sizes it, so a green `main` run's copy is the refreshed
  tests/durations.json;
- a summary.

Nothing here gates a change. A lane that cannot fit is a warning, and it gets the shards that come closest:
- one test too long for the deadline alone;
- or more than :data:`MAX_SHARDS` shards needed (E42, E52).
(E51: the operator, 2026-10-06: a wall-clock gate must never fail a correct change for runner speed.)

    python tools/ci/shard_plan.py --history history.json --seed tests/durations.json --durations-out durations.json \
        [--github-output "$GITHUB_OUTPUT"] [--summary "$GITHUB_STEP_SUMMARY"]

With ``--reference`` it sizes the nightly's reference lane instead (nightly.yml `reference`: the whole suite on each
runner, one process per shard), from the nightly's own history of its shards: each runner gets the fewest shards whose
slowest estimated shard is at most :data:`REFERENCE_TARGET_S` (``reference_matrix``). Never from the merge gate's
history: there a test runs beside its platform's other xdist workers, and under coverage on Linux, so the gate's table
put the 10-25 reference run's tests at 1.36x (Windows) and 2.8x (Linux) their serial time, and sized the lane at 15
Linux and more than 16 Windows shards where 5 and 11 fit (measured 2026-10-28). With no history yet, the runners share
what the account's concurrent jobs leave beside the nightly's other jobs, never more.

    python tools/ci/shard_plan.py --reference --history history.json --seed tests/durations.json \
        --durations-out durations.json --runner ubuntu-latest:3.11 --runner windows-latest:3.13 \
        [--github-output "$GITHUB_OUTPUT"] [--summary "$GITHUB_STEP_SUMMARY"]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tier  # noqa: E402  (tools/ci: the lanes each tier requires)
import update_durations  # noqa: E402  (tools/ci: the history's owner)

# Measured, testing-and-ci-strategy.md §8: "Runner-to-runner variation is up to 2x for CPU-bound jobs".
RUNNER_VARIANCE = 2.0
# Tripwire, per lane (8 lanes: at most 128 lane jobs on a run with a history): a lane that needs more is a warning that
# the suite has outgrown sharding (register E42, shared setup; E52, module fixtures rebuilt in every shard).
MAX_SHARDS = 16
# The account's limit on concurrent jobs (GitHub Pro, from 2026-10-07): a full run past it queues behind itself.
CONCURRENT_JOBS = 40
# Measured: the most time outside its tests of 150 green sessions, 2026-10-09 to 10-23 (214 s, Linux acceptance). For
# a lane the history has no run of yet.
DEFAULT_OUTSIDE_S = 215.0
# Measured: the most time a lane job spent before its pytest session started (checkout, setup-aew, the table's
# download) in run 40019126451 (2026-10-23): 48 s on Linux, 56 s on Windows. For a lane the history has no
# measurement of yet (lane reports carry `job_remaining_s` from #235 on).
DEFAULT_SETUP_S = 56.0
# GitHub's limit on the jobs one matrix may start in a workflow run.
MATRIX_LIMIT = 256
# A run without a usable history sizes each lane at this many times its committed count (the operator's ruling on
# CRD-13, 2026-10-23). A count is at most MAX_SHARDS, as on a run with a history, so the fallback's cap is this many
# times that: twice holds for every count, and every lane at the cap still fits one matrix (a test keeps it so).
FALLBACK_MARGIN = 2.0


def fallback_shards(committed: int) -> int:
    """The shards a lane with this committed count runs on a run without a usable history."""
    return math.ceil(FALLBACK_MARGIN * min(committed, MAX_SHARDS))


# The fallback's cap, from the same rule, so the matrix bound a test checks is the one the fallback uses (review of
# #235, N3).
FALLBACK_MAX_SHARDS = fallback_shards(MAX_SHARDS)
# A run with a history warns when the committed table knows less than this share of a platform's tests (the drift
# threshold of the operator's ruling on CRD-13, 2026-10-23).
COVERAGE_WARNING = 0.9
# The lanes the `lanes` job runs on every runner the `core` job tests on (the full tier's, less the ones `core` runs
# itself), and each runner's sys.platform.
LANES = tuple(lane for lane in tier.LANES["full"] if lane not in tier.FAST_LANES)
PLATFORM_OF_OS = {"ubuntu-latest": "linux", "windows-latest": "win32"}
REFRESH = ("copy a green `main` push run's `shard-durations` artifact (durations.json) over tests/durations.json")


def _helpers() -> None:
    helpers = str(ROOT / "tests" / "helpers")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)


def _lanes_module() -> Any:
    _helpers()
    import lanes  # tests/helpers/lanes.py: the partition the shards cut, its weights, the durations' platform fill

    return lanes


def lane_jobs(workflows: Path = WORKFLOWS) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """(runner, Python, sys.platform, lanes) for each runner of ci.yml's `core` matrix, on the Python `core` tests
    that runner's platform on (review of #235, F6)."""
    import yaml

    core = yaml.safe_load((workflows / "ci.yml").read_text(encoding="utf-8"))["jobs"]["core"]
    return [(m["os"], str(m["python"]), PLATFORM_OF_OS[m["os"]], LANES) for m in core["strategy"]["matrix"]["include"]]


@dataclass(frozen=True)
class Deadlines:
    session_s: float  # the lanes job's --session-deadline, from the session's start
    job_s: float  # its AEW_JOB_DEADLINE, from the job's first step: the job's setup comes out of it

    def budget_s(self, setup_s: float) -> float:
        """What a shard may take on the history's runners: on a runner RUNNER_VARIANCE times slower, both the setup
        and the session stretch, and the session must end by its own deadline and by the job's (review of #235,
        F3)."""
        return min(self.session_s, self.job_s - RUNNER_VARIANCE * setup_s) / RUNNER_VARIANCE


def lanes_deadlines(workflows: Path = WORKFLOWS) -> Deadlines:
    """The `lanes` job's deadlines, read where ci.yml sets them."""
    _helpers()
    import bounds  # tests/helpers/bounds.py: every pytest invocation of every workflow, with its bounds

    found = {(lane.deadline_s, lane.job_deadline_s) for lane in bounds.workflow_lanes(workflows)
             if lane.workflow == "ci.yml" and lane.job == "lanes"}
    if len(found) != 1 or None in next(iter(found)):
        raise SystemExit(f"ci.yml's lanes job must run one pytest command with --session-deadline in a job that sets "
                         f"AEW_JOB_DEADLINE, found {found}")
    session, job = found.pop()
    return Deadlines(float(session), float(job))  # type: ignore[arg-type]


@dataclass
class Sizing:
    platform: str
    lane: str
    shards: int  # what the run uses: the larger of `need` and the committed count, or the fallback's
    tests: int
    slowest_s: float  # the estimated slowest of `need` shards on the history's runners
    budget_s: float
    warning: str = ""
    need: int | None = None  # the history's count; None on a fallback run
    committed: int | None = None


def slowest_shard_s(nodeids: Sequence[str], durations: Mapping[str, float], shards: int, workers: int,
                    outside_s: float) -> float:
    """The estimated wall clock of the slowest of ``shards`` shards, cut by ``lanes.partition``."""
    lanes = _lanes_module()
    weight = lanes.weights(nodeids, durations)
    worst = 0.0
    for bin_ in lanes.partition(list(nodeids), durations, shards):
        if bin_:
            loads = [weight[n] for n in bin_]
            worst = max(worst, max(sum(loads) / workers, max(loads)))
    return worst + outside_s


def size_lane(platform: str, lane: str, nodeids: Sequence[str], durations: Mapping[str, float], workers: int,
              outside_s: float, budget: float) -> Sizing:
    """The fewest shards whose slowest one fits ``budget`` (:meth:`Deadlines.budget_s`)."""
    estimates: dict[int, float] = {}
    for n in range(1, MAX_SHARDS + 1):
        estimates[n] = slowest_shard_s(nodeids, durations, n, workers, outside_s)
        if estimates[n] <= budget:
            return Sizing(platform, lane, n, len(nodeids), estimates[n], budget, need=n)
    weight = _lanes_module().weights(nodeids, durations)
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
    return Sizing(platform, lane, n, len(nodeids), estimates[n], budget, why, need=n)


def committed_counts(seed: Mapping[str, Any]) -> dict[tuple[str, str], int]:
    """Each lane's count in the committed table (``shards``: platform -> lane -> count); a malformed entry is none."""
    out: dict[tuple[str, str], int] = {}
    shards = seed.get("shards")
    for platform, per_lane in (shards.items() if isinstance(shards, dict) else ()):
        for lane, n in (per_lane.items() if isinstance(per_lane, dict) else ()):
            if isinstance(n, int) and not isinstance(n, bool) and n >= 1:
                out[(str(platform), str(lane))] = n
    return out


def run_table(platforms: Mapping[str, Any], sizings: Sequence[Sizing], source: str) -> dict[str, Any]:
    """The table this run's shards balance on, with the counts a refresh of tests/durations.json takes from it: the
    history's need, or on a fallback run the committed counts unchanged."""
    counts: dict[str, dict[str, int]] = {}
    for s in sizings:
        n = s.need if s.need is not None else s.committed
        if n is not None:
            counts.setdefault(s.platform, {})[s.lane] = n
    return {"schema": update_durations.DURATIONS_SCHEMA, "platforms": dict(platforms), "shards": counts,
            "sized_from": source}


def fallback(seed: Mapping[str, Any], deadlines: Deadlines, jobs: Sequence[tuple[str, str, str, tuple[str, ...]]],
             why: str) -> tuple[list[Sizing], dict[str, Any], str, list[str]]:
    counts = committed_counts(seed)
    budget = deadlines.budget_s(DEFAULT_SETUP_S)
    sizings, warnings = [], []
    for _, _, platform, lanes in jobs:
        for lane in lanes:
            base = counts.get((platform, lane))
            n = MAX_SHARDS if base is None else fallback_shards(base)
            sizings.append(Sizing(platform, lane, n, 0, 0.0, budget, committed=base))
            if base is None:
                warnings.append(f"{platform} {lane}: tests/durations.json gives it no shard count, so it runs "
                                f"{MAX_SHARDS}; {REFRESH}")
    source = f"the fallback ({why}): {FALLBACK_MARGIN:g}x each lane's count in tests/durations.json"
    runs = "; ".join(f"{p}: " + ", ".join(f"{s.lane} {s.shards}" for s in sizings if s.platform == p)
                     for p in dict.fromkeys(s.platform for s in sizings))
    warnings.insert(0, f"no usable history: {why}. Each lane runs {FALLBACK_MARGIN:g}x its committed count ({runs})")
    return sizings, run_table(seed.get("platforms") or {}, sizings, source), source, warnings


def from_history(history: Mapping[str, Any], seed: Mapping[str, Any], deadlines: Deadlines,
                 jobs: Sequence[tuple[str, str, str, tuple[str, ...]]]
                 ) -> tuple[list[Sizing], dict[str, Any], str, list[str]]:
    lanes_by_platform = history.get("lanes") or {}
    if not all(lanes_by_platform.get(p) and (history.get("workers") or {}).get(p) for _, _, p, _ in jobs):
        raise ValueError("the history has no lanes or workers for a platform the gate runs on")
    durations_table = update_durations.table(dict(history))
    counts = committed_counts(seed)
    lanes_module = _lanes_module()
    sizings, warnings = [], []
    for _, _, platform, lanes in jobs:
        durations = lanes_module.durations_for(platform, durations_table)
        workers = int(history["workers"][platform])
        for lane in lanes:
            nodeids = sorted(n for n, ln in lanes_by_platform[platform].items() if ln == lane)
            kept = ((history.get("overhead") or {}).get(platform) or {}).get(lane) or []
            outside = statistics.median(kept) if kept else DEFAULT_OUTSIDE_S
            left = ((history.get("job_remaining") or {}).get(platform) or {}).get(lane) or []
            setup = max(0.0, deadlines.job_s - statistics.median(left)) if left else DEFAULT_SETUP_S
            s = size_lane(platform, lane, nodeids, durations, workers, outside, deadlines.budget_s(setup))
            s.committed = counts.get((platform, lane))
            s.shards = min(MAX_SHARDS, max(s.shards, s.committed or 0))
            sizings.append(s)
            if s.warning and s.tests:
                warnings.append(f"{platform} {lane}: {s.warning}")
            if s.need is not None and (s.committed is None or s.need > s.committed):
                warnings.append(f"{platform} {lane}: the history needs {s.need} shards and tests/durations.json gives "
                                f"{s.committed or 'none'}, so a fallback run has less margin than "
                                f"{FALLBACK_MARGIN:g}x; {REFRESH}")
    for platform in sorted({p for _, _, p, _ in jobs}):
        tests = set(durations_table["platforms"].get(platform) or {})
        known = set((seed.get("platforms") or {}).get(platform) or {})
        if tests and len(tests & known) / len(tests) < COVERAGE_WARNING:
            warnings.append(f"{platform}: tests/durations.json knows {len(tests & known) / len(tests):.0%} of the "
                            f"history's tests, under {COVERAGE_WARNING:.0%}; {REFRESH}")
    runs = history.get("runs") or []
    source = f"the median of {len(runs)} green `main` run(s), the last {runs[-1] if runs else '-'}"
    return sizings, run_table(durations_table["platforms"], sizings, source), source, warnings


def plan(history: Mapping[str, Any] | None, seed: Mapping[str, Any], deadlines: Deadlines,
         jobs: Sequence[tuple[str, str, str, tuple[str, ...]]], why: str = ""
         ) -> tuple[list[Sizing], dict[str, Any], str, list[str]]:
    """(each lane's sizing, the table the run's shards balance on, where the sizing came from, warnings)."""
    if not history or not history.get("runs"):
        return fallback(seed, deadlines, jobs, why or "no history of green `main` runs yet")
    try:
        return from_history(history, seed, deadlines, jobs)
    except Exception as exc:  # any shape history_problem missed: a history only balances shards (CRD-13)
        return fallback(seed, deadlines, jobs, f"the history could not be used ({type(exc).__name__}: {exc})")


REFERENCE_LANE = update_durations.ALL_LANES  # the history keeps a reference session's outside time under this lane
# The reference lane's rule since E26 (nightly.yml, `reference-plan`): grow the count when a shard nears 45 minutes,
# never the timeout.
REFERENCE_RULE_S = 45 * 60.0
# Measured: the same tests' time in each Windows reference shard, 2026-10-24 against 10-25 (two green nights' lane
# reports), was 0.893 to 1.089 times as long: a night may run a shard 9% over its estimate.
REFERENCE_NIGHT_VARIANCE = 1.09
# The most a reference shard's estimate may be: on a night that slow, it still ends before the rule's 45 minutes.
REFERENCE_TARGET_S = REFERENCE_RULE_S / REFERENCE_NIGHT_VARIANCE


def fallback_split(minutes: Mapping[str, float], jobs: int) -> dict[str, int]:
    """``jobs`` shards split over the platforms by their estimated minutes (largest remainder; at least one each, at
    most MAX_SHARDS each)."""
    if not sum(minutes.values()):
        minutes = dict.fromkeys(minutes, 1.0)  # a table that times none of them: an even split
    total = sum(minutes.values())
    share = {p: max(1.0, jobs * m / total) for p, m in minutes.items()}
    counts = {p: max(1, math.floor(s)) for p, s in share.items()}
    for p in sorted(share, key=lambda q: (counts[q] - share[q], q)):
        if sum(counts.values()) >= jobs:
            break
        counts[p] += 1
    return {p: min(MAX_SHARDS, n) for p, n in counts.items()}


def reference_plan(history: Mapping[str, Any] | None, seed: Mapping[str, Any], runners: Sequence[tuple[str, str, str]],
                   target_s: float = REFERENCE_TARGET_S, why: str = "", jobs: int = CONCURRENT_JOBS
                   ) -> tuple[list[Sizing], dict[str, Any], str, list[str]]:
    """Each reference runner's shards: the fewest whose slowest shard, estimated from the history's medians (its tests'
    seconds in one process, plus the session's time outside them), is at most ``target_s``. With no usable history
    the runners share ``jobs`` (what the account's concurrent jobs leave beside the nightly's others) by their minutes
    in the committed table, balanced on it: measured under xdist, it cannot size a serial shard, but it splits the
    jobs, until a night's passing shards are recorded."""
    platforms = [p for _, _, p in runners]
    tests = (history or {}).get("lanes") or {}
    if not history or not history.get("runs") or not all(tests.get(p) for p in platforms):
        lanes_module = _lanes_module()
        minutes = {}
        for p in platforms:
            durations = lanes_module.durations_for(p, seed)
            minutes[p] = sum(lanes_module.weights(sorted(durations), durations).values()) / 60
        counts = fallback_split(minutes, jobs)
        sizings = [Sizing(p, REFERENCE_LANE, counts[p], 0, 0.0, target_s) for p in platforms]
        split = ", ".join(f"{p} {counts[p]}" for p in platforms)
        source = (f"no usable reference history ({why or 'it has no tests for a platform the lane runs on'}): the "
                  f"{jobs} jobs the account's {CONCURRENT_JOBS} leave, split by tests/durations.json's minutes "
                  f"({split}) and balanced on it")
        return sizings, run_table(seed.get("platforms") or {}, sizings, source), source, [source]
    durations_table = update_durations.table(dict(history))
    lanes_module = _lanes_module()
    sizings, warnings = [], []
    for platform in platforms:
        kept = ((history.get("overhead") or {}).get(platform) or {}).get(REFERENCE_LANE) or []
        s = size_lane(platform, REFERENCE_LANE, sorted(tests[platform]),
                      lanes_module.durations_for(platform, durations_table), 1,
                      statistics.median(kept) if kept else DEFAULT_OUTSIDE_S, target_s)
        sizings.append(s)
        if s.warning:
            warnings.append(f"{platform} reference: {s.warning}")
    runs = history["runs"]
    source = f"the median of {len(runs)} nightly reference run(s), the last {runs[-1]}"
    return sizings, run_table(durations_table["platforms"], sizings, source), source, warnings


def reference_matrix(sizings: Sequence[Sizing], runners: Sequence[tuple[str, str, str]]) -> dict[str, Any]:
    """The `reference` job's matrix: per runner, shards 1..N of N."""
    count = {s.platform: s.shards for s in sizings}
    return {"include": [{"os": os_, "python": python, "shard": k, "of": count[platform]}
                        for os_, python, platform in runners for k in range(1, count[platform] + 1)]}


def starting_jobs(workflow: Path, besides: str) -> int:
    """At least how many jobs of ``workflow`` start with the run beside ``besides`` (each job that needs none, a matrix
    counted by its axes, or else by its include list), so they share the account's concurrent jobs with it."""
    import yaml

    total = 0
    for name, job in ((yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}).get("jobs") or {}).items():
        if name == besides or job.get("needs"):
            continue
        axes = {k: v for k, v in ((job.get("strategy") or {}).get("matrix") or {}).items()
                if k not in ("include", "exclude") and isinstance(v, list)}
        include = ((job.get("strategy") or {}).get("matrix") or {}).get("include")
        total += math.prod(len(v) for v in axes.values()) if axes else len(include) if isinstance(include, list) else 1
    return total


def reference_summary(sizings: Sequence[Sizing], source: str, warnings: Sequence[str], target_s: float,
                      beside: int) -> tuple[str, list[str]]:
    jobs = sum(s.shards for s in sizings)
    lines = ["## Reference shards (tools/ci/shard_plan.py --reference)", "",
             f"Sized from {source}. Each shard's estimate is at most {target_s / 60:.1f} minutes.", "",
             "| Platform | Shards | Tests | Slowest shard (est.) |", "|---|---|---|---|"]
    lines += [f"| {s.platform} | {s.shards} | {s.tests or '-'} | "
              f"{f'{s.slowest_s / 60:.1f} min' if s.tests else '-'} |" for s in sizings]
    out = list(warnings)
    if jobs + beside > CONCURRENT_JOBS:
        out.append(f"the nightly starts {jobs} reference jobs beside at least {beside} others, more than the account's "
                   f"{CONCURRENT_JOBS} concurrent jobs: some queue")
    lines += ["", f"{jobs} reference jobs beside at least {beside} others."]
    if out:
        lines += ["", "### Warnings (reported, never gating)", ""] + [f"- {w}" for w in out]
    return "\n".join(lines) + "\n", out


def matrix(sizings: Sequence[Sizing], jobs: Sequence[tuple[str, str, str, tuple[str, ...]]]) -> dict[str, Any]:
    """The `lanes` job's matrix: per runner and lane, shards 1..N of N."""
    count = {(s.platform, s.lane): s.shards for s in sizings}
    return {"include": [{"os": os_, "python": python, "lane": lane, "shard": k, "of": count[(platform, lane)]}
                        for os_, python, platform, lanes in jobs for lane in lanes
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


def summary(sizings: Sequence[Sizing], source: str, warnings: Sequence[str], extra_jobs: int) -> tuple[str, list[str]]:
    lane_jobs_n = sum(s.shards for s in sizings)
    lines = ["## Shards (tools/ci/shard_plan.py)", "",
             f"Sized from {source}. A shard's budget on the history's runners leaves room for a runner "
             f"{RUNNER_VARIANCE:g}x slower, its setup included.", "",
             "| Platform | Lane | Shards | History needs | Committed | Tests | Slowest shard (est.) | Budget |",
             "|---|---|---|---|---|---|---|---|"]
    for s in sizings:
        est = f"{s.slowest_s / 60:.1f} min" if s.tests else "-"
        lines.append(f"| {s.platform} | {s.lane} | {s.shards} | {s.need if s.need is not None else '-'} | "
                     f"{s.committed if s.committed is not None else '-'} | {s.tests or '-'} | {est} | "
                     f"{s.budget_s / 60:.1f} min |")
    out = list(warnings)
    if lane_jobs_n + extra_jobs > CONCURRENT_JOBS:
        out.append(f"a full run starts {lane_jobs_n} lane jobs and at least {extra_jobs} others, more than the "
                   f"account's {CONCURRENT_JOBS} concurrent jobs: it queues behind itself (register E42, E52)")
    lines += ["", f"{lane_jobs_n} lane jobs."]
    if out:
        lines += ["", "### Warnings (reported, never gating)", ""] + [f"- {w}" for w in out]
    return "\n".join(lines) + "\n", out


def reference_main(args: argparse.Namespace, seed: Mapping[str, Any]) -> int:
    runners = []
    for spec in args.runner:
        os_, _, python = spec.partition(":")
        if os_ not in PLATFORM_OF_OS or not python:
            raise SystemExit(f"--runner {spec}: expected OS:PYTHON with OS one of {', '.join(PLATFORM_OF_OS)}")
        runners.append((os_, python, PLATFORM_OF_OS[os_]))
    history, why = update_durations.read_history(args.history, of="the nightly's reference shards")
    beside = starting_jobs(args.workflows / "nightly.yml", besides="reference-plan")
    sizings, durations_table, source, warnings = reference_plan(history, seed, runners, REFERENCE_TARGET_S, why,
                                                                jobs=CONCURRENT_JOBS - beside)
    update_durations.write_json(args.durations_out, durations_table)
    text, warnings = reference_summary(sizings, source, warnings, REFERENCE_TARGET_S, beside)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"reference_matrix={json.dumps(reference_matrix(sizings, runners), separators=(',', ':'))}\n")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    for w in warnings:
        print(f"::warning title=reference shards::{w}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--history", type=Path, required=True, metavar="FILE", help="the rolling history (may be missing)")
    ap.add_argument("--seed", type=Path, required=True, metavar="FILE",
                    help="the committed table (tests/durations.json)")
    ap.add_argument("--durations-out", type=Path, required=True, metavar="FILE",
                    help="the table this run's shards balance on")
    ap.add_argument("--workflows", type=Path, default=WORKFLOWS, metavar="DIR")
    ap.add_argument("--github-output", type=Path, metavar="FILE", help="append lanes_matrix=<json> here")
    ap.add_argument("--summary", type=Path, metavar="FILE", help="append the Markdown summary here")
    ap.add_argument("--reference", action="store_true",
                    help="size the nightly's reference lane (nightly.yml `reference`) from its own history")
    ap.add_argument("--runner", action="append", default=[], metavar="OS:PYTHON",
                    help="with --reference: a runner the reference lane runs on (repeat for each)")
    args = ap.parse_args(argv)
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    if args.reference:
        if not args.runner:
            ap.error("--reference needs --runner")
        return reference_main(args, seed)
    history, why = update_durations.read_history(args.history)
    jobs = lane_jobs(args.workflows)
    sizings, durations_table, source, warnings = plan(history, seed, lanes_deadlines(args.workflows), jobs, why)
    update_durations.write_json(args.durations_out, durations_table)
    text, warnings = summary(sizings, source, warnings, other_jobs(args.workflows))
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"lanes_matrix={json.dumps(matrix(sizings, jobs), separators=(',', ':'))}\n")
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    for w in warnings:
        print(f"::warning title=shards::{w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
