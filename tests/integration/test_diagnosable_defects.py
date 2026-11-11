"""Unexpected failures through the typed Lead surface (E138)."""

from __future__ import annotations

import json
import os

import pytest
from aewflow import create_planned_ticket
from test_lead_tool import call as broker_call
from test_lead_tool import held as held
from test_stage_resolve import unfinished
from test_stage_runner import CTX, call
from test_stage_runner import project as project
from test_steering_loop import Scripted, loop, mode, notes, policy_text

from aew import errors
from aew.engine.api import Engine
from aew.harness import bridge, defects, tool_calls
from aew.harness.steering_loop import ACTION_STOPPED
from aew.schemas import validate
from aew.surface import mcp, readable, run, stage


def fail_with(exc):
    def fail(*args):
        raise exc
    return fail


def mcp_call(forward, name, arguments):
    [out] = mcp.Server(forward).handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments},
    }))
    return out


@pytest.mark.parametrize("kind", [RuntimeError, ValueError])
def test_e138_mid_stage_defect_reports_the_running_step(project, tmp_path, monkeypatch, kind):
    wid = create_planned_ticket(project, tmp_path)

    monkeypatch.setitem(stage.STEP_RUNNERS, "work.assign", fail_with(kind("synthetic mid-stage failure")))
    out = call(project, "probe_start", work_id=wid)
    validate("surface", out, source="E138 mid-stage defect")
    assert not out["ok"]
    stopped = out["stopped"]
    assert stopped["at"] == "work.assign" and stopped["boundary"] == "error"
    assert stopped["error"]["code"] == "DEFECT"
    assert [s["primitive"] for s in out["completed_steps"]] == ["checkpoint"]
    assert stopped["error"]["details"]["committed"] == 1
    intent = out["stage_intent_id"]
    assert intent and stopped["error"]["details"]["stage_intent"] == intent
    assert intent in unfinished(project)
    assert "next: Call `resume`" in readable.render(out)
    [record] = [json.loads(line) for line in
                (project.root / ".aew/local/lead/defects.jsonl").read_text(encoding="utf-8").splitlines()]
    assert record["defect"] == stopped["error"]["details"]["defect"]
    assert kind.__name__ in record["traceback"] and record["step"] == "work.assign"


def test_e138_mcp_process_names_its_own_failure():
    def fail(*args):
        raise RuntimeError("private value")

    server = mcp.Server(fail)
    out = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "status"}})
    assert out is not None and out["error"]["code"] == mcp.INTERNAL_ERROR
    assert all(word in out["error"]["message"] for word in ("tools/call", "status", "RuntimeError", "stderr"))
    assert "private value" not in out["error"]["message"]


@pytest.mark.parametrize("code", ["GIT_ERROR", "BRIDGE_ERROR"])
def test_e138_mcp_keeps_other_error_codes_without_arbitrary_details(tmp_path, code):
    exc = bridge.rebuild_error({"code": code, "message": "synthetic broker text", "details": {"cwd": str(tmp_path)}})
    error = mcp_call(fail_with(exc), "status", {})["error"]
    assert error["code"] == mcp.INTERNAL_ERROR and error["data"] == {"aew_error": {"code": code}}
    assert error["message"] == ("The Lead broker failed on this call." if code == "BRIDGE_ERROR"
                                else "synthetic broker text")


def test_e138_query_failure_returns_a_bounded_stage_result(project, monkeypatch):
    engine = Engine.discover(project.root)
    monkeypatch.setitem(run.RUNNERS, "status", fail_with(RuntimeError("unpublished value")))
    out = run.run_tool(engine, CTX, "status", {})
    stopped = out["stopped"]
    assert not out["ok"] and stopped["at"] == "status"
    assert stopped["error"]["code"] == "DEFECT" and stopped["error"]["details"]["committed"] == 0
    assert "Call it again" in out["result"]["next_action"]
    assert "unpublished value" not in json.dumps(out)
    assert len(json.dumps(stopped).encode()) < defects.MAX_ERROR_BYTES


def test_e138_an_unreadable_journal_leaves_commit_count_unknown(project, tmp_path, monkeypatch):
    wid = create_planned_ticket(project, tmp_path)
    monkeypatch.setitem(stage.STEP_RUNNERS, "work.assign", fail_with(RuntimeError("step failure")))
    monkeypatch.setattr(stage, "_payload", fail_with(OSError("journal read failure")))
    out = call(project, "probe_start", work_id=wid)
    assert out["stopped"]["error"]["details"]["committed"] is None
    assert out["stage_intent_id"] in unfinished(project)


