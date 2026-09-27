"""M3 harness boundary under attack and failure (ADR-0009; permanent regressions).

Each test is one failure or attack case: a launch that half-happened, a crashed launcher or supervisor,
racing Leads, a run that loses its authority while it is still alive (rotation, cancellation, takeover),
an old run that wakes up after a relaunch, and a model-controlled process trying to obtain the raw
credential or to act as another run. Races are made deterministic with pause points
(``AEW_PAUSE=<point>=<file>``): a process holds at the point while the file exists.

The safe end state asserted every time: no evidence from a run after its authority ended, at most one run
with live authority per invocation, no credential anywhere a model-controlled process can reach, and no
AEW state moved by a harness.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aewflow import (DISCOVERY, SUBTRACT_PATCH, create_investigation, create_planned_ticket, sample_project,
                     unit_check_command)
from conftest import IS_WINDOWS, clean_env
from fake_harness import IMPL_REPORT, HarnessLab, contains_credential, credential_hits
from invariants import assert_control_invariants

from aew.harness import bridge, procs, runlog
from aew.knowledge import evidence as E
from aew.util import dump_yaml

R1, R2 = "R-INV-0001-1", "R-INV-0001-2"
IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]
SLOW_CHECK = ("import os, sys, time\nopen(sys.argv[1] + '.reached', 'a').close()\n"
              "while os.path.exists(sys.argv[1]):\n    time.sleep(0.05)\n")


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


@pytest.fixture
def sync(tmp_path):
    d = tmp_path / "sync"
    d.mkdir()
    return d


def touch(path: Path) -> dict:
    return {"do": "touch", "path": str(path)}


def wait(path: Path, timeout: float = 120) -> dict:
    return {"do": "wait_file", "path": str(path), "timeout": timeout}


def hold(path: Path) -> Path:
    path.write_text("hold", encoding="utf-8")
    return path


WATCHDOG, BRIDGE = "harness.watchdog.tick", "harness.bridge.before_engine"


def pause_env(*points: tuple[str, Path]) -> dict[str, str]:
    """The launched run's supervisor holds at each point while its file exists."""
    return {"AEW_PAUSE": ";".join(f"{name}={path}" for name, path in points)}


def control(lab, wid):
    return lab.ok("work", "show", wid)["control"]


def inv_show(lab, inv):
    return lab.ok("invoke", "show", inv)


def evidence_of(lab, wid, run=None):
    records, problems = E.scan(lab.aew_root, wid)
    assert not problems
    return [e for e in records if run is None or e["producer"].get("run") == run]


def error_code(result: dict) -> str | None:
    return ((result.get("stderr_json") or {}).get("error") or {}).get("code")


