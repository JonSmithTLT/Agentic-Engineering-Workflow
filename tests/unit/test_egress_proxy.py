"""F28's egress proxy under its two policies, with R-6 (STG-05 CS-3a; F28 §3.4).

The client side is one end of a ``socket.socketpair()``. The resolver is synthetic. The connect is a spy that
connects nowhere, or hands back one end of another socketpair that reports a chosen peer address. Every real connect
goes to a loopback listener its test owns: one shows that the proxy never reaches it, one shows the default
connector at work, and the others are the proxy's own front door. Nothing contacts any other host: the public
addresses here are values. Every socket has a timeout and is closed in a ``finally``.
"""

from __future__ import annotations

import errno
import ipaddress
import socket
import threading
import time
import types
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from aew.errors import ValidationFailed
from aew.harness.containment import egress, peer
from aew.harness.containment.egress import Allowlist, AnyPublic, EgressProxy

TIMEOUT = 5.0
ESTABLISHED = b"HTTP/1.1 200 Connection Established\r\n\r\n"


def never_local(ip: peer.IP) -> bool:
    return False


class Resolver:
    """Names to answers, recording every lookup; an unknown name fails as DNS would."""

    def __init__(self, table: dict[str, list[str]] | None = None) -> None:
        self.table = table or {}
        self.calls: list[tuple[str, int]] = []

    def __call__(self, host: str, port: int) -> list[str]:
        self.calls.append((host, port))
        if host not in self.table:
            raise socket.gaierror(socket.EAI_NONAME, "synthetic: no such name")
        return self.table[host]


def ended(sock: socket.socket) -> bool:
    """The far side of a closed tunnel sees its end, after whatever was already on its way: EOF, or a reset when it
    had sent bytes nobody read. A tunnel that stays open makes this raise TimeoutError instead."""
    try:
        while sock.recv(64 * 1024):
            pass
        return True
    except ConnectionResetError:
        return True


class Reported(socket.socket):
    """One end of a socketpair that reports ``reported`` as its peer address."""

    reported: Any = None

    def getpeername(self) -> Any:
        if isinstance(self.reported, Exception):
            raise self.reported
        return self.reported


def small_buffers(*socks: socket.socket) -> None:
    """Pin the kernel's buffers small, so that a side that does not read soon stalls its writer. Linux honours it;
    Windows' loopback still absorbs tens of megabytes, so there the stall below cannot be provoked at all."""
    for sock in socks:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SMALL_BUFFER)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SMALL_BUFFER)


SMALL_BUFFER = 64 * 1024


class ConnectSpy:
    """Records every connect. With no ``peer`` it connects nowhere; with one it returns a socketpair end reporting
    that peer, and keeps the far end in ``far`` for the test to play the upstream."""

    def __init__(self, peer_address: Any = None, *, small: bool = False) -> None:
        self.peer_address = peer_address
        self.small = small
        self.calls: list[tuple[str, int]] = []
        self.far: list[socket.socket] = []

    def __call__(self, ip: peer.IP, port: int, timeout: float) -> socket.socket:
        self.calls.append((str(ip), port))
        if self.peer_address is None:
            raise OSError(errno.ECONNREFUSED, "synthetic: the spy connects nowhere")
        near, far = socket.socketpair()
        if self.small:
            small_buffers(near, far)
        far.settimeout(TIMEOUT)
        self.far.append(far)
        up = Reported(fileno=near.detach())
        up.reported = self.peer_address
        return up

    def close(self) -> None:
        for sock in self.far:
            sock.close()


@contextmanager
def served(proxy: EgressProxy, *, small: bool = False) -> Iterator[socket.socket]:
    """A client connection that ``proxy.handle`` serves on its own thread."""
    client, server = socket.socketpair()
    if small:
        small_buffers(client, server)
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=proxy.handle, args=(server,), daemon=True)
    thread.start()
    try:
        yield client
    finally:
        client.close()
        thread.join(TIMEOUT)
        ended_by_itself = not thread.is_alive()  # before close(), which would end it anyway
        proxy.close()
        thread.join(TIMEOUT)
        assert ended_by_itself


def request(target: str, *headers: str) -> bytes:
    return "".join([f"CONNECT {target} HTTP/1.1\r\n", f"Host: {target}\r\n", *(h + "\r\n" for h in headers),
                    "\r\n"]).encode()


