"""ITEMS 55: one predicate says whether a gate name can be satisfied, and it agrees with both evaluators (designer
decision 1; addenda 1 and 2).

The agreement runs in both directions over every kind and prefix: the evaluator is given every piece of evidence the
catalogue can produce (a review and a verification from each card, a pass of each configured check, a self-review),
and a gate reads CURRENT exactly when ``gates.unsatisfiable`` says it can be satisfied. "Can be satisfied" is not "will
pass": a card that exists may never be launched, so only the names that can never pass are refused."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from aew.engine import gates as G
from aew.engine import hierarchy as H

FP, PLAN = "fp-1", 1
CATALOGUE = G.Catalogue(cards=frozenset({"security_reviewer", "code_reviewer", "verifier"}),
                        specialties={"security": ("security_reviewer",)},
                        checks={"unit": "sha-unit", "guardrails": "sha-guard"}, local_checks=("unit",))


def _evidence(catalogue: G.Catalogue) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Every piece of evidence ``catalogue`` can produce, on the current snapshot and plan, and the invocations."""
    invocations: dict[str, dict[str, Any]] = {"INV-impl": {"role": "implementer"}}
    out: list[dict[str, Any]] = []

    def ev(eid: str, inv: str, card: str | None, **body: Any) -> None:
        out.append({"id": eid, "_sha256": f"sha-{eid}", "result": "pass",
                    "producer": {"invocation": inv, "role_card": {"id": card} if card else None},
                    "evaluated_snapshot": {"relevant_inputs_fingerprint": FP}, "plan_revision": {"revision": PLAN},
                    **body})

    for card in sorted(catalogue.cards):
        specialty = next((s for s, cards in catalogue.specialties.items() if card in cards), None)
        invocations[f"INV-r-{card}"] = {"role": "reviewer"}
        invocations[f"INV-v-{card}"] = {"role": "verifier"}
        for s in {specialty, None}:
            ev(f"E-r-{card}-{s}", f"INV-r-{card}", card, kind="review",
               review={"independence": "R1", "disposition": "pass", "specialty": s})
        ev(f"E-v-{card}", f"INV-v-{card}", card, kind="verification",
           verification={"scope": "ticket", "claims": [{"type": "goal_backwards", "result": "pass"},
                                                       {"type": "contract", "result": "pass"}]})
    for check_id, sha in sorted(catalogue.checks.items()):
        ev(f"E-c-{check_id}", "INV-impl", None, kind="check_result",
           check={"check_id": check_id, "definition_sha256": sha})
    ev("E-impl", "INV-impl", None, kind="implementation_report",
       implementation={"self_review": {"completed": True}})
    return invocations, out


ENGINE = Path(G.__file__).parent
# Where each evidence unit's evaluator is given its fixed gates' statuses (``special``): the production callers.
SPECIAL_TABLES = {G.NON_MUTATING: ("nonmutating_ops.py", "evidence_gate_context"),
                  G.PARENT: ("hierarchy_ops.py", "_parent_gate_context")}


def special_keys(utype: str) -> list[str]:
    """The keys of the ``special`` table ``utype``'s production caller builds, read from its source (review F2)."""
    module, function = SPECIAL_TABLES[utype]
    tree = ast.parse((ENGINE / module).read_text(encoding="utf-8"))
    [fn] = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
    [table] = [n.value for n in ast.walk(fn) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict)
               and [getattr(x, "id", None) for x in n.targets] == ["special"]]
    return [k.value for k in table.keys if isinstance(k, ast.Constant)]


@pytest.mark.parametrize("utype", sorted(SPECIAL_TABLES))
def test_each_evidence_units_special_table_is_its_fixed_gates_less_the_verification_gates(utype):
    """Decision 1: the predicate reads ``FIXED``; an evidence unit's evaluator evaluates a fixed name only if its caller
    put it in ``special``. A name in one and not the other fails here, so the two cannot disagree."""
    assert sorted(special_keys(utype)) == sorted(g for g in G.FIXED[utype] if g not in G.VERIFICATION_GATES)


