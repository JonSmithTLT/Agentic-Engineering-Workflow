"""``aew`` command-line entry point.

The CLI is a thin adapter: it parses arguments, calls the engine, and renders
results. It holds no workflow logic, so a future MCP adapter can call the same
engine without becoming a second state authority (WC §15.6, invariant 21).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew import SPEC_SET, __version__, profile
from aew.cli import credentials, fields
from aew.errors import AEWError

Handler = Callable[[argparse.Namespace], Any]


def emit(result: Any, *, as_json: bool) -> None:
    if as_json or not isinstance(result, str):
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=False, default=str) + "\n")
    else:
        sys.stdout.write(result if result.endswith("\n") else result + "\n")


def build_parser(recall_search: bool = False, coordination_reads: bool = False) -> argparse.ArgumentParser:
    """The ``aew`` parser. ``recall_search`` registers `history search` (register F21, Arm B), which exists only while
    the project's adopted execution policy switches it on (``recall_search_for``); ``coordination_reads`` registers
    `aew message` (F9-A), which exists only while messaging is on or a thread exists (``coordination_reads_for``).
    Every walk of the command set that classifies commands builds it with both flags on, so each command is classified
    even though it is usually absent."""
    from aew.cli import commands

    parser = argparse.ArgumentParser(prog="aew", description="Agent Engineering Workflow")
    parser.add_argument("--version", action="version", version=f"aew {__version__} (spec set {SPEC_SET})")
    parser.add_argument("-C", dest="cwd", default=None, help="run as if started in this directory")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.register(sub, recall_search=recall_search, coordination_reads=coordination_reads)
    fields.register(parser)
    credentials.register(parser)
    return parser


class _PreScan(argparse.ArgumentParser):
    def error(self, message: str):  # never print or exit: the real parser reports every error
        raise ValueError(message)


def recall_search_for(argv: list[str], *, aew_root: Path | None = None) -> bool:
    """Whether the parser for ``argv`` registers `history search`: only for a `history` command (others pay nothing),
    and only when the project it runs in (``-C`` applied as the parser applies it, else the working directory; or
    ``aew_root`` when the caller already knows the project) has the switch on in its adopted execution policy. No
    project found, or anything else unreadable, is off."""
    pre = _PreScan(add_help=False)
    pre.add_argument("-C", dest="cwd", default=None)
    pre.add_argument("--print-credential", action="store_true")
    pre.add_argument("--version", action="store_true")
    pre.add_argument("command", nargs="?")
    pre.add_argument("rest", nargs=argparse.REMAINDER)
    try:
        ns, _ = pre.parse_known_args(argv)
    except ValueError:
        return False
    if ns.command != "history":
        return False
    from aew.engine import recall

    if aew_root is None:
        from aew.engine.base import Kernel

        try:
            _, aew_root = Kernel.locate(Path(ns.cwd) if ns.cwd else Path.cwd())
        except Exception:  # no project here (or not an authoritative one): the command does not exist
            return False
    return recall.recall_search_enabled(aew_root)


def coordination_reads_for(argv: list[str], *, aew_root: Path | None = None) -> bool:
    """Whether the parser for ``argv`` registers `aew message` (F9-A plan D-24, D-31): only for a `message` command
    (others pay nothing), never inside a worker's run (``AEW_AGENT_ENDPOINT`` set: D-21, no worker is offered reads of
    other threads), and only when the project (``-C`` applied, else the working directory, or ``aew_root``) has the
    switch on or holds a thread. No project found, or anything unreadable, is off."""
    if os.environ.get("AEW_AGENT_ENDPOINT"):
        return False
    pre = _PreScan(add_help=False)
    pre.add_argument("-C", dest="cwd", default=None)
    pre.add_argument("--print-credential", action="store_true")
    pre.add_argument("--version", action="store_true")
    pre.add_argument("command", nargs="?")
    pre.add_argument("rest", nargs=argparse.REMAINDER)
    try:
        ns, _ = pre.parse_known_args(argv)
    except ValueError:
        return False
    if ns.command != "message":
        return False
    try:
        from aew.engine.api import Engine
        from aew.engine.base import Kernel

        if aew_root is None:
            repo_root, aew_root = Kernel.locate(Path(ns.cwd) if ns.cwd else Path.cwd())
        else:
            repo_root = aew_root.parent
        return Engine(repo_root, aew_root).coordination_reads_on()
    except Exception:  # no project here, or an unreadable one: the command does not exist
        return False


def _utf8_streams() -> None:
    # Harnesses read AEW output through pipes; on Windows a pipe defaults to the ANSI code page,
    # which cannot encode pack/status text (e.g. "→"). AEW output is always UTF-8.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)  # absent when a caller replaced the stream
        try:
            if reconfigure is not None:
                reconfigure(encoding="utf-8", errors="replace")
        except ValueError:
            pass


def _run(args: argparse.Namespace, argv: list[str], handler: Handler) -> tuple[Any, bool]:
    """Run a command here, or, inside a Lead session, through the session's Lead bridge (ADR-0009)."""
    if os.environ.get("AEW_LEAD_BROKER"):
        from aew.errors import UsageError
        from aew.harness import lead_broker

        refusal = lead_broker.refuses_locally(args)
        if refusal:
            raise UsageError(refusal)
        if args.print_credential:
            raise UsageError("--print-credential is refused in a Lead session: a credential never goes into the "
                             "Lead's transcript")
        if lead_broker.routes(args):
            reply = lead_broker.forward(argv, args)
            return reply["result"], reply["json"]
    from aew.engine import dispatch

    credentials.before(args)  # a credential this command issues must have somewhere safe to go (ADR-0009)
    with dispatch.channel("cli"):  # recorded with any dispatch decision this command makes (M4-A)
        return credentials.deliver(handler(args), args), getattr(args, "json", False)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not profile.cli_start():
        return _main(argv)
    code = 1
    try:
        code = _main(argv)
        return code
    finally:
        profile.cli_finish(argv, code)


