"""Run the messaging snapshot with its output pipes intact and observe its timeout before ending the tree."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import bounds
import childdiag
import proctree

SNAPSHOT_S = bounds.declare("messaging.snapshot", 60, why="the seeded messaging golden's snapshot subprocess")
# A process listing normally takes a fraction of a second. Collection and cleanup have their own small bounds.
OBSERVE_S = 5
CLEANUP_S = 5


def members(pid: int, start: int) -> list[proctree.Proc]:
    if sys.platform == "win32":
        # The parent still owns the helper handle, even after its exit: Windows cannot recycle its PID yet.
        return proctree.descendants((pid, start), proctree.table())
    # ProcessTree gives this helper its own group. A child whose parent exited still belongs to it.
    found = []
    for member, parent, created, state in proctree.linux_states():
        if member != pid and state not in ("X", "Z"):
            try:
                if os.getpgid(member) == pid:
                    found.append(proctree.Proc(member, parent, created))
            except ProcessLookupError:
                pass  # it ended between the two reads
    return found


def observe(proc, start: int, began: float, directory: Path) -> str:
    code = proc.poll()
    lines = [f"before cleanup after {time.monotonic() - began:.3f}s: helper pid={proc.pid} start={start or 'unknown'} "
             f"state={'running' if code is None else f'exited({code})'}",
             f"stdout reader stream closed={proc.stdout.closed}; stderr reader stream closed={proc.stderr.closed}"]
    try:
        command = [sys.executable, "-B", __file__, str(proc.pid), str(start), str(directory)]
        listing = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 text=True, timeout=OBSERVE_S,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        lines.append(listing.stdout.rstrip())
    except (OSError, subprocess.SubprocessError) as exc:
        lines.append(f"descendant observation unavailable: {type(exc).__name__}")
    return "\n".join(lines) + "\n"


def run(script: Path, args: list[str], directory: Path, *, timeout: float = SNAPSHOT_S,
        interval: float | None = None) -> subprocess.CompletedProcess[str]:
    from aew.harness.procs import ProcessTree

    argv = [sys.executable, "-B", str(Path(childdiag.__file__)), str(script), *args]
    tree = ProcessTree()
    try:
        proc = tree.spawn(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          env=childdiag.child_env(directory, capture="none", interval=interval))
        began = time.monotonic()
        start = proctree.start_time(proc.pid) or 0
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as timeout_error:
            try:
                record = observe(proc, start, began, directory)
            finally:
                tree.kill()  # includes an orphan still holding stdout after the helper exited
            try:
                proc.communicate(timeout=CLEANUP_S)
            except (OSError, subprocess.TimeoutExpired) as exc:
                timeout_error.add_note(f"post-termination pipe drain incomplete: {type(exc).__name__}")
            try:
                (directory / "snapshot-timeout.txt").write_text(record, encoding="utf-8")
            except OSError as exc:
                timeout_error.add_note(f"snapshot evidence unavailable: {type(exc).__name__}")
            raise
        return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
    finally:
        tree.close(timeout_s=CLEANUP_S)


if __name__ == "__main__":
    pid = int(sys.argv[1])
    found = members(pid, int(sys.argv[2]))
    for member in found:
        print(f"descendant pid={member.pid} current_ppid={member.ppid} start={member.start or 'unknown'}")
    if not found:
        print("no live descendants observed")
    # A periodic dump can predate the deadline. Supply its age with the file the autopsy retains.
    for stack in sorted(Path(sys.argv[3]).glob(f"stacks-{pid}.*.txt")):
        print(f"{stack.name} last written {max(0, time.time() - stack.stat().st_mtime):.3f}s ago")
