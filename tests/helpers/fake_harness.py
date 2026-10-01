"""The fake harness: a real adapter, a real supervisor, a real (scripted) agent process — no model.

``FakeAdapter`` is registered with ``AEW_HARNESS_ADAPTERS=fake=<this file>:FakeAdapter`` and runs
``fake_agent.py`` with the curated agent environment, inside the supervisor's process tree. Each run's
script is ``<AEW_FAKE_SCRIPTS>/<run>.json``, else ``<invocation>.json``, else ``default.json``.

``HarnessLab`` wraps a sample project for harness tests: a configured execution policy that routes to
the fake harness, the environment that registers it, script helpers, and teardown that kills every
supervisor the test started.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.harness import runlog
from aew.harness import contract as K
from aew.harness.base import HarnessAdapter
from aew.harness.contract import CREDENTIAL_RE, TERMINAL, LaunchContract
from aew.util import dump_yaml

HERE = Path(__file__).resolve().parent
AGENT = HERE / "fake_agent.py"
SCRIPTS_ENV = "AEW_FAKE_SCRIPTS"


class FakeAdapter(HarnessAdapter):
    name = "fake"

    def launch(self, contract: LaunchContract, agent_env: dict[str, str]) -> dict[str, Any]:
        scripts = Path(os.environ[SCRIPTS_ENV])
        script = next((p for p in (scripts / f"{contract.run}.json", scripts / f"{contract.invocation}.json",
                                   scripts / "default.json") if p.exists()), None)
        if script is None:
            from aew.errors import HarnessLaunchFailed
            raise HarnessLaunchFailed(f"no fake script for {contract.run}")
        spec = json.loads(script.read_text(encoding="utf-8"))
        header = spec if isinstance(spec, dict) else {}
        if header.get("health") == "incompatible":  # the capability probe of a harness that lacks something
            from aew.errors import HarnessIncompatible
            raise HarnessIncompatible("fake capability probe: required operation session.fork is missing")
        pin = contract.execution_profile
        self.effective = header.get("effective") or [
            {"provider": pin.get("provider"), "model": pin.get("model"), "effort": pin.get("effort")}]
        hdir = self.run_dir / "harness"
        hdir.mkdir(exist_ok=True)
        (hdir / "prompt.md").write_text(contract.prompt, encoding="utf-8")
        self.transcript = hdir / "transcript.jsonl"
        self._out = (hdir / "agent.log").open("ab")
        self.proc = self.tree.spawn([sys.executable, str(AGENT), "--script", str(script),
                                     "--transcript", str(self.transcript)],
                                    env=agent_env, cwd=contract.workspace, stdin=subprocess.DEVNULL,
                                    stdout=self._out, stderr=self._out)
        self.emit({"event": "fake.launched", "pid": self.proc.pid, "script": script.name})
        self.session = f"fake-{contract.run}"
        (hdir / "sessions").mkdir(exist_ok=True)
        (hdir / "sessions" / self.session).write_text(contract.run, encoding="utf-8")
        return {"harness": "fake", "version": "fake-1", "session": self.session, "state_dir": str(hdir)}

    def inspect(self) -> dict[str, Any]:
        rc = self.proc.poll()
        return {"alive": rc is None, "exit_code": rc, "session": None}

    def terminate(self) -> None:
        if not hasattr(self, "proc"):
            return
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        self._out.close()

    def send(self, text: str) -> None:
        with (self.run_dir / "harness" / "inbox.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"text": text}) + "\n")

    def collect(self) -> dict[str, Any]:
        if not hasattr(self, "transcript"):
            return {}
        lines = self.transcript.read_text(encoding="utf-8").splitlines() if self.transcript.exists() else []
        return {"effective": self.effective, "sessions": [self.session], "transcript_steps": len(lines)}


# ---------------------------------------------------------------------------------------------- test helpers

POLICY = {
    "schema": "aew/execution/v1", "configured": True, "harness": "fake",
    "profiles": {"standard": {"provider": "fakeprov", "model": "fake-model", "effort": "high"}},
    "routing": {"default": "standard", "archetypes": {}, "classes": {}, "cards": {}},
    "provider_env": [],
}


@dataclass
class HarnessLab:
    project: Any                      # conftest.Project
    tmp: Path
    env: dict[str, str] = field(default_factory=dict)
    sessions: list[subprocess.Popen[str]] = field(default_factory=list)  # Lead sessions the test started

    @classmethod
    def create(cls, project: Any, tmp: Path, *, policy: dict[str, Any] | None = None,
               extra_env: dict[str, str] | None = None) -> "HarnessLab":
        (project.root / ".aew/policy/execution.yaml").write_text(dump_yaml(policy or POLICY), encoding="utf-8",
                                                                 newline="\n")
        scripts = tmp / "fake-scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        env = {"AEW_HARNESS_ADAPTERS": f"fake={HERE / 'fake_harness.py'}:FakeAdapter",
               SCRIPTS_ENV: str(scripts), "AEW_LAUNCH_ACK_S": "60", **(extra_env or {})}
        return cls(project, tmp, env)

    @property
    def root(self) -> Path:
        return self.project.root

    @property
    def aew_root(self) -> Path:
        return self.project.root / ".aew"

    def script(self, name: str, steps: list[dict[str, Any]]) -> None:
        (Path(self.env[SCRIPTS_ENV]) / f"{name}.json").write_text(json.dumps(steps), encoding="utf-8")

    def aew(self, *args: str, env: dict[str, str] | None = None):
        return self.project.aew(*args, env={**self.env, **(env or {})})

    def ok(self, *args: str, env: dict[str, str] | None = None) -> Any:
        res = self.aew(*args, env=env)
        assert res.returncode == 0, f"aew {' '.join(args)} failed: {res.stderr or res.stdout}"
        return res.json

    def lead_args(self, *args: str) -> list[str]:
        return [*args, "--token", self.project.token, "--expect-rev", str(self.project.rev())]

    def lead(self, *args: str, env: dict[str, str] | None = None) -> Any:
        return self.ok(*self.lead_args(*args), env=env)

    def lead_res(self, *args: str, env: dict[str, str] | None = None):
        return self.aew(*self.lead_args(*args), env=env)

    def wait(self, run: str, timeout: float = 120) -> dict[str, Any]:
        from conftest import run_aew  # the CLI's own time limit must outlast the wait (a live model run can take minutes)

        res = run_aew("-C", str(self.root), "harness", "wait", run, "--timeout", str(timeout), env=self.env,
                      timeout=timeout + 120)
        assert res.returncode == 0, f"aew harness wait {run} failed: {res.stderr or res.stdout}"
        out = res.json
        assert not out["timed_out"], f"{run} still running after {timeout}s: {out}"
        return out

    def record(self, run: str) -> dict[str, Any]:
        return runlog.read_record(runlog.run_dir(self.aew_root, run)) or {}

    def transcript(self, run: str) -> list[dict[str, Any]]:
        path = runlog.run_dir(self.aew_root, run) / "harness" / "transcript.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def step(self, run: str, i: int) -> dict[str, Any]:
        for entry in self.transcript(run):
            if entry["i"] == i:
                return entry["result"]
        raise AssertionError(f"{run} has no transcript step {i}: {self.transcript(run)}")

    def until(self, predicate: Any, timeout: float = 60, what: str = "condition") -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.1)
        raise AssertionError(f"timed out after {timeout}s waiting for {what}")

    def cleanup(self) -> None:
        """End every run this lab started. A live run is stopped through the Lead (a request file alone is refused,
        independent review R1); when the project's Lead token no longer holds the seat, or a supervisor does not
        answer, the supervisor is killed if its pid still names the same process (pids are reused, and other tests'
        processes run in parallel). Its job object / sentinel then takes the harness tree. A Lead session still
        running is killed first (its own Popen handle: never a bare pid)."""
        from aew.engine.api import Engine
        from aew.errors import AEWError

        for proc in self.sessions:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
        runs = runlog.run_dir(self.aew_root, "x").parent
        dirs = sorted(runs.glob("*")) if runs.is_dir() else []
        live = [d for d in dirs if runlog.observed_status(d)[0] in (K.STARTING, K.RUNNING)]
        engine = Engine(self.root, self.aew_root) if live else None
        for directory in live:
            try:
                engine.harness_stop(token=self.project.token, run=directory.name, reason="test teardown")
            except AEWError:
                runlog.end_supervisor(directory)
        deadline = time.monotonic() + 20
        for directory in live:
            while runlog.observed_status(directory)[0] in (K.STARTING, K.RUNNING) and time.monotonic() < deadline:
                time.sleep(0.1)
            runlog.end_supervisor(directory)


def credential_hits(*roots: Path) -> list[str]:
    return runlog.scan_for_credentials(*roots)


def contains_credential(text: str) -> bool:
    return bool(CREDENTIAL_RE.search(text))


def finished(status: str) -> bool:
    return status in TERMINAL


IMPL_REPORT = {"claim": "subtract implemented with a focused test", "result": "pass",
               "producer": {"model": "fake-model", "harness": "fake"},
               "implementation": {"files_changed": ["calc/core.py", "tests/test_subtract.py"], "checks_run": ["unit"],
                                  "deviations": [], "self_review": {"completed": True, "notes": "diff matches plan"}}}
