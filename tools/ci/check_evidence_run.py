"""Publish evidence defects separately from the test verdict."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml
from cancel_evidence import attach_reasons, valid
from evidence_problems import FAILURE_PHASES, evidence_problems, report_json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_files import BEFORE_TESTS, HOST_STOP_FILE  # noqa: E402 - on the helpers path evidence_problems adds
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


def bundle_prefix(name):
    return name.removeprefix("lane-report-").removesuffix("-running").removesuffix("-watchdog")


def job_digest(directory):
    digest = directory / "job-label-sha256.txt"
    if digest.is_file():
        try:
            value = digest.read_text(encoding="ascii").strip()
            if re.fullmatch(r"[0-9a-f]{64}", value):
                return value
        except (OSError, ValueError):
            pass
    for metadata in directory.glob("runner-resources-*.txt"):
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("job_label"), str) and data["job_label"]:
                return hashlib.sha256(data["job_label"].encode()).hexdigest()
        except (OSError, ValueError):
            continue
    return None


def finished_tests(bundles, complete_report, *, report_exits=(), steps_passed=False):
    if len(report_exits) > 1 or any(code not in (None, 0, 1) for code in report_exits):
        return False
    if steps_passed and complete_report:
        return True
    # The early watchdog upload can survive without the full one. Combine only
    # matching session directories, and reject conflicting copies of a receipt.
    sessions = [(bundle, path.parent) for bundle in bundles for path in bundle.rglob("session-started.txt")]
    if len({directory.relative_to(bundle) for bundle, directory in sessions}) != 1:
        return False

    def receipt(name):
        values = {path.read_text(encoding="utf-8").strip() for _, directory in sessions
                  if (path := directory / name).is_file()}
        if len(values) != 1:
            raise ValueError(name)
        return values.pop()

    try:
        if complete_report and any((directory / "session-finished.txt").is_file() for _, directory in sessions):
            pid = int(receipt("controller-pid.txt"))
            if re.search(rf"\bpid {pid}: the session finished \(exit (?:None|0|1)\);", receipt("session-finished.txt")):
                return True
        # An interrupted controller may not have written its report. Every configured
        # worker must have finished its pytest session with its own matching PID.
        count = int(receipt("worker-count.txt"))
        pids = {path.name for _, directory in sessions for path in directory.glob("worker-gw*-pid.txt")}
        if not pids or count != len(pids):
            return False
        for index in range(count):
            worker = f"worker-gw{index}"
            pid = int(receipt(f"{worker}-pid.txt"))
            exit_note = receipt(f"{worker}-exit.txt")
            if not re.search(rf"\bpid {pid}: worker gw{index} finished its session \(exit [01]\);", exit_note):
                return False
    except (OSError, ValueError):
        return False
    return True


def incomplete_failure_evidence(problems):
    return any(any(tag in problem for tag in ("[failure-", "[omission]", "[scan-unavailable]", "[artifact-unreadable]"))
               for problem in problems)


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
        archives = list(root.iterdir()) if root.is_dir() else []
        digest = hashlib.sha256(job["name"].encode()).hexdigest()
        prefixes = {bundle_prefix(path.name) for path in archives if job_digest(path) == digest}
        found = [path for path in archives if bundle_prefix(path.name) in prefixes]
        steps = job.get("steps", [])
        lane_steps = [s for s in steps if s.get("started_at") and s.get("conclusion") != "skipped"
                      and not s["name"].startswith("Post ")
                      and (any(pattern.fullmatch(s["name"]) for pattern in patterns) or _started_pytest([s]))]
        started = bool(found or lane_steps)
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
                return bundle_prefix(path.relative_to(directory).parts[0])

            failed_phase = re.compile(r"(?m)^.*?\[\S+ pid [0-9]+\] (.+): failed in (setup|call|teardown|collect)$")
            observed = set()
            for breadcrumb in (*merged.rglob("reason.txt"), *merged.rglob("reason.collect.*.txt")):
                for node, phase in failed_phase.findall(breadcrumb.read_text(encoding="utf-8")):
                    observed.add((invocation(breadcrumb), node, phase))
            recorded = set()
            collection_exits = set()
            completed = set()
            reports_by_prefix = defaultdict(list)
            report_exits = []
            for name in prefixes:
                lane_report = root / ("lane-report-" + name)
                for path in lane_report.rglob("*.json"):
                    if not report_json(path.relative_to(lane_report)):
                        continue
                    try:
                        doc = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if not isinstance(doc, dict) or "exitstatus" not in doc:
                        continue
                    if (doc.get("schema") == "aew/lane-report/v1" and doc.get("complete") is True
                            and doc["exitstatus"] in (0, 1)):
                        completed.add(name)
                    results = doc.get("results")
                    phases = {(name, node, record["phase"]) for node, result in
                              (results.items() if isinstance(results, dict) else ()) if isinstance(result, dict)
                              and result.get("outcome") in ("failed", "error")
                              and isinstance(result.get("failures"), list) for record in result["failures"]
                              if isinstance(record, dict)
                              and record.get("phase") in FAILURE_PHASES}
                    recorded.update(phases)
                    # Serial pytest returns INTERRUPTED (2) for an ordinary collection error.
                    if (doc["exitstatus"] == 2 and doc.get("complete") is True
                            and any(item[-1] == "collect" for item in observed & phases)):
                        collection_exits.add(name)
                        report_exits.append(1)
                    else:
                        report_exits.append(doc["exitstatus"])
                    reports_by_prefix[name].append(report_exits[-1])
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
                death_marker = any(re.fullmatch(r"(?:interrupted|cancelled|worker-killed|oom)-[0-9]+"
                                                r"|worker-gw[0-9]+-down|session-deadline|cutoff|abnormal-exit"
                                                r"|(?:running|hang)-.+", name) for name in markers)
                all_steps_passed = (len(lane_steps) == len(prefixes)
                                    and all(s["conclusion"] == "success" for s in lane_steps))

                after_tests = not death_marker and not abnormal_command and all(
                    finished_tests([path for path in found if bundle_prefix(path.name) == name], name in completed,
                                   report_exits=reports_by_prefix[name], steps_passed=all_steps_passed)
                    for name in prefixes)
                # With no death marker, a lane step's record that no session had started a test types the
                # cancellation; evidence_problems checks the bundle bears it out (register E3).
                before_tests = not death_marker and Path(BEFORE_TESTS).stem in markers
                kind = ("cancel-after-tests" if after_tests else "cancel-before-tests" if before_tests
                        else "cancel")
            elif any(re.fullmatch(r"oom-\d+", name) for name in markers):
                kind = "oom"
            elif kind is None and any(re.fullmatch(r"worker-(?:killed-\d+|gw\d+-down)", name) for name in markers):
                # The xdist down hook is an independent observation even if the attribution marker was lost.
                kind = "worker-killed"
            elif kind is None and Path(HOST_STOP_FILE).stem in markers:
                # The lane step stopped the lane for the Windows host's resources and named them (register E3).
                kind = "host-resources"
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
                           else f"{cancelled_as} after tests" if kind == "cancel-after-tests"
                           else f"{cancelled_as} before tests" if kind == "cancel-before-tests"
                           else cancelled_as if conclusion == "cancelled" else kind or "unclassified")
            row["failed_nodes"] = nodes
            if nodes or not kind and conclusion == "failure":
                row["A1"] = "yes" if nodes and not incomplete_failure_evidence(missing) else "no"
            if (kind or died) and kind != "cancel-after-tests":
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
