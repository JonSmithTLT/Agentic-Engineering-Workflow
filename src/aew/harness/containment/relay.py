"""F28's credentialing provider relay (F28 §3.3, network containment design v0.2; STG-05 CS-3b).

The harness's provider ``baseURL`` is a loopback port in its sandbox, which the shim forwards to this relay's socket
file. The relay runs in the run's supervisor, outside the sandbox, and holds the provider's credential: the sandbox
holds only a sentinel in its place (:func:`sentinel`). For each request it:

1. reads the request head (``origin-form`` only: a target that names a host is refused, so the sandbox never chooses
   where the relay connects). A per-request credential also requires a path inside its upstream prefix;
2. puts the real credential where the sentinel is, in a credential header only (:data:`CREDENTIAL_HEADERS`): never in
   any other header, which an upstream might echo back. A credential header without a sentinel passes as it came:
   it carries what the sandbox already had, which is no key (a launch whose provider would get none is refused before
   it starts: ``netns.provider_key_missing``). A credential that
   can change while the relay runs (a stored login the operator's own harness refreshes) is resolved for each
   request instead (``resolve``), with the headers that go with it; one that cannot be used now is answered 401,
   or 503 for a busy or locked store, with the resolver's message (:class:`Unavailable`), and nothing is connected;
3. drops the hop-by-hop headers, sets ``Host`` to the upstream's and asks for ``Connection: close``. A header the
   login's grant sets (``login_headers``, such as ChatGPT's account id) is the grant's alone: the client's, which holds
   a placeholder, is dropped whether or not the grant has a value for it.
   **Placeholders:** a sentinel this relay did not issue, anywhere in the request line or the headers (a credential
   header after the swap, any other header, the target), refuses the request 401 before anything is connected, so no
   such placeholder goes upstream in them: :data:`OTHER_PLACEHOLDER` when this run issued it to another provider,
   :data:`STALE_PLACEHOLDER` when no relay of the run did (an earlier session's, kept in a store), each with its own
   remedy. This relay's own sentinel is swapped in a credential header only, and passes elsewhere as it came (it stands
   for nothing outside the relay). The body is never read for one: a prompt may quote a placeholder;
4. connects to its one fixed upstream, through the operator's HTTP proxy when the provider's environment names one,
   over TLS for ``https``;
5. sends the request and its body (framed by ``Content-Length`` or chunked), then streams the response back as it
   comes, until the upstream ends it or the client goes away.

**The record:** a fixed operation label distinguishes recognized model calls and model lists without recording the
request target. Each request, whatever became of it, is one entry given to the relay's ``record`` (one per request,
when the request ends): when, the provider route, the fixed destination, what became of its credential header
(:data:`SWAP_OUTCOMES`), the login kind, what the relay answered and, for one it forwarded, the upstream's status, with
a short excerpt of a failure's body, redacted. Never a credential value. A forwarded request is also counted by its
upstream status class when that is not 2xx, so a 401 is never counted only as ``allowed``.

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
from collections.abc import Callable, Collection, Mapping
from typing import TYPE_CHECKING, Any, Literal

from aew.errors import ValidationFailed
from aew.harness.containment.egress import CHUNK, Service
from aew.http_close import REFUSAL_DRAIN_S, close_after_response

if TYPE_CHECKING:
    from aew.harness.containment.client_cert import ClientCert

# Implementation bounds, not policy. A provider request's head from OpenCode 2.0.18 is about 1 KiB (measured on the
# Rocky VM, 2026-10-24); 32 KiB is nginx's default for a request head (large_client_header_buffers 4 8k).
MAX_HEAD = 32 * 1024
HEAD_TIMEOUT = 30.0     # the whole request head, from when the relay starts reading it
CONNECT_TIMEOUT = 10.0  # a SYN nobody answers, and the TLS handshake
BODY_TIMEOUT = 60.0     # a pause inside the request body; the response stream itself has no idle bound (see above)
TLS_MINIMUM = ssl.TLSVersion.TLSv1_2  # every upstream context's floor, a client certificate's included
SENTINEL_PREFIX = "aew-relay-"
STALE_PLACEHOLDER = "stale_placeholder"
OTHER_PLACEHOLDER = "other_placeholder"
# What became of a request's credential header: its sentinel swapped for the credential; none carried one; or one
# carried a sentinel this relay does not hold, and the request was refused.
SWAP_OUTCOMES = ("swapped", "none", "refused_unknown_placeholder")
# Implementation bound: how much of a failed answer's body the record keeps. A provider's error is a short JSON object
# (OpenAI's 401 for a wrong key is about 250 bytes); the record is for "why", not the whole answer.
EXCERPT_BYTES = 512
# The headers a provider SDK carries its key in: OpenAI's and most others' bearer token, Anthropic's, Azure OpenAI's
# and Google's. The relay puts a credential nowhere else.
CREDENTIAL_HEADERS = frozenset({"authorization", "x-api-key", "api-key", "x-goog-api-key"})
# Hop-by-hop (RFC 9110 §7.6.1), plus Expect, which the relay answers itself (a 100 Continue before the body).
HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-connection", "proxy-authorization", "proxy-authenticate",
                        "te", "trailer", "upgrade", "expect"})
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
# Resolve-mode forwards the target raw. Accept only unreserved path characters and literal separators so
# neither percent decoding nor upstream-specific path parameter handling can change its interpretation.
_RESOLVED_PATH = re.compile(r"/[A-Za-z0-9._~/\-]*")
_PHRASES = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 408: "Request Timeout",
            431: "Request Header Fields Too Large", 501: "Not Implemented",
            502: "Bad Gateway", 503: "Service Unavailable"}

Connector = Callable[[str, int, float], socket.socket]
# What a resolver gives one request: each sentinel's value, and the headers the relay sets (replacing any of the same
# name the client sent), such as an account header a stored login carries.
Grant = tuple[Mapping[str, str], Mapping[str, str]]


CredentialCause = Literal["expired", "kind_changed", "unknown_shape", "missing", "unreadable"]


class Unavailable(Exception):
    """A name-only refusal whose message is sent to the client and whose cause is counted."""

    def __init__(self, message: str, *, cause: CredentialCause, retryable: bool = False) -> None:
        super().__init__(message)
        self.cause: CredentialCause = cause
        self.retryable = retryable


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


def stale_message() -> str:
    """The refusal of a placeholder no relay of the session issued, with the step for each place it can come from: an
    earlier session's AEW login row (a start removes those), or a login saved inside the Lead, in the Lead's own store,
    which no start removes. Its step acts on the Lead's store alone, never on the operator's own OpenCode login."""
    from aew.harness.opencode.lead import LEAD_DIR
    from aew.harness.opencode.login import STORE_REL
    from aew.knowledge.manifest import AEW_DIR

    return ("AEW: this request carries a key placeholder no relay of this session issued, so it was not sent to the "
            "provider. An earlier session's login row holds one, and each start removes those: start the run again "
            "(for the Lead, `aew opencode`). If it comes back after a fresh start, a login saved inside the Lead holds "
            f"it, in the Lead's own store, which a start keeps: with the Lead stopped, move {AEW_DIR}/{LEAD_DIR}/"
            f"{STORE_REL} aside (OpenCode makes a new one, without the Lead's earlier sessions), then start it again. "
            "Your own OpenCode login is not involved")


OTHER_MESSAGE = ("AEW: this request carries the placeholder this run gave another provider's key, which stands for "
                 "nothing at this provider, so it was not sent. The harness sends that key to the wrong provider: "
                 "check the provider settings the run was given (starting again does not change them)")


def _placeholders(value: str, own: Collection[str], foreign: Collection[str]) -> None:
    """Refuse ``value`` when it holds a sentinel other than one of ``own`` (which pass as they came):
    :data:`OTHER_PLACEHOLDER` for one of ``foreign`` (this run issued it to another provider), else
    :data:`STALE_PLACEHOLDER`. The value is never echoed."""
    rest = value
    for token in own:
        rest = rest.replace(token, "")
    if SENTINEL_PREFIX not in rest:
        return
    if any(token in rest for token in foreign):
        raise _Refused(401, OTHER_PLACEHOLDER, OTHER_MESSAGE)
    raise _Refused(401, STALE_PLACEHOLDER, stale_message())


def _credential(value: str, credentials: Mapping[str, str], foreign: Collection[str] = ()) -> tuple[str, bool]:
    """A credential header's value with its sentinel, alone or after a scheme (``Bearer <sentinel>``), swapped, and
    whether one was. Any sentinel still in it after the swap is refused (:func:`_placeholders`): in a credential header
    not even this relay's own passes, as it would go where the credential goes."""
    scheme, sep, token = value.partition(" ")
    if sep and token.strip() in credentials:
        return f"{scheme} {credentials[token.strip()]}", True
    if value.strip() in credentials:
        return credentials[value.strip()], True
    _placeholders(value, (), foreign)
    return value, False


