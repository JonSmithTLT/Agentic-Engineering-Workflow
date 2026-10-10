"""A standard-library client for one private OpenCode V2 server (ADR-0009).

The server is ``opencode-cli serve --stdio --hostname 127.0.0.1 --port 0``, started inside the run's
process tree with a random password. It prints one ``{"url": ...}`` line and serves the V2 HTTP API
(basic auth ``opencode:<password>``) until its stdin closes. ``--stdio`` removes the password from the
server's own environment, so nothing the server starts can call its API. AEW uses that lease when it is
there but does not depend on it: the supervisor's process tree ends the server either way.

The event stream (``GET /api/event``) is volatile and has no replay. It is used only to react quickly
and to record telemetry. Completion and every other decision are read from the REST API, so losing the
stream never looks like anything having happened.
"""

from __future__ import annotations

import base64
import http.client
import json
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew.errors import HarnessLaunchFailed

START_TIMEOUT_S = 60.0
LOOPBACK_URL = re.compile(r"http://127\.0\.0\.1:[0-9]{1,5}/?")
REQUEST_TIMEOUT_S = 30.0
EVENT_CONNECT_S = 10.0  # how long a launch waits for the event stream's first connection


class OpenCodeError(Exception):
    """A non-2xx reply from the server."""

    def __init__(self, method: str, path: str, status: int, body: Any) -> None:
        detail = body.get("message") if isinstance(body, dict) else body
        super().__init__(f"{method} {path} -> {status}: {str(detail)[:300]}")
        self.status = status
        self.body = body


class OpenCodeUnavailable(Exception):
    """The server could not be reached (not started, exited, or the connection broke)."""


class Client:
    def __init__(self, url: str, password: str) -> None:
        self.url = url.rstrip("/")
        self._auth = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()

    def headers(self, accept: str = "application/json") -> dict[str, str]:
        return {"Authorization": self._auth, "Accept": accept, "Content-Type": "application/json"}

    def request(self, method: str, path: str, body: Any = None, params: dict[str, str] | None = None,
                timeout: float = REQUEST_TIMEOUT_S) -> Any:
        url = self.url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self.headers())  # noqa: S310
        try:  # self.url is the run's own server, checked to be http://127.0.0.1:<port> when it started
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed: Any = json.loads(raw) if raw else None
            except ValueError:
                parsed = raw.decode("utf-8", "replace")
            raise OpenCodeError(method, path, exc.code, parsed) from None
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError, OSError) as exc:
            # HTTPException: e.g. IncompleteRead, when the server dies mid-reply
            raise OpenCodeUnavailable(f"{method} {path}: {type(exc).__name__}: {exc}") from None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw.decode("utf-8", "replace")

    def get(self, path: str, params: dict[str, str] | None = None, **kw: Any) -> Any:
        return self.request("GET", path, params=params, **kw)

    def post(self, path: str, body: Any = None, params: dict[str, str] | None = None, **kw: Any) -> Any:
        return self.request("POST", path, body={} if body is None else body, params=params, **kw)

    def put(self, path: str, body: Any, **kw: Any) -> Any:
        return self.request("PUT", path, body=body, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)


def location(directory: str) -> dict[str, str]:
    """The ``location`` query parameter of instance routes, as the server's schema encodes it."""
    return {"location[directory]": directory}


