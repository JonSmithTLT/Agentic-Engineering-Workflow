"""The G3 service's rules (G3-02 to G3-08, G3-11), apart from its sockets: each route is a method that returns the
HTTP status and the wire body.

Every route runs under one lock, so the in-memory pending approvals and the ledger move together, and each member is
consumed at most once under concurrent calls too (G3-08; the ledger's primary key backs it). The clock, the ledger and
the PIN record are read at use: when any of them fails, the route answers ``G3_UNAVAILABLE`` and nothing is approved or
consumed (G3-11).
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import re
import secrets
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import pinstore, render, wire
from .deployment import Deployment
from .keys import KeyStore
from .ledger import Ledger, LedgerUnavailable

Reply = tuple[int, dict[str, Any] | list[dict[str, Any]] | None]
PROOF = re.compile(r"^proof:[0-9a-f]{32,64}$")  # G3-02; the wire's Proof pattern (tests/unit/test_g3_wire.py)
# issuer_ref (G3-06's `g3:<host-installation>`; the designer's ruling, hand-off addendum 2 §2, 2026-10-25): G3's
# app-specific machine id, derived as systemd's sd_id128_get_machine_app_specific does, so the raw machine id never
# leaves the host in a record. The application id is G3's, fixed and public.
ISSUER_APP_ID = bytes.fromhex("8799075224ae4f699e730c18f9133411")
# Addendum 3: the wire's issuer_ref pattern needs a letter after `g3:`, and a hex id starts with a digit 10 times in 16.
ISSUER_PREFIX = "g3:host:"
_MACHINE_ID = re.compile(r"^[0-9a-f]{32}$")


def app_specific_id(machine_id: str, app_id: bytes = ISSUER_APP_ID) -> str:
    """sd_id128_get_machine_app_specific: HMAC-SHA256 keyed by the machine id's 16 bytes over the application id,
    the first 16 bytes, with the UUID version 4 and variant bits set. A malformed machine id raises ValueError."""
    text = machine_id.strip()
    if not _MACHINE_ID.match(text) or text == "0" * 32:
        raise ValueError("not a machine id")
    b = bytearray(hmac.new(bytes.fromhex(text), app_id, hashlib.sha256).digest()[:16])
    b[6] = (b[6] & 0x0F) | 0x40
    b[8] = (b[8] & 0x3F) | 0x80
    return b.hex()


def issuer_ref_from_machine_id(machine_id: str) -> str:
    return ISSUER_PREFIX + app_specific_id(machine_id)


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


class _Unavailable(Exception):
    """A dependency G3-11 names failed: answered as ``G3_UNAVAILABLE``."""


@dataclass
class _Pending:
    body: dict[str, Any]
    command_set: dict[str, Any]


class G3Service:
    def __init__(self, deployment: Deployment, state_dir: Path, ledger: Ledger, keys: KeyStore, *, issuer_ref: str,
                 clock: Callable[[], datetime] = utcnow,
                 facts: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self.deployment = deployment
        self.state_dir = state_dir
        self.ledger = ledger
        self.keys = keys
        self.issuer_ref = issuer_ref
        self.clock = clock
        # G3-03 source 3 is optional (A-37): the service reads no owner facts, so this stays empty outside the
        # regression aid's own case, which plants the fact its reference service read.
        self.facts: Mapping[str, Mapping[str, Any]] = facts or {}
        self.registry = wire.registry()
        self.pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------------------------------ plumbing
    def _now(self) -> datetime:
        try:
            now = self.clock()
        except Exception as e:
            raise _Unavailable("clock") from e
        if now.tzinfo is None:
            raise _Unavailable("clock")
        return now

    def _guarded(self, fn: Callable[[], Reply]) -> Reply:
        with self._lock:
            try:
                return fn()
            except (_Unavailable, LedgerUnavailable, pinstore.PinUnavailable):
                return wire.problem("G3_UNAVAILABLE")

    def _state(self, p: _Pending, now: datetime) -> str:
        if p.body["state"] == "PENDING" and now >= _parse(p.body["expires_at"]):
            p.body["state"] = "EXPIRED"
        return p.body["state"]

    # ------------------------------------------------------------------------------------------ request.sock
    def request(self, body: Any, *, lines: list[dict[str, Any]] | None = None) -> Reply:
        """``POST /g3/v1/approval-requests`` (G3-02, G3-03). ``lines`` stands in for the service's own rendering in
        the planted cases of G3-03's refusals; the socket server never passes it."""
        return self._guarded(lambda: self._request(body, lines))

    def _request(self, body: Any, lines: list[dict[str, Any]] | None) -> Reply:
        if wire.wire_errors("ApprovalRequest", body):
            return wire.problem("STRUCTURAL")
        cs = body["command_set"]
        if wire.o01_errors(cs) or cs.get("consent_set_ref") is not None:
            return wire.problem("STRUCTURAL")
        if {self.registry.get(i["action"], {}).get("origin") for i in cs["intents"]} != {wire.PROTECTED}:
            return wire.problem("MIXED_AUTHORITY_SET_UNSELECTED")
        proofs = [i.get("origin_proof_ref") for i in cs["intents"]]
        if (any(not isinstance(p, str) or not PROOF.match(p) for p in proofs) or len(set(proofs)) != len(proofs)
                or self.ledger.any_seen(proofs)):
            return wire.problem("MEMBER_PROOF_INVALID")
        now = self._now()
        rendering = render.render(cs, self.registry, self.facts) if lines is None else lines
        if not render.derived(cs, rendering, self.facts):
            return wire.problem("RENDERING_UNDERIVED")
        if not render.complete(cs, rendering):
            return wire.problem("RENDERING_INCOMPLETE")
        ref = "g3:approval:" + secrets.token_hex(16)
        pending = {"wire_version": wire.WIRE, "approval_ref": ref, "state": "PENDING",
                   "set_digest": wire.set_digest(cs), "rendering": rendering,
                   "rendering_digest": hashlib.sha256(wire.canonical(rendering)).hexdigest(),
                   "expires_at": iso(now + timedelta(minutes=self.deployment.approval_expiry_minutes))}
        if wire.wire_errors("PendingApproval", pending):  # R2-1 makes this unreachable; the service checks itself
            raise _Unavailable("the service built a PendingApproval the wire cannot carry")
        if not self.ledger.accept_proofs(proofs):  # durable before the reply, and the key decides (G3-02 step 3, R2-5)
            return wire.problem("MEMBER_PROOF_INVALID")
        self.pending[ref] = _Pending(pending, copy.deepcopy(cs))
        return 201, copy.deepcopy(pending)

    def get(self, approval_ref: str) -> Reply:
        """``GET /g3/v1/approval-requests/{approval_ref}`` (G3-07): the approval, with its record once approved."""
        return self._guarded(lambda: self._get(approval_ref))

    def _get(self, approval_ref: str) -> Reply:
        p = self.pending.get(approval_ref)
        if p is not None and p.body["state"] != "APPROVED":
            self._state(p, self._now())
            return 200, copy.deepcopy(p.body)
        stored = self.ledger.approval(approval_ref)  # an approved one outlives a restart with its record
        if stored is None:
            return wire.problem("NOT_FOUND")
        return 200, stored

    def consume(self, body: Any) -> Reply:
        """``POST /g3/v1/consume`` (G3-08): checked in order, the first failure returned; else consumed once."""
        return self._guarded(lambda: self._consume(body))

    def _consume(self, req: Any) -> Reply:
        if wire.wire_errors("ConsumeRequest", req):
            return wire.problem("STRUCTURAL")
        now = self._now()

        def out(result: str) -> Reply:
            res: dict[str, Any] = {"wire_version": wire.WIRE, "result": result}
            if result == "CONSUMED":
                res["consumed_at"] = iso(now)
            return 200, res

        found = self.ledger.record(req["consent_set_ref"])
        if found is None:
            return out("ORIGIN_NOT_ESTABLISHED")
        r, approved_set = found
        intent_refs: list[Any] = r.get("intent_refs") or []
        if (wire.wire_errors("ConsentRecord", r) or r["issuer_ref"] != self.issuer_ref or not self.keys.verifies(r)
                or set(r["member_proofs"]) != set(intent_refs) or len(set(intent_refs)) != len(intent_refs)):
            return out("CONSENT_ISSUER_UNVERIFIED")  # 1. genuine: issued here, under the current key, well formed
        if not _parse(r["valid_from"]) <= now < _parse(r["valid_until"]):
            return out("CONSENT_EXPIRED")  # 2. current
        member = next((i for i in approved_set["intents"] if i["intent_ref"] == req["intent_ref"]), None)
        if (req["set_digest"] != r["set_digest"] or req["recipient_ref"] != r["recipient_ref"]
                or req["installation_ref"] != r["installation_ref"] or req["intent_ref"] not in intent_refs
                or r["member_proofs"].get(req["intent_ref"]) != req["origin_proof_ref"] or member is None
                or req["owner"] != self.registry.get(member["action"], {}).get("sole_admitting_owner")):
            return out("CONSENT_SCOPE_MISMATCH")  # 3. the request matches the record and the approved set
        if not self.ledger.consume(r["consent_set_ref"], req["intent_ref"], req["owner"], req["operation_ref"],
                                   iso(now)):
            return out("CONSENT_ALREADY_USED")  # 4. not yet consumed; flushed before the reply when it is
        return out("CONSUMED")

    # ------------------------------------------------------------------------------------------ confirm.sock
    def list_pending(self) -> Reply:
        """``GET /g3/v1/pending``: the open approvals, for the confirmer."""
        return self._guarded(self._list_pending)

    def _list_pending(self) -> Reply:
        now = self._now()
        return 200, [copy.deepcopy(p.body) for p in self.pending.values() if self._state(p, now) == "PENDING"]

    def decide(self, approval_ref: str, body: Any) -> Reply:
        """``POST /g3/v1/approvals/{approval_ref}`` (G3-05, G3-06): approve with the PIN, or decline."""
        return self._guarded(lambda: self._decide(approval_ref, body))

    def _decide(self, approval_ref: str, decision: Any) -> Reply:
        if wire.wire_errors("ApprovalDecision", decision):
            return wire.problem("STRUCTURAL")
        p = self.pending.get(approval_ref)
        # The designer's ruling (hand-off addendum 2 §1): an approval already approved or declined is no longer pending,
        # so it is NOT_FOUND, before expiry and before the PIN, outside the lockout count; a retried approval after a
        # lost response fetches the record with GET instead.
        if p is None or p.body["state"] in ("APPROVED", "DECLINED"):
            return wire.problem("NOT_FOUND")
        if self._state(p, self._now()) == "EXPIRED":
            return wire.problem("APPROVAL_EXPIRED")
        if decision["decision"] == "DECLINE":
            p.body["state"] = "DECLINED"  # needs no PIN, and yields no record (G3-05)
            return 204, None
        pin = pinstore.read(self.state_dir)
        if pin.min_length < self.deployment.pin_min_length or self.ledger.failures(pin.pin_id) >= \
                self.deployment.lockout_after:
            return wire.problem("PIN_LOCKED")  # a raised minimum, or the lockout, until root sets the PIN again
        if not pin.matches(decision["pin"]):
            self.ledger.record_failure(pin.pin_id)
            return wire.problem("PIN_INCORRECT")
        now = self._now()
        cs = p.command_set
        record: dict[str, Any] = {
            "consent_set_ref": "consent:g3:" + secrets.token_hex(16), "issuer_ref": self.issuer_ref,
            "qualified": True,  # a claim only (G3-13); the adopted owner model reads it, origin is G3-08 under G3-12
            "set_digest": p.body["set_digest"], "rendering_digest": p.body["rendering_digest"],
            "recipient_ref": cs["recipient_ref"], "installation_ref": cs["installation_ref"],
            "intent_refs": [i["intent_ref"] for i in cs["intents"]],
            "member_proofs": {i["intent_ref"]: i["origin_proof_ref"] for i in cs["intents"]},  # the client's own
            "valid_from": iso(now),
            "valid_until": iso(now + timedelta(minutes=self.deployment.consent_validity_minutes)),
            "approval_ref": approval_ref, "issued_at": iso(now), "key_id": self.keys.key_id}
        record["signature"] = self.keys.sign(record)
        approved = dict(copy.deepcopy(p.body), state="APPROVED", consent_record=record)
        if wire.wire_errors("ConsentRecord", record) or wire.wire_errors("PendingApproval", approved):
            raise _Unavailable("the service built a record the wire cannot carry")
        self.ledger.store_approval(record, cs, approved, pin.pin_id)  # durable before anything changes here
        p.body = approved
        return 200, copy.deepcopy(record)
