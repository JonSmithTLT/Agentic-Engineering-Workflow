"""Bounded samples of the lane's pytest workers, attributed to their process identity and active test."""

from __future__ import annotations

import contextlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

import proctree
from evidence_files import FRAME, FRESH_S, PREFIX, WATCHDOG_HEADER, entries, is_link, open_observation, test_frame

RING_BYTES = 256 * 1024  # well inside the 4 MiB staging limit, including a full lane of recent samples
DROPPED = "older snapshots dropped\n"
PROOF_KINDS = {"sigkill", "worker-kill", "oom", "cancel", "time-limit-github"}


@dataclass(frozen=True)
class Worker:
    directory: Path
    pid: int
    start: int
    node: str
    began: float
    limit: float
    controller: bool = False

    @property
    def identity(self) -> tuple[int, int]:
        return self.pid, self.start


def _phase_file(path: Path) -> str:
    # These receipts have at most three short lines. A malformed evidence file must not stall signal cleanup.
    if is_link(path) or not path.is_file():
        raise ValueError("invalid worker receipt")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("invalid worker receipt")
        data = stream.read(257)
    if len(data) > 256 or not data.endswith(b"\n"):
        raise ValueError("incomplete worker receipt")
    return data.decode("ascii")


def _live_phase_writer(path: Path, pid: int, birth: int, fd: int) -> bool:
    if not proctree.same((pid, birth)):
        return False
    if sys.platform == "linux":
        return path.samefile(f"/proc/{pid}/fd/{fd}")
    return any(p.identity == (pid, birth) for p in proctree.holders([str(path)]).get(str(path), []))


def phases_at_signal(root: Path, at_ns: int) -> list[dict]:
    """Read only positive transitions from the same registered worker on this runner's monotonic clock."""
    from session_deadline import WORKER_PHASES, session_directories

    rows = []
    for directory in session_directories(root):
        for path in sorted(directory.glob("worker-gw*-pid.txt")):
            row = {"session": directory.name, "worker": path.stem.removesuffix("-pid"), "phase": "indeterminate"}
            rows.append(row)
            try:
                pid = int(_phase_file(path))
                birth = int(_phase_file(path.with_name(path.name.replace("-pid.", "-start."))))
                row.update(pid=pid, start=birth)
                receipt = directory / f"worker-{pid}-{birth}-lifecycle.txt"
                lines = _phase_file(receipt).splitlines()
                if len(lines) > len(WORKER_PHASES):
                    continue
                transitions = [(int(stamp), phase, int(fd)) for stamp, phase, fd in (line.split() for line in lines)]
                stamps = [stamp for stamp, _, _ in transitions]
                descriptors = {fd for _, _, fd in transitions}
                if (tuple(phase for _, phase, _ in transitions) != WORKER_PHASES[:len(lines)]
                        or stamps != sorted(set(stamps)) or any(stamp <= 0 or stamp == at_ns for stamp in stamps)
                        or len(descriptors) != 1 or not _live_phase_writer(receipt, pid, birth, descriptors.pop())):
                    continue
                prior = [phase for stamp, phase, _ in transitions if stamp <= at_ns]
                if prior:
                    row["phase"] = prior[-1]
            except (OSError, ValueError):
                continue
    return rows


def workers(root: Path):
    from session_deadline import marker, session_directories

    for directory in session_directories(root):
        for path in (*directory.glob("worker-*-pid.txt"), marker(directory, "controller-pid")):
            try:
                worker = path.stem.removesuffix("-pid")
                pid = int(path.read_text().strip())
                start = int(marker(directory, worker + "-start").read_text().strip())
                gateway = "main" if worker == "controller" else worker.removeprefix("worker-")
                inflight = directory.parent.parent / f"hang-{gateway}-{pid}.txt"
                with open_observation(inflight) as stream:
                    header = WATCHDOG_HEADER.match(stream.readline())
                if header:
                    yield Worker(directory, pid, start, header[1], float(header[4]), float(header[3]),
                                 controller=worker == "controller")
            except (OSError, ValueError):
                continue


def ring_path(root: Path, worker: Worker) -> Path:
    return root / "snapshots" / f"{worker.pid}.txt"


