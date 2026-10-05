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
  without the control lock. The cursor is the revision number. Each revision resolves from its per-revision file,
  else from a refreshed view of its sealed segment, equivalence required where both exist (:class:`LogView`).
* **Sealed segments** (D6, slice D2): revisions older than :data:`LOG_WINDOW` are sealed :data:`SEGMENT_SIZE` at a
  time into ``state/log/seg-NNNNNN.yaml`` by ``aew history compact`` (``aew.engine.log_compact``), never on the
  commit path; a segment keeps every record and overflow payload exactly and preserves the chain (D7).
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.errors import IntegrityError, ValidationFailed
from aew.history.manifest import canonical_json
from aew.schemas import validate
from aew.util import dump_yaml, load_yaml, sha256_bytes

TRANSITION_SCHEMA = "aew/transition/v1"
EVENTS_SCHEMA = "aew/transition-events/v1"
OUTBOX_SCHEMA = "aew/outbox/v1"
MAX_HOT_EVENTS = 64
GENESIS_H = hashlib.sha256(b"aew/transition/v1 genesis").hexdigest()
LOG_DIR = "state/log"
WAKE_REL = "local/wake"
LOG_WINDOW = 4096  # D6: revisions kept as per-revision files; older ones are sealed
SEGMENT_SIZE = 256  # D6: logical transitions per sealed segment ``state/log/seg-NNNNNN.yaml``
SEGMENT_SCHEMA = "aew/transition-segment/v1"

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


# ---------------------------------------------------------------------------------------------- reading (D3, D6)

def record_path(revision: int) -> str:
    return f"{LOG_DIR}/{revision:06d}.yaml"


def segment_of(revision: int) -> int:
    """The sealed segment that holds ``revision``: segments are aligned on multiples of :data:`SEGMENT_SIZE`."""
    return revision // SEGMENT_SIZE


def segment_path(index: int) -> str:
    return f"{LOG_DIR}/seg-{index:06d}.yaml"


def read_optional(path: Path) -> bytes | None:
    """A per-revision log file's bytes, or None when it is absent. Sealing removes these files while lockless readers
    run (D6), so a file that vanishes, or that Windows refuses to open because its deletion is pending, counts as
    absent: the caller then refreshes its sealed view, and only when neither representation resolves after a bounded
    retry is history reported incomplete (D3)."""
    try:
        return path.read_bytes()
    except (FileNotFoundError, PermissionError):
        return None


def _read_record(aew_root: Path, revision: int) -> dict[str, Any] | None:
    """The unsealed per-revision record ``state/log/<rev>.yaml``, or None. Readers use :class:`LogView`, which also
    resolves sealed segments."""
    raw = read_optional(aew_root / record_path(revision))
    if raw is None:
        return None
    return load_yaml(raw.decode("utf-8"), source=record_path(revision))


def payload_events(record: dict[str, Any], raw: bytes, *, source: str, schema: bool = False) -> list[dict[str, Any]]:
    """The complete events of an overflow ``record`` from the payload bytes ``raw`` (a sidecar's, or a segment's copy):
    their digest, revision and count must be the ones the transition committed (D2), else the payload is corrupt.
    ``schema`` also validates the payload against ``aew/transition-events/v1`` (sealing and segment checks)."""
    overflow, revision = record["event_overflow"], record["revision"]
    if sha256_bytes(raw) != overflow["sha256"]:
        raise IntegrityError(f"revision {revision}: overflow events {source} do not match the digest the transition "
                             "committed", revision=revision)
    payload = load_yaml(raw.decode("utf-8"), source=source)
    if schema:
        validate("transition-events", payload, source=source)
    events = payload.get("events") or []
    if payload.get("revision") != revision or len(events) != overflow["event_count"]:
        raise IntegrityError(f"revision {revision}: overflow events {source} disagree with the transition's "
                             "descriptor", revision=revision)
    return events


