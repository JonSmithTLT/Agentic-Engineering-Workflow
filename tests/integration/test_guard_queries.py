"""Queryable transition and ingest guards against real projects (M4-E E4; plan v3 E4 and §6; idea note §13).

Each migrated guard is a pure query that its own execute path calls first, so a query equals the execution by
construction. These tests check it anyway, per guard, on seeded states (``test_guard_query_matches_execute``): the
query is asked on the committed state, then the primitive is executed on that same state; an AVAILABLE answer must
commit, and a BLOCKED one must be refused with exactly the blocker's code, message and details, committing nothing.
They also check what the queries are for: a stage's availability composed per step, ``explain`` per stage, and the
guard recheck ``resume`` reports for an unfinished stage."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project
from guard_reads import GUARD_READS, RecordingArgs

from aew.engine.api import Engine
from aew.engine.guards import AVAILABLE, BLOCKED, UNKNOWN
from aew.errors import AEWError
from aew.surface import projection
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()


@pytest.fixture(autouse=True)
def _fresh_cache():
    projection.clear_cache()
    yield
    projection.clear_cache()


def equivalent(engine: Engine, primitive: str, work_id: str | None, args: dict[str, Any],
               execute: Callable[[int], Any]) -> dict[str, Any]:
    """Ask ``primitive``'s guard on the committed state, then execute it there: the same answer (§13). The query reads
    only the arguments ``GUARD_READS`` lists for it (the planner agreement check relies on that list)."""
    recorded = RecordingArgs(args)
    answer = engine.guard_query(primitive, work_id, recorded)
    assert recorded.inputs_read() <= GUARD_READS[primitive], (primitive, recorded.inputs_read())
    args.update(recorded.data())  # keeps what the query found
    rev = engine.store.read()["revision"]
    try:
        execute(rev)
    except AEWError as exc:
        assert answer["availability"] == BLOCKED, (answer, exc.code, exc.message)
        [blocker] = answer["blocking_conditions"]
        assert (blocker["code"], blocker["message"], blocker.get("details", {})) == (
            exc.code, exc.message, dict(exc.details))
        assert engine.store.read()["revision"] == rev  # a refusal commits nothing
        return answer
    assert answer["availability"] == AVAILABLE, answer
    return answer


@pytest.fixture
def ready(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    return p, wid, Engine.discover(p.root)


def test_explain_answers_a_stage_per_step_from_its_guards(ready):
    """`explain` with a stage: each step's guard, with what it takes as produced by earlier steps (M4-E E4)."""
    p, wid, engine = ready
    out = R.run_tool(engine, CTX, "explain", {"stage": "ticket_start", "work_id": wid})
    assert out["ok"] and out["completed_steps"] == [] and out["revision"] == p.rev()
    result = out["result"]
    assert result["stage"] == "ticket_start" and [s["primitive"] for s in result["steps"]] == [
        "work.assign", "dispatch.launch", "work.transition"]
    assert result["steps"][0]["availability"] == AVAILABLE  # the assignment's dispatch decision
    assert result["steps"][1]["covered_by"] == 1  # the launch is the assignment's
    assert result["steps"][2]["produced_by"] == {"state": 1, "implementer": 1}
    prepare = R.run_tool(engine, CTX, "explain", {"stage": "ticket_prepare", "work_id": wid,
                                                  "arguments": {"verification_evidence": "EV-0001"}})["result"]
    assert prepare["availability"] == BLOCKED and prepare["steps"][0]["reason_codes"] == ["NOT_FOUND"]  # E4b


# ---------------------------------------------------------------------------------------------- work.transition


def _transition(engine: Engine, p: Any, wid: str, to: str, reason: str | None = None) -> Callable[[int], Any]:
    return lambda rev: engine.work_transition(token=p.token, expect_rev=rev, work_id=wid, to=to, reason=reason)


def test_guard_query_matches_execute_work_transition_and_implementer_active(ready):
    """`work.transition` (the table, the reason, the unit's kind) and ASSIGNED -> RUNNING's `implementer_active`."""
    p, wid, engine = ready
    story = p.lead("work", "create", "story", "--title", "a story", "--class", "1")["id"]
    for target, to, reason, code in ((wid, "RUNNING", None, "ILLEGAL_TRANSITION"),  # READY -> RUNNING: no such edge
                                     (wid, "CANCELLED", None, "USAGE"),  # needs a reason
                                     (wid, "CANCELLED", "  ", "USAGE"),
                                     (story, "CANCELLED", "no", "ILLEGAL_TRANSITION"),  # a Story's state is derived
                                     ("T-0099", "RUNNING", None, "NOT_FOUND")):
        answer = equivalent(engine, "work.transition", target, {"to": to, "reason": reason},
                            _transition(engine, p, target, to, reason))
        assert answer["reason_codes"] == [code], (target, to, answer)
    assigned = p.lead("work", "assign", wid)
    p.lead("invoke", "cancel", assigned["invocation"], "--reason", "seed: no active implementer")
    answer = equivalent(engine, "work.transition", wid, {"to": "RUNNING"}, _transition(engine, p, wid, "RUNNING"))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"] and "no active implementer" in (
        answer["blocking_conditions"][0]["message"])
    p.lead("invoke", "create", wid, "--role", "implementer")
    equivalent(engine, "work.transition", wid, {"to": "RUNNING"}, _transition(engine, p, wid, "RUNNING"))
    assert p.ok("work", "show", wid)["control"]["state"] == "RUNNING"


