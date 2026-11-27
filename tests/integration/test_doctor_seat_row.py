"""The doctor seat row (register E384; V-01 burn-down C14): a Lead seat held by a session that is gone is a WARN naming
that session and the fix, judged as `aew opencode`'s resume judges the seat (E330). It only adds a line: every other
doctor row, and its verdict, stays as it was."""

from __future__ import annotations

import re

import pytest
from aewflow import sample_project

from aew.engine import api, lead_ops
from aew.engine.api import Engine
from aew.harness import procs, seat

# The vertical's own regexes for the stale-lead-session case (tests/acceptance/test_vertical_path.py, V3_CASES).
CAUSE = (r"Lead session[^\n]{0,80}(dead|ended|gone|no longer running|stale)|"
         r"(dead|ended|gone|stale)[^\n]{0,40}Lead session")
FIX = r"reattach|recover"


@pytest.fixture
def held(tmp_path, monkeypatch):
    """A seat taken by plain `aew opencode` (a vacant start) on this host and user, its session's process gone."""
    project = sample_project(tmp_path)
    engine = Engine.discover(project.root)
    engine.lead_release(token=project.token)
    taken = engine.lead_acquire(session_label="operator", kind=seat.VACANT_START)
    project.token = taken["token"]
    monkeypatch.setattr(procs, "same_process", lambda *_: False)
    return project, engine, taken


def seat_rows(engine: Engine) -> list[dict[str, str]]:
    return [c for c in engine.doctor_checks() if c["check"] == "lead-seat"]


def test_a_seat_held_by_a_session_that_is_gone_is_a_warn_naming_the_session_and_the_resume_fix(held):
    _, engine, taken = held
    lead = engine.store.current()["lead"]
    row, = seat_rows(engine)
    assert row["status"] == "WARN"
    detail = row["detail"]
    assert all(part in detail for part in ("'operator'", f"generation {taken['generation']}",
                                           f"pid {lead['start']['pid']}", "no longer running"))
    assert "plain `aew opencode`" in detail and "resumes the seat" in detail
    assert "aew lead takeover --reason" in detail  # the way on where resume is refused
    assert re.search(CAUSE, detail) and re.search(FIX, detail)
    # The row's judgement is resume's: this seat is one plain `aew opencode` would resume.
    assert lead_ops.resume_refusal(lead) is None


def test_a_seat_whose_session_still_runs_is_a_pass_that_names_no_fix(held, monkeypatch):
    _, engine, _ = held
    monkeypatch.setattr(procs, "same_process", lambda *_: True)
    row, = seat_rows(engine)
    assert row["status"] == "PASS"
    assert "is running" in row["detail"] and "aew opencode" not in row["detail"]
    assert not re.search(CAUSE, row["detail"])


def test_a_gone_session_with_a_handoff_pending_names_why_resume_is_refused_and_the_handoff_and_takeover(held):
    project, engine, _ = held
    engine.lead_handoff_offer(token=project.token)
    row, = seat_rows(engine)
    assert row["status"] == "WARN"
    detail = row["detail"]
    assert "cannot resume it: a cooperative handoff is pending" in detail
    assert "`aew lead handoff accept`" in detail and "aew lead takeover --reason" in detail
    assert "resumes the seat" not in detail
    assert re.search(CAUSE, detail) and re.search(FIX, detail)


@pytest.mark.parametrize("seat_state", ["vacant", "typed_acquire", "other_host", "other_generation"])
def test_no_seat_row_where_nothing_holds_the_seat_or_its_session_cannot_be_judged_here(held, monkeypatch, seat_state):
    project, engine, taken = held
    if seat_state == "vacant":
        engine.lead_release(token=taken["token"])
    elif seat_state == "typed_acquire":  # `aew lead acquire`: the recorded process is the acquiring command's
        engine.lead_release(token=taken["token"])
        engine.lead_acquire(session_label="operator")
    elif seat_state == "other_host":
        host, user = seat.principal()
        monkeypatch.setattr(seat, "principal", lambda: (f"{host}-elsewhere", user))
    else:
        original = engine.store.current

        def current():
            state = original()
            state["lead"]["start"]["generation"] -= 1
            return state

        monkeypatch.setattr(engine.store, "current", current)
    assert seat_rows(engine) == []
    assert lead_ops.seat_doctor(engine.store.current()["lead"]) is None


def test_the_seat_row_only_adds_a_line_and_every_existing_doctor_row_and_verdict_is_unchanged(held, monkeypatch):
    """The pin of strict additivity (the operator's approval of 2026-11-27): with the seat row, doctor's rows are
    those it gave without it, in the same order with the same verdicts, plus the one seat row after `lead`."""
    _, engine, taken = held
    with_row = engine.doctor_checks()
    monkeypatch.setattr(api, "seat_doctor", lambda _lead: None)
    without = engine.doctor_checks()
    assert [c["check"] for c in with_row].count("lead-seat") == 1
    names = [c["check"] for c in with_row]
    assert names[names.index("lead-seat") - 1] == "lead"
    kept = [c for c in with_row if c["check"] != "lead-seat"]
    assert kept == without
    lead_row, = (c for c in kept if c["check"] == "lead")
    assert lead_row == {"check": "lead", "status": "PASS", "detail": f"active (generation {taken['generation']})"}
