"""CI lanes and shards (docs/implementation/testing-and-ci-strategy.md): every test runs in exactly one
lane and one shard, serial tests never run under xdist, and a session that changes shared state fails."""

from __future__ import annotations

import importlib.util
import json
import os
import random
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

import lanes
from conftest import IS_WINDOWS

HELPERS = Path(lanes.__file__).resolve().parent


# ------------------------------------------------------------------ pure rules


@pytest.mark.parametrize(("path", "markers", "lane"), [
    ("tests/unit/test_store.py", [], "fast"),
    ("tests/test_spec_pin.py", ["parametrize"], "fast"),
    ("tests/integration/test_integration.py", [], "integration"),
    ("tests/integration/test_integration.py", ["acceptance"], "acceptance"),
    ("tests/acceptance/test_at1_serial_lifecycle.py", ["acceptance"], "acceptance"),
    ("tests/integration/test_store_processes.py", ["serial", "acceptance"], "serial"),
    ("tests/regression/test_compositions.py", [], "regression"),
    ("tests/regression/test_composition_walk.py", ["exploratory", "parametrize"], "adversarial"),
    ("tests/unit/test_x.py", ["serial"], "serial"),
])
def test_lane_rules_first_match_wins(path, markers, lane):
    assert lanes.lane_of(path, markers) == lane


@pytest.mark.parametrize("path", ["tests/test_new_thing.py", "tests/acceptance/test_x.py", "tests/e2e/test_y.py"])
def test_a_test_outside_every_lane_is_unclassified(path):
    with pytest.raises(lanes.Unclassified, match="belongs to no CI lane"):
        lanes.lane_of(path, [])


def test_partition_is_total_disjoint_and_deterministic():
    rng = random.Random(7)
    ids = [f"tests/regression/test_{i:03d}.py::t[{j}]" for i in range(40) for j in range(3)]
    durations = {n: rng.uniform(0.01, 40) for n in ids if rng.random() < 0.8}  # some tests have no record
    for shards in range(1, 7):
        bins = lanes.partition(ids, durations, shards)
        flat = [n for b in bins for n in b]
        assert sorted(flat) == sorted(ids) and len(flat) == len(set(flat))
        assert bins == lanes.partition(list(reversed(ids)), dict(durations), shards)  # input order irrelevant
    median = statistics.median(durations.values())
    weight = {n: durations.get(n, median) for n in ids}
    loads = [sum(weight[n] for n in b) for b in lanes.partition(ids, durations, 4)]
    assert max(loads) - min(loads) <= max(weight.values()) + 1e-9  # greedy LPT: within one test of balance


def test_partition_without_durations_is_round_robin_by_nodeid():
    ids = [f"t{i}" for i in range(7)]
    assert lanes.partition(ids, {}, 3) == [["t0", "t3", "t6"], ["t1", "t4"], ["t2", "t5"]]


@pytest.mark.parametrize("spec", ["0/2", "3/2", "a/b", "2"])
def test_bad_shard_spec_is_a_usage_error(spec):
    with pytest.raises(pytest.UsageError):
        lanes.parse_shard(spec)


def test_durations_prefer_the_platform_and_fill_from_others():
    data = {"platforms": {"linux": {"a": 1.0, "b": 2.0}, "win32": {"a": 5.0}}}
    assert lanes.durations_for("win32", data) == {"a": 5.0, "b": 2.0}
    assert lanes.durations_for("darwin", {}) == {}


@pytest.mark.parametrize(("phases", "outcome"), [
    ({"setup": "passed", "call": "passed", "teardown": "passed"}, "passed"),
    ({"setup": "skipped"}, "skipped"),
    ({"setup": "passed", "call": "failed", "teardown": "passed"}, "failed"),
    ({"setup": "failed"}, "error"),
    ({"setup": "passed", "call": "passed", "teardown": "failed"}, "error"),
    ({"setup": "passed", "call": "xfailed", "teardown": "passed"}, "xfailed"),
    ({"setup": "passed", "call": "xpassed", "teardown": "passed"}, "xpassed"),
])
def test_outcome_of_phases(phases, outcome):
    assert lanes.outcome_of(phases) == outcome


# ------------------------------------------------------------------ the plugin, black-box in a scratch project

