"""The in-sandbox network shim (STG-05 CS-3b; F28 §3.2), run as a contained run runs it: ``python -I shim.py <spec>
-- <argv>``, as its harness's parent. Here it runs on the host's network, with loopback ports picked free, so what is
tested is the shim itself: each leg forwards both ways, a leg it cannot set up stops the harness from starting, and it
ends with its harness. The shim inside a network namespace of the run's own is the self-test's row 1
(tests/integration/test_containment.py). Linux: the legs' far ends are socket files (AF_UNIX)."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from aew.harness.containment import netns, shim

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the shim's socket files are AF_UNIX: "
                                "Linux, where contained runs have a network of their own")
TIMEOUT = 10.0

# The harness the shim starts: it serves one connection on the in-leg's port (an upper-casing echo), then calls the
# out-leg's port and prints what comes back, and exits 3.
HARNESS = textwrap.dedent("""
    import socket, sys
    serve, call = int(sys.argv[1]), int(sys.argv[2])
    with socket.create_server(("127.0.0.1", serve)) as listener:
        print("listening", flush=True)
        conn, _ = listener.accept()
        with conn:
            data = b""
            while chunk := conn.recv(4096):
                data += chunk
            conn.sendall(data.upper())
    with socket.create_connection(("127.0.0.1", call)) as out:
        out.sendall(b"ping")
        out.shutdown(socket.SHUT_WR)
        got = b""
        while chunk := out.recv(4096):
            got += chunk
    print(got.decode(), flush=True)
    sys.exit(3)
""")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def unix_listener(path: Path) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # pyright: ignore[reportAttributeAccessIssue]
    sock.bind(str(path))
    sock.listen(1)
    sock.settimeout(TIMEOUT)
    return sock


def run_shim(spec: dict, argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen(netns.shim_argv(spec, argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_each_leg_forwards_both_ways_and_passes_on_an_end_of_stream_and_the_shim_exits_with_its_harness(tmp_path):
    serve, call = free_port(), free_port()
    inside, outside = tmp_path / "server.sock", tmp_path / "relay.sock"
    spec = {"in": [{"unix": str(inside), "port": serve}], "out": [{"port": call, "unix": str(outside)}]}
    relay = unix_listener(outside)
    proc = run_shim(spec, [sys.executable, "-I", "-c", HARNESS, str(serve), str(call)])
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "listening"
        assert inside.is_socket() and (inside.stat().st_mode & 0o777) == 0o600  # only the operator's account
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:  # pyright: ignore[reportAttributeAccessIssue]
            client.settimeout(TIMEOUT)
            client.connect(str(inside))
            client.sendall(b"hello")
            client.shutdown(socket.SHUT_WR)  # the harness answers only once it has seen the end
            echoed = b""
            while chunk := client.recv(4096):
                echoed += chunk
        assert echoed == b"HELLO"
        conn, _ = relay.accept()
        with conn:
            conn.settimeout(TIMEOUT)
            got = b""
            while chunk := conn.recv(4096):
                got += chunk
            conn.sendall(b"pong")
        assert got == b"ping"
        out, _ = proc.communicate(timeout=TIMEOUT)
        assert out.strip() == "pong" and proc.returncode == 3
    finally:
        relay.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(TIMEOUT)


def test_a_leg_that_cannot_be_set_up_stops_the_harness_from_starting(tmp_path):
    marker = tmp_path / "started"
    with socket.create_server(("127.0.0.1", 0)) as taken:
        spec = {"in": [], "out": [{"port": taken.getsockname()[1], "unix": str(tmp_path / "relay.sock")}]}
        proc = run_shim(spec, [sys.executable, "-I", "-c", f"open({str(marker)!r}, 'w').close()"])
        _, err = proc.communicate(timeout=TIMEOUT)
    assert proc.returncode == shim.EXIT_SETUP and not marker.exists()
    assert "a leg could not be set up, so the harness was not started" in err


def test_a_termination_reaches_the_harness_and_the_shim_ends_with_it(tmp_path):
    ready = tmp_path / "ready"
    harness = f"import pathlib, time; pathlib.Path({str(ready)!r}).touch(); time.sleep(60)"
    proc = run_shim({"in": [], "out": []}, [sys.executable, "-I", "-c", harness])
    try:
        deadline = time.monotonic() + TIMEOUT
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "the harness never started"
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait(TIMEOUT)
        assert proc.returncode == 128 + signal.SIGTERM  # as a shell reports a child the signal ended
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(TIMEOUT)
