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
``ignore_config`` (load no configured agent), ``agents_delay_s`` (list no agent at all until this long after the
first agent request), ``agent_override`` (fields that differ from the projection),
``appended_rules`` (rules the server appends after the agent's own, as 2.0.22 appends ``browser: deny``),
``stored_credentials`` (serve 2.0.22's ``GET /api/credential`` with these entries),
``subagent`` (the model starts a child session, as V2's subagent tool would),
``drop_events_every`` (close each event connection after N frames), ``ask`` (a permission request before
the first step), ``form`` (a form before the first step), ``queue_gap_s`` (pause at the end of a turn,
before its queued prompts are taken), ``provider_auth`` (``{"variable", "rejected_sha256": [...]}``: when the
server's own value of that variable hashes to one of these, the provider rejects it at the first model call, as
2.0.18 reports a 401: the turn fails with ``provider.auth``, no retry), ``live_usage`` (F25 L1: sessions carry the
pinned ``TokenUsage.Info`` totals, and each model step adds its tokens to its session's totals; ``{"order":
"message_first" | "totals_first", "gap_s": s}`` says which of the two a reader can see first, and for how long; 2.0.18
commits a step's message and totals together, P1(e), so ``gap_s`` 0 is the pinned behaviour).

Live usage (F25 L1) is served as 2.0.18 serves it, for the paths the meter uses: ``GET /api/session`` pages in
``time.updated`` order from an opaque cursor when ``order``, ``limit`` or ``cursor`` is given, and
``GET /api/session/{id}/message`` filters by ``type`` and pages from an opaque cursor when ``type`` or ``cursor`` is
given (a cursor combined with ``order`` is a 400, as pinned). Without those parameters both answer as before. In
process, :func:`local_app` and :class:`LocalClient` serve the same routes without HTTP, and ``add_session``,
``start_call``, ``end_call``, ``record_usage``, ``fork``, ``revert`` and ``remove`` script the usage facts probe P1
pinned (``tests/fixtures/opencode/live-usage-2.0.18.json``).

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


def zero_usage() -> dict[str, Any]:
    """The pinned ``TokenUsage.Info`` shape, all zeros."""
    return {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}


def add_usage(info: dict[str, Any], tokens: Any, cost: Any) -> None:
    """A session's totals grow by a call's usage (2.0.18's ``SessionProjector`` adds each category and the cost)."""
    if not isinstance(tokens, dict):
        return
    total = info.get("tokens") if isinstance(info.get("tokens"), dict) else {}
    cache, more = dict(total.get("cache") or {}), tokens.get("cache") or {}
    info["tokens"] = {k: (total.get(k) or 0) + (tokens.get(k) or 0) for k in ("input", "output", "reasoning")}
    info["tokens"]["cache"] = {k: (cache.get(k) or 0) + (more.get(k) or 0) for k in ("read", "write")}
    info["cost"] = (info.get("cost") or 0) + (cost or 0)


def encode_cursor(value: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def decode_cursor(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid cursor")
    return value


class Session:
    def __init__(self, info: dict[str, Any]) -> None:
        self.info = info
        self.env: dict[str, str] | None = None
        self.messages: list[dict[str, Any]] = []
        self.inbox: list[dict[str, Any]] = []
        self.prompts: list[dict[str, Any]] = []  # every prompt POST as it arrived: its id and `delivery`, for tests
        self.running = False
        self.interrupted = threading.Event()
        self.contract_done = False
        self.proc: subprocess.Popen[bytes] | None = None
        self.permissions: dict[str, dict[str, Any]] = {}
        self.replies: dict[str, str] = {}
        self.forms: dict[str, dict[str, Any]] = {}
        self.error: dict[str, Any] | None = None  # why the current execution failed (`session.execution.failed`)


class FakeOpenCode:
    def __init__(self, scripts: Path) -> None:
        self.catalog_asked: float | None = None
        self.agents_asked: float | None = None
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
        self.message_reads = 0  # message-list requests answered with a type or cursor (F25 L1)
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
            db = json.loads(json.dumps({sid: {"info": s.info, "messages": s.messages, "prompts": s.prompts}
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
        live = self.knobs.get("live_usage")
        if live is not None:  # the step's usage reaches the session's totals too, in the configured order
            first, then = ((self._add_totals, self._append) if live.get("order") == "totals_first"
                           else (self._append, self._add_totals))
            first(s, msg)
            time.sleep(float(live.get("gap_s") or 0))
            then(s, msg)
        else:
            with self.lock:
                s.messages.append(msg)
        self.emit("session.step.started", {"sessionID": s.info["id"], "model": msg["model"],
                                           "assistantMessageID": msg["id"]})
        self.emit("session.step.ended", {"sessionID": s.info["id"], "assistantMessageID": msg["id"], "finish": finish,
                                         "tokens": msg["tokens"]})

    def _append(self, s: Session, msg: dict[str, Any]) -> None:
        with self.lock:
            s.messages.append(msg)

    def _add_totals(self, s: Session, msg: dict[str, Any]) -> None:
        with self.lock:
            add_usage(s.info, msg.get("tokens"), msg.get("cost"))

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

    def provider_rejects(self, s: Session) -> str | None:
        """The ``provider_auth`` knob: a rejected key fails the first model call as pinned 2.0.18 was observed to do
        (2026-10-09, a local provider answering HTTP 401; no retry): the step's assistant message ends ``error`` with
        ``{type: provider.auth, message, status: 401}``, then ``session.step.failed`` and ``session.execution.failed``
        carry the same error. The message quotes part of the key, as OpenAI's does."""
        knob = self.knobs.get("provider_auth")
        if not knob:
            return None
        import hashlib

        key = os.environ.get(knob["variable"]) or ""
        if hashlib.sha256(key.encode()).hexdigest() not in knob["rejected_sha256"]:
            return None
        error = {"type": "provider.auth", "message": f"Incorrect API key provided: {key[:3]}***{key[-4:]}.",
                 "status": 401}
        msg = {"id": new_id("msg"), "type": "assistant", "agent": s.info.get("agent") or "build",
               "model": self.pin(s, 0), "time": {"created": now_ms(), "completed": now_ms()}, "content": [],
               "finish": "error", "error": error}
        with self.lock:
            s.messages.append(msg)
            s.error = error
        self.emit("session.step.started", {"sessionID": s.info["id"], "model": msg["model"],
                                           "assistantMessageID": msg["id"]})
        self.emit("session.step.failed", {"sessionID": s.info["id"], "assistantMessageID": msg["id"], "error": error})
        return "failed"

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
                outcome = self.gate(s) or self.provider_rejects(s) or "succeeded"
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
                error, s.error = s.error, None
            self.emit(f"session.execution.{outcome}", {"sessionID": sid, **({"error": error} if error else {})})
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
            s.prompts.append({"id": item["id"], "delivery": body.get("delivery")})  # as posted: None when absent
            start = not s.running
            s.running = True
        self.persist()  # a test reads what was posted even when the server is stopped before the turn ends
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
        now = time.monotonic()
        if self.agents_asked is None:
            self.agents_asked = now
        if now - self.agents_asked < float(self.knobs.get("agents_delay_s") or 0):
            return []
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
            if self.knobs.get("live_usage") is not None:
                info["tokens"] = zero_usage()
                info["time"]["updated"] = info["time"]["created"]
            with self.lock:
                self.sessions[sid] = Session(info)
            self.persist()
            self.emit("session.created", {"sessionID": sid})
            return 200, {"data": info}
        if (method, path) == ("GET", "/api/session"):
            if {"order", "limit", "cursor"} & set(query):
                return self.list_sessions(query)
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
        if (method, rest) == ("GET", "/message") and ({"type", "cursor"} & set(query)):
            return self.list_messages(s, query)
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

    # ------------------------------------------------------------------ live usage (F25 L1)

    def list_sessions(self, query: dict[str, list[str]]) -> tuple[int, Any]:
        """``session.list`` as 2.0.18 pages it: ordered and anchored on ``(time.updated, id)``; the cursor carries the
        order and the anchor (not the limit, which each request gives or defaults to 50)."""
        limit = int((query.get("limit") or ["50"])[0])
        raw = (query.get("cursor") or [None])[0]
        if raw is not None:
            try:
                cur = decode_cursor(raw)
            except ValueError:
                return 400, {"message": "Invalid cursor"}
            order, anchor = cur["order"], (cur["time"], cur["id"])
        else:
            order, anchor = (query.get("order") or ["desc"])[0], None
        with self.lock:
            infos = [dict(s.info) for s in self.sessions.values()]

        def key(i: dict[str, Any]) -> tuple[float, str]:
            t = i.get("time") or {}
            return float(t.get("updated") or t.get("created") or 0), str(i["id"])

        infos.sort(key=key, reverse=order == "desc")
        if anchor is not None:
            infos = [i for i in infos if (key(i) > tuple(anchor) if order == "asc" else key(i) < tuple(anchor))]
        page = [json.loads(json.dumps(i)) for i in infos[:limit]]
        cursor: dict[str, Any] = {}
        if page:
            last = key(page[-1])
            cursor["next"] = encode_cursor({"order": order, "time": last[0], "id": last[1]})
        return 200, {"data": page, "cursor": cursor}

    def list_messages(self, s: Session, query: dict[str, list[str]]) -> tuple[int, Any]:
        """``session.message.list`` as 2.0.18 pages it (``SessionStore.messages``): in position order, filtered by
        ``type``, with a cursor on the last item of every non-empty page (an empty page ends the list) that carries
        only the anchor's id and the order and is never combined with ``order``. The anchor is looked up among all
        the session's messages; **when it is gone (a revert deleted it) the page is empty, for good**
        (``if(r.cursor&&!c)return[]``)."""
        raw = (query.get("cursor") or [None])[0]
        if raw is not None and "order" in query:
            return 400, {"message": "Cursor cannot be combined with order"}
        limit = min(int((query.get("limit") or ["100"])[0]), 200)
        kind = (query.get("type") or [None])[0]
        with self.lock:
            self.message_reads += 1
            every = list(s.messages)
        positions = list(range(len(every)))
        if raw is not None:
            try:
                cur = decode_cursor(raw)
            except ValueError:
                return 400, {"message": "Invalid cursor"}
            order = cur["order"]
            ids = [m["id"] for m in every]
            if cur["id"] not in ids:
                return 200, {"data": [], "cursor": {}}
            at = ids.index(cur["id"])
            positions = [i for i in positions if (i > at if order == "asc" else i < at)]
        else:
            order = (query.get("order") or ["desc"])[0]
        if order != "asc":
            positions.reverse()
        ordered = [every[i] for i in positions if kind is None or every[i].get("type") == kind]
        page = [json.loads(json.dumps(m)) for m in ordered[:limit]]
        cursor: dict[str, Any] = {}
        if page:
            cursor["next"] = encode_cursor({"order": order, "id": page[-1]["id"], "direction": "next"})
        return 200, {"data": page, "cursor": cursor}

    def add_session(self, *, model: dict[str, Any] | None = None, parent: str | None = None,
                    created: float | None = None) -> str:
        sid = "ses_" + secrets.token_hex(12)
        at = now_ms() if created is None else created
        info: dict[str, Any] = {"id": sid, "projectID": "fake", "title": "scripted", "agent": "build",
                                "model": dict(model or {"providerID": "fakeprov", "id": "fake-model",
                                                        "variant": "default"}),
                                "location": {"directory": str(self.state)}, "cost": 0, "tokens": zero_usage(),
                                "time": {"created": at, "updated": at}}
        if parent is not None:
            info["parentID"] = parent
        with self.lock:
            self.sessions[sid] = Session(info)
        return sid

    def start_call(self, sid: str, *, model: dict[str, Any] | None = None, kind: str = "assistant",
                   created: float | None = None) -> str:
        """A model call begins: its message exists, with no tokens and (for an assistant call) no ``time.completed``;
        a compaction is ``running`` (P1(a), (f))."""
        s = self.sessions[sid]
        mid = new_id("msg")
        at = now_ms() if created is None else created
        if kind == "assistant":
            msg: dict[str, Any] = {"id": mid, "type": "assistant", "agent": "build",
                                   "model": dict(model or s.info["model"]), "time": {"created": at}, "content": []}
        else:
            msg = {"id": mid, "type": "compaction", "status": "running", "reason": "auto", "summary": "",
                   "recent": "", "time": {"created": at}}
        with self.lock:
            s.messages.append(msg)
        return mid

    def end_call(self, sid: str, mid: str, *, tokens: dict[str, Any] | None, cost: float = 0.0,
                 error: dict[str, Any] | None = None, parts: tuple[str, ...] = ("message", "totals"),
                 completed: float | None = None, model: dict[str, Any] | None = None) -> None:
        """A model call ends. An assistant call's message gets ``time.completed``, ``finish`` and its tokens, and the
        session's totals grow by them in the same transaction (P1(a), (e)); a failure with no usage carries none and
        leaves the totals alone (P1(c)). ``parts`` applies only one of the two halves, to stage a reader's skew (a
        compaction's totals are recorded before its message completes, P1(e))."""
        s = self.sessions[sid]
        with self.lock:
            msg = next(m for m in s.messages if m["id"] == mid)
            if "message" in parts:
                if msg["type"] == "assistant":
                    msg["time"]["completed"] = now_ms() if completed is None else completed
                    msg["finish"] = "error" if error else "stop"
                    if error:
                        msg["error"] = error
                else:
                    msg["status"] = "failed" if error else "completed"
                    if error:
                        msg["error"] = error
                    else:
                        msg["model"] = dict(model or s.info["model"])
                if tokens is not None:
                    msg["tokens"], msg["cost"] = json.loads(json.dumps(tokens)), cost
            if "totals" in parts and tokens is not None:
                add_usage(s.info, tokens, cost)

    def record_usage(self, sid: str, tokens: dict[str, Any], cost: float = 0.0) -> None:
        """``session.usage.recorded``: a title (or compaction) call's usage reaches the totals, on no message."""
        with self.lock:
            add_usage(self.sessions[sid].info, tokens, cost)

    def fork(self, sid: str, *, created: float | None = None) -> str:
        """``session.fork``: a new root session whose totals start at zero, holding copies (new ids, the original
        creation times) of the source's finished messages (P1(d))."""
        src = self.sessions[sid]
        fid = self.add_session(model=src.info["model"], created=created)
        with self.lock:
            f = self.sessions[fid]
            f.info["fork"] = {"sessionID": sid, "boundary": {"type": "through", "messageID": src.messages[-1]["id"]}}
            for m in src.messages:
                done = ((m.get("time") or {}).get("completed") is not None if m["type"] == "assistant"
                        else m.get("status") != "running")
                if done:
                    f.messages.append({**json.loads(json.dumps(m)), "id": new_id("msg")})
        return fid

    def revert(self, sid: str, mid: str) -> None:
        """``session.revert.committed``: messages from ``mid`` on are deleted; the totals stay (P1(d))."""
        with self.lock:
            s = self.sessions[sid]
            at = next(i for i, m in enumerate(s.messages) if m["id"] == mid)
            del s.messages[at:]

    def remove(self, sid: str) -> None:
        with self.lock:
            self.sessions.pop(sid, None)

    def set_totals(self, sid: str, tokens: dict[str, Any], cost: float | None = None) -> None:
        """Totals written directly (``session.import`` sets them, and the REST store is model-writable)."""
        with self.lock:
            info = self.sessions[sid].info
            info["tokens"] = json.loads(json.dumps(tokens))
            if cost is not None:
                info["cost"] = cost

    def set_running(self, sid: str, running: bool) -> None:
        with self.lock:
            self.sessions[sid].running = running


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


class LocalClient:
    """The fake's routes in process, with the adapter ``Client``'s ``get`` signature and errors (F25 L1's meter
    tests). ``requests`` records every ``(method, path, params)`` sent, for the pinned-operation check; ``down``
    makes every request fail as an unreachable server does."""

    def __init__(self, app: FakeOpenCode) -> None:
        self.app = app
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.down = False

    def get(self, path: str, params: dict[str, str] | None = None, **_kw: Any) -> Any:
        from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable

        self.requests.append(("GET", path, dict(params or {})))
        if self.down:
            raise OpenCodeUnavailable(f"GET {path}: the fake server is down")
        status, body = self.app.route("GET", path, {k: [v] for k, v in (params or {}).items()}, None)
        if status >= 400:
            raise OpenCodeError("GET", path, status, body)
        return json.loads(json.dumps(body))


def local_app(root: Path, knobs: dict[str, Any] | None = None) -> FakeOpenCode:
    """A fake server in process, for tests that drive its routes through :class:`LocalClient`. Its files live under
    ``root``; the process environment is left as it was."""
    run = root / "R-LOCAL-1"
    data = run / "harness" / "xdg-data"
    data.mkdir(parents=True, exist_ok=True)
    scripts = root / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "default.json").write_text(json.dumps({"steps": [], "server": {"live_usage": {}, **(knobs or {})}}),
                                          encoding="utf-8")
    saved = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "OPENCODE_PASSWORD", "OPENCODE_SERVER_PASSWORD")}
    os.environ["XDG_DATA_HOME"] = str(data)
    try:
        return FakeOpenCode(scripts)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
