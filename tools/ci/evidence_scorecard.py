"""Report A1 and A2 for the red jobs of CI runs or an explicit list of job IDs."""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from contextlib import nullcontext
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from cancel_evidence import attach_reasons, run_jobs
from check_evidence_run import bundle_prefix, check_jobs, hosted_step_timeout, incomplete_failure_evidence, job_digest
from stage_evidence import JOB_CAP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _api, _gh_read, _pages, check_annotations  # noqa: E402

# A scorecard consumer bounds untrusted ZIP input separately from the publisher, whose deliberate overflow is uncapped.
# Exceeding the consumer limit is an explicit gap. Never execute or import a file from an Actions artifact.
READ_LIMIT = 4 * JOB_CAP
MAX_FILES = 10_000
RED = {"cancelled", "failure", "timed_out", "action_required", "startup_failure"}
BUNDLE_NAME = re.compile(r"(?:lane-report-)?(?:evidence|plant)-[a-zA-Z0-9_.-]+\Z")
HOSTED_RUNNER_LOST = ("The hosted runner lost communication with the server. Anything in your workflow that "
                      "terminates the runner process, starves it for CPU/Memory, or blocks its network access "
                      "can cause this error.")


def read_bundle(data, directory, allowance):
    size = 0
    with ZipFile(BytesIO(data)) as zipped:
        members = zipped.infolist()
        if len(members) > MAX_FILES:
            raise ValueError("artifact member limit")
        for member in members:
            # ZipInfo.filename normalizes backslashes on Windows. Validate the original archive spelling.
            path = PurePosixPath(member.orig_filename)
            if (path.is_absolute() or not path.parts or any(part in {"..", "."} or ":" in part or "\\" in part
                                                           for part in path.parts) or member.flag_bits & 1):
                raise ValueError("invalid artifact member path")
            if member.is_dir():
                continue
            size += member.file_size
            if size > allowance:
                raise ValueError("artifact read budget")
            target = directory.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(member) as response, target.open("xb") as output:
                shutil.copyfileobj(response, output)
    return size


def download_artifacts(repo, run, selected, directory):
    """Match per-attempt artifacts by the runner's existing job-name digest before reading payload bundles."""
    attempt = int(run["run_attempt"])
    all_files = list(_pages(repo, f"actions/runs/{run['id']}/artifacts?per_page=100", "artifacts"))
    records = [a for a in all_files if BUNDLE_NAME.fullmatch(a["name"])
               and re.search(rf"-attempt-{attempt}(?:-|$)", a["name"])]
    gaps = []
    by_job = {hashlib.sha256(j["name"].encode()).hexdigest(): j["id"] for j in selected}
    links = {j["id"]: [] for j in selected}
    # Typed running bundles are much smaller than the scanned evidence; bound the whole operation's reads.
    remaining = READ_LIMIT

    def fetch(artifact):
        nonlocal remaining
        allowance = remaining
        if artifact.get("expired"):
            raise ValueError("expired")
        if not 0 < artifact["size_in_bytes"] <= allowance:
            raise ValueError("artifact read budget")
        remaining -= artifact["size_in_bytes"]
        data = _gh_read(f"repos/{repo}/actions/artifacts/{int(artifact['id'])}/zip")
        if len(data) > allowance:
            raise ValueError("artifact read budget")
        target = directory / artifact["name"]
        with tempfile.TemporaryDirectory(dir=directory) as transient:
            staged = Path(transient) / "bundle"
            staged.mkdir()
            try:
                used = read_bundle(data, staged, allowance)
            except (BadZipFile, OSError, ValueError):
                remaining = 0  # a rejected archive can already have expanded near the limit
                raise
            staged.rename(target)
        remaining = max(0, allowance - max(artifact["size_in_bytes"], len(data), used))

    bundles = defaultdict(list)
    for artifact in records:
        bundles[bundle_prefix(artifact["name"])].append(artifact)
    for group in bundles.values():
        loaded, unavailable = [], []
        digest = None
        # Prefer the small identity bundle. The scanned report, watchdog and full bundle carry independent identities.
        for artifact in sorted(group, key=lambda a: (not a["name"].endswith("-running"), a["size_in_bytes"])):
            if digest and digest not in by_job:
                break
            try:
                fetch(artifact)
                loaded.append(artifact["id"])
                digest = digest or job_digest(directory / artifact["name"])
            except (BadZipFile, ValueError, OSError, subprocess.SubprocessError):
                unavailable.append(artifact["id"])
        if digest in by_job:
            job_id = by_job[digest]
            links[job_id].extend(loaded)
            gaps.extend((job_id, ident) for ident in unavailable)
        elif digest is None:
            gaps.extend((None, ident) for ident in unavailable)
    return links, gaps


def runner_lost(repo, job):
    # GitHub finalized the job while its last active step was still running (job 138486559048).
    if job.get("status") != "completed" or job["conclusion"] != "failure" or not any(
        step.get("status") == "in_progress" and step.get("started_at") and not step.get("completed_at")
        and step.get("conclusion") is None for step in job.get("steps", [])
    ):
        return False
    return any(row.get("path") == ".github" and row.get("annotation_level") == "failure"
               and row.get("message") == HOSTED_RUNNER_LOST for row in check_annotations(repo, job["id"]))