def read_exactly(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        data = sock.recv(min(size - len(buf), 1 << 20))
        if not data:
            break
        buf += data
    return bytes(buf)


def response(client: socket.socket) -> tuple[int, dict[str, str], bytes]:
    """The proxy's answer to a refused request: status, headers, and the body up to the end of the connection."""
    buf = b""
    while data := client.recv(4096):
        buf += data
    head, _, body = buf.partition(b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    headers = dict(line.split(": ", 1) for line in lines[1:])
    return int(lines[0].split(" ")[1]), headers, body


def refusal(proxy: EgressProxy, raw: bytes) -> tuple[int, str, str]:
    with served(proxy) as client:
        client.sendall(raw)
        status, headers, body = response(client)
    return status, headers.get("X-AEW-Refusal", ""), body.decode()


# The hand-off's targets (and R-6's other classes), each listed on the allowlist: (name, target, answers, reason).
HOST_ROUTES = [
    ("loopback", "127.0.0.1:6000", None, "loopback"),
    ("ipv6-loopback", "[::1]:6000", None, "loopback"),
    ("mapped-loopback", "[::ffff:127.0.0.1]:6000", None, "loopback"),
    ("metadata", "169.254.169.254:80", None, "link_local"),
    ("host-interface", "10.9.8.7:6000", None, "host_interface"),
    ("this-host", "0.0.0.0:6000", None, "this_host"),
    ("name-to-loopback", "gateway.example:443", ["127.0.0.1"], "loopback"),
    ("name-to-mapped-loopback", "gateway.example:443", ["::ffff:127.0.0.1"], "loopback"),
    ("name-to-metadata", "gateway.example:443", ["169.254.169.254"], "link_local"),
    ("name-to-host-interface", "gateway.example:443", ["10.9.8.7"], "host_interface"),
]


def interface_only(ip: peer.IP) -> bool:
    return ip == ipaddress.ip_address("10.9.8.7")


@pytest.mark.parametrize("policy_name", ["allowlist", "any_public"])
@pytest.mark.parametrize(("target", "answers", "reason"), [row[1:] for row in HOST_ROUTES],
                         ids=[row[0] for row in HOST_ROUTES])
def test_the_proxy_refuses_every_host_route_even_an_allowlisted_one(policy_name, target, answers, reason):
    policy = Allowlist([target]) if policy_name == "allowlist" else AnyPublic()
    resolve = Resolver({"gateway.example": answers} if answers else {})
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(policy, resolve=resolve, connect=spy, is_local=interface_only)
    try:
        status, code, body = refusal(proxy, request(target))
    finally:
        spy.close()
    assert (status, code) == (403, reason)
    assert "R-6" in body and reason in body
    assert spy.calls == []  # judged before any connect
    assert proxy.decisions == {reason: 1}


def test_localhost_is_refused_through_the_hosts_own_resolver():
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(Allowlist(["localhost:6000"]), connect=spy)
    try:
        assert refusal(proxy, request("localhost:6000"))[:2] == (403, "loopback")
    finally:
        spy.close()
    assert spy.calls == []


def test_an_allowlisted_name_resolving_to_a_listener_the_test_owns_never_reaches_it():
    """The real connect is in place: only R-6 stands between the request and the listener."""
    listener = socket.create_server(("127.0.0.1", 0))
    try:
        listener.settimeout(0.5)
        port = listener.getsockname()[1]
        proxy = EgressProxy(Allowlist([f"gateway.example:{port}"]),
                            resolve=Resolver({"gateway.example": ["127.0.0.1"]}))
        assert refusal(proxy, request(f"gateway.example:{port}"))[:2] == (403, "loopback")
        with pytest.raises(TimeoutError):
            listener.accept()[0].close()
    finally:
        listener.close()


@pytest.mark.parametrize("policy", [Allowlist(["mixed.example:443"]), AnyPublic()], ids=["allowlist", "any_public"])
def test_one_refused_answer_refuses_the_whole_name(policy):
    """The Lead's rule (2026-10-24): a public answer beside a loopback one is not tried."""
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(policy, resolve=Resolver({"mixed.example": ["8.8.8.8", "127.0.0.1"]}), connect=spy,
                        is_local=never_local)
    try:
        assert refusal(proxy, request("mixed.example:443"))[:2] == (403, "loopback")
    finally:
        spy.close()
    assert spy.calls == []


@pytest.mark.parametrize("target", ["other.example:443", "catalog.example:80", "8.8.8.8:443",
                                    "sub.catalog.example:443", "xcatalog.example:443"])
def test_a_target_off_the_allowlist_is_refused_before_any_dns(target):
    """Entries are exact: neither another port, nor a name under the listed one, nor one ending with it."""
    resolve = Resolver({name: ["8.8.8.8"] for name in
                        ("other.example", "catalog.example", "sub.catalog.example", "xcatalog.example")})
    spy = ConnectSpy()
    proxy = EgressProxy(Allowlist(["catalog.example:443"]), resolve=resolve, connect=spy, is_local=never_local)
    status, code, body = refusal(proxy, request(target))
    assert (status, code) == (403, "not_allowlisted") and "allowlist" in body
    assert resolve.calls == [] and spy.calls == []


@pytest.mark.parametrize(("answer", "reason"), [
    ("10.0.0.5", "private"), ("100.64.0.1", "shared"), ("192.0.2.1", "documentation"),
    ("fd00::1", "not_global_unicast"), ("::ffff:192.168.1.1", "private"),
])
def test_any_public_refuses_an_address_that_is_not_globally_reachable(answer, reason):
    spy = ConnectSpy(peer_address=(answer, 443))
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"intranet.example": [answer]}), connect=spy,
                        is_local=never_local)
    try:
        status, code, body = refusal(proxy, request("intranet.example:443"))
    finally:
        spy.close()
    assert (status, code) == (403, reason) and "public" in body
    assert answer not in body  # the class, never the address: no map of the host's DNS
    assert spy.calls == []


