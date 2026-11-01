"""Recovery commands in cancellation-related refusals remain copyable."""

from __future__ import annotations

from contextlib import contextmanager
from io import StringIO

import pytest

from aew.cli import credentials, fields
from aew.cli.main import build_parser
from aew.engine.evidence_ops import EvidenceCommands
from aew.engine.hierarchy_ops import Hierarchy
from aew.errors import IllegalTransition, UsageError


def test_active_implementer_refusal_has_complete_cancel_command() -> None:
    commands = object.__new__(EvidenceCommands)
    invocation = "INV-0032"
    state = {
        "work": {"T-0007": {"state": "RUNNING", "implementer_invocation": invocation}},
        "invocations": {invocation: {"status": "active"}},
    }

    blocker = commands._g_slot(state, "T-0007", {"scope": "ticket"})

    assert blocker is not None
    assert blocker.message == (
        "INV-0032 is still active; cancel it with:\n\n```sh\n"
        "aew invoke cancel INV-0032 "
        "--expect-rev <revision from aew status> --fields - <<'EOF'\n"
        "reason: 'why this active invocation must end'\n"
        "EOF\n```"
    )
    assert "--expect-rev <revision from aew status>" in blocker.message
    assert "--fields -" in blocker.message
    assert "reason:" in blocker.message


def test_invoke_cancel_parser_keeps_required_reason_and_revision() -> None:
    # ``--fields`` is expanded by the client before argparse; the resulting reason
    # still reaches the command's required --reason option.
    args = build_parser().parse_args(
        ["invoke", "cancel", "INV-0032", "--expect-rev", "7", "--reason", "stop"]
    )

    assert args.invocation == "INV-0032"
    assert args.expect_rev == 7
    assert args.reason == "stop"


def test_advertised_yaml_expands_to_invoke_cancel_parser(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("reason: why\n"))
    parser = build_parser()
    argv = fields.expand(
        ["invoke", "cancel", "INV-0032", "--expect-rev", "7", "--fields", "-"], parser
    )
    args = parser.parse_args(argv)
    assert args.invocation == "INV-0032"
    assert args.expect_rev == 7
    assert args.reason == "why"


def test_ticket_cancel_refusal_has_complete_transition_command() -> None:
    class Units:
        @staticmethod
        def unit(state, work_id):
            return state["work"][work_id]

    class Kernel:
        @staticmethod
        @contextmanager
        def lead_txn(token, expect_rev, operation, reason):
            yield type("Context", (), {"state": {"work": {"T-0007": {"kind": "ticket", "state": "RUNNING"}}}})()

    hierarchy = object.__new__(Hierarchy)
    hierarchy.k = Kernel()
    hierarchy.units = Units()
    with pytest.raises(IllegalTransition) as raised:
        hierarchy.work_cancel(token="lead", expect_rev=7, work_id="T-0007", reason="stop")

    message = str(raised.value)
    assert message == (
        "cancel a Ticket with:\n\n```sh\n"
        "aew work transition T-0007 --to CANCELLED "
        "--expect-rev <revision from aew status> --fields - <<'EOF'\n"
        "reason: 'why this Ticket must end'\n"
        "EOF\n```"
    )


def test_advertised_yaml_expands_to_work_transition_parser(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("reason: why\n"))
    parser = build_parser()
    argv = fields.expand(
        ["work", "transition", "T-0007", "--to", "CANCELLED", "--expect-rev", "7", "--fields", "-"],
        parser,
    )
    args = parser.parse_args(argv)
    assert args.work_id == "T-0007"
    assert args.to == "CANCELLED"
    assert args.expect_rev == 7
    assert args.reason == "why"


def test_terminal_loss_refusal_has_cancel_recovery(monkeypatch) -> None:
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)

    with pytest.raises(UsageError) as raised:
        credentials.deliver({"invocation_token": "secret"}, object())

    message = str(raised.value)
    assert "aew invoke cancel <invocation> --expect-rev <revision from aew status> --fields -" in message
    assert "reason: 'why this invocation must end'" in message
    assert "\nEOF\n```" in message
    assert "aew lead handoff cancel --expect-rev <revision from aew status>" in message


def test_terminal_loss_takeover_guidance_expands_to_cli_parser(monkeypatch) -> None:
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)

    with pytest.raises(UsageError) as raised:
        credentials.deliver({"invocation_token": "secret"}, object())

    message = str(raised.value)
    assert "operator-authorized takeover at an interactive terminal" in message
    assert "aew lead takeover --expect-rev <revision from aew status> --fields -" in message
    start = message.index("aew lead takeover")
    command = message[start:].split("\n```", 1)[0].splitlines()[0]
    command = command.replace("<revision from aew status>", "7").split()[1:]
    command = command[:command.index("<<'EOF'")]
    monkeypatch.setattr("sys.stdin", StringIO("reason: terminal-loss recovery\n"))
    parser = build_parser()
    argv = fields.expand(command, parser)
    args = parser.parse_args(argv)
    assert args.lead_cmd == "takeover"
    assert args.expect_rev == 7
    assert args.reason == "terminal-loss recovery"
