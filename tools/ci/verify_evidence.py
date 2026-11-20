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

from check_evidence_run import check_jobs
from evidence_files import FRAME, state
from evidence_problems import evidence_problems

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _gh_read  # noqa: E402

# Mutation names map to the exact rule they must trip. Multiple variants pin independent branches of one rule.
STATE_TWINS = {
    "inventory": "inventory", "inventory-label": "label", "header-only": "label", "zero-byte": "label",
    "writer-path": "writer-path", "writer-source": "writer-source", "false-timeout": "false-timeout",
    "false-fired": "false-fired", "stack-heading": "false-stack", "timeout-heading": "false-stack",
    "scan-unavailable": "scan-unavailable", "contradiction": "contradiction", "cap": "cap",
    "collection": "collection", "tools": "tools",
}
DEATH_TWINS = {"stacks": "stacks", "kind": "kind", "running": "running", "running-label": "label"}
JOB_TWINS = {"no-evidence": "job-evidence", "missing-kind": "job-kind", "live-ablation": "job-ablation"}
OTHER_TWINS = {"cancel": "false-cutoff"}


def rule_ids(defects: list[str]) -> set[str]:
    return {match[1] for defect in defects if (match := re.search(r"evidence defect: \[([a-z-]+)\]", defect))}


def expect_rule(case: str, expected: str, defects: list[str]) -> list[str]:
    return [] if expected in rule_ids(defects) else [f"{case}: {expected} ablation survived: {defects}"]


def github_jobs() -> list[dict]:
    endpoint = (f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                f"/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}/jobs?per_page=100")
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)["jobs"]


def label(inventory: Path, path: Path, writer: str, declared: str | None = None) -> None:
    actual = state(path, path.read_bytes()) if declared is None else declared
    with inventory.open("a", encoding="utf-8") as output:
        output.write(f"{actual} {path.relative_to(inventory.parent).as_posix()} ({writer})\n")


def checker_twins(root: Path) -> list[str]:
    """Mutate downloaded artifacts and require the specific rule, even if another rule also fires."""
    failures = []
    for case, expected in STATE_TWINS.items():
        with tempfile.TemporaryDirectory() as temporary:
            twin = Path(temporary) / "twin"
            shutil.copytree(root, twin)
            inventories = list(twin.rglob("inventory.txt"))
            if not inventories:
                return ["download has no inventory for checker ablations"]
            inventory = inventories[0]
            if case == "inventory":
                for path in inventories:
                    path.unlink()
            elif case == "inventory-label":
                listing = inventory.read_text(encoding="utf-8")
                inventory.write_text(listing.replace("finding inventory.txt (publisher)\n", ""), encoding="utf-8")
            elif case in {"writer-source", "scan-unavailable", "cap"}:
                with inventory.open("a", encoding="utf-8") as output:
                    output.write({"writer-source": "omitted file-a (unlisted writer)\n",
                                  "scan-unavailable": "gitleaks scan unavailable\n",
                                  "cap": "evidence defect: job cap exceeded\n"}[case])
            else:
                filename, data, writer = {
                    "header-only": ("hang-twin-123.txt", "armed now\n", "watchdog"),
                    "zero-byte": ("hang-twin-123.txt", "", "watchdog"),
                    "writer-path": ("unknown-writer.txt", "unregistered writer\n", "synthetic"),
                    "false-timeout": ("hang-twin-123.txt", "was still running after 600s\n", "watchdog"),
                    "false-fired": ("hang-twin-123.txt", "fired after 600s\n", "watchdog"),
                    "stack-heading": ("hang-twin-123.txt", "every thread's stack:\n", "watchdog"),
                    "timeout-heading": ("hang-twin-123.txt", "Timeout (0:00:01)!\n", "watchdog"),
                    "contradiction": ("hang-twin-123.txt",
                                      'armed now; not fired\n  File "test_a.py", line 2 in test_a\n', "watchdog"),
                    "collection": ("collection-incomplete.txt", "evidence defect: collection incomplete\n",
                                   "evidence_inputs"),
                    "tools": ("tools-unavailable.txt", "evidence defect: py-spy unavailable\n", "evidence_inputs"),
                }[case]
                target = inventory.parent / filename
                target.write_text(data, encoding="utf-8")
                label(inventory, target, writer, "finding" if case in {"header-only", "zero-byte"} else None)
            failures.extend(expect_rule(case, expected, evidence_problems(twin)))
    return failures


