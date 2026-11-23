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
from cancel_evidence import attach_reasons, valid
from evidence_problems import evidence_problems, report_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _api, _gh_read, _pages, _started_pytest, check_annotations  # noqa: E402


def hosted_step_timeout(repo: str, job: dict) -> bool:
    if not job.get("check_run_url"):
        return False
    ident = int(job["check_run_url"].split("/")[-1])
    for row in check_annotations(repo, ident):
        message = row.get("message") or ""
        if re.fullmatch(r"The action .+ has timed out after [0-9]+ minutes?\.", message):
            return True
        # The runner gives no action name when the enclosing composite expires.
        if (message == "The action has timed out." and row.get("path") == ".github"
                and row.get("annotation_level") == "failure"):
            return True
    return False


def check_jobs(root: Path, jobs: list[dict], *, include_success: bool = False, timeout_observation=None,
               score_rows: list | None = None) -> list[str]:
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
        conclusion = job.get("conclusion")
        if conclusion in {"skipped", None} or (conclusion == "success" and not include_success):
            continue
        first_defect = len(defects)
        reason = job.get("cancel_reason")
        row = {"job": job.get("id"), "name": job["name"], "kind": conclusion, "A1": "n/a", "A2": "n/a",
               "failed_nodes": [], "cancel_reason": reason, "started_at": job.get("started_at")}
        if score_rows is not None:
            score_rows.append(row)
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
        steps = job.get("steps", [])
        started |= bool(steps) and _started_pytest(steps)
        superseded = valid(reason) and reason["kind"] == "superseded"
        cancelled_as = (f"superseded (by run {reason['run']})" if superseded
                        else "manual/API cancel" if valid(reason) else "cancel")
        if not started:
            if conclusion == "cancelled":
                ran_steps = any(step.get("started_at") and step.get("conclusion") != "skipped" for step in steps)
                row["kind"] = (cancelled_as if ran_steps else "superseded-before-start" if superseded
                               else "cancelled-before-start")
                if not valid(reason):
                    report("cancel-reason", "no verified reason for a cancellation before the lane started")
            elif conclusion in {"failure", "timed_out"}:
                row["kind"] = "before-test"
            row["missing"] = defects[first_defect:]
            continue
        if not found:
            report("job-evidence", "no published evidence")
            row.update(kind=cancelled_as if conclusion == "cancelled" else "unclassified",
                       A1="n/a" if conclusion == "cancelled" else "no", A2="no", missing=defects[first_defect:])
            continue
        # Priority and full bundles are each checked; names in either can identify a running test.
        with tempfile.TemporaryDirectory() as temporary:
            merged = Path(temporary)
            for path in found:
                shutil.copytree(path, merged / path.name)
            # Keep separate invocations in the same job distinct (for example, nightly reference shards).
            # A valid collection error in one invocation cannot explain an unrelated command's interrupt.

            def invocation(path, directory=merged):
                return path.relative_to(directory).parts[0].removesuffix("-running").removesuffix("-watchdog")

            failed_phase = re.compile(r"(?m)^.*?\[\S+ pid [0-9]+\] (.+): failed in (setup|call|teardown|collect)$")
            observed = set()
            for breadcrumb in (*merged.rglob("reason.txt"), *merged.rglob("reason.collect.*.txt")):
                for node, phase in failed_phase.findall(breadcrumb.read_text(encoding="utf-8")):
                    observed.add((invocation(breadcrumb), node, phase))
            recorded = set()
            collection_exits = set()
            report_exits = []
            for bundle in found:
                if not bundle.name.endswith("-running"):
                    continue
                name = bundle.name.removesuffix("-running")
                lane_report = root / ("lane-report-" + name)
                if lane_report.is_dir() and (lane_report / "inventory.txt").exists():
                    shutil.copytree(lane_report, merged / lane_report.name, dirs_exist_ok=True)
                for path in lane_report.rglob("*.json"):
                    if not report_json(path.relative_to(lane_report)):
                        continue
                    try:
                        doc = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if not isinstance(doc, dict) or "exitstatus" not in doc:
                        continue
                    results = doc.get("results")
                    phases = {(name, node, record["phase"]) for node, result in
                              (results.items() if isinstance(results, dict) else ()) if isinstance(result, dict)
                              and isinstance(result.get("failures"), list) for record in result["failures"]
                              if isinstance(record, dict)
                              and record.get("phase") in ("collect", "setup", "call", "teardown")}
                    recorded.update(phases)
                    # Serial pytest returns INTERRUPTED (2) for an ordinary collection error.
                    if (doc["exitstatus"] == 2 and doc.get("complete") is True
                            and any(item[-1] == "collect" for item in observed & phases)):
                        collection_exits.add(name)
                        report_exits.append(1)
                    else:
                        report_exits.append(doc["exitstatus"])
            for _, node, phase in sorted(observed - recorded):
                report("failure-report", f"{node} ({phase}): observed failure missing from lane report")
            command_exits = []
            abnormal_command = False
            for path in merged.rglob("runner-resources-*-exit.txt"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    record = None
                if not isinstance(record, dict):
                    report("job-evidence", "unreadable command exit record")
                    continue
                code = record.get("lane_exit", record.get("command_exit"))
                command_exits.append(code)
                if code not in (0, 1) and not (code == 2 and invocation(path) in collection_exits):
                    abnormal_command = True
                if record.get("ablation") not in (None, "none"):
                    report("job-ablation", "ablation enabled in a real lane")
            died = abnormal_command or any(code not in (0, 1) for code in report_exits)
            died |= not report_exits and not command_exits
            markers = {path.stem for path in merged.rglob("*.txt")}
            kind = "deadline" if "session-deadline" in markers else "time-limit" if "cutoff" in markers else None
            if conclusion == "cancelled":
                kind = "cancel"
            elif any(re.fullmatch(r"oom-\d+", name) for name in markers):
                kind = "oom"
            elif kind is None and any(re.fullmatch(r"worker-(?:killed-\d+|gw\d+-down)", name) for name in markers):
                # The xdist down hook is an independent observation even if the attribution marker was lost.
                kind = "worker-killed"
            elif kind is None and "abnormal-exit" in markers and 137 in command_exits:
                kind = "sigkill"
            elif kind is None and any(re.fullmatch(r"(?:interrupted|cancelled)-\d+", name) for name in markers):
                # A hosted timeout needs independent runner evidence. A generic interrupt alone is ambiguous.
                step_timed_out = any(step.get("conclusion") == "timed_out" for step in job.get("steps", []))
                if step_timed_out or job.get("step_timeout") or (timeout_observation and timeout_observation(job)):
                    kind = "time-limit-github"
            if died and kind is None and conclusion != "cancelled":
                report("job-kind", "death has no kind marker")
            defects.extend(f"{job['name']}: {problem}" for problem in evidence_problems(
                merged, kind=kind, require_stacks=died and kind in {"deadline", "time-limit"},
                cancel_reason=reason))
            missing = defects[first_defect:]
            nodes = sorted({node for _, node, _ in recorded | observed})
            row["kind"] = ("test_failure" if nodes and (not kind or conclusion == "cancelled")
                           else cancelled_as if conclusion == "cancelled" else kind or "test_failure")
            row["failed_nodes"] = nodes
            if nodes or not kind and conclusion == "failure":
                incomplete = any(any(tag in problem for tag in ("[failure-", "[omission]", "[scan-unavailable]"))
                                 for problem in missing)
                row["A1"] = "yes" if nodes and not incomplete else "no"
            if kind or died:
                row["A2"] = "no" if any("[failure-" not in p for p in missing) else "yes"
            row["missing"] = missing
    return defects


def main(root: Path) -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    jobs = list(_pages(repo, f"actions/runs/{run}/attempts/{attempt}/jobs?per_page=100", "jobs"))
    current = _api(repo, f"actions/runs/{run}")
    attach_reasons(repo, current, jobs)
    rows = []
    problems = check_jobs(root, jobs, score_rows=rows, timeout_observation=lambda job: hosted_step_timeout(repo, job))
    text = "\n".join(problems) or "Published evidence states match their recorded contents."
    for row in rows:
        reason = row.get("cancel_reason") or {}
        if reason:
            text += f"\nJob {row['job']}: {row['kind']}; cancel_reason={json.dumps(reason)}"
    if current.get("event") == "pull_request":
        from record_cancel_evidence import predecessor

        if not current.get("pull_requests") and os.environ.get("GITHUB_EVENT_PATH"):
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
            if isinstance(event.get("number"), int):
                current["pull_requests"] = [{"number": event["number"]}]
        previous = predecessor(repo, current)
        if previous:
            text += f"\nSuperseded predecessor: run {previous['id']} at {previous['head_sha']} ({previous['event']})."
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
