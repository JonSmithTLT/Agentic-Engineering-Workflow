"""What a process tree counts as still running (register E247).

On Linux a zombie keeps its process group until its parent reaps it, and ``killpg(pgid, 0)`` succeeds on a group that
holds nothing else. ``ProcessTree.active`` read that as a running member, so ``close`` and ``survivors`` waited their
whole bound on a tree whose every process had ended. Each test holds a member as a zombie without reaping it
(``waitid`` with ``WNOWAIT``), which is the state a caller's unreaped ``Popen`` leaves.
"""

from __future__ import annotations

import os
import platform
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
        # Nothing was running, so close kills nothing. Its wait loop runs while ``active()`` is not zero, so the reading
        # above is also what keeps it from waiting; how long it took is not asserted outside the serial lane.
        assert tree.close(EXIT_S) == 0
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


# A member whose main thread ends while another runs on: the kernel shows the process as ``Z`` though it is alive.
SYS_EXIT = {"x86_64": 60, "aarch64": 93}.get(platform.machine())
THREADED = ("import ctypes, sys, threading, time; threading.Thread(target=time.sleep, args=(60,)).start(); "
            "sys.stdout.write('ready\\n'); sys.stdout.flush(); ctypes.CDLL(None).syscall({exit}, 0)")


def kernel_state(pid: int) -> bytes:
    with open(f"/proc/{pid}/stat", "rb") as stat:
        return stat.read().rsplit(b")", 1)[1].split()[0]


@pytest.mark.skipif(not IS_LINUX or SYS_EXIT is None,
                    reason="a zombie holding its process group, and /proc to read it, are Linux's")
def test_a_member_whose_main_thread_ended_while_another_runs_is_still_active_and_close_ends_it():
    """Review of #608, M1: such a process reads ``Z`` in ``/proc/<pid>/stat``, and is no zombie."""
    tree = ProcessTree()
    proc = tree.spawn([sys.executable, "-c", THREADED.format(exit=SYS_EXIT)], stdout=subprocess.PIPE)
    try:
        assert proc.stdout is not None and proc.stdout.readline() == b"ready\n"
        deadline = time.monotonic() + EXIT_S
        while kernel_state(proc.pid) != b"Z":  # what the kernel says of it once its main thread has ended
            assert time.monotonic() < deadline, "the main thread did not end"
            time.sleep(0.01)
        assert proc.poll() is None  # and it has not ended
        assert tree.active() == 1
        assert tree.close(EXIT_S) == 1  # it was running, and close ended it
        assert tree.active() == 0
    finally:
        tree.kill()
        proc.wait(EXIT_S)
        if proc.stdout is not None:
            proc.stdout.close()
