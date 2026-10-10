"""The OpenCode client's calls to the run's own loopback server never go through a proxy.

Behind HTTP_PROXY (or HTTPS_PROXY, ALL_PROXY, either case) with no NO_PROXY exception for 127.0.0.1, ``urlopen``'s
default opener sent the client's REST calls to the proxy, and every launch failed. The REST client and the event
stream are both checked against a dead proxy (they still reach the server) and a recording one (it sees nothing).
"""

from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from proxy_env import RecordingProxy, dead_proxy, proxy_env

from aew.harness.opencode.client import Client, EventStream


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api/event":
            frame = b'data: {"type": "server.connected"}\n\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return
        body = json.dumps({"path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        body = json.dumps({"echo": json.loads(raw or b"null")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    """A local stand-in for the run's OpenCode server, at http://127.0.0.1:<port>."""
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _behind(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    for name, value in proxy_env(url).items():
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


def _use(url: str) -> list[dict[str, Any]]:
    """What a run does with its server: REST calls, and the event stream."""
    client = Client(url, "pw")
    assert client.get("/api/info") == {"path": "/api/info"}
    assert client.post("/api/session", {"title": "t"}) == {"echo": {"title": "t"}}
    frames: list[dict[str, Any]] = []
    got = threading.Event()

    def on_event(frame: dict[str, Any]) -> None:
        frames.append(frame)
        got.set()

    stream = EventStream(client, on_event, alive=lambda: True)
    stream.start()
    try:
        assert got.wait(10), f"the event stream never delivered a frame ({stream.last_error})"
    finally:
        stream.close()
    return frames


def test_the_client_reaches_its_loopback_server_when_every_proxy_variable_points_at_a_dead_proxy(server, monkeypatch):
    with dead_proxy() as proxy:
        _behind(monkeypatch, proxy)
        assert _use(server)[0] == {"type": "server.connected"}


def test_no_loopback_call_ever_reaches_a_configured_proxy(server, monkeypatch):
    with RecordingProxy() as proxy:
        _behind(monkeypatch, proxy.url)
        _use(server)
    assert (proxy.connections, proxy.request_lines) == (0, [])
