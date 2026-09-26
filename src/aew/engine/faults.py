"""Named fault-injection points for crash-safety tests.

``AEW_FAULT=<point>[,<point>...]`` makes the process die at that point:
``AEW_FAULT_MODE=exit`` (default) calls ``os._exit`` so no cleanup handlers run,
which is the realistic crash; ``raise`` raises ``InjectedFault`` for fast
in-process tests. With the variable unset this is a no-op.
"""

from __future__ import annotations

import os

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
