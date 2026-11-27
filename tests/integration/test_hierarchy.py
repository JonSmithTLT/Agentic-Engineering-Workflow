"""Epic/Story/Ticket hierarchy through the CLI (ADR-0007; WC §7-§8; KC §9): construction, derived parent
state, closeout gates, cascading cancellation, moves, promotion, dependency edits and rendering."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
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
from invariants import assert_control_invariants, control_violations, load_control

from aew.engine import approval, gate_ops, hierarchy_ops
from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.engine.api import Engine
from aew.engine.store import Transition
from aew.errors import ObligationsDropped
from aew.knowledge.manifest import DEFAULT_GATES
from aew.policy import validation as V
from aew.util import load_yaml


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def err(p, *args):
    res = p.aew(*p.lead_args(*args), env={"AEW_LEAD_TOKEN": p.token})
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
    gates (``gates.effective_obligations``), and for a mutating Ticket whether a verifier validates its integration
    (``validation.obligation``)."""
    state = load_control(p.root)
    gates_policy = load_yaml((p.root / ".aew/policy/gates.yaml").read_text(encoding="utf-8"))
    out = {}
    for wid in [root_id, *H.descendants(state, root_id)]:
        unit = state["work"][wid]
        ob = G.effective_obligations(state, wid, {**gates_policy, "risk_paths": G.path_table(gates_policy, unit)})
        verifier = unit["kind"] == "ticket" and unit["mutating"] and V.obligation(state, wid, gates_policy)[
            "mode"] == V.VERIFIER
        out[wid] = {"class": ob["effective_class"], "gates": set(ob["non_waivable"]), "verifier": verifier}
    return out


def lowered(before, after):
    """The units of ``before`` whose obligations ``after`` lowers (the EW-U05.g invariant, over the whole subtree)."""
    return sorted(w for w, was in before.items()
                  if after[w]["class"] < was["class"] or not was["gates"] <= after[w]["gates"]
                  or (was["verifier"] and not after[w]["verifier"]))


