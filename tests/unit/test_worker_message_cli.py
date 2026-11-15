"""The worker's messaging parser is presentation only; the bridge's closed operation table owns the boundary."""

from __future__ import annotations

import argparse

import pytest

from aew.cli.main import build_parser
from aew.errors import PermissionDenied, UsageError
from aew.harness import bridge


def commands(parser):
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    message = subs.choices.get("message")
    if message is None:
        return set()
    return set(next(a for a in message._actions if isinstance(a, argparse._SubParsersAction)).choices)


def test_inside_a_run_the_parser_offers_only_reply_read_and_wait():
    assert commands(build_parser(worker_messaging=True)) == {"reply", "read", "wait"}
    assert commands(build_parser(coordination_reads=True)) == {"thread", "list", "unseen"}
    assert commands(build_parser()) == set()
    assert commands(build_parser(coordination_reads=True, worker_messaging=True)) == {
        "reply", "read", "wait", "thread", "list", "unseen"}  # classification walks see both sets


def test_forging_presentation_does_not_add_an_operation_to_an_off_bridge():
    args = build_parser(worker_messaging=True).parse_args(["message", "read"])
    assert args.message_cmd == "read"
    with pytest.raises(PermissionDenied):
        bridge.validate_request({"op": "message.read", "args": {}}, bridge.OPERATIONS)


@pytest.mark.parametrize("field", ["to", "invocation", "run", "credential", "token"])
@pytest.mark.parametrize("operation", ["message.reply", "message.read", "message.wait"])
def test_a_worker_message_cannot_choose_a_sibling_or_a_credential(field, operation):
    request = {k: [] if v is list else "" for k, v in bridge.MESSAGE_OPERATIONS[operation].items()}
    request[field] = "forged"
    with pytest.raises(UsageError, match="exactly"):
        bridge.validate_request({"op": operation, "args": request}, bridge.MESSAGE_OPERATIONS)
