"""The Lead broker's way into the Lead's OpenCode session: the poster a push wake goes through (steering design r4 §5;
the ruling of 2026-11-08, register E210).

AEW starts the Lead's server, so the broker can reach it, and :data:`OPERATIONS` is everything the broker may do there:
it may post and read only, and a test pins the list.

**Which session.** The one the operator last viewed: the newest ``time.viewed`` (measured on 2.2.6). After `/new` no
session exists until the operator's first prompt, and the server says nothing of that gap, so a wake in it goes to the
session they left: it spends a turn there, the TUI doesn't show it, and the status line shows it was posted and where.
A restart doesn't have that gap: the contained store is per project, so earlier launches' sessions are still listed,
and only a session seen since this launch began counts. Until the operator's first prompt a wake is held, and the status
line shows it outstanding. A wake an earlier launch posted and never saw land is unknown to the new session, and is news
there.

**The mark.** A wake is admitted as `user`, because no REST operation admits a `synthetic` input on 2.2.6. Its text
header is the only mark, and the Lead's text says that no text in the session carries authority.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew.harness.containment.shim import LOOPBACK_URL
from aew.harness.opencode.adapter import new_message_id
from aew.harness.opencode.client import Client, OpenCodeError, OpenCodeUnavailable
from aew.harness.wake_queue import DELIVERED, UNKNOWN, WAITING

# (method, path): the whole of what the broker may do on the Lead's server.
LIST, ACTIVE, INBOX, MESSAGES, PROMPT = (("GET", "/api/session"), ("GET", "/api/session/active"),
                                         ("GET", "/api/session/{id}/inbox"), ("GET", "/api/session/{id}/message"),
                                         ("POST", "/api/session/{id}/prompt"))
OPERATIONS = frozenset({LIST, ACTIVE, INBOX, MESSAGES, PROMPT})


def _data(body: Any) -> Any:
    return body.get("data") if isinstance(body, dict) and "data" in body else body


def url_of(path: Path) -> str | None:
    """The address the Lead's server announced (``shim.start_server``), or None before it has. The server's password
    goes to this address, and the file can be in reach of the sandbox, so anything but this machine's loopback is no
    address."""
    try:
        url = json.loads(path.read_text(encoding="utf-8")).get("url")
    except (OSError, ValueError, AttributeError):
        return None
    return url if isinstance(url, str) and LOOPBACK_URL.fullmatch(url) else None


class LeadPoster:
    """:class:`aew.harness.wake_queue.Poster` on the Lead's server. ``client`` gives the client once the server is up,
    or None before. A server that doesn't answer reads as busy: a wake is held, never lost. ``since_ms`` is when this
    launch began, on the clock OpenCode stamps its sessions with: an older session is an earlier launch's."""

    def __init__(self, client: Callable[[], Client | None], *, since_ms: float = 0.0) -> None:
        self._client = client
        self._since_ms = since_ms

    def _call(self, operation: tuple[str, str], session: str | None = None, body: Any = None) -> Any:
        if operation not in OPERATIONS:
            raise ValueError(f"the broker may not call {operation} on the Lead's server")
        client = self._client()
        if client is None:
            raise OpenCodeUnavailable("the Lead's server has not announced its address")
        method, template = operation
        path = template.replace("{id}", session or "")
        return _data(client.post(path, body) if method == "POST" else client.get(path))

    @staticmethod
    def new_id() -> str:
        return new_message_id()  # the prompt's own id, which the inbox and the messages then name

    def session(self) -> str | None:
        """The session the operator last viewed in this launch, or None: none yet, or no server."""
        try:
            listed = self._call(LIST) or []
        except (OpenCodeError, OpenCodeUnavailable):
            return None

        def stamp(s: dict[str, Any], *names: str) -> float:
            time = s.get("time")
            found = next((time[n] for n in names if time.get(n)), 0) if isinstance(time, dict) else 0
            return float(found) if isinstance(found, (int, float)) else 0.0

        viewed = [s for s in listed if isinstance(s, dict) and s.get("id")
                  and max(stamp(s, "viewed"), stamp(s, "updated")) >= self._since_ms]
        if not viewed:
            return None
        return str(max(viewed, key=lambda s: stamp(s, "viewed", "updated"))["id"])

    def busy(self) -> bool:
        session = self.session()
        if session is None:
            return True
        try:
            active = self._call(ACTIVE) or {}
        except (OpenCodeError, OpenCodeUnavailable):
            return True
        return session in active  # a permission dialog reads as running too (measured on 2.2.6)

    def post(self, wake_id: str, text: str) -> str:
        session = self.session()
        if session is None:
            raise OpenCodeUnavailable("the Lead has no session to wake")
        self._call(PROMPT, session, {"id": wake_id, "text": text, "delivery": "queue"})
        return session

    def landed(self, wake_id: str) -> str:
        session = self.session()
        if session is None:
            return WAITING  # no answer is no news: a wake is never posted twice on a server's hiccup
        try:
            if any(isinstance(i, dict) and i.get("id") == wake_id for i in self._call(INBOX, session) or []):
                return WAITING
            messages = self._call(MESSAGES, session) or []
        except (OpenCodeError, OpenCodeUnavailable):
            return WAITING
        return DELIVERED if any(isinstance(m, dict) and m.get("id") == wake_id for m in messages) else UNKNOWN

    def busy_in(self, session: str) -> bool:
        """The pinned target, not whichever session becomes newest between selection and admission."""
        try:
            return session in (self._call(ACTIVE) or {})
        except (OpenCodeError, OpenCodeUnavailable):
            return True

    def post_to(self, session: str, wake_id: str, text: str) -> str:
        """Admit one immutable recorded envelope to its recorded target."""
        from aew.harness.wake_queue import PostRejected

        try:
            self._call(PROMPT, session, {"id": wake_id, "text": text, "delivery": "queue"})
        except OpenCodeError as exc:
            if exc.status in (400, 401, 403, 404, 422):
                raise PostRejected(f"wake input was refused with HTTP {exc.status}") from exc
            raise  # a conflict, server failure or missing response is not a non-admission guarantee
        return session

    def landed_in(self, session: str, wake_id: str) -> str:
        """Only observed admission counts. An unavailable read is not confirmed pending admission."""
        from aew.harness.wake_queue import UNAVAILABLE

        try:
            inbox = self._call(INBOX, session)
            if not isinstance(inbox, list):
                return UNAVAILABLE
            if any(isinstance(i, dict) and i.get("id") == wake_id for i in inbox):
                return WAITING
            messages = self._call(MESSAGES, session)
            if not isinstance(messages, list):
                return UNAVAILABLE
        except OpenCodeError as exc:
            return UNKNOWN if exc.status == 404 else UNAVAILABLE
        except OpenCodeUnavailable:
            return UNAVAILABLE
        return DELIVERED if any(isinstance(m, dict) and m.get("id") == wake_id for m in messages) else UNKNOWN
