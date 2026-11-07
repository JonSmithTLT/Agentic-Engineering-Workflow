"""The OpenCode adapter against a fake V2 server: what the neutral conformance scenarios cannot reach (the
designer's step-4 watch list, docs/implementation/harness-conformance.md §5).

The fake server (tests/helpers/fake_opencode.py) serves V2's shapes and the real 2.0.18 OpenAPI; knobs make
it behave badly in the ways a real server can: a slow catalog, a missing model or variant, a V1 or doctored
API, a lost event stream, a queued prompt at a turn boundary, a permission request, a form, a crash, a provider that
rejects the key (register V1).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import fake_opencode
import lead_session
import pytest
from aewflow import SUBTRACT_SCOPE, create_planned_ticket, own_scope
from fake_harness import IMPL_REPORT, HarnessLab, credential_hits
from harness_conformance import IMPLEMENT, PROVIDER_SECRET, FakeOpenCodeDriver, evidence_of, sync_dir
from lead_session import KEYS
from proxy_env import RecordingProxy, proxy_env

from aew.harness import contract as K
from aew.harness import runlog, weaker_register
from aew.harness.containment import netns
from aew.harness.opencode import adapter as opencode_adapter
from aew.harness.opencode import projection
from aew.util import dump_yaml, load_yaml

RUN = "R-INV-0001-1"
# The relaunch command the adapter's refusals print for the lab's invocation (#313 review, N1).
RELAUNCH = "`aew harness launch INV-0001 --expect-rev <revision from aew status>`"


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def script(lab: HarnessLab, steps: list[dict[str, Any]], key: str = RUN, **server: Any) -> None:
    lab.script(key, {"steps": steps, "server": server})


def launch(lab: HarnessLab, tmp_path: Path, scope: tuple[str, ...] | None = None) -> tuple[str, str, str]:
    wid = create_planned_ticket(lab.project, tmp_path, **({"scope": scope} if scope else {}))
    out = lab.lead("work", "assign", wid, "--launch")
    return wid, out["invocation"], out["launch"]["run"]


def harness_dir(lab: HarnessLab, run: str = RUN) -> Path:
    return runlog.run_dir(lab.aew_root, run) / "harness"


def fake_db(lab: HarnessLab, run: str = RUN) -> dict[str, Any]:
    return fake_opencode.read_db(harness_dir(lab, run) / "xdg-data" / "opencode" / "fake-db.json")


def events(lab: HarnessLab, run: str = RUN) -> list[dict[str, Any]]:
    """The run's event log so far; a last line still being written is skipped."""
    path = runlog.run_dir(lab.aew_root, run) / "events.jsonl"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return [json.loads(line) for line in text[:text.rfind("\n") + 1].splitlines()]


def refused_launch(lab: HarnessLab, tmp_path: Path, reason_code: str = "incompatible_config") -> str:
    """A launch OpenCode refuses as HARNESS_INCOMPATIBLE, with the closed launch-failure code its record and the
    launcher's error carry (M4-E E8a): `incompatible_config`, or `unknown` for a timing-dependent refusal."""
    wid = create_planned_ticket(lab.project, tmp_path)
    res = lab.lead_res("work", "assign", wid, "--launch")
    assert res.error["code"] == "HARNESS_LAUNCH_FAILED" and "HARNESS_INCOMPATIBLE" in res.error["message"], res.error
    assert (res.error["details"]["reason_code"], res.error["details"]["reason_code_source"]) == (
        reason_code, "acknowledgement"), res.error
    record = lab.record(RUN)
    assert record["status"] == "launch_failed" and record["reason_code"] == reason_code, record
    assert lab.ok("invoke", "show", "INV-0001")["status"] == "active" and not evidence_of(lab, wid)
    return res.error["message"]


# The second of two runs at once: its own change, in a scope disjoint from IMPLEMENT's (the launch conflict check).
SECOND_SCOPE = own_scope(2)
IMPLEMENT_SECOND = [{"do": "write", "files": {SECOND_SCOPE[0]: "def op2():\n    return 2\n"}},
                    {"do": "check", "id": "unit"},
                    {"do": "submit", "kind": "implementation_report",
                     "meta": {**IMPL_REPORT, "implementation": {**IMPL_REPORT["implementation"],
                                                                 "files_changed": [SECOND_SCOPE[0]]}}}]


def two_at_once(lab: HarnessLab) -> None:
    """`mutating_concurrency: 2`: two implementer runs may hold their workspaces at once, given disjoint scopes
    (SUBTRACT_SCOPE for the first, SECOND_SCOPE for the second)."""
    gates = lab.root / ".aew" / "policy" / "gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": 2}),
                     encoding="utf-8", newline="\n")
    lab.project.pin_policy()


# ---------------------------------------------------------------------------------------------- projection


def test_the_projection_reaches_the_server_and_the_session(lab, tmp_path):
    script(lab, IMPLEMENT)
    wid, inv, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    hdir = harness_dir(lab)
    started = json.loads((hdir / "fake-server.json").read_text(encoding="utf-8"))
    config = json.loads((hdir / "opencode-config.json").read_text(encoding="utf-8"))
    assert started["config"] == config
    denied = [projection.rule(a, "deny") for a in projection.ALWAYS_DENIED]
    private = projection.private_output_dirs(os.path.realpath(hdir), os.sep,
                                             scratch=os.path.realpath(hdir.parent / "scratch"))
    # then the run's copy of the skills its card (`engineer`) is offered: readable, never editable (E127)
    at = projection.skills_at(os.path.realpath(hdir), os.sep)
    assert config["permissions"][-9:] == denied + [projection.rule("external_directory", "allow", p) for p in private] \
        + [projection.rule("external_directory", "allow", at.pattern), projection.rule("edit", "deny", at.pattern)]
    assert config["skills"] == [at.folder]
    assert projection.rule("edit", "allow") in config["permissions"]  # an implementer
    assert config["plugins"] == [projection.COMPATIBILITY_PLUGIN] and config["share"] == "disabled"
    # the server's environment: the named provider variable, private state, no project config, and of AEW's only its
    # context's marker (G3 addendum 7; #321 review, F6), which is the path of the run's record, never a credential
    assert "OPENAI_API_KEY" in started["env_names"]
    assert not [n for n in started["env_names"] if n.upper().startswith("AEW_") and n != weaker_register.MARKER]
    marker = Path(started["flags"][weaker_register.MARKER])
    assert marker.name == runlog.RECORD and marker.parent.name == run
    assert started["flags"]["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TEMP"):
        assert Path(started["flags"][name]).resolve().is_relative_to(hdir.resolve())
    workspace = os.path.realpath(lab.ok("invoke", "show", inv)["workspace"])
    assert started["cwd"] == workspace
    [session] = fake_db(lab).values()
    info = session["info"]
    assert info["model"] == {"providerID": "fakeprov", "id": "fake-model", "variant": "high"}
    assert info["location"] == {"directory": workspace} and info["permissions"] == config["permissions"]
    assert info["metadata"] == {"aew_invocation": inv, "aew_run": run, "aew_work_unit": wid}
    record = lab.record(run)
    assert record["launch"]["health"]["version"] == "2.0.18" and record["launch"]["health"]["tested"]
    assert record["result"]["effective"] == [{"provider": "fakeprov", "model": "fake-model", "effort": "high"}]
    assert record["model_check"]["status"] == "match" and record["result"]["prompts"] == 1
    if record["containment"]["network"]["mode"] == "proxy_only":  # Linux (F28 §3.5): the provider through the relay
        relayed = f"http://127.0.0.1:{netns.PROVIDER_PORT}/v1"
        assert config["providers"]["fakeprov"]["settings"] == {"baseURL": relayed, "transport": "http"}
        assert config["providers"]["fakeprov"]["models"]["fake-model"]["settings"] == {"baseURL": relayed}
        assert started["sentinel_names"] == ["OPENAI_API_KEY"]  # the key's variable holds a sentinel, not the key
        assert started["proxy"]["HTTPS_PROXY"] == f"http://127.0.0.1:{netns.EGRESS_PORT}"  # the catalog's egress
        assert started["proxy"]["HTTP_PROXY"] is None and "127.0.0.1" in started["proxy"]["NO_PROXY"].split(",")
        network = record["containment"]["network"]
        assert network["provider_relay"] == "configured" and network["provider_upstream"] == lab.provider.url
        assert network["egress_allow"] == ["models.opencode.ai:443"]
        # the self-test checked the allowlist the run got: one list, built once (register E143)
        assert record["containment"]["self_test"]["rows"]["1"]["egress_allow"] == network["egress_allow"]
        assert set(network["decisions"]) == {"relay", "egress"}  # counted at the run's end
        assert not Path(record["containment"]["layout"]["net_dir"]).exists()  # closed with the run
        # the agent is told its network and how to ask for more (#257's review, F3)
        assert projection.network_text(network) in config["agents"][projection.AGENT]["system"]
    else:
        assert "network of its own" not in config["agents"][projection.AGENT]["system"]


