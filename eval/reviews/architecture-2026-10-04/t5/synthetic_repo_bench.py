"""Synthetic large-repository benchmark for the structural map (semantic-map thread S7).

  python synthetic_repo_bench.py WORKDIR --files 10000 [--files 100000] [--probe PATH/codebase_map_probe.py]

Builds a git repository with N tracked files in a realistic shape (depth-3 directory tree, a mix of .c/.h/.py/.md/.json,
small contents), commits it, then times the T5 structural generator (`codebase_map_probe.py`, Git-object based, no
imports) against it, plus the two primitives everything scales on: `git ls-tree -r` and `git diff --name-status`
between two commits that touch a small fraction of the files. Prints one line per size. Scratch only; nothing else is
touched. The C/C++ semantic cost is extrapolated separately from the measured per-TU cost (S1), not benchmarked here.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import time
from pathlib import Path

EXTS = [".c", ".h", ".py", ".md", ".json", ".yaml", ".txt"]
TOP = ["src", "lib", "include", "tests", "docs", "tools", "third_party", "cmd", "pkg", "internal"]


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def build_repo(root: Path, n: int, seed: int = 7) -> None:
    rnd = random.Random(seed)
    root.mkdir(parents=True)
    git("init", "-q", cwd=root)
    git("config", "user.email", "bench@local", cwd=root)
    git("config", "user.name", "bench", cwd=root)
    git("config", "gc.auto", "0", cwd=root)  # no background gc: it holds the object dir open during cleanup
    dirs = []
    for top in TOP:
        for i in range(max(1, n // 400)):
            for j in range(3):
                dirs.append(Path(top) / f"mod{i:03d}" / f"part{j}")
    for k in range(n):
        d = root / dirs[k % len(dirs)]
        d.mkdir(parents=True, exist_ok=True)
        ext = rnd.choice(EXTS)
        (d / f"f{k:06d}{ext}").write_text(f"// file {k}\n" if ext in (".c", ".h") else f"# file {k}\n")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "base", cwd=root)
    # a second commit touching 0.5% of files (half modified, half added) for the freshness primitive
    files = git("ls-files", cwd=root).split()
    for f in rnd.sample(files, max(1, n // 400)):
        (root / f).write_text("changed\n")
    for k in range(max(1, n // 400)):
        (root / "src" / f"new{k:05d}.c").write_text("// new\n")
    git("add", "-A", cwd=root)
    git("commit", "-q", "-m", "change", cwd=root)


def timeit(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir", type=Path)
    ap.add_argument("--files", type=int, action="append", required=True)
    ap.add_argument("--probe", type=Path, default=Path(__file__).with_name("codebase_map_probe.py"))
    a = ap.parse_args()
    for n in a.files:
        root = a.workdir / f"synth-{n}"
        if root.exists():
            subprocess.run(["rm", "-rf", str(root)], check=True)
        t_build = timeit(lambda: build_repo(root, n))
        head = git("rev-parse", "HEAD", cwd=root).strip()
        base = git("rev-parse", "HEAD~1", cwd=root).strip()
        t_lstree = timeit(lambda: git("ls-tree", "-r", "--name-only", "--full-tree", head, cwd=root))
        t_diff = timeit(lambda: git("diff", "--name-status", base, head, cwd=root))
        t_diff_adr = timeit(lambda: git("diff", "--name-status", "--diff-filter=ADR", base, head, cwd=root))
        out = root.parent / f"map-{n}.yaml"
        t_probe = timeit(lambda: subprocess.run([sys.executable, str(a.probe), str(root), "--no-imports", "--repeat", "1",
                                                 "--out", str(out)], capture_output=True, text=True, check=True))
        size = out.stat().st_size
        print(f"files={n:>7,}  build {t_build:6.1f}s | ls-tree {t_lstree*1000:7.0f} ms | diff --name-status "
              f"{t_diff*1000:6.0f} ms | diff ADR-only {t_diff_adr*1000:6.0f} ms | structural map (no imports) "
              f"{t_probe*1000:7.0f} ms, {size:,} bytes", flush=True)
        subprocess.run(["rm", "-rf", str(root)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
