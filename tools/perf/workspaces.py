#!/usr/bin/env python3
"""Mutation workspace cost at concurrency 1, 2 and 4 (M4-C; m4-ambiguity-report.md §2.5).

    python tools/perf/workspaces.py --repo PATH --work DIR [--levels 1,2,4] [--reps 3] [--json results.json]

For each level N, the engine's own ``worktrees.allocate`` creates N Ticket workspaces from the repository's HEAD
(one after another, as N assignments would), then ``worktrees.remove`` removes them. The measured repository is a
fresh local clone of ``--repo`` in a new directory this run creates under ``--work``, so the source is never
touched: the run refuses a ``--work`` that overlaps the source, and removes only the directory it created. Reported
per level: the median time to set up one workspace and to clean one up, the total for all N, and the files in one
worktree.

This records cost on the sample and AEW repositories. It is not the repository-scale benchmark (isolation §13),
which needs repositories M4 does not run on.
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

from aew.workspace import worktrees  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          creationflags=NO_WINDOW).stdout.strip()


def overlaps(a: Path, b: Path) -> bool:
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def measure(repo: Path, work: Path, levels: list[int], reps: int) -> dict:
    """``repo`` and ``work`` are resolved. Everything this run writes is under one directory it creates in ``work``,
    and only that directory is removed afterwards (the review of #47: an existing ``work/repo`` was deleted, which
    could be the source)."""
    if overlaps(repo, work):
        raise SystemExit(f"--work {work} overlaps --repo {repo}: choose a work directory outside the repository")
    run = Path(tempfile.mkdtemp(prefix="aew-wsbench-", dir=work))
    try:
        return _measure(repo, run, levels, reps)
    finally:
        shutil.rmtree(run, ignore_errors=True)


def _measure(repo: Path, work: Path, levels: list[int], reps: int) -> dict:
    clone = work / "repo"
    git("clone", "-q", "--no-hardlinks", str(repo), str(clone), cwd=work)
    head = git("rev-parse", "HEAD", cwd=clone)
    files = len(git("ls-files", cwd=clone).splitlines())
    roots = work / "ws"
    out: dict = {"repo": str(repo), "head": head, "tracked_files": files, "levels": {}}
    for n in levels:
        setup: list[float] = []
        cleanup: list[float] = []
        totals: list[float] = []
        for rep in range(reps):
            t_all = time.perf_counter()
            made = []
            for i in range(n):
                t0 = time.perf_counter()
                ws = worktrees.allocate(repo_root=clone, aew_root=clone / ".aew", workspaces_root=roots,
                                        work_id=f"T-{rep:02d}{i:02d}", attempt=1, base_commit=head,
                                        referenced_paths=set())
                setup.append(time.perf_counter() - t0)
                made.append(ws["path"])
            for path in made:
                t0 = time.perf_counter()
                worktrees.remove(clone, path)
                cleanup.append(time.perf_counter() - t0)
            totals.append(time.perf_counter() - t_all)
            for i in range(n):
                git("branch", "-q", "-D", worktrees.branch_name(f"T-{rep:02d}{i:02d}", 1), cwd=clone)
        out["levels"][str(n)] = {"setup_s": round(statistics.median(setup), 3),
                                 "cleanup_s": round(statistics.median(cleanup), 3),
                                 "total_s": round(statistics.median(totals), 3)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--levels", default="1,2,4")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    repo, work = a.repo.resolve(), a.work.resolve()
    if overlaps(repo, work):  # before anything is created
        raise SystemExit(f"--work {work} overlaps --repo {repo}: choose a work directory outside the repository")
    work.mkdir(parents=True, exist_ok=True)
    result = measure(repo, work, [int(x) for x in a.levels.split(",")], a.reps)
    text = json.dumps(result, indent=2)
    print(text)
    if a.json:
        a.json.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
