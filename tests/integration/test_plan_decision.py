"""A plan awaiting acceptance is the operator's PLAN decision (register E351; the kind's name is the operator's ruling
of 2026-11-26), offered like every other decision: in the action projection, with its owner, the command that carries
it out and the operator's confirmation a Lead session's call waits for (#618, ``aew.engine.operator_decisions``).

Each printed step is followed to its outcome (review guide §5): the Lead session's run of the offered command is
refused until the operator confirms with the command the decision names, and then accepts the plan; the operator's own
run of it accepts the plan at once. The steering loop stops on the decision and names it the operator's."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from invariants import assert_control_invariants, load_control
from operator_confirms import confirm

from aew import errors
from aew.engine import operator_decisions as OD
from aew.engine.api import Engine
from aew.harness import lead_broker, steering_loop
from aew.owners import OPERATOR
from aew.schemas import validate_def
from aew.surface import readable
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()


def _ticket(p, title: str = "Add subtract()") -> str:
    return p.lead("work", "create", "ticket", "--title", title, "--class", "1", "--goal", "g",
                  "--scope", "calc/**", "--scope", "tests/**")["id"]


def _propose(p, tmp_path: Path, wid: str, text: str, *extra: str) -> int:
    plan = tmp_path / f"{wid}-{abs(hash(text))}.md"
    plan.write_text(text, encoding="utf-8")
    return p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), "--affected", "calc/core.py",
                  *extra)["revision_number"]


def _status(p, wid: str) -> dict[str, Any]:
    return R.run_tool(Engine.discover(p.root), CTX, "status", {"work_id": wid})


def _plans(p, wid: str) -> list[dict[str, Any]]:
    return [d for d in _status(p, wid)["projection"]["decisions_required"] if d["decision"] == "PLAN"]


def _accepted(p, wid: str) -> int | None:
    return (load_control(p.root)["work"][wid].get("plan") or {}).get("accepted")


def test_a_proposed_plan_is_the_operators_plan_decision_with_its_command_and_the_confirmation_it_waits_for(
        project, tmp_path):
    wid = _ticket(project)
    assert _plans(project, wid) == []  # nothing proposed: proposing is the Lead's work, not a decision
    _propose(project, tmp_path, wid, "1. Add subtract(a, b) to calc/core.py.\n")
    entry = load_control(project.root)["work"][wid]["plans"][0]
    [d] = _plans(project, wid)
    validate_def("surface", "decision", d, source="test")
    assert d["owner"] == OPERATOR and d["availability"] == "AVAILABLE" and d["default"] == "NONE"
    assert d["subject"] == wid and d["evidence"] == [entry["path"]] and d["tool"] is None
    assert d["ask_operator"] == OD.command(OD.PLAN, wid, 1)
    assert d["cli_fallback"] == ["plan", "accept", wid, "--revision", "1", "--approval-digest", entry["sha256"]]


def test_the_lead_sessions_run_of_the_offered_command_waits_for_the_named_confirmation_then_accepts_the_plan(
        project, tmp_path):
    """The printed steps in order: the Lead session runs the offered command and is refused, naming the very command
    the decision names for the operator; the operator confirms with it; the same offered command then accepts the plan,
    and the decision is gone."""
    wid = _ticket(project)
    _propose(project, tmp_path, wid, "1. Add subtract(a, b) to calc/core.py.\n")
    [d] = _plans(project, wid)

    def session() -> dict[str, Any]:
        return lead_broker.run_cli(Engine.discover(project.root), project.token, d["cli_fallback"],
                                   str(project.root), "", channel="lead_broker")

    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        session()
    assert refused.value.details["reason"] == OD.REQUIRED
    assert refused.value.details["ask_operator"] == d["ask_operator"]
    assert _accepted(project, wid) is None and _plans(project, wid) == [d]

    confirm(project.root, "plan", wid, revision=1)  # the endpoint's record of `d["ask_operator"]`, challenge answered
    Engine.discover(project.root).checkpoint(token=project.token, note="Unrelated Lead update")
    assert _plans(project, wid) == [d]
    assert session()["result"]["accepted"] == 1 and _accepted(project, wid) == 1
    assert _plans(project, wid) == []
    assert_control_invariants(project)


def test_the_operators_own_run_of_the_offered_command_accepts_the_plan(project, tmp_path):
    wid = _ticket(project)
    _propose(project, tmp_path, wid, "1. Add subtract(a, b) to calc/core.py.\n")
    [d] = _plans(project, wid)
    assert project.ok(*d["cli_fallback"], env={"AEW_LEAD_TOKEN": project.token})["accepted"] == 1
    assert _accepted(project, wid) == 1 and _plans(project, wid) == [] and not OD.standing(project.root / ".aew")


def test_the_lead_reads_the_plan_decision_as_the_operators_with_the_confirmation_to_ask_for(project, tmp_path):
    """The readable head, the text the Lead's model reads first: the decision is named the operator's, with the
    command the operator confirms with and the call that carries it out, whole. It asks the Lead for no code."""
    wid = _ticket(project)
    _propose(project, tmp_path, wid, "1. Add subtract(a, b) to calc/core.py.\n")
    [d] = _plans(project, wid)
    head = readable.render(_status(project, wid)).split("\n\n" + readable.JSON_MARKER)[0].split("\n")
    accept = "aew " + " ".join(d["cli_fallback"])
    assert head[1] == (f"the operator's decision, PLAN on {wid}; ask the operator to confirm it at their own "
                       f"terminal: {d['ask_operator']}; it is carried out by: {accept}"), head
    assert f"decision: PLAN on {wid}, the operator's (AVAILABLE)" in head, head
    assert "code" not in head[1]


def test_the_steering_loop_stops_on_the_plan_decision_as_the_operators(project, tmp_path):
    """A Ticket whose plan awaits acceptance is never advanced: the loop's stop names the decision the operator's, and
    it is the stop reported over another Ticket's self-clearing BLOCKED (``LEAD_ONLY``)."""
    blocked = _ticket(project, "Not yet planned")  # BLOCKED on no plan, with no decision: a self-clearing stop
    wid = _ticket(project)
    _propose(project, tmp_path, wid, "1. Add subtract(a, b) to calc/core.py.\n")
    engine = Engine.discover(project.root)
    proj, units = steering_loop._project_all(engine, CTX, engine.store.current())
    assert [u["subject"] for u in units] == sorted([blocked, wid])
    stop = steering_loop.select(proj, units)
    assert isinstance(stop, steering_loop.Stop), stop
    assert (stop.code, stop.subject, stop.message) == (steering_loop.DECISION_REQUIRED, wid,
                                                       f"{wid}: PLAN is the operator's")


