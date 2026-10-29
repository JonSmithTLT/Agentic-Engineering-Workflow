"""The operator endpoint's notifier end to end (M4-E E7a; plan v3 §2.8, N3; amendment 1, E7a).

The endpoint notifies with no broker running: a generation ended by takeover, a broker that crashed (and, in Run, is
gone), a broker that closed cleanly while Run is effective. A delivery failure is visible in `status` and the
dashboard's attention and moves nothing. A slow notifier never delays a challenge, and the notifier's child inherits
no endpoint handle. The broker's liveness record beats from its own thread; a clean close or a supersession is never
a crash, a slow read is never stale, and a wedged watchdog is. Launch-failure events come from the supervisor only,
and a deadline stop is spooled as `hard_deadline`."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project
from fake_harness import POLICY, HarnessLab
from notifier import (
    Console,
    Stepped,
    adopt,
    broker_chain,
    dead_pid,
    hidden,
    raise_to,
    received,
    recorder,
    request,
    script,
    step_guard_s,
    takeover,
    until,
    watchdog_wait_s,
)
from racing_read import read_json_or_none

from aew.dashboard.projections import Projector
from aew.dashboard.reader import StateReader
from aew.engine.api import Engine
from aew.engine.lock import FileLock
from aew.engine.store import LOCK_REL
from aew.harness import broker_liveness, event_spool, lead_broker, notify, operator_client, operator_endpoint, procs
from aew.harness import contract as K
from aew.harness import supervisor as S
from aew.history.index import INDEX_REL, HistoryIndex


@pytest.fixture
def serve(project):
    """Start the project's operator endpoint (with its watcher) once the test has adopted its policy."""
    started: list[operator_endpoint.OperatorEndpoint] = []

    def start() -> tuple[operator_endpoint.OperatorEndpoint, Console]:
        console = Console()
        ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=console, dev=True, timeout=20)
        ep.start()
        started.append(ep)
        # The watcher's cursor starts at its first pass: wait for it, so what the test does next is after it.
        until(lambda: notify.summary(project.root / ".aew") is not None, what="the watcher's first pass")
        return ep, console

    yield start
    for ep in started:
        ep.close()


def events(out: Path, name: str) -> list[dict[str, Any]]:
    return [e for e in received(out) if e["event"] == name]


# ---------------------------------------------------------------------------------------------- N3


BROKER = """\
import sys, time
from pathlib import Path
from aew.engine.api import Engine
from aew.harness.lead_broker import LeadBroker
token = sys.stdin.readline().strip()
broker = LeadBroker(Engine.discover(Path(sys.argv[1])), token)
broker.start()
open(sys.argv[2], "w").close()
time.sleep(300)
"""


