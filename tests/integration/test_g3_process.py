"""The real G3 service process over its real Unix sockets (A-37 G3-02 to G3-11, G3-14; STG-03, G3-A). Linux only.

Each test installs the service into a temporary root laid out as root installs it (``<root>/aew_g3``,
``<root>/etc/deployment.json``), runs ``python -m aew_g3 serve`` as its own process, and talks HTTP to it over
``request.sock`` and ``confirm.sock`` as the clients and the confirmer will. The confirmer's window is never opened: the
tests send its ``ApprovalDecision`` themselves. The PIN is a labelled stand-in.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from aew_g3 import CONFIRM_SOCK, REQUEST_SOCK, ROOT, deployment, pinstore, wire
from tests.helpers import g3 as G

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="G3 is a Linux profile: Unix sockets, SO_PEERCRED")
SRC = G.REPO / "src"
READY = "aew-g3: ready"
START_WAIT_S = 60.0


class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path: Path) -> None:
        super().__init__("localhost", timeout=30)
        self._path = str(path)

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(30)
        s.connect(self._path)
        self.sock = s


def call(sock: Path, method: str, path: str, body: Any = None) -> tuple[int, Any, dict[str, str]]:
    conn = _UnixHTTP(sock)
    try:
        data = None if body is None else json.dumps(body).encode()
        conn.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        r = conn.getresponse()
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None), dict(r.getheaders())
    finally:
        conn.close()


def raw_call(sock: Path, data: bytes, *, then: bytes = b"", pause_s: float = 0.0) -> tuple[int, Any, dict[str, str]]:
    """Sends bytes no http.client would (a request http.server refuses itself); with ``then``, sends ``data``, checks
    that no reply has come within ``pause_s``, then sends the rest. Returns the reply as ``call`` does."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(30)
    try:
        s.connect(str(sock))
        s.sendall(data)
        if then:
            s.settimeout(pause_s)
            with pytest.raises(TimeoutError):
                s.recv(1)  # the service waits for the body it was told of, and says nothing yet
            s.settimeout(30)
            s.sendall(then)
        out = b""
        try:
            while chunk := s.recv(65536):
                out += chunk
        except ConnectionResetError:  # Linux: the service closed with bytes of ours it never read, after its reply
            assert out, "the reply came first"
    finally:
        s.close()
    head, _, body = out.partition(b"\r\n\r\n")
    status_line, *header_lines = head.decode("latin-1").split("\r\n")
    headers = dict(line.split(": ", 1) for line in header_lines)
    return int(status_line.split()[1]), (json.loads(body) if body else None), headers


def install(base: Path, **over: Any) -> Path:
    """A root laid out as /opt/aew-g3 is (G3-14), with the deployment's values."""
    root = base / "opt-aew-g3"
    shutil.copytree(ROOT / "aew_g3", root / "aew_g3", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "etc").mkdir(parents=True)
    values = {k: v for k, v in G.shipped_values().items() if k not in over}
    values.update({k: v for k, v in over.items() if v is not None})
    (root / "etc" / "deployment.json").write_bytes(json.dumps(values).encode())
    return root


class Service:
    """One service process: its owner, bounded waits, and a group kill so nothing outlives the test."""

    def __init__(self, base: Path, root: Path, *, argv_prefix: list[str] | None = None,
                 pass_fds: tuple[int, ...] = ()) -> None:
        self.state, self.run = base / "state", base / "run"
        self.state.mkdir(exist_ok=True)
        self.log = base / f"service-{time.monotonic_ns()}.log"
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(root), str(SRC)]), PYTHONDONTWRITEBYTECODE="1")
        argv = [sys.executable, "-m", "aew_g3", "serve", "--state-dir", str(self.state), "--runtime-dir",
                str(self.run)]
        with self.log.open("wb") as out:
            self.proc = subprocess.Popen((argv_prefix or []) + argv, stdout=out, stderr=subprocess.STDOUT, env=env,
                                         cwd=base, start_new_session=True, pass_fds=pass_fds)

    @property
    def request(self) -> Path:
        return self.run / REQUEST_SOCK

    @property
    def confirm(self) -> Path:
        return self.run / CONFIRM_SOCK

    def text(self) -> str:
        return self.log.read_bytes().decode("utf-8", "replace")

    def wait_ready(self) -> Service:
        deadline = time.monotonic() + START_WAIT_S
        while READY not in self.text():
            if self.proc.poll() is not None or time.monotonic() > deadline:
                self.kill()
                raise AssertionError(f"the service did not start: {self.text()[-2000:]}")
            time.sleep(0.05)
        return self

    def stop(self) -> int:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                return self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.kill()
        return self.proc.wait(timeout=15)

    def kill(self) -> None:
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.proc.wait(timeout=15)