def test_the_allowlist_admits_a_listed_private_address_r6_does_not_refuse():
    """The workers' policy is not "public only": a listed enterprise mirror on a private address is reached."""
    spy = ConnectSpy(peer_address=("10.0.0.5", 443))
    proxy = EgressProxy(Allowlist(["mirror.example:443"]), resolve=Resolver({"mirror.example": ["10.0.0.5"]}),
                        connect=spy, is_local=never_local)
    try:
        with served(proxy) as client:
            client.sendall(request("mirror.example:443"))
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
    finally:
        spy.close()
    assert spy.calls == [("10.0.0.5", 443)]


def test_an_admitted_target_is_tunnelled_byte_for_byte_with_nothing_added():
    """Credentialless: the upstream gets exactly what the client sent after its request (no request header, no
    credential), and the client gets exactly what the upstream sent. When one side closes, the tunnel closes both
    ways (RFC 9110 §9.3.6)."""
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=spy,
                        is_local=never_local)
    try:
        with served(proxy) as client:
            client.sendall(request("public.example:443", "Proxy-Authorization: synthetic-not-a-credential")
                           + b"early-bytes")
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
            far = spy.far[0]
            assert read_exactly(far, len(b"early-bytes")) == b"early-bytes"
            client.sendall(b"more")
            assert read_exactly(far, 4) == b"more"
            far.sendall(b"reply")
            assert read_exactly(client, 5) == b"reply"
            client.shutdown(socket.SHUT_WR)
            assert far.recv(1) == b""
            assert client.recv(1) == b""
    finally:
        spy.close()
    assert spy.calls == [("8.8.8.8", 443)]
    assert proxy.decisions == {"allowed": 1}


def test_when_the_upstream_closes_the_client_gets_what_it_sent_then_the_end():
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=spy,
                        is_local=never_local)
    try:
        with served(proxy) as client:
            client.sendall(request("public.example:443"))
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
            spy.far[0].sendall(b"last words")
            spy.far[0].close()
            assert read_exactly(client, 10) == b"last words"
            assert client.recv(1) == b""
    finally:
        spy.close()


def test_a_side_busy_writing_never_stalls_the_other_direction():
    """Over a direct connection, an upstream may write its whole answer before it reads the client's upload, while the
    client reads and writes at once; through the proxy too. A single relay for both directions would block in
    ``sendall`` towards the upstream, stop reading the answer, and leave both sides waiting: this test shows that on
    Linux (the ablation turns it red there), while Windows' loopback buffers absorb the stall."""
    size = 64 * SMALL_BUFFER  # far past every buffer on the way
    up, down = b"u" * size, b"d" * size
    spy = ConnectSpy(peer_address=("8.8.8.8", 443), small=True)
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=spy,
                        is_local=never_local)
    got: dict[str, bytes] = {}
    try:
        with served(proxy, small=True) as client:
            client.sendall(request("public.example:443"))
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
            far = spy.far[0]
            reader = threading.Thread(target=lambda: got.__setitem__("down", read_exactly(client, size)), daemon=True)
            writer = threading.Thread(target=client.sendall, args=(up,), daemon=True)
            reader.start()
            writer.start()
            try:
                far.sendall(down)  # the whole answer before reading anything
                got["up"] = read_exactly(far, size)
            finally:
                writer.join(TIMEOUT)
                reader.join(TIMEOUT)
    finally:
        spy.close()
    assert got.get("down") == down and got.get("up") == up