@pytest.mark.parametrize("case", ["takeover", "broker_crash", "clean_close_in_run"])
def test_notifies_with_no_broker_running(project, tmp_path, monkeypatch, serve, case):
    """N3: the endpoint notifies the operator while no broker is alive. A takeover ends the generation (control
    state); a broker that dies ends it as `crash` and, in Run, is `broker_gone`; a broker that closes cleanly with the
    seat held is not a crash, but in Run the away operator is told (`broker_gone`, reason `closed`; R3-m1)."""
    command, out = recorder(tmp_path)
    engine = adopt(project, command=command)
    if case != "takeover":
        raise_to(engine, "run")
    root = project.root / ".aew"
    ep, _ = serve()
    assert ep.watcher is not None
    generation = Engine.discover(project.root).store.read()["lead"]["generation"]
    if case == "takeover":
        assert broker_liveness.read(root) is None  # no broker was ever started
        takeover(project, monkeypatch)
        [ended] = until(lambda: events(out, "generation_ended"), what="generation_ended")
        assert (ended["reason"], ended["subject"], ended["source"], ended["authenticated"]) == (
            "takeover", f"lead generation {generation}", "control_state", True)
        assert not events(out, "broker_gone")
    elif case == "broker_crash":
        ready = tmp_path / "broker-ready"
        child = subprocess.Popen([sys.executable, script(tmp_path, "broker", BROKER), str(project.root), str(ready)],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 **hidden())
        pids = {child.pid}
        try:
            assert child.stdin is not None
            child.stdin.write((project.token + "\n").encode("utf-8"))
            child.stdin.close()
            until(ready.exists, 60, "the broker to start")
            record = until(lambda: broker_liveness.read(root), what="the broker's liveness record")
            # The broker's own process (a venv's launcher on Windows starts the interpreter as its child).
            assert record["generation"] == generation and procs.pid_alive(record["pid"])
            pids.add(record["pid"])
        finally:
            for pid in pids:
                procs.kill_pid(pid)
            child.wait(30)
        until(lambda: events(out, "generation_ended") and events(out, "broker_gone"), what="the crash events")
        [ended], [gone] = events(out, "generation_ended"), events(out, "broker_gone")
        assert ended["reason"] == gone["reason"] == "crash"
        assert ended["source"] == gone["source"] == "liveness" and not ended["authenticated"]
    else:
        broker = lead_broker.LeadBroker(Engine.discover(project.root), project.token)
        broker.start()
        broker.close()
        [gone] = until(lambda: events(out, "broker_gone"), what="broker_gone")
        assert gone["reason"] == "closed" and gone["subject"] == f"lead generation {generation}"
        ep.watcher.pass_once()
        assert ep.watcher.drain()
        assert not events(out, "generation_ended")  # a clean end is not a generation ending


# ---------------------------------------------------------------------------------------------- failure, isolation


def test_delivery_failure_is_visible_and_moves_no_revision(project, tmp_path, serve):
    """Decision 1: a failed delivery is recorded and surfaced in `status` and the dashboard's attention, and has no
    workflow effect: the revision and control state stand, and the request it was about is still open."""
    failing = [sys.executable, "-I", script(tmp_path, "failing", "import sys\nsys.stdin.read()\nsys.exit(3)\n")]
    adopt(project, command=failing)
    root = project.root / ".aew"
    ep, _ = serve()
    assert ep.watcher is not None
    request(project, "raise")
    revision = project.rev()
    control = (root / "state/control.yaml").read_bytes()
    until(lambda: (notify.summary(root) or {}).get("failed"), what="the failed delivery")
    ep.watcher.pass_once()
    assert ep.watcher.drain()
    assert project.rev() == revision and (root / "state/control.yaml").read_bytes() == control
    [line] = notify.deliveries(root)
    assert (line["event"], line["outcome"], line["reason"], line["exit_code"]) == (
        "raise_requested", "failed", "exit_code", 3)
    engine = Engine.discover(project.root)
    status = engine.status()
    assert status["notifier"]["attention"] and status["notifier"]["failed"] == 1
    assert status["notifier"]["last_failure"]["event"] == "raise_requested"
    assert "the latest delivery failed" in engine.render_status(status)
    assert status["steering"]["requests"][0]["kind"] == "raise"  # nothing about the request changed
    attention = Projector(StateReader(engine).snapshot()).attention_items()
    [item] = [a for a in attention if a["id"] == "AT-notifier"]
    assert item["kind"] == "anomaly" and item["reasons"][0]["code"] == "NOTIFY_DELIVERY_FAILED"


def test_a_slow_notifier_never_delays_a_challenge(project, tmp_path, serve):
    """Delivery runs on its own thread and never holds `_authorizing` or `_engine_lock` (amendment 1, m9): while a
    notifier is still running, a raise's challenge is shown and answered."""
    started, done = tmp_path / "started", tmp_path / "done"
    body = (f"import sys, time\nsys.stdin.read()\nopen({str(started)!r}, 'w').close()\ntime.sleep(25)\n"
            f"open({str(done)!r}, 'w').close()\n")
    adopt(project, command=[sys.executable, "-I", script(tmp_path, "slow", body)], timeout_s=30)
    _, console = serve()
    request(project, "raise")
    until(started.exists, what="the slow notifier to start")
    seen: dict[str, Any] = {}

    def answer(prompt: str) -> str:
        seen.update(at=time.monotonic(), running=not done.exists())
        return console.code()

    asked = time.monotonic()
    out = operator_client.request_raise(project.root / ".aew", "walk", ask=answer, requester="test")
    assert out["mode"] == "walk"
    assert seen["running"], "the challenge waited for the notifier"
    assert seen["at"] - asked < 15