def spawn_aew(lab, *args: str, env: dict | None = None) -> subprocess.Popen:
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    return subprocess.Popen([sys.executable, "-m", "aew", "-C", str(lab.root), *args],
                            env=clean_env({**lab.env, **(env or {})}), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", **kwargs)


def assigned(lab, tmp_path, steps=None, *, launch=True, env=None, **kw):
    """A planned Ticket assigned (and, by default, launched) with the given script for its first run."""
    wid = create_planned_ticket(lab.project, tmp_path, **kw)
    if steps is not None:
        lab.script(R1, steps)
    out = lab.lead("work", "assign", wid, *(["--launch"] if launch else []), env=env)
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    return wid, out


# ---------------------------------------------------------------------------------------------- launch half-done

def test_launch_commit_succeeds_but_the_supervisor_never_spawns(lab, tmp_path):
    """Nobody holds the credential: it existed only in the launcher that died. Recovery rotates it."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R2, IMPLEMENT)
    rev = lab.project.rev()
    res = lab.lead_res("work", "assign", wid, "--launch", env={"AEW_FAULT": "harness.launch.after_commit"})
    assert res.returncode == 86 and not contains_credential(res.stdout + res.stderr)
    assert lab.project.rev() == rev + 1  # the dispatch and its run were one commit
    inv = control(lab, wid)["implementer_invocation"]
    [run] = lab.ok("harness", "status", inv)["runs"]
    assert (run["run"], run["status"], run["authority"], run["supervisor_pid"]) == (R1, "unconfirmed", "current", None)
    assert not runlog.run_dir(lab.aew_root, R1).exists()
    # A plain relaunch is refused while that launch could still be completing; --replace rotates the credential.
    assert lab.lead_res("harness", "launch", inv).error["code"] == "RUN_LIVE"
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    out = lab.lead("harness", "launch", inv, "--replace")
    assert (out["run"], out["superseded"]) == (R2, R1)
    assert lab.wait(R2)["status"] == "ended_with_evidence"
    tokens = {r["run"]: r["token_id"] for r in inv_show(lab, inv)["runs"]}
    assert tokens[R1] != tokens[R2]
    assert_control_invariants(lab.project)


def test_supervisor_spawns_then_the_launcher_crashes_before_handing_over_custody(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R2, IMPLEMENT)
    res = lab.lead_res("work", "assign", wid, "--launch", env={"AEW_FAULT": "harness.launch.after_spawn"})
    assert res.returncode == 86
    record = lab.until(lambda: lab.record(R1).get("status") == "launch_failed" and lab.record(R1), what="launch_failed")
    assert "no credential handoff" in record["reason"]
    lab.until(lambda: not procs.pid_alive(record["supervisor_pid"]), what="supervisor exit")
    inv = control(lab, wid)["implementer_invocation"]
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    assert lab.lead("harness", "launch", inv)["run"] == R2  # a failed launch is not live: no --replace needed
    assert lab.wait(R2)["status"] == "ended_with_evidence"
    assert_control_invariants(lab.project)


def test_supervisor_spawns_then_the_launcher_crashes_after_handing_over_custody(lab, tmp_path):
    """The run belongs to its supervisor, not to the process that launched it."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R1, IMPLEMENT)
    res = lab.lead_res("work", "assign", wid, "--launch", env={"AEW_FAULT": "harness.launch.after_handoff"})
    assert res.returncode == 86 and not contains_credential(res.stdout + res.stderr)
    done = lab.wait(R1)
    assert done["status"] == "ended_with_evidence" and len(done["evidence"]) == 2
    assert_control_invariants(lab.project)


def test_supervisor_crash_takes_the_whole_harness_tree_with_it(lab, tmp_path, sync):
    wid, out = assigned(lab, tmp_path, [{"do": "spawn_orphan", "pidfile": str(sync / "orphan")},
                                        {"do": "pid", "path": str(sync / "agent")}, touch(sync / "ready"),
                                        wait(sync / "never", 300)])
    lab.until(lambda: (sync / "ready").exists(), what="agent ready")
    agent, orphan = procs.Watch(int((sync / "agent").read_text())), procs.Watch(int((sync / "orphan").read_text()))
    assert agent.alive() and orphan.alive()
    procs.kill_pid(lab.record(R1)["supervisor_pid"])  # the supervisor dies abruptly: no cleanup code runs
    lab.until(lambda: not agent.alive() and not orphan.alive(), 30, "harness tree killed by the OS")
    stale = {"AEW_RUN_STALE_S": "2"}
    lab.until(lambda: lab.ok("harness", "status", out["invocation"], env=stale)["runs"][0]["status"] == "lost",
              what="run observed lost")
    lab.script(R2, IMPLEMENT)
    assert lab.lead("harness", "launch", out["invocation"], env=stale)["run"] == R2  # lost is not live
    assert lab.wait(R2)["status"] == "ended_with_evidence"
    assert_control_invariants(lab.project)


def test_two_leads_race_to_launch_the_same_invocation(lab, tmp_path, sync):
    wid, out = assigned(lab, tmp_path, launch=False)
    printed = out["invocation_token"]  # dispatched without --launch: this credential was printed
    inv = out["invocation"]
    lab.script(R1, [touch(sync / "ready"), wait(sync / "go")])
    lab.script(R2, [touch(sync / "ready"), wait(sync / "go")])
    rev = str(lab.project.rev())
    racers = [spawn_aew(lab, "harness", "launch", inv, "--token", lab.project.token, "--expect-rev", rev)
              for _ in range(2)]
    results = [(p.wait(timeout=180), *p.communicate()) for p in racers]
    codes = sorted(r[0] for r in results)
    assert codes == [0, 3], results
    loser = next(r for r in results if r[0] == 3)
    assert json.loads(loser[2])["error"]["code"] == "STALE_REVISION"
    assert [r["run"] for r in inv_show(lab, inv)["runs"]] == [R1]
    assert not runlog.run_dir(lab.aew_root, R2).exists()
    # A third Lead that re-reads the revision is refused: run 1 may be live.
    assert lab.lead_res("harness", "launch", inv).error["code"] == "RUN_LIVE"
    # The credential printed at dispatch died at the first launch.
    res = lab.aew("whoami", "--invocation-token", printed)
    assert res.error["code"] == "STALE_AUTHORITY" and "rotated: R-INV-0001-1" in res.error["message"]
    (sync / "go").touch()
    assert lab.wait(R1)["status"] == "ended_without_evidence"
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------------------------------------- authority ends mid-run

def test_old_run_alive_then_rotation_then_old_process_immediately_submits(lab, tmp_path, sync):
    watchdog = hold(sync / "watchdog")  # a slow supervisor: it has not yet noticed the rotation
    wid, out = assigned(lab, tmp_path, [{"do": "write", "files": SUBTRACT_PATCH}, touch(sync / "ready1"),
                                        wait(sync / "go1"),
                                        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
                                        {"do": "aew", "args": ["whoami"]}, touch(sync / "done1")],
                        env=pause_env((WATCHDOG, watchdog)))
    inv = out["invocation"]
    lab.until(lambda: (sync / "ready1").exists(), what="run 1 ready")
    lab.script(R2, [wait(sync / "go2"), *IMPLEMENT])
    assert lab.lead("harness", "launch", inv, "--replace")["run"] == R2
    (sync / "go1").touch()
    lab.until(lambda: (sync / "done1").exists(), what="old run's attempts")
    submit, who = lab.step(R1, 3), lab.step(R1, 4)
    assert submit["exit"] == 3 and error_code(submit) == "STALE_AUTHORITY", submit
    assert who["exit"] == 3 and error_code(who) == "STALE_AUTHORITY"
    assert not evidence_of(lab, wid, R1)
    watchdog.unlink()
    done = lab.wait(R1)
    assert done["status"] == "terminated" and "superseded by R-INV-0001-2" in done["reason"]
    (sync / "go2").touch()
    assert lab.wait(R2)["status"] == "ended_with_evidence"
    assert_control_invariants(lab.project)


def test_rotation_while_the_old_runs_submission_is_in_flight(lab, tmp_path, sync):
    """The request passed the bridge's own check, then the credential rotated: the engine refuses it."""
    watchdog, in_flight = hold(sync / "watchdog"), hold(sync / "bridge")
    wid, out = assigned(lab, tmp_path, [{"do": "write", "files": SUBTRACT_PATCH},
                                        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
                                        touch(sync / "done1")],
                        env=pause_env((WATCHDOG, watchdog), (BRIDGE, in_flight)))
    lab.until(lambda: Path(str(in_flight) + ".reached").exists(), what="submission in flight")
    lab.script(R2, [wait(sync / "go2")])
    lab.lead("harness", "launch", out["invocation"], "--replace")
    in_flight.unlink()
    lab.until(lambda: (sync / "done1").exists(), what="old submission answered")
    submit = lab.step(R1, 1)
    assert submit["exit"] == 3 and error_code(submit) == "STALE_AUTHORITY", submit
    assert "rotated: R-INV-0001-2" in submit["stderr_json"]["error"]["message"]
    assert not evidence_of(lab, wid, R1)
    watchdog.unlink()
    (sync / "go2").touch()
    lab.wait(R1)
    lab.wait(R2)
    assert_control_invariants(lab.project)


def test_rotation_while_the_old_runs_check_is_running(lab, tmp_path, sync):
    """check run spans two lock sessions; the second re-verifies the credential before writing anything."""
    slow = hold(sync / "slow")
    checks = {"schema": "aew/checks/v1", "baseline_failures": [], "checks": {
        "unit": {"configured": True, "command": unit_check_command(), "cwd": ".", "timeout_s": 300},
        "slow": {"configured": True, "command": ["{python}", "-c", SLOW_CHECK, str(slow)], "cwd": ".",
                 "timeout_s": 300}}}
    (lab.aew_root / "policy/checks.yaml").write_text(dump_yaml(checks), encoding="utf-8", newline="\n")
    watchdog = hold(sync / "watchdog")
    wid, out = assigned(lab, tmp_path, [{"do": "check", "id": "slow"}, touch(sync / "done1")],
                        env=pause_env((WATCHDOG, watchdog)))
    lab.until(lambda: Path(str(slow) + ".reached").exists(), what="check running")
    lab.script(R2, [wait(sync / "go2")])
    lab.lead("harness", "launch", out["invocation"], "--replace")
    slow.unlink()
    lab.until(lambda: (sync / "done1").exists(), what="old check answered")
    assert error_code(lab.step(R1, 0)) == "STALE_AUTHORITY"
    assert not [e for e in evidence_of(lab, wid) if e["kind"] == "check_result"]
    assert not list((lab.aew_root / "evidence").rglob("*check-slow*"))  # not even its log
    watchdog.unlink()
    (sync / "go2").touch()
    lab.wait(R1)
    lab.wait(R2)
    assert_control_invariants(lab.project)


def test_rotation_racing_submissions_never_admits_evidence_after_revocation(lab, tmp_path, sync):
    """No pause points: whichever wins the control lock, the oracle (rules 5, 17, 18) holds."""
    wid, out = assigned(lab, tmp_path, [{"do": "write", "files": SUBTRACT_PATCH}, touch(sync / "ready1"),
                                        wait(sync / "go1"),
                                        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}])
    inv = out["invocation"]
    for n in range(1, 4):
        lab.until(lambda: (sync / f"ready{n}").exists(), what=f"run {n} ready")
        nxt = f"R-{inv}-{n + 1}"
        lab.script(nxt, [touch(sync / f"ready{n + 1}"), wait(sync / f"go{n + 1}"),
                         {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}])
        racer = spawn_aew(lab, "harness", "launch", inv, "--replace", "--token", lab.project.token,
                          "--expect-rev", str(lab.project.rev()))
        (sync / f"go{n}").touch()
        assert racer.wait(timeout=180) == 0, racer.communicate()
        lab.wait(f"R-{inv}-{n}")
        assert_control_invariants(lab.project)
    (sync / "go4").touch()
    lab.wait(f"R-{inv}-4")
    assert_control_invariants(lab.project)


