"""F28's credentialing provider relay (STG-05 CS-3b; F28 §3.3).

The client is one end of a ``socket.socketpair()``, whose other end the relay serves (``ProviderRelay.handle``) on a
thread. The connect is a seam: it hands the relay one end of another socketpair, whose other end plays the upstream
(or the operator's proxy), so every byte the upstream receives is the test's to read. Nothing contacts any host. The
credential here is a synthetic value. Every socket has a timeout and is closed in a ``finally``.
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from aew.errors import ValidationFailed
from aew.harness.containment import relay
from aew.harness.containment.relay import ProviderRelay, Proxy, Upstream

TIMEOUT = 5.0
SECRET = "synthetic-provider-key-cs3b"
# Plain http, so the test reads what the relay sends; https differs only in the TLS wrap (the live lane runs it).
UPSTREAM = "http://provider.example/v1"
OK = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: keep-alive\r\n\r\nok"


class Seam:
    """The relay's connect: records where it was asked to connect, and hands back one end of a socketpair whose other
    end (``far``) the test drives; or raises ``error``."""

    def __init__(self, error: OSError | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.far: socket.socket | None = None
        self.error = error
        self.connected = threading.Event()

    def __call__(self, host: str, port: int, timeout: float) -> socket.socket:
        self.calls.append((host, port))
        if self.error is not None:
            raise self.error
        near, far = socket.socketpair()
        far.settimeout(TIMEOUT)
        self.far = far
        self.connected.set()
        return near

    def upstream(self) -> socket.socket:
        assert self.connected.wait(TIMEOUT), "the relay never connected"
        assert self.far is not None
        return self.far


def read_head(sock: socket.socket) -> tuple[bytes, bytes]:
    buf = b""
    while b"\r\n\r\n" not in buf:
        data = sock.recv(4096)
        if not data:
            break
        buf += data
    head, _, rest = buf.partition(b"\r\n\r\n")
    return head, rest


def headers(head: bytes) -> list[tuple[str, str]]:
    out = []
    for raw in head.split(b"\r\n")[1:]:
        name, _, value = raw.decode("latin-1").partition(":")
        out.append((name.strip().lower(), value.strip()))
    return out


def read_all(sock: socket.socket) -> bytes:
    out = b""
    while True:
        data = sock.recv(65536)
        if not data:
            return out
        out += data


@contextmanager
def relayed(seam: Seam, *, upstream: str = UPSTREAM, proxy: Proxy | None = None,
            credentials: dict[str, str] | None = None) -> Iterator[tuple[ProviderRelay, socket.socket, str]]:
    """A relay serving one connection; yields it, the client end, and the sentinel that stands for ``SECRET``."""
    token = relay.sentinel()
    service = ProviderRelay(Upstream(upstream), credentials if credentials is not None else {token: SECRET},
                            proxy=proxy, connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT)
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        yield service, client, token
    finally:
        client.close()
        thread.join(TIMEOUT)
        service.close()
        if seam.far is not None:
            seam.far.close()
    assert not thread.is_alive(), "the relay's handler did not end"


def exchange(seam: Seam, request: bytes, response: bytes = OK, **kw: Any) -> tuple[bytes, bytes, ProviderRelay]:
    """``request`` through a relay to an upstream that answers ``response``: (what the upstream got, what the client
    got, the relay)."""
    with relayed(seam, **kw) as (service, client, _):
        client.sendall(request)
        upstream = seam.upstream()
        got_head, got_rest = read_head(upstream)
        upstream.sendall(response)
        upstream.close()
        answer = read_all(client)
    return got_head + b"\r\n\r\n" + got_rest, answer, service


def test_the_credential_goes_only_where_its_sentinel_is_and_only_in_a_credential_header():
    """The sentinel in Authorization and X-Api-Key becomes the credential; the same sentinel in any other header (one an
    upstream might echo back) stays as it came, so the credential never reaches a header the client can be shown."""
    seam = Seam()
    with relayed(seam) as (_, client, token):
        client.sendall(f"POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:4101\r\n"
                       f"Authorization: Bearer {token}\r\nX-Api-Key: {token}\r\nX-Request-Id: {token}\r\n"
                       "Content-Length: 2\r\n\r\n{}".encode())
        upstream = seam.upstream()
        head, body = read_head(upstream)
        while len(body) < 2:
            body += upstream.recv(64)
        upstream.sendall(OK)
        upstream.close()
        read_all(client)
    got = headers(head)
    assert head.split(b"\r\n")[0] == b"POST /v1/chat/completions HTTP/1.1"
    assert ("authorization", f"Bearer {SECRET}") in got and ("x-api-key", SECRET) in got
    assert ("x-request-id", token) in got  # never the credential outside a credential header
    assert ("host", "provider.example") in got and ("host", "127.0.0.1:4101") not in got
    assert seam.calls == [("provider.example", 80)]  # the fixed upstream, never what the request named
    assert body == b"{}"


def test_a_credential_header_without_a_sentinel_passes_as_it_came():
    """The free provider's catalog key (``Bearer public``) is what the sandbox already had: it passes unchanged."""
    upstream_got, _, _ = exchange(Seam(), b"GET /v1/models HTTP/1.1\r\nAuthorization: Bearer public\r\n\r\n")
    assert ("authorization", "Bearer public") in headers(upstream_got.split(b"\r\n\r\n")[0])


