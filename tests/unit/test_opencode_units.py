"""OpenCode adapter units: the projection (golden), the capability probe against the real pinned API and doctored
copies of it, the server and Lead environments, and effective-model extraction.

Goldens live in tests/fixtures/opencode/. A deliberate projection change is reviewed as a diff of those files:
regenerate them with ``AEW_UPDATE_GOLDENS=1 pytest tests/unit/test_opencode_units.py``.
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from aew.errors import HarnessIncompatible, UsageError
from aew.harness.contract import LaunchContract
from aew.harness.opencode import adapter, capabilities, lead, projection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "opencode"
SPEC = json.loads((FIXTURES / f"openapi-{capabilities.TESTED_VERSIONS[0]}.min.json").read_text(encoding="utf-8"))
CREDENTIAL = "aew1.tk_0123456789abcdef." + "S" * 43


def contract(role: str = "implementer", *, card: str = "python_engineer", skills: list[str] | None = None,
             capabilities_: list[str] | None = None, effort: str | None = "high",
             max_steps: int | None = None, optional: list[str] | None = None) -> LaunchContract:
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
               "card_optional_skills": optional or [],
               "card_capabilities": capabilities_ or ["exact_code_search", "source_mutation"],
               "provider_env": ["ANTHROPIC_API_KEY"]})


# Where a run's skills are copied, as an adapter on Linux would say (E127)
AT = projection.skills_at("/r/harness", "/")


def config_of(c: LaunchContract, **kw: Any) -> dict[str, Any]:
    return projection.invocation_config(c, skills_dir=AT, **kw)


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
    config = config_of(c, private_dirs=projection.private_output_dirs("/r/harness", "/", scratch=c.scratch))
    golden("projection-implementer", {"config": config, "session": projection.session_body(c, "/ws", config[
        "permissions"]), "skills": projection.skills(c)})


def test_reviewer_and_researcher_projection_golden():
    reviewer = contract("reviewer", card="code_reviewer", skills=["adversarial-review"],
                        capabilities_=["exact_code_search", "repository_exploration"], effort=None)
    researcher = contract("researcher", card="researcher", skills=[], capabilities_=["documentation_lookup"])
    golden("projection-read-only", {"reviewer": config_of(reviewer), "researcher": config_of(researcher)})


def test_lead_projection_golden():
    """The machine's own interpreter and `aew` location (E180) are placeholders here; their values are pinned by
    ``test_the_lead_projection_matches_the_pinned_opencode_configuration_schema``."""
    config = projection.lead_config()
    server = config["mcp"]["servers"][projection.LEAD_MCP_SERVER]
    assert server["command"][0] == sys.executable
    server["command"][0] = "<this interpreter>"
    server["environment"]["PYTHONPATH"] = "<this aew's import root>"
    golden("projection-lead", config)


def test_lead_projection_messaging_golden():
    config = projection.lead_config(switches=frozenset({"coordination.messaging"}))
    server = config["mcp"]["servers"][projection.LEAD_MCP_SERVER]
    server["command"][0] = "<this interpreter>"
    server["environment"]["PYTHONPATH"] = "<this aew's import root>"
    golden("projection-lead-messaging", config)


@pytest.mark.parametrize(("platform", "harness", "supported"), [
    ("linux", "opencode", True), ("win32", "opencode", False), ("linux", "codex", False)])
def test_worker_preamble_offers_wait_only_on_the_qualified_harness_platform(monkeypatch, platform, harness, supported):
    from aew.harness import wait_binding
    from aew.harness.contract import preamble

    monkeypatch.setattr(wait_binding.sys, "platform", platform)
    c = contract()
    c.extra["coordination"] = {"messaging": "enabled"}
    c.execution_profile["harness"] = harness
    text = preamble(c)
    assert ("`aew message wait`" in text) == supported
    if not supported:
        assert "Reply and end your turn." in text and "--timeout" not in text and "WAIT_UNSUPPORTED" not in text


def effect(rules: list[dict[str, str]], action: str, resource: str = "*") -> str:
    """OpenCode's evaluation: the last rule whose action and resource match wins."""
    out = "ask"
    for r in rules:
        if r["action"] in (action, "*") and r["resource"] in (resource, "*"):
            out = r["effect"]
    return out


