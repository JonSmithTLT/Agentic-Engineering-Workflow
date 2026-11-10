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

For the Lead's TUI (STG-05 CS-4) its spec also says ``ctty``: standard input is the terminal relay's pseudo-terminal,
and the shim makes it its controlling terminal before it starts the TUI (:func:`take_terminal`). A Lead on the host's
network runs under the shim too, with no legs, for that step alone.

It also says ``serve``: the Lead's OpenCode server, which AEW starts so the Lead broker can reach the session (the
steering design's ruling of 2026-11-08). The shim starts it with its own environment, reads the address it announces,
records that in ``url_file`` and gives it to the TUI in place of :data:`SERVER_URL`; it holds the server's lease on its
stdin, so the server ends with the shim. The environment holds the server's password, which the TUI connects with and
which the server removes from its own (``--stdio``, what keeps it out of the environment the Lead's shell inherits); the
shim never reads it.

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
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any

LOOPBACK = "127.0.0.1"
LOOPBACK_URL = re.compile(rf"http://{re.escape(LOOPBACK)}:[0-9]{{1,5}}/?")  # the only address a password goes to
CHUNK = 64 * 1024
BACKLOG = 64
EXIT_SETUP = 70  # EX_SOFTWARE: a leg could not be set up, so the harness was not started
EXIT_SERVER_LOST = 69  # EX_UNAVAILABLE: the Lead's server died, so the session ended; `aew opencode`'s result says so
EXIT_INTERRUPTED = 130  # Ctrl+C before the harness started
SERVER_URL = "{aew_server_url}"  # in the harness argv: the address ``serve``'s server announced
SERVE_TIMEOUT_S = 60.0           # the server's announcement, as the worker adapter's start allows
SERVE_END_S = 5.0                # the lease ended: the server's moment to exit on its own
SERVE_NOTICE_S = 5.0             # a blank screen for this long gets a line (about 2 s to announce, measured 2026-11-08)
SERVE_SLICE_S = 0.2              # a Windows wait can't be interrupted: Ctrl+C is seen between slices


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


def take_terminal() -> None:
    """The ``ctty`` step (STG-05 CS-4, ruling R-7): make standard input, the relay's pseudo-terminal, this process's
    controlling terminal, in a session of its own, so the harness it starts inherits it. Under bubblewrap's
    ``--new-session`` the sandbox starts with none, and this process does not lead that session, so ``setsid`` succeeds.
    Then a ``TIOCSTI`` from inside reaches only that terminal's own input. Checked on this process itself: its
    controlling terminal (``/proc/self/stat`` field 7) must be standard input's device. Raises ``OSError`` otherwise."""
    if sys.platform == "win32":
        raise OSError("a controlling terminal is POSIX's")
    import fcntl
    import termios

    try:
        os.setsid()
    except OSError:
        pass  # already a session's leader (outside bubblewrap): TIOCSCTTY below decides
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    rdev = os.fstat(0).st_rdev
    with open("/proc/self/stat", "rb") as f:
        nr = int(f.read().rsplit(b")", 1)[1].split()[4])
    major, minor = os.major(rdev), os.minor(rdev)
    if nr != (minor & 0xFF) | (major << 8) | ((minor & ~0xFF) << 12):
        raise OSError(f"the controlling terminal ({nr}) is not standard input's ({major},{minor})")


def start_server(serve: dict[str, Any]) -> tuple[subprocess.Popen[bytes], str]:
    """Start ``serve``'s server and read the address it announces. Raises ``OSError`` when it announces none: it exited,
    or said nothing in time, or named anything but this machine's loopback, where its password would go."""
    with open(str(serve["log"]), "ab") as log:
        proc = subprocess.Popen([str(a) for a in serve["argv"]],  # noqa: S603  # the argv AEW's Lead gave
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
    found: list[str] = []
    announced = threading.Event()

    def read() -> None:
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):  # keeps draining afterwards, so the pipe never blocks the server
            if not found:
                try:
                    found.append(str(json.loads(raw.decode("utf-8", "replace"))["url"]))
                    announced.set()
                except (ValueError, KeyError, TypeError):
                    continue
        announced.set()

    threading.Thread(target=read, daemon=True).start()
    try:
        _wait_for(announced)
    except KeyboardInterrupt:
        proc.kill()
        raise
    if not found or not LOOPBACK_URL.fullmatch(found[0]):
        proc.kill()
        raise OSError(f"the Lead's server announced {found[0][:80] if found else 'no address'}, not a "
                      f"http://{LOOPBACK} address. Run `aew doctor`, and read the server's log: {serve['log']}")
    temporary = f"{serve['url_file']}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as out:
        json.dump({"url": found[0]}, out)
    os.replace(temporary, str(serve["url_file"]))
    return proc, found[0]


def _wait_for(announced: threading.Event) -> None:
    """Until the server has announced, or its time is up, saying so once if the wait is long."""
    deadline = time.monotonic() + SERVE_TIMEOUT_S
    notice = time.monotonic() + SERVE_NOTICE_S
    while not announced.wait(SERVE_SLICE_S) and time.monotonic() < deadline:
        if notice is not None and time.monotonic() >= notice:
            notice = None
            sys.stderr.write(f"aew network shim: waiting for the Lead's server, for up to {SERVE_TIMEOUT_S:g} s\n")
            sys.stderr.flush()


def end_server(proc: subprocess.Popen[bytes]) -> None:
    """End the lease (stdin EOF), and give the server a moment to exit on its own."""
    try:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait(SERVE_END_S)
    except (OSError, subprocess.TimeoutExpired):
        proc.kill()


def terminal_signals_reach_it(spec: dict[str, Any]) -> bool:
    """Whether the terminal's own signals reach the harness without this process: on a terminal of its own, or on a
    Windows console (:func:`pass_signals`)."""
    return bool(spec.get("ctty")) or sys.platform == "win32"


def pass_signals(proc: subprocess.Popen[bytes], *, on_its_terminal: bool) -> None:
    """Pass what this process is sent on to the harness. On a terminal of its own the harness is in this process's
    foreground group, so the terminal's own signals reach it directly: forwarding them as well would double them. So
    does a Windows console's Ctrl+C reach every process on it, and ``Popen.send_signal`` can't carry one there: it
    raises, which would end this process with the harness still running. Ignored by a handler, not SIG_IGN, which the
    harness would inherit. Windows has no SIGHUP or SIGQUIT: the shim runs there for ``serve`` alone."""
    for name in ("SIGTERM", "SIGHUP") if on_its_terminal else ("SIGTERM", "SIGINT", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda s, _f: proc.send_signal(s))
    if on_its_terminal:
        for name in ("SIGINT", "SIGQUIT"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), lambda _s, _f: None)


