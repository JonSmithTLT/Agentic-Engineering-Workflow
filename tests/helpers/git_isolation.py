"""No test session writes to the git repository it runs in, or to the user's git configuration.

On 2026-11-08 a pre-push hook ran pytest with git's ``GIT_DIR`` still set. Tests that make throwaway repositories wrote
into the shared repository instead: ``core.bare``, the test identity, junk commits on real branches. Three layers:

- :func:`isolate` runs when ``tests/conftest.py`` is imported, so before xdist starts a worker and again in each worker.
  It clears every variable that redirects git, stops git walking up out of the checkout or the temp root, and points
  git's global configuration at a file of this session's, so ``--global`` never reaches the user's and a commit that
  lands anywhere unexpected still carries a test identity. A test's own ``env=`` for its own child still works.
- :class:`Tripwire` is the backstop: one check for the run, in the controller, that fails the session and names what
  changed.

Other sessions share this ``.git``: they commit, fetch, push, add worktrees and set branch tracking during a run. So the
tripwire never compares refs or configuration wholesale. It checks exact keys no one changes on purpose, this
checkout's own HEAD, and new or moved branches and lightweight tags whose tip a test identity committed during this run.

What it does not see, on purpose or at a known cost:

- a commit by a child with a stripped environment and the user's identity, into another branch;
- an annotated tag, whose own object has no committer; a commit with a pinned old committer date; a remote-tracking ref;
  a deleted branch; a branch moved back to an older commit;
- any other configuration key, such as ``core.hooksPath``;
- a worktree under a temp directory that is not pytest's;
- the user's files where a stripped child finds them elsewhere: it reads ``~/.gitconfig`` and
  ``~/.config/git/config`` from ``Path.home()``, so ``XDG_CONFIG_HOME``, and ``HOME`` on Windows, are not followed. With
  a session's global file, ``lanes.py``'s guard watches that file, so that child's write to any other key of the user's
  file passes too.

A cwd exactly at the checkout is the one walk-free route left, and a test's default cwd is the checkout: a ``git
config`` with no ``cwd=`` still writes to the shared file. Only the tripwire catches that, and only for its exact keys.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from aew.workspace.git import COUNTED_CONFIG as _COUNTED_CONFIG
from aew.workspace.git import LOCAL_ENV_VARS

# The installed Git's repository-local list is pinned against the product's LOCAL_ENV_VARS. The test harness also
# clears these extra names so synthetic repositories don't inherit the caller's discovery, ref, or template settings.
REDIRECTING = LOCAL_ENV_VARS | {
    "GIT_DISCOVERY_ACROSS_FILESYSTEM", "GIT_NAMESPACE", "GIT_QUARANTINE_PATH",
    "GIT_REFLOG_ACTION", "GIT_TEMPLATE_DIR",
}
# A hook runs with these set, and they outrank a test repository's own `user.name`.
IDENTITY = frozenset(f"GIT_{who}_{what}" for who in ("AUTHOR", "COMMITTER") for what in ("NAME", "EMAIL", "DATE"))

SESSION_NAME, SESSION_EMAIL = "AEW Test", "aew-test@invalid"
# Exact: a change to any of these is never another session's ordinary work.
WATCHED_SHARED = ("core.bare", "core.worktree", "user.name", "user.email")
WATCHED_USER = ("user.name", "user.email")
# A bound on a hung read, not a budget: one read took under 1 s on the shared repository at 100 % CPU (338 refs, 21
# worktrees). A read past it reports "could not read", and never fails the session.
GIT_TIMEOUT_S = 30.0
_NO_WINDOW: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


# Every identity a helper, a test or a perf tool commits as: closed, and pinned by a test against what they configure.
# Not `.invalid` as a whole: AEW's own runs commit at that domain too, in a repository a test session may run in (the
# product's AEW_IDENTITY, a dogfood clone's, CI's), and another ticket's commit during a run must not trip this.
TEST_IDENTITIES = frozenset({
    SESSION_EMAIL, "aew-perf@invalid", "aew-probe@invalid", "p@example.invalid", "perf@example.invalid", "perf@invalid",
    "probe@invalid", "t@example.invalid", "t@invalid", "t@t",
})


def is_test_identity(email: str) -> bool:
    return email.strip().strip("<>").lower() in TEST_IDENTITIES


def ceilings(root: Path) -> str:
    """``GIT_CEILING_DIRECTORIES``: git never walks up into the checkout, its parent or the temp root.

    A cwd exactly at the checkout still reaches it: that is how the tests read it. git resolves each entry itself, so a
    Windows temp root in its 8.3 short form (``JONSMI~1``) still matches: a test walks up in each form."""
    return os.pathsep.join((str(root), str(Path(root).parent), tempfile.gettempdir()))


def _session_config(root: Path) -> str:
    """This session's global git configuration: the file itself, removed at exit.

    It gives a commit made anywhere a test identity. The checkout is named as safe for a copy another user owns, and
    Windows keeps long paths. The user's own file holds nothing else the suite needs: CI's holds only an identity."""
    directory = tempfile.mkdtemp(prefix="aew-test-gitconfig-")
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    path = Path(directory) / "gitconfig"
    lines = ["[user]", f"\tname = {SESSION_NAME}", f"\temail = {SESSION_EMAIL}",
             "[safe]", f'\tdirectory = "{Path(root).as_posix()}"']
    if sys.platform == "win32":
        lines += ["[core]", "\tlongpaths = true"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def isolate(root: Path) -> None:
    """Clear what redirects git and set what confines it, for this process and every child it starts."""
    for name in list(os.environ):
        if name in REDIRECTING or name in IDENTITY or _COUNTED_CONFIG.match(name):
            del os.environ[name]
    os.environ["GIT_CEILING_DIRECTORIES"] = ceilings(root)
    # A worker shares its session's file.
    if not ("PYTEST_XDIST_WORKER" in os.environ and os.environ.get("GIT_CONFIG_GLOBAL")):
        os.environ["GIT_CONFIG_GLOBAL"] = _session_config(root)


def _git(checkout: Path, *args: str) -> str | None:
    """Its output, or None if git could not answer."""
    try:
        got = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=GIT_TIMEOUT_S, **_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return got.stdout if got.returncode == 0 else None


def _watched(checkout: Path, path: Path, keys: tuple[str, ...]) -> dict[str, str] | None:
    """The watched keys of one configuration file, read as a file so that a broken repository still answers. Nothing
    else in the file is kept."""
    if not path.exists():
        return {}
    text = _git(checkout, "config", "--file", str(path), "--list", "-z")
    if text is None:
        return None
    pairs = (entry.partition("\n") for entry in text.split("\0") if entry)
    return {key: value for key, _, value in pairs if key in keys}


def _under_pytest_temp(path: str, basetemp: str | None) -> bool:
    if any(part.startswith("pytest-of-") for part in Path(path).parts):
        return True
    if basetemp is None:
        return False
    return Path(os.path.realpath(path)).is_relative_to(os.path.realpath(basetemp))


class Tripwire:
    """Reads the repository the session runs in as it starts, and fails the session if a test changed it."""

    def __init__(self, config: pytest.Config, checkout: Path, common_dir: Path, git_dir: Path) -> None:
        self.config = config
        self.checkout, self.common_dir, self.git_dir = checkout, common_dir, git_dir
        self.started = int(time.time()) - 1  # git's commit dates are whole seconds
        self.before = self.read()

    def _config_files(self) -> dict[Path, tuple[str, ...]]:
        home = Path.home()
        return {self.common_dir / "config": WATCHED_SHARED, self.git_dir / "config.worktree": WATCHED_SHARED,
                home / ".gitconfig": WATCHED_USER, home / ".config" / "git" / "config": WATCHED_USER}

    def _head_file(self) -> str | None:
        try:
            return (self.git_dir / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def read(self) -> dict[str, Any]:
        tips = _git(self.checkout, "for-each-ref",
                    "--format=%(refname)%00%(objectname)%00%(committeremail)%00%(committerdate:unix)",
                    "refs/heads", "refs/tags")
        trees = _git(self.checkout, "worktree", "list", "--porcelain")
        head = _git(self.checkout, "rev-parse", "-q", "--verify", "HEAD")
        return {
            "config": {path: _watched(self.checkout, path, keys) for path, keys in self._config_files().items()},
            "head": (self._head_file(), head.strip() if head else None),
            "refs": None if tips is None else {
                fields[0]: fields[1:] for fields in (line.split("\0") for line in tips.splitlines()) if len(fields) == 4
            },
            "worktrees": None if trees is None else {
                line[len("worktree "):] for line in trees.splitlines() if line.startswith("worktree ")
            },
        }

    def changes(self) -> tuple[list[str], list[str]]:
        """What a test changed, and what could not be read: a read that fails, for instance on another session's lock,
        says nothing about this run, so it is reported and never fails the session."""
        after, found, unread = self.read(), [], []
        for path, was in self.before["config"].items():
            now = after["config"][path]
            if was is None or now is None:
                unread.append(str(path))
            elif was != now:
                found += [f"{key} changed in {path}: {was.get(key)!r} -> {now.get(key)!r}"
                          for key in sorted(set(was) | set(now)) if was.get(key) != now.get(key)]
        if None in after["head"] or None in self.before["head"]:  # so an unborn HEAD at the start goes unchecked
            unread.append("this checkout's HEAD")
        elif after["head"] != self.before["head"]:
            found.append(f"this checkout's HEAD moved: {self.before['head']} -> {after['head']}")
        if self.before["refs"] is None or after["refs"] is None:
            unread.append("the refs")
        else:
            for ref, (sha, email, date) in sorted(after["refs"].items()):
                moved = (self.before["refs"].get(ref) or [None])[0] != sha
                if moved and is_test_identity(email) and date.isdigit() and int(date) >= self.started:
                    found.append(f"{ref} is at {sha[:12]}, committed by the test identity {email} during this run")
        if self.before["worktrees"] is None or after["worktrees"] is None:
            unread.append("the worktrees")
        else:
            basetemp = self.config.getoption("basetemp", None)
            found += [f"a worktree was added in a test's temp directory: {path}"
                      for path in sorted(after["worktrees"] - self.before["worktrees"])
                      if _under_pytest_temp(path, basetemp)]
        return found, unread

    @pytest.hookimpl(tryfirst=True)  # before the lane report is written with the session's exit status
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        found, unread = self.changes()
        if found:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = self.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is None:
            return
        if found:
            reporter.write_sep("!", f"git isolation: this session changed the repository at {self.common_dir}",
                               red=True)
            for line in found:
                reporter.write_line(f"  {line}")
            reporter.write_line("  Do not repair it and do not rerun: another session may share this repository, and "
                                "a repair can lose its work. Stop and tell the Lead, or the operator.")
        if unread:
            reporter.write_line(f"git isolation: could not read, so did not check: {', '.join(unread)}")


class Unchecked:
    """A checkout whose repository could not be read as the session started: the run has no tripwire, and says so."""

    def __init__(self, checkout: Path) -> None:
        self.checkout = checkout

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        terminalreporter.write_line(f"git isolation: could not read the repository at {self.checkout} as this session "
                                    "started, so this session did not check it")


def configure(config: pytest.Config) -> None:
    """In the controller, or a session without xdist: one check for the run. It registers as its own plugin because a
    conftest holds only one ``pytest_sessionfinish``, and ours is ``worker_coverage``'s. A session outside any
    repository, or without git, has nothing to check; one whose repository could not be read says so."""
    if hasattr(config, "workerinput"):
        return
    checkout = Path(str(config.rootpath))
    found = _git(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir", "--absolute-git-dir")
    lines = found.splitlines() if found else []
    if len(lines) == 2:
        config.pluginmanager.register(Tripwire(config, checkout, Path(lines[0]), Path(lines[1])), "aew-git-tripwire")
    elif (checkout / ".git").exists():  # a directory, or a linked worktree's file
        config.pluginmanager.register(Unchecked(checkout), "aew-git-unchecked")
