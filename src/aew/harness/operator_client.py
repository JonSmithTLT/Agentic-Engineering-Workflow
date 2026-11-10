"""The operator endpoint's client side (M4-E plan v3 §2.1): locate it, ping it, and ask it for a raise.

It holds no authority and constructs nothing the engine accepts as the operator's: only the endpoint
(``aew.harness.operator_endpoint``, imported by ``aew operator serve`` alone) builds an ``OperatorPrincipal``. Every
client command only sends a request; the operator's answer is the code shown on the endpoint's console, typed here, or
for a raise where G3 counts, their approval in G3's confirmer.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from multiprocessing.connection import Client
from pathlib import Path
from typing import Any

from aew import errors, operator
from aew.engine.lock import FileLock
from aew.errors import LockTimeout
from aew.harness import procs
from aew.harness.bridge import rebuild_error
from aew.util import atomic_write

LOCATOR_REL = "local/operator/endpoint.json"
LOCK_NAME = "endpoint.lock"  # beside the locator: held by the live endpoint for its whole life
SESSIONS_REL = "local/operator/sessions"  # one file per Lead session a background endpoint serves
SESSIONS_LOCK = "sessions.lock"  # beside the locator: a session naming itself, or an endpoint deciding to stop
LOCATOR_SCHEMA = "aew/operator-endpoint/v1"
MAX_MESSAGE = 16 * 1024
CHALLENGE_TIMEOUT_S = 300.0
WAKE_TIMEOUT_S = 5.0
SESSIONS_LOCK_TIMEOUT_S = 5.0  # held for a few file operations; a session that misses it says what to run
OPERATIONS = ("ping", "mode_raise", "capability_change")  # capability_change: CAP-1, the designer's ruling 1
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
    start, started = locator.get("start_id"), locator.get("process_started")
    if not isinstance(pid, int) or not procs.pid_alive(pid):
        return False
    if start is not None or isinstance(started, int | float):
        return procs.same_process(pid, procs.recorded(start, started))
    return True  # alive and unprovable: never replaced


def same_process(record: dict[str, Any]) -> bool:
    """Whether the process a record names by ``pid`` and ``start_id`` (or, in a record from before start ids,
    ``process_started``) is alive and is that process: the locator's own check, which the endpoint's watcher also
    applies to the broker's liveness record (M4-E E7a)."""
    return _same_process(record)


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
            pid = int((proc / "stat").read_bytes().decode("latin-1").rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return None


def _is_lead_session(argv: list[str]) -> bool:
    """``aew lead session ...``, ``aew opencode ...`` (and ``python -m aew`` forms). ``-C`` is the one global option
    that takes a value, so its value is not a word of the command."""
    for i, word in enumerate(argv):
        if os.path.basename(word) in ("aew", "aew.exe") or (word == "aew" and i and argv[i - 1] == "-m"):
            rest, words = [], iter(argv[i + 1:])
            for w in words:
                if w == "-C":
                    next(words, None)
                elif not w.startswith("-"):
                    rest.append(w)
            return rest[:2] == ["lead", "session"] or rest[:1] == ["opencode"]
    return False


def sessions_lock(aew_root: Path) -> FileLock:
    """Taken to name a session and to decide to stop, so a session either is seen by the endpoint's last look or finds
    that the endpoint has already taken its locator away, and starts another."""
    path = locator_path(aew_root).with_name(SESSIONS_LOCK)
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(path, timeout=SESSIONS_LOCK_TIMEOUT_S)


def name_session(aew_root: Path) -> Path | None:
    """Name this process as a session a background endpoint serves, before the endpoint starts: from here on, a live
    locator is an endpoint that will see this file. ``None`` if it cannot be named."""
    pid = os.getpid()
    path = Path(aew_root) / SESSIONS_REL / f"{pid}.json"
    try:
        with sessions_lock(aew_root):
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, json.dumps({"pid": pid, "start_id": procs.start_id(pid),
                                           "process_started": procs.started_at(pid)}) + "\n")
    except (LockTimeout, OSError):
        return None
    return path


def no_session_live(aew_root: Path) -> bool:
    """A look that decides nothing: whether a background endpoint has anything to do before its deciding look."""
    try:
        with sessions_lock(aew_root):
            return not session_holders_live(aew_root)
    except (LockTimeout, OSError):
        return False


