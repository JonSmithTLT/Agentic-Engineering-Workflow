"""Adapter-neutral harness conformance (ADR-0009; docs/implementation/harness-conformance.md).

What every harness adapter must do, whatever the harness, stated as scenarios over one action
vocabulary (the fake agent's steps: write, aew, check, submit, submit_raw, dump_env, child_env, scan,
spawn_orphan, touch, wait_file, pid, cwd, model_step, exit). A ``Driver`` makes one harness perform them:

* ``FakeDriver`` (CI): the fake harness runs them as one scripted agent process.
* ``FakeOpenCodeDriver`` (CI): the real OpenCode adapter against a fake V2 server whose "model" runs each
  step as a tool call in the session's shell environment (``fake_opencode.py``).
* ``OpenCodeDriver`` (live lane, ``tests/live``): the real OpenCode 2.0.18 server; each step runs through
  the session's own shell endpoint, and ``model_step`` is a real prompt to a real (free) model.

Every scenario asserts AEW-side outcomes only: evidence, state, run records, files, processes. A scenario
needing something a driver cannot do (``capabilities``) is skipped for that driver, visibly.
"""

from __future__ import annotations

import calendar
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import fake_opencode
from aewflow import DISCOVERY, SUBTRACT_PATCH, create_investigation, create_planned_ticket, sample_project
from fake_harness import IMPL_REPORT, POLICY, SCRIPTS_ENV, HarnessLab, contains_credential, credential_hits
from invariants import assert_control_invariants

from aew.harness import bridge, procs, runlog
from aew.knowledge import evidence as E

PROVIDER_SECRET = "sk-provider-secret-must-not-reach-the-agent"


class Driver:
    """How the scenarios make one harness act. Subclass for each adapter."""

    name = "abstract"
    capabilities: frozenset[str] = frozenset()

    def create_lab(self, tmp_path: Path) -> HarnessLab:
        raise NotImplementedError

    def script(self, lab: HarnessLab, key: str, steps: list[dict[str, Any]], *,
               effective: list[dict[str, Any]] | None = None, health: str | None = None) -> None:
        raise NotImplementedError

    def state_dir(self, lab: HarnessLab, run: str) -> Path:
        """Where the harness keeps a run's private state (sessions, transcripts, databases)."""
        raise NotImplementedError

    def sessions(self, lab: HarnessLab, run: str) -> set[str]:
        """The sessions a run's harness state holds: the run's own, and nothing of any other run."""
        raise NotImplementedError


class FakeDriver(Driver):
    name = "fake"
    capabilities = frozenset({"effective_override", "incompatible"})

    def create_lab(self, tmp_path: Path) -> HarnessLab:
        return HarnessLab.create(sample_project(tmp_path), tmp_path, extra_env={"OPENAI_API_KEY": PROVIDER_SECRET})

    def script(self, lab, key, steps, *, effective=None, health=None):
        spec: Any = steps if effective is None and health is None else {"steps": steps, "effective": effective,
                                                                         "health": health}
        lab.script(key, spec)

    def state_dir(self, lab, run):
        return runlog.run_dir(lab.aew_root, run) / "harness"

    def sessions(self, lab, run):
        d = self.state_dir(lab, run) / "sessions"
        return {p.name for p in d.iterdir()} if d.is_dir() else set()


class FakeOpenCodeDriver(Driver):
    """The real OpenCode adapter against the fake V2 server. The execution policy names the provider secret as a
    provider variable, so the *server* holds it: the scenarios prove the agent's shell still does not."""

    name = "opencode-fake"
    capabilities = frozenset({"effective_override", "incompatible"})

    def create_lab(self, tmp_path: Path) -> HarnessLab:
        policy = {**POLICY, "harness": "opencode", "provider_env": ["OPENAI_API_KEY"]}
        lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy,
                                extra_env={"OPENAI_API_KEY": PROVIDER_SECRET})
        launcher = fake_opencode.write_launcher(tmp_path / "fake-opencode", Path(lab.env[SCRIPTS_ENV]))
        lab.env["AEW_OPENCODE_BIN"] = str(launcher)
        return lab

    def script(self, lab, key, steps, *, effective=None, health=None):
        FakeDriver.script(self, lab, key, steps, effective=effective, health=health)  # the same script files

    def state_dir(self, lab, run):
        return runlog.run_dir(lab.aew_root, run) / "harness"

    def sessions(self, lab, run):
        db = self.state_dir(lab, run) / "xdg-data" / "opencode" / "fake-db.json"
        return set(json.loads(db.read_text(encoding="utf-8"))) if db.exists() else set()


