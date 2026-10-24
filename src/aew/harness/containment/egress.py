"""F28's generic egress proxy: credentialless, CONNECT only, with two policies and R-6 (STG-05 CS-3a; F28 §3.4).

The proxy serves the sandbox's optional non-provider egress, such as OpenCode's catalog fetch in connected mode. It
runs in the host's network namespace, outside the run's sandbox, and holds no credential: it never sees or adds
one, and it forwards no request header. Provider traffic never comes here: it goes through the credentialing relay
(F28 §3.3, decision 5).

**Policies.** :class:`Allowlist` is a bounded ``host:port`` list, the workers' policy. Web, browser and
package-manager destinations are never added to it just because a harness supports them (F28 §3.4). :class:`AnyPublic`
admits any public address, for the Lead (the operator, 2026-10-21, decision 3; CS-4 selects it), with every port. A
policy decides only what is asked; R-6 then judges every address, under either policy, and cannot be turned off.

**A request, in order:**

1. Parse ``CONNECT host:port``. Anything else is refused.
2. Ask the policy about ``host:port``. The allowlist answers before any DNS.
3. Resolve the name, once. A literal address is not resolved.
4. Judge every answer (:func:`aew.harness.containment.peer.host_route`, then the policy's address rule).
5. Connect to the literal address, never to the name.
6. Judge the connected socket's peer address the same way.
7. Answer ``200`` and splice bytes both ways, unchanged.

**One refused answer refuses the name,** under both policies (the Lead, 2026-10-24). A name whose answers mix public
and host-local addresses looks like rebinding or split-horizon tricks, and refusing it whole is simpler to prove than
picking among its answers. A refusal is ``403`` with a stable reason code in ``X-AEW-Refusal``. It names the refused
address class, never the address: under any-public, the address would let the model map the host's private DNS.

**Not here:** the AF_UNIX listener and its bind into the sandbox, the shim that forwards to it, the label and the
self-test row are CS-3b's. The proxy serves whatever listening socket it is given.

**Known limits:**

- The number of concurrent tunnels is unbounded. F28 gives no number, and the shim, its only client, is CS-3b's. A
  connection that cannot get a thread is closed unserved (``overloaded``), and the proxy goes on serving.
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

# Implementation bounds, not policy. A CONNECT from Bun or curl is under 200 bytes; 8 KiB is Apache httpd's default
# request-line and header-field limit (LimitRequestLine, LimitRequestFieldSize: 8190 bytes), rounded up.
MAX_HEADER = 8192
# The shim forwards a CONNECT as soon as the harness sends it. The whole request head has one deadline, this long
# after the connection was accepted, however its bytes are spaced.
HEADER_TIMEOUT = 10.0
# A refused or unreachable address fails in milliseconds (F28 §1, P1); this bounds only a SYN nobody answers.
CONNECT_TIMEOUT = 10.0
# How long close() waits for each connection's thread after shutting its sockets down.
JOIN_TIMEOUT = 5.0
# An accept that fails (out of descriptors, EMFILE) leaves the listener readable: the accept loop waits this long
# before it tries again, rather than spinning while descriptors free up.
ACCEPT_BACKOFF = 0.1
CHUNK = 64 * 1024

_LABEL = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
_PHRASES = {400: "Bad Request", 403: "Forbidden", 405: "Method Not Allowed", 408: "Request Timeout",
            431: "Request Header Fields Too Large", 502: "Bad Gateway"}

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


def _literal(host: str) -> peer.IP | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


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
    def __init__(self, status: int, reason: str, message: str) -> None:
        super().__init__(message)
        self.status, self.reason, self.message = status, reason, message

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


class EgressProxy:
    """Serves ``listener`` (any listening socket; the proxy owns it from here) under ``policy``. Without a listener
    it serves only the connections passed to :meth:`handle`.

    ``resolve``, ``connect`` and ``is_local`` are seams for tests: the defaults are the host's resolver, a plain
    connect to a literal address, and the kernel's local table. Nothing a request carries reaches them."""

    def __init__(self, policy: Policy, *, listener: socket.socket | None = None, resolve: Resolver = _resolve,
                 connect: Connector = _connect, is_local: Callable[[peer.IP], bool] = peer.is_host_address,
                 header_timeout: float = HEADER_TIMEOUT, connect_timeout: float = CONNECT_TIMEOUT) -> None:
        self.listener = listener
        self.policy = policy
        self._resolve, self._connect, self._is_local = resolve, connect, is_local
        self.header_timeout, self.connect_timeout = header_timeout, connect_timeout
        # Telemetry: how many requests were tunnelled ("allowed") or refused, by reason. Never targets or payload.
        self.decisions: dict[str, int] = {}
        self._lock = threading.Lock()
        self._open: set[socket.socket] = set()
        self._handlers: set[threading.Thread] = set()
        self._closed = threading.Event()
        self._wake_r, self._wake_w = socket.socketpair()
        self._thread = threading.Thread(target=self._serve, name="aew-egress", daemon=True)

    def start(self) -> EgressProxy:
        if self.listener is None:
            raise ValueError("an egress proxy without a listener serves only handle()")
        self._thread.start()
        return self

    def __enter__(self) -> EgressProxy:
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
                                              name="aew-egress-conn", daemon=True)
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
        if not self._track(conn):
            conn.close()
            return
        upstream: socket.socket | None = None
        established = False
        try:
            host, port, early = self._read_request(conn)
            conn.settimeout(self.header_timeout)  # for the answer
            upstream = self._open_upstream(host, port)
            if not self._track(upstream):
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
            self._answer(conn, refused)
        except OSError:
            pass  # the client or the upstream went away mid-tunnel
        except Exception:  # anything else is counted, and answered with a fixed 502 unless the tunnel is open
            if established:
                self._count("proxy_error")
            else:
                self._answer(conn, _Refused(502, "proxy_error", "the egress proxy could not serve this request"))
        finally:
            if upstream is not None:
                self._untrack(upstream)
            self._untrack(conn)

    def _answer(self, conn: socket.socket, refused: _Refused) -> None:
        self._count(refused.reason)
        try:
            conn.settimeout(self.header_timeout)
            conn.sendall(refused.response())
        except OSError:
            pass

    def _read_request(self, conn: socket.socket) -> tuple[str, int, bytes]:
        """The request head, which has one deadline (``header_timeout`` from now) however its bytes are spaced."""
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
        if method != "CONNECT":
            raise _Refused(405, "method", "this egress proxy serves CONNECT only (F28 §3.4)")
        if version not in ("HTTP/1.1", "HTTP/1.0"):
            raise _Refused(400, "bad_request", f"unsupported version {version!r}")
        try:
            host, port = authority(target)
        except ValueError as exc:
            raise _Refused(400, "bad_request", f"CONNECT {target}: {exc}") from None
        return host, port, buf[end + 4:]

    def _refusal(self, value: Any) -> str | None:
        """R-6 first, whatever the policy; then the policy's own address rule."""
        ip = peer.address(value)
        return peer.host_route(ip, is_local=self._is_local) or self.policy.refuses(ip)

    def _open_upstream(self, host: str, port: int) -> socket.socket:
        target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        reason = self.policy.admits(host, port)
        if reason:
            raise _Refused(403, reason, f"CONNECT {target} refused: it is not on this run's egress allowlist "
                           "(F28 §3.4). A destination is added by the operator's execution policy, never by a run.")
        literal = _literal(host)
        try:
            answers = [literal] if literal is not None else [peer.address(a) for a in self._resolve(host, port)]
        except (OSError, ValueError, UnicodeError):
            answers = []
        if not answers:
            raise _Refused(502, "unresolved", f"CONNECT {target}: the name did not resolve")
        answers = list(dict.fromkeys(answers))
        for ip in answers:  # one refused answer refuses the target (see the module docstring)
            reason = self._refusal(ip)
            if reason:
                raise _Refused(403, reason, self._why(target, reason))
        for ip in answers:
            if self._closed.is_set():  # no new connect once close() has begun
                raise _Refused(502, "closed", f"CONNECT {target}: the egress proxy is closing")
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
                raise _Refused(403, reason, self._why(target, reason))
            return sock
        raise _Refused(502, "unreachable", f"CONNECT {target}: no address of it could be connected")

    @staticmethod
    def _why(target: str, reason: str) -> str:
        if reason == "peer_unknown":
            return (f"CONNECT {target} refused: the connected peer's address could not be confirmed, so nothing was "
                    "relayed. Retry the request.")
        if reason in peer.HOST_ROUTE_REASONS:
            return (f"CONNECT {target} refused: it reaches a {reason} address. The egress proxy runs on the host and "
                    "never connects to the host's own addresses, even allowlisted ones (R-6). Provider traffic goes "
                    "through the provider relay, not this proxy.")
        return (f"CONNECT {target} refused: it reaches a {reason} address, which is not public; this run's egress "
                "admits public addresses only.")

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
