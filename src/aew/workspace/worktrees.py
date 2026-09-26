"""Isolated, attributable mutation workspaces (WC §8.1; KC §9.5).

Each mutating Ticket gets its own git worktree on branch ``aew/<ticket>-<n>``,
even in serial mode, so an accepted-but-unintegrated result is a real
integration candidate and never leaks into another Ticket's source snapshot.
A private marker in the worktree's own git dir tells ``aew`` (run from inside
the workspace) where the authoritative project is; the worktree's copy of
``.aew/`` is never treated as an authority.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from aew.engine.base import WORKSPACE_MARKER
from aew.errors import AEWError, GitError
from aew.snapshot import fingerprint
from aew.util import dump_yaml, utc_now
from aew.workspace import git


def branch_name(work_id: str, attempt: int) -> str:
    return f"aew/{work_id}-{attempt}"


def allocate(
    *,
    repo_root: Path,
    aew_root: Path,
    workspaces_root: Path,
    work_id: str,
    attempt: int,
    base_commit: str,
    referenced_paths: set[str],
) -> dict[str, Any]:
    workspace_id = f"ws-{work_id}-{attempt}"
    path = (workspaces_root / f"{work_id}-{attempt}").resolve()
    branch = branch_name(work_id, attempt)
    _clear_orphan(repo_root, path, branch, referenced_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    git.git("worktree", "add", "-q", "-b", branch, str(path), base_commit, cwd=repo_root)
    marker = git.git_dir(path) / WORKSPACE_MARKER
    marker.write_text(dump_yaml({
        "authoritative_repo_root": str(repo_root),
        "authoritative_aew_root": str(aew_root),
        "work_unit": work_id,
        "workspace_id": workspace_id,
    }), encoding="utf-8")
    return {
        "id": workspace_id,
        "path": str(path),
        "branch": branch,
        "base_commit": base_commit,
        "allocated_at": utc_now(),
        "status": "active",
    }


def allocate_detached(
    *,
    repo_root: Path,
    aew_root: Path,
    workspaces_root: Path,
    work_id: str,
    name: str,
    workspace_id: str,
    commit: str,
    referenced_paths: set[str],
) -> dict[str, Any]:
    """A detached worktree at ``commit`` (used for integration candidates)."""
    path = (workspaces_root / name).resolve()
    if str(path) in referenced_paths:
        raise GitError(f"workspace path {path} is referenced by committed control state")
    if path.exists():
        remove(repo_root, str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    git.git("worktree", "add", "-q", "--detach", str(path), commit, cwd=repo_root)
    (git.git_dir(path) / WORKSPACE_MARKER).write_text(dump_yaml({
        "authoritative_repo_root": str(repo_root),
        "authoritative_aew_root": str(aew_root),
        "work_unit": work_id,
        "workspace_id": workspace_id,
    }), encoding="utf-8")
    return {"path": str(path), "workspace_id": workspace_id}


def _clear_orphan(repo_root: Path, path: Path, branch: str, referenced_paths: set[str]) -> None:
    """Remove a slot left by an assignment that crashed before its commit (never a referenced one)."""
    if str(path) in referenced_paths:
        raise GitError(f"workspace path {path} is referenced by committed control state")
    if path.exists():
        git.git("worktree", "remove", "--force", str(path), cwd=repo_root, check=False)
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        git.git("worktree", "prune", cwd=repo_root, check=False)
    if git.rev_parse(f"refs/heads/{branch}", cwd=repo_root):
        git.git("branch", "-D", branch, cwd=repo_root, check=False)


def remove(repo_root: Path, path: str) -> None:
    git.git("worktree", "remove", "--force", path, cwd=repo_root, check=False)
    if Path(path).exists():
        shutil.rmtree(path, ignore_errors=True)
    git.git("worktree", "prune", cwd=repo_root, check=False)


def inspect(path: str, base_commit: str | None) -> dict[str, Any]:
    """What a workspace holds, judged from content.

    ``dirty`` is True when the working state (tracked + untracked-not-ignored, read from content with
    index flags neutralized) differs from HEAD's tree, False when it is exactly HEAD, and None when that
    cannot be established (e.g. sparse entries) — callers deciding on removal must treat None as dirty.
    ``git status`` is deliberately not used: it honours assume-unchanged/skip-worktree (re-review B1).
    """
    ws = Path(path)
    if not ws.exists():
        return {"exists": False}
    head = git.rev_parse("HEAD", cwd=ws)
    out: dict[str, Any] = {"exists": True, "head": head, "head_is_base": head == base_commit}
    try:
        head_tree = (git.out("rev-parse", f"{head}^{{tree}}", cwd=ws) if head
                     else git.out("hash-object", "-t", "tree", "--stdin", cwd=ws))
        out["dirty"] = fingerprint.working_tree_id(ws) != head_tree
    except AEWError as exc:
        out["dirty"] = None
        out["dirty_unknown"] = exc.message
    return out