def test_a_kind_whose_guard_has_no_query_is_unknown_and_still_executes(tmp_path):
    """A non-mutating Ticket replaces `implementer_active` with its own guard, not migrated: its ASSIGNED -> RUNNING
    is UNKNOWN (never answered by the mutating Ticket's query), and the transition still runs its own guard. Its
    review ingest is its own kind's, not migrated either."""
    from aewflow import create_investigation

    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    p.lead("work", "dispatch", wid)
    engine = Engine.discover(p.root)
    answer = engine.guard_query("work.transition", wid, {"to": "RUNNING"})
    assert answer["availability"] == UNKNOWN and answer["not_queryable"] == "implementer_active"
    engine.work_transition(token=p.token, expect_rev=p.rev(), work_id=wid, to="RUNNING")
    assert engine.store.read()["work"][wid]["state"] == "RUNNING"
    # Its ingest is another kind's too (the KindRegistry selects it): not migrated, UNKNOWN.
    ingest = engine.guard_query("review.ingest", wid, {"evidence": "EV-0001"})
    assert ingest["availability"] == UNKNOWN and ingest["not_queryable"] == "review.ingest"


def test_ticket_start_is_composed_from_the_assignment_and_the_transition_it_produces(ready):
    """Step 3's guard (`implementer_active`) reads what step 1 produces (the ASSIGNED state and an active
    implementer): taken as satisfied, so the stage is the assignment's decision, AVAILABLE, never UNKNOWN."""
    p, wid, engine = ready
    out = R.run_tool(engine, CTX, "status", {"work_id": wid})
    [start] = [a for a in out["projection"]["actions"] if a["action"] == "ticket_start"]
    assert start["availability"] == AVAILABLE and not start["auto_runnable"]  # not built until E5a
    explained = R.run_tool(engine, CTX, "explain", {"stage": "ticket_start", "work_id": wid})["result"]
    assert [s["availability"] for s in explained["steps"]] == [AVAILABLE] * 3
    assert engine.store.read()["work"][wid]["state"] == "READY"  # asking changed nothing


def test_guard_query_matches_execute_ready_for_review(ready):
    """RUNNING -> REVIEW_PENDING (`ready_for_review`): refused while the implementation is unreported, then allowed
    and committed with its effect (the relied-on evidence pinned, the implementer completed)."""
    from aewflow import assign, implement

    p, wid, engine = ready
    impl = assign(p, wid)
    answer = equivalent(engine, "work.transition", wid, {"to": "REVIEW_PENDING"},
                        _transition(engine, p, wid, "REVIEW_PENDING"))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"] and "unmet" in answer["blocking_conditions"][0]["details"]
    review = R.run_tool(engine, CTX, "status", {"work_id": wid})["projection"]["actions"][0]
    assert review["action"] == "ticket_request_review" and review["availability"] == BLOCKED
    implement(impl)
    projection.clear_cache()
    review = R.run_tool(engine, CTX, "status", {"work_id": wid})["projection"]["actions"][0]
    assert review["availability"] == AVAILABLE and not review["auto_runnable"]  # not built until E5b
    equivalent(engine, "work.transition", wid, {"to": "REVIEW_PENDING"}, _transition(engine, p, wid, "REVIEW_PENDING"))
    control = p.ok("work", "show", wid)["control"]
    assert control["state"] == "REVIEW_PENDING" and control["evidence"]  # the effect ran after the query passed


# ---------------------------------------------------------------------------------------------- review.ingest


def _ingest(engine: Engine, p: Any, wid: str, evidence: str) -> Callable[[int], Any]:
    return lambda rev: engine.review_ingest(token=p.token, expect_rev=rev, work_id=wid, evidence_id=evidence)


@pytest.fixture
def implemented(ready):
    """A RUNNING Ticket whose implementation is reported, ready to go to review."""
    from aewflow import assign, implement

    p, wid, engine = ready
    impl = assign(p, wid)
    implement(impl)
    return p, wid, engine, impl


def test_guard_query_matches_execute_review_ingest(implemented):
    """`review.ingest`: the Ticket is REVIEW_PENDING and the report is a known review of it (a finding it resolves that
    is unknown is refused at submission already); then the report is accepted, and the state its outcome implies and
    the reference it pins are what the query predicted."""
    from aewflow import review

    p, wid, engine, _impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    assert equivalent(engine, "review.ingest", wid, {"evidence": "EV-9999"},
                      _ingest(engine, p, wid, "EV-9999"))["reason_codes"] == ["NOT_FOUND"]
    first, second = review(p, wid), review(p, wid)
    args: dict[str, Any] = {"evidence": first}
    equivalent(engine, "review.ingest", wid, args, _ingest(engine, p, wid, first))
    assert args["found"]["to"] == engine.store.read()["work"][wid]["state"] == "REVIEW_PASSED"
    assert args["found"]["ref"] in engine.store.read()["work"][wid]["evidence"]  # what the ingest pinned
    answer = equivalent(engine, "review.ingest", wid, {"evidence": second}, _ingest(engine, p, wid, second))
    assert answer["reason_codes"] == ["ILLEGAL_TRANSITION"] and "not REVIEW_PENDING" in (
        answer["blocking_conditions"][0]["message"])


def test_a_review_that_is_not_one_is_refused_alike(implemented):
    p, wid, engine, impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    report = p.ok("work", "show", wid)["control"]["evidence"][-1]["id"]  # the implementation report it relied on
    answer = equivalent(engine, "review.ingest", wid, {"evidence": report}, _ingest(engine, p, wid, report))
    assert answer["reason_codes"] == ["ILLEGAL_TRANSITION"] and "is not a review" in (
        answer["blocking_conditions"][0]["message"])


# ---------------------------------------------------------------------------------------------- review_current


