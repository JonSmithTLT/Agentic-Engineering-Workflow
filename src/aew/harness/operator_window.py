"""The console of an operator endpoint with no terminal (`aew opencode` started it): a window, shown when a challenge
needs one and gone when the challenge has ended. The operator allowed this on 2026-10-11, "aew CAN open terminals
intentionally if needed just keep it reasonable not in testing".

The code stays where it was: in the endpoint's own memory, and on no command line and in no file.

- **Windows:** the endpoint has a hidden console of its own (:mod:`aew.harness.operator_autostart`), which is shown.
- **Linux:** a pseudo-terminal the endpoint holds, shown by a terminal emulator running ``cat`` on it. Closing it ends
  the ``cat``, and so the window. Reading a terminal device as the operator's uid is already one of
  ``operator_client.RESIDUALS``.

With no display (an SSH session) or no terminal emulator, no window can open: the request's reply says to run
`aew operator serve --dev`, and the endpoint gives up its lock so that can start (``on_unavailable``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from typing import Any

from aew import errors

LINGER_S = 8.0  # how long the window stays once the challenge has ended, for its result line to be read
# Each emulator with the flag that gives it a command; the first one on PATH is used
TERMINALS = (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"), ("xfce4-terminal", "-x"),
             ("xterm", "-e"))
NO_WINDOW = ("this operator endpoint runs in the background and cannot open a window for its code here ({why}), so it "
             "has stopped. Run `aew operator serve --dev` in another terminal, and ask again")


def terminal_command(device: str, env: Mapping[str, str] | None = None,
                     which: Callable[[str], str | None] = shutil.which) -> list[str] | str:
    """The command that shows ``device`` in a window, or why there is none."""
    env = os.environ if env is None else env
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return "no display"
    for name, flag in TERMINALS:
        path = which(name)
        if path:
            return [path, flag, "sh", "-c", 'exec cat "$0"', device]
    return "no terminal emulator on PATH"


class WindowConsole:
    """A ``Console`` for the endpoint (``OperatorEndpoint.console``): each call shows the window and writes to it."""

    def __init__(self, *, spawn: Callable[[list[str]], Any] | None = None) -> None:
        self.on_unavailable: Callable[[], None] = lambda: None
        self._spawn = spawn or (lambda argv: subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._master: int | None = None
        self._slave: int | None = None

    def __call__(self, text: str) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            why = self._write_windows(text) if sys.platform == "win32" else self._write_posix(text)
        if why:
            self.on_unavailable()
            raise errors.OperatorAuthorizationRequired(NO_WINDOW.format(why=why), detail=why)

    def done(self) -> None:
        """The challenge has ended: the window goes after :data:`LINGER_S`, unless another one starts."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(LINGER_S, self.close)
            self._timer.daemon = True
            self._timer.start()

    def close(self) -> None:
        with self._lock:
            if sys.platform == "win32":  # pragma: windows-only
                self._show(False)
                return
            for fd in (self._master, self._slave):  # pragma: posix-only
                if fd is not None:
                    os.close(fd)
            self._master = self._slave = None  # pragma: posix-only

    # ------------------------------------------------------------------ Windows: its own hidden console

    @staticmethod
    def _show(visible: bool) -> bool:  # pragma: windows-only
        import ctypes

        window = ctypes.windll.kernel32.GetConsoleWindow()
        if not window:
            return False
        ctypes.windll.user32.ShowWindow(window, 5 if visible else 0)  # SW_SHOW, SW_HIDE
        if visible:
            ctypes.windll.user32.SetForegroundWindow(window)
        return True

    def _write_windows(self, text: str) -> str | None:  # pragma: windows-only
        if not self._show(True):
            return "this process has no console"
        try:
            with open("CONOUT$", "w", encoding="utf-8") as out:
                out.write(text)
        except OSError as exc:
            return f"its console cannot be written ({exc})"
        return None

    # ------------------------------------------------------------------ Linux: a pseudo-terminal, shown by an emulator

    def _write_posix(self, text: str) -> str | None:  # pragma: posix-only
        if self._master is None:
            why = self._open_posix()
            if why:
                return why
        assert self._master is not None
        try:
            os.write(self._master, text.encode("utf-8"))
        except OSError as exc:
            return f"its window cannot be written ({exc})"
        return None

    def _open_posix(self) -> str | None:  # pragma: posix-only
        import pty
        import termios

        master, slave = pty.openpty()
        attrs = termios.tcgetattr(slave)
        attrs[3] &= ~termios.ECHO  # what is written here is shown once, by the `cat`, and never read back
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        command = terminal_command(os.ttyname(slave))
        if isinstance(command, str):
            os.close(master)
            os.close(slave)
            return command
        try:
            self._spawn(command)
        except OSError as exc:
            os.close(master)
            os.close(slave)
            return f"{command[0]} did not start ({exc})"
        self._master, self._slave = master, slave
        return None
