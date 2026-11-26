"""The operator's local D-01 read channel (A-45)."""

from __future__ import annotations

import argparse
from pathlib import Path


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("read", add_help=False, help="read committed AEW state without a service")
    parser.add_argument("route", nargs="?", help="D-01 route, including its query if any")
    parser.add_argument("--human", action="store_true", help="render the D-01 response as text")
    parser.add_argument("-h", "--help", dest="read_help", action="store_true", help="list the outage read profile")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    from aew.cli.main import emit
    from aew.errors import OutageReadRefused
    from aew.stg02 import wire
    from aew.stg02.outage import profile, read, render

    correlation = wire.correlation_id()
    route = None if args.read_help else args.route
    try:
        response = read(Path(args.cwd) if args.cwd else Path.cwd(), route, correlation)
    except OutageReadRefused as exc:
        _, problem = wire.problem(exc.details["reason"], correlation, title=exc.message or None)
        text = f"{problem['code']}: {problem['title']}"
        if exc.details.get("destination"):
            text += f"\nNot read on this channel. {exc.details['destination']}"
        emit(text if args.human else problem, as_json=not args.human)
        return exc.exit_code
    if response is None:
        emit(profile(), as_json=False)
    else:
        emit(render(response) if args.human else response.body, as_json=not args.human)
    return 0
