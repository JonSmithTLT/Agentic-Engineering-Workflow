"""Verify downloaded lane artifacts against the hosted job's observed conclusion."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from cancel_evidence import REASON_FILE, observe
from check_evidence_run import check_jobs, hosted_step_timeout
from evidence_files import CANCEL_COLLECTION, FRAME, WARNING, entries, state, test_frame
from evidence_problems import evidence_problems

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
OTHER_TWINS = {"cancel": "false-cutoff", "ring": "snapshot", "unlabelled": "snapshot-label",
               "trigger": "pressure", "missing-death": "death-record", "stale": "snapshot-age",
               "missing-counter": "oom-event", "missing-peak": "pressure", "wrong-bundle": "file-class",
               "live": "live-stack", "annotations-off": "cancel-reason"}
ABRUPT = {"worker-kill": "worker-killed", "oom": "oom", "time-limit-github": "time-limit-github", "cancel": "cancel"}
FAILURE_TWINS = {"invalid-json": "failure-report", "missing-exception": "failure-text",
                 "missing-result": "failure-report"}
PLANTED = {"stacks": {"stacks"}, "unlabelled": {"snapshot-label"}, "trigger": {"pressure"},
           "ring": {"snapshot", "snapshot-label", "snapshot-age"}, "verbosity": {"failure-elision"},
           "mask": {"omission"}, "overflow": {"omission", "failure-overflow"}}
DEATH_EXITS = {"deadline": 70, "time-limit": 71, "hang": 70, "sigkill": 137, "failure": 1, "failure-in-death": 70}


def rule_ids(defects: list[str]) -> set[str]:
    return {match[1] for defect in defects if (match := re.search(r"evidence defect: \[([a-z-]+)\]", defect))}


def expect_rule(case: str, expected: str, defects: list[str]) -> list[str]:
    return [] if expected in rule_ids(defects) else [f"{case}: {expected} ablation survived: {defects}"]


def github_jobs() -> list[dict]:
    endpoint = (f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                f"/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}/jobs?per_page=100")
    result = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True, timeout=30, check=True)
    jobs = json.loads(result.stdout)["jobs"]
    for job in jobs:
        if ", time-limit-github," not in job["name"]:
            continue
        job["step_timeout"] = hosted_step_timeout(os.environ["GITHUB_REPOSITORY"], job)
    if any(job["conclusion"] == "cancelled" and ", cancel," in job["name"] for job in jobs):
        from flake_register import _api

        repo = os.environ["GITHUB_REPOSITORY"]
        run = _api(repo, f"actions/runs/{os.environ['GITHUB_RUN_ID']}")
        for job in jobs:
            if job["conclusion"] == "cancelled" and ", cancel," in job["name"]:
                job["cancel_reason"] = observe(repo, run, job, jobs)
    return jobs


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
                if case == "kind" and (path.stem in {"session-deadline", "cutoff"} or re.fullmatch(
                    r"(?:(?:worker-killed|oom|interrupted|cancelled)-[0-9]+|worker-gw[0-9]+-down)", path.stem
                )):
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
                failures.extend(expect_rule("missing-kind", JOB_TWINS["missing-kind"],
                                            check_jobs(twin, [job], include_success=True)))
    return failures


def job_twins(root: Path, job: dict) -> list[str]:
    with tempfile.TemporaryDirectory() as temporary:
        twin = Path(temporary) / "twin"
        twin.mkdir()
        failures = expect_rule("no-evidence", JOB_TWINS["no-evidence"], check_jobs(twin, [job], include_success=True))
        shutil.copytree(root, twin, dirs_exist_ok=True)
        directory = next(twin.glob("*-running"))
        marker = directory / "runner-resources-twin-exit.txt"
        marker.write_text(json.dumps({"command_exit": 70, "ablation": "stacks"}), encoding="utf-8")
        label(directory / "inventory.txt", marker, "lane_step")
        return failures + expect_rule("live-ablation", JOB_TWINS["live-ablation"],
                                      check_jobs(twin, [job], include_success=True))


def abrupt_twins(root: Path, kind: str, job: dict) -> list[str]:
    failures = []
    cases = (("missing-death", "stale", "wrong-bundle") if kind == "worker-killed"
             else ("missing-counter", "missing-peak"))
    for case in cases:
        with tempfile.TemporaryDirectory() as temporary:
            twin = Path(temporary) / "copy"
            shutil.copytree(root, twin)
            if case == "wrong-bundle":
                inventory = next(twin.glob("*-watchdog/inventory.txt"))
                bad = inventory.parent / "junit.xml"
                bad.write_text("<testsuite/>", encoding="utf-8")
                label(inventory, bad, "pytest")
            elif case in {"missing-counter", "missing-peak"}:
                name = "runner-resources-oom.txt" if case == "missing-counter" else "runner-resources-high-water.txt"
                for path in twin.rglob(name):
                    path.unlink()
            else:
                for path in twin.rglob("worker-killed-*.txt"):
                    if case == "missing-death":
                        path.unlink()
                    else:
                        row = json.loads(path.read_text())
                        row["age_s"] = 100
                        path.write_text(json.dumps(row), encoding="utf-8")
            failures.extend(expect_rule(case, OTHER_TWINS[case], evidence_problems(twin, kind=kind)))
            failures.extend(expect_rule(case, OTHER_TWINS[case], check_jobs(twin, [job], include_success=True)))
    return failures


def observe_cancel(root: Path, platform: str, jobs: list[dict], *, trigger_at: str | None = None) -> list[str]:
    observed = [json.loads(path.read_text()) for glob in ("cancelled-*.txt", "interrupted-*.txt")
                for path in root.rglob(glob)]
    if not observed or any(type(row.get("alive_when_observed")) is not bool for row in observed):
        return ["plant misfired: no live/dead identity observed during cancellation"]
    if platform == "Linux":
        registered = {(int(pid.read_text()), int(pid.with_name(pid.name.replace("-pid.", "-start.")).read_text()))
                      for pid in root.rglob("worker-gw*-pid.txt")}
        interrupted = [row for row in observed if row.get("kind") == "interrupted" and row["alive_when_observed"]]
        if len(registered) != 4 or registered != {(row["pid"], row["start"]) for row in interrupted}:
            return ["Linux: cancellation did not observe all four registered workers alive"]
        for row in interrupted:
            captures = ((sample, frames) for path in root.rglob(f"snapshots/{row['pid']}.txt")
                        for sample, frames in entries(path.read_text()))
            if not any(sample.get("reason") == WARNING and sample.get("pid") == row["pid"]
                       and sample.get("start") == row["start"] and sample.get("node") == row["node"]
                       and row.get("collect_at", float("inf")) <= sample["at"] <= row["at"]
                       and test_frame(row["node"], frames) for sample, frames in captures):
                return [f"Linux: no pre-signal test stack for worker {row['pid']} at {row['node']}"]
    if platform == "Windows":
        ready = next((job for job in jobs if job["name"] == "cancel-ready-windows"), {})
        ended = trigger_at or ready.get("completed_at")
        if not ended:
            return ["plant misfired: cancellation poll did not finish"]
        # Queueing starts after this job completes, giving a conservative server-side lower bound on cancel time.
        before = datetime.fromisoformat(ended.replace("Z", "+00:00")).timestamp()
        for row in observed:
            samples = [sample for path in root.rglob(f"snapshots/{row['pid']}.txt")
                       for sample, _ in entries(path.read_text()) if sample.get("start") == row["start"]]
            earlier = [sample for sample in samples if sample.get("node") and 0 <= before - sample["at"] <= 60]
            if not earlier:
                return ["Windows: no labelled worker sample predating the cancellation trigger"]
            sample = max(earlier, key=lambda entry: entry["at"])
            print(f"Windows worker {row['pid']} sample {sample['node']} UTC {sample['utc']} predates "
                  f"the cancellation trigger's lower bound {ended} by {before - sample['at']:.3f}s.")
    return []


def observation_problems(root: Path, platform: str, kind: str) -> list[str]:
    """Verify runner observations from the downloaded bundle, alongside GitHub's job conclusion."""
    failures = []
    expected_exit = DEATH_EXITS.get(kind)
    if expected_exit is not None:
        records = [json.loads(path.read_text(encoding="utf-8"))
                   for path in root.rglob("runner-resources-*-exit.txt")]
        exits = {record.get("lane_exit") for record in records}
        if exits != {expected_exit}:
            failures.append(f"plant misfired: expected lane exit {expected_exit}, found {exits}")
        if kind == "hang":
            for record in records:
                beat = record.get("heartbeat", {})
                entered = beat.get("entered")
                if entered is None or beat.get("beats_before", 0) < 3:
                    failures.append("plant misfired: heartbeat handshake missing")
                elif beat.get("observed_until", 0) <= entered + 1 or beat.get("latest_beat_after", 0) > entered + 1:
                    failures.append("plant misfired: heartbeat did not stall through the observation window")
    if kind in {"worker-kill", "oom"}:
        crashes = [json.loads(path.read_text()) for path in root.rglob("worker-killed-*.txt")]
        if not crashes or any(row.get("signal") != 9 if platform == "Linux" else row.get("exit") != 1
                              for row in crashes):
            failures.append(f"plant misfired: external worker exit was not observed: {crashes}")
        if kind == "oom" and not list(root.rglob("runner-resources-high-water.txt")):
            failures.append("plant misfired: no observed high-water crossing")
    if kind == "time-limit-github":
        if any(root.rglob("cutoff.txt")) or any(root.rglob("session-deadline.txt")):
            failures.append("plant misfired: a local deadline preempted the hosted deadline")
        serial = False
        for observation in (*root.rglob("interrupted-*.txt"), *root.rglob("cancelled-*.txt")):
            row = json.loads(observation.read_text())
            controller = observation.parent / "controller-pid.txt"
            birth = observation.parent / "controller-start.txt"
            if controller.is_file() and birth.is_file():
                serial |= (row["pid"], row["start"]) == (int(controller.read_text()), int(birth.read_text()))
        if not serial:
            failures.append("plant misfired: no observation of the active no-xdist controller")
    if kind == "normal" and platform == "Linux":
        probes = [p.read_text(encoding="utf-8").strip() for p in root.rglob("runner-resources-attachment.txt")]
        if len(probes) != 1 or probes[0] not in {"unelevated", "sudo -n"}:
            failures.append(f"hosted attachment probe failed: {probes}")
    return failures


