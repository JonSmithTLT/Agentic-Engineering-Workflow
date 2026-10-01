"""OpenCode adapter units: the projection (golden), the capability probe against the real 2.0.18 API and doctored
copies of it, the server and Lead environments, and effective-model extraction.

Goldens live in tests/fixtures/opencode/. A deliberate projection change is reviewed as a diff of those files:
regenerate them with ``AEW_UPDATE_GOLDENS=1 pytest tests/unit/test_opencode_units.py``.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from aew.errors import UsageError
from aew.harness.contract import LaunchContract
from aew.harness.opencode import adapter, capabilities, lead, projection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "opencode"
SPEC = json.loads((FIXTURES / "openapi-2.0.18.min.json").read_text(encoding="utf-8"))
CREDENTIAL = "aew1.tk_0123456789abcdef." + "S" * 43


def contract(role: str = "implementer", *, card: str = "python_engineer", skills: list[str] | None = None,
             capabilities_: list[str] | None = None, effort: str | None = "high",
             max_steps: int | None = None) -> LaunchContract:
    return LaunchContract(
        run="R-INV-0007-2", invocation="INV-0007", work_unit="T-0003", role=role, scope="ticket",
        card={"id": card, "version": 1, "sha256": "0" * 64},
        execution_profile={"profile": "standard", "harness": "opencode", "provider": "anthropic",
                           "model": "claude-sonnet-5", "effort": effort, "max_steps": max_steps, "deadline_s": None,
                           "selected_by": "policy", "rule": "default", "policy_sha256": "1" * 64},
        workspace="/work/aew-workspaces/T-0003", expected_kinds=["implementation_report"],
        operations=["check.run", "context.read", "submit.implementation_report"], pack_path="/p", pack_sha256="2" * 64,
        pack_text="# pack\n", continuation=None, run_dir="/r", scratch="/r/scratch",
        extra={"card_skills": skills if skills is not None else ["python-development"],
               "card_capabilities": capabilities_ or ["exact_code_search", "source_mutation"],
               "provider_env": ["ANTHROPIC_API_KEY"]})


def golden(name: str, value: Any) -> None:
    path = FIXTURES / f"{name}.golden.json"
    text = json.dumps(value, indent=1, sort_keys=True) + "\n"
    if os.environ.get("AEW_UPDATE_GOLDENS") == "1":
        path.write_bytes(text.encode("utf-8"))
    assert path.exists(), f"missing golden {path.name}: run with AEW_UPDATE_GOLDENS=1 and review the new file"
    assert json.loads(path.read_text(encoding="utf-8")) == json.loads(text), f"{path.name} changed: review the diff"


# ---------------------------------------------------------------------------------------------- projection


def test_implementer_projection_golden():
    c = contract(max_steps=40)
    config = projection.invocation_config(c, private_dirs=projection.private_output_dirs("/r/harness", "/",
                                                                                         scratch=c.scratch))
    golden("projection-implementer", {"config": config, "session": projection.session_body(c, "/ws", config[
        "permissions"]), "skills": projection.skills(c)})


def test_reviewer_and_researcher_projection_golden():
    reviewer = contract("reviewer", card="code_reviewer", skills=["code-review"],
                        capabilities_=["exact_code_search", "repository_exploration"], effort=None)
    researcher = contract("researcher", card="researcher", skills=[], capabilities_=["documentation_lookup"])
    golden("projection-read-only", {"reviewer": projection.invocation_config(reviewer),
                                    "researcher": projection.invocation_config(researcher)})


def test_lead_projection_golden():
    golden("projection-lead", projection.lead_config())


def effect(rules: list[dict[str, str]], action: str, resource: str = "*") -> str:
    """OpenCode's evaluation: the last rule whose action and resource match wins."""
    out = "ask"
    for r in rules:
        if r["action"] in (action, "*") and r["resource"] in (resource, "*"):
            out = r["effect"]
    return out


@pytest.mark.parametrize("role, edit, web", [("implementer", "allow", "deny"), ("reviewer", "deny", "deny"),
                                             ("verifier", "deny", "deny"), ("researcher", "deny", "allow"),
                                             ("investigator", "deny", "deny"), ("planner", "deny", "deny")])
