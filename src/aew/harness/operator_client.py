"""The operator endpoint's client side (M4-E plan v3 §2.1): locate it, ping it, and ask it for a raise.

It holds no authority and constructs nothing the engine accepts as the operator's: only the endpoint
(``aew.harness.operator_endpoint``, imported by ``aew operator serve`` alone) builds an ``OperatorPrincipal``. Every
client command only sends a request; the operator's answer is the code shown on the endpoint's console, typed here.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from multiprocessing.connection import Client
from pathlib import Path
from typing import Any

from aew import errors, operator
from aew.harness import procs
from aew.harness.bridge import rebuild_error

LOCATOR_REL = "local/operator/endpoint.json"
LOCK_NAME = "endpoint.lock"  # beside the locator: held by the live endpoint for its whole life
LOCATOR_SCHEMA = "aew/operator-endpoint/v1"
MAX_MESSAGE = 16 * 1024
CHALLENGE_TIMEOUT_S = 300.0
WAKE_TIMEOUT_S = 5.0
OPERATIONS = ("ping", "mode_raise")
# What a Lead running as the operator's uid can still do (plan v3 §2.1, "the same-uid residuals, stated in full").
# Reported by ping, status and doctor, and never claimed as closed: production authority needs F18.6.
RESIDUALS = (
    "run the endpoint's code in its own Python process (bypassing the CLI's refusals) and answer its own challenge "
    "through a pty",
    "read or inject into the operator's terminal device",
    "kill this endpoint and start another once the stale-locator check passes",
    "write control state or .aew/ files directly (the protected set is not owned by another principal until F18.6)",
)

def locator_path(aew_root: Path) -> Path:
    return Path(aew_root) / LOCATOR_REL


def _same_process(locator: dict[str, Any]) -> bool:
    pid = locator.get("pid")
    started = locator.get("process_started")
    if not isinstance(pid, int) or not procs.pid_alive(pid):
        return False
    if isinstance(started, int | float):
        return procs.same_process(pid, float(started))
    return True  # alive and unprovable: never replaced


def read_locator(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == LOCATOR_SCHEMA else None


# ---------------------------------------------------------------------------------------------- the client side


def _request(raw: bytes) -> tuple[str, dict[str, Any]]:
    try:
        message = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise errors.UsageError("an operator endpoint request is one JSON object") from None
    if not isinstance(message, dict) or set(message) != {"op", "args"} or not isinstance(message["args"], dict):
        raise errors.UsageError("an operator endpoint request is exactly {op, args}")
    return str(message["op"]), message["args"]


def _connect(aew_root: Path) -> Any:
    data = read_locator(locator_path(aew_root))
    if data is None:
        raise errors.NotFound("no operator endpoint is running for this project: the operator starts one in their own "
                              "terminal with `aew operator serve --dev`")
    if not data.get("address"):
        raise errors.NotFound("the operator endpoint is still starting; try again in a moment")
    try:
        return Client(data["address"], family=data["family"])
    except (OSError, EOFError):
        raise errors.NotFound("no operator endpoint answers at its recorded address; the operator starts one with "
                              "`aew operator serve --dev`", address=data["address"]) from None


def _reply(conn: Any) -> dict[str, Any]:
    try:
        reply = json.loads(conn.recv_bytes(MAX_MESSAGE).decode("utf-8"))
    except (OSError, EOFError):
        raise errors.NotFound("the operator endpoint closed the connection") from None
    if not reply.get("ok"):
        raise rebuild_error(reply.get("error") or {})
    return reply["result"]


def _send(conn: Any, op: str, args: dict[str, Any]) -> None:
    """Send the request. The endpoint refuses a peer that is not the operator principal before it reads anything,
    and may already have closed: its refusal is then the reply to read."""
    try:
        conn.send_bytes(json.dumps({"op": op, "args": args}).encode("utf-8"))
    except (OSError, EOFError):
        _reply(conn)  # raises the endpoint's refusal (or NotFound when there is none)
        raise errors.NotFound("the operator endpoint closed the connection") from None


def ping(aew_root: Path) -> dict[str, Any]:
    conn = _connect(aew_root)
    try:
        _send(conn, "ping", {})
        return _reply(conn)
    finally:
        conn.close()


def status(aew_root: Path) -> dict[str, Any]:
    """The endpoint as ``status`` shows it, without connecting: the locator, and whether its process is alive."""
    data = read_locator(locator_path(aew_root))
    if data is None:
        return {"running": False}
    return {"running": _same_process(data), "pid": data.get("pid"), "started_at": data.get("started_at"),
            "guarantee": data.get("guarantee")}


def raise_prompt(bound: dict[str, Any], requester: str) -> str:
    return operator.challenge(
        "", f"RAISE the Lead's steering mode to {bound['mode']} for Lead generation {bound['generation']}",
        requested_by=requester, destination="a steering mode record (no credential is issued)",
        instruction="The terminal running `aew operator serve` now shows a one-time confirmation code. Type it here "
                    "and press Enter; anything else refuses.") + "> "


def request_raise(aew_root: Path, mode: str, *, ask: Callable[[str], str] | None = None,
                  requester: str | None = None) -> dict[str, Any]:
    """``aew lead mode raise``: ask the endpoint, read the code the operator types at **this** terminal, send it."""
    who = requester if requester is not None else (" <- ".join(procs.process_chain()) or "unknown")
    read = ask if ask is not None else (lambda prompt: operator.ask(prompt))
    conn = _connect(aew_root)
    try:
        _send(conn, "mode_raise", {"mode": mode, "requester": who})
        shown = _reply(conn)
        try:
            answer = read(raise_prompt(shown["bound"], who))
        except errors.AEWError:
            try:  # void the code at the endpoint, and let it finish refusing
                conn.send_bytes(json.dumps({"op": "answer", "args": {"code": ""}}).encode("utf-8"))
                _reply(conn)
            except errors.AEWError:
                pass
            raise
        try:
            conn.send_bytes(json.dumps({"op": "answer", "args": {"code": answer.strip()}}).encode("utf-8"))
        except (OSError, EOFError):
            try:
                _reply(conn)
            except errors.NotFound:
                pass
            raise errors.PermissionDenied("operator authorization timed out: the endpoint closed the request before "
                                          "the code arrived") from None
        return _reply(conn)
    finally:
        conn.close()


def wait_for_locator(aew_root: Path, timeout: float = 10.0) -> dict[str, Any] | None:
    """For tests and tooling: the locator once a starting endpoint has written its address."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = read_locator(locator_path(aew_root))
        if data and data.get("address"):
            return data
        time.sleep(0.05)
    return None
