"""Give every relayed command and typed tool one value at a time that names a path, and report what the process did with
it. A process of its own, because an audit hook cannot be removed: run by
tests/integration/test_relayed_file_arguments_through_a_broker.py.

Each row is a command with its required arguments only, and the one argument under test holding a value with a marker
in it: an absolute path, then a relative one that climbs. A row is reported when the marker reaches an audit event (an
open, a directory listing, a write, a child process) or a call of ``os.stat``, ``lstat``, ``access`` or
``os.path.exists``, ``isfile``, ``isdir`` (none of which audits, and which is how a read behind ``is_file()`` starts).

What this does not see: a child process's own reads; a path past a state check this project doesn't reach (one planned
Ticket, and what the rows before did to it), which includes a row that stops at a check of an argument this walk filled
in itself; a typed tool's object-typed properties, which are not walked; options of a dispatching command, whose id is
never a real one here, so that no row launches anything. ``-C`` and a request's directory are not rows: the broker holds
those to the project.

Arguments: the project's root, its Lead credential, a Ticket's id and a directory for the values. Options: ``--only
COMMAND`` to walk one command, and ``--plant open|exists`` to add a ``checkpoint --attachment`` with no help text, read
through a helper, for the test that this walk can fail."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

from aew.cli import main as cli_main
from aew.engine.api import Engine
from aew.harness import lead_broker
from aew.surface import contract, run
from aew.surface.context import SurfaceContext

MARK = "relayed-value-marker"
NOT_A_ROW = {"help", "token", "fields", "print_credential"}
# These end the walk's one Ticket, so they come last.
ENDS_THE_TICKET = {"work cancel", "work close", "work accept", "work reconcile", "work move", "work promote",
                   "work transition", "work reclassify"}
# What a typed tool's required arguments hold when they are not the one under test.
TOOL_DEFAULTS = {"title": "t", "risk_class": 1, "rationale": "r", "subject": "SI-0001", "choice": "abandon",
                 "action": "lower", "mode": "crawl", "runs": ["R-INV-0001-1"], "timeout_s": 1}

seen: list[tuple[str, str]] = []


def _text(value: Any) -> str:
    if isinstance(value, (str, bytes, os.PathLike)):
        return os.fsdecode(value)
    if isinstance(value, (list, tuple)):
        return " ".join(_text(v) for v in value)
    return ""


def _hook(event: str, args: tuple) -> None:
    if not event.startswith(("sys.", "builtins.", "code.", "compile", "exec", "import", "marshal", "object.", "ctypes",
                             "gc.", "socket.", "time.")) and MARK in _text(args):
        seen.append((event, _text(args)[:200]))


def _watch(module: Any, name: str) -> None:
    real = getattr(module, name)

    def watched(path: Any, *a: Any, **k: Any) -> Any:
        if MARK in _text(path):
            seen.append((f"{module.__name__}.{name}", _text(path)[:200]))
        return real(path, *a, **k)

    setattr(module, name, watched)


def commands(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs and parser.get_default("handler"):
        yield path, parser
    for sub in subs:
        for name, child in sub.choices.items():
            yield from commands(child, (*path, name))


def _value_of(a: argparse.Action, ticket: str, rev: int, dispatches: bool) -> str:
    """A required argument that is not the one under test: ``choices`` first, since a choice may be an int."""
    if a.choices:
        return str(a.choices[0])
    if a.dest == "expect_rev":
        return str(rev)
    if a.type is int:
        return "1"
    if not a.option_strings:
        return "T-9999" if dispatches else ticket if a.dest == "work_id" else "r"
    return "-" if isinstance(a, cli_main.fields.FileInput) else "r"


def argv_for(path: tuple[str, ...], command: argparse.ArgumentParser, target: argparse.Action, value: str, ticket: str,
             rev: int) -> list[str]:
    """The command with its required arguments only, and ``target`` holding ``value``."""
    dispatches = any(p <= frozenset(path) for p in lead_broker.DISPATCHES)
    rivals = {x.dest for g in command._mutually_exclusive_groups if target in g._group_actions
              for x in g._group_actions}
    chosen = {g._group_actions[0].dest for g in command._mutually_exclusive_groups
              if g.required and target not in g._group_actions}
    argv = list(path)
    for a in command._actions:
        if a is target:
            argv += [a.option_strings[0], value] if a.option_strings else [value]
        elif a.dest in NOT_A_ROW or a.dest in rivals:
            continue
        elif a.nargs == 0:
            argv += [a.option_strings[0]] if a.dest == "launch" and dispatches else []
        elif a.required or not a.option_strings or a.dest in chosen:
            given = _value_of(a, ticket, rev, dispatches)
            argv += [a.option_strings[0], given] if a.option_strings else [given]
    return argv


def _outcome(call: Any) -> str:
    noise = io.StringIO()
    try:
        with contextlib.redirect_stderr(noise), contextlib.redirect_stdout(noise):
            call()
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - what counts is how far it got, and most of these are refused
        return f"{getattr(exc, 'code', type(exc).__name__)}: {getattr(exc, 'message', exc)}"[:160]
    return "ran"


def _plant(kind: str) -> None:
    """A later author's mistake: ``checkpoint --attachment``, no help text, read below the handler through a helper."""
    real = cli_main.build_parser

    def read_it(name: str | None) -> None:
        if name and (kind == "open" or Path(name).exists()):
            Path(name).read_text(encoding="utf-8")

    def build(*a: Any, **k: Any) -> argparse.ArgumentParser:
        parser = real(*a, **k)
        command = dict(commands(parser))[("checkpoint",)]
        command.add_argument("--attachment")
        handler = command.get_default("handler")

        def planted(ns: argparse.Namespace) -> Any:
            with contextlib.suppress(OSError):
                read_it(ns.attachment)
            return handler(ns)

        command.set_defaults(handler=planted)
        return parser

    cli_main.build_parser = build


