"""The dashboard tests' one request: the answer is checked as the dashboard's before anything reads it (register E75).

CI rows got answers that were not their dashboard server's (a bare 32-hex body where JSON was due). An answer that
does not carry the dashboard's marks fails here, and the failure records who held the port while the connection was
still open: the kernel's listening and connected sockets on it with their owners, this process's socket inodes, and
its threads. One occurrence then shows whether the answer came from this process or another, and from which socket.
"""

from __future__ import annotations

import http.client
import os
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping

from aew.dashboard.server import SECURITY_HEADERS

TIMEOUT_S = 60.0  # the World clients' own
COMMAND_TIMEOUT_S = 10.0  # each command the diagnostics run
BODY_SHOWN = 256  # how much of a foreign body the failure quotes
NO_OWNER = ("An answering listener with no LISTEN row on its port, or a row without users:(...), was held by no "
            "descriptor: the kernel keeps a listener for a thread blocked in accept() after its descriptor is closed, "
            "and frees the port once that accept returns, as the probe's upstream did after one answer (register E75).")
SHARED = ("Two LISTENING rows on one port are two listeners sharing it, which Windows allows when both set "
          "SO_REUSEADDR (register E75).")


def request(port: int, method: str, path: str,
            headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    """``method path`` on the dashboard at ``127.0.0.1:port``: the status, the headers (names lower-cased) and the
    body. An answer that is not the dashboard's raises ``AssertionError`` with what held the port."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT_S)
    try:
        conn.connect()
        assert conn.sock is not None
        local = conn.sock.getsockname()[1]
        conn.request(method, path, headers=dict(headers or {}))
        resp = conn.getresponse()
        got = {k.lower(): v for k, v in resp.getheaders()}
        problem = not_the_dashboards(resp.status, got)
        if problem is not None:  # described before the body is read, while this end of the connection is open
            raise AssertionError(describe(problem, port=port, local=local, request=f"{method} {path}",
                                          status=resp.status, headers=got, read=lambda: resp.read(BODY_SHOWN)))
        return resp.status, got, resp.read()
    finally:
        conn.close()


def not_the_dashboards(status: int, headers: Mapping[str, str]) -> str | None:
    """Why an answer is not the dashboard's, or None. Every dashboard answer carries R21's headers, and every one
    with a body is JSON; a ``304`` has none (``aew.dashboard.server``)."""
    missing = [name for name, value in SECURITY_HEADERS if headers.get(name.lower()) != value]
    if missing:
        return f"it lacks the dashboard's R21 headers {missing}"
    kind = headers.get("content-type")
    if status != 304 and not (kind or "").startswith("application/json"):
        return f"its Content-Type is {kind!r}, not application/json"
    return None


def describe(problem: str, *, port: int, local: int, request: str, status: int, headers: Mapping[str, str],
             read: Callable[[], bytes]) -> str:
    """The failure's message: the mismatch first, then each diagnostic, each of which may fail on its own without
    hiding the mismatch."""
    lines = [f"the answer on 127.0.0.1:{port} to {request} is not the dashboard's: {problem}",
             f"status {status}; headers {dict(headers)}"]
    facts: list[tuple[str, Callable[[], str]]] = [("this client's local port", lambda: str(local))]
    if sys.platform == "linux":
        facts += [
            (f"listening on :{port} (ss -Htlnpe)", lambda: _run(["ss", "-Htlnpe", f"sport = :{port}"])),
            (f"every socket on :{port} or :{local} (ss -Htanpe)",
             lambda: _run(["ss", "-Htanpe", f"( sport = :{port} or dport = :{port} or sport = :{local} )"])),
            (f"this process ({os.getpid()})'s socket inodes", _own_socket_inodes),
        ]
    elif sys.platform == "win32":
        facts.append((f"every TCP socket on :{port} or :{local} (netstat -ano -p TCP)",
                      lambda: _matching(_run(["netstat", "-ano", "-p", "TCP"]), (f":{port} ", f":{local} "))))
    facts.append(("threads", lambda: "; ".join(f"{t.name} (ident {t.ident}, daemon {t.daemon})"
                                               for t in threading.enumerate())))
    # last: reading to the body's end closes this end of the connection, which the socket tables above still show
    facts.append((f"body (first {BODY_SHOWN} bytes)", lambda: repr(read())))
    for label, fact in facts:
        try:
            lines.append(f"{label}: {fact()}")
        except Exception as exc:  # noqa: BLE001 (a diagnostic that fails is reported, never raised over the mismatch)
            lines.append(f"{label}: could not be read ({type(exc).__name__}: {exc})")
    lines.append(NO_OWNER if sys.platform == "linux" else SHARED)
    return "\n".join(lines)


def _run(argv: list[str]) -> str:
    """``argv``'s output, bounded: a command that does not finish in time is killed, and says so."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_S, check=False,
                              creationflags=flags)
    except subprocess.TimeoutExpired:
        return f"(no answer in {COMMAND_TIMEOUT_S:g}s: killed)"
    return (done.stdout.strip() or "(none)") + (f" [exit {done.returncode}: {done.stderr.strip()}]"
                                                 if done.returncode else "")


def _matching(text: str, needles: tuple[str, ...]) -> str:
    return "\n".join(line for line in text.splitlines() if any(n in line for n in needles)) or "(none)"


def _own_socket_inodes() -> str:
    held = []
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        if target.startswith("socket:["):
            held.append(f"fd {fd} {target}")
    return ", ".join(held) or "(none)"
