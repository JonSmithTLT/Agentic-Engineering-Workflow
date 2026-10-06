"""``aew lead mcp``: the typed Lead surface's MCP transport, server ``aew-lead`` (typed-lead-surface-design-v0.2 §4).

The Lead's harness (OpenCode) spawns this process in the Lead session's curated environment. It holds **no AEW
credential** and has no authority of its own: it never constructs an engine, never reads ``AEW_LEAD_TOKEN`` and
imports no engine code. Every well-formed ``tools/call`` is forwarded to the session's Lead broker (``lead.tool``,
ingress ``mcp``), which runs the one runner with the credential it holds. There is no direct mode: without a live
Lead broker this process refuses to start (§12.4).

The protocol layer is small and dependency-free by intent (§4.3, §13): newline-delimited JSON-RPC 2.0 on stdio,
``initialize`` with a known protocol revision, ``ping``, ``tools/list`` rendered from the catalog filtered by the
surface profile (the generic ``cli`` escape only on ``recovery``), ``tools/call`` returning the ``StageResult`` as
structured content with ``isError`` from its ``ok``. A call naming an unknown, designed or concealed tool, or with
arguments outside the tool's schema, is an input error that never reaches the broker; an unreachable broker is a
transport error, never a fabricated result. Stdout carries the protocol only; diagnostics go to stderr.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
from collections.abc import Callable
from typing import IO, Any

from aew.surface import SERVER_NAME, client, contract
from aew.surface.errors import AdapterInputError
from aew.surface.validate import check_call

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
BROKER_UNREACHABLE = -32001  # a server error: the Lead broker could not be reached; nothing about AEW is claimed
# Variables whose presence means this is not the Lead session's curated environment (the broker's own coordinates
# are expected; any credential, or another bridge's coordinates, is not).
FORBIDDEN_ENV = ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY", "AEW_INVOCATION",
                 "AEW_RUN", "AEW_WORK_UNIT")
INSTRUCTIONS = ("The AEW Lead's typed tools. Every result is a StageResult: `revision` is the expect_rev for your next "
                "mutation, and `projection` says which actions are AVAILABLE, BLOCKED or UNKNOWN and which decisions "
                "are yours. Decisions never have a default.")

Forward = Callable[[str, dict[str, Any], str], dict[str, Any]]  # (name, arguments, profile) -> StageResult


def environment_problem(env: dict[str, str]) -> str | None:
    """Why this environment is not one ``aew lead mcp`` may serve in, or ``None`` (fail closed, §4.1)."""
    if not env.get(client.ENV_ENDPOINT) or not env.get(client.ENV_KEY):
        return ("aew lead mcp serves only inside a live Lead session (`aew opencode` or `aew lead session`): "
                f"{client.ENV_ENDPOINT} and {client.ENV_KEY} are not set. It has no direct mode.")
    present = sorted(n for n in FORBIDDEN_ENV if env.get(n))
    if present:
        return ("aew lead mcp refuses to start: its environment carries " + ", ".join(present) + ", so it is not the "
                "Lead session's curated environment (a credential never reaches this process)")
    pattern = re.compile(r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}")  # harness.contract.CREDENTIAL_RE
    if any(pattern.search(v or "") for v in env.values()):
        return "aew lead mcp refuses to start: a credential-shaped value is in its environment"
    return None


def tool_entry(t: contract.Tool) -> dict[str, Any]:
    """One entry of ``tools/list``. The result schema is not advertised per tool (§4.4: it is structured content)."""
    return {"name": t.name, "description": t.description, "inputSchema": t.input_schema,
            "annotations": {"title": t.name.replace("_", " "), "readOnlyHint": not t.mutates,
                            "destructiveHint": False, "idempotentHint": t.kind in (contract.QUERY, contract.WAIT),
                            "openWorldHint": False}}


def tools_list(profile: str) -> dict[str, Any]:
    return {"tools": [tool_entry(t) for t in contract.exposed(profile)]}


class Server:
    def __init__(self, forward: Forward, *, profile: str = "normal", log: IO[str] | None = None) -> None:
        self.forward = forward
        self.profile = profile
        self.log = log or sys.stderr
        self.initialized = False

    # ------------------------------------------------------------------ framing

    def serve(self, stdin: IO[bytes], stdout: IO[bytes]) -> int:
        reader = io.TextIOWrapper(stdin, encoding="utf-8", newline="\n")
        for line in reader:
            if not line.strip():
                continue
            for reply in self.handle_line(line):
                stdout.write((json.dumps(reply, separators=(",", ":")) + "\n").encode("utf-8"))
                stdout.flush()
        return 0

    def handle_line(self, line: str) -> list[dict[str, Any]]:
        try:
            message = json.loads(line)
        except ValueError:
            return [_error(None, PARSE_ERROR, "not JSON")]
        if isinstance(message, list):  # a batch: each item answered on its own; notifications get no answer
            if not message:
                return [_error(None, INVALID_REQUEST, "an empty batch")]
            return [r for m in message if (r := self.handle(m)) is not None]
        reply = self.handle(message)
        return [] if reply is None else [reply]

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST,
                          "not a JSON-RPC 2.0 message")
        method, rid = message.get("method"), message.get("id")
        if not isinstance(method, str):
            return None  # a response to something we never asked: ignored
        notification = "id" not in message
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return None if notification else _error(rid, INVALID_PARAMS, "params must be an object")
        if method.startswith("notifications/"):
            if method == "notifications/initialized":
                self.initialized = True
            return None
        try:
            result = self.dispatch(method, params)
        except _RpcError as exc:
            return None if notification else _error(rid, exc.code, exc.message, exc.data)
        except Exception as exc:  # an implementation defect: reported, and the session goes on
            self.log.write(f"aew lead mcp: internal error in {method}: {type(exc).__name__}: {exc}\n")
            return None if notification else _error(rid, INTERNAL_ERROR, "internal error")
        return None if notification else {"jsonrpc": "2.0", "id": rid, "result": result}

    # ------------------------------------------------------------------ methods

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            asked = params.get("protocolVersion")
            from aew import __version__

            return {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "title": "AEW Lead", "version": __version__},
                    "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return tools_list(self.profile)
        if method == "tools/call":
            return self.call(params.get("name"), params.get("arguments", {}))
        if method in ("resources/list", "prompts/list"):
            return {method.split("/")[0]: []}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        raise _RpcError(METHOD_NOT_FOUND, f"no method {method}")

    def call(self, name: Any, arguments: Any) -> dict[str, Any]:
        try:
            check_call(name, arguments, self.profile)  # an ill-formed call never reaches the broker
            result = self.forward(str(name), arguments, self.profile)
        except AdapterInputError as exc:
            code = BROKER_UNREACHABLE if exc.code == "BROKER_UNREACHABLE" else INVALID_PARAMS
            raise _RpcError(code, exc.message, {"adapter_input_error": exc.to_dict()}) from None
        return {"content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}],
                "structuredContent": result, "isError": not result["ok"]}


class _RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


def _error(rid: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def broker_forward(name: str, arguments: dict[str, Any], profile: str) -> dict[str, Any]:
    return client.forward(name, arguments, ingress="mcp", profile=profile)


def serve(profile: str = "normal") -> int:
    """``aew lead mcp``: refuse outside a live Lead session, prove the broker is there, then serve stdio."""
    from aew import errors
    from aew.harness import bridge

    problem = environment_problem(dict(os.environ))
    if problem:
        raise errors.PermissionDenied(problem)
    try:
        bridge.call("lead.whoami", {}, env_names=client.ENV_NAMES)
    except errors.AEWError as exc:
        raise errors.StaleAuthority(f"aew lead mcp: the Lead broker is not live ({exc.message}); it has no direct "
                                    "mode") from None
    return Server(broker_forward, profile=profile).serve(sys.stdin.buffer, sys.stdout.buffer)