@pytest.mark.parametrize("profile", [{"provider": "fakeprov", "model": "fakeprov/fake-model", "effort": "high"},
                                     {"model": "fakeprov/fake-model", "effort": "high"}])
def test_a_model_id_typed_as_opencode_prints_it_reaches_the_session_undoubled_and_matches(lab, tmp_path, profile):
    """The operator pastes OpenCode's own ``provider/model`` id, with or without the provider beside it: the adapter's
    model identity pins the pair apart, so the session gets ``fakeprov`` and ``fake-model`` (never
    ``fakeprov/fakeprov/fake-model``) and the effective model matches the pin (ADR-0010 amendment 2026-10-11)."""
    path = lab.aew_root / "policy/execution.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    policy["profiles"] = {"standard": profile}
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    lab.project.pin_policy()
    script(lab, IMPLEMENT)
    _, inv, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    pinned = lab.ok("invoke", "show", inv)["execution_profile"]
    assert (pinned["provider"], pinned["model"]) == ("fakeprov", "fake-model")
    [session] = fake_db(lab).values()
    assert session["info"]["model"] == {"providerID": "fakeprov", "id": "fake-model", "variant": "high"}
    assert lab.record(run)["model_check"]["status"] == "match"


def test_tool_calls_are_logged_by_name_never_by_input(lab, tmp_path):
    """V2 names a tool in `session.tool.input.started`; `session.tool.called` carries only the call id and input
    (found live in M3 step 8: the log said `"tool": null`). The run's event log names each call's tool and never
    records its input."""
    script(lab, IMPLEMENT)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    called = [e for e in events(lab) if e["event"] == "opencode.session.tool.called"]
    assert [e.get("tool") for e in called] == ["shell"] * len(IMPLEMENT)
    log = (runlog.run_dir(lab.aew_root, run) / "events.jsonl").read_text(encoding="utf-8")
    assert fake_opencode.TOOL_INPUT not in log
    assert lab.record(run)["result"]["tools_called"] == {"shell": len(IMPLEMENT)}


def test_a_read_only_role_gets_no_edit_and_no_web(lab, tmp_path):
    script(lab, IMPLEMENT)
    wid, inv, run = launch(lab, tmp_path)
    lab.wait(run)
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    script(lab, [], key="R-INV-0002-1")
    review = lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")["launch"]["run"]
    lab.wait(review)
    config = json.loads((harness_dir(lab, review) / "opencode-config.json").read_text(encoding="utf-8"))
    assert projection.rule("edit", "deny") in config["permissions"]
    assert projection.rule("edit", "allow") not in config["permissions"]
    assert projection.rule("webfetch", "allow") not in config["permissions"]
    assert "must not modify any file" in config["agents"][projection.AGENT]["system"]


# ---------------------------------------------------------------------------------------------- health


def test_a_slow_model_catalog_is_waited_for(lab, tmp_path):
    script(lab, IMPLEMENT, catalog_delay_s=3)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    assert lab.record(run)["launch"]["health"]["catalog_wait_s"] >= 2.5


def test_a_launch_behind_a_proxy_runs_and_no_loopback_call_reaches_the_proxy(lab, tmp_path):
    """Every proxy variable set, in both cases, with no NO_PROXY exception for 127.0.0.1: the supervisor's calls to
    the run's own server go direct, so the run ends normally and the proxy (answering 502) sees no connection."""
    with RecordingProxy() as proxy:
        lab.env.update(proxy_env(proxy.url))
        script(lab, IMPLEMENT)
        _, _, run = launch(lab, tmp_path)
        assert lab.wait(run)["status"] == "ended_with_evidence"
    assert (proxy.connections, proxy.request_lines) == (0, [])


def test_a_model_the_harness_does_not_offer_fails_closed(lab, tmp_path):
    """On Linux the relay projection names the pinned model in the server's configuration, so the server lists it even
    though its catalog does not offer it (as 2.0.18 does): the launch still refuses it, and says why it is listed. Its
    next step names both ways on: a new invocation when the pinned model is wrong, since a relaunch reuses the pin
    (ADR-0010; CS-4 addendum 11), and a relaunch when a variable was (#304 review, m1)."""
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"
    script(lab, IMPLEMENT, models=[{"id": "cheaper-model", "providerID": "other", "enabled": True, "variants": []}])
    # Timing-dependent (the catalog's wait ran out), so never a lasting incompatibility (M4-E E8a; PR #185, F1).
    message = refused_launch(lab, tmp_path, reason_code="unknown")
    assert "fakeprov/fake-model is not offered" in message
    relayed = lab.record(RUN)["containment"]["network"]["mode"] == "proxy_only"
    assert ("listed only because AEW names it" in message) == relayed, message
    assert message.endswith(
        "check the execution policy and the provider variables it names; if the pinned model is what is wrong, "
        "dispatch a new invocation with --profile or --model (a relaunch reuses this one's pin, ADR-0010); "
        f"otherwise fix the variable and relaunch with {RELAUNCH}"), message


# -------------------------------------------------------------------- the relay route: the pinned model's family

UPSTREAM = "https://opencode.ai/inference/openai/v1"  # the relay's fixed upstream for `opencode` (netns.UPSTREAMS)
SNAPSHOT = "https://opencode.ai/zen/v1"  # how 2.0.18's embedded catalog snapshot spells Zen (the designer, 2026-11-06)
RELAY_BASE = f"http://127.0.0.1:{netns.PROVIDER_PORT}/inference/openai/v1"  # where the projection points the pin
OPENAI, COMPATIBLE, ANTHROPIC = ("@opencode/ai/providers/openai", "@opencode/ai/providers/openai-compatible",
                                 "@opencode/ai/providers/anthropic")  # 2.0.18's packages (measured 2026-11-06)
MISTRAL = "@opencode/ai/providers/mistral"  # the live catalog's one model of it is served from the upstream


