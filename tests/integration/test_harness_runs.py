"""Harness runs through the CLI with the fake harness (ADR-0009): launch, custody bridge, rotation,
status, stop, deadlines, process-tree ownership, continuation, and the rule that a run's end never
moves AEW state."""

from __future__ import annotations

from pathlib import Path

import pytest
from aewflow import DISCOVERY, SUBTRACT_PATCH, create_investigation, create_planned_ticket, sample_project
from fake_harness import IMPL_REPORT, POLICY, HarnessLab, contains_credential, credential_hits, watch_agent_pid
from invariants import assert_control_invariants

from aew.harness import runlog


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


@pytest.fixture
def sync(tmp_path):
    d = tmp_path / "sync"
    d.mkdir(exist_ok=True)  # HarnessLab already made it (a writable root for contained runs)
    return d


IMPLEMENT = [
    {"do": "write", "files": SUBTRACT_PATCH},
    {"do": "check", "id": "unit"},
    {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
    {"do": "aew", "args": ["whoami"]},
]


def touch_step(path):
    return {"do": "touch", "path": str(path)}


def launch_assign(lab, tmp_path, steps, **kw):
    wid = create_planned_ticket(lab.project, tmp_path, **kw)
    lab.script("default", steps)
    out = lab.lead("work", "assign", wid, "--launch")
    return wid, out


def test_launch_at_dispatch_acts_through_the_bridge_and_never_prints_the_credential(lab, tmp_path):
    wid, out = launch_assign(lab, tmp_path, IMPLEMENT)
    assert "invocation_token" not in out and not contains_credential(str(out))
    run = out["launch"]["run"]
    assert run == f"R-{out['invocation']}-1" and out["launch"]["status"] == "running"
    rev_after_launch = lab.project.rev()
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    rev_before_end = lab.project.rev()
    done = lab.wait(run)
    assert done["status"] == "ended_with_evidence", lab.record(run)
    assert lab.step(run, 1)["exit"] == 0 and lab.step(run, 2)["exit"] == 0
    who = lab.step(run, 3)["stdout_json"]
    assert who["invocation"] == out["invocation"] and who["run"] == run and who["role"] == "implementer"
    evidence = done["evidence"]
    assert len(evidence) == 2  # the check result and the implementation report, both stamped with this run
    assert lab.project.rev() == rev_before_end > rev_after_launch  # the run's end committed nothing
    record = lab.record(run)
    assert record["credential_scan"]["clean"] and not credential_hits(lab.aew_root / "local", tmp_path / "fake-scripts")
    assert_control_invariants(lab.project)


def test_launching_a_dispatched_invocation_rotates_the_printed_credential(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    out = lab.lead("work", "assign", wid)  # scripted dispatch: the credential is printed
    printed = out["invocation_token"]
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.script("default", IMPLEMENT)
    launched = lab.lead("harness", "launch", out["invocation"])
    assert (launched["run"], launched["superseded"]) == (f"R-{out['invocation']}-1", None)
    assert not contains_credential(str(launched))
    assert lab.aew("whoami", "--invocation-token", printed).error["code"] == "STALE_AUTHORITY"
    assert lab.wait(launched["run"])["status"] == "ended_with_evidence"
    [run] = lab.ok("harness", "status", out["invocation"])["runs"]
    assert run["kind"] == "launch" and run["authority"] == "current"
    assert_control_invariants(lab.project)


def test_launch_preconditions_refuse_before_anything_is_committed(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    rev = lab.project.rev()
    workspaces = tmp_path / ".aew-workspaces"

    def files():
        return sorted(p for p in workspaces.rglob("*") if p.is_file()) if workspaces.exists() else []

    before = files()
    # An invocation needs a pinned execution profile to be launched...
    policy = lab.aew_root / "policy/execution.yaml"
    saved = policy.read_text(encoding="utf-8")
    policy.unlink()
    assert lab.lead_res("work", "assign", wid, "--launch").error["code"] == "ILLEGAL_TRANSITION"
    policy.write_text(saved, encoding="utf-8", newline="\n")
    # ... and a harness adapter AEW can load.
    unknown = lab.lead_res("work", "assign", wid, "--launch", env={"AEW_HARNESS_ADAPTERS": ""})
    assert unknown.error["code"] == "HARNESS_INCOMPATIBLE"
    assert lab.project.rev() == rev and files() == before  # no commit, no worktree left behind
    assert lab.ok("work", "show", wid)["control"]["state"] == "READY"


def test_relaunch_preconditions(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "exit", "code": 0}])
    out = lab.lead("work", "assign", wid, "--launch")
    inv, run = out["invocation"], out["launch"]["run"]
    lab.wait(run)
    # The pinned context must still be what durable state produces.
    guard = lab.aew_root / "policy/guardrails.yaml"
    original = guard.read_text(encoding="utf-8")
    guard.write_text(original + "# edited after dispatch\n", encoding="utf-8", newline="\n")
    drift = lab.lead_res("harness", "launch", inv).error
    assert drift["code"] == "ILLEGAL_TRANSITION" and "context pack" in drift["message"]
    guard.write_text(original, encoding="utf-8", newline="\n")
    # An ended invocation is never launched again.
    lab.lead("invoke", "cancel", inv, "--reason", "done with it")
    assert lab.lead_res("harness", "launch", inv).error["code"] == "ILLEGAL_TRANSITION"
    assert_control_invariants(lab.project)


def test_lead_stop_ends_the_run_but_not_the_invocation(lab, tmp_path, sync):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [{"do": "touch", "path": str(sync / "ready")},
                                {"do": "wait_file", "path": str(sync / "never"), "timeout": 300}])
    out = lab.lead("work", "assign", wid, "--launch")
    run = out["launch"]["run"]
    lab.until(lambda: (sync / "ready").exists(), what="ready")
    rev = lab.project.rev()
    lab.ok("harness", "stop", run, "--reason", "wrong approach", "--token", lab.project.token)
    done = lab.wait(run)
    assert done["status"] == "terminated" and done["reason"] == "stopped: wrong approach"
    # The stop request itself is recorded (independent review R1); the invocation is unchanged.
    assert lab.project.rev() == rev + 1 and lab.ok("invoke", "show", out["invocation"])["status"] == "active"
    lab.script("R-INV-0001-2", [{"do": "exit", "code": 0}])
    assert lab.lead("harness", "launch", out["invocation"])["run"] == "R-INV-0001-2"  # a stopped run is not live
    lab.wait("R-INV-0001-2")
    assert_control_invariants(lab.project)


