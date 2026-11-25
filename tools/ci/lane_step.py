"""Run a lane with an independent cutoff and collect before publication."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import functools
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

HELPERS = Path(__file__).resolve().parents[2] / "tests" / "helpers"
sys.path.insert(0, str(HELPERS))
import bounds  # noqa: E402
import proctree  # noqa: E402
import worker_evidence  # noqa: E402
from evidence_files import CANCEL_COLLECTION, HOST_STOP_FILE, WARNING, open_observation, stacks_ablated  # noqa: E402
from evidence_files import WATCHDOG_HEADER as HEADER  # noqa: E402
from session_deadline import (  # noqa: E402
    HOST_RESOURCES_EXIT,
    SUPERVISOR_CUTOFF_EXIT,
    marker,
    session_directories,
    session_job,
)
from session_deadline import collect_leftovers as collect  # noqa: E402
from session_deadline import recorded_processes as identities  # noqa: E402
from watchdog import running_names  # noqa: E402

CUTOFF_CLEARANCE_S = bounds.CUTOFF_CLEARANCE_S
CUTOFF_GRACE_S = bounds.SESSION_END_MARGINS * bounds.DEADLINE_MARGIN_S + CUTOFF_CLEARANCE_S
POLL_S = 0.25
SPY_TIMEOUT_S = 3  # one bounded request per live worker; the cutoff reserves this per worker
HEARTBEAT = re.compile(rb"evidence-heartbeat ([0-9]+) ([0-9.]+)")
GIL_ENTER = re.compile(rb"evidence-gil-enter ([0-9.]+)")
# The Windows host's resources (register E3). Windows regression jobs have been lost with every in-VM timer silent;
# the leading suspect is the host running out of something the lane's tests use. Each limit stops the lane while the
# runner can still publish, and is an estimate set well past the highest of the first observed peaks, so that only a
# runaway trips it. Those peaks, over the 17 Windows regression and integration jobs of CI run 45431850900 (#546 at
# 3c33bbda): commit 8.3 GiB, 44% of the smallest commit limit seen (integration 10/14, job 138579271173), 58,422
# handles and 187 processes (integration 11/14, job 138579271198), and at least 142.9 GiB free (integration 1/14, job
# 138579271016). Every Windows lane's exit record and step log carry its peaks, which is how a limit is recalibrated.
HOST_POLL_S = 1.0  # GetPerformanceInfo walks the process list: once a second, as the cgroup monitor polls
HOST_COMMIT_FRACTION = 0.92  # at the commit limit, process creation and heap growth fail with no Python trace;
# 8% of the limit (over a GiB on a hosted runner) is left for the capture and the publication steps. The limit is the
# current one: the runner's pagefile grows (the limit ran from 18.9 to 20.5 GiB across those jobs), so this can stop
# before the host would truly run out
HOST_HANDLES = 1_000_000  # system-wide; handles come from paged pool. About 17 times the observed peak
HOST_PROCESSES = 1_000  # each CREATE_NO_WINDOW child also gets a conhost, and every process in the service session
# takes desktop heap, whose exhaustion fails a new process at start (0xc0000142, as M4-B saw). About 5 times the
# observed peak; where desktop heap actually runs out is not known
HOST_FREE_DISK = 2 * 1024 ** 3  # the scanned bundles are staged and zipped on this drive before upload


class _PerformanceInformation(ctypes.Structure):
    # PERFORMANCE_INFORMATION (psapi.h): the sizes are in pages, the counts are whole numbers.
    _fields_ = [("cb", ctypes.c_uint32), *((name, ctypes.c_size_t) for name in (
        "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable", "SystemCache",
        "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")),
        ("HandleCount", ctypes.c_uint32), ("ProcessCount", ctypes.c_uint32), ("ThreadCount", ctypes.c_uint32)]


def note(directory: Path, name: str, text: str) -> None:
    try:
        with marker(directory, name).open("x", encoding="utf-8") as output:
            output.write(text)
    except FileExistsError:
        pass


def attach(pid: int, *, allow_sudo: bool = True, timeout: float = SPY_TIMEOUT_S,
           failures: list[str] | None = None) -> tuple[str, str] | None:
    binary = shutil.which("py-spy")
    if binary is None:
        if failures is not None:
            failures.append("py-spy executable missing")
        return None
    hosted_linux = sys.platform == "linux" and os.environ.get("GITHUB_ACTIONS") == "true"
    prefixes = [[], ["sudo", "-n"]] if allow_sudo and hosted_linux else [[]]
    until = time.monotonic() + min(SPY_TIMEOUT_S, timeout)
    for prefix in prefixes:
        via = "sudo -n" if prefix else "unelevated"
        try:
            # A malformed byte in a diagnostic must not abort the lane supervisor's sampling loop.
            result = subprocess.run([*prefix, binary, "dump", "--nonblocking", "--full-filenames", "--pid", str(pid)],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=max(0, until - time.monotonic()),
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0 and result.stdout.strip():
                return via, result.stdout
            if failures is not None:
                # py-spy can include the target's command line in diagnostics. Keep only its exit and OS error codes.
                code = re.search(r"\bos error ([0-9]{1,10})\b", result.stderr or "")
                outcome = f"exit {result.returncode}" if result.returncode else "empty dump"
                failures.append(f"{via}: {outcome}" + (f" (os error {code[1]})" if code else ""))
        except subprocess.TimeoutExpired:
            if failures is not None:
                failures.append(f"{via}: timed out")
        except OSError as exc:
            if failures is not None:
                failures.append(f"{via}: launch error {exc.errno}")
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
                    worker_evidence.save_sample(root, worker, time.time(), elapsed, *result, reason=WARNING)
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


@functools.cache
def _psapi_performance_info():
    return ctypes.WinDLL("psapi", use_last_error=True).GetPerformanceInfo  # loaded once, on the first Windows read


def _performance_info(call=None) -> _PerformanceInformation | None:
    info = _PerformanceInformation()
    info.cb = ctypes.sizeof(info)
    try:
        return info if (call or _psapi_performance_info())(ctypes.pointer(info), info.cb) else None
    except (OSError, AttributeError):
        return None


def host_reading(call=None) -> dict | None:
    """The Windows host's commit charge, handles, processes and free scratch space, or None off Windows."""
    if os.name != "nt":
        return None
    info = _performance_info(call)
    if info is None:
        return None
    page = info.PageSize
    reading = {"commit_bytes": info.CommitTotal * page, "commit_limit_bytes": info.CommitLimit * page,
               "physical_available_bytes": info.PhysicalAvailable * page, "kernel_paged_bytes": info.KernelPaged * page,
               "kernel_nonpaged_bytes": info.KernelNonpaged * page, "handles": info.HandleCount,
               "processes": info.ProcessCount, "threads": info.ThreadCount}
    with contextlib.suppress(OSError, KeyError):
        reading["free_disk_bytes"] = shutil.disk_usage(os.environ["RUNNER_TEMP"]).free
    return reading


