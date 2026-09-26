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
    proc = subprocess.run(
        [sys.executable, "-m", "aew", *args],
        cwd=cwd,
        env=clean_env(env),
        input=input,
        capture_output=True,
        text=True,
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
