"""The scripted model: a local model server that answers from a script, so a harness runs real turns with no key, no
provider and no network beyond loopback.

The protocol is behind :class:`ScriptedModel`; each mode is one wire protocol. ``responses`` (the OpenAI Responses API,
streamed) is the one built now: it is OpenAI's default route in OpenCode, and the one the Codex pack will need too.

A script is a list of turns, one per *main* request (a request that offers tools), in order:

- ``{"text": str}``: answer with text, which ends the agent's turn;
- ``{"call": [names...], "arguments": {...}}``: call the first offered tool whose name is in ``names``; an argument
  value ``"$path:<key>"`` is replaced by the offered tool's first parameter whose name contains ``path`` (tools spell
  it ``path``, ``filePath`` or ``file_path``), and ``<key>`` is that argument's value;
- either may carry ``"usage"``: the raw Responses ``usage`` object to report; it defaults to zeros.
- ``{"calls": [{"call": [...], "arguments": {...}}, ...]}`` emits parallel calls in one step.
- Tool-owned ``entered``/``release`` threading events pause a response at a deterministic boundary for probes. They
  are never taken from an HTTP request; a bounded missing release fails the probe rather than returning fake text.

Past the end of the script a main request is answered with text. An auxiliary request (one with no tools: a title, a
summary) is answered with text and zero usage. Every request is logged (path, tool names, whether it carried an
``Authorization`` header, never its value). A WebSocket upgrade is answered 501 and counted, so a check sees whether
the harness tried one. Binds 127.0.0.1 only.
"""

from __future__ import annotations

import http.server
import itertools
import json
import threading
from typing import Any, Protocol

ZERO_USAGE = {"input_tokens": 0, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": 0,
              "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": 0}


class ScriptedModel(Protocol):
    mode: str
    base_url: str
    requests: list[dict[str, Any]]
    upgrades: int

    def close(self) -> None: ...