def catalog_model(model_id: str, package: str | None, address: str | None, provider: str = "opencode",
                  ) -> dict[str, Any]:
    """A catalog entry as 2.0.18's /api/model shows it (measured 2026-11-06): family and release time (so not one the
    configuration made up), its package when it has one, and its address when it has one."""
    entry: dict[str, Any] = {"id": model_id, "modelID": model_id, "providerID": provider, "name": model_id.upper(),
                             "family": "f", "time": {"released": 1}, "enabled": True, "variants": []}
    if package:
        entry["package"] = package
    return {**entry, "settings": {"baseURL": address}} if address else entry


def live_catalog(*pinned: dict[str, Any], spelling: str = UPSTREAM) -> list[dict[str, Any]]:
    """The pinned model(s) beside the live catalog's shape: OpenAI-style models served from the upstream, Anthropic
    ones from their own endpoint (2.0.18, 2026-11-06), with the OpenAI-style address spelt as given."""
    return [*pinned, catalog_model("gpt-5-mini", OPENAI, spelling),
            catalog_model("glm-5.3-flash", COMPATIBLE, spelling),
            catalog_model("claude-sonnet-5", ANTHROPIC, "https://opencode.ai/inference/anthropic/v1")]


# Each pinned model as the run's server shows it: its own address replaced by the relay's (projection.relayed).
NANO = catalog_model("gpt-5-nano", OPENAI, RELAY_BASE)
HAIKU = catalog_model("claude-haiku-5-5", ANTHROPIC, RELAY_BASE)


@pytest.mark.parametrize("pinned, catalog, check, upstream_packages", [
    # The pin's own package is among those served from the upstream.
    (NANO, live_catalog(NANO), opencode_adapter.RELAY_FAMILY_MATCHES, [OPENAI, COMPATIBLE]),
    # An Anthropic model behind the OpenAI-style upstream: refused.
    (HAIKU, live_catalog(HAIKU), opencode_adapter.RELAY_FAMILY_MISMATCH, [OPENAI, COMPATIBLE]),
    # The snapshot's spelling: no model is served from the upstream as the relay spells it, so nothing to compare,
    # whichever the pin; never refused on a spelling.
    (NANO, live_catalog(NANO, spelling=SNAPSHOT), opencode_adapter.RELAY_FAMILY_UNVERIFIED, []),
    (HAIKU, live_catalog(HAIKU, spelling=SNAPSHOT), opencode_adapter.RELAY_FAMILY_UNVERIFIED, []),
    # The same address spelt with its case, default port and a trailing slash is the same upstream.
    (HAIKU, [HAIKU, catalog_model("gpt-5-mini", OPENAI, "https://OPENCODE.ai:443/inference/openai/v1/"),
             catalog_model("claude-sonnet-5", ANTHROPIC, "https://opencode.ai/inference/anthropic/v1")],
     opencode_adapter.RELAY_FAMILY_MISMATCH, [OPENAI]),
    # The only model of its package (the live catalog's one mistral model, served from the upstream): its own address
    # is hidden, so nothing decides where it is served, and it is never refused (#338 review, F1).
    (catalog_model("mistral-medium", MISTRAL, RELAY_BASE), live_catalog(catalog_model("mistral-medium", MISTRAL,
                                                                                       RELAY_BASE)),
     opencode_adapter.RELAY_FAMILY_UNVERIFIED, [OPENAI, COMPATIBLE]),
    # Another model of its package served from the upstream: it matches.
    (catalog_model("mistral-medium", MISTRAL, RELAY_BASE),
     live_catalog(catalog_model("mistral-medium", MISTRAL, RELAY_BASE),
                  catalog_model("mistral-small", MISTRAL, UPSTREAM)),
     opencode_adapter.RELAY_FAMILY_MATCHES, [MISTRAL, OPENAI, COMPATIBLE]),
    # Which models are carriers on that branch: never another provider's, never one the configuration made up, and
    # never one with no readable address of its own (none, not an upstream URL, or the relay's provider-level
    # address): each leaves the lone pin unverified (#338 quick check, m1 and m2).
    *[(catalog_model("mistral-medium", MISTRAL, RELAY_BASE),
       live_catalog(catalog_model("mistral-medium", MISTRAL, RELAY_BASE), carrier),
       opencode_adapter.RELAY_FAMILY_UNVERIFIED, [OPENAI, COMPATIBLE])
      for carrier in (catalog_model("mistral-go", MISTRAL, "https://opencode.ai/inference/mistral/v1",
                                    provider="opencode-go"),
                      {**catalog_model("made-up", MISTRAL, "https://opencode.ai/inference/mistral/v1"),
                       "family": None, "time": {}, "name": "made-up"},
                      catalog_model("mistral-small", MISTRAL, None),
                      catalog_model("mistral-small", MISTRAL, "not a url"),
                      catalog_model("mistral-small", MISTRAL, RELAY_BASE))],
    # A stated limit: a package served from two addresses, the pin at the upstream and its only other carrier
    # elsewhere, is refused (the pin's own address is hidden).
    (catalog_model("mistral-medium", MISTRAL, RELAY_BASE),
     live_catalog(catalog_model("mistral-medium", MISTRAL, RELAY_BASE),
                  catalog_model("mistral-small", MISTRAL, "https://opencode.ai/inference/mistral/v1")),
     opencode_adapter.RELAY_FAMILY_MISMATCH, [OPENAI, COMPATIBLE]),
    # Another provider's models, models the configuration made up, and models with no package or no address say
    # nothing of what this provider's upstream serves.
    (HAIKU, [HAIKU, catalog_model("claude-x", ANTHROPIC, UPSTREAM, provider="opencode-go"),
             {**catalog_model("made-up", ANTHROPIC, UPSTREAM), "family": None, "time": {}, "name": "made-up"},
             catalog_model("no-package", None, UPSTREAM), catalog_model("no-address", OPENAI, None)],
     opencode_adapter.RELAY_FAMILY_UNVERIFIED, []),
    # A pin with no package: nothing to compare.
    (catalog_model("gpt-5-nano", None, RELAY_BASE), live_catalog(catalog_model("gpt-5-nano", None, RELAY_BASE)),
     opencode_adapter.RELAY_FAMILY_UNVERIFIED, [OPENAI, COMPATIBLE]),
])
def test_the_relay_route_compares_the_pinned_models_package_with_what_the_upstream_serves(pinned, catalog, check,
                                                                                         upstream_packages):
    """The pin's family is its own catalog package (2.0.18 keeps it on the relay route: measured 2026-11-06); what the
    relay's one upstream serves is read from the same catalog's models served from it. The catalog changes under
    the same pins: live, then the snapshot's spelling."""
    found = opencode_adapter.relay_family(pinned, catalog, UPSTREAM)
    assert found == {"check": check, "package": pinned.get("package"), "upstream_packages": upstream_packages}, found


def fake_sibling(model_id: str, package: str, address: str) -> dict[str, Any]:
    return {"id": model_id, "modelID": model_id, "providerID": "fakeprov", "name": model_id.title(), "family": "fake",
            "time": {"released": 1}, "enabled": True, "variants": [], "package": package,
            "settings": {"baseURL": address}}