class Server:
    """One private ``serve --stdio`` process, started by the caller's spawner (the run's process tree)."""

    def __init__(self, proc: subprocess.Popen[bytes], url: str, password: str, started_s: float) -> None:
        self.proc = proc
        self.url = url
        self.password = password
        self.started_s = started_s
        self.client = Client(url, password)

    @classmethod
    def start(cls, spawn: Callable[..., subprocess.Popen[bytes]], command: list[str], *, env: dict[str, str],
              cwd: str, log_path: Path, timeout: float = START_TIMEOUT_S) -> Server:
        """Start the server and read its ``{"url"}`` line. ``env`` must already hold ``OPENCODE_PASSWORD``."""
        argv = [*command, "serve", "--stdio", "--hostname", "127.0.0.1", "--port", "0"]
        t0 = time.monotonic()
        with log_path.open("ab") as log:
            proc = spawn(argv, env=env, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
        lines: queue.Queue[bytes | None] = queue.Queue()

        def pump() -> None:
            assert proc.stdout is not None
            for raw in iter(proc.stdout.readline, b""):
                lines.put(raw)
            lines.put(None)

        threading.Thread(target=pump, name="aew-opencode-stdout", daemon=True).start()
        deadline = t0 + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HarnessLaunchFailed(f"the OpenCode server printed no address within {timeout:.0f}s "
                                          f"(see {log_path.name})")
            try:
                raw = lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if raw is None:
                code = proc.wait(timeout=10)
                raise HarnessLaunchFailed(f"the OpenCode server exited ({code}) before serving "
                                          f"(see {log_path.name})")
            try:
                url = json.loads(raw.decode("utf-8", "replace"))["url"]
            except (ValueError, KeyError, TypeError):
                continue  # anything else the server prints before its address
            if not LOOPBACK_URL.fullmatch(str(url)):  # the password goes there: only the loopback server we started
                proc.kill()
                raise HarnessLaunchFailed(f"the OpenCode server announced {str(url)[:80]!r}, not an http://127.0.0.1 "
                                          "address; refusing to send it the server password")
            # The rest of stdout keeps draining in the pump thread, so the pipe never blocks the server.
            return cls(proc, str(url), env["OPENCODE_PASSWORD"], time.monotonic() - t0)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self, wait_s: float = 5.0) -> int | None:
        """End the lease (stdin EOF) and give the server a moment to exit on its own."""
        try:
            if self.proc.stdin is not None:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            return self.proc.wait(timeout=wait_s)
        except subprocess.TimeoutExpired:
            return None


class EventStream:
    """Background reader of ``GET /api/event`` that reconnects while the server lives.

    ``on_event`` receives every decoded frame. A dropped stream is counted and re-opened; it never
    implies completion (the adapter decides that from the REST API).
    """

    def __init__(self, client: Client, on_event: Callable[[dict[str, Any]], None],
                 alive: Callable[[], bool]) -> None:
        self.client = client
        self.on_event = on_event
        self.alive = alive
        self.connected = threading.Event()
        self.drops = 0
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._run, name="aew-opencode-events", daemon=True)

    def start(self, wait_s: float = EVENT_CONNECT_S) -> None:
        self._thread.start()
        self.connected.wait(wait_s)

    def close(self) -> None:
        self._stop.set()
        self._drop()

    def _drop(self) -> None:
        """Break the current connection (also used by tests to simulate a lost stream).

        The socket is shut down, not the response closed: closing a buffered response from another thread
        waits for the lock its blocked reader holds."""
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _run(self) -> None:
        backoff = 0.2
        target = urllib.parse.urlsplit(self.client.url)
        while not self._stop.is_set() and self.alive():
            try:
                conn = http.client.HTTPConnection(target.hostname or "127.0.0.1", target.port, timeout=30)
                conn.request("GET", "/api/event", headers=self.client.headers("text/event-stream"))
                resp = conn.getresponse()
                if resp.status != 200:
                    raise OpenCodeUnavailable(f"event stream refused: {resp.status}")
                self._sock = conn.sock
                if conn.sock is not None:
                    conn.sock.settimeout(None)  # a quiet stream is normal; liveness comes from the REST polls
                self.connected.set()
                backoff = 0.2
                self._read(resp)
            except Exception as exc:  # noqa: BLE001 - any stream failure: record, reconnect
                self.last_error = f"{type(exc).__name__}: {exc}"
            if self._stop.is_set():
                return
            self.drops += 1
            self.connected.set()  # a failed first connect must not block start()
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 5.0)

    def _read(self, resp: Any) -> None:
        buf: list[str] = []
        for raw in resp:
            if self._stop.is_set():
                return
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("data:"):
                buf.append(line[5:].lstrip())
            elif line == "" and buf:
                text, buf = "\n".join(buf), []
                try:
                    frame = json.loads(text)
                except ValueError:
                    continue
                if isinstance(frame, dict):
                    self.on_event(frame)
        raise OpenCodeUnavailable("event stream ended")
