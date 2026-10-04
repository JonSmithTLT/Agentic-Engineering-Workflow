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
    _add(repo_root, path, "-b", branch, str(path), base_commit)
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
    _add(repo_root, path, "--detach", str(path), commit)
    (git.git_dir(path) / WORKSPACE_MARKER).write_text(dump_yaml({
        "authoritative_repo_root": str(repo_root),
        "authoritative_aew_root": str(aew_root),
        "work_unit": work_id,
        "workspace_id": workspace_id,
    }), encoding="utf-8")
    return {"path": str(path), "workspace_id": workspace_id}


# git's own paths below a worktree (``.git/worktrees/<name>/...``) and its files must fit the platform's limit; on
# Windows without long paths that is 260 characters, and a deep workspaces root fails inside git (M4 spike fact 4).
LONG_PATH_HINTS = ("too big", "filename too long", "path too long", "name too long")


def _add(repo_root: Path, path: Path, *args: str) -> None:
    """``git worktree add``, with a path-length failure reported as one: where, how long, and what to change."""
    try:
        git.git("worktree", "add", "-q", *args, cwd=repo_root)
    except GitError as exc:
        stderr = str(exc.details.get("stderr") or "").lower()
        if not any(hint in stderr for hint in LONG_PATH_HINTS):
            raise
        raise GitError(f"the workspace path {path} ({len(str(path))} characters) is too long for git here; set a "
                       "shorter `workspaces.root` in .aew/project.yaml and run `aew manifest adopt` (for example a "
                       "short directory beside the repository), or enable long paths (git config core.longpaths "
                       "true, and Windows long-path support)", path=str(path), length=len(str(path)),
                       stderr=exc.details.get("stderr")) from None


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

    ``dirty`` is True when either the working state (tracked + untracked-not-ignored, read from content
    with index flags neutralized) or the index as staged differs from HEAD's tree, False when both are
    exactly HEAD, and None when that cannot be established (sparse or unmerged entries) — callers
    deciding on removal must treat None as dirty. ``git status`` is deliberately not used: it honours
    assume-unchanged/skip-worktree (re-review B1). Both views are needed: working content cannot see a
    change that exists only in the index (foundation review).
    """
    ws = Path(path)
    if not ws.exists():
        return {"exists": False}
    head = git.rev_parse("HEAD", cwd=ws)
    out: dict[str, Any] = {"exists": True, "head": head, "head_is_base": head == base_commit}
    try:
        head_tree = fingerprint.head_tree_id(ws)
        out["staged"] = fingerprint.index_tree_id(ws) != head_tree
        out["dirty"] = out["staged"] or fingerprint.working_tree_id(ws) != head_tree
    except AEWError as exc:
        out["dirty"] = None
        out["dirty_unknown"] = exc.message
    return out
