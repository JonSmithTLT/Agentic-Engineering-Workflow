"""The G3 client, on every platform (A-37 G3-02, G3-05, G3-07; STG-03, G3-D; the Lead's rulings of 2026-10-25): the
facts it restates, held to their owners; the sets it refuses before asking anything; the proofs it makes; the wait,
bounded by the approval's own life; the G3-07 digest check; the O-01 route on the loopback address only; and a bearer
token that appears in nothing it says. The run against the real service and the real O-01 route is
``tests/integration/test_g3client_process.py`` (Linux).
"""

from __future__ import annotations

import ast
import copy
import http.server
import json
import re
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import aew_g3
from aew import g3client as C
from aew.cli.main import main
from aew.engine.custody_ops import LEAD_SESSION, LEAD_SESSION_VARS
from aew.errors import (
    NotFound,
    OperatorAuthorizationRequired,
    PermissionDenied,
    Unavailable,
    UsageError,
    ValidationFailed,
)
from aew.stg02 import wire as W
from aew_g3 import REQUEST_SOCK, cli, deployment, wire
from tests.helpers import g3 as G

TOKEN = "token-planted-g3-client-unit"  # a synthetic token: it must appear in nothing the client says


def operator_set() -> dict[str, Any]:
    """The set as the operator gives it: the regression aid's P1, with no proofs and no consent yet."""
    cs = copy.deepcopy(G.base_set())
    cs["consent_set_ref"] = None
    for i in cs["intents"]:
        i["origin_proof_ref"] = None
    return cs


# ------------------------------------------------------------------------------------------------ restated facts
def test_the_clients_restated_facts_are_their_owners() -> None:
    assert C.REQUEST_SOCK == (cli.RUNTIME_DIR / REQUEST_SOCK).as_posix()
    assert (C.G3_HEADER, C.G3_WIRE) == (wire.HEADER, wire.WIRE)
    server = ast.parse((Path(aew_g3.__file__).parent / "server.py").read_bytes().decode())  # Linux-only to import
    timeout = next(n.value for n in server.body if isinstance(n, ast.Assign)
                   and [getattr(x, "id", None) for x in n.targets] == ["REQUEST_TIMEOUT_S"])
    assert isinstance(timeout, ast.Constant) and C.TIMEOUT_S == timeout.value
    assert C.EXPIRY_CEILING_S == deployment.TRIPWIRES["approval_expiry_minutes"][1] * 60
    assert deployment.TRIPWIRES["approval_expiry_minutes"][0] == "max"
    pattern = wire.schema()["$defs"]["Proof"]["pattern"]
    shortest = re.fullmatch(r"\^proof:\[0-9a-f\]\{(\d+),\d+\}\$", pattern)
    assert shortest and shortest.group(1) == str(2 * C.PROOF_BYTES)


# ------------------------------------------------------------------------------------------------ the set (ruling 1)
def test_a_complete_protected_set_with_no_proofs_and_no_consent_is_accepted() -> None:
    cs = operator_set()
    assert C.check_set(cs) is cs  # control: the shape every refusal below departs from


@pytest.mark.parametrize("edit, reason", [
    ("not_an_object", "not_a_command_set"),
    ("no_intents", "not_a_command_set"),
    ("delegated_member", "member_not_protected"),
    ("successor_member", "member_not_protected"),
    ("member_not_an_object", "member_not_protected"),
    ("proof_already_set", "origin_proof_ref_set"),
    ("consent_already_set", "consent_set_ref_set"),
])
def test_a_set_the_client_cannot_ask_for_is_refused_whole_naming_what_and_the_fix(edit: str, reason: str) -> None:
    cs: Any = operator_set()
    if edit == "not_an_object":
        cs = [cs]
    elif edit == "no_intents":
        cs["intents"] = []
    elif edit == "delegated_member":
        cs["intents"].append({**cs["intents"][0], "action": "CONTINUE_ELIGIBLE_WORK"})
    elif edit == "successor_member":
        cs["intents"][0]["action"] = "REAFFIRM_ELIGIBLE_CHILD_GRANTS"
    elif edit == "member_not_an_object":
        cs["intents"].append("CONFIRM_LEAD_ATTACHMENT")
    elif edit == "proof_already_set":
        cs["intents"][0]["origin_proof_ref"] = "proof:" + "a" * 32
    else:
        cs["consent_set_ref"] = "consent:early"
    with pytest.raises(ValidationFailed) as e:
        C.check_set(cs)
    assert e.value.details["reason"] == reason
    if reason == "member_not_protected":
        assert "Submit them apart" in e.value.message
    if reason in ("origin_proof_ref_set", "consent_set_ref_set"):
        assert "to null" in e.value.message


