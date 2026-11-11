"""Real CLI/bridge EOF, cooperative requests and parallel-call lifetime; no runtime/provider qualification.

The adapter receives the production event vocabulary directly here. Fake-V2 supervisor/fidelity tests separately
prove those open calls are reached through actual server events; no production adapter opts into a run-end binding.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
from message_wait_adapter import FakeWaitOpenCodeAdapter
from notifier import until
from test_coordination_store import world

from aew.engine.api import Engine
from aew.harness import agentenv, bridge, worker_messages


def event(adapter, kind, **fields):
    adapter._on_event({"type": "session." + kind,
                       "data": {"sessionID": "session-test", "assistantMessageID": "step-1", **fields}})


@pytest.mark.parametrize("end", ["eof", "bridge_close", "parallel_call", "grace", "outside"])
def test_a_pending_real_cli_wait_releases_its_hold_on_connection_or_call_end_and_blocks_no_other_request(
        tmp_path, monkeypatch, end):
    w = world(tmp_path)
    e = Engine.discover(w.root)
    adapter = FakeWaitOpenCodeAdapter(SimpleNamespace(), tmp_path, lambda value: None)
    adapter.session = "session-test"

    def open_calls():
        event(adapter, "step.started")
        for call in ("one", "two"):
            event(adapter, "tool.input.started", id=call, name="shell")
            event(adapter, "tool.called", id=call)

    if end not in ("grace", "outside"):
        open_calls()
    binding = adapter.wait_binding()
    assert (binding is None) == (end in ("grace", "outside"))
    empty_snapshots = []
    if end == "grace":
        original = adapter.wait_binding

        def late_call():
            found = original()
            if found is None:
                empty_snapshots.append(True)
                open_calls()  # arrives after the first empty snapshot; the next grace iteration must bind it
            return found

        monkeypatch.setattr(adapter, "wait_binding", late_call)
    owner = SimpleNamespace(adapter=adapter, _ending=threading.Event(), _credential=w.worker, engine=e,
                            events=lambda value: None, run="R-INV-0001-1",
                            require_message_authority=lambda: e.invocation_whoami(invocation_token=w.worker))
    selections = []
    deliver = e.message_deliver_wait

    def selecting(**kwargs):
        selections.append(True)
        return deliver(**kwargs)

    monkeypatch.setattr(e, "message_deliver_wait", selecting)
    messages = worker_messages.WorkerMessages(owner)
    owner.bridge = server = bridge.BridgeServer(
        lambda op, args: e.invocation_whoami(invocation_token=w.worker),
        operations=bridge.OPERATIONS | bridge.MESSAGE_OPERATIONS, cooperative=frozenset({"message.wait"}),
        connection_handlers={"message.wait": messages.wait})
    server.start()
    env = agentenv.build(os.environ, endpoint=server.address, key_hex=server.key_hex,
                         invocation=w.inv, run=owner.run, work_unit=w.wid)
    env["AEW_MESSAGING"] = "enabled"
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    argv = [sys.executable, "-B", "-m", "aew", "-C", str(w.root), "message", "wait", "--timeout", "20"]
    child = subprocess.Popen(argv,
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    try:
        if end == "outside":
            _, err = child.communicate(timeout=10)
            assert child.returncode != 0 and json.loads(err)["error"]["code"] == "WAIT_OUTSIDE_A_STEP"
            assert not selections
        else:
            until(lambda: messages.waiting, timeout=10)
            until(lambda: bool(selections), timeout=10)  # actual wait reached the real engine's selector
            other = subprocess.run([sys.executable, "-B", "-m", "aew", "-C", str(w.root), "whoami"],
                                   env=env, capture_output=True, timeout=10, **kwargs)
            assert other.returncode == 0 and json.loads(other.stdout)["invocation"] == w.inv
            assert messages.waiting and child.poll() is None
            if end in ("eof", "grace"):
                if end == "grace":
                    assert empty_snapshots == [True]
                    binding = adapter.wait_binding()
                    assert binding is not None
                child.kill()  # only the client dies; both foreground shell calls remain open in the adapter
            elif end == "bridge_close":
                server.close()
            else:
                event(adapter, "tool.success", id="one")
                assert adapter.open_shell_calls() == ["two"]
            out, err = child.communicate(timeout=10)
            if end not in ("eof", "grace"):
                assert child.returncode == 0 and json.loads(out)["outcome"] == "ended_early", err
        until(lambda: not messages.waiting, timeout=10)
        if end in ("eof", "grace"):
            assert adapter.wait_binding_valid(binding)  # EOF alone released the hold, not a step/run end
        mid = w.send()["message"]["id"]
        assert [m["id"] for m in e.message_waiting(invocation_token=w.worker, after="")["messages"]] == [mid]
        assert not any(f["kind"] == "DELIVERED" for f in e.message_thread(w.inv)["messages"][0]["facts"])
    finally:
        owner._ending.set()
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=10)
        server.close()
        assert server.wait_stopped()
