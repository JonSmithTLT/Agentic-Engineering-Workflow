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
from threading import Thread
from typing import BinaryIO
from uuid import uuid4

import worker_evidence

HELPERS = Path(__file__).resolve().parents[2] / "tests" / "helpers"
sys.path.insert(0, str(HELPERS))
import bounds  # noqa: E402
import proctree  # noqa: E402
from evidence_files import WATCHDOG_HEADER as HEADER  # noqa: E402
from evidence_files import open_observation, stacks_ablated  # noqa: E402
from session_deadline import SUPERVISOR_CUTOFF_EXIT, marker, session_directories  # noqa: E402
from session_deadline import collect_leftovers as collect  # noqa: E402
from session_deadline import recorded_processes as identities  # noqa: E402

CUTOFF_CLEARANCE_S = bounds.CUTOFF_CLEARANCE_S
CUTOFF_GRACE_S = bounds.SESSION_END_MARGINS * bounds.DEADLINE_MARGIN_S + CUTOFF_CLEARANCE_S
POLL_S = 0.25
SPY_TIMEOUT_S = 3  # one bounded request per live worker; the cutoff reserves this per worker
HEARTBEAT = re.compile(rb"evidence-heartbeat ([0-9]+) ([0-9.]+)")
GIL_ENTER = re.compile(rb"evidence-gil-enter ([0-9.]+)")


def note(directory: Path, name: str, text: str) -> None:
    try:
        with marker(directory, name).open("x", encoding="utf-8") as output:
            output.write(text)
    except FileExistsError:
        pass


