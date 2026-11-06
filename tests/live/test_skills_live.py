"""Live lane, register E127: skills reach a real OpenCode 2.0.18 run through AEW's production path.

The skills probe of 2026-11-04 (the designer's ruling of 2026-11-03, §3) rebuilt the shapes by hand. This runs AEW's own
path: ``harness_contract`` decides the plan, the supervisor copies the exposed skills before containment, the layout
binds the copy read-only on Linux, and the projection's one ``skills`` entry and rules reach a real private server.

**Model-free** (``test_live_the_copy_is_loaded_bound_read_only_and_nothing_else``), run with any OpenCode binary: the
production adapter launches with scripted steps instead of a model (``opencode_scripted.py``). Asserted: ``/api/skill``,
on a fresh server over the run's own projection, lists exactly the exposed skills beside OpenCode's built-ins, which it
lists without the entry (a copy test: it shows what is loaded, not what is exposed); a write into the copy is refused,
with a control write beside it; the record says how the copy was protected.

**With a model** (``test_live_a_model_lists_loads_and_is_refused_what_it_was_not_given``), only when
``AEW_LIVE_SKILLS_MODEL`` (``provider/model``) and ``AEW_LIVE_PROVIDER_KEY_ENV`` (the name of the variable holding that
provider's key) are set. A paid model needs the operator's approval for each run (the operator, 2026-11-06), and never
one of OpenCode's free models: a ``-free`` id, or one the served catalog prices at zero (``live_models``), whatever its
provider; a paid OpenCode Zen model is allowed. Three runs, each capped at ``AEW_LIVE_SKILLS_STEPS`` steps:

* ``engineer`` and a project card that is ``engineer`` without ``optional_skills``: their
  ``first_step_input_tokens`` and ``system_bytes`` are **recorded, never asserted** (the cost of the listing, the
  2026-11-04 ruling §6);
* an investigator card with ``skills: [adversarial-review]`` and ``optional_skills: [c-development]``, whose Ticket
  asks it to call the ``skill`` tool with a denied id (``opencode``, a built-in), to load ``adversarial-review`` and
  read one of its ``references/`` files, and to try writing into the skill's folder from its shell.

What the model does is recorded, not asserted. What is asserted, whatever it does: a ``skill`` call of an id the run
was not given never completes; a write into the copy never succeeds; ``loaded`` and ``skill_other`` sum to the ``skill``
calls; no ``skill`` id the model wrote is stored. Each run's record goes to ``AEW_LIVE_RESULTS`` if set::

    AEW_LIVE_RESULTS=skills.jsonl pytest --live tests/live/test_skills_live.py -p no:xdist -q
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_investigation, create_planned_ticket, sample_project
from fake_harness import POLICY, HarnessLab
from harness_conformance import PROVIDER_SECRET
from live_models import free_model

from aew import skills
from aew.harness import procs, runlog
from aew.harness.opencode import adapter
from aew.harness.opencode.client import Server, location

pytestmark = pytest.mark.skipif(not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None,
                                reason="no OpenCode binary (set AEW_OPENCODE_BIN)")

MODEL_ENV, KEY_ENV, STEPS_ENV = "AEW_LIVE_SKILLS_MODEL", "AEW_LIVE_PROVIDER_KEY_ENV", "AEW_LIVE_SKILLS_STEPS"
RESULTS_ENV = "AEW_LIVE_RESULTS"
PIN_ENV = "AEW_LIVE_SKILLS_PIN"  # the model-free test's pin: offered by the catalog, never prompted
LINUX = sys.platform.startswith("linux")
LOAD_WAIT_S, SETTLE_S = 30.0, 5.0


def record_result(entry: dict[str, Any]) -> None:
    entry = {"schema": "aew/live-skills/v1", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}
    if os.environ.get(RESULTS_ENV):
        with open(os.environ[RESULTS_ENV], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")


def listed_skills(tmp: Path, config: dict[str, Any], directory: str) -> list[str]:
    """``/api/skill`` on a fresh private server with ``config`` (no model, no prompt): what OpenCode loaded. It loads
    skill sources asynchronously (2.0.18 on the VM: built-ins at about 1.5 s, the entry's skills at about 3 s), so the
    list is read until it has held still for ``SETTLE_S``."""
    state = tmp / f"inspect-{time.monotonic_ns()}"
    state.mkdir(parents=True)
    tree = procs.ProcessTree()
    env = adapter.server_env(dict(os.environ), state, provider_env=[], config=config, password=os.urandom(16).hex())
    try:
        server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=directory,
                              log_path=state / "server.log")
        seen: list[str] = []
        since, until = time.monotonic(), time.monotonic() + LOAD_WAIT_S
        while time.monotonic() < until:
            found = (server.client.get("/api/skill", location(directory)) or {}).get("data") or []
            now = sorted(str(s.get("id") or s.get("name")) for s in found)
            if now != seen:
                seen, since = now, time.monotonic()
            elif seen and time.monotonic() - since >= SETTLE_S:
                return seen
            time.sleep(0.5)
        return seen
    finally:
        tree.kill()


def served_catalog(tmp: Path) -> list[dict[str, Any]]:
    """``/api/model`` on a fresh private server (no model, no prompt, no key): the catalog this OpenCode serves, read
    until it has held still for ``SETTLE_S`` (it fills in asynchronously, as the skills do)."""
    state = tmp / f"catalog-{time.monotonic_ns()}"
    state.mkdir(parents=True)
    tree = procs.ProcessTree()
    env = adapter.server_env(dict(os.environ), state, provider_env=[], config={"snapshots": False},
                             password=os.urandom(16).hex())
    try:
        server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=str(tmp),
                              log_path=state / "server.log")
        seen: list[dict[str, Any]] = []
        since, until = time.monotonic(), time.monotonic() + LOAD_WAIT_S
        while time.monotonic() < until:
            now = (server.client.get("/api/model", location(str(tmp))) or {}).get("data") or []
            if len(now) != len(seen):
                seen, since = now, time.monotonic()
            elif seen and time.monotonic() - since >= SETTLE_S:
                break
            time.sleep(0.5)
        return seen
    finally:
        tree.kill()


def run_messages(state_dir: Path, directory: str) -> list[dict[str, Any]]:
    """Every message of every session in a run's private state, through a fresh server (never its database)."""
    tree = procs.ProcessTree()
    env = adapter.server_env(dict(os.environ), state_dir, provider_env=[], config={"snapshots": False},
                             password=os.urandom(16).hex())
    try:
        server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=directory,
                              log_path=state_dir / "inspect-server.log")
        out: list[dict[str, Any]] = []
        for s in (server.client.get("/api/session", location(directory)) or {}).get("data") or []:
            page = server.client.get(f"/api/session/{s['id']}/message", {"order": "asc", "limit": "200"}) or {}
            out += page.get("data") or []
        return out
    finally:
        tree.kill()


