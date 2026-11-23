"""Cancel only the isolated dispatch target created by this proof and verify the server's completed record."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from cancel_evidence import _api, classify, run_jobs
from cancel_evidence_plant import SENTINEL_READY_S, ready_job
from evidence_files import PREFIX, entries
from evidence_scorecard import inspect_run
from flake_register import _gh_read
from verify_evidence import observe_cancel


def poll(find, seconds, purpose):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        result = find()
        if result:
            return result
        time.sleep(5)
    raise RuntimeError(f"timed out waiting for {purpose}")


def dispatch(repo, workflow, ref, origin, scenario, role):
    _gh_read("--method", "POST", f"repos/{repo}/actions/workflows/{workflow}/dispatches", "-f", f"ref={ref}",
             "-f", f"inputs[probe_origin]={origin}", "-f", f"inputs[probe_scenario]={scenario}",
             "-f", f"inputs[probe_role]={role}")


def target_run(repo, workflow, parent, head, branch, title):
    from urllib.parse import quote

    data = _api(repo, f"actions/workflows/{workflow}/runs?event=workflow_dispatch&branch={quote(branch, safe='')}"
                f"&head_sha={head}&per_page=100")
    found = [r for r in data["workflow_runs"] if r["id"] != parent and r["display_title"] == title
             and r["head_sha"] == head and r["workflow_id"] == workflow and r["event"] == "workflow_dispatch"
             and r["head_branch"] == branch and (r["head_repository"] or {}).get("full_name") == repo]
    if len(found) > 1:
        raise RuntimeError("multiple matching synthetic targets; no cancellation issued")
    return found[0] if found else None


def verify_pretrigger(directory, attempt, trigger_at):
    windows = directory / f"plant-Windows-cancel-none-attempt-{attempt}"
    problems = observe_cancel(windows, "Windows", [], trigger_at=trigger_at)
    if problems:
        raise RuntimeError(str(problems))
    # On the downloaded copy, remove only older snapshots. A post-trigger live observation cannot prove this twin.
    bound = datetime.fromisoformat(trigger_at).timestamp()
    for ring in windows.rglob("snapshots/*.txt"):
        blocks = re.split(r"(?m)(?=^" + re.escape(PREFIX) + ")", ring.read_text(encoding="utf-8"))
        kept = [block for block in blocks if not any(sample["at"] <= bound for sample, _ in entries(block))]
        ring.write_text("".join(kept), encoding="utf-8")
    problems = observe_cancel(windows, "Windows", [], trigger_at=trigger_at)
    if not any("no labelled worker sample predating" in problem for problem in problems):
        raise RuntimeError("the missing pre-trigger Windows sample went undetected")


def main(scenario):
    if scenario not in {"manual", "supersede"}:
        raise ValueError("expected a controlled cancellation scenario")
    repo = os.environ["GITHUB_REPOSITORY"]
    parent = int(os.environ["GITHUB_RUN_ID"])
    current = _api(repo, f"actions/runs/{parent}")
    workflow = current["workflow_id"]
    head, branch = current["head_sha"], current["head_branch"]
    origin = f"{parent}-{int(os.environ['GITHUB_RUN_ATTEMPT'])}"
    group = f"evidence-cancel-run-{origin}-{scenario}"
    if current["path"] != ".github/workflows/evidence-proof.yml":
        raise ValueError("expected the isolated evidence proof workflow")
    try:
        dispatch(repo, workflow, branch, origin, scenario, "target")
    except subprocess.CalledProcessError as exc:
        error = (exc.stderr or b"").decode(errors="replace")
        if os.environ.get("GITHUB_EVENT_NAME") == "pull_request" and (
                "HTTP 403" in error or "Unexpected inputs" in error):
            print("This PR token or default-branch dispatch schema prevented the synthetic dispatch. "
                  "The scheduled default-branch proof must exercise it.")
            return
        raise
    target = poll(lambda: target_run(repo, workflow, parent, head, branch, group + "-target"), 90, "the target run")
    ident = target["id"]

    def live():
        jobs = _api(repo, f"actions/runs/{ident}/jobs?per_page=100")["jobs"]
        active = [ready_job(f"plant ({runner}, cancel, none)", jobs, SENTINEL_READY_S)
                  for runner in ("ubuntu-24.04", "windows-latest")]
        return active if all(active) else None

    targets = poll(live, 540, "both controlled pytest lanes to enter their worker sessions")
    if scenario == "manual":
        # A server timestamp taken before requesting cancellation is a conservative, independent lower bound.
        response = _gh_read("--include", "--silent", f"repos/{repo}/actions/runs/{ident}")
        date = next(line.split(b":", 1)[1].decode().strip() for line in response.splitlines()
                    if line.lower().startswith(b"date:"))
        trigger_at = parsedate_to_datetime(date).isoformat()
        _gh_read("--method", "POST", f"repos/{repo}/actions/runs/{ident}/cancel")
        replacements = []
    else:
        dispatch(repo, workflow, branch, origin, scenario, "replacement")
        successor = poll(lambda: target_run(repo, workflow, parent, head, branch, group + "-replacement"),
                         90, "the unique replacement run")
        replacements = [successor]
        trigger_at = successor["created_at"]

    def finished():
        run = _api(repo, f"actions/runs/{ident}")
        if run["status"] == "completed":
            if run["conclusion"] != "cancelled":
                raise RuntimeError(f"synthetic target concluded {run['conclusion']}")
            return run
        return None

    ended = poll(finished, 360, "the target's canceled run conclusion")
    ids = {job["id"] for job in targets}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        all_rows = inspect_run(repo, ended, directory=root)
        verify_pretrigger(root, ended["run_attempt"], trigger_at)
    gaps = {r["job"]: r["missing"] for r in all_rows if r["missing"]}
    if gaps:
        raise RuntimeError(f"the completed child record has missing evidence: {gaps}")
    rows = [r for r in all_rows if r["job"] in ids]
    if {r["job"] for r in rows} != ids:
        raise RuntimeError("the completed run did not retain both canceled target jobs")
    for row in rows:
        reason = row["cancel_reason"]
        expected = "manual-or-api" if scenario == "manual" else "superseded"
        if reason["kind"] != expected or (replacements and reason.get("run") != replacements[0]["id"]):
            raise RuntimeError(f"completed-run discovery did not establish the planted {scenario} cancel: {reason}")
        if scenario == "manual" and reason.get("actor") != "github-actions[bot]":
            raise RuntimeError("the hosted manual cancellation actor is missing or incorrect")
        if row["A2"] != "yes" or row["missing"] or not row["artifacts"]:
            raise RuntimeError(f"target {row['job']} lacks verifiable worker evidence: {row['missing']}")
        print(f"Canceled run {ident}, job {row['job']}, reason {json.dumps(reason)}, A2={row['A2']}, "
              f"verified artifact IDs {row['artifacts']}.")
    blind = classify(ended, targets[0], [], replacements, run_jobs(repo, ident, ended["run_attempt"]))
    if blind["kind"] != "unresolved":
        raise RuntimeError("disabling the annotation fetch retained attribution")


if __name__ == "__main__":
    main(sys.argv[1])
