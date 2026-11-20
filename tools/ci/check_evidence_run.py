"""Publish evidence defects separately from the test verdict."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import yaml
from evidence_problems import evidence_problems

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _gh_read, _pages  # noqa: E402


def check_jobs(root: Path, jobs: list[dict]) -> list[str]:
    defects = []

    def report(rule: str, detail: str) -> None:
        defects.append(f"evidence defect: [{rule}] {job['name']}: {detail}")

    workflows = Path(__file__).resolve().parents[2] / ".github/workflows"
    action = "./.github/actions/lane"
    names = {f"Run {action}"}
    for workflow in workflows.glob("*.yml"):
        for job in yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"].values():
            names.update(step["name"] for step in job.get("steps", [])
                         if "name" in step and step.get("uses") == action)
    patterns = [re.compile("^" + ".+?".join(re.escape(part) for part in re.split(r"\$\{\{.*?\}\}", name)) + "$")
                for name in names]
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
            step.get("started_at") and step.get("conclusion") != "skipped"
            and any(pattern.fullmatch(step["name"]) for pattern in patterns)
            for step in job.get("steps", []))
        if not started:
            continue
        if not found:
            report("job-evidence", "no published evidence")
            continue
        # Priority and full bundles are each checked; names in either can identify a running test.
        with tempfile.TemporaryDirectory() as temporary:
            merged = Path(temporary)
            for path in found:
                shutil.copytree(path, merged / path.name)
            reports = []
            for bundle in found:
                if bundle.name.endswith("-running"):
                    lane_report = root / ("lane-report-" + bundle.name.removesuffix("-running"))
                    for path in lane_report.glob("*.json"):
                        try:
                            data = json.loads(path.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            continue  # collection can leave an incomplete report; use the other observations
                        if isinstance(data, dict) and "exitstatus" in data:
                            reports.append(data)
            command_exits = []
            for path in merged.rglob("runner-resources-*-exit.txt"):
                record = json.loads(path.read_text())
                command_exits.append(record.get("command_exit"))
                if record.get("ablation") not in (None, "none"):
                    report("job-ablation", "ablation enabled in a real lane")
            died = (any(report.get("exitstatus") not in (0, 1) for report in reports)
                    or any(code not in (0, 1) for code in command_exits)
                    or (not reports and not command_exits))
            markers = {path.stem for path in merged.rglob("*.txt")}
            kind = "deadline" if "session-deadline" in markers else "time-limit" if "cutoff" in markers else None
            if died and kind is None and job.get("conclusion") != "cancelled":
                report("job-kind", "death has no kind marker")
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
    payload = {"name": "evidence", "head_sha": os.environ["EVIDENCE_HEAD"], "status": "completed",
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
