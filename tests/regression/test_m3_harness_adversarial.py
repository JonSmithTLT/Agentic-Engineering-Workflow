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
from aewflow import (
    DISCOVERY,
    SUBTRACT_PATCH,
    create_investigation,
    create_planned_ticket,
    sample_project,
    unit_check_command,
)
from conftest import IS_WINDOWS, clean_env, run_aew
from fake_harness import AGENT, IMPL_REPORT, HarnessLab, contains_credential, credential_hits, watch_agent_pid
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
    d.mkdir(exist_ok=True)  # HarnessLab already made it (a writable root for contained runs)
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
    printing = [] if (env or {}).get("AEW_LEAD_BROKER") else ["--print-credential"]  # no terminal here
    return subprocess.Popen([sys.executable, "-m", "aew", *printing, "-C", str(lab.root), *args],
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


def test_harness_wait_keeps_waiting_while_a_just_launched_run_may_still_start(lab, tmp_path):
    """Found by CI on PR #5 (Linux), in the test above: its launcher crashed right after handing over custody, and
    `aew harness wait` returned `unconfirmed` at once, because the supervisor had not yet written its first record.
    Launch treats such a run as possibly live for its first 30 s (a relaunch is refused, RUN_LIVE); `harness wait`
    must too, instead of telling the Lead the run never started."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R1, IMPLEMENT)
    held = hold(tmp_path / "supervisor-held")
    res = lab.lead_res("work", "assign", wid, "--launch", env={
        "AEW_FAULT": "harness.launch.after_handoff", **pause_env(("harness.supervisor.before_custody", held))})
    assert res.returncode == 86
    lab.until(lambda: Path(f"{held}.reached").exists(), what="the supervisor held before its first record")
    early = run_aew("-C", str(lab.root), "harness", "wait", R1, "--timeout", "3", env=lab.env, timeout=120)
    assert early.returncode == 0 and early.json["timed_out"], early.json  # possibly live: still waited on
    held.unlink()
    done = lab.wait(R1)
    assert done["status"] == "ended_with_evidence" and len(done["evidence"]) == 2
    assert_control_invariants(lab.project)


def test_a_run_is_never_reported_lost_before_its_first_heartbeat(lab, tmp_path):
    """Found by CI on PR #132 (Windows): the test two above saw `lost` for a run that then ended with evidence. The
    supervisor wrote its first `starting` record before its first heartbeat, and writing the record wakes every
    `harness wait`: a waiter woken into that gap saw a live record with no heartbeat, which reads as `lost`. A held
    run's first record must already have a heartbeat."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R1, IMPLEMENT)
    held = hold(tmp_path / "supervisor-held")
    res = lab.lead_res("work", "assign", wid, "--launch", env={
        "AEW_FAULT": "harness.launch.after_handoff", **pause_env(("harness.supervisor.after_custody_record", held))})
    assert res.returncode == 86
    lab.until(lambda: Path(f"{held}.reached").exists(), what="the supervisor held right after its first record")
    early = run_aew("-C", str(lab.root), "harness", "wait", R1, "--timeout", "3", env=lab.env, timeout=120)
    assert early.returncode == 0 and early.json["timed_out"], early.json  # held, alive and waited on: never `lost`
    held.unlink()
    done = lab.wait(R1)
    assert done["status"] == "ended_with_evidence" and len(done["evidence"]) == 2
    assert_control_invariants(lab.project)


def test_a_run_that_takes_long_to_end_is_not_reported_lost(lab, tmp_path):
    """Found by CI on main after PR #7 (Windows): `aew harness wait` reported a healthy run `lost`. Ending a run
    (stopping the harness, for up to 20 s; collecting; scanning its evidence and its directory) happened outside
    the watch loop, where nothing beat, so on a loaded machine the heartbeat went stale before the final record."""
    held = hold(tmp_path / "ending")
    assigned(lab, tmp_path, IMPLEMENT, env=pause_env(("harness.supervisor.finishing", held)))
    lab.until(lambda: Path(f"{held}.reached").exists(), what="the supervisor ending the run")
    # The wait outlasts the stale window, so a heartbeat that stopped while ending would be reported `lost`. The
    # window leaves 3 s of slack over the 1 s beat for a loaded machine (register E3: under coverage on 16 workers, a
    # 2 s window once saw a beat arrive late; raise test-side timeouts, never the product's).
    stale = {**lab.env, "AEW_RUN_STALE_S": "4"}
    early = run_aew("-C", str(lab.root), "harness", "wait", R1, "--timeout", "8", env=stale, timeout=120)
    assert early.returncode == 0 and early.json["timed_out"], early.json  # still ending, and visibly alive
    held.unlink()
    done = lab.wait(R1)
    assert done["status"] == "ended_with_evidence" and len(done["evidence"]) == 2
    assert_control_invariants(lab.project)


def test_a_start_that_wedges_after_custody_reads_lost_within_its_bound_and_never_runs(lab, tmp_path, sync):
    """Independent review of PR #147 (register E3): the starting heartbeat had no limit, so a supervisor wedged between
    its custody acknowledgement and `running` kept a single-run `harness wait` on `starting` until the wait's own
    timeout. The start now has a deadline (`AEW_RUN_START_S`, 300 s by default): its heartbeat stops there, so the run
    reads `lost` within the deadline plus the stale window, its bridge refuses the agent, and a start that comes back
    afterwards ends `launch_failed`, never `running`."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script(R1, [wait(sync / "go", 300), {"do": "aew", "args": ["whoami"]}, touch(sync / "asked"),
                    wait(sync / "never", 300)])
    held, ending = hold(tmp_path / "start-held"), hold(tmp_path / "ending")
    res = lab.lead_res("work", "assign", wid, "--launch", env={
        "AEW_FAULT": "harness.launch.after_handoff", "AEW_RUN_START_S": "3",
        **pause_env(("harness.supervisor.launched", held), ("harness.supervisor.finishing", ending))})
    assert res.returncode == 86
    lab.until(lambda: Path(f"{held}.reached").exists(), what="the supervisor wedged after launching the harness")
    # 3 s of start, then the 4 s stale window: well inside the wait's own 60 s, which must not be what ends it.
    stale = {**lab.env, "AEW_RUN_STALE_S": "4"}
    lost = run_aew("-C", str(lab.root), "harness", "wait", R1, "--timeout", "60", env=stale, timeout=180)
    assert lost.returncode == 0 and lost.json["status"] == "lost" and not lost.json["timed_out"], lost.json
    (sync / "go").touch()  # the agent, still alive under the wedged supervisor, tries to act
    lab.until(lambda: (sync / "asked").exists(), what="the agent's bridge call")
    who = lab.step(R1, 1)
    assert who["exit"] != 0 and error_code(who) == "HARNESS_LAUNCH_FAILED", who
    status = {"AEW_RUN_STALE_S": "4"}
    assert lab.ok("harness", "status", "INV-0001", env=status)["runs"][0]["status"] == "lost"
    held.unlink()  # the start comes back: it ends the run instead of running it, and does not beat again meanwhile
    lab.until(lambda: Path(f"{ending}.reached").exists(), what="the abandoned start ending")
    assert lab.ok("harness", "status", "INV-0001", env=status)["runs"][0]["status"] == "lost"
    ending.unlink()
    record = lab.until(lambda: (r := lab.record(R1)).get("status") == "launch_failed" and r, what="launch_failed")
    assert "the start took longer than 3s" in record["reason"], record
    assert "started" not in [e["event"] for e in record["timeline"]], record["timeline"]
    lab.script(R2, IMPLEMENT)
    assert lab.lead("harness", "launch", "INV-0001")["run"] == R2  # neither lost nor launch_failed is live
    assert lab.wait(R2)["status"] == "ended_with_evidence"
    assert_control_invariants(lab.project)


def test_supervisor_crash_takes_the_whole_harness_tree_with_it(lab, tmp_path, sync):
    wid, out = assigned(lab, tmp_path, [{"do": "spawn_orphan", "pidfile": str(sync / "orphan")},
                                        {"do": "pid", "path": str(sync / "agent")}, touch(sync / "ready"),
                                        wait(sync / "never", 300)])
    lab.until(lambda: (sync / "ready").exists(), what="agent ready")
    agent, orphan = (watch_agent_pid(lab, R1, int((sync / n).read_text())) for n in ("agent", "orphan"))
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
    lab.project.pin_policy()
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
        lab.until(lambda n=n: (sync / f"ready{n}").exists(), what=f"run {n} ready")
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
    if contained(lab, R1):  # M4-B: the supervisor is outside the run's PID namespace; the parent is the sandbox's
        assert not parent.get("readable") or not (parent["has_credential"] or parent["has_lead_var"]), parent
    elif sys.platform.startswith("linux"):  # the supervisor is non-dumpable: same-user processes cannot read it
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
    report = "---\nclaim: forged\nresult: pass\n---\nx\n"
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
    # Uncontained, B's socket is reachable and refuses A's key. Contained (M4-B), B's socket lies in a /tmp this run
    # cannot see, so there is nothing to connect to.
    want = "STALE_AUTHORITY" if contained(lab, "R-INV-0002-1") else "PERMISSION_DENIED"
    assert (step(2)["ok"], step(2)["code"]) == (False, want), step(2)
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


# ---------------------------------------------------------------------------------------------- the brief's attacks
# M3 brief, "Security and authority review": each attack is a permanent regression here or in the named test.

REVIEW_PASS = {"claim": "independent review", "review": {"independence": "R1", "disposition": "pass", "findings": [],
                                                          "resolved_findings": []}}
TAMPER = {"calc/core.py": "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return 0  # 'fixed'\n"}


def implemented(lab, tmp_path):
    """A Ticket whose implementer run reported, moved on to REVIEW_PENDING (the implementer is retired)."""
    wid, out = assigned(lab, tmp_path, IMPLEMENT)
    assert lab.wait(R1)["status"] == "ended_with_evidence"
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    return wid, out


def contained(lab, run: str) -> bool:
    """The run had OS filesystem containment (Linux, M4-B): a write outside its roots fails where it is made."""
    return (lab.record(run).get("containment") or {}).get("filesystem") == "os_readonly_roots"


def details(step: dict) -> dict:
    return ((step.get("stderr_json") or {}).get("error") or {}).get("details") or {}


def test_a_reviewer_cannot_mutate_source(lab, tmp_path):
    """Attack 5 (M3-B6): a reviewer shares the implementer's live workspace. Its edit is refused where it is made,
    named and attributed, and no reviewer can then be dispatched for code no implementer reported."""
    wid, _ = implemented(lab, tmp_path)
    lab.script("R-INV-0002-1", [{"do": "write", "files": TAMPER},
                                {"do": "submit", "kind": "review", "meta": REVIEW_PASS}])
    run = lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")["launch"]["run"]
    if contained(lab, run):  # M4-B: the reviewer's source is read-only, so the edit never happens
        assert lab.wait(run)["status"] == "ended_with_evidence"  # a review of the unchanged code is a valid review
        assert lab.step(run, 0) == {"wrote": [], "refused": {"calc/core.py": "EROFS"}}
        assert lab.lead_res("invoke", "create", wid, "--role", "reviewer").returncode == 0
        assert_control_invariants(lab.project)
        return
    assert lab.wait(run)["status"] == "ended_without_evidence"
    refused = lab.step(run, 1)
    assert error_code(refused) == "WORKSPACE_MUTATED" and details(refused)["changed"] == ["calc/core.py"]
    assert not [e for e in evidence_of(lab, wid) if e["kind"] == "review"]
    again = lab.lead_res("invoke", "create", wid, "--role", "reviewer")
    assert again.error["code"] == "WORKSPACE_MUTATED" and again.error["details"]["changed"] == ["calc/core.py"]
    assert control(lab, wid)["state"] == "REVIEW_PENDING"
    assert_control_invariants(lab.project)


def test_a_verifier_cannot_mutate_source(lab, tmp_path):
    """M3-B6 for verification: an edited workspace is refused before a check runs on it and at submission."""
    from aewflow import review
    wid, _ = implemented(lab, tmp_path)
    lab.project.lead("review", "ingest", wid, "--evidence", review(lab.project, wid))
    lab.project.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    verification = {"claim": "verified", "verification": {"scope": "ticket", "claims": [
        {"type": "goal_backwards", "claim": "x", "result": "pass", "checks": []},
        {"type": "contract", "claim": "y", "result": "pass", "checks": []}]}}
    lab.script("R-INV-0003-1", [{"do": "write", "files": TAMPER}, {"do": "check", "id": "unit"},
                                {"do": "submit", "kind": "verification", "meta": verification}])
    run = lab.lead("invoke", "create", wid, "--role", "verifier", "--launch")["launch"]["run"]
    if contained(lab, run):  # M4-B: the verifier's source is read-only; its check and verification are of intact code
        assert lab.wait(run)["status"] == "ended_with_evidence"
        assert lab.step(run, 0) == {"wrote": [], "refused": {"calc/core.py": "EROFS"}}
        check = next(e for e in evidence_of(lab, wid, run) if e["kind"] == "check_result")
        assert check["method"]["containment"] == "os_readonly_roots" and check["check"]["mutated_inputs"] is False
        assert_control_invariants(lab.project)
        return
    assert lab.wait(run)["status"] == "ended_without_evidence"
    for i in (1, 2):
        assert error_code(lab.step(run, i)) == "WORKSPACE_MUTATED", lab.step(run, i)
    assert not [e for e in evidence_of(lab, wid, run)]  # not even a check result
    assert lab.lead_res("invoke", "create", wid, "--role", "verifier").error["code"] == "WORKSPACE_MUTATED"
    assert_control_invariants(lab.project)


def test_the_retired_implementers_run_stops_when_review_begins(lab, tmp_path, sync):
    """Attack 2 and the M3-B6 companion: once the Lead moves a Ticket to review, the implementer's invocation is
    complete; a run still alive loses its authority, is stopped, and its invocation cannot be relaunched."""
    wid, out = assigned(lab, tmp_path, [*IMPLEMENT, touch(sync / "reported"), wait(sync / "never", 300)])
    lab.until(lambda: (sync / "reported").exists(), what="the implementer reported")
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    done = lab.wait(R1)
    assert done["status"] == "terminated" and "invocation completed" in done["reason"], done
    assert inv_show(lab, out["invocation"])["status"] == "completed"
    assert lab.lead_res("harness", "launch", out["invocation"]).error["code"] == "ILLEGAL_TRANSITION"
    assert_control_invariants(lab.project)


def test_a_single_run_wait_returns_the_runs_own_end_not_its_invocations(lab, tmp_path, sync):
    """Found by CI (nightly 2026-10-06, Linux; then Windows on `main`, register E3): the test above saw the retired
    implementer's run still `running` from a `harness wait` that had returned. The invocation was already completed in
    control state, and the wait's control lane (ADR-0012 D5, `--any`'s) ended the single-run wait before the supervisor
    had written the run's end. Held right there, the single-run wait keeps waiting; `--any` still ends at once."""
    held = hold(tmp_path / "ending")
    wid, _ = assigned(lab, tmp_path, [*IMPLEMENT, touch(sync / "reported"), wait(sync / "never", 300)],
                      env=pause_env(("harness.supervisor.finishing", held)))
    lab.until(lambda: (sync / "reported").exists(), what="the implementer reported")
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    lab.until(lambda: Path(f"{held}.reached").exists(), what="the supervisor ending the retired run")
    early = run_aew("-C", str(lab.root), "harness", "wait", R1, "--timeout", "3", env=lab.env, timeout=120)
    assert early.returncode == 0 and early.json["timed_out"] and early.json["status"] == "running", early.json
    anyway = lab.ok("harness", "wait", R1, "--any", "--timeout", "3")  # the control lane, where it is asked for
    assert not anyway["timed_out"] and anyway["ended_by"]["lane"] == "control", anyway
    held.unlink()
    done = lab.wait(R1)
    assert done["status"] == "terminated" and "invocation completed" in done["reason"], done
    assert "ended_by" not in done, done
    assert_control_invariants(lab.project)


