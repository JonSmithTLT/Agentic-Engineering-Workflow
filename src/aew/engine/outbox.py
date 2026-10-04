"""The transaction outbox: the transition log, typed, complete and consumed (ADR-0012, M4-D slice D1).

The outbox is the transition log, not a second store. Every commit already records ``last_transition`` inside the
commit point (ADR-0001); this module adds what makes the log consumable:

* **Typed events** (D2), derived in the store from the committed states, so every commit site is covered, whether it
  runs through ``Kernel.lead_txn`` or calls ``Session.commit`` directly. Operation-declared facts the state difference
  cannot recover (a decision recorded, evidence ingested) are appended by the authoritative operation itself
  (``TxnContext.events``).
* **A hot bound** (D2): ``last_transition.events`` holds at most :data:`MAX_HOT_EVENTS`. A larger set is written in
  full to an immutable sidecar ``state/log/<rev>.events.yaml``, staged in the same redo record as the transition's
  other writes and named and hashed by ``last_transition.event_overflow``. Nothing reconstructs events afterwards.
* **A hash chain** (D7): each record's ``h`` commits to the previous one and, for an overflow, to the sidecar's
  digest and count. The chain starts at ``outbox.since``, the first revision an outbox-era engine committed.
* **A reader** (D3): transitions after a revision, in order, overflow resolved and verified, the chain checked,
  without the control lock. The cursor is the revision number.
* **An advisory wake signal** (D4): ``local/wake`` changes after each commit's log write and after each run record
  write. Waking costs latency when missed, never correctness.

The top-level ``outbox`` key marks a control file as outbox-era. It is what makes an older engine refuse the file
(its schema closes the top level with ``additionalProperties: false``, while ``last_transition`` was open), so an
older engine can never commit over the chain without extending it (ADR-0012 D10).
"""

from __future__ import annotations

import hashlib
import os
import time
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from aew.errors import IntegrityError
from aew.history.manifest import canonical_json
from aew.util import dump_yaml, load_yaml, sha256_bytes

TRANSITION_SCHEMA = "aew/transition/v1"
EVENTS_SCHEMA = "aew/transition-events/v1"
OUTBOX_SCHEMA = "aew/outbox/v1"
MAX_HOT_EVENTS = 64
GENESIS_H = hashlib.sha256(b"aew/transition/v1 genesis").hexdigest()
LOG_DIR = "state/log"
WAKE_REL = "local/wake"

# Event kinds (ADR-0012 D2). Derived kinds come from the committed states; declared kinds only from the operation.
DERIVED_KINDS = ("lead.generation", "work.state", "invocation.status", "run.added", "credential.revoked",
                 "history.appended", "unit.archived")
DECLARED_KINDS = ("decision.recorded", "handoff.recorded", "evidence.ingested", "audit.recorded")


# ---------------------------------------------------------------------------------------------- derivation (D2)

def derive_events(before: dict[str, Any], working: dict[str, Any], committed: dict[str, Any]) -> list[dict[str, Any]]:
    """The events a commit's state change implies, in a fixed order.

    ``working`` is the state the operation produced; ``committed`` is what is serialized, which differs only when the
    archival finalizer projected finished units out of the hot state (ADR-0011 R6). Unit and credential changes are
    read from ``working`` (a unit that finishes and is archived in the same commit still moves to DONE), archival
    and history from ``committed``. Every collection compared is hot, so the cost tracks active work (H1)."""
    events: list[dict[str, Any]] = []
    old_gen, new_gen = (before.get("lead") or {}).get("generation"), (working.get("lead") or {}).get("generation")
    if old_gen != new_gen:
        events.append({"kind": "lead.generation", "from": old_gen, "to": new_gen})
    old_work, new_work = before.get("work") or {}, working.get("work") or {}
    for wid in sorted(new_work):
        was = (old_work.get(wid) or {}).get("state")
        now = new_work[wid].get("state")
        if was != now:
            events.append({"kind": "work.state", "id": wid, "unit": new_work[wid].get("kind"), "from": was, "to": now})
    old_inv, new_inv = before.get("invocations") or {}, working.get("invocations") or {}
    for iid in sorted(new_inv):
        inv, was = new_inv[iid], (old_inv.get(iid) or {})
        if was.get("status") != inv.get("status"):
            events.append({"kind": "invocation.status", "id": iid, "work": inv.get("work_unit"),
                           "role": inv.get("role"), "from": was.get("status"), "to": inv.get("status")})
        seen = {r.get("run") for r in was.get("runs") or []}
        for run in inv.get("runs") or []:
            if run.get("run") not in seen:
                events.append({"kind": "run.added", "invocation": iid, "run": run.get("run")})
    old_tok, new_tok = before.get("tokens") or {}, working.get("tokens") or {}
    for tid in sorted(new_tok):
        rec = new_tok[tid]
        if rec.get("revoked_at") and not (old_tok.get(tid) or {}).get("revoked_at"):
            events.append({"kind": "credential.revoked", "id": tid, "reason": rec.get("revoke_reason")})
    old_root = ((before.get("cold") or {}).get("root") or {})
    new_root = ((committed.get("cold") or {}).get("root") or {})
    if new_root and old_root.get("count", 0) != new_root.get("count", 0):
        events.append({"kind": "history.appended", "from_count": old_root.get("count", 0),
                       "to_count": new_root.get("count", 0), "head_h": new_root.get("head_h")})
    archived = sorted(set(new_work) - set(committed.get("work") or {}))
    for wid in archived:
        events.append({"kind": "unit.archived", "id": wid, "unit": new_work[wid].get("kind"),
                       "state": new_work[wid].get("state")})
    return events


