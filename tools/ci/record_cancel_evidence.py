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
from cancel_evidence import MANUAL, ci_group, classify, observe, run_jobs
from evidence_scorecard import format_rows, inspect_run
from flake_register import INDEX_MEMBER, REGISTER_PATH, _api, _gh_read, _matches_session, _own_ci_run, _pages
from stage_evidence import stage


def scan_details(rows):
    """The completed-run check is public. Re-scan details derived from artifacts in the trusted recorder."""
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "raw"
        checked = Path(tmp) / "checked"
        source.mkdir()
        details = {}
        for row in rows:
            if row.get("defects"):
                filename = f"runner-resources-defects-{int(row['job'])}.txt"
                details[row["job"]] = filename
                text = "\n".join(d.replace("\r", " ").replace("\n", " ")[:1500] for d in row["defects"])
                (source / filename).write_text(text, encoding="utf-8")
        if not details:
            return
        stage(source, checked)
        for row in rows:
            if row["job"] not in details:
                continue
            path = checked / details[row["job"]]
            if path.is_file():
                row["defects"] = path.read_text(encoding="utf-8").splitlines()
            else:
                row["defects"] = ["evidence defect: [scan-unavailable] defect details withheld"]
                row["missing"].append("scan-unavailable")


def record(repo, run, report_dir=None):
    rows = inspect_run(repo, run)
    scan_details(rows)
    summary = format_rows(repo, rows)
    artifacts = list(_pages(repo, f"actions/runs/{run['id']}/artifacts?per_page=100", "artifacts"))
    base = f"https://github.com/{repo}/actions/runs/{run['id']}"
    summary += "\n\nRun artifacts: " + (", ".join(f"[{int(a['id'])}]({base}/artifacts/{int(a['id'])})"
                                                  for a in artifacts) or "none")
    missing = sum(bool(r["missing"]) for r in rows)
    if not rows:
        jobs = run_jobs(repo, run["id"], run["run_attempt"])
        status = "Cancelled before any job was recorded" if not jobs else "No canceled job was recorded"
        reason = classify(run, {}, [{"path": ".github", "message": MANUAL}]) if run.get("cancelled_by") else {}
        if reason.get("actor"):
            summary += f"\n\n{status}. {MANUAL} Actor: {reason['actor']}."
        else:
            summary += f"\n\n{status}. Run evidence defect: [cancel-reason] no available cancellation attribution."
            missing += 1
    identity = f"aew-evidence-run-{run['id']}-attempt-{run['run_attempt']}"
    payload = {"name": "evidence", "head_sha": run["head_sha"], "external_id": identity, "status": "completed",
               "conclusion": "failure" if missing else "success",
               "details_url": f"https://github.com/{repo}/actions/runs/{run['id']}/attempts/{run['run_attempt']}",
               "output": {"title": f"Canceled run {run['id']}: {len(rows)} red jobs, {missing} evidence gaps",
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
        if report_dir is None:
            raise ValueError("the full evidence check needs a report output directory")
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "evidence.md").write_text(summary, encoding="utf-8")
        recorder = int(os.environ["GITHUB_RUN_ID"])
        attempt = int(os.environ["GITHUB_RUN_ATTEMPT"])
        url = f"https://github.com/{repo}/actions/runs/{recorder}/attempts/{attempt}"
        payload["output"]["summary"] = (
            f"The complete scanned A3 diagnostics and job links are in the [recorder artifacts]({url}), "
            f"under cancel-evidence-{run['id']}-attempt-{run['run_attempt']}.")
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
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--index-dir", type=Path)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    run = _api(repo, f"actions/runs/{args.run}/attempts/{args.attempt}")
    ci = run["path"] == ".github/workflows/ci.yml"
    plant = (run["path"] == ".github/workflows/evidence-proof.yml" and run["event"] == "workflow_dispatch"
             and run["name"] == "evidence-proof" and any(
                 re.fullmatch(r"evidence-cancel-run-[0-9]+-[0-9]+-(?:supersede|manual)-target", job["name"])
                 for job in run_jobs(repo, run["id"], run["run_attempt"])))
    if run["conclusion"] == "cancelled" and (ci or plant) and run["repository"]["full_name"] == repo:
        rows = record(repo, run, args.report_dir)
        if _own_ci_run(repo, run) and args.index_dir is not None:
            record_test_sightings(args.index_dir, run, rows)


if __name__ == "__main__":
    main()