def matches(pattern: str, text: str) -> bool:
    """OpenCode's pattern match (read from its 2.2.6 bundle): `*` is any run of characters, `?` one character, a
    trailing ` *` also matches nothing after it, and case is ignored."""
    def rx(p: str) -> str:
        return "".join(".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in p)
    body = rx(pattern[:-2]) + "( .*)?" if pattern.endswith(" *") else rx(pattern)
    return re.fullmatch(body, text, re.S | re.I) is not None


def decided(rules: list[dict[str, str]], action: str, resource: str) -> str:
    """OpenCode's evaluation with its own matching: the last rule whose action and resource match wins."""
    out = "ask"
    for r in rules:
        if matches(r["action"], action) and matches(r["resource"], resource):
            out = r["effect"]
    return out


SHELL_COMMANDS = ("aew status", "aew", "git status", "git diff HEAD", "git diff --output=x", "git log -p .env",
                  "git diff --no-index a b", "git -C x diff", "rm -rf build", "python -m pytest", "ls")


@pytest.mark.parametrize("who", ["implementer", "reviewer", "lead"])
def test_a_call_to_bash_is_decided_as_a_call_to_shell(who):
    """The 2.2.6 bump: 2.2.5 runs a call to `bash` as `shell`, so every rule set decides each command the same under
    both names (projection.SHELL_ACTIONS), whichever name OpenCode checks."""
    rules = projection.LEAD_RULES if who == "lead" else config_of(contract(who))["permissions"]
    for command in SHELL_COMMANDS:
        assert decided(rules, "bash", command) == decided(rules, "shell", command), (who, command)
    assert decided(rules, "shell", "aew status") == "allow"


def test_every_projection_closes_session_warming_and_image_generation():
    """The 2.2.6 bump: session warming sends model requests a provider's rate limit counts, and image generation
    offers a tool whenever a provider has an image model. Every worker's and the Lead's configuration turns both off."""
    reviewer = contract("reviewer", card="code_reviewer", skills=[], capabilities_=["exact_code_search"])
    for config in (config_of(contract()), config_of(reviewer), projection.lead_config(),
                   projection.lead_config("guide", contained={"network": {}}, relays={"openai": "http://x"})):
        assert config["warming"] is False
        assert config["experimental"]["image_generate"] is False
    assert projection.lead_config()["experimental"]["policies"] == projection.lead_provider_policies()


def test_the_leads_mcp_server_is_never_pooled():
    """2.2.6's `pool` shares one connection across every directory that configures a server identically."""
    servers = projection.lead_config()["mcp"]["servers"]
    assert servers and all(server["pool"] is False for server in servers.values())


def test_the_closed_defaults_are_keys_the_probe_requires():
    """A release that respells a key AEW closes fails closed at launch, rather than leaving the default open."""
    fields = capabilities.REQUIRED_FIELDS["Config.InfoEncoded"]
    assert set(projection.CLOSED) | {f"experimental.{k}" for k in projection.CLOSED_EXPERIMENTAL} <= set(fields)
    assert "pool" in capabilities.REQUIRED_FIELDS["Mcp.LocalConfigEncoded"]


def test_the_leads_rules_deny_the_browser_tool_and_skill_themselves():
    """OpenCode appends these denies itself; AEW's own rules state them, so they do not rest on its defaults."""
    assert effect(projection.LEAD_RULES, "browser") == "deny"
    assert effect(projection.LEAD_RULES, "skill", "browser") == "deny"


def test_the_probe_requires_the_policy_actions_aew_projects():
    """2.2.3 changed `integration.use` incompatibly; the probe now checks the inline action enum, not only that the
    policies are an array."""
    key = ("Config.InfoEncoded", "experimental.policies[].action")
    assert {p["action"] for p in projection.lead_provider_policies()} <= capabilities.REQUIRED_FIELD_ENUMS[key]
    assert capabilities.problems(SPEC) == []
    doctored = copy.deepcopy(SPEC)
    action = (doctored["components"]["schemas"]["Config.InfoEncoded"]["properties"]["experimental"]["properties"]
              ["policies"]["items"]["properties"]["action"])
    action["enum"] = [v for v in action["enum"] if v != "provider.use"]
    assert ("schema Config.InfoEncoded field experimental.policies[].action lacks ['provider.use']"
            in capabilities.problems(doctored))
    # The same values spelt as `anyOf` of `const`s still satisfy it (#364 review, n2).
    values = list(dict.fromkeys([*action["enum"], "provider.use"]))
    del action["enum"]
    action["anyOf"] = [{"type": "string", "const": v} for v in values]
    assert capabilities.problems(doctored) == []


@pytest.mark.parametrize("role, edit, web", [("implementer", "allow", "deny"), ("reviewer", "deny", "deny"),
                                             ("verifier", "deny", "deny"), ("researcher", "deny", "allow"),
                                             ("investigator", "deny", "deny"), ("planner", "deny", "deny")])
def test_invocation_rules_never_ask_and_deny_what_no_role_may_do(role, edit, web):
    caps = ["documentation_lookup"] if role == "researcher" else ["exact_code_search"]
    rules = config_of(contract(role, capabilities_=caps))["permissions"]
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
    rules = config_of(contract(), private_dirs=private)["permissions"]
    assert effect(rules, "external_directory") == "deny"
    assert all(effect(rules, "external_directory", p) == "allow" for p in (*private, AT.pattern))  # E127: + skills


def test_requested_skills_not_shipped_are_reported_unavailable_and_stay_denied():
    c = contract(skills=["python-development", "never-shipped"])
    planned = projection.skills(c)
    assert (planned["requested"], planned["exposed"], planned["unavailable"]) == (
        ["never-shipped", "python-development"], ["python-development"], ["never-shipped"])
    assert planned["reasons"] == {"never-shipped": "not_shipped"}
    config = config_of(c)
    assert "does not provide: never-shipped." in config["agents"][projection.AGENT]["system"]
    assert effect(config["permissions"], "skill", "never-shipped") == "deny"
    assert effect(config["permissions"], "skill", "python-development") == "allow"


def test_a_run_on_its_own_network_is_told_what_it_reaches_and_how_to_ask_for_more():
    """#257's review, F3: the run's network, from its label: the mode, what it reaches, that the rest is refused by
    design, and the setting the Lead asks the operator for. The upstream and the stated limits stay the operator's;
    a run on the host's network gets no such line."""
    def line(network: dict[str, Any] | None) -> list[str]:
        system = config_of(contract(), network=network)["agents"][projection.AGENT]["system"]
        assert "https://upstream.example" not in system and "the stated residual" not in system
        return [s for s in system.splitlines() if "network of its own" in s]

    [own] = line({"mode": "proxy_only", "provider_relay": "configured", "provider_upstream": "https://upstream.example",
                  "egress_allow": ["models.opencode.ai:443", "pypi.org:443"], "limits": ["the stated residual"]})
    assert own == ("- This run has a network of its own (`proxy_only`): it reaches your model's provider and, through "
                   "`HTTPS_PROXY`, only `models.opencode.ai:443`, `pypi.org:443`. Every other connection is refused by "
                   "design. If your work needs another host, do not work around the refusal: name the `host:port` and "
                   "what you needed it for in your report, so the Lead can ask the operator to add it to "
                   "`containment.network.egress_allow`.")
    [isolated] = line({"mode": "isolated", "provider_relay": "none"})
    assert "(`isolated`): it has no route out. Every other connection is refused by design." in isolated
    assert line(None) == []


def test_the_pinned_model_is_everywhere_a_model_is_chosen():
    config = config_of(contract())
    pinned = {"providerID": "anthropic", "model": "claude-sonnet-5", "variant": "high"}
    assert {name: a["model"] for name, a in config["agents"].items()} == {
        name: pinned for name in (projection.AGENT, *projection.AUXILIARY_AGENTS)}
    assert projection.model_ref({"provider": "p", "model": "m", "effort": None}) == {"providerID": "p", "id": "m"}


def test_lead_rules_ask_the_present_operator_but_never_edit_or_delegate():
    rules = projection.lead_config()["agents"][projection.LEAD_AGENT]["permissions"]
    assert effect(rules, "edit") == "deny" and effect(rules, "subagent") == "deny"
    assert effect(rules, "shell") == "ask" and effect(rules, "shell", "aew *") == "allow"
    assert effect(rules, "question") == "allow"
    # which command may run inline is test_lead_text's rule; here, none takes an argument
    for cmd in projection.lead_config()["commands"].values():
        for block in __import__("re").findall(r"!`([^`]*)`", cmd["template"]):
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
    env = adapter.server_env(base_env(), tmp_path, provider_env=["ANTHROPIC_API_KEY"], config={"a": 1},
                             password="pw2")
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-secret"
    assert adapter.server_env({**base_env(), "SHELL": "/bin/bash"}, tmp_path, provider_env=[], config={},
                              password="p")["SHELL"] == "/bin/bash"  # OpenCode picks the agent's shell from it
    assert not {"OPENAI_API_KEY", "GITHUB_TOKEN", "AEW_HARNESS_ADAPTERS", "AEW_LEAD_TOKEN"} & set(env)
    assert env["OPENCODE_PASSWORD"] == "pw2" and env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == {"a": 1}
    for kind in ("CONFIG", "DATA", "STATE", "CACHE"):
        assert Path(env[f"XDG_{kind}_HOME"]).parent == tmp_path


@pytest.mark.parametrize(("name", "why"), [("MISSING", "MISSING is not set in this environment: set MISSING in the "
                                                     "terminal you start AEW from"),
                                         ("AEW_LEAD_TOKEN", "AEW_LEAD_TOKEN is an AEW variable"),
                                         ("SNEAKY", "SNEAKY holds an AEW credential")])
def test_a_provider_variable_the_server_cannot_get_refuses_the_start_naming_it_never_silently_dropped(tmp_path, name,
                                                                                                    why):
    with pytest.raises(HarnessIncompatible) as refused:
        adapter.server_env({**base_env(), "SNEAKY": CREDENTIAL}, tmp_path, provider_env=["ANTHROPIC_API_KEY", name],
                           config={}, password="p")
    assert why in refused.value.message and refused.value.details["variables"] == [name]
    assert CREDENTIAL not in refused.value.message  # the refusal names the variable, never its value


def test_the_lead_tui_environment_has_no_credential_and_no_provider_key():
    env = lead.tui_env(base_env(), provider_env=[])
    assert not {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN", "AEW_LEAD_TOKEN", "AEW_HARNESS_ADAPTERS",
                "OPENCODE_PASSWORD"} & set(env)
    assert env["XDG_CONFIG_HOME"] == "/c" and env["OPENCODE_CONFIG"] == "/cfg/opencode.json"
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == projection.lead_config(tools={"placed": False, "tools": []})
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"])["experimental"]["policies"] == [
        {"action": "provider.use", "resource": "opencode", "effect": "deny"},
        {"action": "provider.use", "resource": "opencode-go", "effect": "deny"}]  # the designer's ruling, 2026-11-06
    assert "opencode" not in json.loads(env["OPENCODE_CONFIG_CONTENT"]).get("providers", {})  # never switched on
    assert env["PATH"].split(os.pathsep)[0] == os.path.dirname(sys.executable)
    assert lead.tui_env(base_env(), provider_env=["ANTHROPIC_API_KEY"])["ANTHROPIC_API_KEY"] == "sk-ant-secret"


