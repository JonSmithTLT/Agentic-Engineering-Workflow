"""Worker waits bind to qualified foreground lifetimes, never process ancestry or telemetry files (A1 A3)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.harness import wait_binding
from aew.harness.opencode import adapter as OC
from aew.harness.opencode.client import EventStream


def adapter(tmp_path):
    events = []
    a = OC.OpenCodeAdapter(SimpleNamespace(), tmp_path, events.append)
    a.session = "session-own"
    return a, events


def event(a, kind, *, step="step-1", call=None, tool=None, session="session-own"):
    data = {"sessionID": session, "assistantMessageID": step}
    if call is not None:
        data["id"] = call
    if tool is not None:
        data["name"] = tool
    a._on_event({"type": "session." + kind, "data": data})


def start_call(a, call="shell-1", *, step="step-1", tool="shell"):
    event(a, "step.started", step=step)
    event(a, "tool.input.started", step=step, call=call, tool=tool)
    event(a, "tool.called", step=step, call=call)


@pytest.mark.parametrize("kind", ["tool.success", "tool.failed", "step.ended", "step.failed",
                                  "execution.succeeded", "execution.failed", "execution.interrupted"])
def test_each_call_step_or_execution_end_invalidates_the_pending_binding(tmp_path, kind):
    a, _ = adapter(tmp_path)
    start_call(a)
    b = a.wait_binding()
    assert b is not None and a.wait_binding_valid(b)
    event(a, kind, call="shell-1")
    assert not a.wait_binding_valid(b)
    assert a.open_shell_calls() == []


@pytest.mark.parametrize("kind", ["step.ended", "step.failed", "step.started"])
def test_a_step_boundary_with_another_id_ends_the_wait(tmp_path, kind):
    a, _ = adapter(tmp_path)
    start_call(a)
    b = a.wait_binding()
    assert b is not None
    event(a, kind, step="step-other")
    assert not a.wait_binding_valid(b)
    assert a.wait_binding() is None


@pytest.mark.parametrize("finished", ["shell-1", "shell-2"])
def test_parallel_shell_binding_ends_when_either_bound_call_finishes(tmp_path, finished):
    a, _ = adapter(tmp_path)
    start_call(a)
    start_call(a, "shell-2", tool="bash")
    b = a.wait_binding()
    assert b is not None and a.open_shell_calls() == ["shell-1", "shell-2"]
    event(a, "tool.success", call=finished)
    assert a.open_step() == "step-1" and len(a.open_shell_calls()) == 1
    assert not a.wait_binding_valid(b)  # the longer call must not keep an orphaned wait alive


def test_a_completed_and_reused_call_id_cannot_revive_an_old_binding(tmp_path):
    a, _ = adapter(tmp_path)
    start_call(a)
    b = a.wait_binding()
    assert b is not None
    event(a, "tool.success", call="shell-1")
    start_call(a)
    assert not a.wait_binding_valid(b)


def test_reconnect_clears_open_lifetimes_and_does_not_revive_the_old_binding(tmp_path):
    a, _ = adapter(tmp_path)
    start_call(a)
    b = a.wait_binding()
    assert b is not None
    a._stream_dropped()
    assert a.open_step() is None and a.open_shell_calls() == [] and a.wait_binding() is None
    start_call(a)
    assert not a.wait_binding_valid(b)


@pytest.mark.parametrize("end", ["adapter", "stop"])
def test_run_end_or_stop_invalidates_a_still_open_call(tmp_path, end):
    a, _ = adapter(tmp_path)
    start_call(a)
    b = a.wait_binding()
    assert b is not None
    if end == "adapter":
        a._end(1, "server gone")
    else:
        a._stop.set()
    assert not a.wait_binding_valid(b)


def test_only_own_session_calls_bound_to_the_open_step_can_establish_a_wait(tmp_path):
    a, _ = adapter(tmp_path)
    assert a.wait_binding() is None
    start_call(a, tool="write")
    assert a.wait_binding() is None
    event(a, "tool.input.started", call="other", tool="shell")
    event(a, "tool.called", call="other", step="other-step")
    assert a.wait_binding() is None
    event(a, "tool.called", call="other", session="session-foreign")
    assert a.wait_binding() is None
    event(a, "tool.called", call="other", session=None)
    assert a.wait_binding() is None
    event(a, "tool.called", call="other")
    assert a.wait_binding() is not None


def test_tool_success_is_tracked_but_does_not_join_the_logged_event_vocabulary(tmp_path):
    a, events = adapter(tmp_path)
    start_call(a)
    before = list(events)
    event(a, "tool.success", call="shell-1")
    assert events == before and "session.tool.success" not in OC.LOGGED_EVENTS
    assert a.open_shell_calls() == []


@pytest.mark.parametrize(("platform", "version", "supported"), [
    ("linux", "2.2.6", True), ("linux", "2.0.18", False), ("win32", "2.2.6", False)])
def test_runtime_wait_reporting_is_enabled_only_for_the_measured_platform_and_version(
        tmp_path, monkeypatch, platform, version, supported):
    a, _ = adapter(tmp_path)
    a.health["version"] = version
    monkeypatch.setattr(OC.sys, "platform", platform)
    assert a.reports_steps is supported


def test_event_stream_drop_notifies_before_reconnecting(tmp_path):
    a, _ = adapter(tmp_path)
    start_call(a)
    b = a.wait_binding()
    assert b is not None
    calls = []

    def drop():
        calls.append("drop")
        a._stream_dropped()
        stream._stop.set()

    class Client:
        def connection(self, **kwargs):
            calls.append("connect")
            raise OSError("scripted disconnect")

    stream = EventStream(Client(), lambda frame: None, lambda: True, on_drop=drop)
    stream._run()
    assert calls == ["connect", "drop"] and stream.drops == 1
    assert not a.wait_binding_valid(b)


def test_wait_maximum_is_no_larger_than_the_qualified_linux_margin():
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "opencode" / "messaging-2.2.6-linux.json"
    observed = json.loads(fixture.read_bytes())["facts"]["measurement.shell_timeout"]
    assert 0 < wait_binding.MAX_WAIT_S <= min(90, observed["default_seconds"] - 30,
                                             observed["maximum_safe_wait_seconds"])
