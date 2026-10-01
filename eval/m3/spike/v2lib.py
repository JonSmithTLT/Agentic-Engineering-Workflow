"""Disposable spike helpers for the OpenCode V2 re-baseline (M3 step 0).

Not product code. Stdlib only. Every server this module starts is a *private* `opencode-cli serve`
child with isolated XDG directories; it never talks to the user's Desktop background service.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PINNED_BIN = Path(os.environ.get("APPDATA", "")) / "ai.opencode.desktop" / "cli" / "2.0.18" / "opencode-cli.exe"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def isolated_env(root: Path, *, config: dict[str, Any] | None = None, extra: dict[str, str] | None = None,
                 password: str | None = None, disable_project: bool = True) -> dict[str, str]:
    """A server environment whose OpenCode state lives entirely under ``root``."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("AEW_") and not k.startswith("OPENCODE_")}
    for name in ("config", "data", "state", "cache"):
        d = root / f"xdg-{name}"
        d.mkdir(parents=True, exist_ok=True)
        env[f"XDG_{name.upper()}_HOME"] = str(d)
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    if disable_project:
        env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    if config is not None:
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
    if password is not None:
        env["OPENCODE_PASSWORD"] = password
    env.update(extra or {})
    return env


@dataclass
class Server:
    proc: subprocess.Popen
    url: str
    password: str
    started_s: float
    stderr_lines: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ http
    def _headers(self, auth: bool = True) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            h["Authorization"] = "Basic " + base64.b64encode(f"opencode:{self.password}".encode()).decode()
        return h

    def request(self, method: str, path: str, body: Any = None, params: dict[str, str] | None = None,
                auth: bool = True, timeout: float = 60) -> tuple[int, Any]:
        url = self.url.rstrip("/") + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self._headers(auth))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        if not raw:
            return status, None
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw.decode("utf-8", "replace")

    def get(self, path: str, **kw: Any) -> tuple[int, Any]:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> tuple[int, Any]:
        return self.request("POST", path, body=body if body is not None else {}, **kw)

    # ------------------------------------------------------------------ events
    def subscribe(self) -> "EventStream":
        return EventStream(self)

    # ------------------------------------------------------------------ lifecycle
    def close_lease(self, wait: float = 15) -> float | None:
        """Close stdin (the --stdio lease) and measure how long the server takes to exit."""
        t0 = time.perf_counter()
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=wait)
            return time.perf_counter() - t0
        except subprocess.TimeoutExpired:
            return None

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=15)


def start_server(env: dict[str, str], cwd: Path, *, stdio: bool = True, binary: Path = PINNED_BIN,
                 timeout: float = 60) -> Server:
    password = env.get("OPENCODE_PASSWORD") or secrets.token_urlsafe(24)
    env = {**env, "OPENCODE_PASSWORD": password}
    args = [str(binary), "serve", "--hostname", "127.0.0.1", "--port", "0"]
    if stdio:
        args.append("--stdio")
    t0 = time.perf_counter()
    proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    stderr_lines: list[str] = []
    threading.Thread(target=lambda: [stderr_lines.append(l.decode("utf-8", "replace").rstrip())
                                     for l in iter(proc.stderr.readline, b"")], daemon=True).start()
    deadline = time.time() + timeout
    url = None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited {proc.returncode}: {stderr_lines[-20:]}")
            continue
        text = line.decode("utf-8", "replace").strip()
        if stdio:
            try:
                url = json.loads(text)["url"]
                break
            except (ValueError, KeyError):
                continue
        elif "listening on" in text:
            url = text.split("listening on", 1)[1].strip()
            break
    if not url:
        proc.kill()
        raise RuntimeError(f"no server url within {timeout}s: {stderr_lines[-20:]}")
    # drain remaining stdout in the background so the pipe never blocks the server
    threading.Thread(target=lambda: [None for _ in iter(proc.stdout.readline, b"")], daemon=True).start()
    return Server(proc, url, password, time.perf_counter() - t0, stderr_lines)


class EventStream:
    """Background SSE reader for /api/event: frames go to a queue and to a list."""

    def __init__(self, server: Server) -> None:
        self.server = server
        self.frames: list[dict[str, Any]] = []
        self.q: queue.Queue[dict[str, Any]] = queue.Queue()
        self.connected = threading.Event()
        self.error: str | None = None
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        if not self.connected.wait(20):
            raise RuntimeError(f"event stream did not connect: {self.error}")

    def _run(self) -> None:
        req = urllib.request.Request(self.server.url.rstrip("/") + "/api/event",
                                     headers={**self.server._headers(), "Accept": "text/event-stream"})
        try:
            with urllib.request.urlopen(req, timeout=3600) as resp:
                buf: list[str] = []
                for raw in resp:
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.startswith("data:"):
                        buf.append(line[5:].lstrip())
                    elif line == "" and buf:
                        try:
                            frame = json.loads("\n".join(buf))
                        except ValueError:
                            frame = {"type": "_unparsed", "raw": "\n".join(buf)}
                        buf = []
                        frame["_t"] = time.perf_counter()
                        self.frames.append(frame)
                        self.q.put(frame)
                        self.connected.set()
        except Exception as exc:  # noqa: BLE001 - spike: record and stop
            self.error = repr(exc)
            self.connected.set()

    def wait_for(self, pred, timeout: float) -> dict[str, Any] | None:
        deadline = time.time() + timeout
        for f in list(self.frames):
            if pred(f):
                return f
        while time.time() < deadline:
            try:
                f = self.q.get(timeout=max(0.05, deadline - time.time()))
            except queue.Empty:
                return None
            if pred(f):
                return f
        return None


def new_id(prefix: str) -> str:
    """Client-chosen ids (the spec requires the prefix; the suffix is ours)."""
    return f"{prefix}_{secrets.token_hex(12)}"
