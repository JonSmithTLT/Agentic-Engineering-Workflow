"""``--fields FILE|-``: any command's option values as data (M3 hardening B1; ``AEW-INV-INTENT-001``).

Free text that a person or a model authors (titles, goals, contract clauses, scopes, reasons, notes) is rewritten
by any shell it passes through: ``"-$15.00"`` loses ``$1``, backticks run commands, ``*`` globs. A model Lead in
the M3 dogfood stored a corrupted Ticket goal exactly that way. With ``--fields``, the values come from a YAML (or
JSON) mapping in a file or on stdin, typically a quoted heredoc (``<<'EOF'``) that no shell expands, and each one
becomes a ``--name=value`` argument before the command's arguments are parsed, so no shell ever sees it.

The mapping is parsed as data, not taken byte for byte. Scalars are read with YAML's base loader (``1.10`` is not
``1.1``, ``yes`` is not a boolean), and quoted values follow YAML's rules (double quotes process escapes, as in
JSON). Every YAML form that would silently change authored text is refused, with a hint: a ``#`` comment after an
unquoted value (``Finish #1`` would be stored ``Finish``), an unquoted value continued on another line (the line
break would become a space), a repeated key or two spellings of one option (only the last would be kept), and
anchors, aliases and tags (independent audit I5).

Inside a Lead session the expansion happens in the ``aew`` client, so the broker receives the values as argument
data, never as shell text.
"""

from __future__ import annotations

import argparse
import difflib
import re
from typing import Any

import yaml

from aew.errors import UsageError
from aew.util import read_text_input

OPTION = "--fields"
HELP = ("option values as data: a YAML/JSON mapping (option name: value, or a list for a repeatable option) from "
        "FILE or - (stdin). Use it for free text, e.g. `--fields - <<'EOF'`, so that no shell rewrites $, backticks, "
        "globs or quotes. Quote a value containing ' #' or ': ' ('...', '' for a quote), or write it as a block "
        "(|-); YAML forms that would change the text are refused")
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


def _refuse(what: str, at: Any) -> UsageError:
    return UsageError(f"--fields line {at.start_mark.line + 1}: {what}, so YAML would not keep the text as written. "
                      "Quote the value ('...', with '' for a quote inside it), write it as a block (`|-` and indented "
                      "lines), or give the mapping as JSON")


def _text(node: Any, source: list[str], key: str) -> str:
    """One authored value; refused where YAML would change the text as written (independent audit I5)."""
    if not isinstance(node, yaml.ScalarNode):
        raise UsageError(f"--fields: {key} must be text or a list of texts, not a nested structure")
    if node.style is None:  # unquoted
        if node.end_mark.line != node.start_mark.line:
            raise _refuse(f"the unquoted value of {key} continues on the next line (YAML joins lines with a space)",
                          node)
        line = source[node.end_mark.line] if node.end_mark.line < len(source) else ""
        if line[node.end_mark.column:].lstrip().startswith("#"):
            raise _refuse(f"` #` after the unquoted value of {key} starts a YAML comment, which drops the rest of "
                          "the line", node)
    return str(node.value)


def _load(text: str) -> dict[str, str | list[str]]:
    """The option mapping, walked node by node so that nothing is silently replaced or dropped."""
    if not text.strip():
        return {}
    try:
        for event in yaml.parse(text, Loader=yaml.BaseLoader):  # noqa: S506 - events only, nothing is constructed
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None) is not None:
                raise _refuse("a YAML anchor or alias (`&name`, `*name`) is not text", event)
            if getattr(event, "tag", None) is not None:
                raise _refuse("a YAML tag (`!name`) is not text", event)
        root = yaml.compose(text, Loader=yaml.BaseLoader)  # noqa: S506 - nodes only: scalars stay text
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark is not None else ""
        raise UsageError(f"--fields: not a YAML or JSON mapping: {getattr(exc, 'problem', None) or exc}{where}. "
                         "Start every option name at the beginning of its line, and put a value containing ': ' or "
                         "' #' in single quotes") from None
    if not isinstance(root, yaml.MappingNode):
        raise UsageError("--fields: expected a mapping of option names to values, e.g. `title: ...` and "
                         "`goal: [..., ...]`")
    source = text.splitlines()
    data: dict[str, str | list[str]] = {}
    seen: dict[str, str] = {}
    for key_node, value_node in root.value:
        key = str(key_node.value) if isinstance(key_node, yaml.ScalarNode) else repr(key_node)
        name = key.replace("_", "-")
        if name in seen:
            raise UsageError(f"--fields: {seen[name]!r} and {key!r} name the same option, and YAML would keep only "
                             "the last. Give it once, with a list for a repeatable option")
        seen[name] = key
        if isinstance(value_node, yaml.SequenceNode):
            data[key] = [_text(item, source, key) for item in value_node.value]
        else:
            data[key] = _text(value_node, source, key)
    return data


def _scalar(value: Any, key: str) -> str:
    if isinstance(value, (dict, list)):
        raise UsageError(f"--fields: {key} must be text or a list of texts, not a nested structure")
    return str(value)


def expand(argv: list[str], parser: argparse.ArgumentParser) -> list[str]:
    """Replace ``--fields FILE|-`` with ``--name=value`` arguments, one per value, never through a shell."""
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
    data = _load(read_text_input(source))
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
        if action is None:  # M3 audit X1: say which option was meant, not only that this one does not exist
            known = [o for o in command._option_string_actions if o.startswith("--") and o not in {OPTION, "--help"}]
            close = difflib.get_close_matches(option, known, n=1)
            raise UsageError(f"--fields: this command has no option {option}"
                             + (f"; did you mean {close[0]}?" if close else " (see its --help)"))
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
