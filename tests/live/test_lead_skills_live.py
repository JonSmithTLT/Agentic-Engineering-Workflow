"""Live lane, register E161: the Lead's skills reach a real OpenCode through `aew opencode`'s own projection.

The row asks for a live check on Windows of an absolute ``skills`` path and a colliding id. Windows runs the Lead that
is not contained, whose configuration AEW merges over the operator's own: AEW's copy is one ``skills`` entry, an
absolute path, beside the operator's sources. Both tests build that configuration with AEW's production code
(``lead.deliver_lead_skills``, ``projection.lead_config``) on a fresh private server, never the operator's state, and
run on any platform with an OpenCode binary; on Windows the path is a drive path.

**Model-free** (``test_live_the_leads_absolute_skills_path_loads_beside_the_operators_own_and_a_colliding_id``): no
model, no key, no cost. A synthetic operator configuration file (``OPENCODE_CONFIG``, which `aew opencode` passes
through) names a skills folder of the operator's own holding a skill of AEW's id (``engineering-planning``) and one of
its own. Asserted: ``/api/skill`` lists AEW's three ids, from the absolute path; the operator's own skill is still
listed (AEW's entry is beside it, not over it); the colliding id is listed once. Which body OpenCode keeps for that id
is recorded, not asserted: the rules allow the id, whichever source wins.

**With a model** (``test_live_a_paid_model_loads_a_lead_skill_and_the_cost_is_recorded``), only when
``AEW_LIVE_LEAD_SKILLS_MODEL`` (``provider/model``) and ``AEW_LIVE_PROVIDER_KEY_ENV`` (the name of the variable holding
that provider's key, which must be set) are: a keyed, paid model the operator approves for that run (the operator,
2026-11-06), never one of OpenCode's free models (``live_models.free_model``). Two private servers, the Lead's
configuration with and without AEW's skills. Asserted: the model's ``skill`` call of ``engineering-planning`` completes,
counted as loaded by the function a run's record uses (``adapter.skill_loads``), and no permission is left asking.
Recorded, never asserted: which exposed skills the Lead loaded and how many other ``skill`` calls it made (the Lead's
server ends with its TUI, so a session's own record cannot count them at teardown, as a run's does), the first step's
input tokens with and without the listing (the listing's cost) and the input tokens before and after the load (a
loaded body's cost), with the ``SKILL.md`` size.
Each record goes to ``AEW_LIVE_RESULTS`` if set::

    AEW_LIVE_LEAD_SKILLS_MODEL=<provider/model> AEW_LIVE_PROVIDER_KEY_ENV=<VARIABLE> \\
        AEW_LIVE_RESULTS=lead-skills.jsonl python -m pytest --live tests/live/test_lead_skills_live.py -p no:xdist -q
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from live_models import free_model

from aew import skills
from aew.harness import procs
from aew.harness.opencode import adapter, lead, projection
from aew.harness.opencode.client import Server, location

pytestmark = pytest.mark.skipif(not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None,
                                reason="no OpenCode binary (set AEW_OPENCODE_BIN)")

MODEL_ENV, KEY_ENV, RESULTS_ENV = "AEW_LIVE_LEAD_SKILLS_MODEL", "AEW_LIVE_PROVIDER_KEY_ENV", "AEW_LIVE_RESULTS"
COLLIDING, OPERATORS_OWN = "engineering-planning", "operators-own-skill"
LOAD_WAIT_S, SETTLE_S, TURN_S = 30.0, 5.0, 300.0


def record_result(entry: dict[str, Any]) -> None:
    entry = {"schema": "aew/live-lead-skills/v1", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "platform": sys.platform, **entry}
    if os.environ.get(RESULTS_ENV):
        with open(os.environ[RESULTS_ENV], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")


def operator_config(tmp: Path) -> Path:
    """A synthetic operator configuration file and skills folder: one skill of AEW's id, one of the operator's own."""
    folder = tmp / "operator-skills"
    for name, about in ((COLLIDING, "The operator's own planning notes, which share an id with one of AEW's"),
                        (OPERATORS_OWN, "The operator's own skill, which no AEW skill shares an id with")):
        (folder / name).mkdir(parents=True)
        (folder / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {about}. Skip it in tests.\n---\n\n"
                                                f"# {name} (operator)\n", encoding="utf-8", newline="\n")
    path = tmp / "operator-opencode.json"
    path.write_text(json.dumps({"skills": [str(folder.resolve())]}), encoding="utf-8")
    return path


def lead_configuration(tmp: Path, *, with_skills: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """The uncontained Lead's configuration as `aew opencode` builds it (``tui_env``'s ``lead_config``), its skills
    copied by the production code into a synthetic project's per-start folder, and the plan as delivered."""
    engine = SimpleNamespace(aew_root=tmp / "project" / ".aew")
    if not with_skills:
        return projection.lead_config(), {}
    planned, at = lead.deliver_lead_skills(engine)
    return projection.lead_config(skills_dir=at, skills_planned=planned), planned


