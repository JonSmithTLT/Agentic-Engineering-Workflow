"""`aew g3 request` against the real G3 service on its real socket and the real O-01 route (STG-03, G3-D; A-37 G3-02,
G3-07). Linux only: ``request.sock`` is a Unix filesystem socket with SO_PEERCRED.

The G3 service runs in this process (G3-A's server over sockets in a temporary directory) and the O-01 route is the
STG-02 slice's server on 127.0.0.1 with a synthetic bearer token. The operator's decision is made from a thread, on the
service, with the regression aid's labelled stand-in PIN: the client never sees a PIN.
"""

from __future__ import annotations

import copy
import functools
import http.client
import json
import os
import re
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from aew import g3client as C
from aew import g3standing as S
from aew.cli.main import main
from aew.errors import OperatorAuthorizationRequired, Unavailable, ValidationFailed
from aew.stg02 import ledger as L
from aew.stg02 import server as SV
from aew.stg02 import wire as W
from tests.helpers import g3 as G

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="G3 is a Linux profile: Unix sockets, SO_PEERCRED")

TOKEN = "token-planted-g3-client-process"  # synthetic: it must appear in nothing the client says
RECIPIENT, INSTALLATION = "fixture:recipient-operator", "fixture:installation-slice"


@dataclass
class World:
    rig: G.Rig
    url: str
    token_file: Path
    set_file: Path
    o01: SV.Slice


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    from aew_g3 import server

    rig = G.make(tmp_path / "g3", clock=G.Clock(now=datetime.now(UTC)))
    g3 = server.G3Server(rig.svc, server.bind_sockets(tmp_path / "run"))
    g3.start()
    s = SV.Slice(tmp_path / "o01", tokens={TOKEN: RECIPIENT})
    o01 = SV.make_server(s, 0)
    t = threading.Thread(target=o01.serve_forever, daemon=True)
    t.start()
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "run" / "request.sock"))
    # The wait reads the service's clock, so an expiry is the service's (the rig's), not the wall's.
    monkeypatch.setattr(C, "await_decision", functools.partial(C.await_decision, now=rig.clock))
    cs = copy.deepcopy(G.base_set())
    cs.update(installation_ref=INSTALLATION, recipient_ref=RECIPIENT, consent_set_ref=None)
    for i in cs["intents"]:
        i["origin_proof_ref"] = None
        i["subject"]["installation_ref"] = INSTALLATION
    set_file, token_file = tmp_path / "set.json", tmp_path / "token"
    set_file.write_bytes(json.dumps(cs).encode())
    token_file.write_bytes((TOKEN + "\n").encode())
    try:
        yield World(rig, f"http://127.0.0.1:{o01.server_address[1]}", token_file, set_file, s)
    finally:
        o01.shutdown()
        o01.server_close()
        g3.stop()


