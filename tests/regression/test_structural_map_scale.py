"""Scale regression for the structural map (register F22.1; design v0.5 §2.5; plan §6). Timing-free and CI-safe.

A synthetic 10,000-path repository, built in one ``git fast-import``, against a 100-path one: the counts must not grow
with the repository. Git processes are counted through ``profile.count``, the same counter the one-shot runner uses
(the batch reader counts its one process too), so spawning per file would show. Metadata bytes, the record's size and
the directory rows stay within their caps. The wall-clock figures (10k, 100k) are a ``tools/perf`` measurement by hand
(PR B), never a gate here, by the strategy doc's rule against wall-clock assertions."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from aew import profile
from aew.maps import freshness as F
from aew.maps import service, structural
from aew.maps.canonical import seal

IS_WINDOWS = sys.platform == "win32"
SMALL, LARGE = 100, 10_000


def fast_import(repo: Path, paths: int) -> None:
    """``paths`` files over 3-4 levels of directories, a package.json and a ~12 KiB .gitattributes in many of them."""
    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, capture_output=True, **kw)
    out = [b"commit refs/heads/main\ncommitter AEW Test <aew-test@invalid> 0 +0000\ndata 7\nsynthe\n"]

    def add(path: str, data: bytes) -> None:
        out.append(b"M 100644 inline %s\ndata %d\n%s\n" % (path.encode(), len(data), data))

    attributes = b"".join(b"gen%04d/** linguist-generated\n" % i for i in range(400))  # ~12 KiB
    descriptors = 0
    for i in range(paths):
        a, b, c = i % 37, (i // 37) % 11, (i // 407) % 5
        directory = f"m{a:02d}/s{b:02d}/x{c}/deep{i % 3}"
        add(f"{directory}/f{i:05d}.py", b"x = 1\n")
        if i % 25 == 0 and descriptors < paths // 25:
            descriptors += 1
            add(f"p{i:05d}/package.json", b'{"name": "p%d", "main": "index.js"}' % i)
            add(f"p{i:05d}/sub/.gitattributes", attributes)
    subprocess.run(["git", "fast-import", "--quiet"], cwd=repo, input=b"".join(out), check=True, capture_output=True,
                   **kw)


def measured(repo: Path) -> tuple[dict[str, int], dict[str, int], dict[str, Any]]:
    profile.start()
    try:
        record = service.build(repo, "main")
    finally:
        generation = profile.stop() or {}
    sha, data = seal(record)
    profile.start()
    try:
        F.clear_cache()
        assert F.freshness(repo, {**record, "artifact_sha256": sha}, "main", service.identity())["status"] == "CURRENT"
    finally:
        fresh = profile.stop() or {}
    return generation["counts"], fresh["counts"], {"record": record, "bytes": len(data)}


def test_structural_generation_starts_a_constant_number_of_git_processes_and_stays_bounded(tmp_path):
    fast_import(tmp_path / "small", SMALL)
    fast_import(tmp_path / "large", LARGE)
    small_gen, small_fresh, _ = measured(tmp_path / "small")
    large_gen, large_fresh, large = measured(tmp_path / "large")
    git_counts = {k: v for k, v in large_gen.items() if k.startswith("git")}
    assert git_counts == {k: v for k, v in small_gen.items() if k.startswith("git")}, (small_gen, large_gen)
    assert git_counts["git:cat-file"] == 1 and git_counts["git"] <= 5, git_counts  # one batch process, not per file
    assert large_fresh == small_fresh and large_fresh["git"] <= 4, large_fresh
    record = large["record"]
    assert record["limits"]["tracked_paths"]["seen"] == LARGE + 2 * (LARGE // 25)
    assert record["limits"]["metadata_bytes"]["read"] <= structural.METADATA_LIMIT
    assert record["limits"]["metadata_bytes"]["capped"] is True  # 400 x 12 KiB of .gitattributes: the cap holds
    directories = record["sections"]["directories"]
    assert len(directories["rows"]) == structural.CAPS["directories"] and directories["rows_omitted"] > 0
    assert large["bytes"] < 400_000, large["bytes"]  # bounded by the caps, whatever the repository's size
    assert len(json.dumps(record["inputs"])) < 200_000
