"""What a process tree counts as still running (register E247).

On Linux a zombie keeps its process group until its parent reaps it, and ``killpg(pgid, 0)`` succeeds on a group that
holds nothing else. ``ProcessTree.active`` read that as a running member, so ``close`` and ``survivors`` waited their
whole bound on a tree whose every process had ended. Each test holds a member as a zombie without reaping it
(``waitid`` with ``WNOWAIT``), which is the state a caller's unreaped ``Popen`` leaves.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from aew.harness.procs import ProcessTree

IS_LINUX = sys.platform.startswith("linux")
EXIT_S = 60.0  # a child that only exits is a zombie well within this
ORPHANER = ("import subprocess, sys; d = subprocess.DEVNULL; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], stdin=d, stdout=d, stderr=d)")


def zombie(proc: subprocess.Popen[bytes]) -> None:
    """Wait until ``proc`` has exited, and leave it unreaped: its ``Popen`` has not seen it end."""
    deadline = time.monotonic() + EXIT_S
    while os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
        assert time.monotonic() < deadline, "the child did not exit"
        time.sleep(0.01)
    assert proc.returncode is None


@pytest.mark.skipif(not IS_LINUX, reason="a zombie holding its process group, and /proc to read it, are Linux's")
def test_a_tree_whose_group_holds_only_a_zombie_is_not_active_and_closes_without_waiting():
    tree = ProcessTree()
    proc = tree.spawn([sys.executable, "-c", "pass"])
    try:
        zombie(proc)
        os.killpg(proc.pid, 0)  # the group is still there: this is the reading that counted the zombie
        assert tree.active() == 0
        assert tree.survivors(0.0) == []
        started = time.monotonic()
        assert tree.close(EXIT_S) == 0  # nothing was running, so nothing is killed and nothing waited for
        assert time.monotonic() - started < EXIT_S / 2
    finally:
        tree.kill()
        proc.wait(EXIT_S)


@pytest.mark.skipif(not IS_LINUX, reason="a zombie holding its process group, and /proc to read it, are Linux's")
def test_a_tree_with_a_running_member_beside_a_zombie_is_still_active_and_close_ends_it():
    tree = ProcessTree()
    leader = tree.spawn([sys.executable, "-c", ORPHANER])  # it starts a member of its group, and exits
    try:
        zombie(leader)
        assert tree.active() == 1
        assert tree.close(EXIT_S) == 1  # the member was running, and close ended it
        assert tree.active() == 0  # the member is gone, or a zombie until whoever adopted it reaps it
    finally:
        tree.kill()
        leader.wait(EXIT_S)
