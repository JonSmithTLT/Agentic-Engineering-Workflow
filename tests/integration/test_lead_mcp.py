"""The `aew-lead` MCP server inside a real Lead session (F15.1 slice C; typed-lead-surface-design-v0.2 §4.1, §4.3):
the Lead's harness (a scripted MCP client here) spawns `aew lead mcp`, which holds no credential and forwards every
call to the session's broker. Custody is checked the way the Lead-session tests check it: no credential in the
server's environment, the transcript, the output or any file; the server refuses to start without a live broker or
with a credential in its environment; after a takeover the harness keeps running and the server never fabricates an
answer."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from aewflow import create_planned_ticket, sample_project
from conftest import IS_WINDOWS, clean_env, run_aew
from fake_harness import contains_credential, credential_hits
from invariants import assert_control_invariants

PROBE = Path(__file__).resolve().parents[1] / "helpers" / "mcp_probe_agent.py"
HANDSHAKE = [{"rpc": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                              "clientInfo": {"name": "probe", "version": "0"}}},
             {"notify": "notifications/initialized"}, {"rpc": "tools/list"}]


def _argv(tmp_path: Path, name: str, steps: list[dict], profile: str = "normal") -> tuple[list[str], Path]:
    script, transcript = tmp_path / f"{name}.json", tmp_path / f"{name}.jsonl"
    script.write_text(json.dumps(steps), encoding="utf-8")
    return ["lead", "session", "--", sys.executable, str(PROBE), "--script", str(script), "--transcript",
            str(transcript), "--profile", profile], transcript


def _records(transcript: Path) -> list[dict]:
    return [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]


def _content(record: dict) -> dict:
    return record["reply"]["result"]["structuredContent"]


def _rev(p) -> int:
    return p.ok("lead", "show")["revision"]


def test_the_lead_drives_aew_through_mcp_and_nothing_in_it_holds_the_credential(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    rev = _rev(p)
    env_file = tmp_path / "server-env.json"
    argv, transcript = _argv(tmp_path, "lead", [
        *HANDSHAKE,
        {"call": "status", "arguments": {}},
        {"call": "checkpoint", "arguments": {"expect_rev": "$revision", "note": "paused", "next": "start T-0001"}},
        {"call": "explain", "arguments": {"work_id": wid}},
        {"call": "nope", "arguments": {}},
        {"call": "ticket_start", "arguments": {"expect_rev": "$revision", "work_id": wid}},
        {"call": "cli", "arguments": {"argv": ["status"]}},
        {"call": "checkpoint", "arguments": {"expect_rev": "$revision", "bogus": True}},
        {"server_env": str(env_file)},
        {"call": "status", "arguments": {"work_id": wid}},
    ])
    res = run_aew("-C", str(p.root), *argv, env={"AEW_LEAD_TOKEN": p.token}, timeout=600)
    assert res.returncode == 0, res.stderr
    r = _records(transcript)
    init, listed = r[0]["reply"]["result"], r[2]["reply"]["result"]
    assert init["serverInfo"]["name"] == "aew-lead"
    assert [t["name"] for t in listed["tools"]] == ["status", "resume", "work_show", "explain", "harness_status",
                                                    "harness_wait", "checkpoint", "steering"]  # no cli or designed stage
    assert _content(r[3])["ok"] and _content(r[3])["revision"] == rev
    assert _content(r[4])["ok"] and _content(r[4])["revision"] == rev + 1
    explained = _content(r[5])
    assert explained["result"]["channel"] == "lead_mcp" and explained["result"]["entrypoint"] == "work.assign"
    codes = [r[i]["reply"]["error"]["data"]["adapter_input_error"]["code"] for i in (6, 7, 8, 9)]
    assert codes == ["UNKNOWN_TOOL", "TOOL_NOT_BUILT", "TOOL_NOT_EXPOSED", "INVALID_ARGUMENTS"]
    assert _rev(p) == rev + 1  # the refused calls committed nothing
    start = next(a for a in _content(r[11])["projection"]["actions"] if a["action"] == "ticket_start")
    assert start["callable"] is False and start["cli_fallback"][:2] == ["work", "assign"]
    # Custody: the server's environment, the transcript, the session's output and every file.
    env = json.loads(env_file.read_text(encoding="utf-8"))
    assert "AEW_LEAD_TOKEN" not in env["names"] and not env["credential_shaped"], env
    assert {"AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"} <= set(env["names"])
    assert not {"AEW_INVOCATION_TOKEN", "AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY"} & set(env["names"])
    end = r[-1]
    assert end["i"] == "end" and end["server_exit"] == 0, end
    assert "AEW_LEAD_TOKEN" not in end["own_env"]["names"] and not end["own_env"]["credential_shaped"]
    for blob in (transcript.read_text(encoding="utf-8"), res.stdout, res.stderr, end["server_stderr"]):
        assert p.token not in blob and not contains_credential(blob)
    assert not credential_hits(tmp_path), "a credential string was left in a file"
    assert_control_invariants(p)


def test_after_a_takeover_the_harness_keeps_running_and_the_server_never_fabricates_an_answer(tmp_path, monkeypatch):
    import aew.operator
    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    sync = tmp_path / "sync"
    sync.mkdir()
    argv, transcript = _argv(tmp_path, "takeover", [
        *HANDSHAKE, {"call": "status", "arguments": {}}, {"touch": str(sync / "ready")},
        {"wait_file": str(sync / "go")}, {"call": "status", "arguments": {}}, {"call": "status", "arguments": {}},
        {"rpc": "ping"}])
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen([sys.executable, "-m", "aew", "-C", str(p.root), *argv],
                            env=clean_env({"AEW_LEAD_TOKEN": p.token}), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, encoding="utf-8", **kwargs)
    deadline = time.monotonic() + 120
    while not (sync / "ready").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (sync / "ready").exists(), "the Lead session never became ready"
    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator (test)"})
    Engine.discover(p.root).lead_takeover(expect_rev=_rev(p), reason="session lost", session_label="operator")
    time.sleep(1.5)  # the broker's watchdog notices within a second and closes its bridge
    (sync / "go").touch()
    out, err = proc.communicate(timeout=300)
    assert json.loads(out)["superseded"], err
    r = _records(transcript)
    assert _content(r[3])["ok"]
    for record in (r[6], r[7]):
        reply = record["reply"]
        if "result" in reply:  # answered from committed state: a real StageResult that says so
            assert _content(record)["stopped"]["boundary"] == "stale_authority"
        else:  # the bridge is gone: a transport error, with no state claimed
            assert reply["error"]["code"] == -32001 and "structuredContent" not in json.dumps(reply)
    assert "error" in r[7]["reply"]  # once closed, it stays closed
    assert r[8]["reply"]["result"] == {}  # and the harness's server is still serving (read-only now)
    assert r[-1]["i"] == "end"


def test_a_wait_through_mcp_never_queues_the_next_call_on_the_same_connection(tmp_path, monkeypatch):
    """The real `aew lead mcp` process and its stdio, in front of a real broker whose run never ends (each single
    check reports it running, as in the broker's own cooperative-wait tests). A status sent right after a four-second
    `harness_wait`, on the same connection and before its answer, is answered first and promptly (PR #95 review)."""
    from aew.engine.api import Engine
    from aew.harness import lead_broker

    p = sample_project(tmp_path)
    engine = Engine.discover(p.root)
    monkeypatch.setattr(engine, "harness_wait", lambda runs, *, timeout=600.0, any_=False: {
        "run": runs if isinstance(runs, str) else runs[0], "status": "running", "timed_out": True})
    broker = lead_broker.LeadBroker(engine, p.token)
    broker.start()
    try:
        env = clean_env(broker.env)
        env.pop("AEW_LEAD_TOKEN", None)
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
        server = subprocess.Popen([sys.executable, "-m", "aew", "lead", "mcp"], cwd=str(p.root), env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        assert server.stdin is not None and server.stdout is not None
        for rid, name, arguments in [(1, "harness_wait", {"runs": ["R-INV-0009-1"], "timeout_s": 4}),
                                     (2, "status", {})]:
            server.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                            "params": {"name": name, "arguments": arguments}}) + "\n").encode())
            server.stdin.flush()
        sent = time.monotonic()
        first = json.loads(server.stdout.readline())
        first_at = time.monotonic() - sent
        second = json.loads(server.stdout.readline())
        waited = time.monotonic() - sent
        server.stdin.close()
        assert server.wait(timeout=30) == 0
    finally:
        broker.close()
    assert first["id"] == 2 and first["result"]["structuredContent"]["ok"], first
    assert first_at < 3.0, f"the status waited {first_at:.1f}s behind the wait"
    assert second["id"] == 1 and second["result"]["structuredContent"]["result"]["timed_out"] is True
    assert 3.5 <= waited < 20


@pytest.mark.parametrize(("extra", "why"), [
    ({}, "live Lead session"),
    ({"AEW_LEAD_BROKER": "nowhere", "AEW_LEAD_BROKER_KEY": "00" * 32, "AEW_LEAD_TOKEN": "aew1.x"}, "AEW_LEAD_TOKEN"),
    ({"AEW_LEAD_BROKER": r"\\.\pipe\aew-nowhere" if IS_WINDOWS else "/nonexistent/aew-bridge",
      "AEW_LEAD_BROKER_KEY": "00" * 32}, "not live"),
])
def test_without_a_live_broker_or_with_a_credential_it_refuses_to_start(tmp_path, extra, why):
    p = sample_project(tmp_path)
    env = clean_env(extra)
    for name in ("AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"):
        if name not in extra:
            env.pop(name, None)
    res = subprocess.run([sys.executable, "-m", "aew", "-C", str(p.root), "lead", "mcp"], env=env,
                         input="", capture_output=True, text=True, timeout=120,
                         creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    assert res.returncode != 0 and why in res.stderr, res.stderr
    assert res.stdout == ""  # stdout is the protocol's, and nothing was served
