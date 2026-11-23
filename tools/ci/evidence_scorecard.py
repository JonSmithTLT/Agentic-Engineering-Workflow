"""Report A1 and A2 for the red jobs of CI runs or an explicit list of job IDs."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from cancel_evidence import attach_reasons, run_jobs
from check_evidence_run import check_jobs, hosted_step_timeout
from stage_evidence import JOB_CAP

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import _api, _gh_read, _pages  # noqa: E402

# A scorecard consumer bounds untrusted ZIP input separately from the publisher, whose deliberate overflow is uncapped.
# Exceeding the consumer limit is an explicit gap. Never execute or import a file from an Actions artifact.
READ_LIMIT = 4 * JOB_CAP
MAX_FILES = 10_000
RED = {"cancelled", "failure", "timed_out", "action_required", "startup_failure"}
BUNDLE_NAME = re.compile(r"(?:lane-report-)?(?:evidence|plant)-[a-zA-Z0-9_.-]+\Z")


def read_bundle(data, directory, allowance):
    size = 0
    with ZipFile(BytesIO(data)) as zipped:
        members = zipped.infolist()
        if len(members) > MAX_FILES:
            raise ValueError("artifact member limit")
        for member in members:
            path = PurePosixPath(member.filename)
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
    prefixes = {}
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

    for artifact in records:
        name = artifact["name"]
        if not name.endswith("-running"):
            continue
        try:
            fetch(artifact)
            digest = (directory / name / "job-label-sha256.txt").read_text().strip()
            if digest in by_job:
                job_id = by_job[digest]
                prefixes[name.removesuffix("-running")] = job_id
                links[job_id].append(artifact["id"])
        except (BadZipFile, ValueError, OSError, subprocess.SubprocessError):
            gaps.append((None, artifact["id"]))
    for artifact in records:
        name = artifact["name"]
        prefix = name.removeprefix("lane-report-").removesuffix("-watchdog")
        if prefix not in prefixes:
            continue
        job_id = prefixes[prefix]
        try:
            fetch(artifact)
            links[job_id].append(artifact["id"])
        except (BadZipFile, ValueError, OSError, subprocess.SubprocessError):
            gaps.append((job_id, artifact["id"]))
    return links, gaps


def inspect_run(repo, run, selected=None):
    jobs = run_jobs(repo, run["id"], int(run["run_attempt"]))
    selected = [j for j in jobs if j["conclusion"] in RED and (selected is None or j["id"] in selected)]
    if not selected:
        return []
    attach_reasons(repo, run, jobs)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
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
            rows.extend(result)
        for row in rows:
            row["run"] = run["id"]
            row["artifacts"] = links[row["job"]]
            row["unreadable_artifacts"] = [ident for job, ident in gaps if job in (None, row["job"])]
            row["missing"] = sorted({rule for message in row.get("missing", [])
                                     for rule in re.findall(r"evidence defect: \[([a-z-]+)\]", message)})
            if row["unreadable_artifacts"]:
                row["missing"].append("artifact-unavailable")
                for key in ("A1", "A2"):
                    if row[key] == "yes":
                        row[key] = "no"
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
            kind += f" · [run {reason['run']}](https://github.com/{repo}/actions/runs/{reason['run']})"
            kind += f" {reason['head_sha'][:12]} {reason['event']}"
        if reason.get("kind") == "manual-or-api":
            kind += " · " + reason["message"] + (" " + reason["actor"] if reason.get("actor") else "")
        base = f"https://github.com/{repo}/actions/runs/{run}"
        links = ", ".join(f"[{a}]({base}/artifacts/{a})" for a in row["artifacts"])
        lines.append(f"| {run} | [{job}](https://github.com/{repo}/actions/runs/{run}/job/{job}) | "
                     f"{kind} | {row['A1']} | {row['A2']} | {', '.join(row['missing']) or '—'} | {links or '—'} |")
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
            if run.get("conclusion") in RED or args.jobs:
                rows.extend(inspect_run(args.repo, run, selections.get((run["id"], run["run_attempt"]))))
    print(format_rows(args.repo, rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
