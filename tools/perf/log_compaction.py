"""ADR-0012's git-cost criterion: ``git status`` on a 60,000-revision transition log, before and after compaction.

Usage::

    python tools/perf/log_compaction.py WORKDIR [--revisions 60000] [--runs 15] [--json OUT.json]

Builds, in WORKDIR (which must not exist), a git repository whose ``.aew`` holds a store with ``--revisions``
chained transition records (``tests/helpers/log_fixture.py``: real record shapes, one overflow sidecar every 500
revisions) and commits it. It then times ``git status`` (median of ``--runs`` after one warm-up), runs the
compaction primitive behind the real 4,096-revision window, times ``git status`` with the compaction uncommitted
(the one-off cost), commits it, and times ``git status`` again (the steady state the criterion is about: at most
0.15 s on the reference machine). Not a test: no lane runs it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/helpers"))

from log_fixture import extend_log  # noqa: E402
from store_model import init, make_store  # noqa: E402

from aew.engine import log_compact, outbox  # noqa: E402

NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, **NO_WINDOW).stdout


def time_status(repo: Path, runs: int) -> dict[str, Any]:
    git("status", "--porcelain", cwd=repo)  # warm-up: the index and the OS caches
    samples = []
    for _ in range(runs):
        t = time.perf_counter()
        git("status", "--porcelain", cwd=repo)
        samples.append(time.perf_counter() - t)
    return {"median_s": round(statistics.median(samples), 4), "min_s": round(min(samples), 4),
            "max_s": round(max(samples), 4), "runs": runs}


def count_log_files(aew: Path) -> int:
    return sum(1 for _ in (aew / outbox.LOG_DIR).iterdir())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", type=Path)
    ap.add_argument("--revisions", type=int, default=60_000)
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    repo = a.workdir
    repo.mkdir(parents=True)
    git("init", "-q", cwd=repo)
    for key, value in (("user.name", "AEW perf"), ("user.email", "perf@example.invalid"),
                       ("core.autocrlf", "false"), ("commit.gpgsign", "false")):
        git("config", key, value, cwd=repo)
    (repo / "README.md").write_text("# log compaction fixture\n", encoding="utf-8")
    aew = repo / ".aew"
    report: dict[str, Any] = {"revisions": a.revisions, "git": git("--version", cwd=repo).strip(),
                              "platform": sys.platform}

    t = time.perf_counter()
    init(aew)
    extend_log(aew, a.revisions, overflow_every=500)
    report["build_s"] = round(time.perf_counter() - t, 1)
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "fixture: uncompacted log", cwd=repo)
    report["log_files_before"] = count_log_files(aew)
    report["status_before"] = time_status(repo, a.runs)

    t = time.perf_counter()
    result = log_compact.compact(make_store(aew))
    report["compact_s"] = round(time.perf_counter() - t, 1)
    report["compact"] = {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}
    report["log_files_after"] = count_log_files(aew)
    report["status_after_uncommitted"] = time_status(repo, max(3, a.runs // 5))
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "fixture: compacted log", cwd=repo)
    report["status_after"] = time_status(repo, a.runs)
    report["criterion_met"] = report["status_after"]["median_s"] <= 0.15

    text = json.dumps(report, indent=2)
    print(text)
    if a.json:
        a.json.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
