"""``aew operator serve``: the operator endpoint (M4-E plan v3 §2.1; A1 §1.1; F18 §2.1 to §2.3).

The one place an :class:`~aew.engine.steering.OperatorPrincipal` is constructed (a static test pins it), so the one way
an autonomy increase reaches the engine. Three layers, each doing one job (operator, 2026-10-07):

- **Who is authorized:** the peer check. POSIX: an AF_UNIX socket in a directory the service creates 0700, and each
  connection's peer credentials (``SO_PEERCRED``) must equal the uid that runs the service. Windows: a named pipe,
  whose default access list admits the creating user, administrators and SYSTEM; there is no peer check beyond it,
  which the ``dev`` label says.
- **Did that human intend this exact action:** a one-time code shown on **this process's console** and typed at the
  requesting terminal. It is held only in this process's memory (Linux: the process is made non-dumpable, so a
  same-uid process cannot read it through ``ptrace`` or ``/proc/<pid>/mem``) and never written to the requester.
- **What the approval applies to:** the Lead generation and legality digest shown with the challenge; the engine's
  commit refuses if either moved, and records both digests, the revision and this endpoint's pid and start time.

**One endpoint, never from a Lead session.** It refuses to start inside a Lead session (the broker's environment, or
a Lead session's broker or harness among its ancestors) and while another endpoint for the project answers. Its
locator (``.aew/local/operator/endpoint.json``) is created exclusively and only locates: it never authorizes. A stale
one is replaced only once its process is proven gone.

**The label.** Every record is ``guarantee: dev``, and the endpoint starts only with ``--dev``: until F18.6 the
operator principal cannot be shown distinct from the Lead host's. What a same-uid Lead can still do is
:data:`RESIDUALS`; none of these barriers is a security boundary against it (plan v3 §2.1).

The protocol is the dashboard control channel's (F20.3): one JSON request per connection, ``{op, args}``, never pickle,
bounded size, one challenge at a time. E2's operations are ``ping`` and ``mode_raise``; ``confirm`` (E7), the
publication grants (E6b) and the relaunch breaker reset (E8) join them.
"""

from __future__ import annotations

import hmac
import json
import os
import socket
import struct
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any

from aew import errors, operator
from aew.engine.steering import GUARANTEE, OperatorPrincipal
from aew.harness import procs
from aew.harness.bridge import private_address
from aew.harness.operator_client import (
    CHALLENGE_TIMEOUT_S,
    LOCATOR_SCHEMA,
    MAX_MESSAGE,
    OPERATIONS,
    RESIDUALS,
    WAKE_TIMEOUT_S,
    _request,
    _same_process,
    locator_path,
    read_locator,
)

Console = Callable[[str], None]


def lead_session_problem(env: dict[str, str] | None = None) -> str | None:
    """Why this process is inside a Lead session, or ``None`` (plan v3 §2.1, P1). Dev-grade: it reads the broker's
    environment and the process chain; a same-uid process that hides both is one of :data:`RESIDUALS`."""
    env = dict(os.environ) if env is None else env
    if env.get("AEW_LEAD_BROKER") or env.get("AEW_LEAD_BROKER_KEY"):
        return "this process runs in a Lead session (its environment carries the Lead broker's coordinates)"
    if not sys.platform.startswith("linux"):  # pragma: windows-only
        return None
    pid, seen = os.getppid(), 0  # pragma: posix-only
    while pid > 1 and seen < 64:
        seen += 1
        proc = Path(f"/proc/{pid}")
        try:
            argv = [a.decode("utf-8", "replace") for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
        except OSError:
            break
        if _is_lead_session(argv):
            return f"an ancestor process ({pid}: {' '.join(argv)[:120]}) is a Lead session"
        try:
            if b"\0AEW_LEAD_BROKER=" in b"\0" + (proc / "environ").read_bytes():
                return f"an ancestor process ({pid}) runs in a Lead session"
        except OSError:
            pass  # another uid's, or a hardened broker's: its command line was checked above
        try:
            pid = int((proc / "stat").read_text(encoding="latin-1").rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return None


def _is_lead_session(argv: list[str]) -> bool:
    """``aew lead session ...``, ``aew opencode ...`` (and ``python -m aew`` forms)."""
    for i, word in enumerate(argv):
        if os.path.basename(word) in ("aew", "aew.exe") or (word == "aew" and i and argv[i - 1] == "-m"):
            rest = [w for w in argv[i + 1:] if not w.startswith("-")]
            return rest[:2] == ["lead", "session"] or rest[:1] == ["opencode"]
    return False


def peer_uid(conn: Any) -> int | None:
    """The peer's uid on a connected AF_UNIX socket (Linux ``SO_PEERCRED``)."""
    sock = socket.socket(fileno=os.dup(conn.fileno()))
    try:
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))  # type: ignore[attr-defined]
    finally:
        sock.close()
    return struct.unpack("3i", raw)[1]


