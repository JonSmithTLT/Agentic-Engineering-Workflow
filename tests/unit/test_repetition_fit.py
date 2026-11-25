"""The nightly's repetition sessions fit the recorded time of the tests they run (register E75's fit pin; plan v6,
G3a-r2 item 3).

The nightly runs some sessions outside the shard sizer (tools/ci/shard_plan.py): one process, no ``--shard``. They are
the race-and-kill job's serial lane ten times and its racing writers, and the crash job's randomized iterations. Their
``--test-timeout``, ``--session-deadline`` and job deadline were literals that nothing checked against the time their
tests take. The serial lane grew to 98 tests, and on 2026-11-24 and 11-25 (runs 45463965123 and 45698876718) its first
Windows repetition reached its 270 s deadline with the next test just started. Each session's autopsy recorder shows no
stall: the first test started 69.8 s and 46.3 s into the session (a cold collection), and the tests ran at the
record's pace (0.97x to 0.98x the recorded time of the same tests).

Each fact has one owner, and this pin reads them there:
- the budgets: the workflow (``bounds.workflow_lanes`` parses every pytest command, with its job's deadline);
- the tests' time: tests/durations.json, the table a green `main` run measures and CI refreshes, weighted for each
  platform as the shard sizer weights it (``lanes.durations_for``, ``lanes.weights``);
- which tests a session runs: the collection (``lanes.lane_of`` through the session's lane plugin), filtered by the
  command's ``--lane``, ``-k`` and test paths;
- what a knob multiplies: the test module's own default for it (:data:`SCALES`).

The rule, for each session on each platform the record holds, with ``work`` its tests' recorded seconds times its
knobs' ratio and ``longest`` its longest test's:
- ``--test-timeout`` is at least :data:`MARGIN` x ``longest``: a slow test is not cut as a hang;
- ``--session-deadline`` is at least :data:`COLD_START_S` + :data:`MARGIN` x ``work``: a slow night fits;
- ``--session-deadline`` is at least :data:`COLD_START_S` + ``work`` + ``--test-timeout``: a test that hangs anywhere in
  a pass at the record's pace fails by name, with its stack, before the session ends (at 240 s within 270 s, a hang
  after the first 30 s could only end the whole session);
- the job's ``AEW_JOB_DEADLINE`` holds its setup and every session at the slow night's pace, its repetitions included.

Known limits:
- a test the record does not hold yet is weighed as ``lanes.weights`` estimates it, by its file's or directory's
  mean. The serial lane's slowest new test (``test_validation_coverage_disclosure``, 26.3 s on Windows on 11-25) was
  estimated at 3.8 s, so until the record is refreshed (register E111, N4) the margin carries it;
- a platform's missing tests are filled from the other's (``lanes.durations_for``), so a test skipped on one platform
  still counts there: the estimate errs long;
- ``-k`` is read as one name matched against node ids; another expression fails this pin, to be taught here;
- a knob multiplies every test the session selects, which errs long where it drives only some of them;
- sessions under xdist (the walk blocks) and the sharded reference lane are out of scope: the shard sizer sizes the
  reference lane, and a parallel session's time is not its tests' sum.
"""

from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import bounds
import lanes
import pytest
from test_ci_tools import ROOT, shard_plan

WORKFLOWS = ROOT / ".github" / "workflows"
FITTED = "nightly.yml"
# The longest wait from a repetition's start to its first test, cold: 69.8 s in run 45463965123 (2026-11-24, Windows,
# repetition 1; 46.3 s in run 45698876718), from the session's autopsy recorder. Every session is given it: a later
# repetition collects warm, so this errs long.
COLD_START_S = 70.0
# The spread of the nightly's Windows repetitions from night to night, about 25% either side (11-01 to 11-25: passing
# first repetitions from 133 to 238 s), over the record that sits inside it: the failing nights ran their tests at
# 0.97x to 0.98x the record.
MARGIN = 1.25
# A knob a fitted session sets, and the module constant that holds the merge gate's value, which the record measured.
SCALES = {
    "AEW_RACE_WRITES": ("tests/integration/test_store_processes.py", "RACE_WRITES_DEFAULT"),
    "AEW_CRASH_ITERATIONS": ("tests/unit/test_store.py", "CRASH_ITERATIONS_DEFAULT"),
}
TABLE = ROOT / "tests" / "durations.json"


def fitted_sessions(workflows: Path = WORKFLOWS) -> list[bounds.Lane]:
    """The nightly's sessions outside the shard sizer: one process (no ``-n``) and no ``--shard``."""
    return [lane for lane in bounds.workflow_lanes(workflows)
            if lane.workflow == FITTED and not lane.xdist and lane.shard is None]


def module_constant(relative: str, name: str, root: Path = ROOT) -> float:
    """A test module's module-level ``NAME = <number>``, read without importing the module."""
    tree = ast.parse((root / relative).read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, int | float)):
            return float(node.value.value)
    raise AssertionError(f"{relative} has no module-level {name} = <number>")