@dataclass(frozen=True)
class Segment:
    """A verified sealed segment (D6): 256 logical transitions from ``first``, with their overflow payloads' exact
    text by revision."""

    index: int
    first: int
    prev_h: str | None
    head_h: str | None
    records: list[dict[str, Any]]
    payloads: dict[int, str]

    def record(self, revision: int) -> dict[str, Any]:
        return self.records[revision - self.first]


def _segment_shape_ok(doc: Any) -> bool:
    """The structure a reader relies on, checked without the (costly) full schema: the chain and the payload digests
    then vouch for the content."""
    def descriptor_ok(d: Any) -> bool:
        return d is None or (isinstance(d, dict) and isinstance(d.get("path"), str)
                              and isinstance(d.get("sha256"), str) and isinstance(d.get("event_count"), int))

    return (isinstance(doc, dict) and doc.get("schema") == SEGMENT_SCHEMA and isinstance(doc.get("segment"), int)
            and isinstance(doc.get("first"), int) and doc.get("count") == SEGMENT_SIZE
            and all(doc.get(k) is None or isinstance(doc.get(k), str) for k in ("prev_h", "head_h"))
            and isinstance(doc.get("transitions"), list) and len(doc["transitions"]) == SEGMENT_SIZE
            and all(isinstance(r, dict) and isinstance(r.get("revision"), int)
                    and descriptor_ok(r.get("event_overflow")) for r in doc["transitions"])
            and isinstance(doc.get("overflow"), dict)
            and all(isinstance(k, str) and k.isdigit() and isinstance(v, str) for k, v in doc["overflow"].items()))


def verify_segment(doc: Any, index: int, since: int | None, *, source: str, schema: bool = True) -> Segment:
    """Check a parsed segment completely and return it (D6, D7; oracle rule 27): its schema, its position, exactly
    :data:`SEGMENT_SIZE` consecutive revisions, the hash chain through every record from the outbox's start ``since``
    (from ``prev_h``, or genesis at ``since``) ending at ``head_h``, and every overflow payload present, schema-valid
    and matching the digest and count its transition committed. Continuity with the previous segment is the caller's
    to check (``prev_h`` against the transition before ``first``). Any failure is an ``IntegrityError``.

    ``schema=False`` (lockless readers) checks the structure it relies on instead of the full JSON Schemas, which cost
    seconds per segment; the chain and the digests are checked either way. Sealing validates the schemas on the
    segment it re-reads before pruning anything, and the oracle on every segment."""
    if schema:
        try:
            validate("transition-segment", doc, source=source)
        except ValidationFailed as exc:
            raise IntegrityError(f"{source} is not a valid sealed segment", violations=exc.details.get("violations"),
                                 path=source) from None
    elif not _segment_shape_ok(doc):
        raise IntegrityError(f"{source} is not a valid sealed segment", path=source)
    first = index * SEGMENT_SIZE
    if doc["segment"] != index or doc["first"] != first:
        raise IntegrityError(f"{source} declares segment {doc['segment']} from revision {doc['first']}", path=source)
    records = doc["transitions"]
    for i, record in enumerate(records):
        if record["revision"] != first + i:
            raise IntegrityError(f"{source}: entry {i} records revision {record['revision']}, not {first + i}",
                                 path=source)
    h = doc["prev_h"]
    if since is not None:
        if (h is None) != (first <= since):
            raise IntegrityError(f"{source}: prev_h must name the transition before revision {first} exactly when "
                                 f"the chain began before it (at {since})", path=source)
        for record in records:
            revision = record["revision"]
            if revision < since:
                continue
            expected = GENESIS_H if revision == since else h
            if record.get("h") is None or record["h"] != transition_hash(expected, record):
                raise IntegrityError(f"{source}: the transition hash chain is broken at revision {revision}",
                                     revision=revision, path=source)
            h = record["h"]
        if doc["head_h"] != h:
            raise IntegrityError(f"{source}: head_h is not the hash of its last transition", path=source)
    payloads = {int(k): v for k, v in doc["overflow"].items()}
    overflowing = {r["revision"] for r in records if r.get("event_overflow") is not None}
    if set(payloads) != overflowing:
        raise IntegrityError(f"{source}: holds overflow payloads for {sorted(payloads)}, its transitions name "
                             f"{sorted(overflowing)}", path=source)
    for revision in sorted(overflowing):
        record = records[revision - first]
        if record["event_overflow"]["path"] != overflow_path(revision):
            raise IntegrityError(f"{source}: revision {revision}'s overflow names {record['event_overflow']['path']}",
                                 revision=revision, path=source)
        payload_events(record, payloads[revision].encode("utf-8"), source=f"{source} (revision {revision})",
                       schema=schema)
    return Segment(index, first, doc["prev_h"], doc["head_h"], records, payloads)


