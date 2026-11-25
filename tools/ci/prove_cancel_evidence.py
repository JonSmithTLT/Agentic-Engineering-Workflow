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
    failed = None
    while time.monotonic() < until:
        try:
            result = find()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            # One failed read, such as of a run seconds old whose attempt is not yet readable, is not the answer:
            # only the deadline ends the wait (#546, job 138579044835). A finding that raises otherwise still ends it.
            failed, result = exc, None
        if result:
            return result
        time.sleep(5)
    raise RuntimeError(f"timed out waiting for {purpose}" + (f"; the last read failed: {failed}" if failed else ""))


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


# Both controlled plants get 360 s from their first deadline step, and run at
# least that long if uninterrupted (180 serially scheduled cases of 2-5 s).
# Leave time for dispatch and delivery before pytest switches to collection.
CANCEL_PLANT_SECONDS = 360
TRIGGER_RESERVE_SECONDS = 60
# A target plant holds its deadline step until its twin has a runner, for at most this long, so one platform's runner
# queueing does not spend the other's window before both can be live (target runs 45513035294 and 45547533341, where
# the Windows plant started 5 min 22 s and 5 min 23 s after its Linux twin). The workflow's barrier step states it.
TWIN_BARRIER_SECONDS = 600
RUNNER_ALLOCATION_SECONDS = 20 * 60
PLANT_LABELS = tuple(f"plant ({runner}, cancel, none)" for runner in ("ubuntu-24.04", "windows-latest"))


class PlantQueued(RuntimeError):
    """A plant's runner queued past its twin's live window: runner allocation, not the evidence under test.

    It is never a pass, and never the overlap failure: both plants were never live together, so nothing was triggered.
    """

    code = "plant-queued"


def wait_for_workers(repo, ident):
    labels = PLANT_LABELS

    def jobs():
        return _api(repo, f"actions/runs/{ident}/attempts/1/jobs?per_page=100")["jobs"]

    def runner(job):
        return job is not None and bool(job.get("runner_id") or job.get("conclusion"))

    # GitHub can accept the dispatch while neither child has a runner. Start the existing nine-minute readiness
    # clock only once the later target has one: each plant's own window counts from its own deadline step.
    def assigned():
        named = {job["name"]: job for job in jobs()}
        return all(runner(named.get(label)) for label in labels)

    try:
        poll(assigned, RUNNER_ALLOCATION_SECONDS, "a hosted runner to be assigned to both controlled lanes")
    except RuntimeError as exc:
        named = {job["name"]: job for job in jobs()}
        if any(runner(named.get(label)) for label in labels):
            late = [label for label in labels if not runner(named.get(label))]
            raise PlantQueued(f"a plant's runner queued past its deadline: {', '.join(late)} had no runner "
                              f"{RUNNER_ALLOCATION_SECONDS} s after dispatch while its twin ran") from exc
        raise

    def ended(job):
        lane = next((step for step in job.get("steps", []) if step["name"] == "Real planted lane"), {})
        return bool(job.get("conclusion")) or lane.get("status") == "completed"

    def live():
        attempt = jobs()
        named = {job["name"]: job for job in attempt}
        # A twin so late that the early plant's lane already ended at its session deadline is the same queueing, not
        # a target that finished early or lost its execution window (#564 review).
        for label, twin in zip(labels, reversed(labels), strict=True):
            job, other = named.get(label), named.get(twin)
            if job and ended(job) and not (other and (ended(other) or ready_job(twin, attempt, SENTINEL_READY_S))):
                raise PlantQueued(f"a plant's runner queued past its deadline: {twin} was not live before "
                                  f"{label}'s lane ended")
        active = [ready_job(label, attempt, SENTINEL_READY_S) for label in labels]
        for job in filter(None, active):
            steps = {step["name"]: step for step in job["steps"]}
            lane = steps["Real planted lane"]
            deadline_step = steps.get("The job's deadline", {})
            if not deadline_step.get("started_at") or lane.get("status") != "in_progress":
                raise RuntimeError("controlled pytest lane has no active execution window")
            opened = datetime.fromisoformat(deadline_step["started_at"]).timestamp()
            if time.time() >= opened + CANCEL_PLANT_SECONDS - TRIGGER_RESERVE_SECONDS:
                if not all(active):
                    # The twin is not yet live, so its runner or setup came too late for this window: name it.
                    late = [label for label, other in zip(labels, active, strict=True) if not other]
                    raise PlantQueued(f"a plant's runner queued past its deadline: {', '.join(late)} was not live "
                                      f"before {job['name']} reached its trigger reserve")
                raise RuntimeError("controlled pytest lanes have no overlapping time before collection")
        return active if all(active) else None

    return poll(live, 9 * 60, "both controlled pytest lanes to enter their worker sessions")


def verify_pretrigger(directory, attempt, trigger_at):
    linux = directory / f"plant-Linux-cancel-none-attempt-{attempt}"
    if problems := observe_cancel(linux, "Linux", []):
        raise RuntimeError(str(problems))
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

    targets = wait_for_workers(repo, ident)
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
    try:
        main(sys.argv[1])
    except PlantQueued as exc:
        print(f"::error title={exc.code}::{exc}")
        raise SystemExit(1) from exc