def _statuses(gates: list[str], utype: str, catalogue: G.Catalogue) -> dict[str, str]:
    invocations, evidence = _evidence(catalogue)
    kind, mutating = {G.MUTATING: ("ticket", True), G.NON_MUTATING: ("ticket", False), G.PARENT: ("story", None)}[utype]
    unit = {"kind": kind, "mutating": mutating, "risk_class": 1, "plan": {"accepted": PLAN}, "waivers": [],
            "invocations": list(invocations), "evidence": [{"id": e["id"], "sha256": e["_sha256"]} for e in evidence]}
    state = {"work": {"W-1": unit}, "invocations": invocations}
    obligations = {"gates": gates, "non_waivable": []}
    if utype == G.MUTATING:
        results = G.evaluate(state, "W-1", evidence, obligations=obligations,
                             gates_policy={"local_checks": list(catalogue.local_checks)}, fingerprint=FP, plan_ok=True,
                             check_definitions=dict(catalogue.checks))
    else:
        for e in evidence:  # an evidence unit's reports are scoped to it
            if e["kind"] == "verification":
                e["verification"]["scope"] = "parent" if utype == G.PARENT else "ticket"
        special = {g: {"status": G.CURRENT} for g in special_keys(utype)}  # what the production caller builds
        results = G.evaluate_evidence_unit(state, "W-1", evidence, obligations=obligations, special=special,
                                           is_current=lambda e: True)
    return {g: r["status"] for g, r in results.items()}


def sample(utype: str) -> list[str]:
    """Every kind and prefix of every evaluator, each with a suffix that resolves and one that does not, and names
    no evaluator has: so a kind missing from one evaluator's table shows as a disagreement."""
    names = [g for t in G.UNIT_TYPES for g in G.FIXED[t]]
    names += ["review_r1", "review_security", "review_prose_standard", "review_",
              "review_card:security_reviewer", "review_card:ghost", "verify_card:verifier", "verify_card:ghost",
              "check:unit", "check:guardrails", "check:ghost", "check:",
              "the targeted tests pass", "targeted", "Review_r1"]
    return list(dict.fromkeys(names))


def disagreements(utype: str, catalogue: G.Catalogue, predicate: Any = G.unsatisfiable) -> list[str]:
    statuses = _statuses(sample(utype), utype, catalogue)
    return [f"{g}: evaluate {statuses[g]}, predicate {'unsatisfiable' if predicate(g, utype, catalogue) else 'ok'}"
            for g in sample(utype) if (statuses[g] == G.CURRENT) != (predicate(g, utype, catalogue) is None)]


@pytest.mark.parametrize("utype", G.UNIT_TYPES)
def test_the_predicate_agrees_with_the_evaluator_in_both_directions(utype):
    assert disagreements(utype, CATALOGUE) == []


def test_local_checks_needs_each_of_its_ids_defined_and_configured():
    undefined = CATALOGUE._replace(local_checks=("unit", "lint"))
    assert disagreements(G.MUTATING, undefined) == []
    found = G.unsatisfiable("local_checks", G.MUTATING, undefined)
    assert found is not None and "`lint`" in found.why and "check:unit" in found.candidates


def test_the_agreement_check_catches_a_wrong_and_a_missing_predicate():
    """The planted control: a right predicate agrees; one that accepts every name (wrong), and one that has lost a
    kind (missing), each disagree, so the agreement test can fail."""
    def accepts_all(gate: str, utype: str, catalogue: G.Catalogue) -> G.Unsatisfiable | None:
        return None

    def lost_check_kind(gate: str, utype: str, catalogue: G.Catalogue) -> G.Unsatisfiable | None:
        if gate.startswith(G.CHECK_PREFIX):
            return G.Unsatisfiable(gate, "planted", ())
        return G.unsatisfiable(gate, utype, catalogue)

    assert disagreements(G.MUTATING, CATALOGUE) == []
    assert any(d.startswith("the targeted tests pass:") for d in disagreements(G.MUTATING, CATALOGUE, accepts_all))
    assert any(d.startswith("check:unit:") for d in disagreements(G.MUTATING, CATALOGUE, lost_check_kind))


def test_the_kind_comes_from_the_evaluators_dispatch_and_evaluate_says_why_it_is_missing():
    """``evaluate``'s last branch is the predicate's own refusal: it names the gate and the kinds that exist."""
    detail = _detail("the targeted tests pass", G.MUTATING)
    assert "gate `the targeted tests pass` can never be satisfied" in detail
    assert "`check:<check id>`" in detail and "`review_card:<card>`" in detail and "`local_checks`" in detail
    # A change-only kind has no evaluator on a parent: its own type's kinds are what that refusal lists.
    parent = G.unsatisfiable("check:unit", G.PARENT)
    assert parent is not None and "for a Story or Epic" in parent.why
    assert "children_complete" in parent.candidates and "check:<check id>" not in parent.candidates


def _detail(gate: str, utype: str) -> str:
    found = G.unsatisfiable(gate, utype)
    assert found is not None
    return found.message


