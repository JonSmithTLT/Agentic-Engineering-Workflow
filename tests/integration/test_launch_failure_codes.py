"""Every launch failure carries a closed reason code (M4-E E8a; plan v3 n8, amendment 1 §1 and R3-n1), at each of the
four sites: the supervisor refusing custody, the harness not starting, the supervisor getting no usable handoff, and
the launcher when custody is never acknowledged. The record keeps its free-text `reason`; the launcher takes the code
only from the supervisor's acknowledgement, or sets its own, and never from the model-writable run record. Each mapped
code here is produced by the launch that reproduces it; everything else is `unknown`. Nothing relaunches (E8b)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project
from conftest import clean_env
from fake_harness import SCRIPTS_ENV, HarnessLab
from invariants import assert_control_invariants

from aew import errors
from aew.engine import harness_ops
from aew.engine.api import Engine
from aew.harness import contract as K
from aew.harness import runlog

RUN = "R-INV-0001-1"
NO_WINDOW: dict[str, Any] = ({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32"
                             else {"start_new_session": True})


@pytest.fixture
def lab(tmp_path, monkeypatch):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    for k, v in lab.env.items():  # the launches here run in this process, and hand the fake harness to supervisors
        monkeypatch.setenv(k, v)
    yield lab
    lab.cleanup()


def dispatched(lab: HarnessLab, tmp_path: Path) -> str:
    """An implementer dispatched without a launch, its Ticket RUNNING: `harness launch` records run 1."""
    wid = create_planned_ticket(lab.project, tmp_path)
    inv = lab.lead("work", "assign", wid)["invocation"]
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    return inv


def launch_failure(lab: HarnessLab, inv: str) -> errors.HarnessLaunchFailed:
    p = lab.project
    with pytest.raises(errors.HarnessLaunchFailed) as failed:
        Engine.discover(p.root).harness_launch(token=p.token, expect_rev=p.rev(), invocation=inv)
    return failed.value


def incompatible(lab: HarnessLab, run: str = RUN) -> None:
    """The fake harness's capability probe finds something missing (`HarnessIncompatible` from its launch)."""
    (Path(lab.env[SCRIPTS_ENV]) / f"{run}.json").write_text(json.dumps({"health": "incompatible"}), encoding="utf-8")


def paused_at_custody(tmp_path: Path, monkeypatch) -> Path:
    pause = tmp_path / "custody.pause"
    pause.touch()
    monkeypatch.setenv("AEW_PAUSE", f"harness.supervisor.before_custody={pause}")
    return pause


def record_of(lab: HarnessLab, run: str = RUN) -> dict[str, Any] | None:
    return runlog.read_record(runlog.run_dir(lab.aew_root, run))


# ------------------------------------------------------------------ each site, through the launch that reproduces it