def published_failures(root: Path, kind: str, ablation: str) -> list[str]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests/integration/evidence_plants"))
    from failures import scanner_fixtures

    token, pem = scanner_fixtures()
    private_fragments = [part.encode() for part in (token, *pem.splitlines()[1:-1])]
    exposed = []
    for path in root.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            if any(fragment in content for fragment in private_fragments):
                exposed.append(path.relative_to(root))
    if exposed:
        return [f"synthetic fixture bytes survived masking in {path}" for path in exposed]
    reports = list(root.glob("lane-report-*/plant.json"))
    if ablation == "mask":
        return ["masking-off twin published its failure report"] if reports else []
    if len(reports) != 1:
        return [f"expected one scanned lane report, found {len(reports)}"]
    path = reports[0]
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    if data.get("complete") is not (kind == "failure"):
        errors.append(f"unexpected report completeness: {data.get('complete')}")
    failed = {node.split("::")[-1]: result["failures"][0] for node, result in data["results"].items()
              if result.get("failures")}
    for test, phrase in (("test_list_difference", "actual middle entry"),
                         ("test_string_difference", "actual string suffix")):
        if ablation != "verbosity" and phrase not in failed.get(test, {}).get("longrepr", ""):
            errors.append(f"{test}: missing differing item in published report")
    overflow = failed.get("test_full_masked_failure", {})
    full = path.parent / overflow.get("overflow", "absent")
    if ablation != "overflow" and not full.is_file():
        errors.append("full overflow file missing from lane-report artifact")
    for text in [overflow.get("longrepr", ""), *([full.read_text(encoding="utf-8")] if full.is_file() else [])]:
        if not all(marker in text for marker in ("overflow begins", "overflow ends", "<redacted:github-pat>",
                                                  "<redacted:private-key>")):
            errors.append("published failure lost its context or a scanner mask")
    return errors


