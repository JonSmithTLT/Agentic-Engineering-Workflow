"""The records that name a process carry its start id, from every writer, and the control schema takes it additively
(ADR-0009 amendment 2026-10-23; the readers and the identity itself: ``tests/unit/test_process_identity.py``).

Each writer here runs in this process, or in a process the test can still see, and each test steps the wall clock
after the record was written (``clock_step``): a writer that left the start id out would leave its reader judging by a
start time, which the step misjudges.

The schema stays ``aew/control/v2``, additive: the custody worker's ``start_id`` is optional, so a state from before it
still loads, and an engine from before it refuses a state that carries one (its worker is closed), as ADR-0004 and
ADR-0012 have every additive key fail closed. Proven against the vendored schema of main before this change
(0f59742).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import test_integration_stages as stages
from aewflow import create_planned_ticket, sample_project
from clock_step import STEP_S, stepper
from fake_harness import HarnessLab
from harness_conformance import harness_processes, supervisor_gone
from invariants import load_control
from jsonschema import Draft202012Validator
from test_integration_stages import checks_mode, engine, lease, prepared

from aew import schemas
from aew.dashboard import service
from aew.engine import validation_ops as VO
from aew.engine.api import Engine
from aew.harness import procs, runlog

ROOT = Path(__file__).resolve().parents[2]
PRE_START_ID_SCHEMA = ROOT / "tests/fixtures/baseline/control.schema.0f59742.json"  # main before start ids

custody, contained = stages.custody, stages.contained  # the stage tests' fixtures: the custody worker, in process


def pre_start_id_validator() -> Draft202012Validator:
    """The control schema of main before start ids, with the schemas it refers to (none of which changed)."""
    from aew.schemas import _registry

    return Draft202012Validator(json.loads(PRE_START_ID_SCHEMA.read_text(encoding="utf-8")), registry=_registry())


def test_a_custody_worker_registers_its_start_id_additively_and_is_not_lost_across_a_clock_step(
        tmp_path, contained, custody, monkeypatch):
    p = sample_project(tmp_path)
    checks_mode(p)
    _wid, custodian, _out = prepared(p, tmp_path)
    e = engine(p)
    e.custody_register(custody[custodian])
    state = load_control(p.root)
    assert state["invocations"][custodian]["worker"]["start_id"] == procs.start_id(os.getpid())
    # Additive: the schema stays v2 and takes it; an engine from before it refuses the state, for the start id alone.
    assert state["schema"] == "aew/control/v2" and schemas.iter_errors("control", state) == []
    old = pre_start_id_validator()
    errors = [err.message for err in old.iter_errors(state)]
    assert errors == ["Additional properties are not allowed ('start_id' was unexpected)"], errors
    del state["invocations"][custodian]["worker"]["start_id"]
    assert [err.message for err in old.iter_errors(state)] == [] and schemas.iter_errors("control", state) == []
    stepper(monkeypatch)(STEP_S)
    e.checkpoint(token=p.token, expect_rev=p.rev(), note="any Lead commit runs sync")
    held = lease(p)
    assert held is not None and held["reconcile"] is None
    assert load_control(p.root)["invocations"][custodian]["status"] == "active"


def test_a_state_from_before_start_ids_loads_and_the_run_its_worker_executes_records_one(tmp_path, contained, custody,
                                                                                         monkeypatch):
    """The upgrade: a worker registered before start ids is still judged by its start time, and a run that starts
    under this engine names its executor by start id."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    with monkeypatch.context() as m:  # a start id that cannot be read: the worker registers as it did before them
        m.setattr(procs, "start_id", lambda pid: None)
        engine(p).custody_register(custody[custodian])
    state = load_control(p.root)
    assert "start_id" not in state["invocations"][custodian]["worker"]
    assert [err.message for err in pre_start_id_validator().iter_errors(state)] == []
    e = engine(p)  # loads the state from disk, validated by the current schema
    e.checkpoint(token=p.token, expect_rev=p.rev(), note="any Lead commit runs sync")
    held = lease(p)
    assert held is not None and held["reconcile"] is None  # a live worker, by its start time
    found, result = e.custody_step(custodian, custody[custodian])
    assert result is not None and result["result"] == "pass", (found, result)
    run = load_control(p.root)["work"][wid]["integration"][VO.CURRENT]
    assert run["executor"]["start_id"] == procs.start_id(os.getpid())  # the custody worker validated in this process
    stepper(monkeypatch)(STEP_S)
    assert VO.executor_alive(run)


def test_the_dashboard_records_its_start_id_and_is_found_across_a_clock_step(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    svc = service.Service(Engine.discover(p.root), port=0, console=None)
    svc.start()
    try:
        info = json.loads((p.root / ".aew" / service.SERVER_JSON_REL).read_text(encoding="utf-8"))
        assert info["start_id"] == procs.start_id(os.getpid())
        stepper(monkeypatch)(STEP_S)
        found = service.locate(p.root / ".aew")
        assert found is not None and found["instance"] == svc.instance
    finally:
        svc.stop()


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def test_a_run_record_names_its_supervisor_and_harness_processes_by_start_id(lab, tmp_path, monkeypatch):
    sync = tmp_path / "sync"
    sync.mkdir(exist_ok=True)
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [{"do": "wait_file", "path": str(sync / "never"), "timeout": 300}])
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    record = lab.until(lambda: (r := lab.record(run)).get("harness_pids") and r, what="the run's harness processes")
    assert record["supervisor_start_id"] == procs.start_id(record["supervisor_pid"])
    assert record["harness_start_ids"] == [procs.start_id(pid) for pid in record["harness_pids"]]
    assert all(record["harness_start_ids"])
    stepper(monkeypatch)(STEP_S)
    assert not supervisor_gone(record)
    assert all(procs.same_process(pid, named) for pid, named in harness_processes(record))
    assert runlog.end_supervisor(runlog.run_dir(lab.aew_root, run)) is True
    lab.until(lambda: supervisor_gone(record), 30, "the supervisor to exit")
