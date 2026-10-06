"""What a Lead session may reach, fail closed (F15.1 slice B; A1 §1), and the bridge's cooperative operations.

Every Lead-authenticated command is classified Lead-reachable, operator-only or a typed-surface transport; anything
unclassified is refused by the one check the `aew` client and the broker both apply. No typed tool reaches an
operator-only command. A cooperative bridge operation never holds up another request; every other operation is still
serialized."""

from __future__ import annotations

import argparse
import threading
import time

import pytest

from aew import errors
from aew.cli.main import build_parser
from aew.harness import bridge, lead_broker
from aew.surface import contract


def leaves(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        yield path, parser
        return
    for action in subs:
        for name, child in action.choices.items():
            yield from leaves(child, (*path, name))


def lead_authenticated() -> set[frozenset[str]]:
    return {frozenset(path) for path, p in leaves(build_parser()) if any(a.dest == "token" for a in p._actions)}


def test_every_lead_authenticated_command_is_classified_exactly_once():
    commands = lead_authenticated()
    operator = {p for p in lead_broker.OPERATOR_ONLY if p in commands}
    transports = set(lead_broker.NOT_RELAYED) & commands
    reachable = set(lead_broker.LEAD_REACHABLE)
    assert not reachable & operator and not reachable & transports and not operator & transports
    unclassified = commands - reachable - operator - transports
    assert not unclassified, f"classify these (LEAD_REACHABLE or OPERATOR_ONLY): {sorted(map(sorted, unclassified))}"
    assert reachable <= commands, f"no such commands: {sorted(map(sorted, reachable - commands))}"


def _ns(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


def test_an_unclassified_lead_command_is_refused_until_someone_classifies_it(monkeypatch):
    ns = _ns("plan", "accept", "T-0001", "--revision", "1", "--expect-rev", "3")
    assert lead_broker.refuses_locally(ns) is None
    monkeypatch.setattr(lead_broker, "LEAD_REACHABLE", lead_broker.LEAD_REACHABLE - {frozenset({"plan", "accept"})})
    refusal = lead_broker.refuses_locally(ns)
    assert refusal and "not classified" in refusal
    with pytest.raises(errors.PermissionDenied):  # the broker applies the same check before anything runs
        lead_broker.run_cli(object(), "token", ["plan", "accept", "T-0001", "--revision", "1", "--expect-rev", "3"],
                            ".", "", channel="lead_broker")


def test_operator_only_commands_are_refused_and_read_only_commands_are_not_relayed():
    for argv in (("lead", "release", "--expect-rev", "1"), ("lead", "handoff", "offer", "--expect-rev", "1"),
                 ("lead", "acquire", "--expect-rev", "1"), ("lead", "takeover", "--expect-rev", "1", "--reason", "x"),
                 ("dashboard", "open")):
        assert lead_broker.refuses_locally(_ns(*argv)), argv
    assert lead_broker.refuses_locally(_ns("status")) is None  # read-only: runs locally, holds no authority


def test_the_typed_surfaces_transports_are_never_relayed(monkeypatch):
    monkeypatch.setenv(lead_broker.ENV_ENDPOINT, r"\\.\pipe\nowhere")
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    ns = _ns("lead", "tool", "status")
    assert lead_broker.refuses_locally(ns) is None and not lead_broker.routes(ns)
    with pytest.raises(errors.PermissionDenied, match="transport"):
        lead_broker.run_cli(object(), "token", ["lead", "tool", "status"], ".", "", channel="lead_broker")


def test_no_typed_tool_reaches_an_operator_only_command():
    operator = {" ".join(sorted(p)) for p in lead_broker.OPERATOR_ONLY}
    for t in contract.TOOLS.values():
        for primitive in t.expands_to:
            assert " ".join(sorted(primitive.replace(".", " ").split())) not in operator, (t.name, primitive)
    assert "cli" not in {t.name for t in contract.exposed("normal")}


# ---------------------------------------------------------------------------------------------- the bridge


def _serve(cooperative: frozenset[str]):
    ops: bridge.Operations = {"slow": {}, "fast": {}}
    server: bridge.BridgeServer

    def handler(op, _args):
        if op == "slow":
            if op in cooperative:
                time.sleep(1.5)  # a cooperative wait: outside the serialization
                with server.serialized():
                    return "slow"
            time.sleep(1.5)
            return "slow"
        return "fast"

    server = bridge.BridgeServer(handler, ops, cooperative)
    server.start()
    return server


@pytest.mark.parametrize(("cooperative", "blocked"), [(frozenset({"slow"}), False), (frozenset(), True)])
def test_only_a_cooperative_operation_lets_another_request_through(cooperative, blocked):
    server = _serve(cooperative)
    try:
        def call(op):
            return bridge.call(op, {}, endpoint=server.address, key=server.key_hex)

        thread = threading.Thread(target=call, args=("slow",))
        thread.start()
        time.sleep(0.3)
        started = time.monotonic()
        assert call("fast") == "fast"
        waited = time.monotonic() - started
        thread.join(10)
        assert (waited > 0.8) is blocked, waited
    finally:
        server.close()


def test_a_cooperative_operation_must_be_an_operation():
    with pytest.raises(ValueError):
        bridge.BridgeServer(lambda *_: None, {"a": {}}, frozenset({"b"}))