def start(tmp: Path, config: dict[str, Any], *, operator: Path | None, provider_env: list[str]) -> tuple[Any, Any]:
    state = tmp / f"state-{time.monotonic_ns()}"
    state.mkdir(parents=True)
    tree = procs.ProcessTree()
    env = adapter.server_env(dict(os.environ), state, provider_env=provider_env, config=config,
                             password=os.urandom(16).hex())
    if operator is not None:
        env["OPENCODE_CONFIG"] = str(operator)  # the operator's own file, as `aew opencode` passes it through
    workspace = tmp / "workspace"
    workspace.mkdir(exist_ok=True)
    server = Server.start(tree.spawn, adapter.binary_command(), env=env, cwd=str(workspace),
                          log_path=state / "server.log")
    return server, tree


def listed(server: Any, directory: str) -> list[dict[str, Any]]:
    """``/api/skill``, read until it has held still for ``SETTLE_S``: OpenCode loads skill sources asynchronously."""
    seen: list[dict[str, Any]] = []
    since, until = time.monotonic(), time.monotonic() + LOAD_WAIT_S
    while time.monotonic() < until:
        now = (server.client.get("/api/skill", location(directory)) or {}).get("data") or []
        if [s.get("id") or s.get("name") for s in now] != [s.get("id") or s.get("name") for s in seen]:
            seen, since = now, time.monotonic()
        elif seen and time.monotonic() - since >= SETTLE_S:
            break
        time.sleep(0.5)
    return seen


def test_live_the_leads_absolute_skills_path_loads_beside_the_operators_own_and_a_colliding_id(tmp_path):
    config, planned = lead_configuration(tmp_path, with_skills=True)
    [folder] = config["skills"]
    assert os.path.isabs(folder) and planned["exposed"] == list(skills.lead())
    if sys.platform == "win32":
        assert len(folder) > 2 and folder[1] == ":", folder  # a drive path, the shape the row asks to be checked
    server, tree = start(tmp_path, config, operator=operator_config(tmp_path), provider_env=[])
    try:
        found = listed(server, os.path.realpath(tmp_path / "workspace"))
    finally:
        tree.kill()
    ids = [str(s.get("id") or s.get("name")) for s in found]
    record_result({"test": "listing", "folder": folder, "listed": found})
    assert set(planned["exposed"]) <= set(ids), ids
    assert OPERATORS_OWN in ids, ids  # AEW's entry is beside the operator's sources, never over them
    assert ids.count(COLLIDING) == 1, ids
    winner = next(s for s in found if str(s.get("id") or s.get("name")) == COLLIDING)
    record_result({"test": "colliding", "id": COLLIDING, "kept": winner,
                   "aews": "operator" not in json.dumps(winner).lower()})


# ---------------------------------------------------------------------------------------------- with a model


def model_choice(tmp_path: Path) -> tuple[str, str]:
    ref, key_name = os.environ.get(MODEL_ENV), os.environ.get(KEY_ENV)
    if not ref or not key_name or not os.environ.get(key_name):
        pytest.skip(f"set {MODEL_ENV} and {KEY_ENV} (and the key itself): a keyed, paid model the operator approves "
                    "for this run, never one of OpenCode's free models")
    server, tree = start(tmp_path / "catalog", {"snapshots": False}, operator=None, provider_env=[])
    try:  # the catalog fills in asynchronously, as the skills do: read until it has held still
        catalog: list[dict[str, Any]] = []
        since, until = time.monotonic(), time.monotonic() + LOAD_WAIT_S
        while time.monotonic() < until:
            now = (server.client.get("/api/model", location(str(tmp_path))) or {}).get("data") or []
            if len(now) != len(catalog):
                catalog, since = now, time.monotonic()
            elif catalog and time.monotonic() - since >= SETTLE_S:
                break
            time.sleep(0.5)
    finally:
        tree.kill()
    why = free_model(ref, catalog)
    assert why is None, f"the operator ruled out OpenCode's free models (2026-11-06): {why}"
    return ref, key_name


