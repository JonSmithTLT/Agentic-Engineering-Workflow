"""Every decision the action projection asks for states its owner (register E335; the designer's ruling of 2026-11-11
on E334 and E335, part 2): one owner per decision kind, read from one table of primitive owners
(``primitives.PRIMITIVE_OWNERS``), and an owner the table does not state is the operator's.

The owners are then held against what a Lead session can reach (``lead_broker.LEAD_REACHABLE``): a decision the Lead
owns is one it can carry out, and a decision the operator owns is not one it can carry out by itself, except the gaps
it names (register E350's, and those of the owners awaiting the designer, E335's note of 2026-11-26), which this test
pins exactly so that a new one fails and a fixed one is taken off."""

from __future__ import annotations

import argparse
import ast
import inspect

import pytest

from aew.cli.main import build_parser
from aew.engine import primitives as P
from aew.errors import ValidationFailed
from aew.harness import lead_broker
from aew.schemas import schema, validate_def
from aew.surface import projection

# Register E350: commands the Lead can relay that carry out a decision the owner table makes the operator's. For
# `integrate publish` that is W09's G3 approval, not built yet; `verify ingest` is PUBLISH's verifier variant (the same
# command accepts a Ticket's own verification, which is the Lead's).
E350_KNOWN_GAPS = frozenset({frozenset({"integrate", "publish"}), frozenset({"verify", "ingest"}),
                             frozenset({"verify", "classify"}), frozenset({"work", "reconcile"})})
# The commands of the three owners left unstated, so the operator's, until the designer confirms them (the operator,
# 2026-11-26: "might as well do the safe default for now"; E335's note): dispositions, stage resolution and a publish's
# finish. Named here as gaps of their own, not folded into E350's four.
AWAITING_DESIGNER_GAPS = frozenset({frozenset({"work", "dispose"}), frozenset({"stage", "continue"}),
                                    frozenset({"stage", "abandon"}), frozenset({"integrate", "reconcile"})})


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
    return {words(op) for op in {primitive, *P.commit_ops(primitive)}} & _every_command()


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
            assert p in P.SPECS or p in P.CONTROL_OP_SPECS, f"{kind}: {p} is no primitive or control op"


def test_one_owner_per_decision_kind_and_its_primitives_agree_on_it():
    for kind, primitives in projection.DECISION_PRIMITIVES.items():
        owners = {P.owner_of(p) for p in primitives}
        assert len(owners) == 1, f"{kind}'s primitives disagree on its owner: {owners}"
        assert projection.decision_owner(kind) == owners.pop()


def test_an_owner_the_table_does_not_state_is_the_operators():
    assert P.owner_of("no.such.primitive") == P.OPERATOR
    assert projection.decision_owner("NO_SUCH_DECISION") == P.OPERATOR
    assert set(P.PRIMITIVE_OWNERS.values()) <= set(P.OWNERS)
    assert all(p in P.SPECS or p in P.CONTROL_OP_SPECS for p in P.PRIMITIVE_OWNERS)


def test_the_lead_owns_the_review_and_verification_acceptances_and_the_operator_owns_publication():
    """E335's purpose: the acceptances that are the Lead's by design are taken by the Lead, and publication stays the
    operator's (V1's two operator decisions are the plan and the publish). The Lead's set is pinned whole: an owner
    given to the Lead is an authority boundary, so widening it is a change to this test, never a default."""
    assert projection.decision_owner("ACCEPT_REVIEW_EVIDENCE") == P.LEAD
    assert projection.decision_owner("ACCEPT_VERIFICATION") == P.LEAD
    assert projection.decision_owner("PUBLISH") == P.OPERATOR
    assert {k for k in projection.DECISION_PRIMITIVES if projection.decision_owner(k) == P.LEAD} == {
        "ACCEPT_REVIEW_EVIDENCE", "ACCEPT_VERIFICATION"}
    for kind in ("DISPOSE_ANOMALY", "DISPOSE_CLAIM", "DISPOSE_FINDING", "RESOLVE_STAGE", "FINISH_PUBLISH"):
        assert projection.decision_owner(kind) == P.OPERATOR, kind  # awaiting the designer (E335's note)


def test_a_decision_the_lead_owns_is_one_a_lead_session_can_carry_out():
    for kind, primitives in projection.DECISION_PRIMITIVES.items():
        if projection.decision_owner(kind) == P.LEAD:
            for p in primitives:
                assert _commands(p) & lead_broker.LEAD_REACHABLE, f"{kind}: the Lead cannot reach {p}"


def test_a_decision_the_operator_owns_is_not_lead_reachable_but_for_the_named_known_gaps():
    """These commands are in LEAD_REACHABLE while the owner table makes them the operator's: register E350's four, and
    the four of the owners awaiting the designer. The set is pinned exactly: a new gap fails here, and so does one that
    closes, until it is taken off."""
    gaps = {c for kind, primitives in projection.DECISION_PRIMITIVES.items()
            if projection.decision_owner(kind) == P.OPERATOR
            for p in primitives for c in _commands(p) & lead_broker.LEAD_REACHABLE}
    known = E350_KNOWN_GAPS | AWAITING_DESIGNER_GAPS
    assert gaps == known, sorted(map(sorted, gaps ^ known))


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
