"""A process's identity survives a wall-clock step (ADR-0009 amendment 2026-10-23).

On Linux ``procs.started_at`` is ``btime`` plus the process's start ticks, and ``btime`` (the wall clock minus the time
since boot) moves with every step of the wall clock, so an epoch start time names no process: ``same_process`` judged
a live process gone after a forward step of more than 2 s. A record now names its process by ``procs.start_id`` (the
boot id and the start ticks; on Windows the absolute creation time), compared exactly.

Each reader of a record that names a process is proved here to prefer the record's start id, with the clock stepped
after the record was written (``clock_step``); the writers that run in this process are proved with their reader. A
reused pid, another boot, another platform's id and a malformed id each read as another process, and a record from
before start ids keeps its start-time check. The custody worker, the validation executor, the dashboard and the
supervisor write their records in ``tests/integration/test_process_identity_records.py``.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from clock_step import STEP_S, reused, stepper

from aew.dashboard import service
from aew.engine import queue_ops, validation_ops
from aew.engine.api import Engine
from aew.harness import broker_liveness, operator_client, operator_endpoint, procs, runlog
from aew.util import utc_now

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
ZERO_BOOT = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def step(monkeypatch) -> Callable[[float], None]:
    return stepper(monkeypatch)


def sleeper() -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)


def ended(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(30)


def mine() -> str:
    start = procs.start_id(os.getpid())
    assert start is not None
    return start


# ---------------------------------------------------------------------------------------------- the identity


@pytest.mark.skipif(not IS_LINUX, reason="btime is Linux's; Windows' creation time is absolute")
def test_a_wall_clock_step_moves_the_epoch_start_time_but_never_the_start_id_on_linux(step):
    me, start = os.getpid(), mine()
    before = procs.started_at(me)
    assert before is not None and procs.same_process(me, before)
    moved = 0.0
    for seconds in (3.0, STEP_S, -5.0, 3600.0):
        step(seconds)
        moved += seconds
        assert procs.started_at(me) == pytest.approx(before + moved)  # the simulated step reaches the reader
        assert procs.start_id(me) == start
        assert procs.same_process(me, start)
        # The residual: a record from before start ids misjudges a live process once the clock has moved past 2 s.
        assert procs.same_process(me, before) is (moved <= 2.0)


def test_a_start_id_names_one_process_of_one_boot():
    me, start = os.getpid(), mine()
    if IS_WINDOWS:
        assert re.fullmatch(r"win:\d+", start), start
    else:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        assert re.fullmatch(rf"linux:{re.escape(boot)}:\d+", start), start
    child = sleeper()
    try:
        theirs = procs.start_id(child.pid)
        assert theirs is not None and theirs != start
        assert procs.same_process(child.pid, theirs)
        assert not procs.same_process(child.pid, start) and not procs.same_process(me, theirs)
    finally:
        ended(child)
    assert not procs.same_process(child.pid, theirs)  # gone: whatever that pid names later is another process


def test_a_reused_pid_another_boot_or_another_platform_never_reads_as_the_recorded_process():
    me, start = os.getpid(), mine()
    assert procs.same_process(me, start)
    ticks = start.rpartition(":")[2]
    if IS_WINDOWS:
        forged = [reused(start), f"linux:{ZERO_BOOT}:{ticks}"]
    else:
        forged = [reused(start), f"linux:{ZERO_BOOT}:{ticks}", f"win:{ticks}"]
    for other in forged:
        assert other != start and not procs.same_process(me, other), other
    for malformed in ("", "garbage", start + " ", start.upper(), start.rpartition(":")[0]):
        assert not procs.same_process(me, malformed), malformed  # an id no process has: fail closed
    for kept in (5, 5.0, ["x"], {"start": start}, True):
        assert procs.recorded(kept, procs.started_at(me)) == ""  # a start id that is not a string names no process
    assert not procs.same_process(None, start)


def test_a_record_from_before_start_ids_keeps_its_start_time_check(step):
    me = os.getpid()
    before = procs.started_at(me)
    assert before is not None
    assert procs.recorded(None, before) == before
    assert procs.same_process(me, procs.recorded(None, before))
    assert not procs.same_process(me, before - 10)  # it started after the recorded time: another process
    assert procs.recorded(None, None) == 0.0 and not procs.same_process(me, procs.recorded(None, None))


# ---------------------------------------------------------------------------------------------- each reader


def test_a_validation_runs_executor_is_alive_across_a_clock_step(step):
    me, start = os.getpid(), mine()
    executor = {"host": socket.gethostname(), "host_pid": me, "start_time": procs.started_at(me)}
    old, new = {"executor": dict(executor)}, {"executor": {**executor, "start_id": start}}
    assert validation_ops.executor_alive(old) and validation_ops.executor_alive(new)
    step(STEP_S)
    assert validation_ops.executor_alive(new)
    assert not validation_ops.executor_alive({"executor": {**executor, "start_id": reused(start)}})
    assert not validation_ops.executor_alive({"executor": {**executor, "start_id": 7}})
    assert validation_ops.stuck_run({"id": "IV-1-1", "state": "running", "deadline_at": "2999-01-01T00:00:00Z",
                                     **new}) is None


def test_a_custody_worker_is_not_lost_across_a_clock_step(step):
    me, start = os.getpid(), mine()
    lease = {"custodian": "IA-1"}
    worker = {"host": socket.gethostname(), "host_pid": me, "started_at": procs.started_at(me),
              "registered_at": utc_now()}
    queue = cast(Any, object())  # a registered worker is judged without the queue's kernel

    def lost(w: dict[str, Any]) -> str | None:
        return queue_ops.Queue._lost_worker(queue, lease, {"worker": w})  # noqa: SLF001 (the judgement alone)

    assert lost(worker) is None  # a worker registered before start ids, with no step
    step(STEP_S)
    assert lost({**worker, "start_id": start}) is None
    gone = lost({**worker, "start_id": reused(start)})
    assert gone is not None and "custody worker" in gone


def test_the_operator_endpoints_locator_names_its_process_across_a_clock_step(project, step):
    root = project.root / ".aew"
    endpoint = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=print, dev=True)
    data = endpoint._locator_data()  # noqa: SLF001 (what the endpoint writes; serving it is not under test)
    assert data["start_id"] == mine()
    locator = operator_client.locator_path(root)
    locator.parent.mkdir(parents=True, exist_ok=True)
    locator.write_text(json.dumps(data), encoding="utf-8")
    step(STEP_S)
    assert operator_client.status(root)["running"] is True
    locator.write_text(json.dumps({**data, "start_id": reused(data["start_id"])}), encoding="utf-8")
    assert operator_client.status(root)["running"] is False
    old = {k: v for k, v in data.items() if k != "start_id"}
    old["process_started"] = procs.started_at(os.getpid())  # written after the step: a record from before start ids
    locator.write_text(json.dumps(old), encoding="utf-8")
    assert operator_client.status(root)["running"] is True


def test_a_live_brokers_record_is_never_judged_a_crash_across_a_clock_step(tmp_path, step):
    beat = broker_liveness.Beat(tmp_path, generation=1, poll_s=5.0, wedge_after_s=60.0)
    beat._write(None)  # noqa: SLF001 (one beat, without the thread)
    record = broker_liveness.read(tmp_path)
    assert record is not None and record["start_id"] == mine()
    step(STEP_S)
    assert broker_liveness.judge(record, generation=1, poll_s=5.0, now=record["beat_at"]) is None
    forged = {**record, "start_id": reused(record["start_id"])}
    verdict = broker_liveness.judge(forged, generation=1, poll_s=5.0, now=record["beat_at"])
    assert verdict is not None and verdict.reason == "crash"
    old = {k: v for k, v in record.items() if k != "start_id"}
    assert broker_liveness.judge(old, generation=1, poll_s=5.0, now=record["beat_at"]) is not None  # the residual


def test_a_broker_record_whose_start_id_is_not_a_string_is_not_one_the_broker_wrote(tmp_path):
    beat = broker_liveness.Beat(tmp_path, generation=1, poll_s=5.0, wedge_after_s=60.0)
    beat._write(None)  # noqa: SLF001
    record = broker_liveness.read(tmp_path)
    assert record is not None
    for bad in (5, ["linux:x:1"], {"id": 1}):
        broker_liveness.write(tmp_path, {**record, "start_id": bad})
        assert broker_liveness.read(tmp_path) is None, bad
    broker_liveness.write(tmp_path, {k: v for k, v in record.items() if k != "start_id"})
    assert broker_liveness.read(tmp_path) is not None  # a record from before start ids is still read


def test_a_superseded_brokers_close_never_overwrites_a_record_whose_start_id_is_not_its_own(tmp_path):
    beat = broker_liveness.Beat(tmp_path, generation=1, poll_s=5.0, wedge_after_s=60.0)
    beat._write(None)  # noqa: SLF001
    record = broker_liveness.read(tmp_path)
    assert record is not None
    broker_liveness.write(tmp_path, {**record, "start_id": reused(record["start_id"]), "generation": 2})
    beat.close()
    after = broker_liveness.read(tmp_path)
    assert after is not None and after["generation"] == 2 and "closed_at" not in after


def test_the_dashboards_endpoint_file_names_its_process_across_a_clock_step(tmp_path, step):
    me, start = os.getpid(), mine()
    (tmp_path / service.DIR_REL).mkdir(parents=True)
    (tmp_path / service.KEY_REL).write_text("ab" * 16 + "\n", encoding="utf-8")
    info = {"schema": "aew/dashboard-endpoint/v1", "instance": "i", "pid": me, "started_by": procs.started_at(me),
            "start_id": start, "port": 1, "url": "http://127.0.0.1:1",
            "control": {"endpoint": "x", "key_file": service.KEY_REL}}
    endpoint = tmp_path / service.SERVER_JSON_REL
    endpoint.write_text(json.dumps(info), encoding="utf-8")
    step(STEP_S)
    assert service.locate(tmp_path) is not None
    endpoint.write_text(json.dumps({**info, "start_id": reused(start)}), encoding="utf-8")
    assert service.locate(tmp_path) is None
    endpoint.write_text(json.dumps({**info, "start_id": 7}), encoding="utf-8")
    assert service.locate(tmp_path) is None  # malformed: no process, so no server
    old = {k: v for k, v in info.items() if k != "start_id"}
    old["started_by"] = procs.started_at(me)  # written after the step: a record from before start ids
    endpoint.write_text(json.dumps(old), encoding="utf-8")
    assert service.locate(tmp_path) is not None


def test_teardown_ends_the_supervisor_its_record_names_across_a_clock_step(tmp_path, monkeypatch, step):
    child = sleeper()
    try:
        start = procs.start_id(child.pid)
        assert start is not None
        killed: list[int] = []
        real_kill = procs.kill_pid
        monkeypatch.setattr(procs, "kill_pid", lambda pid: (killed.append(pid), real_kill(pid)))
        run_json = tmp_path / "run.json"
        record = {"supervisor_pid": child.pid, "custody_at": utc_now()}
        run_json.write_text(json.dumps({**record, "supervisor_start_id": reused(start)}), encoding="utf-8")
        assert runlog.end_supervisor(tmp_path) is False and not killed  # another process: never ended
        step(STEP_S)
        run_json.write_text(json.dumps({**record, "supervisor_start_id": start}), encoding="utf-8")
        assert runlog.end_supervisor(tmp_path) is True and killed == [child.pid]
        child.wait(30)
    finally:
        ended(child)


def test_teardown_still_ends_a_supervisor_whose_record_predates_start_ids(tmp_path, step):
    child = sleeper()
    try:
        time.sleep(1.1)  # custody_at has 1 s resolution: the record's custody time is after the child started
        (tmp_path / "run.json").write_text(json.dumps({"supervisor_pid": child.pid, "custody_at": utc_now()}),
                                           encoding="utf-8")
        assert runlog.end_supervisor(tmp_path) is True
        child.wait(30)
    finally:
        ended(child)
