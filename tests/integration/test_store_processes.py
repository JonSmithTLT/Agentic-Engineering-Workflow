"""Real-process crash and race tests for the persistence core (AT-4a foundation)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

import history_model  # noqa: E402
from store_model import check_invariants, init, make_store, one_transaction  # noqa: E402

from aew.engine.faults import CRASH_EXIT_CODE  # noqa: E402

# Real processes killed at every fault point and racing on the lock: timing and process concurrency are the
# property here, so this module never shares the machine with other tests (lane `serial`).
pytestmark = pytest.mark.serial

WORKER = HELPERS / "store_worker.py"
HISTORY_WORKER = HELPERS / "history_worker.py"
# Transactions per racing writer. The merge gate uses 50; the nightly race-repeat job raises it.
RACE_WRITES = int(os.environ.get("AEW_RACE_WRITES", "50"))
FAULT_POINTS = [
    "txn.before_stage",
    "txn.after_stage",
    "txn.before_replace",
    "txn.after_replace",
    "txn.mid_apply",
    "txn.after_apply",
    "txn.after_log",
    "txn.after_render",
    "log.overflow_unpublished",  # committed with its overflow sidecar not yet written (ADR-0012 D9)
]
BEFORE_COMMIT = {"txn.before_stage", "txn.after_stage", "txn.before_replace"}
# ADR-0011 history writes, applied after the commit point: a bundle, a sealed segment, the tail.
HISTORY_POINTS = ["history.after_bundle", "history.mid_seal", "history.after_tail"]


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
        subprocess.Popen([sys.executable, str(WORKER), str(tmp_path), str(RACE_WRITES)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    for p in procs:
        _, err = p.communicate(timeout=600)
        assert p.returncode == 0, err
    assert check_invariants(tmp_path) == 2 * RACE_WRITES
    assert make_store(tmp_path).read()["revision"] == 2 * RACE_WRITES


def test_stale_revision_from_another_process(tmp_path):
    init(tmp_path)
    assert run_worker(tmp_path, 1).returncode == 0  # revision 1
    # A writer that decided based on revision 0 must be rejected, not merged.
    proc = run_worker(tmp_path, 1, "0")
    assert proc.returncode == 3
    assert check_invariants(tmp_path) == 1


def run_history_worker(root: Path, units: int, *extra: str, fault: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("AEW_FAULT_MODE", None)
    env["AEW_FAULT"] = fault
    return subprocess.run([sys.executable, str(HISTORY_WORKER), str(root), str(units), *extra],
                          env=env, capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("point", HISTORY_POINTS + ["txn.after_stage", "txn.mid_apply"])
def test_process_killed_at_each_history_point_recovers(tmp_path, point):
    store = history_model.init(tmp_path)
    history_model.archive(store, 255)  # the next archival seals segment 1, so every history point is on its path
    proc = run_history_worker(tmp_path, 1, fault=point)
    assert proc.returncode == CRASH_EXIT_CODE, proc.stderr
    n = history_model.check(tmp_path)  # recovery rolls the committed archival forward, or there was none
    assert n == (255 if point in BEFORE_COMMIT else 256)
    history_model.archive(make_store(tmp_path), 2)
    assert history_model.check(tmp_path) == n + 2


def test_process_killed_after_prewriting_leaves_only_benign_records(tmp_path):
    store = history_model.init(tmp_path)
    history_model.archive(store, 1)
    proc = run_history_worker(tmp_path, 3, "prewritten", fault="history.after_prewrite")
    assert proc.returncode == CRASH_EXIT_CODE, proc.stderr
    assert history_model.check(tmp_path, unreferenced=("work/T-0002/archive.yaml",)) == 1
    history_model.archive(make_store(tmp_path), 3, prewritten=True)
    assert history_model.check(tmp_path) == 4


# ADR-0012 D9: the transition log's sealing points (M4-D slice D2). Not on the commit path: a compaction is killed.
SEAL_POINTS = ["log.seal.after_segment", "log.seal.mid_prune"]
COMPACT_WORKER = HELPERS / "compact_worker.py"


@pytest.mark.parametrize("point", SEAL_POINTS)
def test_process_killed_at_each_sealing_point_recovers(tmp_path, point):
    from log_fixture import extend_log
    from store_model import outbox_violations

    init(tmp_path)
    one_transaction(make_store(tmp_path))
    extend_log(tmp_path, 300, overflow_every=13)
    env = dict(os.environ, AEW_FAULT=point)
    env.pop("AEW_FAULT_MODE", None)
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    proc = subprocess.run([sys.executable, str(COMPACT_WORKER), str(tmp_path), "8"], env=env, capture_output=True,
                          text=True, timeout=300, **kwargs)
    assert proc.returncode == CRASH_EXIT_CODE, proc.stderr
    state = make_store(tmp_path).read()
    assert outbox_violations(tmp_path, state) == []  # one valid representation of every transition, readable
    one_transaction(make_store(tmp_path))  # commits continue over a half-sealed log
    env.pop("AEW_FAULT")
    proc = subprocess.run([sys.executable, str(COMPACT_WORKER), str(tmp_path), "8"], env=env, capture_output=True,
                          text=True, timeout=300, **kwargs)
    assert proc.returncode == 0, proc.stderr
    assert check_invariants(tmp_path, synthetic_through=300) == 301
