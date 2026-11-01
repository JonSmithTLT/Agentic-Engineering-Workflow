"""Recovery commands in cancellation-related refusals remain copyable."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from io import StringIO

import printed_commands as P
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


# A synthetic credential: never a real one (the reviewers' rule); the refusal must never print it.
SYNTHETIC = "synthetic-credential-value-0123456789"


@pytest.mark.parametrize(
    ("result", "args", "command", "check"),
    [
        pytest.param({"token": SYNTHETIC}, argparse.Namespace(), ["lead", "takeover"],
                     lambda a: a.reason, id="lead-credential"),
        pytest.param({"offer": SYNTHETIC}, argparse.Namespace(), ["lead", "handoff", "cancel"],
                     lambda a: True, id="handoff-offer"),
        pytest.param({"invocation": "INV-0032", "invocation_token": SYNTHETIC}, argparse.Namespace(),
                     ["invoke", "cancel"], lambda a: a.invocation == "INV-0032" and a.reason, id="invocation"),
        pytest.param({"session_url": f"http://127.0.0.1:4280/#{SYNTHETIC}"}, argparse.Namespace(dashboard_cmd="serve"),
                     ["dashboard", "serve"], lambda a: True, id="dashboard-session-url"),
    ],
)
def test_a_lost_terminal_names_the_recovery_for_the_credential_lost(
    monkeypatch, result, args, command, check,
) -> None:
    """#311 review F1: the recovery is the lost credential's own (a Lead credential: takeover; an offer: cancel the
    handoff; an invocation credential: cancel that invocation, by its id; a session URL: run the dashboard command
    again), named by kind and never by value, and its command parses as printed."""
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)
    with pytest.raises(UsageError) as raised:
        credentials.deliver(result, args)

    message = str(raised.value)
    assert SYNTHETIC not in message and SYNTHETIC not in repr(raised.value.to_dict())
    assert raised.value.details["lost"] == [k for k in credentials.KEYS if k in result]
    [(printed, fenced)] = P.commands(message)
    [parsed] = P.parse(printed, fenced=fenced)
    words = [parsed.command, *(getattr(parsed, f"{w}_cmd") for w in command[:-1])]
    assert words == command and check(parsed)