def _tools(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Offered tools by name -> their parameters' properties (Responses' flat form, or Chat's ``function`` form)."""
    out = {}
    for t in body.get("tools") or []:
        fn = t.get("function") if isinstance(t.get("function"), dict) else t
        if fn.get("name"):
            out[str(fn["name"])] = ((fn.get("parameters") or {}).get("properties")) or {}
    return out


def _arguments(args: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    out = {}
    path_key = next((k for k in params if "path" in k.lower()), "path")
    for k, v in args.items():
        out[path_key if k == "$path" else k] = v
    return out


class ResponsesModel:
    """The ``responses`` mode: ``POST <base>/responses``, streamed as server-sent events."""

    mode = "responses"

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = list(script)
        self.requests: list[dict[str, Any]] = []
        self.upgrades = 0
        self._main = 0
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        model = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_a: Any) -> None:
                pass

            def _plain(self, code: int, obj: Any) -> None:
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(raw)
                self.close_connection = True

            def do_GET(self) -> None:  # noqa: N802 (http.server's name)
                if (self.headers.get("Upgrade") or "").lower() == "websocket":
                    with model._lock:
                        model.upgrades += 1
                        model.requests.append({"method": "GET", "path": self.path, "upgrade": True})
                    self._plain(501, {"error": {"message": "no websocket here"}})
                    return
                with model._lock:
                    model.requests.append({"method": "GET", "path": self.path})
                self._plain(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                tools = _tools(body)
                with model._lock:
                    main = bool(tools)
                    turn: dict[str, Any] = {"text": "done"}
                    if main:
                        if model._main < len(model.script):
                            turn = model.script[model._main]
                        model._main += 1
                    model.requests.append({"method": "POST", "path": self.path, "main": main, "tools": sorted(tools),
                                           "auth": "present" if self.headers.get("Authorization") else "absent",
                                           "stream": bool(body.get("stream")), "body": body})
                if not self.path.rstrip("/").endswith("/responses"):
                    self._plain(404, {"error": {"message": f"this scripted model serves /responses, not {self.path}"}})
                    return
                if main and turn.get("entered") is not None:
                    turn["entered"].set()
                if main and turn.get("release") is not None and not turn["release"].wait(60):
                    self._plain(500, {"error": {"message": "scripted response was not released"}})
                    return
                self._stream(model._events(turn if main else {"text": "title"}, tools, body))

            def _stream(self, events: list[dict[str, Any]]) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                for ev in events:
                    self.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode())
                self.wfile.flush()
                self.close_connection = True

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="hq-model", daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def _events(self, turn: dict[str, Any], tools: dict[str, dict[str, Any]], body: dict[str, Any]) -> list[dict]:
        n = next(self._ids)
        rid, model_id = f"resp_{n}", str(body.get("model") or "scripted")
        usage = dict(turn.get("usage") or ZERO_USAGE)
        usage.setdefault("total_tokens", int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0)))
        base = {"id": rid, "object": "response", "created_at": 1, "model": model_id, "status": "in_progress",
                "output": []}
        events: list[dict[str, Any]] = [{"type": "response.created", "sequence_number": 0, "response": base}]
        if "calls" in turn:
            calls = turn["calls"]
            if not isinstance(calls, list) or not calls:
                raise ValueError("parallel scripted calls must be a nonempty list")
            events = [events[0]]
            output = []
            for index, call in enumerate(calls):
                made = self._events(call, tools, body)
                for event in made[1:-1]:
                    if "output_index" in event:
                        event["output_index"] = index
                    events.append(event)
                output.extend(made[-1]["response"]["output"])
            events.append({"type": "response.completed", "response": {
                **base, "status": "completed", "output": output, "usage": usage}})
            for index, event in enumerate(events):
                event["sequence_number"] = index
            return events
        name = next((c for c in turn.get("call") or [] if c in tools), None)
        if turn.get("call") and name is None:
            turn = {"text": f"none of {turn['call']} is offered (offered: {sorted(tools)})", "usage": usage}
        if name is not None:
            args = json.dumps(_arguments(turn.get("arguments") or {}, tools[name]))
            item = {"id": f"fc_{n}", "type": "function_call", "status": "in_progress", "call_id": f"call_{n}",
                    "name": name, "arguments": ""}
            done = {**item, "status": "completed", "arguments": args}
            events += [{"type": "response.output_item.added", "output_index": 0, "item": item},
                       {"type": "response.function_call_arguments.delta", "item_id": item["id"], "output_index": 0,
                        "delta": args},
                       {"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": 0,
                        "arguments": args},
                       {"type": "response.output_item.done", "output_index": 0, "item": done}]
        else:
            text = str(turn.get("text", "done"))
            item = {"id": f"msg_{n}", "type": "message", "status": "in_progress", "role": "assistant", "content": []}
            part = {"type": "output_text", "text": "", "annotations": []}
            done = {**item, "status": "completed", "content": [{**part, "text": text}]}
            events += [{"type": "response.output_item.added", "output_index": 0, "item": item},
                       {"type": "response.content_part.added", "item_id": item["id"], "output_index": 0,
                        "content_index": 0, "part": part},
                       {"type": "response.output_text.delta", "item_id": item["id"], "output_index": 0,
                        "content_index": 0, "delta": text},
                       {"type": "response.output_text.done", "item_id": item["id"], "output_index": 0,
                        "content_index": 0, "text": text},
                       {"type": "response.content_part.done", "item_id": item["id"], "output_index": 0,
                        "content_index": 0, "part": {**part, "text": text}},
                       {"type": "response.output_item.done", "output_index": 0, "item": done}]
        events.append({"type": "response.completed",
                       "response": {**base, "status": "completed", "output": [done], "usage": usage}})
        for i, ev in enumerate(events):
            ev["sequence_number"] = i
        return events

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


MODES = {"responses": ResponsesModel}


def start(mode: str, script: list[dict[str, Any]]) -> ScriptedModel:
    try:
        return MODES[mode](script)
    except KeyError:
        raise ValueError(f"no scripted model mode {mode!r} (built: {sorted(MODES)})") from None
