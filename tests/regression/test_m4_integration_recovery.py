"""Regressions from the integration and publication review (area 4, 2026-10-03): I1 to I5."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from aewflow import prepare_and_validate, sample_project, to_commit_ready
from conftest import git, make_git_repo

from aew.errors import GitError
from aew.workspace import integration as I


def main_commit(p) -> str:
    return git("rev-parse", "refs/heads/main", cwd=p.root)


def control(p, wid) -> dict:
    return p.ok("work", "show", wid)["control"]


def test_after_a_post_cas_crash_a_later_operator_commit_does_not_strand_the_ticket(tmp_path):
    """I1: after a crash past the CAS, the operator's local edit is refused with advice to stash or restore, never to
    commit. If they commit anyway, the paths their commit settled are left as they are, reported, and the Ticket
    reaches DONE instead of staying `publishing` for ever."""
    p = sample_project(tmp_path)
    a, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, a)
    res = p.aew("integrate", "publish", a, "--token", p.token, "--expect-rev", str(p.rev()),
                env={"AEW_FAULT": "integrate.after_cas"})
    assert res.returncode == 86 and main_commit(p) == integ["candidate"]
    core = p.root / "calc/core.py"
    core.write_text(core.read_text() + "# operator note\n", encoding="utf-8", newline="\n")
    res = p.aew("integrate", "reconcile", a, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR", res.stderr
    assert "Stash" in res.error["message"] and "commit/stash" not in res.error["message"]
    assert "calc/core.py" in res.error["details"]["paths"]
    git("commit", "-q", "-am", "operator commit on top of the published candidate", cwd=p.root)
    later = main_commit(p)
    done = p.lead("integrate", "reconcile", a)
    assert done["state"] == "DONE" and main_commit(p) == later  # the operator's commit is never rewritten
    settled = done["worktree_sync"]["settled_by_later_commit"]
    assert settled["commit"] == later and "calc/core.py" in settled["paths"]
    assert core.read_text().endswith("# operator note\n")


def test_a_failed_ref_update_with_an_unmoved_ref_keeps_the_candidate(tmp_path):
    """I2: a leftover ref lock makes `update-ref` fail without the ref moving. That is a git error, the candidate stays
    publishable, and reconcile publishes it once the cause is gone; it is not recorded as a stale candidate."""
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
    assert res.error["code"] == "GIT_ERROR", res.stderr
    assert "has not moved" in res.error["message"]
    assert main_commit(p) == before
    assert control(p, wid)["integration"]["status"] == "publishing"
    done = p.lead("integrate", "reconcile", wid)
    assert done["state"] == "DONE" and main_commit(p) == integ["candidate"]


def test_a_candidate_whose_worktree_is_gone_is_refused_clearly_and_can_be_prepared_again(tmp_path):
    """I3: publish refuses with an AEW error naming the next step (not a traceback), and prepare replaces the
    candidate."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    shutil.rmtree(integ["workspace"])
    subprocess.run(["git", "worktree", "prune"], cwd=p.root, check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "GATE_UNSATISFIED" and "integrate prepare" in res.error["message"], res.stderr
    assert "Traceback" not in res.stderr
    again = p.lead("integrate", "prepare", wid)
    assert again["integration"]["status"] == "prepared" and again["integration"]["attempt"] == 2
    history = control(p, wid)["integration_history"]
    assert "worktree is gone" in history[-1]["retired"]["reason"]


def test_git_with_a_missing_directory_is_an_aew_error(tmp_path):
    """I3: git run in a directory that no longer exists raises GitError, which the CLI reports."""
    with pytest.raises(GitError, match="does not exist"):
        I.git.git("status", cwd=tmp_path / "gone")


def test_a_case_only_rename_is_refused_up_front_on_a_case_insensitive_checkout(tmp_path):
    """I4: paths that differ only by case name one file on a case-insensitive filesystem. They are reported when the
    candidate is prepared, naming the platform limit, not later as the operator's local change."""
    repo = make_git_repo(tmp_path / "repo", {"Foo.txt": "same content\n"})
    insensitive = (repo / ".GIT").exists()
    assert I.case_only_renames(repo, ["Foo.txt", "foo.txt", "bar.txt"]) == ([["Foo.txt", "foo.txt"]] if insensitive
                                                                            else [])
    assert I.case_only_renames(repo, ["Foo.txt", "bar.txt"]) == []


def test_a_merge_that_fails_without_a_conflict_is_a_failure_not_a_conflict(tmp_path):
    """I5: `git merge` failing for another reason (here: an unknown commit) is a GitError, not a conflict with no
    paths."""
    repo = make_git_repo(tmp_path / "repo", {"a.txt": "a\n"})
    with pytest.raises(GitError, match="without a conflict"):
        I.merge_candidate(repo, repo, "0" * 40, "merge")

