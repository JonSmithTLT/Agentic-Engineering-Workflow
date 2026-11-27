"""Real HTTP through a run's provider path, as a contained harness sends it (STG-05 CS-3b; F28 §3.2, §3.3): a client on
the shim's loopback port inside, the shim's relay leg (built from the run's own spec, ``netns.shim_spec``), the
provider relay on its socket file (``netns.listen``), and a local fake upstream on 127.0.0.1. The relay's unit tests
drive ``ProviderRelay.handle`` on socket pairs; this drives the whole path over real sockets: streaming, a rate
limit, a provider's errors, ``100 Continue``, a large chunked body, a refused HTTP/2 preface, a failed answer's body
with the request's credential out of it, and the shim's answer when the relay is gone.

Nothing leaves the host and the credential is synthetic. Linux: the legs' far ends are socket files (AF_UNIX), and the
relay serves contained runs there.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from aew.harness.containment import netns, relay, shim

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the relay and the shim's legs listen "
                                "on socket files (AF_UNIX), and serve only a Linux run's network of its own")
TIMEOUT = 10.0
SECRET = "synthetic-provider-key-http-path"
GAP = 0.3  # between the fake upstream's events: the client must have each before the next is sent
BIG = 16 * 1024 * 1024  # a large model call: within the relay's bound (64 MiB), and far past every buffer on the way


def _request(conn: socket.socket) -> tuple[str, dict[str, str], bytes]:
    """The upstream's view of one request: its line, its headers (last of a name) and its body, by its length."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        data = conn.recv(65536)
        if not data:
            return "", {}, b""
        buf += data
    head, _, body = buf.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    fields = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:])}
    while len(body) < int(fields.get("content-length", "0")):
        data = conn.recv(1 << 20)
        if not data:
            break
        body += data
    return lines[0], fields, body


def _chunk(data: bytes) -> bytes:
    return b"%x\r\n%s\r\n" % (len(data), data)


class Upstream:
    """A provider on 127.0.0.1 that answers by the request's ``X-Scenario``, and keeps what each request carried."""

    def __init__(self) -> None:
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.seen: list[tuple[str, dict[str, str], int]] = []
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def port(self) -> int:
        return self.listener.getsockname()[1]

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._answer, args=(conn,), daemon=True).start()

    def _answer(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(TIMEOUT)
            line, fields, body = _request(conn)
            self.seen.append((line, fields, len(body)))
            scenario = fields.get("x-scenario", "ok")
            if scenario == "sse":
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                             b"Transfer-Encoding: chunked\r\n\r\n")
                for i in range(3):
                    conn.sendall(_chunk(b'data: {"i": %d}\n\n' % i))
                    time.sleep(GAP)
                conn.sendall(b"0\r\n\r\n")
                return
            if scenario == "echo":  # a failed answer that quotes what the request carried
                answer = json.dumps({"error": "refused", "request": fields}).encode()
                conn.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\n"
                             b"Content-Length: %d\r\n\r\n" % len(answer) + answer)
                return
            status, extra = 200, b""
            answer = json.dumps({"received": len(body)}).encode()
            if scenario == "429":
                status, extra = 429, b"Retry-After: 7\r\nx-ratelimit-remaining-requests: 0\r\n"
                answer = b'{"error": {"type": "rate_limit_error"}}'
            elif scenario.isdigit():
                status, answer = int(scenario), b'{"error": {"message": "upstream says %s"}}' % scenario.encode()
            conn.sendall(b"HTTP/1.1 %d X\r\n" % status + extra + b"Content-Type: application/json\r\n"
                         b"Content-Length: %d\r\n\r\n" % len(answer) + answer)

    def close(self) -> None:
        self.listener.close()


class RunPath:
    """One run's provider path, as the supervisor and the shim set it up, with the port the harness calls."""

    def __init__(self, directory: Path) -> None:
        self.upstream = Upstream()
        self.token = relay.sentinel()
        self.records: list[dict[str, Any]] = []
        sock = os.path.join(directory, netns.RELAY)
        self.relay = relay.ProviderRelay(relay.Upstream(f"http://127.0.0.1:{self.upstream.port}/v1"),
                                         {self.token: SECRET}, listener=netns.listen(sock),
                                         record=self.records.append, route="openai", login="key").start()
        with socket.socket() as probe:  # a free port inside, as the run's fixed one would be
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        spec = netns.shim_spec(str(directory), server=None, relay_sock=netns.RELAY)
        spec["out"][0]["port"] = port
        self.listeners = shim.listen(spec)
        self.port = port

    def send(self, request: bytes, *, then: bytes = b"") -> bytes:
        """``request`` (and ``then``, once its head has gone) to the shim's port; everything the client got."""
        with socket.create_connection(("127.0.0.1", self.port), timeout=TIMEOUT) as client:
            client.sendall(request)
            if then:
                client.sendall(then)
            return _all(client)

    def call(self, scenario: str, body: bytes = b"{}", extra: str = "") -> bytes:
        return self.send(f"POST /v1/responses HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {self.token}\r\n"
                         f"Content-Type: application/json\r\nX-Scenario: {scenario}\r\n{extra}"
                         f"Content-Length: {len(body)}\r\n\r\n".encode() + body)

    def close(self) -> None:
        for listener in self.listeners:
            listener.close()
        self.relay.close()
        self.upstream.close()


def _all(sock: socket.socket) -> bytes:
    out = b""
    while data := sock.recv(65536):
        out += data
    return out


def _head(answer: bytes) -> tuple[str, dict[str, str], bytes]:
    head, _, body = answer.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    return lines[0], {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:])}, body


