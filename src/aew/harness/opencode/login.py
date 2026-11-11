"""The operator's stored OpenCode login, read on the host for contained provider relays.

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
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.harness.opencode import capabilities

DB = "opencode.db"
BUSY_TIMEOUT_S = 5.0  # the operator's OpenCode holds its write lock briefly; a launch waits this long at most
# The files SQLite keeps beside a database (its write-ahead log, the log's index, the rollback journal): they hold rows
# not yet in the database, and appear and go while the database is open, after any launch.
SIDECARS = ("-wal", "-shm", "-journal")
# Where OpenCode keeps each kind of directory under the home directory when its XDG variable is unset.
XDG_DEFAULTS = {"data": (".local", "share"), "config": (".config",), "state": (".local", "state"),
                "cache": (".cache",)}


UNKNOWN = "unknown"  # a row in a shape AEW does not know: nothing of it is read out
# The ``credential`` table as OpenCode 2.0.18's migrations leave it (read in the 2.0.18 bundle; unchanged at 2.2.6,
# measured by tools/harness_qualify's `login.store`): each column's name and declared type, in order. The Lead's
# login seed writes only to a table exactly like it, and skips any other, so a newer OpenCode's schema is met by not
# writing, never by a row in a shape AEW guessed at (E118).
CREDENTIAL_SCHEMA = (("id", "text"), ("integration_id", "text"), ("label", "text"), ("value", "text"),
                     ("connector_id", "text"), ("method_id", "text"), ("active", "integer"),
                     ("time_created", "integer"), ("time_updated", "integer"))
CREDENTIAL_COLUMNS = ("id", "integration_id", "label", "value", "method_id", "active", "time_created", "time_updated")
# S608: the statement is built from the constant column names above; the values are bound parameters.
CREDENTIAL_INSERT = (f"INSERT INTO credential ({', '.join(CREDENTIAL_COLUMNS)}) "  # noqa: S608
                     f"VALUES ({', '.join('?' * len(CREDENTIAL_COLUMNS))})")
# Where 2.0.18 keeps each session's own permission rules (evaluated after the agent's): the ``permission`` column of
# its session table, ``session_v2`` (``session`` before the migration that renamed it), read in the 2.0.18 bundle;
# still ``session_v2`` at 2.2.6, and no other table holds the column (measured, `login.store`).
SESSION_TABLES = ("session_v2", "session")
SESSION_RULES_COLUMN = "permission"
STORE_OUTSIDE_STATE = "lead_store_outside_state"


class StoreSchemaChanged(sqlite3.DatabaseError):
    """A table of an OpenCode store is not the one AEW knows (the pinned version's)."""


def _columns(con: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [(row[1], str(row[2]).lower()) for row in con.execute(f"PRAGMA table_info({table})")]


def require_schema(con: sqlite3.Connection, table: str, schema: tuple[tuple[str, str], ...]) -> None:
    """Raise :class:`StoreSchemaChanged` unless ``table``'s columns are exactly ``schema``: the same names, declared
    types and order, none missing and none extra."""
    have = _columns(con, table)
    if have != list(schema):
        names, known = dict(have), dict(schema)
        diff = [*(f"no {n}" for n in known if n not in names), *(f"an extra {n}" for n in names if n not in known),
                *(f"{n} {names[n]}, not {known[n]}" for n in known if n in names and names[n] != known[n])]
        raise StoreSchemaChanged(f"the {table} table is not OpenCode {', '.join(capabilities.TESTED_VERSIONS)}'s: "
                                 f"{', '.join(diff) or 'its columns are in another order'}")


def own_store(db: Path, state: Path) -> None:
    """Refuse (``CONTAINMENT_UNAVAILABLE``, :data:`STORE_OUTSIDE_STATE`) unless the Lead's store, its directory and
    each file SQLite keeps beside it, where present, are a regular file (a directory for the directory) whose real path
    lies inside the Lead's state directory: AEW writes that store on the host, so it writes nothing else (E118)."""
    from aew.errors import ContainmentUnavailable

    root = Path(os.path.realpath(state))
    for path in (db.parent, db, *(db.with_name(db.name + s) for s in SIDECARS)):
        if not os.path.lexists(path):
            continue
        kind = stat.S_ISDIR if path == db.parent else stat.S_ISREG
        if not kind(os.lstat(path).st_mode) or not Path(os.path.realpath(path)).is_relative_to(root):
            raise ContainmentUnavailable(
                f"the contained Lead's OpenCode store must be a regular file inside its state directory ({state}), "
                f"and {path} is not: move it aside, then start `aew opencode` again", reason=STORE_OUTSIDE_STATE,
                path=str(path))


def clear_failure_step(db: Path, exc: BaseException) -> str:
    """What the operator does when the Lead's store could not be cleared: wait for a busy store, else move it aside."""
    if isinstance(exc, sqlite3.OperationalError) and any(w in str(exc).lower() for w in ("locked", "busy")):
        return f"start `aew opencode` again once nothing holds {db}"
    return (f"move {db} aside (OpenCode makes a new one, without the Lead's earlier sessions), then start "
            f"`aew opencode` again")


def clear_saved_permissions(db: Path, state: Path) -> int:
    """Remove every saved permission and every session's own permission rules from the contained Lead's own OpenCode
    store (never the operator's, which AEW only reads), and return how many rows changed: the contained Lead starts
    each session with none (E118). OpenCode 2.0.18 keeps the saved ones in the ``permission`` table, in either of its
    two schemas, so the whole table is cleared whatever its columns, and a session's rules in its session table's
    ``permission`` column (:data:`SESSION_TABLES`), set to null. No database, or no such table, means nothing is kept;
    a session table without that column is a schema AEW does not know (:class:`StoreSchemaChanged`). The store must be
    the Lead's own (:func:`own_store`). A failure raises (:class:`OSError`, :class:`sqlite3.Error`), for the caller to
    refuse the start."""
    own_store(db, state)
    if not db.is_file():
        return 0
    con = sqlite3.connect(db, timeout=BUSY_TIMEOUT_S)
    try:
        with con:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            changed = con.execute("DELETE FROM permission").rowcount if "permission" in tables else 0
            for table in (t for t in SESSION_TABLES if t in tables):
                if SESSION_RULES_COLUMN not in dict(_columns(con, table)):
                    raise StoreSchemaChanged(f"the {table} table has no {SESSION_RULES_COLUMN} column")
                # S608: the table and column names are the constants above
                changed += con.execute(f"UPDATE {table} SET {SESSION_RULES_COLUMN} = NULL "  # noqa: S608
                                       f"WHERE {SESSION_RULES_COLUMN} IS NOT NULL").rowcount
            return changed
    finally:
        con.close()


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


def operator_dir(env: Mapping[str, str], kind: str) -> Path:
    """The operator's OpenCode directory of ``kind`` (``data``, ``config``, ``state`` or ``cache``), from their
    environment: ``$XDG_<KIND>_HOME/opencode``, or its default under the home directory (:data:`XDG_DEFAULTS`)."""
    home = Path(env.get("HOME") or os.path.expanduser("~"))
    return Path(env.get(f"XDG_{kind.upper()}_HOME") or home.joinpath(*XDG_DEFAULTS[kind])) / "opencode"


def db_path(env: Mapping[str, str]) -> Path:
    """Where the operator's OpenCode keeps its database, from the operator's environment."""
    named = env.get("OPENCODE_DB")
    if named:
        return Path(named) if os.path.isabs(named) else operator_dir(env, "data") / named
    return operator_dir(env, "data") / DB


def store_files(env: Mapping[str, str], *, real: bool = False) -> list[Path]:
    """The login database and the files SQLite keeps beside it (:data:`SIDECARS`), where the environment puts it or,
    with ``real``, where it really is."""
    db = Path(os.path.realpath(db_path(env))) if real else db_path(env)
    return [db, *(db.with_name(db.name + suffix) for suffix in SIDECARS)]


def operator_masks(env: Mapping[str, str]) -> dict[Path, tuple[str, ...]]:
    """``{directory: the variable that puts it there, none where it is OpenCode's default}``: the operator's OpenCode
    data, configuration, state and cache directories, as the operator's environment puts them, which a contained run
    masks whole (``containment.layout``; STG-05 CS-4, outcome 2, and addendum 4, ruling 2). The files it keeps
    elsewhere are :func:`operator_files`."""
    out: dict[Path, tuple[str, ...]] = {}
    for kind in XDG_DEFAULTS:  # two variables may put two kinds in one directory: each is named
        variable = f"XDG_{kind.upper()}_HOME"
        out[operator_dir(env, kind)] = (*out.get(operator_dir(env, kind), ()), *((variable,) if env.get(variable)
                                                                                 else ()))
    return out


def operator_files(env: Mapping[str, str]) -> dict[Path, tuple[str, ...]]:
    """``{file: the variable that puts it there}``: the files of the operator's OpenCode that may lie outside
    :func:`operator_masks`' directories, which a contained run leaves out of their directories (``containment.layout``;
    STG-05 CS-4, addendum 6): the login database with its sidecars (:func:`store_files`), and the configuration file
    ``OPENCODE_CONFIG`` names, each where the variable puts it and where it really is. A file may be absent: its name is
    left out all the same, so one made during the session is not seen."""
    out: dict[Path, tuple[str, ...]] = {}
    data = "XDG_DATA_HOME" if env.get("XDG_DATA_HOME") else None
    db = ("OPENCODE_DB",) if env.get("OPENCODE_DB") else (data,) if data else ()
    for path in (*store_files(env), *store_files(env, real=True)):
        out.setdefault(path, db)
    if env.get("OPENCODE_CONFIG"):
        named = Path(os.path.abspath(env["OPENCODE_CONFIG"]))
        for path in (named, Path(os.path.realpath(named))):
            out.setdefault(path, ("OPENCODE_CONFIG",))
    return out


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


@dataclass(frozen=True)
class WorkerKey:
    secret: str = field(repr=False)
    generation: tuple[int, int | None]


def worker_keys(env: Mapping[str, str], providers: set[str]) -> tuple[dict[str, WorkerKey], str | None]:
    """Read the deciding API-key rows for the requested providers in one bounded operation.

    The deciding row may be of another kind. In that case SQLite returns no credential material
    for it, and the host does not fall back to an older row. Diagnostics never include the path.
    """
    if not providers:
        return {}, None
    path = db_path(env)
    if not path.is_absolute():
        return {}, "the stored OpenCode login database needs an absolute location"
    if not path.is_file():
        return {}, "the stored OpenCode login database is missing"
    try:
        con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_S)
        try:
            rows = con.execute(
                "WITH deciding AS (SELECT integration_id, rowid, time_updated, value, "
                "row_number() OVER (PARTITION BY integration_id "
                "ORDER BY active IS NOT 1, time_updated DESC, rowid DESC) AS rank "
                "FROM credential WHERE integration_id IN (SELECT value FROM json_each(?))) "
                "SELECT integration_id, rowid, time_updated, "
                "CASE WHEN json_valid(value) THEN CASE WHEN json_extract(value, '$.type') = 'key' "
                "THEN value END END FROM deciding WHERE rank = 1",
                (json.dumps(sorted(providers)),),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        locked = getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
        return {}, f"the stored OpenCode login database is {'locked' if locked else 'unreadable'}"
    if not rows:
        return {}, "the stored OpenCode API-key row is missing"
    found: dict[str, WorkerKey] = {}
    for provider, rowid, updated, value in rows:
        entry = _read(provider, None, value)
        if entry.kind == "key" and entry.secret:
            found[provider] = WorkerKey(entry.secret, (rowid, updated if type(updated) is int else None))
    return found, None if found else "the stored OpenCode login has no supported API-key row"