def test_invocation_rules_never_ask_and_deny_what_no_role_may_do(role, edit, web):
    caps = ["documentation_lookup"] if role == "researcher" else ["exact_code_search"]
    rules = projection.invocation_config(contract(role, capabilities_=caps))["permissions"]
    assert {r["effect"] for r in rules} <= {"allow", "deny"}  # an unanswered ask blocks a V2 session forever
    for action in ("subagent", "question", "external_directory", "todowrite", "some_future_tool", "skill"):
        assert effect(rules, action) == "deny", action
    assert (effect(rules, "edit"), effect(rules, "webfetch"), effect(rules, "websearch")) == (edit, web, web)
    assert effect(rules, "shell") == effect(rules, "read") == "allow"
    assert effect(rules, "read", "*.env") == effect(rules, "read", "*.env.*") == "deny"  # V2's own default asks
    assert effect(rules, "read", "*.env.example") == "allow"


def test_only_the_runs_own_opencode_output_is_readable_outside_the_workspace():
    private = projection.private_output_dirs("/r/harness", "/", scratch="/r/scratch")
    assert private == ("/r/harness/xdg-data/opencode/tool-output/*", "/r/harness/xdg-data/opencode/shell/*/*",
                       "/r/harness/tmp/opencode/*", "/r/scratch/*")  # the last: the run's scratch (M3 step 8)
    rules = projection.invocation_config(contract(), private_dirs=private)["permissions"]
    assert effect(rules, "external_directory") == "deny"
    assert all(effect(rules, "external_directory", p) == "allow" for p in private)


def test_requested_skills_are_reported_unavailable_and_stay_denied():
    c = contract(skills=["python-development", "security-review"])
    assert projection.skills(c) == {"requested": ["python-development", "security-review"], "exposed": [],
                                    "unavailable": ["python-development", "security-review"]}
    config = projection.invocation_config(c)
    assert "python-development, security-review" in config["agents"][projection.AGENT]["system"]
    assert effect(config["permissions"], "skill", "python-development") == "deny"
    provided = projection.invocation_config(c, provided_skills=frozenset({"security-review"}))
    assert effect(provided["permissions"], "skill", "security-review") == "allow"
    assert effect(provided["permissions"], "skill", "python-development") == "deny"


def test_the_pinned_model_is_everywhere_a_model_is_chosen():
    config = projection.invocation_config(contract())
    pinned = {"providerID": "anthropic", "model": "claude-sonnet-5", "variant": "high"}
    assert {name: a["model"] for name, a in config["agents"].items()} == {
        name: pinned for name in (projection.AGENT, *projection.AUXILIARY_AGENTS)}
    assert projection.model_ref({"provider": "p", "model": "m", "effort": None}) == {"providerID": "p", "id": "m"}


def test_lead_rules_ask_the_present_operator_but_never_edit_or_delegate():
    rules = projection.lead_config()["agents"][projection.LEAD_AGENT]["permissions"]
    assert effect(rules, "edit") == "deny" and effect(rules, "subagent") == "deny"
    assert effect(rules, "shell") == "ask" and effect(rules, "shell", "aew *") == "allow"
    assert effect(rules, "question") == "allow"
    for cmd in projection.lead_config()["commands"].values():  # inline shell only for fixed read-only commands
        for block in __import__("re").findall(r"!`([^`]*)`", cmd["template"]):
            assert block in {"aew resume", "aew status", "aew harness status"}, block
            assert "$" not in block


# ---------------------------------------------------------------------------------------------- capability probe


def test_the_real_2_0_18_api_has_everything_the_adapter_uses():
    assert capabilities.problems(SPEC) == []
    assert capabilities.version_problems("2.0.18") == []


def doctored(mutate) -> dict[str, Any]:
    spec = copy.deepcopy(SPEC)
    mutate(spec)
    return spec


@pytest.mark.parametrize("mutate, expected", [
    (lambda s: s["paths"]["/api/session/{sessionID}/environment"].pop("put"),
     "operation PUT /api/session/{sessionID}/environment is missing"),
    (lambda s: s["paths"]["/api/session/{sessionID}/prompt"]["post"]["requestBody"]["content"]["application/json"][
        "schema"]["properties"].pop("delivery"), "does not accept ['delivery']"),
    (lambda s: s["components"]["schemas"]["Session.Message.Assistant"]["properties"].pop("model"),
     "Session.Message.Assistant lacks ['model']"),
    (lambda s: s["components"]["schemas"]["Permission.Effect"].update(enum=["allow", "ask"]),
     "Permission.Effect lacks ['deny']"),
    (lambda s: s["components"]["schemas"]["Config.AgentEncoded"]["properties"].pop("permissions"),
     "Config.AgentEncoded lacks ['permissions']"),
    (lambda s: s["paths"]["/api/model"]["get"].update(parameters=[]), "does not accept query ['location']"),
], ids=["operation", "request-field", "response-field", "enum", "config-key", "query"])
def test_a_doctored_api_names_what_is_missing(mutate, expected):
    found = capabilities.problems(doctored(mutate))
    assert any(expected in p for p in found), found


