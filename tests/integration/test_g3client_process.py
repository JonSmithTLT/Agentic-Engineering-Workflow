"""`aew g3 request` against the real G3 service on its real socket and the real O-01 route (STG-03, G3-D; A-37 G3-02,
G3-07). Linux only: ``request.sock`` is a Unix filesystem socket with SO_PEERCRED.

The G3 service runs in this process (G3-A's server over sockets in a temporary directory) and the O-01 route is the
STG-02 slice's server on 127.0.0.1 with a synthetic bearer token. The operator's decision is made from a thread, on the
service, with the regression aid's labelled stand-in PIN: the client never sees a PIN.
"""

from __future__ import annotations

import copy
import functools
import json
import os
import socket
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from aew import g3client as C
from aew.cli.main import main
from aew.errors import OperatorAuthorizationRequired
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
    receipt, ORIGIN_NOT_ESTABLISHED until G3-C, carries the fixed note that says why."""
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
    # The client keys on the reason alone; the route's admission_state for it is the carrier's (REJECTED today).
    assert [r["reason_code"] for r in results] == ["ORIGIN_NOT_ESTABLISHED"]
    assert all(r["admission_state"] != "ADMITTED" for r in results)
    assert result["note"] == C.NOT_ESTABLISHED
    assert TOKEN not in out + err and G.PIN not in out + err


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
        conn, _ = listener.accept()
        got = b""
        while b"\r\n\r\n" not in got:  # the whole request first: a close with its body unread resets the connection
            got += conn.recv(65536)
        head, rest = got.split(b"\r\n\r\n", 1)
        length = int(next(ln.split(b":")[1] for ln in head.split(b"\r\n") if ln.lower().startswith(b"content-length")))
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


def test_no_g3_service_is_unavailable_and_says_where_to_look(
        world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "absent.sock"))
    code, _, err = _run(world, capsys)
    error = _error(err)
    assert error["code"] == "UNAVAILABLE" and error["details"]["reason"] == "g3_unreachable"
    assert "systemctl status aew-g3.service" in error["message"] and code == 10
