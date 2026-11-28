"""F28's credentialing provider relay (STG-05 CS-3b; F28 §3.3).

The client is one end of a ``socket.socketpair()``, whose other end the relay serves (``ProviderRelay.handle``) on a
thread. The connect is a seam: it hands the relay one end of another socketpair, whose other end plays the upstream
(or the operator's proxy), so every byte the upstream receives is the test's to read. Nothing contacts any host. The
credential here is a synthetic value. Every socket has a timeout and is closed in a ``finally``.
"""

from __future__ import annotations

import gzip
import http.client
import json
import socket
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tcp_pair import tcp_pair

from aew.errors import ValidationFailed
from aew.harness.containment import netns, relay
from aew.harness.containment.relay import ProviderRelay, Proxy, Upstream
from aew.harness.opencode import login
from aew.harness.opencode.login import WorkerKey

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
            credentials: dict[str, str] | None = None, resolve: Callable[[], relay.Grant] | None = None,
            record: Callable[[dict[str, Any]], None] | None = None, **bounds: Any,
            ) -> Iterator[tuple[ProviderRelay, socket.socket, str]]:
    """A relay serving one connection; yields it, the client end, and the sentinel that stands for ``SECRET``.
    ``bounds`` are the relay's other keywords (its bounds, its policy's sha)."""
    token = relay.sentinel()
    service = ProviderRelay(Upstream(upstream), credentials if credentials is not None else {token: SECRET},
                            proxy=proxy, connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT, resolve=resolve, record=record, route="openai", login="key",
                            **bounds)
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


def test_stored_worker_key_uses_the_builtin_relay_and_does_not_retry_a_401(monkeypatch):
    _check_stored_worker_relay(monkeypatch, other_export=False)


def test_a_run_relay_swaps_no_other_built_in_providers_key(monkeypatch):
    _check_stored_worker_relay(monkeypatch, other_export=True)


def _check_stored_worker_relay(monkeypatch, *, other_export: bool):
    synthetic = "SYNTHETIC-NOT-A-KEY"
    variable = "OPENAI_API_KEY"
    other = "ANTHROPIC_API_KEY"
    other_key = "SYNTHETIC-NOT-A-KEY-OTHER"
    exports = {other: other_key} if other_export else {}
    seam = Seam()
    monkeypatch.setattr(netns, "mode", lambda _: netns.PROXY_ONLY)
    monkeypatch.setitem(netns.UPSTREAMS, "openai", UPSTREAM)
    monkeypatch.setattr(netns, "listen", lambda _: None)
    monkeypatch.setattr(relay, "ProviderRelay", lambda target, credentials, sources, **_: ProviderRelay(
        target, credentials, connect=seam, sources=sources, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
        body_timeout=TIMEOUT,
    ))
    monkeypatch.setattr(ProviderRelay, "start", lambda self: self)
    layout = SimpleNamespace(network=netns.PROXY_ONLY, net_dir="unused")
    network = netns.RunNetwork.start(layout, provider="openai", provider_env=[variable, *exports],
                                    policy={}, env=exports, relay_needed=True, stored=WorkerKey(synthetic, (1, 10)))
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=network.relay.handle, args=(served,), daemon=True)
    try:
        thread.start()
        inside = network.harness_env({})
        token = inside[variable]
        extra_header = f"X-Api-Key: {inside[other]}\r\n" if other_export else ""
        assert token != synthetic
        assert network.relay.sources == {token: "saved_key"}
        assert network.describe()["provider_key_source"] == "stored OpenCode login"
        assert synthetic not in repr(network.describe())
        client.sendall(f"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n"
                       f"Authorization: Bearer {token}\r\n{extra_header}Content-Length: 0\r\n\r\n".encode())
        if other_export:  # another provider's placeholder is one this relay does not hold: refused, nothing connects
            answer = read_all(client)
            assert answer.startswith(b"HTTP/1.1 401") and b"X-AEW-Refusal: other_placeholder" in answer
            assert seam.calls == [] and other_key.encode() not in answer and inside[other].encode() not in answer
            assert other in network.leaks(other_key)
            return
        upstream = seam.upstream()
        head, _ = read_head(upstream)
        assert ("authorization", f"Bearer {synthetic}") in headers(head)
        upstream.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        upstream.close()
        assert read_all(client).startswith(b"HTTP/1.1 401")
        assert seam.calls == [("provider.example", 80)]
    finally:
        client.close()
        thread.join(TIMEOUT)
        network.dir = None
        network.close()
        if seam.far is not None:
            seam.far.close()
    assert not thread.is_alive()


def test_a_resolved_credential_is_read_for_each_request_with_its_headers_and_an_unusable_one_is_a_401():
    """A stored login the operator's own harness may refresh (STG-05 CS-4, addendum 1): the relay asks for the
    credential on each request, so a changed one is used from the next request on; the grant's headers replace any of
    the same name the client sent (an account header from inside is a placeholder); and when the resolver has nothing
    usable, the client gets a 401 whose body is the resolver's message, and nothing is connected."""
    token = relay.sentinel()
    grants = [({token: f"synthetic-access-{n}"}, {"ChatGPT-Account-Id": "synthetic-account"}) for n in (1, 2)]
    asked: list[int] = []

    def resolve() -> relay.Grant:
        asked.append(1)
        if len(asked) > len(grants):
            raise relay.Unavailable("the stored login has expired: refresh it, and the next request works",
                                    cause="expired")
        return grants[len(asked) - 1]

    request = (f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\nchatgpt-account-id: inside\r\n"
               "Content-Length: 0\r\n\r\n").encode()
    seam = Seam()
    service = ProviderRelay(Upstream(UPSTREAM), {}, connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT, resolve=resolve)
    try:
        for n in (1, 2):  # one relay, two requests: the second uses what the resolver gives then
            seam.connected.clear()
            client, served = socket.socketpair()
            client.settimeout(TIMEOUT)
            thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
            thread.start()
            try:
                client.sendall(request)
                upstream = seam.upstream()
                head, _ = read_head(upstream)
                upstream.sendall(OK)
                upstream.close()
                read_all(client)
            finally:
                client.close()
                thread.join(TIMEOUT)
            sent = headers(head)
            assert ("authorization", f"Bearer synthetic-access-{n}") in sent, sent
            assert ("chatgpt-account-id", "synthetic-account") in sent and ("chatgpt-account-id", "inside") not in sent
    finally:
        service.close()
    seam = Seam()
    with relayed(seam, credentials={}, resolve=resolve) as (service, client, _):
        client.sendall(request)
        answer = read_all(client)
    assert seam.calls == [], "a request without a usable credential connected to the upstream"
    assert answer.startswith(b"HTTP/1.1 401 Unauthorized\r\n") and b"X-AEW-Refusal: credential_unavailable" in answer
    assert answer.endswith(b"the stored login has expired: refresh it, and the next request works")
    assert service.counts().get("credential_unavailable") == 1
    assert service.counts().get("credential:expired") == 1


@pytest.mark.parametrize("status,reason", [
    pytest.param(401, "credential_unavailable", id="expired-401"),
    pytest.param(403, "outside_upstream_path", id="outside-path-403"),
    pytest.param(503, "credential_unreadable", id="retryable-503"),
])
def test_a_refusal_survives_a_delayed_body_without_a_connection_reset(status, reason):
    """Force body bytes to arrive only after the refusal is sent, and read only after the relay closes.
    Without the drain Windows resets this unread-data close; no sleep or probabilistic repetition is needed."""
    seam = Seam(OSError("a refusal must connect nothing"))
    answer_sent, body_sent, ended = threading.Event(), threading.Event(), threading.Event()
    cause = "expired" if status == 401 else "unreadable"
    message = f"planted {cause} credential"
    target = "/v1/responses"
    if status == 403:
        target = "/outside/responses"
        message = ("the provider relay takes only unambiguous paths under the stored login's upstream path: this "
                   "request was not sent. Address the provider's API at the base URL AEW gave the harness")

    def resolve():
        assert status != 403, "an outside-path request must be refused before resolving credentials"
        raise relay.Unavailable(message, cause=cause, retryable=status == 503)

    service = ProviderRelay(Upstream(UPSTREAM), {}, connect=seam, resolve=resolve)
    client, served = tcp_pair(TIMEOUT)
    client.settimeout(TIMEOUT)

    class SplitRequest:
        def __getattr__(self, name):
            return getattr(served, name)

        def sendall(self, data):
            served.sendall(data)
            answer_sent.set()
            assert body_sent.wait(TIMEOUT), "the client never supplied the delayed body"
            assert served.recv(1, socket.MSG_PEEK) == b"x", "the body must be queued and unread before close"

    def handle():
        try:
            service.handle(SplitRequest())
        finally:
            ended.set()

    thread = threading.Thread(target=handle, daemon=True)
    thread.start()
    try:
        body = b"x" * (64 * 1024)
        client.sendall(f"POST {target} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(body)}\r\n\r\n".encode())
        assert answer_sent.wait(TIMEOUT), "the relay did not send its pre-body refusal"
        client.sendall(body)  # a distinct write, after the relay rejected the head
        client.shutdown(socket.SHUT_WR)
        body_sent.set()
        assert ended.wait(TIMEOUT), "the relay did not end after draining the refused request"
        answer = read_all(client)  # must be a complete HTTP answer, never WinError 10054
        head, boundary, reply = answer.partition(b"\r\n\r\n")
        assert head.startswith(f"HTTP/1.1 {status} ".encode()), answer
        assert boundary and reply == message.encode()
        response_headers = dict(headers(head))
        assert response_headers["x-aew-refusal"] == reason
        assert response_headers["content-length"] == str(len(reply))
        assert response_headers["connection"] == "close"
        assert seam.calls == [], "a pre-body refusal connected upstream"
        assert service.counts().get(reason) == 1
        if status != 403:
            assert service.counts().get(f"credential:{cause}" + ("_retryable" if status == 503 else "")) == 1
    finally:
        body_sent.set()
        client.close()
        thread.join(TIMEOUT)
        service.close()
    assert not thread.is_alive()


@pytest.mark.parametrize("status,cause,retryable", [(401, "expired", False), (503, "unreadable", True)],
                         ids=["expired-401", "retryable-503"])
def test_a_provider_sized_http_post_gets_its_complete_refusal(status, cause, retryable):
    """8 MiB is inside the review's measured provider-body range; no tiny-body or AF_UNIX-only proxy proof."""
    seam = Seam(OSError("a refusal must connect nothing"))

    def resolve():
        raise relay.Unavailable(f"planted {cause} credential", cause=cause, retryable=retryable)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with ProviderRelay(Upstream(UPSTREAM), {}, connect=seam, resolve=resolve, listener=listener) as service:
            with closing(http.client.HTTPConnection(*listener.getsockname(), timeout=TIMEOUT)) as client:
                client.request("POST", "/v1/responses", b"x" * (8 * 1024 * 1024))
                answer = client.getresponse()
                assert answer.status == status and answer.read() == f"planted {cause} credential".encode()
            assert seam.calls == [] and service.counts().get("credential_unavailable" if status == 401
                                                            else "credential_unreadable") == 1


@pytest.mark.parametrize("target", [
    "/v1/models",
    "*",
    "?/backend-api/codex/responses",
    "/elsewhere?path=/backend-api/codex/responses",
    "http://provider.example/backend-api/codex/responses",
    "https://provider.example/backend-api/codex/responses",
    "/backend-api/codex",
    "/backend-api/codexX",
    "/backend-api/codex/../x",
    "/backend-api/codex/./responses",
    "/backend-api/codex/%2e%2E/x",
    "/backend-api/codex/%252e%252e/x",
    "/backend-api/codex/%2F../x",
    "/backend-api/codex/%zz",
    "/backend-api/codex/..;param/x",
    "/backend-api/codex/x;p",
    "/backend-api/codex//responses",
    "/backend-api/codex/responses#fragment",
    r"/backend-api/codex/..\elsewhere",
    "/backend-api/codex/responses?x=\t",
    "/backend-api/codex/responses?x=\n",
    "/backend-api/codex/responses?x=\x00",
    "/backend-api/codex/responses?x=\x7f",
])
def test_a_resolve_mode_target_outside_the_prefix_or_ambiguous_connects_nothing(target):
    seam = Seam(OSError("unexpected connection"))
    asked = []

    def resolve():
        asked.append(True)
        return {}, {}

    with relayed(seam, upstream="http://provider.example/backend-api/codex", resolve=resolve) as (_, client, _):
        client.sendall(f"POST {target} HTTP/1.1\r\nContent-Length: 0\r\n\r\n".encode())
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 403 Forbidden\r\n")
    assert not seam.calls and not asked


def test_resolve_mode_forwards_a_codex_path_and_its_query_as_received():
    request = b"POST /backend-api/codex/responses?include=a%2Fb HTTP/1.1\r\n\r\n"
    sent, answer, _ = exchange(Seam(), request, upstream="http://provider.example/backend-api/codex",
                               resolve=lambda: ({}, {}))
    assert answer.startswith(b"HTTP/1.1 200 OK")
    assert sent.split(b"\r\n", 1)[0] == request.split(b"\r\n", 1)[0]


def write_refreshing_store(db):
    con = sqlite3.connect(db)
    try:
        with con:
            con.execute("CREATE TABLE credential (integration_id, method_id, active, time_updated, value)")
            value = json.dumps({"type": "oauth", "access": "synthetic-access", "expires": (time.time() + 3600) * 1000})
            con.execute("INSERT INTO credential VALUES ('openai', 'chatgpt', 1, 1, ?)", (value,))
    finally:
        con.close()


