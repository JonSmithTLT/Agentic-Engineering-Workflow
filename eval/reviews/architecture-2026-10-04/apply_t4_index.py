"""Index changes for the ADR-0013 prototype: about(), current() with the disposition fold, FTS5 over knowledge record
bodies, search(). Run from tree/."""
from __future__ import annotations

from pathlib import Path

P = Path("src/aew/history/index.py")
s = P.read_text(encoding="utf-8")


def rep(old: str, new: str) -> None:
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, 1)


rep('from aew.errors import IntegrityError, LockTimeout\n', 'from aew.errors import IntegrityError, LockTimeout, UsageError\n')

rep('''CREATE INDEX IF NOT EXISTS links_dst ON links (dst);
"""
''', '''CREATE INDEX IF NOT EXISTS links_dst ON links (dst);
"""
# Full-text search over knowledge record bodies (ADR-0013 draft D8). Derived like everything else here, and a hit is a
# locator: the entry at its position is authenticated before anything is shown, so a tampered body hides a record and
# never invents one. Created only where this SQLite has FTS5.
_FTS_SCHEMA = "CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(seq UNINDEXED, id UNINDEXED, kind UNINDEXED, body)"
# The current state of a knowledge record is a fold over its disposition entries in manifest order (shared semantics
# §4.2, §7): admission, serving hold, lifecycle. Never written back.
ADMISSION_RELS = ("admitted", "held_active", "held_dormant", "rejected", "superseded_proposal")
LIFECYCLE_RELS = ("superseded_by", "quarantined", "archived")


def fold_dispositions(dispositions: list[dict[str, Any]]) -> dict[str, Any]:
    """The current operational state of a knowledge record from its disposition entries, in manifest order."""
    admission, serving_hold, lifecycle, challenges = "candidate", False, "active", 0
    for d in dispositions:
        rel = d.get("rel")
        if rel in ADMISSION_RELS:
            admission = str(rel)
        elif rel == "serving_hold":
            serving_hold = True
        elif rel == "serving_release":
            serving_hold = False
        elif rel in LIFECYCLE_RELS:
            lifecycle = {"superseded_by": "superseded_within_scope"}.get(str(rel), str(rel))
        elif rel == "challenged":
            challenges += 1
    return {"admission": admission, "serving_hold": serving_hold, "lifecycle": lifecycle, "challenges": challenges,
            "disposition_seq": len(dispositions),
            "last_event_seq": dispositions[-1]["seq"] if dispositions else None}
''')

rep('''        self.root: dict[str, Any] | None = None  # that root, which every query result is authenticated against
''', '''        self.root: dict[str, Any] | None = None  # that root, which every query result is authenticated against
        self.fts: bool | None = None  # whether this SQLite has FTS5 (known after the first connection)
''')

rep('''        conn = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        try:
            conn.executescript(_SCHEMA)
            yield conn''', '''        conn = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        try:
            conn.executescript(_SCHEMA)
            if self.fts is not False:
                try:
                    conn.execute(_FTS_SCHEMA)
                    self.fts = True
                except sqlite3.OperationalError:
                    self.fts = False
            yield conn''')

rep('''                    mode, since = "rebuilt", None
                    conn.execute("DELETE FROM entries")
                    conn.execute("DELETE FROM links")''', '''                    mode, since = "rebuilt", None
                    conn.execute("DELETE FROM entries")
                    conn.execute("DELETE FROM links")
                    if self.fts:
                        conn.execute("DELETE FROM fts")''')

rep('''    @staticmethod
    def _insert(conn: sqlite3.Connection, e: dict[str, Any]) -> None:
        conn.execute(''', '''    def _insert(self, conn: sqlite3.Connection, e: dict[str, Any]) -> None:
        conn.execute(''')

rep('''        conn.executemany("INSERT INTO links (seq, src, rel, dst) VALUES (?, ?, ?, ?)",
                         [(e["seq"], e["id"], rel, dst) for rel, dsts in sorted((e.get("links") or {}).items())
                          for dst in dsts])
''', '''        conn.executemany("INSERT INTO links (seq, src, rel, dst) VALUES (?, ?, ?, ?)",
                         [(e["seq"], e["id"], rel, dst) for rel, dsts in sorted((e.get("links") or {}).items())
                          for dst in dsts])
        if self.fts and e["kind"] in M.KNOWLEDGE_KINDS:  # the record's text, for search; a missing file indexes empty
            conn.execute("DELETE FROM fts WHERE seq = ?", (e["seq"],))
            try:
                body = (self.history.root / e["path"]).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                body = ""
            conn.execute("INSERT INTO fts (seq, id, kind, body) VALUES (?, ?, ?, ?)", (e["seq"], e["id"], e["kind"], body))
''')

