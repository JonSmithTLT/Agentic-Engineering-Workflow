"""Epic/Story/Ticket hierarchy through the CLI (ADR-0007; WC §7-§8; KC §9): construction, derived parent
state, closeout gates, cascading cancellation, moves, promotion, dependency edits and rendering."""

from __future__ import annotations

from pathlib import Path

from aewflow import (
    Role,
    close_parent,
    complete_investigation,
    create_investigation,
    create_unit,
    dispatch,
    parent_review,
    parent_verify,
    plan_unit,
    sample_project,
    submit_record,
)
from invariants import assert_control_invariants


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def err(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def test_hierarchy_shape_is_enforced(tmp_path):
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    story = create_unit(p, "story", "Objective", parent=epic)
    ticket = create_unit(p, "ticket", "Work", parent=story)
    assert err(p, "work", "create", "story", "--title", "x", "--class", "1", "--parent", story)["code"] == "USAGE"
    assert err(p, "work", "create", "ticket", "--title", "x", "--class", "1", "--parent", ticket)["code"] == "USAGE"
    assert err(p, "work", "create", "epic", "--title", "x", "--class", "1", "--parent", epic)["code"] == "USAGE"
    # A Ticket may sit directly under an Epic, or stand alone (small work stays small, KC §9.1).
    create_unit(p, "ticket", "Epic-level work", parent=epic)
    create_unit(p, "ticket", "Standalone work")
    # No edge may make a unit wait on its own ancestor or descendant.
    cyc = err(p, "work", "create", "ticket", "--title", "x", "--class", "1", "--parent", story, "--depends-on", story)
    assert cyc["code"] == "USAGE" and "cycle" in cyc["message"]
    assert err(p, "work", "depend", story, "--add", ticket, "--reason", "x")["code"] == "USAGE"
    assert [show(p, w)["state"] for w in (epic, story, ticket)] == ["IN_PROGRESS", "IN_PROGRESS", "BLOCKED"]
    assert_control_invariants(p)


def test_children_complete_is_not_parent_acceptance(tmp_path):
    """WC §8: only the Lead closes a Story, and only after its own gates pass for the current child set."""
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Understand calc", cls=1)
    plan_unit(p, tmp_path, story, "Investigate, then decide.\n")
    t1 = create_investigation(p, tmp_path, parent=story)
    assert show(p, story)["state"] == "IN_PROGRESS"
    complete_investigation(p, t1)
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"
    refused = err(p, "work", "close", story)
    assert refused["code"] == "GATE_UNSATISFIED" and set(refused["details"]["unmet"]) == {
        "review_r1", "verification_goal_backwards", "verification_contract"}
    # A parent review of one child set goes stale when the child set changes.
    p.lead("review", "ingest", story, "--evidence", parent_review(p, story))
    t2 = create_investigation(p, tmp_path, parent=story, title="Second look")
    assert show(p, story)["state"] == "IN_PROGRESS"
    complete_investigation(p, t2)
    gates = p.ok("gate", "show", story)["gates"]
    assert gates["review_r1"]["status"] == "STALE"
    decision = close_parent(p, story)
    u = show(p, story)
    assert u["state"] == "DONE" and u["closeout"]["decision"] == decision
    closeout = (p.root / ".aew" / u["closeout"]["record"]).read_text(encoding="utf-8")
    assert t1 in closeout and t2 in closeout and "children_digest" in closeout
    assert err(p, "work", "create", "ticket", "--title", "late", "--class", "0", "--parent", story)["code"] \
        == "ILLEGAL_TRANSITION"  # a closed parent takes no new children
    assert_control_invariants(p)


def test_class_zero_story_closes_on_children_alone_and_ancestor_policy_still_applies(tmp_path):
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Hardening", cls=3, extra=("--mandatory-gate", "review_security", "--rationale",
                                                             "crosses the auth boundary"))
    story = create_unit(p, "story", "Small objective", cls=0, parent=epic)
    t = create_investigation(p, tmp_path, parent=story, cls=0)
    # The Ticket keeps its local class 0 but inherits the Epic's non-waivable security review.
    gates = p.ok("gate", "show", t)
    assert gates["obligations"]["local_class"] == 0 and "review_security" in gates["obligations"]["non_waivable"]
    assert "review_security" in p.ok("gate", "show", story)["obligations"]["gates"]  # the Story inherits it too
    assert_control_invariants(p)