def tool_parts(messages: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [c for m in messages for c in m.get("content") or [] if isinstance(c, dict) and c.get("type") == "tool"
            and c.get("name") == name]


# ---------------------------------------------------------------------------------------------- model-free


def scripted_lab(tmp_path: Path) -> HarnessLab:
    from opencode_scripted import HERE as HELPERS

    # Pinned and never prompted (the steps are scripted): a model this OpenCode's catalog offers, never called
    provider, _, model = os.environ.get(PIN_ENV, "openai/gpt-5-nano").partition("/")
    policy = {**POLICY, "harness": "opencode-scripted", "provider_env": ["OPENAI_API_KEY"],
              "profiles": {"standard": {"provider": provider, "model": model}}}
    return HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy, extra_env={
        "OPENAI_API_KEY": PROVIDER_SECRET, "AEW_LAUNCH_ACK_S": "240",
        "AEW_HARNESS_ADAPTERS": f"opencode-scripted={HELPERS / 'opencode_scripted.py'}:ScriptedOpenCodeAdapter"})


def test_live_the_copy_is_loaded_bound_read_only_and_nothing_else(tmp_path):
    lab = scripted_lab(tmp_path)
    try:
        run = "R-INV-0001-1"
        harness = runlog.run_dir(lab.aew_root, run) / "harness"
        inside, beside = harness / "skills" / "c-development" / "planted.md", harness / "control.txt"
        lab.script("default", {"steps": [{"do": "write", "files": {str(inside): "x", str(beside): "x"}}]})
        wid = create_planned_ticket(lab.project, tmp_path)  # the default implementer card: `engineer`
        out = lab.lead("work", "assign", wid, "--launch")
        assert out["launch"]["run"] == run
        lab.wait(run, timeout=300)
        record = lab.record(run)
        planned = record["contract"]["extra"]["skills"]
        assert planned["offered"] == ["c-development", "python-development"] == planned["exposed"]
        assert record["launch"]["skills"] == planned
        wrote = lab.step(run, 0)
        contained = record["containment"]["filesystem"] == "os_readonly_roots"
        assert planned["copy"] == ("read_only_bind" if contained else "rules_only")
        if contained:  # the shell's own write (the rules stand in front of the model's edit tool, not of this)
            assert wrote["refused"] == {str(inside): "EROFS"} and wrote["wrote"] == [str(beside)], wrote
        config = json.loads((harness / "opencode-config.json").read_text(encoding="utf-8"))
        assert config["skills"] == [os.path.realpath(harness / "skills")]
        directory = os.path.realpath(record["contract"]["workspace"])
        built_in = listed_skills(tmp_path, {k: v for k, v in config.items() if k != "skills"}, directory)
        loaded = listed_skills(tmp_path, config, directory)
        assert sorted(set(loaded) - set(built_in)) == planned["exposed"] and set(built_in) <= set(loaded)
        record_result({"test": "copy", "platform": sys.platform, "copy": planned["copy"], "built_in": built_in,
                       "loaded": loaded, "write": wrote})
    finally:
        lab.cleanup()


