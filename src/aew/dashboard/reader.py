"""The lock-free committed-state reader (design note §4.8; ADR-0012 D3, invariant 4).

Per request the server stats ``control.yaml``; only when its identity changed does it read the bytes
(``ControlStore.read_committed``: digest-cached parse, no recovery, no lock). The project manifest is read the same
way, by its own file identity, never through the engine's locked path. A :class:`Snapshot` is one coherent read: every
projection of one request is built from it (contract: "one coherent composite projection from a single control-state
read").

What this reader may observe, and how the projections treat it: a committed revision whose staged record files are not
applied yet (the window the engine's recovery closes under the lock). A record that is missing or does not match its
pin is then ``500 PROJECTION_FAILED`` (the frontend keeps its last known content visibly stale), and the next poll
succeeds once the apply has happened. Nothing is repaired and no gap is invented.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from aew.engine.api import Engine
from aew.engine.base import POLICY_PINS
from aew.errors import AEWError, MapArtifactCorrupt, NotFound, ValidationFailed
from aew.knowledge.manifest import MANIFEST, load_manifest
from aew.maps import store as MS
from aew.schemas import validate
from aew.util import load_yaml, sha256_bytes, utc_now


@dataclass(frozen=True)
class Snapshot:
    """One read of the committed state and the manifest, with the moment it was taken."""

    engine: Engine
    state: dict[str, Any]
    manifest: dict[str, Any]
    gates: dict[str, Any]  # the gates policy, read lock-free with the manifest ({} when it cannot be read)
    generated_at: str

    @property
    def revision(self) -> int:
        return int(self.state["revision"])

    @property
    def project_id(self) -> str:
        return str(self.manifest["project"]["id"])

    @property
    def project_name(self) -> str:
        return str(self.manifest["project"]["name"])

    @property
    def aew_root(self) -> Path:
        return self.engine.aew_root


def _identity(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


class StateReader:
    """Snapshots of a project's committed state without the control lock. The cached state is shared between
    snapshots taken at the same identity; projections read it and never change it."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._lock = threading.Lock()
        self._state: tuple[tuple[int, int, int] | None, dict[str, Any]] | None = None
        self._manifest: tuple[tuple[int, int, int] | None, dict[str, Any]] | None = None
        # keyed by the gates file's identity and its pin: adopting an edit changes what may be shown
        self._gates: tuple[tuple[tuple[int, int, int] | None, bool, str | None] | None, dict[str, Any]] | None = None

    def snapshot(self) -> Snapshot:
        store = self.engine.store
        with self._lock:
            identity = store.control_identity()
            if self._state is None or self._state[0] != identity:
                self._state = (identity, store.read_committed())
            manifest_path = self.engine.aew_root / MANIFEST
            manifest_identity = _identity(manifest_path)
            if self._manifest is None or self._manifest[0] != manifest_identity:
                self._manifest = (manifest_identity, load_manifest(self.engine.aew_root))
            gates_rel = (self._manifest[1].get("policy") or {}).get("gates")
            gates_path = self.engine.aew_root / str(gates_rel) if gates_rel else None
            pins = self._state[1].get(POLICY_PINS)
            gates_pin = pins.get(str(gates_rel)) if isinstance(pins, dict) else None
            gates_identity = (_identity(gates_path), pins is not None, gates_pin) if gates_path else None
            if self._gates is None or self._gates[0] != gates_identity:
                self._gates = (gates_identity, self._read_gates(gates_path, pins is not None, gates_pin)
                               if gates_path else {})
            return Snapshot(self.engine, self._state[1], self._manifest[1], self._gates[1], utc_now())

    @staticmethod
    def _read_gates(path: Path, pinned: bool, pin: str | None) -> dict[str, Any]:
        """The gates policy as the engine reads it (``Kernel.policy``: as adopted, checked against its pin in the
        committed state), without the engine's locked manifest path; an unreadable, invalid or unadopted policy counts
        as empty, as the audit's own ``_policy`` treats it."""
        try:
            raw = path.read_bytes()
            if pinned and sha256_bytes(raw) != pin:
                return {}
            data = load_yaml(raw.decode("utf-8"), source=str(path))
            validate("gates", data, source=str(path))
        except (AEWError, OSError):
            return {}
        return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------------------------- the maps reader

K = TypeVar("K")
V = TypeVar("V")