def test_stopping_a_run_ends_its_running_check_and_records_nothing(lab, tmp_path, sync):
    """Independent review (area 2, F6): a check runs in its own process tree, so the run's end must end it too, and a
    check its run's end cut short is not sealed as evidence after the run ended."""
    import time

    from aew.knowledge import evidence
    from aew.util import dump_yaml, load_yaml

    beat = sync / "beat"
    checks_path = lab.root / ".aew/policy/checks.yaml"
    checks = load_yaml(checks_path.read_text(encoding="utf-8"))
    checks["checks"]["unit"]["command"] = [  # a check that keeps a heartbeat until it is killed
        "{python}", "-c", "import pathlib, sys, time\np = pathlib.Path(sys.argv[1])\n"
        "for i in range(3000):\n    p.write_text(str(i))\n    time.sleep(0.1)\n", str(beat)]
    checks_path.write_text(dump_yaml(checks), encoding="utf-8", newline="\n")
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [{"do": "check", "id": "unit"}])
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.until(lambda: beat.exists(), what="the check running")
    started = time.monotonic()
    lab.ok("harness", "stop", run, "--reason", "check cut short", "--token", lab.project.token)
    assert lab.wait(run)["status"] == "terminated"
    assert time.monotonic() - started < 60  # not the check's own timeout
    last = beat.read_text()
    time.sleep(1.0)
    assert beat.read_text() == last  # the check's process is gone
    records, _ = evidence.scan(lab.aew_root, wid)
    assert not [e for e in records if e["kind"] == "check_result"]
    assert_control_invariants(lab.project)


def test_a_check_in_flight_when_its_run_ends_starts_nothing(lab, tmp_path, sync):
    """M4-B review (P2): a check registered just before its run ended, and not yet started, must not start after the
    end. The run's end closes every registered check tree, and the check's request is refused."""
    import time

    from aew.knowledge import evidence
    from aew.util import dump_yaml, load_yaml

    beat = sync / "beat"
    checks_path = lab.root / ".aew/policy/checks.yaml"
    checks = load_yaml(checks_path.read_text(encoding="utf-8"))
    checks["checks"]["unit"]["command"] = ["{python}", "-c",
                                           "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('ran')",
                                           str(beat)]
    checks_path.write_text(dump_yaml(checks), encoding="utf-8", newline="\n")
    gate = sync / "before-spawn"
    gate.write_text("hold", encoding="utf-8")
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [{"do": "check", "id": "unit"}])
    run = lab.lead("work", "assign", wid, "--launch", env={"AEW_PAUSE": f"checks.before_spawn={gate}"})["launch"]["run"]
    lab.until(lambda: Path(str(gate) + ".reached").exists(), what="the check registered and held before its start")
    lab.ok("harness", "stop", run, "--reason", "ended mid-check", "--token", lab.project.token)
    assert lab.wait(run)["status"] == "terminated"
    gate.unlink()  # the held request now carries on, after its run ended
    time.sleep(2.0)
    assert not beat.exists()  # the check never started
    records, _ = evidence.scan(lab.aew_root, wid)
    assert not [e for e in records if e["kind"] == "check_result"]
    assert_control_invariants(lab.project)