def test_each_member_gets_a_fresh_proof_from_a_secure_source_in_the_wires_form() -> None:
    pattern = wire.schema()["$defs"]["Proof"]["pattern"]
    one, two = C.with_proofs(operator_set()), C.with_proofs(operator_set())
    proofs = [i["origin_proof_ref"] for s in (one, two) for i in s["intents"]]
    assert all(re.fullmatch(pattern, p) for p in proofs)
    assert len(set(proofs)) == len(proofs)  # fresh per member and per request
    assert one["consent_set_ref"] is None and not wire.wire_errors("ApprovalRequest",
                                                                   {"wire_version": C.G3_WIRE, "command_set": one})
    drawn: list[int] = []
    C.with_proofs(operator_set(), token=lambda n: drawn.append(n) or "0" * (2 * n))
    assert drawn == [C.PROOF_BYTES] * len(operator_set()["intents"])  # each from the source it is given


def test_a_set_that_is_not_a_valid_command_set_once_proved_is_refused_before_anything_is_asked() -> None:
    cs = operator_set()
    cs["intents"][0]["target"]["unexpected"] = "x"
    with pytest.raises(ValidationFailed) as e:
        C.with_proofs(C.check_set(cs))
    assert e.value.details["reason"] == "command_set_schema" and e.value.details["errors"]


# ------------------------------------------------------------------------------------------------ G3-07
def test_the_set_is_submitted_only_when_the_records_digest_is_the_digest_of_that_set() -> None:
    proved = C.with_proofs(operator_set())
    out = copy.deepcopy(proved)
    out["consent_set_ref"] = "consent:approved-one"
    record = {"consent_set_ref": "consent:approved-one", "set_digest": W.set_digest(out)}
    assert C.approved_set(proved, record) == out and proved["consent_set_ref"] is None  # unchanged but for the ref
    changed = copy.deepcopy(proved)
    changed["intents"][0]["target"]["requested_lead_ref"] = "lead:other"  # one leaf moved after the approval
    with pytest.raises(ValidationFailed) as e:
        C.approved_set(changed, record)
    assert e.value.details["reason"] == "set_digest_mismatch"