def test_e138_projection_failure_keeps_the_cause_and_committed_count(project, monkeypatch):
    engine = Engine.discover(project.root)
    cause = "cause ``` " + "x" * 10_000 + "END"
    monkeypatch.setattr(run, "_projection", fail_with(errors.IntegrityError(cause, cwd=str(project.root))))
    with pytest.raises(errors.Defect) as caught:
        run.run_tool(engine, CTX, "checkpoint", {"expect_rev": project.rev()}, token=project.token)
    defect = caught.value
    assert defect.details["cause_code"] == "INTEGRITY_ERROR" and defect.details["committed"] == 1
    assert "cause ｀｀｀" in defect.message and "END" not in defect.message
    assert "Call it again" in defect.message and "resume" not in defect.message
    assert len(defect.message) <= defects.MAX_MESSAGE
    assert isinstance(defect.__cause__, errors.IntegrityError)

    def forward(name, arguments, profile):
        try:
            return run.run_tool(engine, CTX, name, arguments, token=project.token)
        except errors.Defect as exc:
            raise bridge.rebuild_error(exc.to_dict()) from None

    out = mcp_call(forward, "checkpoint", {"expect_rev": project.rev()})
    error = out["error"]
    assert error["code"] == mcp.INTERNAL_ERROR and "INTEGRITY_ERROR" in error["message"]
    typed = error["data"]["aew_error"]
    assert typed["code"] == "DEFECT" and typed["details"]["committed"] == 1
    assert typed["details"]["cause_code"] == "INTEGRITY_ERROR"
    assert "cwd" not in typed["details"] and str(project.root) not in error["message"]
    assert len(json.dumps(error).encode()) < defects.MAX_ERROR_BYTES


@pytest.mark.parametrize("kind", [RuntimeError, ValueError])
def test_e138_broker_failure_stays_typed_and_secrets_stay_out(held, tmp_path, monkeypatch, kind):
    _p, _wid, engine, broker = held
    path = str(tmp_path / "outside-project")
    aew_key = "aew1." + "tk_" + "0" * 16 + "." + "f" * 40
    provider_key = "sk-" + "1" + "a" * 24
    monkeypatch.setenv("E138_TEST_VALUE", "synthetic-private-environment-value")
    value = os.environ["E138_TEST_VALUE"]
    secret_text = f"{path} {aew_key} {provider_key} {value}"
    monkeypatch.setitem(run.RUNNERS, "status", fail_with(kind(secret_text)))
    stage_result = broker_call("status", {})
    assert stage_result["stopped"]["error"]["code"] == "DEFECT"
    assert kind.__name__ in stage_result["stopped"]["error"]["message"]
    monkeypatch.setattr(broker, "_authority_lost", fail_with(kind(secret_text)))
    with pytest.raises(errors.Defect) as caught:
        broker_call("status", {})
    assert "outcome is unknown" in caught.value.message and caught.value.details["committed"] is None
    assert caught.value.details["exception"] == kind.__name__

    out = mcp_call(lambda name, args, profile: broker_call(name, args, profile=profile), "status", {})
    error = out["error"]
    assert error["code"] == mcp.INTERNAL_ERROR
    detail = error["data"]["aew_error"]["details"]
    assert error["data"]["aew_error"]["code"] == "DEFECT" and detail["exception"] == kind.__name__
    line = tool_calls.read(engine.aew_root)[-1]
    assert line["error_code"] == "DEFECT" and line["defect"] == detail["defect"]
    assert line["exception"] == kind.__name__ and line["cause_code"] is None
    for hidden in (path, aew_key, provider_key, value):
        escaped = json.dumps(hidden)[1:-1]
        assert hidden not in caught.value.message
        assert all(escaped not in json.dumps(item) for item in (stage_result, out, line))
    record = json.loads((engine.aew_root / defects.DEFECT_LOG_REL).read_text(encoding="utf-8").splitlines()[-1])
    assert path in record["traceback"]
    assert aew_key not in record["traceback"] and provider_key not in record["traceback"]


def test_e138_broker_telemetry_preserves_the_cause_code(held, monkeypatch):
    _p, _wid, engine, _broker = held
    monkeypatch.setattr(run, "_projection", fail_with(errors.IntegrityError("synthetic projection failure")))
    with pytest.raises(errors.Defect) as caught:
        broker_call("checkpoint", {"expect_rev": engine.store.current()["revision"]})
    line = tool_calls.read(engine.aew_root)[-1]
    assert line["error_code"] == "DEFECT" and line["exception"] == "IntegrityError"
    assert line["defect"] == caught.value.details["defect"] and line["cause_code"] == "INTEGRITY_ERROR"
    assert len(tool_calls.path(engine.aew_root).read_bytes().splitlines()[-1]) + 1 <= tool_calls.MAX_LINE


def test_e138_steering_stops_on_a_runner_defect(project, monkeypatch):
    policy_text(project)
    mode(project, "walk")
    monkeypatch.setitem(stage.STEP_RUNNERS, "checkpoint", fail_with(RuntimeError("private value")))
    stop = loop(project, Scripted(notes)).activate()
    assert stop.code == ACTION_STOPPED and "DEFECT" in stop.message and "private value" not in stop.message
