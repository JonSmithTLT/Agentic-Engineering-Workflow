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
    """Ask ``primitive``'s guard on the committed state, then execute it there: the same answer (§13)."""
    answer = engine.guard_query(primitive, work_id, args)  # keeps what the query found
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
    unmigrated = R.run_tool(engine, CTX, "explain", {"stage": "ticket_prepare", "work_id": wid,
                                                     "arguments": {"verification_evidence": "EV-0001"}})["result"]
    assert unmigrated["availability"] == UNKNOWN and unmigrated["steps"] == []  # E4b migrates it


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
    assert stage.guard_status(engine, "verify.classify", {"work_id": wid})[0] == UNKNOWN
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
