"""Bound the Windows regression step independently of pytest and its sentinel."""

from __future__ import annotations

import math
import os
import runpy
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "helpers"))
import proctree
from bounds import DEADLINE_MARGIN_S, SESSION_END_MARGINS
from session_deadline import SUPERVISOR_CUTOFF_EXIT

PYTHON_MODULE_PATH = sys.path[2:]  # omit the helper and script directories, as in python -m pytest
CUTOFF_CLEARANCE_S = 10  # let the sentinel finish its last process scan and writes after its backstop acts
CUTOFF_GRACE_S = SESSION_END_MARGINS * DEADLINE_MARGIN_S + CUTOFF_CLEARANCE_S


def supervise(directory: Path, pytest_args: list[str], cutoff: float) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    status = directory / "step.txt"
    status.write_text("Windows regression step entered its supervisor.\n", encoding="utf-8")
    if cutoff <= time.monotonic():
        status.write_text("The job budget was exhausted before pytest could start.\n", encoding="utf-8")
        return SUPERVISOR_CUTOFF_EXIT

    name = f"aew-ci-lane-{uuid4().hex}"
    job = proctree.Job(name)
    child = subprocess.Popen([sys.executable, __file__, "_pytest", name,
                              f"--running-tests-dir={directory.resolve()}", *pytest_args],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        code = child.wait(timeout=max(0, cutoff - time.monotonic()))
        # A surviving descendant can hold the runner's output pipe after pytest has exited.
        while job.pids():
            remaining = cutoff - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(child.args, 0)
            time.sleep(min(remaining, 0.25))
    except subprocess.TimeoutExpired:
        code = child.poll()
        pytest_status = "Pytest was still running" if code is None else f"Pytest had exited with code {code}"
        members = []
        with suppress(OSError):
            members = [f"  {proc.pid} {Path(proc.exe).name or '<unknown>'}"
                       for proc in job.members(command_lines=False)]
        job.terminate(SUPERVISOR_CUTOFF_EXIT)
        # Bound startup too: the Python process may have stalled before joining the job.
        child.kill()
        status.write_text("\n".join([
            f"Independent step cutoff. {pytest_status} (pid {child.pid}).",
            "Job members at cutoff (pid and image):", *members,
        ]) + "\n", encoding="utf-8")
        return SUPERVISOR_CUTOFF_EXIT
    status.write_text(f"Pytest process returned exit {code}.\n", encoding="utf-8")
    return code


def main(args: list[str]) -> int:
    if args[0] == "_pytest":
        # Join before pytest startup so the workers and pytest's external sentinel inherit this job.
        proctree.Job.open(args[1]).assign_self()
        sys.path[:] = [str(Path.cwd()), *PYTHON_MODULE_PATH]
        sys.argv = ["pytest", *args[2:]]
        runpy.run_module("pytest", run_name="__main__", alter_sys=True)
        return 0
    deadline = float(os.environ["AEW_JOB_DEADLINE"])
    if not math.isfinite(deadline):
        raise ValueError("AEW_JOB_DEADLINE must be finite")
    cutoff = time.monotonic() + (deadline - time.time()) + CUTOFF_GRACE_S
    return supervise(Path(args[0]), args[1:], cutoff)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
