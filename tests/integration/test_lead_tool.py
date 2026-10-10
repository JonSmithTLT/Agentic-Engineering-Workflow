"""The typed Lead surface through the Lead broker (F15.1 slice B; typed-lead-surface-design-v0.2 §4.1, §5, §7): the
`lead.tool` operation, the CLI parity transport, the recovery-only cli escape with every broker refusal, the channel
each ingress records, the cooperative wait that never holds the broker, and the difference between a broker that
answers "your authority is gone" and one that cannot be reached."""

from __future__ import annotations

import json
import threading
import time

import pytest
from aewflow import create_planned_ticket, sample_project
from conftest import clean_env

from aew import errors
from aew.engine.api import Engine
from aew.harness import lead_broker
from aew.surface import client, run
from aew.surface.context import SurfaceContext
from aew.surface.errors import AdapterInputError


@pytest.fixture
def held(tmp_path, monkeypatch):
    """A real Lead broker for a project, serving its bridge; this process acts as the Lead's harness."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    broker = lead_broker.LeadBroker(engine, p.token)
    broker.start()
    for name, value in broker.env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    yield p, wid, engine, broker
    broker.close()


def _rev(engine) -> int:
    """The current revision, read directly (a CLI subprocess here would inherit the session's coordinates)."""
    return engine.store.read()["revision"]


def call(name, arguments, *, ingress="mcp", profile="normal"):
    return client.forward(name, arguments, ingress=ingress, profile=profile)


def test_the_client_uses_the_brokers_coordinates():
    assert client.ENV_NAMES == lead_broker.ENV_NAMES


# ---------------------------------------------------------------------------------------------- parity


def test_a_call_through_the_broker_returns_the_runners_own_result(held):
    p, wid, engine, broker = held
    via_broker = call("status", {"work_id": wid})
    ctx = SurfaceContext.for_session({"generation": broker.generation, "session_label": broker.session_label},
                                     profile="normal", ingress="mcp")
    here = run.run_tool(engine, ctx, "status", {"work_id": wid})
    for key in ("ok", "surface", "tool", "revision", "generation", "result", "completed_steps", "stopped"):
        assert via_broker[key] == here[key], key
    assert [a["action"] for a in via_broker["projection"]["actions"]] == ["ticket_start"]


def test_the_cli_transport_goes_through_the_session_broker(held):
    p, wid, engine, broker = held
    env = clean_env(broker.env)
    res = p.aew("lead", "tool", "status", "--arguments", json.dumps({"work_id": wid}), env=env)
    assert res.returncode == 0, res.stderr
    out = res.json
    assert out["ok"] and out["tool"] == "status" and out["projection"]["subject"] == wid
    bad = p.aew("lead", "tool", "cli", "--arguments", json.dumps({"argv": ["status"]}), env=env)
    assert bad.returncode != 0 and bad.error["code"] == "TOOL_NOT_EXPOSED"  # recovery-only: concealed normally
    listed = p.aew("lead", "tool", "--list", env=env)
    assert listed.returncode == 0, listed.stderr
    assert [t["name"] for t in listed.json["tools"]][:3] == ["status", "resume", "work_show"]


def test_a_checkpoint_commits_through_the_broker_and_no_result_carries_the_credential(held):
    p, wid, engine, broker = held
    rev = _rev(engine)
    out = call("checkpoint", {"expect_rev": rev, "note": "paused", "next": "review"})
    assert out["ok"] and out["revision"] == rev + 1 and out["completed_steps"][0]["primitive"] == "checkpoint"
    assert p.token not in json.dumps(out)


def test_ill_formed_calls_never_reach_the_engine(held):
    p, wid, engine, broker = held
    rev = _rev(engine)
    for name, args, profile, code in (("nope", {}, "normal", "UNKNOWN_TOOL"),
                                      ("ticket_prepare", {"expect_rev": rev, "work_id": wid,
                                                          "verification_evidence": "EV-0001"}, "normal",
                                       "TOOL_NOT_BUILT"),
                                      ("cli", {"argv": ["status"]}, "normal", "TOOL_NOT_EXPOSED"),
                                      ("checkpoint", {"expect_rev": rev, "bogus": 1}, "normal", "INVALID_ARGUMENTS")):
        with pytest.raises(AdapterInputError) as exc:
            call(name, args, profile=profile)
        assert exc.value.code == code
    assert _rev(engine) == rev


# ---------------------------------------------------------------------------------------------- the cli escape


def test_the_cli_escape_runs_a_lead_command_on_the_recovery_profile(held):
    p, wid, engine, broker = held
    rev = _rev(engine)
    out = call("cli", {"argv": ["checkpoint", "--next", "recovered", "--expect-rev", str(rev)]}, profile="recovery")
    assert out["ok"] and out["effective_operation_class"] == "JUDGMENT_BEARING" and _rev(engine) == rev + 1
    assert out["completed_steps"][0]["revision"] == rev + 1


@pytest.mark.parametrize(("argv", "why"), [
    (["lead", "release", "--expect-rev", "{rev}"], "operator"),  # operator-only
    (["lead", "handoff", "offer", "--expect-rev", "{rev}"], "operator"),
    (["lead", "tool", "status"], "transport"),  # no nested surface
    (["work", "assign", "{wid}", "--expect-rev", "{rev}"], "--launch"),  # it would print an invocation credential
    (["status"], "Lead-authenticated"),  # not a Lead command: run it directly
])
def test_the_cli_escape_keeps_every_broker_refusal(held, argv, why):
    p, wid, engine, broker = held
    rev = _rev(engine)
    argv = [a.replace("{rev}", str(rev)).replace("{wid}", wid) for a in argv]
    out = call("cli", {"argv": argv}, profile="recovery")
    assert not out["ok"] and out["stopped"]["boundary"] == "permission", out["stopped"]
    assert out["stopped"]["error"]["code"] == "PERMISSION_DENIED" and why in out["stopped"]["error"]["message"]
    assert _rev(engine) == rev


def test_a_command_that_answers_not_ok_stops_the_call_and_keeps_what_it_committed(held, monkeypatch):
    """`integrate publish` after the head moved commits one rebuild and answers ``ok: false`` (revalidate, then
    publish); the direct CLI exits nonzero for it. The typed result must not call that a success (PR #93 review).
    A checkpoint that commits and then answers the same way stands in for it here."""
    p, wid, engine, broker = held
    real = Engine.checkpoint

    def committed_but_not_done(self, **kwargs):
        out = real(self, **kwargs)
        return {**out, "ok": False, "rebuilt": True, "next": "rerun post-integration validation, then publish"}

    monkeypatch.setattr(Engine, "checkpoint", committed_but_not_done)
    rev = _rev(engine)
    out = call("cli", {"argv": ["checkpoint", "--expect-rev", str(rev)]}, profile="recovery")
    assert not out["ok"] and out["stopped"]["boundary"] == "refused", out
    assert out["stopped"]["at"] == "aew checkpoint" and out["stopped"]["error"]["code"] == "NOT_COMPLETED"
    assert out["stopped"]["error"]["message"] == "rerun post-integration validation, then publish"
    assert _rev(engine) == rev + 1 and out["completed_steps"][0]["revision"] == rev + 1  # what committed stays
    assert out["result"]["output"]["rebuilt"] is True and out["revision"] == rev + 1


def test_the_cli_escape_expands_fields_from_its_own_stdin(held):
    p, wid, engine, broker = held
    rev = _rev(engine)
    out = call("cli", {"argv": ["checkpoint", "--expect-rev", str(rev), "--fields", "-"],
                       "stdin": "next: 'from fields: $1 `x`'\n"}, profile="recovery")
    assert out["ok"], out["stopped"]
    assert _rev(engine) == rev + 1 and engine.store.read()["next_action"] == "from fields: $1 `x`"
    (p.root / "fields.yaml").write_text("next: from a file\n", encoding="utf-8")  # a FILE is read from the project
    out = call("cli", {"argv": ["checkpoint", "--expect-rev", str(rev + 1), "--fields", "fields.yaml"]},
               profile="recovery")
    assert out["ok"] and engine.store.read()["next_action"] == "from a file"


@pytest.mark.parametrize(("argv", "stdin", "code", "because"), [
    # a credential never goes through --fields: refused by the expansion itself, named so (PR #93 re-review)
    (["checkpoint", "--expect-rev", "{rev}"], "token: x\n", "USAGE", "a credential never goes through --fields"),
    # nor around a broker refusal: the expanded argv meets every one of them
    (["work", "assign", "{wid}", "--expect-rev", "{rev}"], "launch: false\n", "PERMISSION_DENIED", None),
])
def test_fields_expansion_keeps_every_broker_check(held, argv, stdin, code, because):
    p, wid, engine, broker = held
    rev = _rev(engine)
    argv = [a.replace("{rev}", str(rev)).replace("{wid}", wid) for a in argv] + ["--fields", "-"]
    out = call("cli", {"argv": argv, "stdin": stdin}, profile="recovery")
    assert not out["ok"] and out["stopped"]["error"]["code"] == code, out["stopped"]
    if because:
        assert because in out["stopped"]["error"]["message"], out["stopped"]
    assert _rev(engine) == rev


def test_the_cli_escape_refuses_a_token(held):
    p, wid, engine, broker = held
    out = call("cli", {"argv": ["checkpoint", "--token", "x", "--expect-rev", str(_rev(engine))]}, profile="recovery")
    assert not out["ok"] and out["stopped"]["error"]["code"] == "USAGE"


def test_the_bridge_key_is_not_a_lead_credential(held):
    p, wid, engine, broker = held
    with pytest.raises((errors.PermissionDenied, errors.StaleAuthority)):
        engine.checkpoint(token=broker.env[lead_broker.ENV_KEY], expect_rev=_rev(engine), note="x")


# ---------------------------------------------------------------------------------------------- channels and waiting


def _fake_wait(engine, monkeypatch, seen):
    """A run that never ends: each single check (timeout 0) reports it still running."""
    def harness_wait(runs, *, timeout=600.0, any_=False):
        seen.append(timeout)
        return {"run": runs if isinstance(runs, str) else runs[0], "status": "running", "timed_out": True}

    monkeypatch.setattr(engine, "harness_wait", harness_wait)


def test_a_wait_never_holds_the_broker_and_channels_never_bleed(held, monkeypatch):
    p, wid, engine, broker = held
    seen: list[float] = []
    _fake_wait(engine, monkeypatch, seen)
    waited: dict = {}

    def waiter():
        started = time.monotonic()
        waited["out"] = call("harness_wait", {"runs": ["R-INV-0009-1", "R-INV-0010-1"], "timeout_s": 4})
        waited["took"] = time.monotonic() - started

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.5)
    for _ in range(3):  # explain from both ingresses and a query, all while the wait blocks
        started = time.monotonic()
        mcp = call("explain", {"work_id": wid}, ingress="mcp")
        cli = call("explain", {"work_id": wid}, ingress="cli")
        status = call("status", {}, ingress="mcp")
        assert mcp["result"]["channel"] == "lead_mcp" and cli["result"]["channel"] == "lead_broker"
        assert status["ok"] and time.monotonic() - started < 3.0, "a request waited behind the blocking wait"
    rev = _rev(engine)
    from aew.harness import bridge

    out = bridge.call("lead.cli", {"argv": ["checkpoint", "--next", "during the wait", "--expect-rev", str(rev)],
                                   "cwd": str(p.root), "stdin": ""}, env_names=lead_broker.ENV_NAMES)
    assert out["result"]["revision"] == rev + 1  # a relayed command commits while the wait blocks
    thread.join(30)
    assert waited["out"]["ok"] and waited["out"]["result"]["timed_out"] is True
    assert 3.5 <= waited["took"] < 15
    assert seen and set(seen) == {0}, "the cooperative wait checks once per observation, never blocking in the engine"