# ---------------------------------------------------------------------------------------------- with a model


PROBE_CARD = """schema: aew/role/v1
role: skill_probe
display_name: Skill probe
version: 1
extends: investigator
purpose: Check which skills this run's skill tool offers, and what it may do with them.
skills: [adversarial-review]
optional_skills: [c-development]
outputs: [discovery_record]
"""
PLAIN_CARD = """schema: aew/role/v1
role: plain_engineer
display_name: Plain engineer
version: 1
extends: implementer
purpose: General software engineer implementing an accepted Ticket plan within scope.
skills: []
required_capabilities: [exact_code_search, source_mutation, targeted_test_execution]
outputs: [implementation_report]
"""
PROBE_GOAL = (
    "report, in this order: (1) every skill id the skill tool lists; (2) the result of calling the skill tool with "
    "the id opencode; (3) load adversarial-review, then read its references/plan-review.md with your read tool and "
    "quote its first line; (4) the exact output of running `touch` on a new file named probe in the folder that holds "
    "that SKILL.md")


def model_lab(tmp_path: Path) -> HarnessLab:
    ref, key_name = os.environ.get(MODEL_ENV), os.environ.get(KEY_ENV)
    if not ref or not key_name or not os.environ.get(key_name):
        pytest.skip(f"set {MODEL_ENV} and {KEY_ENV} (and the key itself) for the model runs: a paid model, each run "
                    "approved by the operator; never one of OpenCode's free models")
    why = free_model(ref, served_catalog(tmp_path))
    assert why is None, f"the operator ruled out OpenCode's free models (2026-11-06): {why}"
    provider, _, model = ref.partition("/")
    steps = int(os.environ.get(STEPS_ENV, "8"))
    policy = {**POLICY, "harness": "opencode", "provider_env": [key_name],
              "profiles": {"standard": {"provider": provider, "model": model, "max_steps": steps,
                                        "deadline_s": 600}}}
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy,
                            extra_env={key_name: os.environ[key_name], "AEW_LAUNCH_ACK_S": "240"})
    roles_dir = lab.aew_root / "roles"
    roles_dir.mkdir(exist_ok=True)
    (roles_dir / "skill_probe.yaml").write_text(PROBE_CARD, encoding="utf-8", newline="\n")
    (roles_dir / "plain_engineer.yaml").write_text(PLAIN_CARD, encoding="utf-8", newline="\n")
    return lab


