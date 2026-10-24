"""F28's credentialing provider relay (F28 §3.3, network containment design v0.2; STG-05 CS-3b).

The harness's provider ``baseURL`` is a loopback port in its sandbox, which the shim forwards to this relay's socket
file. The relay runs in the run's supervisor, outside the sandbox, and holds the provider's credential: the sandbox
holds only a sentinel in its place (:func:`sentinel`). For each request it:

1. reads the request head (``origin-form`` only: a target that names a host is refused, so the sandbox never chooses
   where the relay connects);
2. puts the real credential where the sentinel is, in a credential header only (:data:`CREDENTIAL_HEADERS`): never in
   any other header, which an upstream might echo back. A credential header without a sentinel passes as it came:
   it carries what the sandbox already had, such as the free provider's catalog key ``public``;
3. drops the hop-by-hop headers, sets ``Host`` to the upstream's and asks for ``Connection: close``;
4. connects to its one fixed upstream (the execution policy's, never the sandbox's; through the operator's own HTTP
   proxy when the provider's environment names one), over TLS for ``https``;
5. sends the request and its body (framed by ``Content-Length`` or chunked), then streams the response back as it
   comes, until the upstream ends it or the client goes away.

One request per connection: each answer says ``Connection: close``. The upstream is fixed, so the relay never judges
a destination: ruling R-6 is the egress proxy's (``egress.py``), and this module does not use it. A host-local upstream
(F18.8's Provider Gateway) is allowed for the same reason.

**Streaming:** the response is relayed by one thread per connection, reading the upstream only when the client has
taken the last chunk (a ``sendall`` that blocks is the backpressure), and watching the client: when it goes away, the
upstream connection is closed at once. It is counted ``cancelled`` only when it went before the response's end (its
``Content-Length``, or its last chunk): OpenCode closes as soon as it has a whole answer, before the upstream's own
close arrives (seen in the live lane, 2026-10-24), and that is no cancelled turn (:class:`_Body`).
"""

from __future__ import annotations

import base64
import re
import secrets
import selectors
import socket
import ssl
import time
import urllib.parse
from collections.abc import Callable, Mapping
from typing import Any

from aew.errors import ValidationFailed
from aew.harness.containment.egress import CHUNK, Service

# Implementation bounds, not policy. A provider request's head from OpenCode 2.0.18 is about 1 KiB (measured on the
# Rocky VM, 2026-10-24); 32 KiB is nginx's default for a request head (large_client_header_buffers 4 8k).
MAX_HEAD = 32 * 1024
HEAD_TIMEOUT = 30.0     # the whole request head, from when the relay starts reading it
CONNECT_TIMEOUT = 10.0  # a SYN nobody answers, and the TLS handshake
BODY_TIMEOUT = 60.0     # a pause inside the request body; the response stream itself has no idle bound (see above)
SENTINEL_PREFIX = "aew-relay-"
# The headers a provider SDK carries its key in: OpenAI's and most others' bearer token, Anthropic's, Azure OpenAI's
# and Google's. The relay puts a credential nowhere else.
CREDENTIAL_HEADERS = frozenset({"authorization", "x-api-key", "api-key", "x-goog-api-key"})
# Hop-by-hop (RFC 9110 §7.6.1), plus Expect, which the relay answers itself (a 100 Continue before the body).
HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-connection", "proxy-authorization", "proxy-authenticate",
                        "te", "trailer", "upgrade", "expect"})
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_PHRASES = {400: "Bad Request", 408: "Request Timeout", 431: "Request Header Fields Too Large", 501: "Not Implemented",
            502: "Bad Gateway"}

Connector = Callable[[str, int, float], socket.socket]


def sentinel() -> str:
    """A placeholder for one provider variable inside the sandbox: random, so the relay never mistakes text a client
    happens to send for it, and worthless outside this run's relay."""
    return SENTINEL_PREFIX + secrets.token_hex(16)


