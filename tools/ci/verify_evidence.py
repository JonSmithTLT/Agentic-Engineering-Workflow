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

from evidence_problems import evidence_problems

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _gh_read  # noqa: E402

ABLATIONS = {"stacks": "no stack", "kind": "kind marker", "running": "running test name",
             "header-only": "publication state", "zero-byte": "publication state"}


def ablation_problem(rule: str, defects: list[str]) -> str | None:
    expected = ABLATIONS.get(rule)
    if expected is None or not any(expected in defect for defect in defects):
        return f"{rule} ablation survived or has no expectation: {defects}"
    return None


def github_jobs() -> list[dict]:
    endpoint = (f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                f"/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}/jobs?per_page=100")
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)["jobs"]


def checker_twins(root: Path) -> list[str]:
    """Every state rule is negated on a copy of the downloaded artifact, with a specific expected defect."""
    failures = []
    for rule in ("inventory", "inventory-label", "label", "writer", "false-timeout", "false-stack", "scan-unavailable"):
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
            elif rule == "inventory-label":
                listing = inventory.read_text(encoding="utf-8")
                inventory.write_text(listing.replace("finding inventory.txt (publisher)\n", ""), encoding="utf-8")
            elif rule == "label":
                target.write_text("armed now; not fired\n")
            elif rule == "writer":
                (inventory.parent / "unknown-writer.txt").write_text("unregistered writer\n")
            elif rule == "false-timeout":
                target.write_text("was still running after 600s\n")
                with inventory.open("a") as output:
                    output.write(f"armed-placeholder {target.name} (watchdog)\n")
            elif rule == "scan-unavailable":
                with inventory.open("a") as output:
                    output.write("gitleaks scan unavailable\n")
            else:
                target.write_text("every thread's stack:\n")
                with inventory.open("a") as output:
                    output.write(f"armed-placeholder {target.name} (watchdog)\n")
            defects = evidence_problems(twin)
            if rule == "inventory-label":
                if not any("inventory.txt: missing or false publication state" in defect for defect in defects):
                    failures.append(f"{rule}: ablated twin survived: {defects}")
            elif not defects:
                failures.append(f"{rule}: ablated twin survived")
            print(f"checker twin {rule}: {defects}")
    return failures


def death_twins(root: Path, kind: str) -> list[str]:
    failures = []
    for rule in ("stacks", "kind", "running", "running-label"):
        with tempfile.TemporaryDirectory() as temporary:
            twin = Path(temporary) / "twin"
            shutil.copytree(root, twin)
            for path in list(twin.rglob("*.txt")):
                if rule == "kind" and path.stem in {"session-deadline", "cutoff"}:
                    path.unlink()
                elif rule == "running" and path.name.startswith(("running-", "hang-")):
                    path.unlink()
                elif rule == "running-label" and path.name == "inventory.txt":
                    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
                    path.write_text("".join(line for line in lines if not line.startswith("finding running-")),
                                    encoding="utf-8")
                elif rule == "stacks":
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                    path.write_text("".join(line for line in lines
                                            if not re.search(r'File "|\([^\n]+\.py:\d+\)', line)), encoding="utf-8")
            defects = evidence_problems(twin, kind=kind, require_stacks=True)
            expected = {"stacks": "no stack", "kind": "kind marker", "running": "running test name",
                        "running-label": ".txt: missing or false publication state"}[rule]
            if not any(expected in defect for defect in defects):
                failures.append(f"{rule}: death twin survived: {defects}")
            print(f"death twin {rule}: {defects}")
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
            if ablate != "none":
                problem = ablation_problem(ablate, defects)
                if problem:
                    failures.append(f"{job['name']}: {problem}")
            elif defects:
                failures.extend(f"{job['name']}: {defect}" for defect in defects)
            expected = "success" if kind == "normal" else "cancelled" if kind == "cancel" else "failure"
            log = _gh_read(f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/jobs/{job['id']}/logs").decode(
                "utf-8", errors="replace")
            timing = re.findall(r"evidence timing ([a-z-]+) ([0-9.]+)s", log)
            if kind == "normal":
                required_times = {"prepare", "collect", "stage", "names-upload", "report-upload",
                                  "watchdog-upload", "full-upload", "after-pytest"}
                if not required_times <= {label for label, _ in timing}:
                    failures.append(f"{job['name']}: first-push post-step timings are incomplete: {timing}")
                print(f"{job['name']}: first-push timings {timing}")
            if kind == "hang":
                entered = re.findall(r"evidence-gil-enter ([0-9.]+)", log)
                beats = re.findall(r"evidence-heartbeat (\d+) ([0-9.]+)", log)
                if not entered or len(beats) < 3:
                    failures.append(f"{job['name']}: plant misfired; heartbeat handshake missing")
                elif any(float(at) > float(entered[-1]) + 1 for _, at in beats):
                    failures.append(f"{job['name']}: heartbeat kept moving; GIL plant misfired")
            expected_code = {"deadline": 70, "time-limit": 71, "sigkill": 137}.get(kind)
            if expected_code and f"Process completed with exit code {expected_code}" not in log:
                failures.append(f"{job['name']}: plant misfired; expected exit {expected_code}")
            if job["conclusion"] != expected or lane_step["conclusion"] != expected:
                failures.append(f"{job['name']}: plant misfired: {job['conclusion']}, {lane_step['conclusion']}")
            if kind == "normal":
                failures.extend(checker_twins(merged))
            elif kind == "deadline" and ablate == "none":
                failures.extend(death_twins(merged, kind))
            elif kind == "cancel":
                (merged / "cutoff.txt").write_text("step cutoff\n", encoding="utf-8")
                twin = evidence_problems(merged, kind=kind)
                if not any("cutoff marker claimed" in problem for problem in twin):
                    failures.append(f"{job['name']}: planted false cutoff survived: {twin}")
                print(f"{job['name']}: false cutoff twin: {twin}")
            rows.append(f"| {platform} | {kind} | {ablate} | [{job['conclusion']}]({job['html_url']}) | {defects} |")
    if len(rows) != 23:
        failures.append(f"expected 23 plants, observed {len(rows)}")
    print("\n".join(rows + failures))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write("| platform | plant | ablation | job conclusion | evidence defects |\n"
                         "|---|---|---|---|---|\n" + "\n".join(rows + failures))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
