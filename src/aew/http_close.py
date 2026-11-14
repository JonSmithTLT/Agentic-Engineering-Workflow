"""One owner for RFC 9112 section 9.6 staged HTTP close after a response has been flushed.

Unread request bytes can turn a TCP close into a reset that discards the answer. Half-close writes, discard input
until EOF or an absolute deadline, then close. A byte cap would reintroduce that reset for large provider requests;
only a fixed-size receive buffer is needed to bound memory. A peer that exceeds the deadline can still be reset.
"""

from __future__ import annotations

import socket
import time

# The pre-existing dashboard refusal-close budget; busy accept-loop replies retain their shorter 0.1 s budget.
REFUSAL_DRAIN_S = 0.5
RECV_CHUNK = 64 * 1024


def close_after_response(sock: socket.socket, seconds: float = REFUSAL_DRAIN_S) -> None:
    """Best-effort staged close, bounded by elapsed time (not an extendible per-read idle timeout)."""
    try:
        sock.shutdown(socket.SHUT_WR)
        end = time.monotonic() + seconds
        while (wait := end - time.monotonic()) > 0:
            sock.settimeout(wait)
            if not sock.recv(RECV_CHUNK):
                break
    except OSError:  # timeout, service shutdown or a vanished peer: close still follows
        pass
    finally:
        sock.close()
