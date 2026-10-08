"""The closed writer of ``.aew/local/maps/`` (ADR-0015; design v0.5 §3.1 to §3.3; plan §4.1, §4.2).

This module is the only code that writes under ``local/maps/``: the artifacts (design §3.2's ``map.artifact.*``
family) and the registry with its log (``map.registry.*``). The Lead's synchronous ``aew map`` commands call it today;
F22.2's ``map_service`` will call the same functions under its own principal (ADR-0015 reconciles §3.2: adoption goes
through this closed path, and the principal in front of it is what F22.2 adds).

* **Placement.** ``.aew/local/`` is git-ignored, rebuildable data (KC §5.3, ``AEW_GITIGNORE``): a committed artifact
  would change the very path listing it describes. Deleting ``local/maps/`` means "no selection", which is safe
  because a map grants nothing (T5-INV-01).
* **Artifacts** are immutable and content-addressed (``structural/<artifact_sha256>.json``, canonical JSON). A second
  identical write succeeds; different bytes under an existing name are ``MAP_ARTIFACT_CORRUPT``.
* **The registry** has its own revision domain: its own lock, an ``epoch`` (random, new whenever the registry is
  created, so an expectation from before a deletion never matches again) and ``map_revision``; a selection is a
  compare-and-set on both (``<epoch>:<rev>``, or ``none:0`` before there is a registry). A refusal is
  ``STALE_REVISION`` with ``details.domain = "map_revision"``. It never touches control state or ``control_revision``
  (T5-INV-11), and each selection is appended to ``registry-log.jsonl`` with its actor and its ``selection_id``,
  which the registry also holds (§3.3: attributable, not workflow
  history).
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.engine.lock import FileLock
from aew.errors import (
    IntegrityError,
    MapArtifactCorrupt,
    MapRegistryInvalid,
    NotFound,
    StaleRevision,
    UsageError,
    ValidationFailed,
)
from aew.maps.canonical import seal
from aew.schemas import validate
from aew.util import atomic_write, create_exclusive, fsync_dir, utc_now

MAPS_REL = "local/maps"
STRUCTURAL_REL = f"{MAPS_REL}/structural"
REGISTRY_REL = f"{MAPS_REL}/registry.json"
LOG_REL = f"{MAPS_REL}/registry-log.jsonl"
LOCK_REL = f"{MAPS_REL}/registry.lock"
REGISTRY_SCHEMA = "aew/map-registry/v1"
NO_REGISTRY = "none:0"
SHA = re.compile(r"^[0-9a-f]{64}$")
EXPECTATION = re.compile(r"^(none|[0-9a-f]{16}):([0-9]+)$")


def artifact_rel(sha: str) -> str:
    return f"{STRUCTURAL_REL}/{sha}.json"


def _check_sha(sha: str) -> None:
    if not SHA.match(sha):
        raise UsageError(f"{sha!r} is not a structural map root (64 lower-case hex digits)")


# ------------------------------------------------------------------------------------------- artifacts


def write_artifact(aew_root: Path, record: dict[str, Any]) -> tuple[str, str]:
    """Publish ``record`` as an immutable artifact; returns ``(artifact_sha256, root)``. Idempotent: a concurrent or
    repeated write of the same bytes succeeds."""
    sha, data = seal(record)
    rel = artifact_rel(sha)
    path = aew_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        create_exclusive(path, data)
    except IntegrityError:  # the name exists: it must hold exactly these bytes
        if path.read_bytes() != data:
            raise MapArtifactCorrupt(
                f"{rel} exists and does not hold the bytes that hash to its name: the stored artifact is corrupt "
                f"(delete it and generate again)", root=sha, reason="hash_mismatch") from None
    return sha, rel


def read_artifact(aew_root: Path, sha: str) -> dict[str, Any]:
    """The strict reader (``aew map show --root``): the record, or ``NOT_FOUND`` / ``MAP_ARTIFACT_CORRUPT``. The
    stored bytes must be exactly the canonical JSON of a valid record whose identity is its name."""
    _check_sha(sha)
    rel = artifact_rel(sha)
    try:
        raw = (aew_root / rel).read_bytes()
    except FileNotFoundError:
        raise NotFound(f"no structural map {sha} in {MAPS_REL}", root=sha) from None

    def corrupt(why: str) -> MapArtifactCorrupt:
        return MapArtifactCorrupt(f"{rel} is corrupt ({why}); delete it and generate the map again", root=sha,
                                  reason=why)

    try:
        record = json.loads(raw)
    except ValueError:
        raise corrupt("not_json") from None
    if not isinstance(record, dict):
        raise corrupt("not_a_record")
    try:
        digest, sealed = seal(record)
    except TypeError:
        raise corrupt("not_canonical") from None
    if digest != sha or record.get("artifact_sha256") != sha or sealed != raw:
        raise corrupt("hash_mismatch")
    try:
        validate("codebase-map", record, source=rel)
    except ValidationFailed:
        raise corrupt("schema") from None
    return record


@dataclass(frozen=True)
class Available:
    record: dict[str, Any]
    entry: dict[str, Any]
    status: str = "AVAILABLE"


@dataclass(frozen=True)
class Unavailable:
    reason: str  # none | missing | corrupt | registry_invalid | unknown
    status: str = "UNAVAILABLE"


def read_selected(aew_root: Path) -> Available | Unavailable:
    """The selected structural map, never raising (plan §5.3): whatever is wrong with ``local/maps/`` becomes a typed
    ``Unavailable`` reason, so a consumer can never be refused or broken by a map (T5-INV-01)."""
    try:
        registry = read_registry(aew_root)
    except MapRegistryInvalid:
        return Unavailable("registry_invalid")
    except Exception:  # never raise: an unreadable registry is an unavailable map
        return Unavailable("unknown")
    entry = (registry or {}).get("selected", {}).get("structural")
    if not entry:
        return Unavailable("none")
    try:
        return Available(read_artifact(aew_root, entry["sha256"]), dict(entry))
    except NotFound:
        return Unavailable("missing")
    except MapArtifactCorrupt:
        return Unavailable("corrupt")
    except Exception:  # never raise (as above)
        return Unavailable("unknown")


# ------------------------------------------------------------------------------------------- the registry


def read_registry(aew_root: Path) -> dict[str, Any] | None:
    """The registry, or None when there is none; ``MAP_REGISTRY_INVALID`` when it is malformed."""
    path = aew_root / REGISTRY_REL
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    try:
        data = json.loads(raw)
        validate("map-registry", data, source=REGISTRY_REL)
    except (ValueError, ValidationFailed) as exc:
        raise MapRegistryInvalid(f"{REGISTRY_REL} is malformed; delete {MAPS_REL}/registry.json to clear the "
                                 "selection (a map grants nothing, so this is safe) and select again",
                                 problem=str(exc)[:400]) from None
    return data


def revision_of(registry: dict[str, Any] | None) -> str:
    """The registry's revision as ``--expect-map-rev`` takes it: ``<epoch>:<map_revision>``, or ``none:0``."""
    return NO_REGISTRY if registry is None else f"{registry['epoch']}:{registry['map_revision']}"