def withdraw_locator(aew_root: Path) -> None:
    """An endpoint about to retire stops being found, as :func:`no_session_left` does, so a session starts another
    rather than reusing one that is going away. If the lock is busy, its close removes the locator anyway."""
    try:
        with sessions_lock(aew_root):
            locator_path(aew_root).unlink(missing_ok=True)
    except (LockTimeout, OSError):
        pass


def no_session_left(aew_root: Path) -> bool:
    """A background endpoint's look that decides to stop. The locator goes with the decision, under the lock: a session
    naming itself is either seen here or finds no endpoint and starts one."""
    try:
        with sessions_lock(aew_root):
            if session_holders_live(aew_root):
                return False
            locator_path(aew_root).unlink(missing_ok=True)
            return True
    except (LockTimeout, OSError):
        return False  # the next look decides


def session_holders_live(aew_root: Path) -> bool:
    """Whether any Lead session a background endpoint serves is alive and is that process. A file whose process has
    gone is removed: a session that died never keeps the endpoint up."""
    live = False
    try:
        files = list((Path(aew_root) / SESSIONS_REL).glob("*.json"))
    except OSError:
        return False
    for path in files:
        data = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if isinstance(data, dict) and _same_process(data):
            live = True
        else:
            path.unlink(missing_ok=True)
    return live


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


# Where the code is shown: `aew operator serve`'s terminal, or on Windows the window of `aew opencode`'s endpoint
SHOWN_THERE = ("The operator endpoint's console (the terminal running `aew operator serve`, or on Windows the window "
               "`aew opencode`'s endpoint opens) now shows a one-time confirmation code. Type it here and press Enter; "
               "anything else refuses.")


def raise_prompt(bound: dict[str, Any], requester: str) -> str:
    return operator.challenge(
        "", f"RAISE the Lead's steering mode to {bound['mode']} for Lead generation {bound['generation']}",
        requested_by=requester, destination="a steering mode record (no credential is issued)",
        instruction=SHOWN_THERE) + "> "


def request_raise(aew_root: Path, mode: str, *, ask: Callable[[str], str] | None = None,
                  requester: str | None = None) -> dict[str, Any]:
    """``aew lead mode raise``: ask the endpoint, read the code the operator types at **this** terminal, and send it; or
    where G3 counts, wait here while they approve in the confirmer. Leaving ends the request, either way."""
    who = requester if requester is not None else (" <- ".join(procs.process_chain()) or "unknown")
    read = ask if ask is not None else (lambda prompt: operator.ask(prompt))
    conn = _connect(aew_root)
    try:
        _send(conn, "mode_raise", {"mode": mode, "requester": who})
        shown = _reply(conn)
        if shown.get("challenge") == "g3":  # the operator's PIN goes in G3's confirmer: there is no code to type here
            sys.stderr.write(f"aew lead mode raise: approve or decline {shown['approval_ref']} in the confirmer (AEW "
                             f"approvals), until {shown['expires_at']}\n")
            sys.stderr.flush()
            return _reply(conn)
        if shown.get("g3"):
            sys.stderr.write(f"aew lead mode raise: {shown['g3']}\n")
        return _answer(conn, lambda: read(raise_prompt(shown["bound"], who)))
    finally:
        conn.close()


def _answer(conn: Any, read: Callable[[], str]) -> dict[str, Any]:
    """Read the code the operator types at this terminal (``read``) and send it; the endpoint's reply is the result."""
    try:
        answer = read()
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


def capability_prompt(shown: dict[str, Any], requester: str) -> str:
    return operator.challenge(
        "", "CHANGE this host's capability register:\n" + "\n".join(shown["change"]), requested_by=requester,
        destination="the capability register (no credential is issued)",
        instruction=SHOWN_THERE) + "> "


def request_capability_change(aew_root: Path, change: str, args: dict[str, Any], *,
                              ask: Callable[[str], str] | None = None, requester: str | None = None) -> dict[str, Any]:
    """``aew capability import``, ``add``, ``remove`` and ``host-copies`` (CAP-1; the designer's ruling 1): ask the
    endpoint, which shows the exact change and its code on its console, read the code typed at **this** terminal, and
    send it. The endpoint applies the change it showed; this side holds no authority."""
    who = requester if requester is not None else (" <- ".join(procs.process_chain()) or "unknown")
    read = ask if ask is not None else (lambda prompt: operator.ask(prompt))
    conn = _connect(aew_root)
    try:
        _send(conn, "capability_change", {"change": change, "args": args, "requester": who})
        shown = _reply(conn)
        return _answer(conn, lambda: read(capability_prompt(shown, who)))
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