@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED])
def test_a_busy_store_returns_503_and_counts_the_cause_after_the_bounded_retry(tmp_path, monkeypatch, code):
    db = tmp_path / "synthetic.db"
    write_refreshing_store(db)
    attempts = []
    pauses = []

    def busy(database, *, uri, timeout):
        attempts.append(timeout)
        assert database == f"{db.as_uri()}?mode=ro" and uri is True
        exc = sqlite3.OperationalError("database is locked")
        exc.sqlite_errorcode = code
        raise exc

    stored = login.StoredLogin("openai", {"OPENCODE_DB": str(db)})
    seam = Seam(OSError("unexpected connection"))
    with monkeypatch.context() as patch:
        patch.setattr(login.sqlite3, "connect", busy)
        patch.setattr(login, "time", SimpleNamespace(sleep=pauses.append))
        with relayed(seam, upstream="http://provider.example/backend-api/codex",
                     resolve=lambda: netns._grant("synthetic-sentinel", stored)) as (service, client, _):
            client.sendall(b"POST /backend-api/codex/responses HTTP/1.1\r\n\r\n")
            answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 503 Service Unavailable\r\n")
    assert b"X-AEW-Refusal: credential_unreadable\r\n" in answer
    assert answer.endswith(b"Try again once the store is available.")
    assert b"synthetic.db" not in answer and b"database is locked" not in answer
    assert not seam.calls
    assert len(attempts) == 2 and sum(attempts) == login.BUSY_TIMEOUT_S
    assert pauses == [login.RESOLVE_RETRY_PAUSE_S] and pauses[0] > 0
    assert service.counts().get("credential:unreadable_retryable") == 1
    assert stored()[0] == "synthetic-access"  # the same resolver works once the lock is gone


@pytest.mark.parametrize("fault", ["not-a-database", "missing-table", "directory"])
def test_a_nonbusy_store_fault_refuses_without_retry_and_names_how_to_recover(tmp_path, monkeypatch, fault):
    db = tmp_path / "synthetic.db"
    if fault == "directory":
        db.mkdir()
    elif fault == "missing-table":
        sqlite3.connect(db).close()
    else:
        db.write_text("synthetic invalid SQLite data", encoding="utf-8")
    pauses = []
    stored = login.StoredLogin("openai", {"OPENCODE_DB": str(db)})
    seam = Seam(OSError("unexpected connection"))
    with monkeypatch.context() as patch:
        patch.setattr(login, "time", SimpleNamespace(sleep=pauses.append))
        with relayed(seam, upstream="http://provider.example/backend-api/codex",
                     resolve=lambda: netns._grant("synthetic-sentinel", stored)) as (service, client, _):
            client.sendall(b"POST /backend-api/codex/responses HTTP/1.1\r\n\r\n")
            answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 401 Unauthorized\r\n")
    assert b"X-AEW-Refusal: credential_unavailable\r\n" in answer
    assert b"move it aside so OpenCode can recreate it" in answer
    assert answer.endswith(b"Log in again with your own OpenCode (`opencode auth login openai`).")
    assert b"Try again" not in answer and b"synthetic" not in answer
    assert not pauses and not seam.calls
    assert service.counts().get("credential:unreadable") == 1
    db.rename(tmp_path / "store-moved-aside")
    write_refreshing_store(db)  # stand in for OpenCode recreating the store and writing the new login
    assert stored()[0] == "synthetic-access"


@pytest.mark.parametrize("override", [False, True])
def test_the_lead_network_only_builds_refreshing_relays_to_the_builtin_upstream(monkeypatch, override):
    policy = {"containment": {"network": {"upstreams": {
        "openai": "https://override.example/backend-api/codex",
    } if override else {}}}}
    monkeypatch.setattr(netns, "listen", lambda _: None)
    monkeypatch.setattr(ProviderRelay, "start", lambda self: self)
    monkeypatch.setattr(netns.egress.EgressProxy, "start", lambda self: self)

    def policy_upstream(*args, **kwargs):
        pytest.fail("a refreshing relay must use its built-in upstream directly")

    monkeypatch.setattr(netns, "upstream", policy_upstream)
    layout = SimpleNamespace(network=netns.PROXY_ONLY, net_dir="unused")
    reads = []

    def stored():
        reads.append(True)
        return "synthetic-access", {}

    network = netns.RunNetwork.start_lead(layout, keys={}, provider_env=[], policy=policy, env={},
                                          refreshing={"openai": stored})
    try:
        if override:
            assert not network.relays and not network.login_sentinels and not reads
        else:
            assert network.relays["openai"][1].upstream.url == netns.REFRESHING_UPSTREAMS["openai"]
            assert len(reads) == 1
    finally:
        network.dir = None
        network.close()


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


@pytest.mark.parametrize("control", [b"\n", b"\r", b"\x00", b"\x1b", b"\x7f"], ids=["lf", "cr", "nul", "esc", "del"])
def test_a_header_value_with_a_control_character_is_refused_before_any_upstream_connects(control):
    """A header value may hold no control character but HTAB (RFC 9110 §5.5): one that does is refused 400
    ``bad_header``, the refusal names the header, and nothing is connected."""
    seam = Seam()
    with relayed(seam) as (service, client, token):
        client.sendall(b"GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:4101\r\nX-Request-Id: a" + control + b"b\r\n"
                       + f"Authorization: Bearer {token}\r\n\r\n".encode())
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: bad_header" in answer
    assert b"X-Request-Id" in answer and b"RFC 9110" in answer
    assert seam.calls == [] and service.counts() == {"bad_header": 1}


def test_a_request_head_with_bare_lf_line_ends_is_refused_before_any_upstream_connects():
    """A head is read as lines ended by CRLF (RFC 9112 §2.2): one whose lines end in a bare LF reads as one line, which
    is refused, never taken as separate fields."""
    seam = Seam()
    with relayed(seam) as (service, client, token):
        client.sendall(f"GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:4101\nX-Request-Id: 1\n"
                       f"Authorization: Bearer {token}\r\n\r\n".encode())
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: bad_header" in answer
    assert seam.calls == [] and service.counts() == {"bad_header": 1}


def test_a_header_value_with_a_horizontal_tab_or_obs_text_still_reaches_the_upstream():
    """HTAB is the one control character a header value may hold (RFC 9110 §5.5), and obs-text (bytes 0x80 to 0xFF)
    is no control character: both go upstream as they came."""
    seam = Seam()
    got, answer, service = exchange(seam, b"GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:4101\r\n"
                                    b"X-Request-Id: a\tb\x80c\xff\r\n\r\n")
    assert ("x-request-id", "a\tb\x80c\xff") in headers(got.split(b"\r\n\r\n", 1)[0])
    assert answer.startswith(b"HTTP/1.1 200 ") and service.counts() == {"allowed": 1}


@pytest.mark.parametrize("length", [b"\xb2", b"\xb9\xb2"], ids=["superscript-two", "superscript-one-two"])
def test_a_content_length_of_digits_other_than_ascii_is_refused_as_bad_framing_before_any_upstream_connects(length):
    """A Content-Length is ASCII digits alone (RFC 9110 §8.6): other digits are refused 400 ``bad_framing``, saying
    so, never answered as the relay's own error, and nothing is connected."""
    seam = Seam()
    with relayed(seam) as (service, client, _):
        client.sendall(b"GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:4101\r\nContent-Length: " + length
                       + b"\r\n\r\nab")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: bad_framing" in answer
    assert seam.calls == [] and service.counts() == {"bad_framing": 1}


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
    with relayed(seam, operations=("POST /embeddings",)) as (_, client, _):
        client.sendall(b"POST /v1/embeddings HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n" + body
                       + b"GET /x HTTP/1.1")
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


