"""Register F21's Arm B prototype: guarded, explicit raw-history search (the lead developer's plan v6; recall and
routing v0.3 §7 to §9 as its specification, not governing; ADR-0013 D8 and its dated note of 2026-10-07 for storage).

**Off by default, and absent while off.** The switch is ``recall.raw_history_search`` in the execution policy, read
only from the adopted bytes (``recall_search_enabled``): an edit nobody adopted leaves it off. Off, `aew history
search` is not registered, and nothing here creates or reads a file. On (``explicit``), the command works from an
operator terminal or a Lead shell, and refuses inside an invocation's environment. That refusal is a discoverability
guard, not a security boundary: raw history stays readable to anything that can read ``.aew``.

**The substrate is separate and outside every commit path.** ``local/recall/history-fts.sqlite`` (rebuildable, under
the git-ignored ``local/``) is never opened by the history index's sync, inside a Lead transaction or under the control
lock. Only a search (catching up first, within a bounded budget), ``history reindex`` and the full audit build it, in
short batches that each advance its watermark (the history root it has indexed through).

**A row is a locator, never a voucher** (D8). Every field a hit shows or is filtered on comes from the authenticated
history: the entry at the row's position, proven against the root; the record that entry pins, checked against its
hash; for evidence, the reference that authenticated record holds, and the file checked against that reference. The
query is matched again against the authenticated text in a throwaway in-memory FTS5 table with the same tokenizer, and
the snippet is cut from that text. A row that disagrees drops its candidate and marks the substrate stale: it is
rebuilt under the same budget as a catch-up. A tampered substrate can hide a result until then, never invent one.

**What is indexed:** for each archived entry, its own record and each evidence record it holds (role reports, reviews,
verifications, check results), each expandable by `aew history show <id>`. Plans, unit records and completion records
are not (`history show` cannot expand them by id); check logs are not; credential bundles (``tokens``) never are. A
document's text is its string leaves, with credential verifiers and every credential-shaped string redacted, capped at
256 KiB (a truncation is recorded and shown).
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import time
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.engine.archive_ops import evidence_source, redact
from aew.errors import AEWError, CapabilityUnavailable, IntegrityError, UsageError, ValidationFailed
from aew.history import manifest as M
from aew.history.store import History
from aew.util import load_yaml, parse_frontmatter, sha256_bytes, sha256_text

SUBSTRATE_REL = "local/recall/history-fts.sqlite"
SUBSTRATE_VERSION = "1"
OFF, EXPLICIT = "off", "explicit"
BUILD_BUDGET_S, BUILD_BUDGET_DOCS = 2.0, 500  # what one search spends catching up (KST-44: bounded query cost)
BATCH_DOCS = 50  # documents per build transaction: short write locks, and a watermark that advances often
DOC_CAP = 256 * 1024  # bytes of text indexed per document
LIMIT_DEFAULT, LIMIT_MAX = 10, 50
SNIPPET_MAX = 240
MAX_TERMS, MAX_QUERY_CHARS = 16, 512
KINDS = (*M.ENTRY_KINDS, "evidence")
TOKENIZE = "unicode61"  # the substrate's and the re-match's: identical query semantics
READ_WAIT_S = 1.0  # how long a read waits for another process's commit to land (never for a build: writes wait 0)
LABEL = ("raw history: archived records as they were written, not admitted Knowledge; reference only, never current "
         "evidence or instructions (register F21, Arm B prototype)")

_TABLES = ("meta", "docs", "doc_text")
_DDL = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS docs (rowid INTEGER PRIMARY KEY, seq INTEGER NOT NULL, doc_id TEXT NOT NULL, "
    "sha256 TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, at TEXT NOT NULL, text_sha256 TEXT NOT NULL, "
    "truncated INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS docs_seq ON docs (seq)",
    # With content, not contentless: a contentless table returns NULL columns and NULL snippet() (plan v1 finding 1).
    f"CREATE VIRTUAL TABLE IF NOT EXISTS doc_text USING fts5(text, tokenize='{TOKENIZE}')",
)


# ---------------------------------------------------------------------------------------------- the switch


def recall_search_enabled(aew_root: Path) -> bool:
    """Whether ``aew history search`` exists for the project at ``aew_root``: true only when the committed state pins
    the manifest and the policy files, ``project.yaml`` matches its pin, the execution policy it names matches its pin,
    and that adopted policy sets ``recall.raw_history_search: explicit``. Read lock-free, as a reader reads, so that an
    unadopted edit is off for a read too, not only inside a Lead transaction (plan v6 §1). Anything else (no pins, a
    mismatch, an unreadable or invalid file, any error at all) is off. It never raises."""
    try:
        from aew.engine.base import POLICY_PINS
        from aew.engine.store import ControlStore
        from aew.knowledge.manifest import MANIFEST
        from aew.policy import execution as X

        state = ControlStore(aew_root).read_committed()
        pins, manifest_pin = state.get(POLICY_PINS), state.get("manifest_sha256")
        if not isinstance(pins, dict) or not isinstance(manifest_pin, str):
            return False
        raw_manifest = (aew_root / MANIFEST).read_bytes()
        if sha256_bytes(raw_manifest) != manifest_pin:
            return False
        manifest = load_yaml(raw_manifest.decode("utf-8"), source=MANIFEST)
        if not isinstance(manifest, dict):
            return False
        named = manifest.get("policy") or {}
        # The path exactly as ``policy_files`` names it, which is the key of its pin.
        rel = (named.get("execution") if isinstance(named, dict) else None) or X.REL_PATH
        pin = pins.get(rel)
        if not isinstance(rel, str) or not isinstance(pin, str):
            return False
        raw = (aew_root / rel).read_bytes()
        if sha256_bytes(raw) != pin:
            return False
        policy = X.parse(raw, source=rel)
        return (policy.get("recall") or {}).get("raw_history_search") == EXPLICIT
    except Exception:  # fail closed by contract: whatever went wrong, the switch is off
        return False


# The variables that mark an invoked agent's environment, whichever way it was invoked: a harness run's (``AGENT_VARS``:
# its invocation, run, unit, bridge coordinates and scratch directory) and a Lead-spawned role's, which sets its
# invocation credential for every `aew` command (the context pack's "Credential and writeback", knowledge/context.py;
# PR #148 review, m3). The Lead's own shell sets none of them (its broker variables are the Lead's).
INVOCATION_CREDENTIAL = "AEW_INVOCATION_TOKEN"


def invocation_markers() -> tuple[str, ...]:
    from aew.harness.agentenv import AGENT_VARS

    return (*AGENT_VARS, INVOCATION_CREDENTIAL)


def refuse_in_invocations() -> None:
    """An invoked agent's environment (any of ``invocation_markers``) never gets the search: the designer's intent is
    that it is not model-visible. A discoverability guard, not a security boundary."""
    present = sorted(v for v in invocation_markers() if os.environ.get(v))
    if present:
        raise CapabilityUnavailable(
            "raw-history search is not offered inside an invocation; it is the operator's and the Lead's explicit "
            "read (a discoverability guard, not a security boundary)", reason="not_in_invocations", markers=present)


_FTS5: bool | None = None


def fts5_available() -> bool:
    """Whether this process's SQLite runs exactly what the substrate uses: its DDL, ``MATCH``, ``bm25``, ``snippet``
    and FTS5's ``integrity-check`` (probed once, in memory)."""
    global _FTS5
    if _FTS5 is None:
        try:
            conn = sqlite3.connect(":memory:")
            try:
                for statement in _DDL:
                    conn.execute(statement)
                conn.execute("INSERT INTO doc_text (rowid, text) VALUES (1, 'probe text')")
                conn.execute("SELECT bm25(doc_text), snippet(doc_text, 0, '', '', '', 8) FROM doc_text "
                             "WHERE doc_text MATCH '\"probe\"'").fetchall()
                conn.execute("INSERT INTO doc_text (doc_text) VALUES ('integrity-check')")
                _FTS5 = True
            finally:
                conn.close()
        except sqlite3.Error:
            _FTS5 = False
    return _FTS5


