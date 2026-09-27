"""Persistence core: atomic commits, CAS, recovery, integrity (WC §5, §8.2; KC §12.3)."""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from store_model import check_invariants, init, make_store, one_transaction  # noqa: E402

from aew.engine.faults import InjectedFault  # noqa: E402
from aew.engine.store import Transition  # noqa: E402
from aew.errors import IntegrityError, ProjectNotFound, StaleRevision  # noqa: E402

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


def test_initial_create_and_commits(tmp_path):
    store = init(tmp_path)
    assert check_invariants(tmp_path) == 0
    for _ in range(3):
        one_transaction(store)
    assert check_invariants(tmp_path) == 3
    with pytest.raises(IntegrityError):
        store.create({}, {})  # already initialized


def test_missing_project(tmp_path):
    with pytest.raises(ProjectNotFound):
        make_store(tmp_path).read()


def test_stale_expected_revision_rejected(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    before = (tmp_path / "state/control.yaml").read_bytes()
    with pytest.raises(StaleRevision) as exc:
        one_transaction(store, expect_rev=0)
    assert exc.value.details == {"expected": 0, "current": 1}
    assert (tmp_path / "state/control.yaml").read_bytes() == before
    assert check_invariants(tmp_path) == 1


def test_immutable_record_never_overwritten(tmp_path):
    store = init(tmp_path)
    (tmp_path / "records").mkdir()
    (tmp_path / "records/item-1.md").write_text("planted by someone else\n")
    with pytest.raises(IntegrityError):
        one_transaction(store)
    assert store.read()["revision"] == 0
    assert (tmp_path / "records/item-1.md").read_text() == "planted by someone else\n"
    assert not list((tmp_path / "state").glob("txn/*.yaml"))


@pytest.mark.parametrize("point", FAULT_POINTS)
def test_injected_fault_each_point_in_process(tmp_path, monkeypatch, point):
    store = init(tmp_path)
    one_transaction(store)
    monkeypatch.setenv("AEW_FAULT", point)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        one_transaction(make_store(tmp_path))
    monkeypatch.delenv("AEW_FAULT")
    n = check_invariants(tmp_path)
    assert n == (1 if point in BEFORE_COMMIT else 2)
    one_transaction(make_store(tmp_path))  # and the store keeps working
    assert check_invariants(tmp_path) == n + 1


def test_randomized_crash_iterations(tmp_path, monkeypatch):
    # Merge gate: seed 20260925, 200 iterations. The nightly crash-extended job rotates the seed and raises the count.
    rng = random.Random(int(os.environ.get("AEW_CRASH_SEED", "20260925")))
    init(tmp_path)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    expected = 0
    for _ in range(int(os.environ.get("AEW_CRASH_ITERATIONS", "200"))):
        point = rng.choice(FAULT_POINTS + [None, None])
        if point:
            monkeypatch.setenv("AEW_FAULT", point)
        else:
            monkeypatch.delenv("AEW_FAULT", raising=False)
        try:
            one_transaction(make_store(tmp_path))
            expected += 1
        except InjectedFault:
            if point not in BEFORE_COMMIT:
                expected += 1
        monkeypatch.delenv("AEW_FAULT", raising=False)
        assert check_invariants(tmp_path) == expected


def test_truncated_control_state_fails_closed(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    control = tmp_path / "state/control.yaml"
    lines = control.read_text().splitlines(keepends=True)
    control.write_text("".join(lines[: len(lines) // 2]))
    with pytest.raises(IntegrityError):
        store.read()


def test_edited_control_state_fails_closed(tmp_path):
    store = init(tmp_path)
    control = tmp_path / "state/control.yaml"
    control.write_text(control.read_text().replace("generation: 0", "generation: 9"))
    with pytest.raises(IntegrityError) as exc:
        store.read()
    assert "checksum" in exc.value.message


def test_out_of_band_edit_during_apply_fails_closed(tmp_path, monkeypatch):
    store = init(tmp_path)
    one_transaction(store)
    monkeypatch.setenv("AEW_FAULT", "txn.after_replace")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(InjectedFault):
        one_transaction(make_store(tmp_path))
    monkeypatch.delenv("AEW_FAULT")
    # Someone edits a target between commit and roll-forward: never clobber it.
    (tmp_path / "manifest.txt").write_text("hand edit\n")
    with pytest.raises(IntegrityError) as exc:
        make_store(tmp_path).read()
    assert exc.value.details["path"] == "manifest.txt"
    assert (tmp_path / "manifest.txt").read_text() == "hand edit\n"


def test_write_outside_root_refused(tmp_path):
    store = init(tmp_path / "aew")
    with pytest.raises(IntegrityError):
        with store.session() as s:
            s.write("../escape.txt", "x")
            s.commit(Transition(op="escape", actor={"kind": "test"}))
    assert not (tmp_path / "escape.txt").exists()


def test_derived_views_rebuilt_after_deletion(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    (tmp_path / "state/CURRENT.md").unlink()
    (tmp_path / "state/log/000001.yaml").unlink()
    check_invariants(tmp_path)  # read() repairs the log and the render