def save_sample(root: Path, worker: Worker, at: float, elapsed: float, method: str, dump: str, *, reason: str) -> bool:
    # py-spy's process header can include argv. Only stack frames enter the scanned publication path.
    frames = [match[0] for line in dump.splitlines() if (match := FRAME.match(line))]
    if not frames:
        return False
    row = {"at": at, "utc": datetime.fromtimestamp(at, UTC).isoformat(),
           "pid": worker.pid, "start": worker.start, "node": worker.node,
           "test_began": worker.began, "running_s": round(elapsed, 3), "via": method, "reason": reason}
    if os.environ.get("AEW_EVIDENCE_PLANT") in PROOF_KINDS and os.environ.get("AEW_EVIDENCE_ABLATE") == "unlabelled":
        row.pop("node")
    header = PREFIX + json.dumps(row, ensure_ascii=True) + "\n"
    body = header.encode() + ("\n".join(frames) + "\n").encode("utf-8", errors="replace")
    limit = RING_BYTES - len(DROPPED)
    if len(body) > limit:
        body = body[:limit - 30].rsplit(b"\n", 1)[0] + b"\nremaining frames truncated\n"
    path = ring_path(root, worker)
    if is_link(root):
        return False
    path.parent.mkdir(exist_ok=True)
    if is_link(path.parent):
        return False
    prior = b""
    with contextlib.suppress(FileNotFoundError):
        if is_link(path) or not path.is_file():
            return False
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags | getattr(os, "O_BINARY", 0)), "rb") as old:
            if not stat.S_ISREG(os.fstat(old.fileno()).st_mode):
                return False
            size = old.seek(0, os.SEEK_END)
            old.seek(max(0, size - RING_BYTES))
            prior = old.read(RING_BYTES)
    combined = prior + body
    if len(combined) > RING_BYTES:
        tail = combined[-limit:]
        boundary = tail.find(b"\n" + PREFIX.encode())
        combined = DROPPED.encode() + (tail[boundary + 1:] if boundary >= 0 else body)
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as temp:
        temp.write(combined)
    pending = Path(temp.name)
    try:
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)
    return True


def read_ring(root: Path, worker: Worker):
    try:
        path = ring_path(root, worker)
        if is_link(root) or is_link(path.parent) or is_link(path) or not path.is_file():
            return []
        with path.open("rb") as source:
            return list(entries(source.read(RING_BYTES).decode("utf-8", errors="replace")))
    except OSError:
        return []


def record(root: Path, worker: Worker, kind: str, at: float, **facts) -> None:
    from session_deadline import marker

    samples = [row for row, _ in read_ring(root, worker) if row.get("start") == worker.start
               and isinstance(row.get("at"), (float, int)) and row["at"] <= at]
    last = samples[-1] if samples else {}
    row = {"kind": kind, "at": at, "pid": worker.pid, "start": worker.start, "node": worker.node,
           "alive_when_observed": proctree.same(worker.identity), "snapshot_node": last.get("node"),
           "snapshot_at": last.get("at"), "age_s": round(at - last["at"], 3) if last else None, **facts}
    path = marker(worker.directory, f"{kind}-{worker.pid}")
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=True) + "\n")
    except FileExistsError:
        pass


def cgroup(pid: int | str = "self") -> Path | None:
    """Resolve the v2 group in this process's mount namespace, including a delegated mount root."""
    try:
        membership = next(line[3:] for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                          if line.startswith("0::"))
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            if " - cgroup2 " not in line:
                continue
            fields = line.split()
            mount, group_root = Path(fields[4]), Path(fields[3])
            group = Path(membership)
            if group.is_relative_to(group_root):
                return mount / group.relative_to(group_root)
    except (OSError, IndexError, StopIteration):
        pass
    return None


def memory(group: Path) -> tuple[int, int, int] | None:
    try:
        current = int((group / "memory.current").read_text())
        raw = (group / "memory.max").read_text().strip()
        if raw == "max":
            host = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
            limit = int(host["MemTotal"].split()[0]) * 1024
            current = limit - int(host["MemAvailable"].split()[0]) * 1024
        else:
            limit = int(raw)
        events = dict(line.split() for line in (group / "memory.events").read_text().splitlines())
        return current, limit, int(events["oom_kill"])
    except (OSError, ValueError, KeyError):
        return None


def top_rss(observed: list[Worker]) -> list[dict]:
    rows = []
    for worker in observed:
        if not proctree.same(worker.identity):
            continue
        try:
            status = Path(f"/proc/{worker.pid}/status").read_text().splitlines()
            rss = next(int(line.split()[1]) for line in status if line.startswith("VmRSS:"))
            rows.append({"pid": worker.pid, "rss_kib": rss, "node": worker.node})
        except (OSError, ValueError, StopIteration):
            continue
    return sorted(rows, key=lambda row: -row["rss_kib"])[:10]


