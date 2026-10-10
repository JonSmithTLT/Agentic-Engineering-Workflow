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


def build_parser(recall_search: bool = False) -> argparse.ArgumentParser:
    """The ``aew`` parser. ``recall_search`` registers `history search` (register F21, Arm B), which exists only while
    the project's adopted execution policy switches it on (``recall_search_for``); every walk of the command set that
    classifies commands builds it with the flag on, so the command is classified even though it is usually absent."""
    from aew.cli import commands

    parser = argparse.ArgumentParser(prog="aew", description="Agent Engineering Workflow")
    parser.add_argument("--version", action="version", version=f"aew {__version__} (spec set {SPEC_SET})")
    parser.add_argument("-C", dest="cwd", default=None, help="run as if started in this directory")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.register(sub, recall_search=recall_search)
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
    _utf8_streams()
    parser = build_parser(recall_search=recall_search_for(argv))
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
        result, as_json = _run(args, argv, handler)
    except AEWError as exc:
        sys.stderr.write(json.dumps({"ok": False, "error": exc.to_dict()}, indent=2, default=str) + "\n")
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    if result is not None:
        emit(result, as_json=as_json)
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