def _operator(rig: G.Rig, act: Callable[[str], None]) -> threading.Thread:
    """The operator, in the confirmer: once an approval is pending, ``act`` on it."""
    def run() -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status, listed = rig.svc.list_pending()
            if status == 200 and listed:
                act(listed[0]["approval_ref"])  # type: ignore[index]
                return
            time.sleep(0.05)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def _run(w: World, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(["g3", "request", str(w.set_file), "--o01", w.url, "--token-file", str(w.token_file), "--json"])
    out = capsys.readouterr()
    return code, out.out, out.err


def _error(err: str) -> dict[str, Any]:
    """The error object main writes, after the client's one waiting line, if any."""
    return json.loads(err[err.index("{"):])["error"]


def test_an_approved_set_is_submitted_unchanged_with_its_consent_and_not_admitted_for_want_of_g3(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """G3-02 then G3-07: the record's set_digest is the SW-02 digest of the set the O-01 route received, and the
    receipt, held while G3 does not count for the route, carries the note that says why. Nothing is consumed."""
    seen: list[dict[str, Any]] = []
    real = C.submit

    def submit(cs: dict[str, Any], url: str, token: str) -> dict[str, Any]:
        seen.append(copy.deepcopy(cs))
        return real(cs, url, token)

    monkeypatch.setattr(C, "submit", submit)
    approved: list[str] = []
    t = _operator(world.rig, lambda ref: approved.append(ref) or world.rig.svc.decide(
        ref, {"decision": "APPROVE", "pin": G.PIN}))
    code, out, err = _run(world, capsys)
    t.join(10)
    assert code == 0, err
    result = json.loads(out)
    assert result["approval_ref"] == approved[0] and f"waiting for the operator to approve or decline {approved[0]}" \
        in err
    stored = world.rig.svc.ledger.record(result["consent_set_ref"])
    assert stored is not None
    record = stored[0]
    assert record["approval_ref"] == approved[0]
    sent = seen[0]
    assert sent["consent_set_ref"] == record["consent_set_ref"] and W.set_digest(sent) == record["set_digest"]
    asked = json.loads(world.set_file.read_bytes())
    proofs = [i["origin_proof_ref"] for i in sent["intents"]]
    for i in sent["intents"]:
        i["origin_proof_ref"] = None
    assert dict(sent, consent_set_ref=None) == asked  # unchanged but for the proofs and the consent
    assert all(p and p.startswith("proof:") for p in proofs) and len(set(proofs)) == len(proofs)
    results = result["receipt"]["results"]
    # This route has no project, so G3 does not count for it and the member is held (addendum 5; addendum 7, ruling 2).
    assert [(r["admission_state"], r["reason_code"], r["operation_ref"]) for r in results] == [
        ("HELD", "ORIGIN_NOT_ESTABLISHED", None)]
    assert result["note"].startswith("Approved in the confirmer and submitted, and the owner held it")
    assert world.rig.svc.ledger.consumed(result["consent_set_ref"], results[0]["intent_ref"]) is False
    assert TOKEN not in out + err and G.PIN not in out + err


def test_a_held_note_says_what_the_probe_found_after_the_submission(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """The review of G3-C's first pull request, n3: where the host's conditions hold and the owner still held the
    member, the client names the service when the probe finds it not answering, not the project's policy."""
    monkeypatch.setattr(S, "standing", lambda *_, **__: S.Standing(True, judged=(1, 3)))
    monkeypatch.setattr(C, "probe", lambda *_: "planted: the service stopped")
    t = _operator(world.rig, lambda ref: world.rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN}))
    code, out, err = _run(world, capsys)
    t.join(10)
    assert code == 0, err
    note = json.loads(out)["note"]
    assert "the G3 service does not answer: planted: the service stopped" in note and "the project's policy" not in note


def _g3_counts(w: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The route's owner, on a host where G3 counts for its project: it then consumes on the real service's socket."""
    monkeypatch.setattr(S, "standing", lambda *_, **__: S.Standing(True))
    w.o01.carrier.policy = lambda: {}


def test_an_approved_set_is_admitted_and_its_member_consumed_once_against_the_route_s_operation(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole path on the real sockets: approved in the confirmer, submitted, consumed by the owner at admission, and
    admitted against the operation the service recorded. Submitting the same approval under a new key is refused."""
    _g3_counts(world, monkeypatch)
    seen: list[dict[str, Any]] = []
    real = C.submit

    def submit(cs: dict[str, Any], url: str, token: str) -> dict[str, Any]:
        seen.append(copy.deepcopy(cs))
        return real(cs, url, token)

    monkeypatch.setattr(C, "submit", submit)
    t = _operator(world.rig, lambda ref: world.rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN}))
    code, out, err = _run(world, capsys)
    t.join(10)
    assert code == 0, err
    result = json.loads(out)
    (admitted,) = result["receipt"]["results"]
    assert (admitted["admission_state"], admitted["effect_state"], admitted["owner_evidence_ref"]) == (
        "ADMITTED", "NOT_OBSERVED", None)
    assert admitted["operation_ref"].startswith("op:") and result["note"] == C.NO_EFFECT + "."
    ledger = world.rig.svc.ledger
    assert ledger.consumed(result["consent_set_ref"], admitted["intent_ref"])
    again = dict(seen[0], client_request_key=seen[0]["client_request_key"] + ".again",
                 request_set_ref=seen[0]["request_set_ref"])
    token = world.token_file.read_text(encoding="utf-8").strip()
    (refused,) = C.submit(again, world.url, token)["results"]
    assert (refused["admission_state"], refused["reason_code"], refused["operation_ref"]) == (
        "REJECTED", "CONSENT_ALREADY_USED_OR_MISSING", None)


