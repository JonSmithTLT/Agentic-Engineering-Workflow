"""A return from escalation meets the gates of the phase it enters, and a reconcile after an interruption meets the
guard of the Lead's direct edge from the interrupted phase, where the table has one (EW-U06.f; R1-D2; option C of the
R1 plan v4, the designer's ruling of 2026-10-25).

Through the Lead's direct edge from the phase the unit left, the return meets that edge's guard; otherwise it meets
the gate guards of the Lead's own entries into the phase, asked through their query forms, and is refused where one
has no query for the unit's kind. Every refusal leaves a governed path: it names what to do instead, and these tests
take that path through the real transitions to the phase that was refused."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from aewflow import (
    assign,
    create_investigation,
    create_planned_ticket,
    dispatch,
    implement,
    redispatch_implementer,
    review,
    sample_project,
    submit_record,
)
from invariants import assert_control_invariants

from aew.engine import transitions as T
from aew.engine.api import Engine
from aew.engine.guards import AVAILABLE, BLOCKED, UNKNOWN
from aew.engine.seams import GATE, MUTATING, NON_MUTATING
from aew.engine.store import Transition
from aew.errors import AEWError
from aew.knowledge.manifest import DEFAULT_GATES
from aew.util import dump_yaml, load_yaml

REQUIRED_FINDING = [{"id": "F1", "severity": "major", "summary": "missing negative test", "required": True}]
PRE_REVIEW_KINDS = {"check_result", "implementation_report"}  # what the pre-review gates count (local_checks, ...)


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def err(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def move(p, wid, to, reason="the operator answered"):
    p.lead("work", "transition", wid, "--to", to, "--reason", reason)


def refused(p, wid, to, reason_code, *, verb=("work", "transition")):
    """A refused entry into ``to``: the typed refusal, its reason, and nothing changed."""
    rev, state = p.rev(), show(p, wid)["state"]
    out = err(p, *verb, wid, "--to", to, "--reason", "the operator answered")
    assert out["code"] == "GATE_UNSATISFIED" and out["details"]["reason"] == reason_code, out
    assert "Instead:" in out["message"] and out["details"]["instead"], out  # a governed path is named
    assert p.rev() == rev and show(p, wid)["state"] == state
    return out["details"]


def relied_pre_review(p, wid) -> set[str]:
    """The evidence the pre-review gates (local_checks, self_review) count now: what a recheck of them relies on."""
    gates = p.ok("gate", "show", wid)["gates"]
    return {i for g in ("local_checks", "self_review")
            for i in [gates[g].get("evidence"), *(c.get("evidence") for c in gates[g].get("checks", {}).values())]
            if isinstance(i, str)}


def seed(p, mutate) -> None:
    """Put a unit into a state with one plain commit (the class test reaches every origin this way)."""
    engine = Engine.discover(p.root)
    with engine.store.session() as s:
        mutate(s.state)
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="seeded for the escalation tests"))


def test_a_return_from_escalation_never_skips_the_findings_a_rework_round_needs(tmp_path):
    """A rework round needs the review's findings: a unit escalated from a failed review returns to RUNNING only as
    the Lead's direct edge from that phase admits it, which requires them. The named path, taken: back to review, where
    a review records them, then rework."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid, disposition="changes_required"))
    assert show(p, wid)["state"] == "REVIEW_FAILED"
    move(p, wid, "ESCALATED")
    details = refused(p, wid, "RUNNING", "direct_edge_guard_unmet")
    assert details["guard"] == "findings_recorded"
    assert "requires recorded review findings" in details["refused"]["message"]
    assert details["instead"][0] == {"option": "meet_the_guard", "guard": "findings_recorded"}
    # Only the returns the hub admits now are named: VERIFY_PENDING is beyond the phase left.
    assert [o for o in details["instead"] if o["option"] == "return_to"] == [{"option": "return_to",
                                                                              "to": "REVIEW_PENDING"}]
    assert details["instead"][-1] == {"option": "leave_to", "to": ["CANCELLED", "REPLAN_REQUIRED"]}
    # The remedy: return to review (its gate rechecked: admitted), where the findings are recorded; then rework.
    move(p, wid, "REVIEW_PENDING", "a new review records what failed")
    p.lead("review", "ingest", wid, "--evidence",
           review(p, wid, disposition="changes_required", findings=REQUIRED_FINDING))
    assert show(p, wid)["state"] == "REVIEW_FAILED"
    # Planted control: with the findings recorded, the same return is admitted.
    move(p, wid, "ESCALATED")
    move(p, wid, "RUNNING")
    assert show(p, wid)["state"] == "RUNNING"
    assert_control_invariants(p)