def _operation(method: str, target: str, base: str) -> str:
    """Recognize API operations relative to the exact configured base, without retaining the path or query."""
    path = target.partition("?")[0]
    if not path.startswith(base + "/"):
        return "unknown"
    endpoint = path[len(base):]
    if method == "GET" and endpoint == "/models":
        return "models_list"
    if method == "POST" and (endpoint in ("/responses", "/chat/completions", "/completions", "/messages")
                             or re.fullmatch(r"/models/[^/:]+:(?:generateContent|streamGenerateContent)", endpoint)):
        return "model"
    return "unknown"


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
    """Serves ``listener`` for one run's provider. ``credentials`` maps each sentinel to the value it stands for, or
    ``resolve`` gives that map and the headers to set for each request (raising :class:`Unavailable` when it has
    none to give); ``proxy`` is the operator's HTTP proxy, if any. ``tls`` is the upstream's context: a provider's
    client certificate's (``client_cert.context``, with ``client`` the files it was read from, for the answers on a
    failed handshake), else the system's default verifying context; tests give their own. ``connect`` is a seam for
    tests (a plain connect to the upstream's name). ``record`` takes each request's entry (see the module's "The
    record"), with ``route`` (the provider) and ``login`` (``key``, ``oauth`` or ``none``) in it; a record that fails
    is counted (``record_failed``) and never fails the request."""

    name = "aew-relay"

    def __init__(self, upstream: Upstream, credentials: Mapping[str, str], *, listener: socket.socket | None = None,
                 proxy: Proxy | None = None, connect: Connector = _connect, tls: ssl.SSLContext | None = None,
                 head_timeout: float = HEAD_TIMEOUT, connect_timeout: float = CONNECT_TIMEOUT,
                 body_timeout: float = BODY_TIMEOUT, resolve: Callable[[], Grant] | None = None,
                 client: ClientCert | None = None, record: Callable[[dict[str, Any]], None] | None = None,
                 route: str | None = None, login: str = "none", login_headers: Collection[str] = (),
                 issued: Collection[str] = ()) -> None:
        super().__init__(listener=listener)
        self.upstream, self.proxy = upstream, proxy
        self._credentials = dict(credentials)
        self._resolve = resolve
        self.login_headers = frozenset(h.lower() for h in login_headers)
        self.own = frozenset(credentials) | frozenset(issued)  # the sentinels this relay issued (a grant's included)
        # The sentinels the run issued to its other relays and variables (netns sets it once they all exist): one of
        # them here is another provider's placeholder, refused as such
        self.foreign: frozenset[str] = frozenset()
        self._record, self.route, self.login = record, route, login
        self._retryable_pending = False
        self._connect, self._tls = connect, tls
        self.client = client
        self.head_timeout, self.connect_timeout, self.body_timeout = head_timeout, connect_timeout, body_timeout

    def start(self) -> ProviderRelay:
        super().start()
        return self

    def close(self) -> None:
        super().close()
        self._credentials.clear()
        self._resolve = None

    def _grant(self) -> Grant:
        resolve = self._resolve
        if resolve is None:
            return self._credentials, {}
        try:
            grant = resolve()
            with self._lock:
                self._retryable_pending = False
            return grant
        except Unavailable as exc:
            self._count(f"credential:{exc.cause}" + ("_retryable" if exc.retryable else ""))
            with self._lock:
                self._retryable_pending = exc.retryable
            if exc.cause == "unreadable" and exc.retryable:
                raise _Refused(503, "credential_unreadable", str(exc)) from None
            raise _Refused(401, "credential_unavailable", str(exc)) from None

    def retryable_pending(self) -> bool:
        with self._lock:
            return self._retryable_pending

    def _check_resolved_target(self, target: str) -> None:
        path = target.partition("?")[0]
        if (not path.startswith(f"{self.upstream.path}/") or not _RESOLVED_PATH.fullmatch(path)
                or "//" in path or "#" in target or {".", ".."}.intersection(path.split("/"))
                or any(c <= " " or c == "\x7f" for c in target)):
            raise _Refused(403, "outside_upstream_path", "the provider relay takes only unambiguous paths "
                           "under the stored login's upstream path")

    def handle(self, conn: socket.socket) -> None:
        """Serve one request on ``conn`` to its end, and close it."""
        if not self._track(conn):
            conn.close()
            return
        upstream: socket.socket | None = None
        answered = False  # once the response's head has gone to the client, nothing else may be sent it
        entry: dict[str, Any] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "route": self.route,
                                 "destination": f"{self.upstream.host}:{self.upstream.port}", "login": self.login,
                                 "swap": "none", "operation": "unknown", "outcome": None, "reason": None,
                                 "status": None, "answered": None}
        held: list[str] = []  # this request's credential values, kept out of the record's excerpt
        excerpt: _Excerpt | None = None
        try:
            head, early = _read_head(conn, self.head_timeout)
            method, target, headers = self._request(head)
            entry["operation"] = _operation(method, target, self.upstream.path)
            framing = _framing(headers)
            credentials, extra = self._grant()  # before anything is connected: a refusal connects nothing
            held = [*credentials.values(), *extra.values()]
            try:
                rewritten, swapped = self._rewrite(headers, credentials, extra)
                _placeholders(target, credentials, self.foreign)
            except _Refused as refused:
                if refused.reason in (STALE_PLACEHOLDER, OTHER_PLACEHOLDER):
                    entry["swap"] = "refused_unknown_placeholder"
                raise
            entry["swap"] = "swapped" if swapped else "none"
            if any(k.lower() == "expect" and v.lower() == "100-continue" for k, v in headers):
                conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
            upstream = self._connect_upstream()
            if not self._track(upstream):
                entry.update(outcome="refused", reason="closed")
                return
            upstream.sendall(_head(f"{method} {target} HTTP/1.1", rewritten))
            self._send_body(conn, upstream, framing, early)
            reader, response = self._relay_head(conn, upstream)
            answered = True
            self._count("allowed")
            status = _status_code(response)
            entry.update(outcome="forwarded", status=status, answered=status)
            if status is None or not 200 <= status < 300:  # "allowed" means only not blocked; this is how it went
                self._count(f"upstream_status:{status}")
                excerpt = _Excerpt(response)
            self._stream(conn, upstream, reader, _Body(response, method), excerpt)
        except _Refused as refused:
            if not answered:
                self._answer(conn, refused, entry)
        except ssl.SSLError as exc:  # the upstream's TLS: in the handshake, or (TLS 1.3) an alert on the first read
            if not answered:
                self._answer(conn, _tls_refused(exc, self.upstream, self.client), entry)
        except OSError:
            if not answered:
                self._answer(conn, _Refused(502, "upstream_unreachable", "the provider relay could not reach "
                                            f"{self.upstream.url}, the run's fixed provider upstream"), entry)
        except Exception:  # anything else is counted, and answered with a fixed 502 when nothing was relayed yet
            self._count("relay_error")
            if not answered:
                self._answer(conn, _Refused(502, "relay_error", "the provider relay could not serve this request"),
                             entry)
        finally:
            if upstream is not None:
                self._untrack(upstream)
            self._untrack(conn)
            if excerpt is not None:
                entry["excerpt"] = excerpt.text(held)
            self._write(entry)

    def _write(self, entry: dict[str, Any]) -> None:
        if self._record is None:
            return
        try:
            self._record(entry)
        except Exception:  # the record is evidence of the request, never a reason to fail it
            self._count("record_failed")

    def _answer(self, conn: socket.socket, refused: _Refused, entry: dict[str, Any] | None = None) -> None:
        if entry is not None:
            entry.update(outcome="refused", reason=refused.reason, answered=refused.status)
        self._count(refused.reason)
        try:
            conn.settimeout(self.head_timeout)
            conn.sendall(refused.response())
            close_after_response(conn, REFUSAL_DRAIN_S)
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
        if self._resolve is not None:
            self._check_resolved_target(target)
        elif not target.startswith("/") or any(c <= " " or c == "\x7f" for c in target):
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

    def _rewrite(self, headers: list[tuple[str, str]], credentials: Mapping[str, str],
                 extra: Mapping[str, str]) -> tuple[list[tuple[str, str]], bool]:
        """Hop-by-hop headers (and any the client's ``Connection`` names) out; ``Host`` the upstream's; the
        credential in for its sentinel, in a credential header only; the grant's headers in place of any of the same
        name, and the client's of a name in ``login_headers`` dropped; ``Connection: close``. A sentinel this relay did
        not issue, in any header kept, is refused (:func:`_placeholders`). Returns the headers and whether a sentinel
        was swapped."""
        named = {t.strip().lower() for k, v in headers if k.lower() == "connection" for t in v.split(",")}
        replaced = {k.lower() for k in extra} | self.login_headers
        out = [("Host", self.upstream.authority)]
        swapped = False
        for name, value in headers:
            low = name.lower()
            if low in HOP_BY_HOP or low in named or low == "host" or low in replaced:
                continue
            if low in CREDENTIAL_HEADERS:
                value, one = _credential(value, credentials, self.foreign)
                swapped = swapped or one
            else:
                _placeholders(value, credentials, self.foreign)
            out.append((name, value))
        out += list(extra.items())
        out.append(("Connection", "close"))
        return out, swapped

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
            context = self._tls or _tls_context()
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
                size = _chunk_size(line)
                if size is None:
                    raise _Refused(400, "bad_chunk", "the request body's chunked encoding is malformed")
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

    def _stream(self, conn: socket.socket, upstream: socket.socket, reader: _Reader, body: _Body,
                excerpt: _Excerpt | None = None) -> None:
        """The response's body as it streams, until the upstream ends it. A client that goes away ends it at once,
        and so does :meth:`close`. ``excerpt`` sees the body's first bytes as they pass (a failed answer's)."""
        conn.settimeout(None)
        if reader.buffer:
            data = reader.take()
            body.feed(data)
            if excerpt is not None:
                excerpt.feed(data)
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
                        if excerpt is not None:  # the record still gets the failure's body, whoever stopped reading
                            excerpt.drain(upstream, body)
                    return
                if pending or upstream in ready:
                    data = upstream.recv(CHUNK)
                    if not data:
                        return
                    body.feed(data)
                    if excerpt is not None:
                        excerpt.feed(data)
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
            size = _chunk_size(line)
            if size is None:
                self.kind = "close"
                return
            self.state, self.left = ("trailer", 0) if size == 0 else ("data", size + 2)