def test_parent_cancellation_cascades_and_ends_every_credential(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Abandoned objective", cls=1)
    done = create_investigation(p, tmp_path, parent=story, title="Finished")
    complete_investigation(p, done)
    running = create_investigation(p, tmp_path, parent=story, title="In flight")
    role, out = dispatch(p, running)
    ready = create_unit(p, "ticket", "Not started", parent=story)
    res = p.lead("work", "cancel", story, "--reason", "objective dropped")
    assert sorted(res["cancelled_descendants"]) == sorted([running, ready])
    states = [show(p, w)["state"] for w in (story, done, running, ready)]
    assert states == ["CANCELLED", "DONE", "CANCELLED", "CANCELLED"]
    assert p.ok("invoke", "show", out["invocation"])["status"] == "cancelled"
    assert not Path(out["observation"]["path"]).exists()  # the observation was retired and removed
    straggler = Role(p, role.token, p.root)  # a straggler agent still holding the credential
    late = submit_record(straggler, "discovery_record", expect_ok=False)
    assert late.returncode != 0 and late.error["code"] == "STALE_AUTHORITY"
    assert err(p, "work", "transition", story, "--to", "CANCELLED", "--reason", "x")["code"] == "ILLEGAL_TRANSITION"
    assert_control_invariants(p)


def test_move_records_provenance_and_requires_plan_reconfirmation(tmp_path):
    p = sample_project(tmp_path)
    a = create_unit(p, "story", "A", cls=1)
    b = create_unit(p, "story", "B", cls=1)
    plan_unit(p, tmp_path, b, "B's plan.\n")
    t = create_investigation(p, tmp_path, parent=a)
    res = p.lead("work", "move", t, "--parent", b, "--reason", "belongs to B's objective")
    assert res["plans_needing_reconfirmation"] == [t]
    u = show(p, t)
    assert u["parent"] == b and u["parent_history"][-1]["from"] == a
    assert (p.root / ".aew" / u["record"]).read_text(encoding="utf-8").count(f"parent: {a}") == 1  # creation provenance
    assert p.ok("gate", "show", t)["gates"]["accepted_plan"]["status"] == "STALE"
    assert u["state"] == "BLOCKED" and u["blocked_by"][0]["kind"] == "plan_binding_stale"  # fail closed
    assert err(p, "work", "dispatch", t)["code"] == "ILLEGAL_TRANSITION"
    p.lead("plan", "reconfirm", t, "--reason", "still valid under B")
    assert p.ok("gate", "show", t)["gates"]["accepted_plan"]["status"] == "CURRENT"
    assert show(p, t)["state"] == "READY"
    assert_control_invariants(p)


def test_ticket_promotion_preserves_identity_and_evidence(tmp_path):
    """KC §26 (Ticket promotion): the original Ticket, its evidence and the reason survive."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    story = create_unit(p, "story", "Objective", parent=epic)
    t = create_investigation(p, tmp_path, parent=story)
    role, _ = dispatch(p, t)
    ev = submit_record(role, "discovery_record")["evidence"]
    res = p.lead("work", "promote", t, "--to", "story", "--title", "Hidden cross-component scope",
                 "--reason", "the investigation found three components involved")
    new = res["promoted_to"]
    n = show(p, new)
    assert n["kind"] == "story" and n["parent"] == epic and n["promoted_from"] == t
    u = show(p, t)
    assert u["parent"] == new and u["state"] == "REPLAN_REQUIRED"
    assert (p.root / f".aew/evidence/{t}/{ev}.md").exists()  # evidence stays with the original identity
    decision = (p.root / f".aew/decisions/{res['decision']}.md").read_text(encoding="utf-8")
    assert "promotion" in decision and "three components" in decision
    assert_control_invariants(p)


def test_dependency_edits_and_story_level_edges(tmp_path):
    p = sample_project(tmp_path)
    s1 = create_unit(p, "story", "First", cls=0)
    s2 = create_unit(p, "story", "Second", cls=0, extra=("--depends-on", f"{s1}:evidence"))
    first = create_investigation(p, tmp_path, parent=s1, cls=0)
    second = create_investigation(p, tmp_path, parent=s2, cls=0)
    blocked = show(p, second)
    assert blocked["state"] == "BLOCKED" and blocked["blocked_by"][0]["inherited_from"] == s2
    complete_investigation(p, first)
    assert show(p, second)["state"] == "BLOCKED"  # S1's children are done, but S1 is not closed
    p.lead("work", "close", s1, "--reason", "class 0: children complete")
    assert show(p, second)["state"] == "READY"
    role, _ = dispatch(p, second)
    assert err(p, "work", "depend", second, "--add", first, "--reason", "x")["code"] == "ILLEGAL_TRANSITION"
    third = create_investigation(p, tmp_path, cls=0, title="Standalone")
    p.lead("work", "depend", third, "--add", f"{second}:evidence", "--reason", "needs the second look")
    assert show(p, third)["state"] == "BLOCKED"
    p.lead("work", "depend", third, "--remove", second, "--reason", "not needed after all")
    assert show(p, third)["state"] == "READY"
    assert_control_invariants(p)


def test_failed_parent_verification_needs_classification_and_its_remedy(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    p.lead("review", "ingest", story, "--evidence", parent_review(p, story))
    p.lead("verify", "ingest", story, "--evidence", parent_verify(p, story, result="fail"))
    assert any("classify" in a for a in show(p, story)["attention"])
    assert err(p, "invoke", "create", story, "--role", "verifier")["code"] == "ILLEGAL_TRANSITION"
    p.lead("verify", "classify", story, "--as", "LOCAL_IMPLEMENTATION_DEFECT", "--reason", "a child missed a case")
    p.lead("verify", "ingest", story, "--evidence", parent_verify(p, story))
    refused = err(p, "work", "close", story)
    assert refused["code"] == "GATE_UNSATISFIED" and "remediation child" in refused["message"]
    complete_investigation(p, create_investigation(p, tmp_path, parent=story, title="Remediation"))
    close_parent(p, story)
    assert show(p, story)["state"] == "DONE"
    assert_control_invariants(p)


def test_tree_status_and_resume_render_the_hierarchy(tmp_path):
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Toolchain readiness")
    story = create_unit(p, "story", "Durability", parent=epic)
    t = create_investigation(p, tmp_path, parent=story)
    lines = p.ok("work", "tree")["lines"]
    assert lines[0].startswith(f"Epic {epic} [IN_PROGRESS]") and f"Story {story}" in lines[1] \
        and f"Ticket {t}" in lines[2] and "non-mutating" in lines[2]
    status = p.aew("status")
    assert status.returncode == 0 and "Hierarchy" in status.stdout
    resume = p.ok("resume", "--json")
    assert resume["tree"] == lines
    assert any(a.startswith(f"{t}: dispatch it") for a in resume["next_actions"])
    assert f"{epic} [IN_PROGRESS]" in (p.root / ".aew/state/CURRENT.md").read_text(encoding="utf-8")
