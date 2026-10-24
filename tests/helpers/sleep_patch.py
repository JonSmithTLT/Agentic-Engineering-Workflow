"""Patching ``time.sleep`` for one test's own thread only.

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

This module imports nothing from AEW: helper children may load it.
"""

from __future__ import annotations

import threading
import time
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
