"""Git mechanics for controlled integration (WC §8.1, §13; ADR-0004, D-op-2).

validate, then publish:

1. commit the gated Ticket workspace (its tree must equal the gated fingerprint);
2. build candidate M from authoritative commit H in a detached integration worktree;
3. (post-integration verification runs against M — engine/roles, not here);
4. publish with an atomic compare-and-swap on the authoritative ref
   (``git update-ref <ref> M H``): it succeeds only if the ref is still H;
5. sync the authoritative worktree: force exactly the paths changed between H
   and M to M's content. Other paths — including dirty ``.aew/`` control files —
   are untouched. Sync is idempotent and refuses paths that match neither H nor M.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.errors import GitError, IntegrityError, StaleCandidate
from aew.workspace import git

AEW_EXCLUDE = ":(exclude).aew"


def commit_workspace(workspace: Path, message: str) -> str:
    """Commit all non-AEW working changes in a Ticket workspace; return HEAD."""
    status = git.out("status", "--porcelain", "--untracked-files=normal", "--", ".", AEW_EXCLUDE, cwd=workspace)
    if status:
        git.git("add", "-A", "--", ".", AEW_EXCLUDE, cwd=workspace)
        git.git("commit", "-q", "--no-verify", "-m", message, cwd=workspace, env=git.identity_env(workspace))
    head = git.rev_parse("HEAD", cwd=workspace)
    assert head
    return head


def merge_candidate(repo_root: Path, int_path: Path, ticket_commit: str, message: str) -> dict[str, Any]:
    """Merge the Ticket commit into the detached integration worktree (at H). Returns M or a conflict."""
    proc = git.git("merge", "--no-ff", "--no-edit", "-m", message, ticket_commit, cwd=int_path, check=False,
                   env=git.identity_env(repo_root))
    if proc.returncode != 0:
        conflicts = git.out("diff", "--name-only", "--diff-filter=U", cwd=int_path)
        git.git("merge", "--abort", cwd=int_path, check=False)
        return {"conflict": True, "paths": [p for p in conflicts.splitlines() if p],
                "stderr": proc.stderr.decode("utf-8", "replace")[-2000:]}
    return {"conflict": False, "commit": git.rev_parse("HEAD", cwd=int_path)}


def changed_between(repo_root: Path, a: str, b: str) -> list[str]:
    raw = git.out("diff", "--name-only", "--no-renames", "-z", a, b, cwd=repo_root)
    return [p for p in raw.split("\x00") if p]


def _chunks(items: list[str], n: int = 200) -> list[list[str]]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def authoritative_worktree_applies(repo_root: Path, branch: str) -> bool:
    return git.current_branch(repo_root) == branch


def precheck_sync(repo_root: Path, base: str, paths: list[str]) -> None:
    """Before publishing: every path the integration changes must be clean (== H) in the authoritative worktree."""
    for chunk in _chunks(paths):
        wt = git.git("diff", "--quiet", base, "--", *chunk, cwd=repo_root, check=False).returncode
        idx = git.git("diff", "--cached", "--quiet", base, "--", *chunk, cwd=repo_root, check=False).returncode
        if wt != 0 or idx != 0:
            dirty = git.out("diff", "--name-only", base, "--", *chunk, cwd=repo_root)
            raise IntegrityError(
                "the authoritative worktree has local changes on paths this integration changes; "
                "commit/stash them or resolve before publishing",
                paths=[p for p in dirty.splitlines() if p][:50])


def cas_publish(repo_root: Path, ref: str, new: str, expected_old: str, message: str) -> None:
    proc = git.git("update-ref", "-m", message, ref, new, expected_old, cwd=repo_root, check=False)
    if proc.returncode != 0:
        current = git.rev_parse(ref, cwd=repo_root)
        raise StaleCandidate(
            "the authoritative ref moved since the candidate was built; rebuild and revalidate",
            ref=ref, expected=expected_old, current=current, stderr=proc.stderr.decode("utf-8", "replace").strip())


def _blob(repo_root: Path, commit: str, path: str) -> str | None:
    proc = git.git("rev-parse", "--verify", "--quiet", f"{commit}:{path}", cwd=repo_root, check=False)
    return proc.stdout.decode().strip() or None if proc.returncode == 0 else None


def _worktree_blob(repo_root: Path, path: str) -> str | None:
    target = repo_root / path
    if not target.exists():
        return None
    return git.out("hash-object", "--", path, cwd=repo_root)


def sync_worktree(repo_root: Path, base: str, new: str, paths: list[str], *, on_first=None) -> dict[str, Any]:
    """Force exactly ``paths`` to ``new``'s content in the authoritative worktree (idempotent)."""
    present, deleted = [], []
    for p in paths:
        want = _blob(repo_root, new, p)
        have = _worktree_blob(repo_root, p)
        if have == want:
            continue
        if have != _blob(repo_root, base, p):
            raise IntegrityError(f"{p} matches neither the pre-integration nor the integrated content; refusing "
                                 "to overwrite it", path=p)
        (present if want is not None else deleted).append(p)
    for i, chunk in enumerate(_chunks(present)):
        git.git("checkout", new, "--", *chunk, cwd=repo_root)
        if i == 0 and on_first:
            on_first()
    for p in deleted:
        git.git("rm", "-q", "--cached", "--ignore-unmatch", "--", p, cwd=repo_root)
        (repo_root / p).unlink(missing_ok=True)
    # Index entries for unchanged-content paths may still carry base: refresh them from `new`.
    for chunk in _chunks([p for p in paths if _blob(repo_root, new, p) is not None]):
        git.git("reset", "-q", new, "--", *chunk, cwd=repo_root)
    for chunk in _chunks(paths):
        if git.git("diff", "--quiet", new, "--", *chunk, cwd=repo_root, check=False).returncode != 0:
            raise GitError("authoritative worktree did not converge to the integrated commit", paths=chunk)
    return {"synced": len(present) + len(deleted), "paths": len(paths)}
