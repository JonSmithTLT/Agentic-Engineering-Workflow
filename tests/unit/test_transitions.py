"""Table-driven checks of the Ticket state machine against WC §8's mandatory rules."""

from __future__ import annotations

import itertools

import pytest

from aew.engine import transitions as t
from aew.errors import IllegalTransition

VIAS = {r.via for r in t.RULES.values()}


@pytest.mark.parametrize(("frm", "to"), list(itertools.product(t.STATES, t.STATES)))
def test_every_pair_is_either_ruled_or_rejected(frm, to):
    rule = t.RULES.get((frm, to))
    for via in VIAS:
        if rule is not None and rule.via == via:
            assert t.check(frm, to, via) is rule
        else:
            with pytest.raises(IllegalTransition):
                t.check(frm, to, via)


def test_terminal_states_have_no_exits():
    assert not [k for k in t.RULES if k[0] in t.TERMINAL]


@pytest.mark.parametrize(
    ("frm", "to", "via"),
    [
        # results owned by Reviewer/Verifier are applied only by ingest, never chosen freely
        ("REVIEW_PENDING", "REVIEW_PASSED", "review.ingest"),
        ("VERIFY_PENDING", "VERIFIED", "verify.ingest"),
        ("VERIFY_PENDING", "VERIFICATION_FAILED", "verify.ingest"),
        # only Lead classification leaves VERIFICATION_FAILED
        ("VERIFICATION_FAILED", "RUNNING", "verify.classify"),
        ("VERIFICATION_FAILED", "REPLAN_REQUIRED", "verify.classify"),
        # DONE only via controlled integration
        ("COMMIT_READY", "DONE", "integrate.publish"),
        ("READY", "ASSIGNED", "assign"),
    ],
)
def test_role_owned_and_integration_transitions_need_their_operation(frm, to, via):
    assert t.check(frm, to, via).via == via
    with pytest.raises(IllegalTransition) as exc:
        t.check(frm, to, "transition")
    assert exc.value.details["required_operation"] == via


def test_review_failed_to_running_requires_findings_guard():
    assert t.check("REVIEW_FAILED", "RUNNING", "transition").guard == "findings_recorded"


def test_verification_failed_cannot_escape_by_escalation():
    with pytest.raises(IllegalTransition):
        t.check("VERIFICATION_FAILED", "ESCALATED", "transition")
    assert t.check("VERIFICATION_FAILED", "CANCELLED", "transition").reason_required


def test_classification_mapping_is_the_spec_mapping():
    assert t.VERIFICATION_CLASSIFICATIONS == {
        "LOCAL_IMPLEMENTATION_DEFECT": "RUNNING",
        "PLAN_OR_DESIGN_DEFECT": "REPLAN_REQUIRED",
        "CONTRACT_VIOLATION": "REPLAN_REQUIRED",
        "ENVIRONMENT_OR_EVIDENCE_BLOCKED": "VERIFICATION_INCONCLUSIVE",
    }
    for dst in set(t.VERIFICATION_CLASSIFICATIONS.values()):
        assert t.check("VERIFICATION_FAILED", dst, "verify.classify")


def test_regressions_require_reasons():
    for src in ("REVIEW_PASSED", "VERIFIED", "COMMIT_READY"):
        assert t.check(src, "RUNNING", "transition").reason_required


def test_interrupted_reconcile_is_bounded():
    rule = t.check("INTERRUPTED", "COMMIT_READY", "reconcile")
    assert rule.guard == "not_beyond_interrupted_phase" and rule.reason_required
    with pytest.raises(IllegalTransition):
        t.check("INTERRUPTED", "DONE", "reconcile")
