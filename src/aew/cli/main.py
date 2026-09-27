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
from typing import Any, Callable

from aew import SPEC_SET, __version__
from aew.errors import AEWError

Handler = Callable[[argparse.Namespace], Any]


def emit(result: Any, *, as_json: bool) -> None:
    if as_json or not isinstance(result, str):
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=False, default=str) + "\n")
    else:
        sys.stdout.write(result if result.endswith("\n") else result + "\n")


def build_parser() -> argparse.ArgumentParser:
    from aew.cli import commands

    parser = argparse.ArgumentParser(prog="aew", description="Agent Engineering Workflow")
    parser.add_argument("--version", action="version", version=f"aew {__version__} (spec set {SPEC_SET})")
    parser.add_argument("-C", dest="cwd", default=None, help="run as if started in this directory")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.register(sub)
    return parser


def _utf8_streams() -> None:
    # Harnesses read AEW output through pipes; on Windows a pipe defaults to the ANSI code page,
    # which cannot encode pack/status text (e.g. "→"). AEW output is always UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _run(args: argparse.Namespace, argv: list[str], handler: Handler) -> tuple[Any, bool]:
    """Run a command here, or, inside a Lead session, through the session's Lead bridge (ADR-0009)."""
    if os.environ.get("AEW_LEAD_BROKER"):
        from aew.errors import UsageError
        from aew.harness import lead_broker

        refusal = lead_broker.refuses_locally(args)
        if refusal:
            raise UsageError(refusal)
        if lead_broker.routes(args):
            reply = lead_broker.forward(argv, args)
            return reply["result"], reply["json"]
    return handler(args), getattr(args, "json", False)


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
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
