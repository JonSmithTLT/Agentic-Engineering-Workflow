"""The in-sandbox network shim (STG-05 CS-3b; F28 §3.2), run as a contained run runs it: ``python -I shim.py <spec>
-- <argv>``, as its harness's parent. Here it runs on the host's network, with loopback ports picked free, so what is
tested is the shim itself: each leg forwards both ways, a leg it cannot set up stops the harness from starting, it
ends with its harness, and for the Lead (STG-05 CS-4) its ``ctty`` step makes the relay's pseudo-terminal the harness's
controlling terminal or starts nothing. The shim inside a network namespace of the run's own is the self-test's row 1
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


def wait_for(path: Path, text: str) -> str:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        got = path.read_text() if path.exists() else ""
        if text in got:
            return got
        time.sleep(0.05)
    raise AssertionError(f"{text!r} never appeared in {path.name}: {got!r}")


# The Lead's TUI as the ``ctty`` step leaves it: it records its controlling terminal (``/proc/self/stat`` field 7),
# whether /dev/tty opens, whether it is in the terminal's foreground group, and each SIGINT it gets.
TERMINAL_HARNESS = textwrap.dedent("""
    import os, signal, sys, time
    log = open(sys.argv[1], "a", buffering=1)
    signal.signal(signal.SIGINT, lambda _s, _f: log.write("sigint\\n"))
    with open("/proc/self/stat", "rb") as f:
        nr = int(f.read().rsplit(b")", 1)[1].split()[4])
    os.close(os.open("/dev/tty", os.O_RDWR))
    log.write(f"tty_nr {nr} foreground {os.tcgetpgrp(0) == os.getpgrp()}\\n")
    time.sleep(60)
""")


def test_the_ctty_step_makes_standard_input_the_harnesss_controlling_terminal_and_a_ctrl_c_reaches_it_once(tmp_path):
    """STG-05 CS-4, ruling R-7: on the relay's pseudo-terminal the shim makes it the controlling terminal, so the TUI
    it starts has that terminal (and /dev/tty) and is in its foreground group. A Ctrl-C there reaches the TUI once,
    from the terminal: the shim does not forward it as well, and a SIGINT sent to the shim alone neither ends the shim
    nor reaches the TUI. A termination still does, and the shim ends with it."""
    import pty

    master, slave = pty.openpty()
    log = tmp_path / "log"
    rdev = os.fstat(slave).st_rdev
    major, minor = os.major(rdev), os.minor(rdev)
    try:
        proc = subprocess.Popen(netns.shim_argv({"in": [], "out": [], "ctty": True},
                                                [sys.executable, "-I", "-c", TERMINAL_HARNESS, str(log)]),
                                stdin=slave, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    finally:
        os.close(slave)
    try:
        got = wait_for(log, "foreground")
        assert f"tty_nr {(minor & 0xFF) | (major << 8) | ((minor & ~0xFF) << 12)} foreground True" in got
        os.write(master, b"\x03")  # the line discipline's Ctrl-C: SIGINT to the terminal's foreground group
        wait_for(log, "sigint")
        os.kill(proc.pid, signal.SIGINT)
        time.sleep(0.5)
        assert proc.poll() is None and log.read_text().count("sigint") == 1
        os.kill(proc.pid, signal.SIGTERM)
        proc.wait(TIMEOUT)
        assert proc.returncode == 128 + signal.SIGTERM
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()
            proc.wait(TIMEOUT)


def test_a_ctty_step_that_cannot_take_the_terminal_stops_the_harness_from_starting(tmp_path):
    """Standard input that is not a terminal: the step fails, and the shim starts nothing rather than run the TUI with
    no controlling terminal (row 4's Lead form refuses such a launch before it, on the probe)."""
    marker = tmp_path / "started"
    proc = subprocess.Popen(netns.shim_argv({"in": [], "out": [], "ctty": True},
                                            [sys.executable, "-I", "-c", f"open({str(marker)!r}, 'w').close()"]),
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _, err = proc.communicate(timeout=TIMEOUT)
    assert proc.returncode == shim.EXIT_SETUP and not marker.exists()
    assert "standard input could not be made the controlling terminal, so the harness was not started" in err


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