class LRU(Generic[K, V]):
    """A bounded LRU: by entries (each of size 1), or by the sizes its values are given."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.used = 0
        self._items: OrderedDict[K, tuple[V, int]] = OrderedDict()

    def get(self, key: K) -> V | None:
        found = self._items.get(key)
        if found is None:
            return None
        self._items.move_to_end(key)
        return found[0]

    def put(self, key: K, value: V, size: int = 1) -> None:
        if size > self.capacity:
            return  # never kept: it would evict everything else
        old = self._items.pop(key, None)
        if old is not None:
            self.used -= old[1]
        self._items[key] = (value, size)
        self.used += size
        while self.used > self.capacity:
            _, (_, gone) = self._items.popitem(last=False)
            self.used -= gone

    def __len__(self) -> int:
        return len(self._items)


REGISTRY_MAX = 64 << 10  # a registry holds two selections: far below this
REGISTRY_ATTEMPTS = 3  # a read that meets the writer's atomic replace (Windows: a sharing violation) tries again
ARTIFACT_NAME = re.compile(r"^([0-9a-f]{64})\.json$")
NONE, PRESENT, INVALID = "NONE", "PRESENT", "INVALID"


@dataclass(frozen=True)
class Registry:
    """One read of the map registry: ``PRESENT`` with its data, ``NONE``, or ``INVALID`` with why (``problem``)."""

    state: str
    data: dict[str, Any] | None = None
    problem: str | None = None

    @property
    def revision(self) -> str | None:
        """``<epoch>:<n>``, ``none:0`` before the first selection, None when the registry is invalid."""
        if self.state == INVALID:
            return None
        return MS.revision_of(self.data)

    def selected(self, capability: str) -> dict[str, Any] | None:
        return ((self.data or {}).get("selected") or {}).get(capability)


class MapsReader:
    """The maps routes' lock-free reader of ``.aew/local/maps/`` (register F20.8; the change note §4.1, §4.2).

    It never takes the map registry's lock and never writes: the registry is replaced atomically under its writer's
    lock, so a read sees one whole registry, before or after a selection. Every file is read bounded and
    type-checked (``maps.store.read_bounded``), and only when its identity changed. Its caches hold inputs that are
    immutable or keyed by everything they depend on, never a response: the registry by its identity, summaries
    (:data:`SUMMARIES` entries) and projected details (:data:`DETAIL_BYTES`, size-aware) by root and file identity,
    and the architecture reference's freshness (:data:`ARCHITECTURE` entries) by evidence, observed commit and head.
    The server builds one projection at a time, which is what serializes this reader."""

    SUMMARIES = 256
    DETAIL_BYTES = 32 << 20
    ARCHITECTURE = 64

    def __init__(self, aew_root: Path) -> None:
        self.aew_root = aew_root
        self._registry: tuple[MS.Identity, Registry] | None = None
        self.summaries: LRU[tuple[str, MS.Identity], dict[str, Any]] = LRU(self.SUMMARIES)
        self.details: LRU[tuple[str, MS.Identity], Any] = LRU(self.DETAIL_BYTES)
        self.architecture: LRU[tuple[str, str | None, str | None], dict[str, Any]] = LRU(self.ARCHITECTURE)

    # ---------------------------------------------------------------- the registry

    def registry(self) -> Registry:
        """The registry as it stands. Its condition is a state, never an error (missing: ``NONE``; oversized, not a
        regular file or malformed: ``INVALID``); only a read that failed raises its ``OSError`` (the server's
        ``500``, which the frontend shows as stale)."""
        path = self.aew_root / MS.REGISTRY_REL
        for attempt in range(REGISTRY_ATTEMPTS):
            try:
                st = MS.lstat_regular(path, REGISTRY_MAX)
                identity = MS.file_identity(st)
                if self._registry is not None and self._registry[0] == identity:
                    return self._registry[1]
                raw, identity = MS.read_bounded(path, REGISTRY_MAX, st)
            except FileNotFoundError:
                return Registry(NONE)
            except MS.NotARegularFile as exc:
                if exc.reason == "not_a_file" and attempt + 1 < REGISTRY_ATTEMPTS and _regular(path):
                    continue  # replaced by the writer between the lstat and the open: read the new one
                return Registry(INVALID, problem=exc.reason)
            except PermissionError:
                if os.name == "nt" and attempt + 1 < REGISTRY_ATTEMPTS:
                    time.sleep(0.02)  # the writer's replace holds the name for a moment (a sharing violation)
                    continue
                raise
            parsed = _parse_registry(raw)
            self._registry = (identity, parsed)
            return parsed
        raise AssertionError("unreachable")

    # ---------------------------------------------------------------- the stored maps

    def roots(self) -> list[str]:
        """The stored maps' roots, sorted, from the directory's names only (nothing is opened)."""
        try:
            with os.scandir(self.aew_root / MS.STRUCTURAL_REL) as entries:
                return sorted(m.group(1) for e in entries if (m := ARTIFACT_NAME.match(e.name)))
        except (FileNotFoundError, NotADirectoryError):
            return []

    def stat(self, root: str) -> os.stat_result:
        """The artifact's ``lstat``: a regular file within the dashboard's bound, or ``MAP_ARTIFACT_CORRUPT``
        (``not_a_file``, ``too_large``); ``NOT_FOUND`` when there is none. Nothing is opened."""
        try:
            return MS.lstat_regular(self.aew_root / MS.artifact_rel(root), MS.MAP_FILE_MAX)
        except FileNotFoundError:
            raise NotFound(f"no stored map {root}", root=root) from None
        except MS.NotARegularFile as exc:
            raise MapArtifactCorrupt(f"the stored map {root} is corrupt ({exc.reason})", root=root,
                                     reason=exc.reason) from None

    def load(self, root: str, st: os.stat_result) -> tuple[dict[str, Any], MS.Identity]:
        """The record, read bounded and checked by the strict reader, with its file's identity."""
        try:
            return MS.read_artifact_bounded(self.aew_root, root, st=st)
        except RecursionError:  # nested past the parser's depth: not a record any generator wrote
            raise MapArtifactCorrupt(f"the stored map {root} is corrupt (not_json)", root=root,
                                     reason="not_json") from None


def _regular(path: Path) -> bool:
    try:
        MS.lstat_regular(path, REGISTRY_MAX)
    except OSError:
        return False
    return True


def _parse_registry(raw: bytes) -> Registry:
    try:
        data = json.loads(raw)
        validate("map-registry", data, source=MS.REGISTRY_REL)
    except (ValueError, ValidationFailed, RecursionError):
        return Registry(INVALID, problem="malformed")
    return Registry(PRESENT, data=data)