def _status_code(head: bytes) -> int | None:
    """A response head's status code, or None when its status line has none."""
    parts = head.split(b"\r\n", 1)[0].split(b" ")
    return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None


# Implementation bound: how much of a failed answer's raw body is read for its excerpt, with room for chunk framing
# and a compressed body's header before the :data:`EXCERPT_BYTES` of text.
EXCERPT_RAW_BYTES = 16 * 1024
# Implementation bound: how long the record waits for a failed answer's body once its client has gone (a client may
# close as soon as it has the status). A provider's error body comes with its head or right after it.
EXCERPT_DRAIN_S = 2.0
_ELLIPSIS_MASKED = re.compile(r"\S{2,}\.{3}\S{2,}")  # a provider's own masking of a key it was sent (abcd...wxyz)


class _Excerpt:
    """The start of a failed answer's body, as text for the record: de-chunked, inflated when ``gzip`` or ``deflate``
    (any other coding is named, not read), redacted over the whole of what was read (:data:`EXCERPT_RAW_BYTES`), and
    only then cut to :data:`EXCERPT_BYTES` characters (:meth:`text`)."""

    def __init__(self, head: bytes) -> None:
        values = {}
        for raw in head[:-4].split(b"\r\n")[1:]:
            name, sep, value = raw.partition(b":")
            if sep:
                values[name.strip().lower()] = value.strip().lower().decode("latin-1")
        self.chunked = values.get(b"transfer-encoding", "").split(",")[-1].strip() == "chunked"
        self.coding = values.get(b"content-encoding", "identity") or "identity"
        self.raw = bytearray()

    def feed(self, data: bytes) -> None:
        if len(self.raw) < EXCERPT_RAW_BYTES:
            self.raw += data[:EXCERPT_RAW_BYTES - len(self.raw)]

    def drain(self, upstream: socket.socket, body: _Body) -> None:
        """Read the rest of the body from ``upstream`` for the record alone, its client gone: until its end, the
        :data:`EXCERPT_RAW_BYTES` bound, or :data:`EXCERPT_DRAIN_S`, whichever comes first. Nothing is sent on."""
        deadline = time.monotonic() + EXCERPT_DRAIN_S
        try:
            while not body.done and len(self.raw) < EXCERPT_RAW_BYTES:
                left = deadline - time.monotonic()
                if left <= 0:
                    return
                upstream.settimeout(left)
                data = upstream.recv(CHUNK)
                if not data:
                    return
                body.feed(data)
                self.feed(data)
        except OSError:  # a timeout, or the upstream gone: the record keeps what it has
            return

    def text(self, held: list[str]) -> str:
        import zlib

        from aew.harness.defects import redact_text

        data = _unchunk(bytes(self.raw)) if self.chunked else bytes(self.raw)
        if self.coding in ("gzip", "x-gzip", "deflate"):
            try:
                inflate = zlib.decompressobj(zlib.MAX_WBITS | (16 if "gzip" in self.coding else 0))
                data = inflate.decompress(data, EXCERPT_RAW_BYTES)
            except zlib.error:
                return f"(a {self.coding} body that could not be read)"
        elif self.coding != "identity":
            return f"(a {self.coding} body: not read)"
        # Redacted whole, then cut: a value that crosses the cut is removed whole, never left less its tail
        text = data[:EXCERPT_RAW_BYTES].decode("utf-8", "replace")
        for value in sorted((v for v in held if len(v) >= 4), key=len, reverse=True):
            text = text.replace(value, "<redacted>")
        text = re.sub(re.escape(SENTINEL_PREFIX) + r"\S*", "<redacted placeholder>", text)
        return redact_text(_ELLIPSIS_MASKED.sub("<redacted>", text))[:EXCERPT_BYTES]