def test_the_default_connect_goes_to_the_literal_address_it_is_given():
    """The connector the proxy uses outside tests: no name, no resolution, and an error where nothing listens."""
    listener = socket.create_server(("127.0.0.1", 0))
    sock = None
    try:
        listener.settimeout(TIMEOUT)
        port = listener.getsockname()[1]
        sock = egress._connect(ipaddress.ip_address("127.0.0.1"), port, TIMEOUT)
        assert sock.getpeername()[:2] == ("127.0.0.1", port)
        listener.accept()[0].close()
    finally:
        if sock is not None:
            sock.close()
        listener.close()
    with pytest.raises(OSError):  # port 0, where nothing can listen: refused at once (Linux 111, Windows 10049)
        egress._connect(ipaddress.ip_address("127.0.0.1"), 0, TIMEOUT).close()


@pytest.mark.parametrize(("policy", "reported", "reason"), [
    (Allowlist(["public.example:443"]), ("127.0.0.1", 443), "loopback"),
    (AnyPublic(), ("::ffff:169.254.169.254", 443, 0, 0), "link_local"),
    (AnyPublic(), ("10.0.0.1", 443), "private"),
    (AnyPublic(), OSError(errno.ENOTCONN, "synthetic"), "peer_unknown"),
], ids=["allowlist-loopback", "any-public-mapped-link-local", "any-public-private", "peer-unknown"])
def test_the_connected_peer_is_judged_again_before_any_byte_is_relayed(policy, reported, reason):
    spy = ConnectSpy(peer_address=reported)
    proxy = EgressProxy(policy, resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=spy,
                        is_local=never_local)
    try:
        status, code, body = refusal(proxy, request("public.example:443") + b"early-bytes")
        assert (status, code) == (403, reason)
        assert spy.far[0].recv(1) == b""  # closed with nothing relayed
    finally:
        spy.close()
    if reason == "peer_unknown":  # said to be just that, never a host address
        assert "could not be confirmed" in body and "R-6" not in body


def test_when_every_address_binds_everything_counts_as_local_and_is_refused(monkeypatch):
    """The residual of ``net.ipv4.ip_nonlocal_bind=1``: safe (all egress refused), and named host_interface."""
    fake = types.SimpleNamespace(AF_INET=socket.AF_INET, AF_INET6=socket.AF_INET6, SOCK_STREAM=socket.SOCK_STREAM,
                                 socket=lambda family, kind: types.SimpleNamespace(bind=lambda a: None,
                                                                                   close=lambda: None))
    monkeypatch.setattr(peer, "socket", fake)
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=spy)
    try:
        assert refusal(proxy, request("public.example:443"))[:2] == (403, "host_interface")
    finally:
        spy.close()
    assert spy.calls == []


@pytest.mark.parametrize(("raw", "status", "reason"), [
    (b"GET http://catalog.example/ HTTP/1.1\r\nHost: catalog.example\r\n\r\n", 405, "method"),
    (b"CONNECT catalog.example HTTP/1.1\r\n\r\n", 400, "bad_request"),
    (b"CONNECT catalog.example:0 HTTP/1.1\r\n\r\n", 400, "bad_request"),
    (b"CONNECT [::1 HTTP/1.1\r\n\r\n", 400, "bad_request"),
    (b"CONNECT ::1:443 HTTP/1.1\r\n\r\n", 400, "bad_request"),
    (b"CONNECT catalog.example:443 HTTP/2\r\n\r\n", 400, "bad_request"),
    (b"CONNECT catalog.example:443\r\n\r\n", 400, "bad_request"),
    (b"\xff\xfe\r\n\r\n", 400, "bad_request"),
    (b"CONNECT " + b"a" * egress.MAX_HEADER, 431, "header_too_large"),
    (b"CONNECT catalog.example:443 HTTP/1.1\r\nX-Pad: " + b"a" * egress.MAX_HEADER + b"\r\n\r\n", 431,
     "header_too_large"),
    (b"CONNECT [2606:4700:4700::1111%eth9]:443 HTTP/1.1\r\n\r\n", 400, "bad_request"),
    (b"CONNECT [2606:4700:4700::1111%\x00]:443 HTTP/1.1\r\n\r\n", 400, "bad_request"),
    (b"CONNECT catalog.example:" + b"4" * 5000 + b" HTTP/1.1\r\n\r\n", 400, "bad_request"),
], ids=["get", "no-port", "port-zero", "open-bracket", "bare-ipv6", "http2", "no-version", "not-ascii", "oversize",
        "complete-oversize", "zone-id", "zone-id-nul", "long-port"])