def no_proxy_of(env: dict[str, str]) -> list[str]:
    names = [k for k in env if k.upper() == "NO_PROXY"]
    assert len({env[k] for k in names}) <= 1, names  # every spelling carries the same list
    return env[names[0]].split(",") if names else []


@pytest.mark.parametrize("proxy", ["HTTPS_PROXY", "http_proxy", "ALL_PROXY"])
def test_a_proxy_passed_to_opencode_never_carries_its_loopback_traffic(tmp_path, proxy):
    base = {**base_env(), proxy: "http://proxy.example:3128", "NO_PROXY": "intranet.example"}
    server = adapter.server_env(base, tmp_path, provider_env=[proxy, "NO_PROXY"], config={}, password="p")
    tui = lead.tui_env(base, provider_env=[proxy, "NO_PROXY"])
    for env in (server, tui):
        assert env[proxy] == "http://proxy.example:3128"  # the provider traffic keeps the operator's proxy
        assert no_proxy_of(env) == ["intranet.example", "127.0.0.1", "localhost", "::1", "[::1]"]
    if sys.platform != "win32":
        assert server["no_proxy"] == server["NO_PROXY"]  # curl reads only the lower-case spelling
    else:
        assert [k for k in server if k.upper() == "NO_PROXY"] == ["NO_PROXY"]  # one entry: Windows ignores case


