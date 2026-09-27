"""Live lane: the harness conformance scenarios against a real OpenCode 2.0.18 server (opt-in: ``--live``).

The real adapter starts a real private ``opencode-cli serve --stdio`` per run, with private XDG state, and never
touches the operator's OpenCode state or Desktop service. Scenario steps run through the real session's shell
endpoint (``opencode_scripted.py``); ``model_step`` is a real prompt to a free model
(``AEW_LIVE_OPENCODE_MODEL``, default below). Run it with::

    pytest --live tests/live -p no:xdist -q
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from aewflow import sample_project
from fake_harness import POLICY, HarnessLab
from harness_conformance import PROVIDER_SECRET, SCENARIOS, Driver, run_scenario
from opencode_scripted import HERE as HELPERS
from opencode_scripted import sessions_in_state

from aew.harness import procs, runlog
from aew.harness.opencode import adapter, projection
from aew.harness.opencode.client import Server

FREE_MODEL = os.environ.get("AEW_LIVE_OPENCODE_MODEL", "opencode/longcat-2.5-preview-free")

pytestmark = pytest.mark.skipif(not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None,
                                reason="no OpenCode binary (set AEW_OPENCODE_BIN)")


class OpenCodeDriver(Driver):
    name = "opencode-live"
    capabilities = frozenset({"incompatible"})

    def create_lab(self, tmp_path: Path) -> HarnessLab:
        provider, _, model = FREE_MODEL.partition("/")
        policy = {**POLICY, "harness": "opencode-scripted", "provider_env": ["OPENAI_API_KEY"],
                  "profiles": {"standard": {"provider": provider, "model": model}}}
        return HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy, extra_env={
            "OPENAI_API_KEY": PROVIDER_SECRET, "AEW_LAUNCH_ACK_S": "240",
            "AEW_HARNESS_ADAPTERS": f"opencode-scripted={HELPERS / 'opencode_scripted.py'}:ScriptedOpenCodeAdapter"})

    def script(self, lab, key, steps, *, effective=None, health=None):
        lab.script(key, {"steps": steps, "health": health})

    def state_dir(self, lab, run):
        return runlog.run_dir(lab.aew_root, run) / "harness"

    def sessions(self, lab, run):
        workspace = os.path.realpath(lab.record(run)["contract"]["workspace"])
        return sessions_in_state(self.state_dir(lab, run), workspace)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_opencode_2_0_18_conforms(scenario, tmp_path):
    run_scenario(scenario, OpenCodeDriver(), tmp_path)


def test_the_real_server_accepts_the_lead_projection(tmp_path):
    """`aew opencode` gives the TUI OPENCODE_CONFIG_CONTENT = the Lead projection: the real server must load its
    agent and commands (checked on a private server with private state, never the operator's)."""
    tree = procs.ProcessTree()
    env = adapter.server_env(dict(os.environ), tmp_path / "state", provider_env=[], config=projection.lead_config(),
                             password=os.urandom(16).hex())
    workspace = tmp_path / "ws"
    workspace.mkdir()
    try:
        server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=str(workspace),
                              log_path=tmp_path / "server.log")
        loc = {"location[directory]": os.path.realpath(workspace)}
        deadline = time.monotonic() + 60
        agents: dict = {}
        while not agents and time.monotonic() < deadline:  # agents load asynchronously, like the model catalog
            agents = {a["id"]: a for a in (server.client.get("/api/agent", loc) or {}).get("data") or []}
            time.sleep(0.25)
        commands = {c.get("name") or c.get("id") for c in (server.client.get("/api/command", loc) or {}).get("data")
                    or []}
    finally:
        tree.kill()
    assert projection.LEAD_AGENT in agents, sorted(agents)
    assert set(projection.LEAD_COMMANDS) <= commands, sorted(commands)
    lead = agents[projection.LEAD_AGENT]
    assert lead["system"] == projection.LEAD_SYSTEM
    assert lead["permissions"][-len(projection.LEAD_RULES):] == projection.LEAD_RULES  # the Lead's rules win
    (tmp_path / "lead-agent.json").write_text(json.dumps(agents[projection.LEAD_AGENT], indent=1))
