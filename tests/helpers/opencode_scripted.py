"""The live-lane OpenCode driver: the real adapter and a real OpenCode 2.0.18 server, acting without a model.

``ScriptedOpenCodeAdapter`` is the production ``OpenCodeAdapter`` (private server, health probe, projection,
curated session environment, watching, process tree) with one change: instead of prompting a model with the
launch contract, it performs the scenario's steps itself through the session's own shell endpoint
(``POST /api/session/{id}/shell``), which runs each command in the real session environment and records it
in OpenCode's real database, exactly as a model's shell tool call would. ``model_step`` is a real prompt to
the pinned (free) model. ``exit`` with a non-zero code kills the server: the harness crashed.

Registered as ``opencode-scripted`` through ``AEW_HARNESS_ADAPTERS`` by ``OpenCodeDriver``.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from aew.harness import procs
from aew.harness.contract import LaunchContract
from aew.harness.opencode import capabilities
from aew.harness.opencode.adapter import OpenCodeAdapter, binary_command, new_message_id, server_env
from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable, Server, location

HERE = Path(__file__).resolve().parent
AGENT = HERE / "fake_agent.py"
SCRIPTS_ENV = "AEW_FAKE_SCRIPTS"


def load_script(run: str, invocation: str) -> dict[str, Any]:
    scripts = Path(os.environ[SCRIPTS_ENV])
    path = next((p for p in (scripts / f"{run}.json", scripts / f"{invocation}.json", scripts / "default.json")
                 if p.exists()), None)
    spec = json.loads(path.read_text(encoding="utf-8")) if path else []
    return spec if isinstance(spec, dict) else {"steps": spec}


class ScriptedOpenCodeAdapter(OpenCodeAdapter):
    name = "opencode-scripted"

    def launch(self, contract: LaunchContract, agent_env: dict[str, str]) -> dict[str, Any]:
        self.spec = load_script(contract.run, contract.invocation)
        return super().launch(contract, agent_env)

    def extra_requirements(self) -> tuple[capabilities.Op, ...]:
        if self.spec.get("health") == "incompatible":  # a real server lacking an operation must fail closed
            return (capabilities.Op("POST", "/api/aew-conformance/impossible"),)
        return ()

    def deliver_contract(self, contract: LaunchContract) -> None:
        self._model_turn = threading.Event()
        self.turn = "scripted"
        threading.Thread(target=self._run_script, args=(contract,), name="aew-scripted", daemon=True).start()

    def _turn_over(self, outcome: str, last: str = "", since: float = 0.0) -> None:
        """A model_step's turn ended: the script goes on (the base adapter would end the run here)."""
        self._take_snapshot()
        with self._lock:
            self.turn = "scripted"
        self._model_outcome = outcome
        self._model_turn.set()

    def _run_script(self, contract: LaunchContract) -> None:
        assert self.client is not None and self.server is not None
        transcript = self.state_dir / "transcript.jsonl"
        try:
            for i, step in enumerate(self.spec.get("steps") or []):
                do = step["do"]
                if do == "exit":
                    if step.get("code", 0):
                        self.server.proc.kill()  # the harness crashed; the monitor sees the server gone
                        return
                    break
                if do == "hang":
                    self._stop.wait()
                    return
                if do == "model_step":
                    self._model_turn.clear()
                    self._prompt("Reply with only the word OK.")
                    self._model_turn.wait(600)
                    continue
                step_file = self.state_dir / "steps" / f"{i}.json"
                step_file.parent.mkdir(exist_ok=True)
                step_file.write_text(json.dumps(step), encoding="utf-8")
                # `python` is the curated PATH's first (AEW's own); the line runs alike in bash, PowerShell and cmd
                command = (f'python "{AGENT.as_posix()}" --step-file "{step_file.as_posix()}" --index {i} '
                           f'--transcript "{transcript.as_posix()}"')
                self.client.post(f"/api/session/{self.session}/shell", {"id": new_message_id(), "command": command},
                                 timeout=float(step.get("timeout") or 120) + 120)
            self._take_snapshot()
            self._end(0, "the scripted run finished")
        except (OpenCodeError, OpenCodeUnavailable) as exc:
            if self.server.alive() and not self._stop.is_set():
                self._end(70, f"scripted step failed: {exc}")


def sessions_in_state(state_dir: Path, directory: str) -> set[str]:
    """The sessions a run's private OpenCode state holds, read through a fresh private server on that state
    (the supported interface; AEW never reads OpenCode's database files)."""
    tree = procs.ProcessTree()
    env = server_env(dict(os.environ), state_dir, provider_env=[], config={"snapshots": False},
                     password=os.urandom(16).hex())
    try:
        server = Server.start(tree.spawn, binary_command(), env=env, cwd=directory,
                              log_path=state_dir / "inspect-server.log")
        return {s["id"] for s in (server.client.get("/api/session", location(directory)) or {}).get("data") or []}
    finally:
        tree.kill()
