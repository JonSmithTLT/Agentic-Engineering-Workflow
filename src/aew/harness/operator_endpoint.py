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
a Lead session's broker or harness among its ancestors) and while another endpoint for the project is live: the live
endpoint holds the project's endpoint lock (``.aew/local/operator/endpoint.lock``) for its whole life, and writes its
locator (``endpoint.json``) only under it. The locator only locates: it never authorizes. A locator found while the lock
is free is stale by proof (the OS releases the lock when its holder dies) and is overwritten.

**The label.** Every record is ``guarantee: dev``, and the endpoint starts only with ``--dev``: until F18.6 the
operator principal cannot be shown distinct from the Lead host's. What a same-uid Lead can still do is
:data:`RESIDUALS`; none of these barriers is a security boundary against it (plan v3 §2.1).

The protocol is the dashboard control channel's (F20.3): one JSON request per connection, ``{op, args}``, never pickle,
bounded size, one challenge at a time. E2's operations are ``ping`` and ``mode_raise``; ``confirm`` (M4-E E7c), the
publication grants (E6b) and the relaunch breaker reset (E8b) join them (plan v3 amendment 1). ``capability_change``
is the capability register's operator changes (CAP-1; the designer's ruling 1): the register is per host, so a
project's endpoint authorizes a change every project on the host reads.

**Started by a Lead session** (``aew opencode``, :mod:`aew.harness.operator_autostart`): the same endpoint with the
same refusals, in the background, reparented so that no Lead session is its ancestor. It stops once no session it serves
is live. A G3 approval needs no console. A typed code does: on Windows it has a console of its own, shown when a
challenge needs it (:mod:`aew.harness.operator_window`). On Linux it has no terminal, so it says to run
`aew operator serve --dev` and stops, so that command can take the lock.

**G3** (:mod:`aew.harness.g3_adapter`): where G3 counts and the operation is bound, a consumed approval stands in for
the typed code, for that one challenge. No code is made, and the console shows only the outcome, as the typed path's
does: the operator's PIN goes only in G3's confirmer. A requester that has gone ends the wait, as it voids a typed code.
Everything else here is unchanged, and the engine's checks all still run.

**Notification** (plan v3 §2.8; M4-E E7a). The endpoint runs the notifier's watcher (``aew.harness.notify``) for its
whole life, on threads of its own and through an engine of its own: it reads control state, the event spool and the
broker's liveness record, commits nothing, and never takes ``_authorizing`` or ``_engine_lock``, so a slow notifier
never delays a challenge.
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
from typing import Any

from aew import errors, operator
from aew.engine.lock import FileLock
from aew.engine.steering import GUARANTEE, OperatorPrincipal
from aew.errors import LockTimeout
from aew.harness import g3_adapter, notify, procs
from aew.harness.bridge import private_address
from aew.harness.operator_client import (
    CHALLENGE_TIMEOUT_S,
    LOCATOR_SCHEMA,
    LOCK_NAME,
    MAX_MESSAGE,
    OPERATIONS,
    RESIDUALS,
    WAKE_TIMEOUT_S,
    _request,
    lead_session_problem,
    locator_path,
    no_session_left,
    read_locator,
)

