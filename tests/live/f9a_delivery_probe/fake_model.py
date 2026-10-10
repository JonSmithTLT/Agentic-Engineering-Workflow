"""A scripted fake OpenAI-compatible model for the F9-A MS0 live-delivery probe (measurement only, no real
model; ``probe.py`` serves it in-process).

Adapted from an earlier OpenCode compaction probe's fake model. Binds 127.0.0.1 only. Serves
``POST /v1/chat/completions`` (streaming SSE and non-streaming) and ``GET /v1/models``. No credential is read or
checked: the Authorization header is logged only as present or absent.

The scenario's ``script`` is a list of actions, one per main request (a request that carries tools), in order:

- ``{"shell": CMD, "timeout": MS?, "background": BOOL?}``: call the shell tool with that command;
- ``{"read": PATH}``: call the read tool;
- ``{"text": STR}``: answer with text only (ends the agent's turn);
- any action may add ``"delay": S``: the response headers and the role chunk are sent at once, then the model "thinks"
  for S seconds before the rest (a model call in flight), so a client abort shows as a failed write.

Past the end of the script every main request is answered with text naming the Lead markers it saw, which ends the
turn. Every request is logged twice to the run's ``model.jsonl``: on arrival (``ev: req``) and when answered
(``ev: resp``), with wall-clock times (``t``) so they line up with the event stream. Each ``req`` record lists the
Lead markers (``LEADMSG-<tag>``) in the conversation in order, the roles, the tool results' heads and tails, and
whether the OpenCode input metadata keys (``aew_message``, ``aew_thread``) appear anywhere in what the model
received. The first request that carries a marker also logs that user message's full text (what the worker sees).
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler
from typing import Any

MARKER_RE = re.compile(r"LEADMSG-[A-Za-z0-9_]+")
METADATA_KEYS = ("aew_message", "aew_thread", "PROBE-META-")


class State:
    def __init__(self, scenario: dict[str, Any], log_path: str) -> None:
        self.s = scenario
        self.log_path = log_path
        self.lock = threading.Lock()
        self.n = 0
        self.main_n = 0
        self.seen_markers: set[str] = set()
        self.in_flight = threading.Event()  # set while a delayed main request is being held
        self.requests: list[dict[str, Any]] = []

    def log(self, rec: dict[str, Any]) -> None:
        with self.lock, open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
    return "" if content is None else json.dumps(content)


def tool_param(body: dict[str, Any], names: tuple[str, ...]) -> tuple[str, dict[str, Any]] | None:
    for t in body.get("tools") or []:
        fn = t.get("function") or {}
        if fn.get("name") in names:
            return str(fn["name"]), (fn.get("parameters") or {}).get("properties") or {}
    return None


def build_call(body: dict[str, Any], action: dict[str, Any]) -> dict[str, Any] | None:
    if "shell" in action:
        sh = tool_param(body, ("shell", "bash"))
        if not sh:
            return None
        args: dict[str, Any] = {"command": action["shell"], "description": "probe step"}
        if action.get("timeout") is not None:
            args["timeout"] = action["timeout"]
        if action.get("background"):
            args["background"] = True
        return {"name": sh[0], "arguments": json.dumps(args)}
    if "read" in action:
        rt = tool_param(body, ("read",))
        if not rt:
            return None
        key = next((k for k in rt[1] if "path" in k.lower()), "path")
        return {"name": rt[0], "arguments": json.dumps({key: action["read"]})}
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-model/ms0"
    st: State
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet
        pass

    def _json(self, code: int, obj: Any) -> None:
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": "probe-small", "object": "model", "owned_by": "probe"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # one scripted answer
        st = self.st
        t_in = time.time()
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        body = json.loads(raw or b"{}")
        msgs = body.get("messages") or []
        kind = "main" if body.get("tools") else "auxiliary"
        with st.lock:
            st.n += 1
            n = st.n
            if kind == "main":
                st.main_n += 1
            ordinal = st.main_n if kind == "main" else None
        raw_text = raw.decode("utf-8", "replace")
        user_markers: list[str] = []
        positions: list[list[Any]] = []  # [marker, message index, role]
        for i, m in enumerate(msgs):
            for mk in MARKER_RE.findall(text_of(m.get("content"))):
                positions.append([mk, i, m.get("role")])
                if m.get("role") == "user" and mk not in user_markers:
                    user_markers.append(mk)
        rec: dict[str, Any] = {
            "ev": "req", "t": t_in, "n": n, "kind": kind, "main_ordinal": ordinal, "stream": bool(body.get("stream")),
            "bytes": len(raw), "roles": [m.get("role") for m in msgs], "markers": user_markers,
            "marker_positions": positions, "metadata_visible": {k: (k in raw_text) for k in METADATA_KEYS},
            "auth_header": "present" if self.headers.get("Authorization") else "absent",
        }
        tools = []
        for i, m in enumerate(msgs):
            if m.get("role") == "tool":
                txt = text_of(m.get("content"))
                tools.append({"i": i, "id": m.get("tool_call_id"), "len": len(txt), "head": txt[:240],
                              "tail": txt[-300:]})
        rec["tool_results"] = tools
        if kind == "main":
            new = [mk for mk in user_markers if mk not in st.seen_markers]
            rec["new_markers"] = new
            for mk in new:
                st.seen_markers.add(mk)
                full = next((text_of(m.get("content")) for m in msgs if m.get("role") == "user"
                             and mk in text_of(m.get("content"))), None)
                rec.setdefault("rendered", {})[mk] = full
            if ordinal == 1:
                rec["tool_names"] = [((t.get("function") or {}).get("name")) for t in body.get("tools") or []]
                sh = tool_param(body, ("shell", "bash"))
                rec["shell_params"] = sh[1] if sh else None
        st.log(rec)
        # The scripted answer.
        script = st.s.get("script") or []
        action: dict[str, Any]
        if kind != "main":
            action = {"text": "Probe session"}
        elif ordinal is not None and ordinal <= len(script):
            action = dict(script[ordinal - 1])
        else:
            action = {"text": "Acknowledged " + (", ".join(user_markers) or "nothing") + ". Done."}
        text = action.get("text", "")
        calls: list[dict[str, Any]] = []
        for a in action.get("multi") or [action]:  # "multi": several tool calls in one step (run in parallel)
            call = build_call(body, a)
            if call is not None:
                calls.append(call)
        if calls and not text:
            text = "Running a probe step."
        tool_call = calls[0] if calls else None
        finish = "tool_calls" if tool_call else "stop"
        usage = {"prompt_tokens": len(raw) // 4, "completion_tokens": 20, "total_tokens": len(raw) // 4 + 20}
        delay = float(action.get("delay") or 0)
        cid = f"chatcmpl-ms0-{n}"
        outcome = "answered"
        try:
            if body.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                        "model": "probe-small"}
                self._sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]})
                if delay:
                    st.in_flight.set()
                    end = time.time() + delay
                    while time.time() < end:  # a keep-alive comment every second shows a client abort early
                        time.sleep(min(1.0, max(0.0, end - time.time())))
                        self.wfile.write(b": thinking\n\n")
                        self.wfile.flush()
                    st.in_flight.clear()
                if text:
                    self._sse({**base, "choices": [{"index": 0, "delta": {"content": text}}]})
                for k, call in enumerate(calls):
                    self._sse({**base, "choices": [{"index": 0, "delta": {"tool_calls": [
                        {"index": k, "id": f"call_ms0_{n}_{k}", "type": "function",
                         "function": {"name": call["name"], "arguments": ""}}]}}]})
                    self._sse({**base, "choices": [{"index": 0, "delta": {"tool_calls": [
                        {"index": k, "function": {"arguments": call["arguments"]}}]}}]})
                self._sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
                self._sse({**base, "choices": [], "usage": usage})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True
            else:
                if delay:
                    st.in_flight.set()
                    time.sleep(delay)
                    st.in_flight.clear()
                message: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    message["tool_calls"] = [{"id": f"call_ms0_{n}_{k}", "type": "function",
                                              "function": {"name": c["name"], "arguments": c["arguments"]}}
                                             for k, c in enumerate(calls)]
                self._json(200, {"id": cid, "object": "chat.completion", "created": int(time.time()),
                                 "model": "probe-small", "choices": [{"index": 0, "message": message,
                                                                      "finish_reason": finish}], "usage": usage})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            outcome = f"client_gone: {type(exc).__name__}"
            st.in_flight.clear()
        st.log({"ev": "resp", "t": time.time(), "n": n, "main_ordinal": ordinal, "outcome": outcome,
                "answer": ("tool:" + " + ".join(c["arguments"] for c in calls)) if calls else ("text:" + text[:120]),
                "delay": delay})

    def _sse(self, obj: Any) -> None:
        self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
        self.wfile.flush()
