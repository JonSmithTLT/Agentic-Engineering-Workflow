from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

IS_WINDOWS = sys.platform == "win32"
sys.path.insert(0, str(Path(__file__).resolve().parent / "helpers"))

import lanes  # noqa: E402  (CI lanes, shards, lane reports; docs/implementation/testing-and-ci-strategy.md)
import watchdog  # noqa: E402  (--test-timeout: a hung test fails by name with every thread's stack)
from lanes import process_isolation  # noqa: E402,F401  (autouse: no test leaks AEW_* env or cwd)


def pytest_addoption(parser: pytest.Parser) -> None:
    lanes.addoption(parser)
    watchdog.addoption(parser)


def pytest_configure(config: pytest.Config) -> None:
    lanes.configure(config)
    watchdog.configure(config)


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    return lanes.ignore_collect(collection_path, config)


@dataclass
class CLIResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    @property
    def error(self) -> dict[str, Any]:
        return json.loads(self.stderr)["error"]


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_FAULT", "AEW_FAULT_MODE"):
        env.pop(key, None)
    if extra:
        env.update(extra)
    return env


def run_aew(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None,
            input: str | None = None, timeout: float = 180) -> CLIResult:
    """Run the CLI as a separate process with NO controlling terminal/console.

    This is exactly how a harness tool call runs, and it guarantees a takeover
    prompt can never block on the developer's terminal during tests.
    """
    kwargs: dict[str, Any] = {}
    if IS_WINDOWS:
        # A hidden console shared with child git processes: no window ever appears.
        # (DETACHED_PROCESS made every child git.exe allocate a visible console.)
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    # No terminal here, so a credential a command issues comes back on stdout only with --print-credential (refused,
    # and not needed, inside a Lead session).
    printing = [] if (env or {}).get("AEW_LEAD_BROKER") else ["--print-credential"]
    lanes.count_cli_call()
    proc = subprocess.run(
        [sys.executable, "-m", "aew", *printing, *args],
        cwd=cwd,
        env=clean_env(env),
        input=input,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        stdin=None if input is not None else subprocess.DEVNULL,
        **kwargs,
    )
    return CLIResult(proc.returncode, proc.stdout, proc.stderr)


@pytest.fixture
def aew_cli():
    return run_aew


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_git_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "user.name", "AEW Test", cwd=path)
    git("config", "user.email", "aew-test@invalid", cwd=path)
    git("config", "core.autocrlf", "false", cwd=path)
    for rel, content in (files or {"README.md": "# fixture\n"}).items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    git("add", "-A", cwd=path)
    git("commit", "-q", "-m", "initial", cwd=path)
    return path


@dataclass
class Project:
    root: Path
    token: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def aew(self, *args: str, env: dict[str, str] | None = None, input: str | None = None) -> CLIResult:
        return run_aew("-C", str(self.root), *args, env=env, input=input)

    def ok(self, *args: str, env: dict[str, str] | None = None) -> Any:
        res = self.aew(*args, env=env)
        assert res.returncode == 0, f"aew {' '.join(args)} failed: {res.stderr or res.stdout}"
        return res.json

    def rev(self) -> int:
        return self.ok("lead", "show")["revision"]

    def lead(self, *args: str) -> Any:
        """Run a Lead mutation with the current token and revision."""
        return self.ok(*args, "--token", self.token, "--expect-rev", str(self.rev()))

    def adopt_policy(self, reason: str = "the operator's reviewed policy edit") -> Any:
        """Accept a manifest or policy edit made in the test, as the operator would: `aew manifest adopt`, confirmed at
        their own terminal (substituted in-process, as :meth:`as_operator` does)."""
        return self.as_operator("manifest_adopt", reason=reason)

    def pin_policy(self) -> None:
        """Fixture setup only: pin the policy files as they are now, with no transition, as if the project had been
        initialized with them. For fixtures that configure policy before the test starts (so revisions and decision
        ids stay what the test expects); an edit the test is about goes through :meth:`adopt_policy`."""
        from invariants import load_control

        from aew.engine.base import POLICY_PINS
        from aew.engine.store import serialize_control

        state = load_control(self.root)
        state[POLICY_PINS] = policy_pins(self.root)
        (self.root / ".aew/state/control.yaml").write_bytes(serialize_control(state))

    def as_operator(self, method: str, **kwargs: Any) -> Any:
        """A Lead mutation the operator confirmed at their own terminal (a decision recorded as theirs). The terminal
        channel is substituted in-process, as the takeover tests do; `test_authority.py` covers the refusal without
        it."""
        from aew.engine.api import Engine

        return getattr(Engine.discover(self.root), method)(
            token=self.token, expect_rev=self.rev(), authorization={"authorized_by": "operator-tty"},
            **kwargs)


def policy_pins(root: Path) -> dict[str, str | None]:
    """The pins `aew manifest adopt` would record for the project at ``root`` now."""
    from aew.engine.base import policy_files
    from aew.knowledge.manifest import load_manifest
    from aew.util import sha256_file

    aew = root / ".aew"
    return {rel: sha256_file(aew / rel) if (aew / rel).is_file() else None for rel in policy_files(load_manifest(aew))}


@pytest.fixture
def repo(tmp_path) -> Path:
    return make_git_repo(tmp_path / "repo", {
        "README.md": "# fixture\n",
        "docs/adr/0001-use-aew.md": "# ADR 1\n",
    })


@pytest.fixture
def project(repo) -> Project:
    p = Project(repo)
    p.ok("init")
    p.token = p.ok("lead", "acquire", "--expect-rev", "0", "--session-label", "lead-a")["token"]
    return p