def test_guard_query_matches_execute_review_current(implemented):
    """REVIEW_PASSED -> VERIFY_PENDING (`review_current`): refused while the workspace differs from what was reviewed,
    allowed again once it holds the reviewed snapshot."""
    from aewflow import SUBTRACT_PATCH, review

    p, wid, engine, impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "# an unreviewed edit\n"})
    answer = equivalent(engine, "work.transition", wid, {"to": "VERIFY_PENDING"},
                        _transition(engine, p, wid, "VERIFY_PENDING"))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"] and "REVIEW_PASSED -> VERIFY_PENDING" in (
        answer["blocking_conditions"][0]["message"])
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"]})  # the reviewed snapshot again
    equivalent(engine, "work.transition", wid, {"to": "VERIFY_PENDING"}, _transition(engine, p, wid, "VERIFY_PENDING"))
    assert engine.store.read()["work"][wid]["state"] == "VERIFY_PENDING"


def _verification_stage(engine: Engine, wid: str, evidence: str) -> dict[str, Any]:
    return R.run_tool(engine, CTX, "explain", {"stage": "ticket_request_verification", "work_id": wid,
                                              "arguments": {"review_evidence": evidence}})["result"]


def test_ticket_request_verification_is_composed_from_the_ingest_and_what_it_produces(implemented):
    """Accepting a passing review: step 2's guard sees the REVIEW_PASSED state and the pinned report step 1 produces,
    and step 3's verifier decision the VERIFY_PENDING state step 2 produces. The stage is AVAILABLE, and never
    auto-runnable: it is judgment-bearing (m2)."""
    from aewflow import review

    p, wid, engine, _impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    report = review(p, wid)
    found = _verification_stage(engine, wid, report)
    assert found["availability"] == AVAILABLE, found
    assert [s["availability"] for s in found["steps"]] == [AVAILABLE] * 4
    assert found["steps"][1]["produced_by"] == {"state": 1, "evidence": 1}
    assert engine.store.read()["work"][wid]["state"] == "REVIEW_PENDING"  # asking changed nothing
    # The primitives the stage would run, run directly, agree with each step's answer.
    engine.review_ingest(token=p.token, expect_rev=p.rev(), work_id=wid, evidence_id=report)
    engine.work_transition(token=p.token, expect_rev=p.rev(), work_id=wid, to="VERIFY_PENDING")
    assert p.lead("invoke", "create", wid, "--role", "verifier")["role"] == "verifier"


def test_a_failing_review_blocks_the_verification_stage_where_it_would_stop(implemented):
    """A review that fails: its ingest is legal (step 1), but the state it produces, REVIEW_FAILED, has no edge to
    VERIFY_PENDING, so the stage is BLOCKED at step 2, exactly where running it would stop (rule 3)."""
    from aewflow import review

    p, wid, engine, _impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    report = review(p, wid, disposition="changes_required",
                    findings=[{"id": "F1", "severity": "major", "summary": "missing test", "required": True}])
    found = _verification_stage(engine, wid, report)
    assert found["availability"] == BLOCKED and [s["availability"] for s in found["steps"][:2]] == [
        AVAILABLE, BLOCKED]
    assert found["steps"][1]["reason_codes"] == ["ILLEGAL_TRANSITION"]
    engine.review_ingest(token=p.token, expect_rev=p.rev(), work_id=wid, evidence_id=report)
    with pytest.raises(AEWError) as refused:
        engine.work_transition(token=p.token, expect_rev=p.rev(), work_id=wid, to="VERIFY_PENDING")
    assert refused.value.code == "ILLEGAL_TRANSITION"


# ---------------------------------------------------------------------------------------------- work.create

DRAFT = {"kind": "ticket", "title": "Add multiply()", "risk_class": 1, "scope_paths": ["calc/**", "tests/**"],
         "goal_backwards": ["multiply(2, 3) == 6"], "contract": ["changes stay in calc/ and tests/"]}


def _create(engine: Engine, p: Any, fields: dict[str, Any]) -> Callable[[int], Any]:
    return lambda rev: engine.work_create(token=p.token, expect_rev=rev, **fields)


@pytest.mark.parametrize(("change", "code"), [
    ({"kind": "task"}, "USAGE"),
    ({"risk_class": 5}, "USAGE"),
    ({"scope_paths": ["calc/**,tests/**"]}, "USAGE"),  # the scope lint (M3-D9)
    ({"class0_assertions": ["inputs_complete"]}, "USAGE"),  # only with class 0
    ({"parent": "S-0099"}, "NOT_FOUND"),
    ({"depends_on": ["T-0099"]}, "NOT_FOUND"),
    ({"title": "  "}, "USAGE"),  # a blank title (PR #170 review, finding 2)
    ({"card": "code_reviewer"}, "USAGE"),  # a reviewer card cannot fill the execute slot
    ({"card": "no_such_card"}, "NOT_FOUND"),
])
def test_guard_query_matches_execute_work_create_refusals(ready, change, code):
    p, _wid, engine = ready
    fields = {**DRAFT, **change}
    before = engine.store.read()["counters"]
    assert equivalent(engine, "work.create", None, dict(fields), _create(engine, p, fields))["reason_codes"] == [code]
    assert engine.store.read()["counters"] == before


def test_guard_query_matches_execute_work_create(ready):
    """The query drafts the unit on a copy (the counter, the graph and the record untouched) and names the id the
    creation then takes."""
    p, wid, engine = ready
    args = dict(DRAFT, depends_on=[wid])
    before = engine.store.read()
    equivalent(engine, "work.create", None, args, _create(engine, p, {**DRAFT, "depends_on": [wid]}))
    created = args["found"]["work_id"]
    assert created not in before["work"] and created in engine.store.read()["work"]
    assert args["found"]["unit"]["depends_on"] == engine.store.read()["work"][created]["depends_on"]


# ---------------------------------------------------------------------------------------------- plan.propose


