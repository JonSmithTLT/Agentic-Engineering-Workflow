"""No test leaves the test process non-dumpable (tests/conftest.py, ``no_hardened_test_process``).

AEW hardens its credential holders with ``PR_SET_DUMPABLE 0`` (``procs.harden_current_process``). A test that calls a
holder's entry point in process hardened the test process itself, and every later test in it lost ``ss``'s owner for
its own sockets: the dashboard client's probe test then failed on a nightly shard, far from the test that did it.
"""

from __future__ import annotations

import sys

import process_dumpable

from aew.harness import procs


def test_the_hardening_called_in_process_leaves_the_test_process_dumpable():
    """The path the nightly failure took: a Lead session's entry point, run in process, calls the hardening."""
    before = process_dumpable.dumpable()
    procs.harden_current_process()
    assert process_dumpable.dumpable() == before
    assert before is (None if not sys.platform.startswith("linux") else True)


def test_a_process_left_non_dumpable_is_reported_and_made_dumpable_again():
    """What the guard does after each test: says the flag was cleared, and sets it for the next."""
    if process_dumpable.dumpable() is None:  # not Linux: no flag, nothing to report or restore
        assert process_dumpable.restored() is False
        return
    process_dumpable.set_dumpable(False)
    try:
        assert process_dumpable.dumpable() is False
        assert process_dumpable.restored() is True
        assert process_dumpable.dumpable() is True
        assert process_dumpable.restored() is False  # nothing to restore twice
    finally:
        process_dumpable.set_dumpable(True)
