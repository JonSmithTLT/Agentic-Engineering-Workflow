"""A holder's check of its own Lead credential reads the hot control state alone (CI on PR #281).

``require_held_lead`` is what the Lead broker's watchdog asks every iteration. A takeover moves the old Lead's
credential out of the token table into its archive (ADR-0011 R7), and ``require_lead`` looks an absent credential up
there, in the history index, whose SQLite busy wait no watchdog bound counts. A holder's credential that has left the
table has lost the seat, so the check never needs the archive; one still in the table is judged as ``require_lead``
judges it."""

from __future__ import annotations

from typing import Any

import pytest

from aew.engine import authority
from aew.errors import PermissionDenied, StaleAuthority


def _state(*, status: str = "held", generation: int = 1) -> tuple[dict[str, Any], str]:
    """A control state's token table and Lead seat, with the seat held by the credential returned."""
    state: dict[str, Any] = {"tokens": {}, "lead": {"generation": generation, "status": status, "token_id": None,
                                                    "session_label": "lead-a", "handoff": None}}
    token = authority.issue_token(state, "lead", {"generation": generation})
    state["lead"]["token_id"] = authority.token_id_of(token)
    return state, token


def _takeover(state: dict[str, Any], old: str) -> None:
    """What a takeover leaves in the hot state: a new Lead's credential, the old one gone to its archive."""
    del state["tokens"][authority.token_id_of(old)]
    state["lead"]["generation"] += 1
    state["lead"]["token_id"] = authority.token_id_of(
        authority.issue_token(state, "lead", {"generation": state["lead"]["generation"]}))


def test_a_holder_whose_credential_has_left_the_token_table_has_lost_the_seat():
    state, token = _state()
    _takeover(state, token)
    with pytest.raises(StaleAuthority) as exc:
        authority.require_held_lead(state, token)
    assert exc.value.message == "Lead authority superseded; this credential can no longer change control state"
    assert exc.value.details["current_generation"] == 2
    with pytest.raises(PermissionDenied, match="unknown or invalid credential"):
        authority.require_lead(state, token)  # a presenter without the archive is told it is unknown, as before


def test_a_holder_whose_credential_has_left_the_table_of_a_vacant_seat_is_told_no_lead_holds_it():
    state, token = _state()
    del state["tokens"][authority.token_id_of(token)]
    state["lead"].update(status="vacant", token_id=None)
    with pytest.raises(StaleAuthority, match="no Lead holds authority"):
        authority.require_held_lead(state, token)


def test_a_holder_whose_credential_is_in_the_table_is_judged_as_require_lead_judges_it():
    state, token = _state()
    assert authority.require_held_lead(state, token) == authority.require_lead(state, token)
    state["lead"]["status"] = "handoff_pending"
    with pytest.raises(PermissionDenied, match="handoff is pending"):  # not lost: the Lead may still cancel it
        authority.require_held_lead(state, token)
    authority.revoke(state, authority.token_id_of(token), "superseded by operator-authorized takeover")
    with pytest.raises(StaleAuthority, match="Lead authority superseded"):  # revoked, not yet archived
        authority.require_held_lead(state, token)


def test_a_malformed_credential_is_refused_as_malformed():
    state, _ = _state()
    with pytest.raises(PermissionDenied, match="malformed credential"):
        authority.require_held_lead(state, "")  # the broker's credential, cleared by close() (M3-D11)
