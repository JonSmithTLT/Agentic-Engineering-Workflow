"""Retention of kept harness session databases (agent-effectiveness adoption, Revision C; delta D2's retention half).

A raw run keeps its harness state (its session database included) for the evaluator-side reader, and records where
(``outcome.session_db.state_dir``) and until when (``retain_until``, from the preregistered ``retention_days``).
Retention is enforced, not only recorded:

* :func:`purge` deletes the harness state of every finalized run of an experiment whose ``retain_until`` has
  passed, and appends what it deleted to the experiment's ``retention.jsonl`` (paths and dates, never content). A
  state already gone is recorded as such. Running it again purges nothing twice.
* :func:`open_session_db` is the reader side's only door to a database: it refuses one past its window or already
  purged, and opens one inside its window **read-only**. D2's reader (the field allowlist, the metric functions)
  goes through it; nothing under ``src/aew`` imports this module.

    python -m aew_eval.retention purge FROZEN.yaml --ledger DIR
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from aew_eval import prereg
from aew_eval.ledger import AttemptLedger
from aew_eval.schemas import Invalid

LOG = "retention.jsonl"


def _today(now: datetime | None) -> date:
    return (now or datetime.now(UTC)).date()


def _records(ledger_dir: Path, frozen: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = AttemptLedger(ledger_dir, frozen)
    out = []
    for attempt in ledger.attempts().values():
        if attempt.finalized is None:
            continue
        path = ledger.runs / (attempt.run_id.split("/", 1)[1] + ".json")
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return out


def purged(ledger_dir: Path) -> dict[str, dict[str, Any]]:
    """The purges recorded so far, by run id."""
    path = ledger_dir / LOG
    if not path.exists():
        return {}
    return {e["run_id"]: e for e in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                                       if line.strip())}


def _log(ledger_dir: Path, entry: dict[str, Any]) -> None:
    with (ledger_dir / LOG).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def purge(ledger_dir: Path, frozen: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Delete every kept harness state past its retention window, and record each purge. Returns the new entries."""
    today, done, new = _today(now), purged(ledger_dir), []
    for record in _records(ledger_dir, frozen):
        db = (record.get("outcome") or {}).get("session_db") or {}
        if not db.get("retain_until") or record["run_id"] in done:
            continue
        if date.fromisoformat(db["retain_until"]) >= today:
            continue
        state = Path(db["state_dir"]) if db.get("state_dir") else None
        existed = state is not None and state.exists()
        if existed:
            shutil.rmtree(state)
        entry = {"run_id": record["run_id"], "state_dir": str(state) if state else None,
                 "retain_until": db["retain_until"], "purged_on": today.isoformat(),
                 "deleted": existed, "reason": "retention window passed"}
        _log(ledger_dir, entry)
        new.append(entry)
    return new


def open_session_db(ledger_dir: Path, frozen: dict[str, Any], run_id: str, *,
                    now: datetime | None = None) -> sqlite3.Connection:
    """A run's kept session database, read-only. Refused past its retention window, after a purge, or when the run
    kept none."""
    record = next((r for r in _records(ledger_dir, frozen) if r["run_id"] == run_id), None)
    if record is None:
        raise Invalid(f"{run_id} has no finalized result")
    db = (record.get("outcome") or {}).get("session_db") or {}
    if run_id in purged(ledger_dir):
        raise Invalid(f"the session database of {run_id} was purged ({purged(ledger_dir)[run_id]['purged_on']})")
    if not db.get("retain_until") or date.fromisoformat(db["retain_until"]) < _today(now):
        raise Invalid(f"the session database of {run_id} is past its retention window ({db.get('retain_until')}): "
                      "it is never read; purge it")
    if not db.get("path") or not db.get("state_dir"):
        raise Invalid(f"{run_id} kept no session database")
    path = Path(db["state_dir"]).parent / db["path"]
    if not path.is_file():
        raise Invalid(f"the session database of {run_id} is missing ({path})")
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew_eval.retention")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("purge")
    p.add_argument("frozen", type=Path)
    p.add_argument("--ledger", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        for entry in purge(args.ledger, prereg.load(args.frozen)):
            print(json.dumps(entry, sort_keys=True))
    except Invalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
