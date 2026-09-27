"""Named fault-injection points for crash-safety tests.

``AEW_FAULT=<point>[,<point>...]`` makes the process die at that point:
``AEW_FAULT_MODE=exit`` (default) calls ``os._exit`` so no cleanup handlers run,
which is the realistic crash; ``raise`` raises ``InjectedFault`` for fast
in-process tests. With the variable unset this is a no-op.
"""

from __future__ import annotations

import os
import time

CRASH_EXIT_CODE = 86


class InjectedFault(BaseException):
    """Deliberately a BaseException so ordinary ``except Exception`` never swallows it."""


def hit(point: str) -> None:
    spec = os.environ.get("AEW_FAULT")
    if not spec or point not in spec.split(","):
        return
    if os.environ.get("AEW_FAULT_MODE", "exit") == "raise":
        raise InjectedFault(point)
    os._exit(CRASH_EXIT_CODE)


def pause(point: str, *, limit_s: float = 120.0) -> None:
    """Hold at ``point`` while a file exists: ``AEW_PAUSE=<point>=<file>[;<point>=<file>...]``.

    Makes a race window deterministic in tests (for example a bridge request that is in flight while the
    Lead rotates the credential). With the variable unset this is a no-op.
    """
    spec = os.environ.get("AEW_PAUSE")
    if not spec:
        return
    for item in spec.split(";"):
        name, _, path = item.partition("=")
        if name == point and path:
            try:  # tells the test the process reached the point
                open(path + ".reached", "a").close()
            except OSError:
                pass
            deadline = time.monotonic() + limit_s
            while os.path.exists(path) and time.monotonic() < deadline:
                time.sleep(0.05)
