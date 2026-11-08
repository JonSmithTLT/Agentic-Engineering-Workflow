"""A test session never writes to the repository it runs in, or to the user's git configuration.

Most of these run a real inner pytest session (tests/helpers/git_isolation.py): the leak they plant happens in a process
with the isolation in place, and what counts is that session's exit code and the throwaway repository afterwards. No
test here touches this checkout's repository: the "enclosing" repository is always one made under ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import git_isolation
import pytest

from aew.workspace.git import AEW_IDENTITY

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "tests" / "helpers"
NO_WINDOW: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
needs_xdist = pytest.mark.skipif(importlib.util.find_spec("xdist") is None,
                                 reason="pytest-xdist not installed (extra: parallel)")
WORKERS = [pytest.param([], id="in-process"), pytest.param(["-n", "2"], id="xdist", marks=needs_xdist)]

# The shape of tests/conftest.py's wiring: `test_this_suite_is_wired_as_the_inner_sessions_are` holds the two together.
CONFTEST = f"""\
import os, sys
from pathlib import Path
sys.path.insert(0, {str(HELPERS)!r})
import git_isolation
git_isolation.isolate(Path(__file__).resolve().parents[1])
import worker_coverage
from worker_coverage import pytest_sessionfinish
if os.environ.get("COVERAGE_SAVE_MARK"):
    def save(session):
        if hasattr(session.config, "workerinput"):
            Path(os.environ["COVERAGE_SAVE_MARK"]).write_text("saved", encoding="utf-8")
    worker_coverage.save = save
def pytest_configure(config):
    git_isolation.configure(config)
"""
PRELUDE = """\
import os, subprocess
from pathlib import Path

ROOT = Path(os.environ["SESSION_ROOT"]) if "SESSION_ROOT" in os.environ else None

