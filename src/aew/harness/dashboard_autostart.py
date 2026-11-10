"""The operator's first dashboard session, opened by ``aew opencode`` (2026-11-07 no-code decision).

The server lives on threads in the host, outside the Lead's sandbox, and ends with this session. Only this call
issues without a typed-back code; there is no command-line mint route. A running dashboard is reused without issuing.
Later opens have no console on either platform: the single check in ``ControlServer._open`` refuses them (operator,
2026-11-09). Future in-process G3 approval belongs there, wherever doctor's g3 check counts; it is not built here.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

from aew import operator
from aew.dashboard import service
from aew.dashboard.defaults import DEFAULT_PORT
from aew.dashboard.session import OPERATOR_START
from aew.engine.api import Engine
from aew.errors import UsageError
from aew.harness import operator_client

OFF_ENV = "AEW_DASHBOARD_AUTOSTART"
# Designer's DAB-02 ruling, 2026-11-10: starting at a terminal is not a typed-back confirmation.
FIRST_AUTHORIZED_BY = OPERATOR_START
SERVE = "run `aew dashboard serve` in a terminal of its own"


def has_display() -> bool:
    """A desktop, not a text browser on an SSH terminal. No browser lookup launches anything here."""
    if sys.platform in ("win32", "darwin"):
        return not any(os.environ.get(k) for k in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"))
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def open_browser(url: str) -> bool:
    """Deliver only to the desktop opener, never its output or exception text.

    Both platforms may put the URL on the browser's command line: a single-use bootstrap, valid for at most ten
    minutes, not the session cookie. Windows ShellExecute via startfile avoids only AEW's own child argv. On Unix,
    DEVNULL fds and a new session keep launcher output off the TUI; xdg-open may consult inherited BROWSER.
    No test calls a real opener.
    """
    if sys.platform == "win32":  # pragma: windows-only
        os.startfile(url)  # noqa: S606 (fixed loopback bootstrap URL minted below, not an executable or a user path)
        return True
    command = ["open" if sys.platform == "darwin" else "xdg-open", url]
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
    try:
        return child.wait(timeout=0.1) == 0
    except subprocess.TimeoutExpired:
        return True  # generic xdg-open may wait for the browser; delivery does not wait for that browser to close


def _line(text: str) -> None:
    sys.stderr.write(f"aew opencode: {text}\n")


def _reused(engine: Any) -> bool:
    running = service.locate(engine.aew_root)
    if running is None:
        return False
    _line(f"the dashboard is already running; {service.session_step(running)}")
    return True


def _start(engine: Any) -> service.Service | None:
    svc = None
    try:
        if _reused(engine):
            return None
        # The dashboard's read collaborators must not share the broker's engine caches across threads.
        svc = service.Service(Engine.discover(engine.repo_root), console=None)
        svc.start()  # Service rechecks publication under its per-project lock, before any mint.
        url = svc.issue(authorized_by=FIRST_AUTHORIZED_BY)
        if not open_browser(url):
            raise OSError("desktop opener refused")
    except BaseException as exc:
        if svc is not None:
            _stop(svc)
        if not isinstance(exc, Exception):
            raise
        # A concurrent start won: reuse it, never mint through its control channel. A broken locator must not
        # turn the best-effort failure report into a session failure either.
        with contextlib.suppress(Exception):
            if _reused(engine):
                return None
        if isinstance(exc, UsageError) and exc.details.get("errno") == errno.EADDRINUSE:
            _line(f"dashboard port 127.0.0.1:{DEFAULT_PORT} is in use; "
                  "run `aew dashboard serve --port 0` in a terminal of its own for an ephemeral port, "
                  "or pass a free port you choose")
        else:
            _line(f"the dashboard did not open on 127.0.0.1:{DEFAULT_PORT} ({type(exc).__name__}); {SERVE}")
        return None
    _line(f"the dashboard opened in your browser on port {svc.port}, for this session's lifetime; "
          f"{OFF_ENV}=off turns this off")
    return svc


def _stop(svc: service.Service) -> None:
    try:
        svc.stop()
    except Exception:  # noqa: BLE001 (cleanup must neither hide the TUI's outcome nor disclose a credential)
        _line("the dashboard could not finish cleanup; its sessions end when this process exits")


@contextlib.contextmanager
def _quiet_log() -> Iterator[None]:
    """The TUI owns stderr, including when no root handler masks logging.lastResort (review m1)."""
    logger = logging.getLogger("aew.dashboard")
    handlers, propagate = logger.handlers, logger.propagate
    quiet = logging.NullHandler()
    logger.handlers, logger.propagate = [quiet], False
    try:
        yield
    finally:
        logger.handlers, logger.propagate = handlers, propagate
        quiet.close()


@contextlib.contextmanager
def for_session(engine: Any) -> Iterator[None]:
    """Own the dashboard and its quiet log for this session, after its seat is held and before the TUI."""
    with _quiet_log():
        with _for_session(engine):
            yield


@contextlib.contextmanager
def _for_session(engine: Any) -> Iterator[None]:
    """Start before the TUI; stop on normal exit, refusal or interrupt. Failures never fail the session."""
    svc = None
    try:
        if os.environ.get(OFF_ENV) == "off":
            _line(f"dashboard auto-start is off ({OFF_ENV}=off)")
        elif operator_client.lead_session_problem() is not None:
            _line(f"the dashboard was not started: this is a Lead session; {SERVE} outside this session")
        elif not operator.has_terminal():
            _line(f"the dashboard was not started: no operator terminal; {SERVE}")
        elif not has_display():
            _line(f"the dashboard was not started: no display; {SERVE}")
        else:
            svc = _start(engine)
    except Exception as exc:  # noqa: BLE001 (even a failed preflight must not fail the Lead, or echo secrets)
        _line(f"the dashboard was not started ({type(exc).__name__}); {SERVE}")
    try:
        yield
    finally:
        if svc is not None:
            _stop(svc)
