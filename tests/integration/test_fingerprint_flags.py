"""Evaluated-snapshot identity vs content-hiding index flags (ADR-0002 amendment; review 2026-09-26 M3).

The fingerprint must reflect the bytes actually in the workspace even when the
real index tells Git not to look, and must never modify the user's real index.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git, make_git_repo

from aew.errors import IntegrityError
from aew.snapshot.fingerprint import changed_paths, relevant_inputs_fingerprint


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path) -> Path:
    return make_git_repo(tmp_path / "repo", {"calc/core.py": "def f():\n    return 1\n", "README.md": "# r\n"})


def flags(repo: Path) -> str:
    return git("ls-files", "-v", cwd=repo)


def test_assume_unchanged_does_not_hide_a_changed_input(repo):
    base = relevant_inputs_fingerprint(repo)
    git("update-index", "--assume-unchanged", "calc/core.py", cwd=repo)
    real_index_flags = flags(repo)
    write(repo / "calc/core.py", "def f():\n    return 999\n")
    changed = relevant_inputs_fingerprint(repo)
    assert changed != base
    assert changed_paths(repo, git("rev-parse", "HEAD", cwd=repo)) == ["calc/core.py"]
    assert flags(repo) == real_index_flags  # the user's real index is untouched
    write(repo / "calc/core.py", "def f():\n    return 1\n")
    assert relevant_inputs_fingerprint(repo) == base


def test_ignore_stat_config_does_not_hide_a_changed_input(repo):
    base = relevant_inputs_fingerprint(repo)
    git("config", "core.ignoreStat", "true", cwd=repo)
    git("update-index", "--really-refresh", cwd=repo)
    write(repo / "calc/core.py", "def f():\n    return 2\n")
    assert relevant_inputs_fingerprint(repo) != base


def test_unflagged_fingerprint_is_unchanged_by_the_flag_handling(repo):
    """No regression: a plain workspace hashes to the tree of its content, as before."""
    assert relevant_inputs_fingerprint(repo) == "git-tree:" + git("rev-parse", "HEAD^{tree}", cwd=repo)


def test_skip_worktree_entries_are_refused(repo):
    git("update-index", "--skip-worktree", "README.md", cwd=repo)
    with pytest.raises(IntegrityError) as exc:
        relevant_inputs_fingerprint(repo)
    assert exc.value.details["paths"] == ["README.md"]
    assert "S README.md" in flags(repo)  # still flagged in the real index
