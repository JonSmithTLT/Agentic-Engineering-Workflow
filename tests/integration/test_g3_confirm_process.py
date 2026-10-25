"""The G3 confirmer's client against the real service on its real sockets (A-37 G3-05, G3-10; hand-off addendum 2
§1; STG-03, G3-B). Linux only: the sockets are Unix filesystem sockets with SO_PEERCRED.

The service runs in this process (G3-A's server over sockets in a temporary directory), so its ledger and lockout stay
readable. The window is never opened: these drive ``aew_g3_confirm.core``, everything the window calls. The PIN is
the regression aid's labelled stand-in, on this throwaway service only.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from aew_g3 import CONFIRM_SOCK, REQUEST_SOCK, pinstore
from aew_g3_confirm import core
from tests.helpers import g3 as G

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="G3 is a Linux profile: Unix sockets, SO_PEERCRED")


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[G.Rig, str]]:
    from aew_g3 import server

    rig = G.make(tmp_path / "state")
    srv = server.G3Server(rig.svc, server.bind_sockets(tmp_path / "run"))
    srv.start()
    try:
        yield rig, str(tmp_path / "run" / CONFIRM_SOCK)
    finally:
        srv.stop()


def _pending(rig: G.Rig) -> str:
    status, body = rig.svc.request(G.request_body(G.fresh_proofs(G.base_set())))
    assert status == 201, body
    return body["approval_ref"]


def _failures(rig: G.Rig) -> int:
    return rig.svc.ledger.failures(pinstore.read(rig.state).pin_id)


def test_the_confirmers_two_requests_are_the_confirm_sockets_two_routes() -> None:
    from aew_g3 import server

    assert core.TIMEOUT_S == server.REQUEST_TIMEOUT_S
    routes = {(m, p.pattern) for m, p, _ in server._ROUTES[CONFIRM_SOCK]}
    assert ("GET", "^" + core.PENDING_PATH + "$") in routes
    assert any(m == "POST" and p.startswith("^" + core.DECISION_PATH + "(") for m, p in routes)
    assert len(routes) == 2


def test_the_confirmer_lists_what_is_pending_and_shows_the_services_own_rendering_whole(
        served: tuple[G.Rig, str]) -> None:
    rig, sock = served
    assert core.list_pending(sock) == []
    ref = _pending(rig)
    listed = core.list_pending(sock)
    assert [core.summary(p)[0] for p in listed] == [ref]
    assert len(core.rows(listed[0])) == len(listed[0]["rendering"])  # the service's rendering is shown, all of it


def test_approve_issues_one_record_and_a_retry_with_any_pin_is_not_found_and_counts_nothing(
        served: tuple[G.Rig, str]) -> None:
    """Addendum 2 §1, a lost response stays harmless: the retry of a decided approval is NOT_FOUND before the PIN is
    compared, issues no second record and leaves the lockout count alone; the confirmer says so and refreshes."""
    rig, sock = served
    ref = _pending(rig)
    assert core.decide(ref, G.PIN, sock) == core.APPROVED
    record = rig.svc.ledger.approval(ref)
    assert record is not None
    for pin in (G.PIN, "wrong-pin-1234"):
        assert core.decide(ref, pin, sock) == "NOT_FOUND"
    assert rig.svc.ledger.approval(ref) == record and _failures(rig) == 0
    assert "no longer pending" in core.message("NOT_FOUND") and core.list_pending(sock) == []
    declined = _pending(rig)
    assert core.decide(declined, None, sock) == core.DECLINED
    assert core.decide(declined, None, sock) == "NOT_FOUND" and core.decide(declined, G.PIN, sock) == "NOT_FOUND"
    assert rig.svc.ledger.approval(declined) is None and _failures(rig) == 0


def test_each_refusal_reaches_the_operator_as_its_own_fixed_text(served: tuple[G.Rig, str],
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    from aew_g3 import server

    rig, sock = served
    reached = {}
    ref = _pending(rig)
    reached["STRUCTURAL"] = core.decide(ref, "12345", sock)  # under the wire's 6
    for _ in range(rig.dep.lockout_after):
        reached["PIN_INCORRECT"] = core.decide(ref, "wrong-pin-1234", sock)
    reached["PIN_LOCKED"] = core.decide(ref, G.PIN, sock)
    pinstore.set_pin(rig.state, G.PIN, rig.dep)  # root's set-pin ends the lockout
    held = _pending(rig)
    rig.clock.broken = True  # G3-11: an unreadable clock holds the decision
    reached["G3_UNAVAILABLE"] = core.decide(held, None, sock)
    rig.clock.broken = False
    rig.clock.advance(minutes=rig.dep.approval_expiry_minutes)  # at expires_at, expired
    reached["APPROVAL_EXPIRED"] = core.decide(held, G.PIN, sock)
    monkeypatch.setattr(server, "peer_uid", lambda conn: os.getuid() + 1)
    reached["PEER_NOT_PERMITTED"] = core.decide("g3:approval:x", None, sock)
    with pytest.raises(core.NotPermitted) as listing:  # at login, the confirmer exits on it (addendum 4)
        core.list_pending(sock)
    assert str(listing.value) == core.MESSAGES["PEER_NOT_PERMITTED"]
    assert reached == {code: code for code in reached}, reached
    assert set(reached) | {"NOT_FOUND", core.APPROVED, core.DECLINED} == set(core.MESSAGES)  # each has its own text


@pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason="root passes every file mode")
def test_another_accounts_socket_is_not_permitted_and_a_service_not_yet_up_is_waited_for(
        served: tuple[G.Rig, str], tmp_path: Path) -> None:
    """Addendum 4: the autostart entry runs at every account's login, and confirm.sock is the operator's, mode 0600.
    On another account the confirmer exits at once, silently; a socket not there yet is a service not yet up."""
    _, sock = served
    assert core.may_use(sock) and core.list_pending(sock) == []  # control: the operator's own
    os.chmod(sock, 0)  # as another account sees the operator's 0600 socket
    try:
        assert not core.may_use(sock)
        with pytest.raises(core.NotPermitted):
            core.list_pending(sock)
    finally:
        os.chmod(sock, 0o600)
    absent = str(tmp_path / "absent.sock")
    assert core.may_use(absent)
    with pytest.raises(core.Unreachable) as down:
        core.list_pending(absent)
    assert not isinstance(down.value, core.NotPermitted)  # down is waited for, never taken for another account


def test_a_successful_pending_read_writes_no_log_line_and_a_refused_one_does(
        served: tuple[G.Rig, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Addendum 4: the confirmer reads the list every few seconds, so the service logs a successful read no more; a
    refused or failed read, and every other request, is logged as before."""
    from aew_g3 import server

    rig, sock = served
    capsys.readouterr()
    for _ in range(3):
        core.list_pending(sock)
    assert core.PENDING_PATH not in capsys.readouterr().err
    assert core.decide(_pending(rig), None, sock) == core.DECLINED
    assert "POST " + core.DECISION_PATH in capsys.readouterr().err  # control: every other request is logged
    monkeypatch.setattr(server, "peer_uid", lambda conn: os.getuid() + 1)
    with pytest.raises(core.NotPermitted):
        core.list_pending(sock)
    refused = [ln for ln in capsys.readouterr().err.splitlines() if "GET " + core.PENDING_PATH in ln]
    assert len(refused) == 1 and " 403 " in refused[0], refused