class Upstream:
    """The relay's one destination, from the execution policy: ``scheme://host[:port][/base path]``."""

    def __init__(self, url: str) -> None:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.query or parts.fragment \
                or parts.username or parts.password:
            raise ValidationFailed(f"provider upstream {url!r} is not an http(s)://host[:port][/path] URL",
                                   upstream=url, reason="bad_upstream")
        try:
            port = parts.port
        except ValueError:
            raise ValidationFailed(f"provider upstream {url!r} has a bad port", upstream=url,
                                   reason="bad_upstream") from None
        self.url = url
        self.scheme = parts.scheme
        self.host = parts.hostname
        self.port = port or (443 if parts.scheme == "https" else 80)
        self.path = parts.path.rstrip("/")
        default = (self.scheme, self.port) in (("https", 443), ("http", 80))
        self.authority = (f"[{self.host}]" if ":" in self.host else self.host) + ("" if default else f":{self.port}")


class Proxy:
    """The operator's own HTTP proxy for the relay's upstream (``HTTPS_PROXY`` and the like in the provider's
    environment): ``http://[user:password@]host:port``. The relay asks it for a ``CONNECT`` to the upstream."""

    def __init__(self, url: str) -> None:
        parts = urllib.parse.urlsplit(url if "://" in url else f"http://{url}")
        if parts.scheme != "http" or not parts.hostname:
            raise ValidationFailed("the provider's proxy variable names a proxy the relay cannot use: only an "
                                   "http://host:port proxy is supported", reason="bad_proxy")
        self.host, self.port = parts.hostname, parts.port or 80
        self.auth = None
        if parts.username is not None:
            raw = f"{urllib.parse.unquote(parts.username)}:{urllib.parse.unquote(parts.password or '')}"
            self.auth = "Basic " + base64.b64encode(raw.encode()).decode()


def _connect(host: str, port: int, timeout: float) -> socket.socket:
    return socket.create_connection((host, port), timeout=timeout)  # every address the name has, in turn


class _Refused(Exception):
    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status, self.reason, self.message = status, reason, message

    def response(self) -> bytes:
        body = self.message.encode()
        head = (f"HTTP/1.1 {self.status} {_PHRASES[self.status]}\r\nX-AEW-Refusal: {self.reason}\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n")
        return head.encode() + body


