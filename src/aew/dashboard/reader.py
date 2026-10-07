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

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.engine.api import Engine
from aew.engine.base import POLICY_PINS
from aew.errors import AEWError
from aew.knowledge.manifest import MANIFEST, load_manifest
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
        self._gates: tuple[tuple[int, int, int] | None, dict[str, Any]] | None = None

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
