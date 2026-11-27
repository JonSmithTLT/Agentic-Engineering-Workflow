"""A review of a named local ref, as a non-mutating Ticket (register E168; SYS-45; the designer's decision of
2026-11-06, (d); ADR-0008, amended).

A non-mutating Ticket may name a ref (``review_ref``). The name is fixed at creation (``resolve``): one full ref name,
never a commit, so a later checkout never changes what the Ticket reviews. The commit is fixed at each dispatch
(``pin``): the ref's commit then, with its merge-base against the authoritative branch, so each attempt reviews one
commit and says which. The executor's observation is a detached, read-only worktree at that commit, and its pack holds
the diff from the merge-base to it (``pack_view``).

AEW fetches nothing: a ref is what the operator's repository holds now, and every git call here reads through
``git.object_git`` (no replace refs, no lazy fetch, no window). What a ref name means (its accepted namespaces, its full
name, its commit) is ``aew.workspace.git``'s; what this module adds is what AEW refuses to review: the authoritative
branch, which an investigator Ticket observes, and AEW's own Ticket branches, whose change is reviewed through that
Ticket's own review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.errors import IllegalTransition, NotFound, PermissionDenied, Unavailable, UsageError
from aew.workspace import git, worktrees

# A ref review's diff, from the merge-base to the pinned commit, is in its pack whole up to this many bytes; above it,
# the pack holds its stat and changed paths with the command that reads the rest in the observation. A stated choice
# (E168 plan §3.7): a pack is read by a model, and a diff this size is already a long read.
REF_DIFF_MAX_BYTES = 256 * 1024
# The diff of two pinned commits: never an external diff tool or a text conversion, never renames guessed differently
# from one git to the next.
DIFF_ARGS = ("diff", "--no-ext-diff", "--no-textconv", "--no-color", "--no-renames")


def _aew_branch(full: str) -> bool:
    return full.startswith("refs/heads/" + worktrees.BRANCH_PREFIX)


def refuse_unreviewable(full: str, *, authoritative_branch: str) -> None:
    """Refuse a full ref name AEW does not review: the authoritative branch (``USAGE``, ``authoritative_ref``) and an
    AEW Ticket branch (``PERMISSION_DENIED``, ``aew_managed_ref``), each saying what to do instead."""
    if full == f"refs/heads/{authoritative_branch}":
        raise UsageError(f"{full} is the authoritative branch: its source is observed by an investigator Ticket (a "
                         "non-mutating Ticket without --review-ref), not reviewed as a ref", reason="authoritative_ref",
                         ref=full)
    if _aew_branch(full):
        raise PermissionDenied(
            f"{full} is an AEW Ticket branch: that Ticket's change is reviewed through its own review (`aew invoke "
            "create <T> --role reviewer`, or the `ticket_request_review` tool), and its unintegrated work stays "
            "invisible to other Tickets (ADR-0008)", reason="aew_managed_ref", ref=full)


def resolve(repo_root: Path, name: str, *, authoritative_branch: str) -> str:
    """The full ref name a Ticket created with ``--review-ref name`` records (``git.full_ref_name``), refused when AEW
    does not review it (``refuse_unreviewable``)."""
    full = git.full_ref_name(name, cwd=repo_root)
    refuse_unreviewable(full, authoritative_branch=authoritative_branch)
    return full


def pin(repo_root: Path, full: str, *, authoritative_branch: str, authoritative_commit: str) -> dict[str, Any]:
    """The pin of a ref review's attempt (``execution.ref_pin``): the commit ``full`` points at now, its merge-base with
    the authoritative commit (the first ``git merge-base --all`` prints, with how many there are), the authoritative
    branch and commit it was judged against, and any uncommitted work where the branch is checked out (reported, never
    refused: the review is of the commit). Refused, with ``reason`` in the details: a partial clone on a git that could
    fetch lazily (``UNAVAILABLE``, ``lazy_fetch_possible``), the ref gone (``NOT_FOUND``, ``unknown_ref``), a ref that
    is not a commit or lacks its objects (``git.ref_commit``), no merge-base (``ILLEGAL_TRANSITION``, ``no_merge_base``)
    and a ref already in the authoritative branch (``ILLEGAL_TRANSITION``, ``ref_already_contained``)."""
    refuse_unreviewable(full, authoritative_branch=authoritative_branch)
    if git.lazy_fetch_possible(repo_root):
        raise Unavailable("this repository is a partial clone and this git (older than 2.44) cannot be stopped from "
                          "fetching missing objects lazily, and AEW fetches nothing: review the ref in a full clone, "
                          "or upgrade git", reason="lazy_fetch_possible", ref=full)
    commit = git.ref_commit(full, cwd=repo_root)
    if commit is None:
        raise NotFound(f"{full} no longer exists; AEW fetches nothing: create or fetch it yourself and dispatch again, "
                       "or cancel the Ticket", reason="unknown_ref", ref=full)
    bases = git.merge_bases(authoritative_commit, commit, cwd=repo_root)
    if not bases:
        raise IllegalTransition(f"{full} shares no history with {authoritative_branch}, so there is no diff to review: "
                                "an investigator Ticket (without --review-ref) can study it", reason="no_merge_base",
                                ref=full, commit=commit)
    if bases[0] == commit:
        raise IllegalTransition(f"every commit of {full} ({commit[:12]}) is already in {authoritative_branch}: nothing "
                                "lies between the merge-base and the ref", reason="ref_already_contained", ref=full,
                                commit=commit)
    return {"name": full, "commit": commit, "merge_base": bases[0], "merge_bases": len(bases),
            "authoritative_branch": authoritative_branch, "authoritative_commit": authoritative_commit,
            "uncommitted": git.uncommitted_on(full, cwd=repo_root)}


def pack_view(repo_root: Path, ref_pin: dict[str, Any]) -> dict[str, Any]:
    """What a ref review's pack shows of its pin: the pin, and the diff from the merge-base to the pinned commit, whole
    up to ``REF_DIFF_MAX_BYTES``, otherwise its stat and changed paths. A pure function of two pinned commits, so a
    regenerated pack is the same."""
    base, commit = ref_pin["merge_base"], ref_pin["commit"]
    diff = git.object_git(*DIFF_ARGS, base, commit, cwd=repo_root).stdout
    view = {**ref_pin, "diff_bytes": len(diff), "diff_bound": REF_DIFF_MAX_BYTES,
            "read_rest": f"git diff {base} {commit} -- <path>"}
    if len(diff) <= REF_DIFF_MAX_BYTES:
        return {**view, "diff": diff.decode("utf-8", "replace")}
    stat = git.object_git(*DIFF_ARGS, "--stat", base, commit, cwd=repo_root).stdout.decode("utf-8", "replace")
    names = git.object_git(*DIFF_ARGS, "--name-only", base, commit, cwd=repo_root).stdout.decode("utf-8", "replace")
    return {**view, "diff": None, "stat": stat, "paths": names.splitlines()}
