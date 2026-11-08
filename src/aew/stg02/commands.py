"""The O-01 0.2 command carrier: the fixture HEB owner it admits ``CONTINUE_ELIGIBLE_WORK`` to (STG-02), and G3's
consume, which admits a protected member (STG-03).

Written from the adopted profile's CS-01..CS-09 and A-24 SW-04/06/07/08, with the vendored registry, refusal map and
set-level Problem map; the sealed oracle (``03-ORACLE/command_admission.py``) is a cross-check, not the source.

    set level, no owner state and no receipt on failure (an HTTP Problem):
      1. the CommandSet schema; this deployment's installation; the authenticated recipient
      2. CS-01 canonical set; CS-02 one origin class, consent_set_ref iff protected
      3. CS-03/CS-04 the key ledger, inside the write fence: a known key is a lookup, decided in the order
         read entitlement -> missing or corrupt -> changed -> expired -> the stored receipt, exactly as issued
    member level, in request order (CS-05):
      4. ORIGIN first, before any owner state: the current delegated grant (SW-04: issuer and status, then the
         binding to the exact intent, then expiry). A current-successor member has no authenticated session in the
         slice: HELD, ORIGIN_NOT_ESTABLISHED, nothing allocated (addendum 5). A protected G3 member goes by the host's
         standing, then the member's one consume (G3-08; addendum 7, ruling 2): see ``Carrier._protected``
      5. CONTINUE_ELIGIBLE_WORK reaches an owner's state: HEB's own (the fixture world's eligibility and its
         attachment), then at most one effect. HEB's refusal is an allocated operation; a hold allocates nothing
    6. one receipt, one result per intent in request order, stored under the key whatever the outcomes (CS-08)

The continuation vector is never read here: admission checks the grant and HEB's state (C18, never C17).

**HEB's effect is a labelled record, not scheduling.** An admitted continuation is recorded by the fixture HEB as
``EFFECT_CONFIRMED`` with a ``fixture:`` evidence ref; nothing in AEW continues or launches anything (live model and
tool calls are out of the slice's scope). **A protected member the service consumed** is admitted with its operation
and no effect observed: no owner here performs a protected action, and the receipt says only what happened.

**The sealed oracle disagrees here by ruling.** It answers REJECTED for a member with no origin, and this route answers
HELD (addendum 5: the profile and the wire govern; the oracle is a regression aid, not a conformance claim). It stays
this route's cross-check on everything else.
"""

from __future__ import annotations

import copy
import hashlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from aew import g3client as G3
from aew import g3standing as standing
from aew.stg02 import adopted as A
from aew.stg02 import wire as W
from aew.stg02.ledger import Ledger
from aew.stg02.world import DELEGATION_ISSUER, Fixture

LOG = logging.getLogger("aew.stg02")
REGISTRY = A.registry()
ORIGIN_CLASS = {"PROTECTED_G3": "OPERATOR_RESERVED", "CURRENT_DELEGATED_GRANT": "CURRENT_DELEGATED_GRANT",
                "CURRENT_SUCCESSOR_GENERATION": "CURRENT_SUCCESSOR_GENERATION"}
RESULT = {  # outcome -> (admission_state, effect_state, residual_remote_effect), A-24 SW-06
    "EFFECT_CONFIRMED": ("ADMITTED", "EFFECT_CONFIRMED", "NOT_ESTABLISHED"),
    "ADMITTED": ("ADMITTED", "NOT_OBSERVED", "NOT_ESTABLISHED"),  # a consumed protected member: no effect is claimed
    "REFUSED_ALLOCATED": ("REJECTED", "FAILED_CONFIRMED_NO_EFFECT", "NONE_QUALIFIED"),
    "REFUSED": ("REJECTED", "NOT_OBSERVED", "NOT_ESTABLISHED"),
    "HELD": ("HELD", "NOT_OBSERVED", "NOT_ESTABLISHED")}