def test_broker_alive_then_invocation_cancelled(lab, tmp_path, sync):
    watchdog = hold(sync / "watchdog")
    wid, out = assigned(lab, tmp_path, [{"do": "dump_env", "path": str(sync / "env")}, touch(sync / "ready"),
                                        wait(sync / "go"),
                                        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
                                        touch(sync / "done")],
                        env=pause_env((WATCHDOG, watchdog)))
    lab.until(lambda: (sync / "ready").exists(), what="ready")
    harness = [procs.Watch(p) for p in lab.record(R1)["harness_pids"]]
    lab.lead("invoke", "cancel", out["invocation"], "--reason", "the Lead changed course")
    (sync / "go").touch()
    lab.until(lambda: (sync / "done").exists(), what="attempt after cancel")
    assert error_code(lab.step(R1, 3)) == "STALE_AUTHORITY"
    watchdog.unlink()
    done = lab.wait(R1)
    assert done["status"] == "terminated" and "invocation cancelled" in done["reason"]
    agent_env = json.loads((sync / "env").read_text())
    lab.until(lambda: not any(w.alive() for w in harness), 30, "harness tree killed")
    with pytest.raises(Exception) as closed:  # the bridge is gone, whoever holds its coordinates
        bridge.call("whoami", {}, endpoint=agent_env[bridge.ENV_ENDPOINT], key=agent_env[bridge.ENV_KEY])
    assert getattr(closed.value, "code", None) == "STALE_AUTHORITY"
    assert not evidence_of(lab, wid, R1)
    assert_control_invariants(lab.project)