def relay_catalog(lab: HarnessLab, sibling_package: str | None, cousin_elsewhere: bool = False) -> None:
    """The fake server's catalog: the pinned fake model (package fake-pkg); when given, a sibling of the same provider
    served from the relay's upstream with ``sibling_package``; and with ``cousin_elsewhere``, another fake-pkg model
    served somewhere else. The server shows each address as 2.0.18 does (fake_opencode.FakeServer.models)."""
    pinned = {**fake_opencode.DEFAULT_MODELS[0], "family": "fake", "time": {"released": 1}, "package": "fake-pkg"}
    models = [pinned]
    if sibling_package:
        models.append(fake_sibling("fake-sibling", sibling_package, lab.provider.url))
    if cousin_elsewhere:
        models.append(fake_sibling("fake-cousin", "fake-pkg", "https://elsewhere.invalid/v1"))
    script(lab, IMPLEMENT, models=models)


def test_on_the_relay_route_a_model_of_a_family_the_upstream_does_not_serve_is_refused_at_launch(lab, tmp_path):
    """The relay's upstream serves another family, so the model's requests would go to an endpoint that does not
    serve them: refused before the first prompt, naming both families, the upstream, and both ways on. Without a
    relay (no network of the run's own) the model is called at its own address, so the check does not apply."""
    relay_catalog(lab, "other-pkg", cousin_elsewhere=True)
    wid = create_planned_ticket(lab.project, tmp_path)
    res = lab.lead_res("work", "assign", wid, "--launch")
    if lab.record(RUN)["containment"]["network"]["mode"] != "proxy_only":
        assert res.returncode == 0, res.error
        assert lab.wait(RUN)["status"] == "ended_with_evidence"
        assert "relay_family" not in lab.record(RUN)["launch"]["health"]
        return
    assert res.error["code"] == "HARNESS_LAUNCH_FAILED" and "HARNESS_INCOMPATIBLE" in res.error["message"], res.error
    assert res.error["details"]["reason_code"] == "incompatible_config", res.error
    # the adapter's own reason, carried by the supervisor's acknowledgement and kept on the record (register E143)
    assert res.error["details"]["refusal"] == "relay_family_mismatch", res.error
    assert lab.record(RUN)["refusal"] == "relay_family_mismatch"
    message = res.error["message"]
    assert (f"model fakeprov/fake-model is a fake-pkg model, but the run's provider relay sends only to "
            f"{lab.provider.url}, which this OpenCode's catalog serves other-pkg models from, so its requests would "
            "go to an endpoint that does not serve them; dispatch a new invocation with --profile or --model naming a "
            "model of a family it serves (other-pkg), or the operator sets containment.network.upstreams.fakeprov to "
            f"an address that serves fake-pkg models and relaunches with {RELAUNCH}") in message, message
    assert lab.record(RUN)["status"] == "launch_failed"
    assert lab.provider.seen == [], "no model call was made"


@pytest.mark.parametrize("sibling, check, upstream_packages", [
    ("fake-pkg", "matches", ["fake-pkg"]),
    # Only other-pkg is served from the upstream, and no other model carries fake-pkg: the pin may be what serves it
    # there (its own address is hidden), so nothing decides, and it launches (#338 review, F1).
    ("other-pkg", "unverified", ["other-pkg"]),
    (None, "unverified", []),
])
def test_on_the_relay_route_the_family_check_is_recorded_and_the_run_goes_ahead(lab, tmp_path, sibling, check,
                                                                                upstream_packages):
    """A sibling of the pin's family served from the relay's upstream: `matches`. Nothing to decide by: `unverified`,
    which launches all the same. Either way the launch record keeps what was found, and the launch's output and the
    run's network label show the check, beside the status (register E143)."""
    relay_catalog(lab, sibling)
    wid = create_planned_ticket(lab.project, tmp_path)
    started = lab.lead("work", "assign", wid, "--launch")["launch"]
    run = started["run"]
    assert lab.wait(run)["status"] == "ended_with_evidence"
    record = lab.record(run)
    if record["containment"]["network"]["mode"] != "proxy_only":
        assert "relay_family" not in record["launch"]["health"] and "relay_family" not in started
        assert "relay_family" not in record["containment"]["network"]
        return
    assert record["launch"]["health"]["relay_family"] == {
        "check": check, "package": "fake-pkg", "upstream_packages": upstream_packages}
    assert started["status"] == "running" and started["relay_family"] == check, started
    assert record["containment"]["network"]["relay_family"] == check


def test_on_linux_a_provider_key_that_would_reach_the_sandbox_another_way_refuses_the_launch(lab, tmp_path):
    """F28 §3.6, row 6: in a run's own network the key's variable holds a sentinel; the same value in any other
    variable the server is given (here a locale variable) would put the key in the sandbox, so the server is not
    started, and the refusal names the provider variable, never the value. Elsewhere there is no relay, and the run
    goes on as before."""
    lab.env["LC_AEW_TEST"] = PROVIDER_SECRET
    script(lab, IMPLEMENT)
    if not sys.platform.startswith("linux"):
        _, _, run = launch(lab, tmp_path)
        assert lab.wait(run)["status"] == "ended_with_evidence"
        return
    message = refused_launch(lab, tmp_path)
    assert "the value of OPENAI_API_KEY would reach the run's sandbox" in message and PROVIDER_SECRET not in message


def test_a_missing_effort_variant_fails_closed(lab, tmp_path):
    """The effort is in the pin, so only a new invocation changes it (ADR-0010; #304 review, m1)."""
    script(lab, IMPLEMENT, models=[{"id": "fake-model", "providerID": "fakeprov", "enabled": True,
                                    "variants": [{"id": "low"}]}])
    message = refused_launch(lab, tmp_path)
    assert "no variant 'high'" in message
    assert message.endswith(
        "; dispatch a new invocation with --profile or --model, or with another --effort (a relaunch reuses this "
        f"one's pin, ADR-0010); once OpenCode offers the variant, relaunch with {RELAUNCH}"), message


def test_a_disabled_model_fails_closed_and_names_both_ways_on(lab, tmp_path):
    """A model the server lists but has disabled: the operator enables it and relaunches, or the Lead dispatches a new
    invocation with another model (#304 review, m1)."""
    script(lab, IMPLEMENT, models=[{"id": "fake-model", "providerID": "fakeprov", "enabled": False,
                                    "variants": [{"id": "high"}]}])
    message = refused_launch(lab, tmp_path)
    assert ("fakeprov/fake-model is disabled in this OpenCode; enable it in OpenCode and relaunch with "
            f"{RELAUNCH}, or dispatch a new invocation with --profile or --model") in message, message
    assert message.endswith("or --model"), message


@pytest.mark.parametrize("knobs, expected", [
    ({"version": "1.18.32"}, "is not a V2 server"),
    ({"openapi_drop": ["POST /api/session/{sessionID}/interrupt"]},
     "operation POST /api/session/{sessionID}/interrupt is missing"),
    ({"ignore_config": True}, "did not load AEW's agent"),
    ({"agent_override": {"steps": 5}}, "with a different step limit"),
    ({"agent_override": {"model": {"providerID": "other", "id": "cheaper-model", "variant": "default"}}},
     "with a different model"),
    ({"agent_override": {"permissions": [{"action": "*", "resource": "*", "effect": "allow"}]}},
     "with a different permissions"),
    ({"appended_rules": [{"action": "browser", "resource": "*", "effect": "allow"}]},
     "with a different permissions"),
    ({"appended_rules": [{"action": "shell", "resource": "*", "effect": "ask"}]},
     "with a different permissions"),
], ids=["v1-server", "doctored-openapi", "config-ignored", "steps-differ", "model-differs", "rules-differ",
        "appended-allow", "appended-ask"])
