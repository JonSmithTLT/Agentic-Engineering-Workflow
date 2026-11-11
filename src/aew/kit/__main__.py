"""Operator entry point for the seeded kit."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from aew.errors import AEWError
from aew.kit import OPENING_REQUEST, RECEIPT_READER, launch_argv, prepare
from aew.kit.receipt import write_receipt


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m aew.kit")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="prepare a seeded repository and open the Lead")
    start.add_argument("dest", type=Path)
    start.add_argument("--model", required=True)
    start.add_argument("--lead-model", required=True)
    start.add_argument("--provider-env", action="append", default=[])
    receipt = commands.add_parser("receipt", help="write the run receipt from AEW records")
    receipt.add_argument("dest", type=Path)
    receipt.add_argument("--readable", choices=("yes", "no"))
    args = parser.parse_args()
    try:
        if args.command == "receipt":
            readable = args.readable
            if readable is None and sys.stdin.isatty() and sys.stdout.isatty():
                try:
                    answer = input("Was the run readable? [yes/no, Enter to skip] ").strip().lower()
                except EOFError:
                    answer = ""
                readable = answer if answer in ("yes", "no") else None
            print(write_receipt(args.dest, readable=readable))
            print(RECEIPT_READER)
            return 0
        provider_env = tuple(args.provider_env)
        prepare(args.dest, args.model, args.lead_model, lead_provider_env=provider_env)
        print(OPENING_REQUEST, flush=True)
        print(RECEIPT_READER, flush=True)
        if sys.platform == "win32":
            print("Windows: UNQUALIFIED. This is an install check only. Run the personal alpha on Linux.")
            return 0
        return subprocess.call(launch_argv(args.dest, provider_env, args.lead_model))
    except (AEWError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