def test_a_wait_ends_with_a_real_stale_result_when_authority_goes_and_then_the_broker_is_unreachable(held,
                                                                                                    monkeypatch):
    p, wid, engine, broker = held
    _fake_wait(engine, monkeypatch, [])
    waited: dict = {}
    thread = threading.Thread(target=lambda: waited.update(out=call("harness_wait", {"runs": ["R-INV-0009-1"]})))
    thread.start()
    time.sleep(0.5)
    Engine.discover(p.root).lead_release(token=p.token, expect_rev=_rev(engine))  # the seat moves on, elsewhere
    thread.join(30)
    out = waited["out"]
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_authority"
    assert isinstance(out["revision"], int) and out["projection"]["subject"] == "project"  # it read committed state
    with pytest.raises(AdapterInputError) as exc:
        call("status", {})
    assert exc.value.code == "BROKER_UNREACHABLE"  # not "stale": nothing about AEW's state is claimed


def test_a_call_after_authority_moved_is_answered_once_then_the_bridge_closes(tmp_path, monkeypatch):
    """With the watchdog held off, the next call still reaches the broker, which answers from committed state that the
    authority is gone (a real StageResult) and closes. Normally the watchdog closes the bridge within a second, and a
    caller then sees only BROKER_UNREACHABLE: both are truthful, neither is fabricated."""
    monkeypatch.setattr(lead_broker, "POLL_S", 3600.0)
    p = sample_project(tmp_path)
    engine = Engine.discover(p.root)
    broker = lead_broker.LeadBroker(engine, p.token)
    broker.start()
    for name, value in broker.env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    try:
        _answered_once_then_closed(p, engine)
    finally:
        broker.close()


