"""`aew harness wait --any`: the first of several runs to end, woken by the wake file (M4-D slice D6; register E1;
ADR-0012 D4, D5 and D8; M4 report §2.9; ledger OBX-37 and OBX-38).

Two fake-harness runs hold on files the test controls. A waiter on both returns the one that ends first, with its next
action, and names the one still running; an invocation cancelled from the control side ends the wait too (the second
lane); and between commits a waiter parses no control state however often the wake file changes.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from aewflow import create_planned_ticket, sample_project
from conftest import IS_WINDOWS, clean_env
from fake_harness import HarnessLab, credential_hits
from invariants import assert_control_invariants

from aew.engine import outbox
from aew.engine.api import Engine
from aew.util import dump_yaml, load_yaml

RA, RB = "R-INV-0001-1", "R-INV-0002-1"


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def held(lab, tmp_path, *names: str) -> dict[str, Path]:
    """Two Tickets assigned and launched, each run holding until its file exists."""
    gates = lab.root / ".aew/policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": 2}),
                     encoding="utf-8", newline="\n")
    lab.project.pin_policy()
    release = {}
    for i, run in enumerate(names):
        release[run] = tmp_path / "sync" / f"release-{i}"
        lab.script(run, [{"do": "touch", "path": str(tmp_path / "sync" / f"started-{i}")},
                         {"do": "wait_file", "path": str(release[run]), "timeout": 300}])
        wid = create_planned_ticket(lab.project, tmp_path, title=f"Add op{i}")
        lab.lead("work", "assign", wid, "--launch")
        lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    for i in range(len(names)):
        lab.until(lambda i=i: (tmp_path / "sync" / f"started-{i}").exists(), what=f"run {i} started")
    return release


def spawn_wait(lab, *args: str) -> subprocess.Popen:
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    return subprocess.Popen([sys.executable, "-m", "aew", "-C", str(lab.root), "harness", "wait", *args],
                            env=clean_env(lab.env), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            stdin=subprocess.DEVNULL, text=True, encoding="utf-8", **kwargs)


def finish(proc: subprocess.Popen, timeout: float = 120) -> dict:
    import json

    out, err = proc.communicate(timeout=timeout)
    assert proc.returncode == 0, err or out
    return json.loads(out)


def test_wait_any_returns_the_first_run_to_end_with_its_next_action(lab, tmp_path):
    release = held(lab, tmp_path, RA, RB)
    waiter = spawn_wait(lab, RA, RB, "--any", "--timeout", "120")
    time.sleep(1.0)  # the waiter is blocked on the wake file, not polling a run
    release[RB].write_text("go", encoding="utf-8")
    out = finish(waiter)
    assert out["run"] == RB and not out["timed_out"] and out["still_running"] == [RA]
    assert out["status"].startswith("ended") and "next_action" in out
    release[RA].write_text("go", encoding="utf-8")
    assert lab.wait(RA)["run"] == RA  # the single-run form is unchanged
    assert_control_invariants(lab.project)


def test_a_run_whose_invocation_is_cancelled_ends_the_wait_from_the_control_side(lab, tmp_path):
    release = held(lab, tmp_path, RA, RB)
    waiter = spawn_wait(lab, RA, RB, "--any", "--timeout", "120")
    time.sleep(1.0)
    lab.lead("invoke", "cancel", "INV-0001", "--reason", "no longer needed")
    out = finish(waiter)
    assert out["run"] == RA, out
    # Whichever lane saw it first: the control state (the invocation is cancelled) or the run's own record.
    assert out.get("ended_by", {}).get("why") == "invocation INV-0001 is cancelled" or out["status"] != "running"
    release[RB].write_text("go", encoding="utf-8")
    lab.wait(RB)
    assert_control_invariants(lab.project)


def test_several_runs_need_any_and_each_run_once(lab, tmp_path):
    release = held(lab, tmp_path, RA, RB)
    for args, needle in (((RA, RB), "needs --any"), ((RA, RA, "--any"), "named twice")):
        res = lab.aew("harness", "wait", *args, "--timeout", "1")
        assert res.returncode != 0 and needle in res.error["message"], res.stdout
    timed = lab.ok("harness", "wait", RA, RB, "--any", "--timeout", "1")
    assert timed["timed_out"] and set(timed["runs"]) == {RA, RB}
    for f in release.values():
        f.write_text("go", encoding="utf-8")
    lab.wait(RA)
    lab.wait(RB)


def test_a_waiter_parses_no_control_state_between_commits(lab, tmp_path, monkeypatch):
    """OBX-38: wakes without a commit (a run-record write, a spurious bump) cost a stat, never a parse of
    control.yaml; a commit costs exactly one."""
    release = held(lab, tmp_path, RA, RB)
    engine = Engine.discover(lab.root)
    reads = []
    real = engine.store.read
    monkeypatch.setattr(engine.store, "read", lambda *a, **k: reads.append(1) or real(*a, **k))
    stop = threading.Event()

    def bump() -> None:
        while not stop.is_set():
            outbox.bump_wake(lab.aew_root)
            time.sleep(0.05)

    noise = threading.Thread(target=bump, daemon=True)
    noise.start()
    try:
        out = engine.harness_wait([RA, RB], any_=True, timeout=1.5)
    finally:
        stop.set()
        noise.join()
    assert out["timed_out"] and len(reads) == 1, len(reads)  # the initial read only
    reads.clear()
    committer = threading.Thread(target=lambda: (time.sleep(0.5), create_planned_ticket(lab.project, tmp_path,
                                                                                       title="A commit")))
    committer.start()
    out = engine.harness_wait([RA, RB], any_=True, timeout=4.0)
    committer.join()
    assert out["timed_out"] and 2 <= len(reads) <= 1 + 6, len(reads)  # the initial read, then one per commit
    for f in release.values():
        f.write_text("go", encoding="utf-8")
    lab.wait(RA)
    lab.wait(RB)


def _records_say_running(monkeypatch, *runs: str) -> None:
    """Hold the named runs' own records at running, so only the control lane can end the wait."""
    from aew.harness import runlog

    real = runlog.observed_status
    monkeypatch.setattr(runlog, "observed_status",
                        lambda d, *a, **k: ("running", None) if Path(d).name in runs else real(d, *a, **k))


