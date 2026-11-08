"""Run every relayed command through the broker's ``run_cli`` with each value naming a file, and print which commands
opened that file. A process of its own, because an audit hook cannot be removed: run by
tests/integration/test_relayed_file_arguments_through_a_broker.py. Arguments: the project's root, its Lead credential,
a Ticket's id and the absolute path of the file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from aew import errors
from aew.cli.main import build_parser
from aew.engine.api import Engine
from aew.harness import lead_broker


def commands(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs and parser.get_default("handler"):
        yield path, parser
    for sub in subs:
        for name, child in sub.choices.items():
            yield from commands(child, (*path, name))


def argv_for(path: tuple[str, ...], command: argparse.ArgumentParser, value: str, positional: str,
             rev: int) -> list[str]:
    argv = list(path)
    for a in command._actions:
        if a.dest in {"help", "token", "fields", "print_credential"}:
            continue
        if a.nargs == 0:
            if a.dest == "launch":  # a Lead session's dispatches are refused without it, before the handler
                argv.append(a.option_strings[0])
            continue
        given = (str(rev) if a.type is int else str(a.choices[0]) if a.choices else
                 value if a.option_strings else positional)
        argv += [a.option_strings[0], given] if a.option_strings else [given]
    return argv


def main() -> None:
    root, token, ticket, target = sys.argv[1:5]
    wanted = os.path.normcase(target)
    opened: list[str] = []
    current: list[str] = [""]

    def hook(event: str, args: tuple) -> None:
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            if wanted in os.path.normcase(os.fsdecode(args[0])):
                opened.append(current[0])

    sys.addaudithook(hook)
    engine = Engine.discover(Path(root))
    walked = 0
    for path, command in commands(build_parser(recall_search=True, coordination_reads=True)):
        if not any(a.dest == "token" for a in command._actions) or frozenset(path) in lead_broker.NOT_RELAYED:
            continue
        walked += 1
        for positional in (target, ticket):  # a value that is not an id, then one that gets further
            current[0] = " ".join(path)
            argv = argv_for(path, command, target, positional, engine.store.read()["revision"])
            try:
                lead_broker.run_cli(engine, token, argv, root, "", channel="lead_broker")
            except (errors.AEWError, OSError, ValueError, KeyError):
                pass  # refused, as most of these are: what counts is what it opened on the way
    print(json.dumps({"walked": walked, "opened": sorted(set(opened))}))


if __name__ == "__main__":
    main()
