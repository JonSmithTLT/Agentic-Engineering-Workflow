"""The durable one-use ledger (G3-02, G3-06, G3-08, G3-11): SQLite in the service's state directory.

What survives a restart, and only this: the consent records with their approved sets and approvals, the consumed
members, every member proof the service has accepted, and the lockout count. Pending approvals are not here: they are
lost at a restart and must be requested again (G3-11). Every write is one transaction committed with
``synchronous=FULL`` before the service replies, so a reply the caller saw is on disk (G3-08: "written and flushed
before the reply"). Any SQLite error is :class:`LedgerUnavailable`, and the caller holds the action.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

LEDGER_FILE = "ledger.sqlite3"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS proofs (proof TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS records (
  consent_set_ref TEXT PRIMARY KEY, approval_ref TEXT NOT NULL UNIQUE,
  record TEXT NOT NULL, command_set TEXT NOT NULL, approval TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS consumed (
  consent_set_ref TEXT NOT NULL, intent_ref TEXT NOT NULL, owner TEXT NOT NULL, operation_ref TEXT NOT NULL,
  consumed_at TEXT NOT NULL, PRIMARY KEY (consent_set_ref, intent_ref));
CREATE TABLE IF NOT EXISTS pin_failures (pin_id TEXT PRIMARY KEY, count INTEGER NOT NULL);
"""


class LedgerUnavailable(Exception):
    """The ledger cannot be read or written: nothing is approved or consumed (G3-11)."""


class _Conflict(LedgerUnavailable):
    """A row's key is already taken. Only :meth:`Ledger.consume` expects one; anywhere else it holds the action."""


def _dumps(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"))


class Ledger:
    """One connection, used under the service's lock: the service is one process, and SQLite's own locking backs it."""

    def __init__(self, state_dir: Path) -> None:
        path = state_dir / LEDGER_FILE
        try:
            if not path.exists():
                os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))
            self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript(_SCHEMA)
        except sqlite3.Error as e:
            raise LedgerUnavailable(str(e)) from None

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")
        except sqlite3.IntegrityError as e:
            raise _Conflict(str(e)) from None
        except sqlite3.Error as e:
            raise LedgerUnavailable(str(e)) from None

    def _one(self, sql: str, *args: Any) -> Any:
        try:
            return self._db.execute(sql, args).fetchone()
        except sqlite3.Error as e:
            raise LedgerUnavailable(str(e)) from None

    # ------------------------------------------------------------------------------------------ member proofs
    def any_seen(self, proofs: list[str]) -> bool:
        marks = ",".join("?" * len(proofs))
        return self._one(f"SELECT 1 FROM proofs WHERE proof IN ({marks}) LIMIT 1", *proofs) is not None  # noqa: S608 - placeholders only

    def accept_proofs(self, proofs: list[str]) -> bool:
        """Records every proof, or none; False when any was already accepted. The primary key decides, not a read
        (hand-off addendum 2 §3)."""
        try:
            with self._tx() as db:
                db.executemany("INSERT INTO proofs (proof) VALUES (?)", [(p,) for p in proofs])
        except _Conflict:
            return False
        return True

    # ------------------------------------------------------------------------------------------ the lockout
    def failures(self, pin_id: str) -> int:
        row = self._one("SELECT count FROM pin_failures WHERE pin_id = ?", pin_id)
        return int(row[0]) if row else 0

    def record_failure(self, pin_id: str) -> None:
        with self._tx() as db:
            db.execute("INSERT INTO pin_failures (pin_id, count) VALUES (?, 1) "
                       "ON CONFLICT (pin_id) DO UPDATE SET count = count + 1", (pin_id,))

    # ------------------------------------------------------------------------------------------ records
    def store_approval(self, record: dict[str, Any], command_set: dict[str, Any], approval: dict[str, Any],
                       pin_id: str) -> None:
        """Issues the record and ends the run of wrong PINs, in one transaction (G3-05, G3-06)."""
        with self._tx() as db:
            db.execute("INSERT INTO records (consent_set_ref, approval_ref, record, command_set, approval) "
                       "VALUES (?, ?, ?, ?, ?)", (record["consent_set_ref"], record["approval_ref"], _dumps(record),
                                                  _dumps(command_set), _dumps(approval)))
            db.execute("DELETE FROM pin_failures WHERE pin_id = ?", (pin_id,))

    def record(self, consent_set_ref: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        row = self._one("SELECT record, command_set FROM records WHERE consent_set_ref = ?", consent_set_ref)
        return (json.loads(row[0]), json.loads(row[1])) if row else None

    def approval(self, approval_ref: str) -> dict[str, Any] | None:
        row = self._one("SELECT approval FROM records WHERE approval_ref = ?", approval_ref)
        return json.loads(row[0]) if row else None

    # ------------------------------------------------------------------------------------------ consumption
    def consume(self, consent_set_ref: str, intent_ref: str, owner: str, operation_ref: str, at: str) -> bool:
        """Records the member as consumed; False when it already was. The primary key makes it once, whatever races."""
        try:
            with self._tx() as db:
                db.execute("INSERT INTO consumed (consent_set_ref, intent_ref, owner, operation_ref, consumed_at) "
                           "VALUES (?, ?, ?, ?, ?)", (consent_set_ref, intent_ref, owner, operation_ref, at))
        except _Conflict:
            return False
        return True

    def consumed(self, consent_set_ref: str, intent_ref: str) -> bool:
        return self._one("SELECT 1 FROM consumed WHERE consent_set_ref = ? AND intent_ref = ?",
                         consent_set_ref, intent_ref) is not None

    def close(self) -> None:
        self._db.close()
