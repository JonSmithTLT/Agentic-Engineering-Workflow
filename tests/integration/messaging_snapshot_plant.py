"""Deliberate failures for the messaging snapshot autopsy test. Run only by explicit path."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import autopsy
import bounds
import pytest
import snapshot_process


def block_in_snapshot() -> None:
    threading.Event().wait(60)  # a finite backstop if the outer test itself is interrupted


def helper(case: str, ready: Path) -> None:
    if case == "exited":
        # Only the descendant's stdout leads back to the pytest process.
        hold = ("import os, sys, threading; from pathlib import Path; "
                "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii'); threading.Event().wait(60)")
        child = subprocess.Popen([sys.executable, "-B", "-c", hold, str(ready)],
                                 stdout=sys.stdout, stderr=subprocess.DEVNULL,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        bounds.bounded_wait("wait.condition", ready.is_file, gone=lambda: child.poll() is not None)
        return
    ready.write_text(str(os.getpid()), encoding="ascii")
    block_in_snapshot()


@pytest.mark.autopsy(children_only=True)
@pytest.mark.parametrize("case", ["blocked", "exited", "stalled"])
def test_snapshot_timeout(case, tmp_path, monkeypatch):
    ready = tmp_path / "ready"
    directory = autopsy.child_dir()
    state = tmp_path / ".aew" / "project.yaml"
    state.parent.mkdir()
    state.write_text("project: seeded", encoding="utf-8")
    # Spelled in parts so only the private file contains the synthetic token.
    (directory / "probe.txt").write_text("ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz", encoding="ascii")
    communicate = subprocess.Popen.communicate
    plant_deadline = 0.4

    def communicate_when_ready(proc, *args, **kwargs):
        if kwargs.get("timeout") != plant_deadline or proc.args[3] != __file__:
            return communicate(proc, *args, **kwargs)
        bounds.bounded_wait("wait.condition", lambda: ready.is_file() and ready.read_text(encoding="ascii").isdigit())
        holder = int(ready.read_text(encoding="ascii"))
        # Independent expected identities, outside the retained autopsy.
        (directory.parent.parent / f"expected-{case}.txt").write_text(f"{proc.pid} {holder}", encoding="ascii")
        if case == "exited":
            assert proc.wait(30) == 0
        else:
            bounds.bounded_wait("wait.condition", lambda: any(
                "in block_in_snapshot" in p.read_text(encoding="utf-8", errors="replace")
                for p in directory.glob(f"stacks-{proc.pid}.*.txt")))
        return communicate(proc, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", communicate_when_ready)
    if case == "stalled":
        sleeper = tmp_path / "slow-observer.py"
        sleeper.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        monkeypatch.setattr(snapshot_process, "__file__", str(sleeper))
        monkeypatch.setattr(snapshot_process, "OBSERVE_S", 0.2)
    snapshot_process.run(Path(__file__), [case, str(ready)], directory, timeout=plant_deadline, interval=1)


if __name__ == "__main__":
    helper(sys.argv[1], Path(sys.argv[2]))
