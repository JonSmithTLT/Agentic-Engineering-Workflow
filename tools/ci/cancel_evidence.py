"""Attribute a cancellation from check-run annotations and the workflow's actual concurrency group."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flake_register import CHECK_CONCURRENCY, _api, _pages, check_annotations  # noqa: E402

PRIORITY = re.compile(r"Cancel(?:ing|ling) since a higher priority waiting request for (.+?) exists\.?")
MANUAL = "The operation was canceled."
LOGIN = r"[a-zA-Z0-9-]+(?:\[bot\])?"
CANCEL_ACTOR = re.compile(rf"The run was cancel(?:ed|led) by @({LOGIN})\.")
REASON_FILE = "runner-resources-cancel-reason.txt"
# ci_group names this workflow's own concurrency group: another workflow's run is not in it.
CI_WORKFLOW = ".github/workflows/ci.yml"


def priority_group(notes):
    for note in notes:
        match = PRIORITY.fullmatch((note.get("message") or "").strip())
        if note.get("path") == ".github" and match:
            return match[1]
    return None


def ci_group(run):
    numbers = {p["number"] for p in run.get("pull_requests", []) if isinstance(p.get("number"), int)}
    if run.get("event") == "pull_request" and len(numbers) == 1:
        return f"ci-{numbers.pop()}"
    if run.get("event") == "push":
        return f"ci-{run['head_sha']}"
    return None


def replacement(run, group, candidates, jobs):
    ident = run["id"]
    for runner, platform in (("ubuntu-24.04", "linux"), ("windows-latest", "windows")):
        if group == f"evidence-{ident}-{run['run_attempt']}-{runner}-cancel-none" and any(
                job["name"] == f"cancel-trigger-{platform}" for job in jobs):
            return run  # the synthetic replacement is another job in the same run
    plant_group = re.fullmatch(r"evidence-cancel-run-[0-9]+-[0-9]+-(?:supersede|manual)", group)
    ci = re.fullmatch(r"ci-[0-9]+", group)
    if not (ci or plant_group) or (ci and ci_group(run) not in (None, group)):
        return None
    repository = (run.get("head_repository") or {}).get("id")
    if not repository:
        return None
    valid = []
    for candidate in candidates:
        if (candidate["id"] == ident or candidate.get("workflow_id") != run.get("workflow_id")
                or candidate.get("event") != run.get("event") or candidate["created_at"] < run["created_at"]
                or candidate.get("head_branch") != run.get("head_branch")
                or (candidate.get("head_repository") or {}).get("id") != repository):
            continue
        if group.startswith("ci-"):
            if run.get("event") != "pull_request" or ci_group(candidate) != group:
                continue
        elif candidate.get("display_title") != group + "-replacement":
            continue
        valid.append(candidate)
    return valid[0] if len(valid) == 1 else None


def classify(run, job, notes, candidates=(), jobs=()):
    group = priority_group(notes)
    if group:
        successor = replacement(run, group, candidates, jobs)
        if successor:
            return {"kind": "superseded", "run": successor["id"], "head_sha": successor["head_sha"],
                    "event": successor["event"]}
        return {"kind": "unresolved", "detail": "priority cancellation observed; replacement not established"}
    notes = [n.get("message") or "" for n in notes if n.get("path") == ".github"]
    actors = {m[1] for text in notes if (m := CANCEL_ACTOR.fullmatch(text))}
    run_wide = bool(actors or run.get("cancelled_by"))
    if MANUAL in notes or actors:
        result = {"kind": "manual-or-api", "message": MANUAL}
        # actor/triggering_actor identify who started a run. They do not identify the caller that cancelled it.
        caller = job.get("cancelled_by") or run.get("cancelled_by")
        actor = caller.get("login") if isinstance(caller, dict) else None
        if isinstance(actor, str) and re.fullmatch(LOGIN, actor):
            actors.add(actor)
        if len(actors) == 1:
            result["actor"] = actors.pop()
            if run_wide:
                result["scope"] = "run"
        return result
    return {"kind": "unresolved", "detail": "cancellation annotation unavailable"}


def valid(reason):
    if not isinstance(reason, dict):
        return False
    if reason.get("kind") == "superseded":
        return (type(reason.get("run")) is int and reason["run"] > 0
                and isinstance(reason.get("head_sha"), str) and re.fullmatch(r"[0-9a-f]{40}", reason["head_sha"])
                and reason.get("event") in ("pull_request", "workflow_dispatch", "push", "schedule"))
    return reason.get("kind") == "manual-or-api" and reason.get("message") == MANUAL


@cache
def run_jobs(repo, run, attempt):
    return list(_pages(repo, f"actions/runs/{run}/attempts/{attempt}/jobs?per_page=100", "jobs"))


@cache
def candidates(repo, workflow, branch, event, start, end):
    interval = quote(f"{start}..{end}", safe="")
    endpoint = (f"actions/workflows/{workflow}/runs?branch={quote(branch, safe='')}&event={quote(event, safe='')}"
                f"&created={interval}&per_page=100")
    return list(_pages(repo, endpoint, "workflow_runs"))


@cache
def commit_pulls(repo, sha):
    return list(_pages(repo, f"commits/{sha}/pulls?per_page=100"))


def with_pull_group(repo, run):
    if run.get("event") != "pull_request" or run.get("pull_requests"):
        return run
    # Actions sometimes omits pull_requests on an old run. Branch reuse alone cannot establish its concurrency group.
    prs = [p for p in commit_pulls(repo, run["head_sha"])
           if (p.get("head") or {}).get("ref") == run["head_branch"] and
           ((p.get("head") or {}).get("repo") or {}).get("id") == (run.get("head_repository") or {}).get("id")]
    return {**run, "pull_requests": prs}


def observe(repo, run, job, jobs):
    notes = check_annotations(repo, job["id"])
    group = priority_group(notes)
    newer = []
    if group and not group.startswith(f"evidence-{run['id']}-"):
        end = ((run.get("updated_at") if run.get("status") == "completed" else None)
               or job.get("completed_at") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        newer = [r for r in candidates(repo, run["workflow_id"], run["head_branch"], run["event"],
                                       run["created_at"], end)
                 if not job.get("completed_at") or r["created_at"] <= job["completed_at"]]
    if group and re.fullmatch(r"ci-[0-9]+", group):
        newer = [with_pull_group(repo, r) for r in newer if r["id"] != run["id"]]
    return classify(run, job, notes, newer, jobs)


def superseded_before_any_job(repo, run):
    """The one run that replaced a ci pull-request run cancelled before any of its jobs existed, or None.

    Such a run has no check run, so no annotation names its concurrency group (`observe` starts from one). The group
    is derived from the run instead (`ci_group`), and the successor comes from run history under `replacement`'s own
    rule: exactly one other run of that group created within this run's life. ci.yml cancels a pull request's run in
    progress for the next one of its group, so that run is what ended this one. No candidate, or more than one, names
    nothing: the caller keeps its attribution gap.
    """
    if (run.get("path") != CI_WORKFLOW or run.get("event") != "pull_request" or run.get("conclusion") != "cancelled"
            or not run.get("updated_at")):
        return None
    run = with_pull_group(repo, run)
    group = ci_group(run)
    if not group:
        return None
    newer = [with_pull_group(repo, r) for r in candidates(repo, run["workflow_id"], run["head_branch"], run["event"],
                                                          run["created_at"], run["updated_at"])
             if r["id"] != run["id"]]
    return replacement(run, group, newer, [])


def may_inherit_run_wide(run):
    """Whether a run-wide origin may still cover this run: it concluded cancelled, or it has not concluded yet.

    Assurance observes its own run, which is still in progress while that job runs, and GitHub creates the matrix
    jobs of a cancelled `needs` job after the cancellation, with no annotation of their own. A completed run that
    concluded otherwise was never cancelled whole.
    """
    return run.get("conclusion") == "cancelled" or (run.get("status") != "completed" and run.get("conclusion") is None)


def attach_reasons(repo, run, jobs):
    """A verified run-wide cancellation also covers queued siblings with no annotation of their own."""
    cancelled = [j for j in jobs if j.get("conclusion") == "cancelled"]
    if not cancelled:
        return
    with ThreadPoolExecutor(max_workers=CHECK_CONCURRENCY) as pool:
        reasons = list(pool.map(lambda j: observe(repo, run, j, jobs), cancelled))
    origins = {}
    for reason in reasons:
        if valid(reason):
            if reason["kind"] == "superseded" and reason["run"] != run["id"]:
                origins[("superseded", reason["run"])] = reason
            elif reason.get("scope") == "run" and reason.get("actor"):
                origins[("manual-or-api", reason["actor"])] = reason
    for job, reason in zip(cancelled, reasons, strict=True):
        if (may_inherit_run_wide(run) and len(origins) == 1
                and reason["kind"] in {"unresolved", "manual-or-api"} and not reason.get("actor")
                and not reason.get("detail", "").startswith("priority")):
            reason = next(iter(origins.values()))
        job["cancel_reason"] = reason


def collect_reason(root: Path, label: str):
    # The hosted check runner can add annotations after cleanup completes. Assurance/recorder will query them again.
    result = {"kind": "unresolved", "detail": "cancellation annotation unavailable at collection"}
    repo, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if repo and run_id and os.environ.get("GH_TOKEN"):
        try:
            run = _api(repo, f"actions/runs/{int(run_id)}")
            jobs = run_jobs(repo, run["id"], int(os.environ["GITHUB_RUN_ATTEMPT"]))
            target = next((job for job in jobs if job["name"] == label), None)
            if target:
                result = observe(repo, run, target, jobs)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            pass  # persist the explicit unavailable observation for the later recorder
    (root / REASON_FILE).write_text(json.dumps(result) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # This independent process is bounded even if several REST lookups would each reach gh's timeout.
    if len(sys.argv) == 4 and sys.argv[1] == "--lookup":
        collect_reason(Path(sys.argv[2]), sys.argv[3])
    else:
        try:
            subprocess.run([sys.executable, __file__, "--lookup", *sys.argv[1:]], check=True, timeout=12)
        except subprocess.TimeoutExpired:
            print("Cancellation metadata is not yet available; the completed-run observer will retry.")