def _unchunk(raw: bytes) -> bytes:
    """A chunked body's data, as far as ``raw`` holds whole chunk-size lines (a chunk cut short is kept as it is)."""
    out, i = bytearray(), 0
    while True:
        end = raw.find(b"\r\n", i)
        size = _chunk_size(raw[i:end]) if end >= 0 else None
        if not size:
            return bytes(out)
        out += raw[end + 2:end + 2 + size]
        i = end + 2 + size + 2


class RequestLog:
    """Where a run's relays record each request: one JSON line per request in ``path``, a file on the host outside
    every sandbox (the run's directory). Appends are serialized, as several relays share it."""

    def __init__(self, path: Any) -> None:
        import threading

        self.path = path
        self._lock = threading.Lock()

    def __call__(self, entry: dict[str, Any]) -> None:
        import json

        line = (json.dumps(entry, sort_keys=True) + "\n").encode("utf-8")
        with self._lock, open(self.path, "ab") as out:
            out.write(line)


def _chunk_size(line: bytes) -> int | None:
    """A chunk-size line's size, or None when its size is not hex digits alone (``1*HEXDIG``, RFC 9112 §7.1).
    ``int`` would also take a sign or underscores, and a negative size never ends its chunk (#257's quick check, Q1)."""
    token = line.split(b";", 1)[0].strip()
    return int(token, 16) if re.fullmatch(rb"[0-9A-Fa-f]+", token) else None


