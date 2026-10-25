"""The operator's stored OpenCode login, read on the host for the contained Lead's provider relays (STG-05 CS-4).

OpenCode 2.0.18 keeps each login as a row of the ``credential`` table in its SQLite database, ``<data>/opencode.db``
(``$XDG_DATA_HOME/opencode``, by default ``~/.local/share/opencode``; ``OPENCODE_DB`` names another), read in the pinned
bundle on 2026-10-25. A row's ``integration_id`` is the provider's id (the legacy import files each ``auth.json``
entry under its provider's key), and its ``value`` is JSON: ``{type: "key", key}`` for an API key, ``{type: "oauth",
methodID, refresh, access, expires, metadata}`` for a refreshing login.

AEW reads it and writes nothing (ADR-0009): SQLite's read-only mode with a busy timeout, never ``immutable``, since the
operator's own OpenCode may be writing it (WAL). What is read stays in this process's memory, for the relay; it is
never printed, logged or put in the sandbox. :func:`stored` returns the logins with what each holds, and the reason
when there are none to read.

The operator's own OpenCode wrote the store, and it may be newer than the 2.0.18 AEW pins (the designer's addendum 2 to
the CS-4 hand-off, ruling 1). A provider's row in a shape other than those two is ``unknown``: AEW never guesses at
it, and never falls back to an older row of that provider.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DB = "opencode.db"
BUSY_TIMEOUT_S = 5.0  # the operator's OpenCode holds its write lock briefly; a launch waits this long at most


UNKNOWN = "unknown"  # a row in a shape AEW does not know: nothing of it is read out


@dataclass(frozen=True)
class Login:
    """One provider's login: ``kind`` is ``key``, ``oauth`` or :data:`UNKNOWN`. ``secret`` (the key, or the OAuth
    access token) and ``metadata`` are never in ``repr``."""

    integration: str
    kind: str
    method: str | None = None
    secret: str = field(default="", repr=False)
    expires: int | None = None  # oauth: when the access token expires, in milliseconds since the epoch
    metadata: Mapping[str, Any] = field(default_factory=dict, repr=False)


def db_path(env: Mapping[str, str]) -> Path:
    """Where the operator's OpenCode keeps its database, from the operator's environment."""
    data = Path(env.get("XDG_DATA_HOME") or Path(env.get("HOME") or os.path.expanduser("~")) / ".local" / "share")
    named = env.get("OPENCODE_DB")
    if named:
        return Path(named) if os.path.isabs(named) else data / "opencode" / named
    return data / "opencode" / DB


def _read(integration: str, method: str | None, value: Any) -> Login:
    """A row as a :class:`Login`; :data:`UNKNOWN` unless its value is one of OpenCode 2.0.18's two shapes."""
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        parsed = None
    meta = parsed.get("metadata") if isinstance(parsed, dict) else None
    meta = {} if meta is None else meta  # absent, or JSON null: none
    if not isinstance(parsed, dict) or not isinstance(meta, dict):
        return Login(integration, UNKNOWN, method)
    if parsed.get("type") == "key" and isinstance(parsed.get("key"), str):
        return Login(integration, "key", method, parsed["key"], metadata=meta)
    expires = parsed.get("expires")
    if (parsed.get("type") == "oauth" and isinstance(parsed.get("access"), str)
            and isinstance(expires, (int, float)) and not isinstance(expires, bool)):
        return Login(integration, "oauth", str(parsed.get("methodID") or method or ""), parsed["access"], int(expires),
                     meta)
    return Login(integration, UNKNOWN, method)


def stored(env: Mapping[str, str]) -> tuple[list[Login], str | None]:
    """``(logins, why none)``: each provider's login, the active row where a provider has several (else its newest),
    sorted by provider; that row decides, :data:`UNKNOWN` when AEW does not know its shape. ``why`` says, in the
    operator's terms and without any value, why nothing could be read."""
    path = db_path(env)
    if not path.is_file():
        return [], f"no OpenCode login database at {path}"
    try:
        con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_S)
        try:
            rows = con.execute("SELECT integration_id, method_id, active, value, time_updated FROM credential "
                               "ORDER BY integration_id, active IS NOT 1, time_updated DESC").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        return [], f"the OpenCode login database at {path} could not be read ({type(exc).__name__})"
    out: dict[str, Login] = {}
    for integration, method, _active, value, _updated in rows:
        if integration and integration not in out:
            out[integration] = _read(str(integration), method, value)
    return [out[k] for k in sorted(out)], None
