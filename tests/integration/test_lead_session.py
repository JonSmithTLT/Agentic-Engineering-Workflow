"""Lead custody (ADR-0009; operator requirement): a Lead harness session requests Lead operations through
the Lead bridge and never receives the Lead credential. The parity test runs the same custody properties
and the same transport attacks against the invocation bridge and the Lead bridge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aewflow import create_investigation, create_planned_ticket, sample_project
from conftest import IS_WINDOWS, Project, clean_env, make_git_repo, run_aew
from fake_harness import AGENT, HarnessLab, contains_credential, credential_hits
from invariants import assert_control_invariants

from aew.harness import bridge, lead_broker

SECRET = "sk-provider-secret-must-not-reach-the-agent"


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, extra_env={"OPENAI_API_KEY": SECRET})
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


@pytest.fixture
def sync(tmp_path):
    d = tmp_path / "sync"
    d.mkdir(exist_ok=True)  # HarnessLab already made it (a writable root for contained runs)
    return d


def _session_argv(lab, name: str, steps: list[dict], acquire: bool) -> tuple[list[str], Path]:
    script = lab.tmp / f"{name}.json"
    script.write_text(json.dumps(steps), encoding="utf-8")
    transcript = lab.tmp / f"{name}.transcript.jsonl"
    argv = ["lead", "session", *(["--acquire", "--session-label", name] if acquire else []), "--",
            sys.executable, str(AGENT), "--script", str(script), "--transcript", str(transcript)]
    return argv, transcript


def _steps(transcript: Path) -> dict[int, dict]:
    lines = transcript.read_text(encoding="utf-8").splitlines() if transcript.exists() else []
    return {e["i"]: e["result"] for e in map(json.loads, lines)}


def session(lab, name: str, steps: list[dict], *, acquire: bool = False, token: bool = True):
    """Run ``aew lead session`` to completion with the fake agent as the Lead's harness."""
    argv, transcript = _session_argv(lab, name, steps, acquire)
    # A whole Lead session (several CLI round trips and possibly a run launch) in one call: generous timeout.
    res = run_aew("-C", str(lab.root), *argv, env={**lab.env, **({"AEW_LEAD_TOKEN": lab.project.token} if token
                                                                  else {})}, timeout=600)
    return res, _steps(transcript)


def start_session(lab, name: str, steps: list[dict]) -> tuple[subprocess.Popen, Path]:
    """Start ``aew lead session`` in the background (the test acts while the Lead's harness runs)."""
    argv, transcript = _session_argv(lab, name, steps, False)
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-m", "aew", "-C", str(lab.root), *argv],
                            env=clean_env({**lab.env, "AEW_LEAD_TOKEN": lab.project.token}), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", **kwargs)
    return proc, transcript


def code(step: dict) -> str | None:
    if isinstance(step.get("stderr_json"), dict):
        return (step["stderr_json"].get("error") or {}).get("code")
    if isinstance(step.get("error"), dict):
        return step["error"].get("code")
    return step.get("code")


def takeover(lab, monkeypatch) -> None:
    import aew.operator
    from aew.engine.api import Engine

    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator (test)"})
    lab.project.token = Engine.discover(lab.root).lead_takeover(expect_rev=lab.project.rev(), reason="session lost",
                                                                session_label="operator")["token"]


# ---------------------------------------------------------------------------------------------- Lead bridge

def test_the_lead_harness_acts_through_the_bridge_and_never_holds_the_credential(lab, tmp_path, sync):
    res, steps = session(lab, "lead-a", [
        {"do": "dump_env", "path": str(sync / "env")},
        {"do": "child_env", "path": str(sync / "child"), "shell_path": str(sync / "shell")},
        {"do": "lead", "args": ["work", "create", "ticket", "--title", "Survey calc", "--class", "0",
                                "--non-mutating", "--goal", "document calc", "--scope", "calc/**"]},
        {"do": "aew", "args": ["status", "--json"]},
        {"do": "scan", "out": str(sync / "hits"), "roots": [str(lab.root), str(tmp_path)]},
        {"do": "read_parent_environ", "pid": "ppid"},
    ])
    assert res.returncode == 0, res.stderr
    if sys.platform.startswith("linux") and os.geteuid() != 0:  # the credential holder is non-dumpable
        assert steps[5]["readable"] is False, steps[5]
    assert res.json["exit"] == 0 and res.json["seat"] == "held by your AEW_LEAD_TOKEN"
    assert steps[2]["exit"] == 0 and steps[2]["stdout_json"]["id"] == "T-0001"
    env, child = json.loads((sync / "env").read_text()), json.loads((sync / "child").read_text())
    for blob in (res.stdout, json.dumps(env), json.dumps(child), (sync / "shell").read_text(), json.dumps(steps)):
        assert not contains_credential(blob)
    assert "AEW_LEAD_TOKEN" not in env and "AEW_LEAD_TOKEN" not in child
    assert {lead_broker.ENV_ENDPOINT, lead_broker.ENV_KEY} <= set(env)
    assert steps[4]["hits"] == []
    assert_control_invariants(lab.project)


