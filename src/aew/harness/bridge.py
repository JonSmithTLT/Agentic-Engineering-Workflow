"""Credential custody bridge (ADR-0009; ADR-0005 amendment).

Invariant: **an agent can exercise exactly its invocation's authorized operations without possessing, or
being able to print, the raw AEW credential.**

The run supervisor holds the invocation credential in memory. It serves this bridge on a local
endpoint (a named pipe on Windows, an AF_UNIX socket in a private directory on POSIX) guarded by a
per-run random key: ``multiprocessing.connection``'s HMAC challenge, so the key itself never crosses
the connection. The agent's environment carries only the endpoint and the key; the ``aew`` CLI routes
``check run``, ``submit`` and ``whoami`` here when no credential is supplied.

* Requests are **structured JSON** (``send_bytes``/``recv_bytes``): never pickle, which would let an
  authenticated client run code inside the credential-holding supervisor.
* Only three operations exist, each with exact arguments. A request cannot name an invocation, run or
  credential: the bridge acts only as its own run.
* The supervisor executes each request through the AEW engine with the held credential, so the engine's
  authority and scope checks stay authoritative. The bridge adds no authority.
* The key is a run-scoped capability deliberately usable by every process the agent starts (they are the
  agent). It is not the AEW credential, and it is useless once the run ends, rotates or is revoked:
  the supervisor refuses and closes the bridge.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
from collections.abc import Callable
from multiprocessing.connection import Client, Listener
from multiprocessing import AuthenticationError
from pathlib import Path
from typing import Any

from aew import errors
from aew.harness.contract import redact

ENV_ENDPOINT = "AEW_AGENT_ENDPOINT"
ENV_KEY = "AEW_AGENT_KEY"
OPERATIONS: dict[str, frozenset[str]] = {
    "whoami": frozenset(),
    "check.run": frozenset({"check_id"}),
    "submit": frozenset({"kind", "text"}),
}
MAX_REQUEST = 16 * 1024 * 1024
IS_WINDOWS = sys.platform == "win32"


def _error_classes() -> dict[str, type[errors.AEWError]]:
    out: dict[str, type[errors.AEWError]] = {}
    stack: list[type[errors.AEWError]] = [errors.AEWError]
    while stack:
        cls = stack.pop()
        out.setdefault(cls.code, cls)
        stack.extend(cls.__subclasses__())
    return out


def rebuild_error(err: dict[str, Any]) -> errors.AEWError:
    cls = _error_classes().get(err.get("code", ""), errors.AEWError)
    exc = cls(err.get("message", "AEW bridge error"), **(err.get("details") or {}))
    if cls is errors.AEWError:
        exc.code = err.get("code", exc.code)
    return exc


def validate_request(request: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(request, dict) or set(request) != {"op", "args"} or not isinstance(request["args"], dict):
        raise errors.UsageError("a bridge request is exactly {op, args}")
    op, args = request["op"], request["args"]
    if op not in OPERATIONS:
        raise errors.PermissionDenied(f"the AEW bridge does not offer {op!r}", offered=sorted(OPERATIONS))
    if set(args) != OPERATIONS[op]:
        raise errors.UsageError(f"{op} takes exactly {sorted(OPERATIONS[op])}; the bridge acts only as its own run "
                                "(no invocation, run or credential can be named)", got=sorted(args))
    if not all(isinstance(v, str) for v in args.values()):
        raise errors.UsageError(f"{op} arguments are strings")
    return op, args


class BridgeServer:
    """The supervisor side. ``handler(op, args)`` runs one request with the held credential."""

    def __init__(self, handler: Callable[[str, dict[str, Any]], Any]) -> None:
        self.handler = handler
        self.key = secrets.token_bytes(32)
        self._private_dir: str | None = None
        if IS_WINDOWS:
            self.address = r"\\.\pipe\aew-bridge-" + secrets.token_hex(16)
            family = "AF_PIPE"
        else:
            self._private_dir = tempfile.mkdtemp(prefix="aew-bridge-")
            os.chmod(self._private_dir, 0o700)
            self.address = os.path.join(self._private_dir, "s")
            family = "AF_UNIX"
        self._listener = Listener(self.address, family=family, authkey=self.key)
        self._closed = threading.Event()
        self._serial = threading.Lock()  # one engine operation at a time
        self._thread = threading.Thread(target=self._serve, name="aew-bridge", daemon=True)
        self.requests = 0
        self.refused = 0
        self._in_flight = 0
        self._idle = threading.Condition()

    @property
    def key_hex(self) -> str:
        return self.key.hex()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        while not self._closed.is_set():
            try:
                conn = self._listener.accept()
            except (AuthenticationError, OSError, EOFError):
                continue  # a client without the key, or one that went away mid-handshake
            if self._closed.is_set():
                conn.close()
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: Any) -> None:
        with self._idle:
            self._in_flight += 1
        try:
            raw = conn.recv_bytes(MAX_REQUEST)
            try:
                op, args = validate_request(json.loads(raw.decode("utf-8")))
                with self._serial:
                    if self._closed.is_set():
                        raise errors.StaleAuthority("this run's AEW bridge is closed: the run ended, was superseded, "
                                                    "or its invocation ended")
                    self.requests += 1
                    result = self.handler(op, args)
                reply: dict[str, Any] = {"ok": True, "result": result}
            except errors.AEWError as exc:
                self.refused += 1
                reply = {"ok": False, "error": exc.to_dict()}
            except (ValueError, UnicodeDecodeError):
                self.refused += 1
                reply = {"ok": False, "error": {"code": "USAGE", "message": "a bridge request is one JSON object"}}
            except Exception as exc:  # never let a request kill the supervisor
                self.refused += 1
                reply = {"ok": False, "error": {"code": "BRIDGE_ERROR", "message": f"{type(exc).__name__}: {exc}"}}
            conn.send_bytes(redact(json.dumps(reply, default=str)).encode("utf-8"))
        except (OSError, EOFError):
            pass
        finally:
            conn.close()
            with self._idle:
                self._in_flight -= 1
                self._idle.notify_all()

    def drain(self, timeout: float) -> bool:
        """Wait for requests already being handled to finish (each is refused or completed by the engine)."""
        with self._idle:
            return self._idle.wait_for(lambda: self._in_flight == 0, timeout)

    def close(self) -> None:
        """Stop serving. Requests already waiting are refused; new connections fail."""
        if self._closed.is_set():
            return
        # No waiting for an operation in flight: the engine re-checks the credential under the control lock
        # before it writes anything, so an operation that races a revocation is refused there.
        self._closed.set()
        threading.Thread(target=self._wake, daemon=True).start()

    def _wake(self) -> None:
        try:  # unblock accept() so the serving thread observes the closure
            Client(self.address, family="AF_PIPE" if IS_WINDOWS else "AF_UNIX", authkey=self.key).close()
        except Exception:
            pass
        try:
            self._listener.close()
        except OSError:
            pass
        if self._private_dir:
            shutil.rmtree(self._private_dir, ignore_errors=True)


def available() -> bool:
    return bool(os.environ.get(ENV_ENDPOINT))


def call(op: str, args: dict[str, Any], *, endpoint: str | None = None, key: str | None = None) -> Any:
    """The agent side: forward one operation to this run's supervisor."""
    endpoint = endpoint or os.environ.get(ENV_ENDPOINT)
    key = key or os.environ.get(ENV_KEY)
    if not endpoint or not key:
        raise errors.UsageError(f"no AEW bridge: {ENV_ENDPOINT} and {ENV_KEY} are not set")
    family = "AF_PIPE" if endpoint.startswith("\\\\.\\pipe\\") else "AF_UNIX"
    try:
        authkey = bytes.fromhex(key)
    except ValueError:
        raise errors.UsageError(f"{ENV_KEY} is not a bridge key") from None
    try:
        conn = Client(endpoint, family=family, authkey=authkey)
    except AuthenticationError:
        raise errors.PermissionDenied("the AEW bridge refused this key: it belongs to a different run") from None
    except (OSError, EOFError):
        raise errors.StaleAuthority("this run's AEW bridge is closed: the run ended, was superseded, or its "
                                    "invocation ended; nothing more can be recorded by it", endpoint=endpoint) from None
    try:
        conn.send_bytes(json.dumps({"op": op, "args": args}).encode("utf-8"))
        reply = json.loads(conn.recv_bytes(MAX_REQUEST).decode("utf-8"))
    except (OSError, EOFError):
        raise errors.StaleAuthority("the AEW bridge closed during the request; its outcome was not confirmed",
                                    endpoint=endpoint) from None
    finally:
        conn.close()
    if not reply.get("ok"):
        raise rebuild_error(reply.get("error") or {})
    return reply["result"]


def read_submission(path: str) -> str:
    """``--file`` is read by the client, in the agent's own working directory."""
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")