@dataclass
class Scenario:
    name: str
    fn: Callable[..., None]
    needs: frozenset[str] = frozenset()


SCENARIOS: list[Scenario] = []


def scenario(*needs: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    def register(fn: Callable[..., None]) -> Callable[..., None]:
        SCENARIOS.append(Scenario(fn.__name__, fn, frozenset(needs)))
        return fn
    return register


def run_scenario(sc: Scenario, driver: Driver, tmp_path: Path) -> None:
    missing = sc.needs - driver.capabilities
    if missing:
        pytest.skip(f"{driver.name} cannot drive {sorted(missing)}")
    lab = driver.create_lab(tmp_path)
    try:
        sc.fn(lab, driver, tmp_path)
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


# ---------------------------------------------------------------------------------------------- helpers

IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]


def sync_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sync"
    d.mkdir(exist_ok=True)
    return d


def launch_ticket(lab: HarnessLab, driver: Driver, tmp_path: Path, steps: list[dict[str, Any]], **kw: Any):
    """A planned Ticket assigned with --launch; its first run performs ``steps``."""
    wid = create_planned_ticket(lab.project, tmp_path)
    driver.script(lab, "R-INV-0001-1", steps, **kw)
    out = lab.lead("work", "assign", wid, "--launch")
    return wid, out["invocation"], out["launch"]["run"]


def supervisor_gone(record: dict[str, Any]) -> bool:
    """The run's supervisor has exited (checked by start time: pids are reused)."""
    custody = calendar.timegm(time.strptime(record["custody_at"], "%Y-%m-%dT%H:%M:%SZ"))
    return not procs.same_process(record.get("supervisor_pid"), custody)


def evidence_of(lab: HarnessLab, wid: str, run: str | None = None) -> list[dict[str, Any]]:
    records, problems = E.scan(lab.aew_root, wid)
    assert not problems, problems
    return [e for e in records if run is None or e["producer"].get("run") == run]


def code_of(step: dict[str, Any]) -> str | None:
    return ((step.get("stderr_json") or {}).get("error") or {}).get("code")


# ---------------------------------------------------------------------------------------------- scenarios

@scenario()
def authorized_operations_act_through_the_bridge(lab, driver, tmp_path):
    """Custody 1 + correlation: whoami/check/submit work with no credential; everything is attributed."""
    wid, inv, run = launch_ticket(lab, driver, tmp_path, [*IMPLEMENT, {"do": "aew", "args": ["whoami"]}])
    done = lab.wait(run)
    assert done["status"] == "ended_with_evidence", lab.record(run)
    who = lab.step(run, 3)["stdout_json"]
    assert (who["invocation"], who["run"], who["role"]) == (inv, run, "implementer")
    record = lab.record(run)
    assert record["launch"].get("session") and record["execution_profile"]["model"] == who["execution_profile"]["model"]
    for ev in evidence_of(lab, wid, run):
        assert ev["producer"]["execution_profile"] == who["execution_profile"]
        assert ev["producer"]["credential"] == lab.ok("invoke", "show", inv)["runs"][0]["token_id"]
    assert_control_invariants(lab.project)


