"""The G3 service's rules, in process (A-37 G3-02 to G3-08 and G3-11; STG-03, G3-A).

Each case of the regression aid A-37 keeps binding (A-26 ``verify_g3.py``: P1, P2, N01 to N11 and N14 to N19, apart from
N12's and N13's identity and qualification checks, which A-37 cuts) runs here against the real service: its real P-256
key, its SQLite ledger, its scrypt PIN. The sockets, the real process and its restarts are in
``tests/integration/test_g3_process.py``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from aew_g3 import COMMAND, pinstore, render, wire
from aew_g3.keys import KeyStore, rotate
from aew_g3.ledger import Ledger, LedgerUnavailable
from tests.helpers import g3 as G

ACCEPTED = (200, 201, 204)


def _valid(ref: str, body: Any) -> bool:
    return not wire.wire_errors(ref, body)


# ------------------------------------------------------------------------------------------------ P1 and P2
def test_p1_the_service_renders_issues_and_consumes_the_regression_aids_case_byte_for_byte(tmp_path: Path) -> None:
    rig = G.make(tmp_path, facts=G.P1_FACTS)
    status, pending = rig.svc.request(G.P1["approval_request"])
    assert status == 201 and _valid("PendingApproval", pending)
    for k in ("set_digest", "rendering", "rendering_digest", "expires_at", "state", "wire_version"):
        assert pending[k] == G.P1["pending"][k], k
    status, record = rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})
    assert status == 200 and _valid("ConsentRecord", record)
    # The record's own refs, issuer, key and signature are this service's; every bound value is the case's.
    for k in ("set_digest", "rendering_digest", "recipient_ref", "installation_ref", "intent_refs", "member_proofs",
              "valid_from", "valid_until", "issued_at", "qualified"):
        assert record[k] == G.P1["consent_record"][k], k
    assert record["approval_ref"] == pending["approval_ref"] and record["key_id"] == rig.svc.keys.key_id
    # G3-07's invariant: the approved digest is the SW-02 digest of the exact set the owner receives.
    submitted = dict(G.P1["submitted_command_set"], consent_set_ref=record["consent_set_ref"])
    assert not wire.o01_errors(submitted) and wire.set_digest(submitted) == record["set_digest"]
    req = dict(G.P1["consume_request"], consent_set_ref=record["consent_set_ref"])
    assert rig.svc.consume(req) == (200, G.P1["consume_result"])


def test_p1_without_an_owner_fact_renders_the_cases_lines_less_the_optional_fact(tmp_path: Path) -> None:
    """A-37 makes G3-03's consequence fact optional, and the service reads none."""
    rig = G.make(tmp_path)
    status, pending = rig.svc.request(G.P1["approval_request"])
    assert status == 201
    assert pending["rendering"] == [ln for ln in G.P1["pending"]["rendering"] if ln["source"]["kind"] != "OWNER_FACT"]
    assert pending["rendering_digest"] == hashlib.sha256(wire.canonical(pending["rendering"])).hexdigest()


