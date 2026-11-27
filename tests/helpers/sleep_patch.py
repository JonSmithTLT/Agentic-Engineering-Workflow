"""Patching ``time.sleep``, and the clocks of ``time``, for one test's own thread only.

``module.time`` is the one shared ``time`` module, so ``monkeypatch.setattr(module.time, "sleep", ...)`` replaces
``sleep`` for every thread in the worker process, not only for the code under test. A thread an earlier test left
running then has its sleeps counted, or skipped so it spins. On #237's run 40035060397 (Windows, fast lane) a stray
thread's 0.05 s sleeps doubled the count ``test_store_read_committed`` asserts on (15 sleeps for 7 retries).

:func:`patch_sleep` records and skips the calls made from the test's own thread, and lets every other thread keep the
real ``sleep``. ``tests/unit/test_sleep_patches.py`` refuses a test that patches ``sleep`` in these spellings, and no
others: ``setattr`` or ``patch.object`` with positional arguments ``time`` (or ``<x>.time``) and ``"sleep"``, and
``setattr`` or ``patch`` with a first positional argument that is the string ``"time.sleep"`` or ends in
``.time.sleep``. A plain assignment, keyword arguments, an aliased ``patch``, ``patch.multiple``, a replaced ``time``
binding, a ``from time import sleep`` binding and a ``time`` module bound to another name are not seen: the reviewer
reads for them. No check by binding is done (see that module's docstring).

:func:`patch_clock` does the same for a clock (``time.time``, ``time.monotonic``, ...). The worker's own threads read
the shared clocks: the session deadline's thread (``session_deadline.Worker``) wakes at least once a minute and exits
the worker when ``time.monotonic()`` is past its deadline. On ``main``'s push run 45997128944 (Windows, integration
14/14) ``test_no_map_freshness_turns_current_on_a_timer`` moved ``time.monotonic`` a year ahead for every thread, that
thread woke inside the patch, and gw2 exited 1.4 s into the test, about 24 minutes before the real deadline.

This module imports nothing from AEW: helper children may load it.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from types import ModuleType

import pytest


def patch_sleep(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> list[float]:
    """Replace ``sleep`` as ``module`` sees it, for the calling thread only, and return the list its calls append to.

    Other threads sleep for real, so a background thread neither adds to the count nor spins while the patch is on.
    Call it from the test's own thread: the patch is keyed on that thread's id, which another thread may reuse once it
    exits.
    """
    real = time.sleep
    owner = threading.get_ident()
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        if threading.get_ident() == owner:
            sleeps.append(seconds)
        else:
            real(seconds)

    monkeypatch.setattr(module.time, "sleep", sleep)
    return sleeps


def patch_clock(monkeypatch: pytest.MonkeyPatch, name: str, reading: Callable[[], float]) -> None:
    """Replace the shared ``time`` module's clock ``name`` with ``reading``, for the calling thread only.

    Every other thread reads the real clock, so the worker's session deadline and a thread an earlier test left
    running are not moved with the test's clock. The hang watchdog's timer is not moved either, but on Linux its
    alarm handler runs on the patching thread, so the "fired after" time it reports can read the moved clock. Call it
    from the test's own thread, as :func:`patch_sleep`. A module that bound the clock at import
    (``from time import monotonic``) is not reached.
    """
    real = getattr(time, name)
    owner = threading.get_ident()

    def clock() -> float:
        return reading() if threading.get_ident() == owner else real()

    monkeypatch.setattr(time, name, clock)
