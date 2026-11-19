"""Publish evidence defects separately from the test verdict."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_assurance import evidence_problems  # noqa: E402
from flake_register import _gh_read, _pages  # noqa: E402


def check_jobs(root: Path, jobs: list[dict]) -> list[str]:
    defects = []
    for job in jobs:
        if job.get("conclusion") in {"success", "skipped", None}:
            continue
        found = []
        for path in root.iterdir() if root.is_dir() else ():
            labels = []
            for record in path.glob("runner-resources-*.txt"):
                try:
                    data = json.loads(record.read_text())
                    if isinstance(data, dict):
                        labels.append(data.get("job_label"))
                except (ValueError, OSError):
                    continue
            digest = path / "job-label-sha256.txt"
            named = digest.is_file() and digest.read_text().strip() == hashlib.sha256(job["name"].encode()).hexdigest()
            if job["name"] in labels or named:
                found.append(path)
        for path in list(found):
            if path.name.endswith("-running"):
                found.extend(sibling for sibling in root.glob(path.name.removesuffix("-running") + "*")
                             if sibling not in found)
        started = bool(found) or any(
            step.get("started_at") and ("pytest" in step["name"] or "/lane" in step["name"])
            for step in job.get("steps", []))
        if not started:
            continue
        if not found:
            defects.append(f"evidence defect: {job['name']}: no published evidence")
            continue
        # Priority and full bundles are each checked; names in either can identify a running test.
        with tempfile.TemporaryDirectory() as temporary:
            import shutil

            merged = Path(temporary)
            for path in found:
                shutil.copytree(path, merged / path.name)
            reports = []
            for path in merged.rglob("*.json"):
                if "autopsy" not in path.parts:
                    reports.append(json.loads(path.read_text()))
            command_exits = []
            for path in merged.rglob("runner-resources-*-exit.txt"):
                record = json.loads(path.read_text())
                command_exits.append(record.get("command_exit"))
                if record.get("ablation") is not None:
                    defects.append(f"evidence defect: {job['name']}: ablation enabled in a real lane")
            died = (any(report.get("exitstatus") not in (0, 1) for report in reports)
                    or any(code not in (0, 1) for code in command_exits)
                    or (not reports and not command_exits))
            markers = {path.stem for path in merged.rglob("*.txt")}
            kind = "deadline" if "session-deadline" in markers else "time-limit" if "cutoff" in markers else None
            if died and kind is None and job.get("conclusion") != "cancelled":
                defects.append(f"evidence defect: {job['name']}: death has no kind marker")
            defects.extend(f"{job['name']}: {problem}" for problem in evidence_problems(
                merged, kind=kind, require_stacks=died and kind is not None))
    return defects


def main(root: Path) -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    jobs = list(_pages(repo, f"actions/runs/{run}/attempts/{attempt}/jobs?per_page=100", "jobs"))
    problems = check_jobs(root, jobs)
    text = "\n".join(problems) or "Published evidence states match their recorded contents."
    payload = {"name": "evidence", "head_sha": os.environ["GITHUB_SHA"], "status": "completed",
               "conclusion": "failure" if problems else "success",
               "output": {"title": f"{len(problems)} evidence defects", "summary": text}}
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "check.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        _gh_read("--method", "POST", f"repos/{repo}/check-runs", "--input", str(path))
    print(text)
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