def test_broker_alive_then_takeover(lab, tmp_path, sync, monkeypatch):
    import aew.operator
    from aew.engine.api import Engine

    watchdog = hold(sync / "watchdog")
    wid, out = assigned(lab, tmp_path, [touch(sync / "ready"), wait(sync / "go"),
                                        {"do": "aew", "args": ["whoami"]}, touch(sync / "done")],
                        env=pause_env((WATCHDOG, watchdog)))
    lab.until(lambda: (sync / "ready").exists(), what="ready")
    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator (test)"})
    taken = Engine.discover(lab.root).lead_takeover(expect_rev=lab.project.rev(), reason="Lead unresponsive",
                                                    session_label="lead-b")
    lab.project.token = taken["token"]
    (sync / "go").touch()
    lab.until(lambda: (sync / "done").exists(), what="attempt after takeover")
    assert error_code(lab.step(R1, 2)) == "STALE_AUTHORITY"
    watchdog.unlink()
    done = lab.wait(R1)
    assert done["status"] == "terminated" and "invocation interrupted" in done["reason"]
    assert_control_invariants(lab.project)


def test_a_carried_run_keeps_working_across_a_cooperative_handoff(lab, tmp_path, sync):
    """Contrast with takeover: a handoff that carries the invocation re-scopes its credential; the run lives on."""
    wid = create_investigation(lab.project, tmp_path)
    lab.script("R-INV-0001-1", [touch(sync / "ready"), wait(sync / "go"),
                                {"do": "submit", "kind": "discovery_record", "meta": DISCOVERY}])
    out = lab.lead("work", "dispatch", wid, "--launch")
    lab.until(lambda: (sync / "ready").exists(), what="ready")
    offer = lab.lead("lead", "handoff", "offer", "--carry", out["invocation"])["offer"]
    accepted = lab.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(lab.project.rev()),
                      "--session-label", "lead-b")
    lab.project.token = accepted["token"]
    (sync / "go").touch()
    done = lab.wait("R-INV-0001-1")
    assert done["status"] == "ended_with_evidence", done
    assert_control_invariants(lab.project)


