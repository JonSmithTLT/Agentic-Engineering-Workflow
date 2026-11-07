"""AEW does not rely on OpenCode's free models (the operator, 2026-11-06; the designer's rulings of that day).

- A worker launch on the relay route whose provider would get no key is refused, before anything is committed, with
  the closed reason ``provider_key_missing``: by the engine (``require_launchable``) and again by the supervisor
  (``_contain``), from one pure predicate (``netns.provider_key_missing``).
- The egress proxy records each target it refuses, bounded and in a closed character set, for the run's record only;
  one fixed note marks the refusal that is known and expected.

Synthetic names, keys and targets only: nothing here reaches a network.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace
from typing import Any

import pytest

from aew import errors
from aew.engine.workspace_ops import Invocations
from aew.harness import supervisor
from aew.harness.containment import egress, netns
from aew.harness.containment.egress import Allowlist, AnyPublic, EgressProxy

KEY = "sk-synthetic-provider-key-0001"
TIMEOUT = 5.0


@pytest.fixture
def relay_route(monkeypatch):
    """The relay route on any platform: the policy's network mode reads ``proxy_only`` (Linux's default)."""
    monkeypatch.setattr(netns, "mode", lambda policy: netns.PROXY_ONLY)


# ---------------------------------------------------------------------------------------------------- the predicate

def test_the_predicate_names_the_providers_key_variable_only_when_no_key_would_reach_the_run():
    """Right: the provider's variable named and set. Wrong: not named, named but empty, or a key of another provider
    (a keyless opencode worker with only OPENAI_API_KEY named: the case the operator's decision refuses). Missing: a
    provider whose variable AEW does not know, and any run off the relay route, are never judged."""
    on = {"on_relay_route": True}
    assert netns.provider_key_missing("openai", ["OPENAI_API_KEY"], {"OPENAI_API_KEY": KEY}, **on) is None
    assert netns.provider_key_missing("openai", [], {"OPENAI_API_KEY": KEY}, **on) == "OPENAI_API_KEY"
    assert netns.provider_key_missing("openai", ["OPENAI_API_KEY"], {"OPENAI_API_KEY": ""}, **on) == "OPENAI_API_KEY"
    assert netns.provider_key_missing("openai", ["OPENAI_API_KEY"], {}, **on) == "OPENAI_API_KEY"
    assert netns.provider_key_missing("opencode", ["OPENAI_API_KEY"], {"OPENAI_API_KEY": KEY},
                                      **on) == "OPENCODE_API_KEY"
    assert netns.provider_key_missing("opencode", ["OPENCODE_API_KEY"], {"OPENCODE_API_KEY": KEY}, **on) is None
    assert netns.provider_key_missing("fakeprov", [], {}, **on) is None  # a Provider Gateway may need none
    assert netns.provider_key_missing(None, [], {}, **on) is None
    assert netns.provider_key_missing("opencode", [], {}, on_relay_route=False) is None


def test_the_relay_route_is_a_relaying_harness_under_proxy_only(monkeypatch):
    for found, expected in ((netns.PROXY_ONLY, True), (netns.SHARED, False), (netns.ISOLATED, False),
                            (netns.NOT_PROVIDED, False)):
        monkeypatch.setattr(netns, "mode", lambda policy, found=found: found)
        assert netns.relay_route({}, True) is expected
        assert netns.relay_route({}, False) is False  # a harness that never calls its provider itself


def test_the_refusal_quotes_the_published_rule_and_names_both_steps():
    message = netns.provider_key_message("opencode", "OPENCODE_API_KEY")
    assert netns.FREE_TIER_RULE in message and "https://opencode.ai/docs/zen/" in message
    assert ("Free-tier chat models require OpenCode; use paid models or Go from other clients." in message)
    assert "`provider_env: [OPENCODE_API_KEY]`" in message  # step 1: a key
    assert "pin a paid model of opencode" in message and "--profile or --model" in message  # step 2: a paid model
    assert netns.PROVIDER_KEY_MISSING == "provider_key_missing"


# ------------------------------------------------------------------------------------------------ the engine's check

def engine_invocations(policy: dict[str, Any]) -> Invocations:
    return Invocations(SimpleNamespace(execution_policy=lambda: (policy, None)), roles=None)  # type: ignore[arg-type]


def launchable_state(provider: str) -> dict[str, Any]:
    profile = {"harness": "opencode", "provider": provider, "model": "synthetic-paid-model"}
    return {"invocations": {"INV-0001": {"status": "active", "execution_profile": profile}}}


@pytest.mark.parametrize(("provider", "provider_env", "env", "refused"), [
    ("opencode", [], {}, "OPENCODE_API_KEY"),                                  # wrong: no key at all
    ("opencode", ["OPENAI_API_KEY"], {"OPENAI_API_KEY": KEY}, "OPENCODE_API_KEY"),  # wrong: another provider's key
    ("opencode", ["OPENCODE_API_KEY"], {"OPENCODE_API_KEY": KEY}, None),       # right: its own key
    ("fakeprov", [], {}, None),                                               # missing: not judged
], ids=["no-key", "another-providers-key", "its-own-key", "unknown-provider"])
def test_require_launchable_refuses_a_relay_route_launch_whose_provider_would_get_no_key(
        relay_route, monkeypatch, provider, provider_env, env, refused):
    for name in ("OPENAI_API_KEY", "OPENCODE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    invocations = engine_invocations({"provider_env": provider_env})
    if refused is None:
        assert invocations.require_launchable(launchable_state(provider), "INV-0001", relaunch=False)
        return
    with pytest.raises(errors.HarnessIncompatible) as caught:
        invocations.require_launchable(launchable_state(provider), "INV-0001", relaunch=False)
    assert caught.value.details["reason"] == "provider_key_missing" and caught.value.details["variable"] == refused
    assert netns.FREE_TIER_RULE in caught.value.message and KEY not in caught.value.message


def test_require_launchable_judges_nothing_off_the_relay_route(monkeypatch):
    monkeypatch.setattr(netns, "mode", lambda policy: netns.SHARED)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    assert engine_invocations({"provider_env": []}).require_launchable(launchable_state("opencode"), "INV-0001",
                                                                       relaunch=False)


# -------------------------------------------------------------------------------------------- the supervisor's check

class Reached(Exception):
    """The supervisor went past its key check, to the containment it builds next."""


def contain(monkeypatch, provider_env: list[str], provider: str = "openai", relay: bool = True) -> None:
    """``Supervisor._contain``'s first steps, on a stand-in supervisor: its key check, then (raising ``Reached``)
    the sandbox it would build."""
    def establish(**kwargs: Any) -> Any:
        raise Reached

    monkeypatch.setattr(supervisor.containment, "establish", establish)
    stand_in = SimpleNamespace(engine=SimpleNamespace(execution_policy=lambda: ({}, None), repo_root="/p",
                                                      aew_root="/p/.aew"),
                               bridge=SimpleNamespace(private_dir=None, address=None),
                               record={"execution_profile": {"provider": provider}}, run_dir=None)
    contract = SimpleNamespace(extra={"provider_env": provider_env}, role="implementer", scope="ticket",
                               workspace="/w", scratch="/s")
    adapter_cls = SimpleNamespace(PROVIDER_RELAY=relay, EGRESS=())
    supervisor.Supervisor._contain(stand_in, contract, adapter_cls)  # type: ignore[arg-type]


def test_the_supervisor_refuses_again_before_any_sandbox_or_network_exists(relay_route, monkeypatch):
    """The second check, on the names the run's contract carries: wrong (no key) refuses before ``establish``; right
    (named and set) goes on to it; missing (a harness that never calls its provider, or an unknown provider) is not
    judged."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(errors.HarnessIncompatible) as caught:
        contain(monkeypatch, [])
    assert caught.value.details["reason"] == "provider_key_missing"
    assert caught.value.details["variable"] == "OPENAI_API_KEY"
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    with pytest.raises(Reached):
        contain(monkeypatch, ["OPENAI_API_KEY"])
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(Reached):
        contain(monkeypatch, [], relay=False)
    with pytest.raises(Reached):
        contain(monkeypatch, [], provider="fakeprov")


# ----------------------------------------------------------------------------------------- the refused-target record

def refuse(proxy: EgressProxy, target: str) -> bytes:
    """One CONNECT to ``target``, served by ``proxy.handle`` on this thread: its answer."""
    client, server = socket.socketpair()
    client.settimeout(TIMEOUT)
    try:
        client.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        proxy.handle(server)
        answer = b""
        while chunk := client.recv(65536):
            answer += chunk
        return answer
    finally:
        client.close()


def unresolved(host: str, port: int) -> list[str]:
    raise socket.gaierror(socket.EAI_NONAME, "synthetic: no such name")


def test_each_refused_target_is_recorded_with_its_reasons_and_count_and_nothing_else_is():
    """A target the allowlist refuses (403) and one R-6 refuses (a host-local answer) are recorded; a refusal that
    names no judged target (a malformed request, a name that does not resolve) is not."""
    proxy = EgressProxy(Allowlist(["models.opencode.ai:443", "local.example:443"]),
                        resolve=lambda host, port: ["127.0.0.1"] if host == "local.example" else unresolved(host, port))
    try:
        assert b" 403 " in refuse(proxy, "opencode.ai:443")
        refuse(proxy, "opencode.ai:443")
        assert b" 403 " in refuse(proxy, "local.example:443")
        assert b" 502 " in refuse(proxy, "models.opencode.ai:443")  # unresolved: no judgement of the target
        assert b" 400 " in refuse(proxy, "not a target")
        found = proxy.refused_targets()
        assert found == {"targets": [{"target": "opencode.ai:443", "reasons": ["not_allowlisted"], "count": 2},
                                     {"target": "local.example:443", "reasons": ["loopback"], "count": 1}],
                         "more": 0}, found
    finally:
        proxy.close()


def test_at_most_twenty_distinct_targets_are_named_and_the_rest_are_counted():
    proxy = EgressProxy(Allowlist(["models.opencode.ai:443"]))
    try:
        for i in range(egress.MAX_REFUSED_TARGETS + 5):
            refuse(proxy, f"host-{i}.example:443")
        refuse(proxy, "host-0.example:443")  # a named one is still counted against its own entry
        refuse(proxy, "host-24.example:443")
        found = proxy.refused_targets()
        assert len(found["targets"]) == egress.MAX_REFUSED_TARGETS == 20
        assert found["targets"][0] == {"target": "host-0.example:443", "reasons": ["not_allowlisted"], "count": 2}
        assert found["more"] == 6
    finally:
        proxy.close()


@pytest.mark.parametrize(("text", "kept"), [
    ("opencode.ai:443", "opencode.ai:443"),                         # right: as authority() gives it
    ("[2001:db8::1]:443", "[2001:db8::1]:443"),                     # right: an address
    ("Evil\x1b[31m<b>\"x\"</b>\n:443", "evil[31mbxb:443"),       # wrong: control, markup and quotes go
    ("a" * 300 + ":443", "a" * egress.REFUSED_TARGET_MAX + ":443"),  # wrong: the host cut, its port kept (n4)
    ("a" * 300, "a" * egress.REFUSED_TARGET_MAX),                   # wrong: no port, the whole cut
    ("", ""),                                                       # missing: nothing
], ids=["name", "ipv6", "markup", "long", "long-no-port", "empty"])
def test_a_refused_target_is_kept_in_a_closed_character_set_and_cut(text, kept):
    assert egress.refused_target(text) == kept
    assert set(kept) <= set("abcdefghijklmnopqrstuvwxyz0123456789.:[]-")


def test_any_public_records_what_r6_refuses():
    proxy = EgressProxy(AnyPublic(), resolve=lambda host, port: ["10.0.0.7"], is_local=lambda ip: False)
    try:
        assert b" 403 " in refuse(proxy, "inside.example:443")
        assert proxy.refused_targets()["targets"][0]["target"] == "inside.example:443"
    finally:
        proxy.close()


def run_network(provider: str | None, key_relayed: bool, *targets: str) -> netns.RunNetwork:
    net = netns.RunNetwork(SimpleNamespace(network=netns.PROXY_ONLY, net_dir=None),  # type: ignore[arg-type]
                           egress_proxy=EgressProxy(Allowlist(["models.opencode.ai:443"])))
    net.provider, net.key_relayed = provider, key_relayed
    assert net.egress is not None
    for target in targets:
        refuse(net.egress, target)
    return net


def test_the_console_sync_note_is_on_opencode_ai_443_only_for_a_keyed_opencode_run():
    """Right: provider opencode, its key relayed, `opencode.ai:443` refused: the one fixed note. Wrong: every other
    target on that run, and that target on a run of another provider or without its key, gets none. Missing: a run
    with no egress proxy has no record."""
    net = run_network("opencode", True, "opencode.ai:443", "opencode.ai:80", "api.opencode.ai:443",
                      "evil.example:443")
    try:
        found = net.refused()
        assert found is not None
        notes = {e["target"]: e.get("note") for e in found["targets"]}
        assert notes == {"opencode.ai:443": netns.CONSOLE_SYNC_NOTE, "opencode.ai:80": None,
                         "api.opencode.ai:443": None, "evil.example:443": None}
        assert netns.CONSOLE_SYNC_NOTE == "expected: OpenCode's console sync (inferred), refused by design"
    finally:
        net.close()
    for provider, keyed in (("openai", True), ("opencode", False), (None, False)):
        net = run_network(provider, keyed, "opencode.ai:443")
        try:
            found = net.refused()
            assert found is not None and "note" not in found["targets"][0], (provider, keyed)
        finally:
            net.close()
    bare = netns.RunNetwork(SimpleNamespace(network=netns.PROXY_ONLY, net_dir=None))  # type: ignore[arg-type]
    assert bare.refused() is None


def test_the_refused_targets_are_never_in_the_runs_label_or_its_system_text():
    """The record is written beside the label (``egress_refused``), never in it: the label is what `harness status`,
    `harness wait` and the system text read. Nothing offers a refused target as an allowlist entry."""
    from aew.harness.opencode import projection

    net = run_network("opencode", True, "opencode.ai:443", "secret-plan.example:443")
    try:
        label = net.describe()
        assert "secret-plan" not in repr(label) and "'opencode.ai:443'" not in repr(label)
        assert "secret-plan" not in projection.network_text(label)
        assert "secret-plan" not in repr(net.decisions())  # counts only
    finally:
        net.close()


# ------------------------------------------------------------------------------------- the provider deny's keys

def test_a_release_that_respells_the_leads_provider_deny_is_refused_at_a_workers_launch():
    """`Config.InfoEncoded.experimental.policies` carries every Lead's provider deny (the designer's ruling): the
    capability probe checks both keys, so a release without either is refused. Right: the pinned schema passes.
    Wrong: `experimental` renamed, or `policies` gone from it. Missing: `experimental` with no properties."""
    import copy
    import json
    from pathlib import Path

    from aew.harness.opencode import capabilities

    spec = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode" / "openapi-2.0.18.min.json")
                      .read_text(encoding="utf-8"))
    assert capabilities.problems(spec) == []
    config = "Config.InfoEncoded"
    renamed = copy.deepcopy(spec)
    props = renamed["components"]["schemas"][config]["properties"]
    props["experimental_v3"] = props.pop("experimental")
    assert any("experimental" in p for p in capabilities.problems(renamed)), capabilities.problems(renamed)
    no_policies = copy.deepcopy(spec)
    no_policies["components"]["schemas"][config]["properties"]["experimental"]["properties"].pop("policies")
    assert any("experimental.policies" in p for p in capabilities.problems(no_policies))
    empty = copy.deepcopy(spec)
    empty["components"]["schemas"][config]["properties"]["experimental"] = {"type": "object"}
    assert any("experimental.policies" in p for p in capabilities.problems(empty))


