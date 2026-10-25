"""HTTP over G3's two Unix sockets (A-37, Interfaces; G3-10), on Linux.

Both sockets are filesystem sockets under the runtime directory (``/run/aew-g3/`` on a host), never abstract. Under
systemd they come from ``aew-g3.socket`` (``SocketUser=`` the operator, ``SocketMode=0600``), passed by socket
activation; elsewhere, a test's for example, the service binds them itself. The operator's UID is the sockets' own
owner, which ``SocketUser=`` sets: it is read from the socket files, never configured a second time.

Every request reads the peer's credentials with ``SO_PEERCRED`` and is refused ``PEER_NOT_PERMITTED`` unless the peer's
UID is the operator's, or when they cannot be read (G3-10, G3-11). One request per connection (HTTP/1.0).
"""

from __future__ import annotations

import json
import os
import re
import socket
import socketserver
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote

from aew.errors import ValidationFailed

from . import wire
from .service import G3Service, Reply

if sys.platform == "win32":
    raise ImportError("aew_g3.server runs on Linux only: G3's sockets are Unix filesystem sockets with SO_PEERCRED")

REQUEST_SOCK, CONFIRM_SOCK = "request.sock", "confirm.sock"
# The largest body the service reads: an O-01 set has at most 8 closed members, a few kilobytes; a megabyte is far
# beyond any valid request, and anything larger is refused STRUCTURAL before it is parsed.
MAX_BODY = 1024 * 1024
_REF = r"([A-Za-z][A-Za-z0-9:._-]{2,127})"  # the wire's Ref, without '/', which no approval_ref the service makes holds
_ROUTES: dict[str, list[tuple[str, re.Pattern[str], str]]] = {
    REQUEST_SOCK: [("POST", re.compile(r"^/g3/v1/approval-requests$"), "request"),
                   ("GET", re.compile(rf"^/g3/v1/approval-requests/{_REF}$"), "get"),
                   ("POST", re.compile(r"^/g3/v1/consume$"), "consume")],
    CONFIRM_SOCK: [("GET", re.compile(r"^/g3/v1/pending$"), "list_pending"),
                   ("POST", re.compile(rf"^/g3/v1/approvals/{_REF}$"), "decide")],
}


def peer_uid(conn: socket.socket) -> int | None:
    """The connected peer's UID by ``SO_PEERCRED``, or None when it cannot be read."""
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        return struct.unpack("3i", raw)[1]
    except (OSError, AttributeError, struct.error):
        return None


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    @property
    def _srv(self) -> _Server:
        return cast(_Server, self.server)

    def address_string(self) -> str:  # a Unix peer has no address; the default indexes an empty one
        return self._srv.kind

    def log_message(self, format: str, *args: Any) -> None:
        # The request line and the status only: a PIN travels only in a body, and no body is ever logged.
        sys.stderr.write(f"aew-g3 {self._srv.kind}: {format % args}\n")

    def _send(self, reply: Reply) -> None:
        status, body = reply
        data = b"" if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header(wire.HEADER, wire.WIRE)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _dispatch(self, method: str) -> None:
        if peer_uid(self.connection) != self._srv.operator_uid:  # re-read on every request (G3-10)
            return self._send(wire.problem("PEER_NOT_PERMITTED"))
        path = unquote(self.path.split("?", 1)[0])
        for m, pattern, route in _ROUTES[self._srv.kind]:
            match = pattern.match(path)
            if m == method and match:
                name = route
                break
        else:
            return self._send(wire.problem("NOT_FOUND"))
        svc = self._srv.service
        if method == "GET":
            return self._send(svc.get(match.group(1)) if name == "get" else svc.list_pending())
        body = self._body()
        if body is _BAD:
            return self._send(wire.problem("STRUCTURAL"))
        if name == "request":
            return self._send(svc.request(body))
        if name == "consume":
            return self._send(svc.consume(body))
        return self._send(svc.decide(match.group(1), body))

    def _body(self) -> Any:
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return _BAD
        if n < 0 or n > MAX_BODY:
            return _BAD
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return _BAD

    def do_GET(self) -> None:  # noqa: N802 - http.server's name
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - http.server's name
        self._dispatch("POST")


_BAD = object()


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, sock: socket.socket, kind: str, service: G3Service, operator_uid: int) -> None:
        super().__init__(sock.getsockname(), _Handler, bind_and_activate=False)
        self.socket.close()
        self.socket = sock
        self.kind = kind
        self.service = service
        self.operator_uid = operator_uid


def activated_sockets() -> dict[str, socket.socket]:
    """The sockets systemd passed (``LISTEN_FDS``), by file name; empty when the service was not socket-activated."""
    if os.environ.get("LISTEN_PID") != str(os.getpid()):
        return {}
    out = {}
    for fd in range(3, 3 + int(os.environ.get("LISTEN_FDS", "0"))):
        sock = socket.socket(fileno=fd)
        name = sock.getsockname()
        if sock.family != socket.AF_UNIX or not isinstance(name, str) or not name.startswith("/"):
            raise ValidationFailed(f"systemd passed descriptor {fd}, which is not a filesystem Unix socket",
                                   reason="SOCKET_NOT_FILESYSTEM")
        out[Path(name).name] = sock
    for k in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
        os.environ.pop(k, None)
    return out


def bind_sockets(runtime_dir: Path) -> dict[str, socket.socket]:
    """Binds both sockets in ``runtime_dir`` with mode 0600, owned by the account that runs the service."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in (REQUEST_SOCK, CONFIRM_SOCK):
        path = runtime_dir / name
        path.unlink(missing_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            sock.bind(str(path))
        finally:
            os.umask(old)
        sock.listen(16)
        out[name] = sock
    return out


def operator_uid_of(socks: dict[str, socket.socket]) -> int:
    """The operator's UID: the owner of both socket files (``SocketUser=``). They must agree, and root is no
    operator (G3-01: what root runs is administration, not an approval path)."""
    if set(socks) != {REQUEST_SOCK, CONFIRM_SOCK}:
        raise ValidationFailed(f"the service needs exactly {REQUEST_SOCK} and {CONFIRM_SOCK}, and has {sorted(socks)}",
                               reason="SOCKETS_MISSING", sockets=sorted(socks))
    uids = {os.stat(s.getsockname()).st_uid for s in socks.values()}
    if len(uids) != 1 or 0 in uids:
        raise ValidationFailed("the two G3 sockets must belong to one operator account that is not root (SocketUser=)",
                               reason="SOCKET_OWNER", owners=sorted(uids))
    return uids.pop()


class G3Server:
    """Both sockets' servers, each on its own thread."""

    def __init__(self, service: G3Service, socks: dict[str, socket.socket]) -> None:
        self.operator_uid = operator_uid_of(socks)
        self.servers = [_Server(socks[k], k, service, self.operator_uid) for k in (REQUEST_SOCK, CONFIRM_SOCK)]
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for s in self.servers:
            s.socket.listen(16)
            t = threading.Thread(target=s.serve_forever, name=f"aew-g3-{s.kind}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        for s in self.servers:
            s.shutdown()
            s.server_close()
        for t in self._threads:
            t.join(timeout=10)