def main() -> None:
    options = argparse.ArgumentParser()
    options.add_argument("root")
    options.add_argument("token")
    options.add_argument("ticket")
    options.add_argument("values")
    options.add_argument("--only")
    options.add_argument("--plant", choices=["open", "exists"])
    a = options.parse_args()
    if a.plant:
        _plant(a.plant)
    engine = Engine.discover(Path(a.root))
    values = (str(Path(a.values) / MARK / "x"), f"../../../../{MARK}/x")
    parser = cli_main.build_parser(recall_search=True, coordination_reads=True, worker_messaging=True)
    sys.addaudithook(_hook)
    for module, name in ((os, "stat"), (os, "lstat"), (os, "access"), (os.path, "exists"), (os.path, "isfile"),
                         (os.path, "isdir")):
        _watch(module, name)
    rows: list[dict[str, Any]] = []

    def row(route: str, command: str, argument: str, call: Any) -> None:
        del seen[:]
        out = _outcome(call)
        rows.append({"route": route, "command": command, "argument": argument, "outcome": out,
                     "events": sorted({e for e, _ in seen})})

    relayed = [(p, c) for p, c in commands(parser) if any(x.dest == "token" for x in c._actions)
               and frozenset(p) not in lead_broker.NOT_RELAYED and (not a.only or " ".join(p) == a.only)]
    for path, command in sorted(relayed, key=lambda item: " ".join(item[0]) in ENDS_THE_TICKET):
        for target in command._actions:
            if target.dest in NOT_A_ROW or target.nargs == 0 or target.choices or target.type is int:
                continue
            for value in values:
                argv = argv_for(path, command, target, value, a.ticket, engine.store.read()["revision"])
                row("lead.cli", " ".join(path), target.option_strings[0] if target.option_strings else target.dest,
                    lambda argv=argv: lead_broker.run_cli(engine, a.token, argv, a.root, "", channel="lead_broker"))
    if not a.only:
        ctx = SurfaceContext.outside_session(profile="recovery")

        def cli(argv: list[str], stdin: str) -> Any:
            return lead_broker.run_cli(engine, a.token, argv, a.root, stdin, channel="lead_broker")

        for name, tool in contract.TOOLS.items():
            if name == "cli":  # its arguments are the rows above
                continue
            props, required = tool.input_schema.get("properties", {}), tool.input_schema.get("required", [])
            for key, spec in props.items():
                if spec.get("type") not in {"string", "array"} or "enum" in spec:
                    continue
                for value in values:
                    args = {k: a.ticket if k == "work_id" else TOOL_DEFAULTS.get(k, "r") for k in required}
                    if "expect_rev" in props:
                        args["expect_rev"] = engine.store.read()["revision"]
                    if "timeout_s" in props:
                        args["timeout_s"] = 1
                    args[key] = value if spec["type"] == "string" else [value]
                    row("lead.tool", name, key, lambda args=args, name=name: run.run_tool(
                        engine, ctx, name, args, token=a.token, run_cli=cli))
    print(json.dumps({"commands": len(relayed), "rows": rows}))


if __name__ == "__main__":
    main()
