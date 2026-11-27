"""Every decision the action projection asks for states its owner (register E335; the designer's ruling of 2026-11-11
on E334 and E335, part 2): one owner per decision kind, read from one table of primitive owners
(``owners.PRIMITIVE_OWNERS``), and an owner the table does not state is the operator's.

The owners are then held against what a Lead session can reach (``lead_broker.LEAD_REACHABLE``): a decision the Lead
owns is one it can carry out, and a decision the operator owns is not one it can carry out by itself, except the gaps
register E350 names, which this test pins exactly so that a new one fails and a fixed one is taken off."""

from __future__ import annotations

import argparse
import ast
import inspect

import pytest

from aew import owners as P
from aew.cli.main import build_parser
from aew.engine import operator_decisions as OD
from aew.engine import primitives as PR
from aew.errors import ValidationFailed
from aew.harness import lead_broker
from aew.schemas import schema, validate_def
from aew.surface import projection

# Register E350: commands the Lead can relay that carry out a decision the owner table makes the operator's, with
# nothing of the operator's asked. `verify ingest` is PUBLISH's verifier variant (the same command accepts a Ticket's
# own verification, which is the Lead's). `plan accept` and `integrate publish` are not gaps: a Lead session's call of
# either waits for the operator's confirmation (#618, ``operator_decisions.COMMITS``).
E350_KNOWN_GAPS = frozenset({frozenset({"verify", "ingest"}), frozenset({"verify", "classify"}),
                             frozenset({"work", "reconcile"})})


