"""The dashboard tests' request helper (tests/helpers/dashboard_client.py; register E75): an answer that is not the
dashboard's fails with what held the port, and the diagnostics never hide the mismatch. Served by planted listeners:
the dashboard's real answers pass through it in every dashboard API test."""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import threading
from collections.abc import Iterator

import dashboard_client as D
import pytest

from aew.dashboard.server import SECURITY_HEADERS

R21 = "".join(f"{name}: {value}\r\n" for name, value in SECURITY_HEADERS)
JSON_OK = ("HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: 11\r\n" + R21
           + "Connection: close\r\n\r\n").encode() + b'{"ok":true}'
# What the probe's leaked upstream answered on CI: 200, text/plain, and a 32-hex token
TOKEN = ("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 32\r\nConnection: close\r\n\r\n"
         + "0123456789abcdef" * 2).encode()


@contextlib.contextmanager
def answering(response: bytes) -> Iterator[int]:
    """A loopback listener that answers every request with ``response``, then closes: its port."""
    listener = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(5)
                with contextlib.suppress(OSError):
                    buf = b""
                    while b"\r\n\r\n" not in buf and (data := conn.recv(4096)):
                        buf += data
                    conn.sendall(response)
                    conn.shutdown(socket.SHUT_WR)
                    conn.recv(1)  # until the client is done with it: the diagnostics run while it is open

    thread = threading.Thread(target=serve, name="flake-planted-listener", daemon=True)
    thread.start()
    try:
        yield listener.getsockname()[1]
    finally:
        stop.set()
        with contextlib.suppress(OSError):
            listener.shutdown(socket.SHUT_RDWR)  # wakes the accept, on Linux
        listener.close()
        thread.join(5)


@pytest.mark.parametrize("response", [
    JSON_OK,
    ("HTTP/1.1 304 Not Modified\r\nETag: \"e\"\r\n" + R21 + "\r\n").encode(),  # a 304 has no body and no type
], ids=["json", "not_modified"])
def test_the_dashboards_answer_passes_as_it_came(response):
    with answering(response) as port:
        status, headers, body = D.request(port, "GET", "/api/v1/runs")
    assert status in (200, 304) and headers["x-frame-options"] == "DENY"
    assert body == (b'{"ok":true}' if status == 200 else b"")


def test_the_probes_token_fails_naming_its_mismatch_and_what_held_the_port():
    with answering(TOKEN) as port, pytest.raises(AssertionError) as exc:
        D.request(port, "HEAD", "/api/v1/maps")
    text = str(exc.value)
    first = text.splitlines()[0]
    assert first.startswith(f"the answer on 127.0.0.1:{port} to HEAD /api/v1/maps is not the dashboard's")
    assert "lacks the dashboard's R21 headers" in first
    assert "this client's local port: " in text and "flake-planted-listener" in text
    if sys.platform == "linux":  # the planted listener is this process's: ss names it, with this pid
        listening = next(line for line in text.splitlines() if line.startswith(f"listening on :{port}"))
        assert f":{port}" in listening.split(": ", 1)[1] and f"pid={os.getpid()}," in listening, listening
        local = next(line for line in text.splitlines() if line.startswith("this client's local port: ")).split()[-1]
        # recorded while this end of the connection was open: the client's own socket, with this pid
        assert any(f"127.0.0.1:{local} " in line and f"pid={os.getpid()}," in line for line in text.splitlines()), text
        assert "socket inodes: fd " in text and D.NO_OWNER in text
    elif sys.platform == "win32":  # netstat's rows for the port, the listening one with this pid
        assert any("LISTENING" in line and line.split()[-1] == str(os.getpid()) for line in text.splitlines()), text
        assert D.SHARED in text


@pytest.mark.parametrize(("response", "says"), [
    (JSON_OK.replace(b"application/json", b"text/html"), "its Content-Type is 'text/html; charset=utf-8'"),
    (JSON_OK.replace(b"Content-Type: application/json; charset=utf-8\r\n", b""), "its Content-Type is None"),
    (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}", "lacks the dashboard's R21 headers"),
    (JSON_OK.replace(b"X-Frame-Options: DENY\r\n", b""), "lacks the dashboard's R21 headers ['X-Frame-Options']"),
], ids=["wrong_type", "no_type", "nothing_of_the_dashboards", "one_header_missing"])
def test_an_answer_without_the_dashboards_marks_fails(response, says):
    with answering(response) as port, pytest.raises(AssertionError, match="is not the dashboard's") as exc:
        D.request(port, "GET", "/api/v1/runs")
    assert says in str(exc.value).splitlines()[0]


def test_a_diagnostic_that_fails_is_reported_and_never_hides_the_mismatch(monkeypatch):
    def broken(argv):
        raise OSError("no such command")

    monkeypatch.setattr(D, "_run", broken)
    monkeypatch.setattr(D, "_own_socket_inodes", lambda: 1 / 0)
    with answering(TOKEN) as port, pytest.raises(AssertionError) as exc:
        D.request(port, "GET", "/api/v1/runs")
    lines = str(exc.value).splitlines()
    assert "is not the dashboard's" in lines[0]
    if sys.platform in ("linux", "win32"):
        assert any("could not be read (OSError: no such command)" in line for line in lines), lines


def test_a_command_that_does_not_finish_is_killed_at_its_bound(monkeypatch):
    monkeypatch.setattr(D, "COMMAND_TIMEOUT_S", 0.5)
    assert D._run([sys.executable, "-c", "import time; time.sleep(30)"]) == "(no answer in 0.5s: killed)"
    assert D._run([sys.executable, "-c", "print('held')"]) == "held"