def _do_the_printed_get(world: World, said: str) -> list[dict[str, Any]]:
    """Does what the client printed, its path and its header read from the words, and gives the list's items."""
    found = re.search(r"GET (/\S+) on the route, with the bearer token and the header ([\w-]+): (\S+?),", said)
    assert found, said
    target = urlsplit(world.url)
    conn = http.client.HTTPConnection(target.hostname or "", target.port, timeout=10)
    token = world.token_file.read_text(encoding="utf-8").strip()
    conn.request("GET", found[1], headers={found[2]: found[3], "Authorization": "Bearer " + token})
    reply = conn.getresponse()
    body = json.loads(reply.read())
    conn.close()
    assert reply.status == 200, body
    return body["items"]


def test_the_held_notes_way_on_can_be_followed_to_an_admission(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator does what the client says, end to end. Held, with a note. The same file again is refused, naming the
    key. Then a new client_request_key in the set file, and a new approval: admitted."""
    def approve() -> threading.Thread:
        return _operator(world.rig, lambda ref: world.rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN}))

    t = approve()
    code, out, err = _run(world, capsys)
    t.join(10)
    first = json.loads(out)
    assert code == 0 and first["receipt"]["results"][0]["admission_state"] == "HELD"
    assert "new client_request_key in the set file" in first["note"]
    _g3_counts(world, monkeypatch)
    t = approve()
    code, out, err = _run(world, capsys)
    t.join(10)
    assert code != 0 and "request_key_conflict" in err and "new client_request_key in the set file" in err
    assert "approval is unused" in err and "for another set" not in err and "may be this file's" in err
    assert _do_the_printed_get(world, err) == []  # it was held, so the list says it was not admitted
    cs = json.loads(world.set_file.read_bytes())
    cs["client_request_key"] += ".again"
    world.set_file.write_bytes(json.dumps(cs).encode())
    t = approve()
    code, out, err = _run(world, capsys)
    t.join(10)
    third = json.loads(out)
    assert code == 0 and third["consent_set_ref"] != first["consent_set_ref"]
    (admitted,) = third["receipt"]["results"]
    assert admitted["admission_state"] == "ADMITTED" and admitted["operation_ref"]
    assert world.rig.svc.ledger.consumed(third["consent_set_ref"], admitted["intent_ref"])
    t = approve()
    code, out, err = _run(world, capsys)  # the same file again: the list it names now shows the admission
    t.join(10)
    assert code != 0 and "request_key_conflict" in err
    assert [i["data"]["operation_ref"] for i in _do_the_printed_get(world, err)] == [admitted["operation_ref"]]


def test_the_human_output_of_an_admitted_member_says_no_effect_and_nothing_else_happens(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Admitted in a run must not read as performed: a one-use approval was used for a record."""
    _g3_counts(world, monkeypatch)
    t = _operator(world.rig, lambda ref: world.rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN}))
    code = main(["g3", "request", str(world.set_file), "--o01", world.url, "--token-file", str(world.token_file)])
    t.join(10)
    got = capsys.readouterr()
    assert code == 0 and "ADMITTED effect NOT_OBSERVED" in got.out and C.NO_EFFECT in got.out


