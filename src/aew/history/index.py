"""The derived history lookup index: ``local/history.sqlite`` (ADR-0011; investigation §3.3).

It is never authoritative. It records the root it was built against; ``sync`` brings it to a newer root by walking
only the entries appended since (when the newer root extends the recorded one), and rebuilds it from the manifest
otherwise, or when the database is missing or damaged. Both walks check the hash chain (``History.walk``), so the
index only ever holds entries whose membership in the history the current root pins has been established.

It serves the history surface: an exact lookup by id, a listing by kind and date range, the links an entry records
and the annotations about a subject, and the set of referenced paths (for unreachable-record reports).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aew.history import manifest as M
from aew.history.store import History

INDEX_REL = "local/history.sqlite"
INDEX_VERSION = "1"

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

    def __init__(self, aew_root: Path) -> None:
        self.history = History(aew_root)
        self.path = aew_root / INDEX_REL
        self.upto: int | None = None  # queries see entries up to the root last synced to (another process may be ahead)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()  # never left open: on Windows an open handle would block a rebuild's delete

    # ------------------------------------------------------------------ freshness

    def sync(self, root: dict[str, Any]) -> dict[str, Any]:
        """Bring the index to ``root``: ``{"mode": "current" | "ahead" | "caught_up" | "rebuilt", "added": n}``.
        ``ahead``: another process already indexed a later root that extends this one; queries then stop at ``root``.
        """
        try:
            out = self._sync(root)
        except sqlite3.DatabaseError:  # damaged or not a database: derived data, so start over
            self.path.unlink(missing_ok=True)
            out = self._sync(root)
        self.upto = root["count"]
        return out

    def _sync(self, root: dict[str, Any]) -> dict[str, Any]:
        with self._db() as conn:
            conn.execute("BEGIN IMMEDIATE")  # one writer at a time; readers see the previous root until COMMIT
            try:
                built = self._built(conn)
                target = {"count": root["count"], "h": root["head_h"]}
                if built == target:
                    conn.execute("ROLLBACK")
                    return {"mode": "current", "added": 0}
                ahead = built is not None and built["count"] > root["count"]
                if ahead and self._indexed_h(conn, root) == root["head_h"]:
                    conn.execute("ROLLBACK")
                    return {"mode": "ahead", "added": 0}
                mode = "caught_up"
                since = built
                if built is None or built["count"] > root["count"] or not self._on_chain(root, built):
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
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        if meta.get("version") != INDEX_VERSION or "count" not in meta:
            return None
        return {"count": int(meta["count"]), "h": meta["h"]}

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

    def _rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._db() as conn:
            rows = [json.loads(body) for (body,) in conn.execute(sql, args).fetchall()]
        return [r for r in rows if self.upto is None or r["seq"] <= self.upto]

    def by_id(self, record_id: str) -> list[dict[str, Any]]:
        """Every entry for ``record_id`` (a unit has one; an audit or Lead record id likewise), in history order."""
        return self._rows("SELECT body FROM entries WHERE id = ? ORDER BY seq", (record_id,))

    def list(self, *, kind: str | None = None, since: str | None = None, until: str | None = None,
             limit: int | None = None) -> list[dict[str, Any]]:
        """Entries by kind and a date range (``at`` compares as ISO-8601 text), newest first."""
        where, args = [], []
        for clause, value in (("kind = ?", kind), ("at >= ?", since), ("at <= ?", until)):
            if value is not None:
                where.append(clause)
                args.append(value)
        sql = "SELECT body FROM entries" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY seq DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        return self._rows(sql, tuple(args))

    def units(self, state: str) -> list[dict[str, Any]]:
        """Archived unit entries in a finished state (DONE or CANCELLED), in history order."""
        return self._rows("SELECT body FROM entries WHERE kind = 'unit' AND state = ? ORDER BY seq", (state,))

    def children(self, parent: str) -> list[dict[str, Any]]:
        """Unit entries archived with ``parent`` as their parent (a move later is an annotation: apply those)."""
        return self._rows("SELECT body FROM entries WHERE kind = 'unit' AND parent = ? ORDER BY seq", (parent,))

    def linked(self, rel: str, target: str) -> list[dict[str, Any]]:
        """Entries that record a ``rel`` link to ``target`` (the unit that archived an invocation or a credential)."""
        return self._rows("SELECT e.body FROM entries e JOIN links l ON l.seq = e.seq WHERE l.rel = ? AND l.dst = ? "
                          "ORDER BY e.seq", (rel, target))

    def annotations(self, subject: str) -> list[dict[str, Any]]:
        return self._rows("SELECT body FROM entries WHERE kind = 'annotation' AND subject = ? ORDER BY seq",
                          (subject,))

    def links(self, record_id: str) -> list[dict[str, str]]:
        """The links recorded from ``record_id``'s entries, and to it from others."""
        with self._db() as conn:
            out = [{"from": s, "rel": r, "to": d} for s, r, d in conn.execute(
                "SELECT src, rel, dst FROM links WHERE src = ? OR dst = ? ORDER BY seq, rel, dst",
                (record_id, record_id)).fetchall()]
        return out

    def paths(self) -> set[str]:
        with self._db() as conn:
            return {p for (p,) in conn.execute("SELECT path FROM entries").fetchall()}