@pytest.mark.parametrize("operator", [" a.example ,, a.example,", "b.example"])
def test_the_operators_no_proxy_entries_are_kept_whatever_their_spelling_or_spacing(tmp_path, operator):
    name = "NO_PROXY" if sys.platform == "win32" else "no_proxy"  # POSIX: the lower-case spelling merges too
    base = {**base_env(), "HTTPS_PROXY": "http://proxy.example:3128", name: operator}
    env = adapter.server_env(base, tmp_path, provider_env=["HTTPS_PROXY", name], config={}, password="p")
    kept = list(dict.fromkeys(h.strip() for h in operator.split(",") if h.strip()))
    assert no_proxy_of(env) == [*kept, "127.0.0.1", "localhost", "::1", "[::1]"]


def test_an_operators_no_proxy_star_is_left_exactly_as_it_was(tmp_path):
    base = {**base_env(), "HTTPS_PROXY": "http://proxy.example:3128", "NO_PROXY": "*"}
    server = adapter.server_env(base, tmp_path, provider_env=["HTTPS_PROXY", "NO_PROXY"], config={}, password="p")
    tui = lead.tui_env(base, provider_env=["HTTPS_PROXY", "NO_PROXY"])
    for env in (server, tui):  # urllib reads * only as the whole value: appending would re-enable the proxy
        assert {k: v for k, v in env.items() if k.upper() == "NO_PROXY"} == {"NO_PROXY": "*"}


