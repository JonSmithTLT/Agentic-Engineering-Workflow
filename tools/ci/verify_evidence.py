"""Verify downloaded lane artifacts against the hosted job's observed conclusion."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from check_assurance import evidence_problems


def github_jobs() -> list[dict]:
    endpoint = (f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                f"/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}/jobs?per_page=100")
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)["jobs"]


def checker_twins(root: Path) -> list[str]:
    """Every state rule is negated on a copy of the downloaded artifact, with a specific expected defect."""
    failures = []
    for rule in ("inventory", "label", "writer", "false-timeout", "false-stack"):
        with tempfile.TemporaryDirectory() as temporary:
            twin = Path(temporary) / "twin"
            shutil.copytree(root, twin)
            inventories = list(twin.rglob("inventory.txt"))
            if not inventories:
                return ["download has no inventory for checker ablations"]
            inventory = inventories[0]
            target = inventory.parent / "hang-ablated-123.txt"
            if rule == "inventory":
                for path in inventories:
                    path.unlink()
            elif rule == "label":
                target.write_text("armed now; not fired\n")
            elif rule == "writer":
                (inventory.parent / "unknown-writer.txt").write_text("unregistered writer\n")
            elif rule == "false-timeout":
                target.write_text("was still running after 600s\n")
                with inventory.open("a") as output:
                    output.write(f"armed-placeholder {target.name} (watchdog)\n")
            else:
                target.write_text("every thread's stack:\n")
                with inventory.open("a") as output:
                    output.write(f"armed-placeholder {target.name} (watchdog)\n")
            defects = evidence_problems(twin)
            if not defects:
                failures.append(f"{rule}: ablated twin survived")
            print(f"checker twin {rule}: {defects}")
    return failures


def main(root: Path) -> int:
    jobs = github_jobs()
    failures = []
    rows = []
    for job in jobs:
        match = re.fullmatch(r"plant \(([^,]+), ([^,]+), ([^)]+)\)", job["name"])
        if not match:
            continue
        runner, kind, ablate = match.groups()
        platform = "Windows" if runner == "windows-latest" else "Linux"
        prefix = f"plant-{platform}-{kind}-{ablate}-attempt-{os.environ['GITHUB_RUN_ATTEMPT']}"
        paths = [path for path in root.iterdir() if path.name.startswith(prefix)]
        lane_step = next((step for step in job.get("steps", []) if step["name"] == "Real planted lane"), None)
        if not paths or not lane_step or not lane_step.get("started_at"):
            failures.append(f"{job['name']}: plant did not start or artifacts missing")
            continue
        with tempfile.TemporaryDirectory() as temporary:
            merged = Path(temporary)
            for path in paths:
                shutil.copytree(path, merged / path.name)
            needs_stack = kind in {"deadline", "time-limit", "hang"}
            defects = evidence_problems(merged, kind=kind, require_stacks=needs_stack)
            if ablate == "stacks":
                if not any("no stack" in defect for defect in defects):
                    failures.append(f"{job['name']}: stacks ablation survived: {defects}")
            elif defects:
                failures.extend(f"{job['name']}: {defect}" for defect in defects)
            expected = "success" if kind == "normal" else "failure"
            if job["conclusion"] != expected or lane_step["conclusion"] != expected:
                failures.append(f"{job['name']}: plant misfired: {job['conclusion']}, {lane_step['conclusion']}")
            if kind == "normal":
                failures.extend(checker_twins(merged))
            rows.append(f"| {platform} | {kind} | {ablate} | {job['conclusion']} | {defects} |")
    if len(rows) != 15:
        failures.append(f"expected 15 plants, observed {len(rows)}")
    print("\n".join(rows + failures))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write("| platform | plant | ablation | job conclusion | evidence defects |\n"
                         "|---|---|---|---|---|\n" + "\n".join(rows + failures))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