FDS = """\
import json, os, sys
sys.stdin.read()
found = []
if sys.platform.startswith("linux"):
    for fd in os.listdir("/proc/self/fd"):
        try:
            found.append([int(fd), os.readlink(f"/proc/self/fd/{fd}")])
        except OSError:
            pass
else:
    for fd in range(3, 256):
        try:
            os.fstat(fd)
            found.append([fd, "open"])
        except OSError:
            pass
json.dump(found, open(sys.argv[1], "w"))
"""


def test_notifier_child_inherits_no_endpoint_handle(project, tmp_path, serve, monkeypatch):
    """`close_fds=True`: the notifier inherits its three pipes and nothing else, so never the endpoint's lock or its
    listener (amendment 1, m9)."""
    report = tmp_path / "fds.json"
    spawned: list[dict[str, Any]] = []
    real = subprocess.Popen

    def spy(*args: Any, **kwargs: Any) -> Any:
        spawned.append({"argv": args[0], **{k: v for k, v in kwargs.items() if k == "close_fds"}})
        return real(*args, **kwargs)

    command = [sys.executable, "-I", script(tmp_path, "fds", FDS), str(report)]
    adopt(project, command=command)
    ep, _ = serve()
    monkeypatch.setattr(subprocess, "Popen", spy)
    request(project, "raise")

    def whole_report() -> list[Any] | None:  # the child's json.dump opens the file empty before it writes
        found = read_json_or_none(report)
        return None if found is None else [found]

    [found] = until(whole_report, what="the notifier's whole report")
    [call] = [c for c in spawned if c["argv"] == command]
    assert call.get("close_fds") is True
    inherited = [(fd, target) for fd, target in found if fd > 2 and not str(target).startswith("/proc/")]
    if sys.platform.startswith("linux"):
        assert not [t for _, t in inherited if "endpoint" in t or t.startswith("socket:")], inherited
    else:
        assert inherited == [], inherited
    assert ep.address and not [t for _, t in found if ep.address in str(t)]


# ---------------------------------------------------------------------------------------------- broker liveness


@pytest.mark.serial  # the smoke test on real threads and the real clock: a beat every POLL_S, a real supersession
def test_broker_liveness_is_local_and_beats_every_poll(project, monkeypatch):
    """M2, R2-m3, on real threads and the real clock: the broker's beat thread writes `.aew/local/lead/broker.json`
    every POLL_S (local, never control state), and once a takeover supersedes the broker its watchdog writes
    `closed_at`, which is never a crash. The one case of the broker's liveness that still waits for real time (the
    flake audit's rank 2): the cases below step the same threads, on a clock the test moves."""
    poll = 0.25
    monkeypatch.setattr(lead_broker, "POLL_S", poll)
    root = project.root / ".aew"
    engine = Engine.discover(project.root)
    engine.store.lock_timeout = 10.0  # the broker's own store
    broker = lead_broker.LeadBroker(engine, project.token)
    broker.start()
    try:
        generation = broker.generation
        first = until(lambda: broker_liveness.read(root), what="the first beat")
        assert (first["pid"], first["generation"]) == (os.getpid(), generation)
        assert first["wedge_after_s"] == pytest.approx(engine.store.lock_timeout + 2 * poll)
        until(lambda: (broker_liveness.read(root) or first)["beat_at"] > first["beat_at"], 5, "a second beat")
        assert broker_liveness.judge(broker_liveness.read(root), generation=generation, poll_s=poll) is None
        takeover(project, monkeypatch)
        # The watchdog's next iteration may first wait out the control lock: the wait is the broker's own bound for one
        # iteration (wedge_after_s, which judge holds to), never a literal at or below it (f41b001e)
        closed = until(lambda: (broker_liveness.read(root) or {}).get("closed_at") and broker_liveness.read(root),
                       watchdog_wait_s(first, poll), "the superseded broker's closed_at",
                       describe=broker_chain(broker, root))
        assert broker.superseded
        assert broker_liveness.judge(closed, generation=generation, poll_s=poll).reason == "closed"
        assert broker_liveness.judge(closed, generation=generation + 1, poll_s=poll) is None  # not the current
    finally:
        broker.close()
    assert "beat_at" not in (root / "state/control.yaml").read_text(encoding="utf-8")  # local, never control state


