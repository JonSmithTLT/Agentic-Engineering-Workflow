"""The per-test hang watchdog (tests/helpers/watchdog.py; strategy §3, "A test that hangs fails by name"): a test still running after
``--test-timeout`` is named with every thread's stack, instead of holding its CI job until the job is cancelled and
nothing is recorded (the 2026-10-08 integration hangs). On POSIX it fails in place and the run carries on; on Windows
the stacks are written to the dump file the CI job uploads."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

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


def test_a_run_without_a_hang_leaves_no_dump_and_the_default_is_off(tmp_path):
    root = project(tmp_path, "def test_ok():\n    pass\n")
    for extra in (["--test-timeout", "30"], []):
        proc, _ = inner_pytest(root, tmp_path / "hangs", "-p", "no:xdist", *extra)
        assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dumps(tmp_path / "hangs") == []