def _propose(engine: Engine, p: Any, wid: str, fields: dict[str, Any]) -> Callable[[int], Any]:
    return lambda rev: engine.plan_propose(token=p.token, expect_rev=rev, work_id=wid, **fields)


def test_guard_query_matches_execute_plan_propose(ready):
    """`plan.propose`: a body, a hot unfinished unit, a declared assurance whose cards fill their slots, and the
    reason a revision that supersedes the accepted plan needs."""
    p, wid, engine = ready
    plan = {"body": "1. Revise the approach.\n", "no_assurance": True}
    for target, fields, code in ((wid, {**plan, "body": "  "}, "USAGE"),
                                 ("T-0099", plan, "NOT_FOUND"),
                                 (wid, {**plan, "no_assurance": False}, "USAGE"),  # no assurance declared
                                 (wid, {**plan, "no_assurance": False, "review": ["verifier"]}, "USAGE"),  # wrong slot
                                 (wid, plan, "USAGE")):  # supersedes plan v1 without a reason
        answer = equivalent(engine, "plan.propose", target, dict(fields), _propose(engine, p, target, fields))
        assert answer["reason_codes"] == [code], (fields, answer)
    fields = {**plan, "reason": "the approach changed"}
    equivalent(engine, "plan.propose", wid, dict(fields), _propose(engine, p, wid, fields))
    assert [x["status"] for x in engine.store.read()["work"][wid]["plans"]] == ["accepted", "proposed"]


def test_ticket_draft_is_composed_from_the_creation_and_the_unit_it_produces(ready):
    """The plan step's guard is asked of the unit step 1 would create; nothing is created by asking."""
    p, _wid, engine = ready
    draft = {"title": "Add multiply()", "risk_class": 1, "scope": ["calc/**"], "goal": ["multiply works"]}
    before = engine.store.read()
    ok = R.run_tool(engine, CTX, "explain", {"stage": "ticket_draft", "arguments": {
        **draft, "plan": {"body": "1. Add multiply.\n", "assurance": "none"}}})["result"]
    assert ok["availability"] == AVAILABLE and ok["steps"][1]["produced_by"] == {"unit": 1}
    undeclared = R.run_tool(engine, CTX, "explain", {"stage": "ticket_draft", "arguments": {
        **draft, "plan": {"body": "1. Add multiply.\n", "assurance": {}}}})["result"]
    assert [s["availability"] for s in undeclared["steps"]] == [AVAILABLE, BLOCKED]
    assert undeclared["availability"] == BLOCKED and undeclared["reason_codes"] == ["USAGE"]
    assert engine.store.read()["counters"] == before["counters"] and engine.store.read()["work"] == before["work"]


# ---------------------------------------------------------------------------------------------- resume and R5-1


def test_the_stage_rechecks_ask_the_migrated_guards(ready):
    """`resume`'s guard recheck of an unfinished stage's next step, and R5-1's availability condition, ask the same
    guard (`aew.surface.stage.guard_status`): a migrated one now answers AVAILABLE or BLOCKED, no longer UNKNOWN; one
    with no query form stays UNKNOWN (E3c's `unknown_checks`)."""
    from aew.surface import stage

    p, wid, engine = ready
    assert stage.guard_status(engine, "work.transition", {"work_id": wid, "to": "RUNNING"}) == (
        BLOCKED, ["ILLEGAL_TRANSITION"])
    assert stage.guard_status(engine, "plan.propose", {"work_id": wid, "body": "b", "no_assurance": True,
                                                       "reason": "r"}) == (AVAILABLE, [])
    assert stage.guard_status(engine, "verify.classify", {"work_id": wid}) == (UNKNOWN, ["GUARD_NOT_QUERYABLE"])
    p.lead("work", "assign", wid)
    assert stage.guard_status(engine, "work.transition", {"work_id": wid, "to": "RUNNING"}) == (AVAILABLE, [])


@pytest.mark.parametrize("to", ["RUNNING", "CANCELLED", "ESCALATED"])
def test_guard_query_matches_execute_a_state_hooks_refusal(tmp_path, to):
    """PR #170 review, finding 1: a Ticket left `publishing` by a crash refuses every state change but DONE in its
    `before` state hook; `work.transition`'s query asks the same hook, so it answers BLOCKED where execution refuses."""
    from aewflow import prepare_and_validate, to_commit_ready

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    crashed = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()),
                    env={"AEW_FAULT": "integrate.after_publishing_record"})
    assert crashed.returncode == 86
    engine = Engine.discover(p.root)
    assert engine.store.read()["work"][wid]["integration"]["status"] == "publishing"
    answer = equivalent(engine, "work.transition", wid, {"to": to, "reason": "r"},
                        _transition(engine, p, wid, to, "r"))
    assert answer["reason_codes"] == ["ILLEGAL_TRANSITION"] and "publish" in answer["blocking_conditions"][0]["message"]


def test_a_create_query_missing_its_title_is_a_usage_refusal_not_an_exception(ready):
    """PR #170 review, finding 2: the query is a public answer, asked with whatever a stage stored."""
    _p, _wid, engine = ready
    answer = engine.guard_query("work.create", None, {"kind": "ticket", "risk_class": 1})
    assert answer["availability"] == BLOCKED and answer["reason_codes"] == ["USAGE"]


