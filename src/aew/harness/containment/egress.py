"""F28's generic egress proxy: credentialless, with two policies and R-6 (STG-05 CS-3a; F28 §3.4). It tunnels
``CONNECT`` and forwards plain ``http://`` requests (register E92), under the same host check.

The proxy serves the sandbox's optional non-provider egress, such as OpenCode's catalog fetch in connected mode. It
runs in the host's network namespace, outside the run's sandbox, and holds no credential: it adds none. A tunnel
carries the client's bytes unchanged; a plain request is forwarded with the client's own end-to-end headers, and none
of the proxy's (below). Provider traffic never comes here: it goes through the credentialing relay (F28 §3.3,
decision 5).

**Policies.** :class:`Allowlist` is a bounded ``host:port`` list, the workers' policy. Web, browser and
package-manager destinations are never added to it just because a harness supports them (F28 §3.4). :class:`AnyPublic`
admits any public address, for the Lead (the operator, 2026-10-21, decision 3; CS-4 selects it), with every port. A
policy decides only what is asked; R-6 then judges every address, under either policy, and cannot be turned off.

**A request, in order:**

1. Parse ``CONNECT host:port``, or a plain request whose target is an absolute ``http://`` URL (below). Anything else
   is refused.
2. Ask the policy about ``host:port``. The allowlist answers before any DNS.
3. Resolve the name, once. A literal address is not resolved.
4. Judge every answer (:func:`aew.harness.containment.peer.host_route`, then the policy's address rule).
5. Connect to the literal address, never to the name.
6. Judge the connected socket's peer address the same way.
7. For ``CONNECT``, answer ``200`` and splice bytes both ways, unchanged. For plain ``http://``, forward the one
   request and stream its response back.

**Plain ``http://``** (register E92; CS-4's hand-off, addendum 1, §4). Steps 2 to 6 are ``CONNECT``'s, on the
``host:port`` the URL names (port 80 when it names none), so a plain request reaches exactly what a ``CONNECT`` to that
``host:port`` would. What the request may be is narrow, and anything else is refused before any DNS:

- its target is absolute-form, ``http://`` exactly (RFC 9112 §3.2.2): an origin-form path, ``*``, another scheme, a
  userinfo part (``user@``), a fragment or a control character in it is refused;
- it carries exactly one ``Host``, naming the URL's ``host:port`` (RFC 9112 §3.2);
- its header lines are fields as :mod:`aew.harness.containment.http1` reads them (no control character but HTAB in a
  value); no ``Upgrade``; ``Expect`` only ``100-continue``, which the proxy answers itself;
- its body is framed one way only (RFC 9112 §6.3): one ``Content-Length`` of ASCII digits, or one
  ``Transfer-Encoding`` of exactly ``chunked`` on HTTP/1.1, never both; within :data:`MAX_BODY`, chunk lines and
  trailer fields held to the field-value rule, and a trailer carrying ``Host``, ``Content-Length`` or
  ``Transfer-Encoding`` refused (RFC 9110 §6.5.1).

The proxy forwards it with an origin-form target and the client's own HTTP version (so an HTTP/1.0 client is never sent
a chunked response), ``Host`` set to the URL's authority, the hop-by-hop headers out (``http1.HOP_BY_HOP``, every
``Proxy-*`` header, and ``Connection`` and what it names, in the head and in a chunked body's trailer section), its
framing as checked, and ``Connection: close``. An upstream that answers and closes before it has taken the whole request
(a 401 to a large upload) has that answer relayed. **One request per connection:** the answer says
``Connection: close``, and what the client sends after its one request is never forwarded. The proxy holds no credential
and adds none, so none it holds can reach a host. The response head is bounded (:data:`MAX_RESPONSE_HEAD`), and the
response ends when the upstream ends it, the client goes, :meth:`EgressProxy.close`, or :data:`RESPONSE_IDLE_TIMEOUT`
passes with no byte either way.

**One refused answer refuses the name,** under both policies (the Lead, 2026-10-24). A name whose answers mix public
and host-local addresses looks like rebinding or split-horizon tricks, and refusing it whole is simpler to prove than
picking among its answers. A refusal is ``403`` with a stable reason code in ``X-AEW-Refusal``. It names the refused
address class, never the address: under any-public, the address would let the model map the host's private DNS.

**Where it sits** (CS-3b): a run's proxy listens on ``egress.sock`` in the run's network directory
(:mod:`aew.harness.containment.netns`), which the in-sandbox shim reaches from loopback inside; the label and the
self-test's network row are netns's and probe's. The proxy serves whatever listening socket it is given.

**Known limits:**

- The number of concurrent tunnels is unbounded. F28 gives no number; the shim, its only client, opens one per
  connection made inside. A connection that cannot get a thread is closed unserved (``overloaded``), and the proxy
  goes on serving.
- An established tunnel has no idle timeout: it lasts until either side ends it, or :meth:`EgressProxy.close`.
- Under any-public, the names the model asks for reach the host's resolver, and so the DNS.
- :meth:`EgressProxy.close` starts no new connect, but a connect already in flight is not interrupted. It ends within
  ``CONNECT_TIMEOUT`` (the resolver has its own timeout), and is then closed with nothing relayed.
"""

from __future__ import annotations

