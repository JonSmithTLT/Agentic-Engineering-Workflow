"""CI lanes, shards and lane reports (docs/implementation/testing-and-ci-strategy.md).

Every test belongs to exactly one lane, decided by a pure function of its path and markers. CI runs
each lane as its own job (optionally split into shards), and a final assurance job proves from the
lane reports that every collected test ran exactly once. Nothing here changes what a test asserts.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Generator, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

LANES = ("fast", "integration", "acceptance", "regression", "adversarial", "serial", "live")
LIVE_DIR = "tests/live/"
LANE_KEY = pytest.StashKey[str]()
REPORT_SCHEMA = "aew/lane-report/v1"
DURATIONS_SCHEMA = "aew/test-durations/v1"
# `aew` processes each test started through the test helper (`conftest.run_aew`), by node id: the cost record's
# "CLI calls per test" (CI redesign P4, register E43). Counted in the process that runs the test, carried to the
# report writer in the teardown report's user properties (xdist sends those to the controller).
CLI_CALLS: Counter[str] = Counter()
CLI_CALLS_PROPERTY = "aew_cli_calls"


def count_cli_call() -> None:
    """Count one `aew` process for the running test (its node id from pytest's ``PYTEST_CURRENT_TEST``)."""
    current = os.environ.get("PYTEST_CURRENT_TEST")
    if current:
        CLI_CALLS[current.rsplit(" (", 1)[0]] += 1
SERIAL_UNDER_XDIST = (
    "serial test collected by an xdist worker: its property is timing or real-process concurrency, so it "
    "must never share the machine with other tests. Run it with `pytest --lane serial -p no:xdist` "
    "(or `-m serial` without -n) and the rest with `-m \"not serial\" -n auto`."
)


class Unclassified(Exception):
    """A test that maps to no lane: classify it (a directory below or a lane marker) before it can run."""


def lane_of(path: str, markers: Iterable[str]) -> str:
    """The single lane of a test. ``path`` is the nodeid's file part relative to the rootdir (``/``-separated).

    First match wins: the opt-in live lane (real harness binaries and models; collected only with ``--live``, never
    part of CI assurance), then the cross-cutting properties (serial, acceptance, exploratory), then the directory.
    """
    if path.startswith(LIVE_DIR):
        return "live"
    marks = set(markers)
    if "serial" in marks:
        return "serial"
    if "acceptance" in marks:
        return "acceptance"
    if "exploratory" in marks:
        return "adversarial"
    if path.startswith("tests/unit/") or path == "tests/test_spec_pin.py":
        return "fast"
    if path.startswith("tests/integration/"):
        return "integration"
    if path.startswith("tests/regression/"):
        return "regression"
    raise Unclassified(
        f"{path} belongs to no CI lane: put it under tests/unit, tests/integration or tests/regression, or give it "
        "a lane marker (see docs/implementation/testing-and-ci-strategy.md, 'Classifying a new test')")


def parse_shard(spec: str) -> tuple[int, int]:
    """``"k/N"`` (1-based) -> (k, N)."""
    try:
        k, n = (int(x) for x in spec.split("/"))
    except ValueError:
        raise pytest.UsageError(f"--shard expects k/N, got {spec!r}") from None
    if not 1 <= k <= n:
        raise pytest.UsageError(f"--shard {spec}: need 1 <= k <= N")
    return k, n


def partition(nodeids: Sequence[str], durations: Mapping[str, float], shards: int) -> list[list[str]]:
    """Deterministic longest-processing-time partition into ``shards`` bins.

    Every nodeid lands in exactly one bin whatever the durations say; durations only affect balance.
    Tests without a recorded duration count as the mean of the recorded ones: the median of a suite of millisecond
    tests is 0, which piled every new test into one shard (equal weights = round-robin by nodeid).
    """
    known = [durations[n] for n in nodeids if n in durations]
    default = statistics.fmean(known) if known else 1.0
    weight = {n: float(durations.get(n, default)) for n in nodeids}
    bins: list[list[str]] = [[] for _ in range(shards)]
    loads = [0.0] * shards
    for nid in sorted(nodeids, key=lambda n: (-weight[n], n)):
        i = min(range(shards), key=lambda b: (loads[b], b))
        bins[i].append(nid)
        loads[i] += weight[nid]
    return bins


def durations_for(platform: str, data: Mapping[str, Any]) -> dict[str, float]:
    """Recorded durations for ``platform``, filled in from other platforms (relative cost is similar)."""
    platforms = data.get("platforms", {}) if data else {}
    merged: dict[str, float] = {}
    for name, table in sorted(platforms.items()):
        if name != platform:
            merged.update(table)
    merged.update(platforms.get(platform, {}))
    return merged


def outcome_of(phases: Mapping[str, str]) -> str:
    """Collapse per-phase outcomes (setup/call/teardown -> passed|failed|skipped|xfailed|xpassed) into one."""
    values = set(phases.values())
    if phases.get("setup") == "failed" or phases.get("teardown") == "failed":
        return "error"
    for worst in ("failed", "xpassed", "xfailed", "skipped"):
        if worst in values:
            return worst
    return "passed"


def _report_outcome(report: pytest.TestReport) -> str:
    if hasattr(report, "wasxfail"):
        return "xfailed" if report.skipped else "xpassed"
    return report.outcome


def _is_worker(config: pytest.Config) -> bool:
    return hasattr(config, "workerinput")


def _checkout_state(root: Path, ignore: Iterable[Path]) -> dict[str, Any]:
    """What a test must never change: the AEW checkout (its status and the content of every dirty path) and the
    user's global git config."""
    ignored = {p.resolve() for p in ignore}
    status = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root,
                            capture_output=True)
    dirty: dict[str, str] = {}
    for entry in status.stdout.decode("utf-8", "replace").split("\0") if status.returncode == 0 else []:
        path = (root / entry[3:]).resolve()
        if len(entry) > 3 and path not in ignored and not ignored.intersection(path.parents):
            try:
                digest = hashlib.sha256((root / entry[3:]).read_bytes()).hexdigest()[:16]
            except OSError:
                digest = "-"
            dirty[f"{entry[:2]} {entry[3:]}"] = digest
    glob = subprocess.run(["git", "config", "--global", "--list"], capture_output=True, text=True)
    return {"status": status.returncode, "dirty": dirty, "global_git_config": (glob.returncode, glob.stdout)}