# ------------------------------------------------------------------------------------------------ the wait
class _Service:
    """A stand-in for request.sock's GET: the states it answers in turn, the last repeated."""

    def __init__(self, states: list[Any]) -> None:
        self.states, self.calls = states, 0

    def __call__(self, sock_path: str | None, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        assert self.calls <= 2 * C.EXPIRY_CEILING_S, "the wait never ended"  # a failure, never a hang
        if state == 404:
            return 404, {"code": "NOT_FOUND"}
        reply: dict[str, Any] = {"state": state}
        if state == "APPROVED":
            reply["consent_record"] = {"consent_set_ref": "consent:one"}
        return 200, reply


def _wait(monkeypatch: pytest.MonkeyPatch, states: list[Any], life_s: float = 60) -> tuple[Any, _Service, float]:
    svc = _Service(states)
    monkeypatch.setattr(C, "_g3", svc)
    clock = [datetime(2026, 10, 25, 12, tzinfo=UTC)]
    pending = {"approval_ref": "approval:one", "expires_at": W.utc(clock[0] + timedelta(seconds=life_s))}
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        clock[0] += timedelta(seconds=s)

    try:
        return C.await_decision(pending, now=lambda: clock[0], sleep=sleep), svc, sum(slept)
    except Exception as e:  # noqa: BLE001 - the test inspects what the wait raised
        return e, svc, sum(slept)


@pytest.mark.parametrize("status, body", [
    (201, {"expires_at": "2026-10-25T12:00:00Z"}),
    (201, {"approval_ref": None}),
    (200, {"approval_ref": "approval:one", "expires_at": "2026-10-25T12:00:00Z"}),
    (400, {"code": "STRUCTURAL"}),
])
def test_only_a_created_pending_approval_with_its_ref_is_waited_for(
        monkeypatch: pytest.MonkeyPatch, status: int, body: Any) -> None:
    monkeypatch.setattr(C, "_g3", lambda *a: (201, {"approval_ref": "approval:one"}))
    assert C.request_approval(operator_set())["approval_ref"] == "approval:one"  # control
    monkeypatch.setattr(C, "_g3", lambda *a: (status, body))
    with pytest.raises(ValidationFailed) as e:
        C.request_approval(operator_set())
    assert e.value.details["reason"] == "g3_refused"


def test_a_pending_approval_with_no_readable_expiry_is_not_g3s_and_nothing_is_waited_for(
        monkeypatch: pytest.MonkeyPatch) -> None:
    svc = _Service(["PENDING"])
    monkeypatch.setattr(C, "_g3", svc)
    for pending in ({"approval_ref": "approval:one"}, {"approval_ref": "approval:one", "expires_at": "soon"},
                    {"approval_ref": "approval:one", "expires_at": None}):
        with pytest.raises(Unavailable) as e:
            C.await_decision(pending, sleep=lambda s: None)
        assert e.value.details["reason"] == "g3_not_g3"
    assert svc.calls == 0


def test_the_wait_returns_the_record_once_the_operator_approves(monkeypatch: pytest.MonkeyPatch) -> None:
    out, svc, _ = _wait(monkeypatch, ["PENDING", "PENDING", "APPROVED"])
    assert out == {"consent_set_ref": "consent:one"} and svc.calls == 3


@pytest.mark.parametrize("state, reason", [("DECLINED", "declined"), ("EXPIRED", "expired"), (404, "approval_lost")])
def test_a_decline_an_expiry_or_a_lost_approval_ends_the_wait_and_submits_nothing(
        monkeypatch: pytest.MonkeyPatch, state: Any, reason: str) -> None:
    out, svc, waited = _wait(monkeypatch, ["PENDING", state])
    assert isinstance(out, OperatorAuthorizationRequired) and out.details["reason"] == reason
    assert svc.calls == 2 and waited == C.POLL_S  # at once, on the answer: never at the deadline
    assert "nothing was" in out.message.lower()


@pytest.mark.parametrize("status, code, error, reason", [
    (403, "PEER_NOT_PERMITTED", PermissionDenied, "g3_peer_not_permitted"),
    (503, "G3_UNAVAILABLE", Unavailable, "g3_unavailable"),
    (503, None, Unavailable, "g3_unavailable"),
    (400, "MEMBER_PROOF_INVALID", ValidationFailed, "g3_refused"),
])
def test_each_refusal_of_the_g3_service_is_typed_by_its_code(
        status: int, code: str | None, error: type[Exception], reason: str) -> None:
    refused = C._g3_refusal(status, {"code": code} if code else None)
    assert type(refused) is error and refused.details["reason"] == reason  # type: ignore[attr-defined]
    if reason == "g3_refused":
        assert refused.details["g3_code"] == code  # type: ignore[attr-defined]


def test_the_wait_ends_with_the_approvals_life_and_never_later_than_g3_02s_ceiling(
        monkeypatch: pytest.MonkeyPatch) -> None:
    out, svc, waited = _wait(monkeypatch, ["PENDING"], life_s=30)
    assert isinstance(out, OperatorAuthorizationRequired) and out.details["reason"] == "expired"
    assert 30 + C.GRACE_S <= waited <= 30 + C.GRACE_S + C.POLL_S and svc.calls >= 30
    out, _, waited = _wait(monkeypatch, ["PENDING"], life_s=24 * 3600)  # a service that names a far expiry
    assert isinstance(out, OperatorAuthorizationRequired) and waited <= C.EXPIRY_CEILING_S + C.GRACE_S + C.POLL_S


# ------------------------------------------------------------------------------------------------ the O-01 route
@pytest.mark.parametrize("url", ["http://127.0.0.1:4261", "http://localhost:4261/", "http://[::1]:4261"])
def test_the_o01_route_is_taken_only_on_this_hosts_loopback_address(url: str) -> None:
    assert C.o01_target(url)[1] == 4261


@pytest.mark.parametrize("url", ["https://127.0.0.1:4261", "http://example.com:4261", "http://10.0.0.5:4261",
                                 "http://user:pw@127.0.0.1:4261", "http://127.0.0.1:4261/o01", "http://127.0.0.1:x",
                                 "http://127.0.0.1:4261/?q=1", "http://127.0.0.1:4261#f", "http://127.0.0.1:99999"])
def test_any_other_o01_url_is_refused_before_a_token_is_read(url: str) -> None:
    with pytest.raises(UsageError) as e:
        C.o01_target(url)
    assert e.value.details["reason"] == "o01_not_loopback"


def test_the_token_file_holds_one_token_on_one_line(tmp_path: Path) -> None:
    f = tmp_path / "token"
    f.write_bytes((TOKEN + "\n").encode())
    assert C.read_token(str(f)) == TOKEN
    with pytest.raises(NotFound) as missing:
        C.read_token(str(tmp_path / "absent"))
    assert missing.value.details["reason"] == "token_file_missing"
    for bad, reason in ((b"", "token_file_malformed"), (b"two tokens", "token_file_malformed"),
                        (b"\n\n", "token_file_malformed"), (TOKEN.encode() + b"\xff", "token_file_unreadable")):
        f.write_bytes(bad)
        with pytest.raises(UsageError) as e:
            C.read_token(str(f))
        assert e.value.details["reason"] == reason and TOKEN not in e.value.message


@pytest.fixture
def route() -> Iterator[tuple[str, list[dict[str, Any]], list[tuple[int, Any]]]]:
    """A stand-in O-01 route on 127.0.0.1: it answers each request with the next (status, body) it is given, and
    keeps what it was sent."""
    seen: list[dict[str, Any]] = []
    answers: list[tuple[int, Any]] = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server's name
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append({"headers": dict(self.headers), "body": json.loads(body)})
            status, out = answers.pop(0)
            data = json.dumps(out).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - http.server's name
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}", seen, answers
    finally:
        srv.shutdown()
        srv.server_close()