import ipaddress
import re
import selectors
import socket
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from aew.errors import ValidationFailed
from aew.harness.containment import peer
from aew.harness.containment.http1 import HOP_BY_HOP, TOKEN, BadField, chunk_size, close_head, fields, head
from aew.http_close import REFUSAL_DRAIN_S, close_after_response

# Implementation bounds, not policy. A CONNECT from Bun or curl is under 200 bytes; 8 KiB is Apache httpd's default
# request-line and header-field limit (LimitRequestLine, LimitRequestFieldSize: 8190 bytes), rounded up.
MAX_HEADER = 8192
# The shim forwards a CONNECT as soon as the harness sends it. The whole request head has one deadline, this long
# from when the proxy starts reading the request, however its bytes are spaced.
HEADER_TIMEOUT = 10.0
# A refused or unreachable address fails in milliseconds (F28 §1, P1); this bounds only a SYN nobody answers.
CONNECT_TIMEOUT = 10.0
# How long close() waits for each connection's thread after shutting its sockets down.
JOIN_TIMEOUT = 5.0
# An accept that fails (out of descriptors, EMFILE) leaves the listener readable: the accept loop waits this long
# before it tries again, rather than spinning while descriptors free up.
ACCEPT_BACKOFF = 0.1
CHUNK = 64 * 1024
# Implementation bounds for a plain http:// request (E92), not policy. A body: a plain fetch is a GET; 16 MiB is far
# above a form post or a small upload, and below what one connection should hold the proxy for.
MAX_BODY = 16 * 1024 * 1024
# A pause inside the request body, and a response with no byte either way, this long ends the request.
BODY_TIMEOUT = 60.0
RESPONSE_IDLE_TIMEOUT = 60.0
# A response head: nginx's default for a request head (large_client_header_buffers 4 8k), as the relay's is.
MAX_RESPONSE_HEAD = 32 * 1024

_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
# A refused target as the run's record keeps it (the designer's ruling of 2026-11-06, the Lead's point 1): the CONNECT's
# ``host:port`` as :func:`authority` normalized it, in a closed character set (a host name's, an address's and the
# port's), cut to a host name's longest (RFC 1035: 253). At most this many distinct targets per run, then a count.
REFUSED_TARGET_CHARS = re.compile(r"[^a-z0-9.:\[\]-]")
REFUSED_TARGET_MAX = 253
MAX_REFUSED_TARGETS = 20
_PHRASES = {400: "Bad Request", 403: "Forbidden", 405: "Method Not Allowed", 408: "Request Timeout",
            413: "Content Too Large", 417: "Expectation Failed", 431: "Request Header Fields Too Large",
            501: "Not Implemented", 502: "Bad Gateway"}

Resolver = Callable[[str, int], Iterable[Any]]
Connector = Callable[[peer.IP, int, float], socket.socket]


def authority(text: str) -> tuple[str, int]:
    """``host:port`` as ``(host, port)``, normalized: a lowercase name without its trailing dot, or an address in its
    compressed form (an IPv6 one in brackets). Raises ``ValueError`` saying what is wrong. The allowlist's entries and
    every request go through it, so they compare equal exactly when they name the same target. Text is validated
    before it is transformed: a name must be ASCII before it is lowercased, and a port at most five digits before it
    is read as a number. An address with a zone id (``%eth0``) is refused: a zone means something only on a link-local
    address, which R-6 refuses anyway, and the address connected must be the one judged."""
    if text.startswith("["):
        inside, sep, rest = text[1:].partition("]")
        if not sep or not rest.startswith(":"):
            raise ValueError("an IPv6 address is written [address]:port")
        if "%" in inside:
            raise ValueError("an address with a zone id is not a target")
        host, port_text = str(ipaddress.IPv6Address(inside)), rest[1:]
    else:
        host, sep, port_text = text.rpartition(":")
        if not sep or not host:
            raise ValueError("the target is host:port")
        if ":" in host:
            raise ValueError("an IPv6 address is written [address]:port")
        try:
            host = str(ipaddress.IPv4Address(host))
        except ValueError:
            if not host.isascii():
                raise ValueError(f"{host!r} is neither an IP address nor an ASCII host name") from None
            host = host.lower().removesuffix(".")
            labels = host.split(".")
            if len(host) > 253 or not all(_LABEL.fullmatch(label) for label in labels):
                raise ValueError(f"{host!r} is neither an IP address nor a host name") from None
    if not (port_text.isascii() and port_text.isdigit() and len(port_text) <= 5 and 0 < int(port_text) < 65536):
        raise ValueError("the port must be a number from 1 to 65535")
    return host, int(port_text)


def refused_target(target: str) -> str:
    """``target`` as the run's record keeps it: only :data:`REFUSED_TARGET_CHARS`'s characters, with the host cut to
    :data:`REFUSED_TARGET_MAX` before its port is put back, so a long host keeps its port (review of #340, n4). What
    :func:`authority` passes is already in that set; this holds whatever reaches the record."""
    kept = REFUSED_TARGET_CHARS.sub("", target.lower())
    host, colon, port = kept.rpartition(":")
    if not (colon and host and port.isdigit() and len(port) <= 5):
        return kept[:REFUSED_TARGET_MAX]
    return f"{host[:REFUSED_TARGET_MAX]}:{port}"