def _constants(node: ast.expr) -> set[str]:
    """The string values an expression can take: a constant, or either branch of a conditional."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _constants(node.body) | _constants(node.orelse)
    return set()


def _emitted_kinds() -> set[str]:
    """Every decision kind the projection's source writes: a ``"decision"`` key's value, and the first argument of
    ``_decision``, read from the module itself so that a new kind cannot be added without its owner."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(projection))):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "decision" and value is not None:
                    found |= _constants(value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_decision":
            found |= _constants(node.args[0])
    return found


def _commands(primitive: str) -> set[frozenset[str]]:
    """The CLI commands that carry out a primitive: its id's and its commit ops' first two words, where such a
    command exists (``stage.resolve`` commits as ``stage continue`` or ``stage abandon``)."""
    def words(op: str) -> frozenset[str]:
        return frozenset(op.split(".")[:2])
    return {words(op) for op in {primitive, *PR.commit_ops(primitive)}} & _every_command()


def _operator_confirmed(primitive: str) -> set[frozenset[str]]:
    """The commands of a primitive whose commit a Lead session makes only with the operator's confirmation (#618): its
    commit ops include one of ``operator_decisions.COMMITS``."""
    return _commands(primitive) if PR.commit_ops(primitive) & set(OD.COMMITS.values()) else set()


def _every_command() -> set[frozenset[str]]:
    def leaves(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            yield path
            return
        for action in subs:
            for name, child in action.choices.items():
                yield from leaves(child, (*path, name))
    return {frozenset(p) for p in leaves(build_parser(recall_search=True, coordination_reads=True,
                                                     worker_messaging=True))}


def test_every_decision_kind_the_projection_emits_has_its_primitives_in_the_owner_table_input():
    assert _emitted_kinds() == set(projection.DECISION_PRIMITIVES), (
        "a decision kind the projection emits needs its primitives in projection.DECISION_PRIMITIVES")
    for kind, primitives in projection.DECISION_PRIMITIVES.items():
        assert primitives, kind
        for p in primitives:
            assert p in PR.SPECS or p in PR.CONTROL_OP_SPECS, f"{kind}: {p} is no primitive or control op"


def test_one_owner_per_decision_kind_and_its_primitives_agree_on_it():
    for kind, primitives in projection.DECISION_PRIMITIVES.items():
        owners = {P.owner_of(p) for p in primitives}
        assert len(owners) == 1, f"{kind}'s primitives disagree on its owner: {owners}"
        assert projection.decision_owner(kind) == owners.pop()


def test_an_owner_the_table_does_not_state_is_the_operators():
    assert P.owner_of("no.such.primitive") == P.OPERATOR
    assert projection.decision_owner("NO_SUCH_DECISION") == P.OPERATOR
    assert set(P.PRIMITIVE_OWNERS.values()) <= set(P.OWNERS)
    assert all(p in PR.SPECS or p in PR.CONTROL_OP_SPECS for p in P.PRIMITIVE_OWNERS)


def test_the_lead_owns_the_review_and_verification_acceptances_and_the_operator_owns_publication():
    """E335's purpose: the acceptances that are the Lead's by design are taken by the Lead, and publication stays the
    operator's (V1's two operator decisions are the plan and the publish). The Lead's set is pinned whole: an owner
    given to the Lead is an authority boundary, so widening it is a change to this test, never a default."""
    assert projection.decision_owner("ACCEPT_REVIEW_EVIDENCE") == P.LEAD
    assert projection.decision_owner("ACCEPT_VERIFICATION") == P.LEAD
    assert projection.decision_owner("PUBLISH") == P.OPERATOR
    assert projection.decision_owner("PLAN") == P.OPERATOR  # register E351
    assert {k for k in projection.DECISION_PRIMITIVES if projection.decision_owner(k) == P.LEAD} == {
        "ACCEPT_REVIEW_EVIDENCE", "ACCEPT_VERIFICATION", "DISPOSE_ANOMALY", "DISPOSE_CLAIM", "DISPOSE_FINDING",
        "FINISH_PUBLISH", "RESOLVE_STAGE"}


def test_a_decision_the_lead_owns_is_one_a_lead_session_can_carry_out():
    for kind, primitives in projection.DECISION_PRIMITIVES.items():
        if projection.decision_owner(kind) == P.LEAD:
            for p in primitives:
                assert _commands(p) & lead_broker.LEAD_REACHABLE, f"{kind}: the Lead cannot reach {p}"


def test_a_decision_the_operator_owns_is_not_lead_reachable_but_for_e350s_known_gaps():
    """Register E350: these commands are in LEAD_REACHABLE while the owner table makes them the operator's. The set is
    pinned exactly: a new gap fails here, and so does one E350 closes, until it is taken off. A command a Lead session
    carries out only with the operator's confirmation (#618) is no gap, and that set is pinned too: PLAN's `plan
    accept` (register E351) and PUBLISH's `integrate publish`."""
    operators = [p for kind, primitives in projection.DECISION_PRIMITIVES.items()
                 if projection.decision_owner(kind) == P.OPERATOR for p in primitives]
    confirmed = {c for p in operators for c in _operator_confirmed(p)}
    assert confirmed == {frozenset({"plan", "accept"}), frozenset({"integrate", "publish"})}, confirmed
    gaps = {c for p in operators for c in (_commands(p) - _operator_confirmed(p)) & lead_broker.LEAD_REACHABLE}
    assert gaps == E350_KNOWN_GAPS, sorted(map(sorted, gaps ^ E350_KNOWN_GAPS))


def test_the_result_contract_requires_an_owner_and_names_exactly_the_tables_owners():
    decision = schema("surface")["$defs"]["decision"]
    assert "owner" in decision["required"]
    assert tuple(decision["properties"]["owner"]["enum"]) == P.OWNERS
    shown = {"decision": "PUBLISH", "subject": "T-0001", "owner": P.OPERATOR, "evidence": [], "tool": None,
             "arguments": None, "availability": "UNKNOWN", "default": "NONE", "cli_fallback": None}
    validate_def("surface", "decision", shown, source="test")
    for bad in ({k: v for k, v in shown.items() if k != "owner"}, {**shown, "owner": "Lead"},
                {**shown, "owner": "mechanical"}):
        with pytest.raises(ValidationFailed):
            validate_def("surface", "decision", bad, source="test")


def test_whose_decision_the_lead_facing_text_names_is_read_from_the_owner_table():
    """The review of #597, m1: text that says whose decision a call or a stop is derives it from the owner, never
    restates it. PUBLISH is the operator's, so neither catalog calls `integration_publish` the Lead's decision, and the
    steering loop's stop names each decision's own owner (a decision with none reads as the operator's). The quick
    check of #597, m1: the readable head, the text the Lead's model reads first, tells the Lead to decide only a
    decision that is its own; another's is named as theirs, with the call that carries it out."""
    from aew.harness import steering_loop
    from aew.surface import contract, presentation, readable

    publish = P.whose(P.owner_of("integrate.publish"), to_lead=True)
    assert publish == "the operator's"
    standard = contract.tool("integration_publish", switches=contract.ALL_SWITCHES).description
    for text in (standard, presentation.DESCRIPTIONS["integration_publish"]):
        assert f"carries out {publish} publication decision" in text and "your" not in text
    project = {"anomalies": [], "blockers": [], "decisions_required": []}
    for owner, said in ((P.LEAD, "the Lead's"), (P.OPERATOR, "the operator's"), (None, "the operator's")):
        decisions = [{"decision": "PUBLISH", "evidence": [], **({"owner": owner} if owner else {})}]
        unit = {"subject": "T-0001", "actions": [], "blockers": [], "decisions_required": decisions}
        stop = steering_loop.select(project, [unit])
        assert isinstance(stop, steering_loop.Stop) and stop.message == f"T-0001: PUBLISH is {said}", stop
        loose = steering_loop.select({**project, "decisions_required": decisions}, [])
        assert isinstance(loose, steering_loop.Stop) and loose.message.endswith(f"is {said}"), loose
        offered = {**decisions[0], "subject": "T-0001", "availability": "AVAILABLE", "tool": "integration_publish",
                   "arguments": {"work_id": "T-0001"}, "cli_fallback": None}
        result = {"tool": "status", "completed_steps": [], "stopped": None,
                  "projection": {"subject": "T-0001", "actions": [], "decisions_required": [offered]}}
        head = readable.render(result).split("\n\n" + readable.JSON_MARKER)[0].split("\n")
        call = "integration_publish work_id=T-0001"
        assert head[1] == (f"decide PUBLISH on T-0001: {call}" if owner == P.LEAD else
                           f"{said} decision, PUBLISH on T-0001; it is carried out by: {call}"), head
        assert head[2] == f"decision: PUBLISH on T-0001, {said} (AVAILABLE)", head


def _resolve_kinds() -> list[str]:
    """The decision kinds whose call is `resolve`: those whose primitives a `resolve` choice runs (the contract's
    ``RESOLVE_CHOICE_PRIMITIVE``)."""
    from aew.surface import contract

    run = set(contract.RESOLVE_CHOICE_PRIMITIVE.values())
    return [k for k, primitives in projection.DECISION_PRIMITIVES.items() if set(primitives) <= run]


def test_a_resolve_decision_names_as_judgment_inputs_exactly_the_fields_its_arguments_leave_out():
    """Register E388: each `resolve` decision names what its call takes from its owner's judgment, read from the
    contract: the schema's required fields the arguments leave out, the choice offered as the choices that run the
    kind's own primitives (each a pair the contract maps to one of them), the rationale as the schema's own field.
    Whole arguments name none, and the result contract accepts the field."""
    from aew.surface import contract

    resolve = contract.tool("resolve", contract.ALL_SWITCHES).input_schema
    kinds = _resolve_kinds()
    assert {"RESOLVE_STAGE", "DISPOSE_FINDING", "DISPOSE_CLAIM", "DISPOSE_ANOMALY"} <= set(kinds)
    for kind in kinds:
        primitives = projection.DECISION_PRIMITIVES[kind]
        inputs = projection.judgment_inputs(kind, "resolve", {"subject": "X-1"})
        assert inputs is not None and set(inputs) == set(resolve["required"]) - {"subject"}, kind
        options = inputs["choice"]["options"]
        assert options and set(options) == {c for (c, _), p in contract.RESOLVE_CHOICE_PRIMITIVE.items()
                                            if p in primitives}, kind
        assert inputs["rationale"] == resolve["properties"]["rationale"], kind
        assert projection.judgment_inputs(kind, "resolve", {"subject": "X-1", "choice": options[0]}) \
            == {"rationale": inputs["rationale"]}, kind
        assert projection.judgment_inputs(kind, "resolve", {"subject": "X-1", "choice": options[0],
                                                            "rationale": "why"}) is None, kind
        shown = {"decision": kind, "subject": "T-0001", "owner": projection.decision_owner(kind), "evidence": [],
                 "tool": "resolve", "arguments": {"subject": "X-1"}, "availability": "AVAILABLE",
                 "default": "NONE", "cli_fallback": None, "judgment_inputs": inputs}
        validate_def("surface", "decision", shown, source="test")
    assert projection.judgment_inputs("PUBLISH", None, None) is None  # no call to fill
    assert projection.judgment_inputs("RESOLVE_STAGE", "resolve", None) is None


def test_a_decision_whose_call_is_not_resolve_names_no_judgment_inputs_whatever_its_arguments_leave_out():
    """The quick check of #630, m1: only `resolve`'s missing fields are judgments. A PUBLISH whose `integration_publish`
    arguments lack the required `prepared_candidate` (a mechanical fact) names no judgment input, and the decision as
    the projection builds it validates against the result contract."""
    from aew.surface import contract

    publish = contract.tool("integration_publish", contract.ALL_SWITCHES).input_schema
    arguments = {"work_id": "T-0001"}
    assert "prepared_candidate" in set(publish["required"]) - set(arguments)
    assert projection.judgment_inputs("PUBLISH", "integration_publish", arguments) is None
    shown = projection._decision("PUBLISH", "T-0001", tool="integration_publish", arguments=arguments,
                                 cli_fallback=None, availability="AVAILABLE")
    assert "judgment_inputs" not in shown
    validate_def("surface", "decision", shown, source="test")