# ---------------------------------------------------------------------------------------------- hot bound (D2)

def events_payload(revision: int, events: list[dict[str, Any]]) -> str:
    """The canonical bytes of a complete overflow event list (``aew/transition-events/v1``)."""
    return dump_yaml({"schema": EVENTS_SCHEMA, "revision": revision, "events": events})


def overflow_path(revision: int) -> str:
    return f"{LOG_DIR}/{revision:06d}.events.yaml"


def bound(revision: int, events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None,
                                                                str | None]:
    """``(hot events, event_overflow, sidecar text)``: the set itself when it fits, else its first
    :data:`MAX_HOT_EVENTS` with a descriptor of the complete sidecar."""
    if len(events) <= MAX_HOT_EVENTS:
        return events, None, None
    text = events_payload(revision, events)
    counts = Counter(e["kind"] for e in events)
    return events[:MAX_HOT_EVENTS], {"path": overflow_path(revision), "sha256": sha256_bytes(text.encode("utf-8")),
                                     "event_count": len(events), "counts_by_kind": dict(sorted(counts.items()))}, text


# ---------------------------------------------------------------------------------------------- chain (D7)

def transition_hash(prev_h: str, record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "h"}
    return hashlib.sha256(bytes.fromhex(prev_h) + canonical_json(body)).hexdigest()


def seal(record: dict[str, Any], prev_h: str) -> dict[str, Any]:
    record["h"] = transition_hash(prev_h, record)
    return record


def previous_h(before: dict[str, Any]) -> str:
    """The head the next record chains from: the newest record's ``h``, or genesis when the chain starts now."""
    if not before.get("outbox"):
        return GENESIS_H
    return (before.get("last_transition") or {}).get("h") or GENESIS_H


def marker(state: dict[str, Any], revision: int) -> dict[str, Any]:
    """The ``outbox`` key for a commit at ``revision``: kept once present, else the chain starts here."""
    return state.get("outbox") or {"schema": OUTBOX_SCHEMA, "since": revision}


# ---------------------------------------------------------------------------------------------- reading (D3)

def _read_record(aew_root: Path, revision: int) -> dict[str, Any] | None:
    try:
        raw = (aew_root / LOG_DIR / f"{revision:06d}.yaml").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return load_yaml(raw, source=f"{LOG_DIR}/{revision:06d}.yaml")


def complete_events(aew_root: Path, record: dict[str, Any]) -> list[dict[str, Any]] | None:
    """A record's complete event list: the hot list, or the verified sidecar it names. None before the outbox."""
    overflow = record.get("event_overflow")
    if overflow is None:
        return record.get("events")
    try:
        raw = (aew_root / overflow["path"]).read_bytes()
    except FileNotFoundError:
        raise IntegrityError(f"revision {record['revision']}: its overflow events {overflow['path']} are missing",
                             revision=record["revision"]) from None
    if sha256_bytes(raw) != overflow["sha256"]:
        raise IntegrityError(f"revision {record['revision']}: overflow events {overflow['path']} do not match the "
                             "digest the transition committed", revision=record["revision"])
    payload = load_yaml(raw.decode("utf-8"), source=overflow["path"])
    events = payload.get("events") or []
    if payload.get("revision") != record["revision"] or len(events) != overflow["event_count"]:
        raise IntegrityError(f"revision {record['revision']}: overflow events {overflow['path']} disagree with the "
                             "transition's descriptor", revision=record["revision"])
    return events