@pytest.mark.parametrize("case", ["clean_close_is_not_a_crash", "superseded_is_not_a_crash", "slow_read_is_not_stale",
                                  "wedged_watchdog_is_stale"])
def test_broker_liveness_verdicts_on_a_stepped_broker(project, tmp_path, monkeypatch, case):
    """M2, R2-m3, R3-n2, R4-m1, one stepped iteration at a time on a clock the test moves (the flake audit's seam #3):
    the beat writes the local record on each step and never reads the store; a clean close or a supersession writes
    `closed_at` and is never a crash; a watchdog iteration waiting on the control lock is not stale while it stays
    inside `store.lock_timeout + 2 x POLL_S`, however far past 2 x POLL_S (a stale beat's bound) that is; a watchdog
    stopped past it is stale while the beat goes on, and live again once it goes on.

    Safe under xdist: no thread runs on real time (each iteration waits for its step), and the project, its control
    lock and its liveness record are this test's own."""
    poll = lead_broker.POLL_S
    root = project.root / ".aew"
    engine = Engine.discover(project.root)
    revision = project.rev()
    stepped = Stepped(engine, project.token)
    broker, clock = stepped.broker, stepped.clock
    broker.start()
    try:
        generation = broker.generation
        first = broker_liveness.read(root)  # Beat.start writes it before its thread starts: a whole record
        assert first is not None and (first["pid"], first["generation"]) == (os.getpid(), generation)
        assert first["beat_at"] == first["watchdog_tick_at"] == clock()
        assert first["wedge_after_s"] == pytest.approx(engine.store.lock_timeout + 2 * poll)
        clock.advance(poll)
        assert stepped.beat()["beat_at"] == clock()  # a beat on each step, stamped from the clock
        clock.advance(poll)
        stepped.watchdog()  # an iteration that finds this Lead current, and ticks
        record = stepped.beat()
        assert record["watchdog_tick_at"] == clock()
        assert broker_liveness.judge(record, generation=generation, poll_s=poll, now=clock()) is None

        if case == "clean_close_is_not_a_crash":
            broker.close()
            closed = broker_liveness.read(root)
            assert closed is not None and closed["closed_at"] == clock()
            assert broker_liveness.judge(closed, generation=generation, poll_s=poll, now=clock()).reason == "closed"
            gone = dict(closed, pid=dead_pid())  # even once its process is gone: a clean end, never a crash
            assert broker_liveness.judge(gone, generation=generation, poll_s=poll, now=clock()).reason == "closed"
        elif case == "superseded_is_not_a_crash":
            takeover(project, monkeypatch)
            clock.advance(poll)
            stepped.watchdog()  # the iteration that reads the takeover ends the watchdog
            closed = broker_liveness.read(root)
            assert broker.superseded and not broker._watch.is_alive()
            assert closed is not None and closed["closed_at"] == clock()
            assert broker_liveness.judge(closed, generation=generation, poll_s=poll, now=clock()).reason == "closed"
            assert broker_liveness.judge(closed, generation=generation + 1, poll_s=poll) is None  # not the current
        elif case == "slow_read_is_not_stale":
            tick = record["watchdog_tick_at"]
            with FileLock(root / LOCK_REL):
                clock.advance(poll)  # an iteration that ticked before its read would show this
                n = stepped.begin_watchdog()
                until(stepped.in_lock_wait, step_guard_s(), "the watchdog's read to wait for the control lock")
                # Since the last tick, all of the bound but one POLL_S: far past 2 x POLL_S, a stale beat's bound
                clock.advance(first["wedge_after_s"] - 2 * poll)
                held = stepped.beat()  # the beat goes on under the control lock: it never reads the store
                assert held["watchdog_tick_at"] == tick and held["beat_at"] == clock()  # the read still waits
                assert broker_liveness.judge(held, generation=generation, poll_s=poll, now=clock()) is None, held
            stepped.finish_watchdog(n)  # the read takes the released lock, finds the Lead current, and ticks
            assert stepped.beat()["watchdog_tick_at"] == clock() > tick
        else:
            hold = tmp_path / "wedge"
            hold.write_text("hold", encoding="utf-8")
            monkeypatch.setenv("AEW_PAUSE", f"harness.lead_broker.watchdog={hold}")
            try:
                clock.advance(poll)
                n = stepped.begin_watchdog()
                until(Path(f"{hold}.reached").exists, step_guard_s(), "the watchdog to wedge")
                clock.advance(first["wedge_after_s"] + poll)  # past the bound
                wedged = stepped.beat()
                verdict = broker_liveness.judge(wedged, generation=generation, poll_s=poll, now=clock())
                assert verdict is not None and verdict.reason == "stale" and ":tick:" in verdict.occurrence, wedged
                assert wedged["beat_at"] == clock()  # the beat went on: only the watchdog stopped
            finally:
                hold.unlink()
            stepped.finish_watchdog(n)  # the wedge ends: the iteration goes on, and ticks
            assert broker_liveness.judge(stepped.beat(), generation=generation, poll_s=poll, now=clock()) is None
    finally:
        broker.close()
    assert project.rev() == revision or case == "superseded_is_not_a_crash"  # beats are never commits
    assert "beat_at" not in (root / "state/control.yaml").read_text(encoding="utf-8")  # local, never control state