def test_hop_by_hop_headers_are_dropped_and_both_sides_are_told_connection_close():
    request = (b"GET /v1/models HTTP/1.1\r\nConnection: keep-alive, X-Private\r\nKeep-Alive: timeout=5\r\nTE: trailers"
               b"\r\nProxy-Authorization: Basic eDp5\r\nX-Private: dropped\r\nAccept: */*\r\n\r\n")
    upstream_got, answer, service = exchange(Seam(), request)
    sent = headers(upstream_got.split(b"\r\n\r\n")[0])
    names = [n for n, _ in sent]
    assert not {"keep-alive", "te", "proxy-authorization", "x-private"} & set(names)
    assert ("connection", "close") in sent and ("accept", "*/*") in sent
    head, body = answer.split(b"\r\n\r\n", 1)
    assert ("connection", "close") in headers(head) and ("connection", "keep-alive") not in headers(head)
    assert body == b"ok" and service.counts() == {"allowed": 1}


@pytest.mark.parametrize(("request_line", "reason"), [
    (b"GET http://elsewhere.example/v1/models HTTP/1.1", b"not_origin_form"),
    (b"CONNECT elsewhere.example:443 HTTP/1.1", b"not_origin_form"),
    (b"GET /v1/models HTTP/2.0", b"bad_request"),
])
def test_a_request_that_names_its_own_destination_is_refused_and_nothing_is_connected(request_line, reason):
    seam = Seam()
    with relayed(seam) as (service, client, _):
        client.sendall(request_line + b"\r\nHost: elsewhere.example\r\n\r\n")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: " + reason in answer
    assert seam.calls == [] and service.counts() == {reason.decode(): 1}


def test_a_protocol_upgrade_is_refused_with_what_to_do_instead():
    seam = Seam()
    with relayed(seam) as (_, client, _):
        client.sendall(b"GET /v1/realtime HTTP/1.1\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 501 ") and b"X-AEW-Refusal: upgrade" in answer and b"transport" in answer
    assert seam.calls == []


