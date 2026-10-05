"""The dashboard's operator session (design note §4.1 to §4.3; ADR-0005, amendment of 2026-10-05).

A browser session is a credential of the kind ``operator_session``: the token record's shape, held only in this
process's :class:`SessionTable`, verified by the engine's own ``authority.lookup`` over that table. It authenticates a
browser to the local server and authorizes nothing in the engine. The raw secret exists here between minting and the
one-time exchange, then only as its verifier; it is never written to a file or logged.

Delivery is a one-time URL ``/session/<code>`` (256 random bits, ten minutes, single use) that the browser exchanges
for the ``aew_session`` cookie (``HttpOnly``, ``SameSite=Strict``, ``Max-Age`` to the session's expiry). Revocation is
the end of the serving process (the table dies with it), the expiry, or displacement from the bounded table.
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any

from aew.engine import authority
from aew.errors import PermissionDenied, StaleAuthority
from aew.util import utc_now

COOKIE = "aew_session"
DEFAULT_HOURS = 24
MIN_HOURS, MAX_HOURS = 1, 168
MAX_SESSIONS = 32
CODE_TTL_S = 600.0
# An expired record is kept this long so a stale cookie is answered SESSION_EXPIRED (the engine's "credential
# expired"), not SESSION_REQUIRED as an unknown id would be (lead developer's review of F20.3).
EXPIRED_GRACE = timedelta(days=7)
SUPERSEDED = "superseded: session limit"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SCOPE_OPERATIONS = ["dashboard.read"]


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=UTC)


def cookie_value(headers: Any) -> str | None:
    """The ``aew_session`` cookie a request carries, or ``None``."""
    raw = headers.get("Cookie") if headers is not None else None
    if not raw:
        return None
    jar: SimpleCookie = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:  # noqa: BLE001 (a malformed cookie header is simply no session)
        return None
    morsel = jar.get(COOKIE)
    return morsel.value if morsel is not None and morsel.value else None


def expired_cookie() -> str:
    """A ``Set-Cookie`` value that removes a dead session cookie from the browser."""
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


def cross_site(headers: Any) -> bool:
    """R9: the exchange is refused, without consuming the code, when the browser says the navigation did not start
    from the user (the address bar, a bookmark, a paste) or from this origin."""
    site = headers.get("Sec-Fetch-Site")
    if site is not None and site.strip().lower() not in ("none", "same-origin"):
        return True
    mode = headers.get("Sec-Fetch-Mode")
    return mode is not None and mode.strip().lower() != "navigate"


def prefetch(headers: Any) -> bool:
    """A speculative fetch (`Sec-Purpose: prefetch`, or the older `Purpose: prefetch`) must not spend the one-time
    code: refused without consuming it, and the real navigation that follows succeeds."""
    for name in ("Sec-Purpose", "Purpose", "X-Purpose", "X-Moz"):
        value = headers.get(name)
        if value is not None and "prefetch" in value.lower():
            return True
    return False


def not_a_user_navigation(headers: Any) -> bool:
    return cross_site(headers) or prefetch(headers)


class SessionTable:
    """The serving process's token table, the pending one-time codes, and the verification the server calls.

    ``clock`` is the time the expiry is judged by (injected by the tests); ``monotonic`` paces the one-time codes."""

    def __init__(self, project_id: str, *, hours: int = DEFAULT_HOURS, generation: int = 0,
                 clock: Callable[[], str] = utc_now, monotonic: Callable[[], float] = time.monotonic) -> None:
        if not MIN_HOURS <= hours <= MAX_HOURS:
            raise ValueError(f"a session lasts {MIN_HOURS} to {MAX_HOURS} hours")
        self.project_id = project_id
        self.hours = hours
        self.generation = generation
        self.clock = clock
        self.monotonic = monotonic
        self.tokens: dict[str, dict[str, Any]] = {}
        # code -> (credential, token_id, deadline): the raw secret lives here until the exchange or the code's expiry
        self._pending: dict[str, tuple[str, str, float]] = {}

    # ------------------------------------------------------------------ issuing

    def mint(self) -> str:
        """Issue a session and return its one-time bootstrap code (never the credential)."""
        now = self.clock()
        self._purge(now)
        live = sorted((r for r in self.tokens.values() if self._live(r, now)), key=lambda r: r["issued_at"])
        while len(live) >= MAX_SESSIONS:
            oldest = live.pop(0)
            oldest["revoked_at"] = now
            oldest["revoke_reason"] = SUPERSEDED
        expires = (parse_time(now) + timedelta(hours=self.hours)).strftime(TIME_FORMAT)
        scope = {"surface": "dashboard", "project": self.project_id, "operations": list(SCOPE_OPERATIONS),
                 "authorized_by": "operator-tty"}
        credential = authority.mint(self.tokens, authority.OPERATOR_SESSION, scope, generation=self.generation,
                                    expires_at=expires)
        code = secrets.token_urlsafe(32)  # 256 bits
        self._pending[code] = (credential, authority.token_id_of(credential), self.monotonic() + CODE_TTL_S)
        return code

    def newest(self) -> dict[str, Any]:
        """The record minted last (its id and times; the caller never gets a verifier out of it by this path)."""
        return max(self.tokens.values(), key=lambda r: (r["issued_at"], id(r)))

    def exchange(self, code: str) -> tuple[str, dict[str, Any]] | None:
        """Spend a one-time code: the credential and its record, or ``None`` for an unknown, used or expired code."""
        self._purge(self.clock())
        found = next((c for c in self._pending if hmac.compare_digest(c, code or "")), None)
        if found is None:
            return None
        credential, token_id, _deadline = self._pending.pop(found)
        record = self.tokens.get(token_id)
        if record is None or record["revoked_at"] is not None:
            return None
        return credential, record

    def cookie(self, credential: str, record: dict[str, Any]) -> str:
        """The ``Set-Cookie`` value that hands the credential to the browser (R10)."""
        remaining = int((parse_time(record["expires_at"]) - parse_time(self.clock())).total_seconds())
        return f"{COOKIE}={credential}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max(remaining, 0)}"

    # ------------------------------------------------------------------ verifying

    def verify(self, credential: str) -> dict[str, Any]:
        """The record of a live session credential, through the engine's lookup; raises as the engine does."""
        token_id, record = authority.lookup(self.tokens, credential, now=self.clock())
        if record["kind"] != authority.OPERATOR_SESSION or record["scope"].get("project") != self.project_id:
            raise PermissionDenied("not a session of this dashboard", presented=record["kind"])
        if record["revoked_at"] is not None:
            raise StaleAuthority(f"this session was ended: {record['revoke_reason']}", token_id=token_id)
        return record

    def authenticate(self, headers: Any) -> dict[str, Any] | None:
        """The server's authenticator: ``None`` admits the request; an ``Error`` body refuses it with 401."""
        from aew.dashboard.server import error_body

        credential = cookie_value(headers)
        if credential is None:
            return error_body("SESSION_REQUIRED")
        try:
            self.verify(credential)
        except StaleAuthority:
            return error_body("SESSION_EXPIRED")
        except PermissionDenied:
            return error_body("SESSION_REQUIRED")
        return None

    # ------------------------------------------------------------------ lifecycle

    def clear(self) -> None:
        """Every session ends with the serving process (R4)."""
        self.tokens.clear()
        self._pending.clear()

    def live(self) -> list[dict[str, Any]]:
        """The live sessions as ``aew dashboard status`` shows them: ids and times, never a verifier."""
        now = self.clock()
        return [{"token_id": tid, "issued_at": r["issued_at"], "expires_at": r["expires_at"]}
                for tid, r in sorted(self.tokens.items(), key=lambda kv: kv[1]["issued_at"]) if self._live(r, now)]

    @property
    def pending_codes(self) -> int:
        return len(self._pending)

    def _live(self, record: dict[str, Any], now: str) -> bool:
        return record["revoked_at"] is None and record["expires_at"] > now

    def _purge(self, now: str) -> None:
        cutoff = (parse_time(now) - EXPIRED_GRACE).strftime(TIME_FORMAT)
        for tid in [t for t, r in self.tokens.items() if r["expires_at"] <= cutoff]:
            del self.tokens[tid]  # expired long enough ago that SESSION_EXPIRED no longer needs the record
        tick = self.monotonic()
        for code in [c for c, (_cred, tid, deadline) in self._pending.items()
                     if deadline <= tick or tid not in self.tokens]:
            del self._pending[code]
