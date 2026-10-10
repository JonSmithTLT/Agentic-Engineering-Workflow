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