def test_an_invocation_already_ended_when_the_wait_starts_ends_it_at_once(lab, tmp_path, monkeypatch):
    """The initial control snapshot is examined too: a cancellation committed before the wait began ends it at once,
    even while the run's own record still says running (independent review of #79)."""
    release = held(lab, tmp_path, RA, RB)
    lab.lead("invoke", "cancel", "INV-0001", "--reason", "no longer needed")
    engine = Engine.discover(lab.root)
    _records_say_running(monkeypatch, RA, RB)
    started = time.monotonic()
    out = engine.harness_wait([RA, RB], any_=True, timeout=30)
    assert out["run"] == RA and not out["timed_out"], out
    assert out["ended_by"] == {"lane": "control", "why": "invocation INV-0001 is cancelled"}
    assert time.monotonic() - started < 5, "the waiter waited for a commit it had already seen"
    assert out["still_running"] == [RB]
    monkeypatch.undo()
    release[RB].write_text("go", encoding="utf-8")
    lab.wait(RB)


def test_a_commit_between_the_initial_read_and_its_identity_is_not_lost(lab, tmp_path, monkeypatch):
    """A commit that lands just after the waiter's initial read is a change it must examine: the identity it compares
    against is taken before that read, never after (independent review of #79)."""
    release = held(lab, tmp_path, RA, RB)
    engine = Engine.discover(lab.root)
    _records_say_running(monkeypatch, RA, RB)
    real = engine.store.read
    calls = []

    def read(*a, **k):
        snapshot = real(*a, **k)
        if not calls:  # the initial read: the cancellation commits right after it
            lab.lead("invoke", "cancel", "INV-0001", "--reason", "no longer needed")
        calls.append(1)
        return snapshot

    monkeypatch.setattr(engine.store, "read", read)
    out = engine.harness_wait([RA, RB], any_=True, timeout=30)
    assert out["run"] == RA and out.get("ended_by", {}).get("lane") == "control", out
    monkeypatch.undo()
    release[RB].write_text("go", encoding="utf-8")
    lab.wait(RB)


def test_still_running_names_only_runs_observed_live(lab, tmp_path):
    """Several targets already ended: wait-any returns one and calls none of the others still running."""
    release = held(lab, tmp_path, RA, RB)
    for f in release.values():
        f.write_text("go", encoding="utf-8")
    lab.wait(RA)
    lab.wait(RB)
    out = lab.ok("harness", "wait", RA, RB, "--any", "--timeout", "10")
    assert out["run"] in (RA, RB) and not out["timed_out"] and out["still_running"] == [], out


def test_still_running_reflects_a_commit_the_record_lane_returned_before(lab, tmp_path, monkeypatch):
    """One run's record has ended, so the first check returns from the record lane without examining control state;
    the other run's invocation was cancelled by a commit right after the waiter's initial read. still_running must
    not name it (independent review of #79, second pass)."""
    release = held(lab, tmp_path, RA, RB)
    release[RA].write_text("go", encoding="utf-8")
    lab.wait(RA)
    engine = Engine.discover(lab.root)
    _records_say_running(monkeypatch, RB)
    real = engine.store.read
    calls = []

    def read(*a, **k):
        snapshot = real(*a, **k)
        if not calls:  # the initial read: RB's invocation is cancelled right after it
            lab.lead("invoke", "cancel", "INV-0002", "--reason", "no longer needed")
        calls.append(1)
        return snapshot

    monkeypatch.setattr(engine.store, "read", read)
    out = engine.harness_wait([RA, RB], any_=True, timeout=30)
    assert out["run"] == RA and "ended_by" not in out, out  # returned by the record lane
    assert out["still_running"] == [], out
    monkeypatch.undo()
    release[RB].write_text("go", encoding="utf-8")
    lab.wait(RB)
