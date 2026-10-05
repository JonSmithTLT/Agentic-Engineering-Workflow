#!/usr/bin/env python3
"""Commit-to-waiter wake latency across two processes (ADR-0012 D4; ledger OBX-37: median under 50 ms).

A waiter process blocks on the wake file the way ``aew harness wait --any`` does (``outbox.wait_for``: a stat of
``local/wake`` every 25 ms, a coarse re-check every 2 s); this process makes N commits at random intervals. For each
commit the latency is the waiter's wake time minus the moment the commit started (an upper bound: it includes the
commit's own cost) and minus the moment it returned (the wake signal's own delay). The clocks are the same machine's
wall clock in both processes.

    python tools/perf/wake_latency.py [--commits 60] [--json]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from aew.engine.api import Engine  # noqa: E402
from aew.engine.store import Transition  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
WAITER = """
import sys, time
sys.path.insert(0, {src!r})
from pathlib import Path
from aew.engine import outbox
root, n = Path({root!r}), {n}
print("ready", flush=True)
for _ in range(n):
    start = outbox.wake_mark(root)
    if outbox.wait_for(lambda: outbox.wake_mark(root) != start, root, timeout=30):
        print(time.time_ns(), flush=True)
    else:
        print("timeout", flush=True)
"""


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, creationflags=NO_WINDOW)


def project(root: Path) -> Engine:
    git("init", "-q", "-b", "main", cwd=root)
    git("config", "user.name", "AEW perf", cwd=root)
    git("config", "user.email", "aew-perf@invalid", cwd=root)
    (root / "README.md").write_text("perf\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "initial", cwd=root)
    Engine.initialize(root, project_id="wake-perf")
    return Engine.discover(root)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commits", type=int, default=60)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="aew-wake-") as tmp:
        root = Path(tmp) / "p"
        root.mkdir()
        eng = project(root)
        aew_root = root / ".aew"
        waiter = subprocess.Popen(
            [sys.executable, "-c", WAITER.format(src=str(ROOT / "src"), root=str(aew_root), n=args.commits)],
            stdout=subprocess.PIPE, text=True, creationflags=NO_WINDOW)
        assert waiter.stdout is not None
        assert waiter.stdout.readline().strip() == "ready"
        rng = random.Random(1)
        from_start, from_return = [], []
        for i in range(args.commits):
            time.sleep(rng.uniform(0.08, 0.2))  # the waiter is idle and blocked between commits
            t0 = time.time_ns()
            with eng.store.session() as s:
                s.commit(Transition(op="perf.wake", actor={"kind": "test"}, summary=f"wake {i}"))
            t1 = time.time_ns()
            line = waiter.stdout.readline().strip()
            if line == "timeout":
                raise SystemExit(f"commit {i}: the waiter never woke")
            woke = int(line)
            from_start.append((woke - t0) / 1e6)
            from_return.append((woke - t1) / 1e6)
        waiter.wait(timeout=30)
    result = {"commits": args.commits, "platform": sys.platform,
              "median_ms_from_commit_start": round(statistics.median(from_start), 1),
              "p90_ms_from_commit_start": round(statistics.quantiles(from_start, n=10)[-1], 1),
              "median_ms_from_commit_return": round(statistics.median(from_return), 1),
              "budget_ms": 50}
    result["within_budget"] = result["median_ms_from_commit_start"] < 50
    print(json.dumps(result, indent=None if args.json else 2))
    return 0 if result["within_budget"] else 1


if __name__ == "__main__":
    sys.exit(main())