def test_the_ingest_predicts_reviews_still_pending_as_the_ingest_leaves_them(tmp_path):
    """PR #170 review, finding 4: one outcome function for the prediction and the ingest. A general review accepted
    while a triggered specialist review is outstanding leaves the Ticket REVIEW_PENDING; the query predicts exactly
    that, so the verification stage is BLOCKED at step 2 with the refusal running it meets (ILLEGAL_TRANSITION)."""
    from aewflow import SUBTRACT_PATCH, assign, implement, review

    p = sample_project(tmp_path, guardrails={
        "schema": "aew/guardrails/v1", "protected_paths": ["vendor/**"], "generated_paths": [],
        "ticket_scope_enforcement": True, "dependency_rules": [],
        "review_triggers": [{"name": "security", "paths": ["calc/crypto*.py"]}]})
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid), {**SUBTRACT_PATCH, "calc/crypto_util.py": "KEY_BITS = 256\n"})
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    engine = Engine.discover(p.root)
    general = review(p, wid)
    stage = _verification_stage(engine, wid, general)
    assert [s["availability"] for s in stage["steps"][:2]] == [AVAILABLE, BLOCKED]
    assert stage["steps"][1]["reason_codes"] == ["ILLEGAL_TRANSITION"]
    args: dict[str, Any] = {"evidence": general}
    equivalent(engine, "review.ingest", wid, args, _ingest(engine, p, wid, general))
    assert args["found"]["to"] == engine.store.read()["work"][wid]["state"] == "REVIEW_PENDING"
    with pytest.raises(AEWError) as refused:
        engine.work_transition(token=p.token, expect_rev=p.rev(), work_id=wid, to="VERIFY_PENDING")
    assert refused.value.code == stage["steps"][1]["reason_codes"][0]
    special = review(p, wid, specialty="security")
    args = {"evidence": special}
    equivalent(engine, "review.ingest", wid, args, _ingest(engine, p, wid, special))
    assert args["found"]["to"] == engine.store.read()["work"][wid]["state"] == "REVIEW_PASSED"


def test_a_failing_reviews_predicted_state_is_the_ingests(implemented):
    from aewflow import review

    p, wid, engine, _impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    report = review(p, wid, disposition="changes_required",
                    findings=[{"id": "F1", "severity": "major", "summary": "missing test", "required": True}])
    args: dict[str, Any] = {"evidence": report}
    equivalent(engine, "review.ingest", wid, args, _ingest(engine, p, wid, report))
    unit = engine.store.read()["work"][wid]
    assert args["found"]["to"] == unit["state"] == "REVIEW_FAILED"
    # The outcome function applies the review to a copy: applied again to the ingested unit, it changes nothing.
    again = engine._evidence._review_outcome(engine.store.read(), wid, args["found"]["evidence"])
    assert again[0] == "REVIEW_FAILED" and [f["id"] for f in again[1]] == [f"{report}#F1"]
    assert engine.store.read()["work"][wid]["findings"] == unit["findings"]
    # A waived required finding is not open: the outcome reads it through the same rule the gates do.
    waived = engine.store.read()
    waived["work"][wid]["waivers"] = [{"finding": f"{report}#F1", "reason": "accepted risk"}]
    assert engine._evidence._review_outcome(waived, wid, args["found"]["evidence"])[1] == []


def test_one_read_only_answer_computes_a_gate_context_once_per_state(implemented, monkeypatch):
    """The review's observation: within `Engine.gate_memo` (a query's runner and projection, a stage's composition),
    a gate context asked again of the same control state is reused, a copy each time; an overlaid state is its own
    entry; outside it nothing is reused (an execute path computes its own)."""
    from aew.engine import evidence_ops

    p, wid, _engine, _impl = implemented
    calls: list[str] = []
    real = evidence_ops.Gates._ticket_gate_context

    def counted(self, state, work_id):
        calls.append(work_id)
        return real(self, state, work_id)

    monkeypatch.setattr(evidence_ops.Gates, "_ticket_gate_context", counted)
    engine = Engine.discover(p.root)  # composed after the patch: its kind registry holds `counted`
    state = engine.store.read()
    with engine.gate_memo():
        first = engine.gate_context(state, wid)
        first["gates"].clear()  # a caller's change never reaches the next caller
        again = engine.gate_context(engine.store.read(), wid)
        overlaid = dict(state, work={**state["work"], wid: {**state["work"][wid], "state": "REVIEW_PENDING"}})
        engine.gate_context(overlaid, wid)
    assert len(calls) == 2 and again["gates"]
    engine.gate_context(state, wid)
    assert len(calls) == 3
    calls.clear()
    R.run_tool(engine, CTX, "status", {"work_id": wid})  # RUNNING: the current state, and step 2's overlay
    assert len(calls) == 2


# ------------------------------------------------------------------------------------------ verify.ingest (M4-E E4b)


def _verify_ingest(engine: Engine, p: Any, wid: str, evidence: str, scope: str = "ticket") -> Callable[[int], Any]:
    """The primitive's own execute entry: `verify.ingest` (``ticket``) or `verify.ingest.integration`."""
    return lambda rev: engine.verify_ingest(token=p.token, expect_rev=rev, work_id=wid, evidence_id=evidence,
                                            scope=scope)


@pytest.fixture
def reviewed(implemented):
    """A REVIEW_PASSED Ticket, ready for verification."""
    from aewflow import review

    p, wid, engine, impl = implemented
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    return p, wid, engine, impl