def _main(argv: list[str]) -> int:
    from aew import process_kind

    # Before anything can open the store (STG-05 CB-09). Scoped, since tests call `main` in-process.
    with process_kind.declared_as(process_kind.cli_entry_point(argv, os.environ)):
        return _run_main(argv)


def _run_main(argv: list[str]) -> int:
    _utf8_streams()
    parser = build_parser(recall_search=recall_search_for(argv), coordination_reads=coordination_reads_for(argv))
    try:
        argv = fields.expand(argv, parser)  # authored values arrive as data, never as shell text (B1)
    except AEWError as exc:
        sys.stderr.write(json.dumps({"ok": False, "error": exc.to_dict()}, indent=2, default=str) + "\n")
        return exc.exit_code
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        relayed = _relayed_read(args, argv)
        if relayed is not None:
            return relayed
        result, as_json = _run(args, argv, handler)
    except AEWError as exc:
        # A refusal that moved the revision by recording itself (an anomaly, M4-E E5b) says so beside the error.
        recorded = {"recorded": exc.recorded} if exc.recorded else {}
        sys.stderr.write(json.dumps({"ok": False, "error": exc.to_dict(), **recorded}, indent=2, default=str) + "\n")
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    except OSError as exc:
        refusal = _contained_refusal(exc)
        if refusal is None:
            raise
        sys.stderr.write(json.dumps({"ok": False, "error": refusal.to_dict()}, indent=2, default=str) + "\n")
        return refusal.exit_code
    if result is not None:
        emit(result, as_json=as_json)
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    exit_status = getattr(args, "exit_status", None)  # a command whose result has its own exit status (`harness wait`)
    return int(exit_status(result)) if exit_status is not None else 0


def _relayed_read(args: argparse.Namespace, argv: list[str]) -> int | None:
    """Inside the contained Lead, a read its broker runs on the host (STG-05 CS-4 addendum 4: what it reads is under
    the masked `.aew/local`): what it printed there, as it printed it, and its exit status. ``None`` otherwise."""
    if not os.environ.get("AEW_LEAD_BROKER"):
        return None
    from aew.harness import lead_broker

    if not lead_broker.relays(args):
        return None
    reply = lead_broker.relay_read(argv)
    sys.stdout.write(reply["stdout"])
    sys.stderr.write(reply["stderr"])
    return int(reply["exit"])


def _contained_refusal(exc: OSError) -> AEWError | None:
    """In the contained Lead's sandbox (STG-05 CS-4, outcome 7), a write that met its read-only `.aew/` or git metadata
    is refused by design, and says so instead of a traceback. The variable that marks the sandbox shapes this message
    only: the kernel refused the write."""
    import errno

    from aew import process_kind
    from aew.errors import PermissionDenied

    if exc.errno != errno.EROFS or not os.environ.get(process_kind.LEAD_CONTAINED_ENV):
        return None
    return PermissionDenied(
        f"this Lead session is contained by design: {exc.filename or 'that path'} is read-only inside it, as are "
        "`.aew/` and the git metadata. Lead-authenticated `aew` commands reach the session's broker, which writes AEW "
        "state for you; anything else that writes them is for the operator, at their own terminal",
        reason="lead_contained", path=str(exc.filename) if exc.filename else None)


if __name__ == "__main__":
    raise SystemExit(main())