def test_an_incompatible_server_fails_closed(lab, tmp_path, knobs, expected):
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"
    script(lab, IMPLEMENT, **knobs)
    # An ignored configuration is found only when the agent wait runs out, which a slow server also does: `unknown`
    # (M4-E E8a; PR #185 review, F3). The other refusals are decided on what the server reported.
    code = "unknown" if knobs.get("ignore_config") else "incompatible_config"
    assert expected in refused_launch(lab, tmp_path, reason_code=code)


def test_a_server_that_lists_no_agent_within_the_wait_is_not_an_incompatibility(lab, tmp_path):
    """A slow server: no agent at all appears within the agent wait. The launch fails closed, as before, but its
    code is `unknown` (`launch_cause: agent_load_timeout`), never `incompatible_config` (PR #185 review, F3)."""
    lab.env["AEW_OPENCODE_CATALOG_S"] = "2"
    script(lab, IMPLEMENT, agents_delay_s=60)
    assert "did not load AEW's agent" in refused_launch(lab, tmp_path, reason_code="unknown")


def test_a_denial_the_server_appends_after_aews_rules_is_accepted(lab, tmp_path):
    """E17: OpenCode 2.0.22 appends a default `browser: deny` after AEW's rules. It can only narrow access, so the
    projection still holds and the run proceeds."""
    script(lab, IMPLEMENT, appended_rules=[{"action": "browser", "resource": "*", "effect": "deny"}])
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"


def test_a_run_server_with_stored_credentials_is_refused(lab, tmp_path):
    """E17: 2.0.22 serves stored integration credentials, values included, and the agent can reach its server. A run's
    server state starts empty; AEW proves it at launch, and refuses a server that holds any."""
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"
    script(lab, IMPLEMENT, stored_credentials=[{"id": "github", "type": "oauth", "access": "gho_example"}])
    assert "holds 1 stored credential" in refused_launch(lab, tmp_path)


def test_an_empty_credential_store_is_recorded(lab, tmp_path):
    script(lab, IMPLEMENT, stored_credentials=[])
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    assert lab.record(run)["launch"]["health"]["stored_credentials"] == 0


# ---------------------------------------------------------------------------------------------- completion


def test_losing_the_event_stream_changes_nothing(lab, tmp_path):
    """Every event connection closes after its first frame: completion is still decided correctly (by polling)."""
    script(lab, IMPLEMENT, drop_events_every=1)
    wid, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    record = lab.record(run)
    assert record["result"]["events_dropped"] >= 1
    assert {e["kind"] for e in evidence_of(lab, wid, run)} >= {"implementation_report"}


def test_a_queue_input_at_the_turn_boundary_is_answered_before_the_run_ends(lab, tmp_path):
    """The server goes idle while a prompt AEW queued during the turn is still undelivered, then starts it: the run
    must not be declared over in between. Since `harness send` posts `steer` (register E55), the `queue` input is
    reached at the adapter level, through `adapter.send(text, "queue")` (F9-A plan v4 amendment 2 §4)."""
    helper = Path(fake_opencode.__file__).resolve().parent / "opencode_queue_send.py"
    lab.env["AEW_HARNESS_ADAPTERS"] += f";opencode={helper}:QueueSendOpenCodeAdapter"
    sync = sync_dir(tmp_path)
    script(lab, [{"do": "touch", "path": str(sync / "ready")}, {"do": "wait_file", "path": str(sync / "go")}],
           idle_before_queue_s=3)
    _, _, run = launch(lab, tmp_path)
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    lab.ok("harness", "send", run, "--text", "Also note the changed files.", env={"AEW_LEAD_TOKEN": lab.project.token})
    lab.until(lambda: any(e["event"] == "opencode.prompt" and e["delivery"] == "queue" for e in events(lab)),
              what="the message queued")
    (sync / "go").write_text("x")
    assert lab.wait(run)["status"] == "ended_without_evidence"
    [session] = fake_db(lab).values()
    users = [m for m in session["messages"] if m["type"] == "user"]
    assert users[-1]["text"] == "Also note the changed files."
    assert session["messages"][-1]["type"] == "idle" and session["messages"][-2]["type"] == "assistant"
    assert lab.record(run)["result"]["prompts"] == 2


def test_a_lead_interrupt_holds_the_session_until_send(lab, tmp_path):
    sync = sync_dir(tmp_path)
    script(lab, [{"do": "touch", "path": str(sync / "ready")}, {"do": "hang"}])
    _, _, run = launch(lab, tmp_path)
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    lab.ok("harness", "interrupt", run, env={"AEW_LEAD_TOKEN": lab.project.token})
    lab.until(lambda: any(e["event"] == "opencode.held" for e in events(lab)), what="the session held")
    assert lab.ok("harness", "status")["runs"][0]["status"] == "running"
    lab.ok("harness", "send", run, "--text", "Continue and finish.", env={"AEW_LEAD_TOKEN": lab.project.token})
    assert lab.wait(run)["status"] == "ended_without_evidence"
    kinds = [t.get("kind") for t in lab.record(run)["timeline"] if t["event"] == "request"]
    assert kinds == ["interrupt", "send"]
    # `steer` with the default resume still wakes the held session (F9-A plan v4 amendment 2 §4)
    [session] = fake_db(lab).values()
    assert session["prompts"][-1]["delivery"] == "steer"


# ---------------------------------------------------------------------------------------------- the unexpected


def test_a_permission_request_is_rejected_and_recorded(lab, tmp_path):
    script(lab, IMPLEMENT, ask=True)
    wid, _, run = launch(lab, tmp_path)
    done = lab.wait(run)
    record = lab.record(run)
    assert done["status"] == "crashed" and "interrupted" in record["harness_outcome"]
    assert record["result"]["permission_rejected"] == [{"action": "shell", "resources": ["rm -rf /"]}]
    assert not evidence_of(lab, wid)


def test_a_subagent_session_is_never_invisible(lab, tmp_path):
    """Brief attack 7: `subagent` is denied, and a session started anyway (by the model or anything else) is recorded
    on the run and shown by `aew harness status`: nothing runs for the invocation unseen."""
    script(lab, IMPLEMENT, subagent=True)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    [child] = lab.record(run)["result"]["foreign_sessions"]
    assert child != lab.record(run)["launch"]["session"]
    assert lab.ok("harness", "status")["runs"][0]["foreign_sessions"] == [child]


def test_a_form_is_cancelled_and_the_run_continues(lab, tmp_path):
    script(lab, IMPLEMENT, form=True)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    assert len(lab.record(run)["result"]["forms_cancelled"]) == 1


def test_the_server_dying_mid_run_is_a_crash(lab, tmp_path):
    sync = sync_dir(tmp_path)
    script(lab, [{"do": "touch", "path": str(sync / "ready")}, {"do": "wait_file", "path": str(sync / "go")},
                 {"do": "exit", "code": 9}])
    _, inv, run = launch(lab, tmp_path)
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    rev = lab.project.rev()
    (sync / "go").write_text("x")
    done = lab.wait(run)
    assert done["status"] == "crashed"
    record = lab.record(run)
    assert record["exit_code"] == 9 and "server exited (9)" in record["harness_outcome"]
    # the outcome reaches the reason the Lead is shown, by `harness wait` and by `harness status` (PR #310, F4)
    outcome = "; harness outcome: the OpenCode server exited (9) during the run"
    assert outcome in done["reason"]
    [row] = lab.ok("harness", "status", inv)["runs"]
    assert row["reason"] == done["reason"]
    assert lab.project.rev() == rev and lab.ok("invoke", "show", inv)["status"] == "active"


