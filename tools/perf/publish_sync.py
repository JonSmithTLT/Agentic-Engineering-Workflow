#!/usr/bin/env python3
"""How long a publish holds the control lock for its checkout steps, by changed-path count (register E34, note 9).

    python tools/perf/publish_sync.py --work DIR [--paths 100,1000,5000] [--reps 3] [--json results.json]

A publish runs ``precheck_sync``, the compare-and-swap and ``sync_worktree`` inside the control lock (ADR-0004), so
their cost grows with the number of paths the candidate changes. For each count N this builds, in a new directory
under ``--work``, a repository with N tracked files at H and a candidate M that changes all of them, then times the
engine's own functions on the authoritative checkout: ``precheck_sync`` (classify), ``cas_publish`` and
``sync_worktree`` (classify, write, verify convergence). Reported per N: the median of each step and per path.
Only the directory the run created is removed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from aew.workspace import integration as I  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          creationflags=NO_WINDOW).stdout.strip()


def build(root: Path, n: int) -> tuple[Path, str, str]:
    repo = root / f"repo-{n}"
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=repo)
    for k, v in (("user.name", "perf"), ("user.email", "perf@invalid"), ("core.autocrlf", "false")):
        git("config", k, v, cwd=repo)
    for i in range(n):
        f = repo / "src" / f"d{i // 500:03d}" / f"f{i:05d}.txt"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"file {i}\n", encoding="utf-8", newline="\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "H", cwd=repo)
    h = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", "-b", "candidate", cwd=repo)
    for f in (repo / "src").rglob("*.txt"):
        f.write_text(f.read_text(encoding="utf-8") + "changed\n", encoding="utf-8", newline="\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "M", cwd=repo)
    m = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    return repo, h, m


def once(repo: Path, h: str, m: str) -> dict[str, float]:
    git("update-ref", "refs/heads/main", h, cwd=repo)
    git("reset", "-q", "--hard", h, cwd=repo)
    paths = I.changed_between(repo, h, m)
    t0 = time.perf_counter()
    I.precheck_sync(repo, h, paths)
    t1 = time.perf_counter()
    I.cas_publish(repo, "refs/heads/main", m, h, "perf publish")
    t2 = time.perf_counter()
    I.sync_worktree(repo, h, m, paths)
    t3 = time.perf_counter()
    return {"precheck_s": t1 - t0, "cas_s": t2 - t1, "sync_s": t3 - t2, "total_s": t3 - t0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--paths", default="100,1000,5000")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="aew-publish-sync-", dir=a.work))
    results = []
    try:
        for n in (int(x) for x in a.paths.split(",")):
            repo, h, m = build(root, n)
            runs = [once(repo, h, m) for _ in range(a.reps)]
            med = {k: statistics.median(r[k] for r in runs) for k in runs[0]}
            row = {"paths": n, **{k: round(v, 3) for k, v in med.items()},
                   "per_path_ms": round(1000 * med["total_s"] / n, 3)}
            results.append(row)
            print(json.dumps(row), flush=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if a.json:
        a.json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
