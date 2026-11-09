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
from typing import NamedTuple

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
              instruction: str | None = None, purpose: str | None = None) -> str:
    """The operator authorization prompt: ``text`` says what is being authorized, ``code`` is what the operator types
    back. The dashboard server writes the same prompt to its own console when ``aew dashboard open`` asks for a session
    (F20.3), naming the requester that process reported and where the code is to be typed. ``purpose`` is for a prompt
    that releases no credential: it names what changes, in place of the credential's destination."""
    from aew.harness.procs import process_chain

    who = requested_by if requested_by is not None else (" <- ".join(process_chain()) or "unknown")
    where = destination if destination is not None else credential_destination.get()
    typed = instruction or f"Type the confirmation code {code} and press Enter to authorize; anything else refuses."
    target = f"  changes        : {purpose}\n" if purpose is not None else f"  credential to  : {where}\n"
    return (
        "\n==== AEW OPERATOR AUTHORIZATION REQUIRED ====\n"
        f"{text}\n"
        f"  requested by   : {who}\n"
        f"{target}"
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


# What a prompt that ends unanswered says: (timed out, terminal closed). The authorization prompt's own words.
AUTHORIZATION_ENDS = ("operator authorization timed out", "terminal closed before authorization")


def ask(prompt: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> str:
    """Write ``prompt`` to the controlling terminal and return the line the operator types, or raise
    ``OperatorAuthorizationRequired`` when this process has no terminal. Never reads argv, environment or stdin."""
    return _ask_windows(prompt, timeout) if IS_WINDOWS else _ask_posix(prompt, timeout)


def ask_hidden(prompt: str, *, what: str, timeout: float = DEFAULT_TIMEOUT_S) -> str:
    """:func:`ask` for a secret: what the operator types is never echoed (CS-4 addendum 12, the Lead credential's
    prompt). The Windows console read never echoes; on POSIX the terminal's echo is off while it reads. ``what`` names
    the secret in the refusal when the prompt times out or the terminal closes (review of #316, m6)."""
    ends = (f"the prompt for {what} timed out", f"terminal closed before {what} was entered")
    return _ask_windows(prompt, timeout, ends=ends) if IS_WINDOWS else _ask_posix(prompt, timeout, hidden=True,
                                                                                  ends=ends)


class Answer(NamedTuple):
    """What the operator answered, exactly one of: ``authorization``, the code typed back; ``declined``, Enter alone."""

    authorization: dict[str, str] | None
    declined: bool


def answer(text: str, *, timeout: float = DEFAULT_TIMEOUT_S, instruction: str | None = None,
           purpose: str | None = None) -> Answer:
    """The approval where Enter alone means no, rather than a refusal (the switch offer). ``instruction`` may name the
    code as ``{code}``. Raises ``PermissionDenied`` on anything else typed, a timeout or a closed terminal, and
    ``OperatorAuthorizationRequired`` with no terminal: none of those is an answer. The one approval site, so G3's
    later in-process adapter finds it here. Input already queued isn't an answer to a prompt nobody has seen: Enter is
    a remembered no here, so it is discarded first (review of the switch offer, point 6)."""
    discard_typed_ahead()
    return _answered(text, timeout=timeout, instruction=instruction, purpose=purpose)


def _answered(text: str, *, timeout: float, instruction: str | None = None, purpose: str | None = None) -> Answer:
    code = _code()
    typed = instruction.replace("{code}", code) if instruction is not None else None
    reply = ask(challenge(code, text, instruction=typed, purpose=purpose) + "> ", timeout=timeout).strip()
    if not reply:
        return Answer(None, True)
    if reply.upper() != code:
        raise PermissionDenied("operator refused or mistyped the confirmation code")
    return Answer({"authorized_by": "operator-tty", "challenge_code": code}, False)


def authorize(text: str, *, timeout: float = DEFAULT_TIMEOUT_S) -> dict[str, str]:
    """Block until the operator confirms at the controlling terminal, or raise. An empty answer refuses here."""
    got = _answered(text, timeout=timeout)
    if got.authorization is None:
        raise PermissionDenied("operator refused or mistyped the confirmation code")
    return got.authorization


def discard_typed_ahead() -> None:
    """Drop what is queued at the controlling terminal. With no terminal there is nothing to drop."""
    if IS_WINDOWS:
        _discard_windows()
    else:
        _discard_posix()


def _discard_posix() -> None:  # pragma: posix-only
    import termios

    assert sys.platform != "win32"  # narrows the os module for the type checker

    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError:
        return
    try:
        termios.tcflush(fd, termios.TCIFLUSH)
    except termios.error:
        pass
    finally:
        os.close(fd)


def _discard_windows() -> None:  # pragma: windows-only
    import msvcrt

    assert sys.platform == "win32"  # narrows msvcrt for the type checker

    while msvcrt.kbhit():
        msvcrt.getwch()


def _no_terminal(detail: str) -> OperatorAuthorizationRequired:
    return OperatorAuthorizationRequired(
        "operator authorization requires an interactive controlling terminal; run this command "
        "yourself in a terminal (flags, environment variables and stdin are never accepted)",
        detail=detail,
    )


def _ask_posix(prompt: str, timeout: float, *, hidden: bool = False,
               ends: tuple[str, str] = AUTHORIZATION_ENDS) -> str:  # pragma: posix-only
    import select
    import termios

    assert sys.platform != "win32"  # narrows the os module for the type checker

    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
    except OSError as exc:
        raise _no_terminal(f"/dev/tty unavailable: {exc.strerror}") from None
    saved = None
    try:
        if hidden:  # echo off before the prompt shows, so nothing typed after it is ever echoed
            saved = termios.tcgetattr(fd)
            quiet = list(saved)
            quiet[3] &= ~termios.ECHO
            termios.tcsetattr(fd, termios.TCSAFLUSH, quiet)
        os.write(fd, prompt.encode("utf-8"))
        buf = b""
        deadline = time.monotonic() + timeout
        while b"\n" not in buf and b"\r" not in buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PermissionDenied(ends[0])
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                continue
            chunk = os.read(fd, 256)
            if not chunk:
                raise PermissionDenied(ends[1])
            buf += chunk
        os.write(fd, b"\n")
        return buf.decode("utf-8", "replace").splitlines()[0] if buf.strip() else ""
    finally:
        if saved is not None:
            termios.tcsetattr(fd, termios.TCSAFLUSH, saved)
        os.close(fd)


def _ask_windows(prompt: str, timeout: float, *,
                 ends: tuple[str, str] = AUTHORIZATION_ENDS) -> str:  # pragma: windows-only
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
                raise PermissionDenied(ends[0])
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