PAST = {"past_lock_timeout": 1, "past_the_iteration_bound": 2}  # how many of the watchdog's reads give up on the hold


@pytest.mark.parametrize("hold", ["no_hold", "under_lock_timeout", *PAST])
def test_a_superseded_broker_closes_within_one_watchdog_iteration_of_a_held_lock(project, monkeypatch, hold):
    """Main's run at f41b001e: a watchdog read that waits out the control lock is "still the Lead" (`_authority_lost`
    swallows the `LockTimeout`), so only the next iteration acts. Here each iteration is stepped (the flake audit's
    seam #3) and the control lock is held from after the takeover, so the order is forced, never raced.

    With no hold, or a hold the read waits for and then gets (under its lock timeout), the iteration after the takeover
    closes the broker. A hold the read gives up on (past its lock timeout) leaves the broker open, its watchdog
    ticking, so `judge` calls it live: no iteration is stale, and the swallowed `LockTimeout` is what hides the
    supersession (review of #276, F1), for as many iterations as the hold outlasts. The first iteration after the hold
    closes the broker.

    Safe under xdist: no thread runs on real time (a read past its lock timeout gives up at its first try), and the
    project, its control lock and its liveness record are this test's own."""
    root = project.root / ".aew"
    engine = Engine.discover(project.root)
    if hold in PAST:
        # The read gives up at its first try against the hold (FileLock checks its deadline after each try): past its
        # lock timeout, however long the hold, with no real wait
        engine.store.lock_timeout = 0.0
    stepped = Stepped(engine, project.token)
    broker, clock, poll = stepped.broker, stepped.clock, lead_broker.POLL_S
    broker.start()
    try:
        generation = broker.generation
        takeover(project, monkeypatch)
        stepped.loop_ended()  # from here only the watchdog's reads and the test's hold take the control lock
        if hold == "under_lock_timeout":
            with FileLock(root / LOCK_REL):
                clock.advance(poll)
                n = stepped.begin_watchdog()
                until(stepped.in_lock_wait, step_guard_s(), "the watchdog's read to wait for the control lock")
            stepped.finish_watchdog(n)  # the read takes the released lock and reads the takeover
        else:
            if hold in PAST:
                with FileLock(root / LOCK_REL):
                    for _ in range(PAST[hold]):
                        clock.advance(poll)
                        stepped.watchdog()  # its read gives up on the hold
                        record = stepped.beat()
                        # Still the Lead: the LockTimeout was swallowed and the iteration ticked, so judge calls it live
                        assert broker.superseded is None and record["watchdog_tick_at"] == clock(), record
                        assert broker_liveness.judge(record, generation=generation, poll_s=poll, now=clock()) is None
            clock.advance(poll)
            stepped.watchdog()  # the first iteration after the takeover, or after the hold
        closed = broker_liveness.read(root)
        assert broker.superseded and not broker._watch.is_alive()
        assert closed is not None and closed["closed_at"] == clock()
        assert broker_liveness.judge(closed, generation=generation, poll_s=poll, now=clock()).reason == "closed"
    finally:
        broker.close()