def test_guard_query_matches_execute_verify_ingest(reviewed):
    """`verify.ingest` (Ticket scope): the Ticket is VERIFY_PENDING, the report is a known verification of it, of the
    workspace's current snapshot; then it is accepted, in the state the query predicted."""
    from aewflow import SUBTRACT_PATCH, verify

    p, wid, engine, impl = reviewed
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    review_report = [r["id"] for r in engine.store.read()["work"][wid]["evidence"] if r["kind"] == "review"][-1]
    for evidence, code in (("EV-9999", "NOT_FOUND"), (review_report, "ILLEGAL_TRANSITION")):
        assert equivalent(engine, "verify.ingest", wid, {"evidence": evidence},
                          _verify_ingest(engine, p, wid, evidence))["reason_codes"] == [code]
    report = verify(p, wid)
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "# an unverified edit\n"})
    answer = equivalent(engine, "verify.ingest", wid, {"evidence": report}, _verify_ingest(engine, p, wid, report))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"] and "stale" in answer["blocking_conditions"][0]["message"]
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"]})
    # The integration-scope primitive refuses a Ticket-scope report, on execution as in the query (finding 2).
    wrong = equivalent(engine, "verify.ingest.integration", wid, {"evidence": report},
                       _verify_ingest(engine, p, wid, report, "integration"))
    assert wrong["reason_codes"] == ["ILLEGAL_TRANSITION"]
    assert "ticket-scope" in wrong["blocking_conditions"][0]["message"]
    args: dict[str, Any] = {"evidence": report}
    equivalent(engine, "verify.ingest", wid, args, _verify_ingest(engine, p, wid, report))
    assert args["found"]["to"] == engine.store.read()["work"][wid]["state"] == "VERIFIED"
    answer = equivalent(engine, "verify.ingest", wid, {"evidence": report}, _verify_ingest(engine, p, wid, report))
    assert answer["reason_codes"] == ["ILLEGAL_TRANSITION"] and "not VERIFY_PENDING" in (
        answer["blocking_conditions"][0]["message"])


def test_a_failing_verifications_predicted_state_is_the_ingests(reviewed):
    from aewflow import verify

    p, wid, engine, _impl = reviewed
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    report = verify(p, wid, goal_result="fail")
    args: dict[str, Any] = {"evidence": report}
    equivalent(engine, "verify.ingest", wid, args, _verify_ingest(engine, p, wid, report))
    assert args["found"]["to"] == engine.store.read()["work"][wid]["state"] == "VERIFICATION_FAILED"


def test_guard_query_matches_execute_all_gates_current(reviewed):
    """VERIFIED -> COMMIT_READY (`all_gates_current`): refused while the workspace differs from what the gates were
    met on, allowed again once it holds it; the acceptance recorded is the snapshot the query evaluated."""
    from aewflow import SUBTRACT_PATCH, verify

    p, wid, engine, impl = reviewed
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "# after verification\n"})
    answer = equivalent(engine, "work.transition", wid, {"to": "COMMIT_READY"},
                        _transition(engine, p, wid, "COMMIT_READY"))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"] and "-> COMMIT_READY" in (
        answer["blocking_conditions"][0]["message"])
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"]})
    args: dict[str, Any] = {"to": "COMMIT_READY"}
    equivalent(engine, "work.transition", wid, args, _transition(engine, p, wid, "COMMIT_READY"))
    unit = engine.store.read()["work"][wid]
    assert unit["state"] == "COMMIT_READY" and unit["commit_ready_seq"] == 1
    assert unit["commit_ready_snapshot"] == args["found"]["gate_context"]["snapshot"]


# ------------------------------------------------------------------------------------- integrate.prepare (M4-E E4b)


def _prepare(engine: Engine, p: Any, wid: str) -> Callable[[int], Any]:
    return lambda rev: engine.integrate_prepare(token=p.token, expect_rev=rev, work_id=wid)


def untouched(p: Any) -> Callable[[], None]:
    """A check that asking changed nothing a query must not touch: the control file, the refs, the worktree list, and
    every worktree's (the main one's and each linked one's) own index bytes and files (``git status``, run so that it
    writes no index refresh). A fingerprint writes only a throwaway index in a temporary directory and
    content-addressed objects, as `status` always has (PR #171 review, finding 6)."""
    from pathlib import Path

    from aew.workspace import git

    project = Path(p.root)  # the test's own project repository, never this checkout
    quiet = {"GIT_OPTIONAL_LOCKS": "0"}  # `git status` must not refresh the index it is checking

    def worktree(path: Path) -> tuple[Any, ...]:
        index = Path(git.out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=path))
        return (str(path), index.read_bytes() if index.exists() else b"",
                git.out("status", "--porcelain=v2", "--untracked-files=all", cwd=path, env=quiet))

    def snapshot() -> tuple[Any, ...]:
        listed = git.out("worktree", "list", "--porcelain", cwd=project)
        paths = [Path(line.split(" ", 1)[1]) for line in listed.splitlines() if line.startswith("worktree ")]
        return ((project / ".aew/state/control.yaml").read_bytes(), git.out("show-ref", cwd=project), listed,
                tuple(worktree(path) for path in paths))

    before = snapshot()

    def check() -> None:
        assert snapshot() == before, "a query changed the control state, a ref, a worktree's index or its files"

    return check


def test_guard_query_matches_execute_integrate_prepare(tmp_path):
    """`integrate.prepare`: the queue brought in line and the decision required, on a copy: no lease is granted, no
    custodian started and nothing enqueued by asking. Refused for an unknown Ticket, for one behind an earlier entry
    (FIFO) and for one behind another entry's lease; then the prepare runs."""
    from test_queue import tickets

    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    engine = Engine.discover(p.root)
    check = untouched(p)
    assert equivalent(engine, "integrate.prepare", "T-0099", {},
                      _prepare(engine, p, "T-0099"))["reason_codes"] == ["NOT_FOUND"]
    assert equivalent(engine, "integrate.prepare", second, {},
                      _prepare(engine, p, second))["reason_codes"] == ["QUEUE_ORDER"]
    # The candidate a later step takes as produced: on a deep copy, the lease granted and the candidate bound to the
    # acceptance, nothing merged; the state given is unchanged (M4-E E4b).
    import copy

    state = engine.store.read()
    given = copy.deepcopy(state)
    overlaid = engine.candidate_overlay(state, first)
    assert state == given and overlaid is not None
    assert overlaid["queue"]["lease"]["entry"] == next(q for q, e in overlaid["queue"]["entries"].items()
                                                       if e["work"] == first)
    assert overlaid["work"][first]["integration"]["status"] == "prepared"
    assert engine.candidate_overlay(overlaid, second) is None  # another entry holds the lease
    check()
    equivalent(engine, "integrate.prepare", first, {}, _prepare(engine, p, first))  # takes the lease
    check = untouched(p)
    assert equivalent(engine, "integrate.prepare", second, {},
                      _prepare(engine, p, second))["reason_codes"] == ["LEASE_HELD"]
    check()