def parse_expectation(text: str) -> tuple[str, int]:
    m = EXPECTATION.match(text or "")
    if not m:
        raise UsageError(f"--expect-map-rev takes <epoch>:<revision> as `aew map show` prints it (or {NO_REGISTRY} "
                         f"before the first selection), not {text!r}")
    return m.group(1), int(m.group(2))


def select_structural(aew_root: Path, *, expect: str, entry: dict[str, Any], actor: dict[str, Any],
                      note: dict[str, Any] | None = None,
                      authorize: Callable[[], object] | None = None) -> dict[str, Any]:
    """Select ``entry`` as the structural map: compare-and-set on the registry's epoch and revision, under the
    registry's own lock. ``authorize`` is called under that lock, after the compare and before anything is written,
    and refuses by raising: the writer's authority is proven at the moment of the write, not only when its command
    began (ADR-0015 D4). Appends the log line, then replaces the registry atomically. Returns the new registry."""
    expected = parse_expectation(expect)
    with FileLock(aew_root / LOCK_REL) as lock:
        registry = read_registry(aew_root)
        current = revision_of(registry)
        if expected != parse_expectation(current):
            raise StaleRevision(f"expected map revision {expect}, current is {current}: read it again with "
                                "`aew map show`", domain="map_revision", expected=expect, current=current)
        if authorize is not None:
            authorize()
        if registry is None:  # the first selection creates the registry and its epoch, under the lock
            registry = {"schema": REGISTRY_SCHEMA, "epoch": secrets.token_hex(8), "map_revision": 0,
                        "selection_id": None, "selected": {}}
        previous = registry["selected"].get("structural")
        new = {**registry, "map_revision": registry["map_revision"] + 1, "selection_id": secrets.token_hex(8),
               "selected": {**registry["selected"], "structural": entry}}
        validate("map-registry", new, source="new map registry")
        if not lock.intact():
            raise IntegrityError(f"the map registry lock {LOCK_REL} was removed while held; nothing was written. "
                                 "Retry (and do not delete .aew/local/maps while a map command runs)")
        line = {"epoch": new["epoch"], "map_revision": new["map_revision"], "selection_id": new["selection_id"],
                "previous_selection_id": registry["selection_id"], "capability": "structural",
                "previous": previous["sha256"] if previous else None, "new": entry["sha256"], "actor": actor,
                "at": utc_now(), **(note or {})}
        _append_log(aew_root, line)
        atomic_write(aew_root / REGISTRY_REL, json.dumps(new, indent=2, sort_keys=True) + "\n")
    return new


def _append_log(aew_root: Path, line: dict[str, Any]) -> None:
    """The log line goes first, so no selection the registry holds is missing from the log. A crash or a failed
    registry write after it leaves a line for a selection that did not take effect, and the next selection may log
    the same ``(epoch, map_revision)`` again (PR #126 review, F2). Each line therefore carries a random
    ``selection_id`` and the ``previous_selection_id`` it replaced: the registry holds the id of the selection in
    effect, and each later line names the one it replaced, so the selections that took effect form one chain back from
    the registry, and a line off that chain is one that never took effect."""
    path = aew_root / LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as fh:
        fh.write((json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())
    fsync_dir(path.parent)
