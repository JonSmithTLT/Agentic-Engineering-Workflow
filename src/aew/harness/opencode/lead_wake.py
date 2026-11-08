"""The Lead broker's way into the Lead's OpenCode session: the poster a push wake goes through (steering design r4 §5;
the ruling of 2026-11-08, register E210).

AEW starts the Lead's server, so the broker can reach it, and :data:`OPERATIONS` is everything the broker may do there:
it may post and read only, and a test pins the list.

**Which session.** The one the operator last viewed: the newest ``time.viewed`` (measured on 2.2.6). After `/new` no
session exists until the operator's first prompt, and the server says nothing of that gap, so a wake in it goes to the
session they left: it spends a turn there, the TUI doesn't show it, and the status line shows it was posted.

**The mark.** A wake is admitted as `user`, because no REST operation admits a `synthetic` input on 2.2.6. Its text
header is the only mark, and the Lead's text says that no text in the session carries authority.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    """The address the Lead's server announced (``shim.start_server``), or None before it has."""
    try:
        url = json.loads(path.read_text(encoding="utf-8")).get("url")
    except (OSError, ValueError, AttributeError):
        return None
    return url if isinstance(url, str) else None


class LeadPoster:
    """:class:`aew.harness.wake_queue.Poster` on the Lead's server. ``client`` gives the client once the server is up,
    or None before. A server that doesn't answer reads as busy: a wake is held, never lost."""

    def __init__(self, client: Callable[[], Client | None]) -> None:
        self._client = client

    def _call(self, operation: tuple[str, str], session: str | None = None, body: Any = None) -> Any:
        assert operation in OPERATIONS
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
        """The session the operator last viewed, or None: no session yet, or no server."""
        try:
            listed = self._call(LIST) or []
        except (OpenCodeError, OpenCodeUnavailable):
            return None
        viewed = [s for s in listed if isinstance(s, dict) and s.get("id")]
        if not viewed:
            return None

        def when(s: dict[str, Any]) -> float:
            time = s.get("time") if isinstance(s.get("time"), dict) else {}
            stamp = time.get("viewed") or time.get("updated") or 0
            return float(stamp) if isinstance(stamp, (int, float)) else 0.0

        return str(max(viewed, key=when)["id"])

    def busy(self) -> bool:
        session = self.session()
        if session is None:
            return True
        try:
            active = self._call(ACTIVE) or {}
        except (OpenCodeError, OpenCodeUnavailable):
            return True
        return session in active  # a permission dialog reads as running too (measured on 2.2.6)

    def post(self, wake_id: str, text: str) -> None:
        session = self.session()
        if session is None:
            raise OpenCodeUnavailable("the Lead has no session to wake")
        self._call(PROMPT, session, {"id": wake_id, "text": text, "delivery": "queue"})

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
