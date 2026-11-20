"""The test process's dumpable flag (Linux's ``PR_GET_DUMPABLE``).

``procs.harden_current_process`` clears it for AEW's credential holders: a same-uid process can then read none of
their ``/proc/<pid>`` entries. Cleared in the test process itself, it stays cleared for every later test in that
process, and ``ss -p`` then names no owner for this process's own sockets: a test that reads its listener's row by
pid fails, whichever test cleared the flag. ``no_hardened_test_process``, autouse through ``tests/conftest.py``,
keeps it set.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest

PR_GET_DUMPABLE, PR_SET_DUMPABLE = 3, 4


def dumpable() -> bool | None:
    """Whether this process is dumpable; None where there is no such flag (not Linux)."""
    if not sys.platform.startswith("linux"):
        return None
    import ctypes  # pragma: posix-only

    return bool(ctypes.CDLL(None, use_errno=True).prctl(PR_GET_DUMPABLE, 0, 0, 0, 0))


def set_dumpable(on: bool) -> None:
    """Linux only: set this process's dumpable flag (a process may set its own back to 1)."""
    import ctypes  # pragma: posix-only

    if ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, int(on), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE) failed")


def restored() -> bool:
    """If this process is not dumpable, make it dumpable again: whether it had to."""
    if dumpable() is False:
        set_dumpable(True)
        return True
    return False


@pytest.fixture(autouse=True)
def no_hardened_test_process(request: pytest.FixtureRequest) -> Iterator[None]:
    """``procs.harden_current_process`` makes the process that calls it non-dumpable (Linux), for the real credential
    holders. In process it would harden the test process itself, for every later test in it: ``ss -p`` then names no
    owner for this process's own sockets. So in process it does nothing: a test of the call replaces it itself, and a
    fresh interpreter a test starts (``subprocess``, never a bare ``os.fork()``, which keeps this replacement) hardens
    itself as it would. A test that leaves this process non-dumpable any other way errors at teardown, by name, and
    the flag is set again for the next test. (Not through ``monkeypatch``, for the reason ``capability_register`` in
    ``tests/conftest.py`` gives.)"""
    from aew.harness import procs

    saved = procs.harden_current_process
    procs.harden_current_process = lambda: None
    yield
    procs.harden_current_process = saved
    if restored():
        pytest.fail(f"{request.node.nodeid} left the test process non-dumpable (PR_SET_DUMPABLE 0), which hides this "
                    "process's sockets' owner from every later test in it: harden only a process the test starts")