def host_crossed(reading: dict) -> list[dict]:
    """Each stated limit the reading has reached, named with its value."""
    crossed = []
    limit = reading["commit_limit_bytes"] * HOST_COMMIT_FRACTION
    if reading["commit_limit_bytes"] and reading["commit_bytes"] >= limit:
        crossed.append({"resource": "commit_bytes", "value": reading["commit_bytes"], "limit": int(limit)})
    for resource, bound in (("handles", HOST_HANDLES), ("processes", HOST_PROCESSES)):
        if reading[resource] >= bound:
            crossed.append({"resource": resource, "value": reading[resource], "limit": bound})
    if reading.get("free_disk_bytes", HOST_FREE_DISK) < HOST_FREE_DISK:
        crossed.append({"resource": "free_disk_bytes", "value": reading["free_disk_bytes"], "limit": HOST_FREE_DISK})
    return crossed


def host_peak(peak: dict | None, reading: dict) -> dict:
    """The high-water mark of each reading, the low-water mark of free disk."""
    if peak is None:
        return dict(reading)
    worst = {key: (min if key in {"free_disk_bytes", "physical_available_bytes"} else max)(peak.get(key, value), value)
             for key, value in reading.items()}
    return {**peak, **worst}


def running_tests(root: Path) -> list[str]:
    """The tests the watchdog says are running (its own reader, so the stop names what the publication names)."""
    return sorted(set(running_names(Path(os.environ.get("AEW_RUNNING_TESTS_DIR") or root)).values()))


