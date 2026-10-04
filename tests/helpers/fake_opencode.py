"""A fake OpenCode V2 server for CI: the real OpenCode adapter, supervisor and bridge, and a scripted "model".

Started exactly like ``opencode-cli serve --stdio --hostname 127.0.0.1 --port 0``: it prints one
``{"url"}`` line, requires basic auth with ``OPENCODE_PASSWORD`` (and removes it from its own environment,
as ``--stdio`` does), and exits when its stdin closes. It serves the operations the adapter uses, with
V2's shapes, and its ``/openapi.json`` is the real 2.0.18 document (trimmed).

Its "model" runs the run's fake-agent script. Each step is one tool call, executed as
``fake_agent.py --step-file`` with **the session's shell environment when one was PUT, else the server's
own environment**, which is V2's rule. An adapter that forgot to curate the environment would leak the
server's provider secret, and the conformance scenarios would catch it.

Behaviour comes from the same script files as the fake harness (``<scripts>/<run>.json`` |
``<invocation>.json`` | ``default.json``): a list of steps, or ``{"steps", "effective", "health", "server"}``.
``server`` knobs: ``catalog_delay_s`` (counted from the first catalog request, not from server start, so a
slow start cannot eat into it), ``models``, ``openapi_drop`` (``["METHOD /path", ...]``), ``version``,
``ignore_config`` (load no configured agent), ``agent_override`` (fields that differ from the projection),
``appended_rules`` (rules the server appends after the agent's own, as 2.0.22 appends ``browser: deny``),
``stored_credentials`` (serve 2.0.22's ``GET /api/credential`` with these entries),
``subagent`` (the model starts a child session, as V2's subagent tool would),
``drop_events_every`` (close each event connection after N frames), ``ask`` (a permission request before
the first step), ``form`` (a form before the first step), ``queue_gap_s`` (pause at the end of a turn,
before its queued prompts are taken).

Run as ``opencode --standalone <dir>`` (what ``aew opencode`` starts) it is the Lead's TUI: its "model" runs
``<scripts>/lead-tui.json`` with the TUI's own environment, which a V2 ``--standalone`` TUI sends as every
session's shell environment, and records the steps in ``<scripts>/lead-tui.jsonl``.
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
AGENT = HERE / "fake_agent.py"
SPEC = HERE.parent / "fixtures" / "opencode" / "openapi-2.0.18.min.json"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
DEFAULT_MODELS = [
    {"id": "fake-model", "modelID": "fake-model", "providerID": "fakeprov", "name": "Fake", "enabled": True,
     "variants": [{"id": "low"}, {"id": "medium"}, {"id": "high"}]},
    {"id": "cheaper-model", "modelID": "cheaper-model", "providerID": "other", "name": "Cheaper", "enabled": True,
     "variants": []},
]


def now_ms() -> float:
    return time.time() * 1000


TOOL_INPUT = "fake-tool-input-must-not-be-logged"


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


class Session:
    def __init__(self, info: dict[str, Any]) -> None:
        self.info = info
        self.env: dict[str, str] | None = None
        self.messages: list[dict[str, Any]] = []
        self.inbox: list[dict[str, Any]] = []
        self.running = False
        self.interrupted = threading.Event()
        self.contract_done = False
        self.proc: subprocess.Popen[bytes] | None = None
        self.permissions: dict[str, dict[str, Any]] = {}
        self.replies: dict[str, str] = {}
        self.forms: dict[str, dict[str, Any]] = {}


class FakeOpenCode:
    def __init__(self, scripts: Path) -> None:
        self.catalog_asked: float | None = None
        self.data_home = Path(os.environ["XDG_DATA_HOME"])
        self.state = self.data_home.parent            # <run>/harness
        self.run = self.state.parent.name             # R-<INV>-<n>
        inv = self.run.rsplit("-", 1)[0][2:]
        path = next((p for p in (scripts / f"{self.run}.json", scripts / f"{inv}.json", scripts / "default.json")
                     if p.exists()), None)
        spec = json.loads(path.read_text(encoding="utf-8")) if path else []
        self.steps: list[dict[str, Any]] = spec["steps"] if isinstance(spec, dict) else spec
        self.effective: list[dict[str, Any]] | None = spec.get("effective") if isinstance(spec, dict) else None
        self.knobs: dict[str, Any] = (spec.get("server") if isinstance(spec, dict) else None) or {}
        if isinstance(spec, dict) and spec.get("health") == "incompatible":
            self.knobs.setdefault("openapi_drop", ["PUT /api/session/{sessionID}/environment"])
        self.password = os.environ.pop("OPENCODE_PASSWORD", "")
        os.environ.pop("OPENCODE_SERVER_PASSWORD", None)
        self.sessions: dict[str, Session] = {}
        self.lock = threading.RLock()
        self.persist_lock = threading.Lock()
        self.listeners: list[queue.Queue[dict[str, Any] | None]] = []
        (self.data_home / "opencode").mkdir(parents=True, exist_ok=True)
        # What the server was started with, for tests: variable NAMES (never values), the projection, the flags.
        started = {"env_names": sorted(os.environ), "config": json.loads(os.environ.get("OPENCODE_CONFIG_CONTENT")
                                                                        or "null"),
                   "flags": {k: os.environ.get(k) for k in ("OPENCODE_DISABLE_PROJECT_CONFIG",
                                                             "OPENCODE_DISABLE_AUTOUPDATE", "XDG_CONFIG_HOME",
                                                             "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
                                                             "TEMP")},
                   "cwd": os.getcwd()}
        (self.data_home.parent / "fake-server.json").write_text(json.dumps(started, indent=1), encoding="utf-8")
        self.config = started["config"] or {}

    # ------------------------------------------------------------------ persistence and events

    def persist(self) -> None:
        with self.lock:
            db = json.loads(json.dumps({sid: {"info": s.info, "messages": s.messages}
                                        for sid, s in self.sessions.items()}))
        target = self.data_home / "opencode" / "fake-db.json"
        with self.persist_lock:  # a server killed mid-write leaves the previous database, never half of one
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(db, indent=1), encoding="utf-8")
            for _ in range(100):
                try:
                    os.replace(tmp, target)
                    return
                except PermissionError:  # Windows: a reader has the file open for a moment
                    time.sleep(0.02)

    def emit(self, kind: str, data: dict[str, Any]) -> None:
        frame = {"id": new_id("evt"), "created": now_ms(), "type": kind, "data": data}
        with self.lock:
            listeners = list(self.listeners)
        for q in listeners:
            q.put(frame)

    # ------------------------------------------------------------------ the model

    def pin(self, s: Session, i: int) -> dict[str, Any]:
        if self.effective:
            e = self.effective[i % len(self.effective)]
            ref = {"providerID": e["provider"], "id": e["model"], "variant": e.get("effort") or "default"}
            return ref
        return dict(s.info["model"])

    def assistant(self, s: Session, i: int, finish: str, tool: str | None = None) -> None:
        msg = {"id": new_id("msg"), "type": "assistant", "agent": s.info.get("agent") or "build",
               "model": self.pin(s, i), "time": {"created": now_ms(), "completed": now_ms()},
               "content": [{"type": "tool", "name": tool}] if tool else [{"type": "text", "text": "ok"}],
               "tokens": {"input": 100 + i, "output": 10, "reasoning": 0, "cache": {"read": 0, "write": 0}},
               "cost": 0, "finish": finish}
        with self.lock:
            s.messages.append(msg)
        self.emit("session.step.started", {"sessionID": s.info["id"], "model": msg["model"],
                                           "assistantMessageID": msg["id"]})
        self.emit("session.step.ended", {"sessionID": s.info["id"], "assistantMessageID": msg["id"], "finish": finish,
                                         "tokens": msg["tokens"]})

    def deliver(self, s: Session, *, boundary: bool = False) -> int:
        """Move waiting prompts into the conversation (user messages), in order. At a step boundary in
        ``idle_before_queue_s`` mode, queued prompts stay waiting (the late-arrival race of a real server)."""
        with self.lock:
            hold = boundary and self.knobs.get("idle_before_queue_s") is not None
            items = [i for i in s.inbox if not (hold and i["delivery"] == "queue")]
            s.inbox = [i for i in s.inbox if i not in items]
            for item in items:
                s.messages.append({"id": item["id"], "type": "user", "text": item["payload"]["text"],
                                   "time": {"created": item["time"]["created"]}})
        for item in items:
            self.emit("session.inbox.delivered", {"sessionID": s.info["id"], "inboxID": item["id"]})
        return len(items)

    def gate(self, s: Session) -> str | None:
        """A permission request or form before the first step, if the knobs ask for one."""
        sid = s.info["id"]
        if self.knobs.get("subagent"):  # a child session the parent's model started (V2: parentID)
            child = "ses_" + secrets.token_hex(12)
            with self.lock:
                self.sessions[child] = Session({**s.info, "id": child, "parentID": sid, "title": "subagent"})
            self.persist()
            self.emit("session.created", {"sessionID": child})
        if self.knobs.get("ask"):
            rid = new_id("per")
            with self.lock:
                s.permissions[rid] = {"id": rid, "sessionID": sid, "action": "shell", "resources": ["rm -rf /"]}
            self.emit("permission.asked", {"sessionID": sid, "id": rid, "action": "shell"})
            while rid not in s.replies and not s.interrupted.is_set():  # an ask blocks until answered (V2)
                time.sleep(0.05)
            if s.replies.get(rid) == "reject":
                return "interrupted"
        if self.knobs.get("form"):
            fid = new_id("frm")
            with self.lock:
                s.forms[fid] = {"id": fid, "sessionID": sid, "title": "choose", "fields": []}
            while fid in s.forms and not s.interrupted.is_set():
                time.sleep(0.05)
        return None

    def run_step(self, s: Session, i: int, step: dict[str, Any]) -> str | None:
        """One tool call. Returns an outcome to end the turn with, or None to continue."""
        do = step["do"]
        self.assistant(s, i, "tool-calls", tool="shell")
        call = new_id("call")  # V2: a tool is named when its input starts; `called` carries the call id and input
        self.emit("session.tool.input.started", {"sessionID": s.info["id"], "id": call, "name": "shell"})
        self.emit("session.tool.called", {"sessionID": s.info["id"], "id": call, "input": {"command": TOOL_INPUT},
                                          "executed": True})
        if do == "exit":
            if step.get("code", 0):
                os._exit(int(step["code"]))  # the harness crashed
            return "succeeded"
        if do == "hang":
            s.interrupted.wait()
            return "interrupted"
        if do == "model_step":
            return None
        step_file = self.state / "steps" / f"{i}.json"
        step_file.parent.mkdir(exist_ok=True)
        step_file.write_text(json.dumps(step), encoding="utf-8")
        env = dict(s.env) if s.env is not None else dict(os.environ)  # V2: sessionEnvironment ?? process.env
        s.proc = subprocess.Popen([sys.executable, str(AGENT), "--step-file", str(step_file), "--index", str(i),
                                   "--transcript", str(self.state / "transcript.jsonl")],
                                  cwd=s.info["location"]["directory"], env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        s.proc.wait()
        s.proc = None
        return "interrupted" if s.interrupted.is_set() else None

    def execute(self, s: Session) -> None:
        sid = s.info["id"]
        self.emit("session.execution.started", {"sessionID": sid})
        outcome = "succeeded"
        try:
            self.deliver(s)
            if not s.contract_done:
                s.contract_done = True
                outcome = self.gate(s) or "succeeded"
                for i, step in enumerate(self.steps if outcome == "succeeded" else []):
                    ended = self.run_step(s, i, step)
                    self.deliver(s, boundary=True)  # steered or queued prompts join between steps
                    if ended:
                        outcome = ended
                        break
            if outcome == "succeeded":
                self.assistant(s, len(self.steps), "stop")
            requeue = self.knobs.get("idle_before_queue_s")
            while outcome == "succeeded" and requeue is None:  # queued prompts: answered in the same execution
                time.sleep(float(self.knobs.get("queue_gap_s") or 0))
                if not self.deliver(s):
                    break
                self.assistant(s, len(self.steps), "stop")
        finally:
            with self.lock:
                s.messages.append({"id": new_id("msg"), "type": "idle", "outcome": outcome,
                                   "time": {"created": now_ms()}})
                s.info["outcome"] = outcome
            # Saved before the session stops being active: a client that sees the turn end may stop the server at
            # once, and the saved conversation must already hold everything the turn did (a CI race, PR #5).
            self.persist()
            with self.lock:
                s.running = False
                s.interrupted.clear()
                pending = bool(s.inbox)
            self.emit(f"session.execution.{outcome}", {"sessionID": sid})
        if pending and self.knobs.get("idle_before_queue_s") is not None:
            # The race a real server has: the turn is idle, a prompt queued during it is not yet delivered, and
            # a new execution starts a moment later. A client that saw only "idle" would call the run finished.
            time.sleep(float(self.knobs["idle_before_queue_s"]))
            with self.lock:
                s.running = True
            self.execute(s)

    def prompt(self, s: Session, body: dict[str, Any]) -> dict[str, Any]:
        item = {"id": body.get("id") or new_id("msg"), "sessionID": s.info["id"], "time": {"created": now_ms()},
                "type": "user", "payload": {"text": body["text"]}, "delivery": body.get("delivery") or "steer"}
        with self.lock:
            s.inbox.append(item)
            start = not s.running
            s.running = True
        self.emit("session.inbox.enqueued", {"sessionID": s.info["id"], "inboxID": item["id"]})
        if start:
            threading.Thread(target=self.execute, args=(s,), daemon=True).start()
        return item

    # ------------------------------------------------------------------ API

    def spec(self) -> dict[str, Any]:
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
        for entry in self.knobs.get("openapi_drop") or []:
            method, path = entry.split(" ", 1)
            spec["paths"].get(path, {}).pop(method.lower(), None)
        if "stored_credentials" in self.knobs:  # 2.0.22's credential store
            spec["paths"]["/api/credential"] = {"get": {"operationId": "credential.list"}}
        return spec

    def agents(self) -> list[dict[str, Any]]:
        """Agents as V2 reports them: its defaults, then the configuration's rules, then the agent's own."""
        defaults = [{"action": "*", "resource": "*", "effect": "allow"},
                    {"action": "external_directory", "resource": "*", "effect": "ask"},
                    {"action": "read", "resource": "*.env", "effect": "ask"}]
        out = [{"id": "build", "name": "build", "mode": "primary", "permissions": defaults}]
        if self.knobs.get("ignore_config"):
            return out
        for name, agent in (self.config.get("agents") or {}).items():
            model = agent.get("model") or {}
            info = {"id": name, "name": name, "mode": agent.get("mode"), "system": agent.get("system"),
                    "steps": agent.get("steps"),
                    "model": {"providerID": model.get("providerID"), "id": model.get("model"),
                              "variant": model.get("variant") or "default"} if model else None,
                    "permissions": defaults + list(self.config.get("permissions") or [])
                    + list(agent.get("permissions") or [])}
            if name == "aew":
                info.update(self.knobs.get("agent_override") or {})
                info["permissions"] = info["permissions"] + list(self.knobs.get("appended_rules") or [])
            out.append(info)
        return out

    def models(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self.catalog_asked is None:
            self.catalog_asked = now
        if now - self.catalog_asked < float(self.knobs.get("catalog_delay_s") or 0):
            return []
        return self.knobs.get("models") or DEFAULT_MODELS

    def route(self, method: str, path: str, query: dict[str, list[str]], body: Any) -> tuple[int, Any]:
        m = re.fullmatch(r"/api/session/(ses[^/]+)(/.*)?", path)
        if m:
            with self.lock:
                s = self.sessions.get(m.group(1))
            if s is None:
                return 404, {"message": f"Session not found: {m.group(1)}"}
            return self.session_route(method, s, m.group(2) or "", query, body)
        if (method, path) == ("GET", "/openapi.json"):
            return 200, self.spec()
        if (method, path) == ("GET", "/api/credential") and "stored_credentials" in self.knobs:
            return 200, {"data": self.knobs["stored_credentials"]}
        if (method, path) == ("GET", "/api/info"):
            return 200, {"version": self.knobs.get("version") or "2.0.18", "pid": os.getpid(), "urls": [],
                         "paths": {"tmp": str(self.state / "tmp")}}
        if (method, path) == ("GET", "/api/agent"):
            return 200, {"location": {"directory": (query.get("location[directory]") or [""])[0]},
                         "data": self.agents()}
        if (method, path) == ("GET", "/api/model"):
            return 200, {"location": {"directory": (query.get("location[directory]") or [""])[0]},
                         "data": self.models()}
        if (method, path) == ("POST", "/api/session"):
            sid = "ses_" + secrets.token_hex(12)
            info = {"id": sid, "projectID": "fake", "title": body.get("title"), "agent": body.get("agent"),
                    "model": {"variant": "default", **(body.get("model") or {})}, "location": body.get("location"),
                    "permissions": body.get("permissions") or [], "metadata": body.get("metadata") or {},
                    "cost": 0, "tokens": {"input": 0, "output": 0}, "time": {"created": now_ms()}}
            with self.lock:
                self.sessions[sid] = Session(info)
            self.persist()
            self.emit("session.created", {"sessionID": sid})
            return 200, {"data": info}
        if (method, path) == ("GET", "/api/session"):
            with self.lock:
                return 200, {"data": [s.info for s in self.sessions.values()]}
        if (method, path) == ("GET", "/api/session/active"):
            with self.lock:
                return 200, {"data": {sid: {"type": "running"} for sid, s in self.sessions.items() if s.running}}
        return 404, {"message": f"no route {method} {path}"}

    def session_route(self, method: str, s: Session, rest: str, query: dict[str, list[str]],
                      body: Any) -> tuple[int, Any]:
        if (method, rest) == ("GET", ""):
            return 200, {"data": s.info}
        if (method, rest) == ("PUT", "/environment"):
            s.env = dict(body["variables"])
            return 204, None
        if (method, rest) == ("POST", "/prompt"):
            return 200, {"data": self.prompt(s, body)}
        if (method, rest) == ("POST", "/interrupt"):
            was = s.running
            s.interrupted.set()
            proc = s.proc
            if proc is not None:
                proc.kill()
            return 200, {"interrupted": was}
        if (method, rest) == ("GET", "/message"):
            with self.lock:
                msgs = list(s.messages)
            if (query.get("order") or ["asc"])[0] == "desc":
                msgs.reverse()
            limit = int((query.get("limit") or ["1000"])[0])
            return 200, {"data": msgs[:limit], "cursor": {}}
        mm = re.fullmatch(r"/message/(msg_[^/]+)", rest)
        if mm and method == "GET":
            with self.lock:
                found = next((x for x in s.messages if x["id"] == mm.group(1)), None)
            return (200, {"data": found}) if found else (404, {"message": "Message not found"})
        if (method, rest) == ("GET", "/inbox"):
            with self.lock:
                return 200, {"data": list(s.inbox)}
        if (method, rest) == ("GET", "/permission"):
            with self.lock:
                return 200, {"data": [p for rid, p in s.permissions.items() if rid not in s.replies]}
        pm = re.fullmatch(r"/permission/(per_[^/]+)/reply", rest)
        if pm and method == "POST":
            s.replies[pm.group(1)] = body["decision"]
            return 204, None
        if (method, rest) == ("GET", "/form"):
            with self.lock:
                return 200, {"data": list(s.forms.values())}
        fm = re.fullmatch(r"/form/(frm_[^/]+)", rest)
        if fm and method == "DELETE":
            with self.lock:
                s.forms.pop(fm.group(1), None)
            return 204, None
        return 404, {"message": f"no route {method} {rest}"}


def handler_for(app: FakeOpenCode) -> type[http.server.BaseHTTPRequestHandler]:
    expected = "Basic " + base64.b64encode(f"opencode:{app.password}".encode()).decode()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            pass

        def _reply(self, status: int, body: Any) -> None:
            raw = b"" if body is None else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self, method: str) -> None:
            if self.headers.get("Authorization") != expected:
                return self._reply(401, {"message": "Unauthorized"})
            url = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            if (method, url.path) == ("GET", "/api/event"):
                return self._events()
            status, out = app.route(method, url.path, parse_qs(url.query), body)
            self._reply(status, out)

        def _events(self) -> None:
            q: queue.Queue[dict[str, Any] | None] = queue.Queue()
            with app.lock:
                app.listeners.append(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            every = int(app.knobs.get("drop_events_every") or 0)
            sent = 0
            try:
                frame: dict[str, Any] | None = {"id": new_id("evt"), "type": "server.connected", "data": {}}
                while frame is not None:
                    self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
                    self.wfile.flush()
                    sent += 1
                    if every and sent >= every:  # the stream is lost; the client must not depend on it
                        break
                    frame = q.get()
            except OSError:
                pass
            finally:
                with app.lock:
                    app.listeners.remove(q)
                self.close_connection = True

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_PUT(self) -> None:
            self._handle("PUT")

        def do_DELETE(self) -> None:
            self._handle("DELETE")

    return Handler


TUI_SCRIPT, TUI_TRANSCRIPT, TUI_ARGV = "lead-tui.json", "lead-tui.jsonl", "lead-tui-argv.json"


def tui(argv: list[str], scripts: Path) -> int:
    """The Lead's TUI (``--standalone``): the Lead's model acts in the TUI's own environment."""
    (scripts / TUI_ARGV).write_text(json.dumps(argv), encoding="utf-8")
    import fake_agent

    sys.argv = ["fake_agent", "--script", str(scripts / TUI_SCRIPT), "--transcript", str(scripts / TUI_TRANSCRIPT)]
    return fake_agent.main()


def main(argv: list[str], scripts: Path) -> int:
    if argv[:1] == ["--version"]:
        print("opencode v2.0.18")
        return 0
    if argv[:1] == ["--standalone"]:
        return tui(argv, scripts)
    if argv[:1] != ["serve"] or "--stdio" not in argv:
        print(f"fake opencode: unsupported arguments {argv}", file=sys.stderr)
        return 2
    app = FakeOpenCode(scripts)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_for(app))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    sys.stdout.write(json.dumps({"url": f"http://127.0.0.1:{server.server_address[1]}"}) + "\n")
    sys.stdout.flush()
    sys.stdin.buffer.read()  # the lease: stdin EOF ends the server
    os._exit(0)


LAUNCHER = """import sys
sys.path.insert(0, {helpers!r})
import fake_opencode
sys.exit(fake_opencode.main(sys.argv[1:], __import__("pathlib").Path({scripts!r})))
"""


def write_launcher(directory: Path, scripts: Path) -> Path:
    """A per-lab ``opencode`` entry point (the adapter runs a ``.py`` binary with the current Python)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fake-opencode.py"
    path.write_text(LAUNCHER.format(helpers=str(HERE), scripts=str(scripts)), encoding="utf-8")
    return path
