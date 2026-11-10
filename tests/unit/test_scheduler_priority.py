"""A Ticket's scheduling priority (register E227): the order the steering loop's ``select`` takes Tickets in, the
levels' one owner, the Ticket field registry's step to v2, and how `status` shows it. The engine-backed draft, CLI and
status paths are in ``tests/integration/test_ticket_priority_draft.py``."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from test_ticket_digests import record_text, world

from aew.engine import priority as PRIORITY
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


def test_a_dependency_inherited_from_a_story_counts_as_what_the_ticket_unblocks():
    state = {"work": {"T-0001": ticket(), "T-0002": ticket(),
                      "S-0001": ticket("PLANNING", kind="story", depends_on=["T-0002"]),
                      "T-0003": ticket("BLOCKED", parent="S-0001")}}
    # the Story's own edge and its Ticket's inherited one: two live units wait on T-0002
    assert PRIORITY.unblocks(state)["T-0002"] == 2
    assert picked([ready("T-0001"), ready("T-0002")], state) == "T-0002"


def test_a_low_ticket_starts_only_when_no_critical_or_normal_one_is_eligible():
    state = {"work": {"T-0001": ticket(level="critical"), "T-0002": ticket(), "T-0003": ticket(level="low")}}
    assert picked([blocked("T-0001"), ready("T-0002"), ready("T-0003")], state) == "T-0002"
    assert picked([blocked("T-0001"), blocked("T-0002"), ready("T-0003")], state) == "T-0003"
    stop = L.select({}, [blocked("T-0001"), blocked("T-0002"), blocked("T-0003")], PRIORITY.order(state))
    assert isinstance(stop, Stop) and stop.subject == "T-0001"  # with none eligible, the first stop in that order


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
    assert list(PRIORITY.LEVELS) == owned == contract.PRIORITY_LEVELS
    assert PRIORITY.DEFAULT in PRIORITY.LEVELS
    draft = contract.tool("ticket_draft")
    assert draft is not None and draft.input_schema["properties"]["priority"] == {"enum": owned}
    assert "priority" not in draft.input_schema.get("required", [])
    # a Lead judgment, never auto-run: the draft that sets it stays judgment-bearing
    assert draft.base_class == contract.JUDGMENT_BEARING


# ---------------------------------------------------------------------------------------------- the registry step


def test_registry_v2_adds_only_a_group_that_is_not_material():
    v1, v2 = TF.load_registry(1), TF.load_registry(2)
    assert TF.load_registry() == v2 and v2.predecessor == v1.identity
    assert TF._registry_delta(v1, v2) == {"scheduling"}
    assert v2.groups["scheduling"] is False and TF.material({"scheduling"}, registry=v2) == frozenset()


def test_a_ticket_digested_under_v1_has_no_material_change_under_v2_and_its_priority_never_stales_it():
    text = record_text()
    state = world(text)
    before = TF.live_digests(state, "T-0001", text, registry=TF.load_registry(1))
    after = TF.live_digests(state, "T-0001", text)
    assert TF.material(TF.changed_groups(before, after)) == frozenset()
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


def test_the_generated_current_page_shows_the_priority_but_no_age_so_it_stays_a_function_of_the_state():
    assert " T-0001   Add subtract()  [low: nice to have]" in work_graph_lines(graph_state("low"))


@pytest.mark.parametrize(("seconds", "shown"), [(59, "0m"), (3599, "59m"), (3600, "1h"), (86399, "23h"),
                                                (86400, "1d")])
def test_a_lows_age_is_whole_days_else_hours_else_minutes(seconds, shown):
    created = (NOW - dt.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert PRIORITY.age({"created_at": created}, NOW) == shown
    assert PRIORITY.age({"created_at": "not a time"}, NOW) is None
