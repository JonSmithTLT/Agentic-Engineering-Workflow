"""The dashboard server's local control channel (design note §4.2, R7).

``aew dashboard open`` and ``aew dashboard status`` reach the running ``aew dashboard serve`` process through a keyed
``multiprocessing.connection`` listener, the credential bridge's pattern: a random key in
``.aew/local/dashboard/control.key``, structured JSON (never pickle), one operation at a time. The key locates and
connects; it never authorizes. A session is authorized at the **serving process's console**: the server writes a
one-time code there, the requester types it at its own terminal and sends it back, and the server compares in constant
time, once, within the timeout. A process that read the key and forged a request still faces a code it cannot see.
"""

from __future__ import annotations

import hmac
import json
import os
import shutil
import threading
from collections.abc import Callable
from multiprocessing import AuthenticationError
from multiprocessing.connection import Client, Listener
from typing import Any

from aew import errors, operator
from aew.dashboard.session import SessionTable
from aew.harness.bridge import private_address, rebuild_error

OPEN_TIMEOUT_S = 300.0
MAX_MESSAGE = 64 * 1024
Console = Callable[[str], None]  # writes a prompt to the serving process's console


def open_prompt(requester: str) -> str:
    """What the requesting terminal shows while the operator reads the code off the server's console."""
    return operator.challenge(
        "", "OPEN a browser session on the read-only dashboard",
        requested_by=requester, destination=operator.credential_destination.get(),
        instruction="The terminal running `aew dashboard serve` now shows a one-time confirmation code. "
                    "Type it here and press Enter; anything else refuses.") + "> "


class ControlServer:
    """The serving side: ``open`` (challenge at the console, then mint) and ``status`` (live sessions, no secrets)."""

    def __init__(self, table: SessionTable, *, url_for_code: Callable[[str], str], console: Console | None,
                 status: Callable[[], dict[str, Any]], timeout: float = OPEN_TIMEOUT_S) -> None:
        self.table = table
        self.url_for_code = url_for_code
        self.console = console  # None: the serving process has no console, so nothing can be authorized
        self.status = status
        self.timeout = timeout
        self.key = os.urandom(32)
        self.address, self._family, self._private_dir = private_address()
        self._listener = Listener(self.address, family=self._family, authkey=self.key)
        self._closed = threading.Event()
        self._authorizing = threading.Lock()  # one challenge at a time: a code shown is a code that can be answered
        self._thread = threading.Thread(target=self._serve, name="aew-dashboard-control", daemon=True)
        self.opened = 0
        self.refused = 0

    @property
    def key_hex(self) -> str:
        return self.key.hex()

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                conn = self._listener.accept()
            except (AuthenticationError, OSError, EOFError):
                continue
            if self._closed.is_set():
                conn.close()
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: Any) -> None:
        try:
            try:
                op, args = _request(conn.recv_bytes(MAX_MESSAGE))
                if op == "status":
                    reply: dict[str, Any] = {"ok": True, "result": self.status()}
                elif op == "open":
                    reply = {"ok": True, "result": self._open(conn, args)}
                else:
                    raise errors.PermissionDenied(f"this dashboard control channel does not offer {op!r}",
                                                  offered=["open", "status"])
            except errors.AEWError as exc:
                self.refused += 1
                reply = {"ok": False, "error": exc.to_dict()}
            except Exception as exc:  # noqa: BLE001 (never let a request kill the server)
                self.refused += 1
                reply = {"ok": False, "error": {"code": "AEW_ERROR", "message": f"{type(exc).__name__}: {exc}"}}
            conn.send_bytes(json.dumps(reply, default=str).encode("utf-8"))
        except (OSError, EOFError):
            pass
        finally:
            conn.close()

    def _open(self, conn: Any, args: dict[str, Any]) -> dict[str, Any]:
        requester = str(args.get("requester") or "unknown")[:400]
        if self.console is None:
            raise errors.OperatorAuthorizationRequired(
                "the dashboard server has no console to show a confirmation code on, so no new session can be "
                "authorized; restart `aew dashboard serve` at a terminal")
        if not self._authorizing.acquire(blocking=False):
            raise errors.PermissionDenied("another `aew dashboard open` is waiting for the operator; try again after "
                                          "it is answered or times out")
        try:
            code = operator.new_code()
            self.console(operator.challenge(
                code, "ISSUE a browser session on the read-only dashboard",
                requested_by=f"{requester} (as reported by the requester; the code below is the authorization)",
                destination="the requesting terminal, as a one-time URL",
                instruction=f"Type the confirmation code {code} into the terminal that ran `aew dashboard open` "
                            "(not here); anything else there refuses."))
            conn.send_bytes(json.dumps({"ok": True, "result": {"challenge": "shown", "timeout_s": self.timeout}})
                            .encode("utf-8"))
            if not conn.poll(self.timeout):
                self.console("\n(the `aew dashboard open` request timed out; the code is void)\n")
                raise errors.PermissionDenied("operator authorization timed out")
            op, answer = _request(conn.recv_bytes(MAX_MESSAGE))
            given = str(answer.get("code", "")).strip().upper() if op == "answer" else ""
            if not hmac.compare_digest(given, code):
                self.console("\n(the `aew dashboard open` request was refused: wrong code)\n")
                raise errors.PermissionDenied("operator refused or mistyped the confirmation code")
            bootstrap = self.table.mint()
            self.opened += 1
            record = self.table.newest()
            self.console("\n(a browser session was issued to the requesting terminal)\n")
            return {"session_url": self.url_for_code(bootstrap), "expires_at": record["expires_at"]}
        finally:
            self._authorizing.release()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._thread.is_alive():  # unblock accept() so the serving thread observes the closure
            try:  # (a listener nobody accepts on would make this connect wait forever on a Windows pipe)
                Client(self.address, family=self._family, authkey=self.key).close()
            except Exception:  # noqa: S110, BLE001 (best effort)
                pass
        try:
            self._listener.close()
        except OSError:
            pass
        if self._private_dir:
            shutil.rmtree(self._private_dir, ignore_errors=True)


