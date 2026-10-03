"""Evaluated-snapshot identity (WC §9.9; KC §11; ADR-0002).

An evaluated snapshot identifies the engineering inputs actually evaluated,
including relevant uncommitted changes:

    base_revision               HEAD commit of the workspace (may be None in an empty repo)
    workspace_id                attributable workspace identity
    relevant_inputs_fingerprint git tree id of the working state, synthesized in a
                                temporary index: tracked + untracked-not-ignored files,
                                plus policy-declared ignored inputs, minus the AEW
                                knowledge root and policy exclusions
    artifact_digests            evaluated build artifact digests (optional)

Because ``.aew/`` is removed from the synthesized tree, writing an AEW report or
control file never changes the fingerprint of the evidence it records. Any change
to a relevant source/config/generated input does.

Known limits (documented, not hidden): dirty state *inside* submodules is not
captured (gitlinks record the submodule commit); Git LFS files contribute their
pointer; content that differs only by line endings normalized by git's filters
hashes identically (it would also commit identically).

Index flags (review 2026-09-26 M3; ADR-0002 amendment). The temporary index
starts as a copy of the real one (for its stat cache), so flags that make Git
*skip reading* the working copy are neutralized there — never in the user's
real index: assume-unchanged bits are cleared, and core.ignoreStat,
core.fsmonitor and core.untrackedCache are forced off. Skip-worktree entries
(sparse checkout) are refused: their content is not in the workspace, so no
honest snapshot of it exists.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aew.errors import GitError, IntegrityError
from aew.workspace import git

AEW_ROOT_REL = ".aew"
NUL = "\x00"
# Windows device names: a file with one of these names (any extension, any case) cannot be read
# through the ordinary path, so ``git add`` fails on it ("short read"). Usually made by a bash
# ``> nul`` redirect on Windows.
WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))])
# Settings that let Git trust cached/filesystem-monitor state instead of reading files: forced off
# for snapshot synthesis (GIT_CONFIG_COUNT needs git >= 2.31, the supported floor).
READ_ALL_CONTENT = {
    "GIT_CONFIG_COUNT": "3",
    "GIT_CONFIG_KEY_0": "core.ignoreStat", "GIT_CONFIG_VALUE_0": "false",
    "GIT_CONFIG_KEY_1": "core.fsmonitor", "GIT_CONFIG_VALUE_1": "false",
    "GIT_CONFIG_KEY_2": "core.untrackedCache", "GIT_CONFIG_VALUE_2": "false",
}


@contextmanager
def _working_index(workspace: Path, *, skip_aew: bool = False) -> Iterator[dict[str, str]]:
    """A throwaway index holding the complete working state (tracked + untracked-not-ignored). With ``skip_aew``,
    ``.aew/``'s working files are not read at all (the caller removes ``.aew/`` from the tree anyway): in the
    authoritative checkout it can hold thousands of uncommitted records (ADR-0011 investigation §8.1)."""
    real_index = Path(git.out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=workspace))
    tmpdir = Path(tempfile.mkdtemp(prefix="aew-idx-"))
    try:
        tmp_index = tmpdir / "index"
        if real_index.exists():
            shutil.copy2(real_index, tmp_index)  # reuse stat cache: fast on large trees
        env = {"GIT_INDEX_FILE": str(tmp_index), **READ_ALL_CONTENT}
        _neutralize_index_flags(workspace, env)
        try:
            git.git("add", "-A", "--", ".", *([f":(exclude){AEW_ROOT_REL}"] if skip_aew else []), cwd=workspace,
                    env=env)
        except GitError:
            _refuse_reserved_names(workspace, env)
            raise
        yield env
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def reserved_device_names(paths: list[str]) -> list[str]:
    """The paths whose last component is a Windows device name (``nul``, ``con.txt``, ``LPT1``, ...)."""
    def stem(path: str) -> str:
        return path.rsplit("/", 1)[-1].split(".", 1)[0].rstrip(" ").upper()
    return [p for p in paths if stem(p) in WINDOWS_RESERVED_NAMES]


def _refuse_reserved_names(workspace: Path, env: dict[str, str]) -> None:
    """After ``git add`` failed: if untracked files with device names explain it, refuse naming them."""
    proc = git.git("ls-files", "--others", "--exclude-standard", "-z", cwd=workspace, env=env, check=False)
    if proc.returncode != 0:
        return
    found = reserved_device_names([p for p in proc.stdout.decode("utf-8", "replace").split(NUL) if p])
    if found:
        raise IntegrityError(
            f"the workspace contains a file named after a Windows device ({', '.join(found[:5])}), which git "
            "cannot read, so no snapshot can be taken. It is usually left by a `> nul` redirect in bash on "
            "Windows; delete it and retry", workspace=str(workspace), paths=found[:20], count=len(found))


def _neutralize_index_flags(workspace: Path, env: dict[str, str]) -> None:
    """In the temporary index only: clear assume-unchanged; refuse skip-worktree (sparse) entries."""
    assumed, sparse = [], []
    for rec in git.out("ls-files", "-v", "-z", cwd=workspace, env=env).split(NUL):
        if len(rec) < 3:
            continue
        tag, path = rec[0], rec[2:]
        if tag.upper() == "S":
            sparse.append(path)
        elif tag.islower():
            assumed.append(path)
    if sparse:
        raise IntegrityError(
            "the workspace has skip-worktree (sparse checkout) entries; their content is not in the workspace, "
            "so an evaluated snapshot cannot include it. Use a full checkout for AEW workspaces",
            workspace=str(workspace), paths=sparse[:20], count=len(sparse))
    if assumed:
        git.git("update-index", "--no-assume-unchanged", "-z", "--stdin", cwd=workspace, env=env,
                input=(NUL.join(assumed) + NUL).encode("utf-8"))


def relevant_inputs_fingerprint(
    workspace: Path,
    *,
    exclude: list[str] | None = None,
    include_ignored: list[str] | None = None,
) -> str:
    workspace = workspace.resolve()
    with _working_index(workspace, skip_aew=True) as env:
        for path in [AEW_ROOT_REL, *(exclude or [])]:
            git.git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", path, cwd=workspace, env=env)
        for path in include_ignored or []:
            if (workspace / path).exists():
                git.git("add", "-f", "--", path, cwd=workspace, env=env)
        tree = git.out("write-tree", cwd=workspace, env=env)
    return f"git-tree:{tree}"


def working_tree_id(workspace: Path) -> str:
    """Tree id of everything Git would keep in a workspace, read from content.

    Tracked plus untracked-not-ignored files — nothing excluded, ``.aew/`` included — built in the
    same flag-neutralized temporary index as the fingerprint, so an assume-unchanged edit cannot
    hide (re-review B1). Compared with ``HEAD^{tree}`` it answers "does this workspace hold anything
    beyond its HEAD commit?". Raises :class:`IntegrityError` for sparse (skip-worktree) entries,
    whose content is absent and so cannot be compared; callers must treat that as "unknown".
    """
    workspace = workspace.resolve()
    with _working_index(workspace) as env:
        return git.out("write-tree", cwd=workspace, env=env)


def index_tree_id(workspace: Path) -> str:
    """Tree id of the workspace's index exactly as staged, written from a copy (the real index is untouched).

    The complement of :func:`working_tree_id`, which reads working-file content and therefore cannot
    see a change that exists only in the index (staged, then the working file restored) — foundation
    review. Raises :class:`GitError` for unmerged entries; callers treat that as "unknown".
    """
    workspace = workspace.resolve()
    real_index = Path(git.out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=workspace))
    tmpdir = Path(tempfile.mkdtemp(prefix="aew-idx-"))
    try:
        tmp_index = tmpdir / "index"
        if real_index.exists():
            shutil.copy2(real_index, tmp_index)
        return git.out("write-tree", cwd=workspace, env={"GIT_INDEX_FILE": str(tmp_index)})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def head_tree_id(workspace: Path) -> str:
    head = git.rev_parse("HEAD", cwd=workspace)
    return (git.out("rev-parse", f"{head}^{{tree}}", cwd=workspace) if head
            else git.out("hash-object", "-t", "tree", "--stdin", cwd=workspace))


def _changed(workspace: Path, a: str, b: str) -> set[str]:
    raw = git.out("diff", "--name-only", "--no-renames", "-z", a, b, cwd=workspace)
    return {p for p in raw.split(NUL) if p}


def index_only_paths(workspace: Path) -> list[str]:
    """Paths whose staged index entry matches neither HEAD nor the working copy.

    That staged content exists nowhere else: ``git add`` of the working state would overwrite it and
    removing the worktree would drop it.
    """
    workspace = workspace.resolve()
    head, index, work = head_tree_id(workspace), index_tree_id(workspace), working_tree_id(workspace)
    return sorted(_changed(workspace, head, index) & _changed(workspace, index, work))


def evaluated_snapshot(
    workspace: Path,
    workspace_id: str,
    *,
    exclude: list[str] | None = None,
    include_ignored: list[str] | None = None,
    artifact_digests: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "base_revision": git.rev_parse("HEAD", cwd=workspace),
        "workspace_id": workspace_id,
        "relevant_inputs_fingerprint": relevant_inputs_fingerprint(
            workspace, exclude=exclude, include_ignored=include_ignored),
        "artifact_digests": list(artifact_digests or []),
    }


def changed_paths(workspace: Path, base: str) -> list[str]:
    """Paths differing between ``base`` and the working state, including untracked files.

    Deliberately *includes* the AEW root so guardrails can reject a Ticket that touches it.
    """
    workspace = workspace.resolve()
    with _working_index(workspace) as env:
        raw = git.out("diff", "--cached", "--name-only", "--no-renames", "-z", base, cwd=workspace, env=env)
    return [p for p in raw.split(NUL) if p]


def working_diff(workspace: Path, base: str) -> str:
    """Unified diff of base..working state (incl. untracked files), excluding the AEW root."""
    workspace = workspace.resolve()
    with _working_index(workspace) as env:
        git.git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", AEW_ROOT_REL, cwd=workspace, env=env)
        return git.git("diff", "--cached", "--no-color", "--no-renames", base, cwd=workspace,
                       env=env).stdout.decode("utf-8", "replace")
