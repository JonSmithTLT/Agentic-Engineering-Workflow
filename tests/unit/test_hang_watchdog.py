"""The per-test hang watchdog (tests/helpers/watchdog.py; strategy §3, "A test that hangs fails by name"): a test
still running after ``--test-timeout`` is named with every thread's stack, instead of holding its CI job until the job
is cancelled and nothing is recorded (the 2026-10-08 integration hangs). On POSIX it fails in place and the run
carries on; on Windows the stacks are written to the dump file the CI job uploads."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import autopsy
import bounds
import lanes
import pytest
import watchdog
from conftest import IS_WINDOWS

HELPERS = Path(lanes.__file__).resolve().parent
CONFTEST = f'''
import sys
sys.path.insert(0, {str(HELPERS)!r})
import lanes
import watchdog


def pytest_addoption(parser):
    lanes.addoption(parser)
    watchdog.addoption(parser)


def pytest_configure(config):
    lanes.configure(config)
    watchdog.configure(config)
'''
HANGS = '''import socket


def test_quick():
    pass


def test_hangs_forever():
    a, b = socket.socketpair()  # a blocking read nobody will answer, as the dashboard's wake handshake was
    a.recv(1)


def test_after():
    pass
'''
SLOW = '''import time


def test_outlives_its_limit():
    time.sleep(8)  # long enough for the limit, short enough to end on Windows, where the test runs on
'''


def project(tmp_path: Path, tests: str) -> Path:
    root = tmp_path / "proj"
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")  # the scratch project is its own rootdir
    (root / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (root / "tests" / "unit" / "test_w.py").write_text(tests, encoding="utf-8")
    return root


def inner_pytest(root: Path, hangs: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], float]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))}
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    started = time.monotonic()
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--hang-dir", str(hangs),
                           *args, "tests"], cwd=root, env=env, capture_output=True, text=True, timeout=240, **kwargs)
    return proc, time.monotonic() - started


def dumps(hangs: Path) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in sorted(hangs.glob("hang-*.txt"))] if hangs.exists() else []


@pytest.mark.serial
@pytest.mark.skipif(not watchdog.USE_ALARM, reason="needs SIGALRM to interrupt a blocking call (POSIX); "
                                                   "Windows records the stacks only, tested below")
@pytest.mark.parametrize("mode", [("-n", "2", "--dist", "worksteal"), ("-p", "no:xdist")], ids=["xdist", "no_xdist"])
def test_a_hung_test_fails_in_place_by_name_with_its_stack_and_the_run_carries_on(tmp_path, mode):
    report, hangs = tmp_path / "r.json", tmp_path / "hangs"
    proc, took = inner_pytest(project(tmp_path, HANGS), hangs, "--test-timeout", "3", "--lane-report", str(report),
                              *mode)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1 and "INTERNALERROR" not in out, out
    assert "HungTest" in out and "test_w.py::test_hangs_forever was still running after 3s" in out, out
    assert "in test_hangs_forever" in out, out  # the stack names the line the test is stuck on
    assert took < 120, took
    results = json.loads(report.read_text(encoding="utf-8"))["results"]
    assert results["tests/unit/test_w.py::test_hangs_forever"]["outcome"] == "failed"
    assert results["tests/unit/test_w.py::test_after"]["outcome"] == "passed"  # one hang costs only its own limit
    assert results["tests/unit/test_w.py::test_quick"]["outcome"] == "passed"
    named = [d for d in dumps(hangs) if "test_hangs_forever was still running" in d]
    assert len(named) == 1 and "in test_hangs_forever" in named[0], dumps(hangs)


def test_a_test_that_outlives_its_limit_leaves_its_stacks_on_disk(tmp_path):
    hangs = tmp_path / "hangs"
    proc, _ = inner_pytest(project(tmp_path, SLOW), hangs, "--test-timeout", "2", "-p", "no:xdist")
    out = proc.stdout + proc.stderr
    assert proc.returncode == (0 if IS_WINDOWS else 1), out  # POSIX fails it in place; Windows records it only
    named = [d for d in dumps(hangs) if "test_outlives_its_limit was still running after 2s" in d]
    assert len(named) == 1 and "in test_outlives_its_limit" in named[0], dumps(hangs)


def test_a_run_without_a_hang_leaves_no_dump_and_the_limit_is_on_by_default(tmp_path):
    """On by default, at the limit CI passes; ``--test-timeout 0`` turns it off, as under a debugger."""
    cases = ((["--test-timeout", "30"], 30.0), ([], bounds.TEST_TIMEOUT_S), (["--test-timeout", "0"], 0.0))
    for extra, limit in cases:
        check = f"def test_the_limit(request):\n    assert request.config.getoption('aew_test_timeout') == {limit!r}\n"
        root = project(tmp_path / f"{limit:g}", check)
        proc, _ = inner_pytest(root, tmp_path / "hangs", "-p", "no:xdist", *extra)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dumps(tmp_path / "hangs") == []


WATCHDOG_WAIT = f'''import sys
sys.path.insert(0, {str(HELPERS)!r})
import bounds


def test_waits_for_its_start():
    bounds.until(lambda: False, bounds.WATCHDOG, "a start that never comes")
'''


@pytest.mark.serial
def test_a_watchdog_wait_fails_by_name_after_the_watchdogs_own_evidence(tmp_path):
    """A start-up wait names WATCHDOG: no deadline of its own (#497). On POSIX the watchdog's alarm ends it in place at
    the limit; on Windows, where the watchdog only dumps stacks, the wait itself raises by name, once the dump is on
    disk, instead of running on to the session deadline."""
    hangs = tmp_path / "hangs"
    proc, took = inner_pytest(project(tmp_path, WATCHDOG_WAIT), hangs, "--test-timeout", "2", "-p", "no:xdist")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert ("(watchdog) waiting for a start that never comes" if IS_WINDOWS else "HungTest") in out, out
    assert [d for d in dumps(hangs) if "test_waits_for_its_start was still running after 2s" in d], dumps(hangs)
    assert took < 120, took


def test_a_watchdog_bound_is_the_time_left_and_room_for_its_evidence_and_none_when_the_watchdog_is_off(monkeypatch):
    monkeypatch.setattr(watchdog, "time", SimpleNamespace(monotonic=lambda: 10.0))
    monkeypatch.setattr(watchdog, "_deadline", 110.0)
    left = bounds.seconds(bounds.WATCHDOG)
    assert left is not None and left == 100 + bounds.WATCHDOG_EVIDENCE_S, left
    assert bounds.lead_session_bound() == bounds.WATCHDOG
    assert bounds.WATCHDOG_EVIDENCE_S > autopsy.WATCHER_GRACE_S  # the autopsy watcher fires within it
    monkeypatch.setattr(watchdog, "_deadline", 1210.0)
    assert bounds.lead_session_bound() == 900
    monkeypatch.setattr(watchdog, "_deadline", None)
    assert bounds.seconds(bounds.WATCHDOG) is None
    assert bounds.lead_session_bound() == 900


@pytest.mark.parametrize("mode", [["-p", "no:xdist"], ["-n", "2"]], ids=["no_xdist", "xdist"])
def test_a_clean_run_with_its_dumps_inside_the_checkout_passes_the_isolation_guard(tmp_path, mode):
    """#132 review: the isolation guard checks the checkout at sessionfinish. A clean test's dump file, kept until
    unconfigure, showed there as an untracked file and failed a run with an in-checkout ``--hang-dir`` or report."""
    root = project(tmp_path, "def test_ok():\n    pass\n\n\ndef test_also_ok():\n    pass\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")  # as the real checkout ignores it
    hangs = root / "reports"
    proc, _ = inner_pytest(root, hangs, *mode, "--test-timeout", "600", "--lane-report", str(hangs / "r.json"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "isolation guard" not in proc.stdout
    assert list(hangs.glob("hang-*.txt")) == []


@pytest.mark.parametrize(("deadline_left", "test_timer_armed"), [(1000.0, True), (100.0, False)],
                         ids=["the_test_timeout_comes_first", "the_deadline_comes_first"])
def test_on_windows_the_one_timer_goes_to_whichever_comes_first_and_back_to_the_deadline_after_the_test(
        tmp_path, monkeypatch, deadline_left, test_timer_armed):
    """A process has one faulthandler timer. If the watchdog's cancel left the deadline's off, a later hang holding the
    GIL would leave no stacks; if it re-armed over an earlier deadline, the stacks would come too late or never."""

    class Stacks:
        armed = 0

        def left(self):
            return deadline_left

        def arm(self):
            self.armed += 1

    class Plugins:
        stacks = Stacks()

        def get_plugin(self, name):
            return self if name == "aew-session-deadline" else None

    class Config:
        pluginmanager = Plugins()
        workerinput = {"workerid": "gw0"}

        def getoption(self, name, default=None):
            return str(tmp_path) if name == "aew_hang_dir" else default

    class Item:
        nodeid = "tests/test_x.py::test_x"

    timers = []
    monkeypatch.setattr(watchdog, "USE_ALARM", False)
    monkeypatch.setattr(watchdog.faulthandler, "dump_traceback_later", lambda seconds, file: timers.append(seconds))
    monkeypatch.setattr(watchdog.faulthandler, "cancel_dump_traceback_later", lambda: None)
    guard = watchdog.HangWatchdog(Config(), 600.0)
    protocol = guard.pytest_runtest_protocol(Item(), None)
    next(protocol)
    assert timers == ([600.0] if test_timer_armed else [])
    assert Plugins.stacks.armed == 0
    with pytest.raises(StopIteration):
        next(protocol)
    assert Plugins.stacks.armed == 1