def read_transitions(aew_root: Path, since: int, through: int, *, outbox: dict[str, Any] | None,
                     prev_h: str | None = None, retries: int = 3) -> Iterator[dict[str, Any]]:
    """Logical transitions ``since + 1 .. through``, in order, each with its complete events and its chain checked.

    No control lock is taken: published log records are immutable. A missing record is retried briefly (a commit
    publishes its log record just after the commit point, and recovery repairs it), then reported as incomplete
    history, never skipped. ``prev_h`` is the ``h`` of record ``since`` when the caller knows it; otherwise the chain
    is checked from the first record read onwards."""
    start = (outbox or {}).get("since")

    def required(revision: int, what: str) -> dict[str, Any]:
        record = None
        for attempt in range(retries + 1):
            record = _read_record(aew_root, revision)
            if record is not None:
                break
            if attempt < retries:
                time.sleep(0.05 * (attempt + 1))
        if record is None:
            raise IntegrityError(f"the transition log has no record of revision {revision} ({what}): incomplete "
                                 "history", revision=revision)
        if record.get("revision") != revision:
            raise IntegrityError(f"{LOG_DIR}/{revision:06d}.yaml records revision {record.get('revision')}",
                                 revision=revision)
        if start is not None and revision >= start and record.get("h") is None:
            raise IntegrityError(f"revision {revision} is after the outbox began ({start}) but has no hash",
                                 revision=revision)
        return record

    if prev_h is None and start is not None and start <= since < through:
        # The chain continues from the record the cursor names: it must exist and carry its hash, or the first record
        # of the page would go unchecked (review of PR #53).
        prev_h = required(since, "the cursor")["h"]
    for revision in range(since + 1, through + 1):
        record = required(revision, "requested")
        if start is not None and revision >= start:
            expected_prev = GENESIS_H if revision == start else prev_h
            if expected_prev is None or record["h"] != transition_hash(expected_prev, record):
                raise IntegrityError(f"revision {revision}: the transition hash chain is broken", revision=revision)
            prev_h = record["h"]
        out = dict(record)
        out["events"] = complete_events(aew_root, record)
        yield out


def matches(record: dict[str, Any], kinds: set[str] | None) -> dict[str, Any] | None:
    """The record narrowed to ``kinds``; None when it has no event of those kinds."""
    if not kinds:
        return record
    events = [e for e in record.get("events") or [] if e["kind"] in kinds]
    return dict(record, events=events) if events else None


# ---------------------------------------------------------------------------------------------- wake (D4)

def bump_wake(aew_root: Path, revision: int | None = None) -> None:
    """Advisory: change ``local/wake``. A plain write, never fsynced: waiters only stat the file, and durability would
    cost a commit milliseconds on Windows for nothing (ADR-0012's H2 budget). Failure is ignored; a waiter's coarse
    check covers a missed wake."""
    try:
        path = aew_root / WAKE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{revision if revision is not None else '-'} {time.time_ns()}\n", encoding="utf-8")
    except OSError:
        pass


def wake_mark(aew_root: Path) -> tuple[int, int] | None:
    try:
        st = os.stat(aew_root / WAKE_REL)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_ino ^ st.st_size


def wait_for(check: Callable[[], Any], aew_root: Path, *, timeout: float, tick: float = 0.025,
             coarse: float = 2.0) -> Any:
    """Block until ``check()`` returns something truthy or ``timeout`` passes: re-checks when the wake file changes,
    and every ``coarse`` seconds regardless. Returns the last ``check()`` result."""
    result = check()
    deadline = time.monotonic() + timeout
    last_mark, last_full = wake_mark(aew_root), time.monotonic()
    while not result and time.monotonic() < deadline:
        time.sleep(tick)
        mark = wake_mark(aew_root)
        if mark != last_mark or time.monotonic() - last_full >= coarse:
            last_mark, last_full = mark, time.monotonic()
            result = check()
    return result
