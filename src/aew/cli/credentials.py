"""Where a credential an ``aew`` command issues goes (ADR-0009 custody).

A command that issues a credential (``lead acquire``, ``lead takeover``, ``lead handoff offer`` with its offer
secret, ``lead handoff accept``, a dispatch without ``--launch`` with its invocation credential, and ``dashboard
serve`` and ``dashboard open`` with their one-time session URL) writes it only to the controlling terminal:
``/dev/tty``, or the console on Windows. Never to standard output, which a harness, a pipe or a transcript may capture.
The JSON result says where the credential went instead.

A script that needs the credential on standard output passes ``aew --print-credential ...``. A Lead session refuses
that flag. With neither a terminal nor the flag the command is refused before it runs, so no credential is ever issued
that nobody received.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from aew.errors import UsageError

KEYS = ("token", "offer", "invocation_token", "session_url")
ISSUING = (frozenset({"lead", "acquire"}), frozenset({"lead", "takeover"}), frozenset({"lead", "handoff", "offer"}),
           frozenset({"lead", "handoff", "accept"}),
           # The dashboard's one-time session URL is a credential's delivery (ADR-0005, 2026-10-05; F20.3).
           frozenset({"dashboard", "serve"}), frozenset({"dashboard", "open"}))
WRITTEN = "(written to your terminal)"


def register(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--print-credential", action="store_true",
                        help="put a credential this command issues on standard output (for a script that keeps it "
                             "safe); by default it is written only to your terminal. Refused in a Lead session")


def issues_credential(args: argparse.Namespace) -> bool:
    from aew.harness.lead_broker import DISPATCHES, command_path

    path = command_path(args)
    if any(p <= path for p in ISSUING):
        return True
    return any(p <= path for p in DISPATCHES) and not getattr(args, "launch", False)


def before(args: argparse.Namespace) -> None:
    """Refuse, before anything is issued, a command whose credential could reach no one; and tell an operator
    authorization prompt where the credential will go."""
    from aew import operator

    if not issues_credential(args):
        return
    if getattr(args, "print_credential", False):
        operator.credential_destination.set(
            "the requesting process's standard output (--print-credential): refuse unless you ran it yourself")
        return
    operator.credential_destination.set(operator.TERMINAL_ONLY)
    if _open_terminal() is None:
        raise UsageError(
            "this command issues a credential, and AEW writes credentials only to your terminal; this process has "
            "none (a harness tool call, a pipe or a scheduled job). Run it yourself at a terminal, or, from a script "
            "that keeps the credential safe, run `aew --print-credential ...` to get it on standard output")


def deliver(result: Any, args: argparse.Namespace) -> Any:
    """Write any credential in ``result`` to the terminal and return the result without it."""
    if getattr(args, "print_credential", False) or not isinstance(result, dict):
        return result
    found = {k: result[k] for k in KEYS if isinstance(result.get(k), str) and result[k]}
    if not found:
        return result
    out = _open_terminal()
    if out is None:  # the terminal went away between the check and now
        raise UsageError("a credential was issued but your terminal is gone, so it was not written anywhere; "
                         "recover with `aew lead takeover` at a terminal (or cancel the invocation or handoff)")
    with out:
        out.write("\n==== AEW CREDENTIAL (keep it out of any agent's reach) ====\n")
        for key, value in found.items():
            out.write(f"{key}: {value}\n")
        out.write("\n")
        out.flush()
    return {**result, **dict.fromkeys(found, WRITTEN)}


def write_to_terminal(label: str, value: str) -> None:
    """Write one credential to the controlling terminal, as ``deliver`` does for a command's result. The long-running
    ``aew dashboard serve`` uses it for each session URL it issues (F20.3). Raises when this process has no terminal."""
    out = _open_terminal()
    if out is None:
        raise UsageError(f"a {label} was issued but this process has no terminal to write it to")
    with out:
        out.write("\n==== AEW CREDENTIAL (keep it out of any agent's reach) ====\n")
        out.write(f"{label}: {value}\n\n")
        out.flush()


def _open_terminal() -> Any:
    """A text stream to the controlling terminal or console, or ``None`` when this process has none."""
    if sys.platform == "win32":  # pragma: windows-only
        import ctypes

        if not ctypes.windll.kernel32.GetConsoleWindow():
            return None
        try:
            return open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115 (the caller closes it)
        except OSError:
            return None
    try:  # pragma: posix-only
        fd = os.open("/dev/tty", os.O_WRONLY | os.O_NOCTTY)
    except OSError:
        return None
    return os.fdopen(fd, "w", encoding="utf-8")