def test_run_dies_then_lead_relaunches_then_old_process_wakes_up(lab, tmp_path, sync):
    watchdog = hold(sync / "watchdog")  # after waking, the old supervisor is slow to notice it was superseded
    wid, out = assigned(lab, tmp_path, [{"do": "dump_env", "path": str(sync / "env1")}, touch(sync / "ready1"),
                                        wait(sync / "go1", 300),
                                        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
                                        touch(sync / "done1")],
                        env=pause_env((WATCHDOG, watchdog)))
    inv = out["invocation"]
    lab.until(lambda: (sync / "ready1").exists(), what="run 1 ready")
    supervisor = lab.record(R1)["supervisor_pid"]
    procs.suspend(supervisor)      # the old supervisor freezes (a sleeping machine, a stopped process)
    try:
        stale = {"AEW_RUN_STALE_S": "2"}
        lab.until(lambda: lab.ok("harness", "status", inv, env=stale)["runs"][0]["status"] == "lost",
                  what="run 1 lost")
        lab.script(R2, IMPLEMENT)
        assert lab.lead("harness", "launch", inv, env=stale)["run"] == R2
        assert lab.wait(R2)["status"] == "ended_with_evidence"
        (sync / "go1").touch()  # the old agent acts while its supervisor is still frozen
    finally:
        procs.resume(supervisor)
    lab.until(lambda: (sync / "done1").exists(), what="the woken run's submission answered")
    submit = lab.step(R1, 3)
    assert submit["exit"] == 3 and error_code(submit) == "STALE_AUTHORITY", submit
    assert "superseded by R-INV-0001-2" in submit["stderr_json"]["error"]["message"]
    watchdog.unlink()
    done = lab.wait(R1)
    assert done["status"] == "terminated" and "superseded by R-INV-0001-2" in done["reason"], done
    assert not evidence_of(lab, wid, R1)
    env1 = json.loads((sync / "env1").read_text())
    for endpoint in (env1[bridge.ENV_ENDPOINT], lab.record(R2)["bridge"]["endpoint"]):
        with pytest.raises(Exception) as refused:
            bridge.call("whoami", {}, endpoint=endpoint, key=env1[bridge.ENV_KEY])
        assert getattr(refused.value, "code", None) in {"STALE_AUTHORITY", "PERMISSION_DENIED"}
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------------------------------------- custody

