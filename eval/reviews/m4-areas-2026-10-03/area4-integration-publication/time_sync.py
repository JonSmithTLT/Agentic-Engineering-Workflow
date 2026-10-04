"""How long does the locked finalization's worktree sync hold the control lock for N changed paths?

    venv/Scripts/python repro/time_sync.py 1000 3000

Pollers (run supervisors, the Lead broker watchdog) read control state with a 60 s lock timeout.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import _env  # noqa: F401
from conftest import git, make_git_repo

from aew.workspace import integration as I


def build(n: int) -> tuple[Path, str, str]:
    root = Path(tempfile.mkdtemp(prefix="aew-sync-")) / "repo"
    repo = make_git_repo(root, {f"src/d{i % 50}/f{i}.txt": f"v1 {i}\n" for i in range(n)})
    h = git("rev-parse", "HEAD", cwd=repo)
    for i in range(n):
        (repo / f"src/d{i % 50}/f{i}.txt").write_text(f"v2 {i}\n", encoding="utf-8", newline="\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "v2", cwd=repo)
    m = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", h, cwd=repo)      # worktree back at H, as before a publish
    git("update-ref", "refs/heads/main", h, cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    return repo, h, m


def main() -> None:
    for n in [int(x) for x in sys.argv[1:]] or [1000]:
        repo, h, m = build(n)
        paths = I.changed_between(repo, h, m)
        t0 = time.perf_counter()
        I.precheck_sync(repo, h, paths)
        t1 = time.perf_counter()
        git("update-ref", "refs/heads/main", m, h, cwd=repo)
        t2 = time.perf_counter()
        I.sync_worktree(repo, h, m, paths)
        t3 = time.perf_counter()
        print(f"n={n}: precheck {t1 - t0:.1f}s, sync {t3 - t2:.1f}s, locked total ~{(t1 - t0) + (t3 - t2):.1f}s")


if __name__ == "__main__":
    main()