def test_a_rejected_provider_key_is_its_own_ending_and_a_relaunch_reads_the_key_again(lab, tmp_path):
    """Register V1: a daily key expired mid-run. The provider's 401 fails the turn (2.0.18: `provider.auth`, no
    retry); the run ends `crashed` with `reason_code: provider_auth_failed`, and `harness status`, `harness wait` and
    the next action say what to do, naming the variable, never its value. A relaunch starts a new server whose
    environment is built from the launcher's at launch, so it runs with the key as it is now."""
    expired, fresh = PROVIDER_SECRET, "sk-fresh-key-after-rotation-must-not-be-recorded"
    rejected = hashlib.sha256(expired.encode()).hexdigest()
    # one script for every run of the invocation: only the key in the launcher's environment differs
    script(lab, IMPLEMENT, key="INV-0001",
           provider_auth={"variable": "OPENAI_API_KEY", "rejected_sha256": [rejected]})
    wid, inv, run = launch(lab, tmp_path)
    rev = lab.project.rev()
    done = lab.wait(run)
    assert done["status"] == "crashed" and done["reason_code"] == "provider_auth_failed", done
    assert done["headline"].startswith(f"{run} FAILED: the model provider rejected the credential"), done
    assert done["reason"].startswith("provider_auth_failed:") and "OPENAI_API_KEY" in done["reason"], done
    action = done["next_action"]
    assert "rejected the credential" in action and "OPENAI_API_KEY" in action and "provider_env" in action, action
    assert f"aew harness launch {inv}" in action and "restart `aew opencode`" in action, action
    record = lab.record(run)
    assert record["reason_code"] == "provider_auth_failed" and record["exit_code"] == 1
    assert record["harness_outcome"] == "the agent's turn ended: failed (provider.auth, 401)"
    [row] = lab.ok("harness", "status")["runs"]
    assert row["reason_code"] == "provider_auth_failed" and row["reason"] == done["reason"]
    # the wait's step is the run's next action as `aew status` gives it, then the line for the operator (E122)
    tell = K.run_ended_step("")
    assert action.endswith(tell) and any(action[:-len(tell)] in a for a in lab.ok("status", "--json")["next_actions"])
    failed = [e for e in events(lab) if e["event"] == "opencode.session.execution.failed"]
    assert failed and all(e["error"] == {"type": "provider.auth", "status": 401} for e in failed), failed
    assert lab.project.rev() == rev and lab.ok("invoke", "show", inv)["status"] == "active"
    assert not evidence_of(lab, wid)

    # The operator rotates the key; the relaunch's server is given it, and the same script now runs through.
    lab.lead("harness", "launch", inv, env={"OPENAI_API_KEY": fresh})
    again = lab.wait("R-INV-0001-2")
    assert again["status"] == "ended_with_evidence" and "reason_code" not in again, again
    assert "reason_code" not in lab.record("R-INV-0001-2")
    if record["containment"]["network"]["mode"] == "proxy_only":  # Linux (F28): the server held a sentinel, and the
        # relay gave the provider each key in its place, the one the launch read
        assert list(dict.fromkeys(lab.provider.seen)) == [hashlib.sha256(k.encode()).hexdigest()
                                                         for k in (expired, fresh)]
        assert record["containment"]["network"]["decisions"]["relay"].get("allowed", 0) >= 1
    # Neither key, nor the provider's message quoting part of one, is in anything AEW wrote, its server log (the
    # harness's stderr) included: only the variable's name. OpenCode's own private state (its XDG directories, with
    # its database) keeps what the provider said.
    for directory in (runlog.run_dir(lab.aew_root, run), runlog.run_dir(lab.aew_root, "R-INV-0001-2")):
        for path in directory.rglob("*"):
            parts = path.relative_to(directory).parts
            if path.is_file() and not any(part.startswith("xdg-") for part in parts):
                text = path.read_text(encoding="utf-8", errors="replace")
                for secret in (expired, fresh, f"{expired[:3]}***{expired[-4:]}", "Incorrect API key"):
                    assert secret not in text, (path, secret)


def test_a_credential_error_loses_its_message_and_key_shaped_text_is_redacted_from_any_other():
    """Fail closed (PR #165 review, finding 2): the message goes for an auth-like type or a 401, 403 or 407 whatever
    the type says, and key-shaped text is redacted from every message kept. Only `provider.auth` has a reason code."""
    from aew.harness.opencode.adapter import REASON_CODES, describe_error, error_view

    bad = {"type": "provider.invalid-request", "message": "max_tokens is too large", "status": 400}
    assert error_view(bad) == bad and bad["type"] not in REASON_CODES
    assert describe_error(error_view(bad)) == "provider.invalid-request, 400: max_tokens is too large"
    auth = {"type": "provider.auth", "message": "Incorrect API key provided: sk-ab***wxyz.", "status": 401}
    assert error_view(auth) == {"type": "provider.auth", "status": 401}
    assert describe_error(error_view(auth)) == "provider.auth, 401"
    assert REASON_CODES == {"provider.auth": "provider_auth_failed"}
    for status in (401, 403, 407):  # another classification of a rejected credential
        other = {"type": "unknown", "message": "Incorrect API key provided: sk-ab***wxyz.", "status": status}
        assert error_view(other) == {"type": "unknown", "status": status}
    assert error_view({"type": "provider.Authentication", "message": "denied: sk-ab***wxyz"}) == {
        "type": "provider.Authentication"}
    leaky = {"type": "provider.internal", "status": 500,
             "message": "upstream said: key sk-proj-abc***wxyz bad, Bearer eyJhbGciOi.x.y, masked ab****cd, "
                        "token Zx9Qk2Lm7Np4Rs8Tv1Wy6Bc3Df5Gh0Jk2Mn4Pq6R"}
    kept = error_view(leaky)["message"]
    for fragment in ("sk-proj", "wxyz", "eyJhbGciOi", "ab****cd", "Zx9Qk2Lm7Np4Rs8Tv1Wy6Bc3Df5Gh0Jk2Mn4Pq6R"):
        assert fragment not in kept, kept
    assert kept.startswith("upstream said: key <redacted> bad, <redacted>"), kept
    # what a non-credential error is diagnosed from stays; a mixed-case 40-character token (above) goes (re-review 1)
    for diagnostic in ("openai/gpt-5.1-codex-max-2025-11-20-preview-extended",  # a model id
                       "4f0a7101c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7",  # a git sha
                       "3f2c9a1e-8b7d-4c6e-9f00-112233445566",  # a UUID
                       "req_0123456789abcdef0123456789abcdef",  # a request id
                       "src/aew/harness/opencode/a_really_long_module_name_for_testing.py"):  # a long path
        message = f"failed on {diagnostic} (rate limit)"
        assert error_view({"type": "provider.api", "status": 400, "message": message})["message"] == message


