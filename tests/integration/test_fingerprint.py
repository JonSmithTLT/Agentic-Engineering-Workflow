"""Evaluated-snapshot fingerprint semantics (WC §9.9; KC §11)."""

from __future__ import annotations

import os

import pytest

from conftest import git, make_git_repo

from aew.errors import IntegrityError
from aew.snapshot.fingerprint import changed_paths, relevant_inputs_fingerprint, reserved_device_names


def fixture(tmp_path):
    return make_git_repo(tmp_path / "r", {
        ".gitignore": "__pycache__/\n*.log\n.pytest_cache/\n",
        "calc/core.py": "def add(a, b):\n    return a + b\n",
        "config/settings.toml": "mode = 'a'\n",
    })


def test_clean_tree_is_head_tree(tmp_path):
    repo = fixture(tmp_path)
    assert relevant_inputs_fingerprint(repo) == "git-tree:" + git("rev-parse", "HEAD^{tree}", cwd=repo)


def test_uncommitted_tracked_edit_changes_and_revert_restores(tmp_path):
    repo = fixture(tmp_path)
    clean = relevant_inputs_fingerprint(repo)
    core = repo / "calc/core.py"
    original = core.read_text()
    core.write_text(original + "\ndef sub(a, b):\n    return a - b\n", newline="\n")
    dirty = relevant_inputs_fingerprint(repo)
    assert dirty != clean
    core.write_text(original, newline="\n")  # byte-identical revert (no CRLF translation)
    assert relevant_inputs_fingerprint(repo) == clean


def test_untracked_counts_ignored_does_not_unless_declared(tmp_path):
    repo = fixture(tmp_path)
    clean = relevant_inputs_fingerprint(repo)
    (repo / "calc/new_module.py").write_text("X = 1\n")
    with_untracked = relevant_inputs_fingerprint(repo)
    assert with_untracked != clean
    (repo / "build.log").write_text("noise\n")
    assert relevant_inputs_fingerprint(repo) == with_untracked
    assert relevant_inputs_fingerprint(repo, include_ignored=["build.log"]) != with_untracked


@pytest.mark.acceptance("AT-3")
def test_aew_files_never_change_the_fingerprint(tmp_path):
    repo = fixture(tmp_path)
    clean = relevant_inputs_fingerprint(repo)
    (repo / ".aew/evidence/T-0001").mkdir(parents=True)
    (repo / ".aew/evidence/T-0001/INV-0003-verification-1.md").write_text("report\n")
    (repo / ".aew/state").mkdir(parents=True)
    (repo / ".aew/state/control.yaml").write_text("revision: 9\n")
    assert relevant_inputs_fingerprint(repo) == clean
    # ...even when .aew is committed and then modified.
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "track aew", cwd=repo)
    (repo / ".aew/state/control.yaml").write_text("revision: 10\n")
    assert relevant_inputs_fingerprint(repo) == clean


def test_policy_exclusion(tmp_path):
    repo = fixture(tmp_path)
    clean = relevant_inputs_fingerprint(repo, exclude=["config"])
    (repo / "config/settings.toml").write_text("mode = 'b'\n")
    assert relevant_inputs_fingerprint(repo, exclude=["config"]) == clean
    assert relevant_inputs_fingerprint(repo) != relevant_inputs_fingerprint(repo, exclude=["config"])


def test_fingerprinting_does_not_touch_the_real_index(tmp_path):
    repo = fixture(tmp_path)
    (repo / "calc/new_module.py").write_text("X = 1\n")
    index = repo / ".git/index"
    before = index.read_bytes()
    status_before = git("status", "--porcelain", cwd=repo)
    relevant_inputs_fingerprint(repo)
    assert index.read_bytes() == before
    assert git("status", "--porcelain", cwd=repo) == status_before


def test_changed_paths_include_untracked_and_aew(tmp_path):
    repo = fixture(tmp_path)
    base = git("rev-parse", "HEAD", cwd=repo)
    (repo / "calc/core.py").write_text("changed\n")
    (repo / "calc/new_module.py").write_text("X = 1\n")
    (repo / ".aew").mkdir()
    (repo / ".aew/project.yaml").write_text("x: 1\n")
    assert sorted(changed_paths(repo, base)) == [".aew/project.yaml", "calc/core.py", "calc/new_module.py"]


def test_reserved_device_names_match_any_case_and_extension():
    assert reserved_device_names(["nul", "a/NUL.txt", "b/Con", "lpt9.log", "aux .md", "COM1"]) == [
        "nul", "a/NUL.txt", "b/Con", "lpt9.log", "aux .md", "COM1"]
    assert reserved_device_names(["null", "nul_x", "console.py", "com10", "lpt0", "a.nul", "nul/x.py"]) == []


def test_device_named_file_refused_by_name_on_windows_and_ordinary_elsewhere(tmp_path):
    """Future-work O1: a `nul` file (a bash `> nul` on Windows) made the fingerprint fail with git's raw error."""
    repo = fixture(tmp_path)
    nul = repo / "calc" / "nul"
    if os.name != "nt":
        nul.write_text("x\n")  # an ordinary name on POSIX
        assert relevant_inputs_fingerprint(repo) != "git-tree:" + git("rev-parse", "HEAD^{tree}", cwd=repo)
        return
    extended = "\\\\?\\" + str(nul)  # the only way to create or delete a file with a device name
    with open(extended, "w") as fh:
        fh.write("x\n")
    try:
        with pytest.raises(IntegrityError) as err:
            relevant_inputs_fingerprint(repo)
        assert err.value.details["paths"] == ["calc/nul"]
        assert "> nul" in str(err.value)
    finally:
        os.remove(extended)
