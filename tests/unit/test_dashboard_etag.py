"""F20.4: the dashboard's strong validator and ``If-None-Match`` (design note §4.12, R19; §5.3)."""

from __future__ import annotations

import copy

from aew.dashboard import etag as E

BODY = {"schema_version": "0.1.2", "project_id": "calc", "control_revision": "12",
        "generated_at": E.SNAPSHOT_TIME,
        "data": {"health": {"status": "HEALTHY", "reasons": [], "observed_at": E.SNAPSHOT_TIME},
                 "runs": [{"id": "R-INV-0001-1", "status": "running"}]}}
SCOPE = E.scope("/api/v1/overview", "calc", {})


def tag(body=BODY, scope=SCOPE) -> str:
    return E.validator(scope, body)


def test_the_validator_is_a_quoted_sha256():
    t = tag()
    assert t.startswith('"') and t.endswith('"') and len(t) == 66 and int(t[1:-1], 16) >= 0
    assert tag() == t  # deterministic


def test_the_validator_excludes_generated_at():
    other = dict(BODY, generated_at="2030-01-01T00:00:00Z")
    assert tag(other) == tag()
    assert tag({k: v for k, v in BODY.items() if k != "generated_at"}) == tag()


def test_the_validator_covers_every_other_field():
    changes = [
        ("control_revision", lambda b: b.__setitem__("control_revision", "13")),
        ("project_id", lambda b: b.__setitem__("project_id", "other")),
        ("schema_version", lambda b: b.__setitem__("schema_version", "0.1.3")),
        ("telemetry", lambda b: b["data"]["runs"][0].__setitem__("status", "crashed")),
        ("a nested time", lambda b: b["data"]["health"].__setitem__("observed_at", "2030-01-01T00:00:00Z")),
        ("a new field", lambda b: b["data"].__setitem__("extra", None)),
    ]
    seen = {tag()}
    for name, change in changes:
        body = copy.deepcopy(BODY)
        change(body)
        t = tag(body)
        assert t not in seen, name
        seen.add(t)


def test_key_order_does_not_change_the_validator():
    reordered = {k: BODY[k] for k in reversed(list(BODY))}
    assert tag(reordered) == tag()


def test_two_scopes_with_equal_bodies_differ():
    scopes = [
        E.scope("/api/v1/overview", "calc", {}),
        E.scope("/api/v1/work", "calc", {}),
        E.scope("/api/v1/work/T-0001", "calc", {}),
        E.scope("/api/v1/work/T-0002", "calc", {}),
        E.scope("/api/v1/work", "other", {}),
        E.scope("/api/v1/work", "calc", {"state": "DONE"}),
        E.scope("/api/v1/work", "calc", {"limit": 2}),
        E.scope("/api/v1/work", "calc", {"limit": 3}),
        E.scope("/api/v1/work", "calc", {"limit": 2, "cursor": "abc"}),
    ]
    assert len({tag(BODY, s) for s in scopes}) == len(scopes)


def test_the_scope_ignores_the_order_of_query_parameters():
    assert E.scope("/api/v1/work", "calc", {"state": "DONE", "kind": "ticket"}) == \
        E.scope("/api/v1/work", "calc", {"kind": "ticket", "state": "DONE"})


def test_if_none_match_is_a_list_of_strong_validators():
    t = tag()
    assert E.matches(t, t)
    assert E.matches(f'"other", {t}', t)
    assert E.matches(f'  {t}  ,"other"', t)
    assert not E.matches('"other"', t)
    assert not E.matches(None, t) and not E.matches("", t)
    assert not E.matches(t[1:-1], t)  # unquoted is not the validator


def test_weak_validators_and_the_star_never_match():
    t = tag()
    assert not E.matches(f"W/{t}", t)
    assert not E.matches("*", t)
    assert not E.matches(f"*, W/{t}", t)


def test_stamp_writes_the_real_time_into_every_marker_and_nothing_else():
    now = "2026-10-05T12:00:00Z"
    stamped = E.stamp(BODY, now)
    assert stamped["generated_at"] == now and stamped["data"]["health"]["observed_at"] == now
    assert stamped["data"]["runs"] == BODY["data"]["runs"] and stamped["control_revision"] == "12"
    assert E.SNAPSHOT_TIME not in repr(stamped)
    assert BODY["generated_at"] == E.SNAPSHOT_TIME  # the marked body is not changed in place
    assert E.stamp({"a": "x" + E.SNAPSHOT_TIME}, now) == {"a": "x" + E.SNAPSHOT_TIME}  # whole values only


def test_the_marker_sorts_after_every_timestamp():
    # The projections order units by their last change and fall back to the snapshot's time for a unit that names
    # none: that unit must still sort as the newest, as the real time did.
    assert E.SNAPSHOT_TIME > "9999-12-31T23:59:59Z"