def watch_server(server: subprocess.Popen[bytes], proc: subprocess.Popen[bytes]) -> threading.Event:
    """End the harness if its server dies: nothing restarts the server, and the TUI would go on reconnecting. The event
    says that happened, and :func:`end_server` ending the lease after the harness doesn't count."""
    lost = threading.Event()

    def watch() -> None:
        server.wait()
        if proc.poll() is None:
            lost.set()
            proc.terminate()

    threading.Thread(target=watch, daemon=True).start()
    return lost


def main(argv: list[str]) -> int:
    try:
        spec, child = parse(argv)
        listen(spec)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.write(f"aew network shim: a leg could not be set up, so the harness was not started: {exc}\n")
        return EXIT_SETUP
    if spec.get("ctty"):
        try:
            take_terminal()
        except OSError as exc:
            sys.stderr.write("aew network shim: standard input could not be made the controlling terminal, so the "
                             f"harness was not started: {exc}\n")
            return EXIT_SETUP
    server = None
    if spec.get("serve"):
        try:
            server, url = start_server(spec["serve"])
        except KeyboardInterrupt:
            return EXIT_INTERRUPTED
        except (OSError, KeyError, TypeError) as exc:
            sys.stderr.write(f"aew network shim: the Lead's server did not start, so the harness was not started: "
                             f"{exc}\n")
            return EXIT_SETUP
        child = [url if a == SERVER_URL else a for a in child]
    proc = subprocess.Popen(child)  # noqa: S603  # the harness argv the supervisor's adapter gave
    pass_signals(proc, on_its_terminal=terminal_signals_reach_it(spec))
    lost = None if server is None else watch_server(server, proc)
    code = proc.wait()
    if server is not None:
        end_server(server)
    if lost is not None and lost.is_set():  # after the harness: a TUI's screen would hide it
        sys.stderr.write("aew network shim: the Lead's server ended, and nothing restarts it, so the session ended. "
                         f"The result that follows says how to go on; the server's log is {spec['serve']['log']}\n")
        return EXIT_SERVER_LOST
    return 128 - code if code < 0 else code