# What each allocated action's operation is about: the target field that names it, for the owner's list (D-01's
# `subject_ref`). A test holds each to the schema's required string fields.
SUBJECT_FIELD = {"CONTINUE_ELIGIBLE_WORK": "work_ref", "ATTACH_LEAD": "requested_lead_ref",
                 "REATTACH_LEAD": "successor_lead_ref", "CLOSE_ATTACHMENT": "attachment_ref",
                 "SUSPEND_GRANT": "grant_ref", "LIFT_OPERATOR_SUSPENSION": "suspension_ref",
                 "ISSUE_STANDING_POLICY": "policy_decision_ref", "REQUEST_PROFILE_CHANGE": "profile_definition_ref"}
# HEB owner causes for CONTINUE_ELIGIBLE_WORK that the adopted refusal map does not list (it has the three delegation
# causes and NOT_MODELLED only; the oracle leaves the owner check unmodelled). INTERIM, recorded as gap entry
# STG02-BE-01: the map is "complete and fail-closed", so a real owner check needs codes the contract does not give.
SLICE_OWNER_REASONS = {"CONTINUE_ELIGIBLE_WORK": {
    "WORK_NOT_CURRENTLY_ELIGIBLE": "PRECONDITION_STALE",  # A-24 N21's verifier prefix
    "HEB_STALE_PREDECESSOR": "PRECONDITION_STALE",
    "HEB_STATE_UNKNOWN": "SOURCE_UNAVAILABLE"}}