def death_twins(root: Path, kind: str, job: dict | None = None) -> list[str]:
    failures = []
    for case, expected in DEATH_TWINS.items():
        with tempfile.TemporaryDirectory() as temporary:
            twin = Path(temporary) / "twin"
            shutil.copytree(root, twin)
            for path in list(twin.rglob("*.txt")):
                if case == "kind" and path.stem in {"session-deadline", "cutoff"}:
                    path.unlink()
                elif case == "running" and path.name.startswith(("running-", "hang-")):
                    path.unlink()
                elif case in {"running-label", "stacks"}:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                    if case == "stacks":
                        path.write_text("".join(line for line in lines if not FRAME.match(line)), encoding="utf-8")
                    elif path.name == "inventory.txt":
                        path.write_text("".join(line for line in lines if not line.startswith("finding running-")),
                                        encoding="utf-8")
            defects = evidence_problems(twin, kind=kind, require_stacks=True)
            failures.extend(expect_rule(f"{kind}/{case}", expected, defects))
            if job is not None and case == "kind":
                failures.extend(expect_rule("missing-kind", JOB_TWINS["missing-kind"], check_jobs(twin, [job])))
    return failures


def job_twins(root: Path, job: dict) -> list[str]:
    with tempfile.TemporaryDirectory() as temporary:
        twin = Path(temporary) / "twin"
        twin.mkdir()
        failures = expect_rule("no-evidence", JOB_TWINS["no-evidence"], check_jobs(twin, [job]))
        shutil.copytree(root, twin, dirs_exist_ok=True)
        directory = next(twin.glob("*-running"))
        marker = directory / "runner-resources-twin-exit.txt"
        marker.write_text(json.dumps({"command_exit": 70, "ablation": "stacks"}), encoding="utf-8")
        label(directory / "inventory.txt", marker, "lane_step")
        return failures + expect_rule("live-ablation", JOB_TWINS["live-ablation"], check_jobs(twin, [job]))


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
        paths = [path for path in root.iterdir() if path.name in {
            prefix, prefix + "-running", prefix + "-watchdog", "lane-report-" + prefix,
        }]
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
                failures.extend(expect_rule(job["name"], "stacks", defects))
                defects = [defect for defect in defects if "stacks" not in rule_ids([defect])]
            failures.extend(f"{job['name']}: {defect}" for defect in defects)
            gate = check_jobs(root, [job])
            expected_rules = {"job-ablation", "stacks"} if ablate == "stacks" else set()
            if kind == "sigkill":
                expected_rules.add("job-kind")  # the unwarned death's classifier lands separately
            if rule_ids(gate) != expected_rules:
                failures.append(f"{job['name']}: assurance expected {sorted(expected_rules)}, found {gate}")
            expected = "success" if kind == "normal" else "cancelled" if kind == "cancel" else "failure"
            log = _gh_read(f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/jobs/{job['id']}/logs").decode(
                "utf-8", errors="replace")
            timing = re.findall(r"evidence timing ([a-z-]+) ([0-9.]+)s", log)
            if kind == "normal" and platform == "Linux":
                probes = re.findall(r"evidence attachment probe: (.+)", log)
                if len(probes) != 1 or "unavailable" in probes[0]:
                    failures.append(f"{job['name']}: hosted attachment probe failed: {probes}")
            print(f"{job['name']}: post-test timings {timing}")
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
            elif needs_stack and ablate == "none":
                failures.extend(death_twins(merged, kind, job))
                if kind == "deadline":
                    failures.extend(job_twins(merged, job))
            elif kind == "cancel":
                (merged / "cutoff.txt").write_text("step cutoff\n", encoding="utf-8")
                twin = evidence_problems(merged, kind=kind)
                failures.extend(expect_rule(job["name"], OTHER_TWINS["cancel"], twin))
            rows.append(f"| {platform} | {kind} | {ablate} | [{job['conclusion']}]({job['html_url']}) | {defects} |")
    expected_count = 15 if os.environ["GITHUB_EVENT_NAME"] == "schedule" else 13
    if len(rows) != expected_count:
        failures.append(f"expected {expected_count} plants, observed {len(rows)}")
    print("\n".join(rows + failures))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write("| platform | plant | ablation | job conclusion | evidence defects |\n"
                         "|---|---|---|---|---|\n" + "\n".join(rows + failures))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