@pytest.fixture
def services() -> Iterator[list[Service]]:
    started: list[Service] = []
    yield started
    for s in started:
        s.kill()


def start(services: list[Service], base: Path, root: Path | None = None, *, pin: bool = True,
          **kw: Any) -> Service:
    root = root or install(base)
    if pin:
        (base / "state").mkdir(exist_ok=True)
        pinstore.set_pin(base / "state", G.PIN, deployment.Deployment(**G.shipped_values()))
    s = Service(base, root, **kw)
    services.append(s)
    return s.wait_ready()


def approve(svc: Service, cs: dict[str, Any], pin: str = G.PIN) -> tuple[dict[str, Any], tuple[int, Any, Any]]:
    status, pending, _ = call(svc.request, "POST", "/g3/v1/approval-requests", G.request_body(cs))
    assert status == 201, pending
    return pending, call(svc.confirm, "POST", f"/g3/v1/approvals/{pending['approval_ref']}",
                         {"decision": "APPROVE", "pin": pin})


# ------------------------------------------------------------------------------------------------ the routes
def test_the_real_service_runs_p1_over_its_two_sockets_and_every_response_carries_the_wire_header(
        tmp_path: Path, services: list[Service]) -> None:
    svc = start(services, tmp_path)
    responses = []
    status, pending, h = call(svc.request, "POST", "/g3/v1/approval-requests", G.P1["approval_request"])
    responses.append(h)
    assert status == 201 and pending["set_digest"] == G.P1["pending"]["set_digest"]
    assert pending["rendering"] == [ln for ln in G.P1["pending"]["rendering"] if ln["source"]["kind"] != "OWNER_FACT"]
    status, listed, h = call(svc.confirm, "GET", "/g3/v1/pending")
    responses.append(h)
    assert status == 200 and [p["approval_ref"] for p in listed] == [pending["approval_ref"]]
    ref = pending["approval_ref"]
    status, record, h = call(svc.confirm, "POST", f"/g3/v1/approvals/{ref}", {"decision": "APPROVE", "pin": G.PIN})
    responses.append(h)
    assert status == 200 and record["set_digest"] == G.P1["consent_record"]["set_digest"]
    status, got, h = call(svc.request, "GET", f"/g3/v1/approval-requests/{ref}")
    responses.append(h)
    assert status == 200 and got["state"] == "APPROVED" and got["consent_record"] == record
    req = dict(G.P1["consume_request"], consent_set_ref=record["consent_set_ref"])
    for expected in ("CONSUMED", "CONSENT_ALREADY_USED"):
        status, res, h = call(svc.request, "POST", "/g3/v1/consume", req)
        responses.append(h)
        assert status == 200 and res["result"] == expected
    # Each socket serves only its own routes.
    for sock, method, path in ((svc.request, "GET", "/g3/v1/pending"), (svc.confirm, "POST", "/g3/v1/consume"),
                               (svc.confirm, "GET", f"/g3/v1/approval-requests/{ref}"),
                               (svc.request, "POST", f"/g3/v1/approvals/{ref}"), (svc.request, "GET", "/")):
        status, body, h = call(sock, method, path, {} if method == "POST" else None)
        responses.append(h)
        assert (status, body["code"]) == (404, "NOT_FOUND"), (sock.name, method, path)
    status, body, h = call(svc.request, "POST", "/g3/v1/consume", None)
    responses.append(h)
    assert (status, body["code"]) == (400, "STRUCTURAL")
    assert all(h.get("X-AEW-G3-Wire") == "g3-0.6.1-candidate" for h in responses)


