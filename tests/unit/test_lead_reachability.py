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
    # The parser with every switched command registered (register F21's `history search`), so none escapes the walk.
    return {frozenset(path) for path, p in leaves(build_parser(recall_search=True))
            if any(a.dest == "token" for a in p._actions)}


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


def test_an_operator_confirmed_command_is_refused_with_its_own_reason_and_validate_is_reachable():
    """M4-D5: resetting the validation breaker is the operator's, confirmed at their terminal; validating a candidate
    is the Lead's."""
    refusal = lead_broker.refuses_locally(_ns("integrate", "breaker", "reset", "--reason", "fixed", "--token", "x",
                                              "--expect-rev", "1"))
    assert refusal and "confirmed by the operator" in refusal and "credential" not in refusal
    assert refusal.startswith("`aew integrate breaker reset`"), refusal  # as typed, never sorted (re-review R4)
    offer = lead_broker.refuses_locally(_ns("lead", "handoff", "offer", "--expect-rev", "1"))
    assert offer and offer.startswith("`aew lead handoff offer`"), offer
    assert lead_broker.refuses_locally(_ns("integrate", "validate", "T-0001", "--token", "x",
                                           "--expect-rev", "1")) is None


@pytest.mark.parametrize("argv", [
    ("authority", "accept", "C-0001", "--class", "decisions", "--decided-by", "operator", "--expect-rev", "1"),
    ("authority", "reject", "C-0001", "--expect-rev", "1"),
    ("manifest", "adopt", "--reason", "reviewed", "--expect-rev", "1"),
    ("migrate", "--expect-rev", "1"),
])
def test_the_operators_decisions_are_refused_in_a_lead_session(argv):
    """Operator, 2026-10-06: a Lead session may not accept authority (or record the operator's sign-off), approve an
    edit to project.yaml it could have made itself, or migrate the control state; the broker refuses them too."""
    refusal = lead_broker.refuses_locally(_ns(*argv))
    name = " ".join(a for a in argv if not a.startswith("-") and a not in {"C-0001", "decisions", "operator",
                                                                           "reviewed", "1"})
    assert refusal and refusal.startswith(f"`aew {name}` is the operator's decision"), refusal
    assert "credential" not in refusal
    with pytest.raises(errors.PermissionDenied):
        lead_broker.run_cli(object(), "token", list(argv), ".", "", channel="lead_broker")


def operator_decided_commands() -> list[str]:
    """The operator's decisions as typed, in the parser's order (`authority accept`, `manifest adopt`, `migrate`)."""
    return sorted(" ".join(path) for path, _ in leaves(build_parser())
                  if any(p == frozenset(path) for p in lead_broker.OPERATOR_DECIDED))


def assert_never_the_leads(text: str) -> None:
    """Every passage that names an operator-decided command also says the operator runs it (PR #103 review, F1)."""
    for passage in text.replace("\n- ", "\n\n").split("\n\n"):
        for command in operator_decided_commands():
            if f"aew {command}" in passage:
                assert "operator" in passage, (command, passage)


def test_the_lead_guide_never_tells_the_lead_to_run_an_operator_decision():
    from aew.engine import guide
    from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES

    assert len(operator_decided_commands()) == len(lead_broker.OPERATOR_DECIDED)
    text = guide.render(DEFAULT_GATES, DEFAULT_CHECKS)
    assert "aew authority accept" in text
    assert_never_the_leads(text)


def test_a_lead_session_never_records_a_decision_as_the_operators():
    """`work staff` stays the Lead's, but `--by operator` records the operator's selection: only the operator, at their
    own terminal. The broker refuses it before anything runs."""
    argv = ("work", "staff", "T-0001", "--review", "security_reviewer", "--by", "operator", "--pin",
            "--expect-rev", "1")
    refusal = lead_broker.refuses_locally(_ns(*argv))
    assert refusal and refusal.startswith("`aew work staff` with `--by operator`"), refusal
    with pytest.raises(errors.PermissionDenied):
        lead_broker.run_cli(object(), "token", list(argv), ".", "", channel="lead_broker")
    assert lead_broker.refuses_locally(_ns(*(a for a in argv if a not in {"--by", "operator"}))) is None
    refusal = lead_broker.refuses_locally(_ns("authority", "accept", "C-0001", "--class", "decisions",
                                              "--decided-by", "operator", "--expect-rev", "1"))
    assert refusal and "operator" in refusal  # authority accept is the operator's in any form


@pytest.mark.parametrize("argv", [
    ("gate", "waive", "T-0001", "--gate", "review", "--reason", "x", "--expect-rev", "1"),
    ("history", "load", "R-0001", "--into", "T-0001", "--reason", "x", "--expect-rev", "1"),
    ("history", "audit", "--expect-rev", "1"),
])
def test_waivers_history_loads_and_audits_stay_the_leads(argv):
    assert lead_broker.refuses_locally(_ns(*argv)) is None


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


def _messages(tree):
    """Every string the program can show (literals and f-strings), skipping docstrings; implicitly concatenated literals
    are one constant, so a sentence split across lines is read whole."""
    import ast

    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}  # read whole, below
    skip = docstrings | parts  # once per file: rebuilding it per node made this test quadratic (CI fast lane, PR #110)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node.lineno, node.value
        elif isinstance(node, ast.JoinedStr):
            yield node.lineno, "".join(v.value for v in node.values if isinstance(v, ast.Constant))


# Machine-readable fields that hold a command and nothing else; the message beside each names the operator.
BARE_COMMAND_FIELDS = {"aew migrate --expect-rev N"}  # MigrationRequired's next_action (base.py)


def test_no_message_in_aew_hands_an_operator_decision_to_whoever_reads_it():
    """PR #103 re-review, R1: a message that names an operator decision says the operator makes it, wherever it is
    shown (refusals the Lead reads, packs, the dashboard, init's files)."""
    import ast
    from pathlib import Path

    import aew

    stale = []
    commands = operator_decided_commands()  # builds the whole CLI parser: once, never per message
    for path in Path(aew.__file__).parent.rglob("*.py"):
        for line, text in _messages(ast.parse(path.read_text(encoding="utf-8"))):
            for command in commands:
                if f"aew {command}" in text and "operator" not in text and text not in BARE_COMMAND_FIELDS:
                    stale.append(f"{path.name}:{line}: {text[:100]}")
    assert not stale, stale
