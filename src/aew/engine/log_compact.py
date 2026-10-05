"""Sealing the transition log into segments (ADR-0012 D6, M4-D slice D2): ``aew history compact``.

The transition log keeps the newest :data:`~aew.engine.outbox.LOG_WINDOW` revisions as per-revision files
(``state/log/<rev>.yaml``, an overflow's ``<rev>.events.yaml``). Older revisions are sealed in groups of
:data:`~aew.engine.outbox.SEGMENT_SIZE`, aligned on multiples of it, into ``state/log/seg-NNNNNN.yaml`` (segment
``NNNNNN`` holds revisions ``NNNNNN * 256`` to ``NNNNNN * 256 + 255``). Nothing is discarded: a segment holds each
record exactly as its file did and the exact bytes of every overflow payload, and it preserves the hash chain (D7).

One segment, in this order (:func:`seal_steps`):

1. **Build** from the unsealed files only (no segment exists yet, so every record and overflow payload must be there:
   it never invents a record). The chain and every overflow digest and count are verified before anything is written.
   A record missing from the outbox era (at or after ``outbox.since``) is incomplete history and stops compaction. A
   record missing, or not a valid transition, from before the outbox began was never protected (ADR-0012 D1), so its
   segment is skipped and reported as unsealable, its files stay unsealed, and compaction continues with the next one.
2. **Publish** create-if-absent (a temp file fsynced, then an atomic no-overwrite rename). Fault point
   ``log.seal.after_segment``: the segment is durable and every unsealed file is still present.
3. **Re-read** the segment from disk and verify it completely: schema, position, the chain through it, its link to the
   transition before it, every overflow payload's digest and count; and every unsealed copy still present must be
   equivalent to its sealed copy (the same record; the same payload bytes). Any disagreement is corruption: nothing is
   removed.
4. **Prune** each revision's record, then its sidecar. Fault point ``log.seal.mid_prune`` halfway through. Removal is
   idempotent; a file Windows will not delete yet (a reader has it open) is left for the next run and reported.

A crash therefore leaves only unsealed files (before 2), or a valid segment and some or all of the equivalent unsealed
files (after 2): never neither. Re-running verifies an existing segment and resumes pruning.

Compaction is never on the commit path: only ``aew history compact`` (or, later, a maintenance service calling
:func:`compact`) runs it. It takes the control lock **only around the publish** (step 2): ``create_exclusive`` writes a
``.seg-*.tmp`` file in ``state/log`` first, and every writer's recovery sweeps ``.*.tmp`` files there under that lock,
so without it a commit could delete the temp file mid-publish. Build, the full re-read and the prune run without the
lock, so a commit never waits for them (a segment costs seconds to verify), and that is safe:

* their inputs are immutable: published records, sidecars and segments are never rewritten, and a writer writes only
  the newest revision's record (a commit, or recovery repairing it), which ``window >= 1`` keeps out of every eligible
  segment, so no writer touches the files a compactor reads or removes;
* a second compactor is harmless: the publish is create-if-absent (the loser verifies the winner's segment), and the
  verification and the prune are idempotent (a file already removed is not an error). A build that fails because
  files are missing looks for the segment again before reporting anything: another compactor may have sealed and
  pruned them after this one found no segment, and then they are sealed, not lost (nor unsealable).

Lockless readers stay correct under any interleaving through the reader protocol (``outbox.LogView``), never through
the lock.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.engine import faults
from aew.engine.lock import FileLock
from aew.engine.outbox import (
    LOG_DIR,
    LOG_WINDOW,
    SEGMENT_SCHEMA,
    SEGMENT_SIZE,
    LogView,
    Segment,
    _read_record,
    load_segment,
    overflow_path,
    payload_events,
    read_optional,
    record_path,
    segment_path,
    verify_segment,
)
from aew.engine.store import LOCK_REL, ControlStore
from aew.errors import IntegrityError, UsageError, ValidationFailed
from aew.schemas import validate
from aew.util import create_exclusive, dump_yaml, load_yaml

_RECORD = re.compile(r"^([0-9]{6,})\.yaml$")
_SIDECAR = re.compile(r"^([0-9]{6,})\.events\.yaml$")
_SEGMENT = re.compile(r"^seg-([0-9]{6,})\.yaml$")
UNLINK_WAIT_S = 1.0


def eligible_segments(revision: int, window: int = LOG_WINDOW) -> int:
    """How many segments, from segment 0, lie entirely before the newest ``window`` revisions."""
    return max(0, (revision - window + 1) // SEGMENT_SIZE)


@dataclass
class Listing:
    """What ``state/log`` holds, from one directory scan."""

    records: set[int] = field(default_factory=set)
    sidecars: set[int] = field(default_factory=set)
    segments: set[int] = field(default_factory=set)

    def leftovers(self, index: int) -> list[int]:
        """Revisions of segment ``index`` that still have an unsealed record or sidecar."""
        span = range(index * SEGMENT_SIZE, (index + 1) * SEGMENT_SIZE)
        return [r for r in span if r in self.records or r in self.sidecars]


def scan(aew_root: Path) -> Listing:
    listing = Listing()
    try:
        entries = list(os.scandir(aew_root / LOG_DIR))
    except FileNotFoundError:
        return listing
    for entry in entries:
        for pattern, bucket in ((_RECORD, listing.records), (_SIDECAR, listing.sidecars),
                                (_SEGMENT, listing.segments)):
            m = pattern.match(entry.name)
            if m:
                bucket.add(int(m.group(1)))
                break
    return listing


def sealed_state(aew_root: Path, revision: int) -> tuple[int, int]:
    """``(sealed segments, unsealed window)`` from one directory scan, no parse: cheap enough for doctor. The window
    is the revisions after the newest sealed segment. Segments are sealed in order, so a gap below it is a segment
    that could not be sealed (:class:`Unsealable`), which no compaction will shrink and the window does not count."""
    segments = scan(aew_root).segments
    sealed_through = (max(segments) + 1) * SEGMENT_SIZE if segments else 0
    return len(segments), revision + 1 - sealed_through


class Unsealable(IntegrityError):
    """A segment that cannot be sealed because a record from before the outbox began is missing or invalid. Nothing
    protected those records (ADR-0012 D1), so this is reported and the segment skipped, never a reason to stop."""


def build_segment(aew_root: Path, index: int, since: int) -> str:
    """The canonical text of segment ``index`` from the unsealed files, verified before it is written."""
    first = index * SEGMENT_SIZE
    view = LogView(aew_root, since, retries=0)
    prev_h = view.record(first - 1, "the transition before the segment")["h"] if first > since else None
    records: list[dict[str, Any]] = []
    payloads: dict[str, str] = {}
    for revision in range(first, first + SEGMENT_SIZE):
        record = _read_record(aew_root, revision)
        if record is None and revision < since:
            raise Unsealable(f"{record_path(revision)} is missing; it is from before the outbox began at revision "
                             f"{since}", segment=index, revision=revision)
        if record is None:
            raise IntegrityError(f"cannot seal {segment_path(index)}: {record_path(revision)} is missing, and no "
                                 "segment holds it: incomplete history", revision=revision)
        if revision < since:  # no chain vouches for it: its schema must, or the published segment would not verify
            try:
                validate("transition", record, source=record_path(revision))
            except ValidationFailed as exc:
                raise Unsealable(f"{record_path(revision)} is not a valid transition record; it is from before the "
                                 f"outbox began at revision {since}", segment=index, revision=revision,
                                 violations=exc.details.get("violations")) from None
        records.append(record)
        overflow = record.get("event_overflow")
        if overflow is not None:
            raw = read_optional(aew_root / overflow["path"])
            if raw is None:
                raise IntegrityError(f"cannot seal {segment_path(index)}: revision {revision}'s overflow events "
                                     f"{overflow['path']} are missing", revision=revision)
            payload_events(record, raw, source=overflow["path"])
            payloads[str(revision)] = raw.decode("utf-8")
    head_h = records[-1].get("h") if first + SEGMENT_SIZE - 1 >= since else None
    doc = {"schema": SEGMENT_SCHEMA, "segment": index, "first": first, "count": SEGMENT_SIZE, "prev_h": prev_h,
           "head_h": head_h, "transitions": records, "overflow": payloads}
    text = dump_yaml(doc)
    # Never publish an immutable segment that would fail: the text round-trips to this document, whose chain and
    # payloads verify (the schemas are validated on the copy read back from disk, before anything is pruned).
    if load_yaml(text, source=segment_path(index)) != doc:
        raise IntegrityError(f"{segment_path(index)} would not read back as written", path=segment_path(index))
    verify_segment(doc, index, since, source=segment_path(index), schema=False)
    return text


def _unlink(path: Path) -> bool:
    """Remove ``path`` if present; False when the OS still refuses after a short wait (Windows: a reader has it open).
    """
    deadline = time.monotonic() + UNLINK_WAIT_S
    while True:
        try:
            path.unlink(missing_ok=True)
            return True
        except PermissionError:
            if time.monotonic() > deadline:
                return False
            time.sleep(0.05)


def verify_against_unsealed(aew_root: Path, segment: Segment, since: int) -> None:
    """A segment read back from disk, checked against everything around it before any unsealed file is removed: its
    link to the transition before it, and the equivalence of every unsealed copy still present (D1)."""
    rel = segment_path(segment.index)
    if segment.prev_h is not None:
        before = LogView(aew_root, since, retries=0).record(segment.first - 1, "the transition before the segment")
        if before["h"] != segment.prev_h:
            raise IntegrityError(f"{rel} does not continue the hash chain from revision {segment.first - 1}",
                                 revision=segment.first, path=rel)
    for revision in range(segment.first, segment.first + SEGMENT_SIZE):
        unsealed = _read_record(aew_root, revision)
        if unsealed is not None and unsealed != segment.record(revision):
            raise IntegrityError(f"revision {revision}: {record_path(revision)} and its sealed copy in {rel} disagree",
                                 revision=revision, path=rel)
        sidecar = read_optional(aew_root / overflow_path(revision))
        if sidecar is not None and (revision not in segment.payloads
                                    or sidecar != segment.payloads[revision].encode("utf-8")):
            raise IntegrityError(f"revision {revision}: {overflow_path(revision)} and the overflow payload sealed in "
                                 f"{rel} disagree", revision=revision, path=rel)


def seal_steps(aew_root: Path, index: int, since: int,
               publish_lock: Callable[[], AbstractContextManager[Any]] = nullcontext) -> Iterator[dict[str, Any]]:
    """Seal segment ``index`` and prune its unsealed files, yielding after each durable step (so tests can interleave
    a lockless reader with every intermediate state). ``publish_lock`` is held around the publish only (the control
    lock, from :func:`compact`). See the module docstring for the order and why the rest needs no lock."""
    rel = segment_path(index)
    if not (aew_root / rel).is_file():
        try:
            text: str | None = build_segment(aew_root, index, since)
        except IntegrityError:  # Unsealable included
            # Another compactor may have published this segment and pruned its files after the check above: a record
            # it removed is not missing, it is sealed. Then the segment is verified below like any existing one.
            # Only a build failure with no segment behind it is incomplete history (or a truly unsealable segment).
            if not (aew_root / rel).is_file():
                raise
            text = None
    else:
        text = None
    if text is not None:
        try:
            with publish_lock():
                create_exclusive(aew_root / rel, text)
        except IntegrityError:
            if not (aew_root / rel).is_file():
                raise
            # Another compactor published it first: it is verified below like any existing segment.
        else:
            faults.hit("log.seal.after_segment")
            faults.pause("log.seal.after_segment")  # tests hold a real compactor here while readers race it
            yield {"step": "sealed", "segment": index}
    segment = load_segment(aew_root, index, since, schema=True)  # re-read: schemas, chain and payloads verified
    if segment is None:
        raise IntegrityError(f"{rel} vanished after it was published", path=rel)
    verify_against_unsealed(aew_root, segment, since)
    yield {"step": "verified", "segment": index}
    half = SEGMENT_SIZE // 2
    for offset in range(SEGMENT_SIZE):
        revision = segment.first + offset
        pending = [p for p in (record_path(revision), overflow_path(revision)) if not _unlink(aew_root / p)]
        yield {"step": "pruned", "revision": revision, "pending": pending}
        if offset == half - 1:
            faults.hit("log.seal.mid_prune")
            faults.pause("log.seal.mid_prune")


def compact(store: ControlStore, *, window: int = LOG_WINDOW) -> dict[str, Any]:
    """Seal every segment that lies entirely before the newest ``window`` revisions, and finish pruning any segment
    an interrupted run left behind. Idempotent. ``window`` below :data:`LOG_WINDOW` is for tests only."""
    if window < 1:
        raise UsageError("the unsealed window must keep at least the newest revision")
    state = store.read()  # recovery has published the newest record; the control lock is released again
    marker = state.get("outbox")
    revision = state["revision"]
    if marker is None:
        return {"ok": True, "revision": revision, "window": window, "sealed": [], "resumed": [], "unsealable": [],
                "pruned": 0, "pending": [], "unsealed": revision + 1, "note": "no outbox yet: nothing is sealed "
                "before the transition chain starts (the next commit starts it)"}
    since = marker["since"]
    listing = scan(store.root)
    sealed: list[int] = []
    resumed: list[int] = []
    unsealable: list[dict[str, Any]] = []
    pruned = 0
    pending: list[str] = []
    for index in range(eligible_segments(revision, window)):
        exists = index in listing.segments
        if exists and not listing.leftovers(index):
            continue
        def control_lock() -> FileLock:
            return FileLock(store.root / LOCK_REL, timeout=store.lock_timeout)

        try:
            for step in seal_steps(store.root, index, since, control_lock):
                if step["step"] == "pruned":
                    pruned += 1
                    pending += step["pending"]
        except Unsealable as exc:
            unsealable.append({"segment": index, "revision": exc.details.get("revision"), "reason": exc.message})
            continue
        (resumed if exists else sealed).append(index)
    count, unsealed = sealed_state(store.root, revision)
    return {"ok": True, "revision": revision, "window": window, "sealed": sealed, "resumed": resumed,
            "unsealable": unsealable, "pruned": pruned, "pending": pending, "segments": count, "unsealed": unsealed}


def window_status(aew_root: Path, revision: int) -> tuple[str, str]:
    """``aew doctor``'s check (D6): WARN when the unsealed window exceeds ``LOG_WINDOW + SEGMENT_SIZE`` revisions."""
    segments, unsealed = sealed_state(aew_root, revision)
    detail = (f"{segments} sealed segment(s); {unsealed} revision(s) unsealed (window {LOG_WINDOW}, sealed "
              f"{SEGMENT_SIZE} at a time)")
    if unsealed > LOG_WINDOW + SEGMENT_SIZE:
        return "WARN", f"{detail}: run `aew history compact` to seal the older revisions"
    return "PASS", detail