def attach(pid: int, *, allow_sudo: bool = True) -> tuple[str, str] | None:
    binary = shutil.which("py-spy")
    if binary is None:
        return None
    hosted_linux = sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
    prefixes = [[], ["sudo", "-n"]] if allow_sudo and hosted_linux else [[]]
    until = time.monotonic() + SPY_TIMEOUT_S
    for prefix in prefixes:
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            result = subprocess.run([*prefix, binary, "dump", "--nonblocking", "--full-filenames", "--pid", str(pid)],
                                    capture_output=True, text=True, timeout=max(0, until - time.monotonic()),
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0 and result.stdout.strip():
                return ("sudo -n" if prefix else "unelevated"), result.stdout
    return None


def probe() -> str:
    """One proof-only probe. The target is bounded even if the runner interrupts cleanup."""
    target = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"],
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        time.sleep(0.25)  # let the probe target initialize Python before inspecting it
        result = attach(target.pid)
        return result[0] if result else "unavailable"
    finally:
        target.kill()
        target.wait(timeout=SPY_TIMEOUT_S)


def snapshot(root: Path, *, all_workers: bool = False, seen: set[tuple[int, str]] | None = None) -> None:
    captured = seen if seen is not None else set()
    known = {identity[0]: (directory, identity) for directory, identity in identities(root)}
    bases = {directory.parent.parent for directory in session_directories(root)}
    for path in (path for base in bases for path in base.glob("hang-*.txt")):
        try:
            with open_observation(path) as stream:
                header = HEADER.match(stream.readline())
            if header is None:
                continue
            node, _, limit, started = header.groups()
            pid = int(path.stem.rsplit("-", 1)[1])
            elapsed = time.monotonic() - float(started)
            out = root / "snapshots" / f"{pid}.txt"
            key = pid, started
            if (pid not in known or not proctree.same(known[pid][1])
                    or (not all_workers and (elapsed < float(limit) or key in captured))):
                continue
            if stacks_ablated():
                continue
            captured.add(key)
            out.parent.mkdir(parents=True, exist_ok=True)
            result = attach(pid)
            if result is None:
                out.with_name(f"{pid}-unavailable.txt").write_text(
                    f"evidence defect: py-spy unavailable for {node}\n", encoding="utf-8")
            else:
                with open_observation(path) as stream:
                    after = HEADER.match(stream.readline())
                if after and after.groups() == header.groups() and proctree.same(known[pid][1]):
                    worker = worker_evidence.Worker(known[pid][0], pid, known[pid][1][1], node, float(started),
                                                    float(limit))
                    worker_evidence.save_sample(root, worker, time.time(), elapsed, *result, reason="warning")
        except (OSError, ValueError):
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


def relay_heartbeat(stream: BinaryIO, observed: dict) -> None:
    """Forward stderr while retaining only the hang plant's numeric handshake."""
    with stream:
        for line in stream:
            if entered := GIL_ENTER.fullmatch(line.strip()):
                observed["entered"] = float(entered[1])
            elif beat := HEARTBEAT.fullmatch(line.strip()):
                if "entered" not in observed:
                    observed["beats_before"] = int(beat[1])
                else:
                    observed["latest_beat_after"] = float(beat[2])
            with contextlib.suppress(OSError):
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()


def record_exit(root: Path, code: int | None, peak: int | None, interrupted: list[str], *,
                lane_exit: int | None, heartbeat: dict | None) -> None:
    scope = "MemTotal minus MemAvailable, whole runner" if sys.platform == "linux" else "unavailable on Windows"
    facts = {"command_exit": code, "lane_exit": lane_exit, "step_signal": interrupted,
             "runner_memory_peak_bytes": peak, "memory_scope": scope,
             "ablation": os.environ.get("AEW_EVIDENCE_ABLATE")}
    if heartbeat is not None:
        facts["heartbeat"] = {**heartbeat, "observed_until": time.time()}
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
        if os.environ.get("GITHUB_ACTIONS") == "true":
            # Git Bash adds HOME. Keep pytest's scratch outside that inherited home on the Windows runner.
            scratch = os.environ["RUNNER_TEMP"]
            kwargs["env"] = {**os.environ, "TMPDIR": scratch, "TEMP": scratch, "TMP": scratch}
    else:
        argv = [shell, "-e", str(script)]
    watch_heartbeat = os.environ.get("AEW_EVIDENCE_PLANT") == "hang"
    if watch_heartbeat:
        kwargs["stderr"] = subprocess.PIPE
    child = subprocess.Popen(argv, **kwargs)
    heartbeat: dict | None = None
    relay = None
    if watch_heartbeat and child.stderr is not None:
        heartbeat = {}
        relay = Thread(target=relay_heartbeat, args=(child.stderr, heartbeat), daemon=True)
        relay.start()
    status = root / "runner-resources-step.txt"
    interrupted = []
    peak = memory_used()
    snapshots_seen: set[tuple[int, str]] = set()
    lane_exit = None
    def scope():
        if job:
            return {p.identity for p in job.members(command_lines=False)}
        supervisor = proctree.identity(os.getpid())
        return {p.identity for p in proctree.descendants(supervisor, proctree.table())} if supervisor else set()

    monitor = worker_evidence.Monitor(root, attach, scope)

    def forward(signum, frame):
        interrupted.append(signal.Signals(signum).name)

    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while True:
            used = memory_used()
            if used is not None:
                peak = max(used, peak or 0)
            snapshot(root, seen=snapshots_seen)
            if not interrupted:
                monitor.poll()
            cutoff_reached = time.time() >= cutoff
            if interrupted or cutoff_reached:
                if interrupted:
                    at = time.time()
                    for worker in worker_evidence.workers(root):
                        worker_evidence.record(root, worker, "interrupted", at)
                    with contextlib.suppress(OSError):
                        child.send_signal(signal.Signals[interrupted[0]])
                snapshot(root, all_workers=True)
                exit_code = 128 + signal.Signals[interrupted[0]] if interrupted else SUPERVISOR_CUTOFF_EXIT
                if not interrupted:
                    for directory, _ in identities(root):
                        note(directory, "cutoff", f"step cutoff at {time.time():.6f}\n")
                code = child.poll()
                command_status = ("Lane command was still running" if code is None
                                  else f"Lane command had exited with code {code}")
                members = job.members(command_lines=False) if job is not None else []
                status.write_text("\n".join([command_status, *[
                    f"  {proc.pid} {Path(proc.exe).name}" for proc in members]]) + "\n", encoding="utf-8")
                collect(root)
                if job is not None:
                    job.terminate(exit_code)
                with contextlib.suppress(OSError):
                    child.kill()
                child.wait(timeout=10)
                lane_exit = exit_code
                return lane_exit
            code = child.poll()
            if code is not None and (job is None or not job.pids()):
                lane_exit = 128 - code if code < 0 else code
                return lane_exit
            time.sleep(POLL_S)
    finally:
        if relay is not None:
            relay.join(timeout=1)  # the process ended; give the final buffered lines one heartbeat window
        worker_evidence.record_crashes(root)
        record_exit(root, child.poll(), peak, interrupted, lane_exit=lane_exit, heartbeat=heartbeat)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main(argv: list[str]) -> int:
    if argv == ["--probe"]:
        print(probe())
        return 0
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
        if metadata["job_status_at_collect"] == "cancelled" or os.environ.get("AEW_PYTEST_OUTCOME") == "cancelled":
            active = list(worker_evidence.workers(args.root))
            at = time.time()
            # Only attach to a live worker whose identity was sampled inside the supervisor's owned tree.
            allowed = {worker.identity for worker in active if any(
                sample.get("pid") == worker.pid and sample.get("start") == worker.start
                for sample, _ in worker_evidence.read_ring(args.root, worker))}
            worker_evidence.capture(args.root, active, lambda pid: attach(pid, allow_sudo=False),
                                    reason="cancel collection", allowed=allowed)
            for worker in active:
                worker_evidence.record(args.root, worker, "cancelled", time.time(), collect_at=at)
        worker_evidence.record_crashes(args.root)
        collect(args.root)
        print(f"evidence timing collect {time.monotonic() - started:.3f}s")
        return 0
    cutoff = float(os.environ["AEW_JOB_DEADLINE"]) + CUTOFF_GRACE_S
    early_cutoff = os.environ.get("AEW_LANE_CUTOFF_AFTER_S")
    if early_cutoff:
        cutoff = min(cutoff, time.time() + float(early_cutoff))
    return supervise(args.root, args.shell, args.script, cutoff)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