def test_an_agent_in_the_wrong_worktree_still_acts_only_for_its_own_workspace(lab, tmp_path):
    """Attack 3: the agent works from the authoritative checkout. Its identity, checks and evidence stay bound to its
    invocation's own workspace (the bridge ignores where the agent stands); its edit of the authoritative checkout
    is in no evidence."""
    root = str(lab.root)
    wid, out = assigned(lab, tmp_path, [
        {"do": "write", "files": {str(lab.root / "calc" / "core.py"): TAMPER["calc/core.py"]}},
        {"do": "write", "files": SUBTRACT_PATCH},
        {"do": "aew", "args": ["-C", root, "whoami"]},
        {"do": "aew", "args": ["-C", root, "check", "run", "unit"]}])
    assert lab.wait(R1)["status"] == "ended_without_evidence"
    workspace = out["workspace"]["path"]
    assert lab.step(R1, 2)["stdout_json"]["workspace"] == workspace
    check = lab.step(R1, 3)["stdout_json"]
    assert check["result"] == "pass" and check["evaluated_snapshot"]["workspace_id"] == out["workspace"]["id"]
    from aew.engine.api import Engine
    engine = Engine.discover(lab.root)
    assert check["evaluated_snapshot"]["relevant_inputs_fingerprint"] == \
        engine.snapshot_of(workspace, out["workspace"]["id"])["relevant_inputs_fingerprint"]
    assert check["evaluated_snapshot"]["relevant_inputs_fingerprint"] != \
        engine.snapshot_of(lab.root, "authoritative")["relevant_inputs_fingerprint"]
    assert_control_invariants(lab.project)


