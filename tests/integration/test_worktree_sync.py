"""Authoritative-worktree synchronization primitives (ADR-0004; review 2026-09-26 B2, M6).

Each test builds H (checked out on ``main``) and a candidate M, moves ``main`` to M
with the same compare-and-swap the engine uses, and exercises the sync step that
follows a publish. The index and the working copy are checked separately, and
file contents are written with LF so results are identical on Windows and POSIX.
"""

from __future__ import annotations

import itertools
import os
from pathlib import Path

import pytest
from conftest import IS_WINDOWS, git, make_git_repo

from aew.errors import IntegrityError
from aew.workspace import integration as I

POSIX_ONLY = pytest.mark.skipif(IS_WINDOWS, reason="needs POSIX filemode/symlink semantics")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build(tmp_path: Path, base_files: dict[str, str], change) -> tuple[Path, str, str]:
    """Return (repo, H, M): ``main`` is checked out at H; ``change(repo)`` produced M on a side branch."""
    repo = make_git_repo(tmp_path / "repo", base_files)
    h = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", "-b", "candidate", cwd=repo)
    change(repo)
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "candidate", cwd=repo)
    m = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    return repo, h, m


def publish(repo: Path, h: str, m: str) -> list[str]:
    paths = I.changed_between(repo, h, m)
    I.precheck_sync(repo, h, paths)
    I.cas_publish(repo, "refs/heads/main", m, h, "test publish")
    return paths


def assert_synced(repo: Path, m: str) -> None:
    assert git("status", "--porcelain", cwd=repo) == ""
    assert git("rev-parse", "HEAD", cwd=repo) == m


def edit_core(repo: Path) -> None:
    write(repo / "calc/core.py", "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n")


BASE = {"calc/core.py": "def add(a, b):\n    return a + b\n", "README.md": "# calc\n"}


def test_staged_independent_edit_is_never_overwritten(tmp_path):
    """B2 (LF-exact): the index holds someone else's staged content; the working copy happens to equal M."""
    repo, h, m = build(tmp_path, BASE, edit_core)
    paths = publish(repo, h, m)
    staged = "def add(a, b):\n    return a + b\n# independent staged work\n"
    write(repo / "calc/core.py", staged)
    git("add", "calc/core.py", cwd=repo)
    write(repo / "calc/core.py", git("show", f"{m}:calc/core.py", cwd=repo) + "\n")
    with pytest.raises(IntegrityError) as exc:
        I.sync_worktree(repo, h, m, paths)
    assert "calc/core.py" in exc.value.details["paths"]
    assert git("show", ":calc/core.py", cwd=repo) == staged.strip()


def test_precheck_rejects_a_staged_edit_hidden_behind_a_clean_working_copy(tmp_path):
    repo, h, m = build(tmp_path, BASE, edit_core)
    write(repo / "calc/core.py", "# staged elsewhere\n")
    git("add", "calc/core.py", cwd=repo)
    write(repo / "calc/core.py", BASE["calc/core.py"])  # working copy looks like H again
    with pytest.raises(IntegrityError):
        I.precheck_sync(repo, h, I.changed_between(repo, h, m))


def test_untracked_file_on_an_added_path_blocks_publication(tmp_path):
    repo, h, m = build(tmp_path, BASE, lambda r: write(r / "calc/new.py", "NEW = 1\n"))
    write(repo / "calc/new.py", "mine = True\n")
    with pytest.raises(IntegrityError):
        I.precheck_sync(repo, h, I.changed_between(repo, h, m))


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
def test_content_hiding_index_flags_are_refused(tmp_path, flag):
    repo, h, m = build(tmp_path, BASE, edit_core)
    git("update-index", flag, "calc/core.py", cwd=repo)
    paths = I.changed_between(repo, h, m)
    with pytest.raises(IntegrityError) as exc:
        I.precheck_sync(repo, h, paths)
    assert "index flag" in exc.value.details["paths"]["calc/core.py"]
    I.cas_publish(repo, "refs/heads/main", m, h, "test publish")
    with pytest.raises(IntegrityError):
        I.sync_worktree(repo, h, m, paths)
    assert (repo / "calc/core.py").read_text(encoding="utf-8") == BASE["calc/core.py"]


def test_delete_and_add_sync(tmp_path):
    def change(r: Path) -> None:
        (r / "README.md").unlink()
        write(r / "docs/guide.md", "# guide\n")

    repo, h, m = build(tmp_path, BASE, change)
    paths = publish(repo, h, m)
    I.sync_worktree(repo, h, m, paths)
    assert not (repo / "README.md").exists()
    assert_synced(repo, m)


def test_file_to_directory_transition_syncs(tmp_path):
    def change(r: Path) -> None:
        (r / "README.md").unlink()
        write(r / "README.md/index.md", "# moved\n")

    repo, h, m = build(tmp_path, BASE, change)
    paths = publish(repo, h, m)
    I.sync_worktree(repo, h, m, paths)
    assert (repo / "README.md/index.md").is_file()
    assert_synced(repo, m)


# Modified, deleted and added paths; each may be in any {H, M} state in the index and the working copy.
MIXED = {"calc/core.py": BASE["calc/core.py"], "README.md": "# calc\n", "keep.txt": "keep\n"}


