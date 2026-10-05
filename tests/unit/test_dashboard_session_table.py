"""F20.3's session table and the engine edits under it (design note §4.1 to §4.3, §4.15; ADR-0005, 2026-10-05): minting,
the one-time codes, the cookie, expiry by an injected clock, displacement from the bounded table, the engine's own
lookup doing the verification, and the kind refused by every engine authority check."""

from __future__ import annotations

import re

import pytest

from aew import operator
from aew.cli import credentials
from aew.dashboard import control
from aew.dashboard import session as S
from aew.engine import authority
from aew.errors import PermissionDenied, StaleAuthority, UsageError
from aew.harness import lead_broker

T0 = "2026-10-05T12:00:00Z"


class Clock:
    def __init__(self, now: str = T0) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


class Ticks:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def table(**kw) -> tuple[S.SessionTable, Clock, Ticks]:
    clock, ticks = Clock(), Ticks()
    return S.SessionTable("proj", clock=clock, monotonic=ticks, **kw), clock, ticks


def headers(**kw) -> dict[str, str]:
    return {k.replace("_", "-"): v for k, v in kw.items()}


# ---------------------------------------------------------------------------------------------- minting and codes


def test_mint_returns_a_code_not_the_credential_and_the_table_holds_only_a_verifier():
    t, _, _ = table()
    code = t.mint()
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", code)  # 256 bits, URL-safe
    (record,) = t.tokens.values()
    assert record["kind"] == authority.OPERATOR_SESSION
    assert record["scope"] == {"surface": "dashboard", "project": "proj", "operations": ["dashboard.read"],
                               "authorized_by": "operator-tty"}
    assert record["expires_at"] == "2026-10-06T12:00:00Z" and record["revoked_at"] is None
    assert "secret" not in record and re.fullmatch(r"[0-9a-f]{64}", record["verifier"])
    assert code not in str(record)


def test_exchange_is_single_use_and_unknown_codes_fail():
    t, _, _ = table()
    code = t.mint()
    got = t.exchange(code)
    assert got is not None
    credential, record = got
    assert authority.TOKEN_RE.match(credential) and record is t.tokens[authority.token_id_of(credential)]
    assert t.exchange(code) is None  # spent
    assert t.exchange("") is None and t.exchange("nope") is None and t.exchange(code[:-1]) is None
    assert t.pending_codes == 0


def test_a_code_expires_after_ten_minutes_but_the_session_it_names_does_not():
    t, _, ticks = table()
    code = t.mint()
    ticks.t += S.CODE_TTL_S + 1
    assert t.exchange(code) is None
    assert len(t.live()) == 1  # the session exists; nobody holds its credential, so it just ages out


def test_the_cookie_is_the_credential_with_the_contracts_attributes():
    t, clock, _ = table(hours=2)
    credential, record = t.exchange(t.mint())  # type: ignore[misc]
    cookie = t.cookie(credential, record)
    assert cookie == f"aew_session={credential}; Path=/; HttpOnly; SameSite=Strict; Max-Age=7200"
    assert "Secure" not in cookie  # a plain-http loopback origin (R10)
    clock.now = "2026-10-05T13:30:00Z"
    assert t.cookie(credential, record).endswith("Max-Age=1800")
    assert S.cookie_value(headers(Cookie=cookie.split(";")[0])) == credential
    assert S.cookie_value(headers(Cookie=f"other=1; {cookie.split(';')[0]}; x=y")) == credential
    assert S.cookie_value(headers()) is None and S.cookie_value(headers(Cookie="other=1")) is None
    assert S.cookie_value(headers(Cookie="aew_session=")) is None
    assert S.expired_cookie() == "aew_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


# ---------------------------------------------------------------------------------------------- verification


def test_verify_is_the_engines_lookup_and_the_server_maps_its_two_refusals():
    t, clock, _ = table()
    credential, _ = t.exchange(t.mint())  # type: ignore[misc]
    assert t.verify(credential)["kind"] == authority.OPERATOR_SESSION
    assert t.authenticate(headers(Cookie=f"aew_session={credential}")) is None
    tid, secret = credential.split(".")[1], credential.split(".")[2]
    for bad in ("", "aew1.", credential[:-3], f"aew1.{tid}.{'x' * 43}", f"aew1.tk_0000000000000000.{secret}",
                credential.upper(), "Bearer " + credential):
        with pytest.raises(PermissionDenied):
            t.verify(bad)
        assert t.authenticate(headers(Cookie=f"aew_session={bad}"))["code"] == "SESSION_REQUIRED"  # type: ignore[index]
    assert t.authenticate(headers())["code"] == "SESSION_REQUIRED"  # type: ignore[index]
    clock.now = "2026-10-06T12:00:00Z"  # exactly the expiry: the engine's rule is `expires_at <= now`
    with pytest.raises(StaleAuthority, match="expired"):
        t.verify(credential)
    assert t.authenticate(headers(Cookie=f"aew_session={credential}"))["code"] == "SESSION_EXPIRED"  # type: ignore[index]