def test_evidence_cannot_claim_another_invocation_run_role_or_credential(lab, tmp_path):
    """Attack 4: a submission naming another invocation, run, role, credential or execution profile is refused;
    identity is recorded by the engine from the run's own credential."""
    forged = [{"invocation": "INV-0009"}, {"run": "R-INV-0009-1"}, {"role": "reviewer"},
              {"credential": "tk_0123456789abcdef"}, {"execution_profile": {"model": "cheaper"}}]
    steps = [{"do": "submit_raw", "kind": "implementation_report",
              "text": "---\nclaim: forged\nresult: pass\nproducer: " + json.dumps(p) + "\n---\nx\n"} for p in forged]
    wid, out = assigned(lab, tmp_path, [*steps, *IMPLEMENT])
    assert lab.wait(R1)["status"] == "ended_with_evidence"
    for i in range(len(forged)):
        assert error_code(lab.step(R1, i)) == "VALIDATION_FAILED", lab.step(R1, i)
    [report] = [e for e in evidence_of(lab, wid) if e["kind"] == "implementation_report"]
    assert (report["producer"]["invocation"], report["producer"]["run"], report["producer"]["role"]) == \
        (out["invocation"], R1, "implementer")
    assert_control_invariants(lab.project)


def test_an_investigator_cannot_obtain_implementer_authority(lab, tmp_path):
    """Attack 6: an investigator (read-only observation) cannot submit implementation evidence, dispatch an
    implementer, or mint any credential; its operations are the investigator's only."""
    wid = create_investigation(lab.project, tmp_path)
    target = create_planned_ticket(lab.project, tmp_path, title="The change it would like to make")
    rev = str(lab.project.rev())
    lab.script(R1, [
        {"do": "aew", "args": ["whoami"]},
        {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT},
        {"do": "aew", "args": ["work", "assign", target, "--expect-rev", rev]},
        {"do": "aew", "args": ["invoke", "create", target, "--role", "implementer", "--expect-rev", rev]},
        {"do": "aew", "args": ["lead", "acquire", "--expect-rev", rev]},
        {"do": "submit", "kind": "discovery_record", "meta": DISCOVERY}])
    run = lab.lead("work", "dispatch", wid, "--launch")["launch"]["run"]
    assert lab.wait(run)["status"] == "ended_with_evidence"
    who = lab.step(run, 0)["stdout_json"]
    assert who["role"] == "investigator" and "submit.implementation_report" not in who["operations"]
    # `lead acquire` issues a credential and the agent has no terminal: refused before anything is issued (ADR-0009)
    assert [error_code(lab.step(run, i)) for i in range(1, 5)] == ["PERMISSION_DENIED", "USAGE", "USAGE", "USAGE"]
    assert control(lab, target)["state"] == "READY" and not control(lab, target).get("implementer_invocation")
    assert [e["kind"] for e in evidence_of(lab, wid)] == ["discovery_record"]
    assert_control_invariants(lab.project)