CONFTEST = f'''
import sys
sys.path.insert(0, {str(HELPERS)!r})
import lanes
from lanes import process_isolation


def pytest_addoption(parser):
    lanes.addoption(parser)


def pytest_configure(config):
    lanes.configure(config)
'''
PYPROJECT = '''[tool.pytest.ini_options]
addopts = "--strict-markers"
markers = ["acceptance(id): a", "serial: s", "exploratory: e"]
'''
FILES = {
    "tests/unit/test_a.py": "def test_a1(): pass\ndef test_a2(): pass\ndef test_a3(): pass\n",
    "tests/integration/test_b.py": ("import pytest\n\ndef test_b1(): pass\n\n"
                                    "@pytest.mark.serial\ndef test_b_serial(): pass\n"),
    "tests/regression/test_c.py": "import pytest\n\n@pytest.mark.parametrize('i', range(5))\ndef test_c(i): pass\n",
}


def scratch(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    root = tmp_path / "proj"
    for rel, text in {"pyproject.toml": PYPROJECT, "tests/conftest.py": CONFTEST, **FILES, **(extra or {})}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def inner_pytest(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))}
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args], cwd=root,
                          env=env, capture_output=True, text=True, timeout=300, **kwargs)


def test_lane_report_records_the_whole_collection_and_only_the_lane_results(tmp_path):
    root = scratch(tmp_path)
    proc = inner_pytest(root, "--lane", "integration", "--lane-report", "out/r.json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads((root / "out/r.json").read_text(encoding="utf-8"))
    assert report["schema"] == lanes.REPORT_SCHEMA and report["lane"] == "integration"
    assert len(report["collected"]) == 10
    assert list(report["results"]) == ["tests/integration/test_b.py::test_b1"]
    assert report["results"]["tests/integration/test_b.py::test_b1"]["outcome"] == "passed"


def test_shards_partition_a_lane_exactly_once(tmp_path):
    root = scratch(tmp_path)
    ran = []
    for k in (1, 2, 3):
        proc = inner_pytest(root, "--lane", "regression", "--shard", f"{k}/3", "--lane-report", f"r{k}.json")
        assert proc.returncode == 0, proc.stdout + proc.stderr
        ran += json.loads((root / f"r{k}.json").read_text(encoding="utf-8"))["results"]
    assert sorted(ran) == [f"tests/regression/test_c.py::test_c[{i}]" for i in range(5)]


def test_an_unclassified_test_stops_the_run(tmp_path):
    root = scratch(tmp_path, {"tests/misc/test_d.py": "def test_d(): pass\n"})
    proc = inner_pytest(root)
    assert proc.returncode == pytest.ExitCode.USAGE_ERROR
    assert "tests/misc/test_d.py belongs to no CI lane" in proc.stderr


def test_a_leaked_environment_variable_fails_the_leaking_test(tmp_path):
    root = scratch(tmp_path, {"tests/unit/test_leak.py": "import os\n\ndef test_leak():\n    os.environ['AEW_X'] = '1'\n"})
    proc = inner_pytest(root, "tests/unit/test_leak.py")
    assert proc.returncode == 1 and "test leaked process state" in proc.stdout


def test_a_session_that_writes_into_the_checkout_fails_the_isolation_guard(tmp_path):
    root = scratch(tmp_path, {"tests/unit/test_w.py": ("from pathlib import Path\n\n"
                                                       "def test_w():\n    Path('stray.txt').write_text('x')\n")})
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@invalid", "commit", "-qm", "i"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    proc = inner_pytest(root, "tests/unit/test_w.py")
    assert proc.returncode == 1 and "isolation guard" in proc.stdout


@pytest.mark.skipif(importlib.util.find_spec("xdist") is None, reason="pytest-xdist not installed (extra: parallel)")
def test_serial_tests_are_refused_under_xdist(tmp_path):
    root = scratch(tmp_path)
    proc = inner_pytest(root, "tests/integration", "-n", "2")
    assert proc.returncode == 1
    assert "1 passed, 1 error" in proc.stdout and "must never share the machine" in proc.stdout


def test_isolation_guard_reports_only_what_changed():
    before = {"status": 0, "dirty": {" M a.py": "1", "?? b.txt": "2"}, "global_git_config": (0, "x")}
    after = {"status": 0, "dirty": {" M a.py": "9", "?? c.txt": "3"}, "global_git_config": (0, "y")}
    assert lanes.describe_change(before, after) == [
        "content changed:  M a.py", "vanished: ?? b.txt", "appeared: ?? c.txt", "the global git config changed"]
    assert lanes.describe_change(before, dict(before)) == []