Console = Callable[[str], None]
CLAIM_TIMEOUT_S = 0.5  # long enough to ride out another starter's failed claim, never a wait for a live endpoint
# A background endpoint rides out one that is stopping: `close`'s three bounded waits, then the ordinary claim
STOPPING_S = 3 * WAKE_TIMEOUT_S + CLAIM_TIMEOUT_S
NO_CONSOLE = ("this operator endpoint runs in the background and cannot show a confirmation code here ({why}), so it "
              "has stopped. Run `aew operator serve --dev` in another terminal, and ask again")


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

    def __init__(self, engine: Any, *, console: Console, dev: bool, timeout: float = CHALLENGE_TIMEOUT_S,
                 background: bool = False, console_done: Callable[[], None] | None = None,
                 code_problem: Callable[[], str | None] | None = None) -> None:
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
        self.console_done = console_done or (lambda: None)  # a challenge ended: a window may close
        self.code_problem = code_problem or (lambda: None)  # why no code can be shown here; an outcome line needs none
        self.background = background  # started by a Lead session: it ends with the sessions it serves
        self._retiring = False  # stop once the reply in hand is sent
        self._retired = threading.Event()
        self.timeout = timeout
        self.uid = os.getuid() if sys.platform != "win32" else None
        self.pid = os.getpid()
        self.started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._started = procs.started_at(self.pid)
        self._start_id = procs.start_id(self.pid)
        self._locator = locator_path(engine.aew_root)
        self._closed = threading.Event()
        self._authorizing = threading.Lock()  # one challenge at a time
        self._awaiting: str | None = None  # the G3 approval the current challenge waits on, for the busy message
        self._engine_lock = threading.Lock()
        self._listener: Any = None
        self._lock: FileLock | None = None
        self._thread: threading.Thread | None = None
        self.watcher: notify.Watcher | None = None
        self.address = ""
        self.family = ""
        self._private_dir: str | None = None
        self.refused = 0

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Claim the project's endpoint lock, then serve. ``aew operator serve`` hardens its process first
        (:func:`harden`)."""
        self._claim()
        try:
            self.address, self.family, self._private_dir = private_address()
            self._listener = Listener(self.address, family=self.family)  # no key: the peer check authorizes
            self._write_locator()  # under the lock: whatever locator was there is stale
            self.watcher = notify.Watcher(self.engine.repo_root, self.engine.aew_root)
        except BaseException:
            self._release()
            raise
        self._thread = threading.Thread(target=self._serve, name="aew-operator-endpoint", daemon=True)
        self._thread.start()
        self.watcher.start()

    def serve_forever(self) -> None:
        try:
            while not self._closed.wait(0.5):
                if self._retired.is_set() or (self.background and self._no_session_left()):
                    return
        finally:
            self.close()

    def _no_session_left(self) -> bool:
        """A challenge in hand finishes first."""
        return not self._authorizing.locked() and no_session_left(self.engine.aew_root)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self.watcher is not None:
            self.watcher.close(WAKE_TIMEOUT_S)  # bounded: a delivery in flight is killed, never waited for
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
        self._release()

    def _release(self) -> None:
        """Remove this endpoint's locator and release the lock; only the lock's holder ever wrote the locator."""
        if self._lock is None:
            return
        self._locator.unlink(missing_ok=True)
        self._lock.__exit__(None, None, None)
        self._lock = None

    def _wake(self) -> None:
        try:
            Client(self.address, family=self.family).close()
        except Exception:  # noqa: S110, BLE001 (best effort)
            pass

    def _claim(self) -> None:
        """Hold the project's endpoint lock for this endpoint's lifetime (review of #134, finding 1). Holding it is
        being the project's endpoint: a second starter is refused while it is held, and once it is free (the OS
        releases it when its holder dies), any locator left behind is proven stale and is simply overwritten. Claiming
        and replacing are therefore serialized, and an unreadable locator is never mistaken for a claim."""
        self._locator.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(self._locator.with_name(LOCK_NAME), timeout=STOPPING_S if self.background else CLAIM_TIMEOUT_S)
        try:
            lock.__enter__()
        except LockTimeout:
            other = read_locator(self._locator) or {}
            raise errors.PermissionDenied(
                "another operator endpoint for this project is live or starting"
                + (f" (pid {other.get('pid')}, started {other.get('started_at')})" if other.get("pid") else "")
                + "; one endpoint per project: use it, or stop it first", pid=other.get("pid")) from None
        self._lock = lock

    def _locator_data(self) -> dict[str, Any]:
        return {"schema": LOCATOR_SCHEMA, "address": self.address, "family": self.family, "pid": self.pid,
                "process_started": self._started, "start_id": self._start_id, "started_at": self.started_at,
                "uid": self.uid, "guarantee": GUARANTEE}

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
                elif op == "capability_change":
                    reply = {"ok": True, "result": self._capability_change(conn, args)}
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
            if self._retiring:
                self._retired.set()

    def ping(self) -> dict[str, Any]:
        """Liveness and the label; no challenge, and nothing secret."""
        return {"alive": True, "pid": self.pid, "started_at": self.started_at, "uid": self.uid,
                "guarantee": GUARANTEE, "dumpable": _dumpable(), "operations": list(OPERATIONS),
                "residuals": list(RESIDUALS)}

    def _require_code_console(self, why_not_g3: str | None = None) -> None:
        """Before a code exists: an endpoint that cannot show one says what to run, and gives its lock up so that can
        start. No code is made, so none can reach a log."""
        why = self.code_problem()
        if why:
            self._retiring = True
            message = NO_CONSOLE.format(why=why)
            raise errors.OperatorAuthorizationRequired(f"{why_not_g3}. {message}" if why_not_g3 else message,
                                                       detail=why)

    def _busy(self) -> errors.PermissionDenied:
        """The refusal while another challenge is open, naming what ends it."""
        approval = self._awaiting
        if approval:
            return errors.PermissionDenied(f"another request is waiting on {approval} in G3's confirmer (AEW "
                                           "approvals): approve or decline it there, or stop the terminal that asked, "
                                           "and try again", approval_ref=approval)
        return errors.PermissionDenied("another request is waiting for the operator at this endpoint; try again "
                                       "after it is answered or times out")

    def _mode_raise(self, conn: Any, args: dict[str, Any]) -> dict[str, Any]:
        mode = str(args.get("mode") or "")
        requester = str(args.get("requester") or "unknown")[:400]
        if not self._authorizing.acquire(blocking=False):
            raise self._busy()
        try:
            with self._engine_lock:
                bound = self.engine.steering_raise_preview(mode)  # refused here before the operator is asked
                policy, _ = self.engine.execution_policy()
            by_g3, why_not = g3_adapter.choose("mode_raise", policy)  # the one choice of this challenge's path
            if by_g3:
                return self._mode_raise_by_g3(conn, mode, bound)
            self._require_code_console(why_not)
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
                                                               "bound": bound, "g3": why_not}}).encode("utf-8"))
            principal = self._await_code(conn, code, "aew lead mode raise")
            with self._engine_lock:
                out = self.engine.steering_raise(principal, mode=mode, generation=bound["generation"],
                                                 legality_digest=bound["legality_digest"])
            self.console(f"\n(steering mode raised to {mode} for Lead generation {bound['generation']}: "
                         f"{out['record']})\n")
            return out
        finally:
            self.console_done()
            self._authorizing.release()

    def _mode_raise_by_g3(self, conn: Any, mode: str, bound: dict[str, Any]) -> dict[str, Any]:
        """The raise on the G3 path, which never moves to the code: the operator approves in the confirmer, and the
        approval is consumed once. Whatever has moved since they approved refuses before consume, and the approval is
        not spent; ``raise_mode`` then gets the values the consent bound. A requester that has gone ends the wait, and
        nothing consumes its approval, so a raise never lands with no terminal to tell."""
        approval = ""

        def on_pending(pending: dict[str, Any]) -> None:
            nonlocal approval
            approval = self._awaiting = pending["approval_ref"]
            shown = {"challenge": "g3", "approval_ref": approval, "expires_at": pending["expires_at"], "bound": bound}
            try:
                conn.send_bytes(json.dumps({"ok": True, "result": shown}).encode("utf-8"))
            except OSError:
                raise g3_adapter.requester_gone(approval) from None

        def wait(seconds: float) -> None:
            """The time between looks at the service, on the requester's connection. It sends nothing on this path, so
            anything readable there is its end."""
            try:
                ended = conn.poll(seconds)
            except (EOFError, OSError):
                ended = True
            if ended:
                raise g3_adapter.requester_gone(approval)

        try:
            approved, record = g3_adapter.approve(g3_adapter.raise_set(bound), on_pending, wait)
            wait(0)
            with self._engine_lock:
                changed = g3_adapter.moved(approved, self.engine.steering_raise_preview(mode))
                policy, _ = self.engine.execution_policy()
            if changed:
                raise g3_adapter.refused(f"{changed} moved after the approval, which was not spent")
            origin = g3_adapter.consume_member(approved, record, policy)
            values = g3_adapter.bound_values(approved)
            with self._engine_lock:
                out = self.engine.steering_raise(self._principal(origin), mode=values.mode,
                                                 generation=values.generation, legality_digest=values.legality_digest)
        except errors.AEWError as exc:
            self.console(f"\n(the `aew lead mode raise` request ended: {exc.message})\n")
            raise
        finally:
            self._awaiting = None
        self.console(f"\n(steering mode raised to {mode} for Lead generation {values.generation} on G3 approval "
                     f"{approval}: {out['record']})\n")
        return out

    def _principal(self, origin: dict[str, Any] | None = None) -> OperatorPrincipal:
        return OperatorPrincipal(uid=self.uid, method="peer_credentials" if self.family == "AF_UNIX" else "named_pipe",
                                 endpoint_pid=self.pid, endpoint_started_at=self.started_at, origin=origin)

    def _await_code(self, conn: Any, code: str, command: str) -> OperatorPrincipal:
        """The code typed back at the requesting terminal, within the timeout: the operator principal of this one
        request, or refused."""
        if not conn.poll(self.timeout):
            self.console(f"\n(the `{command}` request timed out; the code is void)\n")
            raise errors.PermissionDenied("operator authorization timed out")
        op, answer = _request(conn.recv_bytes(MAX_MESSAGE))
        given = str(answer.get("code", "")).strip().upper() if op == "answer" else ""
        if not hmac.compare_digest(given, code):
            self.console(f"\n(the `{command}` request was refused: wrong code)\n")
            raise errors.PermissionDenied("operator refused or mistyped the confirmation code")
        return self._principal()

    def _capability_change(self, conn: Any, args: dict[str, Any]) -> dict[str, Any]:
        """One change to this host's capability register (CAP-1; the designer's ruling 1): previewed here, shown on
        this console, and applied here, exactly as shown, once the operator typed its code back at the requesting
        terminal. Its import's archives are the bytes this process read for the preview, never read again."""
        from aew.capability import ops

        kind = str(args.get("change") or "")
        change_args: dict[str, Any] = args["args"] if isinstance(args.get("args"), dict) else {}
        requester = str(args.get("requester") or "unknown")[:400]
        command = f"aew capability {kind.replace('_', '-')}"
        if not self._authorizing.acquire(blocking=False):
            raise self._busy()
        try:
            change = ops.preview(kind, change_args)  # refused here before the operator is asked
            self._require_code_console()
            code = operator.new_code()
            self.console(operator.challenge(
                code,
                "CHANGE this host's capability register, which every project and every contained run on this host "
                "reads:\n" + "\n".join(change.lines) + f"\n  change digest       : {change.digest}\n"
                f"  guarantee           : {GUARANTEE} (not production authority until F18.6)",
                requested_by=f"{requester} (as reported by the requester; the code below is the authorization)",
                destination="the capability register (no credential is issued)",
                instruction=f"Type the confirmation code {code} into the terminal that ran `{command}` (not here); "
                            "anything else there refuses."))
            conn.send_bytes(json.dumps({"ok": True, "result": {"challenge": "shown", "timeout_s": self.timeout,
                                                               "change": change.lines, "digest": change.digest}},
                                       default=str).encode("utf-8"))
            principal = self._await_code(conn, code, command)
            out = ops.apply(principal, change)
            self.console(f"\n(capability register changed by `{command}`, recorded at {out['recorded']})\n")
            return out
        finally:
            self.console_done()
            self._authorizing.release()