def test_a_lead_acting_on_stale_conversational_state_is_refused(lab, tmp_path, sync):
    """Attack 8: a Lead harness session resumed from an old conversation acts on a revision it remembers; AEW
    refuses (compare-and-swap), and a relaunched run is rebuilt from durable state, not from its old session."""
    wid = create_planned_ticket(lab.project, tmp_path)
    remembered = lab.project.rev()
    lab.project.lead("checkpoint", "--next", "the state moved on")
    script, transcript = tmp_path / "lead-script.json", tmp_path / "lead.jsonl"
    script.write_text(json.dumps([{"do": "aew", "args": ["work", "assign", wid, "--launch", "--expect-rev",
                                                         str(remembered)]}]), encoding="utf-8")
    res = run_aew("-C", str(lab.root), "lead", "session", "--", sys.executable, str(AGENT), "--script", str(script),
                  "--transcript", str(transcript), env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token}, timeout=600)
    assert res.returncode == 0, res.stderr
    [step] = [json.loads(line)["result"] for line in transcript.read_text(encoding="utf-8").splitlines()]
    assert error_code(step) == "STALE_REVISION", step
    assert control(lab, wid)["state"] == "READY" and lab.project.rev() == remembered + 1
    assert_control_invariants(lab.project)


def test_model_and_role_configuration_are_pinned_at_dispatch(lab, tmp_path):
    """Attack 9: editing the execution policy after dispatch changes nothing for the invocation: every run uses its
    pinned profile, and a relaunch accepts no model or role option."""
    wid, out = assigned(lab, tmp_path, [{"do": "exit", "code": 0}])
    lab.wait(R1)
    pinned = inv_show(lab, out["invocation"])["execution_profile"]
    policy = lab.aew_root / "policy" / "execution.yaml"
    policy.write_text(policy.read_text(encoding="utf-8").replace("fake-model", "cheaper-model"), encoding="utf-8")
    lab.project.adopt_policy()
    assert lab.aew("harness", "launch", out["invocation"], "--model", "fakeprov/cheaper-model", "--token",
                   lab.project.token, "--expect-rev", str(lab.project.rev())).returncode != 0
    lab.script(R2, [{"do": "aew", "args": ["whoami"]}])
    lab.lead("harness", "launch", out["invocation"])
    lab.wait(R2)
    assert lab.step(R2, 0)["stdout_json"]["execution_profile"] == pinned
    assert lab.record(R2)["execution_profile"] == pinned and pinned["model"] == "fake-model"
    assert_control_invariants(lab.project)


