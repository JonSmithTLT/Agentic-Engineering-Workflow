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
    # The parser with every switched command registered (register F21's `history search`, F9-A's `message`), so none
    # escapes the walk.
    return {frozenset(path) for path, p in leaves(build_parser(recall_search=True, coordination_reads=True))
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


def every_command() -> dict[frozenset[str], argparse.ArgumentParser]:
    return {frozenset(path): p for path, p in leaves(build_parser(recall_search=True, coordination_reads=True))}


def test_every_command_is_classified_once_for_the_contained_lead():
    """STG-05 CS-4 addendum 4, ruling 1, condition 1: every command is Lead-reachable, relayed for the contained Lead
    (RELAYED_READS), operator-only, a typed-surface transport, kept out of a Lead session (custody_ops.LEAD_KEPT_OUT,
    its one owner: #286 review F1) or, with why, not relayed (CONTAINED_LOCAL), and in exactly one of them. A relayed
    read takes no Lead credential, and each option it may carry is one of its own."""
    from aew.engine import custody_ops

    commands = every_command()
    classes = {"LEAD_REACHABLE": set(lead_broker.LEAD_REACHABLE), "RELAYED_READS": set(lead_broker.RELAYED_READS),
               "OPERATOR_ONLY": set(lead_broker.OPERATOR_ONLY), "NOT_RELAYED": set(lead_broker.NOT_RELAYED),
               "LEAD_KEPT_OUT": {frozenset(words) for words in custody_ops.LEAD_KEPT_OUT},
               "CONTAINED_LOCAL": set(lead_broker.CONTAINED_LOCAL)}
    placed = {path: [name for name, members in classes.items() if path in members] for path in commands}
    assert {" ".join(sorted(p)): c for p, c in placed.items() if len(c) != 1} == {}
    named = set().union(*classes.values())
    assert named <= set(commands), f"no such commands: {sorted(map(sorted, named - set(commands)))}"
    for path, options in lead_broker.RELAYED_READS.items():
        dests = {a.dest for a in commands[path]._actions}
        assert "token" not in dests and options <= dests, (sorted(path), sorted(options - dests))


def test_the_surface_map_marks_exactly_the_relayed_reads_and_each_is_a_read():
    """Condition 1 and 8: each relayed command's surface-map entry says it is relayed for the contained Lead, and
    declares it mutates nothing (condition 2's registry half; the store's half is the integration test's)."""
    from pathlib import Path

    from aew.util import load_yaml

    path = Path(__file__).resolve().parents[2] / "docs" / "implementation" / "surface-map.yaml"
    entries = load_yaml(path.read_text(encoding="utf-8"))["commands"]
    flagged = {frozenset(e["name"].split()): e for e in entries if e.get("relayed") == "contained-lead"}
    assert set(flagged) == set(lead_broker.RELAYED_READS)
    assert {e["name"]: e["mutates"] for e in flagged.values() if e["mutates"] != "no"} == {}


@pytest.mark.parametrize(("argv", "reason"), [
    (["history", "compact"], "not_relayed"),
    (["work", "list"], "not_relayed"),  # a read the sandbox runs itself
    (["plan", "accept", "T-0001", "--revision", "1", "--expect-rev", "3"], "not_relayed"),  # a Lead command
    (["--print-credential", "status"], "relayed_option"),
    (["status", "--json"], "relayed_option"),  # with `json` taken from status's options below
    (["map", "show", "--root", "/; touch x"], "relayed_value"),  # a stored map's sha256, never a path or a shell
    (["map", "diff", "--root", "../maps", "--commit", "HEAD"], "relayed_value"),
    (["map", "show", "--commit=--output=/tmp/x"], "relayed_value"),  # never an option for git
    (["harness", "wait", "../../../etc", "--timeout", "0"], "relayed_value"),  # a run id, never a path
    (["harness", "status", "INV-0001/.."], "relayed_value"),
])
def test_a_read_outside_the_relayed_set_or_with_another_option_or_value_is_refused_before_anything_runs(
        argv, reason, monkeypatch):
    """Conditions 3 and 5: the broker parses the request against the command's own parser. A command outside the set
    is refused, naming the operator's route; a relayed one with an option it may not carry, or a value that could name
    a directory, an output path or an option, is refused. None starts a process (the engine is never reached)."""
    monkeypatch.setitem(lead_broker.RELAYED_READS, frozenset({"status"}), frozenset({"work_id"}))
    with pytest.raises(errors.PermissionDenied) as refused:
        lead_broker.run_read(object(), argv, ".")
    assert refused.value.details["reason"] == reason, refused.value.details
    if reason == "not_relayed":
        assert "is not relayed to a contained Lead: the operator runs it in their own shell" in refused.value.message


@pytest.mark.parametrize("timeout", ["inf", "nan", "1e7"])
def test_a_relayed_wait_the_host_cannot_wait_out_is_refused_saying_what_to_pass(timeout):
    """The review of #283 at b2dc3035, m1: a relayed `harness wait` whose --timeout is not finite, or longer than the
    host can wait (``RELAYED_WAIT_MAX_S``), is refused before anything runs, naming the bound."""
    with pytest.raises(errors.PermissionDenied) as refused:
        lead_broker.run_read(object(), ["harness", "wait", "R-INV-0001-1", "--timeout", timeout], ".")
    assert refused.value.details["reason"] == "relayed_value", refused.value.details
    assert f"pass a finite number of seconds, at most {lead_broker.RELAYED_WAIT_MAX_S}" in refused.value.message


def test_a_relayed_wait_at_the_stated_bound_passes_it_and_one_second_more_is_refused(tmp_path):
    """Quick check of #283 at c307481a, m3: the bound a refusal states is whole seconds, and a request may pass it. At
    the bound the wait passes the check and goes on to the next, the project check, which finds no project in an empty
    directory (so nothing runs); one second above it is refused, naming the bound."""
    bound = lead_broker.RELAYED_WAIT_MAX_S
    assert isinstance(bound, int)
    with pytest.raises(errors.ProjectNotFound):
        lead_broker.run_read(object(), ["harness", "wait", "R-INV-0001-1", "--timeout", str(bound)], str(tmp_path))
    with pytest.raises(errors.PermissionDenied) as refused:
        lead_broker.run_read(object(), ["harness", "wait", "R-INV-0001-1", "--timeout", str(bound + 1)], str(tmp_path))
    assert refused.value.details["reason"] == "relayed_value", refused.value.details
    assert f"refuses --timeout {float(bound + 1)}: pass a finite number of seconds, at most {bound}" \
        in refused.value.message


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


def test_every_forbidden_to_lead_command_is_refused_on_both_lead_channels_in_its_own_text():
    """#286 review F1: every surface-map command whose lead_disposition is forbidden-to-lead, run by its
    keep_out_probe through `run_cli` on each of a Lead session's channels (the relay of `lead.cli` and the typed
    surface's `cli` escape), is refused as a Lead session's, in the one owner's text (custody_ops.LEAD_KEPT_OUT),
    which names the way to ask; never "run this one directly". The rows and LEAD_KEPT_OUT are the same commands, so a
    row added without its text, or a text without its row, fails here. Limits: only refusals made before the engine
    is reached; the direct path's refusal is test_surface_map's check_keep_out."""
    from pathlib import Path

    from aew.engine import custody_ops
    from aew.util import load_yaml

    reg = load_yaml((Path(__file__).resolve().parents[2] / "docs" / "implementation" / "surface-map.yaml")
                    .read_text(encoding="utf-8"))
    rows = [e for e in reg["commands"] if e.get("lead_disposition") == "forbidden-to-lead"]
    assert {e["name"] for e in rows} >= {"capability check", "g3 request"}  # control: the rows are found
    for e in rows:
        argv = [str(a) for a in e["keep_out_probe"]]
        text = custody_ops.kept_out_refusal(frozenset(e["name"].split()))
        assert text and "ask the operator to run" in text, e["name"]
        for channel in lead_broker.INGRESS_CHANNEL.values():
            with pytest.raises(errors.PermissionDenied) as exc:
                lead_broker.run_cli(object(), "token", argv, ".", "", channel=channel)
            assert exc.value.message == text and exc.value.details["reason"] == custody_ops.LEAD_SESSION, (
                e["name"], channel, exc.value.message)
    assert {frozenset(e["name"].split()) for e in rows} == {frozenset(w) for w in custody_ops.LEAD_KEPT_OUT}