def failure_twins(root: Path, job: dict) -> list[str]:
    errors = []
    for mutation, rule in FAILURE_TWINS.items():
        with tempfile.TemporaryDirectory() as tmp:
            twin = Path(tmp) / "copy"
            shutil.copytree(root, twin)
            for path in twin.rglob("plant.json"):
                if mutation == "invalid-json":
                    path.write_text("{", encoding="utf-8")
                else:
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    if mutation == "missing-result":
                        doc["results"] = {}
                    for result in doc["results"].values():
                        for failure in result.get("failures", []):
                            failure["longrepr"] = "with pytest.raises(AssertionError):\n    compare()"
                            failure.pop("overflow", None)
                    path.write_text(json.dumps(doc), encoding="utf-8")
            errors.extend(expect_rule(mutation, rule, check_jobs(twin, [job], include_success=True)))
    return errors


def main(root: Path) -> int:
    jobs = github_jobs()
    failures = []
    rows = []
    for job in jobs:
        # GitHub returns an unexpanded placeholder for the entire skipped PR cancellation matrix.
        match = re.fullmatch(r"plant \((ubuntu-24\.04|windows-latest), ([^,]+), ([^)]+)\)", job["name"])
        if not match:
            continue
        runner, kind, ablate = match.groups()
        platform = "Windows" if runner == "windows-latest" else "Linux"
        prefix = f"plant-{platform}-{kind}-{ablate}-attempt-{os.environ['GITHUB_RUN_ATTEMPT']}"
        prefixes = {prefix, prefix + "-recovered"}
        names = {name for attempt in prefixes for name in (attempt, attempt + "-running", attempt + "-watchdog",
                                                           "lane-report-" + attempt)}
        paths = [path for path in root.iterdir() if path.name in names]
        recovered = any(path.name == prefix + "-recovered" for path in paths)
        if kind == "time-limit-github" and not recovered:
            failures.append(f"{job['name']}: evidence was not published by the post-timeout recovery step")
        if kind not in {"time-limit-github", "cancel"} and recovered:
            failures.append(f"{job['name']}: completed lane unexpectedly required recovery")
        target = "GitHub timed execution" if kind == "time-limit-github" else "Real planted lane"
        lane_step = next((step for step in job.get("steps", []) if step["name"] == target), None)
        if not paths or not lane_step or not lane_step.get("started_at"):
            failures.append(f"{job['name']}: plant did not start or artifacts missing")
            continue
        with tempfile.TemporaryDirectory() as temporary:
            merged = Path(temporary)
            for path in paths:
                shutil.copytree(path, merged / path.name)
            needs_stack = kind in {"deadline", "time-limit", "hang", "failure-in-death"}
            cause = "deadline" if kind == "failure-in-death" else ABRUPT.get(kind, kind)
            reason = job.get("cancel_reason")
            defects = evidence_problems(merged, kind=cause, require_stacks=needs_stack, cancel_reason=reason)
            expected_rules = PLANTED.get(ablate, set())
            if rule_ids(defects) != expected_rules:
                failures.append(f"{job['name']}: checker expected {sorted(expected_rules)}, found {defects}")
            gate = check_jobs(root, [job], include_success=kind in DEATH_EXITS or kind in ABRUPT)
            expected_rules = expected_rules | ({"job-ablation"} if ablate in PLANTED else set())
            if ablate == "mask":
                expected_rules = expected_rules | {"failure-report"}
            if rule_ids(gate) != expected_rules:
                failures.append(f"{job['name']}: assurance expected {sorted(expected_rules)}, found {gate}")
            expected = "cancelled" if kind == "cancel" else "success"
            verdict_step = lane_step
            if kind in DEATH_EXITS or (kind in ABRUPT and kind != "cancel"):
                verdict_step = next((step for step in job["steps"] if step["name"] == "Confirm planted death"), {})
            verdict = verdict_step.get("conclusion")
            failures.extend(f"{job['name']}: {problem}" for problem in observation_problems(merged, platform, kind))
            if kind in {"failure", "failure-in-death"}:
                failures.extend(f"{job['name']}: {problem}" for problem in published_failures(merged, kind, ablate))
                if kind == "failure" and ablate == "none":
                    failures.extend(failure_twins(merged, job))
            if job["conclusion"] != expected or verdict != expected:
                failures.append(f"{job['name']}: plant misfired: job {job['conclusion']}, verdict step {verdict}")
            if kind == "time-limit-github":
                if lane_step.get("conclusion") != "timed_out" and not job.get("step_timeout"):
                    failures.append(f"{job['name']}: GitHub did not report its own step timeout")
            if kind == "cancel":
                failures += [f"{job['name']}: {why}" for why in observe_cancel(merged, platform, jobs)]
                if not list(merged.rglob(REASON_FILE)):
                    failures.append(f"{job['name']}: cleanup wrote no cancellation observation")
                if (not reason or reason.get("kind") != "superseded"
                        or reason.get("run") != int(os.environ["GITHUB_RUN_ID"])
                        or reason.get("head_sha") != os.environ["GITHUB_SHA"]):
                    failures.append(f"{job['name']}: no attribution to the actual concurrency replacement")
                failures.extend(expect_rule("annotations-off", OTHER_TWINS["annotations-off"],
                                            check_jobs(merged, [{**job, "cancel_reason": None}])))
            if kind in {"worker-kill", "oom"} and ablate == "none":
                failures.extend(abrupt_twins(merged, ABRUPT[kind], job))
            if kind == "normal":
                failures.extend(checker_twins(merged))
            elif needs_stack and ablate == "none" and kind != "failure-in-death":
                failures.extend(death_twins(merged, kind, job))
                if kind == "deadline":
                    failures.extend(job_twins(merged, job))
            elif kind == "cancel":
                for path in merged.rglob("snapshots/*.txt"):
                    text = path.read_text().replace(f'"reason": "{WARNING}"', '"reason": "periodic"')
                    path.write_text(text.replace(f'"reason": "{CANCEL_COLLECTION}"', '"reason": "periodic"'))
                live_seen = any(row.get("alive_when_observed") for target in ("cancelled-*.txt", "interrupted-*.txt")
                                for path in merged.rglob(target) for row in [json.loads(path.read_text())])
                if live_seen:
                    failures.extend(expect_rule(job["name"], OTHER_TWINS["live"], evidence_problems(merged, kind=kind)))
                for competing in ("cutoff", "session-deadline"):
                    marker = next(merged.glob("*-watchdog")) / f"{competing}.txt"
                    marker.write_text("competing deadline\n", encoding="utf-8")
                    failures.extend(expect_rule(job["name"], OTHER_TWINS["cancel"], check_jobs(merged, [job])))
                    marker.unlink()
            rows.append(f"| {platform} | {kind} | {ablate} | [{job['conclusion']}]({job['html_url']}) | {defects} |")
    expected_count = 28 if os.environ["GITHUB_EVENT_NAME"] == "pull_request" else 30
    if len(rows) != expected_count:
        failures.append(f"expected {expected_count} plants, observed {len(rows)}")
    print("\n".join(rows + failures))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write("| platform | plant | ablation | job conclusion | evidence defects |\n"
                         "|---|---|---|---|---|\n" + "\n".join(rows + failures))
    return int(bool(failures))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--plant-death", choices=(*DEATH_EXITS, *ABRUPT))
    args = parser.parse_args()
    if args.plant_death:
        problems = observation_problems(args.root, "Windows" if os.name == "nt" else "Linux", args.plant_death)
        for problem in problems:
            print(problem, file=sys.stderr)
        raise SystemExit(int(bool(problems)))
    raise SystemExit(main(args.root))
