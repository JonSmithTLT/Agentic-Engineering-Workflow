"""The history manifest's form: entries, the hash chain over them, and its bounded files (ADR-0011; implementation
plan R1).

The authoritative history is an append-only sequence of entries. Each entry describes one immutable record (a
terminal unit's bundle, an annotation, an audit record) by path and SHA-256. Entries are chained:

    h(0)   = GENESIS_H
    h(n)   = SHA-256( bytes.fromhex(h(n-1)) || canonical_json(entry(n)) )

``canonical_json`` is JSON with sorted keys, no whitespace and UTF-8, over the entry without its own ``h``; it is
never the YAML bytes, so the layout of the files can change without changing a single hash.

The entries live in bounded files under ``history/``: a mutable tail with fewer than ``SEGMENT_SIZE`` entries, and
sealed segments of exactly ``SEGMENT_SIZE`` entries that are never rewritten. Each file records the chain state it
starts from (``start``) and the file hash of the sealed segment before it (``prev``, a repair aid). The hot root that
pins the whole history is

    {count, head_h, sealed_head: {seq, sha256} | null}

where ``count`` is the number of entries, ``head_h`` the chain hash after the last one, and ``sealed_head`` the
newest sealed segment's number and file hash. Any earlier root ``{n, h(n)}`` stays checkable however the entries are
later laid out: fold entries n+1..m from h(n) and compare with the current root.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aew.errors import IntegrityError
from aew.schemas import validate, validate_def
from aew.util import dump_yaml, load_yaml

SEGMENT_SIZE = 256
HISTORY_DIR = "history"
TAIL_REL = f"{HISTORY_DIR}/tail.yaml"
SEGMENT_SCHEMA = "aew/history/segment/v1"
TAIL_SCHEMA = "aew/history/tail/v1"
GENESIS_H = hashlib.sha256(b"aew/history/v1 genesis").hexdigest()
ENTRY_KINDS = ("unit", "annotation", "audit", "lead")
SOURCES = ("engine", "operator", "model", "external")


def segment_rel(seq: int) -> str:
    return f"{HISTORY_DIR}/seg-{seq:06d}.yaml"


def empty_root() -> dict[str, Any]:
    return {"count": 0, "head_h": GENESIS_H, "sealed_head": None}


def canonical_json(value: Any) -> bytes:
    """The bytes an entry is hashed over. Only JSON values are allowed: a timestamp object or a tuple would make the
    hash depend on how a loader happened to type it."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require_json(value: Any, where: str) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise IntegrityError(f"{where}: floats are not allowed in history entries")
    if isinstance(value, list):
        for i, v in enumerate(value):
            _require_json(v, f"{where}[{i}]")
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise IntegrityError(f"{where}: keys must be strings")
            _require_json(v, f"{where}.{k}")
        return
    raise IntegrityError(f"{where}: {type(value).__name__} is not a JSON value")


def chain_hash(prev_h: str, entry: dict[str, Any]) -> str:
    """h(n) from h(n-1) and entry n (``h`` itself is excluded)."""
    body = {k: v for k, v in entry.items() if k != "h"}
    _require_json(body, f"entry {body.get('seq')}")
    return hashlib.sha256(bytes.fromhex(prev_h) + canonical_json(body)).hexdigest()


def new_entry(seq: int, prev_h: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Entry ``seq`` with its chain hash. ``fields`` carries everything but ``seq`` and ``h``."""
    if "seq" in fields or "h" in fields:
        raise IntegrityError("an entry's seq and h are assigned by the manifest")
    entry = {"seq": seq, **fields}
    validate_def("history", "entry", entry, source=f"history entry {seq}")
    entry["h"] = chain_hash(prev_h, entry)
    return entry


# ---------------------------------------------------------------------------------------------- files

def render_file(*, sealed: bool, seq: int, start: dict[str, Any], prev: dict[str, Any] | None,
                entries: list[dict[str, Any]]) -> str:
    doc = {"schema": SEGMENT_SCHEMA if sealed else TAIL_SCHEMA, "seq": seq, "start": dict(start),
           "prev": dict(prev) if prev else None, "entries": entries}
    return dump_yaml(doc)


def parse_file(text: str, *, source: str, sealed: bool) -> dict[str, Any]:
    doc = load_yaml(text, source=source)
    validate("history", doc, source=source)
    want = SEGMENT_SCHEMA if sealed else TAIL_SCHEMA
    if doc["schema"] != want:
        raise IntegrityError(f"{source}: is a {doc['schema']} file, expected {want}")
    if sealed and len(doc["entries"]) != SEGMENT_SIZE:
        raise IntegrityError(f"{source}: a sealed segment holds exactly {SEGMENT_SIZE} entries, "
                             f"found {len(doc['entries'])}")
    if not sealed and len(doc["entries"]) >= SEGMENT_SIZE:
        raise IntegrityError(f"{source}: the tail holds fewer than {SEGMENT_SIZE} entries, found "
                             f"{len(doc['entries'])}")
    return doc


def fold(start: dict[str, Any], entries: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
    """Check that ``entries`` continue the chain from ``start`` ({count, h}); the chain state after them."""
    count, h = start["count"], start["h"]
    for entry in entries:
        if entry.get("seq") != count + 1:
            raise IntegrityError(f"{source}: entry {entry.get('seq')} where {count + 1} was expected")
        expected = chain_hash(h, entry)
        if entry.get("h") != expected:
            raise IntegrityError(f"{source}: entry {entry['seq']} does not continue the hash chain",
                                 seq=entry["seq"])
        count, h = count + 1, expected
    return {"count": count, "h": h}


def segment_of(seq: int) -> int:
    """The number of the segment that holds (or will hold) entry ``seq``."""
    return (seq - 1) // SEGMENT_SIZE + 1
