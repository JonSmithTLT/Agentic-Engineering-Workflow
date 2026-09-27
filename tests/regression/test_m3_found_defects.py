"""Defects found while building M3. Each regression was written, and seen failing, before its fix."""

from __future__ import annotations

from aewflow import (close_parent, complete_investigation, create_investigation, create_unit, dispatch, plan_unit,
                     prepare_and_validate, sample_project, submit_record, to_commit_ready)
from conftest import Project


def test_every_dispatch_pins_the_pack_that_durable_state_regenerates(tmp_path, monkeypatch):
    """M3-D1. A harness launch delivers an invocation's pinned pack only if that pack can be regenerated from
    durable state (ADR-0009: launch refuses a drifted pack). M2's executor dispatch pinned its pack before the
    attempt's output contract was recorded, so the pinned pack lacked the "you must produce exactly one
    <kind>" line that every regeneration contains: `context pack` reported matches_recorded=false for every
    non-mutating executor, and no executor could be launched."""
    seen: list[tuple[str, str, bool]] = []
    original = Project.lead

    def lead(self, *args):
        out = original(self, *args)
        if isinstance(out, dict) and out.get("invocation_token"):
            regenerated = self.ok("context", "pack", out["invocation"])
            seen.append((" ".join(args[:2]), out["invocation"], regenerated["matches_recorded"]))
        return out

    monkeypatch.setattr(Project, "lead", lead)
    p = sample_project(tmp_path)
    # Mutating Ticket: implementer, reviewer, verifier, integration verifier.
    wid, _ = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    # Non-mutating Ticket: executor, redispatched executor.
    inv = create_investigation(p, tmp_path, title="Survey")
    dispatch(p, inv)
    p.lead("work", "redispatch", inv, "--reason", "start over")
    # A record under review.
    rec_unit = create_investigation(p, tmp_path, title="Reviewed survey", cls=2)
    p.lead("work", "staff", rec_unit, "--review", "code_reviewer")
    role, _ = dispatch(p, rec_unit)
    p.lead("evidence", "ingest", rec_unit, "--evidence", submit_record(role, "discovery_record")["evidence"])
    p.lead("work", "transition", rec_unit, "--to", "REVIEW_PENDING")
    p.lead("invoke", "create", rec_unit, "--card", "code_reviewer")
    # Story acceptance: parent reviewer and verifier.
    story = create_unit(p, "story", "Understand calc", cls=1)
    plan_unit(p, tmp_path, story, "Investigate, then decide.\n")
    complete_investigation(p, create_investigation(p, tmp_path, parent=story, title="Child"))
    close_parent(p, story)

    assert {kind for kind, _, _ in seen} >= {"work assign", "invoke create", "work dispatch", "work redispatch"}
    assert len(seen) >= 10, seen
    drifted = [s for s in seen if not s[2]]
    assert not drifted, f"pinned packs that durable state does not regenerate: {drifted}"