def test_a_failed_turn_is_classified_from_the_event_when_the_messages_lack_the_error(tmp_path):
    """The messages are the source; `session.execution.failed` is the fallback, for this execution only."""
    from aew.harness.opencode.adapter import OpenCodeAdapter

    def ended(frames: list[dict[str, Any]], *, assistant: list[dict[str, Any]] | None = None,
              outcome: str = "failed") -> dict[str, Any]:
        logged: list[dict[str, Any]] = []
        adapter = OpenCodeAdapter(None, tmp_path, logged.append)  # type: ignore[arg-type]  # no process is started
        adapter.session, adapter.sent, adapter.turn = "ses_1", ["msg_1"], "running"
        adapter._take_snapshot = lambda: None  # type: ignore[method-assign]
        adapter.snapshot = {"assistant": assistant if assistant is not None else [{"error": None, "created": 200.0}]}
        for frame in frames:
            adapter._on_event({"data": {"sessionID": "ses_1", **frame.pop("data", {})}, **frame})
        adapter._turn_over(outcome, "msg_1", 100.0)  # the last prompt was delivered at 100
        assert all("Incorrect" not in str(e) for e in logged), logged
        return adapter.inspect()

    auth = {"type": "provider.auth", "message": "Incorrect API key provided: sk-ab***wxyz.", "status": 401}
    out = ended([{"type": "session.execution.started"}, {"type": "session.execution.failed", "data": {"error": auth}}])
    assert out["reason_code"] == "provider_auth_failed" and out["exit_code"] == 1
    assert out["detail"] == "the agent's turn ended: failed (provider.auth, 401)"
    # an earlier execution's failure is not this one's
    out = ended([{"type": "session.execution.failed", "data": {"error": auth}}, {"type": "session.execution.started"}])
    assert out["reason_code"] is None and out["detail"] == "the agent's turn ended: failed"
    # an earlier turn's message error is not this turn's: the current execution's failure wins (review, finding 4)
    stale = [{"error": {"type": "provider.auth", "status": 401}, "created": 50.0}, {"error": None, "created": 200.0}]
    other = {"type": "provider.internal", "message": "overloaded", "status": 500}
    out = ended([{"type": "session.execution.started"}, {"type": "session.execution.failed", "data": {"error": other}}],
                assistant=stale)
    assert out["reason_code"] is None, out
    assert out["detail"] == "the agent's turn ended: failed (provider.internal, 500: overloaded)", out
    # and a turn that did not fail never gets a reason code, whatever an earlier message said
    out = ended([], assistant=[{"error": {"type": "provider.auth", "status": 401}, "created": 150.0}],
                outcome="succeeded")
    assert out["reason_code"] is None and out["exit_code"] == 0, out


def test_a_drifted_policy_never_breaks_the_reads_of_an_auth_failed_run(lab, tmp_path):
    """PR #165 review, finding 1: editing the execution policy (to name another key variable, say) is a natural fix,
    and leaves it unadopted for a while. `aew status` and `aew harness wait` still answer, and the next action names
    the variables the run was launched with."""
    script(lab, IMPLEMENT, key="INV-0001", provider_auth={
        "variable": "OPENAI_API_KEY", "rejected_sha256": [hashlib.sha256(PROVIDER_SECRET.encode()).hexdigest()]})
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["reason_code"] == "provider_auth_failed"
    path = lab.root / ".aew" / "policy" / "execution.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "\n# operator edit, not yet adopted\n", encoding="utf-8")
    status = lab.aew("status", "--json")
    assert status.returncode == 0, status.stderr
    waited = lab.aew("harness", "wait", run, "--timeout", "5")
    assert waited.returncode == 0, waited.stderr
    assert "OPENAI_API_KEY" in waited.json["next_action"] and "rejected the credential" in waited.json["next_action"]


# ---------------------------------------------------------------------------------------------- Lead requests


def test_send_refuses_a_credential_and_a_run_that_is_not_running(lab, tmp_path):
    script(lab, [{"do": "exit", "code": 0}])
    _, _, run = launch(lab, tmp_path)
    lab.wait(run)
    res = lab.aew("harness", "send", run, "--text", f"use {lab.project.token}",
                  env={"AEW_LEAD_TOKEN": lab.project.token})
    assert res.error["code"] == "USAGE" and lab.project.token not in res.stderr
    res = lab.aew("harness", "send", run, "--text", "hello", env={"AEW_LEAD_TOKEN": lab.project.token})
    assert res.error["code"] == "ILLEGAL_TRANSITION"