@pytest.mark.parametrize("index", ["fresh", "existing"])
def test_a_superseded_broker_closes_within_one_watchdog_iteration_while_the_history_index_is_held(project, monkeypatch,
                                                                                                  index):
    """CI on PR #281 (the Windows serial lane): with no control lock held, the superseded broker's watchdog sat in the
    history index's `executescript` past `watchdog_wait_s`. A takeover moves the old Lead's credential out of the hot
    token table into its archive (ADR-0011 R7), and `require_lead` looks an absent credential up in the archive, whose
    SQLite index waits up to its own 30 s busy timeout for another connection (here the broker's own steering loop,
    syncing the same index after the same takeover). The watchdog's bound counts the control lock's wait and no other.

    Here another connection holds the index from before the takeover to past the iteration: a fresh index's write lock
    (the sighting: the watchdog's schema statements wait for it), or an existing index's exclusive lock (a reader in
    another process blocks every connection). The watchdog decides from the hot state alone, so the one iteration after
    the takeover closes the broker either way (stepped: the flake audit's seam #3). A watchdog that looked in the
    archive would come back from that iteration still open, once the index's busy timeout gave up.

    Safe under xdist: no thread runs on real time, and the project and its history index are this test's own."""
    root = project.root / ".aew"
    engine = Engine.discover(project.root)
    if index == "existing":
        HistoryIndex(root).sync(engine.store.current()["cold"]["root"])
    (root / INDEX_REL).parent.mkdir(parents=True, exist_ok=True)
    held = sqlite3.connect(root / INDEX_REL, timeout=10, isolation_level=None)  # its own take may wait, bounded
    stepped = Stepped(engine, project.token)
    broker, clock, poll = stepped.broker, stepped.clock, lead_broker.POLL_S
    broker.start()
    try:
        generation = broker.generation
        held.execute("BEGIN IMMEDIATE" if index == "fresh" else "BEGIN EXCLUSIVE")
        takeover(project, monkeypatch)
        clock.advance(poll)
        stepped.watchdog()
        closed = broker_liveness.read(root)
        assert broker.superseded and not broker._watch.is_alive()
        assert closed is not None and closed["closed_at"] == clock()
        assert broker_liveness.judge(closed, generation=generation, poll_s=poll, now=clock()).reason == "closed"
    finally:
        held.close()  # ends the hold: the steering loop's own index read goes on, and close() joins it
        broker.close()


# ---------------------------------------------------------------------------------------------- the supervisor's events