def load_segment(aew_root: Path, index: int, since: int | None, *, schema: bool = False) -> Segment | None:
    """Sealed segment ``index``, verified (:func:`verify_segment`), or None when there is none. Segments are
    immutable once published and never removed."""
    rel = segment_path(index)
    try:
        raw = (aew_root / rel).read_bytes()
    except FileNotFoundError:
        return None
    try:
        doc = load_yaml(raw.decode("utf-8"), source=rel)
    except (ValidationFailed, UnicodeDecodeError) as exc:
        raise IntegrityError(f"{rel} is not a readable sealed segment: {exc}", path=rel) from None
    return verify_segment(doc, index, since, source=rel, schema=schema)


class LogView:
    """One lockless reader's view of the transition log (D3): each revision resolves from its unsealed record, else
    from a refreshed view of its sealed segment; when both exist they must be equivalent; when neither resolves after
    a bounded retry the history is reported incomplete, never skipped. ``since`` is the outbox's start, for the chain.

    The view caches the segments it has loaded (they are immutable) and, for one call, that a segment was absent; an
    absent segment is looked up again whenever a revision is missing from the unsealed side, which is the refresh."""

    def __init__(self, aew_root: Path, since: int | None, *, retries: int = 3) -> None:
        self.root = aew_root
        self.since = since
        self.retries = retries
        self._segments: dict[int, Segment | None] = {}

    def segment(self, index: int, *, refresh: bool = False) -> Segment | None:
        if index not in self._segments or (refresh and self._segments[index] is None):
            self._segments[index] = load_segment(self.root, index, self.since)
        return self._segments[index]

    def _sealed_copy(self, revision: int, segment: Segment | None, unsealed: dict[str, Any] | None
                     ) -> dict[str, Any] | None:
        sealed = segment.record(revision) if segment is not None else None
        if unsealed is not None and sealed is not None and unsealed != sealed:
            raise IntegrityError(f"revision {revision}: {record_path(revision)} and its sealed copy in "
                                 f"{segment_path(segment_of(revision))} disagree", revision=revision)
        return sealed

    def _resolve_once(self, revision: int) -> dict[str, Any] | None:
        unsealed = _read_record(self.root, revision)
        sealed = self._sealed_copy(revision, self.segment(segment_of(revision), refresh=unsealed is None), unsealed)
        return unsealed if unsealed is not None else sealed

    def _retrying(self, attempt_once: Callable[[], Any]) -> Any:
        for attempt in range(self.retries + 1):
            found = attempt_once()
            if found is not None:
                return found
            if attempt < self.retries:
                time.sleep(0.05 * (attempt + 1))
        return None

    def resolve(self, revision: int) -> dict[str, Any] | None:
        """The logical record of ``revision`` from either representation, or None when neither holds it."""
        return self._retrying(lambda: self._resolve_once(revision))

    def record(self, revision: int, what: str = "requested") -> dict[str, Any]:
        record = self.resolve(revision)
        if record is None:
            if self.since is not None and revision < self.since:
                # Completeness is guaranteed from the revision the outbox began (D1): say where that is, so a consumer
                # that started at 0 can move on (D1 review F2). Still an error: no gap is ever skipped silently.
                raise IntegrityError(f"the transition log has no record of revision {revision} ({what}), which is "
                                     f"before the outbox began at revision {self.since}: the log is guaranteed "
                                     f"complete from revision {self.since}; read with --since {self.since - 1} or "
                                     "later", revision=revision, outbox_since=self.since,
                                     resume_since=self.since - 1)
            raise IntegrityError(f"the transition log has no record of revision {revision} ({what}), unsealed or "
                                 "sealed: incomplete history", revision=revision)
        if record.get("revision") != revision:
            raise IntegrityError(f"{record_path(revision)} records revision {record.get('revision')}",
                                 revision=revision)
        if self.since is not None and revision >= self.since and record.get("h") is None:
            raise IntegrityError(f"revision {revision} is after the outbox began ({self.since}) but has no hash",
                                 revision=revision)
        return record

    def _payload_once(self, record: dict[str, Any]) -> tuple[bytes, str] | None:
        revision, rel = record["revision"], record["event_overflow"]["path"]
        raw = read_optional(self.root / rel)
        if raw is not None:
            return raw, rel
        segment = self.segment(segment_of(revision), refresh=True)
        if segment is None or revision not in segment.payloads:
            return None
        self._sealed_copy(revision, segment, record)
        return segment.payloads[revision].encode("utf-8"), f"{segment_path(segment.index)} (revision {revision})"

    def events(self, record: dict[str, Any]) -> list[dict[str, Any]] | None:
        """A record's complete event list: the hot list, or its verified overflow payload from the sidecar or, once
        that is sealed, from the segment. None for a record from before the outbox."""
        if record.get("event_overflow") is None:
            return record.get("events")
        found = self._retrying(lambda: self._payload_once(record))
        if found is None:
            raise IntegrityError(f"revision {record['revision']}: its overflow events "
                                 f"{record['event_overflow']['path']} are missing, unsealed and sealed",
                                 revision=record["revision"])
        return payload_events(record, found[0], source=found[1])