def test_harness_config_prints_the_projection_without_secrets(lab, tmp_path):
    script(lab, IMPLEMENT)
    _, inv, run = launch(lab, tmp_path)
    lab.wait(run)
    out = lab.aew("harness", "config", "opencode", inv)
    assert out.returncode == 0 and PROVIDER_SECRET not in out.stdout and not credential_hits(tmp_path)
    shown = out.json
    used = json.loads((harness_dir(lab) / "opencode-config.json").read_text(encoding="utf-8"))
    assert shown["for_run"] == "R-INV-0001-2"  # the next run: the same rules, its own private output directories
    # The run's own private output directories and scratch directory come last, then its copy of the skills its card
    # (`engineer`, the default) is offered: readable and never editable (E127).
    assert shown["config"]["permissions"][:-6] == used["permissions"][:-6]
    assert all("R-INV-0001-2" in r["resource"] for r in shown["config"]["permissions"][-6:])
    assert [r["action"] for r in shown["config"]["permissions"][-2:]] == ["external_directory", "edit"]
    ran = lab.record("R-INV-0001-1")["launch"]["skills"]  # one plan: what the run got is what config shows
    assert ran["copy"] in ("read_only_bind", "rules_only") and {k: v for k, v in ran.items() if k != "copy"} == shown[
        "skills"]
    assert shown["skills"]["exposed"] == ["c-development", "python-development"] == sorted(
        p.name for p in (harness_dir(lab) / "skills").iterdir())
    assert shown["session"]["model"] == {"providerID": "fakeprov", "id": "fake-model", "variant": "high"}
    assert shown["server_env"]["provider_variables"] == ["OPENAI_API_KEY"]
    lead = lab.ok("harness", "config", "opencode", "--lead")
    from aew.engine.api import Engine
    from aew.surface import lead_text

    assert lead["config"] == projection.lead_config(lead_text.guide_for(Engine.discover(lab.root)))
    assert "OPENAI_API_KEY" not in lead["env_names"] and "AEW_LEAD_TOKEN" not in lead["env_names"]


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="/proc: Linux only")
def test_residual_the_harness_servers_environment_is_readable_from_the_agents_shell(lab, tmp_path):
    """ADR-0009 residual (independent review, area 2, F3; ST-38, STG-05 CS-4), asserted as it is rather than as hoped.
    The agent's own environment carries no provider secret and no server password, but the harness server is its
    shell's parent, runs as the same user and in the same PID namespace: its environment is one read of
    /proc/<parent>/environ away. On a run with its own network, what is there is the provider variable's sentinel,
    never the key's value (the relay outside holds that), and the server's password, which is new per launch and
    opens only that run's server (the next test). No AEW credential is ever there. The Lead's session has the same
    shape (tests/integration/test_lead_contained_session.py). This test fails the day it stops being true, so the
    ADR is updated with it."""
    script(lab, [{"do": "read_parent_environ", "pid": "ppid", "names": ["OPENAI_API_KEY", "OPENCODE_PASSWORD"],
                  "forbid_sha256": [hashlib.sha256(PROVIDER_SECRET.encode()).hexdigest()]}])
    launch(lab, tmp_path)
    lab.wait(RUN)
    parent = lab.step(RUN, 0)
    assert parent["readable"] is True, parent
    assert lab.record(RUN)["containment"]["network"]["mode"] == "proxy_only"  # a run with its own network
    assert parent["names_present"] == ["OPENAI_API_KEY", "OPENCODE_PASSWORD"], parent
    assert parent["sentinel_names"] == ["OPENAI_API_KEY"] and parent["forbidden_present"] is False, parent
    assert parent["has_credential"] is False and parent["has_lead_var"] is False
    # The Lead's session: its TUI's parent is the shim, whose environment is the TUI's. Each stored provider's
    # variable holds its relay's sentinel; opencode's key is not relayed, so it is not there at all.
    _, steps = lead_session.agent_session(tmp_path / "lead", [
        {"do": "read_parent_environ", "pid": "ppid", "names": sorted(netns.PROVIDER_KEY_ENV.values()),
         "forbid_sha256": [hashlib.sha256(v.encode()).hexdigest() for v in (*KEYS.values(), lead_session.SECRET)]}],
        logins=KEYS)
    shim = steps[0]
    assert shim["readable"] is True, shim
    assert shim["names_present"] == shim["sentinel_names"] == ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"], shim
    assert shim["forbidden_present"] is False and shim["has_credential"] is False and shim["has_lead_var"] is False


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="/proc: Linux only")
def test_a_servers_password_is_new_per_launch_and_never_written_outside_its_run_directory(lab, tmp_path):
    """ST-38 (STG-05 CS-4): the password in the server's environment (the residual above) is drawn per launch, so the
    one an agent reads opens only its own run's server, and no file outside that run's directory holds it. The agent
    copies what it read into its run's own directory so the scan has something to look for; the password itself never
    reaches this test's output."""
    two_at_once(lab)
    runs = []
    for run, scope, steps in (("R-INV-0001-1", SUBTRACT_SCOPE, IMPLEMENT),
                              ("R-INV-0002-1", SECOND_SCOPE, IMPLEMENT_SECOND)):
        saved = harness_dir(lab, run) / "seen-password"  # the run's harness state: writable inside, and its own
        script(lab, [{"do": "read_parent_environ", "pid": "ppid", "names": ["OPENCODE_PASSWORD"],
                      "save_name": "OPENCODE_PASSWORD", "save_to": str(saved)}, *steps], key=run)
        assert launch(lab, tmp_path, scope)[2] == run
        lab.wait(run)
        assert lab.step(run, 0)["names_present"] == ["OPENCODE_PASSWORD"]
        runs.append((run, saved.read_text(encoding="utf-8")))
    (_, first), (_, second) = runs
    assert len(first) >= 32 and first != second  # drawn per launch
    for run, password in runs:
        own = runlog.run_dir(lab.aew_root, run)
        hits = [p for p in tmp_path.rglob("*") if p.is_file() and own not in p.parents
                and password.encode() in p.read_bytes()]
        assert hits == [], f"{run}'s server password is in {len(hits)} file(s) outside its run directory"


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="a run's own network: Linux only")
def test_no_context_reaches_another_runs_server_socket_or_loopback_port(lab, tmp_path):
    """ST-38 (STG-05 CS-4): no context but a run's own supervisor reaches its server, so the password opens nothing
    else. Run A holds while run B, and then the Lead's session, try A's server socket (in A's network directory under
    the host's /tmp, which every sandbox replaces with its own) and a loopback port on the host. Each sandbox's
    loopback is its own network namespace's: A's server port there is A's alone, and in the Lead's, which has no
    server leg, nothing listens at it. Every connect fails; from the host, A's socket answers (a live run's)."""
    import glob
    import socket
    import time

    two_at_once(lab)
    a, b = "R-INV-0001-1", "R-INV-0002-1"
    ready, go = harness_dir(lab, a) / "ready", harness_dir(lab, a) / "go"
    script(lab, [{"do": "wait_file", "path": str(go), "ready": str(ready), "timeout": 300}, *IMPLEMENT], key=a)
    host = socket.create_server(("127.0.0.1", 0))  # any service on the host's loopback
    port = host.getsockname()[1]
    before = set(glob.glob("/tmp/aew-net-*"))  # noqa: S108  # where netns.private_dir makes them
    try:
        assert launch(lab, tmp_path, SUBTRACT_SCOPE)[2] == a
        deadline = time.monotonic() + 120
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), lab.record(a)
        servers = sorted(p for p in (os.path.join(d, netns.SERVER) for d in set(glob.glob("/tmp/aew-net-*")) - before)
                         if os.path.exists(p))  # A's, and any other run's that started meanwhile
        live = []
        for path in servers:
            with socket.socket(socket.AF_UNIX) as probe:  # pyright: ignore[reportAttributeAccessIssue]
                live.append(probe.connect_ex(path) == 0)
        assert any(live), servers
        tries = [*({"do": "connect", "unix": p} for p in servers), {"do": "connect", "tcp": ["127.0.0.1", port]}]
        script(lab, [*tries, *IMPLEMENT_SECOND], key=b)
        assert launch(lab, tmp_path, SECOND_SCOPE)[2] == b
        lab.wait(b)
        from_run = [lab.step(b, i) for i in range(len(tries))]
        _, steps = lead_session.agent_session(tmp_path / "lead", [
            *tries, {"do": "connect", "tcp": ["127.0.0.1", netns.SERVER_PORT]}])
        from_lead = [steps[i] for i in range(len(tries) + 1)]
    finally:
        go.write_text("x", encoding="utf-8")
        host.close()
    lab.wait(a)
    refused = [{"connected": False, "error": "ENOENT"}] * len(servers) + [{"connected": False, "error": "ECONNREFUSED"}]
    assert from_run == refused, from_run
    assert from_lead == [*refused, {"connected": False, "error": "ECONNREFUSED"}], from_lead


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="containment: Linux only")
def test_no_route_closing_control_is_a_harness_permission_rule(lab, tmp_path):
    """ST-38 (STG-05 CS-4): nothing AEW relies on for the four routes (a G3 approval, an owner's fact, a credential
    beyond the run, a way out) is a harness permission rule. The fake server here, and the Lead's fake TUI, apply none:
    each step is the raw tool action, as under a harness whose rules allow every tool. A worker's run and the Lead's
    session still pass rows 1 to 6, the store refuses a write, the host's loopback is out of reach, and no AEW
    credential is in reach. The masks, the store and the network have their own tests (test_containment.py), and the
    terminal's route is row 4 and test_lead_containment.py's TIOCSTI test: none of them runs a permission rule."""
    import socket

    host = socket.create_server(("127.0.0.1", 0))
    port = host.getsockname()[1]
    try:
        def tries(store: Path) -> list[dict[str, Any]]:
            return [{"do": "write", "files": {str(store / "route-probe.txt"): "x"}},
                    {"do": "connect", "tcp": ["127.0.0.1", port]},
                    {"do": "read_parent_environ", "pid": "ppid", "names": []}]

        script(lab, [*tries(lab.aew_root), *IMPLEMENT])
        launch(lab, tmp_path)
        lab.wait(RUN)
        rows = lab.record(RUN)["containment"]["self_test"]["rows"]
        from_run = [lab.step(RUN, i) for i in range(3)]
        done, steps = lead_session.agent_session(tmp_path / "lead", lambda lead: tries(lead.aew_root))
        lead_rows = done["result"]["containment"]["self_test"]["rows"]
    finally:
        host.close()
    for seen, rows_seen in ((from_run, rows), ([steps[i] for i in range(3)], lead_rows)):
        assert sorted(rows_seen) == list("123456") and all(r["ok"] for r in rows_seen.values()), rows_seen
        write, reach, parent = seen
        assert write["wrote"] == [] and set(write["refused"].values()) == {"EROFS"}, write
        assert reach == {"connected": False, "error": "ECONNREFUSED"}, reach
        assert parent["has_credential"] is False, parent
