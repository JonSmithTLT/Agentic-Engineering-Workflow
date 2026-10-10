"""Proxy settings for tests of loopback clients: a dead proxy address, and a proxy that records what reaches it.

AEW's loopback clients (the run's own OpenCode server) must never go through a proxy, whatever HTTP_PROXY,
HTTPS_PROXY or ALL_PROXY say in either case, and with no NO_PROXY exception for 127.0.0.1. Python treats an empty
``*_proxy`` value as unset, so ``proxy_env`` blanks NO_PROXY rather than removing it (subprocess environments are
built by merging into ``os.environ``).
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager

PROXY_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def proxy_env(url: str) -> dict[str, str]:
    """Every proxy variable, upper and lower case, set to ``url``, and no NO_PROXY exception."""
    env = {name: url for upper in PROXY_NAMES for name in (upper, upper.lower())}
    env.update({"NO_PROXY": "", "no_proxy": ""})
    return env


@contextmanager
def dead_proxy() -> Iterator[str]:
    """A proxy URL nothing answers: a bound port that never listens, so a connection there is refused, and nobody
    else can take the port while the test runs."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        sock.close()


class RecordingProxy:
    """A proxy on 127.0.0.1 that answers every request ``502`` and records each connection and request line."""

    def __init__(self) -> None:
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.2)
        self.url = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        self.connections = 0
        self.request_lines: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, name="recording-proxy", daemon=True)

    def __enter__(self) -> RecordingProxy:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(5)
        self._listener.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with self._lock:
                self.connections += 1
            threading.Thread(target=self._answer, args=(conn,), daemon=True).start()

    def _answer(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5)
            head = b""
            try:
                while b"\r\n\r\n" not in head and len(head) < 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    head += chunk
                with self._lock:
                    self.request_lines.append(head.split(b"\r\n", 1)[0].decode("latin-1"))
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
