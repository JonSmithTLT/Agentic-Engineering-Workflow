"""``--fields FILE|-``: any command's option values as data (M3 hardening B1; ``AEW-INV-INTENT-001``).

Free text that a person or a model authors (titles, goals, contract clauses, scopes, reasons, notes) is rewritten
by any shell it passes through: ``"-$15.00"`` loses ``$1``, backticks run commands, ``*`` globs. A model Lead in
the M3 dogfood stored a corrupted Ticket goal exactly that way. With ``--fields``, the values come from a YAML (or
JSON) mapping in a file or on stdin, typically a quoted heredoc (``<<'EOF'``) that no shell expands, and each one
is applied literally as ``--name=value`` before the command's arguments are parsed. Scalars are read with YAML's
base loader, so every value stays the exact text written (``1.10`` is not ``1.1``, ``yes`` is not a boolean).

Inside a Lead session the expansion happens in the ``aew`` client, so the broker receives the values as argument
data, never as shell text.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

import yaml

from aew.errors import UsageError
from aew.util import read_text_input

OPTION = "--fields"
HELP = ("option values as data: a YAML/JSON mapping (option name: value, or a list for a repeatable option) from "
        "FILE or - (stdin), applied literally. Use it for free text, e.g. `--fields - <<'EOF'`, so that no shell "
        "rewrites $, backticks, globs or quotes")
REFUSED = {"fields": "--fields cannot nest", "token": "a credential never goes through --fields"}
FLAG_VALUES = {"true": True, "false": False}


def _not_expanded(_: str) -> str:
    raise argparse.ArgumentTypeError("--fields must be expanded by the aew client before parsing")


def register(parser: argparse.ArgumentParser) -> None:
    """Document ``--fields`` on every command (it is expanded before parsing, so the option itself never takes a
    value: a raw ``--fields`` reaching the parser is refused, never ignored)."""
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        if OPTION not in parser._option_string_actions:
            parser.add_argument(OPTION, metavar="FILE|-", type=_not_expanded, help=HELP)
        return
    for sub in subs:
        for child in dict.fromkeys(sub.choices.values()):  # aliases share a parser
            register(child)


def _command_parser(parser: argparse.ArgumentParser, head: list[str]) -> argparse.ArgumentParser:
    """The (sub)command parser the tokens before ``--fields`` select."""
    current = parser
    for token in head:
        sub = next((a for a in current._actions if isinstance(a, argparse._SubParsersAction)), None)
        if sub is not None and token in sub.choices:
            current = sub.choices[token]
    return current


def _scalar(value: Any, key: str) -> str:
    if isinstance(value, (dict, list)):
        raise UsageError(f"--fields: {key} must be text or a list of texts, not a nested structure")
    return str(value)


def expand(argv: list[str], parser: argparse.ArgumentParser) -> list[str]:
    """Replace ``--fields FILE|-`` with literal ``--name=value`` arguments."""
    at = [i for i, a in enumerate(argv) if a == OPTION or a.startswith(OPTION + "=")]
    if not at:
        return argv
    if len(at) > 1:
        raise UsageError("give --fields once")
    i = at[0]
    if argv[i] == OPTION:
        if i + 1 >= len(argv):
            raise UsageError("--fields needs a file, or - for stdin")
        source, head, rest = argv[i + 1], argv[:i], argv[i + 2:]
    else:
        source, head, rest = argv[i].split("=", 1)[1], argv[:i], argv[i + 1:]
    if source == "-" and "-" in head + rest:
        raise UsageError("only one input can read stdin: both --fields and another option name `-`")
    text = read_text_input(source)
    try:
        data = yaml.load(text, Loader=yaml.BaseLoader) if text.strip() else {}  # noqa: S506 - scalars stay text
    except yaml.YAMLError as exc:
        raise UsageError(f"--fields: not a YAML or JSON mapping: {exc}") from None
    if not isinstance(data, dict):
        raise UsageError("--fields: expected a mapping of option names to values, e.g. `title: ...` and "
                         "`goal: [..., ...]`")
    command = _command_parser(parser, head)
    tokens: list[str] = []
    for key, value in data.items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", key):
            raise UsageError(f"--fields: {key!r} is not an option name")
        name = key.replace("_", "-")
        if name in REFUSED:
            raise UsageError(f"--fields: {REFUSED[name]}")
        option = f"--{name}"
        action = command._option_string_actions.get(option)
        if action is None:
            raise UsageError(f"--fields: this command has no option {option} (see its --help)")
        items = [_scalar(v, key) for v in value] if isinstance(value, list) else [_scalar(value, key)]
        if action.nargs == 0:  # an on/off switch
            if len(items) != 1 or items[0].lower() not in FLAG_VALUES:
                raise UsageError(f"--fields: {key} is a switch: give true or false")
            tokens += [option] if FLAG_VALUES[items[0].lower()] else []
            continue
        if len(items) != 1 and not isinstance(action, argparse._AppendAction):
            raise UsageError(f"--fields: {key} takes one value (only repeatable options take a list)")
        tokens += [f"{option}={item}" for item in items]
    return head + tokens + rest