class Refused(Exception):
    """A set-level refusal: the cause names a row of the adopted ``command-set-problems.json``."""

    def __init__(self, cause: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.code = A.set_problems()[cause]["code"]


def refusal(action: str, cause: str, *, allocated: bool = False, held: bool = False) -> dict[str, Any]:
    """``held``: no qualified origin route exists or answers, so the member is held under the same reason (addendum 5:
    the reason code is one, and the origin condition decides the state). No other cause is ever held this way."""
    if held and cause != "ORIGIN_NOT_ESTABLISHED":
        raise AssertionError(f"{action} {cause} is never held for want of an origin")
    reason = A.refusals().get(action, {}).get(cause) or SLICE_OWNER_REASONS.get(action, {}).get(cause)
    if reason is None:  # fail closed: never a default code
        raise AssertionError(f"no reason code for {action} {cause}")
    if held or reason == "SOURCE_UNAVAILABLE":
        return {"outcome": "HELD", "reason_code": reason, "owner_reason": cause}
    return {"outcome": "REFUSED_ALLOCATED" if allocated else "REFUSED", "reason_code": reason, "owner_reason": cause}


class Carrier:
    def __init__(self, fixture: Fixture, ledger: Ledger,
                 policy: Callable[[], dict[str, Any] | None] | None = None) -> None:
        """``policy`` reads the project's execution policy as a launch reads it, through its pin. A carrier started
        with no project has none, so its G3 members are held (addendum 7)."""
        self.fx = fixture
        self.ledger = ledger
        self.policy = policy

    @property
    def receipt_valid_s(self) -> int:
        return int(self.fx.doc["receipt_valid_s"])

    # ------------------------------------------------------------------ the set (steps 1-3, 6)

    def submit(self, req: Any, recipient: str, now: datetime) -> tuple[dict[str, Any], bool]:
        """Admit one command set. Returns ``(receipt, replayed)`` or raises :class:`Refused` (no receipt)."""
        if A.o01_errors("CommandSet", req):
            raise Refused("STRUCTURAL")
        if req["installation_ref"] != self.fx.installation:
            raise Refused("INSTALLATION_NOT_THIS_DEPLOYMENT")
        if req["recipient_ref"] != recipient:
            raise Refused("RECIPIENT_NOT_AUTHENTICATED")
        refs = [i["intent_ref"] for i in req["intents"]]
        if refs != sorted(set(refs)):
            raise Refused("INTENT_ORDER_OR_DUPLICATE")
        if any(i["subject"]["installation_ref"] != req["installation_ref"] for i in req["intents"]):
            raise Refused("MEMBER_INSTALLATION_MISMATCH")
        origins = {REGISTRY[i["action"]]["origin"] for i in req["intents"]}
        if len(origins) != 1:
            raise Refused("MIXED_AUTHORITY_SET_UNSELECTED")
        if origins == {"PROTECTED_G3"} and req["consent_set_ref"] is None:
            raise Refused("PROTECTED_NO_CONSENT_SET")
        if origins != {"PROTECTED_G3"} and req["consent_set_ref"] is not None:
            raise Refused("DELEGATED_CANNOT_MINT_CONSENT_SET")
        with self.ledger.transaction() as t:  # its own transaction: a refusal below must not roll it back
            t.purge(now)
        with self.ledger.transaction() as t:
            old = t.key(req["installation_ref"], recipient, req["client_request_key"])
            if old is not None:  # a lookup (CS-04), never a dispatch
                if not t.entitled(recipient):
                    raise Refused("RECONCILIATION_NOT_ENTITLED")
                if old["receipt"] is None:
                    raise Refused("UNRESOLVED_NO_REDISPATCH")
                if old["full_digest"] != W.full_digest(req):
                    raise Refused("CONFLICT_CHANGED_SET")
                if W.parse_time(old["receipt"]["source_valid_until"]) <= now:
                    raise Refused("UNRESOLVED_NO_REDISPATCH")
                return old["receipt"], True  # exactly as issued (CS-08, v0.5.4)
            # G3's standing once for the request, before its first member, and not again after a CONSUMED (addendum 7).
            # Inside the fence: a known key above is a lookup, which never needs it.
            counts = origins == {"PROTECTED_G3"} and self._g3_counts()
            members = []
            for i in req["intents"]:
                m = self._member(req, i, t, now, counts)
                if m["outcome"] in ("EFFECT_CONFIRMED", "ADMITTED", "REFUSED_ALLOCATED"):
                    m["operation_ref"] = self._allocate(req, i, m, t, now)
                m.update(intent_ref=i["intent_ref"], action=i["action"])
                members.append(m)
            receipt = {"wire_version": W.O01_VERSION, "request_set_ref": req["request_set_ref"],
                       "recipient_ref": req["recipient_ref"], "carrier_state": "COMPLETE_WITH_PER_INTENT_RESULTS",
                       "results": [self._result(i, m, t, now) for i, m in zip(req["intents"], members, strict=True)],
                       "observed_at": W.utc(now), "source_valid_until": W.utc(W.later(now, self.receipt_valid_s))}
            t.store_key(req["installation_ref"], recipient, req["client_request_key"], W.full_digest(req), receipt,
                        members, now)
            return receipt, False

    # ------------------------------------------------------------------ one member (steps 4-5)

    def _member(self, req: dict[str, Any], i: dict[str, Any], t: Any, now: datetime,
                counts: bool = False) -> dict[str, Any]:
        action = i["action"]
        r = REGISTRY[action]
        if i["owner_hint"] != r["sole_admitting_owner"] or i["authority_class"] != ORIGIN_CLASS[r["origin"]]:
            raise AssertionError(f"{action}: the schema accepted an intent the registry disagrees with")
        if r["origin"] == "PROTECTED_G3":
            return self._protected(req, i, r["sole_admitting_owner"], counts)
        if r["origin"] != "CURRENT_DELEGATED_GRANT":
            # No authenticated successor session exists in the slice: no origin, so no owner state is read and nothing
            # is allocated (HELD_UNLESS_QUALIFIED_SUCCESSOR...; addendum 5).
            return refusal(action, "ORIGIN_NOT_ESTABLISHED", held=True)
        e = self._delegation(req, i, now)
        if e:
            return refusal(action, e)
        if action != "CONTINUE_ELIGIBLE_WORK":
            return refusal(action, "NOT_MODELLED")  # DELEGATED_CANCEL: its HEB effect is not in the slice
        return self._heb_continue(i, t)

    def _g3_counts(self) -> bool:
        """G3's standing for this request (addendum 7, ruling 2). The wire has no field for why, so the route's log
        says it: a held note sends the operator here. A carrier started with no project holds its G3 members."""
        if self.policy is None:
            LOG.warning("G3 does not count for this route: it was started with no --project, so no policy says its "
                        "launches run contained")
            return False
        found = standing.standing(self.policy())
        if not found.counts:
            LOG.warning("G3 does not count: %s. Fix: %s", found.reason, found.fix)
        return found.counts

    def _protected(self, req: dict[str, Any], i: dict[str, Any], owner: str, counts: bool) -> dict[str, Any]:
        """A G3-protected member (addendum 7, ruling 2; G3-08), under the request's one standing, ``counts``. A failing
        standing and a service that does not answer are held; a service that answers and refuses the proof presented is
        rejected (addendum 5). Nothing is allocated unless it is consumed."""
        if not counts:
            return refusal(i["action"], "ORIGIN_NOT_ESTABLISHED", held=True)  # consume is not called
        if i["origin_proof_ref"] is None:  # the schema allows it, and the wire does not: no proof to present
            LOG.warning("%s is held: the member has no origin proof to present", i["intent_ref"])
            return refusal(i["action"], "ORIGIN_NOT_ESTABLISHED", held=True)
        got = G3.consume(consent_set_ref=req["consent_set_ref"], set_digest=W.set_digest(req),
                         recipient_ref=req["recipient_ref"], installation_ref=req["installation_ref"],
                         intent_ref=i["intent_ref"], origin_proof_ref=i["origin_proof_ref"], owner=owner,
                         operation_ref=self._operation_ref(req, i, owner))
        if got.result is None:
            LOG.warning("%s is held: %s", i["intent_ref"], got.held_why)  # neither the proof nor the consent is in it
            return refusal(i["action"], "ORIGIN_NOT_ESTABLISHED", held=True)
        if got.result == "CONSUMED":
            return {"outcome": "ADMITTED", "reason_code": None, "owner_reason": None}
        # Each ConsumeResult by name, through the carrier's own table (addendum 7), so the reading of this module sees
        # every cause, and a result no one has named here is the client's to refuse.
        if got.result == "CONSENT_ISSUER_UNVERIFIED":
            return refusal(i["action"], "CONSENT_ISSUER_UNVERIFIED")
        if got.result == "CONSENT_EXPIRED":
            return refusal(i["action"], "CONSENT_EXPIRED")
        if got.result == "CONSENT_SCOPE_MISMATCH":
            return refusal(i["action"], "CONSENT_SCOPE_MISMATCH")
        if got.result == "CONSENT_ALREADY_USED":
            return refusal(i["action"], "CONSENT_ALREADY_USED")
        return refusal(i["action"], "ORIGIN_NOT_ESTABLISHED")  # the service answered: it has no such record (G3-08)

    def _delegation(self, req: dict[str, Any], i: dict[str, Any], now: datetime) -> str | None:
        """A-24 SW-04, in the adopted order: a current proof from the trusted issuer; bound to this exact intent,
        actor, installation and recipient; not expired."""
        proof = self.fx.delegations.get(i["delegated_grant_proof_ref"])
        if proof is None or proof["issuer_ref"] != DELEGATION_ISSUER or proof["status"] != "CURRENT":
            return "DELEGATED_GRANT_UNVERIFIED"
        bound = {"intent_ref": i["intent_ref"], "actor_ref": i["actor_ref"],
                 "installation_ref": req["installation_ref"],
                 "recipient_ref": req["recipient_ref"], "intent_digest": W.intent_digest(i)}
        if any(proof[k] != v for k, v in bound.items()):
            return "DELEGATED_INTENT_NOT_GRANTED"
        if W.parse_time(proof["valid_until"]) <= now:
            return "DELEGATION_EXPIRED"
        return None

    def _heb_continue(self, i: dict[str, Any], t: Any) -> dict[str, Any]:
        """HEB's own state, after the origin: the work it knows, its attachment and generation, its eligibility."""
        tgt, heb = i["target"], self.fx.heb
        w = self.fx.work(tgt["work_ref"])
        if w is None or not w.get("heb_eligibility"):
            return refusal(i["action"], "HEB_STATE_UNKNOWN")
        if ((tgt["work_revision"], i["subject"]["attachment_ref"], i["subject"]["generation_ref"],
             i["predecessor"]["source_epoch"]) != (w["work_revision"], heb["attachment_ref"], heb["generation_ref"],
                                                   heb["epoch"])):
            return refusal(i["action"], "HEB_STALE_PREDECESSOR", allocated=True)
        if not w["heb_eligibility"]["eligible"]:
            return refusal(i["action"], "WORK_NOT_CURRENTLY_ELIGIBLE", allocated=True)
        return {"outcome": "EFFECT_CONFIRMED", "reason_code": None, "owner_reason": None}

    @staticmethod
    def _operation_ref(req: dict[str, Any], i: dict[str, Any], owner: str) -> str:
        """The owner issues the operation's identity: one per (key, set, member), so it is unique (CS-08). A protected
        member's is computed before consume, which records the member against it (G3-08)."""
        return "op:" + hashlib.sha256(W.canonical([owner, req["client_request_key"], W.set_digest(req),
                                                   i["intent_ref"]])).hexdigest()[:32]

    def _allocate(self, req: dict[str, Any], i: dict[str, Any], m: dict[str, Any], t: Any, now: datetime) -> str:
        owner = REGISTRY[i["action"]]["sole_admitting_owner"]
        op = self._operation_ref(req, i, owner)
        h = op.removeprefix("op:")
        a, e, res = RESULT[m["outcome"]]
        record = {"owner": owner, "operation_ref": op, "action": i["action"], "intent_ref": i["intent_ref"],
                  "request_set_ref": req["request_set_ref"], "recipient_ref": req["recipient_ref"],
                  "installation_ref": req["installation_ref"], "consent_set_digest": W.set_digest(req),
                  "intent_digest": W.intent_digest(i), "subject_ref": i["target"][SUBJECT_FIELD[i["action"]]],
                  "attachment_ref": i["subject"]["attachment_ref"],
                  "attachment_generation": i["subject"]["generation_ref"],
                  "issued_at": W.utc(now), "owner_reason": m["owner_reason"],
                  "result": {"intent_ref": i["intent_ref"], "owner": owner, "operation_ref": op, "admission_state": a,
                             "effect_state": e, "cancellation_state": "NONE", "residual_remote_effect": res,
                             "owner_evidence_ref": None if m["outcome"] == "ADMITTED" else "fixture:heb-evidence-" + h,
                             "reason_code": m["reason_code"]}}
        t.add_owner_op(record, now)
        return op

    def _result(self, i: dict[str, Any], m: dict[str, Any], t: Any, now: datetime) -> dict[str, Any]:
        owner = REGISTRY[i["action"]]["sole_admitting_owner"]
        if m.get("operation_ref"):
            return copy.deepcopy(t.owner_op(owner, m["operation_ref"], now)["result"])
        a, e, r = RESULT[m["outcome"]]
        return {"intent_ref": i["intent_ref"], "owner": owner, "operation_ref": None, "admission_state": a,
                "effect_state": e, "cancellation_state": "NONE", "residual_remote_effect": r,
                "owner_evidence_ref": None,
                "reason_code": m["reason_code"]}

    # ------------------------------------------------------------------ the owner's own read (OP-08)

    def owner_get(self, owner: str, operation_ref: str, recipient: str, now: datetime) -> dict[str, Any] | None:
        """HEB's observation of its own record, now. ``None`` for unknown, another recipient's, another
        installation's, or any operation while the recipient's read entitlement is withdrawn: one answer (SW-08)."""
        with self.ledger.reading() as t:
            if not t.entitled(recipient):
                return None
            rec = t.owner_op(owner, operation_ref, now)
        if rec is None or rec["recipient_ref"] != recipient or rec["installation_ref"] != self.fx.installation:
            return None
        return {"wire_version": W.O01_VERSION, "owner": rec["owner"], "operation_ref": rec["operation_ref"],
                "request_set_ref": rec["request_set_ref"], "intent_ref": rec["intent_ref"],
                "recipient_ref": rec["recipient_ref"], "installation_ref": rec["installation_ref"],
                "source_epoch": self.fx.owner_epoch(rec["owner"]), "observed_at": W.utc(now),
                "source_valid_until": W.utc(W.later(now, int(self.fx.doc["owner_observation_valid_s"]))),
                "result": copy.deepcopy(rec["result"])}