def test_a_request_that_is_not_a_well_formed_connect_is_refused_before_any_dns(raw, status, reason):
    resolve, spy = Resolver({"catalog.example": ["8.8.8.8"]}), ConnectSpy()
    proxy = EgressProxy(AnyPublic(), resolve=resolve, connect=spy, is_local=never_local)
    status_got, reason_got, body = refusal(proxy, raw)
    assert (status_got, reason_got) == (status, reason)
    assert resolve.calls == [] and spy.calls == []
    assert "sys." not in body  # the proxy's own words, never the interpreter's


def test_a_silent_client_is_answered_and_closed_after_the_header_timeout():
    proxy = EgressProxy(AnyPublic(), resolve=Resolver(), connect=ConnectSpy(), header_timeout=0.2)
    with served(proxy) as client:
        status, headers, _ = response(client)
    assert (status, headers["X-AEW-Refusal"]) == (408, "header_timeout")


def test_a_client_that_leaves_mid_request_is_counted_and_nothing_is_resolved():
    resolve = Resolver({"catalog.example": ["8.8.8.8"]})
    proxy = EgressProxy(AnyPublic(), resolve=resolve, connect=ConnectSpy())
    with served(proxy) as client:
        client.sendall(b"CONNECT catalog.exa")
        client.shutdown(socket.SHUT_WR)
        response(client)
    assert proxy.decisions == {"incomplete": 1} and resolve.calls == []


@pytest.mark.parametrize(("answers", "reason"), [(None, "unresolved"), ([], "unresolved"),
                                                 (["catalog.example"], "unresolved"), (["8.8.8.8"], "unreachable")],
                         ids=["no-such-name", "no-answers", "a-name-for-an-answer", "unreachable"])
def test_a_target_that_does_not_resolve_or_connect_is_a_bad_gateway(answers, reason):
    spy = ConnectSpy()  # connects nowhere
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({} if answers is None else {"catalog.example": answers}),
                        connect=spy, is_local=never_local)
    assert refusal(proxy, request("catalog.example:443"))[:2] == (502, reason)
    assert spy.calls == ([("8.8.8.8", 443)] if reason == "unreachable" else [])


def test_allowlist_entries_are_normalized_and_validated():
    allow = Allowlist(["Catalog.Example.:443", "[0:0::1]:8080", "8.8.8.8:53"])
    assert allow.describe() == {"policy": "allowlist", "allow": ["8.8.8.8:53", "[::1]:8080", "catalog.example:443"]}
    assert allow.admits("catalog.example", 443) is None
    assert allow.admits("catalog.example", 80) == "not_allowlisted"
    assert allow.admits("sub.catalog.example", 443) == allow.admits("xcatalog.example", 443) == "not_allowlisted"
    assert allow.refuses(ipaddress.ip_address("10.0.0.1")) is None
    assert Allowlist([]).admits("catalog.example", 443) == "not_allowlisted"
    assert AnyPublic().describe() == {"policy": "any_public"}
    for bad in ["catalog.example", "*.example:443", "catalog.example:0", "[::1]", "", "catalog.example:https",
                "[fe80::1%eth0]:443", "Katalog.example:443", "catalog.example:" + "4" * 5000]:
        with pytest.raises(ValidationFailed) as caught:
            Allowlist([bad])
        assert caught.value.details == {"entry": bad, "reason": "bad_allowlist_entry"}
        assert "sys." not in caught.value.message