def test_agent_cannot_print_or_read_the_raw_credential(lab, tmp_path, sync):
    """Custody properties 1-4: an authorized operation works; no credential in the agent's environment, in
    anything it can print through aew, or in any file it can reach, even with the Lead's token in the Lead's
    environment when it launched the run."""
    workspaces = tmp_path / ".aew-workspaces"
    steps = [{"do": "dump_env", "path": str(sync / "env")}, {"do": "aew", "args": ["whoami"]},
             {"do": "aew", "args": ["invoke", "show", "INV-0001"]}, {"do": "aew", "args": ["harness", "status"]},
             {"do": "aew", "args": ["context", "show", "INV-0001"]}, {"do": "aew", "args": ["lead", "show"]},
             {"do": "scan", "out": str(sync / "hits"), "roots": [str(lab.root), str(workspaces), str(sync)]},
             *IMPLEMENT]
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R1, steps)
    lead_env = {"AEW_LEAD_TOKEN": lab.project.token, "AEW_INVOCATION_TOKEN": "aew1.tk_0123456789abcdef." + "x" * 43}
    out = lab.ok("work", "assign", wid, "--launch", "--expect-rev", str(lab.project.rev()), env=lead_env)
    assert not contains_credential(json.dumps(out))
    assert lab.wait(R1)["status"] == "ended_with_evidence"
    env = json.loads((sync / "env").read_text())
    assert not contains_credential(json.dumps(env))
    assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN"} & set(env)
    for i in range(1, 6):
        step = lab.step(R1, i)
        assert step["exit"] == 0, step
        assert not contains_credential(step["stdout"] + step["stderr"])
    assert lab.step(R1, 6)["hits"] == []
    assert lab.record(R1)["credential_scan"] == {"clean": True, "files": []}
    assert_control_invariants(lab.project)


def test_model_controlled_child_processes_inherit_no_secret(lab, tmp_path, sync):
    secrets_in_lead_env = {"OPENAI_API_KEY": "sk-provider-secret-do-not-leak", "AEW_LEAD_TOKEN": lab.project.token}
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R1, [{"do": "child_env", "path": str(sync / "child"), "shell_path": str(sync / "shell")},
                    {"do": "read_parent_environ", "pid": "ppid"}])
    lab.ok("work", "assign", wid, "--launch", "--expect-rev", str(lab.project.rev()), env=secrets_in_lead_env)
    assert lab.wait(R1)["status"] == "ended_without_evidence"
    child = json.loads((sync / "child").read_text())
    shell = (sync / "shell").read_text()
    for blob in (json.dumps(child), shell):
        assert not contains_credential(blob)
        assert "sk-provider-secret-do-not-leak" not in blob and "AEW_LEAD_TOKEN" not in blob
    assert set(child) >= {"AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY", "AEW_RUN"}  # the bridge, and nothing more
    parent = lab.step(R1, 1)
    if sys.platform.startswith("linux"):  # the supervisor is non-dumpable: same-user processes cannot read it
        if os.geteuid() != 0:
            assert parent["readable"] is False, parent
        assert not parent.get("readable") or not (parent["has_credential"] or parent["has_lead_var"]), parent
    assert_control_invariants(lab.project)


