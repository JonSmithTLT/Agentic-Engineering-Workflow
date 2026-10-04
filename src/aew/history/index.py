"""The derived history lookup index: ``local/history.sqlite`` (ADR-0011; investigation §3.3).

It is never authoritative. It records the root it was built against; ``sync`` brings it to a newer root by walking
only the entries appended since (when the newer root extends the recorded one), and rebuilds it from the manifest
otherwise, or when the database is missing, damaged or records no usable root. A database that is only busy (another
process holds its write lock past the timeout) is never mistaken for damage: that is a ``LockTimeout``, and the file
is kept. Both walks check the hash chain (``History.walk``), so the index is built only from entries whose
membership in the history the current root pins has been established.

The index is a locator, never a voucher (independent P3 review, P3-1). The file sits in the project and is not covered
by any hash, so whatever a query returns is authenticated before it is used: each entry is checked against the entry
the root pins at its position (``History.authenticate``, reading each history file once per query), and against the
query's own condition, so a row that names another entry, or holds other columns, or other links, than its entry is
caught. A mismatch rebuilds the index from the history and runs the query again; a second one is an
``IntegrityError``. Missing rows are caught at sync (the rows must be exactly the root's positions). What a query
cannot see is a row whose columns were altered so that it no longer matches: that index omits a record rather than
inventing one, and the explicit full audit compares every row with the history (``check``).

It serves the history surface: an exact lookup by id, a listing by kind and date range, the links an entry records
and the annotations about a subject, and the set of referenced paths (for unreachable-record reports).
"""

from __future__ import annotations

import atexit
import errno
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aew.errors import IntegrityError, LockTimeout
from aew.history import manifest as M
from aew.history.store import EntryMismatch, History

