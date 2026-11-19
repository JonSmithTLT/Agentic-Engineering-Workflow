"""The dashboard tests' request helper (tests/helpers/dashboard_client.py; register E75): an answer that is not the
dashboard's fails with what held the port, and the diagnostics never hide the mismatch. Served by planted listeners:
the dashboard's real answers pass through it in every dashboard API test."""

from __future__ import annotations

import contextlib
import os
import re
import socket
import sys
import threading
from collections.abc import Iterator
from typing import NamedTuple

import dashboard_client as D
import process_dumpable
import pytest

from aew.dashboard.server import SECURITY_HEADERS

R21 = "".join(f"{name}: {value}\r\n" for name, value in SECURITY_HEADERS)
JSON_OK = ("HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: 11\r\n" + R21
           + "Connection: close\r\n\r\n").encode() + b'{"ok":true}'
# What the probe's leaked upstream answered on CI: 200, text/plain, and a 32-hex token
TOKEN = ("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 32\r\nConnection: close\r\n\r\n"
         + "0123456789abcdef" * 2).encode()


class Planted(NamedTuple):
    port: int
    inode: int  # the listening socket's: the one fact that names it in `ss`, whoever can or can't be named as owner


@contextlib.contextmanager
def answering(response: bytes) -> Iterator[Planted]:
    """A loopback listener that answers every request with ``response``, then closes: its port and socket inode."""
    listener = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(5)
                with contextlib.suppress(OSError):
                    buf = b""
                    while b"\r\n\r\n" not in buf and (data := conn.recv(4096)):
                        buf += data
                    conn.sendall(response)
                    conn.shutdown(socket.SHUT_WR)
                    conn.recv(1)  # until the client is done with it: the diagnostics run while it is open

    thread = threading.Thread(target=serve, name="flake-planted-listener", daemon=True)
    thread.start()
    try:
        inode = os.fstat(listener.fileno()).st_ino if sys.platform == "linux" else 0  # Windows: no socket inode
        yield Planted(listener.getsockname()[1], inode)
    finally:
        stop.set()
        with contextlib.suppress(OSError):
            listener.shutdown(socket.SHUT_RDWR)  # wakes the accept, on Linux
        listener.close()
        thread.join(5)


@pytest.mark.parametrize("response", [
    JSON_OK,
    ("HTTP/1.1 304 Not Modified\r\nETag: \"e\"\r\n" + R21 + "\r\n").encode(),  # a 304 has no body and no type
], ids=["json", "not_modified"])
def test_the_dashboards_answer_passes_as_it_came(response):
    with answering(response) as (port, _):
        status, headers, body = D.request(port, "GET", "/api/v1/runs")
    assert status in (200, 304) and headers["x-frame-options"] == "DENY"
    assert body == (b'{"ok":true}' if status == 200 else b"")


def test_the_probes_token_fails_naming_its_mismatch_and_what_held_the_port():
    with answering(TOKEN) as (port, inode), pytest.raises(AssertionError) as exc:
        D.request(port, "HEAD", "/api/v1/maps")
    text = str(exc.value)
    first = text.splitlines()[0]
    assert first.startswith(f"the answer on 127.0.0.1:{port} to HEAD /api/v1/maps is not the dashboard's")
    assert "lacks the dashboard's R21 headers" in first
    assert "this client's local port: " in text and "flake-planted-listener" in text
    if sys.platform == "linux":  # the planted listener is this process's: ss names its socket, with this pid
        _assert_linux_listener(text, port, inode, os.getpid())
        local = next(line for line in text.splitlines() if line.startswith("this client's local port: ")).split()[-1]
        # recorded while this end of the connection was open: the client's own socket, with this pid
        assert any(f"127.0.0.1:{local} " in line and f"pid={os.getpid()}," in line for line in text.splitlines()), text
        assert "socket inodes: fd " in text and D.NO_OWNER in text
    elif sys.platform == "win32":  # netstat's rows for the port: the listening one with this pid, or saying it has none
        row = any(f"127.0.0.1:{port} " in line and "LISTENING" in line and line.split()[-1] == str(os.getpid())
                  for line in text.splitlines())
        assert row != (D.NO_LISTENING_ROW in text), text  # never both: always saying so would pass an `or`
        assert D.SHARED in text


def _assert_linux_listener(text: str, port: int, inode: int, pid: int | None) -> None:
    """The planted listener's row in the listening table, found by its socket inode, and with ``pid`` as its owner
    unless that is None (a process that is not dumpable, whose sockets ss names no owner for)."""
    listening = text.split(f"listening on :{port} (ss -Htlnpe): ", 1)[1].split("\nevery socket on :", 1)[0]
    rows = [row for row in listening.splitlines()
            if re.search(rf"\bLISTEN\b.*:{port}\s", row) and re.search(rf"\bino:{inode}\b", row)]
    assert rows, listening
    assert pid is None or any(f"pid={pid}," in row for row in rows), listening
    assert f"socket:[{inode}]" in text  # and it is among this process's own socket inodes