def refused_changing_nothing(p, *args):
    """An observed Lead decision is refused, leaving its control state as it was."""
    state = load_control(p.root)
    res = p.aew(*p.lead_args(*args), env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode != 0, res.stdout
    assert load_control(p.root) == state
    return res.error


def parent_of(p, wid):
    return load_control(p.root)["work"][wid].get("parent")


def made_with(p, kind, named, *, parent=None):
    """A parent created with the floor and gates a create remedy names (``named``), as its ``how`` says."""
    flags = (("--min-descendant-class", str(named["floor"]), "--rationale", "kept")
             if named["floor"] is not None else ())
    assert ("--rationale" in named["how"]) == bool(flags)
    return create_unit(p, kind, "Made with them", parent=parent, extra=(
        *flags, *(x for g in named["gates"] for x in ("--mandatory-gate", g))))


def test_a_move_never_lowers_the_obligations_of_the_work_it_moves(tmp_path):
    """EW-U05.g: a reorganization preserves the applicable proof obligations. Every unit the move takes keeps its
    effective class, its inherited non-waivable gates and its integration's validation by a verifier, or the move is
    refused, naming what each unit would lose and what to do instead, and nothing changes. Every option of every
    refusal is taken with the values it names: it admits a move that lowers nothing or, for reclassify_first where a
    gate would be lost too, leads to a refusal for the rest alone whose options admit. Class 1, 2 and 4 Tickets are
    validated by checks here: only an ancestor makes a class 1 one's a verifier, 3 is the lowest class above it that a
    verifier validates, and no class above 4 has one. The deliberately inconsistent map pins that search."""
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["post_integration"]["validation"] = {"by_class": {"1": "checks", "2": "checks", "4": "checks"},
                                               "default": "verifier"}
    p = sample_project(tmp_path, gates=gates)
    floor, gate = ("--min-descendant-class", "3", "--rationale", "crosses the auth boundary"), \
        ("--mandatory-gate", "review_security")
    verifier = ("--mandatory-gate", "post_integration_verifier")
    hardening = create_unit(p, "epic", "Hardening", extra=(*floor, *gate))
    floor_only = create_unit(p, "epic", "Floor only", extra=floor)
    gate_only = create_unit(p, "epic", "Gate only", extra=gate)
    swapped = create_unit(p, "epic", "Another gate",
                          extra=(*floor, "--mandatory-gate", "review_card:security_reviewer"))
    plain = create_unit(p, "epic", "Plain")
    more = create_unit(p, "epic", "More", extra=("--min-descendant-class", "4", "--rationale", "money moves", *gate,
                                                 *verifier))
    story = create_unit(p, "story", "Sessions", parent=hardening)
    change = create_unit(p, "ticket", "Rotate the session key", parent=story)
    look = create_unit(p, "ticket", "Survey session use", parent=story, extra=("--non-mutating",))
    moved = {story, change, look}
    before = inherited(p, story)
    assert set(before) == moved and all(b["class"] == 3 and b["gates"] == {"review_security"} for b in before.values())
    assert before[change]["verifier"]

    def refused(root, *target):
        """Moving ``root`` to ``target``, refused, changing nothing: ``(dropped, instead by option)``."""
        out = refused_changing_nothing(p, "work", "move", root, *target, "--reason", "reorganize")
        assert out["code"] == "OBLIGATIONS_DROPPED" and out["details"]["reason"] == "move_lowers_obligations"
        assert out["message"].startswith("a move that would lower") and "this move would lower" in out["message"]
        instead = {o["option"]: o for o in out["details"]["instead"]}
        assert list(instead) in (["move_under_an_equal_parent", "create_the_parent_with_them"],
                                 ["move_under_an_equal_parent", "create_the_parent_with_them", "reclassify_first"])
        return out["details"]["dropped"], instead

    def moves(root, parent, why):
        p.lead("work", "move", root, "--parent", parent, "--reason", why)
        assert parent_of(p, root) == parent

    # Every target that keeps less than the old parent chain, and no parent at all (the missing case). Whatever the
    # target keeps, the create remedy names what the old chain required, its floor and gate.
    refusals = {target: refused(story, "--parent", target) for target in (plain, "none", floor_only, swapped,
                                                                          gate_only)}
    for dropped, named in refusals.values():
        create = named["create_the_parent_with_them"]
        assert set(dropped) == moved and (create["floor"], create["gates"]) == (3, ["review_security"])
    # Neither the floor nor the gate kept: every unit would lose both.
    for target in (plain, "none"):
        dropped, named = refusals[target]
        assert all(d["effective_class"] == {"before": 3, "after": 1} and d["non_waivable_gates"] == ["review_security"]
                   for d in dropped.values())
        assert {w for w, d in dropped.items() if "integration_verifier" in d} == {change}
    # The floor kept and the gate dropped; and as many gates but another one (gates are a set, not a count). No class
    # or verifier is lost, so raising a class is not offered.
    for target in (floor_only, swapped):
        dropped, named = refusals[target]
        assert dropped == {w: {"non_waivable_gates": ["review_security"]} for w in moved}
        assert "reclassify_first" not in named
    # The gate kept, the floor (and with it the floor's verifier) dropped.
    dropped, _ = refusals[gate_only]
    assert {w: set(d) for w, d in dropped.items()} == {story: {"effective_class"}, look: {"effective_class"},
                                                       change: {"effective_class", "integration_verifier"}}
    # reclassify_first raises each unit's own class to the class it would lose, and says when that keeps no gate.
    for target in (plain, "none", gate_only):
        reclassify = refusals[target][1]["reclassify_first"]
        assert reclassify["classes"] == {w: 3 for w in moved}
        assert ("does not keep a gate" in reclassify["how"]) == (target != gate_only)

    # create_the_parent_with_them, one remedy for every target, taken from a refusal whose target keeps part: the
    # parent it names admits the move, lowering nothing; and the way back admits, the obligations being equal.
    made = made_with(p, "epic", refusals[floor_only][1]["create_the_parent_with_them"])
    moves(story, made, "same obligations, new home")
    assert not lowered(before, inherited(p, story))
    moves(story, hardening, "back, to take the next remedy")
    # reclassify_first, one remedy for every target that offers it: each unit's own class raised as named. The
    # gate-only target then admits the move. The others refuse it for the gate alone (no class to raise any more),
    # and its create remedy is the one taken above, so the parent made with it admits.
    for wid, cls in refusals[plain][1]["reclassify_first"]["classes"].items():
        p.lead("work", "reclassify", wid, "--class", str(cls), "--reason", "meet the floor before the move")
    reclassified = inherited(p, story)
    for target in (plain, "none"):
        dropped, named = refused(story, "--parent", target)
        assert dropped == {w: {"non_waivable_gates": ["review_security"]} for w in moved}
        assert "reclassify_first" not in named
        assert named["create_the_parent_with_them"] == refusals[floor_only][1]["create_the_parent_with_them"]
    moves(story, gate_only, "the floor is now the units' own class")
    assert not lowered(reclassified, inherited(p, story))
    moves(story, made, "the gate as well")
    assert not lowered(reclassified, inherited(p, story))
    # move_under_an_equal_parent: one that requires more admits it too.
    moves(story, more, "stricter home")
    after_more = inherited(p, story)
    assert not lowered(before, after_more) and all(a["class"] == 4 for a in after_more.values())

    # A verifier that an ancestor's post_integration_verifier gate requires, with no floor: the create remedy names the
    # gate and no floor. reclassify_first raises a class 1 Ticket to 3, the lowest class above its own a verifier
    # validates, and leaves out a class 4 one, which has none, saying so.
    verified = create_unit(p, "epic", "Verified", extra=verifier)
    payments = create_unit(p, "story", "Payments", parent=verified)
    charge = create_unit(p, "ticket", "Charge the card", parent=payments)
    settle = create_unit(p, "ticket", "Settle the batch", cls=4, parent=payments)
    v_before = inherited(p, payments)
    assert v_before[charge]["verifier"] and v_before[settle]["verifier"]
    lost_gate, lost_both = {"non_waivable_gates"}, {"non_waivable_gates", "integration_verifier"}
    dropped, named = refused(payments, "--parent", plain)
    assert {w: set(d) for w, d in dropped.items()} == {payments: lost_gate, charge: lost_both, settle: lost_both}
    create = named["create_the_parent_with_them"]
    assert (create["floor"], create["gates"]) == (None, ["post_integration_verifier"])
    assert named["reclassify_first"]["classes"] == {charge: 3}
    assert f"does not keep a gate or the verifier of {settle}" in named["reclassify_first"]["how"]
    made = made_with(p, "epic", create)
    moves(payments, made, "same obligations, new home")
    assert not lowered(v_before, inherited(p, payments))
    moves(payments, verified, "back, to take the next remedy")
    for wid, cls in named["reclassify_first"]["classes"].items():
        p.lead("work", "reclassify", wid, "--class", str(cls), "--reason", "a verifier validates that class")
    # The rest alone: the gate, and the class 4 Ticket's verifier, which no class meets, so nothing is to be raised.
    dropped, again = refused(payments, "--parent", plain)
    assert {w: set(d) for w, d in dropped.items()} == {payments: lost_gate, charge: lost_gate, settle: lost_both}
    assert "reclassify_first" not in again and again["create_the_parent_with_them"] == create
    moves(payments, made, "the gate as well")
    assert not lowered(v_before, inherited(p, payments))
    moves(payments, more, "stricter home")
    assert not lowered(v_before, inherited(p, payments))
    assert_control_invariants(p)


def test_a_move_that_would_lower_obligations_is_refused_before_any_replan_is_asked(tmp_path):
    """A move that both lowers obligations and changes the inherited edges of started work is refused for its
    obligations first: no change of state meets that refusal, so asking for a replan first would end the started
    attempt for nothing. The started work stays RUNNING. Planted control: with the gate kept, the same move meets the
    dependency refusal."""
    p = sample_project(tmp_path)
    upstream = create_unit(p, "ticket", "Upstream", extra=("--non-mutating",))
    gated = create_unit(p, "epic", "Security", extra=("--mandatory-gate", "review_security"))
    linked = create_unit(p, "epic", "Linked", extra=("--depends-on", upstream))
    keeps = create_unit(p, "epic", "Linked and gated", extra=("--depends-on", upstream,
                                                              "--mandatory-gate", "review_security"))
    story = create_unit(p, "story", "Sessions", parent=gated)
    look = create_investigation(p, tmp_path, parent=story)
    dispatch(p, look)
    rev = p.rev()
    out = err(p, "work", "move", story, "--parent", linked, "--reason", "reorganize")
    assert out["code"] == "OBLIGATIONS_DROPPED" and set(out["details"]["dropped"]) == {story, look}
    assert p.rev() == rev and show(p, look)["state"] == "RUNNING" and show(p, story)["parent"] == gated
    out = err(p, "work", "move", story, "--parent", keeps, "--reason", "reorganize")
    assert out["code"] == "ILLEGAL_TRANSITION" and out["details"]["in_progress"] == [look]
    assert p.rev() == rev and show(p, look)["state"] == "RUNNING"
    assert_control_invariants(p)


def test_a_promotion_carries_what_it_leaves_behind_and_lowers_nothing(tmp_path):
    """EW-U05.g for a promotion (register E87): what every ancestor a promotion leaves behind imposed is carried onto
    the unit it creates (``carried_obligations``), so each unit of the promoted subtree keeps exactly what it
    inherited, its validation binding included, where E84 refused the promotion. Each entry names its origin, the
    ancestor left behind that held it and the promotion. A chain of promotions keeps the origin; the carrier binds its
    later children too; a move out of it is refused as any move that lowers obligations is; and a promotion that
    leaves no obligation behind writes no carry. Class 0 and 1 Tickets are validated by checks here, so only an
    ancestor makes a mutating one's a verifier."""
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["post_integration"]["validation"] = {"by_class": {"0": "checks", "1": "checks"}, "default": "verifier"}
    p = sample_project(tmp_path, gates=gates)
    floor, gate = ("--min-descendant-class", "2", "--rationale", "money moves"), ("--mandatory-gate", "review_security")
    epic = create_unit(p, "epic", "Initiative")
    gated = create_unit(p, "story", "Payments", parent=epic, extra=(*floor, *gate))
    floored = create_unit(p, "story", "Ledger", parent=epic, extra=floor)
    verified = create_unit(p, "story", "Settlement", parent=epic,
                           extra=("--mandatory-gate", "post_integration_verifier"))
    change = create_unit(p, "ticket", "Charge the card", parent=gated)
    look = create_unit(p, "ticket", "Survey card use", parent=gated, extra=("--non-mutating",))
    posting = create_unit(p, "ticket", "Post the entry", parent=floored)
    settle = create_unit(p, "ticket", "Settle the batch", parent=verified)
    gates_policy = load_yaml((p.root / ".aew/policy/gates.yaml").read_text(encoding="utf-8"))

    def exact(wid):
        """``inherited`` over ``wid``'s subtree, with each mutating Ticket's validation binding."""
        state, out = load_control(p.root), inherited(p, wid)
        for w, entry in out.items():
            if state["work"][w]["kind"] == "ticket" and state["work"][w]["mutating"]:
                entry["binding"] = V.obligation(state, w, gates_policy)["binding"]
        return out

    def promote(wid, to="story"):
        """``wid`` promoted, every unit of its subtree inheriting exactly what it did: ``(new unit, carried)``."""
        before = exact(wid)
        res = p.lead("work", "promote", wid, "--to", to, "--title", f"{wid}, wider", "--reason", "scope grew")
        assert exact(wid) == before
        new = res["promoted_to"]
        assert parent_of(p, wid) == new and show(p, new).get("carried_obligations", []) == res["carried_obligations"]
        return new, res["carried_obligations"], res["decision"]

    def entry(origin, via, decision, cls, gates_, rationale):
        return {"from": origin, "via": via, "decision": decision, "min_descendant_class": cls,
                "mandatory_gates": gates_, "rationale": rationale}

    # A mutating Ticket out of a Story with a floor and a gate, which E84 refused: both go with it, and its
    # integration is still validated by a verifier.
    assert {k: v for k, v in exact(change)[change].items() if k != "binding"} == {
        "class": 2, "gates": {"review_security"}, "verifier": True}
    story, carried, d = promote(change)
    assert parent_of(p, story) == epic and carried == [entry(gated, gated, d, 2, ["review_security"], "money moves")]
    # A non-mutating Ticket out of the same Story; a floor-only Story; a verifier gate with no floor.
    _, carried, d = promote(look)
    assert carried == [entry(gated, gated, d, 2, ["review_security"], "money moves")]
    _, carried, d = promote(posting)
    assert carried == [entry(floored, floored, d, 2, [], "money moves")]
    assert exact(settle)[settle]["verifier"]
    _, carried, d = promote(settle)
    assert carried == [entry(verified, verified, d, None, ["post_integration_verifier"], None)]
    # A real subtree: a Story with its Tickets promoted to an Epic out of an Epic with a floor and a gate.
    guarded = create_unit(p, "epic", "Guarded", extra=(*floor, *gate))
    sessions = create_unit(p, "story", "Sessions", parent=guarded)
    create_unit(p, "ticket", "Rotate the key", parent=sessions)
    create_unit(p, "ticket", "Survey use", parent=sessions, extra=("--non-mutating",))
    top, carried, d = promote(sessions, to="epic")
    assert parent_of(p, top) is None and carried == [entry(guarded, guarded, d, 2, ["review_security"], "money moves")]
    # A chain: the Ticket promoted again, out of the Story that carries for it, keeps the origin.
    _, carried, d = promote(change, to="epic")
    assert carried == [entry(gated, story, d, 2, ["review_security"], "money moves")]
    # The carrier binds what is created under it later, as its own policy would.
    later = create_unit(p, "ticket", "Refund the card", parent=story)
    assert inherited(p, later)[later] == {"class": 2, "gates": {"review_security"}, "verifier": True}
    # Leaving the carrier is a move: refused as E84 refuses any move that lowers obligations, its create remedy naming
    # what the carrier carries.
    out = refused_changing_nothing(p, "work", "move", later, "--parent", epic, "--reason", "reorganize")
    assert out["code"] == "OBLIGATIONS_DROPPED" and set(out["details"]["dropped"]) == {later}
    create = {o["option"]: o for o in out["details"]["instead"]}["create_the_parent_with_them"]
    assert (create["floor"], create["gates"]) == (2, ["review_security"])
    # A promotion that leaves no obligation behind carries nothing and writes no key.
    plain = create_investigation(p, tmp_path, parent=epic, title="Plain look")
    new, carried, _ = promote(plain)
    assert carried == [] and "carried_obligations" not in show(p, new)
    assert_control_invariants(p)


def test_every_reader_of_an_inherited_obligation_reads_the_carried_ones(tmp_path):
    """Every reader of an ancestor's floor or mandatory gates goes through ``hierarchy.ancestor_obligations``, so a
    carried obligation binds as its origin's did (register E87): the effective class and obligations, the validation
    obligation (named by its origin), ``work reclassify``'s floor, and the gate's owners (its holder, the carrier)."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    gated = create_unit(p, "story", "Payments", parent=epic, extra=(
        "--min-descendant-class", "3", "--rationale", "money moves", "--mandatory-gate", "post_integration_verifier"))
    change = create_unit(p, "ticket", "Charge the card", parent=gated)
    gates_policy = load_yaml((p.root / ".aew/policy/gates.yaml").read_text(encoding="utf-8"))

    def read():
        state = load_control(p.root)
        ob, val = G.effective_obligations(state, change, {"risk_paths": {str(c): [] for c in range(5)}}), \
            V.obligation(state, change, gates_policy)
        return {"class": G.effective_class(state, change), "floor": ob["floor"], "non_waivable": ob["non_waivable"],
                "sources": ob["sources"], "validation": {k: val[k] for k in ("mode", "sources", "floor", "binding")}}

    before = read()
    assert before["class"] == 3 and before["validation"]["mode"] == V.VERIFIER
    assert gate_ops.owners(load_control(p.root), change, "post_integration_verifier") == [gated]
    story = p.lead("work", "promote", change, "--to", "story", "--title", "Wider", "--reason", "scope grew")[
        "promoted_to"]
    assert read() == before
    assert gate_ops.owners(load_control(p.root), change, "post_integration_verifier") == [story]
    out = err(p, "work", "reclassify", change, "--class", "2", "--reason", "more risk than planned")
    assert out["code"] == "USAGE" and out["details"]["floor"] == 3
    assert_control_invariants(p)


def test_a_promotion_whose_carry_is_incomplete_is_refused_changing_nothing(tmp_path, monkeypatch):
    """The monotonic check stays as the backstop over the carry (register E87): were a promotion's carry ever
    incomplete, the promotion is refused as E84 refused it, with a promotion's remedies, and nothing is created."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    gated = create_unit(p, "story", "Payments", parent=epic, extra=(
        "--min-descendant-class", "2", "--rationale", "money moves", "--mandatory-gate", "review_security"))
    change = create_unit(p, "ticket", "Charge the card", parent=gated)
    monkeypatch.setattr(hierarchy_ops, "carry", lambda *_: [])
    state = load_control(p.root)
    prior = approval.promotion_value(state["work"][change])
    with pytest.raises(ObligationsDropped) as refused:
        Engine.discover(p.root).work_promote(token=p.token, work_id=change, to="story", title="Wider",
                                             reason="scope grew", prior_value=prior)
    assert load_control(p.root) == state
    details = refused.value.details
    assert refused.value.message.startswith("a promotion that would lower")
    assert details["reason"] == "move_lowers_obligations" and set(details["dropped"]) == {change}
    assert [o["option"] for o in details["instead"]] == ["create_the_parent_then_move", "reclassify_first"]