def test_a_chunked_request_body_reaches_the_upstream_whole_and_nothing_after_it():
    body = b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    seam = Seam()
    with relayed(seam) as (_, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n" + body + b"GET /x HTTP/1.1")
        upstream = seam.upstream()
        head, rest = read_head(upstream)
        while not rest.endswith(b"0\r\n\r\n"):
            rest += upstream.recv(4096)
        upstream.sendall(OK)
        upstream.close()
        read_all(client)
    assert ("transfer-encoding", "chunked") in headers(head) and rest == body


def test_expect_100_continue_is_answered_by_the_relay_and_not_forwarded():
    seam = Seam()
    with relayed(seam) as (_, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nExpect: 100-continue\r\nContent-Length: 2\r\n\r\n")
        assert client.recv(64) == b"HTTP/1.1 100 Continue\r\n\r\n"
        client.sendall(b"{}")
        upstream = seam.upstream()
        head, rest = read_head(upstream)
        if not rest:
            rest = upstream.recv(64)
        upstream.sendall(OK)
        upstream.close()
        read_all(client)
    assert "expect" not in [n for n, _ in headers(head)] and rest == b"{}"


def test_the_response_streams_as_it_comes():
    """The client has the first event before the upstream sends the second: the relay does not wait for the end."""
    seam = Seam()
    with relayed(seam) as (_, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nContent-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\ndata: one\n\n")
        head, first = read_head(client)
        while b"data: one\n\n" not in first:
            first += client.recv(4096)
        upstream.sendall(b"data: two\n\n")
        upstream.close()
        rest = read_all(client)
    assert head.startswith(b"HTTP/1.1 200 ") and first == b"data: one\n\n" and rest == b"data: two\n\n"


def test_a_client_that_goes_away_ends_the_upstream_connection_and_is_counted_cancelled():
    """A cancelled turn: the harness closes its connection mid-stream, and the relay closes the upstream's at once."""
    seam = Seam()
    with relayed(seam) as (service, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nContent-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\ndata: one\n\n")
        _, first = read_head(client)
        while b"data: one\n\n" not in first:
            first += client.recv(4096)
        client.close()
        assert read_all(upstream) == b""  # the relay closed it: EOF, not a timeout
    assert service.counts() == {"allowed": 1, "cancelled": 1}


def test_an_unreachable_upstream_is_a_502_that_names_the_fixed_upstream():
    seam = Seam(error=ConnectionRefusedError(111, "synthetic: refused"))
    with relayed(seam) as (service, client, _):
        client.sendall(b"GET /v1/models HTTP/1.1\r\n\r\n")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 502 ") and b"X-AEW-Refusal: upstream_unreachable" in answer
    assert UPSTREAM.encode() in answer and service.counts() == {"upstream_unreachable": 1}


def test_through_the_operators_proxy_the_relay_asks_for_a_tunnel_to_its_fixed_upstream():
    """``HTTPS_PROXY`` in the provider's environment: the relay connects to the proxy, asks it for ``CONNECT`` to the
    upstream (with the proxy's own credentials), and sends the request through the tunnel (here plain http, so the
    test reads it)."""
    seam = Seam()
    proxy = Proxy("http://user:pa%3Ass@proxy.example:3128")
    with relayed(seam, upstream="http://provider.example:8080/v1", proxy=proxy) as (_, client, token):
        client.sendall(f"GET /v1/models HTTP/1.1\r\nAuthorization: Bearer {token}\r\n\r\n".encode())
        far = seam.upstream()
        connect, _ = read_head(far)
        far.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        head, _ = read_head(far)
        far.sendall(OK)
        far.close()
        answer = read_all(client)
    assert seam.calls == [("proxy.example", 3128)]
    assert connect.split(b"\r\n")[0] == b"CONNECT provider.example:8080 HTTP/1.1"
    assert ("proxy-authorization", "Basic dXNlcjpwYTpzcw==") in headers(connect)
    assert ("authorization", f"Bearer {SECRET}") in headers(head) and ("host", "provider.example:8080") in headers(head)
    assert answer.endswith(b"ok")


def test_a_proxy_that_refuses_the_tunnel_is_the_upstream_unreachable():
    seam = Seam()
    with relayed(seam, proxy=Proxy("http://proxy.example:3128")) as (_, client, _):
        client.sendall(b"GET /v1/models HTTP/1.1\r\n\r\n")
        far = seam.upstream()
        read_head(far)
        far.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 502 ") and b"upstream_unreachable" in answer


def test_closing_the_relay_forgets_its_credentials():
    service = ProviderRelay(Upstream(UPSTREAM), {relay.sentinel(): SECRET})
    service.close()
    assert service._credentials == {}


@pytest.mark.parametrize("url", ["ftp://provider.example", "https://", "https://u:p@provider.example/v1",
                                 "https://provider.example/v1?k=v", "https://provider.example:99999/v1"])
def test_an_upstream_that_is_not_an_http_url_is_refused(url):
    with pytest.raises(ValidationFailed) as caught:
        Upstream(url)
    assert caught.value.details["reason"] == "bad_upstream"


def test_the_label_names_the_upstream_and_never_a_credential():
    service = ProviderRelay(Upstream(UPSTREAM), {relay.sentinel(): SECRET}, proxy=Proxy("http://u:p@proxy.example:3128"))
    try:
        described = relay.describe(service)
    finally:
        service.close()
    assert described == {"provider_relay": "configured", "provider_upstream": UPSTREAM,
                         "provider_upstream_proxy": "proxy.example:3128"}
    assert relay.describe(None) == {"provider_relay": "none"}