def describe_change(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes = []
    for key in sorted(set(before["dirty"]) | set(after["dirty"])):
        was, now = before["dirty"].get(key), after["dirty"].get(key)
        if was != now:
            changes.append(f"{'appeared' if was is None else 'vanished' if now is None else 'content changed'}: {key}")
    if before["global_git_config"] != after["global_git_config"]:
        changes.append("the global git config changed")
    if before["status"] != after["status"]:
        changes.append("the checkout's git status could not be read the same way")
    return changes


class LanePlugin:
    """Selects a lane and shard, refuses serial tests under xdist, guards isolation, writes the lane report."""

    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.root = Path(str(config.rootpath))
        self.lane: str | None = config.getoption("aew_lane")
        spec = config.getoption("aew_shard")
        self.shard = parse_shard(spec) if spec else None
        self.report_path = config.getoption("aew_lane_report")
        self.collected: list[str] = []
        self.lanes: dict[str, str] = {}  # every collected test's lane: assurance requires only the tier's lanes (P1)
        self.phases: dict[str, dict[str, str]] = {}
        self.durations: dict[str, float] = {}
        self.cli_calls: dict[str, int] = {}
        self.started = time.perf_counter()
        self.guard_before: dict[str, Any] | None = None

    # ------------------------------------------------------------------ selection

    def _load_durations(self) -> dict[str, float]:
        path = Path(self.config.getoption("aew_durations_file") or self.root / "tests" / "durations.json")
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != DURATIONS_SCHEMA:
            raise pytest.UsageError(f"{path}: expected schema {DURATIONS_SCHEMA}")
        return durations_for(sys.platform, data)

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, config: pytest.Config, items: list[pytest.Item]) -> None:
        lanes: dict[str, str] = {}
        problems = []
        for item in items:
            try:
                lanes[item.nodeid] = lane_of(item.nodeid.split("::")[0], (m.name for m in item.iter_markers()))
            except Unclassified as exc:
                problems.append(str(exc))
        if problems:
            raise pytest.UsageError("unclassified tests:\n  " + "\n  ".join(sorted(set(problems))))
        self.collected = [item.nodeid for item in items]
        self.lanes = lanes
        if _is_worker(config):
            config.workeroutput["aew_collected"] = self.collected  # type: ignore[attr-defined]
            config.workeroutput["aew_lanes"] = self.lanes  # type: ignore[attr-defined]
        keep = [i for i in items if self.lane is None or lanes[i.nodeid] == self.lane]
        if self.shard:
            k, n = self.shard
            mine = set(partition([i.nodeid for i in keep], self._load_durations(), n)[k - 1])
            keep = [i for i in keep if i.nodeid in mine]
        for item in items:
            item.stash[LANE_KEY] = lanes[item.nodeid]
        dropped = [i for i in items if i not in keep]
        if dropped:
            config.hook.pytest_deselected(items=dropped)
            items[:] = keep

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        if _is_worker(item.config) and item.stash.get(LANE_KEY, None) == "serial":
            pytest.fail(SERIAL_UNDER_XDIST, pytrace=False)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any, None]:
        if call.when == "teardown":
            calls = CLI_CALLS.pop(item.nodeid, 0)
            if calls:
                item.user_properties.append((CLI_CALLS_PROPERTY, calls))
        yield

    # ------------------------------------------------------------------ reporting

    def pytest_report_header(self, config: pytest.Config) -> str | None:
        if self.lane or self.shard:
            shard = f" shard {self.shard[0]}/{self.shard[1]}" if self.shard else ""
            return f"aew lane: {self.lane or 'all'}{shard}"
        return None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.phases.setdefault(report.nodeid, {})[report.when] = _report_outcome(report)
        self.durations[report.nodeid] = self.durations.get(report.nodeid, 0.0) + report.duration
        for name, value in report.user_properties:
            if name == CLI_CALLS_PROPERTY and report.when == "teardown":
                self.cli_calls[report.nodeid] = int(value)

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: Any, error: Any) -> None:
        collected = getattr(node, "workeroutput", {}).get("aew_collected")
        if collected and not self.collected:
            self.collected = list(collected)
            self.lanes = dict(getattr(node, "workeroutput", {}).get("aew_lanes") or {})

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        if not _is_worker(self.config):
            self.guard_before = _checkout_state(self.root, self._own_outputs())

    def _own_outputs(self) -> list[Path]:
        """What the session itself writes, and may write inside the checkout: the reports, and the directory a failed
        harness test's evidence is copied to (everything under it; #136 review, F4)."""
        outs = [self.report_path, getattr(self.config.option, "xmlpath", None)]
        import harness_diagnostics

        outs.append(harness_diagnostics.evidence_dir(self.config))  # None when there is nowhere to copy to
        return [Path(p) for p in outs if p]

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if _is_worker(self.config):
            return
        if self.guard_before is not None:
            changes = describe_change(self.guard_before, _checkout_state(self.root, self._own_outputs()))
            if changes:
                session.exitstatus = pytest.ExitCode.TESTS_FAILED
                tr = self.config.pluginmanager.get_plugin("terminalreporter")
                if tr:
                    tr.write_sep("!", "isolation guard: the test session changed shared state", red=True)
                    for line in changes:
                        tr.write_line(f"  {line}")
                    tr.write_line("  (a test wrote outside its tmp_path; "
                                  "if you edited the checkout during the run, rerun)")
        if self.report_path:
            self._write_report(int(session.exitstatus))

    def _write_report(self, exitstatus: int) -> None:
        xdist = self.config.getoption("numprocesses", None) if self.config.pluginmanager.hasplugin("xdist") else None
        report = {
            "schema": REPORT_SCHEMA,
            "platform": sys.platform,
            "python": ".".join(map(str, sys.version_info[:3])),
            "lane": self.lane,
            "shard": f"{self.shard[0]}/{self.shard[1]}" if self.shard else None,
            "xdist_workers": xdist,
            "exitstatus": exitstatus,
            "wall_s": round(time.perf_counter() - self.started, 2),
            "collected": sorted(self.collected),
            "lanes": dict(sorted(self.lanes.items())),
            "results": {nid: {"outcome": outcome_of(ph), "duration": round(self.durations.get(nid, 0.0), 3)}
                        for nid, ph in sorted(self.phases.items())},
            "cli_calls": dict(sorted(self.cli_calls.items())),
        }
        path = Path(self.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def process_isolation():
    """Every test leaves its process as it found it: no leaked AEW_* variable, no changed working directory.

    Part of the evidence that lets non-serial tests share an xdist worker process.
    """
    env = {k: v for k, v in os.environ.items() if k.startswith("AEW_")}
    cwd = os.getcwd()
    yield
    after = {k: v for k, v in os.environ.items() if k.startswith("AEW_")}
    moved = os.getcwd()
    if after != env or moved != cwd:
        for k in set(after) - set(env):
            del os.environ[k]
        os.environ.update(env)
        os.chdir(cwd)
        pytest.fail(f"test leaked process state: env {env} -> {after}, cwd {cwd} -> {moved}", pytrace=False)


def ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """``tests/live`` is collected only with ``--live``: CI never collects it, so assurance is unaffected."""
    if config.getoption("aew_live"):
        return None
    live = Path(str(config.rootpath)) / LIVE_DIR
    try:
        Path(collection_path).resolve().relative_to(live.resolve())
    except ValueError:
        return None
    return True


def addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("aew-lanes", "AEW CI lanes (docs/implementation/testing-and-ci-strategy.md)")
    group.addoption("--live", dest="aew_live", action="store_true", default=False,
                    help="also collect tests/live: real harness binaries and real models (opt-in; never CI)")
    group.addoption("--lane", dest="aew_lane", choices=LANES, default=None,
                    help="run only this lane's tests")
    group.addoption("--shard", dest="aew_shard", default=None, metavar="K/N",
                    help="run only shard K of N (deterministic, duration-balanced)")
    group.addoption("--durations-file", dest="aew_durations_file", default=None,
                    help="recorded test durations used to balance shards (default tests/durations.json)")
    group.addoption("--lane-report", dest="aew_lane_report", default=None, metavar="PATH",
                    help="write the collected set and per-test outcomes as JSON (read by tools/ci/check_assurance.py)")


def configure(config: pytest.Config) -> None:
    config.pluginmanager.register(LanePlugin(config), "aew-lanes")