def test_a_return_to_review_rechecks_its_gates_and_pins_what_it_relied_on(tmp_path):
    """A return with no direct edge meets the gate guard of the Lead's entry into the phase, against current state:
    admitted while the pre-review gates are current, pinning the evidence current at the return; refused once one is
    stale, naming the way back (rework through RUNNING), which is then taken. A restore to RUNNING meets no gate."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    move(p, wid, "ESCALATED")
    pins = [r["id"] for r in show(p, wid)["evidence"]]
    move(p, wid, "RUNNING")  # RUNNING's entry guards are where the unit comes from: none is a gate
    assert [r["id"] for r in show(p, wid)["evidence"]] == pins  # no pins added
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    move(p, wid, "ESCALATED")
    # Planted: the pins are cleared during escalation; the return pins the evidence its recheck relied on, again.
    seed(p, lambda s: s["work"][wid].update(
        evidence=[r for r in s["work"][wid]["evidence"] if r["kind"] not in PRE_REVIEW_KINDS]))
    move(p, wid, "REVIEW_PENDING")
    relied = relied_pre_review(p, wid)
    assert len(relied) == 2 and relied <= {r["id"] for r in show(p, wid)["evidence"]}
    # A pre-review gate goes stale during escalation: the return is refused with the gate guard's own refusal.
    move(p, wid, "ESCALATED")
    impl.write({"calc/core.py": "def add(a, b):\n    return a + b\n# changed while escalated\n"})
    details = refused(p, wid, "REVIEW_PENDING", "entry_guard_unmet")
    assert details["guard"] == "ready_for_review" and "local_checks" in details["refused"]["details"]["unmet"]
    assert {"option": "return_to", "to": "RUNNING"} in details["instead"]
    # The remedy: rework through RUNNING, then the Lead's own entry into review.
    move(p, wid, "RUNNING")
    implement(redispatch_implementer(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    assert show(p, wid)["state"] == "REVIEW_PENDING"
    assert_control_invariants(p)


def test_a_return_to_verification_without_review_rechecks_the_entry_the_gates_choose(tmp_path):
    """VERIFY_PENDING has two gate guards: after review, and without one. Where no review gate applies, the return
    meets `ready_for_verification_without_review`, through its query form."""
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["risk_paths"]["1"] = [g for g in gates["risk_paths"]["1"] if not g.startswith("review_")]
    p = sample_project(tmp_path, gates=gates)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    move(p, wid, "ESCALATED")
    move(p, wid, "VERIFY_PENDING")
    assert show(p, wid)["state"] == "VERIFY_PENDING"
    move(p, wid, "ESCALATED")
    impl.write({"calc/core.py": "def add(a, b):\n    return a + b\n# changed while escalated\n"})
    details = refused(p, wid, "VERIFY_PENDING", "entry_guard_unmet")
    assert details["guard"] == "ready_for_verification_without_review"
    move(p, wid, "RUNNING")
    implement(redispatch_implementer(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    assert show(p, wid)["state"] == "VERIFY_PENDING"
    assert_control_invariants(p)


def test_a_return_to_verification_after_review_rechecks_that_the_review_is_current(tmp_path):
    """Where a review gate applies, a return to VERIFY_PENDING meets `review_current`, the guard of the Lead's entry
    after review: admitted while the review is of what is there now, pinning the pre-review evidence it relied on;
    refused by `review_current` itself after an edit nobody reviewed, naming the way back (rework through RUNNING),
    which is then taken through review to verification."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    move(p, wid, "ESCALATED")
    # Planted: the pre-review pins are cleared during escalation; the return pins the evidence its recheck relied on.
    seed(p, lambda s: s["work"][wid].update(
        evidence=[r for r in s["work"][wid]["evidence"] if r["kind"] not in PRE_REVIEW_KINDS]))
    move(p, wid, "VERIFY_PENDING")
    relied = relied_pre_review(p, wid)
    assert len(relied) == 2 and relied <= {r["id"] for r in show(p, wid)["evidence"]}
    # An edit nobody reviewed, during escalation: the return is refused with review_current's own refusal.
    move(p, wid, "ESCALATED")
    impl.write({"calc/core.py": "def add(a, b):\n    return a + b\n# changed while escalated\n"})
    details = refused(p, wid, "VERIFY_PENDING", "entry_guard_unmet")
    assert details["guard"] == "review_current"
    assert details["refused"]["message"].startswith("REVIEW_PASSED -> VERIFY_PENDING: gates not satisfied")
    assert {"option": "return_to", "to": "RUNNING"} in details["instead"]
    # The remedy: rework through RUNNING, a review of the new change, then the Lead's own entry into verification.
    move(p, wid, "RUNNING")
    implement(redispatch_implementer(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    assert show(p, wid)["state"] == "VERIFY_PENDING"
    assert_control_invariants(p)


def test_a_return_to_review_once_no_review_gate_applies_is_refused_by_its_entry_guard(tmp_path):
    """The review gate stops applying during escalation (the operator adopts a policy whose class path has none): a
    return to REVIEW_PENDING meets `ready_for_review` against current state and is refused by it, naming the way on,
    back to RUNNING, from where the Lead's own entry into verification without review is taken."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    move(p, wid, "ESCALATED")
    path = p.root / ".aew/policy/gates.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    policy["risk_paths"]["1"] = [g for g in policy["risk_paths"]["1"] if not g.startswith("review_")]
    path.write_text(dump_yaml(policy), encoding="utf-8")
    p.adopt_policy()
    details = refused(p, wid, "REVIEW_PENDING", "entry_guard_unmet")
    assert details["guard"] == "ready_for_review" and "no review gate applies" in details["refused"]["message"]
    assert {"option": "return_to", "to": "RUNNING"} in details["instead"]
    move(p, wid, "RUNNING")
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    assert show(p, wid)["state"] == "VERIFY_PENDING"
    assert_control_invariants(p)


def test_a_non_mutating_return_to_a_gated_phase_takes_the_direct_edge_instead(tmp_path):
    """A non-mutating Ticket's gate guards have no query form, so its return to REVIEW_PENDING or VERIFY_PENDING
    cannot be rechecked and is refused. The named path reaches the phase: back to RUNNING (no gate), then the Lead's
    direct edge, which runs this kind's own guard. A restore to RUNNING is admitted."""
    p = sample_project(tmp_path)
    reviewed = create_investigation(p, tmp_path, cls=2, title="Reviewed look")
    p.lead("work", "staff", reviewed, "--review", "code_reviewer")
    verified = create_investigation(p, tmp_path, cls=2, title="Verified look")
    p.lead("work", "staff", verified, "--verify", "verifier")
    for wid, gated in ((reviewed, "REVIEW_PENDING"), (verified, "VERIFY_PENDING")):
        role, _ = dispatch(p, wid)
        p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
        move(p, wid, "ESCALATED")
        move(p, wid, "RUNNING")  # the restore
        p.lead("work", "transition", wid, "--to", gated)
        move(p, wid, "ESCALATED")
        details = refused(p, wid, gated, "entry_guard_not_queryable")
        assert {"option": "return_to", "to": "RUNNING", "then": gated} in details["instead"]
        move(p, wid, "RUNNING")
        p.lead("work", "transition", wid, "--to", gated)
        assert show(p, wid)["state"] == gated
    assert_control_invariants(p)


def test_a_return_beyond_the_phase_left_names_the_phases_it_may_enter(tmp_path):
    """A return from escalation goes no later than the phase the unit left: the refusal names the phases it may enter
    now, and the named return is taken, then the Lead's own entry (a reconcile's bound: test_workspaces)."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    move(p, wid, "ESCALATED")
    details = refused(p, wid, "REVIEW_PENDING", "beyond_the_phase_left")
    assert {"option": "return_to", "to": "RUNNING"} in details["instead"]
    move(p, wid, "RUNNING")
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    assert show(p, wid)["state"] == "REVIEW_PENDING"
    assert_control_invariants(p)


def _attempt(engine: Engine, p: Any, wid: str, to: str) -> tuple[str, str | None, dict[str, Any] | None, str | None]:
    """Ask the transition's guard, then execute it on the same state: the same answer either way (M4-E E4).
    Returns (``admitted`` or the code, the reason code, the refusal's details, its message)."""
    answer = engine.guard_query("work.transition", wid, {"to": to, "reason": "r"})
    rev = engine.store.read()["revision"]
    try:
        engine.work_transition(token=p.token, expect_rev=rev, work_id=wid, to=to, reason="r")
    except AEWError as exc:
        assert answer["availability"] == BLOCKED, (to, answer, exc.message)
        [blocker] = answer["blocking_conditions"]
        assert (blocker["code"], blocker["message"]) == (exc.code, exc.message)
        assert engine.store.read()["revision"] == rev
        return exc.code, exc.details.get("reason"), dict(exc.details), exc.message
    assert answer["availability"] == AVAILABLE, (to, answer)
    return "admitted", None, None, None


def test_every_escalation_return_meets_what_the_phase_it_enters_requires(tmp_path):
    """Every (origin, target) pair the transition table allows through ESCALATED, for both Ticket kinds, on a unit
    whose gates are not met. Each return answers as the Lead's own entry into the target would, run through the real
    transition: from the origin where the table has that direct edge, else from the phase the gates choose (a
    non-mutating Ticket's gated entries cannot be rechecked: refused). A refused return names the guard of that entry,
    with that entry's own refusal. The guard's query equals its execution."""
    p = sample_project(tmp_path)
    units = {MUTATING: create_planned_ticket(p, tmp_path), NON_MUTATING: create_investigation(p, tmp_path)}
    engine = Engine.discover(p.root)
    roles = engine._units.guards.roles()  # pinned to the plan's list both ways (test_engine_composition)
    origins = sorted({s for (s, d) in T.RULES if d == "ESCALATED"})
    targets = sorted({d for (s, d), r in T.RULES.items() if s == "ESCALATED" and r.guard})
    assert len(origins) == 11 and targets == ["REVIEW_PENDING", "RUNNING", "VERIFY_PENDING"]
    seen: set[tuple[str, str | None]] = set()
    for kind, wid in units.items():
        reviewed = any(g.startswith("review_") for g in p.ok("gate", "show", wid)["obligations"]["gates"])
        for origin in origins:
            for to in targets:
                seed(p, lambda s, w=wid, o=origin: s["work"][w].update(state="ESCALATED", escalated_from=o))
                got = _attempt(engine, p, wid, to)
                seen.add((got[0], got[1]))
                if T.PHASE_ORDER.get(to, 99) > T.PHASE_ORDER.get(origin, -1):
                    assert got[:2] == ("GATE_UNSATISFIED", "beyond_the_phase_left"), (kind, origin, to, got)
                    continue
                if T.direct_lead_edge(origin, to) is not None:
                    source, why = origin, "direct_edge_guard_unmet"
                else:
                    entries = [s for (s, d), r in T.RULES.items() if d == to and r.via == "transition" and r.guard
                               and roles[(r.guard, kind)] == GATE]
                    if not entries:
                        assert got[0] == "admitted", (kind, origin, to, got)
                        continue
                    if kind == NON_MUTATING:
                        assert got[:2] == ("GATE_UNSATISFIED", "entry_guard_not_queryable"), (kind, origin, to, got)
                        continue
                    source = entries[0] if len(entries) == 1 else ("REVIEW_PASSED" if reviewed else "RUNNING")
                    why = "entry_guard_unmet"
                seed(p, lambda s, w=wid, o=source: s["work"][w].update(state=o))
                direct = _attempt(engine, p, wid, to)
                if direct[0] == "admitted":
                    assert got[0] == "admitted", (kind, origin, to, got)
                else:
                    assert got[:2] == ("GATE_UNSATISFIED", why) and got[2] is not None, (kind, origin, to, got, direct)
                    refusal = got[2]["refused"]
                    assert (got[2]["guard"], refusal["code"], refusal["message"]) == (
                        T.RULES[(source, to)].guard, direct[0], direct[3]), (kind, origin, to, got, direct)
    assert {("admitted", None), ("GATE_UNSATISFIED", "beyond_the_phase_left"),
            ("GATE_UNSATISFIED", "direct_edge_guard_unmet"), ("GATE_UNSATISFIED", "entry_guard_unmet"),
            ("GATE_UNSATISFIED", "entry_guard_not_queryable")} <= seen


def test_a_return_with_no_guard_to_recheck_is_refused_and_names_one_that_has(tmp_path, monkeypatch):
    """Fail closed (R1-D2: an unqualified return is refused): a return to a phase whose entry guard has no role for the
    unit's kind, or whose Lead entries have no guard at all, is refused. Neither arises in today's table (the role test
    holds every entry's role); the first is planted in the guard table, the second in the transition table (the
    Lead's own edge RUNNING -> REVIEW_PENDING dropped, so only the hub's own return enters the phase), and the named
    return is taken."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    engine = Engine.discover(p.root)
    guards, role_of = engine._units.guards, engine._units.guards.role_of
    plants = {
        "entry_guard_unclassified": lambda: monkeypatch.setattr(
            guards, "role_of", lambda name, unit: None if name == "ready_for_review" else role_of(name, unit)),
        "no_entry_guard": lambda: monkeypatch.delitem(T.RULES, ("RUNNING", "REVIEW_PENDING")),
    }
    for reason, plant in plants.items():
        p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        move(p, wid, "ESCALATED")
        plant()
        code, why, details, _ = _attempt(engine, p, wid, "REVIEW_PENDING")
        assert (code, why) == ("GATE_UNSATISFIED", reason) and details is not None, (code, why, details)
        assert {"option": "return_to", "to": "RUNNING"} in details["instead"]
        engine.work_transition(token=p.token, expect_rev=engine.store.read()["revision"], work_id=wid, to="RUNNING",
                               reason="the named return")
        assert show(p, wid)["state"] == "RUNNING"
        monkeypatch.undo()
    assert_control_invariants(p)


def test_a_direct_edge_guard_with_no_query_form_still_decides_the_return_and_the_reconcile(tmp_path, monkeypatch):
    """Where the guard of the Lead's direct edge has no query form for the unit's kind, a return through it (or a
    reconcile) cannot be answered beforehand, and its transaction runs that guard itself: refused without the
    findings, admitted with them. Planted: the mutating kind's `findings_recorded` query removed from the guard
    table."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid, disposition="changes_required"))
    move(p, wid, "ESCALATED")
    engine = Engine.discover(p.root)
    monkeypatch.delitem(engine._units.guards._queries, ("findings_recorded", MUTATING))

    def attempt(op: Any) -> AEWError | None:
        rev = engine.store.read()["revision"]
        try:
            op(token=p.token, expect_rev=rev, work_id=wid, to="RUNNING", reason="the operator answered")
        except AEWError as exc:
            assert engine.store.read()["revision"] == rev
            return exc
        return None

    assert engine.guard_query("work.transition", wid, {"to": "RUNNING", "reason": "r"})["availability"] == UNKNOWN
    for op, hub in ((engine.work_transition, "ESCALATED"), (engine.work_reconcile, "INTERRUPTED")):
        seed(p, lambda s, h=hub: s["work"][wid].update(state=h, findings=[], **{
            "escalated_from" if h == "ESCALATED" else "interrupted_from": "REVIEW_FAILED"}))
        exc = attempt(op)
        assert exc is not None and exc.code == "GATE_UNSATISFIED", (hub, exc)
        assert "requires recorded review findings" in exc.message, (hub, exc.message)
        # Planted control: with an open required finding, the guard admits the same move.
        seed(p, lambda s: s["work"][wid].update(findings=[{**REQUIRED_FINDING[0], "status": "open"}]))
        assert attempt(op) is None and show(p, wid)["state"] == "RUNNING", hub
    assert_control_invariants(p)


def test_a_reconcile_meets_the_guard_of_the_direct_edge_it_stands_for(tmp_path):
    """A reconcile from INTERRUPTED back to a phase the Lead's direct edge from the interrupted phase enters meets that
    edge's guard. The pairs are read from the table (today one: REVIEW_FAILED -> RUNNING, `findings_recorded`). The
    named path is taken: replan, and the work starts again."""
    def guarded(o: str, t: str) -> bool:
        rule = T.direct_lead_edge(o, t)
        return rule is not None and rule.guard is not None

    pairs = sorted((o, t) for (o, d) in T.RULES if d == "INTERRUPTED"
                   for (h, t), r in T.RULES.items() if h == "INTERRUPTED" and r.via == "reconcile"
                   and T.PHASE_ORDER.get(t, 99) <= T.PHASE_ORDER.get(o, -1) and guarded(o, t))
    assert pairs == [("REVIEW_FAILED", "RUNNING")]
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    for origin, to in pairs:
        seed(p, lambda s, o=origin: s["work"][wid].update(state="INTERRUPTED", interrupted_from=o))
        details = refused(p, wid, to, "direct_edge_guard_unmet", verb=("work", "reconcile"))
        assert details["guard"] == T.direct_lead_edge(origin, to).guard
        assert {"option": "leave_to", "to": ["CANCELLED", "ESCALATED", "REPLAN_REQUIRED"]} in details["instead"]
        # Planted control: with an open required finding the same reconcile is admitted.
        seed(p, lambda s: s["work"][wid].update(findings=[{**REQUIRED_FINDING[0], "status": "open"}]))
        p.lead("work", "reconcile", wid, "--to", to, "--reason", "inspected: the findings stand")
        assert show(p, wid)["state"] == to
    # The named path from a refusal, taken: replan, and the work runs again.
    seed(p, lambda s: s["work"][wid].update(state="INTERRUPTED", interrupted_from="REVIEW_FAILED", findings=[]))
    refused(p, wid, "RUNNING", "direct_edge_guard_unmet", verb=("work", "reconcile"))
    move(p, wid, "REPLAN_REQUIRED")
    plan = Path(tmp_path / "replan.md")
    plan.write_text("1. Redo the change with the findings in hand.\n", encoding="utf-8")
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), "--affected", "calc/core.py",
           "--reason", "replanned after the interruption")
    p.lead("plan", "accept", wid, "--revision", str(len(show(p, wid)["plans"])))
    assign(p, wid)
    assert show(p, wid)["state"] == "RUNNING"