def complete_events(aew_root: Path, record: dict[str, Any]) -> list[dict[str, Any]] | None:
    """A record's complete event list: the hot list, or the verified overflow payload it names. None before the
    outbox."""
    return LogView(aew_root, None).events(record)


def read_record(aew_root: Path, revision: int, *, since: int | None = None) -> dict[str, Any] | None:
    """The logical record of ``revision`` from whichever representation holds it (equivalence checked when both do),
    or None, without retrying: for oracles and tests."""
    return LogView(aew_root, since, retries=0).resolve(revision)


def read_transitions(aew_root: Path, since: int, through: int, *, outbox: dict[str, Any] | None,
                     prev_h: str | None = None, retries: int = 3) -> Iterator[dict[str, Any]]:
    """Logical transitions ``since + 1 .. through``, in order, each with its complete events and its chain checked.

    No control lock is taken: published log records and sealed segments are immutable, and sealing only removes an
    unsealed copy once its segment is durable and verified. Each revision resolves through :class:`LogView` (unsealed,
    else the refreshed sealed view, equivalence when both exist), so a reader that has fallen behind the window walks
    segments transparently and a reader racing a compaction never sees a false gap. A revision found in neither is
    retried briefly (a commit publishes its log record just after the commit point, and recovery repairs it), then
    reported as incomplete history, never skipped. ``prev_h`` is the ``h`` of record ``since`` when the caller knows
    it; otherwise the chain continues from record ``since`` itself."""
    start = (outbox or {}).get("since")
    view = LogView(aew_root, start, retries=retries)
    if prev_h is None and start is not None and start <= since < through:
        # The chain continues from the record the cursor names: it must exist and carry its hash, or the first record
        # of the page would go unchecked (review of PR #53).
        prev_h = view.record(since, "the cursor")["h"]
    for revision in range(since + 1, through + 1):
        record = view.record(revision)
        if start is not None and revision >= start:
            expected_prev = GENESIS_H if revision == start else prev_h
            if expected_prev is None or record["h"] != transition_hash(expected_prev, record):
                raise IntegrityError(f"revision {revision}: the transition hash chain is broken", revision=revision)
            prev_h = record["h"]
        out = dict(record)
        out["events"] = view.events(record)
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