def test_no_answer_and_an_answer_without_the_g3_wire_are_unreachable_never_a_decision(tmp_path: Path) -> None:
    with pytest.raises(core.Unreachable):
        core.decide("g3:approval:x", G.PIN, str(tmp_path / "absent.sock"))
    path = str(tmp_path / "other.sock")
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(path)
    listener.listen(1)

    def answer() -> None:  # some other server: a 200 with no X-AEW-G3-Wire
        conn, _ = listener.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\n[]")
        conn.close()

    t = threading.Thread(target=answer, daemon=True)
    t.start()
    try:
        with pytest.raises(core.Unreachable):
            core.list_pending(path)
    finally:
        t.join(timeout=10)
        listener.close()


def test_a_planted_pin_never_appears_in_anything_the_confirmer_says_or_raises(
        served: tuple[G.Rig, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rig, sock = served
    planted = "planted-pin-5531"
    said: list[Any] = []
    ref = _pending(rig)
    said.append(core.decide(ref, planted, sock))
    said.append(core.decide(ref, G.PIN, sock))
    for path in (str(tmp_path / "absent.sock"), sock + ".none"):
        try:
            core.decide(ref, planted, path)
        except core.Unreachable as e:
            said.append(str(e))
            said.append(repr(e))
    said += [core.message(s) for s in said if isinstance(s, str)]
    out = capsys.readouterr()
    text = " ".join(map(str, said)) + out.out + out.err
    assert len(said) >= 8 and planted not in text and G.PIN not in text
    assert REQUEST_SOCK not in core.CONFIRM_SOCK  # control: the confirmer talks to confirm.sock only