def _answered_once_then_closed(p, engine):
    Engine.discover(p.root).lead_release(token=p.token, expect_rev=_rev(engine))
    out = call("status", {})
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_authority" and out["result"] is None
    with pytest.raises(AdapterInputError) as exc:
        call("status", {})
    assert exc.value.code == "BROKER_UNREACHABLE"


# ---------------------------------------------------------------------------------------------- the stages (M4-E E5a)


@pytest.fixture
def launching_broker(tmp_path, monkeypatch):
    """A broker for a project whose execution policy launches the fake harness's scripted agent (a live, idle run)."""
    from test_stage_runner import launching

    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    lab.script("default", [{"do": "hang"}])
    wid = create_planned_ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    broker = lead_broker.LeadBroker(engine, p.token)
    broker.start()
    for name, value in broker.env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    yield p, wid, engine, broker
    broker.close()
    lab.cleanup()


def test_a_stage_through_mcp_records_the_lead_mcp_channel_and_the_runners_result(launching_broker):
    """`lead_mcp` channel conformance (plan v3 E5): `ticket_start` through the MCP ingress runs the one runner with
    the held credential; its assignment and run 1 record the transport that carried them, and its result is the stage
    result the runner returns anywhere (its intent, its three steps), with no credential in it."""
    p, wid, engine, broker = launching_broker
    out = call("ticket_start", {"expect_rev": _rev(engine), "work_id": wid}, ingress="mcp")
    assert out["ok"], out["stopped"]
    assert [s["primitive"] for s in out["completed_steps"]] == ["work.assign", "dispatch.launch", "work.transition"]
    state = engine.store.read()
    inv = state["invocations"][state["work"][wid]["implementer_invocation"]]
    assert inv["dispatch"]["channel"] == "lead_mcp" and inv["dispatch"]["entrypoint"] == "work.assign"
    [run1] = inv["runs"]
    assert run1["dispatch"]["channel"] == "lead_mcp" and run1["dispatch"]["entrypoint"] == "dispatch.launch"
    assert engine.stage_intent(out["stage_intent_id"])["ingress"] == "mcp"
    assert p.token not in json.dumps(out)


