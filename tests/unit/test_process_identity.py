"""A process's identity survives a wall-clock step (ADR-0009 amendment 2026-10-23).

On Linux ``procs.started_at`` is ``btime`` plus the process's start ticks, and ``btime`` (the wall clock minus the time
since boot) moves with every step of the wall clock, so an epoch start time names no process: ``same_process`` judged
a live process gone after a forward step of more than 2 s. A record now names its process by ``procs.start_id`` (the
boot id and the start ticks; on Windows the absolute creation time), compared exactly.

Each reader of a record that names a process is proved here to prefer the record's start id, with the clock stepped
after the record was written (``clock_step``); the writers that run in this process are proved with their reader. A
reused pid, another boot, another platform's id and a malformed id each read as another process, and a record from
before start ids keeps its start-time check. On Linux a comm (arbitrary bytes) that is not UTF-8, or that holds a line
break, neither loses a process its start id nor breaks or forges a line of ``/proc/<pid>/status``. The custody worker,
the validation executor, the dashboard and the supervisor write their records in
``tests/integration/test_process_identity_records.py``.
"""

from __future__ import annotations

import ast
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


def renamed(comm: bytes) -> subprocess.Popen[bytes]:
    """Linux: a child that sets its own comm to ``comm`` (``prctl(PR_SET_NAME)``) and then waits."""
    code = (f"import ctypes, sys, time; ctypes.CDLL(None).prctl(15, {comm!r}, 0, 0, 0); "
            "sys.stdout.write('ready\\n'); sys.stdout.flush(); time.sleep(60)")
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE)
    assert child.stdout is not None and child.stdout.readline() == b"ready\n"
    assert Path(f"/proc/{child.pid}/comm").read_bytes() == comm + b"\n"  # the kernel holds the bytes as given
    return child


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


@pytest.mark.skipif(not IS_LINUX, reason="the comm and /proc are Linux's")
def test_a_process_whose_comm_is_not_utf8_still_has_its_start_id_on_linux():
    child = renamed(b"\xff\xfe) bad")
    try:
        raw = Path(f"/proc/{child.pid}/stat").read_bytes()
        ticks = int(raw[raw.rindex(b")") + 1:].split()[19])  # field 22, parsed as bytes: no codec involved
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        assert procs.start_id(child.pid) == f"linux:{boot}:{ticks}"
        assert procs.same_process(child.pid, f"linux:{boot}:{ticks}")
    finally:
        ended(child)


@pytest.mark.skipif(not IS_LINUX, reason="the comm and /proc are Linux's")
def test_a_comm_neither_breaks_nor_forges_a_line_of_proc_status_on_linux():
    """``/proc/<pid>/status`` holds the comm raw, but for a newline and a backslash. A comm that is not UTF-8 must not
    stop the read, and neither a line break ``str.splitlines`` knows (\\x1e) nor a carriage return, which a text-mode
    read turns into a newline (review of #250, M2), may add a forged ``PPid:`` line. One test, so one platform pin."""
    for comm in (b"\xff\x1ePPid:\t1", b"\xff\rPPid:\t1"):
        child = renamed(comm)
        try:
            assert procs.host_pid(child.pid) == child.pid, comm  # every process's status read, this one's included
            assert procs._descends(child.pid, os.getpid()), comm  # noqa: SLF001 (the real parent, not the comm's)
        finally:
            ended(child)


# ---------------------------------------------------------------------------------------------- reads of /proc

ROOT = Path(__file__).resolve().parents[2]
# The only /proc files src may read as text: kernel ASCII that holds no comm (a process's name, arbitrary bytes).
PROC_TEXT_ALLOWED = {
    "/proc/stat": "kernel ASCII: CPU counters and btime, no comm",
    "/proc/sys/kernel/random/boot_id": "kernel ASCII: one UUID",
}
PATH_CALLS = {"Path", "PurePath", "PosixPath", "PurePosixPath"}


def _proc_path(node: ast.AST, names: dict[str, str]) -> str | None:
    """The /proc path an expression names, with ``{}`` for each part only known at run time, or None. It follows a
    string, an f-string, ``Path(...)`` (and ``os.path.join``), ``/`` on such a path, and a name bound to one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    elif isinstance(node, ast.Name):
        return names.get(node.id)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _proc_path(node.left, names)
        right = node.right.value if isinstance(node.right, ast.Constant) else "{}"
        return f"{left}/{right}" if left else None
    elif isinstance(node, ast.Call) and node.args and (
            (isinstance(node.func, ast.Name) and node.func.id in PATH_CALLS)
            or (isinstance(node.func, ast.Attribute) and node.func.attr in PATH_CALLS | {"join"})):
        first = _proc_path(node.args[0], names)
        if not first:
            return None
        rest = [a.value if isinstance(a, ast.Constant) else "{}" for a in node.args[1:]]
        return "/".join([first, *rest])
    else:
        return None
    return text if text == "/proc" or text.startswith("/proc/") else None


def _mode(call: ast.Call, position: int) -> str | None:
    """An ``open`` call's mode: its literal, ``"r"`` when it has none, or None when it is not a literal."""
    arg = call.args[position] if len(call.args) > position else next(
        (k.value for k in call.keywords if k.arg == "mode"), None)
    if arg is None:
        return "r"
    return arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else None


