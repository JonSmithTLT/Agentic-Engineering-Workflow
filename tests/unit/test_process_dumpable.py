"""No test leaves the test process non-dumpable (tests/conftest.py, ``no_hardened_test_process``).

AEW hardens its credential holders with ``PR_SET_DUMPABLE 0`` (``procs.harden_current_process``). A test that calls a
holder's entry point in process hardened the test process itself, and every later test in it lost ``ss``'s owner for
its own sockets: the dashboard client's probe test then failed on a nightly shard, far from the test that did it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import process_dumpable

from aew.harness import procs


def test_the_hardening_called_in_process_leaves_the_test_process_dumpable():
    """The call the nightly failure's polluter made (through a Lead session's entry point, run in process), made here
    directly."""
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


INNER_TESTS = """
import sys

import process_dumpable


def test_a_clears_the_flag():
    if sys.platform.startswith("linux"):
        process_dumpable.set_dumpable(False)


def test_b_runs_after_it():
    assert process_dumpable.dumpable() is (True if sys.platform.startswith("linux") else None)
"""


def test_the_guard_errors_the_test_that_cleared_the_flag_by_name_and_the_next_test_runs_dumpable(tmp_path):
    """The guard itself, in a pytest of its own (clearing the flag here is what it forbids): the test that left its
    process non-dumpable errors at teardown, by name, and the next test in that process finds the flag set again."""
    helpers = Path(process_dumpable.__file__).resolve().parent
    src = Path(procs.__file__).resolve().parents[2]
    (tmp_path / "conftest.py").write_text("from process_dumpable import no_hardened_test_process  # noqa: F401\n",
                                          encoding="utf-8")
    (tmp_path / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(helpers), str(src)])}
    done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist", "-rA",
                           "test_inner.py"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = done.stdout + done.stderr
    if not sys.platform.startswith("linux"):  # no flag to clear: both pass
        assert done.returncode == 0 and "2 passed" in out, out
        return
    assert "ERROR test_inner.py::test_a_clears_the_flag" in out, out
    assert "test_inner.py::test_a_clears_the_flag left the test process non-dumpable" in out, out
    # the clearing test's body passed, then its teardown errored: 2 passed (its call and the next test), 1 error
    assert "PASSED test_inner.py::test_b_runs_after_it" in out and "2 passed, 1 error" in out, out
