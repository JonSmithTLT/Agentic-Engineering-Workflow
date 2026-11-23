"""Write the completed canceled run's evidence record from its server-side jobs, annotations and published files."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote

import yaml
from cancel_evidence import ci_group, observe, run_jobs
from evidence_scorecard import format_rows, inspect_run
from flake_register import INDEX_MEMBER, REGISTER_PATH, _api, _gh_read, _matches_session, _pages


def record(repo, run):
    rows = inspect_run(repo, run)
    summary = format_rows(repo, rows)
    artifacts = list(_pages(repo, f"actions/runs/{run['id']}/artifacts?per_page=100", "artifacts"))
    base = f"https://github.com/{repo}/actions/runs/{run['id']}"
    summary += "\n\nRun artifacts: " + (", ".join(f"[{int(a['id'])}]({base}/artifacts/{int(a['id'])})"
                                                  for a in artifacts) or "none")
    missing = sum(bool(r["missing"]) for r in rows)
    identity = f"aew-evidence-run-{run['id']}-attempt-{run['run_attempt']}"
    payload = {"name": "evidence", "head_sha": run["head_sha"], "external_id": identity, "status": "completed",
               "conclusion": "failure" if missing else "success",
               "details_url": f"https://github.com/{repo}/actions/runs/{run['id']}/attempts/{run['run_attempt']}",
               "output": {"title": f"Canceled run {run['id']}: {len(rows)} jobs, {missing} with missing evidence",
                          "summary": summary}}
    matches = [check for check in _pages(repo, f"commits/{run['head_sha']}/check-runs?check_name=evidence"
                                          "&filter=all&per_page=100", "check_runs")
               if check.get("external_id") == identity and (check.get("app") or {}).get("slug") == "github-actions"]
    endpoint = f"repos/{repo}/check-runs"
    method = "POST"
    if matches:
        method = "PATCH"
        endpoint += "/" + str(max(c["id"] for c in matches))
        payload.pop("head_sha")
    # Check outputs cap the summary at 65,535 characters. Retain each job via the run details link when it overflows.
    if len(summary.encode()) > 65000:
        payload["output"]["summary"] = "\n".join(["The per-job artifact links exceeded the check summary limit.",
                                                 *(f"Job {row['job']}: {row['kind']} A1={row['A1']} A2={row['A2']}"
                                                   for row in rows)])
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        _gh_read("--method", method, endpoint, "--input", str(path))
    print(f"Recorded cancellation evidence for run {run['id']} attempt {run['run_attempt']}.")
    return rows


def record_test_sightings(directory, run, rows):
    # This registry is the validated default-branch copy. Reading it needs no pytest or project installation.
    entries = yaml.safe_load(REGISTER_PATH.read_text(encoding="utf-8"))["entries"]
    sightings = []
    for row in rows:
        if row["kind"] != "test_failure" or not row.get("started_at"):
            continue
        for entry in entries:
            if (entry["scope"] == "test" and entry["status"] == "open" and _matches_session(entry, row["name"])
                    and any(node == entry["test"] or node.startswith(entry["test"] + "[")
                            for node in row["failed_nodes"])):
                sightings.append({"source_run": run["id"], "entry": entry["id"], "job": row["job"],
                                  "at": row["started_at"], "observation": "failed before cancellation"})
    if sightings:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / INDEX_MEMBER).write_text(json.dumps(sightings), encoding="utf-8")


def predecessor(repo, current):
    group = ci_group(current)
    if not group or not re.fullmatch(r"ci-[0-9]+", group) or current["event"] != "pull_request":
        return None
    branch = quote(current["head_branch"], safe="")
    earlier = [r for r in _api(repo, f"actions/workflows/{current['workflow_id']}/runs?branch={branch}"
                                "&event=pull_request&per_page=100")["workflow_runs"]
               if r["id"] != current["id"] and r["created_at"] <= current["created_at"]
               and (r.get("head_repository") or {}).get("id") == (current.get("head_repository") or {}).get("id")]
    if not earlier:
        return None
    prev = max(earlier, key=lambda r: (r["created_at"], r["id"]))
    if prev.get("conclusion") != "cancelled":
        return None
    jobs = run_jobs(repo, prev["id"], prev["run_attempt"])
    for job in jobs:
        if job["conclusion"] == "cancelled" and observe(repo, prev, job, jobs).get("run") == current["id"]:
            return prev
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--index-dir", type=Path)
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    run = _api(repo, f"actions/runs/{args.run}")
    ci = run["path"] == ".github/workflows/ci.yml"
    plant = (run["path"] == ".github/workflows/evidence-proof.yml" and run["event"] == "workflow_dispatch"
             and re.fullmatch(r"evidence-cancel-run-[0-9]+-[0-9]+-(?:supersede|manual)-target", run["display_title"]))
    if run["conclusion"] == "cancelled" and (ci or plant) and run["repository"]["full_name"] == repo:
        rows = record(repo, run)
        if ci and args.index_dir is not None:
            record_test_sightings(args.index_dir, run, rows)


if __name__ == "__main__":
    main()