def test_without_a_proxy_the_harness_environment_gains_no_no_proxy(tmp_path):
    assert no_proxy_of(adapter.server_env(base_env(), tmp_path, provider_env=[], config={}, password="p")) == []
    assert no_proxy_of(lead.tui_env(base_env(), provider_env=[])) == []


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


@pytest.mark.parametrize("announced", ["http://127.0.0.1:4096", "http://127.0.0.1:4096/"])
def test_the_server_address_is_accepted_only_on_loopback(tmp_path, announced):
    server = _announcing_server(tmp_path, announced)
    try:
        assert server.url == announced
    finally:
        server.proc.kill()
        server.proc.wait()


@pytest.mark.parametrize("announced", ["http://evil.example:80", "file:///etc/passwd", "https://127.0.0.1:443",
                                       "http://127.0.0.1.evil.example:80", "http://127.0.0.1:80/x"])
def test_a_server_announcing_any_other_address_never_gets_the_password(tmp_path, announced):
    """Ruff S310 review: the client sends the server password to whatever URL the server announces, so the announced
    address must be the loopback server AEW started (http://127.0.0.1:<port>)."""
    from aew.errors import HarnessLaunchFailed

    with pytest.raises(HarnessLaunchFailed, match="not an http://127.0.0.1 address"):
        _announcing_server(tmp_path, announced)


def _announcing_server(tmp_path: Path, url: str) -> Any:
    import subprocess

    from aew.harness.opencode.client import Server

    script = tmp_path / "announce.py"
    script.write_text(f"import json, sys, time\nprint(json.dumps({{'url': {url!r}}}), flush=True)\ntime.sleep(30)\n")

    def spawn(argv: list[str], **kwargs: Any) -> subprocess.Popen[bytes]:
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        return subprocess.Popen([sys.executable, str(script)], **kwargs, **flags)

    return Server.start(spawn, ["opencode"], env={"OPENCODE_PASSWORD": "pw"}, cwd=str(tmp_path),
                        log_path=tmp_path / "server.log", timeout=20)


def test_rules_hold_when_only_denials_follow_aews_rules():
    """E17: AEW's rules in order as one block; anything OpenCode appends after them may only deny."""
    rule, rules_hold = projection.rule, projection.rules_hold
    want = [rule("*", "deny"), rule("read", "allow"), rule("edit", "deny")]
    defaults = [rule("*", "allow"), rule("external_directory", "ask")]
    assert rules_hold(defaults + want, want) is None
    assert rules_hold(defaults + want + [rule("browser", "deny")], want) is None
    assert "widen" in rules_hold(defaults + want + [rule("browser", "allow")], want)
    assert "widen" in rules_hold(defaults + want + [rule("shell", "ask")], want)
    assert "missing" in rules_hold(defaults + [want[1], want[0], want[2]], want)
    assert "missing" in rules_hold(defaults + want[:2], want)


def test_the_uncontained_lead_names_the_way_on_only_when_nothing_gives_it_a_provider(monkeypatch):
    """Review of #340, m2: off Linux the Lead starts as it is, and one start line says why it would have no model when
    no `--provider-env` is passed and no stored login is for a provider its configuration leaves on. A stored login
    for OpenCode's own providers doesn't count: the configuration switches them off. The logins are stand-ins."""
    from aew.harness.opencode import lead, login

    stored: list[login.Login] = []
    monkeypatch.setattr(login, "stored", lambda env: (list(stored), None))
    line = lead.no_provider_line([], {})
    assert line is not None and "(`opencode auth login`)" in line and "`--provider-env NAME`" in line
    assert "https://opencode.ai/docs/zen/" in line
    assert lead.no_provider_line(["OPENAI_API_KEY"], {}) is None
    stored[:] = [login.Login("opencode", "key", "api"), login.Login("opencode-go", "key", "api")]
    assert lead.no_provider_line([], {}) is not None
    stored.append(login.Login("openai", "oauth", "oauth"))
    assert lead.no_provider_line([], {}) is None
