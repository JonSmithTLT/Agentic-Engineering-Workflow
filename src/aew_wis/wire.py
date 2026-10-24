"""The WIS issuer's wire (``wis-issuer-0.5-candidate``), its derivations and its tripwires (WIS-01, WIS-04, WIS-09).

The adopted schema is the arbiter of shape (``tests/fixtures/wis/wis-issuer.schema.json``, its hash pinned); this
module builds what the issuer emits, and owns the derived values every party recomputes the same way:

* ``wis_epoch`` = ``wis-epoch:`` + the first 32 hex characters of the SHA-256 of the canonical anchor record (WIS-04);
* ``proof_ref`` = ``proof:wis:`` + the first 32 hex characters of the SHA-256 of the canonical attestation without
  ``proof_ref`` and ``signature``; the signature is over the canonical attestation without ``signature`` (WIS-04);
* ``key_id`` = the SHA-256 of the public key's DER ``SubjectPublicKeyInfo`` (WIS-09, as G3-09).

Canonical JSON is the engine's (sorted keys, no spaces, UTF-8, no NaN). Times are UTC to the second, ``Z``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from typing import Any

from aew_wis.engine_rules import canonical_json

WIRE = "wis-issuer-0.5-candidate"
# WIS-02's outcomes, and the four that latch the head to CHAIN_FORK until root re-anchors.
OUTCOMES = ("OK", "STORE_REPLACED", "STORE_UNREADABLE", "CHECKSUM_INVALID", "REVISION_GAP", "CHAIN_BROKEN",
            "STATE_MISMATCH", "CHAIN_FORK")
LATCHING = frozenset({"STORE_REPLACED", "CHAIN_BROKEN", "STATE_MISMATCH", "CHAIN_FORK"})
PROBLEMS = {"PEER_NOT_PERMITTED": 403, "NOT_FOUND": 404, "ISSUER_UNAVAILABLE": 503}
ANCHORED, FORKED = "ANCHORED", "CHAIN_FORK"
STORE_REF_PREFIX = "store:"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(s: str) -> datetime:
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError(f"{s!r} is not a UTC time ending in Z")
    return datetime.fromisoformat(s[:-1] + "+00:00")


def epoch_of(anchor: dict[str, Any]) -> str:
    return "wis-epoch:" + sha(canonical_json(anchor))[:32]


def key_id_of(public_der: bytes) -> str:
    return sha(public_der)


def proof_ref_of(attestation: dict[str, Any]) -> str:
    return "proof:wis:" + sha(canonical_json({k: v for k, v in attestation.items()
                                              if k not in ("proof_ref", "signature")}))[:32]


def signed_bytes(attestation: dict[str, Any]) -> bytes:
    """What the signature covers: the canonical attestation without its ``signature``."""
    return canonical_json({k: v for k, v in attestation.items() if k != "signature"})


def problem(code: str) -> dict[str, Any]:
    return {"wire_version": WIRE, "code": code, "status": PROBLEMS[code]}


# ---------------------------------------------------------------------------------------------- tripwires

@dataclass(frozen=True)
class Tripwires:
    """The designer's tripwires, in seconds (WIS-01, WIS-04, WIS-05). A deployment may only shorten each, and must keep
    their order; the issuer refuses to start otherwise, and never clamps one (as G3-14)."""

    read_interval: int = 60  # WIS-01: the issuer reads at least this often
    renew_before: int = 300  # WIS-05: it renews when less than this is left
    validity: int = 900  # WIS-04: valid_until is at most issued_at + this
    view_age: int = 900  # WIS-01: it exits 0 at this age, so its view is set up again from the path
    runtime_max: int = 960  # WIS-01: the unit's RuntimeMaxSec=, the backstop

    def problems(self) -> list[str]:
        """Every value beyond its tripwire, not a whole positive number of seconds, or out of WIS-01's order: read
        interval < renewal margin <= validity, and view age < RuntimeMaxSec=, with the view age no longer than the
        validity. An empty list is a configuration the issuer may run."""
        out = []
        for f in fields(self):
            value, limit = getattr(self, f.name), f.default
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                out.append(f"{f.name} is {value!r}: a whole number of seconds, at least 1, is required")
            elif value > limit:  # type: ignore[operator]
                out.append(f"{f.name} is {value} s, beyond its tripwire of {limit} s: a deployment may only shorten it")
        if out:
            return out
        if not self.read_interval < self.renew_before <= self.validity:
            out.append(f"the read interval ({self.read_interval} s) must be shorter than the renewal margin "
                       f"({self.renew_before} s), and the margin no longer than the validity ({self.validity} s)")
        if not (self.view_age < self.runtime_max and self.view_age <= self.validity):
            out.append(f"the view's age ({self.view_age} s) must be shorter than RuntimeMaxSec= ({self.runtime_max} s) "
                       f"and no longer than the validity ({self.validity} s)")
        return out


# ---------------------------------------------------------------------------------------------- what the issuer emits

def attestation(*, issuer_ref: str, key_id: str, store_ref: str, wis_epoch: str, revision: int, h: str,
                control_sha256: str, issued_at: datetime, validity: int, facts: dict[str, Any]) -> dict[str, Any]:
    """WIS-04: an attestation without ``proof_ref`` and ``signature`` (:func:`seal` adds both)."""
    issued = issued_at.astimezone(UTC).replace(microsecond=0)
    return {"wire_version": WIRE, "issuer_ref": issuer_ref, "key_id": key_id, "store_ref": store_ref,
            "wis_epoch": wis_epoch, "revision": revision, "h": h, "control_sha256": control_sha256,
            "issued_at": iso(issued), "valid_until": iso(issued + timedelta(seconds=validity)), "facts": facts}


def seal(unsigned: dict[str, Any], sign: Any) -> dict[str, Any]:
    """Add ``proof_ref``, then the signature ``sign(bytes) -> hex`` makes over every other field."""
    a = dict(unsigned)
    a["proof_ref"] = proof_ref_of(a)
    a["signature"] = sign(signed_bytes(a))
    return a


def witness_response(a: dict[str, Any], *, current: bool, head: dict[str, Any]) -> dict[str, Any]:
    return {"wire_version": WIRE, "attestation": a, "head": head, "current": current}