def scale(session: bounds.Lane, root: Path = ROOT) -> float:
    """How many times the record's work each test of ``session`` does: the product of its knobs' ratios."""
    ratio = 1.0
    for knob, value in session.env.items():
        if knob in SCALES:
            ratio *= float(value) / module_constant(*SCALES[knob], root=root)
    return ratio


def unscaled_knobs(session: bounds.Lane) -> list[str]:
    """The AEW_ knobs a session's job or step sets that :data:`SCALES` does not say how to scale."""
    return sorted(k for k in session.env if k.startswith("AEW_") and k not in SCALES)


def selected(session: bounds.Lane, suite: Mapping[str, str]) -> list[str]:
    """The node ids ``session`` runs, from every collected node id and its lane."""
    keyword = session.keyword
    if keyword is not None and not keyword.isidentifier():
        raise AssertionError(f"{session.label}: -k {keyword!r} is not one name; teach selected() its expression")
    return sorted(node for node, lane in suite.items()
                  if (session.lane is None or lane == session.lane)
                  and (keyword is None or keyword in node)
                  and (not session.paths or any(node == p or node.startswith(p.rstrip("/") + ("::" if p.endswith(".py")
                                                                                         else "/"))
                                                for p in session.paths)))


def need(nodeids: Sequence[str], durations: Mapping[str, float], ratio: float) -> tuple[float, float]:
    """(work, longest): the session's recorded seconds and its longest test's, both times ``ratio``."""
    weight = lanes.weights(nodeids, durations)
    return ratio * sum(weight.values()), ratio * max(weight.values(), default=0.0)


def session_problems(session: bounds.Lane, work: float, longest: float, platform: str) -> list[str]:
    """What breaks the fit for one session on one platform (the module's rule)."""
    problems = []
    timeout, deadline = session.test_timeout_s, session.deadline_s
    if timeout is None or deadline is None:
        return [f"{session.label}: no --test-timeout or --session-deadline to fit"]
    where = f"{session.label} on {platform} ({work:.0f} s of recorded tests, the longest {longest:.0f} s)"
    if timeout < MARGIN * longest:
        problems.append(f"{where}: --test-timeout {timeout:g} is under {MARGIN:g} x the longest test, "
                        f"{MARGIN * longest:.0f} s")
    slow = COLD_START_S + MARGIN * work
    if deadline < slow:
        problems.append(f"{where}: --session-deadline {deadline:g} is under a cold start and {MARGIN:g} x its tests, "
                        f"{slow:.0f} s")
    named = COLD_START_S + work + timeout
    if deadline < named:
        problems.append(f"{where}: --session-deadline {deadline:g} is under a cold start, its tests and its "
                        f"--test-timeout, {named:.0f} s, so a hang late in a pass would end the session instead of "
                        "failing by name")
    return problems


def job_problems(sessions: Sequence[tuple[bounds.Lane, float]], platform: str) -> list[str]:
    """Each job's AEW_JOB_DEADLINE holds its setup and all its sessions at the slow night's pace."""
    problems = []
    by_job: dict[str, list[tuple[bounds.Lane, float]]] = {}
    for session, work in sessions:
        by_job.setdefault(session.job, []).append((session, work))
    for job, members in sorted(by_job.items()):
        deadline = members[0][0].job_deadline_s
        total = shard_plan.DEFAULT_SETUP_S + sum(s.repeats * (COLD_START_S + MARGIN * work) for s, work in members)
        if deadline is None or deadline < total:
            problems.append(f"{FITTED} {job} on {platform}: AEW_JOB_DEADLINE start + {deadline} is under its setup "
                            f"and its sessions at {MARGIN:g} x their tests, {math.ceil(total)} s")
    return problems


def fit_problems(sessions: Sequence[bounds.Lane], suite: Mapping[str, str], table: Mapping,
                 root: Path = ROOT) -> list[str]:
    problems = []
    for platform in sorted(table.get("platforms") or {}):
        durations = lanes.durations_for(platform, table)
        worked = []
        for session in sessions:
            nodeids = selected(session, suite)
            if not nodeids:
                problems.append(f"{session.label}: selects no collected test")
                continue
            work, longest = need(nodeids, durations, scale(session, root))
            problems += session_problems(session, work, longest, platform)
            worked.append((session, work))
        problems += job_problems(worked, platform)
    return problems


def _whole_suite(config: pytest.Config) -> bool:
    tests = (ROOT / "tests").resolve()
    return all(Path(str(arg).split("::")[0]).resolve() in (tests, ROOT.resolve()) for arg in config.args)


@pytest.fixture(scope="module")
def suite(request) -> dict[str, str]:
    """Every collected node id and its lane: this session's, when it collected the whole suite (CI's fast lane does),
    else a collection of its own."""
    plugin = request.config.pluginmanager.get_plugin("aew-lanes")
    if plugin is not None and plugin.lanes and _whole_suite(request.config):
        return dict(plugin.lanes)
    report = Path(request.getfixturevalue("tmp_path_factory").mktemp("collection")) / "lanes.json"
    subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                    f"--lane-report={report}"], cwd=ROOT, capture_output=True, text=True,
                   timeout=bounds.seconds(bounds.WATCHDOG), stdin=subprocess.DEVNULL,
                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    return json.loads(report.read_text(encoding="utf-8"))["lanes"]