def _literal(host: str) -> peer.IP | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _http_authority(text: str) -> tuple[str, int]:
    """An ``http://`` URL's authority (or a ``Host`` value) as :func:`authority` normalizes it, port 80 when it names
    none (RFC 9110 §4.2.1)."""
    named = "]:" in text if text.startswith("[") else ":" in text
    return authority(text if named else f"{text}:80")


def _framing(headers: list[tuple[str, str]], version: str) -> tuple[str, int]:
    """How a plain request's body is framed, one way only (RFC 9112 §6.1, §6.3): ``("chunked", 0)``,
    ``("length", n)`` or ``("none", 0)``. Anything else is refused: both headers, either one repeated or in list form,
    a coding other than exactly ``chunked``, chunked on HTTP/1.0, or a length of other than ASCII digits."""
    codings = [v for k, v in headers if k.lower() == "transfer-encoding"]
    lengths = [v for k, v in headers if k.lower() == "content-length"]
    if codings:
        if lengths or len(codings) > 1 or codings[0].lower() != "chunked" or version != "HTTP/1.1":
            raise _Refused(400, "bad_framing", "a request body through this egress proxy is framed one way only: one "
                           "Content-Length, or Transfer-Encoding: chunked alone on HTTP/1.1")
        return "chunked", 0
    if len(lengths) > 1:
        raise _Refused(400, "bad_framing", "the request carries more than one Content-Length")
    if not lengths:
        return "none", 0
    if not re.fullmatch(r"[0-9]{1,19}", lengths[0]):
        raise _Refused(400, "bad_framing", "the request's Content-Length is not a number")
    if int(lengths[0]) > MAX_BODY:
        raise _Refused(413, "body_too_large", f"the request's body exceeds this egress proxy's bound of {MAX_BODY} "
                       "bytes, so it was not sent")
    return "length", int(lengths[0])


def _connection_named(headers: list[tuple[str, str]]) -> set[str]:
    """The header names a request's ``Connection`` lists, lowercased, and ``connection`` itself: hop-by-hop."""
    return {"connection"} | {t.strip().lower() for k, v in headers if k.lower() == "connection" for t in v.split(",")}


class _UpstreamClosed(Exception):
    """The upstream stopped taking a plain request before all of it was sent."""


class _Reader:
    """Buffered reads of a plain request's body from the client, each within ``timeout``."""

    def __init__(self, sock: socket.socket, buffered: bytes, timeout: float) -> None:
        self.sock, self.buffer, self.timeout = sock, buffered, timeout

    def _more(self) -> None:
        self.sock.settimeout(self.timeout)
        try:
            data = self.sock.recv(CHUNK)
        except TimeoutError:
            raise _Refused(408, "body_timeout", "the request body stopped arriving") from None
        except ConnectionError:
            data = b""
        if not data:
            raise _Refused(400, "incomplete", "the connection closed before the request's body was complete")
        self.buffer += data

    def read(self, most: int) -> bytes:
        if not self.buffer:
            self._more()
        out, self.buffer = self.buffer[:most], self.buffer[most:]
        return out

    def line(self) -> bytes:
        """One line with its CRLF; a line longer than :data:`MAX_HEADER` is refused."""
        while b"\r\n" not in self.buffer:
            if len(self.buffer) > MAX_HEADER:
                raise _Refused(400, "bad_chunk", "a chunk-size or trailer line is too long")
            self._more()
        end = self.buffer.index(b"\r\n") + 2
        out, self.buffer = self.buffer[:end], self.buffer[end:]
        return out


class _Plain:
    """A plain ``http://`` request, as checked: what is forwarded, and how its body is framed (``none``, ``length``
    with its size, or ``chunked``)."""

    def __init__(self, method: str, path: str, version: str, headers: list[tuple[str, str]],
                 framing: tuple[str, int], expect_continue: bool) -> None:
        self.method, self.path, self.version, self.headers = method, path, version, headers
        self.framing, self.expect_continue = framing, expect_continue
        self.began = False  # its response's head has gone to the client: nothing else may be sent it


class Policy(Protocol):
    def admits(self, host: str, port: int) -> str | None:
        """Why ``host:port`` is refused before anything is resolved, or None."""

    def refuses(self, ip: peer.IP) -> str | None:
        """Why an address is refused beyond R-6, or None."""

    def describe(self) -> dict[str, Any]: ...


class Allowlist:
    """F28 §3.4's bounded allowlist, the workers' policy: exact ``host:port`` entries, no patterns. A listed entry
    is still refused when it resolves to an address R-6 refuses."""

    def __init__(self, entries: Iterable[str]) -> None:
        allowed: set[tuple[str, int]] = set()
        for entry in entries:
            try:
                allowed.add(authority(entry))
            except ValueError as exc:
                raise ValidationFailed(f"egress allowlist entry {entry!r} is not host:port: {exc}", entry=entry,
                                       reason="bad_allowlist_entry") from None
        self._allowed = frozenset(allowed)

    def admits(self, host: str, port: int) -> str | None:
        return None if (host, port) in self._allowed else "not_allowlisted"

    def refuses(self, ip: peer.IP) -> str | None:
        return None

    def describe(self) -> dict[str, Any]:
        """For the run's label (``network.egress_allow``, F28 §3.1; CS-3b records it)."""
        shown = sorted(f"[{h}]:{p}" if ":" in h else f"{h}:{p}" for h, p in self._allowed)
        return {"policy": "allowlist", "allow": shown}


