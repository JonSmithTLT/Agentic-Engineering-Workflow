#!/usr/bin/env python3
"""Structural-map generation at scale: a wall-clock measurement, run by hand (register F22.1 plan §6; design v0.5 §2.5).

    python tools/perf/structural_map.py --paths 10000,100000 --work DIR [--reps 3] [--json results.json]

For each size it builds a synthetic repository in one ``git fast-import`` (files over four levels of directories, a
``package.json`` and a ~12 KiB ``.gitattributes`` beside every 25th file, so the metadata caps are reached), then
generates its structural map in-process and checks its freshness against the same commit, ``--reps`` times each.
It reports the median wall time, the git processes started (``profile`` counts), the metadata bytes read and the
record's size.

This is a measurement, not a gate: the CI regression (``tests/regression/test_structural_map_scale.py``) asserts the
counts, never a time. The 1,000,000-path point is not measured, and AEW claims no very-large-repository support beyond
the measured 100,000 paths (design v0.5 §2.5).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from aew import profile  # noqa: E402
from aew.maps import freshness as F  # noqa: E402
from aew.maps import service  # noqa: E402
from aew.maps.canonical import seal  # noqa: E402

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0  # subprocess.CREATE_NO_WINDOW: never a console window
ATTRIBUTES = b"".join(b"gen%04d/** linguist-generated\n" % i for i in range(400))  # ~12 KiB


def build(repo: Path, paths: int) -> None:
    """A synthetic repository with ``paths`` source files (plus one descriptor pair per 25 of them), on ``main``."""
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, capture_output=True, timeout=120,
                   stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    out = [b"commit refs/heads/main\ncommitter AEW Perf <aew-perf@invalid> 0 +0000\ndata 7\nsynthe\n"]

    def add(path: str, data: bytes) -> None:
        out.append(b"M 100644 inline %s\ndata %d\n%s\n" % (path.encode(), len(data), data))

    for i in range(paths):
        add(f"m{i % 37:02d}/s{(i // 37) % 11:02d}/x{(i // 407) % 5}/deep{i % 3}/f{i:06d}.py", b"x = 1\n")
        if i % 25 == 0:
            add(f"p{i:06d}/package.json", b'{"name": "p%d", "main": "index.js"}' % i)
            add(f"p{i:06d}/sub/.gitattributes", ATTRIBUTES)
    subprocess.run(["git", "fast-import", "--quiet"], cwd=repo, input=b"".join(out), check=True, capture_output=True,
                   timeout=1800, creationflags=NO_WINDOW)


def measure(repo: Path, reps: int) -> dict[str, Any]:
    times, fresh_times, counts, record = [], [], {}, None
    for _ in range(reps):
        profile.start()
        started = time.perf_counter()
        record = service.build(repo, "main")
        times.append(time.perf_counter() - started)
        counts = (profile.stop() or {}).get("counts", {})
        sha, _ = seal(record)
        F.clear_cache()
        started = time.perf_counter()
        F.freshness(repo, {**record, "artifact_sha256": sha}, "main", service.identity())
        fresh_times.append(time.perf_counter() - started)
    assert record is not None
    _, data = seal(record)
    return {"tracked_paths": record["limits"]["tracked_paths"]["seen"],
            "generate_s_median": round(statistics.median(times), 3),
            "freshness_s_median": round(statistics.median(fresh_times), 3),
            "git_processes": counts.get("git", 0), "metadata_bytes_read": record["limits"]["metadata_bytes"]["read"],
            "metadata_capped": record["limits"]["metadata_bytes"]["capped"], "record_bytes": len(data),
            "directory_rows": len(record["sections"]["directories"]["rows"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paths", default="10000,100000", help="comma-separated repository sizes (source files)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--work", help="where to build the repositories (default: a temporary directory)")
    ap.add_argument("--json", dest="json_out", help="also write the results here")
    args = ap.parse_args()
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="aew-map-perf-"))
    results = []
    for n in (int(x) for x in args.paths.split(",")):
        repo = work / f"repo-{n}"
        build(repo, n)
        results.append({"paths": n, **measure(repo, args.reps)})
        print(json.dumps(results[-1]))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"schema": "aew/perf-structural-map/v1", "results": results},
                                                  indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