def _request(raw: bytes) -> tuple[str, dict[str, Any]]:
    try:
        message = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise errors.UsageError("a control request is one JSON object") from None
    if not isinstance(message, dict) or set(message) != {"op", "args"} or not isinstance(message["args"], dict):
        raise errors.UsageError("a control request is exactly {op, args}")
    return str(message["op"]), message["args"]


def _connect(endpoint: str, key_hex: str) -> Any:
    family = "AF_PIPE" if endpoint.startswith("\\\\.\\pipe\\") else "AF_UNIX"
    try:
        key = bytes.fromhex(key_hex)
    except ValueError:
        raise errors.UsageError("the dashboard control key file is not a key") from None
    try:
        return Client(endpoint, family=family, authkey=key)
    except AuthenticationError:
        raise errors.PermissionDenied("the dashboard server refused this key; its key file is stale") from None
    except (OSError, EOFError):
        raise errors.NotFound("no dashboard server answers at its recorded endpoint; start one with "
                              "`aew dashboard serve`", endpoint=endpoint) from None


def _reply(conn: Any) -> dict[str, Any]:
    try:
        reply = json.loads(conn.recv_bytes(MAX_MESSAGE).decode("utf-8"))
    except (OSError, EOFError):
        raise errors.NotFound("the dashboard server closed the control connection") from None
    if not reply.get("ok"):
        raise rebuild_error(reply.get("error") or {})
    return reply["result"]


def request_session(endpoint: str, key_hex: str, *, ask: Callable[[str], str] | None = None,
                    requester: str | None = None) -> dict[str, Any]:
    """The ``aew dashboard open`` side: ask the server for a session, read the code the operator types at **this**
    terminal, send it, and return the server's result (``session_url``, ``expires_at``)."""
    from aew.harness.procs import process_chain

    who = requester if requester is not None else (" <- ".join(process_chain()) or "unknown")
    read = ask if ask is not None else (lambda prompt: operator.ask(prompt))
    conn = _connect(endpoint, key_hex)
    try:
        conn.send_bytes(json.dumps({"op": "open", "args": {"requester": who}}).encode("utf-8"))
        _reply(conn)  # the challenge is now on the server's console
        try:
            answer = read(open_prompt(who))
        except errors.AEWError:
            try:  # void the code on the server, and let it finish refusing before this side reports
                conn.send_bytes(json.dumps({"op": "answer", "args": {"code": ""}}).encode("utf-8"))
                _reply(conn)
            except errors.AEWError:
                pass
            raise
        try:
            conn.send_bytes(json.dumps({"op": "answer", "args": {"code": answer.strip()}}).encode("utf-8"))
        except (OSError, EOFError):
            # The server gave up waiting (its timeout) and closed the request before the code arrived.
            try:
                _reply(conn)  # its refusal, when it is still readable
            except errors.NotFound:
                pass
            raise errors.PermissionDenied("operator authorization timed out: the dashboard server closed the request "
                                          "before the code arrived") from None
        return _reply(conn)
    finally:
        conn.close()


def request_status(endpoint: str, key_hex: str) -> dict[str, Any]:
    conn = _connect(endpoint, key_hex)
    try:
        conn.send_bytes(json.dumps({"op": "status", "args": {}}).encode("utf-8"))
        return _reply(conn)
    finally:
        conn.close()
