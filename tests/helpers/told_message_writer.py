"""Real process for the local-receipt crash/union tests; no credential, engine state or provider."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from aew import util
from aew.harness import told_messages as T


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("generation", type=int)
    p.add_argument("messages", nargs="+")
    p.add_argument("--gate", type=Path)
    p.add_argument("--ready", type=Path)
    p.add_argument("--crash", choices=["before", "after"])
    p.add_argument("--authority", type=Path)
    p.add_argument("--checked", type=Path)
    args = p.parse_args()
    if args.ready:
        args.ready.touch()
    if args.gate:
        deadline = time.monotonic() + 20
        while not args.gate.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("test gate missing")
            time.sleep(0.01)
    if args.crash:
        replace = util.replace_with_retry

        def die(src, dest):
            if args.crash == "after":
                replace(src, dest)
            os._exit(77)

        util.replace_with_retry = die
    def current():
        held = args.authority is None or args.authority.read_text(encoding="utf-8") == str(args.generation)
        if args.checked:
            args.checked.touch()
        return held

    T.record(args.root, args.generation, args.messages, current=current)


if __name__ == "__main__":
    main()
