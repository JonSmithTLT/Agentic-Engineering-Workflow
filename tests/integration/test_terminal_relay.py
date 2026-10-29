"""The contained Lead's terminal relay (STG-05 CS-4, outcome 4): ``procs.run_session_tree(..., relay=True)``.

A stand-in broker takes a pseudo-terminal as the operator's terminal (its controlling terminal, as a shell's job has)
and runs the session tree with the relay. The stand-in TUI runs on the reaper's pseudo-terminal: it takes it as its
controlling terminal, as the shim's ``ctty`` step does, sets it raw and half-draws a frame, as the TUI does, and logs
what it sees. The relay inside the real sandbox, with TIOCSTI, is in tests/integration/test_lead_containment.py.
Linux: the relay is the contained Lead's."""

from __future__ import annotations

import json
import os
import select
import signal
import struct
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from aew.harness import procs

if sys.platform != "win32":  # the relay is Linux's: these modules do not exist on Windows
    import fcntl
    import pty
    import termios

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the terminal relay is the contained "
                                "Lead's: Linux (the Windows Lead runs labelled not contained)")
TIMEOUT = 10.0
SRC = str(Path(procs.__file__).resolve().parents[2])

BROKER = textwrap.dedent("""
    import fcntl, json, os, sys, termios
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    from aew.harness import procs
    code, ownership = procs.run_session_tree(json.loads(sys.argv[1]), env=dict(os.environ), cwd=os.getcwd(),
                                             relay=True)
    with open(sys.argv[2], "w") as f:
        json.dump([code, ownership], f)
""")

TUI = textwrap.dedent("""
    import fcntl, os, signal, struct, sys, termios, time, tty
    log = open(sys.argv[1], "a", buffering=1)
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    tty.setraw(0)
    def size(*_):
        rows, cols = struct.unpack("HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, bytes(8)))[:2]
        log.write(f"size {rows}x{cols}\\n")
    signal.signal(signal.SIGWINCH, size)
    size()
    os.write(1, b"\\x1b[?1049h\\x1b[?1000h\\x1b[?2004h\\x1b[?2026hFRAME")   # a frame begun and never ended
    log.write(f"ready {os.getpid()} {os.getppid()}\\n")
    while True:
        data = os.read(0, 4096)
        if data == b"q":   # more than the operator's pseudo-terminal holds (about 18 KiB on the Rocky VM), so
            last = b"x" * 25000   # the relay is stuck writing to it when "END" comes, and less than both hold
            while last:
                last = last[os.write(1, last):]
            time.sleep(0.2)
            os.write(1, b"END")
            sys.exit(0)
        if data == b"!":
            os.abort()
        log.write(f"in {data.hex()}\\n")
        os.write(1, data)
""")


class Session:
    """The operator's terminal (a pseudo-terminal whose master the test holds), the broker on it, and the TUI."""

    def __init__(self, scratch: Path) -> None:
        self.master, self.slave = pty.openpty()
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        self.original = termios.tcgetattr(self.slave)
        self.log, self.result = scratch / "tui.log", scratch / "result.json"
        self.out = bytearray()
        self._stop = threading.Event()
        self.paused = threading.Event()  # the operator's terminal reads nothing: what is written to it waits
        argv = [sys.executable, "-I", "-c", TUI, str(self.log)]
        self.broker = subprocess.Popen([sys.executable, "-c", BROKER, json.dumps(argv), str(self.result)],
                                       stdin=self.slave, stdout=self.slave, stderr=self.slave, cwd=scratch,
                                       env={**os.environ, "PYTHONPATH": SRC, "PYTHONDONTWRITEBYTECODE": "1"})
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self.tui = self.reaper = None
        try:
            ready = self.wait_for("ready").split("ready ", 1)[1].split()
        except BaseException:
            self.close()
            raise
        self.tui, self.reaper = int(ready[0]), int(ready[1])

    def _read(self) -> None:
        while not self._stop.is_set():
            if self.paused.is_set():
                time.sleep(0.01)
            elif select.select([self.master], [], [], 0.05)[0]:
                try:
                    self.out += os.read(self.master, 65536)
                except OSError:
                    return

    def wait_for(self, text: str) -> str:
        deadline = time.monotonic() + TIMEOUT
        got = ""
        while time.monotonic() < deadline:
            got = self.log.read_text() if self.log.exists() else ""
            if text in got:
                return got
            time.sleep(0.02)
        raise AssertionError(f"{text!r} never reached the TUI's log: {got!r}; the terminal showed {bytes(self.out)!r}")

    def type(self, data: bytes) -> None:
        os.write(self.master, data)

    def given_back(self) -> bool:
        """The terminal's settings are the ones it had, and the last bytes on it are the relay's reset."""
        return termios.tcgetattr(self.slave) == self.original and bytes(self.out).endswith(procs.TERMINAL_LEAVE)

    def quiet(self) -> bool:
        """Nothing more reached the terminal for a fifth of a second (whatever ended has said all it will)."""
        seen = len(self.out)
        time.sleep(0.2)
        return len(self.out) == seen

    def close(self) -> None:
        for pid in (self.tui, self.reaper):
            if pid is not None and procs.pid_alive(pid):
                procs.kill_pid(pid)
        if self.broker.poll() is None:
            self.broker.kill()
        self.broker.wait(TIMEOUT)
        self._stop.set()
        self._reader.join(TIMEOUT)
        os.close(self.master)
        os.close(self.slave)