def turn(server: Any, session: str, text: str) -> list[dict[str, Any]]:
    """One prompt to the session, until its idle after it; any permission it asks for is rejected (nothing answers
    one here), and recorded by the caller from the messages. Returns every message of the session."""
    def newest() -> dict[str, Any]:
        page = server.client.get(f"/api/session/{session}/message", {"order": "desc", "limit": "1"}) or {}
        return next(iter(page.get("data") or []), {})

    was = newest().get("id")  # the turn is over at an idle that was not there before the prompt
    server.client.post(f"/api/session/{session}/prompt", {"id": adapter.new_message_id(), "text": text})
    deadline = time.monotonic() + TURN_S
    while time.monotonic() < deadline:
        for request in (server.client.get(f"/api/session/{session}/permission") or {}).get("data") or []:
            server.client.post(f"/api/session/{session}/permission/{request['id']}/reply",
                               {"decision": "reject", "message": "the live test answers nothing"})
        last = newest()
        if last.get("type") == "idle" and last.get("id") != was:
            break
        time.sleep(1.0)
    else:
        pytest.fail(f"the turn did not end within {TURN_S:g}s")
    page = server.client.get(f"/api/session/{session}/message", {"order": "asc", "limit": "200"}) or {}
    return page.get("data") or []


def input_tokens(message: dict[str, Any]) -> int | None:
    tokens = message.get("tokens")
    if not isinstance(tokens, dict):
        return None
    return int(tokens.get("input") or 0) + int((tokens.get("cache") or {}).get("read") or 0)


def session_of(server: Any, directory: str, ref: str) -> str:
    provider, _, model = ref.partition("/")
    body = {"title": "AEW live: the Lead's skills", "agent": projection.LEAD_AGENT,
            "model": {"providerID": provider, "id": model}, "location": {"directory": directory}}
    return str(server.client.post("/api/session", body)["data"]["id"])


def test_live_a_paid_model_loads_a_lead_skill_and_the_cost_is_recorded(tmp_path):
    ref, key_name = model_choice(tmp_path)
    directory = os.path.realpath(tmp_path / "workspace")
    first: dict[str, Any] = {}
    for with_skills in (False, True):
        here = tmp_path / ("with" if with_skills else "without")
        config, planned = lead_configuration(here, with_skills=with_skills)
        server, tree = start(tmp_path, config, operator=None, provider_env=[key_name])
        try:
            session = session_of(server, directory, ref)
            messages = turn(server, session, "Reply with the single word: ready.")
            assistant = [m for m in messages if m.get("type") == "assistant"]
            first["with" if with_skills else "without"] = input_tokens(assistant[0]) if assistant else None
            if not with_skills:
                continue
            before = len(assistant)
            messages = turn(server, session, f"Load the `{COLLIDING}` skill with your `skill` tool, then reply with "
                                             "the first heading of its body and nothing else.")
        finally:
            tree.kill()
        assistant = [m for m in messages if m.get("type") == "assistant"]
        calls = [c for m in assistant for c in m.get("content") or []
                 if isinstance(c, dict) and c.get("type") == "tool" and c.get("name") == "skill"]
        # what the Lead loaded, counted by the function a run's record counts its loads with (adapter.skill_loads)
        counted = [adapter.skill_loads(m.get("content"), frozenset(planned["exposed"])) for m in assistant]
        loaded = [sid for ids, _ in counted for sid in ids]
        after = [input_tokens(m) for m in assistant[before:]]
        body = next(d["bytes"] for d in planned["delivered"] if d["name"] == COLLIDING)
        record_result({"test": "model", "model": ref, "first_step_input_tokens": first,
                       "turn_input_tokens_before": input_tokens(assistant[before - 1]) if before else None,
                       "turn_input_tokens_after": after, "skill_md_bytes": body,
                       "skill_calls": [{"status": (c.get("state") or {}).get("status")} for c in calls],
                       "loaded": {sid: loaded.count(sid) for sid in sorted(set(loaded))},
                       "skill_other": sum(other for _, other in counted)})
        assert COLLIDING in loaded, calls