def git(*args, cwd=None, **env):
    return subprocess.run(["git", *args], cwd=cwd or ROOT, env={**os.environ, **env}, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()

def commit_as(email, *, date=None):
    tree = git("rev-parse", "HEAD^{tree}")
    who = dict(GIT_AUTHOR_NAME="x", GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME="x", GIT_COMMITTER_EMAIL=email)
    if date:
        who.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return git("commit-tree", tree, "-m", "c", **who)
"""
PYPROJECT = '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'


def plain_git(*args: str, cwd: Path, **env: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **env}, check=True, capture_output=True,
                          text=True, encoding="utf-8", **NO_WINDOW).stdout.strip()


def session(root: Path, test_body: str, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    """An inner pytest session rooted at ``root``, with two tests under xdist's eyes: the planted one, and one that
    passes. Its environment is this process's, without pytest's own, plus ``env``."""
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (root / "tests" / "test_planted.py").write_text(
        PRELUDE + "\ndef test_planted(tmp_path):\n" + "".join(f"    {line}\n" for line in test_body.splitlines()) +
        "\ndef test_other():\n    pass\n", encoding="utf-8")
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_", "COV_", "COVERAGE_"))}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args], cwd=root,
                          env={**clean, "SESSION_ROOT": str(root), **env}, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300, **NO_WINDOW)


def new_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    plain_git("init", "-q", "-b", "main", cwd=path)
    plain_git("-c", "user.name=Builder", "-c", "user.email=builder@example.com", "commit", "-q", "--allow-empty", "-m",
              "start", cwd=path)
    # What a session must not touch in this repository is judged against a run that also commits nothing here: its tests
    # and report are not in git's way.
    (path / ".git" / "info" / "exclude").write_text("*\n", encoding="utf-8")
    return path


LEAK = """\
repo = tmp_path / "throwaway"
repo.mkdir()
git("init", "-q", "-b", "main", cwd=repo)
git("config", "user.name", "AEW Test", cwd=repo)
git("config", "user.email", "aew-test@invalid", cwd=repo)
git("commit", "-q", "--allow-empty", "-m", "initial", cwd=repo)
assert (repo / ".git" / "config").read_text().count("AEW Test") == 1
"""


@pytest.mark.parametrize("workers", WORKERS)
def test_a_session_started_with_git_dir_set_writes_nothing_to_that_repository(tmp_path, workers):
    """The incident: a hook's `GIT_DIR` reached the tests, and their throwaway repositories' `git init`, `git config`
    and `git commit` went to the repository it named. Run in full, with `GIT_DIR` at a bare repository."""
    bare = tmp_path / "shared.git"
    plain_git("init", "-q", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    before = (bare / "config").read_bytes()
    proc = session(tmp_path / "proj", LEAK, *workers, GIT_DIR=str(bare), GIT_WORK_TREE=str(tmp_path),
                   GIT_INDEX_FILE=str(tmp_path / "index"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (bare / "config").read_bytes() == before
    assert plain_git("for-each-ref", cwd=bare, GIT_DIR=str(bare)) == ""


def test_a_tests_own_git_dir_for_its_own_child_still_works(tmp_path):
    body = (LEAK + 'assert git("rev-parse", "--git-dir", cwd=tmp_path, GIT_DIR=str(repo / ".git")).endswith(".git")\n'
            'assert git("log", "--format=%s", cwd=tmp_path, GIT_DIR=str(repo / ".git")) == "initial"\n')
    proc = session(tmp_path / "proj", body)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_variable_git_calls_repository_local_is_cleared():
    """git's own list, from the installed git: a new version's variable fails here rather than leaks. Its config-count
    pairs are matched by pattern."""
    listed = plain_git("rev-parse", "--local-env-vars", cwd=Path(tempfile.gettempdir())).split()
    assert listed and set(listed) <= git_isolation.REDIRECTING
    assert git_isolation._COUNTED_CONFIG.match("GIT_CONFIG_KEY_0") and git_isolation._COUNTED_CONFIG.match(
        "GIT_CONFIG_VALUE_12")


def test_a_redirecting_variable_is_not_set_in_this_very_session():
    leaked = {name for name in os.environ if name in git_isolation.REDIRECTING | git_isolation.IDENTITY}
    assert not leaked


def short_form(path: Path) -> Path:
    """The Windows 8.3 form of a path, the same path where a volume has none (or off Windows)."""
    if sys.platform != "win32":
        return path
    import ctypes

    buffer = ctypes.create_unicode_buffer(1024)
    got = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))  # type: ignore[attr-defined]
    return Path(buffer.value) if got else path


@pytest.mark.parametrize("ceiling_form", [Path, short_form], ids=["ceiling-long", "ceiling-short"])
@pytest.mark.parametrize("cwd_form", [Path, short_form], ids=["cwd-long", "cwd-short"])
def test_the_ceiling_stops_a_real_walk_up_in_every_path_form(tmp_path, ceiling_form, cwd_form):
    """A real walk: first that git finds the repository with no ceiling, so the second result means something. On
    Windows each of the ceiling and the cwd is tried as an 8.3 short name, where the volume makes them: a temp root
    like `JONSMI~1` must not make the ceiling match nothing."""
    outer = new_repo(tmp_path / "A Long Directory Name" / "Outer Repository Name")
    below = outer / "A Long Subdirectory" / "Deeper Still"
    below.mkdir(parents=True)
    cwd = cwd_form(below)
    assert Path(plain_git("rev-parse", "--show-toplevel", cwd=cwd, GIT_CEILING_DIRECTORIES="")).name == outer.name
    capped = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True,
                            env={**os.environ, "GIT_CEILING_DIRECTORIES": git_isolation.ceilings(ceiling_form(outer))},
                            **NO_WINDOW)
    assert capped.returncode != 0 and "not a git repository" in capped.stderr, capped.stdout + capped.stderr


def test_this_sessions_ceiling_stops_a_walk_up_into_this_checkout():
    """On the real paths of the session running this test. A copy of the tree with no repository has nothing to walk
    into, so it answers the same."""
    below = ROOT / "tests" / "helpers"
    got = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=below, capture_output=True, text=True,
                         **NO_WINDOW)
    assert got.returncode != 0 and "not a git repository" in got.stderr, got.stdout + got.stderr


def linked_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A repository and a linked worktree of it: the worktree's `git config` writes to the repository's shared file."""
    main = new_repo(tmp_path / "main")
    plain_git("worktree", "add", "-q", "-b", "wt", str(tmp_path / "wt"), cwd=main)
    return main, tmp_path / "wt"


@pytest.mark.parametrize("linked", [False, True], ids=["checkout", "linked-worktree"])
def test_a_git_config_below_the_checkout_never_reaches_its_repository(tmp_path, linked):
    """A cwd below a real checkout, with no repository of its own: the walk up would write to the enclosing, and for
    a linked worktree shared, configuration."""
    main, root = linked_worktree(tmp_path) if linked else (new_repo(tmp_path / "main"), tmp_path / "main")
    body = ('below = ROOT / "no_repo_here"\nbelow.mkdir()\n'
            'got = subprocess.run(["git", "config", "user.name", "AEW Test"], cwd=below, capture_output=True,\n'
            '                     text=True)\n'
            'assert got.returncode != 0, got.stdout\n')
    proc = session(root, body)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "AEW Test" not in (main / ".git" / "config").read_text(encoding="utf-8")


def test_the_global_configuration_is_this_sessions_and_gives_a_test_identity(tmp_path):
    """`--global` never reaches the user's file, and a commit with no identity of its own (a leak into a repository with
    none) is a test identity's, so the tripwire can see it."""
    configured = Path(os.environ["GIT_CONFIG_GLOBAL"])
    assert configured.is_file() and configured != Path.home() / ".gitconfig"
    repo = tmp_path / "repo"
    repo.mkdir()
    plain_git("init", "-q", cwd=repo)
    assert plain_git("config", "--global", "user.email", cwd=repo) == git_isolation.SESSION_EMAIL
    assert git_isolation.is_test_identity(git_isolation.SESSION_EMAIL)
    assert plain_git("var", "GIT_COMMITTER_IDENT", cwd=repo).split(">")[0].endswith(git_isolation.SESSION_EMAIL)


def test_a_session_outside_any_repository_has_no_tripwire_and_passes(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    proc = session(root, 'assert not (ROOT / ".git").exists()\n')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "git isolation" not in proc.stdout


# Each changes the enclosing repository as a leak would, and the session's tests all pass.
PLANTED = {
    "core.bare": ('git("config", "core.bare", "true")\n', "core.bare changed"),
    "core.worktree": ('git("config", "core.worktree", str(tmp_path))\n', "core.worktree changed"),
    "user.name": ('git("config", "user.name", "AEW Test")\n', "user.name changed"),
    "user.email": ('git("config", "user.email", "aew-test@invalid")\n', "user.email changed"),
    "new-branch": ('git("update-ref", "refs/heads/junk", commit_as("aew-test@invalid"))\n',
                   "refs/heads/junk is at"),
    "moved-branch": ('git("update-ref", "refs/heads/other", commit_as("t@example.invalid"))\n',
                     "refs/heads/other is at"),
    "new-tag": ('git("update-ref", "refs/tags/junk", commit_as("t@t"))\n', "refs/tags/junk is at"),
    "own-head-moved": ('git("update-ref", "HEAD", commit_as("builder@example.com"))\n', "this checkout's HEAD moved"),
    "own-head-switched": ('git("symbolic-ref", "HEAD", "refs/heads/other")\n', "this checkout's HEAD moved"),
    "temp-worktree": ('git("worktree", "add", "-q", "-b", "ws", str(tmp_path / "ws"))\n',
                      "a worktree was added in a test's temp directory"),
}


@pytest.mark.parametrize("plant", PLANTED)
def test_a_session_that_changes_its_repository_fails_and_names_the_change(tmp_path, plant):
    root = new_repo(tmp_path / "enclosing")
    plain_git("branch", "other", cwd=root)
    body, named = PLANTED[plant]
    proc = session(root, body)
    assert proc.returncode == pytest.ExitCode.TESTS_FAILED, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout, proc.stdout  # no test failed: only the tripwire says so
    assert "git isolation: this session changed the repository" in proc.stdout and named in proc.stdout, proc.stdout


@needs_xdist
def test_the_tripwire_checks_once_for_the_run_and_fails_it_under_xdist_with_the_coverage_save_still_run(tmp_path):
    """`pytest_sessionfinish` in a conftest is `worker_coverage`'s, and a second definition would shadow it. The
    tripwire is a plugin of its own: under xdist the exit code is non-zero, the report appears once, and each worker
    still saved its coverage."""
    root = new_repo(tmp_path / "enclosing")
    mark = tmp_path / "coverage-saved"
    body = PLANTED["core.bare"][0] + 'assert "PYTEST_XDIST_WORKER" in os.environ\n'
    (root / "tests").mkdir()
    (root / "tests" / "test_worker.py").write_text(
        'def test_a_worker_has_no_tripwire(request):\n'
        '    assert request.config.pluginmanager.get_plugin("aew-git-tripwire") is None\n', encoding="utf-8")
    proc = session(root, body, "-n", "2", COVERAGE_SAVE_MARK=str(mark))
    assert proc.returncode == pytest.ExitCode.TESTS_FAILED, proc.stdout + proc.stderr
    assert proc.stdout.count("git isolation: this session changed the repository") == 1, proc.stdout
    assert "3 passed" in proc.stdout and mark.read_text(encoding="utf-8") == "saved", proc.stdout


@pytest.mark.parametrize("workers", WORKERS)
def test_other_builders_ordinary_work_during_a_run_never_trips_it(tmp_path, workers):
    """Six builders share one `.git`. While this session runs, everything they do to it happens, done by a test only
    because that is what runs during the session: commits, a fetch's remote-tracking refs (even one a test identity
    made: this history has hundreds), a branch from an old test-identity commit, tracking configuration, `pack-refs`,
    and a worktree."""
    root = new_repo(tmp_path / "enclosing")
    elsewhere = Path(tempfile.mkdtemp(prefix="aew-builder-worktree-"))
    plain_git("branch", "theirs", cwd=root)
    body = f"""\
git("update-ref", "refs/heads/theirs", commit_as("builder@example.com"))
git("update-ref", "refs/heads/new-branch", commit_as("builder@example.com"))
git("update-ref", "refs/remotes/origin/fetched", commit_as("aew-test@invalid"))
git("update-ref", "refs/heads/from-old", commit_as("aew-test@invalid", date="2026-10-29T22:13:24 -0400"))
git("config", "branch.theirs.remote", "origin")
git("config", "branch.theirs.merge", "refs/heads/theirs")
git("config", "remote.origin.url", "https://example.invalid/repo.git")
git("pack-refs", "--all")
git("worktree", "add", "-q", "-b", "builder-wt", {str(elsewhere / "wt")!r})
"""
    try:
        proc = session(root, body, *workers)
    finally:
        shutil.rmtree(elsewhere, ignore_errors=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "git isolation" not in proc.stdout, proc.stdout
    assert "builder-wt" in plain_git("branch", "--list", cwd=root)  # the planted work did happen


def test_a_read_that_fails_at_the_end_is_reported_and_never_fails_the_session(tmp_path, monkeypatch):
    """Another session's lock can make a read fail. That says nothing about this run."""
    root = new_repo(tmp_path / "enclosing")
    config: Any = type("C", (), {"getoption": staticmethod(lambda *a, **k: None)})()
    wire = git_isolation.Tripwire(config, root, root / ".git", root / ".git")
    monkeypatch.setattr(git_isolation, "_git", lambda *a, **k: None)
    found, unread = wire.changes()
    assert found == [] and "the refs" in unread and "the worktrees" in unread and "this checkout's HEAD" in unread


def test_every_identity_the_tests_and_tools_configure_is_a_test_identity():
    """The tripwire recognizes a leaked commit by its committer. Every identity a helper, a test or a tool sets, found
    in the source, and AEW's own fallback."""
    setting = re.compile(r"""user\.email|_EMAIL""")
    address = re.compile(r"""[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+""")
    found: set[str] = {AEW_IDENTITY["email"]}
    for tree in ("tests", "tools"):
        for path in (ROOT / tree).rglob("*.py"):
            if path.name == Path(__file__).name:
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                if setting.search(line):
                    found.update(address.findall(line))
    assert {"aew-test@invalid", "aew-probe@invalid", "t@t", "aew-engine@invalid"} <= found
    assert sorted(email for email in found if not git_isolation.is_test_identity(email)) == []
    assert not git_isolation.is_test_identity("builder@example.com")


def test_this_suite_is_wired_as_the_inner_sessions_are(request):
    """The real conftest runs the isolation before anything else it imports, and the session has its tripwire when it
    runs in a repository. A worker has none: one check for the run."""
    text = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert text.index("git_isolation.isolate(") < text.index("import autopsy")
    assert "git_isolation.configure(config)" in text
    assert git_isolation.ceilings(ROOT) == os.environ["GIT_CEILING_DIRECTORIES"]
    wire = request.config.pluginmanager.get_plugin("aew-git-tripwire")
    if hasattr(request.config, "workerinput"):
        assert wire is None
    elif (ROOT / ".git").exists():
        assert wire is not None
        assert json.dumps(sorted(wire.before)) == json.dumps(["config", "head", "refs", "worktrees"])