@pytest.fixture
def session(tmp_path) -> Iterator[Session]:
    s = Session(tmp_path)
    try:
        yield s
    finally:
        s.close()


def eventually(check: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return check()


def exits_with_its_last_output_unread(s: Session) -> None:
    """The TUI exits while its last output still waits in the relay: the operator's terminal reads nothing until the
    reaper has the TUI's exit."""
    s.paused.set()
    s.type(b"q")
    assert eventually(lambda: not procs.pid_alive(s.tui))
    time.sleep(0.1)
    s.paused.clear()


ENDINGS: dict[str, Callable[[Session], None]] = {
    "the_tui_exits": exits_with_its_last_output_unread,
    "the_tui_crashes": lambda s: s.type(b"!"),
    "the_sandbox_is_killed": lambda s: os.kill(s.tui, signal.SIGKILL),
    "the_broker_is_killed": lambda s: s.broker.kill(),
    "the_reaper_is_killed": lambda s: os.kill(s.reaper, signal.SIGKILL),
    "the_terminal_hangs_up": lambda s: os.killpg(s.broker.pid, signal.SIGHUP),
}


@pytest.mark.parametrize("ending", list(ENDINGS))
def test_the_operators_terminal_is_restored_on_every_ending(session, ending):
    """Outcome 4: whatever ends the session, the operator's terminal gets back its settings (it was raw) and the
    reset of every mode the TUI sets, last, even after a frame begun and never ended; when the TUI exits, all it
    wrote comes first, and nothing (a traceback) comes after. The reaper gives it back, and the broker does when the
    reaper is killed. The TUI's processes end with the session, except when the reaper is killed: then the broker
    reports survivors (the real sandbox dies with the reaper, `--die-with-parent`)."""
    s = session
    assert termios.tcgetattr(s.slave) != s.original  # raw while the TUI runs
    ENDINGS[ending](s)
    assert eventually(s.given_back), (termios.tcgetattr(s.slave) == s.original, bytes(s.out)[-200:])
    if ending != "the_broker_is_killed":
        s.broker.wait(TIMEOUT)
    if ending == "the_reaper_is_killed":
        assert json.loads(s.result.read_text())[1] == "survivors"
    else:
        assert eventually(lambda: not procs.pid_alive(s.tui) and not procs.pid_alive(s.reaper))
    assert eventually(s.quiet) and s.given_back() and b"Traceback" not in s.out, bytes(s.out)[-500:]
    if ending == "the_tui_exits":  # drained before the reset: nothing the TUI wrote is lost
        assert bytes(s.out).endswith(b"x" * 1000 + b"END" + procs.TERMINAL_LEAVE)
    if ending in ("the_tui_exits", "the_tui_crashes", "the_sandbox_is_killed"):
        code, ownership = json.loads(s.result.read_text())
        assert ownership == "clean" and code == {"the_tui_exits": 0, "the_tui_crashes": 128 + signal.SIGABRT,
                                                 "the_sandbox_is_killed": 128 + signal.SIGKILL}[ending]


def test_the_relay_passes_bytes_unfiltered(session):
    """Outcome 4: what the operator's terminal sends reaches the TUI as it was sent, and what the TUI writes reaches
    the terminal as it was written: OSC 52 (the clipboard), bracketed paste, SGR mouse reports and UTF-8."""
    s = session
    sequences = [b"\x1b]52;c;aGVsbG8=\x07", b"\x1b[200~pasted\ttext\r\n\x1b[201~", b"\x1b[<0;10;5M\x1b[<0;10;5m",
                 "é漢".encode(), b"\x03\x1a\x1c"]  # the last: Ctrl-C, Ctrl-Z and Ctrl-\ as bytes (raw mode)
    for seq in sequences:
        s.type(seq)
        got = s.wait_for(seq.hex()[-8:])
        assert seq.hex() in "".join(line[3:] for line in got.splitlines() if line.startswith("in ")), got
        assert eventually(lambda seq=seq: seq in bytes(s.out)), bytes(s.out)[-200:]
    assert procs.pid_alive(s.tui)  # Ctrl-C reached it as a byte, not as a signal


def test_the_window_size_follows_the_operators_terminal(session):
    s = session
    s.wait_for("size 24x80")
    fcntl.ioctl(s.master, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 132, 0, 0))
    s.wait_for("size 50x132")


def test_the_relay_refuses_a_session_without_a_terminal_and_starts_nothing(tmp_path):
    marker = tmp_path / "started"
    script = textwrap.dedent("""
        import os, sys
        from aew.harness import procs
        harness = [sys.executable, "-c", "import sys; open(sys.argv[1], 'w').close()", sys.argv[1]]
        procs.run_session_tree(harness, env=dict(os.environ), cwd=os.getcwd(), relay=True)
    """)
    done = subprocess.run([sys.executable, "-c", script, str(marker)], stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, cwd=tmp_path, env={**os.environ, "PYTHONPATH": SRC}, timeout=TIMEOUT)
    assert done.returncode != 0 and "the terminal relay needs a terminal on standard input" in done.stderr
    assert not marker.exists()