def test_only_a_revision_plan_accept_would_take_now_is_offered(project, tmp_path):
    """Each revision proposed against the plan accepted now is offered; once another is accepted, a revision proposed
    against the earlier plan is refused by `plan accept` and is no longer offered."""
    wid = _ticket(project)
    _propose(project, tmp_path, wid, "1. First.\n")
    project.lead("plan", "accept", wid, "--revision", "1")
    two = _propose(project, tmp_path, wid, "1. Second.\n", "--reason", "narrower")
    three = _propose(project, tmp_path, wid, "1. Third.\n", "--reason", "wider")
    decisions = _plans(project, wid)
    assert [d["ask_operator"] for d in decisions] == [OD.command(OD.PLAN, wid, n) for n in (two, three)]
    project.lead("plan", "accept", wid, "--revision", str(two))
    assert _plans(project, wid) == []
    res = project.aew(*decisions[-1]["cli_fallback"], env={"AEW_LEAD_TOKEN": project.token})
    assert res.returncode != 0 and res.error["code"] == "ILLEGAL_TRANSITION", res.stderr


def test_a_parents_proposed_plan_is_the_operators_plan_decision_too(project, tmp_path):
    story = project.lead("work", "create", "story", "--title", "Calculator", "--class", "1",
                         "--goal", "g")["id"]
    plan = tmp_path / "story.md"
    plan.write_text("1. Split the work.\n", encoding="utf-8")
    project.lead("plan", "propose", "--assurance", "none", story, "--file", str(plan))
    [d] = _plans(project, story)
    assert d["owner"] == OPERATOR and d["ask_operator"] == OD.command(OD.PLAN, story, 1)


def test_a_revision_proposed_while_the_ticket_is_past_ready_is_offered_only_once_it_is_replan_required(
        project, tmp_path):
    """The state half (review of #628, m1): a replan proposed while the Ticket is ASSIGNED is one `plan accept` refuses,
    so no decision is offered; once the Ticket is REPLAN_REQUIRED, the decision appears and its command accepts it."""
    wid = _ticket(project)
    _propose(project, tmp_path, wid, "1. First.\n")
    project.lead("plan", "accept", wid, "--revision", "1")
    project.lead("work", "assign", wid)  # ASSIGNED, no harness launched
    two = _propose(project, tmp_path, wid, "1. Second.\n", "--reason", "the plan missed a step")
    assert load_control(project.root)["work"][wid]["state"] == "ASSIGNED"
    assert _plans(project, wid) == []
    accept = Engine.discover(project.root).status(wid)["plan_accept_argv"][two]
    res = project.aew(*accept, env={"AEW_LEAD_TOKEN": project.token})
    assert res.returncode != 0 and res.error["code"] == "ILLEGAL_TRANSITION", res.stderr

    project.lead("work", "transition", wid, "--to", "REPLAN_REQUIRED", "--reason", "the plan missed a step")
    [d] = _plans(project, wid)
    assert d["ask_operator"] == OD.command(OD.PLAN, wid, two)
    assert project.ok(*d["cli_fallback"], env={"AEW_LEAD_TOKEN": project.token})["accepted"] == two
    assert _plans(project, wid) == []
    assert_control_invariants(project)