def ablated(mode: str) -> bool:
    return os.environ.get("AEW_EVIDENCE_PLANT") in PROOF_KINDS and os.environ.get("AEW_EVIDENCE_ABLATE") == mode


def capture(root: Path, observed: list[Worker], attach, *, reason: str, allowed) -> set[tuple[int, int]]:
    # A slow or inaccessible worker cannot multiply the pre-cleanup wait by the number of workers.
    # All attaches have their own three-second subprocess cutoff. After this common window expires,
    # queued workers are skipped; four concurrent readers bound the runner load.
    until = time.monotonic() + 3

    def sample(worker: Worker):
        if time.monotonic() >= until or worker.identity not in allowed or not proctree.same(worker.identity):
            return None
        warning = reason == "warning"
        last = None
        failures = []
        matched = False
        for attempt in range(3 if warning else 1):
            if warning and (worker not in workers(root) or not proctree.same(worker.identity)):
                return None
            remaining = until - time.monotonic()
            if remaining <= 0:
                if attempt == 0:
                    return None
                break
            at = time.time()
            elapsed = time.monotonic() - worker.began
            result = attach(worker.pid, timeout=remaining, failures=failures) if warning else attach(worker.pid)
            # A stack straddling a test boundary has no trustworthy node label.
            if worker not in workers(root) or not proctree.same(worker.identity):
                return None
            if result:
                # Nonblocking dumps may omit a live Python frame. Retry only
                # this invocation inside the original shared pre-signal budget.
                if warning and not FRAME.search(result[1]):
                    failures.append(f"{result[0]}: dump has no Python frames")
                    continue
                last = (at, elapsed, result)
                if not warning or test_frame(worker.node, result[1]):
                    matched = True
                    break
                failures.append(f"{result[0]}: dump has no active test frame")
        if warning and not matched:
            path = ring_path(root, worker).with_name(f"{worker.pid}-unavailable.txt")
            message = f"evidence defect: py-spy unavailable for {worker.node}"
            if last is not None:
                path = path.with_name(f"{worker.pid}-{worker.start}-warning-attach.txt")
                message = f"py-spy sampled support frames for {worker.node}"
            with contextlib.suppress(OSError):
                if is_link(root):
                    return None
                path.parent.mkdir(exist_ok=True)
                if not is_link(path.parent):
                    try:
                        output = path.open("x", encoding="utf-8")
                    except FileExistsError:
                        # An earlier timeout snapshot may already have recorded a failure for this PID.
                        output = path.with_name(f"{worker.pid}-{worker.start}-warning-unavailable.txt").open(
                            "x", encoding="utf-8")
                    with output:
                        attempts = f" (attempts: {'; '.join(failures)})" if failures else ""
                        output.write(f"{message}{attempts}\n")
        if last is None:
            return None
        # Retain a support-only stack as evidence of what was actually running.
        # The normal checker still reports a missing live test frame.
        at, elapsed, result = last
        with contextlib.suppress(OSError):
            if save_sample(root, worker, at, elapsed, result[0], result[1], reason=reason):
                return worker.identity
        return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        return {identity for identity in pool.map(sample, observed) if identity is not None}


def dmesg_victim() -> int | str:
    """Only read the last kernel message and retain a numeric victim, never raw kernel lines."""
    try:
        result = subprocess.run(["dmesg", "--level=err", "--since=-1min"], capture_output=True,
                                timeout=1, check=True)
        hits = re.findall(rb"\bKilled process (\d+) ", result.stdout)
        return int(hits[-1]) if hits else "no victim reported"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def controller_loss(root: Path) -> None:
    from session_deadline import ABNORMAL, marker

    for worker in workers(root):
        abnormal = marker(worker.directory, ABNORMAL)
        if abnormal.is_file():
            # The sentinel observes controller loss independently. 137 alone cannot identify the cause.
            record(root, worker, "controller-lost", abnormal.stat().st_mtime, source="sentinel abnormal-exit")