def inspect_run(repo, run, selected=None, *, directory=None):
    jobs = run_jobs(repo, run["id"], int(run["run_attempt"]))
    selected = [j for j in jobs if j["conclusion"] in RED and (selected is None or j["id"] in selected)]
    if not selected:
        return []
    attach_reasons(repo, run, jobs)
    with (tempfile.TemporaryDirectory() if directory is None else nullcontext(directory)) as location:
        root = Path(location)
        links, gaps = download_artifacts(repo, run, selected, root)
        rows = []
        for job in selected:
            result = []
            try:
                check_jobs(root, [job], score_rows=result, timeout_observation=lambda j: hosted_step_timeout(repo, j))
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                # One malformed artifact must not hide any other job's evidence or promote the verdict.
                result = [{"job": job["id"], "name": job["name"], "kind": "unclassified", "A1": "no", "A2": "no",
                           "cancel_reason": job.get("cancel_reason"), "failed_nodes": [],
                           "missing": ["evidence defect: [artifact-unreadable] malformed job evidence"]}]
            for row in result:
                if row["kind"] in {"before-test", "unclassified", "test_failure"} and runner_lost(repo, job):
                    # The host loss is outside A5. Preserve any observed test failure and all A3 defects.
                    row["kind"] = "runner-lost"
                    row["A2"] = "n/a"
                    if not row["failed_nodes"] and not incomplete_failure_evidence(row["missing"]):
                        row["A1"] = "n/a"
            rows.extend(result)
        for row in rows:
            row["run"] = run["id"]
            row["artifacts"] = links[row["job"]]
            row["unreadable_artifacts"] = [ident for job, ident in gaps if job == row["job"]]
            row["defects"] = row.get("missing", [])
            row["missing"] = sorted({rule for message in row["defects"]
                                     for rule in re.findall(r"evidence defect: \[([a-z-]+)\]", message)})
        if rows:
            rows[0]["unassigned_artifacts"] = [ident for job, ident in gaps if job is None]
        return rows


def format_rows(repo, rows):
    lines = ["| Run | Job | Death kind | A1 | A2 | Missing | Artifacts |", "|---|---|---|---|---|---|---|"]
    for row in rows:
        run, job = row["run"], row["job"]
        kind = row["kind"]
        if kind == "test_failure" and (row.get("cancel_reason") or {}).get("kind") == "superseded":
            kind += f" (superseded by run {row['cancel_reason']['run']})"
        reason = row.get("cancel_reason") or {}
        if reason.get("kind") == "superseded":
            if kind == "superseded-before-start":
                kind += f" (by run {reason['run']})"
            kind += f" · [{reason['head_sha'][:12]}](https://github.com/{repo}/actions/runs/{reason['run']})"
            kind += f" {reason['event']}"
        if reason.get("kind") == "manual-or-api":
            kind += " · " + reason["message"]
            kind += " Actor: " + reason["actor"] if reason.get("actor") else " GitHub did not identify the actor."
        base = f"https://github.com/{repo}/actions/runs/{run}"
        links = ", ".join(f"[{a}]({base}/artifacts/{a})" for a in row["artifacts"])
        for ident in row.get("unreadable_artifacts", []):
            links += (", " if links else "") + f"[{ident} unavailable]({base}/artifacts/{ident})"
        lines.append(f"| {run} | [{job}](https://github.com/{repo}/actions/runs/{run}/job/{job}) | "
                     f"{kind} | {row['A1']} | {row['A2']} | {', '.join(row['missing']) or '—'} | {links or '—'} |")
    for row in rows:
        for ident in row.get("unassigned_artifacts", []):
            url = f"https://github.com/{repo}/actions/runs/{row['run']}/artifacts/{ident}"
            lines.append(f"\nUnavailable artifact [{ident}]({url}) has no surviving job identity.")
        for detail in row.get("defects", []):
            # Quote artifact-derived names as visible text. Never interpret them as a check's Markdown or HTML.
            safe = html.escape(detail.translate({ord(c): " " for c in "\r\n"}), quote=True)
            lines.append(f"\nJob {row['job']}: <code>{safe[:1500]}</code>")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY",
                                                         "JonSmithTLT/Agentic-Engineering-Workflow"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--runs", type=int)
    source.add_argument("--jobs", type=int, nargs="+")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or any(p in {".", ".."} for p in args.repo.split("/")):
        parser.error("expected a GitHub repository in owner/name form")
    selections = defaultdict(set)
    if args.jobs:
        for ident in args.jobs:
            if ident < 1:
                parser.error("job IDs must be positive")
            job = _api(args.repo, f"actions/jobs/{ident}")
            selections[(job["run_id"], job["run_attempt"])].add(ident)
        runs = [_api(args.repo, f"actions/runs/{ident}/attempts/{attempt}") for ident, attempt in selections]
    else:
        if args.runs < 1:
            parser.error("run count must be positive")
        # Stop at the requested run count without enumerating the complete workflow history.
        runs = []
        for page in range(1, (args.runs + 99) // 100 + 1):
            batch = _api(args.repo, f"actions/workflows/ci.yml/runs?per_page=100&page={page}")["workflow_runs"]
            runs.extend(batch)
            if len(batch) < 100:
                break
        runs = runs[:args.runs]
    rows = []
    for run in runs:
        if run.get("path") == ".github/workflows/ci.yml":
            rows.extend(inspect_run(args.repo, run, selections.get((run["id"], run["run_attempt"]))))
    print(format_rows(args.repo, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