def test_invariant_64_catches_effective_obligations_missing_a_carry_and_a_carry_no_promotion_wrote(tmp_path,
                                                                                                 monkeypatch):
    """Invariant 64 (register E87) can fail: its independent walk disagrees with ``gates.effective_obligations`` once
    the accessor ignores what a carrier carries, and it refuses a carried entry on a Ticket, or one citing a decision
    that is not the carrier's promotion. (The other readers are proven by
    ``test_every_reader_of_an_inherited_obligation_reads_the_carried_ones``.)"""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    gated = create_unit(p, "story", "Payments", parent=epic, extra=("--mandatory-gate", "review_security"))
    change = create_unit(p, "ticket", "Charge the card", parent=gated)
    res = p.lead("work", "promote", change, "--to", "story", "--title", "Wider", "--reason", "scope grew")
    story = res["promoted_to"]
    assert control_violations(p.root) == []
    with monkeypatch.context() as patch:
        patch.setattr(H, "imposed", lambda state, holder: [(holder, state["work"][holder]["policy"])]
                      if state["work"][holder].get("policy") else [])
        assert any(v.startswith(f"64: {change} inherits floor None and gates []") for v in control_violations(p.root))
    other = create_unit(p, "ticket", "Elsewhere", parent=epic)
    engine = Engine.discover(p.root)
    with engine.store.session() as s:
        s.state["work"][other]["carried_obligations"] = [dict(res["carried_obligations"][0])]
        s.state["work"][story]["carried_obligations"][0]["decision"] = "D-0099"  # never issued
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="carries no promotion wrote"))
    found = control_violations(p.root)
    assert f"64: {other} carries obligations but is not a Story or Epic a promotion created, or carries none" in found
    assert f"64: {story}'s carried entry from {gated} cites D-0099, not the promotion of {change}" in found


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
