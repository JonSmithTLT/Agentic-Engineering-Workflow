"""Register F21's Arm B prototype, the parser side (the lead developer's plan v6 §1, §3, §5): off means absent.

With the switch off, `aew history` is exactly the parser it was before the prototype: the flag-off parser equals the
flag-on parser with `search` taken out, byte for byte, in help, usage and argparse's invalid-choice message, and its
subcommands are exactly the ones `main` had. The query and rendering rules are checked here without a project.
"""

from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

import pytest

from aew.cli.main import build_parser, recall_search_for
from aew.engine import recall
from aew.errors import UsageError
from aew.policy import classes
from aew.schemas import schema as load_schema

# `aew history`'s subcommands on main before the prototype, in registration order.
MAIN_HISTORY = ["show", "list", "log", "compact", "links", "load", "audit", "reindex"]


def history_of(parser: argparse.ArgumentParser) -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    top = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    history = top.choices["history"]
    return history, next(a for a in history._actions if isinstance(a, argparse._SubParsersAction))


def without_search(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """The flag-on parser with `history search` taken out again."""
    _, sub = history_of(parser)
    del sub.choices["search"]
    sub._choices_actions = [a for a in sub._choices_actions if a.dest != "search"]
    return parser


def failure(parser: argparse.ArgumentParser, argv: list[str]) -> str:
    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit):
        parser.parse_args(argv)
    return err.getvalue()


def test_with_the_switch_off_the_history_parser_is_exactly_mains():
    off, reference = build_parser(), without_search(build_parser(recall_search=True))
    history_off, sub_off = history_of(off)
    history_ref, _ = history_of(reference)
    assert list(sub_off.choices) == MAIN_HISTORY
    assert history_off.format_help() == history_ref.format_help() and "search" not in history_off.format_help()
    assert history_off.format_usage() == history_ref.format_usage()
    assert off.format_help() == reference.format_help()
    for argv in (["history", "search", "x"], ["history"], ["history", "nope"]):
        message = failure(off, argv)
        assert message == failure(reference, argv) and "search" not in message.replace("'search'", "")
    unknown, missing = failure(off, ["history", "frobnicate", "x"]), failure(off, ["history", "search", "x"])
    assert missing == unknown.replace("frobnicate", "search")  # `search` fails exactly as an unknown subcommand


def test_with_the_switch_on_search_is_registered_last_and_documents_its_semantics():
    history, sub = history_of(build_parser(recall_search=True))
    assert list(sub.choices) == [*MAIN_HISTORY, "search"]
    text = sub.choices["search"].format_help()
    assert "phrase" in text and "all terms must match" in text and "not admitted Knowledge" in history.format_help()


def test_only_a_history_command_reads_the_switch(monkeypatch):
    read = []
    monkeypatch.setattr(recall, "recall_search_enabled", lambda root: read.append(root) or True)
    assert recall_search_for(["status"]) is False and recall_search_for([]) is False
    assert recall_search_for(["--print-credential", "work", "list"]) is False
    assert read == []
    assert recall_search_for(["-C", "somewhere", "history", "search", "x"], aew_root=Path(".")) \
        is True and len(read) == 1
    assert recall_search_for(["history", "--no-such-option"], aew_root=Path(".")) is True


def test_the_switch_is_an_operational_field_of_the_execution_policy():
    schema = load_schema("execution")
    node = schema["properties"]["recall"]["properties"]["raw_history_search"]
    assert node[classes.KEY] == classes.OPERATIONAL and not classes.unclassified(schema)
    assert set(node["enum"]) == {"off", False, "explicit"}  # YAML reads an unquoted `off` as false: still off


def test_queries_are_quoted_phrases_anded_and_bounded():
    assert recall.check_query(["a b", 'say "hi"']) == '"a b" AND "say ""hi"""'
    for bad in ([], [""], ["   "], ["a\x00b"], ["a\nb"], ["\x7f"], ["\x85"], ["t"] * 17, ["x" * 513],
                ["x" * 300, "y" * 300]):
        with pytest.raises(UsageError):
            recall.check_query(bad)
    assert recall.check_query(["t"] * 16).count(" AND ") == 15
    assert recall.check_query(["x" * 256, "y" * 255])


def test_inert_rendering_escapes_controls_format_characters_and_separators():
    out = recall._inert("a\x1b[31mb\u202ec\u200bd\u2028e\x00f\x85g\x7fh\ni\tj")
    assert out == "a\\u{001b}[31mb\\u{202e}c\\u{200b}d\\u{2028}e\\u{0000}f\\u{0085}g\\u{007f}h i j"
    assert recall._inert("\x1b" * 100, 20) == "\\u{001b}\\u{001b}"  # never cut inside an escape