def test_the_proxy_serves_its_listener_and_close_ends_every_tunnel():
    unstarted = EgressProxy(AnyPublic())
    try:
        with pytest.raises(ValueError):
            unstarted.start()
    finally:
        unstarted.close()
    front = socket.create_server(("127.0.0.1", 0))  # the proxy's own front door, standing in for CS-3b's AF_UNIX one
    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    client = None
    try:
        with EgressProxy(AnyPublic(), listener=front, resolve=Resolver({"public.example": ["8.8.8.8"]}),
                         connect=spy, is_local=never_local) as proxy:
            client = socket.create_connection(front.getsockname(), timeout=TIMEOUT)
            client.sendall(request("public.example:443"))
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
            proxy.close()
            assert client.recv(1) == b""
            assert spy.far[0].recv(1) == b""
            assert front.fileno() == -1
            assert not [t for t in threading.enumerate() if t.name.startswith("aew-egress")]
    finally:
        if client is not None:
            client.close()
        front.close()
        spy.close()


def test_the_whole_request_head_has_one_deadline():
    """However its bytes are spaced, the request head must be complete ``header_timeout`` after the connection began:
    a byte now and then does not extend it."""
    timeout = 0.4
    proxy = EgressProxy(AnyPublic(), resolve=Resolver(), connect=ConnectSpy(), header_timeout=timeout)
    stop = threading.Event()

    def trickle(sock: socket.socket) -> None:
        for byte in b"CONNECT catalog.example:443 HTTP/1.1\r\n":  # never the blank line that ends the head
            if stop.wait(timeout / 4):
                return
            try:
                sock.send(bytes([byte]))
            except OSError:
                return

    with served(proxy) as client:
        started = time.monotonic()
        sender = threading.Thread(target=trickle, args=(client,), daemon=True)
        sender.start()
        try:
            status, headers, _ = response(client)
            assert (status, headers["X-AEW-Refusal"]) == (408, "header_timeout")
        except ConnectionResetError:
            pass  # a byte that arrived after the proxy's last read made its close a reset: the end came all the same
        finally:
            stop.set()
            sender.join(TIMEOUT)
        elapsed = time.monotonic() - started
    assert proxy.decisions == {"header_timeout": 1}
    assert elapsed < 3 * timeout


def test_an_unexpected_error_is_answered_with_a_fixed_bad_gateway():
    def broken(ip: peer.IP, port: int, timeout: float) -> socket.socket:
        raise TypeError("synthetic detail")

    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=broken,
                        is_local=never_local)
    status, code, body = refusal(proxy, request("public.example:443"))
    assert (status, code) == (502, "proxy_error") and "synthetic" not in body
    assert proxy.decisions == {"proxy_error": 1}


def send_until_closed(sock: socket.socket, data: bytes) -> None:
    try:
        sock.sendall(data)
    except OSError:
        pass


@pytest.mark.parametrize("ending", ["client_ends", "upstream_ends", "proxy_closes"])
def test_a_tunnel_ends_both_ways_even_while_a_direction_is_mid_send(ending):
    """RFC 9110 §9.3.6 while the direction towards one side is blocked in ``sendall``, because that side does not
    read: the end still reaches the far side. Linux shows it, where the small buffers fill. Windows' loopback absorbs
    the stream, so there no direction is ever blocked."""
    spy = ConnectSpy(peer_address=("8.8.8.8", 443), small=True)
    proxy = EgressProxy(AnyPublic(), resolve=Resolver({"public.example": ["8.8.8.8"]}), connect=spy,
                        is_local=never_local)
    stream = b"s" * (64 * SMALL_BUFFER)
    try:
        with served(proxy, small=True) as client:
            client.sendall(request("public.example:443"))
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
            far = spy.far[0]
            # The side or sides that stream, which the other never reads. For close(), both directions are blocked
            # at once, so that no relay is waiting where the wake socket reaches it: only close()'s shutdown does.
            sources = {"client_ends": [far], "upstream_ends": [client], "proxy_closes": [client, far]}[ending]
            writers = [threading.Thread(target=send_until_closed, args=(source, stream), daemon=True)
                       for source in sources]
            for writer in writers:
                writer.start()
            try:
                time.sleep(0.3)  # long enough for the stream to fill every buffer on its way
                if ending == "client_ends":
                    client.shutdown(socket.SHUT_WR)
                    assert ended(far)
                elif ending == "upstream_ends":
                    far.shutdown(socket.SHUT_WR)
                    assert ended(client)
                else:
                    proxy.close()
                    assert ended(far)
            finally:
                proxy.close()  # closing the tunnel's sockets wakes the writers at once, on Windows too
                for writer in writers:
                    writer.join(TIMEOUT)
    finally:
        spy.close()


