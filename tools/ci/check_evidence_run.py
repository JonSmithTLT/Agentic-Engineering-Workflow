"""Publish evidence defects separately from the test verdict."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_assurance import evidence_problems  # noqa: E402
from cost_record import JOB_NAME  # noqa: E402
from flake_register import _gh_read, _pages  # noqa: E402
from tier import FAST_LANES  # noqa: E402


def check_jobs(root: Path, jobs: list[dict]) -> list[str]:
    defects = []
    for job in jobs:
        match = JOB_NAME.match(job["name"])
        if not match or job.get("conclusion") in {"success", "skipped", None}:
            continue
        started = any(step.get("started_at") and step["name"].startswith(("fast lane", "serial lane", "pytest --lane"))
                      for step in job.get("steps", []))
        if not started:
            continue
        fields = match.groupdict()
        platform = "Windows" if fields["os"].startswith("windows") else "Linux"
        core = "core-" if fields["lane"] in FAST_LANES else ""
        shard = (fields["shard"] or "1/1").split("/")[0]
        prefix = f"evidence-lane-report-{platform}-{core}{fields['lane']}-{shard}-"
        found = [path for path in root.glob(prefix + "*") if not path.name.endswith("-running")]
        if not found:
            defects.append(f"evidence defect: {job['name']}: no published evidence")
            continue
        # Priority and full bundles are each checked; names in either can identify a running test.
        with tempfile.TemporaryDirectory() as temporary:
            import shutil

            merged = Path(temporary)
            for path in root.glob(prefix + "*"):
                shutil.copytree(path, merged / path.name)
            reports = []
            for path in merged.rglob("*.json"):
                if "autopsy" not in path.parts:
                    reports.append(json.loads(path.read_text()))
            died = not reports or any(report.get("exitstatus") not in (0, 1) for report in reports)
            markers = {path.stem for path in merged.rglob("*.txt")}
            kind = "deadline" if "session-deadline" in markers else "time-limit" if "cutoff" in markers else None
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
