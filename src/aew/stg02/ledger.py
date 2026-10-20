"""The carrier's key ledger and the fixture HEB owner's operation records, in one SQLite file (STG-02).

**Compare-and-fence across processes** (the slice's push-back 3). The profile models a key lookup, HEB's state check
and its one effect as one atomic step. Here each submission runs in one ``BEGIN IMMEDIATE`` transaction over this
file: SQLite takes the database's write lock before the first read, so two server processes given the same key (or
two submissions racing for HEB's state) serialize, and the second sees the first's ledger entry and replays it. The
lock wait is bounded (:data:`BUSY_TIMEOUT_S`); a timeout is a ``503 owner_unavailable``, never a second dispatch.

**Retention** (push-back 4; the contract leaves durations open, these are the slice's choices):

- a receipt is valid for the world's ``receipt_valid_s`` (900 s) after it is issued; then an identical retry is
  ``409 unresolved_no_redispatch`` (CS-04 step 4), and a new effect needs a new key;
- the stored receipt and member outcomes are kept :data:`RECEIPT_RETAIN_S` after that, then dropped;
- the key itself and its request digest are **never** dropped: a key that came back unused would let a lost
  response's retry dispatch a second time. A key whose receipt was dropped is ``409 unresolved_no_redispatch``;
- an owner operation record is kept :data:`OWNER_RECORD_RETAIN_S` after it is issued; then the owner GET is the
  nondisclosing 404, as for any operation the recipient cannot read.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from aew.stg02 import wire as W

BUSY_TIMEOUT_S = 10.0
RECEIPT_RETAIN_S = 7 * 86400
OWNER_RECORD_RETAIN_S = 30 * 86400
SCHEMA = """
CREATE TABLE IF NOT EXISTS keys (
  installation TEXT NOT NULL, recipient TEXT NOT NULL, client_key TEXT NOT NULL,
  full_digest TEXT NOT NULL, receipt TEXT, members TEXT, stored_at TEXT NOT NULL, receipt_until TEXT NOT NULL,
  PRIMARY KEY (installation, recipient, client_key));
CREATE TABLE IF NOT EXISTS owner_ops (
  owner TEXT NOT NULL, operation_ref TEXT NOT NULL, installation TEXT NOT NULL, recipient TEXT NOT NULL,
  record TEXT NOT NULL, issued_at TEXT NOT NULL, retain_until TEXT NOT NULL,
  PRIMARY KEY (owner, operation_ref));
CREATE TABLE IF NOT EXISTS entitlement (recipient TEXT PRIMARY KEY, entitled INTEGER NOT NULL);
"""


class LedgerBusy(Exception):
    """The ledger's write lock was not granted within the bound."""


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as c:
            c.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_S, isolation_level=None)
        c.row_factory = sqlite3.Row
        return c

    @contextlib.contextmanager
    def transaction(self) -> Iterator[Txn]:
        """One write transaction, its lock taken before the first read (the fence)."""
        c = self._connect()
        try:
            try:
                c.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                raise LedgerBusy(str(exc)) from exc
            try:
                yield Txn(c)
            except BaseException:
                c.execute("ROLLBACK")
                raise
            c.execute("COMMIT")
        finally:
            c.close()

    @contextlib.contextmanager
    def reading(self) -> Iterator[Txn]:
        c = self._connect()
        try:
            c.execute("BEGIN")
            yield Txn(c)
            c.execute("COMMIT")
        finally:
            c.close()


class Txn:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    # ------------------------------------------------------------------ read entitlement (SW-07, SW-08)

    def entitled(self, recipient: str) -> bool:
        row = self.c.execute("SELECT entitled FROM entitlement WHERE recipient = ?", (recipient,)).fetchone()
        return True if row is None else bool(row["entitled"])

    def set_entitled(self, recipient: str, entitled: bool) -> None:
        self.c.execute("INSERT INTO entitlement (recipient, entitled) VALUES (?, ?) "
                       "ON CONFLICT (recipient) DO UPDATE SET entitled = excluded.entitled", (recipient, int(entitled)))

    # ------------------------------------------------------------------ the key ledger (CS-03, CS-04, CS-08)

    def key(self, installation: str, recipient: str, client_key: str) -> dict[str, Any] | None:
        row = self.c.execute("SELECT * FROM keys WHERE installation = ? AND recipient = ? AND client_key = ?",
                             (installation, recipient, client_key)).fetchone()
        if row is None:
            return None
        out = dict(row)
        try:
            out["receipt"] = json.loads(row["receipt"]) if row["receipt"] is not None else None
            out["members"] = json.loads(row["members"]) if row["members"] is not None else None
        except ValueError:
            out["receipt"] = out["members"] = None  # corrupt: unresolved, never a new submission
        return out

    def store_key(self, installation: str, recipient: str, client_key: str, full: str, receipt: dict[str, Any],
                  members: list[dict[str, Any]], now: datetime) -> None:
        self.c.execute("INSERT INTO keys VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (installation, recipient, client_key, full, json.dumps(receipt, sort_keys=True),
                        json.dumps(members, sort_keys=True), W.utc(now), receipt["source_valid_until"]))

    # ------------------------------------------------------------------ the HEB owner's records (OP-08)

    def add_owner_op(self, record: dict[str, Any], issued_at: datetime) -> None:
        self.c.execute("INSERT INTO owner_ops VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (record["owner"], record["operation_ref"], record["installation_ref"], record["recipient_ref"],
                        json.dumps(record, sort_keys=True), W.utc(issued_at),
                        W.utc(W.later(issued_at, OWNER_RECORD_RETAIN_S))))

    def owner_op(self, owner: str, operation_ref: str) -> dict[str, Any] | None:
        row = self.c.execute("SELECT record FROM owner_ops WHERE owner = ? AND operation_ref = ?",
                             (owner, operation_ref)).fetchone()
        return json.loads(row["record"]) if row else None

    def owner_ops(self, installation: str, recipient: str) -> list[dict[str, Any]]:
        rows = self.c.execute("SELECT record FROM owner_ops WHERE installation = ? AND recipient = ? "
                              "ORDER BY owner, operation_ref", (installation, recipient)).fetchall()
        return [json.loads(r["record"]) for r in rows]

    # ------------------------------------------------------------------ retention

    def purge(self, now: datetime) -> None:
        """Drop what retention lets go: old receipts (the key stays, as a tombstone) and old owner records."""
        cutoff = W.utc(W.later(now, -RECEIPT_RETAIN_S))
        self.c.execute("UPDATE keys SET receipt = NULL, members = NULL WHERE receipt IS NOT NULL AND receipt_until < ?",
                       (cutoff,))
        self.c.execute("DELETE FROM owner_ops WHERE retain_until < ?", (W.utc(now),))