@pytest.fixture
def path() -> Iterator[RunPath]:
    directory = netns.private_dir()  # where a run's sockets go: short, as a socket file's path is bounded
    served = RunPath(Path(directory))
    try:
        yield served
    finally:
        served.close()
        shutil.rmtree(directory, ignore_errors=True)


def test_a_streamed_answer_reaches_the_sandbox_event_by_event_through_the_shim(path):
    """Each server-sent event reaches the harness as the provider sends it, chunked as it came, through the shim and
    the relay: never held until the stream ends."""
    with socket.create_connection(("127.0.0.1", path.port), timeout=TIMEOUT) as client:
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {path.token}\r\nX-Scenario: sse\r\n"
                       "Content-Length: 2\r\n\r\n{}".encode())
        got, arrivals, start = b"", [], time.monotonic()
        while data := client.recv(65536):
            got += data
            arrivals.append((time.monotonic() - start, got.count(b"data: ")))
    line, fields, body = _head(got)
    assert line == "HTTP/1.1 200 OK" and fields["transfer-encoding"] == "chunked" and body.endswith(b"0\r\n\r\n")
    first = next(t for t, events in arrivals if events >= 1)
    last = next(t for t, events in arrivals if events >= 3)
    assert last - first >= 1.5 * GAP, arrivals  # the first event came a whole gap or more before the last
    assert path.upstream.seen[-1][1]["authorization"] == f"Bearer {SECRET}"


def test_a_rate_limit_reaches_the_sandbox_as_the_provider_sent_it_with_its_retry_after(path):
    line, fields, body = _head(path.call("429"))
    assert line.startswith("HTTP/1.1 429") and fields["retry-after"] == "7"
    assert fields["x-ratelimit-remaining-requests"] == "0" and b"rate_limit_error" in body
    assert "x-aew-refusal" not in fields


@pytest.mark.parametrize("status", [400, 404, 500, 502, 503, 529])
def test_a_providers_error_reaches_the_sandbox_with_its_body_and_no_refusal_of_the_relays(status, path):
    """A provider's own 4xx or 5xx passes through whole: the relay's refusal header is what tells its own 502 apart."""
    line, fields, body = _head(path.call(str(status)))
    assert line.startswith(f"HTTP/1.1 {status}") and body == b'{"error": {"message": "upstream says %d"}}' % status
    assert "x-aew-refusal" not in fields


def test_a_large_body_sent_after_100_continue_reaches_the_provider_whole(path):
    """``Expect: 100-continue``: the relay answers it itself, the body follows, and the provider gets all of it,
    without the expectation."""
    body = json.dumps({"model": "m", "input": "x" * BIG}).encode()
    with socket.create_connection(("127.0.0.1", path.port), timeout=TIMEOUT) as client:
        client.sendall(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {path.token}\r\nX-Scenario: size\r\n"
                       f"Expect: 100-continue\r\nContent-Length: {len(body)}\r\n\r\n".encode())
        interim = b""
        while b"\r\n\r\n" not in interim:
            interim += client.recv(4096)
        assert interim.startswith(b"HTTP/1.1 100 Continue\r\n\r\n")
        client.sendall(body)
        answer = interim.split(b"\r\n\r\n", 1)[1] + _all(client)
    assert _head(answer)[2] == json.dumps({"received": len(body)}).encode()
    _, fields, size = path.upstream.seen[-1]
    assert size == len(body) and "expect" not in fields


def test_a_large_chunked_model_call_reaches_the_provider_whole_framed_by_its_length(path):
    body = json.dumps({"model": "m", "input": "y" * BIG}).encode()
    chunked = b"".join(_chunk(body[i:i + (1 << 20)]) for i in range(0, len(body), 1 << 20)) + b"0\r\n\r\n"
    answer = path.send(f"POST /v1/responses HTTP/1.1\r\nAuthorization: Bearer {path.token}\r\nX-Scenario: size\r\n"
                       "Transfer-Encoding: chunked\r\n\r\n".encode(), then=chunked)
    assert _head(answer)[2] == json.dumps({"received": len(body)}).encode()
    _, fields, size = path.upstream.seen[-1]
    assert size == len(body) and fields["content-length"] == str(len(body)) and "transfer-encoding" not in fields


def test_an_http_2_preface_is_refused_and_nothing_reaches_the_provider(path):
    """The relay serves HTTP/1.1: a client that starts HTTP/2 by prior knowledge is told so, and nothing connects."""
    line, fields, _ = _head(path.send(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"))
    assert line.startswith("HTTP/1.1 400") and fields["x-aew-refusal"] == "bad_request" and path.upstream.seen == []


def test_a_credential_the_upstream_reflects_never_reaches_the_sandbox_through_the_shim(path):
    """The relay removes a credential from a failed answer's body before it reaches the run: an upstream that quotes
    the request's headers back gets the key, and the harness gets the quote without it."""
    answer = path.call("echo")
    line, fields, body = _head(answer)
    assert line.startswith("HTTP/1.1 401") and SECRET.encode() not in answer
    assert json.loads(body)["request"]["authorization"] == "Bearer " + relay.REDACTED.decode()
    assert int(fields["content-length"]) == len(body)
    assert path.upstream.seen[-1][1]["authorization"] == f"Bearer {SECRET}"


def test_a_relay_that_is_gone_is_answered_502_naming_the_cause_and_never_a_bare_reset(path):
    """The relay's socket file takes no connection (its run is ending): the shim answers with the relay's own fixed
    502, which names the cause, after reading the request rather than resetting it."""
    path.relay.close()
    line, fields, body = _head(path.call("ok", body=b"{" + b" " * 300_000 + b"}"))
    assert line == "HTTP/1.1 502 Bad Gateway" and fields["x-aew-refusal"] == relay.RELAY_UNREACHABLE
    assert int(fields["content-length"]) == len(body) and b"not sent to the provider" in body
