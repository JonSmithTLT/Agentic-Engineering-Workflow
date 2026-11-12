#!/usr/bin/env python3
"""Run a failed CI test alone once and write evidence for independent assurance."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import flake_register  # noqa: E402

LANE_SCHEMA = "aew/lane-report/v1"
RERUN_SCHEMA = "aew/flake-rerun/v1"
PLATFORMS = {"linux": "linux", "win32": "windows"}
EVIDENCE_LIMIT = 3
MARKERS = frozenset({"session-deadline", "abnormal-exit", "stuck-after-finish", "left-running", "sentinel-backstop"})


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, encoding="utf-8",
                          timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                          ).stdout  # noqa: S603, S607


def tip_register() -> dict[str, Any]:
    git("fetch", "--no-tags", "--depth=1", "origin", "refs/heads/main")
    revision = git("rev-parse", "--verify", "FETCH_HEAD^{commit}").strip()

    def source(path: str) -> str | None:
        try:
            return git("show", f"{revision}:{path}")
        except subprocess.CalledProcessError:
            return None

    return flake_register.load_register(git("show", f"{revision}:tests/flake-register.yaml"), source=source)


def changed_paths(event: str, revision: str) -> set[str]:
    if event != "pull_request":
        return set()
    # Verify the merge parent, so a missing parent in a shallow checkout fails closed.
    parent = git("rev-parse", "--verify", f"{revision}^1").strip()
    return set(git("diff", "--no-renames", "--name-only", "-z", parent, revision, "--").split("\0")) - {""}


def entries(register: dict[str, Any], platform: str, lane: str, node: str | None) -> list[str]:
    return [row["id"] for row in register["entries"]
            if row["status"] == "open" and PLATFORMS.get(platform) in row["platforms"]
            and (row["scope"] == "session" and fnmatchcase(lane, row["lane"]) if node is None
                 else row["scope"] == "test" and row["lane"] == lane and row["test"] == node)]


def marker_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / "autopsy").glob("session-*/*.txt") if p.stem in MARKERS)


def failed_tests(report: dict[str, Any]) -> list[str]:
    return sorted(nid for nid, result in report["results"].items() if result["outcome"] in ("failed", "error"))


def report_identity(report: dict[str, Any]) -> dict[str, Any]:
    return {key: report.get(key) for key in ("platform", "lane", "shard", "attempt")}


def eligible(report: dict[str, Any], folder: Path) -> bool:
    return (report.get("schema") == LANE_SCHEMA and report.get("exitstatus") == 1
            and report.get("session_problems") == [] and not marker_files(folder))


def rerun_root(report: Path) -> Path:
    return report.parent / f"{report.stem}-reruns"


def passed(record: dict[str, Any], report: dict[str, Any], node: str, directory: Path) -> bool:
    return (record.get("schema") == RERUN_SCHEMA and record.get("lane_report") == report_identity(report)
            and record.get("platform") == report["platform"] and record.get("exitstatus") == 0
            and record.get("process_exit") == 0 and record.get("session_problems") == []
            and record.get("collected") == [node] and record.get("results") == {node: "passed"}
            and not marker_files(directory))


def test_path(node: str) -> str:
    path, separator, _ = node.partition("::")
    parts = PurePosixPath(path).parts
    if (not separator or not parts or parts[0] != "tests" or ".." in parts or "\\" in path
            or not path.endswith(".py")):
        raise ValueError(f"invalid test node {node!r}")
    return path


def run_once(report: dict[str, Any], node: str, folder: Path, deadline: float, coverage: bool) -> bool:
    # The session sentinel also caps itself at the absolute job deadline. The subprocess bound covers startup
    # and cleanup even if pytest cannot install its sentinel.
    remaining = math.floor(deadline - time.time())
    if remaining <= 0:
        print(f"{node}: not re-run (budget)")
        return False
    folder.mkdir(parents=True, exist_ok=False)
    output = folder / "result.json"
    wrapper = ["coverage", "run", "-m", "pytest"] if coverage else ["pytest"]
    command = [sys.executable, "-m", *wrapper, "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
               "--test-timeout", "600", "--session-deadline", str(remaining), f"--hang-dir={folder}",
               f"--rerun-report={output}", "--", node]
    try:
        child = subprocess.run(command, check=False, stdin=subprocess.DEVNULL, timeout=remaining,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))  # noqa: S603
    except subprocess.TimeoutExpired:
        print(f"{node}: re-run exceeded the job deadline")
        return False
    if not output.is_file():
        print(f"{node}: re-run wrote no evidence")
        return False
    record = json.loads(output.read_text(encoding="utf-8"))
    record.update(lane_report=report_identity(report), process_exit=child.returncode)
    output.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return passed(record, report, node, folder)


def evidence_candidates(unknown: list[str], enabled: bool) -> list[str]:
    return unknown[:EVIDENCE_LIMIT] if enabled else []


def decide(path: Path, outcome: str, event: str, revision: str, coverage: bool, evidence: bool) -> int:
    if outcome == "success":
        return 0
    if outcome != "failure" or not path.is_file():
        print(f"Lane {outcome} without a usable failure report")
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    if not eligible(report, path.parent) or report.get("platform") != sys.platform:
        return 1
    failures = failed_tests(report)
    if not failures or any(n not in report["collected"] for n in failures):
        return 1
    paths = {node: test_path(node) for node in failures}
    changed = changed_paths(event, revision)
    register = tip_register()
    known = {node: entries(register, report["platform"], report["lane"], node)
             for node in failures if paths[node] not in changed}
    deadline = float(os.environ["AEW_JOB_DEADLINE"])
    if not math.isfinite(deadline):
        raise ValueError("invalid job deadline")
    unknown = [node for node in failures if not known.get(node) and paths[node] not in changed]
    all_passed = all(known.get(node) for node in failures)
    for node in failures:
        if paths[node] in changed:
            print(f"{node}: test file changed by this pull request")
    for index, node in enumerate([n for n in failures if known.get(n)] + evidence_candidates(unknown, evidence)):
        result = run_once(report, node, rerun_root(path) / str(index), deadline, coverage)
        status = "passed alone" if result else "did not pass alone"
        note = f" ({', '.join(known[node])})" if known.get(node) else " (evidence only)"
        print(f"{node}: {status}{note}")
        all_passed = all_passed and result
    return int(not all_passed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcome", required=True, choices=("success", "failure", "skipped", "cancelled"))
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--evidence", action="store_true")
    args = parser.parse_args(argv)
    try:
        return decide(args.report, args.outcome, os.environ.get("GITHUB_EVENT_NAME", ""),
                      os.environ.get("GITHUB_SHA", "HEAD"), args.coverage, args.evidence)
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Flake re-run refused: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
