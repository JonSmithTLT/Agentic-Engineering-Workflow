"""One running dashboard: the session table, the HTTP server and the control channel together (design note §4.2).

``aew dashboard serve`` builds a :class:`Service`, authorizes at its terminal, starts it and waits. ``.aew/local/
dashboard/server.json`` records where the server is (pid, port, the control endpoint) and ``control.key`` the channel
key, for ``aew dashboard open`` and ``status`` to find it. ``local/`` is disposable and never authority (ADR-0011
invariant 4): the files locate a server; the operator's console authorizes.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from aew.dashboard.control import Console, ControlServer
from aew.dashboard.server import DashboardServer
from aew.dashboard.session import DEFAULT_HOURS, SessionTable
from aew.engine.api import Engine
from aew.errors import UsageError
from aew.harness import procs
from aew.knowledge.manifest import load_manifest
from aew.util import atomic_write, utc_now

DEFAULT_PORT = 4280
DIR_REL = "local/dashboard"
SERVER_JSON_REL = f"{DIR_REL}/server.json"
KEY_REL = f"{DIR_REL}/control.key"


class Service:
    """Binds on construction (so an occupied port fails before any operator prompt), serves after ``start``."""

    def __init__(self, engine: Engine, *, port: int = DEFAULT_PORT, hours: int = DEFAULT_HOURS,
                 console: Console | None, clock: Any = utc_now, validate_with: Any = None) -> None:
        self.engine = engine
        self.project_id = str(load_manifest(engine.aew_root)["project"]["id"])
        try:
            generation = int(engine.store.read_committed()["lead"]["generation"])
        except Exception:  # noqa: BLE001 (provenance only: the session carries no Lead authority)
            generation = 0
        self.table = SessionTable(self.project_id, hours=hours, clock=clock, generation=generation)
        try:
            self.server = DashboardServer(engine, authenticator=self.table, sessions=self.table, port=port,
                                          validate_with=validate_with)
        except OSError as exc:
            raise UsageError(f"the dashboard cannot listen on 127.0.0.1:{port} ({exc.strerror or exc}); it never moves "
                             "to another port by itself: pass --port N for a different one, or --port 0 for an "
                             "ephemeral port", port=port) from None
        self.control = ControlServer(self.table, url_for_code=self.url_for_code, console=console, status=self.status)
        self.started_at: str | None = None
        self._stop = threading.Event()

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def url(self) -> str:
        return self.server.url

    def url_for_code(self, code: str) -> str:
        return f"{self.url}/session/{code}"

    def start(self) -> None:
        """Serve and record the endpoint under ``local/``. Sessions are issued separately (``issue``)."""
        self.started_at = utc_now()
        self.server.start()
        self.control.start()
        self._write_endpoint()

    def issue(self) -> str:
        """Mint a session; its one-time URL."""
        return self.url_for_code(self.table.mint())

    def status(self) -> dict[str, Any]:
        return {"running": True, "pid": os.getpid(), "port": self.port, "url": self.url, "project": self.project_id,
                "started_at": self.started_at, "session_hours": self.table.hours, "sessions": self.table.live(),
                "pending_urls": self.table.pending_codes}

    def wait(self) -> None:
        """Block until ``stop`` (or a KeyboardInterrupt reaches the caller)."""
        while not self._stop.wait(0.5):
            pass

    def stop(self) -> None:
        """End every session (the table dies), close both listeners, remove the endpoint files."""
        self._stop.set()
        self.table.clear()
        self.control.close()
        self.server.stop()
        self._remove_endpoint()

    def close(self) -> None:
        """Give up before serving (the operator refused): nothing was issued, nothing is recorded."""
        self._stop.set()
        self.table.clear()
        self.control.close()
        self.server.httpd.server_close()

    # ------------------------------------------------------------------ the endpoint files

    def _write_endpoint(self) -> None:
        root = self.engine.aew_root
        (root / DIR_REL).mkdir(parents=True, exist_ok=True)
        key_path = root / KEY_REL
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self.control.key_hex + "\n")
        pid = os.getpid()
        atomic_write(root / SERVER_JSON_REL, json.dumps({
            "schema": "aew/dashboard-endpoint/v1", "pid": pid, "started_by": procs.started_at(pid),
            "started_at": self.started_at, "port": self.port, "url": self.url, "project": self.project_id,
            "control": {"endpoint": self.control.address, "key_file": KEY_REL},
        }, indent=2) + "\n")

    def _remove_endpoint(self) -> None:
        for rel in (SERVER_JSON_REL, KEY_REL):
            try:
                (self.engine.aew_root / rel).unlink()
            except OSError:
                pass


def locate(aew_root: Path) -> dict[str, Any] | None:
    """The running server this project's ``local/dashboard/server.json`` names, with its control key, or ``None``
    when there is none (no file, or the recorded process is gone: a stale file is never trusted)."""
    try:
        info = json.loads((aew_root / SERVER_JSON_REL).read_text(encoding="utf-8"))
        key = (aew_root / KEY_REL).read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict) or not isinstance(info.get("pid"), int):
        return None
    started_by = info.get("started_by")
    alive = (procs.same_process(info["pid"], float(started_by)) if isinstance(started_by, (int, float))
             else procs.pid_alive(info["pid"]))
    if not alive:
        return None
    endpoint = (info.get("control") or {}).get("endpoint")
    if not isinstance(endpoint, str) or not key:
        return None
    return {"pid": info["pid"], "port": info.get("port"), "url": info.get("url"), "started_at": info.get("started_at"),
            "project": info.get("project"), "endpoint": endpoint, "key": key}
