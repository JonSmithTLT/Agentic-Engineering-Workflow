"""The engine's own rules the issuer applies, vendored so the issuer imports nothing from AEW (WIS-02; ADR-0012).

WIS-02 requires the issuer to resolve each transition record as the engine's lock-free reader does, to chain it with
the engine's transition hash, and to verify sealed segments as ``aew.engine.outbox.verify_segment`` does. Importing
``aew.engine.outbox`` would pull in ``aew.schemas`` (jsonschema and its dependencies), ``aew.util`` and
``aew.errors``, and root would then install, and WIS-12's manifest cover, most of AEW. So each definition below is a
copy of the engine's, **byte for byte in its syntax tree**, and ``tests/unit/test_wis_engine_rules.py`` requires every
one to equal its source in ``src/aew`` (and every constant to equal the engine's value), so the copy cannot drift: a
change to the engine's rule fails that test until the copy here takes it, and the issuer's manifest then changes with
it. Where the engine's function does more than the issuer may (``deserialize_control`` also validates the control
schema), the issuer's function is the engine's leading statements, and the test pins that slice.

What the copies need from AEW is defined here for them alone: the two error classes (same names, same ``details``),
``sha256_bytes`` and ``IS_WINDOWS``, and a ``validate`` that refuses, because the issuer reads lock-free with
``schema=False`` as every AEW lock-free reader does and never validates a JSON Schema.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

IS_WINDOWS = sys.platform == "win32"  # as aew.util.IS_WINDOWS


class _VendoredError(Exception):
    """The shape of ``aew.errors.AEWError`` the copies use: a message and keyword ``details``."""

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class IntegrityError(_VendoredError):
    """As ``aew.errors.IntegrityError``: durable state is damaged or was modified outside the engine."""


class ValidationFailed(_VendoredError):
    """As ``aew.errors.ValidationFailed``: here, YAML the engine's loader refuses."""


def validate(kind: str, doc: Any, *, source: str) -> None:
    """The engine validates a JSON Schema here only when a copy is called with ``schema=True``; the issuer never is."""
    raise IntegrityError(f"{source}: the issuer reads lock-free and validates no JSON Schema ({kind})")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------------------------- aew.util (YAML)

_SafeLoader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
YAML_MAX_DEPTH = 64
YAML_TOO_DEEP = "yaml_too_deep"
_OPENS = (yaml.SequenceStartEvent, yaml.MappingStartEvent)
_CLOSES = (yaml.SequenceEndEvent, yaml.MappingEndEvent)


def yaml_too_deep(text: str, *, loader: Any = _SafeLoader, limit: int = YAML_MAX_DEPTH) -> int | None:
    """The 1-based line where ``text`` first nests deeper than ``limit``, or None. It reads the event stream, which
    libyaml and PyYAML both parse without recursing, so it is safe on a document that composing would crash on. Call
    it before composing anything that may be hostile; a syntax error raises ``yaml.YAMLError`` as composing would. The
    bound is syntactic: an alias counts as a leaf, so the value composed may be deeper than ``limit``."""
    depth = 0
    for event in yaml.parse(text, Loader=loader):  # noqa: S506 - events only, nothing is constructed
        if isinstance(event, _OPENS):
            depth += 1
            if depth > limit:
                return event.start_mark.line + 1
        elif isinstance(event, _CLOSES):
            depth -= 1
    return None


_FLATTEN_IT = f"flatten it to at most {YAML_MAX_DEPTH} levels of mappings and sequences"


def load_yaml(text: str, *, source: str = "<yaml>", remedy: str = _FLATTEN_IT) -> Any:
    """``text`` as YAML, safely: a syntax error, or a nesting deeper than :data:`YAML_MAX_DEPTH` (reason
    :data:`YAML_TOO_DEEP`), is a ValidationFailed, never a crash. ``remedy`` ends that refusal: what to do instead,
    for a file whose remedy is not flattening it (review of #236, R2-F3). Every read in AEW passes the bound, the
    control store's own files included: their checksums keep out damage, not a writer (a same-account process, a worker
    on Windows, or a git checkout can write them and recompute the hash), so skipping the pass would turn a deep file
    into a process killed with no error (review of #236, F1). The pass costs 28-43% of a parse, once per version of a
    file a process parses (once per CLI command; again after each commit for a long-lived reader): 39 ms at 50 units,
    379 ms at 500 (control state, Windows, libyaml, 2026-10-23)."""
    try:
        line = yaml_too_deep(text)
        if line is not None:
            raise ValidationFailed(f"{source}: the YAML nests deeper than {YAML_MAX_DEPTH} levels (at line {line}): "
                                   f"AEW does not read a document that deep; {remedy}", reason=YAML_TOO_DEEP,
                                   limit=YAML_MAX_DEPTH, line=line)
        return yaml.load(text, Loader=_SafeLoader)  # noqa: S506 (_SafeLoader is a SafeLoader subclass)
    except yaml.YAMLError as exc:
        raise ValidationFailed(f"{source}: invalid YAML: {exc}") from exc


# ---------------------------------------------------------------------------------------------- aew.history.manifest

def canonical_json(value: Any) -> bytes:
    """The bytes an entry is hashed over. Only JSON values are allowed: a timestamp object or a tuple would make the
    hash depend on how a loader happened to type it."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


# ---------------------------------------------------------------------------------------------- aew.engine.store

STORE_REL = "state"
CONTROL_REL = "state/control.yaml"
CHECKSUM_PREFIX = "# aew-checksum sha256:"


def control_body(raw: bytes, *, source: str) -> str:
    """The control file's YAML body, its checksum trailer verified: ``aew.engine.store.deserialize_control``'s leading
    statements, which the test pins, without its parse and its schema validation. A file with no trailer, or whose
    trailer is not the SHA-256 of the body (the body's final newline included), is an ``IntegrityError``; bytes that are
    not UTF-8 raise ``UnicodeDecodeError``, as in the engine."""
    text = raw.decode("utf-8")
    body, sep, trailer = text.rstrip("\n").rpartition("\n")
    if not sep or not trailer.startswith(CHECKSUM_PREFIX):
        raise IntegrityError(f"{source}: missing checksum trailer (damaged or edited outside AEW)")
    body += "\n"
    expected = trailer[len(CHECKSUM_PREFIX):].strip()
    if sha256_bytes(body.encode("utf-8")) != expected:
        raise IntegrityError(f"{source}: checksum mismatch (damaged or edited outside AEW)")
    return body


# ---------------------------------------------------------------------------------------------- aew.engine.outbox

TRANSITION_SCHEMA = "aew/transition/v1"
GENESIS_H = hashlib.sha256(b"aew/transition/v1 genesis").hexdigest()
LOG_DIR = "state/log"
SEGMENT_SIZE = 256
SEGMENT_SCHEMA = "aew/transition-segment/v1"


def overflow_path(revision: int) -> str:
    return f"{LOG_DIR}/{revision:06d}.events.yaml"


def transition_hash(prev_h: str, record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "h"}
    return hashlib.sha256(bytes.fromhex(prev_h) + canonical_json(body)).hexdigest()


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
    except FileNotFoundError:
        return None
    except PermissionError:
        if IS_WINDOWS:  # a deletion still pending; on POSIX it is a real permissions problem, reported as such
            return None
        raise


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