def proc_reads(source: str, *, depth: int = 0) -> list[tuple[int, str, str]]:
    """Every read of a /proc file in ``source``, as (line, path, ``bytes`` or ``text``): ``read_text``, ``read_bytes``,
    and ``open`` (builtin, ``io.open`` or ``Path.open``) with its mode. A string that holds a script with such a read
    (the session reaper's) is read too."""
    tree = ast.parse(source)
    names: dict[str, str] = {}
    for node in ast.walk(tree):  # a name bound to a /proc path, anywhere in the module
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found = _proc_path(node.value, names)
            if found:
                names[node.targets[0].id] = found
    reads: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and depth < 2 and "/proc" in node.value \
                and ("open(" in node.value or "read_" in node.value):
            try:
                inner = proc_reads(node.value, depth=depth + 1)
            except SyntaxError:  # prose, not a script
                continue
            reads.extend((node.lineno, path, kind) for _, path, kind in inner)
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ("read_text", "read_bytes"):
            path = _proc_path(func.value, names)
            if path:
                reads.append((node.lineno, path, "bytes" if func.attr == "read_bytes" else "text"))
        elif isinstance(func, ast.Attribute) and func.attr == "open" and (path := _proc_path(func.value, names)):
            mode = _mode(node, 0)  # Path.open(mode)
            reads.append((node.lineno, path, "bytes" if mode and "b" in mode else "text"))
        elif ((isinstance(func, ast.Name) and func.id == "open")
              or (isinstance(func, ast.Attribute) and func.attr == "open" and isinstance(func.value, ast.Name)
                  and func.value.id == "io")) and node.args:
            path = _proc_path(node.args[0], names)
            if path:
                mode = _mode(node, 1)
                reads.append((node.lineno, path, "bytes" if mode and "b" in mode else "text"))
    return reads


def proc_text_reads(source: str) -> list[tuple[int, str]]:
    """The reads that break the rule: a /proc file read as text, unless it is one of ``PROC_TEXT_ALLOWED``."""
    return [(line, path) for line, path, kind in proc_reads(source) if kind == "text" and path not in PROC_TEXT_ALLOWED]


def test_every_read_of_a_proc_file_in_src_that_can_hold_a_comm_is_a_bytes_read():
    """A comm is arbitrary bytes: a codec that can fail turns it into an error, and text mode turns its ``\\r`` into a
    newline (review of #250, M1 and M2). So src reads every /proc file as bytes, but the kernel-ASCII files that hold
    none (``PROC_TEXT_ALLOWED``, each with why)."""
    broken, seen = [], set()
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        broken += [f"{rel}:{line} reads {proc} as text" for line, proc in proc_text_reads(source)]
        seen |= {(rel, proc, kind) for _, proc, kind in proc_reads(source)}
    assert not broken, broken
    # The scan is not blind: it sees each known read of a comm's file, as bytes, by every form it follows.
    assert {("src/aew/harness/procs.py", "/proc/{}/stat", "bytes"),  # _start_ticks, describe, the reaper's script
            ("src/aew/harness/procs.py", "/proc/{}/status", "bytes"),  # _status_lines: Path(...) with parts
            ("src/aew/harness/operator_endpoint.py", "/proc/{}/stat", "bytes"),  # through a name: proc / "stat"
            ("src/aew/harness/procs.py", "/proc/stat", "text")} <= seen, sorted(seen)


@pytest.mark.parametrize(("source", "flagged"), [
    pytest.param('Path(f"/proc/{pid}/status").read_text()', True, id="read_text"),
    pytest.param('Path(f"/proc/{pid}/stat").read_text(encoding="latin-1")', True, id="read_text-latin1"),
    pytest.param('open(f"/proc/{pid}/stat")', True, id="open-no-mode"),
    pytest.param('io.open("/proc/self/status", mode="r")', True, id="io-open-text"),
    pytest.param('proc = Path(f"/proc/{pid}")\n(proc / "stat").read_text()', True, id="through-a-name"),
    pytest.param('Path("/proc", str(pid), "status").open().read()', True, id="path-parts-open"),
    pytest.param("SCRIPT = " + repr('open(f"/proc/{d}/stat").read()\n'), True, id="script-in-a-string"),
    pytest.param('Path(f"/proc/{pid}/stat").read_bytes().decode("latin-1")', False, id="read_bytes"),
    pytest.param('open(f"/proc/{d}/stat", "rb")', False, id="open-rb"),
    pytest.param('proc = Path(f"/proc/{pid}")\n(proc / "status").read_bytes()', False, id="bytes-through-a-name"),
    pytest.param('Path("/proc/stat").read_text()', False, id="allowed-proc-stat"),
    pytest.param('Path("/proc/sys/kernel/random/boot_id").read_text()', False, id="allowed-boot-id"),
    pytest.param('Path("notes.txt").read_text()', False, id="not-proc"),
    pytest.param('"""Reads ``/proc/<pid>/stat`` with open(...)."""', False, id="prose-naming-proc"),
])
def test_the_proc_read_guard_flags_text_reads_and_passes_bytes_reads(source, flagged):
    assert bool(proc_text_reads(source)) is flagged, proc_reads(source)


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