def refuse(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 1: the invocation is cancelled while its supervisor is on its way to custody, so the credential it is
    handed is no longer valid (STALE_AUTHORITY at custody: `credential_denied`)."""
    inv = dispatched(lab, tmp_path)
    pause = paused_at_custody(tmp_path, monkeypatch)
    p = lab.project
    failed: list[BaseException] = []
    expect_rev = p.rev()

    def launch() -> None:
        try:
            Engine.discover(p.root).harness_launch(token=p.token, expect_rev=expect_rev, invocation=inv)
        except BaseException as exc:  # handed to the test thread, which checks it
            failed.append(exc)

    thread = threading.Thread(target=launch, name="launch-under-test", daemon=True)
    thread.start()
    try:
        lab.until(lambda: Path(f"{pause}.reached").exists(), 60, "the supervisor to reach custody")
        lab.lead("invoke", "cancel", inv, "--reason", "cancelled before custody")
    finally:
        pause.unlink()
    thread.join(120)
    assert not thread.is_alive(), "the launch never returned"
    [exc] = failed  # the launch never returned normally
    if not isinstance(exc, errors.HarnessLaunchFailed):
        raise exc
    record = record_of(lab)
    assert record is not None and record["reason"].startswith(
        f"custody refused: credential rejected: invocation {inv} is cancelled"), record
    assert exc.message.startswith(f"{RUN}'s supervisor refused custody: credential rejected: invocation {inv}")
    return record, exc


def start(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 2: the adapter cannot start the harness (here, no fake script: HARNESS_LAUNCH_FAILED, unmapped)."""
    exc = launch_failure(lab, dispatched(lab, tmp_path))
    record = record_of(lab)
    assert record is not None and record["reason"] == f"HARNESS_LAUNCH_FAILED: no fake script for {RUN}"
    assert exc.message == f"{RUN} failed to start: HARNESS_LAUNCH_FAILED: no fake script for {RUN}"
    return record, exc


def start_incompatible(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 2: a harness that lacks what AEW needs (HARNESS_INCOMPATIBLE at start: `incompatible_config`)."""
    inv = dispatched(lab, tmp_path)
    incompatible(lab)
    exc = launch_failure(lab, inv)
    record = record_of(lab)
    assert record is not None and record["reason"] == (
        "HARNESS_INCOMPATIBLE: fake capability probe: required operation session.fork is missing")
    return record, exc


def supervise(run_dir: Path, handoff: bytes) -> dict[str, Any] | None:
    """Start a supervisor as the launcher does, with ``handoff`` as everything on its stdin."""
    run_dir.mkdir(parents=True)
    res = subprocess.run([sys.executable, "-m", "aew.harness.supervisor", "--run-dir", str(run_dir)], input=handoff,
                         capture_output=True, env=clean_env(None), timeout=120, check=False, **NO_WINDOW)
    assert res.returncode == 3, res.stderr
    return runlog.read_record(run_dir)


def handoff_missing(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 3: the launching process ended before handing over custody."""
    record = supervise(tmp_path / "runs" / RUN, b"")
    assert record is not None and record["reason"] == ("no credential handoff: the launching process ended before "
                                                       "handing over custody; no process holds this run's credential")
    return record, None


def handoff_malformed(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 3: the handoff line is not JSON."""
    record = supervise(tmp_path / "runs" / RUN, b"not a handoff\n")
    assert record is not None and record["reason"] == "malformed credential handoff"
    return record, None


def launcher(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 4: the supervisor never acknowledges custody within the launcher's wait; the launcher stops it."""
    inv = dispatched(lab, tmp_path)
    pause = paused_at_custody(tmp_path, monkeypatch)
    monkeypatch.setattr(harness_ops, "ACK_WAIT_S", 2.0)
    try:
        exc = launch_failure(lab, inv)
    finally:
        pause.unlink()
    assert "never acknowledged custody" in exc.message
    return None, exc  # no supervisor recorded anything: the run reads `unconfirmed`, as before


def launcher_spawn(lab, tmp_path, monkeypatch) -> tuple[dict[str, Any] | None, errors.HarnessLaunchFailed | None]:
    """Site 4: the supervisor process cannot be started at all."""
    inv = dispatched(lab, tmp_path)

    def no_process(*_: Any, **__: Any) -> Any:
        raise OSError("no process slot")

    monkeypatch.setattr(harness_ops.procs, "spawn_detached", no_process)
    exc = launch_failure(lab, inv)
    assert "could not start: no process slot" in exc.message
    return None, exc


CASES = {
    "refuse": (refuse, K.CREDENTIAL_DENIED, "acknowledgement"),
    "start": (start, K.UNKNOWN_LAUNCH_FAILURE, "acknowledgement"),
    "start_incompatible": (start_incompatible, K.INCOMPATIBLE_CONFIG, "acknowledgement"),
    "handoff": (handoff_missing, K.UNKNOWN_LAUNCH_FAILURE, None),
    "handoff_malformed": (handoff_malformed, K.UNKNOWN_LAUNCH_FAILURE, None),
    "launcher": (launcher, K.UNKNOWN_LAUNCH_FAILURE, "launcher"),
    "launcher_spawn": (launcher_spawn, K.UNKNOWN_LAUNCH_FAILURE, "launcher"),
}


@pytest.mark.parametrize("case", list(CASES))
def test_launch_failure_carries_a_closed_reason_code(lab, tmp_path, monkeypatch, case):
    """Each site's record and `HarnessLaunchFailed` carry the same closed code, beside the reason text the site always
    wrote (asserted in each case); the exception says where its code came from."""
    produce, code, source = CASES[case]
    record, exc = produce(lab, tmp_path, monkeypatch)
    if record is not None:
        assert record["status"] == K.LAUNCH_FAILED and record["reason_code"] == code, record
    if exc is not None:
        assert exc.code == "HARNESS_LAUNCH_FAILED"
        assert (exc.details["reason_code"], exc.details["reason_code_source"]) == (code, source), exc.details
    assert code in K.LAUNCH_FAILURE_CODES
    if case not in {"handoff", "handoff_malformed"}:
        assert_control_invariants(lab.project)


def test_a_launch_the_launcher_never_saw_end_takes_no_code_from_the_run_record(lab, tmp_path, monkeypatch):
    """R3-n1: custody was acknowledged, but no started message reached the launcher, so it reads the run's record for
    the reason. The record's code (here `incompatible_config`, and anything a model wrote there) is not passed on:
    the exception says `unknown`, from `run_record`, and E8b never takes a code from there."""
    inv = dispatched(lab, tmp_path)
    incompatible(lab)
    read = harness_ops._read_acks

    def started_lost(proc: Any, wait_s: float) -> list[dict[str, Any]]:  # the final word arrives after the wait ends
        return [ack for ack in read(proc, wait_s) if "started" not in ack]

    monkeypatch.setattr(harness_ops, "_read_acks", started_lost)
    exc = launch_failure(lab, inv)
    record = record_of(lab)
    assert record is not None and record["reason_code"] == K.INCOMPATIBLE_CONFIG
    assert exc.details["status"] == K.LAUNCH_FAILED and exc.details["reason"] == record["reason"]
    assert (exc.details["reason_code"], exc.details["reason_code_source"]) == (K.UNKNOWN_LAUNCH_FAILURE, "run_record")
    assert_control_invariants(lab.project)


def test_launch_failure_reason_text_is_unchanged(lab, tmp_path):
    """`reason` stays the free-text detail everywhere it was read before (the error, `harness status`, `harness wait`,
    next actions); the closed code sits beside it, and `harness wait` prints the record's."""
    wid = create_planned_ticket(lab.project, tmp_path)
    res = lab.lead_res("work", "assign", wid, "--launch")  # no fake script exists for this run
    reason = f"HARNESS_LAUNCH_FAILED: no fake script for {RUN}"
    assert res.returncode == 9 and res.error["code"] == "HARNESS_LAUNCH_FAILED"
    assert res.error["message"] == f"{RUN} failed to start: {reason}"
    assert res.error["details"]["reason"] == reason and res.error["details"]["reason_code"] == "unknown"
    [run] = lab.ok("harness", "status")["runs"]
    assert (run["status"], run["reason"], run["reason_code"]) == ("launch_failed", reason, "unknown")
    waited = lab.ok("harness", "wait", RUN, "--timeout", "30")
    assert (waited["status"], waited["reason"], waited["reason_code"]) == ("launch_failed", reason, "unknown")
    assert "headline" not in waited  # the provider-auth headline is the adapter code's alone
    assert_control_invariants(lab.project)
