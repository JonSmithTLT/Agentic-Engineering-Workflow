"""Real-process crash and race tests for the persistence core (AT-4a foundation)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from store_model import check_invariants, init, make_store, one_transaction  # noqa: E402

from aew.engine.faults import CRASH_EXIT_CODE  # noqa: E402

WORKER = HELPERS / "store_worker.py"
FAULT_POINTS = [
    "txn.before_stage",
    "txn.after_stage",
    "txn.before_replace",
    "txn.after_replace",
    "txn.mid_apply",
    "txn.after_apply",
    "txn.after_log",
    "txn.after_render",
]
BEFORE_COMMIT = {"txn.before_stage", "txn.after_stage", "txn.before_replace"}


def run_worker(root: Path, count: int, *extra: str, fault: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("AEW_FAULT", None)
    env.pop("AEW_FAULT_MODE", None)
    if fault:
        env["AEW_FAULT"] = fault
    return subprocess.run(
        [sys.executable, str(WORKER), str(root), str(count), *extra],
        env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.acceptance("AT-4a")
@pytest.mark.parametrize("point", FAULT_POINTS)
def test_process_killed_at_each_point_recovers(tmp_path, point):
    store = init(tmp_path)
    one_transaction(store)
    proc = run_worker(tmp_path, 1, fault=point)
    assert proc.returncode == CRASH_EXIT_CODE, proc.stderr
    n = check_invariants(tmp_path)
    assert n == (1 if point in BEFORE_COMMIT else 2)
    # After the crash the lock is free and further work proceeds.
    assert run_worker(tmp_path, 2).returncode == 0
    assert check_invariants(tmp_path) == n + 2


@pytest.mark.acceptance("AT-4a")
def test_two_racing_writers_lose_no_updates(tmp_path):
    init(tmp_path)
    env = dict(os.environ)
    env.pop("AEW_FAULT", None)
    procs = [
        subprocess.Popen([sys.executable, str(WORKER), str(tmp_path), "50"], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    for p in procs:
        _, err = p.communicate(timeout=600)
        assert p.returncode == 0, err
    assert check_invariants(tmp_path) == 100
    assert make_store(tmp_path).read()["revision"] == 100


def test_stale_revision_from_another_process(tmp_path):
    init(tmp_path)
    assert run_worker(tmp_path, 1).returncode == 0  # revision 1
    # A writer that decided based on revision 0 must be rejected, not merged.
    proc = run_worker(tmp_path, 1, "0")
    assert proc.returncode == 3
    assert check_invariants(tmp_path) == 1