def test_ticket_prepare_is_composed_from_the_ingest_the_acceptance_and_the_prepare(reviewed):
    """Accepting a passing verification: step 2 sees the VERIFIED state and pinned report step 1 produces, step 3 the
    COMMIT_READY state and acceptance step 2 produces (the queue entry its commit would make included), and in
    verifier mode step 4 the candidate and lease step 3 produces. The stage is judgment-bearing, so never
    auto-runnable."""
    from aewflow import verify

    p, wid, engine, _impl = reviewed
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    report = verify(p, wid)
    check = untouched(p)
    found = R.run_tool(engine, CTX, "explain", {"stage": "ticket_prepare", "work_id": wid,
                                                "arguments": {"verification_evidence": report}})["result"]
    check()
    assert engine.validation_mode(wid) == "verifier"  # the default policy
    assert [s["availability"] for s in found["steps"]] == [AVAILABLE] * 5, found
    assert found["availability"] == AVAILABLE
    assert found["steps"][2]["produced_by"] == {"evidence": 1, "state": 2, "acceptance": 2}
    # Step 4, the integration verifier's decision, is asked on the candidate and lease step 3 produces (a copy).
    assert found["steps"][3]["produced_by"]["candidate"] == 3 and found["steps"][4]["covered_by"] == 4
    # The primitives the stage would run, run directly, agree with each step's answer.
    p.lead("verify", "ingest", wid, "--evidence", report)
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    p.lead("integrate", "prepare", wid)
    assert p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")["scope"] == "integration"


# ----------------------------------------------------------------------------- verify.ingest.integration (M4-E E4b)


def test_guard_query_matches_execute_verify_ingest_integration(tmp_path):
    """`verify.ingest.integration`: a prepared candidate bound to the acceptance, the entry's live lease, a report of
    the candidate's current snapshot; then the candidate is validated, as the query predicted. The Ticket-scope
    primitive refuses the same report, executed as asked (the `aew verify ingest` command, unscoped, takes either)."""
    from pathlib import Path

    from aewflow import to_commit_ready, verify

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    engine = Engine.discover(p.root)
    report = verify(p, wid, scope="integration")
    # The Ticket-scope primitive refuses it, on execution as in the query (PR #171 review, finding 2).
    wrong = equivalent(engine, "verify.ingest", wid, {"evidence": report}, _verify_ingest(engine, p, wid, report))
    assert wrong["reason_codes"] == ["ILLEGAL_TRANSITION"]
    assert "integration-scope" in wrong["blocking_conditions"][0]["message"]
    candidate = Path(engine.store.read()["work"][wid]["integration"]["workspace"]) / "calc" / "core.py"
    original = candidate.read_text(encoding="utf-8")
    candidate.write_text(original + "# an edit after verification\n", encoding="utf-8", newline="\n")
    check = untouched(p)
    answer = equivalent(engine, "verify.ingest.integration", wid, {"evidence": report},
                        _verify_ingest(engine, p, wid, report, "integration"))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"]
    check()
    candidate.write_text(original, encoding="utf-8", newline="\n")
    args: dict[str, Any] = {"evidence": report}
    equivalent(engine, "verify.ingest.integration", wid, args, _verify_ingest(engine, p, wid, report, "integration"))
    integ = engine.store.read()["work"][wid]["integration"]
    assert args["found"]["integration_status"] == integ["status"] == "validated"
    answer = equivalent(engine, "verify.ingest.integration", wid, {"evidence": report},
                        _verify_ingest(engine, p, wid, report, "integration"))
    assert answer["reason_codes"] == ["ILLEGAL_TRANSITION"] and "no prepared integration candidate" in (
        answer["blocking_conditions"][0]["message"])


# ------------------------------------------------------------------------------------- integrate.publish (M4-E E4b)


def _publish(engine: Engine, p: Any, wid: str) -> Callable[[int], Any]:
    return lambda rev: engine.integrate_publish(token=p.token, expect_rev=rev, work_id=wid)


def test_guard_query_matches_execute_integrate_publish(tmp_path):
    """`integrate.publish`: no candidate; a candidate not yet validated after integration (verifier mode); then the
    publication, AVAILABLE and DONE. The projection's PUBLISH decision carries the same answer."""
    from aewflow import to_commit_ready, verify

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    engine = Engine.discover(p.root)
    check = untouched(p)
    answer = equivalent(engine, "integrate.publish", wid, {}, _publish(engine, p, wid))
    assert answer["reason_codes"] == ["ILLEGAL_TRANSITION"]
    check()
    p.lead("integrate", "prepare", wid)
    check = untouched(p)
    answer = equivalent(engine, "integrate.publish", wid, {}, _publish(engine, p, wid))
    assert answer["reason_codes"] == ["GATE_UNSATISFIED"] and "post-integration verification" in (
        answer["blocking_conditions"][0]["message"])
    check()
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, scope="integration"))
    explained = R.run_tool(engine, CTX, "explain", {"stage": "integration_publish", "work_id": wid,
                                                    "arguments": {"prepared_candidate": "c"}})["result"]
    assert explained["availability"] == AVAILABLE
    args: dict[str, Any] = {}
    equivalent(engine, "integrate.publish", wid, args, _publish(engine, p, wid))
    assert args["found"]["outcome"] == "publish"
    assert engine.status(wid)["work_unit"]["state"] == "DONE"  # hot, or archived as it stands now