@scenario()
def agent_processes_receive_only_the_curated_environment(lab, driver, tmp_path):
    """Custody 2-3: the agent, a child process and a shell see the bridge and nothing secret."""
    sync = sync_dir(tmp_path)
    lab.env["AEW_LEAD_TOKEN"] = lab.project.token  # the Lead's own shell holds its credential
    _, _, run = launch_ticket(lab, driver, tmp_path, [
        {"do": "dump_env", "path": str(sync / "env")},
        {"do": "child_env", "path": str(sync / "child"), "shell_path": str(sync / "shell")}])
    lab.wait(run)
    env, child = json.loads((sync / "env").read_text()), json.loads((sync / "child").read_text())
    shell = (sync / "shell").read_text()
    for blob in (json.dumps(env), json.dumps(child), shell):
        assert not contains_credential(blob) and PROVIDER_SECRET not in blob
    for e in (env, child):
        assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "OPENAI_API_KEY", "AEW_HARNESS_ADAPTERS"} & set(e)
        assert {"AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY", "AEW_RUN"} <= set(e)


@scenario()
def no_credential_in_any_file_the_run_leaves(lab, driver, tmp_path):
    """Custody 4: harness state (databases, transcripts), run records, packs, workspace: no credential."""
    sync = sync_dir(tmp_path)
    _, inv, run = launch_ticket(lab, driver, tmp_path, [
        {"do": "aew", "args": ["whoami"]}, {"do": "aew", "args": ["invoke", "show", "INV-0001"]},
        {"do": "aew", "args": ["context", "show", "INV-0001"]},
        {"do": "scan", "out": str(sync / "hits"), "roots": [str(lab.root), str(tmp_path / ".aew-workspaces")]},
        *IMPLEMENT])
    lab.wait(run)
    assert lab.step(run, 3)["hits"] == []
    assert lab.record(run)["credential_scan"] == {"clean": True, "files": []}
    assert not credential_hits(driver.state_dir(lab, run), runlog.run_dir(lab.aew_root, run), lab.aew_root)


@scenario()
def rotation_leaves_the_old_run_without_authority(lab, driver, tmp_path):
    """Custody 5: after a relaunch the old run's bridge refuses, even when reached with its own key."""
    sync = sync_dir(tmp_path)
    wid, inv, run = launch_ticket(lab, driver, tmp_path, [
        {"do": "dump_env", "path": str(sync / "env1")}, {"do": "touch", "path": str(sync / "ready")},
        {"do": "wait_file", "path": str(sync / "never"), "timeout": 300}])
    lab.until(lambda: (sync / "ready").exists(), what="run 1 ready")
    driver.script(lab, "R-INV-0001-2", IMPLEMENT)
    lab.lead("harness", "launch", inv, "--replace")
    old = json.loads((sync / "env1").read_text())
    with pytest.raises(Exception) as refused:
        bridge.call("whoami", {}, endpoint=old[bridge.ENV_ENDPOINT], key=old[bridge.ENV_KEY])
    assert getattr(refused.value, "code", None) == "STALE_AUTHORITY"
    assert lab.wait(run)["status"] == "terminated"
    assert lab.wait("R-INV-0001-2")["status"] == "ended_with_evidence"
    assert not evidence_of(lab, wid, run)
    assert_control_invariants(lab.project)


@scenario()
def harness_success_without_evidence_moves_no_state(lab, driver, tmp_path):
    wid, inv, run = launch_ticket(lab, driver, tmp_path, [{"do": "write", "files": SUBTRACT_PATCH},
                                                          {"do": "exit", "code": 0}])
    rev = lab.project.rev()
    done = lab.wait(run)
    assert done["status"] == "ended_without_evidence"
    assert lab.project.rev() == rev and lab.ok("invoke", "show", inv)["status"] == "active"
    assert lab.ok("work", "show", wid)["control"]["state"] == "ASSIGNED"