def test_a_stalled_service_reaches_the_operator_as_a_held_receipt_not_a_client_that_gave_up(
        world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """G3-11: a service that accepts and never answers. The route's read of consume ends within its bound, and the
    client's read of the route waits longer than that, whatever the bound is."""
    monkeypatch.setattr(C, "TIMEOUT_S", 2)
    _g3_counts(world, monkeypatch)
    path = str(tmp_path / "stalled.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(4)
    monkeypatch.setattr(C, "REQUEST_SOCK", path)
    cs = json.loads(world.set_file.read_bytes())
    cs["consent_set_ref"] = "consent:g3:any"
    for i in cs["intents"]:
        i["origin_proof_ref"] = "proof:" + "0" * 32
    token = world.token_file.read_text(encoding="utf-8").strip()
    try:
        results = C.submit(cs, world.url, token)["results"]
    finally:
        listener.close()
    assert [(r["admission_state"], r["reason_code"]) for r in results] == [
        ("HELD", "ORIGIN_NOT_ESTABLISHED")] * len(results)


def test_a_transaction_that_fails_after_consumed_stores_nothing_and_its_retry_is_refused(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """It fails closed. The client says the approval may have been used, no receipt or operation survives on the route,
    the member stays used on the service, and the set resent under its key is refused with nothing allocated."""
    _g3_counts(world, monkeypatch)
    kept: list[dict[str, Any]] = []
    real_submit = C.submit

    def submit(cs: dict[str, Any], url: str, token: str) -> dict[str, Any]:
        kept.append(copy.deepcopy(cs))
        return real_submit(cs, url, token)

    monkeypatch.setattr(C, "submit", submit)
    real_store = L.Txn.store_key
    armed = [True]

    def store(self: Any, *a: Any, **k: Any) -> None:
        if armed:
            armed.clear()
            raise OSError("planted: the transaction fails after CONSUMED")
        real_store(self, *a, **k)

    monkeypatch.setattr(L.Txn, "store_key", store)
    t = _operator(world.rig, lambda ref: world.rig.svc.decide(ref, {"decision": "APPROVE", "pin": G.PIN}))
    code, out, err = _run(world, capsys)
    t.join(10)
    assert code != 0 and "approval may have been used" in err
    assert _do_the_printed_get(world, err) == []  # nothing survives on the route
    consent, intent = kept[0]["consent_set_ref"], kept[0]["intents"][0]["intent_ref"]
    assert world.rig.svc.ledger.consumed(consent, intent) is True
    with world.o01.ledger.reading() as txn:
        assert txn.owner_ops(INSTALLATION, RECIPIENT, datetime.now(UTC)) == []
    token = world.token_file.read_text(encoding="utf-8").strip()
    (again,) = real_submit(kept[0], world.url, token)["results"]
    assert (again["admission_state"], again["reason_code"], again["operation_ref"]) == (
        "REJECTED", "CONSENT_ALREADY_USED_OR_MISSING", None)


def test_a_set_refused_as_it_stands_says_a_new_key_does_not_change_it_and_what_to_check_does(
        world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A set for another installation, which the client's own checks cannot catch. The operator follows the words: a
    new key meets the same refusal, the route's log names the cause, and the installation_ref they say to check is the
    fix."""
    caplog.set_level("WARNING", logger="aew.stg02")
    _g3_counts(world, monkeypatch)
    token = world.token_file.read_text(encoding="utf-8").strip()
    good = json.loads(world.set_file.read_bytes())
    good["consent_set_ref"] = "consent:g3:any"
    for i in good["intents"]:
        i["origin_proof_ref"] = "fixture:not-a-proof-the-wire-allows"
    bad = dict(copy.deepcopy(good), installation_ref="installation:another")
    with pytest.raises(ValidationFailed) as refused:
        C.submit(bad, world.url, token)
    said = refused.value.message
    assert "invalid_request" in said and "approval is unused" in said and "does not change this" in said
    assert "installation_ref" in said and "request it again" not in said
    assert "INSTALLATION_NOT_THIS_DEPLOYMENT" in caplog.text
    bad["client_request_key"] += ".again"
    with pytest.raises(ValidationFailed) as again:
        C.submit(bad, world.url, token)
    assert again.value.message == said
    assert C.submit(good, world.url, token)["results"]


def test_a_held_note_after_a_refused_consume_sends_the_operator_to_the_routes_log_not_to_the_policy_alone(
        world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A consume the service refuses with a 400 while the probe answers. G3 counted, and the policy was fine: the note
    claims neither that G3 does not count nor that no consent was accepted, and the route's log has the cause."""
    caplog.set_level("WARNING", logger="aew.stg02")
    _g3_counts(world, monkeypatch)
    cs = json.loads(world.set_file.read_bytes())
    cs["consent_set_ref"] = "consent:g3:any"
    for i in cs["intents"]:
        i["origin_proof_ref"] = "fixture:not-a-proof-the-wire-allows"
    token = world.token_file.read_text(encoding="utf-8").strip()
    receipt = C.submit(cs, world.url, token)
    assert receipt["results"][0]["admission_state"] == "HELD" and "STRUCTURAL" in caplog.text
    note = C.note(receipt, S.Standing(True, judged=(1, 3)), C.probe()) or ""
    assert "The route's log, its stderr, names the cause" in note
    assert "G3 does not count" not in note and "accepted no consent" not in note


def test_a_member_whose_consent_names_no_record_is_rejected_on_the_real_service(
        world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """Addendum 5's pin: G3 is established and answers, and it has no such record: REJECTED, not held, no operation."""
    _g3_counts(world, monkeypatch)
    cs = json.loads(world.set_file.read_bytes())
    cs["consent_set_ref"] = "consent:g3:no-such-record"
    for i in cs["intents"]:
        i["origin_proof_ref"] = "proof:" + "0" * 32
    token = world.token_file.read_text(encoding="utf-8").strip()
    results = C.submit(cs, world.url, token)["results"]
    assert [(r["admission_state"], r["reason_code"], r["operation_ref"]) for r in results] == [
        ("REJECTED", "ORIGIN_NOT_ESTABLISHED", None)] * len(results)


def test_a_service_that_is_gone_holds_the_member_at_the_route(
        world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """G3-11 on the real client: G3 counts by the conditions the standing can see, and consume gets no answer."""
    _g3_counts(world, monkeypatch)
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "gone.sock"))
    cs = json.loads(world.set_file.read_bytes())
    cs["consent_set_ref"] = "consent:g3:any"
    for i in cs["intents"]:
        i["origin_proof_ref"] = "proof:" + "0" * 32
    token = world.token_file.read_text(encoding="utf-8").strip()
    results = C.submit(cs, world.url, token)["results"]
    assert [(r["admission_state"], r["reason_code"], r["operation_ref"]) for r in results] == [
        ("HELD", "ORIGIN_NOT_ESTABLISHED", None)] * len(results)


@pytest.mark.parametrize("decision", ["DECLINE", "EXPIRE", "RESTART"])
def test_a_decline_an_expiry_or_a_restart_submits_nothing_and_says_which(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, decision: str) -> None:
    submitted: list[Any] = []
    monkeypatch.setattr(C, "submit", lambda *a: submitted.append(a))

    def act(ref: str) -> None:
        if decision == "DECLINE":
            world.rig.svc.decide(ref, {"decision": "DECLINE"})
        elif decision == "EXPIRE":
            world.rig.clock.advance(minutes=world.rig.dep.approval_expiry_minutes)
        else:
            world.rig.svc.pending.clear()  # a restart keeps the ledger and loses every pending approval (G3-11)

    t = _operator(world.rig, act)
    code, out, err = _run(world, capsys)
    t.join(10)
    error = _error(err)
    reason = {"DECLINE": "declined", "EXPIRE": "expired", "RESTART": "approval_lost"}[decision]
    assert code == OperatorAuthorizationRequired.exit_code and error["details"]["reason"] == reason
    assert not submitted and out == "" and TOKEN not in err


def test_a_set_the_service_refuses_is_reported_and_nothing_is_submitted(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """A proof the service has seen before (G3-02, R2-5): MEMBER_PROOF_INVALID, from the service, typed here."""
    seen_hex = "ab" * C.PROOF_BYTES
    earlier = G.base_set()
    for i in earlier["intents"]:
        i["origin_proof_ref"] = "proof:" + seen_hex
    assert world.rig.svc.request(G.request_body(earlier))[0] == 201  # control: the proof's first use is accepted
    submitted: list[Any] = []
    monkeypatch.setattr(C, "submit", lambda *a: submitted.append(a))
    monkeypatch.setattr(C, "with_proofs", functools.partial(C.with_proofs, token=lambda n: seen_hex))
    code, _, err = _run(world, capsys)
    error = _error(err)
    assert code == 2 and error["details"]["reason"] == "g3_refused"
    assert error["details"]["g3_code"] == "MEMBER_PROOF_INVALID" and not submitted


def test_another_accounts_socket_is_not_permitted_and_nothing_is_submitted(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """request.sock is the operator's, mode 0600: from any other account (or a sandbox) the client is refused there,
    and says so, never "did not answer"."""
    submitted: list[Any] = []
    monkeypatch.setattr(C, "submit", lambda *a: submitted.append(a))
    os.chmod(C.REQUEST_SOCK, 0)  # as another account sees the operator's 0600 socket
    try:
        code, _, err = _run(world, capsys)
    finally:
        os.chmod(C.REQUEST_SOCK, 0o600)
    error = _error(err)
    assert error["code"] == "PERMISSION_DENIED" and error["details"]["reason"] == "g3_peer_not_permitted"
    assert code == 4 and not submitted


def test_an_answer_without_the_g3_wire_is_unavailable_never_a_pending_approval(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Some other server on the socket's path: its 201 with an approval_ref but no X-AEW-G3-Wire is not G3's."""
    path = str(tmp_path / "other.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    body = json.dumps({"approval_ref": "g3:approval:x", "expires_at": "2099-01-01T00:00:00Z"}).encode()

    def answer() -> None:
        # Two requests: the probe before the confirmer (a GET, no body), then the approval request. Each gets the
        # same answer, which is not G3's: the probe says so and the request goes ahead, as the command does (C1).
        for _ in range(2):
            conn, _ = listener.accept()
            got = b""
            while b"\r\n\r\n" not in got:  # the whole request first: a close with its body unread resets it
                got += conn.recv(65536)
            head, rest = got.split(b"\r\n\r\n", 1)
            length = int(next((ln.split(b":")[1] for ln in head.split(b"\r\n")
                               if ln.lower().startswith(b"content-length")), b"0"))
            while len(rest) < length:
                rest += conn.recv(65536)
            conn.sendall(b"HTTP/1.0 201 Created\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
            conn.close()

    t = threading.Thread(target=answer, daemon=True)
    t.start()
    monkeypatch.setattr(C, "REQUEST_SOCK", path)
    try:
        code, _, err = _run(world, capsys)
    finally:
        t.join(timeout=10)
        listener.close()
    error = _error(err)
    assert error["code"] == "UNAVAILABLE" and error["details"]["reason"] == "g3_not_g3" and code == 10
    assert "waiting for the operator" not in err
    assert "aew g3: the G3 service does not answer: the answer on" in err  # the probe found it not G3's first


def test_a_stalled_service_ends_the_wait_by_the_approvals_expiry_not_a_request_timeout_later(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """#286 review F2, on a real socket: a service that takes a request and never answers. Each request is bounded by
    the time left, so a one-second approval's wait ends by its expiry and the grace, not the transport's 30 s."""
    path = str(tmp_path / "stalled.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)
    monkeypatch.setattr(C, "GRACE_S", 1)
    pending = {"approval_ref": "approval:one", "expires_at": W.utc(datetime.now(UTC) + timedelta(seconds=1))}
    started = time.monotonic()
    try:
        with pytest.raises(Unavailable) as e:
            C.await_decision(pending, path)
    finally:
        listener.close()
    took = time.monotonic() - started
    assert e.value.details["reason"] == "g3_unreachable" and took < 1 + 1 + 1, took  # life, grace, and slack


def test_the_probe_reaches_the_real_services_guarded_read_answering_when_it_runs_and_naming_it_when_it_holds(
        world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """#365 review m3: the probe's 404 is the service's own answer for an approval no one made, not the router's for a
    path no route matches, so a service that holds every request is never read as answering."""
    from aew_g3.ledger import LedgerUnavailable

    assert C.probe() is None

    def unreadable(ref: str) -> Any:
        raise LedgerUnavailable("planted: the ledger cannot be read")

    monkeypatch.setattr(world.rig.svc.ledger, "approval", unreadable)
    said = C.probe()
    assert said is not None and "the G3 service is holding every request" in said
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "absent.sock"))
    assert "systemctl status aew-g3.service" in (C.probe() or "")


def _approved(world: World) -> tuple[dict[str, Any], dict[str, Any]]:
    """A protected set the operator approved on the real service, as an owner receives it, and its consent record."""
    cs = C.with_proofs(C.check_set(json.loads(world.set_file.read_bytes())))
    _, record = G.approved(world.rig.svc, cs)
    return dict(cs, consent_set_ref=record["consent_set_ref"]), record


def _consume(cs: dict[str, Any], **over: Any) -> C.Consumed:
    """What an owner sends: the SW-02 digest of the set it received, and the member's own proof."""
    i = cs["intents"][0]
    return C.consume(**{"consent_set_ref": cs["consent_set_ref"], "set_digest": W.set_digest(cs),
                        "recipient_ref": cs["recipient_ref"], "installation_ref": cs["installation_ref"],
                        "intent_ref": i["intent_ref"], "origin_proof_ref": i["origin_proof_ref"],
                        "owner": i["owner_hint"], "operation_ref": "op:client-consume", **over})


def test_consume_on_the_real_socket_consumes_the_member_once_against_its_operation(
        world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """G3-08 over the wire: the service takes the client's request as it stands, records the member against the
    owner and the operation, and refuses the same member a second time."""
    cs, record = _approved(world)
    ledger = world.rig.svc.ledger
    recorded: list[tuple[str, ...]] = []
    real = ledger.consume

    def consume(consent_set_ref: str, intent_ref: str, owner: str, operation_ref: str, at: str) -> bool:
        recorded.append((consent_set_ref, intent_ref, owner, operation_ref))
        return real(consent_set_ref, intent_ref, owner, operation_ref, at)

    monkeypatch.setattr(ledger, "consume", consume)
    i = cs["intents"][0]
    assert _consume(cs).result == "CONSUMED"
    assert recorded == [(record["consent_set_ref"], i["intent_ref"], i["owner_hint"], "op:client-consume")]
    assert ledger.consumed(record["consent_set_ref"], i["intent_ref"])
    assert _consume(cs).result == "CONSENT_ALREADY_USED"


def test_a_consume_whose_reply_is_lost_gives_none_and_the_next_call_is_refused_so_it_fails_closed(
        world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """The designer's ruling: the service commits, the reply never reaches the owner, and the owner holds. Its text says
    a new approval may be needed, because the retry is refused as used; nothing is ever admitted twice."""
    cs, record = _approved(world)
    real = C._UnixHTTP.getresponse
    sent: list[Any] = []

    def lost(conn: Any) -> Any:
        sent.append(conn)
        real(conn).read()  # the service has answered, so it has committed
        raise http.client.RemoteDisconnected("planted: the reply is lost")

    monkeypatch.setattr(C._UnixHTTP, "getresponse", lost)
    got = _consume(cs)
    assert got.result is None and "did not answer" in (got.held_why or "") and C._HELD_WAY_ON in (got.held_why or "")
    assert "new approval" in (got.held_why or "")
    assert len(sent) == 1  # it asks once: the client never sends a used member again by itself
    assert world.rig.svc.ledger.consumed(record["consent_set_ref"], cs["intents"][0]["intent_ref"])
    monkeypatch.setattr(C._UnixHTTP, "getresponse", real)
    assert _consume(cs).result == "CONSENT_ALREADY_USED"


def test_consume_on_the_real_socket_gives_each_of_g3_08s_refusals_and_consumes_nothing(
        world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each refusal but CONSENT_ALREADY_USED, which the test above draws, and the member stays unused."""
    cs, record = _approved(world)
    ledger, keys = world.rig.svc.ledger, world.rig.svc.keys
    assert _consume(cs, consent_set_ref="consent:g3:no-such-record").result == "ORIGIN_NOT_ESTABLISHED"
    another_set = W.set_digest(dict(cs, request_set_ref=cs["request_set_ref"] + "-another"))
    assert _consume(cs, set_digest=another_set).result == "CONSENT_SCOPE_MISMATCH"
    assert _consume(cs, origin_proof_ref="proof:" + "0" * 32).result == "CONSENT_SCOPE_MISMATCH"
    assert _consume(cs, owner="ADC").result == "CONSENT_SCOPE_MISMATCH"
    verifies = keys.verifies
    monkeypatch.setattr(keys, "verifies", lambda record: False)  # a record this service's key does not verify
    assert _consume(cs).result == "CONSENT_ISSUER_UNVERIFIED"
    monkeypatch.setattr(keys, "verifies", verifies)
    world.rig.clock.advance(minutes=world.rig.dep.consent_validity_minutes + 1)
    assert _consume(cs).result == "CONSENT_EXPIRED"
    assert not ledger.consumed(record["consent_set_ref"], cs["intents"][0]["intent_ref"])


def test_consume_on_the_real_socket_gives_no_result_when_the_service_holds_or_refuses_or_is_absent(
        world: World, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """G3-11, with the real service's answers: a 503 from its guard, a 400 for a request off the wire, no socket."""
    from aew_g3.ledger import LedgerUnavailable

    cs, _ = _approved(world)
    bad = _consume(cs, operation_ref=None)
    assert bad.result is None and "refused the request" in (bad.held_why or "")

    def unreadable(ref: str) -> Any:
        raise LedgerUnavailable("planted: the ledger cannot be read")

    monkeypatch.setattr(world.rig.svc.ledger, "record", unreadable)
    held = _consume(cs)
    assert held.result is None and "holding every request" in (held.held_why or "")
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "absent.sock"))
    assert "systemctl status aew-g3.service" in (_consume(cs).held_why or "")


def test_no_g3_service_is_unavailable_and_says_where_to_look(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "absent.sock"))
    code, _, err = _run(world, capsys)
    error = _error(err)
    assert error["code"] == "UNAVAILABLE" and error["details"]["reason"] == "g3_unreachable"
    assert "systemctl status aew-g3.service" in error["message"] and code == 10
