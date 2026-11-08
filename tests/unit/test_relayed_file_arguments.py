"""A relayed Lead command takes bytes: its file arguments are read by the ``aew`` client, and the broker's process reads
no path. The walks below read the live parsers and the handlers' source, so a new file argument that says so in its
name, metavar or help, or that a handler passes straight to a reader, fails here until the client handles it. One that
does neither is for the walk in tests/integration/test_relayed_file_arguments_through_a_broker.py, which runs each
argument and has the same guarantee through a real broker."""

from __future__ import annotations

import argparse
import ast
import io
import re
from pathlib import Path

import pytest

from aew import errors, util
from aew.cli import fields
from aew.cli.main import build_parser
from aew.engine import disposition_ops, stage_intents
from aew.harness import bridge, lead_broker
from aew.schemas import schema

CLI_SOURCE = Path(util.__file__).parent / "cli"
# The file arguments of today's relayed commands: a floor, so the walks cannot pass by finding nothing.
FILE_ARGUMENTS = {("checkpoint", "--note-file"), ("lead handoff offer", "--note-file"),
                  ("work create", "--body-file"), ("plan propose", "--file"), ("harness send", "--file")}
# An option whose words say file or path, that no command opens: what it is instead.
NOT_READ = {("plan propose", "--affected"): "paths recorded on the plan, compared with the change's paths",
            ("work create", "--scope"): "a glob recorded on the Ticket, matched against the change's paths",
            ("work create", "--acceptance-input"): "a glob recorded on the Ticket, for the acceptance checks' run",
            ("plan propose", "--assurance"): "the word `none`: its help says policy path",
            ("plan adopt", "--assurance"): "the word `none`: its help says policy path"}
SAYS_A_FILE = re.compile(r"\b(file|files|path|paths|stdin|dir|directory|folder|output)\b", re.IGNORECASE)
# What takes a path and opens it, as the handlers call it.
READERS = {"read_text_input", "_read_text_arg", "read_submission", "open", "Path", "read_bytes", "read_text"}