def test_profile_deadline_terminates_a_hung_harness(lab, tmp_path):
    policy = dict(POLICY, profiles={"standard": {"provider": "fakeprov", "model": "fake-model", "deadline_s": 1.5}})
    HarnessLab.create(lab.project, tmp_path, policy=policy)
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "hang"}])
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    done = lab.wait(run, timeout=60)
    assert done["status"] == "terminated" and "deadline" in done["reason"]


def test_every_process_the_harness_started_ends_with_the_run(lab, tmp_path, sync):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "spawn_orphan", "pidfile": str(sync / "orphan")}, touch_step(sync / "spawned"),
                           {"do": "wait_file", "path": str(sync / "go"), "timeout": 120}])
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.until(lambda: (sync / "spawned").exists(), what="orphan spawned")
    orphan = watch_agent_pid(lab, run, int((sync / "orphan").read_text()))
    assert orphan.alive()
    (sync / "go").touch()  # the agent exits normally; its descendant must not outlive the run
    assert lab.wait(run)["status"] == "ended_without_evidence"
    lab.until(lambda: not orphan.alive(), 30, "the orphan to be killed with the run's tree")


def test_relaunch_delivers_the_same_pack_plus_a_continuation_from_durable_state(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
                                {"do": "exit", "code": 0}])
    out = lab.lead("work", "assign", wid, "--launch")
    lab.wait("R-INV-0001-1")
    lab.script("R-INV-0001-2", [{"do": "exit", "code": 0}])
    lab.lead("harness", "launch", out["invocation"])
    lab.wait("R-INV-0001-2")
    first = (runlog.run_dir(lab.aew_root, "R-INV-0001-1") / "prompt.md").read_text(encoding="utf-8")
    second = (runlog.run_dir(lab.aew_root, "R-INV-0001-2") / "prompt.md").read_text(encoding="utf-8")
    pack = (lab.aew_root / "local/packs/INV-0001/pack.md").read_text(encoding="utf-8")
    assert pack in first and pack in second and "Continuation" not in first
    tail = second.split("## Continuation", 1)[1]
    assert "R-INV-0001-1" in tail and "INV-0001-check-unit-1 (check_result, pass)" in tail and "calc/core.py" in tail


def test_adapter_launch_failure_is_reported_and_recoverable(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    res = lab.lead_res("work", "assign", wid, "--launch")  # no fake script exists for this run
    assert res.returncode == 9 and res.error["code"] == "HARNESS_LAUNCH_FAILED"
    inv = lab.ok("work", "show", wid)["control"]["implementer_invocation"]
    assert lab.ok("harness", "status", inv)["runs"][0]["status"] == "launch_failed"
    assert lab.ok("invoke", "show", inv)["status"] == "active"
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.script("R-INV-0001-2", IMPLEMENT)
    assert lab.lead("harness", "launch", inv)["run"] == "R-INV-0001-2"
    assert lab.wait("R-INV-0001-2")["status"] == "ended_with_evidence"
    assert_control_invariants(lab.project)


def test_a_non_mutating_executor_runs_in_its_read_only_observation(lab, tmp_path, sync):
    wid = create_investigation(lab.project, tmp_path)
    lab.script("default", [{"do": "cwd", "path": str(sync / "cwd")},
                           {"do": "submit", "kind": "discovery_record", "meta": DISCOVERY}])
    out = lab.lead("work", "dispatch", wid, "--launch")
    assert lab.wait(out["launch"]["run"])["status"] == "ended_with_evidence"
    assert Path((sync / "cwd").read_text()).resolve() == Path(out["observation"]["path"]).resolve()
    assert_control_invariants(lab.project)


def test_bridge_routing_needs_a_bridge_or_a_credential(lab):
    res = lab.aew("whoami")
    assert res.error["code"] == "USAGE" and "invocation credential required" in res.error["message"]


def test_resume_shows_runs_only_when_there_are_some_and_a_lost_harness_is_not_an_interruption(lab, tmp_path):
    """M3-B1: a harness that ended or crashed leaves its invocation active with its authority; `aew resume` says so
    and offers relaunch or cancel. Projects without runs resume exactly as before (no harness section)."""
    wid = create_planned_ticket(lab.project, tmp_path)
    assert "harness_runs" not in lab.ok("resume", "--json")
    lab.script("default", [{"do": "exit", "code": 3}])
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    assert lab.wait(run)["status"] == "crashed"
    r = lab.ok("resume", "--json")
    [entry] = r["harness_runs"]
    assert (entry["run"], entry["status"], entry["invocation"]) == (run, "crashed", "INV-0001")
    assert any("INV-0001 has no live run" in a and "aew harness launch INV-0001" in a for a in r["next_actions"])
    assert lab.ok("work", "show", wid)["control"]["state"] == "ASSIGNED"  # not INTERRUPTED
    text = lab.aew("resume").stdout
    assert "## Harness runs" in text and f"{run} (INV-0001, implementer, {wid}): crashed" in text