def test_the_lead_bridge_refuses_what_would_put_a_credential_in_the_session(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    inv = create_investigation(lab.project, tmp_path, title="Survey")
    lab.script("default", [{"do": "exit", "code": 0}])
    res, steps = session(lab, "lead-b", [
        {"do": "lead", "args": ["lead", "handoff", "offer"]},
        {"do": "aew", "args": ["lead", "acquire", "--expect-rev", "0"]},
        {"do": "lead", "args": ["lead", "release"]},
        {"do": "lead", "args": ["work", "assign", wid]},                    # would print an invocation credential
        {"do": "lead", "args": ["work", "dispatch", inv, "--launch"]},      # custody goes to the run's supervisor
        {"do": "lead", "args": ["checkpoint", "--next", "x", "--token", "{FORGED_CREDENTIAL}"]},
        {"do": "bridge_payload", "bridge": "lead", "request": {"op": "lead.cli", "args": {
            "argv": ["lead", "show"], "cwd": str(lab.root), "stdin": ""}}},
    ])
    assert res.returncode == 0, res.stderr
    assert [code(steps[i]) for i in range(4)] == ["USAGE", "USAGE", "USAGE", "PERMISSION_DENIED"]
    launched = steps[4]["stdout_json"]
    assert steps[4]["exit"] == 0 and "invocation_token" not in launched and not contains_credential(steps[4]["stdout"])
    assert code(steps[5]) == "PERMISSION_DENIED"   # a forged credential runs locally and is rejected
    assert code(steps[6]) == "PERMISSION_DENIED"   # read-only commands are not brokered
    lab.wait(launched["launch"]["run"])
    assert_control_invariants(lab.project)


def test_the_lead_bridge_serves_only_its_own_project(lab, tmp_path):
    other = sample_project(tmp_path / "other")
    res, steps = session(lab, "lead-c", [
        {"do": "aew", "args": ["-C", str(other.root), "checkpoint", "--next", "x", "--expect-rev", "1"]}])
    assert code(steps[0]) == "PERMISSION_DENIED" and "different AEW project" in steps[0]["stderr"]


def test_a_lead_session_needs_a_credential_it_can_hold(lab):
    res, _ = session(lab, "lead-d", [], token=False)
    assert res.error["code"] == "USAGE"


def test_an_acquired_seat_is_released_or_held_explicitly(tmp_path, sync):
    p = Project(make_git_repo(tmp_path / "vacant", {"README.md": "# v\n", "calc/core.py": "x = 1\n"}))
    p.ok("init", "--project-id", "vacant")
    lab = HarnessLab.create(p, tmp_path)
    try:
        res, steps = session(lab, "acq-1", [{"do": "lead", "args": ["checkpoint", "--next", "plan the work"]}],
                             acquire=True, token=False)
        assert res.returncode == 0 and steps[0]["exit"] == 0 and res.json["seat"] == "released"
        assert not contains_credential(res.stdout + res.stderr) and p.ok("lead", "show")["status"] == "vacant"
        plan = tmp_path / "plan.md"
        plan.write_text("Read calc/core.py.\n", encoding="utf-8")
        lab.script("default", [{"do": "wait_file", "path": str(sync / "never"), "timeout": 300}])
        res, steps = session(lab, "acq-2", [
            {"do": "lead", "args": ["work", "create", "ticket", "--title", "Survey", "--class", "0", "--non-mutating",
                                    "--goal", "g", "--scope", "calc/**"]},
            {"do": "lead", "args": ["plan", "propose", "--assurance", "none", "T-0001", "--file", str(plan)]},
            {"do": "lead", "args": ["plan", "accept", "T-0001", "--revision", "1"]},
            {"do": "lead", "args": ["work", "dispatch", "T-0001", "--launch"]},
        ], acquire=True, token=False)
        assert [steps[i]["exit"] for i in range(4)] == [0, 0, 0, 0], steps
        seat = res.json["seat"]
        assert seat.startswith("held;") and "aew lead takeover" in seat and "INV-0001" in seat
        assert not contains_credential(res.stdout + res.stderr) and p.ok("lead", "show")["status"] == "active"
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path)


def test_a_superseded_lead_session_loses_its_bridge(lab, sync, monkeypatch):
    proc, transcript = start_session(lab, "lead-e", [
        {"do": "dump_env", "path": str(sync / "env")}, {"do": "touch", "path": str(sync / "ready")},
        {"do": "wait_file", "path": str(sync / "go"), "timeout": 120},
        {"do": "lead", "args": ["checkpoint", "--next", "after takeover"]}])
    lab.until((sync / "ready").exists, what="Lead session ready")
    takeover(lab, monkeypatch)
    (sync / "go").touch()
    out, err = proc.communicate(timeout=120)
    assert code(_steps(transcript)[3]) == "STALE_AUTHORITY"
    assert json.loads(out)["superseded"]
    env = json.loads((sync / "env").read_text())
    with pytest.raises(Exception) as closed:
        bridge.call("lead.cli", {"argv": ["lead", "show"], "cwd": str(lab.root), "stdin": ""},
                    endpoint=env[lead_broker.ENV_ENDPOINT], key=env[lead_broker.ENV_KEY])
    assert getattr(closed.value, "code", None) == "STALE_AUTHORITY"


