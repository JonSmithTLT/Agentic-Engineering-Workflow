"""Reads relayed for the contained Lead (STG-05 CS-4 addendum 4, ruling 1; ``lead_broker.RELAYED_READS``).

The contained Lead's sandbox masks `.aew/local` whole, so the reads of what is there (the runs' records, the notifier's
and the steering loop's state, the map store) go to its broker, which runs them on the host. Each test drives the real
broker in this process, and the CLI as the Lead's shell runs it: a separate process with the contained Lead's marker
and the broker's coordinates. The sandbox plays no part here; AT-14 and AT-17 (tests/acceptance) run the relay
contained, at a pseudo-terminal."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
import worker_surface
from aewflow import SUBTRACT_PATCH, create_planned_ticket, sample_project
from conftest import clean_env, run_aew
from fake_harness import IMPL_REPORT, HarnessLab
from harness_conformance import FakeOpenCodeDriver, supervisor_gone, sync_dir

from aew import process_kind
from aew.engine import steering
from aew.engine.api import Engine
from aew.engine.store import ControlStore
from aew.harness import bridge, broker_liveness, lead_broker, procs, runlog, wake_queue
from aew.harness import contract as K
from aew.harness import progress as P

IMPLEMENT = [
    {"do": "write", "files": SUBTRACT_PATCH},
    {"do": "check", "id": "unit"},
    {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
]
# These broker receipt files are not session-liveness noise: every test must account for their exact writes.
MESSAGE_DELIVERY_RECORDS = frozenset({"local/lead/told-messages.json", "local/lead/told-messages.lock",
                                      "local/lead/told-messages.lock.queue"})
# What the session's own broker writes under `.aew/local` while it serves, never a relayed read's: its liveness and
# tool-call log (`local/lead/`), the steering loop's state (`local/steering/`), and the wake queue's two files, each
# with the temporary file ``util.atomic_write`` publishes it through (`.<name>.<random>.tmp` beside it). A snapshot
# taken while the broker's wake loop writes catches that temporary file (CI, 2026-11-11: `+local/.lead-wakes.json.
# zrxsd_zt.tmp` on `main`); any other temporary file under `.aew` is still a change.
SESSION_DIRS = tuple(rel.rsplit("/", 1)[0] + "/" for rel in (broker_liveness.REL, steering.LOOP_REL))
SESSION_FILES = (wake_queue.WAKES_REL, wake_queue.SERVING_REL)


def session_own(rel: str) -> bool:
    if rel in MESSAGE_DELIVERY_RECORDS:
        return False  # exact message receipts must remain visible, not hidden as broker-liveness noise
    if rel.startswith(SESSION_DIRS) or rel in SESSION_FILES:
        return True
    folder, _, name = rel.rpartition("/")
    return any(folder == own.rpartition("/")[0] and name.startswith(f".{own.rpartition('/')[2]}.")
               and name.endswith(".tmp") for own in SESSION_FILES)


# The broker's delivery records (STG-05 CS-4 addendum 15): after a relayed `harness wait`, in the directory of the run
# it returned, what it told the Lead (`lead_broker.record_delivery`). Named by exact path; the read's process writes
# nothing.
TOLD = (runlog.END_RETURNED_FILE, runlog.RETURNED_FILE)


def delivery_records(run: str | None, *, messages: bool = False) -> set[str]:
    return ({f"{runlog.RUNS_REL}/{run}/{name}" for name in TOLD} if run is not None else set()) | (
        set(MESSAGE_DELIVERY_RECORDS) if messages else set())


# The one field read from the clock when the command runs: a run's heartbeat age (`harness status`).
CLOCK = re.compile(r'(?<="heartbeat_age_s": )[0-9.]+')


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def start_broker(lab: HarnessLab, monkeypatch) -> lead_broker.LeadBroker:
    """The Lead session's broker, in this process, with the environment the CLI's own runs get (a session's is the
    operator's), so a relayed read sees what a direct one sees."""
    for name, value in clean_env(lab.env).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    broker = lead_broker.LeadBroker(Engine.discover(lab.root), lab.project.token)
    broker.start()
    return broker


@pytest.fixture
def broker(lab, monkeypatch):
    b = start_broker(lab, monkeypatch)
    yield b
    b.close()


def contained(lab: HarnessLab, broker: lead_broker.LeadBroker) -> dict[str, str]:
    return {**lab.env, **broker.env, process_kind.LEAD_CONTAINED_ENV: "1"}


def relayed(lab: HarnessLab, broker: lead_broker.LeadBroker, *argv: str):
    result = run_aew(*argv, cwd=lab.root, env=contained(lab, broker))
    assert broker.server.drain(20)
    return result


def direct(lab: HarnessLab, *argv: str):
    """The read as the Lead's shell ran it before CS-4: on the host, in the project."""
    return run_aew(*argv, cwd=lab.root, env=lab.env)


def worked(lab: HarnessLab, tmp_path: Path) -> tuple[str, str]:
    """A run that ended with its evidence, and a selected structural map: what the relayed reads read."""
    lab.script("default", IMPLEMENT)
    wid = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    assert lab.wait(run)["status"] == "ended_with_evidence", lab.record(run)
    lab.ok("map", "generate", "--select", "--expect-map-rev", lab.ok("map", "show", "--json")["map_revision"],
           "--json", env={"AEW_LEAD_TOKEN": lab.project.token})
    return run, run.removeprefix("R-").rsplit("-", 1)[0]


def cases(run: str, invocation: str) -> list[list[str]]:
    """Every relayed read, with its arguments."""
    out = [["status"], ["status", "--json"], ["resume"], ["resume", "--json"], ["harness", "status"],
           ["harness", "status", invocation], ["harness", "wait", run, "--timeout", "0"], ["harness", "wait", run],
           ["map", "show"],
           ["map", "show", "--json"], ["map", "diff", "--commit", "HEAD", "--commit", "HEAD"], ["map", "diff"],
           ["usage", "show"], ["usage", "show", run, "--json"], ["usage", "show", invocation]]
    assert {frozenset(worker_surface.words(a)) for a in out} == set(lead_broker.RELAYED_READS)
    return out


def changes(before: dict[str, object], after: dict[str, object]) -> list[str]:
    return [c for c in worker_surface.changes(before, after) if not session_own(c[1:])]


def test_only_the_wake_files_atomic_temp_siblings_are_exempt(tmp_path):
    aew = tmp_path / ".aew"
    wakes, serving = Path(wake_queue.WAKES_REL), Path(wake_queue.SERVING_REL)
    wake_temp = wakes.with_name(f".{wakes.name}.planted.tmp")
    siblings = {wake_temp.as_posix(), serving.with_name(f".{serving.name}.planted.tmp").as_posix()}
    other = {"local/.unrelated.planted.tmp", f"state/{wake_temp.name}", wake_temp.with_suffix(".bak").as_posix(),
             serving.with_name(f".{serving.name}-other.planted.tmp").as_posix()}
    for rel in siblings | other:
        (aew / rel).parent.mkdir(parents=True, exist_ok=True)
    before = worker_surface.snapshot(aew)
    for rel in siblings | other:
        (aew / rel).write_text("planted", encoding="utf-8")
    after = worker_surface.snapshot(aew)
    assert set(worker_surface.changes(before, after)) == {f"+{rel}" for rel in siblings | other}
    assert set(changes(before, after)) == {f"+{rel}" for rel in other}


def test_each_relayed_read_prints_what_the_host_prints_and_changes_nothing(lab, broker, tmp_path, monkeypatch):
    """Conditions 2 and 7: through the broker, each read prints what the Lead's shell printed before CS-4, byte for
    byte (apart from a heartbeat's age, read from the clock as it runs), with its exit status, and leaves the store
    and `.aew/local` as they were (the derived history index's catch-up apart, which ``worker_surface.changes``
    names). One write follows a read, and it is the broker's: a wait told the Lead the run's end, which it records in
    its delivery records, each named by its exact path (``delivery_records``; what it records is the next tests')."""
    run, invocation = worked(lab, tmp_path)
    served: list[list[str]] = []
    run_read = lead_broker.run_read

    def spy(engine, argv, cwd, **kw):  # the broker serves in this process: each read it runs is counted
        served.append(list(argv))
        return run_read(engine, argv, cwd, **kw)

    monkeypatch.setattr(lead_broker, "run_read", spy)
    for argv in cases(run, invocation):
        before = worker_surface.snapshot(lab.aew_root)
        via = relayed(lab, broker, *argv)
        assert served[-1:] == [argv], argv  # through the broker, never run by the client itself
        changed = changes(before, worker_surface.snapshot(lab.aew_root))
        told = [c for c in changed if argv[:2] == ["harness", "wait"] and c[1:] in delivery_records(run)]
        assert [c for c in changed if c not in told] == [], argv
        here = direct(lab, *argv)
        assert (via.returncode, CLOCK.sub("AGE", via.stdout), via.stderr) == (
            here.returncode, CLOCK.sub("AGE", here.stdout), here.stderr), argv
    assert run in relayed(lab, broker, "harness", "status").stdout  # it read the run's own record, on the host


class _Poster:
    """The Lead's session for the wake queue: in its turn until the test ends it."""

    def __init__(self) -> None:
        self.posts: list[str] = []
        self.turn = True
        self.made = 0

    def new_id(self) -> str:
        self.made += 1
        return f"msg_{self.made}"

    def busy(self) -> bool:
        return self.turn

    def post(self, wake_id: str, text: str) -> str:
        self.posts.append(text)
        return "ses_this"

    def landed(self, wake_id: str) -> str:
        return wake_queue.DELIVERED


def test_a_relayed_wait_tells_the_lead_through_its_broker_and_its_own_process_writes_nothing(tmp_path, monkeypatch):
    """Review m1 and m2, on a run with news no wait returned. The read's process, a non-writer, writes nothing under
    `.aew`. Its broker, which served it, records what it told the Lead: every trigger the run had, and its end. So the
    triggers aren't returned again, and when the Lead's turn ends no `run_ended` wake repeats the end."""
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        broker = start_broker(lab, monkeypatch)
        poster = _Poster()
        try:
            broker.start_wakes(poster)
            lab.script("default", {"steps": [{"do": "write", "files": {"calc/extra.py": "X = 1\n"}}],
                                   "server": {"tool_parts": True, "live_usage": {}}})
            run = lab.lead("work", "assign", create_planned_ticket(lab.project, tmp_path), "--launch")["launch"]["run"]
            directory = runlog.run_dir(lab.aew_root, run)
            lab.until(lambda: not runlog.possibly_live(runlog.observed_status(directory)[0], None)
                      and (runlog.read_progress(directory) or {}).get("state") == P.ENDED, what="the run to end",
                       timeout=120)
            # The terminal record precedes the supervisor's final advisory wake bump. Observe process exit before
            # attributing every subsequent .aew byte change to the read: do not exempt the wake file from the proof.
            record = lab.record(run)
            lab.until(lambda: supervisor_gone(record), 30, "the ended run's supervisor to exit")
            seq = int(runlog.read_progress(directory)["trigger_seq"])
            assert seq > 0 and runlog.read_returned(directory) == 0 and not runlog.end_returned(directory)
            before = worker_surface.snapshot(lab.aew_root)
            alone = run_aew("harness", "wait", run, "--timeout", "30", cwd=lab.root,
                            env={**lab.env, process_kind.LEAD_CONTAINED_ENV: "1"})  # the process, with no broker
            assert json.loads(alone.stdout)["why"] == [K.RUN_ENDED], alone.stdout + alone.stderr
            assert changes(before, worker_surface.snapshot(lab.aew_root)) == []
            via = relayed(lab, broker, "harness", "wait", run, "--timeout", "30")
            assert json.loads(via.stdout)["why"] == [K.RUN_ENDED], via.stdout + via.stderr
            records = [f"+{p}" for p in sorted(delivery_records(run))]
            assert changes(before, worker_surface.snapshot(lab.aew_root)) == records
            assert runlog.read_returned(directory) == seq and runlog.end_returned(directory)
            # What they hold: a trigger's number and a flag, which move no approval, owner fact, credential or scope
            assert json.loads((directory / runlog.RETURNED_FILE).read_text(encoding="utf-8")) == {"trigger_seq": seq}
            assert (directory / runlog.END_RETURNED_FILE).read_bytes() == b""
            time.sleep(3 * lead_broker.POLL_S)  # a wake gathered meanwhile waits for the turn's end
            poster.turn = False
            time.sleep(3 * lead_broker.POLL_S)
            assert poster.posts == []
        finally:
            broker.close()
    finally:
        lab.cleanup()


def test_a_relayed_wait_that_returns_a_trigger_is_recorded_by_its_broker_alone(tmp_path, monkeypatch):
    """Review N1: the same for a trigger. A run still working wrote outside its scope. The read's process, with no
    broker, returns the trigger and writes nothing; through the broker, the trigger's mark is all that is written, so
    the next wait doesn't return it again."""
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        broker = start_broker(lab, monkeypatch)
        try:
            lab.script("default", {"steps": [{"do": "write", "files": {"src/b/x.py": "Y = 2\n"}}, {"do": "hang"}],
                                   "server": {"tool_parts": True, "live_usage": {}}})
            wid = create_planned_ticket(lab.project, tmp_path, scope=("src/a/**",))
            launch = lab.lead("work", "assign", wid, "--launch")["launch"]
            run = launch["run"]
            directory = runlog.run_dir(lab.aew_root, run)
            try:
                lab.until(lambda: (runlog.read_progress(directory) or {}).get("out_of_scope") == ["src/b/x.py"],
                          what="the write outside the scope", timeout=120)
                # A digest is published before its advisory wake bump. A later digest is the producer's completion
                # barrier: the first poll finished its bump before it could enter the next poll. Keep local/wake in
                # the exact no-write assertion rather than attributing a still-running producer's bump to the read.
                observed = lab.until(lambda: (runlog.read_progress(directory) or {}).get("observed_at"),
                                     what="the trigger poll's observation", timeout=120)
                lab.until(lambda: (runlog.read_progress(directory) or {}).get("observed_at") not in (None, observed),
                          what="the poll after the trigger's advisory wake update", timeout=120)
                own = f"{runlog.RUNS_REL}/{run}/"

                def written(before: dict[str, object]) -> list[str]:  # the live run's supervisor writes its own files
                    return [c for c in changes(before, worker_surface.snapshot(lab.aew_root))
                            if not c[1:].startswith(own) or c[1:] in delivery_records(run)]

                before = worker_surface.snapshot(lab.aew_root)
                alone = run_aew("harness", "wait", run, "--timeout", "30", cwd=lab.root,
                                env={**lab.env, process_kind.LEAD_CONTAINED_ENV: "1"})
                trigger = json.loads(alone.stdout)
                assert trigger["why"] == [K.OUT_OF_SCOPE], alone.stdout + alone.stderr
                assert written(before) == []
                via = relayed(lab, broker, "harness", "wait", run, "--timeout", "30")
                assert json.loads(via.stdout)["why"] == [K.OUT_OF_SCOPE], via.stdout + via.stderr
                seq = max(t["seq"] for t in trigger["triggers"])
                assert written(before) == [f"+{own}{runlog.RETURNED_FILE}"]
                assert runlog.read_returned(directory) == seq and not runlog.end_returned(directory)
                again = json.loads(relayed(lab, broker, "harness", "wait", run, "--timeout", "0").stdout)
                assert again["timed_out"] is True, again  # returned once
            finally:
                lab.lead("invoke", "cancel", launch["invocation"], "--reason", "the test is over")
                lab.wait(run)
        finally:
            broker.close()
    finally:
        lab.cleanup()


def test_a_relayed_read_runs_lock_free_while_a_write_holds_the_control_lock(lab, broker):
    """Conditions 2 and 6: a relayed read runs as a non-writer (``process_kind``), lock-free as the sandbox's reads
    are, so it answers while a write holds the control lock and never takes it; a store writer would wait for it."""
    here = direct(lab, "status", "--json")
    with ControlStore(lab.aew_root).control_lock("a write in progress, held by the test"):
        started = time.monotonic()
        via = relayed(lab, broker, "status", "--json")
        took = time.monotonic() - started
    assert via.returncode == here.returncode == 0 and took < 30, via.stderr
    expected, actual = here.json, via.json
    # The broker can publish its first steering tick between the two reads.
    for status in (expected, actual):
        status["steering"].pop("loop", None)
    assert actual == expected


def test_no_relayed_read_carries_a_runs_password_bridge_key_or_token(lab, broker, tmp_path):
    """Condition 4: with a synthetic server password, bridge key and invocation token planted in every record a run
    keeps, and in the notifier's deliveries, no relayed read's output holds any of them."""
    run, invocation = worked(lab, tmp_path)
    planted = ["SYNTHETIC-SERVER-PASSWORD-0001", "SYNTHETIC-BRIDGE-KEY-0001", "SYNTHETIC-INVOCATION-TOKEN-0001"]
    directory = runlog.run_dir(lab.aew_root, run)
    record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    record.update({"server_password": planted[0], "bridge_key": planted[1], "invocation_token": planted[2]})
    (directory / "run.json").write_text(json.dumps(record), encoding="utf-8")
    line = json.dumps({"at": "2026-10-25T00:00:00Z", "event": "planted", "password": planted[0], "key": planted[1],
                       "token": planted[2]}) + "\n"
    for name in ("events.jsonl", "supervisor.log"):
        with (directory / name).open("a", encoding="utf-8") as f:
            f.write(line)
    (directory / "requests").mkdir(exist_ok=True)
    (directory / "requests" / "planted.json").write_text(line, encoding="utf-8")
    notify = lab.aew_root / "local" / "notify"
    notify.mkdir(parents=True, exist_ok=True)
    with (notify / "deliveries.jsonl").open("a", encoding="utf-8") as f:
        f.write(line)
    for argv in cases(run, invocation):
        out = relayed(lab, broker, *argv)
        assert [p for p in planted if p in out.stdout + out.stderr] == [], argv


def launch_held_open(lab: HarnessLab, tmp_path: Path) -> str:
    """A run whose turn is under way and stays so until the test writes ``sync/go``."""
    sync = sync_dir(tmp_path)
    lab.script("default", [{"do": "touch", "path": str(sync / "ready")},
                           {"do": "wait_file", "path": str(sync / "go"), "timeout": 300}])
    wid = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    return run


def wait_in_flight(lab: HarnessLab, broker: lead_broker.LeadBroker, run: str) -> subprocess.Popen[str]:
    waiting = subprocess.Popen([sys.executable, "-m", "aew", "harness", "wait", run, "--timeout", "120"], cwd=lab.root,
                               env=clean_env(contained(lab, broker)), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding="utf-8",
                               **({"creationflags": procs.CREATE_NO_WINDOW} if procs.IS_WINDOWS
                                  else {"start_new_session": True}))
    lab.until(lambda: broker._reads, what="the relayed wait is in flight on the broker")  # its own process
    return waiting


def test_a_relayed_wait_never_holds_a_lead_write_and_returns_when_the_run_ends(lab, broker, tmp_path):
    """Condition 6: a relayed `harness wait` held open on a live run never delays a Lead-authenticated write through
    the same broker, and returns, as the host's would, once the run ends."""
    run = launch_held_open(lab, tmp_path)
    waiting = wait_in_flight(lab, broker, run)
    try:
        started = time.monotonic()
        out = bridge.call("lead.cli", {"argv": ["work", "create", "ticket", "--title", "While a wait is held",
                                                "--class", "1", "--expect-rev", str(lab.project.rev())],
                                       "cwd": str(lab.root), "stdin": ""},
                          endpoint=broker.env[lead_broker.ENV_ENDPOINT], key=broker.env[lead_broker.ENV_KEY])
        assert out["result"]["id"] and time.monotonic() - started < 30
        assert waiting.poll() is None  # the wait is still held
        (sync_dir(tmp_path) / "go").write_text("x", encoding="utf-8")
        stdout, stderr = waiting.communicate(timeout=120)
    finally:
        if waiting.poll() is None:
            waiting.kill()
    assert json.loads(stdout)["run"] == run and json.loads(stdout)["timed_out"] is False, stdout + stderr
    assert not broker._reads


def test_a_relayed_wait_in_flight_never_holds_the_sessions_close(lab, tmp_path, monkeypatch):
    """Condition 6: when the session closes, a relayed wait in flight ends with it at once (its process is the
    session's), instead of holding the close for the drain's bound; one whose request arrived as the session closed
    is ended as it starts."""
    broker = start_broker(lab, monkeypatch)
    run = launch_held_open(lab, tmp_path)
    try:
        waiting = wait_in_flight(lab, broker, run)
        started = time.monotonic()
        broker.close()
        assert time.monotonic() - started < 20
        waiting.communicate(timeout=60)
        assert waiting.returncode != 0 and not broker._reads
        started = time.monotonic()
        late = lead_broker.run_read(broker.engine, ["harness", "wait", run, "--timeout", "120"], str(lab.root),
                                    track=broker._track)
        assert late["exit"] != 0 and time.monotonic() - started < 20 and not broker._reads
    finally:
        (sync_dir(tmp_path) / "go").write_text("x", encoding="utf-8")


def test_a_relayed_read_whose_wait_fails_is_ended_never_left_running(lab, broker, tmp_path, monkeypatch):
    """Condition 6, and the review of #283 at b2dc3035, m1: whatever ends the broker's wait on a relayed read, the
    read's process ends with it and leaves the session's tracking, so nothing the session's close would miss keeps
    running on the host."""
    run = launch_held_open(lab, tmp_path)
    started: list[subprocess.Popen[str]] = []
    communicate = subprocess.Popen.communicate

    def failing(self, *args, **kw):
        if self in started:  # the relayed read's own process: its wait fails, as an unbounded timeout's did
            raise OverflowError("planted")
        return communicate(self, *args, **kw)

    def track(proc: subprocess.Popen[str], running: bool) -> None:
        if running:
            started.append(proc)
        broker._track(proc, running)

    monkeypatch.setattr(subprocess.Popen, "communicate", failing)
    try:
        began = time.monotonic()
        with pytest.raises(OverflowError):
            lead_broker.run_read(broker.engine, ["harness", "wait", run, "--timeout", "120"], str(lab.root),
                                 track=track)
        assert time.monotonic() - began < 20
        assert started and started[0].returncode is not None and not broker._reads
    finally:
        (sync_dir(tmp_path) / "go").write_text("x", encoding="utf-8")


def test_a_relayed_read_runs_on_the_leads_own_project_only(lab, broker, tmp_path):
    """Condition 3: neither `-C` nor the shell's directory takes a relayed read to another project."""
    other = sample_project(tmp_path / "other")
    res = relayed(lab, broker, "-C", str(other.root), "status")
    assert res.returncode != 0 and res.error["details"]["reason"] == "relayed_project", res.stderr
    res = run_aew("status", cwd=other.root, env=contained(lab, broker))
    assert res.returncode != 0 and res.error["details"]["reason"] == "relayed_project", res.stderr
