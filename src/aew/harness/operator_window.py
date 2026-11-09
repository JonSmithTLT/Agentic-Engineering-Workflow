"""The console of an operator endpoint with no terminal (`aew opencode` started it).

- **Windows:** the endpoint has a hidden console of its own (:mod:`aew.harness.operator_autostart`), shown when a
  challenge needs it and hidden again once it has ended. The operator allowed this on 2026-10-11, "aew CAN open
  terminals intentionally if needed just keep it reasonable not in testing". The code stays in the endpoint's own
  memory, and on no command line and in no file.
- **Linux:** there is nothing to show a code on, so :meth:`BackgroundConsole.problem` says so and the endpoint makes
  none. Only outcome lines arrive here, and they go to the endpoint's log.

A line that cannot be written is dropped: an outcome line reports what already happened and never changes it.
"""

from __future__ import annotations

import sys
import threading

WINDOWS = sys.platform == "win32"
LINGER_S = 8.0  # how long the window stays once the challenge has ended, for its result line to be read
NO_TERMINAL = "it has no terminal"


class BackgroundConsole:
    """A ``Console`` for the endpoint (``OperatorEndpoint.console``), and why no code can be shown on it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def problem(self) -> str | None:
        """Why a code cannot be shown here, or ``None``. Asked before a code exists."""
        if not WINDOWS:
            return NO_TERMINAL
        with self._lock:  # pragma: windows-only
            self._cancel_timer()
            if not self._show(True):
                return "this process has no console"
            try:
                open("CONOUT$", "w", encoding="utf-8").close()
            except OSError as exc:
                return f"its console cannot be written ({exc})"
        return None  # pragma: windows-only

    def __call__(self, text: str) -> None:
        with self._lock:
            self._cancel_timer()
            try:
                if WINDOWS:
                    self._write_windows(text)
                else:
                    sys.stdout.write(text)
                    sys.stdout.flush()
            except (OSError, ValueError):
                pass

    def done(self) -> None:
        """The challenge has ended: the window goes after :data:`LINGER_S`, unless another one starts."""
        if not WINDOWS:
            return
        with self._lock:  # pragma: windows-only
            self._cancel_timer()
            self._timer = threading.Timer(LINGER_S, self.close)
            self._timer.daemon = True
            self._timer.start()

    def close(self) -> None:
        if WINDOWS:
            with self._lock:  # pragma: windows-only
                self._show(False)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    @staticmethod
    def _show(visible: bool) -> bool:  # pragma: windows-only
        if sys.platform != "win32":  # the type checker's narrowing: `windll` exists only there
            return False
        import ctypes

        window = ctypes.windll.kernel32.GetConsoleWindow()
        if not window:
            return False
        ctypes.windll.user32.ShowWindow(window, 5 if visible else 0)  # SW_SHOW, SW_HIDE
        if visible:
            ctypes.windll.user32.SetForegroundWindow(window)
        return True

    def _write_windows(self, text: str) -> None:  # pragma: windows-only
        self._show(True)
        with open("CONOUT$", "w", encoding="utf-8") as out:
            out.write(text)