def observe(lab: HarnessLab, run: str) -> dict[str, Any]:
    lab.wait(run, timeout=900)
    record = lab.record(run)
    result = record.get("result") or {}
    planned = record["launch"]["skills"]
    calls = (result.get("tools_called") or {}).get("skill", 0)
    if "loaded" in result:  # unknown stays unknown; when known, the sum is every skill call (11-04 §5)
        assert sum(result["loaded"].values()) + result["skill_other"] == calls
        assert set(result["loaded"]) <= set(planned["exposed"])
        assert isinstance(result["skill_other"], int)
    return {"run": run, "status": record.get("status"), "exposed": planned["exposed"], "copy": planned.get("copy"),
            "system_bytes": record["launch"]["context"]["system_bytes"],
            "first_step_input_tokens": result.get("first_step_input_tokens"),
            "tools_called": result.get("tools_called"),
            "loaded": result.get("loaded"), "skill_other": result.get("skill_other"), "usage": result.get("usage")}


def test_live_a_model_lists_loads_and_is_refused_what_it_was_not_given(tmp_path):
    lab = model_lab(tmp_path)
    try:
        listing = {}
        for card in ("engineer", "plain_engineer"):
            wid = create_planned_ticket(lab.project, tmp_path, title=f"Add subtract() ({card})",
                                        extra=("--card", card))
            listing[card] = observe(lab, lab.lead("work", "assign", wid, "--launch")["launch"]["run"])
        assert listing["engineer"]["exposed"] == ["c-development", "python-development"]
        assert listing["plain_engineer"]["exposed"] == []
        record_result({"test": "listing", "model": os.environ[MODEL_ENV], "runs": listing})

        wid = create_investigation(lab.project, tmp_path, card="skill_probe",
                                   extra=("--goal", PROBE_GOAL))
        run = lab.lead("work", "dispatch", wid, "--launch")["launch"]["run"]
        seen = observe(lab, run)
        assert seen["exposed"] == ["adversarial-review", "c-development"]
        record = lab.record(run)
        harness = runlog.run_dir(lab.aew_root, run) / "harness"
        messages = run_messages(harness, os.path.realpath(record["contract"]["workspace"]))
        calls = [{"id": (p.get("state") or {}).get("input", {}).get("id")
                  if isinstance((p.get("state") or {}).get("input"), dict) else None,
                  "status": (p.get("state") or {}).get("status")} for p in tool_parts(messages, "skill")]
        for call in calls:  # a denied id through a present `skill` tool never completes
            if call["id"] not in seen["exposed"]:
                assert call["status"] != "completed", call
        reads = [{"path": ((p.get("state") or {}).get("input") or {}).get("path"),
                  "status": (p.get("state") or {}).get("status")} for p in tool_parts(messages, "read")]
        copy = os.path.realpath(harness / "skills")
        for name in os.listdir(copy):  # nothing the model did added to the copy
            assert name in seen["exposed"], name
        assert not (Path(copy) / "adversarial-review" / "probe").exists()
        record_result({"test": "probe", "model": os.environ[MODEL_ENV], "run": seen, "skill_calls": calls,
                       "reads_of_the_copy": [r for r in reads if str(r["path"] or "").startswith(copy)],
                       "shells": [(p.get("state") or {}).get("status") for p in tool_parts(messages, "shell")],
                       "manifest": {n: skills.entries()[n]["sha256"] for n in seen["exposed"]}})
    finally:
        lab.cleanup()
