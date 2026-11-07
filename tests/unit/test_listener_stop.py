"""Stopping a keyed listener never waits forever (the 2026-10-08 CI hangs).

The dashboard's control channel woke its serving thread with a keyed connection to itself. When the serving thread
had already left its loop between two accepts, nobody answered that connection's handshake, and ``close`` (so the
dashboard server's ``stop``, and the test calling it) waited forever. The credential bridge shares the serve loop and
the wake (``aew.harness.bridge.serve_listener`` and ``stop_listener``)."""

from __future__ import annotations

import threading
import time
from multiprocessing.connection import Client, Listener
from typing import Any

import pytest

from aew.dashboard import control
from aew.dashboard.session import SessionTable
from aew.harness import bridge


def _returns_within(fn: Any, limit: float) -> float:
    done = threading.Event()
    started = time.monotonic()

    def run() -> None:
        fn()
        done.set()

    threading.Thread(target=run, daemon=True).start()
    assert done.wait(limit), f"{fn} was still waiting after {limit}s"
    return time.monotonic() - started


def _a_thread_that_will_never_accept() -> tuple[threading.Thread, threading.Event]:
    release = threading.Event()
    thread = threading.Thread(target=release.wait, daemon=True)
    thread.start()
    return thread, release


def test_closing_the_control_channel_never_waits_on_a_serving_thread_that_will_not_accept(monkeypatch):
    """The race's end state, made deterministic: the serving thread is alive but will never accept again."""
    monkeypatch.setattr(bridge, "WAKE_TIMEOUT_S", 0.5)
    server = control.ControlServer(SessionTable("p"), url_for_code=lambda code: code, console=None,
                                   status=lambda: {})
    thread, release = _a_thread_that_will_never_accept()
    server._thread = thread  # it never calls accept(): the wake's handshake has nobody to answer it
    try:
        took = _returns_within(server.close, 30)
    finally:
        release.set()
    assert took < 10, took
    with pytest.raises(OSError):  # the endpoint is gone: a later client is refused, never left waiting
        Client(server.address, family=server._family, authkey=server.key)


def test_closing_the_bridge_releases_its_endpoint_even_when_the_serving_thread_will_not_accept(monkeypatch):
    monkeypatch.setattr(bridge, "WAKE_TIMEOUT_S", 0.5)
    server = bridge.BridgeServer(lambda op, args: None)
    thread, release = _a_thread_that_will_never_accept()
    server._thread = thread
    try:
        server.close()  # never blocks its caller; the wake runs on its own thread
        deadline = time.monotonic() + 30
        while server.private_dir and time.monotonic() < deadline and _exists(server.private_dir):
            time.sleep(0.05)
        assert not (server.private_dir and _exists(server.private_dir)), "the bridge's endpoint was never removed"
    finally:
        release.set()


STOP_DELAY_S = 0.5  # E128's race point: the stop still running when close() has returned, injected


def _a_delayed_stop(monkeypatch: Any) -> None:
    real = bridge.stop_listener

    def delayed(*args: Any, **kwargs: Any) -> None:
        time.sleep(STOP_DELAY_S)
        real(*args, **kwargs)

    monkeypatch.setattr(bridge, "stop_listener", delayed)


def test_a_closed_bridge_whose_owner_waits_is_stopped_with_its_endpoint_removed(monkeypatch):
    """E128: close() returns before its stop has run, so an owner that exits next left the stop on a daemon thread and
    the private directory behind. ``wait_stopped`` waits for it, within WAKE_TIMEOUT_S."""
    _a_delayed_stop(monkeypatch)
    server = bridge.BridgeServer(lambda op, args: None)
    server.start()
    server.close()
    assert server._stopper.is_alive()  # the delay holds the stop: close() did not wait
    assert server.wait_stopped() is True
    assert not server._stopper.is_alive()
    assert not (server.private_dir and _exists(server.private_dir)), "the wait returned before the endpoint went"
    with pytest.raises(OSError):  # the endpoint is gone
        Client(server.address, family="AF_PIPE" if bridge.IS_WINDOWS else "AF_UNIX", authkey=server.key)
    server._thread.join(5)
    assert not server._thread.is_alive()


def test_waiting_for_a_bridge_stop_is_bounded(monkeypatch):
    """A stop that does not finish never holds its owner past the bound; the stop goes on, on its own thread."""
    monkeypatch.setattr(bridge, "WAKE_TIMEOUT_S", 0.2)
    release = threading.Event()
    real = bridge.stop_listener
    monkeypatch.setattr(bridge, "stop_listener", lambda *a, **k: (release.wait(30), real(*a, **k)))
    server = bridge.BridgeServer(lambda op, args: None)
    server.start()
    try:
        server.close()
        assert _returns_within(lambda: server.wait_stopped(), 10) < 5
        assert server.wait_stopped(0) is False
    finally:
        release.set()
    assert server.wait_stopped(10) is True


def test_a_bridge_never_closed_has_no_stop_to_wait_for():
    server = bridge.BridgeServer(lambda op, args: None)
    try:
        assert server.wait_stopped(0) is False
    finally:
        server.close()
        server.wait_stopped()


def _exists(path: str) -> bool:
    import os

    return os.path.exists(path)


@pytest.mark.parametrize("round_", range(25))
def test_a_control_channel_closed_right_after_a_request_stops_promptly(round_):
    """The original race, run for real: a request is served, and close() follows at once, while the serving thread is
    between accepts. Every close returns promptly, and the serving thread ends."""
    server = control.ControlServer(SessionTable("p"), url_for_code=lambda code: code, console=None,
                                   status=lambda: {"ok": True})
    server.start()
    conn = control._connect(server.address, server.key_hex)
    try:
        conn.send_bytes(b'{"op": "status", "args": {}}')
        assert control._reply(conn) == {"ok": True}
    finally:
        conn.close()
    assert _returns_within(server.close, 30) < 10
    server._thread.join(10)
    assert not server._thread.is_alive()


def test_serve_listener_returns_only_after_an_accept_once_closed():
    """The loop observes the closure only after an accept, so the wake connection always has a taker."""
    import os
    import tempfile

    directory = tempfile.mkdtemp()
    address = os.path.join(directory, "s") if os.name != "nt" else r"\\.\pipe\aew-test-" + os.urandom(8).hex()
    family = "AF_UNIX" if os.name != "nt" else "AF_PIPE"
    key = os.urandom(32)
    listener = Listener(address, family=family, authkey=key)
    closed = threading.Event()
    handled: list[Any] = []
    serving = threading.Thread(target=bridge.serve_listener, args=(listener, closed, handled.append), daemon=True)
    serving.start()
    closed.set()  # set before any connection: the loop must still be waiting in accept, not gone
    time.sleep(0.2)
    assert serving.is_alive()
    took = _returns_within(lambda: bridge.stop_listener(listener, address, family, key, directory, serving=serving),
                           30)
    assert took < 5, took  # the wake was accepted at once, not left to the bound
    serving.join(5)
    assert not serving.is_alive() and handled == []
