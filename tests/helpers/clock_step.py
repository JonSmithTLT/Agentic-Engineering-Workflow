"""A wall-clock step, simulated for the process identity tests (ADR-0009 amendment 2026-10-23).

On Linux ``procs.started_at`` is ``btime`` (``/proc/stat``: the wall clock minus the time since boot) plus the
process's start ticks, so a step of the wall clock moves every epoch start time while the process stays the same.
:func:`stepper` simulates that where ``btime`` is read. Elsewhere (Windows' creation time is absolute) it moves what a
step moves on Linux, each ``procs.started_at``, so a reader that still judges by a start time fails on every platform.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from aew.harness import procs

STEP_S = 6.0  # past same_process's 2 s tolerance for a start time; WSL's +3 s steps reach it within a minute
BTIME = re.compile(r"^btime (\d+)$", re.M)


def stepper(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """``step(seconds)`` steps the wall clock. On Linux ``btime`` is frozen from this call on (a host such as WSL steps
    its own clock every half minute, which would move it mid-test) and moves only by these steps."""
    offset = [0.0]
    if sys.platform.startswith("linux"):
        real = Path.read_text
        found = BTIME.search(real(Path("/proc/stat")))
        assert found is not None, "no btime in /proc/stat"
        frozen = int(found.group(1))

        def read_text(self: Path, *args: Any, **kwargs: Any) -> str:
            text = real(self, *args, **kwargs)
            if self.as_posix() == "/proc/stat":
                text = BTIME.sub(f"btime {frozen + int(offset[0])}", text)
            return text

        monkeypatch.setattr(Path, "read_text", read_text)
    else:
        started_at = procs.started_at
        monkeypatch.setattr(procs, "started_at",
                            lambda pid: None if (start := started_at(pid)) is None else start + offset[0])

    def step(seconds: float = STEP_S) -> None:
        offset[0] += seconds

    return step


def reused(start: str) -> str:
    """The start id of a later process given the same pid: another start, on the same boot."""
    head, _, ticks = start.rpartition(":")
    return f"{head}:{int(ticks) + 1}"
