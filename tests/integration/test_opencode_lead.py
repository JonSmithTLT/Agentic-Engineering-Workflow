"""`aew opencode`: the Lead's OpenCode TUI as a Lead session (ADR-0009; M3 plan §2.6).

A V2 TUI running its own server (`--standalone`) gives every session its own environment as the shell
environment, so the environment `aew opencode` gives the TUI is exactly what the Lead's model and its shell
commands can see. A fake TUI (the fake agent behind an `opencode` launcher) records it and acts as the Lead's
model would: through `aew`, reaching the Lead broker.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aewflow import sample_project
from conftest import run_aew
from fake_harness import AGENT, HarnessLab, contains_credential, credential_hits

from aew.harness.opencode import projection

SECRET = "sk-provider-secret-must-not-reach-the-lead-model"
LAUNCHER = """import json, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
if sys.argv[1:2] == ["--version"]:
    print("opencode v2.0.18")
    sys.exit(0)
(here / "tui-argv.json").write_text(json.dumps(sys.argv[1:]))
sys.argv = ["fake_agent", "--script", str(here / "tui-script.json"), "--transcript", str(here / "tui.jsonl")]
sys.path.insert(0, {helpers!r})
import fake_agent
sys.exit(fake_agent.main())
"""


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, extra_env={"OPENAI_API_KEY": SECRET})
    tui = tmp_path / "tui"
    tui.mkdir()
    (tui / "opencode.py").write_text(LAUNCHER.format(helpers=str(AGENT.parent)), encoding="utf-8")
    lab.env["AEW_OPENCODE_BIN"] = str(tui / "opencode.py")
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def run_tui(lab: HarnessLab, steps: list[dict[str, Any]], *args: str):
    tui = Path(lab.env["AEW_OPENCODE_BIN"]).parent
    (tui / "tui-script.json").write_text(json.dumps(steps), encoding="utf-8")
    res = run_aew("-C", str(lab.root), "opencode", *args, env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token},
                  timeout=600)
    lines = (tui / "tui.jsonl").read_text(encoding="utf-8").splitlines() if (tui / "tui.jsonl").exists() else []
    steps_out = {e["i"]: e["result"] for e in map(json.loads, lines)}
    argv = json.loads((tui / "tui-argv.json").read_text()) if (tui / "tui-argv.json").exists() else None
    return res, steps_out, argv


def code(step: dict[str, Any]) -> str | None:
    return ((step.get("stderr_json") or {}).get("error") or {}).get("code")


def guide_of(lab) -> str:
    """The project's Lead guide, as `aew opencode` puts it in the Lead's system text (F16)."""
    from aew.engine.api import Engine

    return Engine.discover(lab.root).lead_guide()


def test_the_lead_tui_gets_a_curated_environment_and_acts_through_the_broker(lab, tmp_path):
    sync = tmp_path / "sync"
    sync.mkdir()
    res, steps, argv = run_tui(lab, [
        {"do": "dump_env", "path": str(sync / "env")},
        {"do": "child_env", "path": str(sync / "child"), "shell_path": str(sync / "shell")},
        {"do": "lead", "args": ["checkpoint", "--next", "dispatch T-0001 with --launch"]},
        {"do": "aew", "args": ["lead", "handoff", "offer", "--expect-rev", "1"]},
        {"do": "aew", "args": ["resume", "--json"]}])
    assert res.returncode == 0, res.stderr
    out = res.json
    assert (out["exit"], out["seat"], out["opencode"]) == (0, "held by your AEW_LEAD_TOKEN", "2.0.18")
    assert argv == ["--standalone", str(lab.root)]
    env = json.loads((sync / "env").read_text())
    for blob in (json.dumps(env), (sync / "child").read_text(), (sync / "shell").read_text()):
        assert SECRET not in blob and not contains_credential(blob)
    assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "OPENAI_API_KEY", "AEW_HARNESS_ADAPTERS",
                "AEW_OPENCODE_BIN"} & set(env)
    assert {"AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY"} <= set(env)
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == projection.lead_config(guide_of(lab))  # with the guide (F16)
    assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert steps[2]["exit"] == 0, steps[2]  # a Lead mutation, carried out by the broker
    assert code(steps[3]) == "USAGE"        # a credential-emitting command is refused in the session
    assert steps[4]["stdout_json"]["lead_note"] == "dispatch T-0001 with --launch"


def test_a_provider_key_reaches_the_lead_only_when_passed_explicitly(lab, tmp_path):
    sync = tmp_path / "sync"
    sync.mkdir()
    res, _, _ = run_tui(lab, [{"do": "dump_env", "path": str(sync / "env")}], "--provider-env", "OPENAI_API_KEY")
    assert res.returncode == 0, res.stderr
    assert json.loads((sync / "env").read_text())["OPENAI_API_KEY"] == SECRET
    assert "OPENAI_API_KEY passed to the Lead's OpenCode; the Lead model's shell commands can read it" in res.stderr


def test_print_config_starts_nothing_and_shows_no_values(lab):
    res = run_aew("-C", str(lab.root), "opencode", "--print-config",
                  env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token})
    assert res.returncode == 0, res.stderr
    shown = res.json
    assert shown["config"] == projection.lead_config(guide_of(lab))
    assert shown["command"][-2:] == ["--standalone", str(lab.root)]
    system = shown["config"]["agents"][projection.LEAD_AGENT]["system"]
    assert system.startswith(projection.LEAD_SYSTEM) and "# How work gets done in AEW: the Lead's guide" in system
    assert "OPENAI_API_KEY" not in shown["env_names"] and "AEW_LEAD_BROKER" in shown["env_names"]
    assert SECRET not in res.stdout and lab.project.token not in res.stdout
    assert not (Path(lab.env["AEW_OPENCODE_BIN"]).parent / "tui-argv.json").exists()


@pytest.mark.parametrize("args", [["--", "--server", "http://127.0.0.1:4096"], ["--provider-env", "AEW_LEAD_TOKEN"]],
                         ids=["another-server", "aew-variable"])
def test_refused_tui_arguments(lab, args):
    res = run_aew("-C", str(lab.root), "opencode", *args, env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token})
    assert res.returncode != 0 and res.error["code"] == "USAGE", res.stderr
    assert not (Path(lab.env["AEW_OPENCODE_BIN"]).parent / "tui-argv.json").exists()


def test_a_v1_opencode_is_refused_before_anything_starts(lab, tmp_path):
    v1 = tmp_path / "v1.py"
    v1.write_text("import sys\nprint('1.18.32')\n", encoding="utf-8")
    res = run_aew("-C", str(lab.root), "opencode", env={**lab.env, "AEW_OPENCODE_BIN": str(v1),
                                                         "AEW_LEAD_TOKEN": lab.project.token})
    assert res.error["code"] == "HARNESS_INCOMPATIBLE", res.stderr


def test_the_lead_commands_are_what_the_tui_is_given():
    commands = projection.lead_config()["commands"]
    assert sorted(commands) == ["aew-handoff", "aew-next", "aew-resume", "aew-status", "aew-ticket"]
    assert all(c["agent"] == projection.LEAD_AGENT for c in commands.values())
