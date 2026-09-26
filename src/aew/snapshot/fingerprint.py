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
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from aew.workspace import git

AEW_ROOT_REL = ".aew"
NUL = "\x00"


@contextmanager
def _working_index(workspace: Path) -> Iterator[dict[str, str]]:
    """A throwaway index holding the complete working state (tracked + untracked-not-ignored)."""
    real_index = Path(git.out("rev-parse", "--path-format=absolute", "--git-path", "index", cwd=workspace))
    tmpdir = Path(tempfile.mkdtemp(prefix="aew-idx-"))
    try:
        tmp_index = tmpdir / "index"
        if real_index.exists():
            shutil.copy2(real_index, tmp_index)  # reuse stat cache: fast on large trees
        env = {"GIT_INDEX_FILE": str(tmp_index)}
        git.git("add", "-A", "--", ".", cwd=workspace, env=env)
        yield env
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def relevant_inputs_fingerprint(
    workspace: Path,
    *,
    exclude: list[str] | None = None,
    include_ignored: list[str] | None = None,
) -> str:
    workspace = workspace.resolve()
    with _working_index(workspace) as env:
        for path in [AEW_ROOT_REL, *(exclude or [])]:
            git.git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", path, cwd=workspace, env=env)
        for path in include_ignored or []:
            if (workspace / path).exists():
                git.git("add", "-f", "--", path, cwd=workspace, env=env)
        tree = git.out("write-tree", cwd=workspace, env=env)
    return f"git-tree:{tree}"


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