def record_oom(root: Path) -> None:
    from session_deadline import session_directories

    try:
        event = json.loads((root / "runner-resources-oom.txt").read_text())
    except (OSError, ValueError):
        return
    candidates = []
    for directory in session_directories(root):
        for path in directory.glob("worker-killed-*.txt"):
            try:
                fact = json.loads(path.read_text(encoding="utf-8"))
                if ([fact["pid"], fact["start"]] in event["members"] and abs(fact["at"] - event["at"]) <= 5
                        and fact["signal"] in (None, 9)):
                    candidates.append((directory, fact))
            except (OSError, ValueError, KeyError, TypeError):
                continue
    victim = event.get("kernel_victim")
    if isinstance(victim, int):
        candidates = [(directory, row) for directory, row in candidates if row["pid"] == victim]
    elif victim == "no matching worker":
        return
    # Multiple simultaneous crashes in a group cannot be assigned to one counter increment.
    # Preserve its group event and the independent xdist crash records without guessing a victim.
    if len(candidates) == 1:
        directory, row = candidates[0]
        worker = Worker(directory, row["pid"], row["start"], row["node"], 0, 0)
        scope = ("cgroup increase and matching PID in recent kernel messages" if isinstance(victim, int)
                 else "only observed worker crash near the cgroup increase")
        record(root, worker, "oom", row["at"], scope=scope)


class Monitor:
    def __init__(self, root: Path, attach, scope):
        self.root = root
        self.attach = attach
        self.scope = scope
        self.next_sample = {}
        self.next_poll = 0.
        plant = os.environ.get("AEW_EVIDENCE_PLANT")
        mode = os.environ.get("AEW_WORKER_SNAPSHOTS")
        # The hosted cancellation control exercises the production switch.
        proof = plant in PROOF_KINDS and (plant != "cancel" or mode is None)
        self.periodic = (proof or mode in {"1", "xdist"}) and not ablated("ring")
        self.xdist_only = mode == "xdist" and not proof
        self.interval = FRESH_S - 3  # one bounded attach before the 60s freshness boundary, including in proof lanes
        self.group = cgroup() if sys.platform == "linux" else None
        proof_group = os.environ.get("AEW_PROOF_OOM_GROUP")
        if proof_group and os.environ.get("AEW_EVIDENCE_PLANT") == "oom":
            self.group = Path(proof_group)
        before = memory(self.group) if self.group else None
        self.last_kills = before[2] if before else None
        self.members = set()
        self.high = False
        self.pressure_seen = False

    def poll(self, *, final: bool = False) -> None:
        now = time.monotonic()
        if not final and now < self.next_poll:
            return
        self.next_poll = now + 1
        reading = memory(self.group) if self.group else None
        high = bool(reading and reading[1] > 0 and reading[0] >= .85 * reading[1])
        if reading and self.last_kills is not None and reading[2] > self.last_kills:
            victim = dmesg_victim()
            if isinstance(victim, int) and victim not in {pid for pid, _ in self.members}:
                victim = "no matching worker"
            event = {"oom_kill_before": self.last_kills, "oom_kill_after": reading[2], "at": time.time(),
                     "kernel_victim": victim, "members": sorted(self.members), "pressure_seen": self.pressure_seen}
            (self.root / "runner-resources-oom.txt").write_text(json.dumps(event) + "\n", encoding="utf-8")
        if reading:
            self.last_kills = reading[2]
        if final:
            return
        crossed = high and not self.high
        self.high = high
        observed = list(workers(self.root)) if self.periodic or crossed else []
        if not observed:
            if crossed:
                self.high = False  # the first worker can still see pressure that began during startup
            return
        due = [w for w in observed if self.periodic and not (self.xdist_only and w.controller)
               and now >= self.next_sample.get(w.identity, 0)]
        if not crossed and not due:
            return
        allowed = self.scope()
        observed = [w for w in observed if w.identity in allowed]
        if self.group:
            self.members.update(w.identity for w in observed if cgroup(w.pid) == self.group)
        if crossed and observed:
            self.pressure_seen = True
            peak = {"at": time.time(), "used_bytes": reading[0], "limit_bytes": reading[1]}
            if not ablated("trigger"):
                peak["top_workers"] = top_rss(observed)
                capture(self.root, observed, self.attach, reason="memory pressure", allowed=allowed)
            (self.root / "runner-resources-high-water.txt").write_text(json.dumps(peak) + "\n", encoding="utf-8")
        due = [w for w in due if w.identity in allowed]
        if due:
            sampled = capture(self.root, due, self.attach, reason="periodic", allowed=allowed)
            for w in due:
                self.next_sample[w.identity] = now + (self.interval if w.identity in sampled else min(5, self.interval))
