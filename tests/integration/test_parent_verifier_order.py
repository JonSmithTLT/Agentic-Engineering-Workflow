"""Parent verifier cards can run together while failures retain one classification subject."""

import pytest
from aewflow import (
    close_parent,
    complete_investigation,
    create_investigation,
    create_unit,
    parent_review,
    parent_verify,
    plan_unit,
    sample_project,
)
from invariants import load_control
from test_role_cards import STRICT_VERIFIER, add_cards

from aew.engine.api import Engine
from aew.errors import GateUnsatisfied, IllegalTransition


@pytest.fixture
def parent(tmp_path):
    p = sample_project(tmp_path)
    add_cards(p, STRICT_VERIFIER)
    story = create_unit(p, "story", "Acceptance")
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    return p, story


def _call(p, method, **kwargs):
    return getattr(Engine.discover(p.root), method)(token=p.token, expect_rev=p.rev(), **kwargs)


def _verify(p, story, evidence):
    return _call(p, "verify_ingest", work_id=story, evidence_id=evidence)


def test_a_parent_first_verifier_dispatch_does_not_crash(parent):
    p, story = parent
    assert "invocations" not in load_control(p.root)["work"][story]
    out = _call(p, "invoke_create", work_id=story, role="verifier")
    assert load_control(p.root)["invocations"][out["invocation"]]["status"] == "active"


def test_a_second_active_parent_verifier_on_the_same_card_is_refused_and_names_another_card(parent):
    p, story = parent
    first = _call(p, "invoke_create", work_id=story, role="verifier")
    before = p.rev()
    with pytest.raises(IllegalTransition, match="--card <card>") as exc:
        _call(p, "invoke_create", work_id=story, role="verifier")
    assert exc.value.details["holding"] == first["invocation"]
    assert p.rev() == before


def test_two_parent_verifier_cards_may_run_at_once(parent):
    p, story = parent
    first = _call(p, "invoke_create", work_id=story, role="verifier")
    other = _call(p, "invoke_create", work_id=story, card="strict_verifier")
    invocations = load_control(p.root)["invocations"]
    assert first["role_card"] != other["role_card"]
    assert all(invocations[r["invocation"]]["status"] == "active" for r in (first, other))


@pytest.mark.parametrize(("classification", "requirement"), [
    ("LOCAL_IMPLEMENTATION_DEFECT", "remediation child"),
    ("PLAN_OR_DESIGN_DEFECT", "new parent plan"),
    ("CONTRACT_VIOLATION", "new parent plan"),
    ("ENVIRONMENT_OR_EVIDENCE_BLOCKED", "Re-verify with verifier"),
])
def test_a_second_failing_parent_ingest_waits_for_the_first_requirement(parent, tmp_path, classification, requirement):
    p, story = parent
    first = parent_verify(p, story, result="fail", card="verifier")
    held = parent_verify(p, story, result="fail", card="strict_verifier")
    _verify(p, story, first)
    with pytest.raises(GateUnsatisfied, match="aew verify classify"):
        _verify(p, story, held)
    p.lead("verify", "classify", story, "--as", classification, "--reason", "synthetic fixture")
    before = load_control(p.root)
    with pytest.raises(GateUnsatisfied, match=requirement) as exc:
        _verify(p, story, held)
    assert first in str(exc.value)
    with pytest.raises(GateUnsatisfied, match=requirement):
        _call(p, "work_close", work_id=story)
    assert load_control(p.root) == before

    if classification == "ENVIRONMENT_OR_EVIDENCE_BLOCKED":
        _verify(p, story, parent_verify(p, story, card="verifier"))
        _verify(p, story, held)
        assert load_control(p.root)["work"][story]["parent_verification"]["awaiting_classification"] == held
        return
    if classification == "LOCAL_IMPLEMENTATION_DEFECT":
        complete_investigation(p, create_investigation(p, tmp_path, parent=story, title="Remediation"))
    else:
        plan_unit(p, tmp_path, story, "A revised plan.\n", reason="repair the failed requirement")
    with pytest.raises(GateUnsatisfied, match="stale"):
        _verify(p, story, held)
    close_parent(p, story)


def test_environment_blocked_needs_its_own_card_to_pass_again(parent):
    p, story = parent
    p.lead("review", "ingest", story, "--evidence", parent_review(p, story))
    failed = parent_verify(p, story, result="fail", card="verifier")
    other = parent_verify(p, story, card="strict_verifier")
    _verify(p, story, failed)
    _verify(p, story, other)
    with pytest.raises(GateUnsatisfied, match="awaits classification"):
        _call(p, "work_close", work_id=story)
    p.lead("verify", "classify", story, "--as", "ENVIRONMENT_OR_EVIDENCE_BLOCKED", "--reason", "environment fixed")
    with pytest.raises(GateUnsatisfied, match="Re-verify with verifier"):
        _call(p, "work_close", work_id=story)
    _verify(p, story, parent_verify(p, story, card="verifier"))
    assert _call(p, "work_close", work_id=story)["ok"]


def test_a_passing_parent_ingest_is_not_held(parent):
    p, story = parent
    failed = parent_verify(p, story, result="fail", card="verifier")
    other = parent_verify(p, story, card="strict_verifier")
    _verify(p, story, failed)
    assert _verify(p, story, other)["result"] == "pass"
    state = load_control(p.root)["work"][story]
    assert state["parent_verification"]["awaiting_classification"] == failed
    assert state["last_verification"]["evidence"] == other


def test_a_stale_held_parent_report_names_invoke_cancel(parent, tmp_path):
    p, story = parent
    first = parent_verify(p, story, result="fail", card="verifier")
    held = parent_verify(p, story, result="fail", card="strict_verifier")
    _verify(p, story, first)
    p.lead("verify", "classify", story, "--as", "LOCAL_IMPLEMENTATION_DEFECT", "--reason", "remediate")
    complete_investigation(p, create_investigation(p, tmp_path, parent=story, title="Remediation"))
    with pytest.raises(GateUnsatisfied, match="aew invoke cancel") as exc:
        _verify(p, story, held)
    with pytest.raises(IllegalTransition, match="still active") as blocked:
        _call(p, "invoke_create", work_id=story, card="strict_verifier")
    inv = blocked.value.details["holding"]
    assert f"aew invoke cancel {inv}" in str(exc.value)
    p.lead("invoke", "cancel", inv, "--reason", "replace the stale report")
    assert _call(p, "invoke_create", work_id=story, card="strict_verifier")["invocation"] != inv
