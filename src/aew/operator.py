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
import time

from aew.errors import OperatorAuthorizationRequired, PermissionDenied
from aew.util import IS_WINDOWS

DEFAULT_TIMEOUT_S = 300.0


def _code() -> str:
    return secrets.token_hex(3).upper()


def authorize(challenge: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, str]:
    """Block until the operator confirms at the controlling terminal, or raise."""
    code = _code()
    prompt = (
        "\n==== AEW OPERATOR AUTHORIZATION REQUIRED ====\n"
        f"{challenge}\n"
        f"Type the confirmation code {code} and press Enter to authorize; anything else refuses.\n"
        "> "
    )
    answer = _ask_windows(prompt, timeout) if IS_WINDOWS else _ask_posix(prompt, timeout)
    if answer.strip().upper() != code:
        raise PermissionDenied("operator refused or mistyped the confirmation code")
    return {"authorized_by": "operator-tty", "challenge_code": code}


def _no_terminal(detail: str) -> OperatorAuthorizationRequired:
    return OperatorAuthorizationRequired(
        "operator authorization requires an interactive controlling terminal; run this command "
        "yourself in a terminal (flags, environment variables and stdin are never accepted)",
        detail=detail,
    )


def _ask_posix(prompt: str, timeout: float) -> str:
    import select

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


def _ask_windows(prompt: str, timeout: float) -> str:
    import ctypes
    import msvcrt

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