def test_every_nightly_repetition_session_and_its_job_fit_the_recorded_time_of_its_tests(suite):
    sessions = fitted_sessions()
    # Not vacuous: the serial lane's repetitions, the racing writers and the crash iterations are all fitted.
    assert any(s.lane == "serial" and s.repeats > 1 for s in sessions)
    assert {s.job for s in sessions} >= {"race-repeat", "crash-extended"}
    problems = fit_problems(sessions, suite, json.loads(TABLE.read_text(encoding="utf-8")))
    assert problems == [], "raise the budget to fit, from the record (nightly.yml's race-repeat comment):\n" + \
        "\n".join(problems)


def test_every_knob_a_fitted_session_sets_says_how_it_scales_the_recorded_time():
    unscaled = {s.label: unscaled_knobs(s) for s in fitted_sessions() if unscaled_knobs(s)}
    assert unscaled == {}, "add each knob to SCALES with the module constant of its merge-gate value"
    assert all(module_constant(*where) > 0 for where in SCALES.values())


def _session(**kw) -> bounds.Lane:
    fields = {"workflow": FITTED, "job": "race-repeat", "step": "serial lane x10", "command": "", "job_timeout_s": None,
              "test_timeout_s": 240.0, "deadline_s": 270.0, "margin_s": 30.0, "lane": "serial", "xdist": False,
              "max_worker_restart": None, "hang_dir": None, "lane_report": None, "repeats": 10,
              "job_deadline_s": 3600.0}
    return bounds.Lane(**{**fields, **kw})


def test_a_deadline_that_leaves_a_late_hang_no_time_to_fail_by_name_fails_the_pin():
    # The nightly before this pin: 240 s per test inside 270 s per pass, for about 250 s of tests.
    problems = session_problems(_session(), work=250.0, longest=20.0, platform="win32")
    assert any("--session-deadline 270 is under a cold start and 1.25 x its tests, 382 s" in p for p in problems)
    assert any("so a hang late in a pass would end the session instead of failing by name" in p for p in problems)
    assert session_problems(_session(test_timeout_s=150.0, deadline_s=470.0), 250.0, 20.0, "win32") == []


def test_a_test_timeout_under_the_margin_over_the_longest_test_fails_the_pin():
    problems = session_problems(_session(test_timeout_s=24.0, deadline_s=1000.0), 250.0, 20.0, "win32")
    assert problems == [f"{_session().label} on win32 (250 s of recorded tests, the longest 20 s): --test-timeout 24 "
                        "is under 1.25 x the longest test, 25 s"]


def test_a_job_deadline_that_cannot_hold_its_repetitions_at_the_slow_pace_fails_the_pin():
    loop, racing = _session(), _session(step="racing writers", repeats=1)
    assert job_problems([(loop, 250.0), (racing, 50.0)], "win32") == [
        f"{FITTED} race-repeat on win32: AEW_JOB_DEADLINE start + 3600.0 is under its setup and its sessions at 1.25 x "
        f"their tests, {math.ceil(shard_plan.DEFAULT_SETUP_S + 10 * (70 + 312.5) + 70 + 62.5)} s"]
    assert job_problems([(_session(job_deadline_s=4320.0), 250.0), (racing, 50.0)], "win32") == []


def test_a_session_selects_by_its_lane_its_keyword_and_its_paths_and_scales_by_its_knobs(tmp_path):
    suite = {"tests/integration/test_store_processes.py::test_two_racing_writers_lose_no_updates": "serial",
             "tests/integration/test_store_processes.py::test_stale_revision_from_another_process": "serial",
             "tests/unit/test_store.py::test_randomized_crash_iterations": "fast",
             "tests/unit/test_store.py::test_other": "fast"}
    assert selected(_session(keyword="racing_writers"), suite) == [
        "tests/integration/test_store_processes.py::test_two_racing_writers_lose_no_updates"]
    crash = _session(lane=None, paths=("tests/unit/test_store.py::test_randomized_crash_iterations",))
    assert selected(crash, suite) == ["tests/unit/test_store.py::test_randomized_crash_iterations"]
    assert selected(_session(lane=None, paths=("tests/unit/test_store.py",)), suite) == [
        "tests/unit/test_store.py::test_other", "tests/unit/test_store.py::test_randomized_crash_iterations"]
    with pytest.raises(AssertionError, match="is not one name"):
        selected(_session(keyword="a or b"), suite)
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_store.py").write_text("CRASH_ITERATIONS_DEFAULT = 200\n", encoding="utf-8")
    assert scale(_session(env={"AEW_CRASH_ITERATIONS": "2000", "AEW_OTHER": "1"}), root=tmp_path) == 10.0
    assert unscaled_knobs(_session(env={"AEW_CRASH_ITERATIONS": "2000", "AEW_OTHER": "1"})) == ["AEW_OTHER"]