def _spooled(aew_root: Path, run: str) -> list[dict[str, Any]]:
    path = event_spool.file_of(aew_root, event_spool.run_writer(run))
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.mark.parametrize("site", ["refuse", "start", "handoff"])
def test_launch_failed_events_come_from_the_supervisor_only(tmp_path, site):
    """R2-m5: `launch_failed` is written by the run's supervisor process, to its run's own spool file, at its three
    failure records: custody refused, the start failed, and main's two records made before any supervisor exists."""
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    try:
        if site == "refuse":
            run = "R-INV-0009-1"
            directory = lab.aew_root / "local/harness/runs" / run
            directory.mkdir(parents=True)
            unknown = ".".join(["aew1", "tk_" + "0" * 16, "a" * 43])  # well-formed, issued by no one: refused
            handoff = {"run": run, "invocation": "INV-0009", "credential": unknown, "repo_root": str(lab.root),
                       "aew_root": str(lab.aew_root)}
            assert S.Supervisor(directory, handoff, io.BytesIO()).start() is False
            runs = [run]
        elif site == "start":
            wid = create_planned_ticket(lab.project, tmp_path)
            res = lab.lead_res("work", "assign", wid, "--launch")  # no fake script for the run: the start fails
            assert res.error["code"] == "HARNESS_LAUNCH_FAILED"
            runs = ["R-INV-0001-1"]
            until(lambda: lab.record(runs[0]).get("status") == K.LAUNCH_FAILED, what="the launch_failed record")
        else:
            runs = ["R-INV-0007-1", "R-INV-0008-1"]
            for run, stdin in zip(runs, (b"", b"not json\n"), strict=True):
                directory = lab.aew_root / "local/harness/runs" / run
                directory.mkdir(parents=True)
                proc = subprocess.run([sys.executable, "-m", "aew.harness.supervisor", "--run-dir", str(directory)],
                                      input=stdin, capture_output=True, timeout=60, env=dict(os.environ), **hidden())
                assert proc.returncode == 3
        for run in runs:
            [line] = _spooled(lab.aew_root, run)
            assert (line["event"], line["subject"]) == ("launch_failed", run)
            assert lab.record(run)["status"] == K.LAUNCH_FAILED and line["reason"] in lab.record(run)["reason"]
        assert sorted(p.name for p in event_spool.spool_dir(lab.aew_root).iterdir()) == sorted(
            f"{event_spool.run_writer(r)}.jsonl" for r in runs)  # one file per writer, the run's own
    finally:
        lab.cleanup()


def test_no_launch_failed_event_when_custody_is_never_acknowledged(tmp_path):
    """R2-m5, site 4: a launch whose custody is never acknowledged has no supervisor and no event. The launcher gets
    `HarnessLaunchFailed` and the run reads `unconfirmed`, as before."""
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    try:
        wid = create_planned_ticket(lab.project, tmp_path)
        hold = tmp_path / "custody-held"
        hold.write_text("hold", encoding="utf-8")
        res = lab.lead_res("work", "assign", wid, "--launch", env={
            "AEW_LAUNCH_ACK_S": "3", "AEW_PAUSE": f"harness.supervisor.before_custody={hold}"})
        assert res.error["code"] == "HARNESS_LAUNCH_FAILED" and "never acknowledged custody" in res.error["message"]
        hold.unlink()
        time.sleep(1.0)  # a supervisor that survived its kill would now go on and write
        assert lab.ok("harness", "status")["runs"][0]["status"] == K.UNCONFIRMED
        assert _spooled(lab.aew_root, "R-INV-0001-1") == []
    finally:
        lab.cleanup()


def test_a_deadline_stop_is_spooled_as_hard_deadline(tmp_path):
    """The supervisor's deadline stop (`supervisor.py`'s watch loop) appends `hard_deadline` before its final record."""
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    try:
        policy = dict(POLICY, profiles={"standard": {"provider": "fakeprov", "model": "fake-model", "deadline_s": 1.5}})
        HarnessLab.create(lab.project, tmp_path, policy=policy)
        wid = create_planned_ticket(lab.project, tmp_path)
        lab.script("default", [{"do": "hang"}])
        run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
        assert lab.wait(run, timeout=60)["status"] == K.TERMINATED
        [line] = _spooled(lab.aew_root, run)
        assert (line["event"], line["subject"]) == ("hard_deadline", run) and "deadline" in line["reason"]
    finally:
        lab.cleanup()