def test_a_session_of_another_project_or_kind_is_refused():
    t, _, _ = table()
    other = S.SessionTable("other-project")
    credential, _ = other.exchange(other.mint())  # type: ignore[misc]
    t.tokens.update(other.tokens)  # the same table (it cannot happen; the check is still there)
    with pytest.raises(PermissionDenied, match="not a session of this dashboard"):
        t.verify(credential)
    lead = authority.mint(t.tokens, "lead", {"generation": 1}, generation=1)
    with pytest.raises(PermissionDenied, match="not a session of this dashboard"):
        t.verify(lead)


def test_displacement_revokes_the_oldest_live_session_at_the_bound():
    t, clock, _ = table()
    creds = []
    for i in range(S.MAX_SESSIONS):
        clock.now = f"2026-10-05T12:{i:02d}:00Z"
        creds.append(t.exchange(t.mint())[0])  # type: ignore[index]
    assert len(t.live()) == S.MAX_SESSIONS
    clock.now = "2026-10-05T13:00:00Z"
    newest = t.exchange(t.mint())[0]  # type: ignore[index]
    assert len(t.live()) == S.MAX_SESSIONS
    oldest = t.tokens[authority.token_id_of(creds[0])]
    assert oldest["revoked_at"] == clock.now and oldest["revoke_reason"] == S.SUPERSEDED
    with pytest.raises(StaleAuthority, match="superseded"):
        t.verify(creds[0])
    assert t.authenticate(headers(Cookie=f"aew_session={creds[0]}"))["code"] == "SESSION_EXPIRED"  # type: ignore[index]
    for live in creds[1:] + [newest]:
        t.verify(live)


def test_clear_ends_every_session_and_pending_code():
    t, _, _ = table()
    code = t.mint()
    credential, _ = t.exchange(t.mint())  # type: ignore[misc]
    t.clear()
    assert t.tokens == {} and t.pending_codes == 0 and t.exchange(code) is None
    with pytest.raises(PermissionDenied):
        t.verify(credential)


def test_expired_records_stay_through_the_grace_then_are_purged_and_the_lifetime_is_bounded():
    t, clock, _ = table(hours=1)
    credential, _ = t.exchange(t.mint())  # type: ignore[misc]
    clock.now = "2026-10-05T13:00:01Z"  # expired a second ago
    t.mint()
    assert len(t.tokens) == 2  # kept: an expired cookie is answered "expired", not "unknown"
    with pytest.raises(StaleAuthority, match="expired"):
        t.verify(credential)
    clock.now = "2026-10-12T13:00:02Z"  # a second past the grace
    t.mint()
    assert len(t.tokens) == 2  # the first record is gone; the second mint of 10-05 is kept (expired, within grace)
    with pytest.raises(PermissionDenied, match="unknown"):
        t.verify(credential)
    for hours in (0, 169):
        with pytest.raises(ValueError):
            S.SessionTable("proj", hours=hours)


def test_cross_site_fetch_metadata_is_refused_and_user_navigation_is_not():
    assert not S.cross_site(headers())
    assert not S.cross_site(headers(Sec_Fetch_Site="none", Sec_Fetch_Mode="navigate"))
    assert not S.cross_site(headers(Sec_Fetch_Site="same-origin"))
    assert S.cross_site(headers(Sec_Fetch_Site="cross-site", Sec_Fetch_Mode="navigate"))
    assert S.cross_site(headers(Sec_Fetch_Site="same-site"))
    assert S.cross_site(headers(Sec_Fetch_Site="none", Sec_Fetch_Mode="cors"))
    assert S.cross_site(headers(Sec_Fetch_Mode="no-cors"))
    # a speculative prefetch is not the user's navigation either (lead developer's review)
    assert S.prefetch(headers(Sec_Purpose="prefetch")) and S.prefetch(headers(Purpose="prefetch"))
    assert S.prefetch(headers(Sec_Purpose="prefetch;anonymous-client-ip"))
    assert not S.prefetch(headers()) and not S.prefetch(headers(Sec_Purpose="navigate"))
    assert S.not_a_user_navigation(headers(Sec_Purpose="prefetch"))
    assert not S.not_a_user_navigation(headers(Sec_Fetch_Site="none", Sec_Fetch_Mode="navigate"))