def _mixed_change(r: Path) -> None:
    edit_core(r)
    (r / "README.md").unlink()
    write(r / "NEW.md", "new\n")


def _set(repo: Path, rev: str, path: str, *, index: bool, worktree: bool) -> None:
    exists = bool(git("ls-tree", rev, "--", path, cwd=repo))
    if index:
        if exists:
            git("reset", "-q", rev, "--", path, cwd=repo)
        else:
            git("rm", "-q", "--cached", "--ignore-unmatch", "--", path, cwd=repo)
    if worktree:
        target = repo / path
        if exists:
            write(target, git("show", f"{rev}:{path}", cwd=repo) + "\n")
        else:
            target.unlink(missing_ok=True)


@pytest.mark.parametrize("index_state,worktree_state", list(itertools.product("HM", "HM")))
def test_resync_converges_from_every_intermediate_state(tmp_path, index_state, worktree_state):
    """A crash can stop a sync anywhere; re-running it converges from any mix of H and M entries."""
    repo, h, m = build(tmp_path, MIXED, _mixed_change)
    paths = publish(repo, h, m)
    for i, path in enumerate(sorted(paths)):
        # Vary the mix per path so each run also covers heterogeneous states.
        want_index = index_state if i % 2 == 0 else ("M" if index_state == "H" else "H")
        _set(repo, m if want_index == "M" else h, path, index=True, worktree=False)
        _set(repo, m if worktree_state == "M" else h, path, index=False, worktree=True)
    I.sync_worktree(repo, h, m, paths)
    I.sync_worktree(repo, h, m, paths)  # idempotent
    assert_synced(repo, m)
    assert (repo / "keep.txt").read_text(encoding="utf-8") == "keep\n"


@POSIX_ONLY
def test_executable_bit_only_change_materializes(tmp_path):
    def change(r: Path) -> None:
        (r / "run.sh").chmod(0o755)

    repo = tmp_path / "x"
    repo, h, m = build(repo, {"run.sh": "#!/bin/sh\necho ok\n"}, change)
    git("config", "core.filemode", "true", cwd=repo)
    paths = publish(repo, h, m)
    assert paths == ["run.sh"]
    I.sync_worktree(repo, h, m, paths)
    assert (repo / "run.sh").stat().st_mode & 0o111
    assert_synced(repo, m)


@POSIX_ONLY
@pytest.mark.parametrize("direction", ["file_to_symlink", "symlink_to_file"])
def test_file_symlink_transitions_sync(tmp_path, direction):
    base = dict(BASE)
    if direction == "symlink_to_file":
        base = {"README.md": "# calc\n"}

    repo = make_git_repo(tmp_path / "repo", base)
    if direction == "symlink_to_file":
        os.symlink("README.md", repo / "link")
        git("add", "link", cwd=repo)
        git("commit", "-q", "-m", "link", cwd=repo)
    h = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", "-b", "candidate", cwd=repo)
    if direction == "file_to_symlink":
        (repo / "calc/core.py").unlink()
        os.symlink("../README.md", repo / "calc/core.py")
    else:
        (repo / "link").unlink()
        write(repo / "link", "now a file\n")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "candidate", cwd=repo)
    m = git("rev-parse", "HEAD", cwd=repo)
    git("checkout", "-q", "main", cwd=repo)
    paths = publish(repo, h, m)
    I.sync_worktree(repo, h, m, paths)
    target = repo / ("calc/core.py" if direction == "file_to_symlink" else "link")
    assert target.is_symlink() == (direction == "file_to_symlink")
    assert_synced(repo, m)


def test_a_reconcile_accepts_paths_any_later_commit_settled_not_only_the_head(tmp_path):
    """Register E34 (note 1): after a publish, more than one commit may land on the ref before the interrupted sync is
    reconciled. A path whose index and working copy hold the entry of a commit between the candidate and the head
    (not the head's own) was settled by that commit: reported, never rewritten, and never mistaken for local work."""
    repo, h, m = build(tmp_path, BASE, edit_core)
    paths = publish(repo, h, m)  # published, and the sync was interrupted before it started

    def commit_on_main(parent: str, text: str) -> str:
        source = tmp_path / "later.py"
        write(source, text)
        blob = git("hash-object", "-w", str(source), cwd=repo)
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},calc/core.py", cwd=repo)
        tree = git("write-tree", cwd=repo)
        git("reset", "-q", cwd=repo)  # leave the authoritative index as it was
        return git("commit-tree", tree, "-p", parent, "-m", "later", cwd=repo)

    x1 = commit_on_main(m, "def add(a, b):\n    return a + b  # first later commit\n")
    x2 = commit_on_main(x1, "def add(a, b):\n    return a + b  # second later commit\n")
    git("update-ref", "refs/heads/main", x2, m, cwd=repo)
    git("checkout", x1, "--", "calc/core.py", cwd=repo)  # the checkout holds the first later commit's entry
    out = I.sync_worktree(repo, h, m, paths, head=x2)
    assert out["settled_by_later_commit"]["paths"] == ["calc/core.py"]
    assert (repo / "calc/core.py").read_text(encoding="utf-8").endswith("# first later commit\n")