def _tls_context() -> ssl.SSLContext:
    """The system's default verifying context, with its floor stated: TLS 1.2 is already the default's minimum on every
    interpreter AEW supports, set here so that a reader, or a scanner, need not know that (#257's quick check, Q2)."""
    context = ssl.create_default_context()
    context.minimum_version = TLS_MINIMUM
    return context


# What the provider says, in its TLS alert, when it does not take the client certificate (or got none): OpenSSL's
# reason names for those alerts. With TLS 1.3 the alert comes after the handshake, on the first read.
_CERT_ALERTS = frozenset({"TLSV13_ALERT_CERTIFICATE_REQUIRED", "SSLV3_ALERT_BAD_CERTIFICATE",
                          "SSLV3_ALERT_CERTIFICATE_EXPIRED", "SSLV3_ALERT_CERTIFICATE_REVOKED",
                          "SSLV3_ALERT_CERTIFICATE_UNKNOWN", "SSLV3_ALERT_UNSUPPORTED_CERTIFICATE",
                          "TLSV1_ALERT_UNKNOWN_CA", "TLSV1_ALERT_ACCESS_DENIED"})


def _tls_refused(exc: ssl.SSLError, upstream: Upstream, client: ClientCert | None) -> _Refused:
    """A failed TLS connection to the upstream as a plain answer, never a bare handshake error (register E123). It
    reaches the sandbox, so it names the policy field and the CA file, never the certificate's or the key's path."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        trust = (f"the CA file {client.ca} ({client.field('ca')}): if the provider's CA changed, put the new one there "
                 "and start the run again") if client else "the system's trusted CAs"
        return _Refused(502, "upstream_untrusted", f"the provider relay does not trust {upstream.url}'s certificate "
                        f"({exc.verify_message}): it checks it against {trust}")
    if exc.reason in _CERT_ALERTS:
        if client is None:
            return _Refused(502, "client_cert_required", f"{upstream.url} refused the connection over its client "
                            f"certificate ({exc.reason}), and the policy names none: name one in "
                            "containment.network.client_certs.<provider>")
        return _Refused(502, "client_cert_refused", f"{upstream.url} refused the client certificate named in "
                        f"{client.field('cert')} ({exc.reason}): `aew doctor` checks it, and the provider may not "
                        "accept it")
    if client is None and exc.reason == "SSLV3_ALERT_HANDSHAKE_FAILURE":
        # TLS 1.2's answer to a missing certificate (E123 review, m2). It also means a cipher or version mismatch, so
        # it is not in _CERT_ALERTS, and is worded as a likelihood. A server that ends the handshake and then answers
        # HTTP 400 for the missing certificate (nginx's `ssl_verify_client on`) is relayed as it answered.
        return _Refused(502, "client_cert_required", f"the TLS connection to {upstream.url} failed ({exc.reason}): "
                        "the provider may require a client certificate, and the policy names none: name one in "
                        "containment.network.client_certs.<provider>")
    return _Refused(502, "tls_failed", f"the TLS connection to {upstream.url} failed ({exc.reason or exc})")


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
    """For the run's label: ``network.provider_relay`` (F28 §3.1) and its fixed upstream, and whether it presents a
    client certificate (by its policy field: the label reaches the sandbox, so never a path)."""
    if relay is None:
        return {"provider_relay": "none"}
    return {"provider_relay": "configured", "provider_upstream": relay.upstream.url,
            **({"provider_upstream_proxy": f"{relay.proxy.host}:{relay.proxy.port}"} if relay.proxy else {}),
            **({"provider_client_cert": relay.client.field("cert")} if relay.client else {})}