INDEX_REL = "local/history.sqlite"
INDEX_VERSION = "1"
_COUNT = re.compile(r"[0-9]+")
_HASH = re.compile(r"[0-9a-f]{64}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries (
    seq INTEGER PRIMARY KEY, id TEXT NOT NULL, kind TEXT NOT NULL, state TEXT, at TEXT NOT NULL, parent TEXT,
    source TEXT, subject TEXT, rel TEXT, path TEXT NOT NULL, sha256 TEXT NOT NULL, h TEXT NOT NULL,
    segment INTEGER NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS links (seq INTEGER NOT NULL, src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entries_id ON entries (id);
CREATE INDEX IF NOT EXISTS entries_kind_at ON entries (kind, at);
CREATE INDEX IF NOT EXISTS entries_subject ON entries (subject);
CREATE INDEX IF NOT EXISTS links_seq ON links (seq);
CREATE INDEX IF NOT EXISTS links_src ON links (src);
CREATE INDEX IF NOT EXISTS links_dst ON links (dst);
"""


class HistoryIndex:
    """The lookup index of the history under ``aew_root``."""

    def __init__(self, aew_root: Path, *, timeout: float = 30.0) -> None:
        self.history = History(aew_root)
        self.path = aew_root / INDEX_REL
        self.timeout = timeout  # how long to wait for another writer before reporting the index busy
        self.upto: int | None = None  # queries see entries up to the root last synced to (another process may be ahead)
        self.root: dict[str, Any] | None = None  # that root, which every query result is authenticated against

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        try:
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()  # never left open: on Windows an open handle would block a rebuild's delete

    # ------------------------------------------------------------------ freshness

    def sync(self, root: dict[str, Any], *, private_when_busy: bool = False) -> dict[str, Any]:
        """Bring the index to ``root``: ``{"mode": "current" | "ahead" | "caught_up" | "rebuilt", "added": n}``.
        ``ahead``: another process already indexed a later root that extends this one; queries then stop at ``root``.

        ``private_when_busy``: when another process holds the shared index, build a private one from the history
        instead of failing. A transaction that needs a cold fact uses this, so a derived file never fails an
        authoritative commit (area 5 F3).
        """
        try:
            out = self._sync(root)
        except (sqlite3.DatabaseError, OSError) as exc:
            if _read_only(exc, self.path):  # a read-only view of the project (a contained run, M4-B)
                self._use_private_copy()
                out = self._sync(root)
                self.upto = root["count"]
                self.root = dict(root)
                return out
            if isinstance(exc, OSError):
                raise
            if _contended(exc) and private_when_busy:  # leave the shared index to its writer
                self._use_private_copy(copy=False)
                out = self._sync(root)
                self.upto = root["count"]
                self.root = dict(root)
                return out
            if _contended(exc):  # healthy but busy: keep it, and say so
                raise LockTimeout(f"the history index {INDEX_REL} is busy: {exc}") from exc
            self.path.unlink(missing_ok=True)  # damaged or not a database: derived data, so start over
            out = self._sync(root)
        self.upto = root["count"]
        self.root = dict(root)
        return out

    def _use_private_copy(self, *, copy: bool = True) -> None:
        """Continue on a private copy of the index (derived data, re-verified against the history on every use), for
        a process that may read the project but not write it: a contained run's own `aew` commands (M4-B). Without
        ``copy`` the private index starts empty and is built from the history (the shared file may be mid-write)."""
        folder = tempfile.mkdtemp(prefix="aew-history-index-")
        atexit.register(shutil.rmtree, folder, ignore_errors=True)
        private = Path(folder) / self.path.name
        if copy and self.path.exists():
            shutil.copy2(self.path, private)
        self.path = private

    def _rebuild(self) -> None:
        """Start over from the history the synced root pins (the index disagreed with it)."""
        assert self.root is not None
        self.path.unlink(missing_ok=True)
        self._sync(self.root)

    def _sync(self, root: dict[str, Any]) -> dict[str, Any]:
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")  # one writer at a time; readers see the previous root until COMMIT
            try:
                built = self._built(conn)
                target = {"count": root["count"], "h": root["head_h"]}
                complete = built is not None and self._complete(conn, min(built["count"], root["count"]))
                if built == target and complete:
                    conn.execute("ROLLBACK")
                    return {"mode": "current", "added": 0}
                ahead = built is not None and built["count"] > root["count"]
                if ahead and complete and self._indexed_h(conn, root) == root["head_h"]:
                    conn.execute("ROLLBACK")
                    return {"mode": "ahead", "added": 0}
                mode = "caught_up"
                since = built
                if built is None or built["count"] > root["count"] or not complete \
                        or not self._on_chain(root, built):
                    mode, since = "rebuilt", None
                    conn.execute("DELETE FROM entries")
                    conn.execute("DELETE FROM links")
                added = 0
                for entry in self.history.walk(root, since):
                    self._insert(conn, entry)
                    added += 1
                conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                                 [("version", INDEX_VERSION), ("count", str(target["count"])), ("h", target["h"])])
                conn.execute("COMMIT")
                return {"mode": mode, "added": added}
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    @staticmethod
    def _built(conn: sqlite3.Connection) -> dict[str, Any] | None:
        """The chain state the index was built to, or None (rebuild) when its metadata is missing or malformed."""
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        count, h = meta.get("count"), meta.get("h")
        if (meta.get("version") != INDEX_VERSION or not isinstance(count, str) or not _COUNT.fullmatch(count)
                or not isinstance(h, str) or not _HASH.fullmatch(h)):
            return None
        return {"count": int(count), "h": h}

    @staticmethod
    def _complete(conn: sqlite3.Connection, count: int) -> bool:
        """The index holds exactly one row for each of the first ``count`` positions (a deleted row is caught here)."""
        n, low, high = conn.execute("SELECT COUNT(*), MIN(seq), MAX(seq) FROM entries WHERE seq <= ?",
                                    (count,)).fetchone()
        return (n, low, high) == ((count, 1, count) if count else (0, None, None))

    @staticmethod
    def _indexed_h(conn: sqlite3.Connection, root: dict[str, Any]) -> str | None:
        if root["count"] == 0:
            return M.GENESIS_H
        row = conn.execute("SELECT h FROM entries WHERE seq = ?", (root["count"],)).fetchone()
        return row[0] if row else None

    def _on_chain(self, root: dict[str, Any], built: dict[str, Any]) -> bool:
        if built["count"] == 0:
            return built["h"] == M.GENESIS_H
        return self.history.entry(root, built["count"])["h"] == built["h"]

    @staticmethod
    def _insert(conn: sqlite3.Connection, e: dict[str, Any]) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO entries (seq, id, kind, state, at, parent, source, subject, rel, path, sha256, h,"
            " segment, body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (e["seq"], e["id"], e["kind"], e.get("state"), e["at"], e.get("parent"), e.get("source"),
             e.get("subject"), e.get("rel"), e["path"], e["sha256"], e["h"], M.segment_of(e["seq"]),
             json.dumps(e, sort_keys=True)))
        conn.execute("DELETE FROM links WHERE seq = ?", (e["seq"],))
        conn.executemany("INSERT INTO links (seq, src, rel, dst) VALUES (?, ?, ?, ?)",
                         [(e["seq"], e["id"], rel, dst) for rel, dsts in sorted((e.get("links") or {}).items())
                          for dst in dsts])

    # ------------------------------------------------------------------ queries (call ``sync`` first)

    def _upto(self) -> int:
        """The last sequence number queries may see: the root last synced to (another process may have indexed more)."""
        return self.upto if self.upto is not None else 2 ** 62

    def _rows(self, sql: str, args: tuple[Any, ...] = (),
              keep: Callable[[dict[str, Any]], bool] = lambda e: True) -> list[dict[str, Any]]:
        """``sql`` selects entry bodies and binds the snapshot bound (``_upto``) itself, before any ordering or limit.
        The bodies are only locators: the result is the history's own entries at those positions, each of which must
        also satisfy the query (``keep``). Anything else rebuilds the index once and asks again."""
        if self.root is None:
            raise IntegrityError("the history index was queried before it was synced to a root")
        for attempt in range(2):
            with self._db() as conn:
                rows = conn.execute(sql, args).fetchall()
            try:
                bodies = [json.loads(row[0]) for row in rows]
                entries = self.history.authenticate(self.root, bodies)
                if all(keep(e) for e in entries):
                    return entries
            except (EntryMismatch, ValueError, TypeError, AttributeError):
                pass
            if attempt == 0:
                self._rebuild()
        raise IntegrityError(f"the history index disagrees with the history even after a rebuild ({INDEX_REL})")

    def by_id(self, record_id: str) -> list[dict[str, Any]]:
        """Every entry for ``record_id`` (a unit has one; an audit or Lead record id likewise), in history order."""
        return self._rows("SELECT body FROM entries WHERE id = ? AND seq <= ? ORDER BY seq", (record_id, self._upto()),
                          lambda e: e["id"] == record_id)

    def by_seq(self, seq: int) -> dict[str, Any] | None:
        """The entry with sequence number ``seq``, or None."""
        rows = self._rows("SELECT body FROM entries WHERE seq = ? AND seq <= ?", (seq, self._upto()),
                          lambda e: e["seq"] == seq)
        return rows[0] if rows else None

    def list(self, *, kind: str | None = None, since: str | None = None, until: str | None = None,
             limit: int | None = None) -> list[dict[str, Any]]:
        """Entries by kind and a date range (``at`` compares as ISO-8601 text), newest first."""
        where: list[str] = ["seq <= ?"]
        args: list[Any] = [self._upto()]
        for clause, value in (("kind = ?", kind), ("at >= ?", since), ("at <= ?", until)):
            if value is not None:
                where.append(clause)
                args.append(value)
        # The clauses are fixed strings above; every value is a bound parameter.
        sql = f"SELECT body FROM entries WHERE {' AND '.join(where)} ORDER BY seq DESC"  # noqa: S608
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        return self._rows(sql, tuple(args), lambda e: (kind is None or e["kind"] == kind)
                          and (since is None or e["at"] >= since) and (until is None or e["at"] <= until))

    def units(self, state: str) -> list[dict[str, Any]]:
        """Archived unit entries in a finished state (DONE or CANCELLED), in history order."""
        return self._rows("SELECT body FROM entries WHERE kind = 'unit' AND state = ? AND seq <= ? ORDER BY seq",
                          (state, self._upto()), lambda e: e["kind"] == "unit" and e.get("state") == state)

    def children(self, parent: str) -> list[dict[str, Any]]:
        """Unit entries archived with ``parent`` as their parent (a move later is an annotation: apply those)."""
        return self._rows("SELECT body FROM entries WHERE kind = 'unit' AND parent = ? AND seq <= ? ORDER BY seq",
                          (parent, self._upto()), lambda e: e["kind"] == "unit" and e.get("parent") == parent)

    def linked(self, rel: str, target: str) -> list[dict[str, Any]]:
        """Entries that record a ``rel`` link to ``target`` (the unit that archived an invocation or a credential)."""
        return self._rows("SELECT DISTINCT e.body, e.seq FROM entries e JOIN links l ON l.seq = e.seq "
                          "WHERE l.rel = ? AND l.dst = ? AND e.seq <= ? ORDER BY e.seq", (rel, target, self._upto()),
                          lambda e: target in (e.get("links") or {}).get(rel, []))

    def annotations(self, subject: str) -> list[dict[str, Any]]:
        return self._rows("SELECT body FROM entries WHERE kind = 'annotation' AND subject = ? AND seq <= ? "
                          "ORDER BY seq", (subject, self._upto()),
                          lambda e: e["kind"] == "annotation" and e.get("subject") == subject)

    def moves(self) -> dict[str, str | None]:
        """Each archived unit moved since it was archived, and its current parent: the target of its last ``moved_to``
        annotation (None: moved to the top level)."""
        out: dict[str, str | None] = {}
        for a in self._rows("SELECT body FROM entries WHERE kind = 'annotation' AND rel = 'moved_to' AND seq <= ? "
                            "ORDER BY seq", (self._upto(),),
                            lambda e: e["kind"] == "annotation" and e.get("rel") == "moved_to"):
            out[a["subject"]] = ((a.get("links") or {}).get("moved_to") or [None])[0]
        return out

    def links(self, record_id: str) -> list[dict[str, str]]:
        """The links recorded from ``record_id``'s entries, and to it from others: read from the authenticated
        entries themselves, the link rows only locating them."""
        entries = self._rows(
            "SELECT DISTINCT e.body, e.seq FROM entries e WHERE e.seq <= ? AND (e.id = ? OR e.seq IN "
            "(SELECT seq FROM links WHERE src = ? OR dst = ?)) ORDER BY e.seq",
            (self._upto(), record_id, record_id, record_id),
            lambda e: e["id"] == record_id or any(record_id in d for d in (e.get("links") or {}).values()))
        return [{"from": e["id"], "rel": rel, "to": dst} for e in entries
                for rel, dsts in sorted((e.get("links") or {}).items()) for dst in sorted(dsts)
                if e["id"] == record_id or dst == record_id]

    def paths(self) -> set[str]:
        return {e["path"] for e in self._rows("SELECT body FROM entries WHERE seq <= ? ORDER BY seq",
                                              (self._upto(),))}

    def check(self) -> bool:
        """Every row, column and link of the index against the history the synced root pins, rebuilding the index
        if any differs (the explicit full audit runs this: linear in history, like the audit itself). True: it was
        consistent."""
        assert self.root is not None
        with self._db() as conn:
            rows = conn.execute("SELECT seq, id, kind, state, at, parent, source, subject, rel, path, sha256, h, "
                                "segment, body FROM entries WHERE seq <= ? ORDER BY seq", (self.upto,)).fetchall()
            links = conn.execute("SELECT seq, src, rel, dst FROM links WHERE seq <= ? ORDER BY seq, rel, dst, src",
                                 (self.upto,)).fetchall()
        expected_rows, expected_links = [], []
        for e in self.history.walk(self.root):
            expected_rows.append((e["seq"], e["id"], e["kind"], e.get("state"), e["at"], e.get("parent"),
                                  e.get("source"), e.get("subject"), e.get("rel"), e["path"], e["sha256"], e["h"],
                                  M.segment_of(e["seq"]), json.dumps(e, sort_keys=True)))
            expected_links += [(e["seq"], e["id"], rel, dst) for rel, dsts in (e.get("links") or {}).items()
                               for dst in dsts]
        if rows == expected_rows and links == sorted(expected_links, key=lambda x: (x[0], x[2], x[3], x[1])):
            return True
        self._rebuild()
        return False


def _read_only(exc: BaseException, path: Path) -> bool:
    """The index cannot be written here because the filesystem (or its directory) is read-only."""
    if isinstance(exc, OSError):
        return exc.errno in (errno.EROFS, errno.EACCES, errno.EPERM)
    text = str(exc).lower()
    if "readonly database" in text or "read-only" in text:
        return True
    return "unable to open database file" in text and not os.access(path.parent, os.W_OK)


def _contended(exc: sqlite3.DatabaseError) -> bool:
    """Whether ``exc`` is SQLite's busy or locked condition rather than damage."""
    name = getattr(exc, "sqlite_errorname", "") or ""
    return name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))