def test_an_http_1_0_client_that_sends_expect_is_never_sent_a_100_continue_and_its_body_still_goes():
    """No 1xx goes to an HTTP/1.0 client (RFC 9110 §15.2): the relay ignores its expectation, as an HTTP/1.0 server must
    (§10.1.1), reads its body all the same, and the client gets only the response."""
    seam = Seam()
    with relayed(seam) as (_, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.0\r\nExpect: 100-continue\r\nContent-Length: 2\r\n\r\n{}")
        upstream = seam.upstream()
        head, rest = read_head(upstream)
        if not rest:
            rest = upstream.recv(64)
        upstream.sendall(OK)
        upstream.close()
        answer = read_all(client)
    assert rest == b"{}" and "expect" not in [n for n, _ in headers(head)]
    assert answer.startswith(b"HTTP/1.1 200 OK") and b"100 Continue" not in answer


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


SSE = b"data: one\n\ndata: [DONE]\n\n"
CHUNKED = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"


@pytest.mark.parametrize(("head", "body", "cancelled"), [
    (CHUNKED, b"c\r\ndata: one\n\n\r\n10\r\ndata: [DONE]\n\n\r\n0\r\n\r\n", False),  # whole: the last chunk sent
    (CHUNKED, b"c\r\ndata: one\n\n\r\n", True),                                     # mid-stream
    (b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(SSE), SSE, False),       # whole by its length
    (b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % (len(SSE) + 9), SSE, True),  # short of its length
])
def test_a_client_that_closes_once_it_has_the_whole_answer_is_not_counted_cancelled(head, body, cancelled):
    """OpenCode closes as soon as it has a whole answer, before the upstream's own close arrives (the live lane,
    2026-10-24): only a client that leaves before the response's end, by its length or its last chunk, is a cancelled
    turn. The upstream here never closes, so the client is always first."""
    seam = Seam()
    with relayed(seam) as (service, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nContent-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(head + body)
        got = b""
        while not got.endswith(body):
            got += client.recv(4096)
        client.close()
        assert read_all(upstream) == b""  # the relay closed the upstream either way
    assert service.counts() == ({"allowed": 1, "cancelled": 1} if cancelled else {"allowed": 1})


@pytest.mark.parametrize("step", [1, 2, 3, 7, 4096])
def test_a_chunked_body_is_followed_to_its_last_chunk_and_trailer_whatever_its_pieces(step):
    """``_Body`` follows a chunked body however the network splits it: chunk extensions, a chunk whose data holds what
    looks like a last chunk, and a trailer section."""
    body = b"5;ext=1\r\n0\r\n\r\n\r\n3\r\nabc\r\n0\r\nX-Trailer: t\r\n\r\n"
    tracker = relay._Body(CHUNKED, "POST")
    for i in range(0, len(body), step):
        assert not tracker.done, i  # never done before its last byte
        tracker.feed(body[i:i + step])
    assert tracker.done


def test_a_body_without_length_or_chunks_ends_only_with_the_upstream_and_one_without_a_body_is_done_at_once():
    close_delimited = relay._Body(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n\r\n", "POST")
    close_delimited.feed(SSE)
    assert not close_delimited.done
    assert relay._Body(b"HTTP/1.1 204 No Content\r\n\r\n", "POST").done
    assert relay._Body(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n", "HEAD").done
    unreadable = relay._Body(CHUNKED, "POST")
    unreadable.feed(b"zz\r\n")  # not a chunk size: the end cannot be told, so the client's leaving counts
    assert not unreadable.done and unreadable.kind == "close"


SIGNED_OR_ODD_SIZES = [b"-6", b"-07", b"-8;x", b"+5", b"1_0"]  # ``int(token, 16)`` takes each; none is 1*HEXDIG


@pytest.mark.parametrize("size", SIGNED_OR_ODD_SIZES)
def test_a_response_chunk_size_that_is_not_hex_digits_is_unreadable_framing_and_never_a_number(size):
    """#257's quick check, Q1: a negative size never ended its chunk, so the tracker went round the same line for ever
    and the answer was never forwarded. A size that is not hex digits alone is framing that cannot be read: the end
    cannot be told, so a client's leaving counts."""
    tracker = relay._Body(CHUNKED, "POST")
    fed = threading.Thread(target=tracker.feed, args=(size + b"\r\nx",), daemon=True)
    fed.start()
    fed.join(TIMEOUT)
    assert not fed.is_alive(), "the tracker never returned"
    assert tracker.kind == "close" and not tracker.done


@pytest.mark.parametrize("size", SIGNED_OR_ODD_SIZES)
def test_a_request_chunk_size_that_is_not_hex_digits_is_refused_as_a_bad_chunk(size):
    """#257's quick check, Q1, the request side: a negative size spun the body's reader without end. It is refused,
    saying what was wrong."""
    seam = Seam()
    with relayed(seam) as (service, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n" + size + b"\r\nx")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: bad_chunk" in answer
    assert service.counts() == {"bad_chunk": 1}


def test_a_429_reaches_the_harness_as_the_upstream_sent_it_with_its_retry_after():
    """Register E123's 429 ladder, its first rung, measured here: the relay neither retries nor rewrites a rate
    limit. Whether the harness then backs off, and how parallel workers share one limit, needs a real harness run."""
    limited = (b"HTTP/1.1 429 Too Many Requests\r\nRetry-After: 7\r\nContent-Type: application/json\r\n"
               b"Content-Length: 27\r\n\r\n{\"error\":\"rate_limit_hit\"}\n")
    seam = Seam()
    got, answer, service = exchange(seam, b"POST /v1/chat/completions HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
                                    response=limited)
    head, _, body = answer.partition(b"\r\n\r\n")
    assert head.split(b"\r\n")[0] == b"HTTP/1.1 429 Too Many Requests"
    assert ("retry-after", "7") in headers(head) and body == b"{\"error\":\"rate_limit_hit\"}\n"
    # one request upstream: no retry; and it is counted by its status too, never as "allowed" alone
    assert len(seam.calls) == 1 and service.counts() == {"allowed": 1, "upstream_status:429": 1}


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


# ------------------------------------------------------------------ an earlier session's placeholder, and the record

@pytest.mark.parametrize("line, header", [
    ("POST /v1/chat/completions", "Authorization: Bearer {stale}"),
    ("POST /v1/chat/completions", "X-Api-Key: {stale}"),
    ("POST /v1/chat/completions", "X-Request-Id: {stale}"),
    ("POST /v1/chat/completions", "ChatGPT-Account-Id: {stale}"),
    ("POST /v1/chat/completions", "Accept-Encoding: gzip, {stale}"),
    ("GET /v1/models?key={stale}", "Accept: */*"),
], ids=["bearer", "api-key", "other-header", "account-header", "accept-encoding", "target"])
def test_a_placeholder_this_relay_does_not_hold_is_refused_and_nothing_connects(line, header):
    """A sentinel no relay of the run issued (an earlier session's, kept in a store), in a credential header, in any
    other header or in the request's target, is refused 401 with its reason and what to do, before anything is
    connected: no such placeholder goes upstream in the request line or the headers, and the refusal never echoes it.
    The request is recorded as refused, with its swap outcome."""
    stale = relay.sentinel()
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append) as (service, client, token):
        assert stale != token
        client.sendall(f"{line.format(stale=stale)} HTTP/1.1\r\n{header.format(stale=stale)}\r\n"
                       "Content-Length: 2\r\n\r\n{}".encode())
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 401 ") and b"X-AEW-Refusal: stale_placeholder" in answer
    assert b"no relay of this session issued" in answer and b"(for the Lead, `aew opencode`)" in answer
    # the cause a start does not cure, a login saved inside the Lead: its step is the Lead's own store, and never a
    # command that would act on the operator's own OpenCode login
    assert b".aew/local/harness/lead/xdg-data/opencode/opencode.db aside" in answer and b"opencode auth" not in answer
    assert stale.encode() not in answer and relay.SENTINEL_PREFIX.encode() not in answer
    assert seam.calls == [] and service.counts() == {"stale_placeholder": 1}
    [entry] = entries
    assert entry["swap"] == "refused_unknown_placeholder" and entry["outcome"] == "refused"
    assert (entry["reason"], entry["answered"], entry["status"]) == ("stale_placeholder", 401, None)
    assert stale not in json.dumps(entry) and token not in json.dumps(entry)


def _gzip(data: bytes) -> bytes:
    return gzip.compress(data)


def _chunked(data: bytes) -> bytes:
    return b"".join(b"%x\r\n%s\r\n" % (len(data[i:i + 7]), data[i:i + 7]) for i in range(0, len(data), 7)) + \
        b"0\r\n\r\n"


@pytest.mark.parametrize("framing", ["length", "chunked", "gzip"])
def test_a_forwarded_request_answered_401_is_recorded_with_its_status_and_never_a_credential(framing):
    """A request the relay forwarded and the upstream refused is recorded as forwarded with the upstream's 401 (and
    counted by it: never as "allowed" alone), with an excerpt of the answer whose echo of the credential, whole or
    masked by the provider, is redacted. Whatever the body's framing or coding, the excerpt is text."""
    message = (f'{{"error": {{"message": "Incorrect API key provided: {SECRET}; shown as {SECRET[:4]}...'
               f'{SECRET[-4:]}", "code": "invalid_api_key"}}}}').encode()
    body, fields = message, f"Content-Length: {len(message)}"
    if framing == "chunked":
        body, fields = _chunked(message), "Transfer-Encoding: chunked"
    elif framing == "gzip":
        body = _gzip(message)
        fields = f"Content-Encoding: gzip\r\nContent-Length: {len(body)}"
    refused = f"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\n{fields}\r\n\r\n".encode() + body
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append) as (service, client, token):
        client.sendall(f"POST /v1/chat/completions HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(refused)
        upstream.close()
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 401 ")  # relayed as the upstream sent it
    assert service.counts() == {"allowed": 1, "upstream_status:401": 1}
    [entry] = entries
    assert {k: entry[k] for k in ("route", "destination", "login", "swap", "outcome", "reason", "status")} == {
        "route": "openai", "destination": "provider.example:80", "login": "key", "swap": "swapped",
        "outcome": "forwarded", "reason": None, "status": 401}
    assert "Incorrect API key provided" in entry["excerpt"] and "invalid_api_key" in entry["excerpt"]
    blob = json.dumps(entry)
    assert SECRET not in blob and f"{SECRET[:4]}...{SECRET[-4:]}" not in blob and token not in blob
    assert len(entry["excerpt"]) <= relay.EXCERPT_BYTES


def _jwt_shaped() -> str:
    """A synthetic token in a JWT's shape, made here so the source holds no such literal."""
    import base64

    parts = (b'{"alg":"HS256"}', b'{"sub":"synthetic"}', b"synthetic-signature")
    return ".".join(base64.urlsafe_b64encode(part).decode().rstrip("=") for part in parts)


@pytest.mark.parametrize("secret", ["synthetic-generic-key-0123456789abcdefghijklmn", "0123456789abcdef" * 2,
                                    _jwt_shaped()], ids=["generic", "hex32", "jwt-shaped"])
@pytest.mark.parametrize("coding", ["identity", "gzip"])
def test_a_credential_echoed_across_the_excerpts_bound_is_redacted_whole(coding, secret):
    """An upstream's failed answer that echoes the credential it was sent across the excerpt's bound: the record holds
    none of it, not even the part before the bound, whether the body is plain or gzip."""
    start = relay.EXCERPT_BYTES - len(secret) + 1  # the echo ends one character past the bound
    message = (b"x" * start) + secret.encode() + b" was refused"
    body, fields = message, f"Content-Length: {len(message)}"
    if coding == "gzip":
        body = _gzip(message)
        fields = f"Content-Encoding: gzip\r\nContent-Length: {len(body)}"
    refused = f"HTTP/1.1 401 Unauthorized\r\n{fields}\r\n\r\n".encode() + body
    token = relay.sentinel()
    seam, entries = Seam(), []
    with relayed(seam, credentials={token: secret}, record=entries.append) as (_, client, _):
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(refused)
        upstream.close()
        read_all(client)
    [entry] = entries
    assert entry["status"] == 401 and len(entry["excerpt"]) <= relay.EXCERPT_BYTES
    assert secret[:-1] not in entry["excerpt"] and secret[: len(secret) // 2] not in entry["excerpt"], entry


def test_a_placeholder_in_a_failed_answer_is_redacted_from_the_record():
    """A failed answer that quotes a placeholder (the relay's own, or a stale one) leaves none in the record."""
    stale = relay.sentinel()
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append) as (_, client, token):
        message = f'{{"error": "unknown key {token} (also tried {stale})"}}'.encode()
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(f"HTTP/1.1 401 Unauthorized\r\nContent-Length: {len(message)}\r\n\r\n".encode() + message)
        upstream.close()
        read_all(client)
    [entry] = entries
    assert "unknown key" in entry["excerpt"] and "<redacted placeholder>" in entry["excerpt"], entry
    assert relay.SENTINEL_PREFIX not in json.dumps(entry), entry


def test_another_providers_placeholder_is_refused_with_its_own_remedy():
    """A sentinel the run issued to another provider stands for nothing here: refused, nothing connects, and the
    remedy is the provider settings, not a restart, which would not change them."""
    other = relay.sentinel()
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append) as (service, client, _):
        service.foreign = frozenset({other})
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nX-Api-Key: {other}\r\nContent-Length: 0\r\n\r\n".encode())
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 401 ") and b"X-AEW-Refusal: other_placeholder" in answer
    assert b"another provider's key" in answer and b"starting again does not change them" in answer
    assert other.encode() not in answer and seam.calls == [] and service.counts() == {"other_placeholder": 1}
    assert [(e["reason"], e["swap"]) for e in entries] == [("other_placeholder", "refused_unknown_placeholder")]


def test_a_login_header_is_the_grants_alone_and_the_clients_placeholder_is_never_forwarded():
    """A header the login's grant sets (ChatGPT's account id) is dropped from the client's request whether or not the
    grant has a value: the placeholder the login row holds never goes upstream, and nothing is refused for it."""
    token = relay.sentinel()
    seam = Seam()
    service = ProviderRelay(Upstream(UPSTREAM), {}, connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT, resolve=lambda: ({token: "synthetic-access"}, {}),
                            login_headers=("chatgpt-account-id",), issued=(token,))
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "ChatGPT-Account-Id: aew-relay-placeholder\r\nContent-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        head, _ = read_head(upstream)
        upstream.sendall(OK)
        upstream.close()
        assert read_all(client).startswith(b"HTTP/1.1 200")
    finally:
        client.close()
        thread.join(TIMEOUT)
        service.close()
        if seam.far is not None:
            seam.far.close()
    got = headers(head)
    assert ("authorization", "Bearer synthetic-access") in got
    assert not any(name == "chatgpt-account-id" for name, _ in got) and b"aew-relay-" not in head


def test_a_failed_answers_excerpt_is_cut_to_its_bound():
    """A failed answer longer than the bound is recorded up to :data:`relay.EXCERPT_BYTES` characters, exactly."""
    message = ("refused: " + "the provider explains at length " * 40).encode()
    assert len(message) > relay.EXCERPT_BYTES
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append) as (_, client, token):
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(f"HTTP/1.1 400 Bad Request\r\nContent-Length: {len(message)}\r\n\r\n".encode() + message)
        upstream.close()
        read_all(client)
    [entry] = entries
    assert entry["excerpt"] == message.decode()[:relay.EXCERPT_BYTES]


def test_a_forwarded_request_answered_200_is_recorded_with_its_status_and_no_excerpt():
    seam, entries = Seam(), []
    exchange(seam, b"GET /v1/models HTTP/1.1\r\n\r\n", record=entries.append)
    [entry] = entries
    assert (entry["outcome"], entry["status"], entry["swap"], entry["answered"]) == ("forwarded", 200, "none", 200)
    assert "excerpt" not in entry and entry["at"].endswith("Z")


def test_a_record_that_fails_is_counted_and_never_fails_the_request():
    def broken(entry: dict[str, Any]) -> None:
        raise OSError("synthetic: the record's disk is full")

    _, answer, service = exchange(Seam(), b"GET /v1/models HTTP/1.1\r\n\r\n", record=broken)
    assert answer.startswith(b"HTTP/1.1 200 ") and service.counts() == {"allowed": 1, "record_failed": 1}


def test_the_request_log_appends_one_json_line_per_request(tmp_path):
    log = relay.RequestLog(tmp_path / "relay-requests.jsonl")
    log({"status": 401, "outcome": "forwarded"})
    log({"status": None, "outcome": "refused"})
    lines = (tmp_path / "relay-requests.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["outcome"] for line in lines] == ["forwarded", "refused"]


def test_a_failed_answers_body_is_recorded_even_when_its_client_stops_reading_at_the_status():
    """A client may close as soon as it has a 401's status line: the record still holds the body the upstream sent
    after it, read for the record alone (bounded), and nothing more is sent on."""
    message = b'{"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}}'
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append) as (service, client, token):
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\n"
                         + f"Content-Length: {len(message)}\r\n\r\n".encode())
        head, _ = read_head(client)
        assert head.startswith(b"HTTP/1.1 401 ")
        client.close()  # the client has its status, and goes
        time.sleep(0.2)
        upstream.sendall(message)
        time.sleep(0.2)
        upstream.close()
    [entry] = entries
    assert (entry["status"], entry["outcome"]) == (401, "forwarded")
    assert "Incorrect API key provided" in entry["excerpt"] and "invalid_api_key" in entry["excerpt"], entry
    assert service.counts().get("upstream_status:401") == 1


@pytest.mark.parametrize(("method", "path", "base", "kind"), [
    ("POST", "/backend-api/codex/responses", "/backend-api/codex", "model"),
    ("POST", "/inference/openai/v1/chat/completions", "/inference/openai/v1", "model"),
    ("POST", "/v1/messages", "/v1", "model"),
    ("POST", "/v1beta/models/example:streamGenerateContent?alt=sse", "/v1beta", "model"),
    ("POST", "/v1beta/models/example:generateContent", "/v1beta", "model"),
    ("GET", "/v1/models", "/v1", "models_list"),
    ("POST", "/v1/messages/count_tokens", "/v1", "unknown"),
    ("POST", "/other/responses", "/v1", "unknown"),
    ("POST", "/gateway/invoke", "/gateway", "unknown"),
    ("GET", "/v1/responses", "/v1", "unknown"),
])
def test_operation_names_only_recognized_provider_api_requests(method, path, base, kind):
    assert relay._operation(method, path, base) == kind


# The relay's operation scope (register STG-05): the provider operations its policy allows, and nothing else.
OPERATIONS = json.loads((Path(__file__).parents[1] / "fixtures" / "opencode" / "relay-operations-2.2.6.json")
                        .read_text(encoding="utf-8"))


def scoped(request: bytes, *, upstream: str = UPSTREAM, credentials: dict[str, str] | None = None,
           resolve: Callable[[], relay.Grant] | None = None,
           operations: tuple[str, ...] = ()) -> tuple[bytes, Seam, ProviderRelay, list[dict[str, Any]]]:
    """``request`` (with ``TOKEN`` for the relay's sentinel) through a relay whose connect fails the test: what the
    client got, the seam, the relay and its record."""
    seam = Seam(OSError("a refused request must connect nothing"))
    entries: list[dict[str, Any]] = []
    token = relay.sentinel()
    service = ProviderRelay(Upstream(upstream), credentials if credentials is not None else {token: SECRET},
                            connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT, body_timeout=TIMEOUT,
                            resolve=resolve, record=entries.append, route="openai", login="key",
                            operations=operations)
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        client.sendall(request.replace(b"TOKEN", token.encode()))
        answer = read_all(client)
    finally:
        client.close()
        thread.join(TIMEOUT)
        service.close()
    assert not thread.is_alive(), "the relay's handler did not end"
    return answer, seam, service, entries


@pytest.mark.parametrize("call", OPERATIONS["calls"], ids=[
    f"{c['provider']}-{c.get('login', 'key')}-{c['method']}-{c['path'].partition('?')[0]}"
    for c in OPERATIONS["calls"]])
def test_every_call_opencode_makes_through_the_relay_is_forwarded_with_its_key(call):
    """Each provider call the fixture records for the pinned OpenCode passes the default scope end to end, its key
    swapped in, the path and query as sent."""
    upstream = f"http://provider.example{call['base']}"
    target = call["base"] + call["path"]
    assert relay._operation(call["method"], target, call["base"]) == call["operation"]
    assert call["operation"] in relay.DEFAULT_OPERATIONS
    seam = Seam()
    with relayed(seam, upstream=upstream) as (_, client, token):
        client.sendall(f"{call['method']} {target} HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        far = seam.upstream()
        head, _ = read_head(far)
        far.sendall(OK)
        far.close()
        answer = read_all(client)
    assert head.split(b"\r\n", 1)[0] == f"{call['method']} {target} HTTP/1.1".encode()
    assert ("authorization", f"Bearer {SECRET}") in headers(head)
    assert answer.startswith(b"HTTP/1.1 200 OK")


@pytest.mark.parametrize(("request_line", "reason"), [
    pytest.param("DELETE /v1/files/file-x", relay.OPERATION_NOT_PERMITTED, id="delete"),
    pytest.param("PUT /v1/responses", relay.OPERATION_NOT_PERMITTED, id="other-method-on-a-model-path"),
    pytest.param("PATCH /v1/models", relay.OPERATION_NOT_PERMITTED, id="other-method-on-the-model-list"),
    pytest.param("GET /v1/responses/resp-x", relay.OPERATION_NOT_PERMITTED, id="stored-response"),
    pytest.param("POST /v1/files", relay.OPERATION_NOT_PERMITTED, id="files"),
    pytest.param("GET /v1/files/file-x/content", relay.OPERATION_NOT_PERMITTED, id="file-content"),
    pytest.param("POST /v1/batches", relay.OPERATION_NOT_PERMITTED, id="batches"),
    pytest.param("POST /v1/fine_tuning/jobs", relay.OPERATION_NOT_PERMITTED, id="fine-tuning"),
    pytest.param("GET /v1/organization/admin_api_keys", relay.OPERATION_NOT_PERMITTED, id="admin-in-prefix"),
    pytest.param("POST /v1/messages/count_tokens", relay.OPERATION_NOT_PERMITTED, id="unlisted-subpath"),
    pytest.param("GET /organization/admin_api_keys", relay.OUTSIDE_UPSTREAM_PATH, id="admin-off-prefix"),
    pytest.param("POST /responses", relay.OUTSIDE_UPSTREAM_PATH, id="off-prefix"),
    pytest.param("POST /v1", relay.OUTSIDE_UPSTREAM_PATH, id="the-prefix-alone"),
    pytest.param("POST /v1/../organization/responses", relay.OUTSIDE_UPSTREAM_PATH, id="dot-dot"),
    pytest.param("POST /v1/./responses", relay.OUTSIDE_UPSTREAM_PATH, id="dot"),
    pytest.param("POST /v1//responses", relay.OUTSIDE_UPSTREAM_PATH, id="empty-segment"),
    pytest.param("POST /v1/%2e%2e/organization/responses", relay.OUTSIDE_UPSTREAM_PATH, id="percent-escape"),
    pytest.param("POST /v1/responses#x", relay.OUTSIDE_UPSTREAM_PATH, id="fragment"),
])
@pytest.mark.parametrize("credentials", [None, {}], ids=["key", "client-certificate-only"])
def test_an_operation_outside_the_relays_scope_is_refused_typed_and_journalled_and_nothing_is_connected(
        request_line, reason, credentials):
    """A request for an operation the relay's policy does not allow, or a path outside (or ambiguously spelled under)
    the upstream's prefix, is answered 403 with its own reason, counted and recorded, and nothing is connected: the
    key is never sent, and neither is a client certificate (a relay with no key presents one)."""
    answer, seam, service, entries = scoped(
        f"{request_line} HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer TOKEN\r\nContent-Length: 0\r\n\r\n".encode(),
        credentials=credentials)
    assert seam.calls == [], "a refused request connected to the upstream"
    assert answer.startswith(b"HTTP/1.1 403 Forbidden\r\n") and f"X-AEW-Refusal: {reason}".encode() in answer
    assert SECRET.encode() not in answer and b"was not sent" in answer  # what was refused, and what to do instead
    assert service.counts().get(reason) == 1 and "allowed" not in service.counts()
    [entry] = entries
    assert (entry["outcome"], entry["reason"], entry["answered"]) == ("refused", reason, 403)
    assert entry["transport"] == "not_established" and entry["upstream_headers_written"] is False
    if reason == relay.OUTSIDE_UPSTREAM_PATH:  # a path that failed the check is never recorded
        assert "method" not in entry and "endpoint" not in entry
        assert "/v1" not in json.dumps(entry) and "admin" not in json.dumps(entry)


def test_a_refused_operations_record_names_what_the_operator_would_list_and_never_its_query_or_prefix():
    """An ``operation_not_permitted`` entry carries the request's method and its endpoint under the upstream's prefix,
    the form a ``relay_operations`` entry takes, without the query (which may carry a key)."""
    _, _, _, entries = scoped(b"POST /v1/files?key=TOKEN&purpose=x HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
    [entry] = entries
    assert (entry["reason"], entry["method"], entry["endpoint"]) == (relay.OPERATION_NOT_PERMITTED, "POST", "/files")
    assert "purpose" not in json.dumps(entry) and relay.SENTINEL_PREFIX not in json.dumps(entry)
    assert "/v1" not in json.dumps(entry)
    _, _, _, [allowed] = scoped(b"POST /v1/responses HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
    assert "method" not in allowed and "endpoint" not in allowed  # an operation in scope keeps no target


def test_an_operation_the_relays_scope_refuses_names_where_the_operator_allows_it():
    answer, _, _, _ = scoped(b"POST /v1/files HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n")
    assert b"containment.network.relay_operations.openai" in answer and b"POST request was not sent" in answer


def test_a_stored_login_relay_refuses_an_operation_outside_its_scope_before_resolving_it():
    def resolve() -> relay.Grant:
        raise AssertionError("a refused operation must be refused before its credential is resolved")

    answer, seam, service, _ = scoped(b"DELETE /backend-api/codex/files/x HTTP/1.1\r\nHost: x\r\n\r\n",
                                      upstream="http://provider.example/backend-api/codex", resolve=resolve)
    assert seam.calls == [] and b"X-AEW-Refusal: operation_not_permitted" in answer
    assert service.counts().get(relay.OPERATION_NOT_PERMITTED) == 1


def test_an_operation_the_policy_lists_is_forwarded_and_labelled_and_nothing_else_is():
    """The policy adds an exact operation, by method and path under the prefix; the same path by another method, and a
    path below it, stay refused."""
    entries: list[dict[str, Any]] = []
    seam = Seam()
    token = relay.sentinel()
    service = ProviderRelay(Upstream(UPSTREAM), {token: SECRET}, connect=seam, head_timeout=TIMEOUT,
                            connect_timeout=TIMEOUT, body_timeout=TIMEOUT, record=entries.append, route="openai",
                            login="key", operations=("POST /embeddings",))
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        client.sendall(f"POST /v1/embeddings HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        far = seam.upstream()
        head, _ = read_head(far)
        far.sendall(OK)
        far.close()
        assert read_all(client).startswith(b"HTTP/1.1 200 OK")
    finally:
        client.close()
        thread.join(TIMEOUT)
        service.close()
    assert head.startswith(b"POST /v1/embeddings ") and ("authorization", f"Bearer {SECRET}") in headers(head)
    assert entries[0]["operation"] == relay.POLICY_OPERATION and entries[0]["outcome"] == "forwarded"
    for line in ("GET /v1/embeddings", "POST /v1/embeddings/x", "POST /v1/files"):
        answer, seam, _, _ = scoped(f"{line} HTTP/1.1\r\nHost: x\r\n\r\n".encode(), operations=("POST /embeddings",))
        assert seam.calls == [] and b"X-AEW-Refusal: operation_not_permitted" in answer, line


@pytest.mark.parametrize("entry", ["DELETE", "/embeddings", "post /embeddings", "CONNECT /x", "POST /",
                                   "POST /a/../b", "POST //b", "POST /a?b=1", "POST /a%2Fb", "POST https://x/a"])
def test_a_policy_operation_the_relay_cannot_match_exactly_is_refused_before_it_serves(entry):
    with pytest.raises(ValidationFailed) as caught:
        ProviderRelay(Upstream(UPSTREAM), {}, operations=(entry,))
    assert caught.value.details["reason"] == "bad_relay_operation"


def test_only_the_adopted_policy_widens_a_runs_relay_and_a_bad_entry_refuses_its_start(tmp_path, monkeypatch):
    """``RunNetwork.start`` reads the provider's ``relay_operations`` from the execution policy on the host, at the
    relay's start; the run's request has no say (the relay takes no other input), and an entry the relay cannot use
    refuses the start, typed."""
    monkeypatch.setattr(netns, "listen", lambda _: None)
    monkeypatch.setattr(ProviderRelay, "start", lambda self: self)
    layout = SimpleNamespace(network=netns.PROXY_ONLY, net_dir=str(tmp_path / "net"))

    def network(policy: dict[str, Any] | None) -> netns.RunNetwork:
        return netns.RunNetwork.start(layout, provider="openai", provider_env=["OPENAI_API_KEY"], policy=policy,
                                      env={"OPENAI_API_KEY": SECRET}, relay_needed=True)

    listed = {"containment": {"network": {"relay_operations": {"openai": ["POST /embeddings"],
                                                               "anthropic": ["POST /files"]}}}}
    widened, plain = network(listed), network(None)
    try:
        assert widened.relay is not None and plain.relay is not None
        assert widened.relay.listed == {("POST", "/embeddings")}  # its own provider's entries alone
        assert plain.relay.listed == frozenset()
    finally:
        widened.close()
        plain.close()
    bad = {"containment": {"network": {"relay_operations": {"openai": ["POST /a/../b"]}}}}
    with pytest.raises(netns.ContainmentUnavailable) as caught:
        network(bad)
    assert caught.value.details["reason"] == "bad_relay_operation"


def test_a_policy_operation_applies_to_the_stored_login_relay_too_and_one_it_could_never_match_refuses_its_start():
    """``relay_operations.<provider>`` applies to whichever upstream the provider's relay uses. An entry with ``:``
    suits an API-key relay but no stored-login path holds one, so a stored-login relay refuses it at its start rather
    than holding an entry that can never match."""
    assert ProviderRelay(Upstream(UPSTREAM), {}, operations=("POST /models/x:embed",)).listed == {
        ("POST", "/models/x:embed")}
    with pytest.raises(ValidationFailed) as caught:
        ProviderRelay(Upstream("http://provider.example/backend-api/codex"), {}, resolve=lambda: ({}, {}),
                      operations=("POST /models/x:embed",))
    assert caught.value.details["reason"] == "bad_relay_operation"
    policy = {"containment": {"network": {"relay_operations": {"openai": ["POST /models/x:embed"]}}}}
    assert netns.relay_operations("openai", policy) == ("POST /models/x:embed",)
    with pytest.raises(netns.ContainmentUnavailable) as refused:
        netns.relay_operations("openai", policy, resolved=True)
    assert refused.value.details["reason"] == "bad_relay_operation"
    plain = {"containment": {"network": {"relay_operations": {"openai": ["POST /embeddings"]}}}}
    assert netns.relay_operations("openai", plain, resolved=True) == ("POST /embeddings",)


def test_the_execution_policy_takes_a_relay_operation_only_as_method_and_exact_path():
    import yaml

    from aew.policy import execution

    def policy(entries: list[str]) -> bytes:
        data = yaml.safe_load(execution.TEMPLATE)
        data.setdefault("containment", {}).setdefault("network", {})["relay_operations"] = {"openai": entries}
        return json.dumps(data).encode()

    assert execution.parse(policy(["POST /embeddings"]), source="t")["containment"]["network"]["relay_operations"]
    for bad in ("DELETE", "post /embeddings", "POST https://x/a", "POST /a b", "POST /embeddings/", "POST /"):
        with pytest.raises(ValidationFailed):
            execution.parse(policy([bad]), source="t")


# ---------------------------------------------------------------------------------------------- bounds and outcome

MODEL_CALL = b"POST /v1/responses HTTP/1.1\r\n"
# An operation the policy lists, whose body the relay streams as it comes (a model call's it reads whole: E361)
STREAMED_CALL = b"POST /v1/embeddings HTTP/1.1\r\n"
STREAMED = ("POST /embeddings",)


def test_a_body_over_the_relays_bound_is_refused_413_and_nothing_is_connected():
    """A ``Content-Length`` over the bound is refused before the credential is resolved or anything connected."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, max_body=1024) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 1025\r\n\r\n" + b"x" * 1025)
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 413 ") and b"X-AEW-Refusal: request_too_large" in answer
    assert seam.calls == [] and service.counts() == {"request_too_large": 1}
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == "request_too_large" and row["answered"] == 413
    assert row["upstream_headers_written"] is False and row["transport"] == "not_established"


def test_a_body_at_the_relays_bound_is_forwarded_whole():
    seam = Seam()
    with relayed(seam, max_body=1024, operations=STREAMED) as (_, client, _):
        client.sendall(STREAMED_CALL + b"Content-Length: 1024\r\n\r\n" + b"x" * 1024)
        upstream = seam.upstream()
        _, body = read_head(upstream)
        while len(body) < 1024:
            data = upstream.recv(4096)
            assert data, body
            body += data
        upstream.sendall(OK)
        upstream.close()
        answer = read_all(client)
    assert body == b"x" * 1024 and answer.endswith(b"ok")


def test_a_chunked_body_over_the_relays_bound_is_refused_and_the_upstream_never_gets_it_whole():
    """A chunked body is counted as it comes: the chunk that passes the bound is refused at its size line, which is
    not sent, so the upstream never gets the last chunk (never a request it could accept)."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, max_body=1024, operations=STREAMED) as (service, client, _):
        client.sendall(STREAMED_CALL + b"Transfer-Encoding: chunked\r\n\r\n" + b"200\r\n" + b"x" * 512 + b"\r\n"
                       + b"201\r\n" + b"y" * 513 + b"\r\n0\r\n\r\n")
        answer = read_all(client)
        upstream = seam.upstream()
        got = read_all(upstream)
    assert answer.startswith(b"HTTP/1.1 413 ") and b"X-AEW-Refusal: request_too_large" in answer
    assert got.endswith(b"200\r\n" + b"x" * 512 + b"\r\n") and b"201" not in got.partition(b"\r\n\r\n")[2]
    assert service.counts() == {"request_too_large": 1}
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == "request_too_large"


def test_a_request_beyond_the_relays_concurrency_bound_gets_503_and_connects_nothing():
    """With the bound's requests in progress, the next is refused 503 ``relay_busy`` before its head is read, and is
    not connected; once one ends, a request is served again."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, max_active=1) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)  # the first request is in progress, its answer not yet come
        second, served = socket.socketpair()
        second.settimeout(TIMEOUT)
        with closing(second):
            thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
            thread.start()
            second.sendall(MODEL_CALL + b"Content-Length: 0\r\n\r\n")
            busy = read_all(second)
            thread.join(TIMEOUT)
        assert busy.startswith(b"HTTP/1.1 503 ") and b"X-AEW-Refusal: relay_busy" in busy
        assert len(seam.calls) == 1
        upstream.sendall(OK)
        upstream.close()
        assert read_all(client).endswith(b"ok")
    assert service.counts() == {"relay_busy": 1, "allowed": 1}
    busy_row, done_row = records
    assert busy_row["outcome"] == "refused" and busy_row["reason"] == "relay_busy" and busy_row["answered"] == 503
    assert done_row["outcome"] == "forwarded" and done_row["ended"] == "complete"
    assert service._active == 0  # each request gave its place back
    seam2 = Seam()
    _, again, _ = exchange(seam2, MODEL_CALL + b"Content-Length: 0\r\n\r\n", max_active=1)
    assert again.endswith(b"ok")


def test_a_stalled_stream_ends_at_the_relays_time_bound_and_its_outcome_is_unknown():
    """A response that stops mid-body is ended at the bound: the client's connection closes, and the record says the
    stream was cut and the outcome is unknown (the provider may have finished the call)."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, stream_timeout=0.5) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nab")
        answer = read_all(client)  # ends when the relay ends the stream; the upstream never closes
    assert answer.startswith(b"HTTP/1.1 200 ") and answer.endswith(b"ab")
    [row] = records
    assert row["ended"] == "stream_timeout" and row["outcome"] == "unknown" and row["reason"] == "stream_timeout"
    assert row["status"] == 200 and service.counts()["stream_timeout"] == 1


def test_a_response_that_never_starts_is_answered_504_at_the_time_bound_and_its_outcome_is_unknown():
    seam, records = Seam(), []
    with relayed(seam, record=records.append, stream_timeout=0.5) as (_, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)  # the request went upstream; no answer comes
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 504 ") and b"X-AEW-Refusal: stream_timeout" in answer
    [row] = records
    assert row["outcome"] == "unknown" and row["reason"] == "stream_timeout" and row["upstream_headers_written"]
    assert row["ended"] == "stream_timeout"


def test_a_mid_response_break_records_upstream_outcome_unknown():
    """The upstream's connection closes before the end its framing names: the client has the head and what came, and
    the record says the outcome is unknown, never forwarded whole."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\npartial")
        upstream.close()
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 200 ") and answer.endswith(b"partial")
    [row] = records
    assert row["outcome"] == "unknown" and row["reason"] == relay.UPSTREAM_OUTCOME_UNKNOWN
    assert row["ended"] == "upstream_broken" and row["status"] == 200
    assert service.counts() == {"allowed": 1, "upstream_outcome_unknown": 1}
    assert len(seam.calls) == 1  # never retried


def test_a_break_after_the_request_went_upstream_is_outcome_unknown_and_never_unreachable():
    """The upstream reads the request and closes without an answer: the provider may have accepted it, so the client
    is told ``upstream_outcome_unknown``, not ``upstream_unreachable`` (which says the request was not sent), and the
    relay does not send it again."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 2\r\n\r\n{}")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.close()
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 502 ") and b"X-AEW-Refusal: upstream_outcome_unknown" in answer
    assert b"upstream_unreachable" not in answer and len(seam.calls) == 1
    [row] = records
    assert row["outcome"] == "unknown" and row["reason"] == "upstream_outcome_unknown"
    assert row["upstream_headers_written"] is True and service.counts() == {"upstream_outcome_unknown": 1}


def test_a_connect_failure_is_recorded_as_not_sent():
    seam, records = Seam(error=ConnectionRefusedError(111, "synthetic: refused")), []
    with relayed(seam, record=records.append) as (_, client, _):
        client.sendall(b"GET /v1/models HTTP/1.1\r\n\r\n")
        read_all(client)
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == "upstream_unreachable"
    assert row["upstream_headers_written"] is False


def test_each_record_names_its_own_request_id_and_the_policys_sha_and_no_certificate_without_one():
    seam, records = Seam(), []
    for _ in range(2):
        exchange(seam, b"GET /v1/models HTTP/1.1\r\n\r\n", record=records.append, policy_sha256="ab" * 32)
        seam = Seam()
    first, second = records
    assert first["request_id"] != second["request_id"]
    assert all(len(r["request_id"]) == 16 and int(r["request_id"], 16) >= 0 for r in records)
    assert first["policy_sha256"] == second["policy_sha256"] == "ab" * 32
    assert first["client_certificate_sha256"] is None and first["ended"] == "complete"


def test_the_relays_bounds_are_stated_and_the_run_network_passes_its_policys_sha(tmp_path, monkeypatch):
    """The defaults are the module's stated bounds; a run's network gives its relay the policy's sha."""
    service = ProviderRelay(Upstream(UPSTREAM), {})
    assert (service.max_body, service.max_active, service.stream_timeout) == (
        relay.MAX_BODY, relay.MAX_ACTIVE, relay.STREAM_TIMEOUT)
    service.close()
    seen: list[dict[str, Any]] = []
    real = relay.ProviderRelay

    def spy(*args: Any, **kw: Any) -> ProviderRelay:
        seen.append(kw)
        return real(*args, **kw)

    monkeypatch.setattr(relay, "ProviderRelay", spy)
    # No socket file and no serving thread: this asserts only what the start hands the relay, so it runs on every
    # platform (Windows has no AF_UNIX), as the relay_operations start test above does.
    monkeypatch.setattr(netns, "listen", lambda _: None)
    monkeypatch.setattr(ProviderRelay, "start", lambda self: self)
    layout = SimpleNamespace(network=netns.PROXY_ONLY, net_dir=str(tmp_path), private_network=True)
    net = netns.RunNetwork.start(layout, provider="openai", provider_env=["OPENAI_API_KEY"], policy=None,
                                 env={"OPENAI_API_KEY": SECRET}, relay_needed=True, policy_sha256="cd" * 32)
    try:
        assert [kw["policy_sha256"] for kw in seen] == ["cd" * 32]
    finally:
        net.close()


def _chunked_refused(body: bytes, max_body: int) -> tuple[bytes, bytes, list[dict[str, Any]]]:
    """A chunked request ``body`` through a relay bounded at ``max_body``: what the client got, what the upstream got
    after the request head, and the records."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, max_body=max_body, operations=STREAMED) as (_, client, _):
        client.sendall(STREAMED_CALL + b"Transfer-Encoding: chunked\r\n\r\n" + body)
        answer = read_all(client)
        upstream = seam.upstream()
        got = read_all(upstream).partition(b"\r\n\r\n")[2]
    return answer, got, records


@pytest.mark.parametrize(("body", "reason", "sent"), [
    (b"3;x=a\n0\n\nX\r\nabc\r\n0\r\n\r\n", b"bad_chunk", b""),  # LF in an extension
    (b"3;x=\x00\r\nabc\r\n0\r\n\r\n", b"bad_chunk", b""),  # NUL in an extension
    (b"\n3\r\nabc\r\n0\r\n\r\n", b"bad_chunk", b""),  # LF before the size
    (b"3\x0c\r\nabc\r\n0\r\n\r\n", b"bad_chunk", b""),  # FF after the size
    (b"0\r\nX-T: a\nX-U: b\r\n\r\n", b"bad_header", b"0\r\n"),  # LF in a trailer field's value
    (b"0\r\nX-T: \x1b\r\n\r\n", b"bad_header", b"0\r\n"),  # a C0 control in a trailer field's value
    (b"0\r\nnot a field\r\n\r\n", b"bad_header", b"0\r\n"),  # a trailer line that is no field
], ids=["ext-lf", "ext-nul", "size-lf", "size-ff", "trailer-lf", "trailer-esc", "trailer-not-a-field"])
def test_a_chunk_extension_or_trailer_field_with_a_control_character_is_refused_and_never_sent(body, reason, sent):
    """Chunk extensions and trailer fields are held to the same field-value rule as the head's (RFC 9112 §7.1.1,
    §7.1.2; RFC 9110 §5.5): the line is refused 400 and never sent, so the upstream never gets the request whole."""
    answer, got, records = _chunked_refused(body, 1 << 20)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: " + reason in answer
    assert got == sent
    assert records[0]["outcome"] == "refused" and records[0]["reason"] == reason.decode()


def test_a_chunk_extension_and_a_trailer_field_that_keep_the_rule_still_reach_the_upstream():
    """HTAB and obs-text are allowed in an extension and a trailer field, as in a header value."""
    seam = Seam()
    body = b"3;x=\ta\x80\r\nabc\r\n0\r\nX-T: a\tb\xff\r\n\r\n"
    with relayed(seam, operations=STREAMED) as (_, client, _):
        client.sendall(STREAMED_CALL + b"Transfer-Encoding: chunked\r\n\r\n" + body)
        upstream = seam.upstream()
        _, rest = read_head(upstream)
        while not rest.endswith(b"\r\n\r\n") and (data := upstream.recv(4096)):
            rest += data
        if rest == body:
            upstream.sendall(OK)
        upstream.close()
        answer = read_all(client)
    assert rest == body and answer.startswith(b"HTTP/1.1 200 ")


def test_a_trailer_section_counts_against_the_body_bound_and_never_goes_upstream_past_it():
    """Review of #542, B1: the trailer lines after the last chunk are body bytes too."""
    line = b"X-T: " + b"a" * 600 + b"\r\n"
    answer, got, records = _chunked_refused(b"0\r\n" + line * 3 + b"\r\n", 1024)
    assert answer.startswith(b"HTTP/1.1 413 ") and b"X-AEW-Refusal: request_too_large" in answer
    assert got == b"0\r\n" + line and not got.endswith(b"\r\n\r\n")  # the end of the request never went
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == "request_too_large"


def test_a_chunk_extension_counts_against_the_body_bound():
    """Review of #542, B1: a size line's extension is counted as it is sent, so a 1-byte chunk with a long extension
    is refused at its size line, and nothing of it goes upstream."""
    answer, got, records = _chunked_refused(b"1;" + b"e" * 2000 + b"\r\nX\r\n0\r\n\r\n", 1024)
    assert answer.startswith(b"HTTP/1.1 413 ") and got == b""
    assert records[0]["reason"] == "request_too_large"


def test_each_chunks_crlf_counts_against_the_body_bound():
    """Review of #542, B1: the bound is on the body as it goes upstream, its framing included: 15 bytes of chunked
    body that carry 5 of data pass a 15-byte bound and not a 14-byte one."""
    body = b"5\r\nhello\r\n0\r\n\r\n"
    answer, got, _ = _chunked_refused(body, 14)
    assert answer.startswith(b"HTTP/1.1 413 ") and got == body[:-2]  # all but the line that ends the request
    seam = Seam()
    with relayed(seam, max_body=15, operations=STREAMED) as (_, client, _):
        client.sendall(STREAMED_CALL + b"Transfer-Encoding: chunked\r\n\r\n" + body)
        upstream = seam.upstream()
        _, rest = read_head(upstream)
        while not rest.endswith(b"0\r\n\r\n"):
            data = upstream.recv(4096)
            assert data, rest
            rest += data
        upstream.sendall(OK)
        upstream.close()
        assert read_all(client).endswith(b"ok")
    assert rest == body


def test_a_chunk_not_followed_by_crlf_is_refused_as_malformed():
    """Review of #542, B1: a chunk's two bytes after its data are CRLF exactly, never two other bytes passed on."""
    answer, got, records = _chunked_refused(b"5\r\nhelloXY0\r\n\r\n", 1024)
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: bad_chunk" in answer
    assert b"XY" not in got and records[0]["outcome"] == "refused"


def test_a_failed_answer_whose_body_breaks_stays_forwarded():
    """Review of #542, m1: a 4xx or 5xx the provider sent has settled the call; a body cut after it changes nothing,
    so the record keeps outcome ``forwarded`` and says how the stream ended."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 100\r\n\r\npartial")
        upstream.close()
        read_all(client)
    [row] = records
    assert row["outcome"] == "forwarded" and row["reason"] is None and row["status"] == 500
    assert row["ended"] == "upstream_broken" and "upstream_outcome_unknown" not in service.counts()


def test_an_unexpected_error_after_the_request_went_upstream_is_outcome_unknown():
    """Review of #542, m2: whatever failed, once the request's head went upstream the provider may have it."""
    seam, records = Seam(), []

    def boom(*_: Any) -> None:
        raise ValueError("synthetic: an unexpected fault in the body relay")

    with relayed(seam, record=records.append, operations=STREAMED) as (service, client, _):
        service._send_body = boom  # type: ignore[method-assign]
        client.sendall(STREAMED_CALL + b"Content-Length: 0\r\n\r\n")
        answer = read_all(client)
    assert answer.startswith(b"HTTP/1.1 502 ") and b"X-AEW-Refusal: upstream_outcome_unknown" in answer
    [row] = records
    assert row["outcome"] == "unknown" and row["upstream_headers_written"] is True
    assert service.counts()["relay_error"] == 1


# ------------------------------------------------------------------------------------- a model call's body (E361)

# What each model-call route's body carries, in the provider packages' request shapes, with a tool call's own
# arguments and a function tool's parameters naming keys the relay holds bodies to (which they never are there).
# These are written here, not recorded: the relay-operations fixture records each call's method and path alone, and
# the live lane (tests/live/test_opencode_live.py) confirms that no request a real session relays is refused for its
# body.
TINY_PNG = "data:image/png;base64,iVBORw0KGgo="
FUNCTION_PARAMETERS = {"type": "object", "properties": {"file_id": {"type": "string"}, "container": {"type": "string"},
                                                       "user_id": {"type": "string"}, "userId": {"type": "string"}}}
ROUTE_BODIES: dict[str, dict[str, Any]] = {
    "responses": {
        "model": "gpt-5", "stream": True, "store": False, "include": ["reasoning.encrypted_content"],
        "reasoning": {"effort": "medium", "summary": "auto"}, "text": {"verbosity": "medium"},
        "prompt_cache_key": "ses_1", "max_output_tokens": 32000, "tool_choice": "auto",
        "instructions": "You are a coding agent.",
        "input": [
            {"role": "developer", "content": "Follow the project's rules."},
            {"role": "user", "content": [
                {"type": "input_text", "text": "Read the attached file."},
                {"type": "input_image", "image_url": TINY_PNG, "detail": "auto"},
                {"type": "input_file", "filename": "a.pdf", "file_data": "data:application/pdf;base64,JVBERi0="}]},
            {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque", "summary": []},
            {"type": "function_call", "call_id": "c1", "name": "read", "arguments": '{"file_id": "x"}'},
            {"type": "function_call_output", "call_id": "c1", "output": "the file's text"}],
        "tools": [{"type": "function", "name": "read", "description": "Read a file", "strict": False,
                   "parameters": FUNCTION_PARAMETERS}]},
    "chat": {
        "model": "gpt-4.1", "stream": True, "stream_options": {"include_usage": True}, "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": [{"type": "text", "text": "Look."},
                                         {"type": "image_url", "image_url": {"url": TINY_PNG}}]},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"file_id": "x"}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "the file's text"}],
        "tools": [{"type": "function", "function": {"name": "read", "parameters": FUNCTION_PARAMETERS}}]},
    "messages": {
        "model": "claude-sonnet-4-5", "max_tokens": 4096, "stream": True,
        "thinking": {"type": "enabled", "budget_tokens": 1024}, "tool_choice": {"type": "auto"},
        "system": [{"type": "text", "text": "You are a coding agent.", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "Read the attached file."},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}},
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": "JVBERi0="}}]},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "...", "signature": "opaque"},
                {"type": "tool_use", "id": "t1", "name": "read", "input": {"file_id": "x", "container": "y"}}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "the text"}]}]}],
        "tools": [{"name": "read", "description": "Read a file", "input_schema": FUNCTION_PARAMETERS,
                   "cache_control": {"type": "ephemeral"}}]},
    "gemini": {
        "systemInstruction": {"parts": [{"text": "You are a coding agent."}]},
        "contents": [
            {"role": "user", "parts": [{"text": "Look."},
                                       {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgo="}}]},
            {"role": "model", "parts": [{"functionCall": {"name": "read", "args": {"fileData": "x"}}}]},
            {"role": "user", "parts": [{"functionResponse": {"name": "read",
                                                             "response": {"cachedContent": "x"}}}]}],
        "tools": [{"functionDeclarations": [{"name": "read", "parameters": FUNCTION_PARAMETERS}]}],
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
        "generationConfig": {"maxOutputTokens": 4096, "thinkingConfig": {"includeThoughts": True}}},
}
ROUTE_TARGETS = {"responses": "/v1/responses", "chat": "/v1/chat/completions", "messages": "/v1/messages",
                 "gemini": "/v1/models/gemini-2.5-pro:streamGenerateContent?alt=sse"}


def _with(route: str, **extra: Any) -> dict[str, Any]:
    return {**ROUTE_BODIES[route], **extra}


def _user_part(route: str, part: dict[str, Any]) -> dict[str, Any]:
    """The route's body with one more content part in a user turn."""
    body = json.loads(json.dumps(ROUTE_BODIES[route]))
    if route == "responses":
        body["input"][1]["content"].append(part)
    elif route == "chat":
        body["messages"][1]["content"].append(part)
    elif route == "messages":
        body["messages"][0]["content"].append(part)
    else:
        body["contents"][0]["parts"].append(part)
    return body


def _tools(route: str, tool: dict[str, Any]) -> dict[str, Any]:
    body = json.loads(json.dumps(ROUTE_BODIES[route]))
    body["tools"].append(tool)
    return body


def model_call(route: str, body: bytes, *, extra_headers: bytes = b"", target: str | None = None) -> bytes:
    return (f"POST {target or ROUTE_TARGETS[route]} HTTP/1.1\r\n".encode() + extra_headers
            + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)


def refused_call(request: bytes, **kw: Any) -> tuple[bytes, Seam, list[dict[str, Any]]]:
    """``request`` through a relay that must refuse it: what the client got, the seam, the records."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, **kw) as (_, client, _):
        client.sendall(request)
        answer = read_all(client)
    return answer, seam, records


def forwarded(request: bytes, **kw: Any) -> tuple[bytes, bytes, bytes, list[dict[str, Any]]]:
    """``request`` through a relay to an upstream that reads the request whole (its ``Content-Length``) before it
    answers ``OK``: (the head and the body the upstream got, what the client got, the records)."""
    seam, records = Seam(), []
    with relayed(seam, record=records.append, **kw) as (_, client, _):
        client.sendall(request)
        upstream = seam.upstream()
        got_head, body = read_head(upstream)
        length = int(dict(headers(got_head))["content-length"])
        while len(body) < length:
            data = upstream.recv(65536)
            assert data, body
            body += data
        upstream.sendall(OK)
        upstream.close()
        answer = read_all(client)
    return got_head, body, answer, records


OUTSIDE_FIELDS = [
    ("responses", _with("responses", previous_response_id="resp_1"), "previous_response_id"),
    ("responses", _with("responses", conversation="conv_1"), "conversation"),
    ("responses", _with("responses", prompt={"id": "pmpt_1"}), "prompt"),
    ("responses", _user_part("responses", {"type": "input_file", "file_id": "file_1"}), "file_id"),
    ("responses", _user_part("responses", {"type": "input_file", "file_url": "https://x.example/a.pdf"}), "file_url"),
    ("responses", _user_part("responses", {"type": "input_image", "file_id": "file_1"}), "file_id"),
    ("responses", _tools("responses", {"type": "file_search", "vector_store_ids": ["vs_1"]}), "tools.file_search"),
    ("responses", _tools("responses", {"type": "mcp", "server_label": "x", "server_url": "https://x.example"}),
     "tools.mcp"),
    ("responses", _tools("responses", {"type": "web_search"}), "tools.web_search"),
    ("chat", _with("chat", web_search_options={}), "web_search_options"),
    ("chat", _user_part("chat", {"type": "file", "file": {"file_id": "file_1"}}), "file_id"),
    ("chat", _tools("chat", {"type": "web_search"}), "tools.web_search"),
    ("messages", _with("messages", mcp_servers=[{"type": "url", "url": "https://x.example", "name": "x"}]),
     "mcp_servers"),
    ("messages", _with("messages", container="container_1"), "container"),
    ("messages", _user_part("messages", {"type": "document", "source": {"type": "file", "file_id": "file_1"}}),
     "file_id"),
    ("messages", _tools("messages", {"type": "web_search_20250305", "name": "web_search"}), "tools.web_search"),
    ("gemini", _with("gemini", cachedContent="cachedContents/1"), "cached_content"),
    ("gemini", _user_part("gemini", {"fileData": {"fileUri": "files/1", "mimeType": "text/plain"}}), "file_data"),
    ("gemini", _tools("gemini", {"googleSearch": {}}), "tools.google_search"),
    ("gemini", _user_part("gemini", {"functionResponse": {"name": "r", "response": {}, "parts": [
        {"fileData": {"fileUri": "files/1", "mimeType": "text/plain"}}]}}), "file_data"),
    ("responses", _tools("responses", {"name": "read"}), "tools.untyped"),
    ("responses", _tools("responses", {"type": "function", "name": "x", "Type": "web_search"}), "tools.web_search"),
    ("messages", _tools("messages", {"type": "custom", "name": "x", "Type": "web_search_20250305"}),
     "tools.web_search"),
]


@pytest.mark.parametrize("route,body,field", OUTSIDE_FIELDS,
                         ids=[f"{route}-{field}-{i}" for i, (route, _, field) in enumerate(OUTSIDE_FIELDS)])
def test_a_model_call_whose_body_uses_a_field_outside_its_policy_is_refused_naming_it_and_sends_nothing_upstream(
        route, body, field):
    """Register E361: a model call's body is held to the provider's allowed operations as its path is. A body that
    uses a field the policy does not opt in is refused 403, naming the field, recorded ``refused``, and nothing is
    connected, so not one byte of it goes upstream."""
    answer, seam, records = refused_call(model_call(route, json.dumps(body).encode()))
    assert answer.startswith(b"HTTP/1.1 403 ") and b"X-AEW-Refusal: body_field_not_permitted" in answer
    assert field.encode() in answer and b"containment.network.relay_body_fields.openai" in answer
    assert seam.calls == []
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == relay.BODY_FIELD_NOT_PERMITTED
    assert row["body_fields"] == [field] and row["upstream_headers_written"] is False


@pytest.mark.parametrize("route", sorted(ROUTE_BODIES))
def test_a_model_call_with_only_the_fields_of_the_call_itself_is_forwarded_as_it_was_sent(route):
    """Each route's ordinary body, with a tool call's arguments and a function's parameters naming held keys (which
    are the model's and the tool's, never the provider's), passes, and the upstream gets it byte for byte."""
    body = json.dumps(ROUTE_BODIES[route]).encode()
    head, rest, answer, _ = forwarded(model_call(route, body))
    assert answer.endswith(b"ok") and rest == body and ("content-length", str(len(body))) in headers(head)


@pytest.mark.parametrize("spelling", ["previousResponseId", "PREVIOUS_RESPONSE_ID", "previous-response-id"])
def test_a_held_field_is_refused_in_any_spelling_an_upstream_might_read_as_it(spelling):
    """An upstream's parser may take a key in another case, or in camel case (Google's takes both), so the relay
    matches a held key without its case, ``_`` or ``-``."""
    answer, seam, _ = refused_call(model_call("responses", json.dumps(_with("responses", **{spelling: "r"})).encode()))
    assert b"X-AEW-Refusal: body_field_not_permitted" in answer and seam.calls == []
    answer, seam, _ = refused_call(model_call("gemini", json.dumps(_with("gemini", cached_content="c")).encode()))
    assert b"cached_content" in answer and seam.calls == []


def test_a_field_the_adopted_policy_opts_in_for_the_provider_is_forwarded_and_no_other_is():
    """``body_fields`` (the policy's ``relay_body_fields.<provider>``) opts in a field, and a tool by its type; one
    opted in passes whole, and a body that also uses another is still refused, naming only that one."""
    body = json.dumps(_tools("responses", {"type": "web_search"}) | {"previous_response_id": "r"}).encode()
    _, rest, answer, _ = forwarded(model_call("responses", body),
                                   body_fields=("previous_response_id", "tools.web_search"))
    assert answer.endswith(b"ok") and rest == body
    answer, seam, records = refused_call(model_call("responses", body), body_fields=("previous_response_id",))
    assert b"X-AEW-Refusal: body_field_not_permitted" in answer and seam.calls == []
    assert records[0]["body_fields"] == ["tools.web_search"]


def test_a_request_cannot_opt_its_own_body_field_in():
    """Only the policy the relay was started from opts a field in: a header, a query or the body itself naming the
    policy's setting changes nothing."""
    body = _with("responses", previous_response_id="r", relay_body_fields={"openai": ["previous_response_id"]})
    for request in (
            model_call("responses", json.dumps(body).encode(),
                       extra_headers=b"X-AEW-Relay-Body-Fields: previous_response_id\r\n"),
            model_call("responses", json.dumps(body).encode(),
                       target="/v1/responses?relay_body_fields=previous_response_id")):
        answer, seam, _ = refused_call(request)
        assert b"X-AEW-Refusal: body_field_not_permitted" in answer and seam.calls == []


def test_a_chunked_model_call_is_read_whole_held_to_its_scope_and_sent_framed_by_its_length():
    """A chunked body is held to the same scope: refused with nothing connected when it uses a held field, and
    otherwise sent as its data, framed by its length, with no chunked framing passed on."""
    data = json.dumps(ROUTE_BODIES["responses"]).encode()
    chunked = b"".join(f"{len(part):x}\r\n".encode() + part + b"\r\n"
                       for part in (data[:100], data[100:])) + b"0\r\n\r\n"
    head, rest, answer, _ = forwarded(MODEL_CALL + b"Transfer-Encoding: chunked\r\n\r\n" + chunked)
    assert answer.endswith(b"ok") and rest == data
    assert ("content-length", str(len(data))) in headers(head) and "transfer-encoding" not in dict(headers(head))
    held = json.dumps(_with("responses", previous_response_id="r")).encode()
    answer, seam, records = refused_call(MODEL_CALL + b"Transfer-Encoding: chunked\r\n\r\n"
                                         + f"{len(held):x}\r\n".encode() + held + b"\r\n0\r\n\r\n")
    assert b"X-AEW-Refusal: body_field_not_permitted" in answer and seam.calls == []
    assert records[0]["body_fields"] == ["previous_response_id"]


@pytest.mark.parametrize("body", [
    b"{", b"[]", b'"text"', b'{"model": "m", "model": "n"}', b'{"max_tokens": NaN}', b"\xef\xbb\xbf{}",
    b'{"model": "\xff"}', b"[" * 100_000, b"{} {}"],
    ids=["truncated", "array", "string", "repeated-key", "nan", "bom", "not-utf8", "too-deep", "two-documents"])
def test_a_model_call_body_the_relay_cannot_read_as_one_json_object_is_refused_and_sends_nothing(body):
    """A body the relay cannot hold to its scope is refused 400 ``body_unreadable``, never sent on for an upstream to
    read its own way: not one JSON object, not UTF-8, a key given twice (parsers differ on which they keep)."""
    answer, seam, records = refused_call(model_call("responses", body))
    assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: body_unreadable" in answer
    assert seam.calls == [] and records[0]["outcome"] == "refused"


def test_a_compressed_model_call_body_is_refused_and_an_empty_one_goes_as_it_came():
    """A ``Content-Encoding`` the relay would have to undo to read the body is refused before it is read; an empty
    body has no field to hold, and goes as it came (the provider answers it)."""
    answer, seam, _ = refused_call(model_call("responses", b"\x1f\x8b", extra_headers=b"Content-Encoding: gzip\r\n"))
    assert b"X-AEW-Refusal: body_unreadable" in answer and seam.calls == []
    got, answer, _ = exchange(Seam(), MODEL_CALL + b"Content-Length: 0\r\n\r\n")
    assert answer.endswith(b"ok") and ("content-length", "0") in headers(got.partition(b"\r\n\r\n")[0])


def test_the_model_call_bodies_a_relay_holds_at_once_are_bounded_and_released():
    """Register E361: reading model-call bodies whole costs memory, so the relay holds at most ``max_held`` bytes for
    them at once. A body that would pass it beside the others is refused 503 ``relay_busy``, and one that would pass
    it alone 413 ``request_too_large``, with nothing connected: by its ``Content-Length`` before it is read (before a
    ``100 Continue``) and, chunked, at the chunk that would pass it. What a request held is released once its body has
    gone upstream, before its response (#551's review, m5)."""
    big = json.dumps({"model": "m", "input": "x" * 2000}).encode()
    answer, seam, _ = refused_call(model_call("responses", big, extra_headers=b"Expect: 100-continue\r\n"),
                                   max_held=1024)
    assert answer.startswith(b"HTTP/1.1 413 ") and b"X-AEW-Refusal: request_too_large" in answer
    assert b"100 Continue" not in answer and seam.calls == []
    chunked = b"".join(f"{len(big[i:i + 500]):x}\r\n".encode() + big[i:i + 500] + b"\r\n"
                       for i in range(0, len(big), 500)) + b"0\r\n\r\n"
    seam = Seam()
    with relayed(seam, max_held=1024) as (service, client, _):
        client.sendall(MODEL_CALL + b"Transfer-Encoding: chunked\r\n\r\n" + chunked)
        answer = read_all(client)
    assert b"X-AEW-Refusal: request_too_large" in answer and seam.calls == [] and service._held == 0
    seam = Seam()
    with relayed(seam, max_held=1000) as (service, client, _):
        client.sendall(MODEL_CALL + b"Content-Length: 600\r\n\r\n{")  # held while its body arrives
        deadline = time.monotonic() + TIMEOUT
        while service._held < 600 and time.monotonic() < deadline:
            time.sleep(0.01)
        second, served = socket.socketpair()
        second.settimeout(TIMEOUT)
        with closing(second):
            thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
            thread.start()
            second.sendall(model_call("responses", b"{" + b" " * 498 + b"}"))
            busy = read_all(second)
            thread.join(TIMEOUT)
        assert busy.startswith(b"HTTP/1.1 503 ") and b"X-AEW-Refusal: relay_busy" in busy and seam.calls == []
    small = json.dumps(ROUTE_BODIES["chat"]).encode()
    seam = Seam()
    with relayed(seam) as (service, client, _):
        client.sendall(model_call("chat", small))
        upstream = seam.upstream()
        _, got = read_head(upstream)
        while len(got) < len(small):
            got += upstream.recv(65536)
        deadline = time.monotonic() + TIMEOUT
        while service._held and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service._held == 0  # sent, its response not yet come
        upstream.sendall(OK)
        upstream.close()
        read_all(client)
    assert service._held == 0


def test_a_body_whose_parse_would_pass_the_relays_bound_is_refused_before_it_is_parsed():
    """#551's review, m3: parsing a body holds more than the body, most of all for many small values. The relay holds
    its estimate (``relay._scan``) within ``max_held`` before it parses, so a body that is small but would parse
    large is refused 413 with nothing connected, and the estimate is above what the scan and the parse hold. What the
    scan alone holds is within what the relay holds before it starts (``relay._scan_hold``), whatever the body:
    #551's quick check, q2 and q3. A compact object of many short unique keys whose values are each a new number
    object, sized just past a dict's resize, the costliest shape per value measured (q1, q4), keeps a margin of a
    tenth on the interpreter that runs it."""
    import itertools
    import string
    import tracemalloc

    dense = json.dumps({"model": "m", "input": [{}] * 2000}).encode()
    answer, seam, _ = refused_call(model_call("responses", dense), max_held=64 * 1024)
    assert b"X-AEW-Refusal: request_too_large" in answer and seam.calls == []
    shapes = [dense, json.dumps({"input": [[]] * 5000}).encode(), json.dumps({"a": "x" * 50_000}).encode(),
              json.dumps({"a": "\U0001F600" * 5000}, ensure_ascii=False).encode(),
              json.dumps({"a": "\U0001F600" * 5000}).encode(), json.dumps({f"k{i}": i for i in range(5000)}).encode(),
              json.dumps(["ab"] * 5000).encode().replace(b"[", b'{"a": [', 1) + b"}"]
    names = ("".join(t) for k in (1, 2, 3, 4) for t in itertools.product(string.ascii_letters, repeat=k))
    resized = 2 * 2 ** 19 // 3 + 1  # a dict of this many keys has just grown
    compact = ("{" + ",".join(f'"{name}":-9' for name in itertools.islice(names, resized)) + "}").encode()
    deep = b'{"a":' + b"[" * 200_000 + b"]" * 200_000 + b"}"
    for body in [*shapes, compact, deep]:
        held = bytearray(body)  # as the relay holds it, before the scan starts
        tracemalloc.start()
        cost, depth = relay._scan(held)
        scanned = tracemalloc.get_traced_memory()[1]
        if depth <= relay.MAX_NESTING:
            relay._document(held)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert scanned <= relay._scan_hold(len(held)), (body[:40], scanned, relay._scan_hold(len(held)))
        assert peak * (1.1 if body is compact else 1) <= cost, (body[:40], peak, cost)


def _reset_mid_body(request: bytes, **kw: Any) -> tuple[Seam, list[dict[str, Any]]]:
    """``request`` sent over TCP, then the connection reset (an RST, not a close) before its body is whole."""
    seam, records = Seam(), []
    service = ProviderRelay(Upstream(UPSTREAM), {}, connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT, record=records.append, route="openai", **kw)
    client, served = tcp_pair(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        client.sendall(request)
        if "operations" in kw:
            seam.upstream()  # a streamed body: its head has gone upstream
        # A held body: the relay is reading its head or its body, and either way the request is not whole
        client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
        client.close()
        thread.join(TIMEOUT)
    finally:
        client.close()
        service.close()
        if seam.far is not None:
            seam.far.close()
    assert not thread.is_alive()
    return seam, records


def test_a_client_that_resets_its_connection_mid_body_is_recorded_refused_incomplete():
    """#542's quick check, m6: a client that resets mid-body never sent the request whole, so its record is
    ``refused`` (``incomplete``), not ``unknown``: for a streamed body whose head went upstream, and for a model
    call's, which the relay was still reading, with nothing connected."""
    seam, records = _reset_mid_body(STREAMED_CALL + b"Content-Length: 100\r\n\r\n" + b"x" * 10,
                                    operations=STREAMED)
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == "incomplete" and row["upstream_headers_written"] is True
    seam, records = _reset_mid_body(MODEL_CALL + b"Content-Length: 100\r\n\r\n{")
    [row] = records
    assert row["outcome"] == "refused" and row["reason"] == "incomplete" and seam.calls == []


def test_every_model_call_opencode_relays_passes_the_body_scope_with_its_ordinary_body():
    """Each call of the relay-operations fixture (OpenCode's calls through the relay, by provider and route), with
    its route's ordinary body (``ROUTE_BODIES``), is forwarded by a relay whose policy opts nothing in: the body scope
    refuses none of OpenCode's real calls."""
    fixture = json.loads((Path(__file__).parents[1] / "fixtures" / "opencode" / "relay-operations-2.2.6.json")
                         .read_text(encoding="utf-8"))
    routes = {"/responses": "responses", "/chat/completions": "chat", "/messages": "messages"}
    for call in fixture["calls"]:
        path = call["path"]
        route = routes.get(path.partition("?")[0]) or ("gemini" if path.startswith("/models/") else None)
        body = json.dumps(ROUTE_BODIES[route]).encode() if route else b""
        request = (f"{call['method']} {call['base']}{path} HTTP/1.1\r\n".encode()
                   + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        _, _, answer, records = forwarded(request, upstream=f"http://provider.example{call['base']}")
        assert answer.endswith(b"ok"), (call, answer)
        assert records[0]["outcome"] == "forwarded" and records[0]["operation"] == call["operation"], call


def test_the_adopted_policy_opts_body_fields_in_per_provider_and_a_bad_entry_refuses_the_relays_start(
        tmp_path, monkeypatch):
    """``RunNetwork.start`` reads ``relay_body_fields.<provider>`` from the execution policy on the host, at the
    relay's start: its own provider's entries alone. An entry the relay does not know refuses the start, typed, so a
    misspelt one never opts nothing in silently; the execution policy takes the setting."""
    import yaml

    from aew.policy import execution

    monkeypatch.setattr(netns, "listen", lambda _: None)
    monkeypatch.setattr(ProviderRelay, "start", lambda self: self)
    layout = SimpleNamespace(network=netns.PROXY_ONLY, net_dir=str(tmp_path / "net"))

    def network(policy: dict[str, Any] | None) -> netns.RunNetwork:
        return netns.RunNetwork.start(layout, provider="openai", provider_env=["OPENAI_API_KEY"], policy=policy,
                                      env={"OPENAI_API_KEY": SECRET}, relay_needed=True)

    opted = {"containment": {"network": {"relay_body_fields": {"openai": ["previous_response_id"],
                                                                "anthropic": ["mcp_servers"]}}}}
    widened, plain = network(opted), network(None)
    try:
        assert widened.relay is not None and widened.relay.opted == {"previous_response_id"}
        assert plain.relay is not None and plain.relay.opted == frozenset()
    finally:
        widened.close()
        plain.close()
    with pytest.raises(netns.ContainmentUnavailable) as caught:
        network({"containment": {"network": {"relay_body_fields": {"openai": ["previous_responseid"]}}}})
    assert caught.value.details["reason"] == "bad_relay_body_field"
    with pytest.raises(ValidationFailed):
        ProviderRelay(Upstream(UPSTREAM), {}, body_fields=("tools.Web Search",))
    data = yaml.safe_load(execution.TEMPLATE)
    data.setdefault("containment", {}).setdefault("network", {})["relay_body_fields"] = {"openai": ["tools.mcp"]}
    parsed = execution.parse(json.dumps(data).encode(), source="t")
    assert parsed["containment"]["network"]["relay_body_fields"] == {"openai": ["tools.mcp"]}


def _nested(depth: int) -> bytes:
    """A Responses body nested ``depth`` levels deep, its top-level object the first, ``[`` and ``]`` in a string
    besides (a string's brackets are not nesting)."""
    inner = depth - 1
    return b'{"model": "m[[[", "input": ' + b"[" * inner + b"]" * inner + b"}"


def test_a_body_at_the_relays_nesting_bound_is_walked_and_one_past_it_refused_on_every_interpreter():
    """#551's review, m4, and its CI at 04c50cce: the relay bounds a body's nesting itself (``relay.MAX_NESTING``),
    before parsing it, so a deep body is answered the same on every interpreter, never by the parser's own recursion
    limit (CPython 3.11's is about 1000 levels, 3.12's far deeper). A body at the bound is forwarded; one past it is
    refused 400 ``body_unreadable``, naming the bound, with nothing connected; and the walk over a document at the
    bound is iterative, so it holds under a recursion limit far below the bound."""
    import sys
    import traceback

    at_bound = _nested(relay.MAX_NESTING)
    assert relay._scan(at_bound)[1] == relay.MAX_NESTING
    _, rest, answer, records = forwarded(model_call("responses", at_bound))
    assert answer.endswith(b"ok") and rest == at_bound and records[0]["outcome"] == "forwarded"
    for past in (_nested(relay.MAX_NESTING + 1), _nested(2000), _nested(20_000)):
        answer, seam, records = refused_call(model_call("responses", past))
        assert answer.startswith(b"HTTP/1.1 400 ") and b"X-AEW-Refusal: body_unreadable" in answer
        assert f"deeper than {relay.MAX_NESTING}".encode() in answer and seam.calls == []
    document = json.loads(at_bound)
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(len(traceback.extract_stack()) + 30)  # far below the bound's depth
    try:
        found = relay.body_fields("/responses", document)
    finally:
        sys.setrecursionlimit(limit)
    assert found == set()


def test_a_policy_cannot_list_a_model_call_and_so_take_its_body_out_of_scope():
    """#551's review, m6, and its quick check: a model call or the model list in ``relay_operations``, in any letter
    case, and an entry whose path ends in ``/``, refuse the relay's start; and a model call is recognized as one
    whatever the policy lists, so its body is always held to its scope."""
    for entry in ("POST /responses", "POST /messages", "POST /models/g:generateContent", "GET /models",
                  "POST /Responses", "POST /MODELS/g:GENERATECONTENT", "GET /Models", "POST /responses/",
                  "POST /embeddings/"):
        with pytest.raises(ValidationFailed) as caught:
            ProviderRelay(Upstream(UPSTREAM), {}, operations=(entry,))
        assert caught.value.details["reason"] == "bad_relay_operation"
    assert relay._operation("POST", "/v1/responses", "/v1", {("POST", "/responses")}) == "model"


# ------------------------------------------------- a failed answer's body, and each provider's own credential header

class _Answer:
    """What the client got, as a socket ``http.client`` can parse a response from."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def makefile(self, *_: Any, **__: Any) -> Any:
        import io

        return io.BytesIO(self.data)


def parsed(answer: bytes) -> tuple[int, Any, bytes]:
    """The status, headers and body of ``answer`` as an HTTP client reads them, its framing held to the letter: a body
    short of its length, or chunked and cut before its last chunk, raises ``http.client.IncompleteRead``."""
    response = http.client.HTTPResponse(_Answer(answer))  # type: ignore[arg-type]
    response.begin()
    return response.status, response.headers, response.read()


def answered(parts: list[bytes], *, version: str = "HTTP/1.1", pause: float = 0.0,
             credentials: dict[str, str] | None = None) -> tuple[bytes, list[dict[str, Any]], ProviderRelay]:
    """A model call carrying the relay's sentinel, answered by an upstream that sends ``parts`` (``pause`` apart), then
    closes: what the client got, the record and the relay."""
    seam, entries = Seam(), []
    with relayed(seam, record=entries.append, credentials=credentials) as (service, client, token):
        client.sendall(f"POST /v1/responses {version}\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        for i, part in enumerate(parts):
            if i and pause:
                time.sleep(pause)
            upstream.sendall(part)
        upstream.close()
        answer = read_all(client)
    return answer, entries, service


FAILED = f'{{"error": {{"message": "Incorrect API key provided: {SECRET}", "code": "invalid_api_key"}}}}'.encode()
CLEANED = FAILED.replace(SECRET.encode(), relay.REDACTED)
LONG = b"x" * (2 * relay.EXCERPT_RAW_BYTES) + FAILED  # its credential lies past the bytes the relay holds first


def _failed(framing: str, message: bytes = FAILED, status: bytes = b"401 Unauthorized") -> list[bytes]:
    """A failed answer that carries ``message``, as the upstream sends it, framed by ``framing``."""
    head = b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\n"
    if framing == "length":
        return [head + b"Content-Length: %d\r\n\r\n" % len(message) + message]
    if framing == "chunked":  # in chunks of seven bytes, so the credential crosses several of them
        return [head + b"Transfer-Encoding: chunked\r\n\r\n" + _chunked(message)]
    if framing == "gzip":
        body = _gzip(message)
        return [head + b"Content-Encoding: gzip\r\nContent-Length: %d\r\n\r\n" % len(body) + body]
    if framing == "close":
        return [head + b"\r\n" + message]
    if framing == "slow":  # its second half comes after the relay has stopped holding: chunked as it goes on
        half = len(message) // 2
        return [head + b"Transfer-Encoding: chunked\r\n\r\n" + _chunked(message[:half])[:-5],
                _chunked(message[half:])]
    raise AssertionError(framing)


@pytest.mark.parametrize("framing", ["length", "chunked", "gzip", "close", "slow"])
@pytest.mark.parametrize("message", [FAILED, LONG], ids=["short", "past-the-hold"])
def test_a_credential_the_upstream_reflects_never_reaches_the_sandbox(framing, message, monkeypatch):
    """The relay removes a credential from a failed answer's body before it reaches the run, whatever the body's
    framing, coding or size, and however the upstream splits it: the rest of the body goes on whole, framed so the
    client reads it to its end, with the status and other headers the upstream sent."""
    monkeypatch.setattr(relay, "EXCERPT_DRAIN_S", 0.2)
    answer, entries, service = answered(_failed(framing, message), pause=0.5 if framing == "slow" else 0.0)
    assert SECRET.encode() not in answer
    status, fields, body = parsed(answer)
    assert status == 401 and fields["Content-Type"] == "application/json" and fields["Connection"] == "close"
    assert body == message.replace(SECRET.encode(), relay.REDACTED) and "Content-Encoding" not in fields
    [entry] = entries
    assert (entry["outcome"], entry["status"], entry["ended"]) == ("forwarded", 401, "complete")
    assert service.counts() == {"allowed": 1, "upstream_status:401": 1}


def test_a_failed_answer_cleaned_as_it_comes_goes_to_an_http_1_0_client_ended_by_the_close(monkeypatch):
    """An HTTP/1.0 client is never sent chunks: a failed answer the relay cleans as it streams ends with the close."""
    monkeypatch.setattr(relay, "EXCERPT_DRAIN_S", 0.2)
    answer, _, _ = answered(_failed("slow"), version="HTTP/1.0", pause=0.5)
    status, fields, body = parsed(answer)
    assert status == 401 and "Transfer-Encoding" not in fields and "Content-Length" not in fields
    assert body == CLEANED and SECRET.encode() not in answer


@pytest.mark.parametrize("framing", ["length", "chunked", "gzip", "close"])
@pytest.mark.parametrize("status", [b"400 Bad Request", b"429 Too Many Requests", b"500 Internal Server Error",
                                    b"529 Overloaded"])
def test_a_failed_answer_that_holds_no_credential_reaches_the_sandbox_byte_for_byte_as_before(framing, status):
    """A provider's own error (a rate limit, an overload, a refusal) holds no credential: the client gets exactly what
    the upstream sent, its framing and coding untouched, and no refusal header of the relay's."""
    message = b'{"error": {"type": "provider_error", "message": "upstream says no"}}'
    [sent] = _failed(framing, message, status)
    answer, entries, _ = answered([sent])
    head, _, body = sent.partition(b"\r\n\r\n")
    assert answer == relay._close_head(head + b"\r\n\r\n") + body
    assert b"X-AEW-Refusal" not in answer and entries[0]["outcome"] == "forwarded"


def test_a_failed_answer_on_a_route_that_holds_no_credential_is_never_held():
    """A route with nothing to swap in (a client certificate's) has nothing to take out: a failed answer streams as it
    comes, its head before its body, as before."""
    seam = Seam()
    with relayed(seam, credentials={}) as (_, client, _):
        client.sendall(b"POST /v1/responses HTTP/1.1\r\nContent-Length: 0\r\n\r\n")
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 4\r\n\r\n")
        head, _ = read_head(client)  # the head is here before any of the body is sent
        assert head.startswith(b"HTTP/1.1 503 ")
        upstream.sendall(b"busy")
        upstream.close()
        assert read_all(client) == b"busy"


def test_a_failed_answer_cut_while_it_is_cleaned_never_reads_as_whole():
    """An upstream that breaks after the relay stopped holding a failed answer: the client's chunked body lacks its
    last chunk, so it reads as cut, and the record keeps ``forwarded`` (the provider had settled the call)."""
    message = LONG[:-len(FAILED)] + SECRET.encode()
    head = b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: %d\r\n\r\n" % (len(message) + 100)
    answer, entries, _ = answered([head + message])
    assert SECRET.encode() not in answer
    with pytest.raises(http.client.IncompleteRead):
        parsed(answer)
    [entry] = entries
    assert (entry["outcome"], entry["status"], entry["ended"]) == ("forwarded", 500, "upstream_broken")


def test_a_successful_streamed_answer_is_relayed_byte_for_byte_as_before():
    """A 2xx answer, an SSE stream in chunks, goes to the client exactly as the upstream sent it, each event as it
    comes: nothing is held, re-framed or rewritten."""
    events = [b"data: {\"i\": %d}\n\n" % i for i in range(3)]
    seam = Seam()
    with relayed(seam) as (_, client, token):
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {token}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        read_head(upstream)
        upstream.sendall(CHUNKED + b"%x\r\n%s\r\n" % (len(events[0]), events[0]))
        got = b""
        while events[0] not in got:  # the first event is here before the upstream sends the next
            got += client.recv(4096)
        rest = b"".join(b"%x\r\n%s\r\n" % (len(e), e) for e in events[1:]) + b"0\r\n\r\n"
        upstream.sendall(rest)
        upstream.close()
        got += read_all(client)
    assert got == relay._close_head(CHUNKED) + b"%x\r\n%s\r\n" % (len(events[0]), events[0]) + rest


@pytest.mark.parametrize(("lines", "forwarded"), [
    ([], "identity"),  # none at all would accept any coding
    (["identity"], "identity"),
    (["gzip, deflate, br, zstd"], "gzip, deflate"),
    (["br;q=1.0, gzip;q=0.8, *;q=0.1"], "gzip;q=0.8, deflate;q=0.1, identity;q=0.1"),
    (["identity;q=0, *"], "identity;q=0, deflate, gzip, x-gzip"),  # what * accepted among them, still accepted
    (["gzip, *;q=0"], "gzip, deflate;q=0, identity;q=0"),
    (["gzip;q=0, *"], "gzip;q=0, deflate, identity"),  # x-gzip is gzip: a * never offers the one refused
    (["x-gzip;q=0, *"], "x-gzip;q=0, deflate, identity"),
    (["*, *;q=0.5"], "deflate, gzip, identity, x-gzip"),  # the first * names them all
    (["deflate;q=0.5, x-gzip, GZIP;q=0.9"], "deflate;q=0.5, x-gzip, GZIP;q=0.9"),  # the client's order and weights
    (["br", "gzip, zstd"], "gzip"),  # two lines read as one list
    (["br, zstd, gzip, br"], "gzip"),
    (["br, zstd"], "identity"),
    (["*"], "deflate, gzip, identity, x-gzip")])
def test_the_relay_asks_the_upstream_only_for_codings_it_can_read(lines, forwarded):
    """The upstream is asked only for codings the relay reads when it cleans a failed answer
    (``relay.READABLE_CODINGS``): the client's own of those keep their order and weights, a ``*`` stands with its
    weight for those the client does not name, and with none left the relay asks for identity."""
    request = b"GET /v1/models HTTP/1.1\r\n" + b"".join(b"Accept-Encoding: %s\r\n" % v.encode() for v in lines)
    upstream_got, answer, _ = exchange(Seam(), request + b"\r\n")
    sent = headers(upstream_got.split(b"\r\n\r\n")[0])
    assert [v for n, v in sent if n == "accept-encoding"] == [forwarded]
    assert answer.endswith(b"ok")


def test_a_successful_answer_in_a_coding_the_client_asked_for_reaches_it_byte_for_byte():
    """Narrowing what the upstream is asked for changes only the coding it picks: a 2xx answer in one of them goes to
    the client exactly as the upstream sent it."""
    body = _gzip(b'{"data": [{"id": "m"}]}')
    sent = b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: %d\r\n\r\n" % len(body) + body
    _, answer, _ = exchange(Seam(), b"GET /v1/models HTTP/1.1\r\nAccept-Encoding: gzip, br\r\n\r\n", sent)
    assert answer == relay._close_head(sent.partition(b"\r\n\r\n")[0] + b"\r\n\r\n") + body


ECHOED = f'Bearer realm="api", error="invalid_token", error_description="key {SECRET} refused"'.encode()


@pytest.mark.parametrize("framing", ["length", "chunked", "gzip", "close", "slow", "no-body"])
@pytest.mark.parametrize("message", [FAILED, b'{"error": "no"}'], ids=["body-holds-one", "body-holds-none"])
def test_a_failed_answers_head_reaches_the_sandbox_without_a_held_credential(framing, message, monkeypatch):
    """A failed answer's head is cleaned of the request's credential values like its body, in its reason phrase and
    each field value, whatever the body's framing, and the client still reads the body to its end: the other headers
    go on as the upstream sent them."""
    monkeypatch.setattr(relay, "EXCERPT_DRAIN_S", 0.2)
    status = b"401 Unauthorized " + SECRET.encode()
    if framing == "no-body":
        parts = [b"HTTP/1.1 304 " + SECRET.encode() + b"\r\nContent-Type: application/json\r\n\r\n"]
    else:
        parts = _failed(framing, message, status)
    extra = b"WWW-Authenticate: " + ECHOED + b"\r\nX-Echo: " + SECRET.encode() + b"\r\nX-Request-Id: req-1\r\n"
    parts[0] = parts[0].replace(b"\r\n", b"\r\n" + extra, 1)
    answer, entries, _ = answered(parts, pause=0.5 if framing == "slow" else 0.0)
    assert SECRET.encode() not in answer
    code, fields, body = parsed(answer)
    assert code == (304 if framing == "no-body" else 401) and fields["X-Request-Id"] == "req-1"
    assert fields["WWW-Authenticate"] == ECHOED.replace(SECRET.encode(), relay.REDACTED).decode()
    assert fields["X-Echo"] == relay.REDACTED.decode() and fields["Content-Type"] == "application/json"
    assert answer.split(b"\r\n", 1)[0].endswith(b" " + relay.REDACTED)
    if fields.get("Content-Encoding") == "gzip":  # a body that held none goes on as it came, in its coding
        body = gzip.decompress(body)
    assert body == (b"" if framing == "no-body" else message.replace(SECRET.encode(), relay.REDACTED))
    assert entries[0]["ended"] == "complete"


def test_a_failed_answers_head_keeps_its_framing_and_coding_as_they_came():
    """Only a field's value outside the response's framing and coding is cleaned: the body is read by the framing the
    upstream gave it. A head that holds no credential value is returned byte for byte."""
    head = (b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 1234\r\nTransfer-Encoding: chunked\r\n"
            b"Content-Encoding: gzip\r\nX-Trace: a1234z\r\n\r\n")
    assert relay._scrub_head(head, ["1234", "gzip"]) == head.replace(b"a1234z", b"a" + relay.REDACTED + b"z")
    assert relay._scrub_head(head, ["absent-value"]) == head and relay._scrub_head(head, []) == head
    for line in (b"HTTP/1.1 401", b"HTTP/1.1", b"garbage"):  # a status line short of its parts, as it came
        assert relay._scrub_head(line + b"\r\nX: y\r\n\r\n", ["abcd"]) == line + b"\r\nX: y\r\n\r\n"


@pytest.mark.parametrize("value", [SECRET, "abcd", "aaaa"])
def test_the_scrub_takes_a_value_out_wherever_the_bytes_are_split(value):
    """The one redaction owner, fed as a stream: a value cut across any two pieces, or repeated, is taken out whole."""
    data = b"before " + value.encode() + b" between " + value.encode() + b"aa after"
    expected = data.replace(value.encode(), relay.REDACTED)
    for cut in range(len(data) + 1):
        scrubbed = relay._Scrub([value])
        assert scrubbed.feed(data[:cut]) + scrubbed.feed(data[cut:]) + scrubbed.end() == expected, cut
    assert relay.scrub(data, [value]) == expected


# Each provider's normal request, as its SDK sends its key (OpenCode's integrations): OpenAI-shaped and OpenCode's own
# route by a bearer token, Anthropic's, Azure OpenAI's and Google's in their own headers
@pytest.mark.parametrize(("route", "header", "value"), [
    ("openai", "Authorization", "Bearer {}"), ("opencode", "Authorization", "Bearer {}"),
    ("anthropic", "x-api-key", "{}"), ("azure", "api-key", "{}"), ("google", "x-goog-api-key", "{}")])
def test_each_providers_normal_request_still_gets_its_key(route, header, value):
    token = relay.sentinel()
    seam = Seam()
    service = ProviderRelay(Upstream(UPSTREAM), {token: SECRET}, connect=seam, head_timeout=TIMEOUT,
                            connect_timeout=TIMEOUT, body_timeout=TIMEOUT, route=route, login="key")
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=service.handle, args=(served,), daemon=True)
    thread.start()
    try:
        client.sendall(f"POST /v1/responses HTTP/1.1\r\n{header}: {value.format(token)}\r\n"
                       "Content-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        head, _ = read_head(upstream)
        upstream.sendall(OK)
        upstream.close()
        assert read_all(client).endswith(b"ok")
    finally:
        client.close()
        thread.join(TIMEOUT)
        service.close()
        if seam.far is not None:
            seam.far.close()
    assert (header.lower(), value.format(SECRET)) in headers(head) and token.encode() not in head


def test_the_certificate_routes_request_carries_no_key_and_still_goes():
    """A provider reached by a client certificate alone: the relay holds no key and swaps nothing in, and the request
    goes as it came."""
    entries: list[dict[str, Any]] = []
    got, answer, _ = exchange(Seam(), b"POST /v1/chat/completions HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
                              credentials={}, record=entries.append)
    assert answer.endswith(b"ok") and not any(k in CREDENTIAL_NAMES for k, _ in headers(got.split(b"\r\n\r\n")[0]))
    assert entries[0]["swap"] == "none"


CREDENTIAL_NAMES = relay.CREDENTIAL_HEADERS
