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
from invariants import assert_control_invariants, load_control

from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.policy import validation as V
from aew.util import load_yaml


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


def inherited(p, root_id):
    """What every unit of ``root_id``'s subtree inherits, read from the owners: its effective class and non-waivable
    gates (``gates.effective_obligations``), and for a mutating Ticket whether its integration needs a verifier
    (``validation.obligation``)."""
    state = load_control(p.root)
    gates_policy = load_yaml((p.root / ".aew/policy/gates.yaml").read_text(encoding="utf-8"))
    out = {}
    for wid in [root_id, *H.descendants(state, root_id)]:
        unit = state["work"][wid]
        ob = G.effective_obligations(state, wid, {**gates_policy, "risk_paths": G.path_table(gates_policy, unit)})
        verifier = unit["kind"] == "ticket" and unit["mutating"] and V.obligation(state, wid, gates_policy)[
            "verifier_required"]
        out[wid] = {"class": ob["effective_class"], "gates": set(ob["non_waivable"]), "verifier": verifier}
    return out


def lowered(before, after):
    """The units of ``before`` whose obligations ``after`` lowers (the EW-U05.g invariant, over the whole subtree)."""
    return sorted(w for w, was in before.items()
                  if after[w]["class"] < was["class"] or not was["gates"] <= after[w]["gates"]
                  or (was["verifier"] and not after[w]["verifier"]))


def test_a_move_never_lowers_the_obligations_of_the_work_it_moves(tmp_path):
    """EW-U05.g: a reorganization preserves the applicable proof obligations. Every unit the move takes keeps its
    effective class, its inherited non-waivable gates and a required integration verifier, or the move is refused,
    naming what each unit would lose, and nothing changes."""
    p = sample_project(tmp_path)
    floor, gate = ("--min-descendant-class", "3", "--rationale", "crosses the auth boundary"), \
        ("--mandatory-gate", "review_security")
    hardening = create_unit(p, "epic", "Hardening", extra=(*floor, *gate))
    same = create_unit(p, "epic", "Hardening too", extra=(*floor, *gate))
    floor_only = create_unit(p, "epic", "Floor only", extra=floor)
    gate_only = create_unit(p, "epic", "Gate only", extra=gate)
    plain = create_unit(p, "epic", "Plain")
    more = create_unit(p, "epic", "More", extra=("--min-descendant-class", "4", "--rationale", "money moves", *gate,
                                                 "--mandatory-gate", "post_integration_verifier"))
    story = create_unit(p, "story", "Sessions", parent=hardening)
    change = create_unit(p, "ticket", "Rotate the session key", parent=story)
    look = create_unit(p, "ticket", "Survey session use", parent=story, extra=("--non-mutating",))
    moved = {story, change, look}
    before = inherited(p, story)
    assert set(before) == moved and all(b["class"] == 3 and b["gates"] == {"review_security"} for b in before.values())
    assert before[change]["verifier"]

    def refused(*args):
        rev = p.rev()
        out = err(p, "work", "move", story, *args, "--reason", "reorganize")
        assert out["code"] == "OBLIGATIONS_DROPPED" and out["details"]["reason"] == "move_lowers_obligations"
        assert p.rev() == rev and show(p, story)["parent"] == hardening and inherited(p, story) == before
        return out["details"]["dropped"]

    # Neither the floor nor the gate, and no parent at all (the missing case): every unit would lose both.
    for target in (("--parent", plain), ("--parent", "none")):
        dropped = refused(*target)
        assert set(dropped) == moved
        assert all(d["effective_class"] == {"before": 3, "after": 1} and d["non_waivable_gates"] == ["review_security"]
                   for d in dropped.values())
        assert {w for w, d in dropped.items() if "integration_verifier" in d} == {change}
    # The floor kept, the gate dropped; the gate kept, the floor (and with it the floor's verifier) dropped.
    assert refused("--parent", floor_only) == {w: {"non_waivable_gates": ["review_security"]} for w in moved}
    dropped = refused("--parent", gate_only)
    assert {w: set(d) for w, d in dropped.items()} == {story: {"effective_class"}, look: {"effective_class"},
                                                       change: {"effective_class", "integration_verifier"}}
    # Admitted: a parent that requires the same, then one that requires more. Nothing in the subtree is lowered.
    p.lead("work", "move", story, "--parent", same, "--reason", "same obligations, new home")
    after = inherited(p, story)
    assert show(p, story)["parent"] == same and not lowered(before, after) and after == before
    p.lead("work", "move", story, "--parent", more, "--reason", "stricter home")
    after_more = inherited(p, story)
    assert not lowered(after, after_more) and all(a["class"] == 4 for a in after_more.values())
    assert_control_invariants(p)


def test_a_promotion_never_lowers_the_obligations_of_the_work_it_moves(tmp_path):
    """EW-U05.g holds for a promotion too: the promoted unit moves under the new parent, which sits under the nearest
    ancestor that can hold it, and must not leave behind what a skipped ancestor required of it."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    gated = create_unit(p, "story", "Payments", parent=epic, extra=(
        "--min-descendant-class", "2", "--rationale", "money moves", "--mandatory-gate", "review_security"))
    t = create_investigation(p, tmp_path, parent=gated)
    rev, before = p.rev(), inherited(p, t)
    out = err(p, "work", "promote", t, "--to", "story", "--title", "Payments, wider", "--reason", "three components")
    assert out["code"] == "OBLIGATIONS_DROPPED"
    assert out["details"]["dropped"] == {t: {"effective_class": {"before": 2, "after": 1},
                                            "non_waivable_gates": ["review_security"]}}
    assert p.rev() == rev and show(p, t)["parent"] == gated and inherited(p, t) == before  # no Story was created
    # A promotion that skips no ancestor's obligations is admitted as before.
    plain = create_investigation(p, tmp_path, parent=epic, title="Plain look")
    assert show(p, p.lead("work", "promote", plain, "--to", "story", "--title", "Wider", "--reason", "scope grew")[
        "promoted_to"])["parent"] == epic
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