def record_host_stop(root: Path, reading: dict, crossed: list[dict], peak: dict | None) -> None:
    facts = {"at": time.time(), "crossed": crossed, "reading": reading, "peak": peak,
             "running_tests": running_tests(root), "exit": HOST_RESOURCES_EXIT}
    (root / HOST_STOP_FILE).write_text(json.dumps(facts, sort_keys=True) + "\n", encoding="utf-8")
    print(f"lane step: stopped for the host's resources: {json.dumps(crossed)}", flush=True)


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


def interrupt_phases(root: Path, at_ns: int) -> dict:
    result = {"monotonic_ns": at_ns, "status": "unavailable"}

    def read():
        with contextlib.suppress(OSError):
            rows = worker_evidence.phases_at_signal(root, at_ns)
            result.update(status="observed", registered_workers=rows)

    reader = Thread(target=read, daemon=True)
    try:
        reader.start()
    except RuntimeError:
        return result
    reader.join(timeout=POLL_S)  # at most one normal supervisor polling interval before cleanup
    return result.copy()


def record_exit(root: Path, code: int | None, peak: int | None, interrupted: list[str], *,
                lane_exit: int | None, heartbeat: dict | None, worker_phases: dict | None = None,
                host: dict | None = None) -> None:
    scope = "MemTotal minus MemAvailable, whole runner" if sys.platform == "linux" else "unavailable on Windows"
    facts = {"command_exit": code, "lane_exit": lane_exit, "step_signal": interrupted,
             "runner_memory_peak_bytes": peak, "memory_scope": scope,
             "ablation": os.environ.get("AEW_EVIDENCE_ABLATE")}
    if worker_phases is not None:
        facts["xdist_at_first_signal"] = worker_phases
    if host is not None:
        facts["host_resources_peak"] = host
        print(f"lane step: host resources peak {json.dumps(host, sort_keys=True)}", flush=True)
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

    def scope():
        if job:
            return {p.identity for p in job.members(command_lines=False)}
        supervisor = proctree.identity(os.getpid())
        return {p.identity for p in proctree.descendants(supervisor, proctree.table())} if supervisor else set()

    # Before the lane starts, so its recorded sampling policy is written before any worker can reach the root (E3).
    monitor = worker_evidence.Monitor(root, attach, scope)
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
    host: dict | None = None
    next_host = 0.
    snapshots_seen: set[tuple[int, str]] = set()
    lane_exit = None

    signal_at = None
    worker_phases = None

    def forward(signum, frame):
        nonlocal signal_at
        if signal_at is None:
            signal_at = time.monotonic_ns()
        interrupted.append(signal.Signals(signum).name)

    previous = {sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        while True:
            used = memory_used()
            if used is not None:
                peak = max(used, peak or 0)
            if not interrupted:
                snapshot(root, seen=snapshots_seen)
            crossed = []
            if time.monotonic() >= next_host:
                next_host = time.monotonic() + HOST_POLL_S
                if (reading := host_reading()) is not None:
                    host = host_peak(host, reading)
                    crossed = [] if interrupted else host_crossed(reading)
                    if crossed:
                        record_host_stop(root, reading, crossed, host)
            cutoff_reached = time.time() >= cutoff
            if not interrupted and not cutoff_reached and not crossed:
                monitor.poll()
            if interrupted or cutoff_reached or crossed:
                before_signal = interrupted and sys.platform == "linux" and os.name != "nt"
                if interrupted:
                    at = time.time()
                    active = list(worker_evidence.workers(root))
                    if before_signal and active:
                        alive = {worker.identity: proctree.same(worker.identity) for worker in active}
                        if not stacks_ablated():
                            worker_evidence.capture(root, active, attach, reason=WARNING, allowed=scope(),
                                                    collect_at=at)
                        for worker in active:
                            worker_evidence.record(root, worker, "interrupted", time.time(),
                                                   collect_at=at, alive_when_observed=alive[worker.identity])
                    else:
                        for worker in active:
                            worker_evidence.record(root, worker, "interrupted", at)
                    # Windows' Popen.send_signal takes only SIGTERM and the console events: SIGINT raises
                    # ValueError there. The lane's job is ended below, after the collection, either way.
                    with contextlib.suppress(OSError, ValueError):
                        child.send_signal(signal.Signals[interrupted[0]])
                if not before_signal:
                    snapshot(root, all_workers=True)
                exit_code = (128 + signal.Signals[interrupted[0]] if interrupted
                             else HOST_RESOURCES_EXIT if crossed else SUPERVISOR_CUTOFF_EXIT)
                if not interrupted and not crossed:
                    for directory, _ in identities(root):
                        note(directory, "cutoff", f"step cutoff at {time.time():.6f}\n")
                elif interrupted:
                    worker_phases = interrupt_phases(root, signal_at)
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
        monitor.poll(final=True)
        worker_evidence.record_oom(root)
        code = child.poll()
        observed_signals = interrupted.copy()
        if observed_signals and worker_phases is None:
            worker_phases = {"monotonic_ns": signal_at, "status": "unavailable"}
        record_exit(root, code, peak, observed_signals, lane_exit=lane_exit, heartbeat=heartbeat,
                    worker_phases=worker_phases, host=host)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def in_session_job(worker: worker_evidence.Worker) -> bool:
    """Whether the job the lane step named for this worker's session holds the worker's identity now."""
    with session_job(worker.directory, named_by_lane=True) as job:
        return job is not None and job.holds(worker.identity)


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
        cancelled = (metadata["job_status_at_collect"] == "cancelled"
                     or os.environ.get("AEW_PYTEST_OUTCOME") == "cancelled")
        step_ended = os.environ.get("AEW_LANE_RECOVERY_OUTCOME") in {"failure", "cancelled"}
        if cancelled or step_ended:
            active = list(worker_evidence.workers(args.root))
            at = time.time()
            # Liveness is decided before the capture, as the Linux supervisor decides it before its warning attach: a
            # worker that exits during the capture is still owed its stack, and its typed outcome says why there is
            # none (register E3).
            alive = {worker.identity: proctree.same(worker.identity) for worker in active}
            # Only attach to a live worker whose identity was sampled inside the supervisor's owned tree, or that its
            # session's job holds now. A hosted cancel kills the supervisor outright, so a worker born in the seconds
            # before has no periodic sample yet (integration 7/14, job 139072636221); membership is checked with the
            # OS, on the worker's identity, in the job the lane step named (register E3).
            allowed = {worker.identity for worker in active if any(
                sample.get("pid") == worker.pid and sample.get("start") == worker.start
                for sample, _ in worker_evidence.read_ring(args.root, worker))}
            admitted = {worker.identity for worker in active if worker.identity not in allowed
                        and in_session_job(worker)}
            sampled = worker_evidence.capture(args.root, active, functools.partial(attach, allow_sudo=False),
                                              reason=CANCEL_COLLECTION, allowed=allowed | admitted, collect_at=at)
            for worker in active:
                # A worker whose first dump straddled a test change is recorded for the test its retained sample
                # labels, so the observation and its stack name one test (register E3).
                held = sampled.get(worker.identity, worker)
                moved = {"straddled_from": worker.node} if held.node != worker.node else {}
                if worker.identity in admitted:
                    moved["admitted_by"] = "session job"
                worker_evidence.record(args.root, held, "cancelled" if cancelled else "interrupted",
                                       time.time(), collect_at=at, alive_when_observed=alive[worker.identity],
                                       **moved)
        worker_evidence.record_oom(args.root)
        worker_evidence.controller_loss(args.root)
        collect(args.root)
        if cancelled:
            from cancel_evidence import collect_reason

            collect_reason(args.root, metadata["job_label"])
        print(f"evidence timing collect {time.monotonic() - started:.3f}s")
        return 0
    cutoff = float(os.environ["AEW_JOB_DEADLINE"]) + CUTOFF_GRACE_S
    early_cutoff = os.environ.get("AEW_LANE_CUTOFF_AFTER_S")
    if early_cutoff:
        cutoff = min(cutoff, time.time() + float(early_cutoff))
    return supervise(args.root, args.shell, args.script, cutoff)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