def test_the_service_publishes_its_keys_and_issuer_ref_and_keeps_its_state_to_itself(
        tmp_path: Path, services: list[Service]) -> None:
    from aew_g3.service import issuer_ref_from_machine_id

    svc = start(services, tmp_path)
    keys = svc.run / "keys"
    issuer = (keys / "issuer_ref").read_text().strip()
    assert issuer == issuer_ref_from_machine_id(Path("/etc/machine-id").read_text())
    assert f"issuer_ref={issuer}" in svc.text()
    pubs = list(keys.glob("*.pub"))
    assert len(pubs) == 1 and f"key_id={pubs[0].stem}" in svc.text()
    assert all(p.stat().st_mode & 0o777 == 0o644 for p in [*pubs, keys / "issuer_ref"])
    for sock in (svc.request, svc.confirm):
        assert sock.is_socket() and sock.stat().st_mode & 0o777 == 0o600
    for f in ("signing-key.pem", "ledger.sqlite3", "pin.json"):
        assert (svc.state / f).stat().st_mode & 0o777 == 0o600, f
    limits = Path(f"/proc/{svc.proc.pid}/limits").read_text()
    core = next(line for line in limits.splitlines() if line.startswith("Max core file size"))
    assert core.split()[4:6] == ["0", "0"], core  # no core dump can hold a PIN


def test_a_socket_activated_service_serves_on_the_sockets_systemd_passes(tmp_path: Path,
                                                                         services: list[Service]) -> None:
    run = tmp_path / "activated"
    run.mkdir()
    socks = []
    for name in (REQUEST_SOCK, CONFIRM_SOCK):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(str(run / name))
        os.chmod(run / name, 0o600)
        s.listen(4)
        socks.append(s)
    fds = tuple(s.fileno() for s in socks)
    # What systemd does: the sockets at descriptors 3 and 4, LISTEN_FDS, and LISTEN_PID naming the service itself.
    shim = ("import os, sys; a, b = int(sys.argv[1]), int(sys.argv[2]); os.dup2(a, 3); os.dup2(b, 4); "
            "os.environ.update(LISTEN_FDS='2', LISTEN_PID=str(os.getpid())); os.execv(sys.argv[3], sys.argv[3:])")
    svc = start(services, tmp_path, argv_prefix=[sys.executable, "-c", shim, str(fds[0]), str(fds[1])], pass_fds=fds)
    for s in socks:
        s.close()
    assert not (svc.run / REQUEST_SOCK).exists(), "it bound nothing of its own"
    assert f"operator_uid={os.getuid()}" in svc.text()
    status, listed, _ = call(run / CONFIRM_SOCK, "GET", "/g3/v1/pending")
    assert status == 200 and listed == []
    status, body, _ = call(run / REQUEST_SOCK, "POST", "/g3/v1/approval-requests",
                           G.request_body(G.fresh_proofs(G.base_set())))
    assert status == 201, body


# ------------------------------------------------------------------------------------------------ G3-10 peers
LONG_LINE = b"GET /" + b"a" * 70_000 + b" HTTP/1.0\r\n\r\n"  # over http.server's 64 KiB request line
# Requests http.server refuses before any do_ method runs (review of #269, m1), each with the operator's Problem.
REFUSED_BY_HTTP_SERVER = [("PUT", b"PUT /g3/v1/consume HTTP/1.0\r\nContent-Length: 2\r\n\r\n{}", "NOT_FOUND"),
                          ("HEAD", b"HEAD /g3/v1/pending HTTP/1.0\r\n\r\n", "NOT_FOUND"),
                          ("malformed line", b"NOT-HTTP\r\n\r\n", "STRUCTURAL"),
                          ("bad version", b"GET /g3/v1/pending HTTP/9.9\r\n\r\n", "STRUCTURAL"),
                          ("line over 64 KiB", LONG_LINE, "STRUCTURAL")]