# ---------------------------------------------------------------------------------------------- queries


def check_query(terms: list[str]) -> str:
    """The FTS5 query for ``terms``: each one quoted as a phrase (so no FTS operator, column filter, prefix or NEAR
    is ever interpreted), all of them ANDed. Refused as ``USAGE`` before SQLite sees anything: no term, more than
    ``MAX_TERMS``, more than ``MAX_QUERY_CHARS`` in all, or a control character (NUL included)."""
    if not terms:
        raise UsageError("give at least one search term")
    if len(terms) > MAX_TERMS:
        raise UsageError(f"at most {MAX_TERMS} search terms (got {len(terms)})")
    if sum(len(t) for t in terms) + len(terms) - 1 > MAX_QUERY_CHARS:
        raise UsageError(f"the search terms are longer than {MAX_QUERY_CHARS} characters in all")
    for term in terms:
        if not isinstance(term, str) or not term.strip():
            raise UsageError("a search term is empty")
        if any(unicodedata.category(c) == "Cc" for c in term):
            raise UsageError("a search term holds a control character")
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _inert(text: str, limit: int | None = None) -> str:
    """``text`` with every C0, C1 and DEL control, Unicode format character (bidi controls, zero-width) and line or
    paragraph separator written as a visible ``\\u{XXXX}`` escape, so it cannot steer a terminal or reorder what a
    reader sees; cut at ``limit`` characters, never inside an escape."""
    out: list[str] = []
    size = 0
    for c in text.replace("\n", " ").replace("\t", " "):
        piece = f"\\u{{{ord(c):04x}}}" if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c
        if limit is not None and size + len(piece) > limit:
            break
        out.append(piece)
        size += len(piece)
    return "".join(out)