def test_a_moved_head_is_blocked_and_the_publish_publishes_nothing(tmp_path):
    """The authoritative head moved under a validated candidate: the query answers BLOCKED (STALE_CANDIDATE,
    outcome `moved_head`); the publish, as before, commits the one rebuild under the same lease and publishes
    nothing."""
    from pathlib import Path

    from aewflow import prepare_and_validate, to_commit_ready

    from aew.workspace import git

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    project = Path(p.root)  # the test's own project repository, never this checkout
    (project / "README.md").write_text("# calc\n\nMoved on.\n", encoding="utf-8", newline="\n")
    git.out("commit", "-q", "-am", "moves the authoritative head", cwd=project)
    engine = Engine.discover(p.root)
    args: dict[str, Any] = {}
    answer = engine.guard_query("integrate.publish", wid, args)
    assert answer["availability"] == BLOCKED and answer["reason_codes"] == ["STALE_CANDIDATE"]
    assert args["found"]["outcome"] == "moved_head"
    # BLOCKED with a disposition: the answer says what the call commits instead (PR #171 review, finding 1), and so do
    # `explain`, the projection's blockers beside the PUBLISH decision, and `resume`'s recheck.
    assert answer["disposition"] == "rebuild"
    assert answer["blocking_conditions"][0]["details"]["disposition"] == "rebuild"
    explained = R.run_tool(engine, CTX, "explain", {"stage": "integration_publish", "work_id": wid,
                                                    "arguments": {"prepared_candidate": "c"}})["result"]
    assert explained["availability"] == BLOCKED and explained["steps"][0]["disposition"] == "rebuild"
    projected = R.run_tool(engine, CTX, "status", {"work_id": wid})["projection"]
    assert any((b.get("details") or {}).get("disposition") == "rebuild" for b in projected["blockers"])
    from aew.surface import stage

    check = stage.guard_check(engine, "integrate.publish", {"work_id": wid})
    assert check["status"] == stage.BLOCKED_WITH_DISPOSITION and "rebuild" in check["message"]
    out = engine.integrate_publish(token=p.token, expect_rev=p.rev(), work_id=wid)
    assert out["ok"] is False and out["rebuilt"] is True
    assert engine.store.read()["work"][wid]["state"] == "COMMIT_READY"  # nothing published


def test_a_superseded_candidate_is_blocked_with_its_requeue(tmp_path):
    """A candidate built for an earlier acceptance: BLOCKED, `STALE_CANDIDATE`, carrying `disposition: requeue`, with
    the details the publish raises after committing the retirement and requeue (the same error, by construction)."""
    from aewflow import prepare_and_validate, to_commit_ready

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    engine = Engine.discover(p.root)
    state = engine.store.read()
    state["work"][wid]["commit_ready_seq"] += 1  # as a later acceptance would leave it (asked on a copy)
    answer = engine.guard_query("integrate.publish", wid, {}, state=state)
    assert answer["availability"] == BLOCKED and answer["disposition"] == "requeue"
    details = answer["blocking_conditions"][0]["details"]
    assert details["disposition"] == "requeue" and details["reason"].startswith("candidate built from an earlier")


def test_the_prepare_and_publish_queries_never_sync_the_state_they_are_given(tmp_path):
    """PR #171 review, finding 4 (its r4): on states where the queue's sync would act (a COMMIT_READY Ticket not yet
    enqueued, as an overlay sees it; a lease whose custodian ended), asking changes nothing of the state passed in, so
    a query that synced in place would fail here."""
    import copy

    from aewflow import to_commit_ready

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    engine = Engine.discover(p.root)
    fresh = engine.store.read()
    fresh["queue"]["entries"].clear()  # not enqueued yet: sync would enqueue it
    before = copy.deepcopy(fresh)
    assert engine.guard_query("integrate.prepare", wid, {}, state=fresh)["availability"] == AVAILABLE
    assert fresh == before, "integrate.prepare's query synced the state it was given"
    engine.guard_query("integrate.publish", wid, {}, state=fresh)
    assert fresh == before, "integrate.publish's query synced the state it was given"
    p.lead("integrate", "prepare", wid)
    leased = engine.store.read()
    custodian = leased["queue"]["lease"]["custodian"]
    leased["invocations"][custodian]["status"] = "cancelled"  # sync would mark the lease for reconciliation
    before = copy.deepcopy(leased)
    answer = engine.guard_query("integrate.publish", wid, {}, state=leased)
    assert answer["reason_codes"] == ["LEASE_RECONCILE_REQUIRED"]  # what the synced copy says
    assert leased == before, "integrate.publish's query synced the state it was given"
    engine.guard_query("integrate.prepare", wid, {}, state=leased)
    assert leased == before, "integrate.prepare's query synced the state it was given"


def test_the_publish_branches_on_the_querys_outcome_alone(tmp_path, monkeypatch):
    """PR #171 review, finding 7: a publish whose query passed without naming an outcome publishes nothing; it is an
    engine defect, refused, with nothing committed (no fall-through to publishing)."""
    from aewflow import to_commit_ready

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    engine = Engine.discover(p.root)
    monkeypatch.setattr(engine._integration, "publish_query", lambda state, work_id, args: None)
    rev = p.rev()
    with pytest.raises(AEWError) as refused:
        engine.integrate_publish(token=p.token, expect_rev=rev, work_id=wid)
    assert refused.value.code == "INTEGRITY_ERROR" and p.rev() == rev
    assert engine.store.read()["work"][wid]["integration"]["status"] == "prepared"