def test_the_listener_check_takes_the_planted_sockets_row_by_its_inode():
    other = "LISTEN 0 128 127.0.0.1:43537 0.0.0.0:* uid:1001 ino:426567 sk:1"
    own = 'LISTEN 0 128 127.0.0.1:43537 0.0.0.0:* users:(("python",pid=2489,fd=4)) uid:1001 ino:426999 sk:2'
    heading = "listening on :43537 (ss -Htlnpe): "
    rest = ("\nevery socket on :43537 or :43538 (ss -Htanpe): "
            "\nthis process (2489)'s socket inodes: fd 4 socket:[426999]")
    _assert_linux_listener(f"{heading}{other}\n{own}{rest}", 43537, 426999, 2489)
    with pytest.raises(AssertionError, match="ino:426567"):  # another socket's row, however it is owned, is not it
        _assert_linux_listener(f"{heading}{other}{rest}", 43537, 426999, None)
    ownerless = own.replace('users:(("python",pid=2489,fd=4)) ', "")
    _assert_linux_listener(f"{heading}{ownerless}{rest}", 43537, 426999, None)
    with pytest.raises(AssertionError):  # with a pid to match, an ownerless row is not enough
        _assert_linux_listener(f"{heading}{ownerless}{rest}", 43537, 426999, 2489)


def test_a_non_dumpable_test_process_still_has_its_planted_listener_named_by_its_socket():
    """A process that is not dumpable (AEW's own hardening) gets no owner from ss for its sockets: the diagnostics say
    so, and the planted listener is still found exactly, by its socket inode, never as some other row."""
    if process_dumpable.dumpable() is None:  # no such flag here: nothing to hide an owner
        assert sys.platform != "linux"
        return
    process_dumpable.set_dumpable(False)
    try:
        with answering(TOKEN) as (port, inode), pytest.raises(AssertionError) as exc:
            D.request(port, "HEAD", "/api/v1/maps")
    finally:
        process_dumpable.set_dumpable(True)
    text = str(exc.value)
    _assert_linux_listener(text, port, inode, None)
    assert D.NOT_DUMPABLE in text and D.NO_OWNER not in text


LISTENER = "  TCP    127.0.0.1:5000         0.0.0.0:0              LISTENING       41"
CLIENT = "  TCP    127.0.0.1:6000         127.0.0.1:5000         ESTABLISHED     41"
OTHER_LISTENER = "  TCP    127.0.0.1:6000         0.0.0.0:0              LISTENING       7"


@pytest.mark.parametrize(("table", "shown", "says_so"), [
    (f"{LISTENER}\n{CLIENT}", [LISTENER, CLIENT], False),
    (CLIENT, [CLIENT], True),
    (f"{OTHER_LISTENER}\n{CLIENT}", [OTHER_LISTENER, CLIENT], True),
    ("", ["(none)"], True),
    ("(no answer in 10s: killed)", ["(no answer in 10s: killed)"], False),
    ("(none) [exit 1: denied]", ["(none) [exit 1: denied]"], False),
], ids=["a_listener", "only_a_connection", "a_listener_on_the_other_port", "no_rows", "netstat_never_answered",
        "netstat_failed"])
def test_netstats_rows_say_when_they_hold_no_listener_on_the_port(table, shown, says_so):
    """Some Windows hosts leave listeners out of the TCP table: on build 26300 a plain listener has no row in netstat
    or Get-NetTCPConnection, and the LISTENING rows there are mostly sockets with a foreign address and port 0. The
    failure then says so, rather than reading as a port nothing held. A row on another port doesn't count. A table
    that never came says only that: it has no rows to be missing."""
    lines = D._netstat_rows(table, 5000, 6000).splitlines()
    assert lines[:len(shown)] == shown
    assert (D.NO_LISTENING_ROW in lines) is says_so


@pytest.mark.parametrize(("response", "says"), [
    (JSON_OK.replace(b"application/json", b"text/html"), "its Content-Type is 'text/html; charset=utf-8'"),
    (JSON_OK.replace(b"Content-Type: application/json; charset=utf-8\r\n", b""), "its Content-Type is None"),
    (b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}", "lacks the dashboard's R21 headers"),
    (JSON_OK.replace(b"X-Frame-Options: DENY\r\n", b""), "lacks the dashboard's R21 headers ['X-Frame-Options']"),
], ids=["wrong_type", "no_type", "nothing_of_the_dashboards", "one_header_missing"])
def test_an_answer_without_the_dashboards_marks_fails(response, says):
    with answering(response) as (port, _), pytest.raises(AssertionError, match="is not the dashboard's") as exc:
        D.request(port, "GET", "/api/v1/runs")
    assert says in str(exc.value).splitlines()[0]


def test_a_diagnostic_that_fails_is_reported_and_never_hides_the_mismatch(monkeypatch):
    def broken(argv):
        raise OSError("no such command")

    monkeypatch.setattr(D, "_run", broken)
    monkeypatch.setattr(D, "_own_socket_inodes", lambda: 1 / 0)
    with answering(TOKEN) as (port, _), pytest.raises(AssertionError) as exc:
        D.request(port, "GET", "/api/v1/runs")
    lines = str(exc.value).splitlines()
    assert "is not the dashboard's" in lines[0]
    if sys.platform in ("linux", "win32"):
        assert any("could not be read (OSError: no such command)" in line for line in lines), lines


def test_a_command_that_does_not_finish_is_killed_at_its_bound(monkeypatch):
    monkeypatch.setattr(D, "COMMAND_TIMEOUT_S", 0.5)
    assert D._run([sys.executable, "-c", "import time; time.sleep(30)"]) == "(no answer in 0.5s: killed)"
    assert D._run([sys.executable, "-c", "print('held')"]) == "held"
