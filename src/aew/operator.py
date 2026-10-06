"""Out-of-band operator authorization (ambiguity report A2, decision D-op-3).

Authorization is obtained by the engine itself from the **controlling terminal**
(``/dev/tty`` on POSIX, the console on Windows). It is never read from argv,
environment variables, stdin or an API argument, so an agent cannot
self-authorize by supplying a flag or boolean. The operator must type back a
one-time challenge code displayed on that terminal.

With no controlling terminal (the normal case for a harness tool call) the
request is refused. Residual risk, accepted for M1 by review: a same-UID agent
that deliberately fabricates a pseudo-terminal is outside the M1 threat model;
future designs (operator-issued one-time token held outside the agent's reach,
approval artifact, or formal lease expiry) close that gap.
"""

from __future__ import annotations

import os
import secrets
import sys
import time
from contextvars import ContextVar

from aew.errors import OperatorAuthorizationRequired, PermissionDenied
from aew.util import IS_WINDOWS

DEFAULT_TIMEOUT_S = 300.0

# Where a credential this authorization releases will go; the CLI sets it from `--print-credential` (ADR-0009).
TERMINAL_ONLY = "this terminal only"
credential_destination: ContextVar[str] = ContextVar("aew_credential_destination", default=TERMINAL_ONLY)


def _code() -> str:
    return secrets.token_hex(3).upper()


def new_code() -> str:
    """A fresh one-time confirmation code (six hex digits), as every operator challenge uses."""
    return _code()


def challenge(code: str, text: str, *, requested_by: str | None = None, destination: str | None = None,
              instruction: str | None = None) -> str:
    """The operator authorization prompt: ``text`` says what is being authorized, ``code`` is what the operator types
    back. The dashboard server writes the same prompt to its own console when ``aew dashboard open`` asks for a session
    (F20.3), naming the requester that process reported and where the code is to be typed."""
    from aew.harness.procs import process_chain

    who = requested_by if requested_by is not None else (" <- ".join(process_chain()) or "unknown")
    where = destination if destination is not None else credential_destination.get()
    typed = instruction or f"Type the confirmation code {code} and press Enter to authorize; anything else refuses."
    return (
        "\n==== AEW OPERATOR AUTHORIZATION REQUIRED ====\n"
        f"{text}\n"
        f"  requested by   : {who}\n"
        f"  credential to  : {where}\n"
        "If you did not start this command yourself (for example, it came from an agent's shell), refuse.\n"
        f"{typed}\n"
        f"{RELAY_WARNING}\n"
    )


# The code is the authorization; a model that can run `aew dashboard open` from a shell with a terminal could ask the
# human for it in chat (lead developer's review of F20.3). The prompt says so, every time.
RELAY_WARNING = "Type it only into a terminal you opened yourself. Never give it to an agent or paste it into a chat."


def has_terminal() -> bool:
    """Whether this process could read an answer from its controlling terminal (the same check ``ask`` makes), so a
    command can refuse before it causes a prompt somewhere else (``aew dashboard open`` asks the serving console for
    a code only when it can type it back)."""
    if sys.platform == "win32":  # pragma: windows-only
        import ctypes

        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    try:  # pragma: posix-only
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return False
    os.close(fd)
    return True


def ask(prompt: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> str:
    """Write ``prompt`` to the controlling terminal and return the line the operator types, or raise
    ``OperatorAuthorizationRequired`` when this process has no terminal. Never reads argv, environment or stdin."""
    return _ask_windows(prompt, timeout) if IS_WINDOWS else _ask_posix(prompt, timeout)


def authorize(text: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, str]:
    """Block until the operator confirms at the controlling terminal, or raise."""
    code = _code()
    answer = ask(challenge(code, text) + "> ", timeout=timeout)
    if answer.strip().upper() != code:
        raise PermissionDenied("operator refused or mistyped the confirmation code")
    return {"authorized_by": "operator-tty", "challenge_code": code}


def _no_terminal(detail: str) -> OperatorAuthorizationRequired:
    return OperatorAuthorizationRequired(
        "operator authorization requires an interactive controlling terminal; run this command "
        "yourself in a terminal (flags, environment variables and stdin are never accepted)",
        detail=detail,
    )


def _ask_posix(prompt: str, timeout: float) -> str:  # pragma: posix-only
    import select

    assert sys.platform != "win32"  # narrows the os module for the type checker

    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError as exc:
        raise _no_terminal(f"/dev/tty unavailable: {exc.strerror}") from None
    try:
        os.write(fd, prompt.encode("utf-8"))
        buf = b""
        deadline = time.monotonic() + timeout
        while b"\n" not in buf and b"\r" not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PermissionDenied("operator authorization timed out")
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(fd, 256)
            if not chunk:
                raise PermissionDenied("terminal closed before authorization")
            buf += chunk
        os.write(fd, b"\n")
        return buf.decode("utf-8", "replace").splitlines()[0] if buf.strip() else ""
    finally:
        os.close(fd)


def _ask_windows(prompt: str, timeout: float) -> str:  # pragma: windows-only
    import ctypes
    import msvcrt

    assert sys.platform == "win32"  # narrows ctypes and msvcrt for the type checker

    if not ctypes.windll.kernel32.GetConsoleWindow():
        raise _no_terminal("no console attached to this process")
    try:
        out = open("CONOUT$", "w", encoding="utf-8")
    except OSError as exc:
        raise _no_terminal(f"CONOUT$ unavailable: {exc}") from None
    with out:
        out.write(prompt)
        out.flush()
        chars: list[str] = []
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() > deadline:
                raise PermissionDenied("operator authorization timed out")
            if not msvcrt.kbhit():
                time.sleep(0.02)
                continue
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                out.write("\n")
                return "".join(chars)
            if ch == "\x03":
                raise PermissionDenied("operator cancelled")
            if ch == "\b":
                if chars:
                    chars.pop()
                continue
            chars.append(ch)


def require_operator_attribution(claimed: bool, authorization: dict[str, str] | None, what: str) -> None:
    """A record that says the operator decided needs the operator's own confirmation, typed back at their terminal
    (:func:`authorize`): a flag says who decided, it never proves it (operator, 2026-10-06: "if my name is attached to
    it I should have actually approved"). The guarantee is the CLI's prompt, which asks before it calls the engine,
    and the Lead broker's refusal of the flag in a Lead session. This check only makes the engine refuse a caller that
    did not ask: an in-process Python caller could supply the record itself (PR #103 re-review, N2)."""
    if claimed and (authorization or {}).get("authorized_by") != "operator-tty":
        raise OperatorAuthorizationRequired(
            f"{what} recorded as the operator's needs the operator's confirmation at their own terminal: the "
            "operator runs the command there and types back the code it shows (a flag is not a sign-off)")