def test_the_supervisor_writes_the_refused_targets_beside_the_label():
    """Right: refusals go in `egress_refused`, beside `containment`. Missing: a run with none, or with no egress proxy,
    gets no such key."""
    record: dict[str, Any] = {"containment": {"network": {"mode": netns.PROXY_ONLY}}}
    net = run_network("opencode", True, "opencode.ai:443")
    try:
        supervisor.record_refused(record, net)
    finally:
        net.close()
    assert record["egress_refused"]["targets"][0]["target"] == "opencode.ai:443"
    assert record["containment"] == {"network": {"mode": netns.PROXY_ONLY}}
    for quiet in (run_network("opencode", True),
                  netns.RunNetwork(SimpleNamespace(network=netns.PROXY_ONLY, net_dir=None))):  # type: ignore[arg-type]
        empty: dict[str, Any] = {}
        supervisor.record_refused(empty, quiet)
        quiet.close()
        assert empty == {}


# ---------------------------------------------------------------------------------------------------- doctor

def test_doctor_names_a_profile_whose_launch_would_get_no_key(relay_route, monkeypatch):
    """`aew doctor`'s `provider-key` line, from the launch's own predicate. Wrong: FAIL naming the provider, the
    variable and the profile. Right: PASS, names only. Missing: nothing judged (a harness that never calls its
    provider itself, or an unknown provider), so no line."""
    from aew.engine import readiness

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    policy = {"harness": "opencode", "provider_env": [],
              "profiles": {"standard": {"provider": "openai", "model": "synthetic-paid-model"},
                           "light": {"provider": "fakeprov", "model": "synthetic-model"}}}
    found = readiness._provider_key_doctor(policy)
    assert found is not None and found[0] == "FAIL", found
    assert "openai (OPENAI_API_KEY), for profile(s) standard" in found[1] and "provider_key_missing" in found[1]
    assert netns.FREE_TIER_RULE in found[1]
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    found = readiness._provider_key_doctor({**policy, "provider_env": ["OPENAI_API_KEY"]})
    assert found == ("PASS", "a provider key reaches the run for profile(s) standard (names only)")
    assert readiness._provider_key_doctor({**policy, "profiles": {"light": policy["profiles"]["light"]}}) is None
    # cannot load: not judged
    assert readiness._provider_key_doctor({**policy, "harness": "fake-not-registered"}) is None
