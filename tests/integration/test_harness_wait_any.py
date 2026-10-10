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
from typing import Any

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
    result = json.loads(out)
    assert proc.returncode == wait_exit(result), err or out  # 20 for a run that ended without evidence (U8)
    return result


def wait_exit(result: dict) -> int:
    from aew.cli.work_commands import WAIT_NO_EVIDENCE_EXIT

    return WAIT_NO_EVIDENCE_EXIT if result.get("status") == "ended_without_evidence" else 0


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
    control.yaml; a commit costs exactly one, and commits that land between two checks cost one between them.

    The second half has no time window: the commits land after the waiter's initial read, the test waits until the
    waiter has parsed the last of them, then ends the wait through a run's own record, which costs no parse (register
    E3, 2026-10-09: a fixed 4 s window closed before the commits on a loaded host)."""
    release = held(lab, tmp_path, RA, RB)
    engine = Engine.discover(lab.root)
    reads: list[int] = []  # the revision of each control state the waiter parsed
    real = engine.store.read

    def read(*a, **k):
        snapshot = real(*a, **k)
        reads.append(snapshot["revision"])
        return snapshot

    monkeypatch.setattr(engine.store, "read", read)
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
    assert out["timed_out"] and len(reads) == 1, reads  # the initial read only
    reads.clear()
    over = threading.Event()
    _record_ends_once(monkeypatch, over, RA)
    result: dict[str, Any] = {}

    def wait() -> None:
        try:
            result["out"] = engine.harness_wait([RA, RB], any_=True, timeout=300)  # a hang guard: `over` ends it
        except BaseException as exc:  # noqa: BLE001 -- re-raised in the test's thread, not lost with the waiter's
            result["error"] = exc

    def waiting(predicate) -> Any:
        """``predicate``, while the waiter is still waiting: a waiter that ended early (only ``over`` ends it) fails
        the test with its own error, not a sync point's timeout (independent review of #156, F1)."""
        if not waiter.is_alive():
            if "error" in result:
                raise result["error"]
            raise AssertionError(f"the waiter returned before the test ended it: {result}")
        return predicate()

    waiter = threading.Thread(target=wait, daemon=True)
    waiter.start()
    try:
        lab.until(lambda: waiting(lambda: reads), what="the waiter's initial read")
        create_planned_ticket(lab.project, tmp_path, title="A commit")  # several commits, all after that read
        last = engine.store.read_committed()["revision"]
        lab.until(lambda: waiting(lambda: reads[-1] >= last), what="the waiter to parse the last commit")
    finally:
        over.set()
        outbox.bump_wake(lab.aew_root)
        waiter.join(timeout=60)
    if "error" in result:
        raise result["error"]
    assert not waiter.is_alive() and "out" in result, result
    out = result["out"]
    assert out["run"] == RA and not out["timed_out"] and "ended_by" not in out, out  # no commit ended the wait
    commits = engine.store.read_committed()["revision"] - reads[0]
    parses = reads[1:-1]  # between the initial read and the one taken once the wait is over
    assert commits >= 2 and reads[-1] == reads[0] + commits, (commits, reads)
    assert 1 <= len(parses) <= commits and parses == sorted(parses) and parses[-1] == reads[-1], (commits, reads)
    monkeypatch.undo()
    for f in release.values():
        f.write_text("go", encoding="utf-8")
    lab.wait(RA)
    lab.wait(RB)


def _record_ends_once(monkeypatch, over: threading.Event, run: str) -> None:
    """The named run's own record reads ended once ``over`` is set: a test ends a wait without a commit."""
    from aew.harness import runlog

    real = runlog.observed_status
    monkeypatch.setattr(runlog, "observed_status",
                        lambda d, *a, **k: ("ended_without_evidence", None) if over.is_set() and Path(d).name == run
                        else real(d, *a, **k))


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
    res = lab.aew("harness", "wait", RA, RB, "--any", "--timeout", "10")
    out = res.json
    assert res.returncode == wait_exit(out), res.stderr
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
