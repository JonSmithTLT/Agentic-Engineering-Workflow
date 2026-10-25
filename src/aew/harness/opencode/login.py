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


@dataclass(frozen=True)
class Login:
    """One provider's login: ``kind`` is ``key`` or ``oauth``. ``secret`` (the key, or the OAuth access token) and
    ``metadata`` are never in ``repr``."""

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


def stored(env: Mapping[str, str]) -> tuple[list[Login], str | None]:
    """``(logins, why none)``: each provider's login, the active row where a provider has several (else its newest),
    sorted by provider; ``why`` says, in the operator's terms and without any value, why nothing could be read."""
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
        if not integration or integration in out:
            continue
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        raw_meta = parsed.get("metadata")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        if parsed.get("type") == "key" and isinstance(parsed.get("key"), str):
            out[integration] = Login(str(integration), "key", method, parsed["key"], metadata=meta)
        elif parsed.get("type") == "oauth" and isinstance(parsed.get("access"), str):
            expires = parsed.get("expires")
            out[integration] = Login(str(integration), "oauth", str(parsed.get("methodID") or method or ""),
                                     parsed["access"], int(expires) if isinstance(expires, (int, float)) else None,
                                     meta)
    return [out[k] for k in sorted(out)], None