class AnyPublic:
    """Any public address, on any port: the Lead's policy (CS-4 selects it). "Public" is
    :func:`aew.harness.containment.peer.not_public`'s."""

    def admits(self, host: str, port: int) -> str | None:
        return None

    def refuses(self, ip: peer.IP) -> str | None:
        return peer.not_public(ip)

    def describe(self) -> dict[str, Any]:
        return {"policy": "any_public"}


class _Refused(Exception):
    """A refused request. ``target`` is the ``host:port`` a CONNECT named, on a refusal of that target (403), which
    the proxy records (:meth:`EgressProxy.refused_targets`); None on any other refusal."""

    def __init__(self, status: int, reason: str, message: str, target: str | None = None) -> None:
        super().__init__(message)
        self.status, self.reason, self.message, self.target = status, reason, message, target

    def response(self) -> bytes:
        body = self.message.encode()
        head = (f"HTTP/1.1 {self.status} {_PHRASES[self.status]}\r\nX-AEW-Refusal: {self.reason}\r\n"
                f"Content-Type: text/plain; charset=utf-8\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n")
        return head.encode() + body


def _resolve(host: str, port: int) -> list[Any]:
    return [info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)]


def _connect(ip: peer.IP, port: int, timeout: float) -> socket.socket:
    sock = socket.socket(socket.AF_INET if ip.version == 4 else socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect((str(ip), port))  # a literal: nothing is resolved here
    except BaseException:
        sock.close()
        raise
    return sock


def _shutdown(sock: socket.socket, how: int = socket.SHUT_RDWR) -> None:
    try:
        sock.shutdown(how)
    except OSError:
        pass


class Service:
    """One listening socket served by a thread per connection, as the egress proxy and the provider relay
    (``relay.py``, CS-3b) both are: :meth:`handle` serves one connection; the rest (accepting, tracking every open
    socket, :meth:`close`) is shared. Without a listener it serves only the connections passed to :meth:`handle`."""

    name = "aew-service"

    def __init__(self, *, listener: socket.socket | None = None) -> None:
        self.listener = listener
        # Telemetry: how many requests were served ("allowed") or refused, by reason. Never targets or payload.
        self.decisions: dict[str, int] = {}
        self._lock = threading.Lock()
        self._open: set[socket.socket] = set()
        self._handlers: set[threading.Thread] = set()
        self._closed = threading.Event()
        self._wake_r, self._wake_w = socket.socketpair()
        self._thread = threading.Thread(target=self._serve, name=self.name, daemon=True)

    def start(self) -> Service:
        if self.listener is None:
            raise ValueError(f"{type(self).__name__} without a listener serves only handle()")
        self._thread.start()
        return self

    def __enter__(self) -> Service:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Stop accepting, end every tunnel, and wait for their threads. The wake byte is never read, so every
        selector that watches the wake socket (the accept loop's and each tunnel's) sees it. The proxy's own sockets
        are closed whatever happens on the way."""
        with self._lock:
            if self._closed.is_set():
                return
            self._closed.set()
            live, handlers = list(self._open), list(self._handlers)
        try:
            try:
                self._wake_w.send(b"x")
            except OSError:
                pass
            if self._thread.is_alive():
                self._thread.join(JOIN_TIMEOUT)
            for sock in live:  # wakes a thread blocked in sendall towards a side that does not read (Linux)
                _shutdown(sock)
            for thread in handlers:
                if thread.ident is not None:  # one recorded but not yet started has nothing to wait for
                    thread.join(JOIN_TIMEOUT)
            for sock in live:  # and on Windows, where only closing the socket wakes it
                sock.close()
        finally:
            for sock in (self._wake_r, self._wake_w, self.listener):
                if sock is not None:
                    sock.close()

    def _count(self, outcome: str) -> None:
        with self._lock:
            self.decisions[outcome] = self.decisions.get(outcome, 0) + 1

    def counts(self) -> dict[str, int]:
        """A copy of :attr:`decisions`."""
        with self._lock:
            return dict(self.decisions)

    def _track(self, sock: socket.socket) -> bool:
        with self._lock:
            if self._closed.is_set():
                return False
            self._open.add(sock)
            return True

    def _untrack(self, sock: socket.socket) -> None:
        with self._lock:
            self._open.discard(sock)
        sock.close()

    def _serve(self) -> None:
        listener = self.listener
        assert listener is not None  # start() refuses to run without one
        with selectors.DefaultSelector() as selector:
            selector.register(listener, selectors.EVENT_READ)
            selector.register(self._wake_r, selectors.EVENT_READ)
            while not self._closed.is_set():
                for key, _ in selector.select():
                    if key.fileobj is self._wake_r:
                        return
                    try:
                        conn, _ = listener.accept()
                    except OSError:
                        self._closed.wait(ACCEPT_BACKOFF)
                        continue
                    thread = threading.Thread(target=self._handle_then_forget, args=(conn,),
                                              name=f"{self.name}-conn", daemon=True)
                    with self._lock:
                        self._handlers.add(thread)
                    try:
                        thread.start()
                    except RuntimeError:  # no thread can be started: this connection is closed unserved
                        with self._lock:
                            self._handlers.discard(thread)
                        self._count("overloaded")
                        conn.close()

    def _handle_then_forget(self, conn: socket.socket) -> None:
        try:
            self.handle(conn)
        finally:
            with self._lock:
                self._handlers.discard(threading.current_thread())

    def handle(self, conn: socket.socket) -> None:
        """Serve one client connection to its end, and close it."""
        raise NotImplementedError


class EgressProxy(Service):
    """Serves ``listener`` (any listening socket; the proxy owns it from here) under ``policy``. Without a listener
    it serves only the connections passed to :meth:`handle`.

    ``resolve``, ``connect`` and ``is_local`` are seams for tests: the defaults are the host's resolver, a plain
    connect to a literal address, and :func:`peer.is_host_address`. Nothing a request carries reaches them."""

    name = "aew-egress"

    def __init__(self, policy: Policy, *, listener: socket.socket | None = None, resolve: Resolver = _resolve,
                 connect: Connector = _connect, is_local: Callable[[peer.IP], bool] = peer.is_host_address,
                 header_timeout: float = HEADER_TIMEOUT, connect_timeout: float = CONNECT_TIMEOUT) -> None:
        super().__init__(listener=listener)
        self.policy = policy
        self._resolve, self._connect, self._is_local = resolve, connect, is_local
        self.header_timeout, self.connect_timeout = header_timeout, connect_timeout
        self._refused: dict[str, dict[str, Any]] = {}  # refused target -> its record entry (:meth:`_record_target`)
        self._refused_more = 0

    def start(self) -> EgressProxy:
        super().start()
        return self

    def __enter__(self) -> EgressProxy:
        return self.start()

    def handle(self, conn: socket.socket) -> None:
        """Serve one client connection to its end, and close it."""
        if not self._track(conn):
            conn.close()
            return
        upstream: socket.socket | None = None
        established = False  # a tunnel is open, or a plain request's response has begun: nothing else goes to conn
        plain: _Plain | None = None
        try:
            host, port, early, plain = self._read_request(conn)
            conn.settimeout(self.header_timeout)  # for the answer
            upstream = self._open_upstream(host, port, f"{plain.method} http://" if plain else "CONNECT ")
            if not self._track(upstream):
                return
            if plain is not None:
                self._forward(conn, upstream, host, port, plain, early)
                return
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            established = True
            self._count("allowed")
            conn.settimeout(None)
            upstream.settimeout(None)
            if early:  # bytes the client sent behind its request, such as a TLS ClientHello
                upstream.sendall(early)
            self._splice(conn, upstream)
        except _Refused as refused:
            if not (established or plain is not None and plain.began):
                self._answer(conn, refused)
        except OSError:
            if plain is not None and upstream is not None and not plain.began:
                # The request may have reached the upstream: said so, and never sent again
                self._answer(conn, _Refused(502, "upstream_broken", "the connection to the upstream broke before its "
                                            "response began; it may have received the request, which the egress "
                                            "proxy does not send again"))
            # else the client or the upstream went away mid-tunnel
        except Exception:  # anything else is counted, and answered with a fixed 502 unless the tunnel is open
            if established or plain is not None and plain.began:
                self._count("proxy_error")
            else:
                self._answer(conn, _Refused(502, "proxy_error", "the egress proxy could not serve this request"))
        finally:
            if upstream is not None:
                self._untrack(upstream)
            self._untrack(conn)

    def _answer(self, conn: socket.socket, refused: _Refused) -> None:
        self._count(refused.reason)
        if refused.target is not None:
            self._record_target(refused.target, refused.reason)
        try:
            conn.settimeout(self.header_timeout)
            conn.sendall(refused.response())
            close_after_response(conn, REFUSAL_DRAIN_S)
        except OSError:
            pass

    def _record_target(self, target: str, reason: str) -> None:
        """Record a refused target for the run's record (the designer's ruling of 2026-11-06, the Lead's point 1):
        records only. The agent chose the string, so it is kept in a closed character set and cut
        (:func:`refused_target`); at most :data:`MAX_REFUSED_TARGETS` distinct targets are named, and refusals of any
        other target are counted, not named."""
        kept = refused_target(target)
        with self._lock:
            entry = self._refused.get(kept)
            if entry is None and len(self._refused) >= MAX_REFUSED_TARGETS:
                self._refused_more += 1
                return
            if entry is None:
                entry = self._refused[kept] = {"target": kept, "reasons": [], "count": 0}
            entry["count"] += 1
            if reason not in entry["reasons"]:
                entry["reasons"] = sorted([*entry["reasons"], reason])

    def refused_targets(self) -> dict[str, Any]:
        """The refused targets so far, in the order first refused: ``targets`` (each ``target``, its ``reasons`` and
        ``count``) and ``more``, how many refusals named a target past the first :data:`MAX_REFUSED_TARGETS`. Never
        given to any agent and never offered as an allowlist entry: it is the run's record's only."""
        with self._lock:
            return {"targets": [{**e, "reasons": list(e["reasons"])} for e in self._refused.values()],
                    "more": self._refused_more}

    def _read_request(self, conn: socket.socket) -> tuple[str, int, bytes, _Plain | None]:
        """The request head, which has one deadline (``header_timeout`` from now) however its bytes are spaced: the
        ``host:port`` it names, the bytes after its head, and for a plain ``http://`` request, the request as checked
        (:meth:`_plain`)."""
        deadline = time.monotonic() + self.header_timeout
        buf = b""
        while True:
            end = buf.find(b"\r\n\r\n")
            if 0 <= end <= MAX_HEADER:
                break
            if len(buf) > MAX_HEADER:
                raise _Refused(431, "header_too_large", f"the request's header exceeds {MAX_HEADER} bytes")
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
        line = buf[:buf.find(b"\r\n")]
        try:
            method, target, version = line.decode("ascii").split(" ")
        except (UnicodeDecodeError, ValueError):
            raise _Refused(400, "bad_request", "the request line is not METHOD target HTTP/1.1") from None
        if version not in ("HTTP/1.1", "HTTP/1.0"):
            raise _Refused(400, "bad_request", f"unsupported version {version!r}")
        if method != "CONNECT":
            # A plain request through the proxy (the Lead's HTTP_PROXY, STG-05 CS-4), forwarded under the same host
            # check (register E92)
            host, port, plain = self._plain(method, target, version, buf[:end])
            return host, port, buf[end + 4:], plain
        try:
            host, port = authority(target)
        except ValueError as exc:
            raise _Refused(400, "bad_request", f"CONNECT {target}: {exc}") from None
        return host, port, buf[end + 4:], None

    @staticmethod
    def _plain(method: str, target: str, version: str, head_bytes: bytes) -> tuple[str, int, _Plain]:
        """A plain request's ``host:port`` and the request as checked (the module docstring's list), or refused."""
        if not TOKEN.fullmatch(method):
            raise _Refused(400, "bad_request", "the request line is not METHOD target HTTP/1.1")
        if not target.startswith("http://"):
            if target.startswith("/") or target == "*":
                raise _Refused(400, "origin_form", "a request through this egress proxy names its whole URL "
                               "(http://host/path), as a client sends one to a proxy; https:// goes through CONNECT")
            raise _Refused(400, "scheme", "this egress proxy forwards http:// URLs and tunnels https:// with CONNECT; "
                           "it forwards no other scheme")
        if any(c <= " " or c == "\x7f" or c == "#" for c in target):
            raise _Refused(400, "bad_request", "the request's URL holds a control character or a fragment")
        rest = target[len("http://"):]
        cut = min((i for i in (rest.find("/"), rest.find("?")) if i >= 0), default=len(rest))
        named, path = rest[:cut], rest[cut:]
        if "@" in named:
            raise _Refused(400, "userinfo", "the request's URL carries a user name or password (user@host), which "
                           "this egress proxy never forwards; send any credential in a header instead")
        try:
            host, port = _http_authority(named)
        except ValueError as exc:
            raise _Refused(400, "bad_request", f"the request's URL: {exc}") from None
        try:
            headers = fields(head_bytes.split(b"\r\n")[1:])
        except BadField as exc:
            raise _Refused(400, "bad_header", str(exc)) from None
        hosts = [v for k, v in headers if k.lower() == "host"]
        try:
            same = len(hosts) == 1 and _http_authority(hosts[0]) == (host, port)
        except ValueError:
            same = False
        if not same:
            raise _Refused(400, "host_mismatch", "the request must carry one Host header naming its URL's host and "
                           "port (RFC 9112 §3.2)")
        if any(k.lower() == "upgrade" for k, _ in headers):
            raise _Refused(501, "upgrade", "this egress proxy forwards plain HTTP requests, not a protocol upgrade")
        expects = [v.lower() for k, v in headers if k.lower() == "expect"]
        if any(v != "100-continue" for v in expects):
            raise _Refused(417, "expectation", "this egress proxy meets no expectation but 100-continue")
        return host, port, _Plain(method, "/" + path if path.startswith("?") else path or "/", version, headers,
                                  _framing(headers, version), bool(expects))

    def _refusal(self, value: Any) -> str | None:
        """R-6 first, whatever the policy; then the policy's own address rule."""
        ip = peer.address(value)
        return peer.host_route(ip, is_local=self._is_local) or self.policy.refuses(ip)

    def _open_upstream(self, host: str, port: int, verb: str = "CONNECT ") -> socket.socket:
        """The connection to ``host:port``, under the policy and R-6 (the module docstring's steps 2 to 6), whether a
        ``CONNECT`` or a plain request named it; ``verb`` starts each refusal's message."""
        target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        asked = f"{verb}{target}"
        reason = self.policy.admits(host, port)
        if reason:
            raise _Refused(403, reason, f"{asked} refused: it is not on this run's egress allowlist "
                           "(F28 §3.4). A destination is added by the operator's execution policy, never by a run.",
                           target)
        literal = _literal(host)
        try:
            answers = [literal] if literal is not None else [peer.address(a) for a in self._resolve(host, port)]
        except (OSError, ValueError, UnicodeError):
            answers = []
        if not answers:
            raise _Refused(502, "unresolved", f"{asked}: the name did not resolve")
        answers = list(dict.fromkeys(answers))
        for ip in answers:  # one refused answer refuses the target (see the module docstring)
            reason = self._refusal(ip)
            if reason:
                raise _Refused(403, reason, self._why(asked, reason), target)
        for ip in answers:
            if self._closed.is_set():  # no new connect once close() has begun
                raise _Refused(502, "closed", f"{asked}: the egress proxy is closing")
            try:
                sock = self._connect(ip, port, self.connect_timeout)
            except OSError:
                continue
            try:
                reason = self._refusal(sock.getpeername())  # R-6 on the address actually connected
            except (OSError, ValueError):
                reason = "peer_unknown"
            if reason:
                sock.close()
                raise _Refused(403, reason, self._why(asked, reason), target)
            return sock
        raise _Refused(502, "unreachable", f"{asked}: no address of it could be connected")

    @staticmethod
    def _why(asked: str, reason: str) -> str:
        if reason == "peer_unknown":
            return (f"{asked} refused: the connected peer's address could not be confirmed, so nothing was "
                    "relayed. Retry the request.")
        if reason in peer.HOST_ROUTE_REASONS:
            return (f"{asked} refused: it reaches a {reason} address. The egress proxy runs on the host and "
                    "never connects to the host's own addresses, even allowlisted ones (R-6). Provider traffic goes "
                    "through the provider relay, not this proxy.")
        return (f"{asked} refused: it reaches a {reason} address, which is not public; this run's egress "
                "admits public addresses only.")

    def _forward(self, conn: socket.socket, upstream: socket.socket, host: str, port: int, plain: _Plain,
                 early: bytes) -> None:
        """Forward one plain request to ``upstream`` (already judged) and stream its response back. A refusal before
        the response begins (``plain.began``) is raised, for :meth:`handle` to answer."""
        named = _connection_named(plain.headers)
        shown = f"[{host}]" if ":" in host else host
        out = [("Host", shown if port == 80 else f"{shown}:{port}")]
        for name, value in plain.headers:
            low = name.lower()
            if (low in HOP_BY_HOP or low in named or low.startswith("proxy-")
                    or low in ("host", "content-length", "transfer-encoding")):
                continue
            out.append((name, value))
        kind, length = plain.framing
        if kind == "length":
            out.append(("Content-Length", str(length)))
        elif kind == "chunked":
            out.append(("Transfer-Encoding", "chunked"))
        out.append(("Connection", "close"))
        upstream.settimeout(self.connect_timeout)

        def send(data: bytes) -> None:
            try:
                upstream.sendall(data)
            except OSError:
                raise _UpstreamClosed from None

        try:
            # The client's own version (RFC 9112 §2.3): an HTTP/1.0 client is never sent a chunked response
            send(head(f"{plain.method} {plain.path} {plain.version}", out))
            if plain.expect_continue and kind != "none":
                conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
            self._send_body(conn, send, plain.framing, early, named)
        except _UpstreamClosed:
            # The upstream stopped taking the request: it may have answered first (a 401 to a large upload), and that
            # answer is the client's. None: said as it happened
            self._count("upstream_closed")
            try:
                self._respond(conn, upstream, plain)
            except _Refused as refused:
                if refused.reason != "no_response":
                    raise
                raise _Refused(502, "upstream_closed", "the upstream closed the connection while the request was "
                               "being sent, and sent no response; it may have received part of the request, which "
                               "the egress proxy does not send again") from None
            close_after_response(conn, REFUSAL_DRAIN_S)  # the client may still be sending: no reset over the answer
            return
        self._count("allowed")  # the whole request went: a refusal of its body is counted as that, never as allowed
        self._respond(conn, upstream, plain)

    def _send_body(self, conn: socket.socket, send: Callable[[bytes], None], framing: tuple[str, int], early: bytes,
                   named: set[str]) -> None:
        """The request body as its head frames it, and nothing after it (one request per connection). A chunked body
        is bounded by :data:`MAX_BODY`, its framing included, and refused at the line that would pass it; its size
        lines and trailer fields are held to the field-value rule (:func:`http1.chunk_size`, :func:`http1.fields`).
        Trailer fields take the head's rule too: a hop-by-hop or ``Proxy-*`` field, ``Connection`` and what the head's
        ``Connection`` names are left out, and ``Host``, ``Content-Length`` or ``Transfer-Encoding`` is refused
        (RFC 9110 §6.5.1). A refused line is never sent, so the upstream never gets the request whole."""
        kind, left = framing
        reader = _Reader(conn, early, BODY_TIMEOUT)
        if kind == "length":
            while left:
                data = reader.read(min(left, CHUNK))
                send(data)
                left -= len(data)
            return
        if kind != "chunked":
            return
        total = 0

        def counted(n: int) -> None:
            nonlocal total
            total += n
            if total > MAX_BODY:
                raise _Refused(413, "body_too_large", f"the request's body exceeds this egress proxy's bound of "
                               f"{MAX_BODY} bytes, so it was not sent whole")

        while True:
            line = reader.line()
            size = chunk_size(line[:-2])
            if size is None:
                raise _Refused(400, "bad_chunk", "the request body's chunked encoding is malformed")
            counted(len(line) + (size + 2 if size else 0))
            send(line)
            if size == 0:
                while True:  # the trailer section, to its empty line
                    trailer = reader.line()
                    counted(len(trailer))
                    if trailer == b"\r\n":
                        send(trailer)
                        return
                    try:
                        [(name, _)] = fields([trailer[:-2]])
                    except BadField as exc:
                        raise _Refused(400, "bad_header", f"a trailer field: {exc}") from None
                    low = name.lower()
                    if low in ("host", "content-length", "transfer-encoding"):
                        raise _Refused(400, "bad_header", f"a trailer may not carry {name} (RFC 9110 §6.5.1)")
                    if not (low in HOP_BY_HOP or low in named or low.startswith("proxy-")):
                        send(trailer)
            while size:
                data = reader.read(min(size, CHUNK))
                send(data)
                size -= len(data)
            end = reader.read(2)
            if len(end) < 2:
                end += reader.read(1)
            if end != b"\r\n":
                raise _Refused(400, "bad_chunk", "a chunk's data is not followed by CRLF")
            send(end)

    def _respond(self, conn: socket.socket, upstream: socket.socket, plain: _Plain) -> None:
        """The upstream's response to the client: interim (1xx) heads as they come, the final head with its hop-by-hop
        headers out and ``Connection: close`` in (:func:`http1.close_head`), then its bytes as they come until the
        upstream ends them, the client goes, :meth:`close`, or :data:`RESPONSE_IDLE_TIMEOUT` passes with no byte. What
        the client sends meanwhile is read and dropped, never forwarded."""
        buf = b""
        while True:
            while b"\r\n\r\n" not in buf:
                if len(buf) > MAX_RESPONSE_HEAD:
                    raise _Refused(502, "bad_response", "the upstream's response head is longer than this egress "
                                   f"proxy's bound of {MAX_RESPONSE_HEAD} bytes")
                upstream.settimeout(RESPONSE_IDLE_TIMEOUT)
                try:
                    data = upstream.recv(CHUNK)
                except TimeoutError:
                    raise _Refused(502, "no_response", "the upstream sent no response in time; it may have received "
                                   "the request, which the egress proxy does not send again") from None
                if not data:
                    raise _Refused(502, "no_response", "the upstream closed without a response; it may have received "
                                   "the request, which the egress proxy does not send again")
                buf += data
            end = buf.index(b"\r\n\r\n") + 4
            if end > MAX_RESPONSE_HEAD:
                raise _Refused(502, "bad_response", "the upstream's response head is longer than this egress proxy's "
                               f"bound of {MAX_RESPONSE_HEAD} bytes")
            response, buf = buf[:end], buf[end:]
            status = response.split(b"\r\n", 1)[0].split(b" ")
            interim = len(status) > 1 and status[1].startswith(b"1") and status[1] != b"101"
            conn.settimeout(RESPONSE_IDLE_TIMEOUT)  # a client that does not read ends the response
            if not interim:
                plain.began = True  # set before the send: a part-sent head is never followed by a refusal
            conn.sendall(response if interim else close_head(response))
            if not interim:
                break
        if buf:
            conn.sendall(buf)
        with selectors.DefaultSelector() as selector:
            for sock in (self._wake_r, conn, upstream):
                selector.register(sock, selectors.EVENT_READ)
            while True:
                ready = {key.fileobj for key, _ in selector.select(RESPONSE_IDLE_TIMEOUT)}
                if not ready or self._wake_r in ready:
                    return
                if conn in ready:
                    try:
                        if not conn.recv(CHUNK):  # the client went; anything else it sends is dropped
                            return
                    except ConnectionError:
                        return
                if upstream in ready:
                    data = upstream.recv(CHUNK)
                    if not data:
                        return
                    conn.sendall(data)

    def _splice(self, conn: socket.socket, upstream: socket.socket) -> None:
        """Relay both ways, one thread per direction: a side that does not read stalls only the direction towards it
        (``sendall`` blocking is the backpressure), never the other one, so the proxy adds no deadlock a direct
        connection would not have. Either side's end closes the tunnel both ways (RFC 9110 §9.3.6), after passing on
        what that side sent; ``handle`` then closes both sockets."""
        done_r, done_w = socket.socketpair()
        try:
            back = threading.Thread(target=self._relay, args=(upstream, conn, done_r, done_w),
                                    name="aew-egress-tunnel", daemon=True)
            back.start()
            self._relay(conn, upstream, done_r, done_w)
            back.join()
        finally:
            done_r.close()
            done_w.close()

    def _relay(self, src: socket.socket, dst: socket.socket, done_r: socket.socket, done_w: socket.socket) -> None:
        """One direction, until ``src`` ends, the other direction ends (``done_r``), or ``close()`` (the proxy's
        wake socket). Both wake sockets stay readable once written, and are watched rather than relying on a
        shutdown: on Windows a shutdown made by another thread does not end a wait for ``src``. When this direction
        ends, both sockets are shut down as well, which ends the other direction even mid-``sendall`` (on Linux)."""
        try:
            with selectors.DefaultSelector() as selector:
                for sock in (self._wake_r, done_r, src):
                    selector.register(sock, selectors.EVENT_READ)
                while True:
                    ready = {key.fileobj for key, _ in selector.select()}
                    if self._wake_r in ready or done_r in ready:
                        return
                    data = src.recv(CHUNK)
                    if not data:
                        return
                    dst.sendall(data)
        except OSError:
            pass  # a side broke: the tunnel ends both ways all the same
        finally:
            _shutdown(src)
            _shutdown(dst)
            try:
                done_w.send(b"x")
            except OSError:
                pass
