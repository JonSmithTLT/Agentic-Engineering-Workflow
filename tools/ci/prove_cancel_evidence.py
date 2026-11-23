"""Cancel only the isolated dispatch target created by this proof and verify the server's completed record."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from io import BytesIO
from zipfile import ZipFile

from cancel_evidence import _api, _pages, check_annotations, classify
from flake_register import _gh_read


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
        return next((j for j in jobs if j["name"] == "Controlled cancellation target" and any(
            step["name"] == "Hold the synthetic target" and step["status"] == "in_progress"
            for step in j.get("steps", []))), None)

    job = poll(live, 360, "the synthetic target to publish its readiness artifact and enter its hold step")
    if scenario == "manual":
        _gh_read("--method", "POST", f"repos/{repo}/actions/runs/{ident}/cancel")
        replacements = []
    else:
        dispatch(repo, workflow, branch, origin, scenario, "replacement")
        successor = poll(lambda: target_run(repo, workflow, parent, head, branch, group + "-replacement"),
                         90, "the unique replacement run")
        replacements = [successor]

    def finished():
        run = _api(repo, f"actions/runs/{ident}")
        if run["status"] == "completed":
            if run["conclusion"] != "cancelled":
                raise RuntimeError(f"synthetic target concluded {run['conclusion']}")
            return run
        return None

    ended = poll(finished, 360, "the target's canceled run conclusion")
    ended_job = _api(repo, f"actions/jobs/{job['id']}")
    notes = check_annotations(repo, ended_job["id"])
    reason = classify(ended, ended_job, notes, replacements)
    expected = "manual-or-api" if scenario == "manual" else "superseded"
    if reason["kind"] != expected or (replacements and reason.get("run") != replacements[0]["id"]):
        raise RuntimeError(f"observed reason does not establish the planted {scenario} cancellation: {reason}")
    if classify(ended, ended_job, [], replacements)["kind"] != "unresolved":
        raise RuntimeError("disabling the annotation fetch retained attribution")
    records = list(_pages(repo, f"actions/runs/{ident}/artifacts?per_page=100", "artifacts"))
    ready = next((a for a in records if a["name"] == "controlled-cancel-ready" and not a["expired"]), None)
    if not ready or not 0 < ready["size_in_bytes"] < 4096:
        raise RuntimeError("the canceled run has no bounded readiness artifact")
    data = _gh_read(f"repos/{repo}/actions/artifacts/{int(ready['id'])}/zip")
    with ZipFile(BytesIO(data)) as zipped:
        member = "controlled-cancel-ready.txt"
        if (zipped.namelist() != [member] or zipped.getinfo(member).file_size > 128
                or zipped.read(member).strip() != b"Controlled cancellation target ready."):
            raise RuntimeError("canceled run's downloaded readiness artifact did not match its controlled target")
    print(f"Canceled run {ident}, job {ended_job['id']}, reason {json.dumps(reason)}.")
    if current["event"] == "schedule" or (current["event"] == "workflow_dispatch" and branch == "main"):
        external = f"aew-evidence-run-{ident}-attempt-{ended['run_attempt']}"
        check = poll(lambda: next((c for c in _pages(repo, f"commits/{head}/check-runs?check_name=evidence"
                                                     "&filter=all&per_page=100", "check_runs")
                                  if c.get("external_id") == external), None), 420, "the default-branch recorder")
        if check["status"] != "completed" or check["conclusion"] != "success":
            raise RuntimeError(f"completed-run evidence record did not pass: {check['id']}")
        print(f"Verified default-branch evidence check {check['id']} for the canceled run.")


if __name__ == "__main__":
    main(sys.argv[1])
