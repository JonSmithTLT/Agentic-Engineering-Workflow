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
from harness_conformance import sync_dir

from aew import process_kind
from aew.engine.api import Engine
from aew.engine.store import ControlStore
from aew.harness import bridge, lead_broker, procs, runlog

IMPLEMENT = [
    {"do": "write", "files": SUBTRACT_PATCH},
    {"do": "check", "id": "unit"},
    {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
]
# What the session's own broker writes under `.aew/local` while it serves (its liveness, the steering loop's state):
# never a relayed read's.
SESSION_OWN = ("local/lead", "local/steering")
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
    return run_aew(*argv, cwd=lab.root, env=contained(lab, broker))


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
    lab.ok("map", "generate", "--select", "--expect-map-rev", "none:0", "--json", "--token", lab.project.token)
    return run, run.removeprefix("R-").rsplit("-", 1)[0]


def cases(run: str, invocation: str) -> list[list[str]]:
    """Every relayed read, with its arguments."""
    out = [["status"], ["status", "--json"], ["resume"], ["resume", "--json"], ["harness", "status"],
           ["harness", "status", invocation], ["harness", "wait", run, "--timeout", "0"], ["harness", "wait", run],
           ["map", "show"],
           ["map", "show", "--json"], ["map", "diff", "--commit", "HEAD", "--commit", "HEAD"], ["map", "diff"]]
    assert {frozenset(worker_surface.words(a)) for a in out} == set(lead_broker.RELAYED_READS)
    return out


def changes(before: dict[str, object], after: dict[str, object]) -> list[str]:
    return [c for c in worker_surface.changes(before, after) if not c[1:].startswith(SESSION_OWN)]


def test_each_relayed_read_prints_what_the_host_prints_and_changes_nothing(lab, broker, tmp_path, monkeypatch):
    """Conditions 2 and 7: through the broker, each read prints what the Lead's shell printed before CS-4, byte for
    byte (apart from a heartbeat's age, read from the clock as it runs), with its exit status, and leaves the store
    and `.aew/local` as they were (the derived history index's catch-up apart, which ``worker_surface.changes``
    names)."""
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
        assert changes(before, worker_surface.snapshot(lab.aew_root)) == [], argv
        here = direct(lab, *argv)
        assert (via.returncode, CLOCK.sub("AGE", via.stdout), via.stderr) == (
            here.returncode, CLOCK.sub("AGE", here.stdout), here.stderr), argv
    assert run in relayed(lab, broker, "harness", "status").stdout  # it read the run's own record, on the host


def test_a_relayed_read_runs_lock_free_while_a_write_holds_the_control_lock(lab, broker):
    """Conditions 2 and 6: a relayed read runs as a non-writer (``process_kind``), lock-free as the sandbox's reads
    are, so it answers while a write holds the control lock and never takes it; a store writer would wait for it."""
    here = direct(lab, "status", "--json")
    with ControlStore(lab.aew_root).control_lock("a write in progress, held by the test"):
        started = time.monotonic()
        via = relayed(lab, broker, "status", "--json")
        took = time.monotonic() - started
    assert (via.returncode, via.stdout) == (here.returncode, here.stdout) and took < 30, via.stderr


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


def test_a_relayed_read_runs_on_the_leads_own_project_only(lab, broker, tmp_path):
    """Condition 3: neither `-C` nor the shell's directory takes a relayed read to another project."""
    other = sample_project(tmp_path / "other")
    res = relayed(lab, broker, "-C", str(other.root), "status")
    assert res.returncode != 0 and res.error["details"]["reason"] == "relayed_project", res.stderr
    res = run_aew("status", cwd=other.root, env=contained(lab, broker))
    assert res.returncode != 0 and res.error["details"]["reason"] == "relayed_project", res.stderr