# ---------------------------------------------------------------------------------------------- parity

def parity_steps(sync: Path, kind: str, authorized: dict, op: str, args: dict) -> list[dict]:
    return [
        {"do": "dump_env", "path": str(sync / "env")},
        {"do": "child_env", "path": str(sync / "child"), "shell_path": str(sync / "shell")},
        authorized,
        {"do": "bridge_payload", "bridge": kind, "raw": "not json"},
        {"do": "bridge_payload", "bridge": kind, "request": {"op": "anything.else", "args": {}}},
        {"do": "bridge_payload", "bridge": kind, "request": {"op": op, "args": {**args, "invocation": "INV-0099"}}},
        {"do": "bridge_raw", "bridge": kind, "op": op, "args": args, "key": "00" * 32},
        {"do": "touch", "path": str(sync / "ready")},
        {"do": "wait_file", "path": str(sync / "go"), "timeout": 120},
        authorized,
        {"do": "touch", "path": str(sync / "done")},
    ]


@pytest.mark.parametrize("kind", ["invocation", "lead"])
def test_both_bridges_hold_the_same_custody_properties(lab, tmp_path, sync, monkeypatch, kind):
    """The designer's parity requirement: the same five custody properties and the same transport refusals,
    whether the credential held is an invocation's or the Lead's."""
    if kind == "invocation":
        steps = parity_steps(sync, kind, {"do": "aew", "args": ["whoami"]}, "whoami", {})
        wid = create_planned_ticket(lab.project, tmp_path)
        lab.script("R-INV-0001-1", steps)
        watchdog = sync / "watchdog"
        watchdog.write_text("hold", encoding="utf-8")  # let the old agent act after revocation (the bridge refuses)
        out = lab.lead("work", "assign", wid, "--launch",
                       env={"AEW_PAUSE": f"harness.watchdog.tick={watchdog}"})
        lab.until((sync / "ready").exists, what="holder ready")
        lab.lead("invoke", "cancel", out["invocation"], "--reason", "revoked mid-run")
        (sync / "go").touch()
        lab.until((sync / "done").exists, what="attempt after revocation")
        result = {i: lab.step("R-INV-0001-1", i) for i in range(10)}
        watchdog.unlink()
        lab.wait("R-INV-0001-1")
        env_names, op, args = (bridge.ENV_ENDPOINT, bridge.ENV_KEY), "whoami", {}
    else:
        args = {"argv": ["checkpoint", "--next", "x", "--expect-rev", "1"], "cwd": str(lab.root), "stdin": ""}
        steps = parity_steps(sync, kind, {"do": "lead", "args": ["checkpoint", "--next", "parity"]}, "lead.cli", args)
        proc, transcript = start_session(lab, "parity", steps)
        lab.until((sync / "ready").exists, what="holder ready")
        takeover(lab, monkeypatch)
        (sync / "go").touch()
        proc.communicate(timeout=120)
        result = _steps(transcript)
        env_names, op = (lead_broker.ENV_ENDPOINT, lead_broker.ENV_KEY), "lead.cli"
    # 1. an authorized operation works without any credential in the holder's environment
    assert result[2]["exit"] == 0, result[2]
    # 2-3. neither the holder, a child process nor a shell can see or print a credential
    env, child = json.loads((sync / "env").read_text()), json.loads((sync / "child").read_text())
    for blob in (json.dumps(env), json.dumps(child), (sync / "shell").read_text()):
        assert not contains_credential(blob)
        # Provider secrets: an invocation's model-controlled processes get the allowlisted agent environment. A Lead
        # session's harness process keeps the operator's environment (minus AEW credentials) because a harness
        # needs its provider keys; curating the Lead model's *shell* is the harness adapter's job (the OpenCode Lead
        # launcher, M3 step 4, applies the same allowlist per session). Not an AEW-credential property.
        assert kind == "lead" or SECRET not in blob
    assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN"} & (set(env) | set(child)) and set(env_names) <= set(env)
    # the same transport refusals
    assert [code(result[i]) for i in (3, 4, 5, 6)] == ["USAGE", "PERMISSION_DENIED", "USAGE", "PERMISSION_DENIED"]
    # 5. once authority is revoked, the bridge refuses — and stays closed
    assert code(result[9]) == "STALE_AUTHORITY", result[9]
    with pytest.raises(Exception) as closed:
        bridge.call(op, args, endpoint=env[env_names[0]], key=env[env_names[1]])
    assert getattr(closed.value, "code", None) == "STALE_AUTHORITY"
    # 4. no credential in any file (also asserted over the whole tmp tree by the fixture)
    assert not credential_hits(tmp_path)
