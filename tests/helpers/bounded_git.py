"""git as an operator runs it, under a bound that holds when one of its programs doesn't end.

The repository of tests/regression/test_m4b_review.py routes files through a script that ends in ``cat``, so git's
children read and hold whatever they inherit. ``subprocess.run(capture_output=True)`` can wait on them forever, and its
``timeout=`` doesn't help on Windows: once it kills git it reads the pipes again with no timeout, and a grandchild still
holds them. So here nothing is a pipe: stdin is the null device, the output goes to files, and at the bound the whole
process tree ends.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import bounds

from aew.harness import procs

PLAIN_GIT_S = bounds.declare("plain_git", 120, why="one git command in a test's repository, whose programs may hold "
                                                   "on; under every lane's --test-timeout, so a hang names its command")
# A helper called dozens of times per test; each call polls this often for git's exit. On Linux each call also waits for
# the process tree's sentinel when it closes, about 16 ms.
POLL_S = 0.01


def _text(output: Any) -> str:
    output.seek(0)
    return output.read().decode(errors="replace").replace("\r\n", "\n")


def plain_git(*args: str, cwd: Path, env: Mapping[str, str], seconds: float | None = None
              ) -> subprocess.CompletedProcess[str]:
    """Run git and return what ``subprocess.run`` would. :class:`bounds.BoundExpired` names the command and what it had
    said, with its process tree ended: a process group on Linux, so a program that calls ``setsid`` would leave it."""
    argv = ["git", *args]
    tree = procs.ProcessTree()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        try:
            proc = tree.spawn(argv, cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL, stdout=out, stderr=err)
            try:
                bounds.bounded_wait("plain_git", lambda: proc.poll() is not None, seconds=seconds, poll_s=POLL_S)
            except bounds.BoundExpired as expired:
                tree.kill()
                proc.wait(PLAIN_GIT_S)  # on Linux a zombie still counts as the group, and `close` would wait on it
                raise bounds.BoundExpired(f"{expired}: {argv} in {cwd}; stdout {_text(out)[-2000:]!r}, "
                                          f"stderr {_text(err)[-2000:]!r}") from None
        finally:
            tree.close()
        return subprocess.CompletedProcess(argv, proc.wait(), _text(out), _text(err))