def test_run_a_cannot_act_as_run_b(lab, tmp_path, sync):
    wid_b = create_investigation(lab.project, tmp_path, title="B's investigation")
    lab.script("R-INV-0001-1", [touch(sync / "readyB"), wait(sync / "goB"),
                                {"do": "submit", "kind": "discovery_record", "meta": DISCOVERY}])
    b = lab.lead("work", "dispatch", wid_b, "--launch")
    lab.until(lambda: (sync / "readyB").exists(), what="B ready")
    b_endpoint = lab.record("R-INV-0001-1")["bridge"]["endpoint"]
    report = f"---\nclaim: forged\nresult: pass\n---\nx\n"
    lab.script("R-INV-0002-1", [
        {"do": "bridge_payload", "request": {"op": "submit", "args": {"kind": "discovery_record", "text": report,
                                                                       "invocation": b["invocation"]}}},
        {"do": "bridge_payload", "request": {"op": "whoami", "args": {}, "run": "R-INV-0001-1"}},
        {"do": "bridge_raw", "op": "whoami", "args": {}, "endpoint": b_endpoint},
        {"do": "aew", "args": ["whoami"], "env": {"AEW_RUN": "R-INV-0001-1", "AEW_INVOCATION": b["invocation"],
                                                  "AEW_WORK_UNIT": wid_b}},
        {"do": "submit", "kind": "discovery_record", "meta": DISCOVERY},
        {"do": "bridge_payload", "raw": "not json"},
        {"do": "bridge_payload", "request": {"op": "lead.acquire", "args": {}}},
    ])
    wid_a = create_planned_ticket(lab.project, tmp_path, title="A's change")
    a = lab.lead("work", "assign", wid_a, "--launch")
    assert lab.wait("R-INV-0002-1")["status"] == "ended_without_evidence"
    step = lambda i: lab.step("R-INV-0002-1", i)  # noqa: E731
    assert step(0)["error"]["code"] == "USAGE" and step(1)["error"]["code"] == "USAGE"
    assert (step(2)["ok"], step(2)["code"]) == (False, "PERMISSION_DENIED")
    who = step(3)["stdout_json"]
    assert (who["invocation"], who["run"], who["work_unit"]) == (a["invocation"], "R-INV-0002-1", wid_a)
    assert error_code(step(4)) == "PERMISSION_DENIED"
    assert step(5)["error"]["code"] == "USAGE" and step(6)["error"]["code"] == "PERMISSION_DENIED"
    (sync / "goB").touch()
    assert lab.wait("R-INV-0001-1")["status"] == "ended_with_evidence"
    [record] = evidence_of(lab, wid_b)
    assert (record["producer"]["invocation"], record["producer"]["run"]) == (b["invocation"], "R-INV-0001-1")
    assert not evidence_of(lab, wid_a)
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------------------------------------- no inferred success

@pytest.mark.parametrize("exit_code, status", [(0, "ended_without_evidence"), (3, "crashed")])
def test_harness_exit_without_its_expected_output_moves_no_state(lab, tmp_path, exit_code, status):
    wid, out = assigned(lab, tmp_path, [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
                                        {"do": "exit", "code": exit_code}])
    inv = out["invocation"]
    before = lab.project.rev()
    token_before = inv_show(lab, inv)["runs"][0]["token_id"]
    done = lab.wait(R1)
    assert done["status"] == status, done
    assert len(done["evidence"]) == 1  # the check result is recorded; it is not the run's expected output
    assert lab.project.rev() == before  # nothing committed by the run's end
    unit, invocation = control(lab, wid), inv_show(lab, inv)
    assert unit["state"] == "RUNNING" and invocation["status"] == "active"
    assert invocation["runs"][0]["token_id"] == token_before  # not revoked or rotated by the harness
    lab.script(R2, [{"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}])
    assert lab.lead("harness", "launch", inv)["run"] == R2
    assert lab.wait(R2)["status"] == "ended_with_evidence"
    assert control(lab, wid)["state"] == "RUNNING"  # evidence waits for the Lead's ingest
    assert_control_invariants(lab.project)
