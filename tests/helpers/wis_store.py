"""Scratch stores for the work-item fact issuer's tests (STG-04 WIS-A), made by the real engine.

Every store here is created and committed to by ``aew.engine.store.ControlStore``, and compacted by
``aew.engine.log_compact``: the issuer reads the bytes the engine writes, never a hand-built stand-in (the adopted
reference model's control file is canonical JSON with another checksum rule; WIS-A finding F-3). Tampering is done
afterwards, on the scratch store's files, as the gate's WIS-Q04 does by hand.

``View`` stands in for the kernel's answers about the bound directory (its identity and its bind's root field), which
a test changes to make the store look renamed, deleted or replaced; on Linux the real ones are tested apart
(``identity.view_identity`` in a bubblewrap bind). ``HmacKey`` is the reference model's labelled stand-in for the key,
used only to show that the issuer derives ``proof_ref`` and the signature by the reference's rules byte for byte.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store_model import init  # noqa: E402

from aew.engine.store import ControlStore, Transition  # noqa: E402
from aew_wis import wire as W  # noqa: E402
from aew_wis.identity import Identity  # noqa: E402
from aew_wis.issuer import Issuer  # noqa: E402

INSTANCE = "0123456789abcdef0123456789abcdef"
OTHER = "fedcba9876543210fedcba9876543210"
T0 = datetime(2026, 10, 18, 13, 0, 0, tzinfo=UTC)  # the adopted world's clock, as the reference runs on it
FS_PATH = "/operator/project-one/.aew/state"
IDENTITY = Identity("uuid:6a1f9c3e-0b2d-4e57-9a88-1c2d3e4f5a6b", 7001, 1_700_000_000_000_000_001, FS_PATH)
OPERATOR = 1000


def unit(state: str, *, plan: int | None = 1, blocked_by: list[dict[str, Any]] | None = None,
         kind: str = "ticket") -> dict[str, Any]:
    """A work unit the control schema accepts, with the fields the WIS fact rule reads."""
    u: dict[str, Any] = {"kind": kind, "title": "a unit", "record": "work/T/ticket.md", "record_sha256": "0" * 64,
                         "state": state, "risk_class": 0, "mutating": False, "depends_on": []}
    if plan is not None:
        u["plan"] = {"accepted": plan, "sha256": "1" * 64}
    if blocked_by is not None:
        u["blocked_by"] = blocked_by
    return u


WORK = {"ticket:one": unit("READY", plan=1),
        "ticket:two": unit("BLOCKED", plan=2, blocked_by=[{"kind": "dependency", "id": "ticket:one",
                                                            "reason": "not_done (READY)"}])}


def commit(store: ControlStore, work: dict[str, Any] | None = None) -> int:
    """One engine commit that sets the work units (or leaves them)."""
    with store.session() as s:
        if work is not None:
            s.state["work"] = copy.deepcopy(work)
        s.state["counters"]["n"] = s.state["counters"]["n"] + 1
        return s.commit(Transition(op="wis.test", actor={"kind": "test"}))


def scratch(root: Path, commits: int = 1, work: dict[str, Any] | None = None) -> ControlStore:
    """A store created by the engine (revision 0 seals its own record) with ``commits`` commits setting ``work``."""
    store = init(root)
    for _ in range(commits):
        commit(store, WORK if work is None else work)
    return store


@dataclass
class View:
    root: Path
    identity: Identity = IDENTITY
    owner: int = OPERATOR
    unavailable: bool = False
    probes: list[datetime] = field(default_factory=list)

    def probe(self) -> tuple[Identity, int]:
        from aew_wis.identity import IdentityUnavailable

        if self.unavailable:
            raise IdentityUnavailable("the mount table cannot be read (test)")
        return self.identity, self.owner


class HmacKey:
    """The reference model's labelled stand-in (``verify_wis.py``: ``KEY``, HMAC-SHA256, the "public key" is the
    key). Only for the derivation check; the issuer's real keys are in ``aew_wis.keys``."""

    def __init__(self, key: bytes = b"stand-in-wis-issuer-key") -> None:
        self.key = key
        self.key_id = hashlib.sha256(key).hexdigest()
        self.public_der = key

    def sign(self, data: bytes) -> str:
        return hmac.new(self.key, data, hashlib.sha256).hexdigest()


def anchor_of(store: ControlStore, identity: Identity = IDENTITY, *, at: datetime = T0 - timedelta(days=1),
              instance: str = INSTANCE) -> dict[str, Any]:
    """What root writes at the console (WIS-11), for the store's current head."""
    state = store.read()
    return {"store_ref": "store:" + instance, **identity.as_anchor_fields(), "revision": state["revision"],
            "h": state["last_transition"]["h"], "anchored_at": W.iso(at)}


def issuer(store: ControlStore, state_dir: Path, *, view: View | None = None, anchor: dict[str, Any] | None = None,
           signer: Any = None, tripwires: W.Tripwires | None = None, instance: str = INSTANCE) -> Issuer:
    state_dir.mkdir(parents=True, exist_ok=True)
    view = view or View(store.root)
    return Issuer(instance=instance, anchor=anchor or anchor_of(store, view.identity, instance=instance), view=view,
                  state_dir=state_dir, signer=signer or HmacKey(), tripwires=tripwires or W.Tripwires())
