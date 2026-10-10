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
    answer = engine.guard_query(primitive, work_id, dict(args))
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
