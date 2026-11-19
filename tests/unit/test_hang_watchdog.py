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

import lanes
import proctree
import pytest
import watchdog
from conftest import IS_WINDOWS
from session_deadline import SUPERVISOR_CUTOFF_EXIT

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


@pytest.mark.skipif(not watchdog.USE_ALARM, reason="needs SIGALRM to interrupt a blocking call (POSIX); "
                                                   "Windows records the stacks only, tested below")
@pytest.mark.parametrize("mode", [("-n", "2", "--dist", "worksteal"), ("-p", "no:xdist")], ids=["xdist", "no_xdist"])
def test_a_hung_test_fails_in_place_by_name_with_its_stack_and_the_run_carries_on(tmp_path, mode):
    report, hangs = tmp_path / "r.json", tmp_path / "hangs"
    proc, took = inner_pytest(project(tmp_path, HANGS), hangs, "--test-timeout", "3", "--lane-report", str(report),
                              *mode)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1 and "INTERNALERROR" not in out, out
    assert "HungTest" in out and "test_w.py::test_hangs_forever started" in out, out
    assert "in test_hangs_forever" in out, out  # the stack names the line the test is stuck on
    assert took < 120, took
    results = json.loads(report.read_text(encoding="utf-8"))["results"]
    assert results["tests/unit/test_w.py::test_hangs_forever"]["outcome"] == "failed"
    assert results["tests/unit/test_w.py::test_after"]["outcome"] == "passed"  # one hang costs only its own limit
    assert results["tests/unit/test_w.py::test_quick"]["outcome"] == "passed"
    named = [d for d in dumps(hangs) if "test_hangs_forever started" in d]
    assert len(named) == 1 and "in test_hangs_forever" in named[0], dumps(hangs)


def test_a_test_that_outlives_its_limit_leaves_its_stacks_on_disk(tmp_path):
    hangs = tmp_path / "hangs"
    proc, _ = inner_pytest(project(tmp_path, SLOW), hangs, "--test-timeout", "2", "-p", "no:xdist")
    out = proc.stdout + proc.stderr
    assert proc.returncode == (0 if IS_WINDOWS else 1), out  # POSIX fails it in place; Windows records it only
    named = [d for d in dumps(hangs) if "test_outlives_its_limit started" in d]
    assert len(named) == 1 and "in test_outlives_its_limit" in named[0], dumps(hangs)


def test_a_run_without_a_hang_leaves_no_dump_and_the_default_is_off(tmp_path):
    root = project(tmp_path, "def test_ok():\n    pass\n")
    for extra in (["--test-timeout", "30"], []):
        proc, _ = inner_pytest(root, tmp_path / "hangs", "-p", "no:xdist", *extra)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dumps(tmp_path / "hangs") == []


def run_windows_supervisor(root, progress, hangs):
    runner = HELPERS.parents[1] / "tools" / "ci" / "lane_step.py"
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))}
    # The venv launcher can kill leaked descendants by itself. Use the base interpreter as CI does.
    clean_env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)
    bootstrap = ("import runpy,sys,time,shlex; "
                 "supervise=runpy.run_path(sys.argv[1])['supervise']; "
                 "from pathlib import Path; "
                 "script=Path(sys.argv[2]).parent/'lane.sh'; "
                 "script.write_text(shlex.join([sys.executable,'-m','pytest',*sys.argv[3:]])); "
                 "raise SystemExit(supervise(Path(sys.argv[2]),'bash',script,time.time()+15))")
    return subprocess.run([sys._base_executable, "-c", bootstrap, str(runner), str(progress), "-q", "-s",
                           "-p", "no:cacheprovider", "-p", "no:xdist", "--test-timeout", "600",
                           f"--hang-dir={hangs}", f"--running-tests-dir={progress}", "tests"],
                          cwd=root, env=clean_env, capture_output=True, text=True, timeout=35,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def run_windows_cutoff(tmp_path, test_body):
    identity_file = tmp_path / "child.txt"
    child_code = (f"import os,sys,time; from pathlib import Path; sys.path.insert(0,{str(HELPERS)!r}); "
                  f"import proctree; pid=os.getpid(); identity=Path({str(identity_file)!r}); "
                  "pending=identity.with_suffix('.tmp'); pending.write_text(f'{pid} {proctree.start_time(pid)}'); "
                  "pending.replace(identity); time.sleep(120)")
    planted = f"""
import socket
import subprocess
import sys
from pathlib import Path

import bounds
import pytest

@pytest.mark.parametrize('value', [1], ids=['private-parameter'])
def test_plant(value):
    subprocess.Popen([sys.executable, '-c', {child_code!r}], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    bounds.bounded_wait("test.planted_child_identity", Path({str(identity_file)!r}).is_file, seconds=5)
{test_body}
"""
    root = project(tmp_path, planted)
    progress = tmp_path / "progress"
    try:
        proc = run_windows_supervisor(root, progress, tmp_path / "hangs")
        assert proc.returncode == SUPERVISOR_CUTOFF_EXIT, proc.stdout + proc.stderr
        pid, started = map(int, identity_file.read_text(encoding="utf-8").split())
        assert not proctree.same((pid, started)), f"the planted child {pid} survived the cutoff"
        status = (progress / "runner-resources-step.txt").read_text(encoding="utf-8")
        assert f"  {pid} python.exe" in status.lower(), status
        assert "time.sleep(120)" not in status
        return progress, status
    finally:
        if identity_file.is_file():
            pid, started = map(int, identity_file.read_text(encoding="utf-8").split())
            proctree.end((pid, started))  # also reap the plant when a cutoff ablation leaves it alive


@pytest.mark.skipif(not IS_WINDOWS, reason="the CI step's outer job object is a Windows API")
def test_windows_supervisor_forwards_pytest_output(tmp_path):
    root = project(tmp_path, """\
import sys

def test_output():
    print("planted pytest stdout")
    print("planted pytest stderr", file=sys.stderr)
""")
    proc = run_windows_supervisor(root, tmp_path / "progress", tmp_path / "hangs")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "planted pytest stdout" in proc.stdout
    assert "planted pytest stderr" in proc.stderr
    assert "1 passed" in proc.stdout


@pytest.mark.skipif(not IS_WINDOWS, reason="the CI step's outer job object is a Windows API")
def test_windows_step_cutoff_leaves_only_the_running_source_test_for_upload(tmp_path):
    progress, status = run_windows_cutoff(tmp_path, "    a, b = socket.socketpair()\n    a.recv(1)")
    assert "Pytest was still running" in status
    [running] = progress.glob("running-*.txt")
    assert running.read_text(encoding="utf-8").splitlines() == ["tests/unit/test_w.py::test_plant"]


@pytest.mark.skipif(not IS_WINDOWS, reason="the CI step's outer job object is a Windows API")
def test_windows_step_cutoff_waits_for_a_leaked_child_after_pytest_passes(tmp_path):
    progress, status = run_windows_cutoff(tmp_path, "    pass")
    assert "Pytest had exited with code 0" in status
    assert not list(progress.glob("running-*.txt"))


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