def test_forged_run_records_and_harness_success_move_nothing(lab, tmp_path):
    """Attacks 10 and 11: a later run forges the finished earlier run's record (status, evidence) and a record for a
    run that never existed, then exits successfully. Run records are telemetry that model-controlled processes can
    write: evidence is always read from the evidence store, a run exists only in control state, no gate reads a
    record, and the Ticket cannot advance."""
    forged = json.dumps({"schema": "aew/harness-run/v1", "run": R1, "status": "ended_with_evidence",
                         "evidence": ["INV-0001-impl-1"], "reason": "forged", "ended_at": "2026-01-01T00:00:00Z"})
    wid, out = assigned(lab, tmp_path, [{"do": "exit", "code": 0}])
    assert lab.wait(R1)["status"] == "ended_without_evidence"
    lab.script(R2, [{"do": "write", "files": {str(runlog.run_dir(lab.aew_root, R1) / "run.json"): forged,
                                              str(runlog.run_dir(lab.aew_root, "R-INV-0007-1") / "run.json"): forged}},
                    {"do": "exit", "code": 0}])
    lab.lead("harness", "launch", out["invocation"])
    assert lab.wait(R2)["status"] == "ended_without_evidence"
    if contained(lab, R2):  # M4-B: other runs' directories are hidden; the forgery lands in a private tmpfs
        assert lab.record(R1)["status"] == "ended_without_evidence"
        assert not runlog.run_dir(lab.aew_root, "R-INV-0007-1").exists()
    else:
        assert lab.record(R1)["status"] == "ended_with_evidence"  # the forgery is on disk ...
    runs = lab.ok("harness", "status")["runs"]
    assert [r["run"] for r in runs] == [R1, R2]  # ... a run that never existed is not listed ...
    assert runs[0]["evidence"] == [] and lab.ok("harness", "wait", R1)["evidence"] == []  # ... evidence: the store
    assert lab.lead_res("work", "transition", wid, "--to", "REVIEW_PENDING").error["code"] == "GATE_UNSATISFIED"
    assert lab.lead_res("review", "ingest", wid, "--evidence", "INV-0001-impl-1").error["code"] in {
        "NOT_FOUND", "ILLEGAL_TRANSITION"}
    assert control(lab, wid)["state"] == "RUNNING"
    assert_control_invariants(lab.project)
