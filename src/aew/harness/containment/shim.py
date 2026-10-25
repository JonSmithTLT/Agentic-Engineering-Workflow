"""The secretless in-sandbox network shim (F28 §3.2, network containment design v0.2; STG-05 CS-3b).

A contained run in a network namespace of its own has only its own loopback. The shim gives it the legs its
configuration names, each between a loopback port inside and a socket file in the run's network directory, which
the layout binds in (``layout.Layout.net_dir``):

* **in:** a socket file the shim binds (in the directory's writable ``shim/``) -> ``127.0.0.1:<port>`` inside. The
  supervisor reaches the harness server this way: the server listens on the sandbox's loopback, which the host
  cannot reach (F28 §1, P3).
* **out:** ``127.0.0.1:<port>`` inside -> a socket file outside, served by the supervisor: the provider relay
  (``relay.py``) and, when the run has one, the egress proxy (``egress.py``).

It holds no credential and no authority: it moves bytes, both ways, as they come (a ``sendall`` that blocks is the
backpressure; one side's end of stream is passed on as a half-close, and the connection ends when both have ended).

It runs as the harness's parent inside the one sandbox, so the two share its network namespace: ``python -I -c
<this file's text> <spec> -- <harness argv>`` (``netns.shim_argv``). Its listeners are bound before the harness
starts, it passes its standard streams to the harness, and it exits with the harness's status. It never execs away:
the run's process tree ends both together (F28 §3.2). Standard library only, and run as the self-test's probe is,
from its text with ``-I``: what runs in the sandbox is this file, whatever an environment variable or the working
directory says. It is not an AEW entry point (``aew.process_kind``): it imports nothing of AEW and never opens the
store, so it declares nothing and has no ``__main__`` block.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
from typing import Any

LOOPBACK = "127.0.0.1"
CHUNK = 64 * 1024
BACKLOG = 64
EXIT_SETUP = 70  # EX_SOFTWARE: a leg could not be set up, so the harness was not started


def parse(argv: list[str]) -> tuple[dict[str, Any], list[str]]:
    """``(spec, harness argv)`` from ``<spec json> -- <argv...>``. Raises ``ValueError`` on anything else."""
    if len(argv) < 3 or argv[1] != "--":
        raise ValueError("usage: shim.py <spec json> -- <harness argv>")
    spec = json.loads(argv[0])
    if not isinstance(spec, dict) or not isinstance(spec.get("in", []), list) or not isinstance(spec.get("out", []),
                                                                                                    list):
        raise ValueError("the spec is {\"in\": [...], \"out\": [...]}")
    return spec, argv[2:]


def _pump(src: socket.socket, dst: socket.socket) -> None:
    """One direction until ``src`` ends; its end is passed on as a half-close of ``dst``."""
    try:
        while True:
            data = src.recv(CHUNK)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def splice(a: socket.socket, b: socket.socket) -> None:
    """Both ways, one thread per direction, then close both."""
    back = threading.Thread(target=_pump, args=(b, a), daemon=True)
    back.start()
    _pump(a, b)
    back.join()
    a.close()
    b.close()


def _serve(listener: socket.socket, connect: Any) -> None:
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        threading.Thread(target=_leg, args=(conn, connect), daemon=True).start()


def _leg(conn: socket.socket, connect: Any) -> None:
    try:
        target = connect()
    except OSError:
        conn.close()  # nothing listens there (yet): the client sees the connection end, as with a refused one
        return
    splice(conn, target)


def _to_port(port: int) -> Any:
    return lambda: socket.create_connection((LOOPBACK, port))


def _to_file(path: str) -> Any:
    def connect() -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # pyright: ignore[reportAttributeAccessIssue]
        try:
            sock.connect(path)
        except OSError:
            sock.close()
            raise
        return sock
    return connect


def listen(spec: dict[str, Any]) -> list[socket.socket]:
    """Bind every leg's listener and start serving it. Raises ``OSError`` when one cannot be bound."""
    out = []
    for leg in spec.get("in") or []:
        path = str(leg["unix"])
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # pyright: ignore[reportAttributeAccessIssue]
        sock.bind(path)
        os.chmod(path, 0o600)
        sock.listen(BACKLOG)
        out.append(sock)
        threading.Thread(target=_serve, args=(sock, _to_port(int(leg["port"]))), daemon=True).start()
    for leg in spec.get("out") or []:
        sock = socket.create_server((LOOPBACK, int(leg["port"])), backlog=BACKLOG)
        out.append(sock)
        threading.Thread(target=_serve, args=(sock, _to_file(str(leg["unix"]))), daemon=True).start()
    return out


def main(argv: list[str]) -> int:
    try:
        spec, child = parse(argv)
        listen(spec)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f"aew network shim: a leg could not be set up, so the harness was not started: {exc}\n")
        return EXIT_SETUP
    proc = subprocess.Popen(child)  # noqa: S603  # the harness argv the supervisor's adapter gave
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):  # pyright: ignore[reportAttributeAccessIssue]
        signal.signal(sig, lambda s, _f: proc.send_signal(s))
    code = proc.wait()
    return 128 - code if code < 0 else code
