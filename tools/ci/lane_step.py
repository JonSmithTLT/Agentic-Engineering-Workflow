"""Run a lane with an independent cutoff and collect before publication."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

HELPERS = Path(__file__).resolve().parents[2] / "tests" / "helpers"
sys.path.insert(0, str(HELPERS))
import bounds  # noqa: E402
import proctree  # noqa: E402
from evidence_files import ablated  # noqa: E402
from session_deadline import SUPERVISOR_CUTOFF_EXIT, marker, session_directories  # noqa: E402
from session_deadline import collect_leftovers as collect  # noqa: E402
from session_deadline import recorded_processes as identities  # noqa: E402

CUTOFF_CLEARANCE_S = bounds.CUTOFF_CLEARANCE_S
CUTOFF_GRACE_S = bounds.SESSION_END_MARGINS * bounds.DEADLINE_MARGIN_S + CUTOFF_CLEARANCE_S
POLL_S = 0.25
SPY_TIMEOUT_S = 3  # one bounded request per live worker; the cutoff reserves this per worker
HEADER = re.compile(r"aew hang watchdog: (.+) started ([^;]+); limit ([0-9.]+)s; not fired; monotonic ([0-9.]+)")


def note(directory: Path, name: str, text: str) -> None:
    if ablated("kind"):
        return
    try:
        with marker(directory, name).open("x", encoding="utf-8") as output:
            output.write(text)
    except FileExistsError:
        pass


def snapshot(root: Path, *, all_workers: bool = False, seen: set[tuple[int, str]] | None = None) -> None:
    captured = seen if seen is not None else set()
    known = {identity[0]: identity for _, identity in identities(root)}
    bases = {directory.parent.parent for directory in session_directories(root)}
    for path in (path for base in bases for path in base.glob("hang-*.txt")):
        try:
            header = HEADER.match(path.read_text(encoding="utf-8"))
            if header is None:
                continue
            node, _, limit, started = header.groups()
            pid = int(path.stem.rsplit("-", 1)[1])
            elapsed = time.monotonic() - float(started)
            out = root / "snapshots" / f"{pid}.txt"
            key = pid, started
            if (pid not in known or not proctree.same(known[pid])
                    or (not all_workers and (elapsed < float(limit) or key in captured))):
                continue
            if ablated("stacks"):
                continue
            captured.add(key)
            out.parent.mkdir(parents=True, exist_ok=True)
            binary = shutil.which("py-spy") or "py-spy"
            prefix = ["sudo", "-n"] if os.environ.get("AEW_PYSPY_SUDO") == "1" and sys.platform == "linux" else []
            result = subprocess.run([*prefix, binary, "dump", "--nonblocking", "--pid", str(pid)],
                                    capture_output=True, text=True, timeout=SPY_TIMEOUT_S,
                                    **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
            if result.returncode:
                # A failed attach is evidence of the missing snapshot, never a stack claim.
                out.write_text(f"snapshot unavailable for {node}: py-spy exit {result.returncode}\n", encoding="utf-8")
                continue
            out.write_text(f"snapshot {time.time():.6f} for {node}, running {elapsed:.3f}s\n" + result.stdout,
                           encoding="utf-8")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue


def memory_used() -> int | None:
    if sys.platform != "linux":
        return None
    try:
        lines = Path("/proc/meminfo").read_text().splitlines()
        fields = {line.split(":", 1)[0]: int(line.split()[1]) for line in lines}
        return (fields["MemTotal"] - fields["MemAvailable"]) * 1024
    except (OSError, ValueError, KeyError):
        return None


def record_exit(root: Path, code: int | None, peak: int | None, interrupted: list[str]) -> None:
    scope = "MemTotal minus MemAvailable, whole runner" if sys.platform == "linux" else "unavailable on Windows"
    facts = {"command_exit": code, "step_signal": interrupted,
             "runner_memory_peak_bytes": peak, "memory_scope": scope,
             "ablation": os.environ.get("AEW_EVIDENCE_ABLATE")}
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.environ.get("AEW_LANE_STEP", "step"))
    facts["job_label"] = os.environ.get("AEW_LANE_JOB_LABEL", "")
    destination = root / f"runner-resources-{name}-exit.txt"
    destination.write_text(json.dumps(facts, sort_keys=True) + "\n", encoding="utf-8")


def supervise(root: Path, shell: str, script: Path, cutoff: float) -> int:
    root.mkdir(parents=True, exist_ok=True)
    kwargs = {"stdout": sys.stdout, "stderr": sys.stderr}
    job = None
    if os.name == "nt":
        name = "aew-ci-lane-" + uuid4().hex
        job = proctree.Job(name)
        argv = [sys.executable, __file__, "_exec", name, shell, str(script)]
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        argv = [shell, "-e", str(script)]
    child = subprocess.Popen(argv, **kwargs)
    status = root / "runner-resources-step.txt"
    interrupted = []
    peak = memory_used()
    snapshots_seen: set[tuple[int, str]] = set()

    def forward(signum, frame):
        interrupted.append(signal.Signals(signum).name)
        with contextlib.suppress(OSError):
            child.send_signal(signum)

    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while True:
            used = memory_used()
            if used is not None:
                peak = max(used, peak or 0)
            snapshot(root, seen=snapshots_seen)
            if interrupted or time.time() >= cutoff:
                snapshot(root, all_workers=True)
                for directory, _ in identities(root):
                    note(directory, "cutoff", f"step cutoff at {time.time():.6f}; signal {interrupted or 'none'}\n")
                code = child.poll()
                pytest_status = "Pytest was still running" if code is None else f"Pytest had exited with code {code}"
                members = job.members(command_lines=False) if job is not None else []
                status.write_text("\n".join([pytest_status, *[
                    f"  {proc.pid} {Path(proc.exe).name}" for proc in members]]) + "\n", encoding="utf-8")
                collect(root)
                if job is not None:
                    job.terminate(SUPERVISOR_CUTOFF_EXIT)
                with contextlib.suppress(OSError):
                    child.kill()
                child.wait(timeout=10)
                return SUPERVISOR_CUTOFF_EXIT
            code = child.poll()
            if code is not None and (job is None or not job.pids()):
                return 128 - code if code < 0 else code
            time.sleep(POLL_S)
    finally:
        record_exit(root, child.poll(), peak, interrupted)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "_exec":
        proctree.Job.open(argv[1]).assign_self()
        shell = argv[2]
        if shell == "bash":
            shell = str(Path(os.environ["ProgramFiles"]) / "Git" / "bin" / "bash.exe")
        return subprocess.call([shell, "-e", argv[3]], stdout=sys.stdout, stderr=sys.stderr)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shell", default="bash")
    parser.add_argument("--script", type=Path)
    args = parser.parse_args(argv)
    if args.collect:
        started = time.monotonic()
        args.root.mkdir(parents=True, exist_ok=True)
        metadata = {"job_label": os.environ.get("AEW_LANE_JOB_LABEL", ""),
                    "job_status_at_collect": os.environ.get("AEW_LANE_JOB_STATUS", "unknown")}
        (args.root / "runner-resources-job.txt").write_text(json.dumps(metadata) + "\n", encoding="utf-8")
        collect(args.root)
        print(f"evidence timing collect {time.monotonic() - started:.3f}s")
        return 0
    cutoff = float(os.environ["AEW_JOB_DEADLINE"]) + CUTOFF_GRACE_S
    if os.environ.get("AEW_EVIDENCE_PLANT") == "time-limit":
        cutoff = time.time() + 35  # the plant's outer killer, below its 4-minute step limit
    return supervise(args.root, args.shell, args.script, cutoff)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
