"""Thin, explicit wrapper over the git CLI (the guaranteed provider; git >= 2.31)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from aew.errors import GitError

AEW_IDENTITY = {"name": "AEW Engine", "email": "aew-engine@invalid"}


def git(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
    input: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    full_env = dict(os.environ)
    full_env["GIT_TERMINAL_PROMPT"] = "0"
    full_env["LC_ALL"] = "C"
    if env:
        full_env.update(env)
    proc = subprocess.run(["git", *args], cwd=cwd, env=full_env, capture_output=True, input=input)
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode})",
            cwd=str(cwd),
            stderr=proc.stderr.decode("utf-8", "replace").strip(),
        )
    return proc


def out(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    return git(*args, cwd=cwd, env=env).stdout.decode("utf-8", "replace").strip()


def ok(*args: str, cwd: Path) -> bool:
    return git(*args, cwd=cwd, check=False).returncode == 0


def rev_parse(ref: str, *, cwd: Path) -> str | None:
    proc = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", cwd=cwd, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip() or None


def is_ancestor(ancestor: str, descendant: str, *, cwd: Path) -> bool:
    proc = git("merge-base", "--is-ancestor", ancestor, descendant, cwd=cwd, check=False)
    if proc.returncode not in (0, 1):
        raise GitError("merge-base --is-ancestor failed", stderr=proc.stderr.decode().strip())
    return proc.returncode == 0


def toplevel(cwd: Path) -> Path | None:
    proc = git("rev-parse", "--show-toplevel", cwd=cwd, check=False)
    return Path(proc.stdout.decode().strip()) if proc.returncode == 0 else None


def git_dir(cwd: Path) -> Path:
    return Path(out("rev-parse", "--absolute-git-dir", cwd=cwd))


def common_dir(cwd: Path) -> Path:
    raw = out("rev-parse", "--git-common-dir", cwd=cwd)
    path = Path(raw)
    return path if path.is_absolute() else (cwd / path).resolve()


def is_linked_worktree(cwd: Path) -> bool:
    return git_dir(cwd).resolve() != common_dir(cwd).resolve()


def current_branch(cwd: Path) -> str | None:
    proc = git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=cwd, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode().strip() or None


def identity_env(cwd: Path) -> dict[str, str]:
    """Commit identity for AEW-created commits: the repo's configured identity, else a fixed one."""
    env: dict[str, str] = {}
    if not ok("config", "user.name", cwd=cwd):
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = AEW_IDENTITY["name"]
    if not ok("config", "user.email", cwd=cwd):
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = AEW_IDENTITY["email"]
    return env