# ---------------------------------------------------------------------------------------------- the engine edits


def control_state_with(record_kind: str) -> tuple[dict, str]:
    """A control state (the shape `require_*` read) holding one credential of the given kind."""
    state = {"revision": 1, "lead": {"generation": 1, "status": "held", "token_id": None, "handoff": None},
             "tokens": {}, "invocations": {}}
    credential = authority.mint(state["tokens"], record_kind, {"surface": "dashboard", "project": "p",
                                                               "operations": ["dashboard.read"]}, generation=1)
    return state, credential


def test_the_kind_is_refused_by_every_engine_authority_check():
    state, credential = control_state_with(authority.OPERATOR_SESSION)
    with pytest.raises(PermissionDenied, match="requires the Lead credential") as exc:
        authority.require_lead(state, credential)
    assert exc.value.details["presented"] == "operator_session"
    with pytest.raises(PermissionDenied, match="requires an invocation credential"):
        authority.require_invocation(state, credential, "context.read")
    with pytest.raises(PermissionDenied, match="not the pending handoff offer"):
        authority.verify_offer(state, credential)


def test_issue_token_mints_and_lookup_is_what_the_engine_verifies_with():
    state = {"lead": {"generation": 3}, "tokens": {}}
    credential = authority.issue_token(state, "lead", {"generation": 3})
    tid = authority.token_id_of(credential)
    assert state["tokens"][tid]["issued_by_generation"] == 3 and state["tokens"][tid]["expires_at"] is None
    assert authority.lookup(state["tokens"], credential)[0] == tid
    assert authority._lookup(state, credential)[0] == tid  # noqa: SLF001 (the delegation under test)
    with pytest.raises(StaleAuthority, match="expired"):
        authority.lookup(state["tokens"], authority.mint(state["tokens"], "lead", {}, generation=3,
                                                         expires_at="2026-01-01T00:00:00Z"))
    assert authority.lookup(state["tokens"], credential, now="2099-01-01T00:00:00Z")[0] == tid  # no expiry set
    archived = {tid: {"verifier": state["tokens"][tid]["verifier"], "revoke_reason": "archived"}}
    del state["tokens"][tid]
    with pytest.raises(StaleAuthority, match="finished work"):
        authority.lookup(state["tokens"], credential, archived=archived.get)


def test_the_dashboard_commands_are_credential_emitting_everywhere():
    for path in ({"dashboard", "serve"}, {"dashboard", "open"}):
        assert any(p <= path for p in credentials.ISSUING)
        assert any(p <= path for p in lead_broker.CREDENTIAL_EMITTING)
    assert not any(p <= {"dashboard", "status"} for p in credentials.ISSUING + lead_broker.CREDENTIAL_EMITTING)
    assert "session_url" in credentials.KEYS


def test_write_to_terminal_needs_a_terminal(monkeypatch):
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)
    with pytest.raises(UsageError, match="no terminal"):
        credentials.write_to_terminal("session_url", "http://127.0.0.1:1/session/x")


def test_the_challenge_prompt_carries_the_code_the_requester_and_the_destination(monkeypatch):
    shown = operator.challenge("ABC123", "START the dashboard", requested_by="aew (7) <- bash (1)",
                               destination="the requesting terminal")
    assert "START the dashboard" in shown and "requested by   : aew (7) <- bash (1)" in shown
    assert "credential to  : the requesting terminal" in shown and "confirmation code ABC123" in shown
    assert "Never give it to an agent or paste it into a chat" in shown  # on every challenge, takeover's included
    assert re.fullmatch(r"[0-9A-F]{6}", operator.new_code())
    opened = control.open_prompt("aew (9)")
    assert "aew dashboard serve" in opened and "Type it here" in opened and opened.endswith("> ")
    assert "confirmation code " not in opened  # the code is on the server's console, never on this terminal


def test_control_requests_are_exactly_op_and_args():
    assert control._request(b'{"op": "status", "args": {}}') == ("status", {})  # noqa: SLF001
    for raw in (b"not json", b"[]", b'{"op": "x"}', b'{"op": "x", "args": [], "more": 1}', b'{"op": "x", "args": 1}'):
        with pytest.raises(UsageError):
            control._request(raw)  # noqa: SLF001