def test_the_set_is_submitted_with_the_o01_wire_and_the_token_in_its_one_header(route: Any) -> None:
    url, seen, answers = route
    receipt = {"results": [{"intent_ref": "intent:attach_lead", "admission_state": "REJECTED",
                            "reason_code": "ORIGIN_NOT_ESTABLISHED"}]}
    answers.append((202, receipt))
    cs = {"consent_set_ref": "consent:one", "intents": []}
    assert C.submit(cs, url, TOKEN) == receipt
    sent = seen[0]
    assert sent["body"] == cs and sent["headers"][W.O01_HEADER] == W.O01_VERSION
    assert sent["headers"]["Authorization"] == "Bearer " + TOKEN
    assert C.note(receipt) == C.NOT_ESTABLISHED and "Nothing was admitted" in C.NOT_ESTABLISHED
    assert C.note({"results": [{"admission_state": "ADMITTED", "reason_code": None}]}) is None


@pytest.mark.parametrize("status, body, error, reason", [
    (401, {"code": "authentication_unqualified"}, PermissionDenied, "o01_unauthenticated"),
    (400, {"code": "invalid_request"}, ValidationFailed, "o01_refused"),
    (503, {"code": "owner_unavailable"}, Unavailable, "o01_unavailable"),
    (202, "not a receipt", ValidationFailed, "o01_refused"),
    (200, {"results": []}, ValidationFailed, "o01_refused"),  # a receipt's shape, but not the route's 202
])
def test_every_refusal_of_the_o01_route_is_typed_and_the_token_is_in_none_of_them(
        route: Any, status: int, body: Any, error: type, reason: str) -> None:
    url, _, answers = route
    answers.append((status, body))
    with pytest.raises(error) as e:
        C.submit({"intents": []}, url, TOKEN)
    assert e.value.details["reason"] == reason and "approval is unused" in e.value.message
    assert TOKEN not in repr(e.value) + str(e.value) + json.dumps(e.value.to_dict())


def test_a_route_that_does_not_answer_is_unavailable_and_the_token_is_not_in_it() -> None:
    import socket

    with socket.socket() as s:  # a port nothing listens on
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(Unavailable) as e:
        C.submit({"intents": []}, f"http://127.0.0.1:{port}", TOKEN)
    assert e.value.details["reason"] == "o01_unreachable" and TOKEN not in repr(e.value) + str(e.value)


# ------------------------------------------------------------------------------------------------ the command
def test_a_lead_session_is_refused_before_anything_is_read_with_the_operators_route(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruling 3: forbidden to the Lead, kept out today by the session's environment, before the set or the token is
    read; the refusal names the operator's route."""
    for var in LEAD_SESSION_VARS:
        monkeypatch.delenv(var, raising=False)
    argv = ["g3", "request", str(tmp_path / "absent.json"), "--o01", "http://127.0.0.1:9", "--token-file",
            str(tmp_path / "absent-token")]
    assert main(argv) == NotFound.exit_code  # control: outside a Lead session it gets as far as the token file
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "NOT_FOUND"
    monkeypatch.setenv(LEAD_SESSION_VARS[0], "x")
    assert main(argv) == PermissionDenied.exit_code
    err = json.loads(capsys.readouterr().err)["error"]
    assert err["code"] == "PERMISSION_DENIED" and err["details"]["reason"] == LEAD_SESSION
    assert err["details"]["variables"] == [LEAD_SESSION_VARS[0]] and "Ask the operator to run it" in err["message"]