# ---------------------------------------------------------------------------------------------- documents


@dataclass(frozen=True)
class Document:
    """One searchable document as the authenticated history holds it."""

    seq: int
    doc_id: str
    sha256: str
    kind: str
    source: str
    at: str
    subject: str | None
    text: str
    truncated: bool

    @property
    def text_sha256(self) -> str:
        return sha256_text(self.text)

    def row(self) -> tuple[Any, ...]:
        """The values its ``docs`` row must hold."""
        return (self.seq, self.doc_id, self.sha256, self.kind, self.source, self.at, self.text_sha256,
                int(self.truncated))


def _leaves(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _leaves(v)
    elif isinstance(value, list):
        for v in value:
            yield from _leaves(v)


def _text(value: Any) -> tuple[str, bool]:
    """A record's string leaves, verifiers and credential-shaped strings redacted, capped at ``DOC_CAP`` bytes."""
    from aew.harness.contract import CREDENTIAL_RE

    text = CREDENTIAL_RE.sub("aew1.<redacted>", "\n".join(_leaves(redact(value))))
    raw = text.encode("utf-8")
    if len(raw) <= DOC_CAP:
        return text, False
    return raw[:DOC_CAP].decode("utf-8", "ignore"), True


def _evidence_refs(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The evidence a history record holds, by id, in the order ``held_evidence`` looks it up: an archived unit's
    ingested evidence, then the checks its verification cites (a ``cited_evidence`` closure annotation's too)."""
    unit = record.get("unit")
    unit = unit if isinstance(unit, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for ref in [*(unit.get("evidence") or []), *(record.get("cited_evidence") or [])]:
        if isinstance(ref, dict) and isinstance(ref.get("id"), str) and ref["id"] not in out:
            out[ref["id"]] = ref
    return out


def _own(entry: dict[str, Any], record: dict[str, Any]) -> Document:
    """An entry's own record (credential bundles left out)."""
    text, cut = _text({k: v for k, v in record.items() if k != "tokens"})
    subject = entry.get("subject") or (entry["id"] if entry["kind"] == "unit" else None)
    # An entry without a source is read as a model's: a missing label never upgrades trust.
    return Document(entry["seq"], entry["id"], entry["sha256"], entry["kind"], entry.get("source") or "model",
                    entry["at"], subject, text, cut)


def _evidence(aew_root: Path, entry: dict[str, Any], ref: dict[str, Any]) -> Document:
    """An evidence record the entry's record holds, read once and checked against the hash that record lists."""
    path, sha = ref.get("path"), ref.get("sha256")
    if not isinstance(path, str) or not isinstance(sha, str):
        raise IntegrityError(f"{entry['id']}'s reference to evidence {ref['id']} pins no path and hash")
    try:
        raw = (aew_root / path).read_bytes()
    except OSError:
        raise IntegrityError(f"evidence record {ref['id']} is missing or unreadable", path=path) from None
    if sha256_bytes(raw) != sha:
        raise IntegrityError(f"evidence record {ref['id']} is not the content its unit recorded", path=path)
    try:
        meta, body = parse_frontmatter(raw.decode("utf-8"), source=path)
    except (UnicodeDecodeError, ValidationFailed) as exc:
        raise IntegrityError(f"evidence record {ref['id']} cannot be read: {exc}", path=path) from None
    text, cut = _text({**{k: v for k, v in meta.items() if k != "schema"}, "body": body})
    return Document(entry["seq"], ref["id"], sha, "evidence", evidence_source(meta), entry["at"],
                    entry.get("subject") or entry["id"], text, cut)


# ---------------------------------------------------------------------------------------------- the substrate


class _Busy(Exception):
    """Another process holds the substrate's write lock (it is building), or has just moved its watermark."""


def _contended(exc: sqlite3.Error) -> bool:
    name = getattr(exc, "sqlite_errorname", "") or ""
    return name.startswith(("SQLITE_BUSY", "SQLITE_LOCKED"))


Record = Callable[[dict[str, Any]], dict[str, Any]]  # an entry's record, verified against its hash (``Archive.record``)


class Substrate:
    """The FTS5 substrate of the history under ``aew_root``. ``record`` reads an entry's record through the engine's
    archive layer."""

    def __init__(self, aew_root: Path, record: Record) -> None:
        self.aew_root = aew_root
        self.path = aew_root / SUBSTRATE_REL
        self.history = History(aew_root)
        self.record = record

    # ------------------------------------------------------------------ the file

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path, timeout=READ_WAIT_S, isolation_level=None)

    def _open(self) -> sqlite3.Connection:
        """A connection to the substrate with its schema. A file of another ``substrate_version``, missing a table, or
        one SQLite reports corrupt is deleted and started over from the genesis. ``_Busy`` when it is being written."""
        for _ in range(2):
            conn = self._connect()
            try:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                if not tables:
                    self._begin(conn)
                    for statement in _DDL:
                        conn.execute(statement)
                    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('substrate_version', ?)",
                                 (SUBSTRATE_VERSION,))
                    conn.execute("COMMIT")
                    return conn
                version = conn.execute("SELECT value FROM meta WHERE key = 'substrate_version'").fetchone() \
                    if "meta" in tables else None
                if set(_TABLES) <= tables and version == (SUBSTRATE_VERSION,):
                    return conn
            except _Busy:
                conn.close()
                raise
            except sqlite3.Error as exc:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                conn.close()
                if _contended(exc):
                    raise _Busy from None
                self._delete()  # damaged, or not a database: derived data, so start over
                continue
            conn.close()
            self._delete()  # another substrate version, or tables missing
        raise _Busy

    def _delete(self) -> None:
        try:
            for suffix in ("", "-journal"):
                Path(f"{self.path}{suffix}").unlink(missing_ok=True)
        except OSError:  # another process has it open (Windows refuses the unlink)
            raise _Busy from None

    @staticmethod
    def _begin(conn: sqlite3.Connection) -> None:
        """Take the write lock or report ``_Busy``: a build is never waited on."""
        conn.execute("PRAGMA busy_timeout = 0")
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if _contended(exc):
                raise _Busy from None
            raise
        finally:
            conn.execute(f"PRAGMA busy_timeout = {int(READ_WAIT_S * 1000)}")

    @staticmethod
    def _watermark(conn: sqlite3.Connection) -> dict[str, Any]:
        meta = dict(conn.execute("SELECT key, value FROM meta WHERE key IN ('count', 'h')").fetchall())
        count, h = meta.get("count"), meta.get("h")
        if isinstance(count, str) and count.isdigit() and isinstance(h, str) and len(h) == 64:
            return {"count": int(count), "h": h}
        return {"count": 0, "h": M.GENESIS_H}

    def _reset(self, conn: sqlite3.Connection) -> None:
        """Mark the substrate stale: every row and the watermark go, and the next build starts from the genesis."""
        self._begin(conn)
        try:
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM doc_text")
            conn.execute("DELETE FROM meta WHERE key IN ('count', 'h')")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------ documents

    def documents(self, entry: dict[str, Any]) -> list[Document]:
        """Every document an authenticated entry holds; one that cannot be authenticated is left out (the audit
        reports damage; the substrate only indexes what it can vouch was read as pinned)."""
        try:
            record = self.record(entry)
        except (IntegrityError, ValidationFailed):
            return []
        out = [_own(entry, record)]
        for ref in _evidence_refs(record).values():
            try:
                out.append(_evidence(self.aew_root, entry, ref))
            except IntegrityError:
                continue
        return out

    def document(self, root: dict[str, Any], seq: int, doc_id: str, cache: dict[int, Any]) -> Document | None:
        """The document ``doc_id`` at position ``seq``, from the history alone: the entry ``root`` pins there, its
        record, and (evidence) the reference that record holds. None when that entry does not hold ``doc_id``.
        ``IntegrityError`` when the history cannot prove it (damage, or a root moved under the reader)."""
        if seq not in cache:
            entry = self.history.pinned_entry(root, seq)
            cache[seq] = (entry, self.record(entry))
        entry, record = cache[seq]
        if doc_id == entry["id"]:
            return _own(entry, record)
        ref = _evidence_refs(record).get(doc_id)
        return None if ref is None else _evidence(self.aew_root, entry, ref)

    # ------------------------------------------------------------------ building

    def catch_up(self, root: dict[str, Any], tail: bytes | None) -> dict[str, Any]:
        """Index the entries after the watermark through ``root`` (``tail``: the tail's bytes, copied with the root
        under the control lock), in batches, until done or the build budget is spent. ``{"complete", "reason",
        "added", "through"}``; the next call resumes from the watermark."""
        try:
            conn = self._open()
        except _Busy:
            return {"complete": False, "reason": "busy", "added": 0, "through": None}
        try:
            return self._catch_up(conn, root, tail, budget_s=BUILD_BUDGET_S, budget_docs=BUILD_BUDGET_DOCS)
        except sqlite3.Error as exc:
            damaged = not _contended(exc)
        finally:
            conn.close()
        if damaged:  # derived data damaged under the builder: start over (the next call builds it)
            self._discard()
        return {"complete": False, "reason": "rebuilding" if damaged else "busy", "added": 0, "through": None}

    def _discard(self) -> None:
        """Delete the file, if no other process holds it open; otherwise leave it for a later call to find."""
        try:
            self._delete()
        except _Busy:
            pass

    def _rebuild(self, root: dict[str, Any], tail: bytes | None) -> dict[str, Any] | None:
        """Delete the file and build it again through ``root`` with no budget; None when another process holds it."""
        try:
            self._delete()
            conn = self._open()
        except _Busy:
            return None
        try:
            return self._catch_up(conn, root, tail, budget_s=None, budget_docs=None)
        except sqlite3.Error:
            return None
        finally:
            conn.close()

    def _catch_up(self, conn: sqlite3.Connection, root: dict[str, Any], tail: bytes | None, *,
                  budget_s: float | None, budget_docs: int | None) -> dict[str, Any]:
        started = time.monotonic()
        mark = self._watermark(conn)
        target = {"count": root["count"], "h": root["head_h"]}
        if mark == target or mark["count"] > target["count"]:  # current, or another process indexed a later root
            return {"complete": True, "reason": None, "added": 0, "through": mark["count"]}  # (queries stop at ours)
        added, batch, batch_docs, reason = 0, [], 0, None
        walk = self.history.walk(root, mark if mark["count"] else None, tail_raw=tail)
        try:
            for entry in walk:
                docs = self.documents(entry)
                if budget_docs is not None and added + batch_docs and added + batch_docs + len(docs) > budget_docs:
                    reason = "budget"
                    break
                batch.append((entry, docs))
                batch_docs += len(docs)
                if batch_docs >= BATCH_DOCS:
                    mark = self._flush(conn, mark, batch)
                    added, batch, batch_docs = added + batch_docs, [], 0
                if budget_s is not None and time.monotonic() - started >= budget_s:
                    reason = "budget"
                    break
        except IntegrityError:
            if not batch and added == 0 and mark["count"]:
                # The watermark is not on this history's chain: the substrate describes another history. Start over.
                try:
                    self._reset(conn)
                except _Busy:
                    return {"complete": False, "reason": "busy", "added": 0, "through": None}
                return {"complete": False, "reason": "rebuilding", "added": 0, "through": 0}
            reason = "history_unreadable"  # damaged history, or a commit replaced the tail: the next call resumes
        except _Busy:
            return {"complete": False, "reason": "busy", "added": added, "through": mark["count"]}
        try:
            if batch:
                mark = self._flush(conn, mark, batch)
                added += batch_docs
        except _Busy:
            return {"complete": False, "reason": "busy", "added": added, "through": mark["count"]}
        complete = reason is None and mark == target
        return {"complete": complete, "reason": None if complete else reason or "budget", "added": added,
                "through": mark["count"]}

    def _flush(self, conn: sqlite3.Connection, mark: dict[str, Any],
               batch: list[tuple[dict[str, Any], list[Document]]]) -> dict[str, Any]:
        """Write one batch of entries' documents and advance the watermark to its last entry, in one transaction; only
        if the watermark is still where this build read it (another process may have built meanwhile)."""
        self._begin(conn)
        try:
            if self._watermark(conn) != mark:
                conn.execute("ROLLBACK")
                raise _Busy
            for _, docs in batch:
                for d in docs:
                    cur = conn.execute("INSERT INTO docs (seq, doc_id, sha256, kind, source, at, text_sha256, "
                                       "truncated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", d.row())
                    conn.execute("INSERT INTO doc_text (rowid, text) VALUES (?, ?)", (cur.lastrowid, d.text))
            last = batch[-1][0]
            conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             [("count", str(last["seq"])), ("h", last["h"])])
            conn.execute("COMMIT")
        except _Busy:
            raise
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        return {"count": last["seq"], "h": last["h"]}

    def reindex(self, root: dict[str, Any], tail: bytes | None) -> dict[str, Any]:
        """Start over and build through ``root`` with no budget (``aew history reindex``)."""
        out = self._rebuild(root, tail)
        if out is None:
            return {"mode": "not rebuilt", "reason": "busy"}
        return {"mode": "rebuilt", "documents": out["added"], "complete": out["complete"],
                **({"reason": out["reason"]} if out["reason"] else {})}

    # ------------------------------------------------------------------ the full audit

    def audit(self, root: dict[str, Any], tail: bytes | None) -> str:
        """FTS5's ``integrity-check``, then every ``docs`` row (and its text) against the documents the history holds
        through the watermark: ``consistent``, ``rebuilt`` when anything differed, or ``not checked`` when the file
        is busy or the history moved meanwhile (the substrate is derived: that only defers the check)."""
        try:
            conn = self._open()
        except _Busy:
            return "not checked"
        try:
            if self._consistent(conn, root, tail):
                return "consistent"
        except (_Busy, IntegrityError):
            return "not checked"
        except sqlite3.Error as exc:
            if _contended(exc):
                return "not checked"
        finally:
            conn.close()
        return "rebuilt" if self._rebuild(root, tail) is not None else "not checked"

    def _consistent(self, conn: sqlite3.Connection, root: dict[str, Any], tail: bytes | None) -> bool:
        try:
            self._begin(conn)
            try:
                conn.execute("INSERT INTO doc_text (doc_text) VALUES ('integrity-check')")
            finally:
                conn.execute("ROLLBACK")
        except sqlite3.DatabaseError as exc:
            if _contended(exc):
                raise _Busy from None
            return False
        mark = self._watermark(conn)["count"]
        upto = min(mark, root["count"])
        rows = conn.execute("SELECT d.seq, d.doc_id, d.sha256, d.kind, d.source, d.at, d.text_sha256, d.truncated, "
                            "t.text FROM docs d LEFT JOIN doc_text t ON t.rowid = d.rowid").fetchall()
        orphans = conn.execute("SELECT COUNT(*) FROM doc_text WHERE rowid NOT IN (SELECT rowid FROM docs)").fetchone()
        if orphans != (0,):
            return False
        # Every row is compared (PR #148 review, m1): one whose position is not an integer in 1..watermark is a
        # difference; one past this root but within the watermark belongs to a later root another process indexed.
        if any(type(r[0]) is not int or not 1 <= r[0] <= mark for r in rows):
            return False
        # Each row with the hash of the text it really holds, against what the history holds: as multisets, so a
        # duplicated, missing or altered row (or text) differs, whatever types a tampered column holds.
        found = Counter((tuple(r[:8]), sha256_text(r[8]) if isinstance(r[8], str) else "") for r in rows
                        if r[0] <= upto)
        expected: Counter[tuple[Any, ...]] = Counter()
        for entry in self.history.walk(root, tail_raw=tail):
            if entry["seq"] > upto:
                break
            expected.update((d.row(), d.text_sha256) for d in self.documents(entry))
        return found == expected

    # ------------------------------------------------------------------ searching

    def search(self, query: str, *, root: dict[str, Any], tail: bytes | None, kinds: list[str] | None,
               since: str | None, until: str | None, limit: int) -> dict[str, Any]:
        """Catch up within the budget, then answer from what is indexed, every hit authenticated (see the module)."""
        build = self.catch_up(root, tail)
        reasons = [build["reason"]] if build["reason"] else []
        hits: list[dict[str, Any]] = []
        unverified, stale, damaged = 0, False, False
        try:
            conn = self._open()
        except _Busy:
            return self._result([], reasons=[*reasons, "busy"], root=root, through=build["through"],
                                unverified=0)
        matcher = _Matcher()
        try:
            through = self._watermark(conn)["count"]
            cache: dict[int, Any] = {}
            seen: set[str] = set()
            where, args = ["doc_text MATCH ?", "d.seq <= ?"], [query, root["count"]]
            if kinds:
                where.append(f"d.kind IN ({', '.join('?' for _ in kinds)})")
                args += kinds
            for clause, value in (("d.at >= ?", since), ("d.at <= ?", until)):
                if value is not None:
                    where.append(clause)
                    args.append(value)
            # The kind and snapshot filters run in SQL, before ranking; every clause is a fixed string above.
            sql = ("SELECT d.rowid, d.seq, d.doc_id, d.sha256, d.kind, d.source, d.at, d.truncated FROM doc_text "  # noqa: S608
                   f"JOIN docs d ON d.rowid = doc_text.rowid WHERE {' AND '.join(where)} "
                   "ORDER BY bm25(doc_text), d.rowid LIMIT ? OFFSET ?")
            offset, page = 0, 50
            try:
                while len(hits) < limit:
                    rows = conn.execute(sql, (*args, page, offset)).fetchall()
                    if not rows:
                        break
                    offset += len(rows)
                    for row in rows:
                        if len(hits) >= limit:
                            break
                        verdict = self._candidate(row, query, root, cache, matcher, kinds, since, until)
                        if isinstance(verdict, str):
                            stale = stale or verdict == "disagrees"
                            unverified += verdict == "unverified"
                        elif verdict["id"] not in seen:
                            seen.add(verdict["id"])
                            hits.append(verdict)
            except sqlite3.DatabaseError as exc:  # a substrate damaged under the reader: derived, so start over
                if _contended(exc):
                    reasons.append("busy")
                else:
                    stale = damaged = True
            if stale:
                reasons.append("stale")
                try:
                    self._reset(conn)
                except _Busy:
                    pass  # another process is building; the next search finds the disagreement again
                except sqlite3.Error:
                    damaged = True
                through = 0
        finally:
            conn.close()
            matcher.conn.close()
        if damaged:
            self._discard()
        return self._result(hits, reasons=reasons, root=root, through=through, unverified=unverified)

    def _candidate(self, row: tuple[Any, ...], query: str, root: dict[str, Any], cache: dict[int, Any],
                   matcher: _Matcher, kinds: list[str] | None, since: str | None,
                   until: str | None) -> dict[str, Any] | str:
        """A hit built from the authenticated document only, ``disagrees`` (the row is not what the history holds),
        or ``unverified`` (the history itself could not be proven: damage, or the root moved under the reader)."""
        _, seq, doc_id, sha, kind, source, at, truncated = row
        if type(seq) is not int or not 1 <= seq <= root["count"] or not isinstance(doc_id, str):
            return "disagrees"  # a position this root cannot hold: the row's fault, not the history's (review, m2)
        try:
            doc = self.document(root, seq, doc_id, cache)
        except AEWError:  # the history could not be proven here (IntegrityError and its kin)
            return "unverified"
        if doc is None:
            return "disagrees"  # the entry at that position does not hold this document
        if (kind, source, sha, at, truncated) != (doc.kind, doc.source, doc.sha256, doc.at, int(doc.truncated)):
            return "disagrees"
        if (kinds and doc.kind not in kinds) or (since is not None and doc.at < since) \
                or (until is not None and doc.at > until):
            return "disagrees"  # the row passed a filter the authenticated values do not
        snippet = matcher.snippet(query, doc.text)
        if snippet is None:
            return "disagrees"  # its indexed text is not the document's
        return {"id": doc.doc_id, "kind": doc.kind, "at": doc.at, "subject": doc.subject, "source": doc.source,
                "trust": {"source": doc.source, "label": _trust_label()}, "truncated": doc.truncated,
                "snippet": _inert(snippet, SNIPPET_MAX), "expand": f"aew history show {doc.doc_id}"}

    @staticmethod
    def _result(hits: list[dict[str, Any]], *, reasons: list[str], root: dict[str, Any], through: int | None,
                unverified: int) -> dict[str, Any]:
        """The response: every snippet inside a fence whose token no snippet contains, so no content can close it."""
        token = secrets.token_hex(8)
        while any(token in h["snippet"] for h in hits):
            token = secrets.token_hex(8)
        fence = {"open": f"<<raw-history {token}>>", "close": f"<</raw-history {token}>>"}
        for h in hits:
            h["snippet"] = f"{fence['open']}{h['snippet']}{fence['close']}"
        out: dict[str, Any] = {
            "label": LABEL, "fence": fence, "hits": hits, "coverage_incomplete": bool(reasons),
            "coverage": {"indexed_through": through, "history_entries": root["count"],
                         "reasons": sorted(set(reasons))}}
        if unverified:
            out["unverified"] = {"count": unverified, "note": "candidates whose history records could not be "
                                 "authenticated were left out; `aew history audit` reports damage"}
        return out


def _trust_label() -> str:
    from aew.engine.history_ops import TRUST_LABEL

    return TRUST_LABEL


class _Matcher:
    """The re-match: one throwaway in-memory FTS5 table with the substrate's tokenizer, so a candidate's authenticated
    text is matched with exactly the semantics its row was found with."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(f"CREATE VIRTUAL TABLE m USING fts5(text, tokenize='{TOKENIZE}')")

    def snippet(self, query: str, text: str) -> str | None:
        self.conn.execute("DELETE FROM m")
        self.conn.execute("INSERT INTO m (rowid, text) VALUES (1, ?)", (text,))
        row = self.conn.execute("SELECT snippet(m, 0, '', '', '...', 40) FROM m WHERE m MATCH ?", (query,)).fetchone()
        return None if row is None else row[0]