def harden() -> None:
    """PR_SET_DUMPABLE 0 (Linux): a same-uid process cannot read the challenge code, held only in this process's
    memory, through ``ptrace`` or ``/proc/<pid>/mem`` (Rocky 8's default ``yama.ptrace_scope`` is 0; plan v3 §2.1)."""
    procs.harden_current_process()


def _dumpable() -> bool | None:
    if not sys.platform.startswith("linux"):  # pragma: windows-only
        return None
    import ctypes  # pragma: posix-only

    return bool(ctypes.CDLL(None, use_errno=True).prctl(3, 0, 0, 0, 0))  # PR_GET_DUMPABLE


class OperatorEndpoint:
    """The serving side. ``engine`` is the project's engine; ``console`` writes to this process's own terminal."""

    def __init__(self, engine: Any, *, console: Console, dev: bool, timeout: float = CHALLENGE_TIMEOUT_S) -> None:
        if not dev:
            raise errors.OperatorAuthorizationRequired(
                "the operator endpoint starts only with --dev: on this host the operator principal cannot be shown "
                "distinct from the Lead host's (F18.6 has not built that check), so every record it makes is "
                "labelled `guarantee: dev` and is not A1/F18 production authority", guarantee=GUARANTEE)
        problem = lead_session_problem()
        if problem:
            raise errors.PermissionDenied(f"`aew operator serve` refuses to start: {problem}. The operator endpoint "
                                          "runs only in the operator's own terminal")
        if not sys.platform.startswith("linux") and sys.platform != "win32":
            raise errors.UsageError("the operator endpoint needs peer credentials (Linux) or a named pipe (Windows)")
        self.engine = engine
        self.console = console
        self.timeout = timeout
        self.uid = os.getuid() if hasattr(os, "getuid") else None
        self.pid = os.getpid()
        self.started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._started = procs.started_at(self.pid)
        self._locator = locator_path(engine.aew_root)
        self._closed = threading.Event()
        self._authorizing = threading.Lock()  # one challenge at a time
        self._engine_lock = threading.Lock()
        self._listener: Any = None
        self._thread: threading.Thread | None = None
        self.address = ""
        self.family = ""
        self._private_dir: str | None = None
        self.refused = 0

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Claim the locator and serve. ``aew operator serve`` hardens its process first (:func:`harden`)."""
        self._claim_locator()
        try:
            self.address, self.family, self._private_dir = private_address()
            self._listener = Listener(self.address, family=self.family)  # no key: the peer check authorizes
            self._write_locator()
        except BaseException:
            self._locator.unlink(missing_ok=True)
            raise
        self._thread = threading.Thread(target=self._serve, name="aew-operator-endpoint", daemon=True)
        self._thread.start()

    def serve_forever(self) -> None:
        try:
            while not self._closed.wait(0.5):
                pass
        finally:
            self.close()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._thread is not None and self._thread.is_alive():
            # The serving thread observes the closure only after an accept, so this connection always has a taker;
            # it runs on its own thread, bounded, so closing never waits on it (the 2026-10-08 CI hangs).
            waker = threading.Thread(target=self._wake, daemon=True)
            waker.start()
            waker.join(WAKE_TIMEOUT_S)
            self._thread.join(WAKE_TIMEOUT_S)
        try:
            if self._listener is not None:
                self._listener.close()
        except OSError:
            pass
        if self._private_dir:
            import shutil

            shutil.rmtree(self._private_dir, ignore_errors=True)
        try:
            data = json.loads(self._locator.read_text(encoding="utf-8"))
            if data.get("pid") == self.pid:
                self._locator.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass

    def _wake(self) -> None:
        try:
            Client(self.address, family=self.family).close()
        except Exception:  # noqa: S110, BLE001 (best effort)
            pass

    def _claim_locator(self) -> None:
        """Create the locator exclusively; replace a stale one only once its process is proven gone."""
        self._locator.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self._locator, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                other = read_locator(self._locator)
                if other is None or not _same_process(other):
                    self._locator.unlink(missing_ok=True)  # its process is gone (or the file is not a locator)
                    continue
                raise errors.PermissionDenied(
                    f"another operator endpoint for this project is live (pid {other.get('pid')}, started "
                    f"{other.get('started_at')}); one endpoint per project: use it, or stop it first",
                    pid=other.get("pid")) from None
            with os.fdopen(fd, "w", encoding="utf-8") as f:  # who claims it, from the first byte: never empty
                f.write(json.dumps(self._locator_data()) + "\n")
            return
        raise errors.PermissionDenied("could not claim the operator endpoint's locator; another endpoint is starting")

    def _locator_data(self) -> dict[str, Any]:
        return {"schema": LOCATOR_SCHEMA, "address": self.address, "family": self.family, "pid": self.pid,
                "process_started": self._started, "started_at": self.started_at, "uid": self.uid,
                "guarantee": GUARANTEE}

    def _write_locator(self) -> None:
        data = self._locator_data()
        tmp = self._locator.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self._locator)

    # ------------------------------------------------------------------ serving

    def _serve(self) -> None:
        while True:
            try:
                conn = self._listener.accept()
            except (OSError, EOFError):
                if self._closed.is_set():
                    return
                continue
            if self._closed.is_set():
                conn.close()
                return
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _peer_problem(self, conn: Any) -> str | None:
        if self.family != "AF_UNIX":  # pragma: windows-only (the pipe's access list; labelled dev)
            return None
        try:
            uid = peer_uid(conn)
        except OSError as exc:
            return f"the peer's credentials could not be read ({exc})"
        if uid != self.uid:
            return f"the connecting process runs as uid {uid}, not the operator principal (uid {self.uid})"
        return None

    def _handle(self, conn: Any) -> None:
        try:
            try:
                refusal = self._peer_problem(conn)  # before anything is read or shown
                if refusal:
                    raise errors.PermissionDenied(f"the operator endpoint refused the connection: {refusal}",
                                                  reason="peer_check")
                op, args = _request(conn.recv_bytes(MAX_MESSAGE))
                if op == "ping":
                    reply: dict[str, Any] = {"ok": True, "result": self.ping()}
                elif op == "mode_raise":
                    reply = {"ok": True, "result": self._mode_raise(conn, args)}
                else:
                    raise errors.PermissionDenied(f"the operator endpoint does not offer {op!r}",
                                                  offered=list(OPERATIONS))
            except errors.AEWError as exc:
                self.refused += 1
                reply = {"ok": False, "error": exc.to_dict()}
            except Exception as exc:  # noqa: BLE001 (never let a request kill the endpoint)
                self.refused += 1
                reply = {"ok": False, "error": {"code": "AEW_ERROR", "message": f"{type(exc).__name__}: {exc}"}}
            conn.send_bytes(json.dumps(reply, default=str).encode("utf-8"))
        except (OSError, EOFError):
            pass
        finally:
            conn.close()

    def ping(self) -> dict[str, Any]:
        """Liveness and the label; no challenge, and nothing secret."""
        return {"alive": True, "pid": self.pid, "started_at": self.started_at, "uid": self.uid,
                "guarantee": GUARANTEE, "dumpable": _dumpable(), "operations": list(OPERATIONS),
                "residuals": list(RESIDUALS)}

    def _mode_raise(self, conn: Any, args: dict[str, Any]) -> dict[str, Any]:
        mode = str(args.get("mode") or "")
        requester = str(args.get("requester") or "unknown")[:400]
        if not self._authorizing.acquire(blocking=False):
            raise errors.PermissionDenied("another request is waiting for the operator at this endpoint; try again "
                                          "after it is answered or times out")
        try:
            with self._engine_lock:
                bound = self.engine.steering_raise_preview(mode)  # refused here before the operator is asked
            code = operator.new_code()
            self.console(operator.challenge(
                code,
                f"Project '{bound['project']}': RAISE the Lead's steering mode {bound['previous'] or 'none'} -> "
                f"{mode}\n"
                f"  for Lead generation : {bound['generation']} (ends with that generation)\n"
                f"  legality digest     : {bound['legality_digest']}\n"
                f"  guarantee           : {GUARANTEE} (not production authority until F18.6)",
                requested_by=f"{requester} (as reported by the requester; the code below is the authorization)",
                destination="a steering mode record (no credential is issued)",
                instruction=f"Type the confirmation code {code} into the terminal that ran `aew lead mode raise` "
                            "(not here); anything else there refuses."))
            conn.send_bytes(json.dumps({"ok": True, "result": {"challenge": "shown", "timeout_s": self.timeout,
                                                               "bound": bound}}).encode("utf-8"))
            if not conn.poll(self.timeout):
                self.console("\n(the `aew lead mode raise` request timed out; the code is void)\n")
                raise errors.PermissionDenied("operator authorization timed out")
            op, answer = _request(conn.recv_bytes(MAX_MESSAGE))
            given = str(answer.get("code", "")).strip().upper() if op == "answer" else ""
            if not hmac.compare_digest(given, code):
                self.console("\n(the `aew lead mode raise` request was refused: wrong code)\n")
                raise errors.PermissionDenied("operator refused or mistyped the confirmation code")
            principal = OperatorPrincipal(uid=self.uid, method="peer_credentials" if self.family == "AF_UNIX"
                                          else "named_pipe", endpoint_pid=self.pid,
                                          endpoint_started_at=self.started_at)
            with self._engine_lock:
                out = self.engine.steering_raise(principal, mode=mode, generation=bound["generation"],
                                                 legality_digest=bound["legality_digest"])
            self.console(f"\n(steering mode raised to {mode} for Lead generation {bound['generation']}: "
                         f"{out['record']})\n")
            return out
        finally:
            self._authorizing.release()