def test_every_typed_call_through_the_broker_is_one_line_of_the_tool_call_log(held):
    """Plan v3 E5a (n7): one line per call, a refused or ill-formed one included, with the tool, its arguments' digest
    (never the arguments), its class, the outcome and boundary, the revisions before and after, the stage intent and
    the duration. It is local telemetry, never control state: writing it moves no revision."""
    from aew.harness import tool_calls

    p, wid, engine, broker = held
    rev = _rev(engine)
    call("status", {"work_id": wid})
    call("checkpoint", {"expect_rev": rev, "note": "a private note", "next": "review"}, ingress="cli")
    call("checkpoint", {"expect_rev": rev, "note": "stale"})  # refused: the revision moved
    with pytest.raises(AdapterInputError):
        call("checkpoint", {"expect_rev": rev, "bogus": 1})
    lines = tool_calls.read(engine.aew_root)
    assert [(x["tool"], x["ok"], x["boundary"], x["error_code"]) for x in lines] == [
        ("status", True, None, None), ("checkpoint", True, None, None),
        ("checkpoint", False, "stale_revision", "STALE_REVISION"),
        ("checkpoint", False, tool_calls.INPUT_ERROR, "INVALID_ARGUMENTS")]
    status, done, stale, bad = lines
    assert status["effective_class"] == "MECHANICAL" and status["revision_before"] == status["revision_after"] == rev
    assert (done["revision_before"], done["revision_after"], done["ingress"]) == (rev, rev + 1, "cli")
    assert stale["revision_before"] == stale["revision_after"] == rev + 1 and bad["effective_class"] is None
    assert all(x["duration_ms"] >= 0 and x["stage_intent"] is None and x["profile"] == "normal" for x in lines)
    assert done["arguments_sha256"] == tool_calls.arguments_digest(
        {"next": "review", "note": "a private note", "expect_rev": rev})
    assert "a private note" not in tool_calls.path(engine.aew_root).read_text(encoding="utf-8")
    assert _rev(engine) == rev + 1  # the log is never control state
