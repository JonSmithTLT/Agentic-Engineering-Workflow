"""Disposable generation-scoped delivery receipts, never durable shown facts (amendment 3 §2.2, reviewed m-1).

Only the broker records IDs from a verified, successful body-bearing result. The stable lock and its turnstile are
not the replaceable JSON inode. Atomic replacement lets lock-free readers see an old complete union or the new one;
missing, invalid or other-generation data suppresses nothing. No body, credential, revision or timestamp is stored.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from aew import process_kind, util
from aew.coordination.layout import MESSAGE_ID_RE
from aew.engine import faults
from aew.engine.lock import FileLock
from aew.errors import IntegrityError, StaleAuthority, UsageError

REL = "local/lead/told-messages.json"
LOCK_REL = "local/lead/told-messages.lock"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError, RecursionError):
        return None


def _valid(doc: Any) -> bool:
    return (isinstance(doc, dict) and set(doc) == {"generation", "messages"}
            and type(doc["generation"]) is int and doc["generation"] >= 0
            and isinstance(doc["messages"], list)
            and all(isinstance(mid, str) and MESSAGE_ID_RE.fullmatch(mid) is not None for mid in doc["messages"])
            and doc["messages"] == sorted(set(doc["messages"])))


def read(aew_root: Path, generation: int) -> set[str]:
    doc = _load(aew_root / REL)
    return set(doc["messages"]) if _valid(doc) and doc["generation"] == generation else set()


def record(aew_root: Path, generation: int, messages: Iterable[str], *, current: Callable[[], bool]) -> set[str]:
    """Union verified result IDs, rechecking broker authority after the lock wait and just before replacement.
    ``current`` is the broker's own lock-free authority/generation check, never a caller-supplied bridge argument.
    A future-generation record is never overwritten, even if its payload is otherwise damaged."""
    process_kind.require_writer("record told messages", writes=REL)
    if type(generation) is not int or generation < 0:
        raise UsageError("a told-message generation is a nonnegative integer")
    ids = set(messages)
    if any(not isinstance(mid, str) or MESSAGE_ID_RE.fullmatch(mid) is None for mid in ids):
        raise UsageError("told messages contain only complete MSG-INV-n-k IDs")
    if not ids:
        return read(aew_root, generation)
    if not current():
        raise StaleAuthority("this broker no longer holds its told-message generation")
    with FileLock(aew_root / LOCK_REL) as lock:
        doc = _load(aew_root / REL)
        if (isinstance(doc, dict) and type(doc.get("generation")) is int and doc["generation"] > generation):
            raise StaleAuthority("a newer broker generation already owns the told-message record")
        if not current():
            raise StaleAuthority("the broker lost authority while waiting for the told-message lock")
        union = (set(doc["messages"]) if _valid(doc) and doc["generation"] == generation else set()) | ids
        faults.pause("messaging.told.before_replace")
        if not lock.intact():
            raise IntegrityError("the stable told-message lock was removed or replaced; nothing was recorded")
        if not current():
            raise StaleAuthority("the broker lost authority before recording told messages")
        util.atomic_write(aew_root / REL, json.dumps({"generation": generation, "messages": sorted(union)}) + "\n")
        return union
