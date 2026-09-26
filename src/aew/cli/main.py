"""``aew`` command-line entry point.

The CLI is a thin adapter: it parses arguments, calls the engine, and renders
results. It holds no workflow logic, so a future MCP adapter can call the same
engine without becoming a second state authority (WC §15.6, invariant 21).
"""

from __future__ import annotations

import argparse
import json
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        result = handler(args)
    except AEWError as exc:
        sys.stderr.write(json.dumps({"ok": False, "error": exc.to_dict()}, indent=2, default=str) + "\n")
        return exc.exit_code
    except KeyboardInterrupt:
        return 130
    if result is not None:
        emit(result, as_json=getattr(args, "json", False))
    if isinstance(result, dict) and result.get("ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