@pytest.fixture
def in_process(tmp_path: Path) -> Iterator[tuple[G.Rig, Path]]:
    """The service's own server over real sockets, in this process: its ledger and lockout stay readable."""
    from aew_g3 import server

    rig = G.make(tmp_path / "state")
    srv = server.G3Server(rig.svc, server.bind_sockets(tmp_path / "run"))
    srv.start()
    try:
        assert srv.operator_uid == os.getuid()
        yield rig, tmp_path / "run"
    finally:
        srv.stop()


def test_a_peer_whose_uid_is_not_the_operators_or_cannot_be_read_is_refused_on_every_route(
        in_process: tuple[G.Rig, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    """Every request, routed or not, and those http.server refuses itself, is refused PEER_NOT_PERMITTED with the wire
    header: the peer check precedes routing (G3-10; review of #269, m1 and m4 B4)."""
    from aew_g3 import server

    rig, run = in_process
    new = G.request_body(G.fresh_proofs(G.base_set()))
    routes = [(REQUEST_SOCK, "POST", "/g3/v1/approval-requests", new),
              (REQUEST_SOCK, "GET", "/g3/v1/approval-requests/g3:approval:x", None),
              (REQUEST_SOCK, "POST", "/g3/v1/consume", {}),
              (CONFIRM_SOCK, "GET", "/g3/v1/pending", None),
              (CONFIRM_SOCK, "POST", "/g3/v1/approvals/g3:approval:x", {"decision": "APPROVE", "pin": G.PIN}),
              (REQUEST_SOCK, "GET", "/g3/v1/no-such-route", None)]
    for label, uid in (("another UID", os.getuid() + 1), ("unreadable credentials", None), ("root", 0)):
        monkeypatch.setattr(server, "peer_uid", lambda conn, uid=uid: uid)
        for sock, method, path, body in routes:
            status, out, h = call(run / sock, method, path, body)
            assert (status, out["code"]) == (403, "PEER_NOT_PERMITTED"), (label, path)
            assert h["X-AEW-G3-Wire"] == wire.WIRE
        for case, data, _ in REFUSED_BY_HTTP_SERVER:
            status, out, h = raw_call(run / REQUEST_SOCK, data)
            assert (status, out["code"], h.get(wire.HEADER)) == (403, "PEER_NOT_PERMITTED", wire.WIRE), (label, case)
    monkeypatch.undo()
    # Controls, the operator: a route answers, an unknown path is NOT_FOUND, and http.server's refusals are the wire's.
    assert call(run / CONFIRM_SOCK, "GET", "/g3/v1/pending")[0] == 200
    assert call(run / REQUEST_SOCK, "GET", "/g3/v1/no-such-route")[1]["code"] == "NOT_FOUND"
    for case, data, code in REFUSED_BY_HTTP_SERVER:
        status, out, h = raw_call(run / REQUEST_SOCK, data)
        assert (status, out, h.get(wire.HEADER)) == (*wire.problem(code), wire.WIRE), case
    assert rig.svc.ledger.approval("g3:approval:x") is None and not rig.svc.pending


def test_a_refusal_waits_for_the_body_the_client_declared_so_the_client_always_receives_it(
        in_process: tuple[G.Rig, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic (review of #269, M2): the headers go first, the service says nothing until the declared body has
    come, then refuses. Answering earlier would close on a client still sending, which then loses the refusal."""
    from aew_g3 import server

    _, run = in_process
    body = json.dumps(G.request_body(G.fresh_proofs(G.base_set()))).encode()
    head = f"POST /g3/v1/approval-requests HTTP/1.0\r\nContent-Length: {len(body)}\r\n\r\n".encode()
    monkeypatch.setattr(server, "peer_uid", lambda conn: os.getuid() + 1)
    assert raw_call(run / REQUEST_SOCK, head, then=body, pause_s=0.5)[1]["code"] == "PEER_NOT_PERMITTED"
    monkeypatch.undo()
    for data in (b"POST /g3/v1/no-such-route HTTP/1.0\r\nContent-Length: 2\r\n\r\n",
                 b"PUT /g3/v1/consume HTTP/1.0\r\nContent-Length: 2\r\n\r\n"):
        assert raw_call(run / REQUEST_SOCK, data, then=b"{}", pause_s=0.5)[1]["code"] == "NOT_FOUND", data
    assert raw_call(run / REQUEST_SOCK, head + body)[0] == 201  # control: a whole request is answered at once


def test_a_client_that_declares_a_body_and_never_sends_it_holds_a_thread_only_until_the_request_timeout(
        in_process: tuple[G.Rig, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    """The drain above waits for the declared body, so a stalled client is dropped at the handler's socket timeout
    rather than holding its thread for ever (review of #269, M2). The timeout is shortened to keep the test short."""
    from aew_g3 import server

    _, run = in_process
    assert server._Handler.timeout == server.REQUEST_TIMEOUT_S  # the shipped bound, before the test shortens it
    monkeypatch.setattr(server._Handler, "timeout", 1)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(10)
    try:
        s.connect(str(run / REQUEST_SOCK))
        s.sendall(b"POST /g3/v1/consume HTTP/1.0\r\nContent-Length: 100\r\n\r\n{")
        began = time.monotonic()
        assert s.recv(1) == b"", "closed with no reply"
        assert time.monotonic() - began < 8
    finally:
        s.close()
    monkeypatch.undo()
    assert call(run / CONFIRM_SOCK, "GET", "/g3/v1/pending")[0] == 200  # control: the service still answers


# ------------------------------------------------------------------------------------------------ malformed bodies
def call_bytes(sock: Path, path: str, data: bytes) -> tuple[int, Any]:
    conn = _UnixHTTP(sock)
    try:
        conn.request("POST", path, body=data, headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        return r.status, json.loads(r.read())
    finally:
        conn.close()


def test_a_body_of_max_body_bytes_is_read_and_one_byte_more_is_structural_and_never_parsed(
        in_process: tuple[G.Rig, Path]) -> None:
    """The bound on what the service reads (review of #269, m4 B6): over it, the request is refused before parsing, so
    the consume it holds never happens; at it, the same consume is served."""
    from aew_g3.server import MAX_BODY

    rig, run = in_process
    cs = G.fresh_proofs(G.base_set())
    _, record = G.approved(rig.svc, cs)
    req = json.dumps(G.consume_req(cs, record)).encode()

    def padded(n: int) -> bytes:
        return req + b" " * (n - len(req))  # JSON's own whitespace: the same request at any length

    assert call_bytes(run / REQUEST_SOCK, "/g3/v1/consume", padded(MAX_BODY + 1)) == wire.problem("STRUCTURAL")
    assert not rig.svc.ledger.consumed(record["consent_set_ref"], cs["intents"][0]["intent_ref"])
    status, out = call_bytes(run / REQUEST_SOCK, "/g3/v1/consume", padded(MAX_BODY))
    assert (status, out["result"]) == (200, "CONSUMED")


def test_a_declared_body_over_max_body_is_read_no_further_than_max_body_before_the_refusal(
        in_process: tuple[G.Rig, Path]) -> None:
    """The drain is bounded (quick check of #269, Q2 C2): a client declares four times MAX_BODY and sends one byte past
    MAX_BODY, then waits. The service reads MAX_BODY bytes and refuses at once; reading the declared length would wait
    for bytes that never come, until the request timeout."""
    from aew_g3.server import MAX_BODY, REQUEST_TIMEOUT_S

    _, run = in_process
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(REQUEST_TIMEOUT_S / 3)  # well inside the timeout, so only a bounded read answers in time
    try:
        s.connect(str(run / REQUEST_SOCK))
        s.sendall(f"POST /g3/v1/consume HTTP/1.0\r\nContent-Length: {4 * MAX_BODY}\r\n\r\n".encode())
        s.sendall(b" " * (MAX_BODY + 1))
        out = b""
        try:
            while chunk := s.recv(65536):
                out += chunk
        except ConnectionResetError:  # the byte past MAX_BODY was never read
            assert out, "the reply came first"
    finally:
        s.close()
    head, _, body = out.partition(b"\r\n\r\n")
    assert int(head.split()[1]) == 400 and json.loads(body)["code"] == "STRUCTURAL"


def test_a_pin_that_is_not_utf8_and_a_body_nested_past_the_parser_are_structural_and_the_service_still_answers(
        in_process: tuple[G.Rig, Path]) -> None:
    """Both once killed the handler thread, so the client got no reply (review of #269, m2). A lone surrogate is a
    valid wire string no UTF-8 encoder takes; neither counts toward the lockout or decides the approval."""
    rig, run = in_process
    status, pending, _ = call(run / REQUEST_SOCK, "POST", "/g3/v1/approval-requests",
                              G.request_body(G.fresh_proofs(G.base_set())))
    assert status == 201
    ref = pending["approval_ref"]
    status, out, _ = call(run / CONFIRM_SOCK, "POST", f"/g3/v1/approvals/{ref}",
                          {"decision": "APPROVE", "pin": chr(0xD800) + G.PIN})
    assert (status, out) == wire.problem("STRUCTURAL")
    deep = b"[" * 100_000 + b"]" * 100_000
    for sock, path in ((REQUEST_SOCK, "/g3/v1/approval-requests"), (REQUEST_SOCK, "/g3/v1/consume"),
                       (CONFIRM_SOCK, f"/g3/v1/approvals/{ref}")):
        assert call_bytes(run / sock, path, deep) == wire.problem("STRUCTURAL"), path
    assert call(run / REQUEST_SOCK, "GET", f"/g3/v1/approval-requests/{ref}")[1]["state"] == "PENDING"
    status, _, _ = call(run / CONFIRM_SOCK, "POST", f"/g3/v1/approvals/{ref}", {"decision": "APPROVE", "pin": G.PIN})
    assert status == 200, "control: nothing counted toward the lockout, and the service still answers"


# ------------------------------------------------------------------------------------------------ G3-14 start
@pytest.mark.parametrize(("label", "over", "error"), [
    ("approval expiry 11", {"approval_expiry_minutes": 11}, "BEYOND_TRIPWIRE:approval_expiry_minutes"),
    ("consent validity 16", {"consent_validity_minutes": 16}, "BEYOND_TRIPWIRE:consent_validity_minutes"),
    ("PIN minimum 5", {"pin_min_length": 5}, "BEYOND_TRIPWIRE:pin_min_length"),
    ("lockout 6", {"lockout_after": 6}, "BEYOND_TRIPWIRE:lockout_after"),
    ("lockout missing", {"lockout_after": None}, "MISSING:lockout_after"),
], ids=["approval_expiry", "consent_validity", "pin_min_length", "lockout_after", "lockout_missing"])
def test_the_service_refuses_to_start_on_a_deployment_value_beyond_its_tripwire_or_missing(
        tmp_path: Path, label: str, over: dict[str, Any], error: str) -> None:
    svc = Service(tmp_path, install(tmp_path, **over))
    try:
        code = svc.proc.wait(timeout=START_WAIT_S)
    finally:
        svc.kill()
    out = json.loads(svc.text().strip().splitlines()[-1])
    assert code != 0 and out["code"] == "VALIDATION_FAILED", label
    assert out["details"]["reason"] == "DEPLOYMENT_INVALID" and out["details"]["errors"] == [error], label
    assert not (tmp_path / "run" / REQUEST_SOCK).exists(), "it never listened"


# ------------------------------------------------------------------------------------------------ G3-11 durability
@pytest.mark.serial
def test_after_sigkill_the_ledger_keeps_records_consumed_members_proofs_and_the_lockout_and_loses_pending(
        tmp_path: Path, services: list[Service]) -> None:
    root = install(tmp_path)
    svc = start(services, tmp_path, root)
    two = G.fresh_proofs(G.base_set())
    two["intents"].append(dict(two["intents"][0], intent_ref="intent:zz-second", origin_proof_ref="proof:" + "e" * 32))
    _, (status, record, _) = approve(svc, two)
    assert status == 200
    assert call(svc.request, "POST", "/g3/v1/consume", G.consume_req(two, record))[1]["result"] == "CONSUMED"
    _, lost, _ = call(svc.request, "POST", "/g3/v1/approval-requests", G.request_body(G.fresh_proofs(G.base_set())))
    for _ in range(5):
        status, body, _ = call(svc.confirm, "POST", f"/g3/v1/approvals/{lost['approval_ref']}",
                               {"decision": "APPROVE", "pin": "wrong-pin"})
        assert body["code"] == "PIN_INCORRECT"
    os.killpg(svc.proc.pid, signal.SIGKILL)
    svc.proc.wait(timeout=15)
    again = start(services, tmp_path, root, pin=False)
    assert call(again.request, "POST", "/g3/v1/consume", G.consume_req(two, record))[1]["result"] == \
        "CONSENT_ALREADY_USED"
    assert call(again.request, "POST", "/g3/v1/consume",
                G.consume_req(two, record, intent_ref="intent:zz-second"))[1]["result"] == "CONSUMED"
    reused = dict(two, request_set_ref="request:after-kill")
    assert call(again.request, "POST", "/g3/v1/approval-requests", G.request_body(reused))[1]["code"] == \
        "MEMBER_PROOF_INVALID"
    assert call(again.request, "GET", f"/g3/v1/approval-requests/{lost['approval_ref']}")[0] == 404
    assert call(again.request, "GET", f"/g3/v1/approval-requests/{record['approval_ref']}")[1]["state"] == "APPROVED"
    pending, (status, body, _) = approve(again, G.fresh_proofs(G.base_set()))
    assert (status, body["code"]) == (423, "PIN_LOCKED")


@pytest.mark.serial
def test_one_member_is_consumed_once_when_many_clients_race_over_the_socket(tmp_path: Path,
                                                                           services: list[Service]) -> None:
    svc = start(services, tmp_path)
    cs = G.fresh_proofs(G.base_set())
    _, (status, record, _) = approve(svc, cs)
    assert status == 200
    req = G.consume_req(cs, record)
    gate = threading.Barrier(12)
    results: list[str] = []

    def go() -> None:
        gate.wait(timeout=30)
        results.append(call(svc.request, "POST", "/g3/v1/consume", req)[1]["result"])

    threads = [threading.Thread(target=go) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(results) == ["CONSENT_ALREADY_USED"] * 11 + ["CONSUMED"]


# ------------------------------------------------------------------------------------------------ G3-05 the PIN
def test_a_planted_pin_never_appears_in_the_logs_the_state_the_runtime_directory_or_the_output(
        tmp_path: Path, services: list[Service]) -> None:
    wrong = "planted-wrong-pin-771"
    svc = start(services, tmp_path)
    pending, (status, _, _) = approve(svc, G.fresh_proofs(G.base_set()), pin=wrong)
    assert status == 422
    _, (status, record, _) = approve(svc, G.fresh_proofs(G.base_set()))
    assert status == 200
    assert svc.stop() == 0
    searched = [svc.log] + [p for p in (svc.state.rglob("*")) if p.is_file()] + \
        [p for p in svc.run.rglob("*") if p.is_file()]
    assert len(searched) >= 5
    for f in searched:
        data = f.read_bytes()
        for pin in (G.PIN, wrong):
            assert pin.encode() not in data, (f.name, pin)
    assert G.PIN not in json.dumps(record)
