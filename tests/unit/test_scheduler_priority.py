"""A Ticket's scheduling priority (register E227): the order the steering loop's ``select`` takes Tickets in, the
levels' one owner, the Ticket field registry's non-material `scheduling` group, and how `status` shows it. The
engine-backed draft, CLI and status paths are in ``tests/integration/test_ticket_priority_draft.py``."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from test_ticket_digests import record_text, world

from aew import priority_levels
from aew.engine import priority as PRIORITY
from aew.engine import resume_ops
from aew.engine import ticket_fields as TF
from aew.harness import steering_loop as L
from aew.harness.steering_loop import Choice, Stop
from aew.knowledge.render import work_graph_lines
from aew.schemas import schema
from aew.surface import contract

NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)


def ready(subject: str) -> dict[str, Any]:
    """A live Ticket's projection with one eligible action."""
    return {"subject": subject, "actions": [{"action": "ticket_start", "availability": "AVAILABLE",
                                             "auto_runnable": True}]}


def blocked(subject: str) -> dict[str, Any]:
    return {"subject": subject, "actions": [], "blockers": [{"code": "FILES_CONFLICT", "message": "held"}]}


def ticket(state: str = "READY", *, level: str | None = None, depends_on: list[str] = (),  # type: ignore[assignment]
           parent: str | None = None, kind: str = "ticket") -> dict[str, Any]:
    unit: dict[str, Any] = {"kind": kind, "state": state, "parent": parent,
                            "depends_on": [{"id": d, "kind": "mutating"} for d in depends_on]}
    if level is not None:
        unit["priority"] = {"level": level, "reason": f"{level} for the test"}
    return unit


def picked(units: list[dict[str, Any]], state: dict[str, Any]) -> str:
    choice = L.select({}, units, PRIORITY.order(state))
    assert isinstance(choice, Choice), choice
    return choice.subject


# ---------------------------------------------------------------------------------------------- the loop's order


def test_select_takes_critical_before_normal_before_low_whatever_the_ids():
    state = {"work": {"T-0001": ticket(level="low"), "T-0002": ticket(), "T-0003": ticket(level="critical")}}
    units = [ready(w) for w in state["work"]]
    assert picked(units, state) == "T-0003"
    del state["work"]["T-0003"]
    assert picked([ready("T-0001"), ready("T-0002")], state) == "T-0002"  # an unset priority is normal


def test_at_the_same_level_the_ticket_that_unblocks_more_live_units_starts_first_then_the_lower_id():
    state = {"work": {"T-0001": ticket(), "T-0002": ticket(), "T-0003": ticket("BLOCKED", depends_on=["T-0002"]),
                      "T-0004": ticket("BLOCKED", depends_on=["T-0002"]), "T-0005": ticket()}}
    units = [ready("T-0001"), ready("T-0002"), ready("T-0005")]
    assert picked(units, state) == "T-0002"
    state["work"]["T-0003"]["state"] = state["work"]["T-0004"]["state"] = "DONE"  # a finished unit waits on nothing
    assert picked(units, state) == "T-0001"


def test_a_dependency_inherited_from_a_story_counts_its_ticket_not_the_story():
    """E227 counts the Tickets each unblocks: a Story's edge is counted once, through each of its Tickets."""
    state = {"work": {"T-0001": ticket(), "T-0002": ticket(),
                      "S-0001": ticket("PLANNING", kind="story", depends_on=["T-0002"]),
                      "T-0003": ticket("BLOCKED", parent="S-0001")}}
    assert PRIORITY.unblocks(state)["T-0002"] == 1  # T-0003, by the Story's edge; the Story itself is not counted
    assert picked([ready("T-0001"), ready("T-0002")], state) == "T-0002"


