"""Builders for the G3 service's tests (g3/aew_g3, STG-03, A-37).

The command sets come from the regression aid A-37 keeps binding for G3-02 to G3-08 (A-26's ``g3-cases.json``,
vendored byte-exact and pinned here): its P1 is a real adopted ``ATTACH_LEAD`` request. Every PIN is a labelled
stand-in.
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aew_g3 import deployment, pinstore, wire
from aew_g3.keys import KeyStore
from aew_g3.ledger import Ledger
from aew_g3.service import G3Service

REPO = Path(__file__).resolve().parents[2]
CASES_FILE = REPO / "tests" / "fixtures" / "g3" / "g3-cases.json"
CASES_SHA256 = "39344cc74e2e6bbf2cc7935b0681476e4e022c1648255558c48b871ba576cb01"  # A-26's frozen SHA256SUMS
SHIPPED_DEPLOYMENT = REPO / "g3" / "etc" / "deployment.json"
PIN = "stand-in-pin-482913"  # a LABELLED STAND-IN for the operator's PIN, the regression aid's own
ISSUER = "g3:host:" + "a" * 32


def cases() -> dict[str, Any]:
    raw = CASES_FILE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CASES_SHA256, "the vendored g3-cases.json changed"
    return json.loads(raw.decode("utf-8"))["cases"]


P1 = cases()["P1"]
T0 = datetime.fromisoformat(P1["consent_record"]["valid_from"].replace("Z", "+00:00"))
_FACT_LINE = next(ln for ln in P1["pending"]["rendering"] if ln["source"]["kind"] == "OWNER_FACT")
# The fact the regression aid's reference service read from HEB for P1 (G3-03 source 3, optional under A-37).
P1_FACTS = {"HEB": {"owner": "HEB", **{k: _FACT_LINE["source"][k] for k in ("fact_ref", "observed_at",
                                                                         "observation_state")},
                    "values": _FACT_LINE["values"]}}


def base_set() -> dict[str, Any]:
    return copy.deepcopy(P1["approval_request"]["command_set"])


def fresh_proofs(cs: dict[str, Any]) -> dict[str, Any]:
    """The client's part (G3-02): a fresh proof per member, from a cryptographically secure source."""
    cs = copy.deepcopy(cs)
    for i in cs["intents"]:
        i["origin_proof_ref"] = "proof:" + secrets.token_hex(16)
    return cs


def request_body(cs: dict[str, Any]) -> dict[str, Any]:
    return {"wire_version": wire.WIRE, "command_set": cs}


def shipped_values(**over: int) -> dict[str, int]:
    return dict(json.loads(SHIPPED_DEPLOYMENT.read_bytes()), **over)


@dataclass
class Clock:
    now: datetime = T0
    broken: bool = False

    def __call__(self) -> datetime:
        if self.broken:
            raise OSError("the clock cannot be read")  # G3-11's case, planted
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@dataclass
class Rig:
    state: Path
    clock: Clock
    svc: G3Service
    dep: deployment.Deployment
    facts: dict[str, Any] = field(default_factory=dict)

    def restart(self, **over: int) -> Rig:
        """A new service over the same state: what a restart keeps is what the ledger and the state directory hold."""
        self.svc.ledger.close()
        return make(self.state, clock=self.clock, facts=self.facts, set_pin=False, **over)


def make(state: Path, *, clock: Clock | None = None, facts: dict[str, Any] | None = None, set_pin: bool = True,
         **over: int) -> Rig:
    state.mkdir(parents=True, exist_ok=True)
    values = shipped_values(**over)
    assert not deployment.deployment_errors(values), values
    dep = deployment.Deployment(**values)
    if set_pin:
        pinstore.set_pin(state, PIN, dep)
    clock = clock or Clock()
    svc = G3Service(dep, state, Ledger(state), KeyStore(state), issuer_ref=ISSUER, clock=clock, facts=facts)
    return Rig(state, clock, svc, dep, facts or {})


def approved(svc: G3Service, cs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    status, pending = svc.request(request_body(cs))
    assert status == 201, pending
    assert isinstance(pending, dict)
    status, listed = svc.list_pending()
    assert status == 200 and any(p["approval_ref"] == pending["approval_ref"] for p in listed or [])  # type: ignore[union-attr]
    status, record = svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": PIN})
    assert status == 200, record
    assert isinstance(record, dict)
    return pending, record


def consume_req(cs: dict[str, Any], record: dict[str, Any], intent_ref: str | None = None,
                **over: Any) -> dict[str, Any]:
    """What an owner sends at allocation (G3-08): the digest of the set IT received, and the member's own proof."""
    sub = dict(copy.deepcopy(cs), consent_set_ref=record["consent_set_ref"])
    ref = intent_ref or sub["intents"][0]["intent_ref"]
    member = next(i for i in sub["intents"] if i["intent_ref"] == ref)
    body = {"wire_version": wire.WIRE, "consent_set_ref": record["consent_set_ref"], "intent_ref": ref,
            "origin_proof_ref": member["origin_proof_ref"], "set_digest": wire.set_digest(sub),
            "recipient_ref": sub["recipient_ref"], "installation_ref": sub["installation_ref"],
            "owner": wire.registry()[member["action"]]["sole_admitting_owner"],
            "operation_ref": "op:heb:" + ref.split(":")[-1]}
    body.update(over)
    return body


def code(reply: tuple[int, Any]) -> str | None:
    """The Problem code of a refusal, or the ConsumeResult's result."""
    body = reply[1]
    if isinstance(body, dict):
        return body.get("code") or body.get("result")
    return None
