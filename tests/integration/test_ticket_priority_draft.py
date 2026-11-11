"""A Ticket's priority through the engine (register E227): set at the draft only, by `ticket_draft` or `aew work create
--priority`, recorded on the Ticket, and shown by `status`. The order the loop takes Tickets in is
``tests/unit/test_scheduler_priority.py``'s."""

from __future__ import annotations

from typing import Any

from aewflow import sample_project
from conftest import Project
from invariants import assert_control_invariants, load_control
from test_stage_runner import call, intent

from aew.engine.api import Engine

DRAFT = {"title": "Add subtract()", "risk_class": 1, "scope": ["calc/**", "tests/**"],
         "goal": ["calc.core.subtract(5, 3) == 2 through the public module"]}


def unit(p: Project, wid: str) -> dict[str, Any]:
    return load_control(p.root)["work"][wid]


def drafted(p: Project, **extra: Any) -> str:
    out = call(p, "ticket_draft", **DRAFT, **extra)
    assert out["ok"], out.get("stopped")
    return intent(p, out)["subject"]["id"]


def test_a_ticket_drafted_with_a_priority_records_it_and_status_shows_it_with_its_reason_and_a_lows_age(tmp_path):
    p = sample_project(tmp_path)
    low = drafted(p, priority="low", priority_reason="a nice-to-have")
    critical = drafted(p, priority="critical", priority_reason="the release waits on it")
    assert unit(p, low)["priority"] == {"level": "low", "reason": "a nice-to-have"}
    report = Engine.discover(p.root).status(usage=False)
    assert report["work"][low]["priority"] == {"level": "low", "reason": "a nice-to-have", "age": "0m"}
    assert report["work"][critical]["priority"] == {"level": "critical", "reason": "the release waits on it"}
    lines = "\n".join(report["work_graph"])
    assert "[low, waiting 0m: a nice-to-have]" in lines and "[critical: the release waits on it]" in lines
    assert_control_invariants(p)


def test_a_ticket_drafted_without_a_priority_is_normal_and_status_adds_nothing_for_it(tmp_path):
    p = sample_project(tmp_path)
    wid = drafted(p)
    assert "priority" not in unit(p, wid)
    report = Engine.discover(p.root).status(usage=False)
    assert "priority" not in report["work"][wid]
    assert not any("[" in line for line in report["work_graph"] if wid in line)


def test_ticket_draft_refuses_a_low_or_critical_priority_with_no_reason_naming_its_field(tmp_path):
    """Review of the priority PR, n3: the Lead's tool is refused in its own terms, naming `priority_reason`, and the
    tool's schema says a reason is needed unless the level is normal."""
    from aew.surface import contract

    p = sample_project(tmp_path)
    before = set(load_control(p.root)["work"])
    out = call(p, "ticket_draft", **DRAFT, priority="low")
    assert not out["ok"] and set(load_control(p.root)["work"]) == before, out  # no Ticket was drafted
    assert "`priority_reason`" in str(out) and "every level but normal needs one" in str(out), out
    draft = contract.tool("ticket_draft")
    assert draft is not None and "needed unless normal" in draft.input_schema["properties"]["priority_reason"][
        "description"]


def test_the_cli_sets_a_priority_at_creation_and_refuses_one_with_no_reason_or_on_a_story(tmp_path):
    p = sample_project(tmp_path)
    base = ["work", "create", "ticket", "--title", "Add subtract()", "--class", "1", "--scope", "calc/**"]
    made = p.lead(*base, "--priority", "critical", "--priority-reason", "the release waits on it")
    assert unit(p, made["id"])["priority"] == {"level": "critical", "reason": "the release waits on it"}
    env = {"AEW_LEAD_TOKEN": p.token}
    for refused, why in [
        ([*base, "--priority", "low"], "give its reason (`priority_reason`, or --priority-reason)"),
        (["work", "create", "story", "--title", "Arithmetic", "--class", "1", "--priority", "low",
          "--priority-reason", "later"], "a priority belongs to a Ticket"),
        ([*base, "--priority", "low", "--priority-reason", "  "], "is not blank"),
        ([*base, "--priority-reason", "later"], "goes with its level"),
    ]:
        res = p.aew(*refused, "--expect-rev", str(p.rev()), env=env)
        assert res.returncode != 0 and res.error["code"] == "USAGE", res.stderr
        assert why in res.error["message"], res.error