rep('''    def annotations(self, subject: str) -> list[dict[str, Any]]:
        return self._rows("SELECT body FROM entries WHERE kind = 'annotation' AND subject = ? AND seq <= ? "
                          "ORDER BY seq", (subject, self._upto()),
                          lambda e: e["kind"] == "annotation" and e.get("subject") == subject)
''', '''    def about(self, subject: str, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        """Every entry about ``subject`` (an annotation about an archived unit, a disposition about a knowledge
        record), optionally of the given kinds, in history order (ADR-0013 draft D4)."""
        if kinds:
            marks = ", ".join("?" for _ in kinds)
            # The clause is built from placeholders only; every value is bound.
            sql = f"SELECT body FROM entries WHERE subject = ? AND kind IN ({marks}) AND seq <= ? ORDER BY seq"  # noqa: S608
            return self._rows(sql, (subject, *kinds, self._upto()),
                              lambda e: e.get("subject") == subject and e["kind"] in kinds)
        return self._rows("SELECT body FROM entries WHERE subject = ? AND seq <= ? ORDER BY seq", (subject, self._upto()),
                          lambda e: e.get("subject") == subject)

    def annotations(self, subject: str) -> list[dict[str, Any]]:
        return self.about(subject, kinds=("annotation",))

    def versions(self, knowledge_id: str) -> list[dict[str, Any]]:
        """The content versions of a knowledge record (reference, case or lesson entries with that id), in order."""
        return [e for e in self.by_id(knowledge_id) if e["kind"] in M.CONTENT_KINDS]

    def current(self, knowledge_id: str) -> dict[str, Any] | None:
        """The latest content version of a knowledge record and the fold of its dispositions, or None."""
        versions = self.versions(knowledge_id)
        if not versions:
            return None
        latest = versions[-1]
        dispositions = self.about(knowledge_id, kinds=("disposition",))
        return {"id": knowledge_id, "kind": latest["kind"], "version": latest.get("version"), "entry_seq": latest["seq"],
                "versions": [{"version": v.get("version"), "seq": v["seq"], "sha256": v["sha256"]} for v in versions],
                **fold_dispositions(dispositions),
                "dispositions": [{"seq": d["seq"], "id": d["id"], "rel": d.get("rel"), "at": d["at"],
                                  "links": d.get("links") or {}} for d in dispositions]}

    def search(self, query: str, *, kinds: tuple[str, ...] | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Knowledge entries whose record body matches the FTS5 ``query``, best first. The FTS rows only locate: the
        returned entries are the history's own, authenticated at their positions (``_rows``)."""
        if self.root is None:
            raise IntegrityError("the history index was queried before it was synced to a root")
        if not self.fts:
            raise UsageError("full-text search needs an SQLite with FTS5, which this Python's sqlite3 lacks")
        with self._db() as conn:
            try:
                rows = conn.execute("SELECT seq FROM fts WHERE fts MATCH ? AND seq <= ? ORDER BY rank LIMIT ?",
                                    (query, self._upto(), limit * 2)).fetchall()
            except sqlite3.OperationalError as exc:
                raise UsageError(f"search query not accepted by FTS5: {exc}") from exc
        seqs = [int(r[0]) for r in rows]
        if not seqs:
            return []
        marks = ", ".join("?" for _ in seqs)
        sql = f"SELECT body FROM entries WHERE seq IN ({marks}) AND seq <= ? ORDER BY seq"  # noqa: S608
        entries = self._rows(sql, (*seqs, self._upto()),
                             lambda e: e["kind"] in M.KNOWLEDGE_KINDS and (not kinds or e["kind"] in kinds))
        order = {seq: i for i, seq in enumerate(seqs)}
        return sorted(entries, key=lambda e: order[e["seq"]])[:limit]
''')

P.write_text(s, encoding="utf-8", newline="\n")
print("index patched")