def test_p2_two_members_under_one_approval_are_each_consumed_once_and_never_for_each_other(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    two = G.fresh_proofs(G.base_set())
    two["intents"].append(dict(copy.deepcopy(two["intents"][0]), intent_ref="intent:zz-second",
                               origin_proof_ref="proof:" + "b" * 32))
    pending, record = G.approved(rig.svc, two)
    assert render.complete(two, pending["rendering"])
    assert set(record["member_proofs"]) == {"intent:attach_lead", "intent:zz-second"}
    swapped = G.consume_req(two, record, intent_ref="intent:zz-second",
                            origin_proof_ref=record["member_proofs"]["intent:attach_lead"])
    assert G.code(rig.svc.consume(swapped)) == "CONSENT_SCOPE_MISMATCH"
    assert G.code(rig.svc.consume(G.consume_req(two, record))) == "CONSUMED"
    assert G.code(rig.svc.consume(G.consume_req(two, record, intent_ref="intent:zz-second"))) == "CONSUMED"
    assert G.code(rig.svc.consume(G.consume_req(two, record, intent_ref="intent:zz-second"))) == "CONSENT_ALREADY_USED"


# ------------------------------------------------------------------------------------------------ G3-08 consume
def test_n01_a_member_is_consumed_once_then_consent_already_used(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    first = rig.svc.consume(G.consume_req(cs, record))
    assert G.code(first) == "CONSUMED" and _valid("ConsumeResult", first[1])
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_ALREADY_USED"


@pytest.mark.parametrize(("label", "edit"), [
    ("N03 the command changed after approval",
     lambda cs, rec: G.consume_req(dict(cs, intents=[dict(cs["intents"][0], target=dict(
         cs["intents"][0]["target"], requested_lead_ref="lead:other"))]), rec)),
    ("N04 another member proof", lambda cs, rec: G.consume_req(cs, rec, origin_proof_ref="proof:" + "0" * 32)),
    ("N05 another recipient", lambda cs, rec: G.consume_req(cs, rec, recipient_ref="recipient:other")),
    ("another installation", lambda cs, rec: G.consume_req(cs, rec, installation_ref="installation:other")),
    ("a member not in the record", lambda cs, rec: dict(G.consume_req(cs, rec), intent_ref="intent:x")),
    ("N17 an owner that is not the member's sole admitting owner", lambda cs, rec: G.consume_req(cs, rec, owner="ADC")),
])
def test_a_consume_that_does_not_match_the_record_is_scope_mismatch_and_consumes_nothing(tmp_path: Path, label: str,
                                                                                         edit: Any) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    assert G.code(rig.svc.consume(edit(cs, record))) == "CONSENT_SCOPE_MISMATCH", label
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSUMED", "the refused call consumed the member"


def test_n02_consent_validity_is_current_until_valid_until_and_expired_at_it(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    two = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    _, record2 = G.approved(rig.svc, two)  # both issued at T0, valid until T0 + 15 minutes
    rig.clock.advance(minutes=15, seconds=-1)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSUMED"  # one second inside the 15 minutes
    rig.clock.advance(seconds=1)
    assert rig.clock.now.strftime("%Y-%m-%dT%H:%M:%SZ") == record2["valid_until"]
    assert G.code(rig.svc.consume(G.consume_req(two, record2))) == "CONSENT_EXPIRED"  # exactly at valid_until


def test_a_record_issued_after_a_valid_from_in_the_future_is_not_yet_current(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    rig.clock.advance(seconds=-1)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_EXPIRED"


def _store(rig: G.Rig, record: dict[str, Any]) -> None:
    """Plants a record in the ledger as if the service had issued it (a forgery, or an issuer bug)."""
    db = rig.svc.ledger._db
    db.execute("UPDATE records SET record = ? WHERE consent_set_ref = ?",
               (json.dumps(record), record["consent_set_ref"]))


def test_n06_a_record_signed_by_another_key_or_edited_after_signing_is_issuer_unverified(tmp_path: Path) -> None:
    rig = G.make(tmp_path / "svc")
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    (tmp_path / "other").mkdir()
    other = KeyStore(tmp_path / "other")
    forged = dict(record, key_id=other.key_id)
    forged["signature"] = other.sign({k: v for k, v in forged.items() if k != "signature"})
    _store(rig, forged)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_ISSUER_UNVERIFIED"
    tampered = dict(record, valid_until=G.T0.replace(year=2027).strftime("%Y-%m-%dT%H:%M:%SZ"))
    _store(rig, tampered)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_ISSUER_UNVERIFIED"
    _store(rig, record)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSUMED", "control: the genuine record"


def test_a_record_naming_another_issuer_is_issuer_unverified(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    other = dict(record, issuer_ref="g3:host:" + "b" * 32)
    other["signature"] = rig.svc.keys.sign({k: v for k, v in other.items() if k != "signature"})
    _store(rig, other)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_ISSUER_UNVERIFIED"


def test_n07_after_a_key_rotation_a_record_under_the_retired_key_is_not_consumable(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    old, new = rotate(tmp_path)
    assert old == record["key_id"] and new != old
    rig2 = rig.restart()
    assert rig2.svc.keys.key_id == new and old in rig2.svc.keys.public_pems()  # still published for audit (G3-09)
    assert G.code(rig2.svc.consume(G.consume_req(cs, record))) == "CONSENT_ISSUER_UNVERIFIED"


def test_n18_a_signed_record_whose_member_proofs_keys_differ_from_intent_refs_is_issuer_unverified(
        tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    bad = dict(record, member_proofs=dict(record["member_proofs"], **{"intent:extra": "proof:" + "a" * 32}))
    bad["signature"] = rig.svc.keys.sign({k: v for k, v in bad.items() if k != "signature"})
    _store(rig, bad)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_ISSUER_UNVERIFIED"


def test_g3_08_checks_in_order_and_returns_the_first_failure(tmp_path: Path) -> None:
    """An expired record from another key is ISSUER_UNVERIFIED (1 before 2); an expired one with the wrong digest
    is EXPIRED (2 before 3); a consumed one with the wrong digest is SCOPE_MISMATCH (3 before 4)."""
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSUMED"
    assert G.code(rig.svc.consume(G.consume_req(cs, record, set_digest="0" * 64))) == "CONSENT_SCOPE_MISMATCH"
    rig.clock.advance(minutes=16)
    assert G.code(rig.svc.consume(G.consume_req(cs, record, set_digest="0" * 64))) == "CONSENT_EXPIRED"
    _store(rig, dict(record, key_id="f" * 64))
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSENT_ISSUER_UNVERIFIED"


def test_n08_a_declined_approval_issues_no_record_and_an_unknown_consent_is_origin_not_established(
        tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, pending = rig.svc.request(G.request_body(cs))
    assert rig.svc.decide(pending["approval_ref"], {"decision": "DECLINE"}) == (204, None)
    assert rig.svc.ledger.approval(pending["approval_ref"]) is None
    status, got = rig.svc.get(pending["approval_ref"])
    assert status == 200 and got["state"] == "DECLINED"
    assert G.code(rig.svc.consume(G.consume_req(cs, {"consent_set_ref": "consent:none"}))) == "ORIGIN_NOT_ESTABLISHED"


def test_each_member_is_consumed_at_most_once_under_concurrent_calls(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    req = G.consume_req(cs, record)
    results: list[str | None] = []
    gate = threading.Barrier(16)

    def go() -> None:
        gate.wait()
        results.append(G.code(rig.svc.consume(dict(req))))

    threads = [threading.Thread(target=go) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(results) == ["CONSENT_ALREADY_USED"] * 15 + ["CONSUMED"]


# ------------------------------------------------------------------------------------------------ G3-02 request
def test_n14_a_set_mixing_protected_and_other_actions_is_mixed_authority_set_unselected(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    first = cs["intents"][0]
    # A delegated-grant member, in the shape STG-02's world makes (aew.stg02.world.Fixture.intent).
    cont = {"intent_ref": "intent:zz-continue", "action": "CONTINUE_ELIGIBLE_WORK", "actor_ref": "lead:one",
            "authority_class": "CURRENT_DELEGATED_GRANT", "owner_hint": "HEB",
            "subject": {"project_ref": first["subject"]["project_ref"], "installation_ref": cs["installation_ref"],
                        "attachment_ref": "attachment:one", "generation_ref": "generation:one"},
            "predecessor": {"basis_ref": "basis:one", "basis_version": "revision:one", "source_epoch": "epoch:one"},
            "target": {"work_ref": "work:one", "work_revision": "revision:one", "grant_ref": "grant:one",
                       "eligible_basis_ref": "basis:one", "selection_mode": "DELIBERATE_SELECTED_WORK"},
            "origin_proof_ref": "proof:" + "d" * 32, "delegated_grant_proof_ref": "grant-proof:one"}
    mixed = dict(cs, intents=[first, cont])
    assert wire.registry()["CONTINUE_ELIGIBLE_WORK"]["origin"] != "PROTECTED_G3"
    assert not wire.o01_errors(mixed), wire.o01_errors(mixed)  # it reaches G3-02 step 2, not step 1
    assert G.code(rig.svc.request(G.request_body(mixed))) == "MIXED_AUTHORITY_SET_UNSELECTED"
    assert G.code(rig.svc.request(G.request_body(dict(cs, intents=[cont])))) == "MIXED_AUTHORITY_SET_UNSELECTED"


@pytest.mark.parametrize(("label", "proof"), [
    ("not proof:<hex>", "proof:origin"),
    ("upper-case hex", "proof:" + "A" * 32),
    ("31 hex", "proof:" + "a" * 31),
    ("65 hex", "proof:" + "a" * 65),
    ("missing", None),
])
def test_n15_a_member_proof_that_is_not_proof_and_32_to_64_hex_is_member_proof_invalid(tmp_path: Path, label: str,
                                                                                      proof: Any) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    cs["intents"][0]["origin_proof_ref"] = proof
    assert G.code(rig.svc.request(G.request_body(cs))) in ("MEMBER_PROOF_INVALID", "STRUCTURAL"), label
    if proof is not None:
        assert G.code(rig.svc.request(G.request_body(cs))) == "MEMBER_PROOF_INVALID", label


@pytest.mark.parametrize("n", [32, 64])
def test_a_proof_of_32_or_64_hex_is_accepted(tmp_path: Path, n: int) -> None:
    rig = G.make(tmp_path)
    cs = G.base_set()
    cs["intents"][0]["origin_proof_ref"] = "proof:" + "c" * n
    assert rig.svc.request(G.request_body(cs))[0] == 201


def test_n15_a_proof_seen_before_is_refused_in_a_new_set_and_across_a_restart_and_repeated_within_a_set(
        tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    assert rig.svc.request(G.request_body(cs))[0] == 201
    again = dict(cs, request_set_ref="request:attach-lead-again")
    assert G.code(rig.svc.request(G.request_body(again))) == "MEMBER_PROOF_INVALID"
    rig2 = rig.restart()
    assert not rig2.svc.pending, "a restart drops pending approvals (G3-11)"
    after = dict(cs, request_set_ref="request:attach-lead-after-restart")
    assert G.code(rig2.svc.request(G.request_body(after))) == "MEMBER_PROOF_INVALID"
    two = G.fresh_proofs(G.base_set())
    two["intents"].append(dict(copy.deepcopy(two["intents"][0]), intent_ref="intent:zz-second"))
    assert G.code(rig2.svc.request(G.request_body(two))) == "MEMBER_PROOF_INVALID"  # the same proof twice


def test_a_refused_request_records_none_of_its_proofs(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    injected = render.render(cs, wire.registry(), {}) + [
        {"template_id": "g3:action:ATTACH_LEAD", "values": {"note": "safe"}, "source": {"kind": "TEMPLATE"}}]
    assert G.code(rig.svc.request(G.request_body(cs), lines=injected)) == "RENDERING_UNDERIVED"
    assert rig.svc.request(G.request_body(cs))[0] == 201  # its proofs are still fresh


def test_the_ledger_refuses_a_proof_seen_before_by_its_key_whatever_the_read_said(tmp_path: Path) -> None:
    """Addendum 2 §3: the uniqueness constraint decides, not the read before it."""
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    rig.svc.ledger.accept_proofs([cs["intents"][0]["origin_proof_ref"]])
    rig.svc.ledger.any_seen = lambda proofs: False  # type: ignore[method-assign]
    assert G.code(rig.svc.request(G.request_body(cs))) == "MEMBER_PROOF_INVALID"


@pytest.mark.parametrize(("label", "body"), [
    ("another wire version", lambda cs: {"wire_version": "g3-0.5-candidate", "command_set": cs}),
    ("an extra field", lambda cs: dict(G.request_body(cs), extra=1)),
    ("a consent_set_ref already set", lambda cs: G.request_body(dict(cs, consent_set_ref="consent:x"))),
    ("a set that is not O-01", lambda cs: G.request_body(dict(cs, intents=[]))),
    ("not an object", lambda cs: [cs]),
])
def test_a_malformed_approval_request_is_structural(tmp_path: Path, label: str, body: Any) -> None:
    rig = G.make(tmp_path)
    assert G.code(rig.svc.request(body(G.fresh_proofs(G.base_set())))) == "STRUCTURAL", label


def test_approval_expiry_is_ten_minutes_ahead_and_the_deployment_may_shorten_it(tmp_path: Path) -> None:
    rig = G.make(tmp_path / "a")
    _, pending = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    assert pending["expires_at"] == (G.T0 + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    short = G.make(tmp_path / "b", approval_expiry_minutes=3, consent_validity_minutes=4)
    p2, rec = G.approved(short.svc, G.fresh_proofs(G.base_set()))
    assert p2["expires_at"] == (G.T0 + timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert rec["valid_until"] == (G.T0 + timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------------ G3-03 rendering
def test_n09_a_rendering_line_carrying_client_prose_or_another_value_is_rendering_underived(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    honest = render.render(cs, wire.registry(), {})
    prose = honest + [{"template_id": "g3:action:ATTACH_LEAD", "values": {"note": "Routine, safe to approve"},
                       "source": {"kind": "TEMPLATE"}}]
    misshown = copy.deepcopy(honest)
    next(ln for ln in misshown if ln["source"]["kind"] == "TYPED_FIELD")["values"]["value"] = "something-else"
    fact = honest + [dict(copy.deepcopy(G.P1["pending"]["rendering"][-1]))]  # an owner fact the service never read
    other_action = honest + [{"template_id": "g3:action:CLOSE_ATTACHMENT", "values": {},
                              "source": {"kind": "TEMPLATE"}}]
    retyped = copy.deepcopy(honest)
    next(ln for ln in retyped if ln["values"].get("value") is None)["values"]["value"] = "null"
    for label, lines in (("prose", prose), ("another value", misshown), ("an unread owner fact", fact),
                         ("another action's template", other_action), ("null shown as text", retyped)):
        assert G.code(rig.svc.request(G.request_body(cs), lines=lines)) == "RENDERING_UNDERIVED", label
    assert rig.svc.request(G.request_body(cs), lines=honest)[0] == 201, "control: the service's own rendering"


def test_n09_the_regression_aids_own_injected_rendering_is_rendering_underived(tmp_path: Path) -> None:
    """The vendored case itself (A-26 g3-cases.json N09, binding under addendum 1), over the set its rendering was made
    from: P1's, with the member proof its own line shows (#269, n3). The control drops only the injected line, so the
    refusal is that line's and no other's."""
    rig = G.make(tmp_path, facts=G.P1_FACTS)
    injected = G.cases()["N09"]["injected_rendering"]
    req = copy.deepcopy(G.P1["approval_request"])
    req["command_set"]["intents"][0]["origin_proof_ref"] = next(
        ln["values"]["value"] for ln in injected if ln["source"].get("field_path") == "intents[0].origin_proof_ref")
    prose = [ln for ln in injected if ln["source"]["kind"] == "TEMPLATE" and ln["values"]]
    assert len(prose) == 1, prose  # the client's note on a template line, which G3-03 never shows
    assert G.code(rig.svc.request(req, lines=injected)) == "RENDERING_UNDERIVED"
    assert rig.svc.request(req, lines=[ln for ln in injected if ln not in prose])[0] == 201, \
        "control: without the injected line the same rendering is derived, and the refusal took none of its proofs"


def test_n16_every_covered_leaf_changes_the_rendering_and_dropping_any_one_is_rendering_incomplete(
        tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    honest = render.render(cs, wire.registry(), {})
    covered = render.leaves(cs)

    def mutate(v: Any) -> Any:
        if v is None or v == "":
            return "x:mutated"
        if isinstance(v, bool):
            return not v
        return v + 1 if isinstance(v, int) else v + ":m"

    def set_at(path: str, value: Any) -> dict[str, Any]:
        out = copy.deepcopy(cs)
        parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]", path)
        node: Any = out
        for p in parts[:-1]:
            node = node[int(p[1:-1])] if p.startswith("[") else node[p]
        last = parts[-1]
        node[int(last[1:-1]) if last.startswith("[") else last] = value
        return out

    same = [f for f, v in covered if wire.canonical(render.render(set_at(f, mutate(v)), wire.registry(), {}))
            == wire.canonical(honest)]
    assert not same, same
    dropped = [f for f, _ in covered
               if G.code(rig.svc.request(G.request_body(cs), lines=[ln for ln in honest
                                                                    if ln["source"].get("field_path") != f]))
               != "RENDERING_INCOMPLETE"]
    assert not dropped, dropped
    no_template = [ln for ln in honest if ln["source"]["kind"] != "TEMPLATE"]
    assert G.code(rig.svc.request(G.request_body(cs), lines=no_template)) == "RENDERING_INCOMPLETE"


# ------------------------------------------------------------------------------------------------ G3-05 the PIN
def test_n10_a_wrong_pin_issues_nothing(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    _, pending = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    assert G.code(rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": "not-the-pin"})) == \
        "PIN_INCORRECT"
    assert rig.svc.ledger.approval(pending["approval_ref"]) is None
    assert rig.svc.get(pending["approval_ref"])[1]["state"] == "PENDING"


def test_n11_approving_at_expires_at_is_approval_expired_and_one_second_before_it_approves(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    _, early = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    _, late = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    rig.clock.advance(minutes=10, seconds=-1)
    assert rig.svc.decide(early["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})[0] == 200
    rig.clock.advance(seconds=1)
    assert G.code(rig.svc.decide(late["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})) == "APPROVAL_EXPIRED"
    assert G.code(rig.svc.decide(late["approval_ref"], {"decision": "DECLINE"})) == "APPROVAL_EXPIRED"
    assert rig.svc.ledger.approval(late["approval_ref"]) is None
    assert rig.svc.list_pending() == (200, [])


LONE_SURROGATE = chr(0xD800)  # a wire-valid JSON string ("\ud800") no keyboard can type, and no codec can encode


def test_no_refused_decision_but_a_wrong_pin_on_an_open_approval_counts_toward_the_lockout(tmp_path: Path) -> None:
    """Addendum 2 §1's order: a malformed decision, a decided or unknown approval, and an expired one are each refused
    before the PIN is compared, and none counts (review of #269, m4 B2)."""
    rig = G.make(tmp_path)
    pin_id = pinstore.read(tmp_path).pin_id
    _, expired = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    rig.clock.advance(minutes=10)
    for decision, expected in (({"decision": "APPROVE", "pin": "wrong-pin"}, "APPROVAL_EXPIRED"),
                               ({"decision": "APPROVE", "pin": "short"}, "STRUCTURAL"),
                               ({"decision": "APPROVE"}, "STRUCTURAL"),
                               ({"decision": "APPROVE", "pin": LONE_SURROGATE * 6}, "STRUCTURAL")):
        assert G.code(rig.svc.decide(expired["approval_ref"], decision)) == expected, decision
    assert G.code(rig.svc.decide("g3:approval:unknown", {"decision": "APPROVE", "pin": "wrong-pin"})) == "NOT_FOUND"
    assert rig.svc.ledger.failures(pin_id) == 0
    _, open_ = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    assert G.code(rig.svc.decide(open_["approval_ref"], {"decision": "APPROVE", "pin": "wrong-pin"})) == "PIN_INCORRECT"
    assert rig.svc.ledger.failures(pin_id) == 1, "control: the one refusal that counts"


def test_a_pin_that_is_not_utf8_is_structural_and_neither_counts_nor_decides(tmp_path: Path) -> None:
    """A lone surrogate reaches _decide from json.loads: STRUCTURAL, not a dropped connection (review of #269, m2)."""
    rig = G.make(tmp_path)
    _, pending = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    pin = "abc" + LONE_SURROGATE + "def"
    assert G.code(rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": pin})) == "STRUCTURAL"
    assert rig.svc.ledger.failures(pinstore.read(tmp_path).pin_id) == 0
    assert rig.svc.get(pending["approval_ref"])[1]["state"] == "PENDING"


def _wrong(rig: G.Rig, ref: str, n: int) -> list[str | None]:
    return [G.code(rig.svc.decide(ref, {"decision": "APPROVE", "pin": "wrong-pin"})) for _ in range(n)]


def test_n19_the_lockout_locks_at_five_consecutive_wrong_pins_and_not_at_four(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    refs = [rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"] for _ in range(3)]
    assert _wrong(rig, refs[0], 4) == ["PIN_INCORRECT"] * 4
    assert rig.svc.decide(refs[0], {"decision": "APPROVE", "pin": G.PIN})[0] == 200, "four wrong: still approves"
    assert _wrong(rig, refs[1], 5) == ["PIN_INCORRECT"] * 5, "the correct PIN reset the count"
    assert G.code(rig.svc.decide(refs[1], {"decision": "APPROVE", "pin": G.PIN})) == "PIN_LOCKED"
    assert rig.svc.decide(refs[2], {"decision": "DECLINE"}) == (204, None), "declining needs no PIN, even locked"


def test_a_deployment_lockout_of_three_locks_at_three(tmp_path: Path) -> None:
    rig = G.make(tmp_path, lockout_after=3)
    ref = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
    assert _wrong(rig, ref, 3) == ["PIN_INCORRECT"] * 3
    assert G.code(rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN})) == "PIN_LOCKED"


def test_the_lockout_survives_a_restart_and_only_setting_the_pin_ends_it(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    ref = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
    _wrong(rig, ref, 5)
    rig2 = rig.restart()
    ref2 = rig2.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
    assert G.code(rig2.svc.decide(ref2, {"decision": "APPROVE", "pin": G.PIN})) == "PIN_LOCKED"
    pinstore.set_pin(tmp_path, G.PIN, rig2.dep)  # root resets it
    assert rig2.svc.decide(ref2, {"decision": "APPROVE", "pin": G.PIN})[0] == 200


def test_a_pin_set_under_a_lower_minimum_than_the_deployments_is_locked_until_set_again(tmp_path: Path) -> None:
    rig = G.make(tmp_path)  # set under the shipped minimum, 6
    for minimum, approves in ((6, True), (7, False)):
        r = rig.restart(pin_min_length=minimum)
        ref = r.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
        reply = r.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN})
        assert (reply[0] == 200) is approves and (approves or G.code(reply) == "PIN_LOCKED"), minimum
        rig = r
    pinstore.set_pin(tmp_path, G.PIN, rig.dep)  # set again under 7
    ref = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
    assert rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN})[0] == 200


@pytest.mark.parametrize("first", ["APPROVE", "DECLINE"])
def test_a_second_decision_on_a_decided_approval_is_not_found_and_issues_nothing_or_counts(
        tmp_path: Path, first: str) -> None:
    """Hand-off addendum 2 §1: approve (or decline), then approve again with the right PIN and with a wrong one."""
    rig = G.make(tmp_path)
    ref = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
    other = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))[1]["approval_ref"]
    assert _wrong(rig, other, 2) == ["PIN_INCORRECT"] * 2  # a run of wrong PINs is under way
    assert rig.svc.decide(ref, {"decision": first, "pin": G.PIN})[0] in ACCEPTED
    pin_id = pinstore.read(tmp_path).pin_id
    count = rig.svc.ledger.failures(pin_id)
    assert count == (0 if first == "APPROVE" else 2)  # the right PIN ends the run; declining leaves it
    records = rig.svc.ledger._db.execute("SELECT count(*) FROM records").fetchone()[0]
    for pin in (G.PIN, "wrong-pin"):
        assert G.code(rig.svc.decide(ref, {"decision": "APPROVE", "pin": pin})) == "NOT_FOUND"
    rig.clock.advance(minutes=11)  # past its expiry too: still NOT_FOUND, not APPROVAL_EXPIRED
    assert G.code(rig.svc.decide(ref, {"decision": "APPROVE", "pin": "wrong-pin"})) == "NOT_FOUND"
    assert rig.svc.ledger._db.execute("SELECT count(*) FROM records").fetchone()[0] == records
    assert rig.svc.ledger.failures(pin_id) == count


def test_an_approval_lost_at_a_restart_is_not_found_and_an_approved_one_is_still_fetched(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    pending, record = G.approved(rig.svc, cs)
    _, lost = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    rig2 = rig.restart()
    assert G.code(rig2.svc.decide(lost["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})) == "NOT_FOUND"
    assert G.code(rig2.svc.get(lost["approval_ref"])) == "NOT_FOUND"
    status, got = rig2.svc.get(pending["approval_ref"])
    assert status == 200 and got["state"] == "APPROVED" and got["consent_record"] == record
    assert _valid("PendingApproval", got)
    assert G.code(rig2.svc.consume(G.consume_req(cs, record))) == "CONSUMED"


def test_the_pin_is_never_kept_in_an_approval_a_record_or_the_ledger(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, wrong = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    rig.svc.decide(wrong["approval_ref"], {"decision": "APPROVE", "pin": "wrong-but-planted-pin"})
    pending, record = G.approved(rig.svc, cs)
    rig.svc.ledger.close()
    for f in tmp_path.rglob("*"):
        if f.is_file():
            data = f.read_bytes()
            for pin in (G.PIN, "wrong-but-planted-pin"):
                assert pin.encode() not in data, (f.name, pin)
    assert G.PIN not in json.dumps([pending, record, rig.svc.get(pending["approval_ref"])[1]])


# ------------------------------------------------------------------------------------------------ G3-11 failure
def test_with_the_clock_unreadable_nothing_is_requested_approved_or_consumed(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    _, pending = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    rig.clock.broken = True
    assert G.code(rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))) == "G3_UNAVAILABLE"
    assert G.code(rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})) == "G3_UNAVAILABLE"
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "G3_UNAVAILABLE"
    assert G.code(rig.svc.list_pending()) == "G3_UNAVAILABLE"
    rig.clock.broken = False
    assert rig.svc.ledger.approval(pending["approval_ref"]) is None
    assert G.code(rig.svc.consume(G.consume_req(cs, record))) == "CONSUMED"


@pytest.mark.parametrize("step", ["accept_proofs", "store_approval", "consume", "record_failure", "failures", "record"])
def test_with_the_ledger_unwritable_or_unreadable_nothing_is_approved_or_consumed(tmp_path: Path, step: str) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    fresh = G.fresh_proofs(G.base_set())
    _, pending = rig.svc.request(G.request_body(fresh))
    real = getattr(rig.svc.ledger, step)

    def fail(*a: Any, **k: Any) -> Any:
        raise LedgerUnavailable("disk full (planted)")

    setattr(rig.svc.ledger, step, fail)
    replies = [rig.svc.request(G.request_body(G.fresh_proofs(G.base_set()))),
               rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE",
                                                        "pin": "wrong-pin" if step == "record_failure" else G.PIN}),
               rig.svc.consume(G.consume_req(cs, record))]
    assert "G3_UNAVAILABLE" in [G.code(r) for r in replies], step
    setattr(rig.svc.ledger, step, real)
    assert rig.svc.ledger.consumed(record["consent_set_ref"], cs["intents"][0]["intent_ref"]) is (step not in (
        "consume", "record")), step
    if step in ("store_approval", "failures", "record_failure"):
        assert rig.svc.ledger.approval(pending["approval_ref"]) is None
        assert rig.svc.get(pending["approval_ref"])[1]["state"] == "PENDING"


def test_with_the_pin_record_unreadable_nothing_is_approved(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    _, pending = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    (tmp_path / pinstore.PIN_FILE).write_bytes(b"{not json")
    assert G.code(rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})) == "G3_UNAVAILABLE"
    (tmp_path / pinstore.PIN_FILE).unlink()
    assert G.code(rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})) == "G3_UNAVAILABLE"
    assert rig.svc.ledger.approval(pending["approval_ref"]) is None


def test_a_hold_names_its_cause_and_the_remedy_in_the_journal_and_never_the_pin(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The wire's Problem has no detail, so G3-11's cause goes to stderr, the service's journal (#269, m5)."""
    rig = G.make(tmp_path)
    _, pending = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    (tmp_path / pinstore.PIN_FILE).unlink()
    assert G.code(rig.svc.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": G.PIN})) == "G3_UNAVAILABLE"
    pin_line = capsys.readouterr().err
    assert "the PIN record cannot be read (FileNotFoundError)" in pin_line and f"sudo {COMMAND} set-pin" in pin_line
    rig.clock.broken = True
    assert G.code(rig.svc.list_pending()) == "G3_UNAVAILABLE"
    assert "the clock cannot be read (OSError)" in capsys.readouterr().err
    rig.clock.broken = False

    def fail(*a: Any, **k: Any) -> Any:
        raise LedgerUnavailable("disk I/O error")

    rig.svc.ledger.accept_proofs = fail  # type: ignore[method-assign]
    assert G.code(rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))) == "G3_UNAVAILABLE"
    err = capsys.readouterr().err
    assert "the ledger cannot be read or written (disk I/O error)" in err
    assert G.PIN not in pin_line + err


def test_the_ledger_commits_with_synchronous_full(tmp_path: Path) -> None:
    """G3-08's "written and flushed before the reply", and addendum 2 §3: FULL (2), never NORMAL or OFF (m4 B5)."""
    ledger = Ledger(tmp_path)
    try:
        assert ledger._db.execute("PRAGMA synchronous").fetchone()[0] == 2
    finally:
        ledger.close()


# ------------------------------------------------------------------------------------------------ the wire
def test_every_body_the_service_returns_is_valid_on_the_wire(tmp_path: Path) -> None:
    rig = G.make(tmp_path)
    cs = G.fresh_proofs(G.base_set())
    pending, record = G.approved(rig.svc, cs)
    replies = [rig.svc.get(pending["approval_ref"]), rig.svc.consume(G.consume_req(cs, record)),
               rig.svc.consume(G.consume_req(cs, record)), rig.svc.get("g3:approval:unknown"),
               rig.svc.request({"bad": 1})]
    kinds = ["PendingApproval", "ConsumeResult", "ConsumeResult", "Problem", "Problem"]
    for (status, body), kind in zip(replies, kinds, strict=True):
        assert _valid(kind, body), (kind, body)
        if kind == "Problem":
            assert body["status"] == status == wire.STATUS[body["code"]]