def test_no_connect_starts_once_close_has_begun():
    """A request still resolving when ``close()`` begins connects nowhere afterwards."""
    entered, release = threading.Event(), threading.Event()

    def slow(host: str, port: int) -> list[str]:
        entered.set()
        release.wait(TIMEOUT)
        return ["8.8.8.8"]

    spy = ConnectSpy(peer_address=("8.8.8.8", 443))
    proxy = EgressProxy(AnyPublic(), resolve=slow, connect=spy, is_local=never_local)
    try:
        with served(proxy) as client:
            client.sendall(request("public.example:443"))
            assert entered.wait(TIMEOUT)
            proxy.close()
            release.set()
            assert ended(client)
    finally:
        release.set()
        spy.close()
    assert spy.calls == [] and proxy.decisions == {"closed": 1}


def test_a_connection_handed_over_after_close_is_closed_unserved():
    resolve = Resolver({"catalog.example": ["8.8.8.8"]})
    proxy = EgressProxy(AnyPublic(), resolve=resolve, connect=ConnectSpy())
    proxy.close()
    with served(proxy) as client:
        assert ended(client)
    assert resolve.calls == [] and proxy.decisions == {}


def test_a_name_is_resolved_once():
    """The address connected is one the single resolution gave, whatever a later lookup would answer."""
    lookups: list[str] = []

    def changing(host: str, port: int) -> list[str]:
        lookups.append(host)
        return ["192.0.2.10"] if len(lookups) == 1 else ["127.0.0.1"]

    spy = ConnectSpy(peer_address=("192.0.2.10", 443))
    proxy = EgressProxy(Allowlist(["catalog.example:443"]), resolve=changing, connect=spy, is_local=never_local)
    try:
        with served(proxy) as client:
            client.sendall(request("catalog.example:443"))
            assert read_exactly(client, len(ESTABLISHED)) == ESTABLISHED
    finally:
        spy.close()
    assert lookups == ["catalog.example"] and spy.calls == [("192.0.2.10", 443)]


class FailingThread(threading.Thread):
    """A thread that cannot be started, as when the process has none left."""

    def start(self) -> None:
        raise RuntimeError("synthetic: can't start new thread")


def test_a_connection_that_cannot_get_a_thread_is_closed_and_serving_goes_on(monkeypatch):
    front = socket.create_server(("127.0.0.1", 0))
    proxy = EgressProxy(AnyPublic(), listener=front, resolve=Resolver(), connect=ConnectSpy())
    clients: list[socket.socket] = []
    try:
        proxy.start()
        monkeypatch.setattr(egress, "threading",
                            types.SimpleNamespace(Thread=FailingThread, current_thread=threading.current_thread))
        for _ in range(2):  # the second shows the accept loop still serving
            clients.append(socket.create_connection(front.getsockname(), timeout=TIMEOUT))
            assert ended(clients[-1])
        assert proxy.decisions == {"overloaded": 2}
    finally:
        proxy.close()  # never raises, and closes the proxy's own sockets
        for client in clients:
            client.close()
        front.close()
    assert front.fileno() == -1


class RefusingListener(socket.socket):
    """A listener whose accept always fails, as when the process is out of descriptors."""

    accepts = 0

    def accept(self) -> tuple[socket.socket, Any]:
        self.accepts += 1
        raise OSError(errno.EMFILE, "synthetic: too many open files")


def test_a_failing_accept_waits_between_tries_and_close_still_returns():
    front = RefusingListener(socket.AF_INET, socket.SOCK_STREAM)
    proxy = EgressProxy(AnyPublic(), listener=front, resolve=Resolver(), connect=ConnectSpy())
    client = None
    try:
        front.bind(("127.0.0.1", 0))
        front.listen()
        client = socket.create_connection(front.getsockname(), timeout=TIMEOUT)  # keeps the listener readable
        proxy.start()
        time.sleep(0.5)
        started = time.monotonic()
        proxy.close()
        assert time.monotonic() - started < 1.0
        assert 1 <= front.accepts <= 0.5 / egress.ACCEPT_BACKOFF + 2
    finally:
        proxy.close()
        if client is not None:
            client.close()
        front.close()