def test_the_hierarchy_s_depth_never_changes_the_order():
    """Review of the priority PR, M1: one Ticket waiting through a Story, against one waiting directly, is a tie that
    the id decides; and an Epic over a Story over three Tickets counts three, not five."""
    tie = {"work": {"T-0002": ticket(), "T-0003": ticket(), "T-0004": ticket("BLOCKED", depends_on=["T-0002"]),
                    "S-0001": ticket("PLANNING", kind="story", depends_on=["T-0003"]),
                    "T-0005": ticket("BLOCKED", parent="S-0001")}}
    assert picked([ready("T-0003"), ready("T-0002")], tie) == "T-0002"
    deep = {"work": {"T-0010": ticket(), "T-0011": ticket(),
                     "E-0001": ticket("OPEN", kind="epic", depends_on=["T-0010"]),
                     "S-0001": ticket("PLANNING", kind="story", parent="E-0001"),
                     **{f"T-01{i}": ticket("BLOCKED", parent="S-0001") for i in range(3)},
                     **{f"T-02{i}": ticket("BLOCKED", depends_on=["T-0011"]) for i in range(4)}}}
    assert PRIORITY.unblocks(deep)["T-0010"] == 3 and PRIORITY.unblocks(deep)["T-0011"] == 4
    assert picked([ready("T-0010"), ready("T-0011")], deep) == "T-0011"


def test_a_low_ticket_starts_only_when_no_critical_or_normal_one_is_eligible():
    state = {"work": {"T-0001": ticket(level="critical"), "T-0002": ticket(), "T-0003": ticket(level="low")}}
    assert picked([blocked("T-0001"), ready("T-0002"), ready("T-0003")], state) == "T-0002"
    assert picked([blocked("T-0001"), blocked("T-0002"), ready("T-0003")], state) == "T-0003"
    stop = L.select({}, [blocked("T-0001"), blocked("T-0002"), blocked("T-0003")], PRIORITY.order(state))
    assert isinstance(stop, Stop) and stop.subject == "T-0001"  # with none eligible, the first stop in that order


def decided(subject: str) -> dict[str, Any]:
    """A live Ticket's projection held on a decision only the Lead can make."""
    return {"subject": subject, "actions": [],
            "decisions_required": [{"decision": "plan_acceptance", "evidence": []}]}


def test_with_none_eligible_a_stop_only_the_lead_can_clear_comes_before_a_higher_tickets_blocked():
    """The merge of the priority order with loop_waiting's Lead-only preference (QC3-m1): the order ranks the stops,
    but a stop that waits on the Lead goes ahead of a BLOCKED that can clear on its own, whatever the levels."""
    state = {"work": {"T-0001": ticket(level="low"), "T-0002": ticket(level="critical")}}
    stop = L.select({}, [decided("T-0001"), blocked("T-0002")], PRIORITY.order(state))
    assert isinstance(stop, Stop) and (stop.code, stop.subject) == (L.DECISION_REQUIRED, "T-0001")


def test_among_stops_only_the_lead_can_clear_the_first_in_priority_order_wins_not_the_lowest_id():
    state = {"work": {"T-0001": ticket(level="low"), "T-0002": ticket(), "T-0003": ticket(level="critical")}}
    stop = L.select({}, [decided("T-0001"), blocked("T-0002"), decided("T-0003")], PRIORITY.order(state))
    assert isinstance(stop, Stop) and (stop.code, stop.subject) == (L.DECISION_REQUIRED, "T-0003")


def test_without_an_order_select_keeps_id_order():
    assert L.select({}, [ready("T-0002"), ready("T-0001")]).subject == "T-0001"  # type: ignore[union-attr]


def test_the_loop_ranks_by_the_committed_state_at_each_tick():
    """Both places the loop selects (its tick and its coarse look) rank by the state they read."""
    import inspect

    source = inspect.getsource(L.SteeringLoop)
    assert source.count("select(project, units, PRIORITY.order(state))") == 2


# ---------------------------------------------------------------------------------------------- one owner


