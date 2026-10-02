"""What the Engine decides by unit kind, through its public interface (register E5).

The guard of a Lead transition, the gate context and the review/verification path all depend on the unit's kind
(mutating Ticket, non-mutating Ticket, Story or Epic). These hold whether that dispatch is done by class
inheritance or by explicit registration; the composition itself is pinned in ``tests/unit/test_engine_composition``.
A Lead transaction's finalizers run inside it, before its commit.
"""

from __future__ import annotations

import pytest
from aewflow import create_investigation, create_planned_ticket, create_unit, dispatch, plan_unit, sample_project

from aew.engine.api import Engine


def refusal(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def test_the_commit_ready_guard_depends_on_the_kind_of_ticket(tmp_path):
    p = sample_project(tmp_path)
    nm = create_investigation(p, tmp_path)
    dispatch(p, nm)
    refused = refusal(p, "work", "transition", nm, "--to", "COMMIT_READY")
    assert refused["code"] == "ILLEGAL_TRANSITION" and "never an integration candidate" in refused["message"]
    mutating = create_planned_ticket(p, tmp_path)
    p.lead("work", "assign", mutating)
    p.lead("work", "transition", mutating, "--to", "RUNNING")
    refused = refusal(p, "work", "transition", mutating, "--to", "COMMIT_READY")
    assert refused["code"] == "GATE_UNSATISFIED"


def test_the_executor_guard_depends_on_the_kind_of_ticket(tmp_path):
    p = sample_project(tmp_path)
    nm = create_investigation(p, tmp_path)
    out = p.lead("work", "dispatch", nm)
    p.lead("invoke", "cancel", out["invocation"], "--reason", "test")
    refused = refusal(p, "work", "transition", nm, "--to", "RUNNING")
    assert "no active executor for its current attempt" in refused["message"]
    mutating = create_planned_ticket(p, tmp_path)
    out = p.lead("work", "assign", mutating)
    p.lead("invoke", "cancel", out["invocation"], "--reason", "test")
    refused = refusal(p, "work", "transition", mutating, "--to", "RUNNING")
    assert "no active implementer invocation" in refused["message"]


def test_the_gate_context_depends_on_the_kind_of_unit(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective")
    plan_unit(p, tmp_path, story)
    nm = create_investigation(p, tmp_path)
    mutating = create_planned_ticket(p, tmp_path)
    p.lead("work", "assign", mutating)
    engine = Engine.discover(p.root)
    state = engine.store.read()
    parent_gc = engine.gate_context(state, story)
    assert "children_digest" in parent_gc["snapshot"]
    assert parent_gc == engine.evidence_gate_context(state, story)
    nm_gc = engine.gate_context(state, nm)
    assert "subject" in nm_gc["snapshot"] and "execute_record" in nm_gc["gates"]
    assert nm_gc == engine.evidence_gate_context(state, nm)
    mutating_gc = engine.gate_context(state, mutating)
    assert mutating_gc["work_id"] == mutating and mutating_gc["snapshot"]["relevant_inputs_fingerprint"]


def test_a_finalizer_runs_inside_the_lead_transaction_before_its_commit(tmp_path):
    p = sample_project(tmp_path)
    engine = Engine.discover(p.root)
    seen = []
    engine._k.finalizers.steps.append(lambda ctx: seen.append((ctx.session.committed_revision, ctx.state["revision"])))
    before = p.rev()
    out = engine.checkpoint(token=p.token, expect_rev=before, note="finalizer")
    assert seen == [(None, before)] and out["revision"] == before + 1

    def refuse(ctx):
        raise RuntimeError("finalizer refused")

    engine._k.finalizers.steps.append(refuse)
    with pytest.raises(RuntimeError, match="finalizer refused"):
        engine.checkpoint(token=p.token, expect_rev=before + 1, note="refused")
    assert p.rev() == before + 1  # nothing was committed
