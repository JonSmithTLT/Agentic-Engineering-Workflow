"""Each lifetime/send failure releases the live-delivery hold without recording a false receipt (A1 A3)."""

from __future__ import annotations

import ast
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew import errors
from aew.harness import wait_binding, worker_messages
from aew.harness.opencode.adapter import OpenCodeAdapter


class QualifiedFake(OpenCodeAdapter):
    reports_steps = True


class Connection:
    def __init__(self):
        self.gone = False

    def poll(self, timeout):
        return self.gone


def setup(tmp_path, *, open_call=True):
    a = QualifiedFake(SimpleNamespace(), tmp_path, lambda e: None)
    a.session = "s"
    calls = a._wait_calls
    if open_call:
        calls.event("session.step.started", {"assistantMessageID": "step"}, None)
        calls.event("session.tool.called", {"assistantMessageID": "step", "id": "call"}, "shell")
    recorded = []

    def engine_send(**kwargs):
        kwargs["send"]({"messages": [{"id": "MSG-INV-0001-1"}], "outcome": "messages"})
        recorded.append("MSG-INV-0001-1")  # same order as the real engine: failed send must not reach this line

    s = SimpleNamespace(adapter=a, bridge=SimpleNamespace(serialized=nullcontext, closed=False),
                        engine=SimpleNamespace(message_deliver_wait=engine_send,
                                               message_waiting=lambda **kw: {"messages": [{"id": "MSG-INV-0001-1"}]}),
                        require_message_authority=lambda: None, _ending=threading.Event(), _credential="held",
                        events=lambda e: None, run="R-INV-0001-1")
    messages = worker_messages.WorkerMessages(s)
    return s, a, messages, Connection(), recorded


@pytest.mark.parametrize("failure", ["call", "step", "reconnect", "run", "eof", "send"])
def test_final_pre_send_failures_record_nothing_and_release_the_hold(tmp_path, failure):
    s, a, messages, conn, recorded = setup(tmp_path)
    engine_send = s.engine.message_deliver_wait

    def race(**kwargs):
        assert messages.waiting
        if failure == "call":
            a._wait_calls.event("session.tool.success", {"id": "call"}, None)
        elif failure == "step":
            a._wait_calls.event("session.step.ended", {"assistantMessageID": "other"}, None)
        elif failure == "reconnect":
            a._stream_dropped()
        elif failure == "run":
            s._ending.set()
        elif failure == "eof":
            conn.gone = True
        engine_send(**kwargs)

    s.engine.message_deliver_wait = race
    result = []

    def send(value):
        if failure == "send":
            raise OSError("closed during the send")
        result.append(value)

    delivery = messages.wait({"after": "", "timeout_s": "1"}, conn)
    if failure == "send":
        with pytest.raises(OSError):
            delivery.deliver(send)
    else:
        delivery.deliver(send)
        assert result == [{"outcome": "ended_early", "messages": [],
                           "next_action": "the wait ended early; call `aew message wait` again"}]
    assert recorded == [] and not messages.waiting


def test_success_records_only_after_send_and_releases_the_hold(tmp_path):
    _, _, messages, conn, recorded = setup(tmp_path)
    returned = []

    def send(value):
        assert messages.waiting and recorded == []
        returned.append(value)

    messages.wait({"after": "", "timeout_s": "1"}, conn).deliver(send)
    assert returned[0]["outcome"] == "messages" and recorded == ["MSG-INV-0001-1"]
    assert not messages.waiting


def test_missing_shell_call_has_a_bounded_grace_and_never_falls_back_to_run_end(tmp_path, monkeypatch):
    _, _, messages, conn, recorded = setup(tmp_path, open_call=False)
    monkeypatch.setattr(wait_binding, "CALL_GRACE_S", 0)
    with pytest.raises(errors.WaitOutsideAStep):
        messages.wait({"after": "", "timeout_s": "1"}, conn).deliver(lambda value: pytest.fail("unexpected result"))
    assert recorded == [] and not messages.waiting


def test_a_shell_call_arriving_in_the_grace_can_bind(tmp_path, monkeypatch):
    s, a, messages, conn, recorded = setup(tmp_path, open_call=False)

    class Grace:
        def is_set(self):
            return False

        def wait(self, seconds):
            assert messages.waiting
            a._wait_calls.event("session.step.started", {"assistantMessageID": "step"}, None)
            a._wait_calls.event("session.tool.called", {"assistantMessageID": "step", "id": "call"}, "shell")

    s._ending = Grace()
    result = []
    messages.wait({"after": "", "timeout_s": "1"}, conn).deliver(result.append)
    assert result[0]["outcome"] == "messages" and recorded == ["MSG-INV-0001-1"]


@pytest.mark.parametrize("timeout", ["nan", "inf", "-1", "89", "wrong"])
def test_worker_wait_refuses_unbounded_invalid_or_excessive_timeouts(tmp_path, timeout):
    _, _, messages, conn, recorded = setup(tmp_path)
    with pytest.raises(errors.UsageError):
        messages.wait({"after": "", "timeout_s": timeout}, conn)
    assert not messages.waiting and recorded == []


def test_no_production_adapter_opts_in_to_run_end_wait_binding():
    src = Path(__file__).resolve().parents[2] / "src" / "aew"
    for path in src.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                assert not any(isinstance(child, ast.Name) and child.id == "TEST_ONLY_WAIT_BINDS_TO_RUN_END"
                               and isinstance(child.ctx, ast.Store) for child in ast.walk(node)), path