def commands(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs and parser.get_default("handler"):
        yield " ".join(path), parser
    for sub in subs:
        for name, child in sub.choices.items():
            yield from commands(child, (*path, name))


def relayed(parser: argparse.ArgumentParser):
    """Every command the broker's ``run_cli`` could run: those with a Lead credential, operator-only ones included,
    since the refusal that keeps them out comes after their ``--fields`` is expanded."""
    for name, command in commands(parser):
        if any(a.dest == "token" for a in command._actions) and frozenset(name.split()) not in lead_broker.NOT_RELAYED:
            yield name, command


def options(command: argparse.ArgumentParser):
    return [a for a in command._actions if a.nargs != 0 and a.dest not in {"help", "token", "fields"}]


def says_a_file_unhandled(parser: argparse.ArgumentParser, not_read: dict[tuple[str, str], str]) -> list[str]:
    return [f"{name} {a.option_strings[0] if a.option_strings else a.dest}" for name, command in relayed(parser)
            for a in options(command)
            if not isinstance(a, fields.FileInput)
            and (name, a.option_strings[0] if a.option_strings else a.dest) not in not_read
            and SAYS_A_FILE.search(" ".join([*a.option_strings, a.metavar or "", a.help or ""]))]


def opened_by_handlers(source: str) -> set[str]:
    """The argument names a handler passes to something that opens a path: ``read_text_input(a.x)``, ``Path(a.x)``."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in READERS:
                found |= {n.attr for arg in node.args for n in ast.walk(arg) if isinstance(n, ast.Attribute)
                          and isinstance(n.value, ast.Name) and n.value.id in {"a", "args", "ns"}}
    return found


def opened_unmarked(parser: argparse.ArgumentParser, opened: set[str]) -> list[str]:
    return [f"{name} {a.option_strings[0] if a.option_strings else a.dest}" for name, command in relayed(parser)
            for a in options(command) if a.dest in opened and not isinstance(a, fields.FileInput)]


def two_file_arguments(parser: argparse.ArgumentParser) -> list[str]:
    return [name for name, command in relayed(parser)
            if sum(isinstance(a, fields.FileInput) for a in command._actions) > 1]


@pytest.fixture(scope="module")
def parser():
    return build_parser(recall_search=True, coordination_reads=True)


def _handlers_source() -> str:
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted(CLI_SOURCE.glob("*.py")))


def test_every_relayed_option_that_says_a_file_is_read_by_the_client_or_is_named_as_not_read(parser):
    assert says_a_file_unhandled(parser, NOT_READ) == []
    marked = {(name, a.option_strings[0]) for name, command in relayed(parser) for a in options(command)
              if isinstance(a, fields.FileInput)}
    assert FILE_ARGUMENTS <= marked


def test_every_argument_a_relayed_handler_opens_is_read_by_the_client(parser):
    opened = opened_by_handlers(_handlers_source()) - {"cwd"}  # `-C`: the broker holds a command to its own project
    assert {"note_file", "body_file", "file"} <= opened
    assert opened_unmarked(parser, opened) == []


def test_no_relayed_read_takes_a_file_argument(parser):
    for name, command in commands(parser):
        path = frozenset(name.split())
        if path in lead_broker.RELAYED_READS:
            allowed = lead_broker.RELAYED_READS[path]
            assert not [a.dest for a in command._actions if isinstance(a, fields.FileInput) and a.dest in allowed], name


def test_the_one_stdin_carries_one_input_so_no_relayed_command_has_two_file_arguments(parser):
    assert two_file_arguments(parser) == []


def test_the_walks_fail_on_a_new_file_argument_the_client_does_not_handle():
    """Planted: a command with each kind of argument, none of them marked."""
    root = argparse.ArgumentParser()
    sub = root.add_subparsers()
    command = sub.add_parser("planted")
    command.set_defaults(handler=lambda a: None)
    command.add_argument("--token")
    command.add_argument("--from-file")
    command.add_argument("--source", metavar="PATH")
    command.add_argument("--config", help="read from this path")
    command.add_argument("--quiet-name")
    assert says_a_file_unhandled(root, {}) == ["planted --from-file", "planted --source", "planted --config"]
    assert says_a_file_unhandled(root, {("planted", "--from-file"): "recorded"}) == ["planted --source",
                                                                                     "planted --config"]
    opened = opened_by_handlers("def h(a):\n    return Path(a.quiet_name).read_bytes()\n")
    assert opened == {"quiet_name"}
    assert opened_unmarked(root, opened) == ["planted --quiet-name"]
    command.add_argument("--one", action=fields.FileInput)
    assert two_file_arguments(root) == []
    command.add_argument("--two", action=fields.FileInput)
    assert two_file_arguments(root) == ["planted"]


# ----------------------------------------------------------------------------------- the client's half


REV = ["--expect-rev", "1"]


def _sent(parser, argv, cwd):
    args = parser.parse_args(argv)
    return lead_broker._as_bytes(argv, args, cwd), args


@pytest.mark.parametrize("form", [["--note-file", "note.md"], ["--note-file=note.md"], ["--note", "note.md"]])
def test_the_client_reads_a_file_argument_and_sends_its_text_however_it_was_spelled(parser, tmp_path, form):
    (tmp_path / "note.md").write_bytes(b"the note\n")
    (sent, stdin), _ = _sent(parser, ["checkpoint", "--next", "x", *form, *REV], tmp_path)
    assert stdin == "the note\n"
    assert parser.parse_args(sent).note_file == "-"


def test_the_client_reads_a_file_named_through_fields(parser, tmp_path):
    (tmp_path / "plan.md").write_bytes(b"the plan\n")
    argv = fields.expand(["plan", "propose", "T-1", *REV, "--fields", "-"], parser, read=lambda _: "file: plan.md\n")
    (sent, stdin), _ = _sent(parser, argv, tmp_path)
    assert stdin == "the plan\n" and parser.parse_args(sent).file == "-"


def test_the_client_reads_a_file_from_the_commands_directory_and_an_absolute_one_as_given(parser, tmp_path):
    (tmp_path / "here").mkdir()
    (tmp_path / "here" / "note.md").write_bytes(b"relative")
    (tmp_path / "abs.md").write_bytes(b"absolute")
    assert _sent(parser, ["checkpoint", *REV, "--note-file", "note.md"], tmp_path / "here")[0][1] == "relative"
    given = ["checkpoint", *REV, "--note-file", str(tmp_path / "abs.md")]
    assert _sent(parser, given, tmp_path / "here")[0][1] == "absolute"


def test_a_file_the_client_cannot_read_is_refused_by_the_client_naming_it(parser, tmp_path):
    with pytest.raises(errors.UsageError, match=r"cannot read .*gone\.md"):
        _sent(parser, ["checkpoint", *REV, "--note-file", "gone.md"], tmp_path)


@pytest.mark.parametrize("form", [["--note-file", "-"], ["--note-file=-"], ["--note", "-"]])
def test_stdin_goes_to_the_broker_however_the_dash_was_spelled(parser, tmp_path, monkeypatch, form):
    monkeypatch.setattr("sys.stdin", io.StringIO("piped"))
    (sent, stdin), _ = _sent(parser, ["checkpoint", *REV, *form], tmp_path)
    assert stdin == "piped" and parser.parse_args(sent).note_file == "-"


def test_a_command_with_no_file_argument_sends_no_input_and_its_arguments_as_they_were(parser, tmp_path):
    argv = ["checkpoint", "--next", "x", *REV]
    assert _sent(parser, argv, tmp_path)[0] == (argv, "")


def test_an_empty_file_argument_is_no_input(parser, tmp_path):
    argv = ["checkpoint", "--note-file", "", *REV]
    assert _sent(parser, argv, tmp_path)[0] == (argv, "")


def test_the_sent_input_comes_before_an_end_of_options_marker(tmp_path):
    planted = argparse.ArgumentParser()
    planted.add_argument("--note-file", action=fields.FileInput)
    planted.add_argument("rest", nargs="*")
    (tmp_path / "n").write_bytes(b"text")
    argv = ["--note-file", "n", "--", "--not-an-option"]
    sent, stdin = lead_broker._as_bytes(argv, planted.parse_args(argv), tmp_path)
    parsed = planted.parse_args(sent)
    assert stdin == "text" and parsed.note_file == "-" and parsed.rest == ["--not-an-option"]


@pytest.mark.parametrize("argv", [["--one", "a", "--two", "b"], ["--one", "a", "--two", "-"], ["--one", "a", "-"]])
def test_a_command_given_two_inputs_is_refused_saying_there_is_one_stdin(tmp_path, argv):
    """No relayed command has two file arguments today (the walk above); this is what one would get."""
    planted = argparse.ArgumentParser()
    planted.add_argument("--one", action=fields.FileInput)
    planted.add_argument("--two", action=fields.FileInput)
    planted.add_argument("rest", nargs="*")
    with pytest.raises(errors.UsageError, match="only one file argument or - can go with a relayed command"):
        lead_broker._as_bytes(argv, planted.parse_args(argv), tmp_path)


def test_a_request_over_the_bridges_limit_is_refused_saying_so_and_nothing_is_sent(tmp_path, monkeypatch):
    """Non-ASCII text counts as JSON sends it, so a file well under the limit in bytes can be over it as a request."""
    sent: list[str] = []
    monkeypatch.setattr(lead_broker.bridge, "call", lambda op, args, **k: sent.append(op))
    big = tmp_path / "big.md"
    big.write_bytes(("\u00e9" * (bridge.MAX_REQUEST // 6 + 1)).encode())  # 6 bytes as JSON, 2 in the file
    assert big.stat().st_size < bridge.MAX_REQUEST
    parsed = build_parser().parse_args(["checkpoint", *REV, "--note-file", "big.md"])
    parsed.cwd = str(tmp_path)
    with pytest.raises(errors.UsageError, match="nothing was sent") as refused:
        lead_broker.forward(["checkpoint", *REV, "--note-file", "big.md"], parsed)
    assert sent == [] and refused.value.details["reason"] == "relayed_too_large"
    assert refused.value.details["limit"] == bridge.MAX_REQUEST
    big.write_bytes(b"small")
    lead_broker.forward(["checkpoint", *REV, "--note-file", "big.md"], parsed)
    assert sent == ["lead.cli"]


# ----------------------------------------------------------------------------------- the broker's half


def test_while_a_relayed_command_runs_a_path_is_refused_naming_the_dash_and_nothing_is_read(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_bytes(b"content")
    read: list[Path] = []
    real = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: read.append(self) or real(self))
    with util.stdin_only(), pytest.raises(errors.UsageError, match="give - as the file") as refused:
        util.read_text_input(str(target))
    assert read == [] and refused.value.details["reason"] == "relayed_path"


def test_the_refusal_ends_with_the_relayed_command(tmp_path):
    target = tmp_path / "file"
    target.write_bytes(b"content")
    with util.stdin_only():
        with pytest.raises(errors.UsageError):
            util.read_text_input(str(target))
        with util.stdin_only():
            pass
        with pytest.raises(errors.UsageError):  # a nested use leaves the outer one standing
            util.read_text_input(str(target))
    assert util.read_text_input(str(target)) == "content"


def test_a_records_name_check_is_its_schemas_id_pattern():
    assert f"^{stage_intents.INTENT_ID.pattern}$" == schema("stage-intent")["$defs"]["intent_id"]["pattern"]
    assert f"^{disposition_ops.DISPOSITION_ID.pattern}$" == schema("disposition")["properties"]["id"]["pattern"]


def test_stdin_and_no_input_still_work_while_a_relayed_command_runs(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("piped"))
    with util.stdin_only():
        assert util.read_text_input("-") == "piped"
        assert util.read_text_input("") == "" and util.read_text_input(None) == ""