@scenario()
def malformed_output_is_refused_and_moves_no_state(lab, driver, tmp_path):
    wid, inv, run = launch_ticket(lab, driver, tmp_path, [
        {"do": "submit_raw", "kind": "implementation_report", "text": "no frontmatter at all\n"},
        {"do": "submit_raw", "kind": "implementation_report",
         "text": "---\nclaim: done\nresult: pass\nstate: DONE\n---\nforging a transition\n"},
        {"do": "submit", "kind": "review", "meta": {"claim": "self review", "review": {
            "independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}}])
    rev = lab.project.rev()
    assert lab.wait(run)["status"] == "ended_without_evidence"
    assert [code_of(lab.step(run, i)) for i in range(3)] == ["VALIDATION_FAILED", "PERMISSION_DENIED",
                                                              "PERMISSION_DENIED"]
    assert not evidence_of(lab, wid) and lab.project.rev() == rev


@scenario()
def a_crashing_harness_moves_no_state(lab, driver, tmp_path):
    wid, inv, run = launch_ticket(lab, driver, tmp_path, [{"do": "exit", "code": 7}])
    rev = lab.project.rev()
    assert lab.wait(run)["status"] == "crashed"
    assert lab.project.rev() == rev and lab.ok("invoke", "show", inv)["status"] == "active"


@scenario()
def stopping_a_run_ends_every_process_it_started(lab, driver, tmp_path):
    sync = sync_dir(tmp_path)
    _, inv, run = launch_ticket(lab, driver, tmp_path, [  # "agent": the process running the harness's current step
        {"do": "spawn_orphan", "pidfile": str(sync / "orphan")},
        {"do": "wait_file", "path": str(sync / "never"), "timeout": 300, "pidfile": str(sync / "agent"),
         "ready": str(sync / "ready")}])
    lab.until(lambda: (sync / "ready").exists(), what="ready")
    watches = [procs.Watch(int((sync / n).read_text())) for n in ("orphan", "agent")]
    assert all(w.alive() for w in watches)
    lab.ok("harness", "stop", run, "--reason", "conformance", "--token", lab.project.token)
    assert lab.wait(run)["status"] == "terminated"
    lab.until(lambda: not any(w.alive() for w in watches), 30, "every harness process gone")


@scenario()
def repeated_runs_start_and_end_cleanly_with_private_state(lab, driver, tmp_path):
    """Startup/teardown under repeated runs: each run its own session and state; nothing survives a run."""
    wid, inv, run = launch_ticket(lab, driver, tmp_path, [{"do": "exit", "code": 0}])
    runs = [run]
    lab.wait(run)
    for n in (2, 3):
        driver.script(lab, f"R-INV-0001-{n}", [{"do": "exit", "code": 0}])
        runs.append(lab.lead("harness", "launch", inv)["run"])
        lab.wait(runs[-1])
    records = [lab.record(r) for r in runs]
    assert all(r["status"] == "ended_without_evidence" for r in records)
    sessions = [r["launch"]["session"] for r in records]
    assert len(set(sessions)) == 3
    for r in runs:
        assert driver.sessions(lab, r) == {lab.record(r)["launch"]["session"]}  # its own session only
        assert Path(driver.state_dir(lab, r)).resolve().is_relative_to(runlog.run_dir(lab.aew_root, r).resolve())
    for rec in records:
        lab.until(lambda rec=rec: supervisor_gone(rec), 30, "every supervisor to exit")
        started = calendar.timegm(time.strptime(rec["started_at"], "%Y-%m-%dT%H:%M:%SZ"))
        for pid in rec["harness_pids"]:  # no harness process (a server, an agent) outlives its run
            lab.until(lambda pid=pid: not procs.same_process(pid, started), 30, f"harness process {pid} to exit")


@scenario()
def a_reviewer_gets_a_fresh_session_isolated_from_the_implementer(lab, driver, tmp_path):
    wid, inv, run = launch_ticket(lab, driver, tmp_path, IMPLEMENT)
    lab.wait(run)
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    driver.script(lab, "R-INV-0002-1", [{"do": "submit", "kind": "review", "meta": {
        "claim": "independent review", "review": {"independence": "R1", "disposition": "pass", "findings": [],
                                                  "resolved_findings": []}}}])
    rv = lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")
    review_run = rv["launch"]["run"]
    assert lab.wait(review_run)["status"] == "ended_with_evidence"
    assert driver.sessions(lab, review_run) == {lab.record(review_run)["launch"]["session"]}
    assert lab.record(run)["launch"]["session"] not in driver.sessions(lab, review_run)
    assert driver.state_dir(lab, review_run) != driver.state_dir(lab, run)
    [review] = [e for e in evidence_of(lab, wid, review_run) if e["kind"] == "review"]
    assert review["producer"]["role"] == "reviewer" and review["producer"]["invocation"] == rv["invocation"]
    assert_control_invariants(lab.project)


@scenario("incompatible")
def an_incompatible_harness_fails_closed(lab, driver, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    driver.script(lab, "R-INV-0001-1", [], health="incompatible")
    res = lab.lead_res("work", "assign", wid, "--launch")
    assert res.error["code"] == "HARNESS_LAUNCH_FAILED" and "HARNESS_INCOMPATIBLE" in res.error["message"]
    record = lab.record("R-INV-0001-1")
    assert record["status"] == "launch_failed" and not record.get("harness_pids")
    lab.until(lambda: supervisor_gone(record), 30, "the supervisor to exit")
    assert lab.ok("harness", "status")["runs"][0]["status"] == "launch_failed"


@scenario("effective_override")
def a_different_effective_model_is_flagged(lab, driver, tmp_path):
    _, _, run = launch_ticket(lab, driver, tmp_path, [{"do": "exit", "code": 0}],
                              effective=[{"provider": "fakeprov", "model": "fake-model", "effort": "high"},
                                         {"provider": "other", "model": "cheaper-model", "effort": None}])
    lab.wait(run)
    check = lab.record(run)["model_check"]
    assert check["status"] == "mismatch" and check["mismatches"] == [
        {"provider": "other", "model": "cheaper-model", "effort": None}]
    assert lab.ok("harness", "status")["runs"][0]["model_check"] == "mismatch"


@scenario()
def the_pinned_model_is_the_effective_model(lab, driver, tmp_path):
    _, _, run = launch_ticket(lab, driver, tmp_path, [{"do": "model_step"}, {"do": "exit", "code": 0}])
    lab.wait(run, timeout=300)
    check = lab.record(run)["model_check"]
    assert check["status"] == "match" and check["effective"], check


@scenario()
def a_read_only_role_cannot_change_its_observation(lab, driver, tmp_path):
    wid = create_investigation(lab.project, tmp_path)
    driver.script(lab, "R-INV-0001-1", [{"do": "write", "files": {"calc/core.py": "# rewritten by a reader\n"}},
                                        {"do": "submit", "kind": "discovery_record", "meta": DISCOVERY}])
    run = lab.lead("work", "dispatch", wid, "--launch")["launch"]["run"]
    assert lab.wait(run)["status"] == "ended_without_evidence"
    assert code_of(lab.step(run, 1)) == "OBSERVATION_MUTATED"
    assert not evidence_of(lab, wid)


@scenario()
def an_agent_cannot_perform_lead_operations(lab, driver, tmp_path):
    _, inv, run = launch_ticket(lab, driver, tmp_path, [
        {"do": "aew", "args": ["work", "transition", "T-0001", "--to", "REVIEW_PENDING", "--expect-rev", "99"]},
        {"do": "aew", "args": ["invoke", "cancel", "INV-0001", "--reason", "x", "--expect-rev", "99",
                               "--token", "{FORGED_CREDENTIAL}"]},
        {"do": "aew", "args": ["lead", "acquire", "--expect-rev", "99"]}])
    rev = lab.project.rev()
    lab.wait(run)
    codes = [code_of(lab.step(run, i)) for i in range(3)]
    assert codes == ["USAGE", "PERMISSION_DENIED", "PERMISSION_DENIED"], codes
    assert lab.project.rev() == rev
