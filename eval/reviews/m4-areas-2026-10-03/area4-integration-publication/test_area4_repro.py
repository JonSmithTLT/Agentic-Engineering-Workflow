"""Area 4 (integration and publication) reproductions against the frozen tree at a6cdc64.

Run from the review folder:
    venv/Scripts/python -m pytest repro/test_area4_repro.py -q -p no:cacheprovider --rootdir repro
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import _env  # noqa: F401  (sys.path for the tree's test helpers)
from aewflow import SUBTRACT_PATCH, create_planned_ticket, prepare_and_validate, sample_project, to_commit_ready
from conftest import git, make_git_repo

from aew.errors import IntegrityError
from aew.workspace import integration as I


def main_commit(p) -> str:
    return git("rev-parse", "refs/heads/main", cwd=p.root)


def control(p, wid) -> dict:
    return p.ok("work", "show", wid)["control"]


# R1 ------------------------------------------------------------------------------------------------------------------

def test_r1_update_ref_failure_with_unmoved_ref_is_recorded_as_stale_candidate(tmp_path):
    """integration.py:102-108: every update-ref failure is reported as 'the ref moved' and the validated candidate is
    retired to stale_candidate, even when the ref did not move (here: a leftover ref lock file)."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    before = main_commit(p)
    lock = p.root / ".git" / "refs" / "heads" / "main.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"")
    try:
        res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    finally:
        lock.unlink()
    assert res.error["code"] == "STALE_CANDIDATE", res.stderr
    details = res.error["details"]
    assert details["current"] == details["expected"] == before == integ["base"]  # the ref never moved
    assert main_commit(p) == before
    assert control(p, wid)["integration"]["status"] == "stale_candidate"  # a validated candidate, discarded
    # and only a full re-prepare + re-verification gets it back
    again = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert again.error["code"] == "ILLEGAL_TRANSITION"


# R2 ------------------------------------------------------------------------------------------------------------------

@pytest.mark.skipif(not Path(__file__).resolve().parent.joinpath("_ENV.PY").exists(),
                    reason="needs a case-insensitive filesystem")
def test_r2_case_only_rename_is_refused_as_a_local_change(tmp_path):
    """integration.py:182-207 + 266-278: on a case-insensitive checkout, worktree_entries() resolves the NEW name of a
    case-only rename to the OLD file, so precheck_sync refuses the publish as 'local change' although the worktree is
    exactly H. The candidate can never be published on this platform, and the message blames the operator."""
    repo = make_git_repo(tmp_path / "repo", {"Foo.txt": "same content\n"})
    h = git("rev-parse", "HEAD", cwd=repo)
    git("mv", "Foo.txt", "tmp.txt", cwd=repo)
    git("mv", "tmp.txt", "foo.txt", cwd=repo)
    git("commit", "-q", "-m", "case-only rename", cwd=repo)
    m = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", h, cwd=repo)  # the authoritative worktree is exactly H
    assert sorted(I.changed_between(repo, h, m)) == ["Foo.txt", "foo.txt"]
    assert git("status", "--porcelain", cwd=repo) == ""
    with pytest.raises(IntegrityError) as exc:
        I.precheck_sync(repo, h, ["Foo.txt", "foo.txt"])
    assert "foo.txt" in exc.value.details["paths"]
    assert "local change" in exc.value.details["paths"]["foo.txt"]


# R3 ------------------------------------------------------------------------------------------------------------------

def test_r3_two_mutating_tickets_cannot_overlap_at_publish(tmp_path):
    """Sound: the mutating-concurrency guard refuses a second mutating assignment while the first Ticket holds an
    unintegrated workspace, so two candidates can never race the same path through sync today."""
    p = sample_project(tmp_path)
    a, _ = to_commit_ready(p, tmp_path)
    b = create_planned_ticket(p, tmp_path, title="Document calc.core")
    res = p.aew("work", "assign", b, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "CONCURRENCY_LIMIT"


def test_r3b_after_a_post_cas_crash_the_advised_commit_leaves_the_ticket_stuck_in_publishing(tmp_path):
    """integration.py:329-333 + integration_ops.py:313-320: after a crash past the CAS, a path the operator then
    changed AND COMMITTED (as the refusal advises) matches neither H nor M, so reconcile refuses forever: the Ticket
    is published on main but can never reach DONE, and every other state change is refused while `publishing`."""
    p = sample_project(tmp_path)
    a, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, a)
    res = p.aew("integrate", "publish", a, "--token", p.token, "--expect-rev", str(p.rev()),
                env={"AEW_FAULT": "integrate.after_cas"})
    assert res.returncode == 86 and main_commit(p) == integ["candidate"]
    # the operator edits a path the integration changes, then follows the refusal's advice and commits it
    core = p.root / "calc/core.py"
    core.write_text(core.read_text() + "# operator note\n", encoding="utf-8", newline="\n")
    res = p.aew("integrate", "reconcile", a, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and "commit/stash" in res.error["message"]
    git("commit", "-q", "-am", "operator commit on top of the published candidate", cwd=p.root)
    res = p.aew("integrate", "reconcile", a, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR", res.stderr          # still refused after committing
    assert control(p, a)["integration"]["status"] == "publishing"
    for args in (("work", "transition", a, "--to", "RUNNING", "--reason", "x"),
                 ("work", "cancel", a, "--reason", "x")):
        res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
        assert res.error["code"] == "ILLEGAL_TRANSITION"
    c = create_planned_ticket(p, tmp_path, title="Depends on A", extra=("--depends-on", a))
    assert control(p, c)["state"] == "BLOCKED"                       # A's output is on main, but never DONE


# R4 ------------------------------------------------------------------------------------------------------------------

def test_r4_a_validated_candidate_whose_worktree_is_gone_cannot_be_published_or_re_prepared(tmp_path):
    """integration_ops.py:103-104 + 164-170: publish needs the integration worktree (to re-snapshot it); prepare refuses
    because a validated candidate exists. Losing the worktree leaves only a regression to RUNNING (full re-review)."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    shutil.rmtree(integ["workspace"])
    subprocess.run(["git", "worktree", "prune"], cwd=p.root, check=True, capture_output=True)
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0
    assert "Traceback" in res.stderr and "NotADirectoryError" in res.stderr, res.stderr   # not an AEW error
    publish_code = "python traceback (NotADirectoryError)"
    res = p.aew("integrate", "prepare", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "ILLEGAL_TRANSITION", res.stderr
    assert control(p, wid)["integration"]["status"] == "validated"
    print(f"publish failed with {publish_code}; prepare refused; status still validated")