def test_the_levels_have_one_owner_the_control_schema():
    owned = schema("control")["$defs"]["work_unit"]["properties"]["priority"]["properties"]["level"]["enum"]
    assert list(priority_levels.LEVELS) == owned == contract.PRIORITY_LEVELS
    assert PRIORITY.LEVELS is priority_levels.LEVELS and PRIORITY.DEFAULT is priority_levels.DEFAULT
    assert PRIORITY.DEFAULT in PRIORITY.LEVELS and PRIORITY.LOWEST == owned[-1]
    draft = contract.tool("ticket_draft")
    assert draft is not None and draft.input_schema["properties"]["priority"] == {"enum": owned}
    assert "priority" not in draft.input_schema.get("required", [])
    # a Lead judgment, never auto-run: the draft that sets it stays judgment-bearing
    assert draft.base_class == contract.JUDGMENT_BEARING


# ---------------------------------------------------------------------------------------------- the registry


def test_the_priority_is_in_v1_s_own_scheduling_group_which_is_not_material():
    """ADR-0016 §1.5 and A-47: before S3 binds evidence to a registry identity, a new group goes into version 1 in
    place (the Lead's ruling on the review's m1)."""
    reg = TF.load_registry()
    assert reg.version == 1 and reg.predecessor is None
    assert reg.groups["scheduling"] is False and TF.material({"scheduling"}, registry=reg) == frozenset()
    assert reg.classifies_control("priority")


def test_a_ticket_s_priority_moves_only_the_scheduling_group_and_never_stales_it():
    text = record_text()
    state = world(text)
    after = TF.live_digests(state, "T-0001", text)
    state["work"]["T-0001"]["priority"] = {"level": "critical", "reason": "a release blocker"}
    moved = TF.changed_groups(after, TF.live_digests(state, "T-0001", text))
    assert moved == {"scheduling"} and TF.material(moved) == frozenset()


# ---------------------------------------------------------------------------------------------- status


def graph_state(level: str | None, *, reason: str | None = "nice to have") -> dict[str, Any]:
    unit = {"kind": "ticket", "state": "READY", "title": "Add subtract()",
            "created_at": (NOW - dt.timedelta(days=3, hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if level is not None:
        unit["priority"] = {"level": level, "reason": reason}
    return {"work": {"T-0001": unit}}


@pytest.mark.parametrize(("level", "line"), [
    (None, " T-0001   Add subtract()"),
    ("normal", " T-0001   Add subtract()"),
    ("critical", " T-0001   Add subtract()  [critical: nice to have]"),
    ("low", " T-0001   Add subtract()  [low, waiting 3d: nice to have]"),
])
def test_status_shows_a_priority_that_is_not_the_default_with_its_reason_and_a_lows_age(level, line):
    assert line in work_graph_lines(graph_state(level), now=NOW)


@pytest.mark.parametrize(("state", "waiting"), [("READY", True), ("BLOCKED", True), ("ASSIGNED", False),
                                                ("RUNNING", False), ("REVIEW_PENDING", False), ("DONE", False),
                                                ("CANCELLED", False)])
def test_only_a_low_ticket_that_has_not_started_is_shown_waiting(state, waiting):
    """Review of the priority PR, m2: a `low` Ticket that started or finished is not waiting, and a finished one's
    status entry carries no age, so the report never grows with history."""
    unit = graph_state("low")["work"]["T-0001"]
    unit["state"] = state
    lines = "\n".join(work_graph_lines({"work": {"T-0001": unit}}, now=NOW))
    assert ("[low, waiting 3d: nice to have]" in lines) is waiting
    assert "[low: nice to have]" in lines or waiting
    assert ("age" in resume_ops._priority(unit)["priority"]) is waiting


def test_the_generated_current_page_shows_the_priority_but_no_age_so_it_stays_a_function_of_the_state():
    assert " T-0001   Add subtract()  [low: nice to have]" in work_graph_lines(graph_state("low"))


@pytest.mark.parametrize(("seconds", "shown"), [(59, "0m"), (3599, "59m"), (3600, "1h"), (86399, "23h"),
                                                (86400, "1d")])
def test_a_lows_age_is_whole_days_else_hours_else_minutes(seconds, shown):
    created = (NOW - dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert PRIORITY.age({"created_at": created}, NOW) == shown
    assert PRIORITY.age({"created_at": "not a time"}, NOW) is None
