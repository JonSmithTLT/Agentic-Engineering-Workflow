"""Independent verification and reporting of flake re-run evidence."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import flake_rerun as rerun

JOB = re.compile(r"([a-z]+) (\d+/\d+) \((windows|ubuntu)-[^)]+\)")
NAMED_HANG = re.compile(r"\] (tests/.*?::.+): the session deadline")
ERRORS = (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)
JobKey = tuple[str, str, str, int]


@dataclass
class Assessment:
    forgiven: dict[str, set[str]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sightings: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return "\n## Flake re-runs and session evidence\n\n" + "\n".join(f"- {note}" for note in self.notes) + "\n" \
            if self.notes else ""

    def sight(self, entries: list[str], job: dict[str, Any], observation: str | None = None) -> None:
        for entry in entries:
            row = {"entry": entry, "job": job["id"], "at": job["started_at"]}
            if observation:
                row["observation"] = observation
            if row not in self.sightings:
                self.sightings.append(row)


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, encoding="utf-8", check=True, timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout  # noqa: S603, S607


def pages(endpoint: str, key: str | None = None) -> list[dict[str, Any]]:
    separator = "&" if "?" in endpoint else "?"
    data = json.loads(gh("api", "--paginate", "--slurp", f"{endpoint}{separator}per_page=100"))
    rows = [row for page in data for row in (page[key] if key else page)]
    if key and data and data[0]["total_count"] != len(rows):
        raise ValueError(f"incomplete GitHub listing for {endpoint}")
    return rows


def job_key(job: dict[str, Any]) -> JobKey | None:
    match = JOB.fullmatch(job["name"])
    if not match:
        return None
    lane, shard, runner = match.groups()
    return ("win32" if runner == "windows" else "linux", lane, shard, job["run_attempt"])


def report_key(report: dict[str, Any]) -> JobKey:
    return report["platform"], report["lane"], report.get("shard") or "", int(report.get("attempt") or 1)


def report_path(root: Path, report: dict[str, Any]) -> Path:
    return root / report["_source"]


def artifact_path(root: Path, key: JobKey) -> Path:
    platform, lane, shard, attempt = key
    runner = {"linux": "Linux", "win32": "Windows"}[platform]
    core = "core-" if lane in ("fast", "serial") else ""
    return root / f"lane-report-{runner}-{core}{lane}-{shard.split('/')[0]}-attempt-{attempt}"


def test_entries(register: dict[str, Any], report: dict[str, Any], node: str, changed: set[str]) -> list[str]:
    if rerun.test_path(node) in changed:
        return []
    return rerun.entries(register, report["platform"], report["lane"], node)


def rerun_records(path: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [(record.parent, json.loads(record.read_text(encoding="utf-8")))
            for record in sorted(rerun.rerun_root(path).glob("*/result.json"))]


def note_markers(result: Assessment, source: str, folder: Path) -> bool:
    markers = rerun.marker_files(folder)
    for marker in markers:
        text = marker.read_text(encoding="utf-8", errors="replace").strip()
        result.notes.append(f"{source}: **{marker.stem}**\n\n"
                            + "\n".join(f"    {line}" for line in text.splitlines()))
    return bool(markers)


def assess_reports(result: Assessment, root: Path, register: dict[str, Any], changed: set[str],
                   history: list[dict[str, Any]], latest: list[dict[str, Any]],
                   jobs: dict[JobKey, dict[str, Any]]) -> None:
    latest_sources = {r["_source"] for r in latest}
    for report in history:
        path = report_path(root, report)
        key = report_key(report)
        job = jobs.get(key)
        if note_markers(result, report["_source"], path.parent) and job:
            result.sight(rerun.entries(register, key[0], key[1], None), job)
        for folder in sorted(rerun.rerun_root(path).glob("*/")):
            if note_markers(result, str(folder.relative_to(root)), folder) and job:
                result.sight(rerun.entries(register, key[0], key[1], None), job)
        failures = rerun.failed_tests(report)
        if report["_source"] not in latest_sources:
            if report.get("session_problems") or report.get("exitstatus") not in (0, 1, 70):
                result.problems.append(f"{key[0]}: {key[1]} had a session failure in earlier attempt {key[3]}")
            for node in failures:
                if not test_entries(register, report, node, changed):
                    result.problems.append(f"{key[0]}: {node} failed in earlier attempt {key[3]} without an "
                                           "applicable open entry")
            continue
        if not failures or not rerun.eligible(report, path.parent):
            continue
        records = rerun_records(path)
        accepted = set()
        for node in failures:
            matching = [(folder, record) for folder, record in records if node in (record.get("results") or {})]
            if len(matching) != 1:
                continue
            folder, record = matching[0]
            passed = rerun.passed(record, report, node, folder)
            ids = test_entries(register, report, node, changed)
            if ids and passed:
                if not job:
                    result.problems.append(f"{key[0]}: no CI job matched the verified re-run of {node}")
                    continue
                accepted.add(node)
                result.notes.append(f"`{node}` passed alone on {key[0]} ({', '.join(ids)}).")
                result.sight(ids, job, node)
            elif not ids:
                outcome = "passed alone" if passed else "failed alone"
                result.notes.append(f"`{node}` {outcome} on {key[0]} (evidence only). "
                                    "If the test is unchanged, triage it before opening a register entry.")
        if accepted == set(failures):
            result.forgiven[report["_source"]] = accepted


def named_hangs(folder: Path) -> set[str]:
    return {match.group(1) for reason in (folder / "autopsy").glob("*/reason.txt")
            for line in reason.read_text(encoding="utf-8", errors="replace").splitlines()
            if (match := NAMED_HANG.search(line))}


def assess_hangs(result: Assessment, root: Path, register: dict[str, Any], changed: set[str],
                 history: list[dict[str, Any]], latest: list[dict[str, Any]],
                 jobs: dict[JobKey, dict[str, Any]], repo: str) -> None:
    old_reports = {report_key(r): r for r in history}
    latest_keys = {report_key(r) for r in latest}
    newest: dict[tuple[str, str], int] = {}
    for platform, lane, _, attempt in latest_keys:
        newest[platform, lane] = max(newest.get((platform, lane), 0), attempt)
    for key, job in jobs.items():
        platform, lane, _, attempt = key
        report = old_reports.get(key)
        folder = report_path(root, report).parent if report else artifact_path(root, key)
        ids = rerun.entries(register, platform, lane, None)
        if report is None and note_markers(result, folder.name, folder):
            result.sight(ids, job)
        if key in latest_keys or attempt >= newest.get((platform, lane), 0):
            continue
        markers = {p.stem for p in rerun.marker_files(folder)}
        deadline = "session-deadline" in markers or bool(report and report.get("exitstatus") == 70)
        timed_out = job["conclusion"] == "timed_out"
        cancelled = job["conclusion"] == "cancelled"
        steps = [step for step in job.get("steps") or [] if step.get("conclusion") not in ("success", "skipped")]
        started = bool(steps) and rerun.flake_register._started_pytest(steps)
        if not deadline and not (started and (timed_out or cancelled)):
            continue
        if not deadline and cancelled:
            notes = pages(f"repos/{repo}/check-runs/{job['id']}/annotations")
            if not any(rerun.flake_register.NO_RESPONSE.search(note["message"]) for note in notes):
                continue
        url = job["html_url"]
        result.notes.append(f"[{job['name']}, attempt {attempt}]({url}) hung"
                            + (f" ({', '.join(ids)})." if ids else " without an applicable open session entry."))
        if not ids:
            result.problems.append(f"{platform}: {lane} hung in earlier attempt {attempt} "
                                   "without an open session entry")
        else:
            result.sight(ids, job)
        for node in sorted(named_hangs(folder)):
            if not test_entries(register, {"platform": platform, "lane": lane}, node, changed):
                result.problems.append(f"{platform}: {node} hung in earlier attempt {attempt} without an applicable "
                                       "open test entry")


def previous_run(result: Assessment, root: Path, latest: list[dict[str, Any]], register: dict[str, Any],
                 changed: set[str], repo: str, run: int, reuse: str) -> None:
    from check_assurance import load_reports
    from pin_shortcut import download_reports

    pr, branch = os.environ.get("PR_NUMBER"), os.environ.get("PR_HEAD_REF")
    if not pr or not branch:
        return
    try:
        if reuse:
            # The shortcut already checked the earlier run and the workflow downloaded its reports.
            previous = load_reports(root)
        else:
            from urllib.parse import urlencode

            query = urlencode({"event": "pull_request", "branch": branch, "per_page": 30})
            data = json.loads(gh("api", f"repos/{repo}/actions/workflows/ci.yml/runs?{query}"))
            old = next((r for r in data["workflow_runs"] if r["id"] < run
                        and r["status"] == "completed"
                        and int(pr) in rerun.flake_register._candidate_prs(repo, r)), None)
            if old is None:
                result.notes.append("Previous PR run unavailable for flake comparison.")
                return
            with tempfile.TemporaryDirectory(prefix="aew-pr-lane-reports-") as folder:
                download_reports(old["id"], repo, Path(folder))
                previous = load_reports(Path(folder))
        if not previous:
            result.notes.append("Previous PR run had no readable lane reports for flake comparison.")
            return
        passed = {(r["platform"], n) for r in latest for n, res in r["results"].items() if res["outcome"] == "passed"}
        probable = {(r["platform"], n) for r in previous for n in rerun.failed_tests(r)
                    if (r["platform"], n) in passed and rerun.test_path(n) not in changed
                    and not rerun.entries(register, r["platform"], r["lane"], n)}
        for platform, node in sorted(probable):
            result.notes.append(f"Likely new flake on {platform}: `{node}` failed in the previous PR run "
                                "and now passes.")
            if platform in rerun.PLATFORMS:
                result.candidates.append({"test": node, "platform": rerun.PLATFORMS[platform]})
    except (*ERRORS, AttributeError) as exc:
        result.notes.append(f"Previous PR run could not be read for flake comparison ({type(exc).__name__}).")


def assess(root: Path, history: list[dict[str, Any]], latest: list[dict[str, Any]], event: str) -> Assessment:
    result = Assessment()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run = int(os.environ.get("GITHUB_RUN_ID", "0"))
    reuse = os.environ.get("REUSE_RUN", "")
    attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    try:
        changed = rerun.changed_paths(event, os.environ.get("GITHUB_SHA", "HEAD"))
        register = rerun.tip_register()
        jobs = {}
        marker_artifact = any(path.stem in rerun.MARKERS
                              for path in root.glob("lane-report-*/autopsy/session-*/*.txt"))
        if repo and (attempt > 1 or reuse or marker_artifact or any(rerun.failed_tests(r) for r in history)):
            endpoint = f"repos/{repo}/actions/runs/{reuse or run}/jobs?filter=all"
            jobs = {key: job for job in pages(endpoint, "jobs") if (key := job_key(job))}
        assess_reports(result, root, register, changed, history, latest, jobs)
        if jobs:
            assess_hangs(result, root, register, changed, history, latest, jobs, repo)
    except ERRORS as exc:
        result.forgiven.clear()
        result.problems.append(f"Flake evidence could not be verified ({type(exc).__name__}).")
        return result
    if event == "pull_request" and repo:
        previous_run(result, root, latest, register, changed, repo, run, reuse)
    return result


def publish(path: Path, result: Assessment) -> None:
    if not result.sightings:
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    run = os.environ["GITHUB_RUN_ID"]
    name = rerun.flake_register.INDEX_ARTIFACT
    rows: list[dict[str, Any]] = []
    if int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) > 1:
        artifacts = pages(f"repos/{repo}/actions/runs/{run}/artifacts", "artifacts")
        if any(a["name"] == name and not a["expired"] for a in artifacts):
            with tempfile.TemporaryDirectory(prefix="aew-flake-index-") as folder:
                gh("run", "download", run, "--repo", repo, "--name", name, "--dir", folder)
                rows = json.loads((Path(folder) / "sightings.json").read_text(encoding="utf-8"))
    known = {(row["entry"], row["job"], row.get("observation")) for row in rows}
    rows.extend(row for row in result.sightings if (row["entry"], row["job"], row.get("observation")) not in known)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows) + "\n", encoding="utf-8")


def publish_candidates(path: Path, result: Assessment) -> None:
    if not result.candidates:
        return
    doc = {"schema": rerun.flake_register.CANDIDATE_SCHEMA, "pr": int(os.environ["PR_NUMBER"]),
           "candidates": result.candidates}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc) + "\n", encoding="utf-8")
