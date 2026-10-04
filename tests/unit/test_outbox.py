"""ADR-0012 (M4-D slice D1): typed events derived from committed states, the hot bound, the hash chain and the
transition schemas, without a project."""

from __future__ import annotations

import copy

import pytest

from aew.engine import outbox
from aew.errors import ValidationFailed
from aew.schemas import validate, validate_def

BASE = {
    "lead": {"generation": 1},
    "work": {"T-0001": {"kind": "ticket", "state": "READY"}},
    "invocations": {"INV-0001": {"work_unit": "T-0001", "role": "implementer", "status": "active",
                                 "runs": [{"run": "R-INV-0001-1"}]}},
    "tokens": {"tok-1": {"kind": "invocation", "revoked_at": None}},
    "cold": {"root": {"count": 3, "head_h": "a" * 64}},
}


def changed(fn) -> dict:
    state = copy.deepcopy(BASE)
    fn(state)
    return state


@pytest.mark.parametrize(("change", "expected"), [
    (lambda s: s["lead"].update(generation=2), [{"kind": "lead.generation", "from": 1, "to": 2}]),
    (lambda s: s["work"]["T-0001"].update(state="RUNNING"),
     [{"kind": "work.state", "id": "T-0001", "unit": "ticket", "from": "READY", "to": "RUNNING"}]),
    (lambda s: s["work"].update({"S-0001": {"kind": "story", "state": "DRAFT"}}),
     [{"kind": "work.state", "id": "S-0001", "unit": "story", "from": None, "to": "DRAFT"}]),
    (lambda s: s["invocations"]["INV-0001"].update(status="completed"),
     [{"kind": "invocation.status", "id": "INV-0001", "work": "T-0001", "role": "implementer", "from": "active",
       "to": "completed"}]),
    (lambda s: s["invocations"]["INV-0001"]["runs"].append({"run": "R-INV-0001-2"}),
     [{"kind": "run.added", "invocation": "INV-0001", "run": "R-INV-0001-2"}]),
    (lambda s: s["tokens"]["tok-1"].update(revoked_at="t", revoke_reason="run ended"),
     [{"kind": "credential.revoked", "id": "tok-1", "reason": "run ended"}]),
    (lambda s: s["cold"]["root"].update(count=5, head_h="b" * 64),
     [{"kind": "history.appended", "from_count": 3, "to_count": 5, "head_h": "b" * 64}]),
    (lambda s: None, []),
])
def test_each_derived_kind_comes_from_its_state_change(change, expected):
    after = changed(change)
    assert outbox.derive_events(BASE, after, after) == expected
    for event in expected:
        validate_def("transition", "event", event, source="test")


def test_a_unit_finished_and_archived_in_one_commit_moves_then_is_archived():
    """The archival finalizer projects finished units out of the committed state (ADR-0011 R6); the working state
    still has them, so the move to DONE is not lost."""
    working = changed(lambda s: s["work"]["T-0001"].update(state="DONE"))
    committed = changed(lambda s: s["work"].clear())
    assert outbox.derive_events(BASE, working, committed) == [
        {"kind": "work.state", "id": "T-0001", "unit": "ticket", "from": "READY", "to": "DONE"},
        {"kind": "unit.archived", "id": "T-0001", "unit": "ticket", "state": "DONE"}]


def test_a_revoked_credential_that_was_already_revoked_is_not_a_new_event():
    before = changed(lambda s: s["tokens"]["tok-1"].update(revoked_at="t0"))
    assert outbox.derive_events(before, before, before) == []


def test_up_to_64_events_stay_hot_and_more_overflow_to_a_complete_sidecar():
    events = [{"kind": "handoff.recorded", "id": f"H-{i:04d}"} for i in range(64)]
    assert outbox.bound(9, events) == (events, None, None)
    events.append({"kind": "decision.recorded", "id": "D-0001", "type": "plan_acceptance"})
    hot, overflow, text = outbox.bound(9, events)
    assert hot == events[:64] and text is not None
    assert overflow == {"path": "state/log/000009.events.yaml", "sha256": outbox.sha256_bytes(text.encode()),
                        "event_count": 65, "counts_by_kind": {"decision.recorded": 1, "handoff.recorded": 64}}
    payload = outbox.load_yaml(text, source="sidecar")
    assert payload["events"] == events
    validate("transition-events", payload, source="sidecar")


def test_the_hash_commits_to_the_overflow_digest_and_count():
    record = {"schema": outbox.TRANSITION_SCHEMA, "revision": 9, "at": "t", "actor": {}, "op": "x", "events": [],
              "event_overflow": {"path": "state/log/000009.events.yaml", "sha256": "c" * 64, "event_count": 70,
                                 "counts_by_kind": {"x": 70}}}
    h = outbox.transition_hash(outbox.GENESIS_H, record)
    for field, value in (("sha256", "d" * 64), ("event_count", 71)):
        other = copy.deepcopy(record)
        other["event_overflow"][field] = value
        assert outbox.transition_hash(outbox.GENESIS_H, other) != h
    assert outbox.transition_hash("0" * 64, record) != h  # and to the previous record
    assert outbox.transition_hash(outbox.GENESIS_H, dict(record, h="ignored")) == h  # never to itself


def test_the_transition_schema_is_closed_and_bounded():
    record = {"schema": outbox.TRANSITION_SCHEMA, "revision": 1, "at": "t", "actor": {}, "op": "x", "events": [],
              "event_overflow": None, "h": "e" * 64}
    validate("transition", record, source="test")
    for bad in (dict(record, extra=1), dict(record, events=[{"kind": "work.state", "id": "T", "unit": None,
                                                             "from": None, "to": None, "extra": 1}]),
                dict(record, events=[{"kind": "made.up"}]),
                dict(record, events=[{"kind": "handoff.recorded", "id": "H"}] * 65)):
        with pytest.raises(ValidationFailed):
            validate("transition", bad, source="test")