@pytest.mark.parametrize(("gate", "why", "candidate"), [
    ("review_prose_standard", "specialty `prose_standard`", "review_security"),
    ("review_card:ghost", "no card `ghost`", "review_card:security_reviewer"),
    ("verify_card:ghost", "no card `ghost`", "verify_card:verifier"),
    ("check:ghost", "`ghost` is not defined and configured", "check:unit"),
])
def test_a_suffix_that_does_not_resolve_is_named_with_the_candidates(gate, why, candidate):
    found = G.unsatisfiable(gate, G.MUTATING, CATALOGUE)
    assert found is not None and why in found.why and candidate in found.candidates
    assert G.unsatisfiable(gate, G.MUTATING) is None  # without a catalogue, only the kind is judged


def test_a_parent_gate_is_refused_when_any_unit_type_under_it_can_neither_satisfy_nor_pass_it():
    """Addendum 2: a change-only gate passes through to mutating descendants, so a Story may require `check:unit`.
    Review F1: `execute_record` (a non-mutating Ticket's) and `children_complete` (a parent's own) strand the mutating
    Tickets under any parent, so both are refused there."""
    for kind in ("story", "epic"):
        for gate in ("check:unit", "local_checks", "self_review", "acceptance_checks", "post_integration_verifier",
                     "review_security", "review_card:verifier", "accepted_plan", *G.VERIFICATION_GATES):
            assert G.unsatisfiable_inherited(gate, kind, CATALOGUE) is None, (kind, gate)
        for gate in ("the targeted tests pass", "check:ghost", "review_prose_standard", "execute_record",
                     "children_complete"):
            found = G.unsatisfiable_inherited(gate, kind, CATALOGUE)
            assert found is not None and G.UNDER[kind] in found.why, (kind, gate)
    assert G.descendant_types("story") == (G.MUTATING, G.NON_MUTATING)
    assert G.descendant_types("epic") == G.UNIT_TYPES and G.descendant_types("ticket") == ()


def _child(kind: str, utype: str) -> dict[str, Any]:
    if utype == G.PARENT:
        return {"kind": "story", "risk_class": 1, "parent": kind}
    return {"kind": "ticket", "mutating": utype == G.MUTATING, "risk_class": 1, "parent": kind}


def test_every_gate_a_parent_may_set_binds_or_passes_through_on_every_unit_type_under_it():
    """The walk (review F1's class): every fixed name and every prefix with a resolving suffix, for each parent kind
    and each unit type ``hierarchy.PARENT_KINDS`` lets sit under it. A gate the write accepts is, on that child,
    either one its evaluator can satisfy or one ``effective_obligations`` passes through; a gate the write refuses
    is neither on some child. So the write and the descendants' obligations cannot disagree."""
    names = [*dict.fromkeys(g for t in G.UNIT_TYPES for g in G.FIXED[t]), "review_r1", "review_security",
             "review_card:verifier", "verify_card:verifier", "check:unit"]
    for kind in sorted(k for k, parents in H.PARENT_KINDS.items() if k != "ticket"):
        for gate in names:
            stuck = []
            for utype in G.descendant_types(kind):
                state = {"work": {kind: {"kind": kind, "risk_class": 1, "parent": None,
                                         "policy": {"mandatory_gates": [gate]}},
                                  "W-1": _child(kind, utype)}}
                o = G.effective_obligations(state, "W-1", {"risk_paths": {"1": []}})
                if gate not in o["pass_through"] and G.unsatisfiable(gate, utype, CATALOGUE) is not None:
                    stuck.append(utype)
            accepted = G.unsatisfiable_inherited(gate, kind, CATALOGUE) is None
            assert accepted == (stuck == []), (kind, gate, stuck)


def test_a_change_only_gate_inherited_by_a_unit_that_integrates_no_change_passes_through():
    state = {"work": {
        "E-1": {"kind": "epic", "risk_class": 1, "parent": None,
                "policy": {"mandatory_gates": ["check:unit", "review_security", "post_integration_verifier"]}},
        "S-1": {"kind": "story", "risk_class": 1, "parent": "E-1"},
        "T-1": {"kind": "ticket", "mutating": True, "risk_class": 1, "parent": "S-1"},
        "T-2": {"kind": "ticket", "mutating": False, "risk_class": 1, "parent": "S-1"}}}
    paths = {"risk_paths": {"1": []}}
    for wid in ("S-1", "T-2"):
        o = G.effective_obligations(state, wid, paths)
        assert o["gates"] == ["review_security"], wid
        assert o["pass_through"] == {"check:unit": G.CHANGE_ONLY_NOTE, "post_integration_verifier": G.CHANGE_ONLY_NOTE}
        assert G.CHANGE_ONLY_NOTE in o["sources"]["check:unit"]
        assert o["non_waivable"] == ["check:unit", "post_integration_verifier", "review_security"]  # still binding
    mutating = G.effective_obligations(state, "T-1", paths)
    assert mutating["gates"] == ["check:unit", "review_security", "post_integration_verifier"]
    assert mutating["pass_through"] == {}
