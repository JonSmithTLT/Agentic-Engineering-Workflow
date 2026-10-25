"""The one rule for AEW's TCP servers: a port is held by exactly one listener (register E75).

On Windows, two sockets that both set ``SO_REUSEADDR`` can bind and listen on one port, and connections are then
answered by either; ``http.server`` sets it on every server (``allow_reuse_address``). A holder without it refuses
such a bind (``WSAEACCES``), and one with ``SO_EXCLUSIVEADDRUSE`` refuses every second bind. On Linux a second
listener on a held port is refused whatever either sets, and ``SO_REUSEADDR`` lets a stopped server's port be bound
again while its connections are in ``TIME_WAIT``: so it stays on there. Measured on Windows 11 with Python 3.13, a
server with this rule binds its port again at once after a stop that left five connections in ``TIME_WAIT``. Its
tests prove the ``allow_reuse_address`` half on loopback, where a holder with neither option refuses the same second
binds: the ``SO_EXCLUSIVEADDRUSE`` half is carried from STG-02 without a case that tells it apart (review of #271, m3).

Every ``socketserver`` server in ``src`` derives from :class:`ExclusiveServer`; the other listening sites are Unix
sockets, named pipes or Linux-only (``tests/unit/test_exclusive_server.py`` enumerates them).
"""

from __future__ import annotations

import socket
import sys
from http.server import ThreadingHTTPServer


class ExclusiveServer(ThreadingHTTPServer):
    """A port held by exactly one server: a second server on the same port fails to start instead of sharing it (a
    stale slice server once answered part of a new one's requests)."""

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":  # pragma: windows-only
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()