@pytest.mark.parametrize("version", ["1.18.32", "3.0.0", "dev", None])
def test_a_non_v2_server_is_refused(version):
    assert capabilities.version_problems(version)


def test_something_that_is_not_openapi_is_refused():
    assert capabilities.problems("<html>") and capabilities.problems({"paths": None})


# ---------------------------------------------------------------------------------------------- environments


def base_env() -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), "ANTHROPIC_API_KEY": "sk-ant-secret", "OPENAI_API_KEY": "sk-openai",
           "AEW_HARNESS_ADAPTERS": "x", "AEW_LEAD_TOKEN": CREDENTIAL, "GITHUB_TOKEN": "ghp_x", "XDG_CONFIG_HOME": "/c",
           "OPENCODE_CONFIG": "/cfg/opencode.json", "OPENCODE_PASSWORD": "pw"}
    env.update({k: "v" for k in (("SYSTEMROOT", "TEMP", "USERPROFILE") if sys.platform == "win32" else ("HOME",))})
    return env


def test_the_server_gets_basics_named_provider_variables_and_private_state(tmp_path):
    env = adapter.server_env(base_env(), tmp_path, provider_env=["ANTHROPIC_API_KEY", "AEW_LEAD_TOKEN", "MISSING"],
                             config={"a": 1}, password="pw2")
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-secret"
    assert adapter.server_env({**base_env(), "SHELL": "/bin/bash"}, tmp_path, provider_env=[], config={},
                              password="p")["SHELL"] == "/bin/bash"  # OpenCode picks the agent's shell from it
    assert not {"OPENAI_API_KEY", "GITHUB_TOKEN", "AEW_HARNESS_ADAPTERS", "AEW_LEAD_TOKEN", "MISSING"} & set(env)
    assert env["OPENCODE_PASSWORD"] == "pw2" and env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == {"a": 1}
    for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
        assert Path(env[f"XDG_{kind}_HOME"]).parent == tmp_path


def test_a_provider_variable_holding_a_credential_is_never_passed(tmp_path):
    env = adapter.server_env({**base_env(), "SNEAKY": CREDENTIAL}, tmp_path, provider_env=["SNEAKY"], config={},
                             password="p")
    assert "SNEAKY" not in env


def test_the_lead_tui_environment_has_no_credential_and_no_provider_key():
    env = lead.tui_env(base_env(), provider_env=[])
    assert not {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "AEW_LEAD_TOKEN", "AEW_HARNESS_ADAPTERS",
                "OPENCODE_PASSWORD"} & set(env)
    assert env["XDG_CONFIG_HOME"] == "/c" and env["OPENCODE_CONFIG"] == "/cfg/opencode.json"
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == projection.lead_config()
    assert env["PATH"].split(os.pathsep)[0] == os.path.dirname(sys.executable)
    assert lead.tui_env(base_env(), provider_env=["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"] == "sk-ant-secret"


@pytest.mark.parametrize("name", ["AEW_LEAD_TOKEN", "NOT_SET", "SNEAKY"])
def test_the_lead_refuses_to_pass_aew_variables_missing_ones_or_credentials(name):
    with pytest.raises(UsageError):
        lead.tui_env({**base_env(), "SNEAKY": CREDENTIAL}, provider_env=[name])


def test_the_lead_tui_never_attaches_to_another_server(tmp_path):
    class E:
        repo_root = tmp_path

    with pytest.raises(UsageError):
        lead.command(E(), ["--server", "http://127.0.0.1:4096"])


# ---------------------------------------------------------------------------------------------- effective model


def test_effective_models_are_distinct_and_default_variant_is_no_effort():
    models = [{"providerID": "p", "id": "m", "variant": "high"}, {"providerID": "p", "id": "m", "variant": "high"},
              {"providerID": "p", "id": "small", "variant": "default"}, None]
    assert adapter._effective(models) == [{"provider": "p", "model": "m", "effort": "high"},
                                          {"provider": "p", "model": "small", "effort": None}]
