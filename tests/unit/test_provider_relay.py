"""F28's credentialing provider relay (STG-05 CS-3b; F28 §3.3).

The client is one end of a ``socket.socketpair()``, whose other end the relay serves (``ProviderRelay.handle``) on a
thread. The connect is a seam: it hands the relay one end of another socketpair, whose other end plays the upstream
(or the operator's proxy), so every byte the upstream receives is the test's to read. Nothing contacts any host. The
credential here is a synthetic value. Every socket has a timeout and is closed in a ``finally``.
"""

from __future__ import annotations

import http.client
import json
import socket
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
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
            record: Callable[[dict[str, Any]], None] | None = None,
            ) -> Iterator[tuple[ProviderRelay, socket.socket, str]]:
    """A relay serving one connection; yields it, the client end, and the sentinel that stands for ``SECRET``."""
    token = relay.sentinel()
    service = ProviderRelay(Upstream(upstream), credentials if credentials is not None else {token: SECRET},
                            proxy=proxy, connect=seam, head_timeout=TIMEOUT, connect_timeout=TIMEOUT,
                            body_timeout=TIMEOUT, resolve=resolve, record=record, route="openai", login="key")
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
        message = "the provider relay takes only unambiguous paths under the stored login's upstream path"

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
    request = b"GET /backend-api/codex/responses?include=a%2Fb HTTP/1.1\r\n\r\n"
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
            client.sendall(b"GET /backend-api/codex/responses HTTP/1.1\r\n\r\n")
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
            client.sendall(b"GET /backend-api/codex/responses HTTP/1.1\r\n\r\n")
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
    ("GET /v1/models?key={stale}", "Accept: */*"),
], ids=["bearer", "api-key", "other-header", "account-header", "target"])
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
    import gzip

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
