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
# M4-E E6a: a lease's grant starts its custodian's custody worker, a detached process that validates or routes under
# the lease. The suite drives custodians itself (in process, `Engine.custody_step` or `custody_run`, or a worker it
# starts), so no grant starts one behind a test's back; the CLI processes tests start inherit this. Withholding the
# worker only reduces authority: the S2 check ends a custodian whose worker never registered (`custody_register_s`).
os.environ.setdefault("AEW_CUSTODY_WORKER", "off")

import autopsy  # noqa: E402  (a hang, a deadline or a marked failure leaves an autopsy: G3 H1)
import harness_diagnostics  # noqa: E402  (a failed harness test reports and keeps its runs' files)
import lanes  # noqa: E402  (CI lanes, shards, lane reports; docs/implementation/testing-and-ci-strategy.md)
import session_deadline  # noqa: E402  (--session-deadline: CI keeps the evidence before a job timeout: G3 H3)
import watchdog  # noqa: E402  (--test-timeout: a hung test fails by name with every thread's stack)
from discovery import capture as discovery_capture  # noqa: E402  (D2: docs/implementation/vertical-uat.md §8)
from host_env import host_env_guard  # noqa: E402,F401  (GUARDED: a module's layouts never read the host's home)
from lanes import process_isolation  # noqa: E402,F401  (autouse: no test leaks AEW_* env or cwd)
from worker_coverage import pytest_sessionfinish  # noqa: E402,F401  (a worker saves coverage before teardown)


def pytest_addoption(parser: pytest.Parser) -> None:
    lanes.addoption(parser)
    watchdog.addoption(parser)
    session_deadline.addoption(parser)
    harness_diagnostics.addoption(parser)
    discovery_capture.addoption(parser)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    # tryfirst: the session deadline's job object must exist, and the controller be in it, before xdist starts any
    # worker (only processes created after the join are members). Without --session-deadline it creates nothing.
    session_deadline.configure(config)
    lanes.configure(config)
    watchdog.configure(config)
    autopsy.configure(config)
    discovery_capture.configure(config)


def pytest_unconfigure(config: pytest.Config) -> None:
    autopsy.unconfigure()


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    return lanes.ignore_collect(collection_path, config)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    outcome = yield
    harness_diagnostics.report(item, outcome.get_result())


def pytest_runtest_logfinish(nodeid: str, location: tuple[str, int | None, str]) -> None:
    harness_diagnostics.forget()


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


HOST_ENV = dict(os.environ)  # as the session found it: the base the host's own capability register lives under
CHILD_DATA_BASE: Path | None = None  # the session's base for the register of every `aew` a test starts (CAP-1 F2)


def clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_FAULT", "AEW_FAULT_MODE"):
        env.pop(key, None)
    if CHILD_DATA_BASE is not None:
        # A child `aew` never reaches the host's capability register: its base is the session's own directory, unless
        # the test already pointed it somewhere else (the sentinel below checks the host's stayed as it was)
        from aew.capability.store import base_variable

        name = base_variable()
        if env.get(name) == HOST_ENV.get(name):
            env[name] = str(CHILD_DATA_BASE)
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


def _register_files(path: Path) -> dict[str, tuple[int, int]]:
    if not path.exists():
        return {}
    return {p.relative_to(path).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(path.rglob("*")) if p.is_file()}


@pytest.fixture(scope="session")
def capability_register_dir(tmp_path_factory) -> Path:
    """The session's register, and the sentinel on the host's (CAP-1 review F2): every `aew` a test starts gets the
    session's own base (``clean_env``), and at the session's end the host's register is as the session found it.

    Its limits (#272's quick check, QC2):
    * a child started without ``clean_env`` that keeps the host's base is seen only here, at the end, and a read
      leaves nothing to see;
    * where the host sets ``XDG_DATA_HOME``, a child that keeps ``HOME`` but drops ``XDG_DATA_HOME`` writes the XDG
      default under the home directory, which is neither redirected nor watched; on Windows, where the host's
      ``LOCALAPPDATA`` is not the profile's own local app-data folder, a child that drops it writes the profile's
      register, also neither redirected nor watched;
    * any real change to the host's register during the run (the operator's own command, or another suite run from a
      commit without this fixture) fails the session, naming the files that changed."""
    global CHILD_DATA_BASE
    from aew.capability import store

    host = store.root()  # no override yet, and the environment as the session found it
    before = _register_files(host)
    CHILD_DATA_BASE = tmp_path_factory.mktemp("child-data-base")
    yield tmp_path_factory.mktemp("capability-register")
    CHILD_DATA_BASE = None
    after = _register_files(host)
    assert after == before, (f"the session changed the host's own capability register at {host}: "
                             f"{sorted(set(after.items()) ^ set(before.items()))}")


@pytest.fixture(autouse=True)
def capability_register(capability_register_dir):
    """No test reads or writes this host's own capability register (STG-15, CAP-1): in process the register is the
    session's own directory, and a test that needs an empty one sets ``aew.capability.store.ROOT_OVERRIDE`` itself;
    an `aew` a test starts gets the session's own base. (Not through ``monkeypatch``: an autouse fixture that takes
    it would undo every test's ``setenv`` after ``process_isolation`` looks.)"""
    from aew.capability import store

    saved = store.ROOT_OVERRIDE
    store.ROOT_OVERRIDE = capability_register_dir
    yield capability_register_dir
    store.ROOT_OVERRIDE = saved


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