class ProviderRelay(Service):
    """Serves ``listener`` for one run's provider. ``credentials`` maps each sentinel to the value it stands for;
    ``proxy`` is the operator's HTTP proxy, if any. ``connect`` and ``tls`` are seams for tests (a plain connect to the
    upstream's name, and the system's default verifying context)."""

    name = "aew-relay"

    def __init__(self, upstream: Upstream, credentials: Mapping[str, str], *, listener: socket.socket | None = None,
                 proxy: Proxy | None = None, connect: Connector = _connect, tls: ssl.SSLContext | None = None,
                 head_timeout: float = HEAD_TIMEOUT, connect_timeout: float = CONNECT_TIMEOUT,
                 body_timeout: float = BODY_TIMEOUT) -> None:
        super().__init__(listener=listener)
        self.upstream, self.proxy = upstream, proxy
        self._credentials = dict(credentials)
        self._connect, self._tls = connect, tls
        self.head_timeout, self.connect_timeout, self.body_timeout = head_timeout, connect_timeout, body_timeout

    def start(self) -> ProviderRelay:
        super().start()
        return self

    def close(self) -> None:
        super().close()
        self._credentials.clear()

    def handle(self, conn: socket.socket) -> None:
        """Serve one request on ``conn`` to its end, and close it."""
        if not self._track(conn):
            conn.close()
            return
        upstream: socket.socket | None = None
        answered = False  # once the response's head has gone to the client, nothing else may be sent it
        try:
            head, early = _read_head(conn, self.head_timeout)
            method, target, headers = self._request(head)
            framing = _framing(headers)
            if any(k.lower() == "expect" and v.lower() == "100-continue" for k, v in headers):
                conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
            upstream = self._connect_upstream()
            if not self._track(upstream):
                return
            upstream.sendall(_head(f"{method} {target} HTTP/1.1", self._rewrite(headers)))
            self._send_body(conn, upstream, framing, early)
            reader, response = self._relay_head(conn, upstream)
            answered = True
            self._count("allowed")
            self._stream(conn, upstream, reader, _Body(response, method))
        except _Refused as refused:
            if not answered:
                self._answer(conn, refused)
        except OSError:
            if not answered:
                self._answer(conn, _Refused(502, "upstream_unreachable", "the provider relay could not reach "
                                            f"{self.upstream.url}, the run's fixed provider upstream"))
        except Exception:  # anything else is counted, and answered with a fixed 502 when nothing was relayed yet
            self._count("relay_error")
            if not answered:
                self._answer(conn, _Refused(502, "relay_error", "the provider relay could not serve this request"))
        finally:
            if upstream is not None:
                self._untrack(upstream)
            self._untrack(conn)

    def _answer(self, conn: socket.socket, refused: _Refused) -> None:
        self._count(refused.reason)
        try:
            conn.settimeout(self.head_timeout)
            conn.sendall(refused.response())
        except OSError:
            pass

    def _request(self, head: bytes) -> tuple[str, str, list[tuple[str, str]]]:
        lines = head.split(b"\r\n")
        try:
            method, target, version = lines[0].decode("ascii").split(" ")
        except (UnicodeDecodeError, ValueError):
            raise _Refused(400, "bad_request", "the request line is not METHOD /path HTTP/1.1") from None
        if not _TOKEN.fullmatch(method) or version not in ("HTTP/1.1", "HTTP/1.0"):
            raise _Refused(400, "bad_request", "the request line is not METHOD /path HTTP/1.1")
        if not target.startswith("/") or any(c <= " " or c == "\x7f" for c in target):
            raise _Refused(400, "not_origin_form", "the provider relay takes a path only (/v1/...): it always "
                           "connects to the run's fixed provider upstream, which a request cannot name")
        headers = []
        for raw in lines[1:]:
            name, sep, value = raw.partition(b":")
            try:
                text = name.decode("ascii")
            except UnicodeDecodeError:
                text = ""
            if not sep or not _TOKEN.fullmatch(text):
                raise _Refused(400, "bad_header", "a request header is not Name: value")
            headers.append((text, value.strip(b" \t").decode("latin-1")))
        if any(k.lower() == "upgrade" for k, _ in headers):
            raise _Refused(501, "upgrade", "the provider relay serves plain HTTP requests, not a protocol upgrade "
                           "(WebSocket); AEW sets the provider's transport to http")
        return method, target, headers

    def _rewrite(self, headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Hop-by-hop headers (and any the client's ``Connection`` names) out; ``Host`` the upstream's; the
        credential in for its sentinel, in a credential header only; ``Connection: close``."""
        named = {t.strip().lower() for k, v in headers if k.lower() == "connection" for t in v.split(",")}
        out = [("Host", self.upstream.authority)]
        for name, value in headers:
            low = name.lower()
            if low in HOP_BY_HOP or low in named or low == "host":
                continue
            if low in CREDENTIAL_HEADERS:
                value = self._credential(value)
            out.append((name, value))
        out.append(("Connection", "close"))
        return out

    def _credential(self, value: str) -> str:
        scheme, sep, token = value.partition(" ")
        if sep and token.strip() in self._credentials:
            return f"{scheme} {self._credentials[token.strip()]}"
        return self._credentials.get(value.strip(), value)

    def _connect_upstream(self) -> socket.socket:
        if self._closed.is_set():
            raise _Refused(502, "closed", "the provider relay is closing: the run is ending")
        up = self.upstream
        if self.proxy is None:
            sock = self._connect(up.host, up.port, self.connect_timeout)
        else:
            sock = self._connect(self.proxy.host, self.proxy.port, self.connect_timeout)
            try:
                self._tunnel(sock)
            except BaseException:
                sock.close()
                raise
        if up.scheme == "https":
            context = self._tls or ssl.create_default_context()
            sock.settimeout(self.connect_timeout)
            try:
                sock = context.wrap_socket(sock, server_hostname=up.host)
            except BaseException:
                sock.close()
                raise
        sock.settimeout(None)
        return sock

    def _tunnel(self, sock: socket.socket) -> None:
        """Ask the operator's proxy for a tunnel to the upstream; anything but a 200 is the upstream unreachable."""
        assert self.proxy is not None
        host, port = self.upstream.host, self.upstream.port
        target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
        if self.proxy.auth:
            lines.append(f"Proxy-Authorization: {self.proxy.auth}")
        sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        try:
            head, _ = _read_head(sock, self.connect_timeout)
        except _Refused as exc:
            raise OSError(f"the operator's proxy gave no answer to CONNECT {target}: {exc.message}") from None
        status = head.split(b"\r\n", 1)[0]
        if status.split(b" ")[1:2] != [b"200"]:
            raise OSError(f"the operator's proxy refused CONNECT {target}: {status[:80]!r}")

    def _send_body(self, conn: socket.socket, upstream: socket.socket, framing: tuple[str, int],
                   early: bytes) -> None:
        """The request body, as its head frames it: ``Content-Length`` bytes, or chunks to the last one and its
        trailer. What the client sends beyond it is not relayed (one request per connection)."""
        kind, length = framing
        reader = _Reader(conn, early, self.body_timeout)
        if kind == "length":
            left = length
            while left:
                data = reader.read(min(left, CHUNK))
                upstream.sendall(data)
                left -= len(data)
        elif kind == "chunked":
            while True:
                line = reader.line()
                upstream.sendall(line)
                try:
                    size = int(line.split(b";", 1)[0].strip(), 16)
                except ValueError:
                    raise _Refused(400, "bad_chunk", "the request body's chunked encoding is malformed") from None
                if size == 0:
                    while True:  # the trailer section, to its empty line
                        trailer = reader.line()
                        upstream.sendall(trailer)
                        if trailer == b"\r\n":
                            return
                left = size + 2  # the chunk and its CRLF
                while left:
                    data = reader.read(min(left, CHUNK))
                    upstream.sendall(data)
                    left -= len(data)

    def _relay_head(self, conn: socket.socket, upstream: socket.socket) -> tuple[_Reader, bytes]:
        """The response's head, with ``Connection: close``; interim 1xx heads first, as they come. Returns the reader
        and the final head as the upstream sent it."""
        reader = _Reader(upstream, b"", None)
        while True:
            head = reader.head()
            status = head.split(b"\r\n", 1)[0].split(b" ")
            interim = len(status) > 1 and status[1].startswith(b"1") and status[1] != b"101"
            conn.sendall(head if interim else _close_head(head))
            if not interim:
                return reader, head

    def _stream(self, conn: socket.socket, upstream: socket.socket, reader: _Reader, body: _Body) -> None:
        """The response's body as it streams, until the upstream ends it. A client that goes away ends it at once,
        and so does :meth:`close`."""
        conn.settimeout(None)
        if reader.buffer:
            data = reader.take()
            body.feed(data)
            conn.sendall(data)
        with selectors.DefaultSelector() as selector:
            selector.register(upstream, selectors.EVENT_READ)
            selector.register(conn, selectors.EVENT_READ)
            selector.register(self._wake_r, selectors.EVENT_READ)
            while True:
                pending = isinstance(upstream, ssl.SSLSocket) and upstream.pending() > 0
                ready = set() if pending else {key.fileobj for key, _ in selector.select()}
                if self._wake_r in ready:
                    return
                if conn in ready and _gone(conn):
                    if not body.done:  # it went before the response's end: a cancelled turn
                        self._count("cancelled")
                    return
                if pending or upstream in ready:
                    data = upstream.recv(CHUNK)
                    if not data:
                        return
                    body.feed(data)
                    conn.sendall(data)


class _Body:
    """How far a response's body has been relayed: whether its end, by its framing (RFC 9112 §6.3), has gone to the
    client. A body with neither length nor chunking ends only when the upstream closes, so it is never ``done`` here.
    Chunked bodies are followed chunk by chunk, to the last chunk and its trailer section."""

    def __init__(self, head: bytes, method: str) -> None:
        status = head.split(b"\r\n", 1)[0].split(b" ")
        code = status[1] if len(status) > 1 else b""
        fields = [raw.split(b":", 1) for raw in head[:-4].split(b"\r\n")[1:]]
        values = [(f[0].strip().lower(), f[1].strip().lower()) for f in fields if len(f) == 2]
        codings = [v for k, v in values if k == b"transfer-encoding"]
        lengths = {v for k, v in values if k == b"content-length"}
        self.state, self.left, self.line = "size", 0, b""
        if method == "HEAD" or code in (b"204", b"304"):
            self.kind = "none"
        elif codings and codings[-1].split(b",")[-1].strip() == b"chunked":
            self.kind = "chunked"
        elif len(lengths) == 1 and next(iter(lengths)).isdigit():
            self.kind, self.left = "length", int(next(iter(lengths)))
        else:
            self.kind = "close"
        self.done = self.kind == "none" or (self.kind == "length" and self.left == 0)

    def feed(self, data: bytes) -> None:
        if self.done or self.kind not in ("length", "chunked"):
            return
        if self.kind == "length":
            self.left -= len(data)
            self.done = self.left <= 0
            return
        i = 0
        while i < len(data) and not self.done:
            if self.state == "data":  # the chunk's bytes and their CRLF
                take = min(self.left, len(data) - i)
                i, self.left = i + take, self.left - take
                if not self.left:
                    self.state = "size"
                continue
            end = data.find(b"\n", i)
            if end < 0:
                self.line += data[i:]
                if len(self.line) > MAX_HEAD:  # no chunk-size line or trailer field is this long: framing unknown
                    self.kind = "close"
                return
            line, self.line, i = (self.line + data[i:end]).rstrip(b"\r"), b"", end + 1
            if self.state == "trailer":
                self.done = not line
                continue
            try:
                size = int(line.split(b";", 1)[0].strip(), 16)
            except ValueError:
                self.kind = "close"
                return
            self.state, self.left = ("trailer", 0) if size == 0 else ("data", size + 2)


class _Reader:
    """Buffered reads from one socket, each with ``timeout`` (None: none)."""

    def __init__(self, sock: socket.socket, buffered: bytes, timeout: float | None) -> None:
        self.sock, self.buffer, self.timeout = sock, buffered, timeout

    def _more(self) -> None:
        self.sock.settimeout(self.timeout)
        try:
            data = self.sock.recv(CHUNK)
        except TimeoutError:
            raise _Refused(408, "body_timeout", "the request body stopped arriving") from None
        if not data:
            raise _Refused(400, "incomplete", "the connection closed before the message was complete")
        self.buffer += data

    def take(self) -> bytes:
        out, self.buffer = self.buffer, b""
        return out

    def read(self, most: int) -> bytes:
        if not self.buffer:
            self._more()
        out, self.buffer = self.buffer[:most], self.buffer[most:]
        return out

    def line(self) -> bytes:
        while b"\r\n" not in self.buffer:
            if len(self.buffer) > MAX_HEAD:
                raise _Refused(400, "bad_chunk", "a chunk-size line is too long")
            self._more()
        end = self.buffer.index(b"\r\n") + 2
        out, self.buffer = self.buffer[:end], self.buffer[end:]
        return out

    def head(self) -> bytes:
        while b"\r\n\r\n" not in self.buffer:
            if len(self.buffer) > MAX_HEAD:
                raise OSError(f"the upstream's response head exceeds {MAX_HEAD} bytes")
            data = self.sock.recv(CHUNK)
            if not data:
                raise OSError("the upstream closed before its response head was complete")
            self.buffer += data
        end = self.buffer.index(b"\r\n\r\n") + 4
        out, self.buffer = self.buffer[:end], self.buffer[end:]
        return out


def _gone(conn: socket.socket) -> bool:
    """Whether a client the relay is streaming to has closed (or reset) its connection. Anything it sends meanwhile is
    not relayed: one request per connection."""
    try:
        return not conn.recv(CHUNK)
    except ConnectionError:
        return True


def _read_head(conn: socket.socket, timeout: float) -> tuple[bytes, bytes]:
    """``(head without its final CRLF CRLF, what followed it)``, with one deadline for the whole head."""
    deadline = time.monotonic() + timeout
    buf = b""
    while True:
        end = buf.find(b"\r\n\r\n")
        if 0 <= end <= MAX_HEAD:
            return buf[:end], buf[end + 4:]
        if len(buf) > MAX_HEAD:
            raise _Refused(431, "header_too_large", f"the request's head exceeds {MAX_HEAD} bytes")
        left = deadline - time.monotonic()
        try:
            if left <= 0:
                raise TimeoutError
            conn.settimeout(left)
            data = conn.recv(4096)
        except TimeoutError:
            raise _Refused(408, "header_timeout", "no complete request arrived in time") from None
        if not data:
            raise _Refused(400, "incomplete", "the connection closed before its request was complete")
        buf += data


def _framing(headers: list[tuple[str, str]]) -> tuple[str, int]:
    """How the request's body is framed (RFC 9112 §6): chunked, a length, or none."""
    encodings = [v.strip().lower() for k, v in headers if k.lower() == "transfer-encoding"]
    lengths = {v.strip() for k, v in headers if k.lower() == "content-length"}
    if encodings:
        if lengths or encodings[-1].split(",")[-1].strip() != "chunked":
            raise _Refused(400, "bad_framing", "a request with Transfer-Encoding must end in chunked and carry no "
                           "Content-Length")
        return "chunked", 0
    if len(lengths) > 1:
        raise _Refused(400, "bad_framing", "the request carries different Content-Length values")
    if lengths:
        value = lengths.pop()
        if not value.isdigit():
            raise _Refused(400, "bad_framing", "the request's Content-Length is not a number")
        return "length", int(value)
    return "none", 0


def _head(line: str, headers: list[tuple[str, str]]) -> bytes:
    return ("\r\n".join([line, *(f"{k}: {v}" for k, v in headers)]) + "\r\n\r\n").encode("latin-1")


def _close_head(head: bytes) -> bytes:
    """A response head with its hop-by-hop headers out and ``Connection: close`` in."""
    lines = head[:-4].split(b"\r\n")
    fields = [(raw.split(b":", 1)[0].strip().lower().decode("latin-1"), raw) for raw in lines[1:]]
    named = {t.strip().lower().decode("latin-1") for name, raw in fields if name == "connection"
             for t in raw.split(b":", 1)[-1].split(b",")}
    kept = [raw for name, raw in fields if name not in HOP_BY_HOP and name not in named]
    return b"\r\n".join([lines[0], *kept, b"Connection: close"]) + b"\r\n\r\n"


def describe(relay: ProviderRelay | None) -> dict[str, Any]:
    """For the run's label: ``network.provider_relay`` (F28 §3.1) and its fixed upstream."""
    if relay is None:
        return {"provider_relay": "none"}
    return {"provider_relay": "configured", "provider_upstream": relay.upstream.url,
            **({"provider_upstream_proxy": f"{relay.proxy.host}:{relay.proxy.port}"} if relay.proxy else {})}
