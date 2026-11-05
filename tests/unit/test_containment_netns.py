"""A contained run's network, outside its sandbox (STG-05 CS-3b; F28 §3.1-§3.5): the mode a policy gives, the relay's
fixed upstream and the operator's proxy for it, the egress allowlist, the harness's environment (sentinels, never the
values) and the label. Pure: no socket is made here; the relay itself is tests/unit/test_provider_relay.py's, and the
network inside the sandbox is tests/integration/test_containment.py's (Linux)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace

import pytest
from host_env import GUARDED

from aew.errors import ContainmentUnavailable, ValidationFailed
from aew.harness.containment import layout as L
from aew.harness.containment import netns, relay
from aew.harness.containment.egress import Allowlist
from aew.harness.opencode import projection

pytestmark = GUARDED
KEY = "synthetic-provider-key-cs3b"
BASE = L.Layout(role="implementer", access="write", bwrap="/usr/bin/bwrap", writable=("/w",), readonly=())


def policy(**network) -> dict:
    return {"containment": {"network": network}}


class Egress:
    """Stands in for a started egress proxy: the label reads its policy, the record its counts."""

    def __init__(self, entries: list[str]) -> None:
        self.policy = Allowlist(entries)

    def counts(self) -> dict[str, int]:
        return {"allowed": 2, "not_allowed": 1}


def test_a_contained_run_on_linux_defaults_to_proxy_only_and_the_policy_may_choose(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert netns.mode(None) == netns.mode({}) == L.PROXY_ONLY  # F28 decision 1
    assert netns.mode(policy(mode="shared")) == L.SHARED and netns.mode(policy(mode="isolated")) == L.ISOLATED
    monkeypatch.setattr(sys, "platform", "win32")
    assert netns.mode(policy(mode="proxy_only")) == netns.NOT_PROVIDED  # no network containment on Windows


def test_a_layout_refuses_a_network_mode_it_does_not_know(tmp_path):
    with pytest.raises(ContainmentUnavailable) as caught:
        L.for_run(role="implementer", scope="ticket", workspace=tmp_path, run_dir=tmp_path, scratch=tmp_path,
                  bridge_dir=None, policy=None, project=tmp_path, network="open")
    assert "proxy_only, isolated, shared" in caught.value.message


def test_a_check_is_isolated_unless_it_asks_for_shared_and_its_run_has_the_hosts_network():
    """F28 §3.8: a check never inherits the run's routes out, and never gets wider than its run."""
    for run_mode in (L.PROXY_ONLY, L.ISOLATED, L.SHARED):
        run = replace(BASE, network=run_mode, net_dir="/tmp/aew-net-x" if run_mode != L.SHARED else None)
        for asked in (None, "isolated", "shared"):
            check = L.for_check(run, asked)
            want = L.SHARED if (asked == "shared" and run_mode == L.SHARED) else L.ISOLATED
            assert (check.network, check.net_dir) == (want, None), (run_mode, asked)
            assert ("--unshare-net" in L.bwrap_argv(check, ["true"])) == (want == L.ISOLATED)


def test_a_private_network_unshares_the_namespace_and_binds_only_the_shim_directory_writable():
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir="/tmp/aew-net-x")
    flags = L.bwrap_argv(layout, ["true"])
    assert "--unshare-net" in flags
    pairs = list(zip(flags, flags[1:], strict=False))
    shim = os.path.join("/tmp/aew-net-x", L.NET_SHIM)
    assert ("--ro-bind", "/tmp/aew-net-x") in pairs and ("--bind", shim) in pairs
    assert ("--bind", "/tmp/aew-net-x") not in pairs  # the relay's and the proxy's sockets cannot be replaced
    assert "--unshare-net" not in L.bwrap_argv(replace(BASE, network=L.SHARED), ["true"])


def test_the_relay_upstream_is_the_policys_else_a_known_one_else_a_refusal_that_says_what_to_set():
    assert netns.upstream("openai", None).url == "https://api.openai.com/v1"
    assert netns.upstream("openai", policy(upstreams={"openai": "https://gw.example/v1"})).url == "https://gw.example/v1"
    with pytest.raises(ContainmentUnavailable) as caught:
        netns.upstream("acme", None)
    assert caught.value.details["reason"] == "no_upstream"
    assert "containment.network.upstreams.acme" in caught.value.message and "mode: shared" in caught.value.message
    with pytest.raises(ContainmentUnavailable) as caught:
        netns.upstream("acme", policy(upstreams={"acme": "ftp://acme.example"}))
    assert caught.value.details["reason"] == "bad_upstream"


def test_the_egress_allowlist_is_the_policys_and_the_harnesss_and_none_when_both_are_empty():
    assert netns.egress_policy(None) is None
    allow = netns.egress_policy(policy(egress_allow=["pypi.org:443", "models.opencode.ai:443"]),
                                ("models.opencode.ai:443",))
    assert allow is not None and allow.describe()["allow"] == ["models.opencode.ai:443", "pypi.org:443"]
    with pytest.raises(ValidationFailed):
        netns.egress_policy(policy(egress_allow=["no port"]))


def test_the_operators_proxy_for_the_upstream_comes_only_from_the_variables_the_policy_names():
    https = relay.Upstream("https://api.openai.com/v1")
    env = {"HTTPS_PROXY": "http://proxy.example:3128", "ALL_PROXY": "http://all.example:1080",
           "NO_PROXY": "internal.example"}
    found = netns.operator_proxy(https, ["OPENAI_API_KEY", "HTTPS_PROXY"], env)
    assert found is not None and (found.host, found.port) == ("proxy.example", 3128)
    assert netns.operator_proxy(https, ["OPENAI_API_KEY"], env) is None  # a proxy the policy does not name is not used
    fallback = netns.operator_proxy(relay.Upstream("http://gw.example/v1"), ["ALL_PROXY"], env)
    assert fallback is not None and fallback.host == "all.example"
    bypassed = netns.operator_proxy(relay.Upstream("https://api.internal.example/v1"), ["HTTPS_PROXY", "NO_PROXY"], env)
    assert bypassed is None


def test_the_harness_gets_sentinels_and_the_egress_port_never_the_values_or_the_operators_proxy():
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir="/tmp/aew-net-x")
    token = relay.sentinel()
    net = netns.RunNetwork(layout, egress_proxy=Egress(["models.opencode.ai:443"]),  # type: ignore[arg-type]
                           sentinels={"OPENAI_API_KEY": token}, values={"OPENAI_API_KEY": KEY})
    env = net.harness_env({"OPENAI_API_KEY": KEY, "HTTPS_PROXY": "http://proxy.example:3128",
                           "HTTP_PROXY": "http://proxy.example:3128", "PATH": "/usr/bin"})
    assert env["OPENAI_API_KEY"] == token and KEY not in env.values()
    assert env["HTTPS_PROXY"] == env["https_proxy"] == f"http://127.0.0.1:{netns.EGRESS_PORT}"
    assert "HTTP_PROXY" not in env  # the provider's baseURL is plain http to loopback: never to the egress proxy
    assert "127.0.0.1" in env["NO_PROXY"].split(",")
    assert net.leaks(str(env)) == [] and net.leaks(f"key={KEY}") == ["OPENAI_API_KEY"]


def test_without_an_egress_proxy_the_harness_has_no_proxy_at_all():
    net = netns.RunNetwork(replace(BASE, network=L.ISOLATED, net_dir="/tmp/aew-net-x"),
                           sentinels={"OPENAI_API_KEY": relay.sentinel()})
    env = net.harness_env({"HTTPS_PROXY": "http://proxy.example:3128", "PATH": "/usr/bin"})
    assert not {k for k in env if k.upper().endswith("_PROXY")}
    assert net.provider_base() is None and net.describe() == {"mode": L.ISOLATED, "provider_relay": "none"}


def test_the_label_names_the_mode_the_relay_the_allowlist_and_the_stated_limit_and_the_record_the_counts():
    net = netns.RunNetwork(replace(BASE, network=L.PROXY_ONLY, net_dir="/tmp/aew-net-x"),
                           egress_proxy=Egress(["models.opencode.ai:443"]))  # type: ignore[arg-type]
    assert net.describe() == {"mode": L.PROXY_ONLY, "provider_relay": "none",
                              "egress_allow": ["models.opencode.ai:443"], "limits": [netns.EGRESS_RESIDUAL]}
    assert net.decisions() == {"egress": {"allowed": 2, "not_allowed": 1}}


@pytest.mark.skipif(sys.platform == "win32", reason="the relays listen on socket files (AF_UNIX)")
def test_the_leads_refreshing_login_has_its_own_upstream_and_its_sentinel_is_for_the_login_store_not_a_variable():
    """STG-05 CS-4, addendum 1: a refreshing login's relay goes to its own upstream (the ChatGPT login's base) unless
    the policy names one; its sentinel is for the Lead's own login store, never a provider variable; and its access
    token, as stored now, is in the leak check. An API-key provider beside it keeps its variable and its upstream."""
    layout = replace(BASE, role="lead", network=L.PROXY_ONLY, net_dir=netns.private_dir())
    net = netns.RunNetwork.start_lead(layout, keys={"anthropic": KEY}, provider_env=[], policy=None, env={},
                                      refreshing={"openai": lambda: ("synthetic-access", {"chatgpt-account-id": "a"})})
    try:
        assert net.describe()["provider_relays"] == {"anthropic": "https://api.anthropic.com/v1",
                                                     "openai": "https://chatgpt.com/backend-api/codex"}
        assert set(net.sentinels) == {"ANTHROPIC_API_KEY"} and set(net.login_sentinels) == {"openai"}
        assert net.lead_bases()["openai"].endswith(":4112/backend-api/codex")
        assert net.leaks("... synthetic-access ...") == ["openai login"]
        assert "OPENAI_API_KEY" not in net.harness_env({})
    finally:
        net.close()


def test_a_relay_with_no_upstream_refuses_the_launch_and_leaves_no_network_directory(tmp_path):
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir=str(tmp_path / "aew-net-x"))
    (tmp_path / "aew-net-x").mkdir()
    with pytest.raises(ContainmentUnavailable) as caught:
        netns.RunNetwork.start(layout, provider="acme", provider_env=["ACME_KEY"], policy=None,
                               env={"ACME_KEY": KEY}, relay_needed=True)
    assert caught.value.details["reason"] == "no_upstream" and not (tmp_path / "aew-net-x").exists()


def test_only_opencode_with_its_key_unnamed_and_no_upstream_named_on_linux_proxy_only_has_no_relay(monkeypatch):
    """Design §8: the one place this is decided, from the pinned profile and the policy."""
    monkeypatch.setattr(sys, "platform", "linux")
    assert netns.keyless_egress("opencode", [], None) == "opencode.ai:443"
    # another provider's variable in the policy-wide list is no key for this provider
    assert netns.keyless_egress("opencode", ["OPENAI_API_KEY", "HTTPS_PROXY"], None) == "opencode.ai:443"
    assert netns.keyless_egress("opencode", ["OPENCODE_API_KEY"], None) is None
    assert netns.keyless_egress("opencode", [], policy(upstreams={"opencode": "https://gw.example/v1"})) is None
    for provider in ("openai", "anthropic", "google", "acme", None):  # never another provider, even with no key
        assert netns.keyless_egress(provider, [], None) is None, provider
    for other in ("shared", "isolated"):
        assert netns.keyless_egress("opencode", [], policy(mode=other)) is None, other
    monkeypatch.setattr(sys, "platform", "win32")
    assert netns.keyless_egress("opencode", [], None) is None


def test_the_one_allowlist_adds_the_providers_host_for_that_run_only_and_never_to_the_harnesss_own(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    egress_extra = ("models.opencode.ai:443",)

    def shown(provider, provider_env, relay_needed=True, **network):
        keyless, allow = netns.worker_route(policy(**network), provider=provider, provider_env=provider_env,
                                            relay_needed=relay_needed, egress_extra=egress_extra)
        return keyless, allow.describe()["allow"] if allow else None
    assert shown("opencode", []) == ("opencode.ai:443", ["models.opencode.ai:443", "opencode.ai:443"])
    assert shown("opencode", [], egress_allow=["pypi.org:443"])[1] == ["models.opencode.ai:443", "opencode.ai:443",
                                                                      "pypi.org:443"]
    assert shown("opencode", ["OPENCODE_API_KEY"]) == (None, ["models.opencode.ai:443"])
    assert shown("openai", []) == (None, ["models.opencode.ai:443"])
    assert shown("opencode", [], relay_needed=False) == (None, ["models.opencode.ai:443"])  # it calls no provider


@pytest.mark.skipif(sys.platform == "win32", reason="the relay and the proxy listen on socket files (AF_UNIX)")
def test_a_keyless_run_has_no_relay_and_holds_no_key_and_its_label_and_text_say_so():
    net_dir = netns.private_dir()
    os.mkdir(os.path.join(net_dir, L.NET_SHIM))
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir=net_dir)
    host = {"OPENAI_API_KEY": KEY, "OPENCODE_API_KEY": "synthetic-opencode-key", "PATH": "/usr/bin"}
    net = netns.RunNetwork.start(layout, provider="opencode", provider_env=["OPENAI_API_KEY"], policy=None, env=host,
                                 relay_needed=True, egress_extra=("models.opencode.ai:443",))
    try:
        assert net.relay is None and net.provider_base() is None  # so projection.relayed() does not run
        assert [leg["port"] for leg in net.spec()["out"]] == [netns.EGRESS_PORT]  # no provider port to fall back on
        # what a server's environment holds by then: the named variable's value, and never the unnamed one's. Another
        # provider's variable holds its sentinel, as on any run; nothing swaps it, and this provider is not sent it
        inside = net.harness_env({"OPENAI_API_KEY": KEY, "PATH": "/usr/bin"})
        assert inside["OPENAI_API_KEY"].startswith(relay.SENTINEL_PREFIX) and KEY not in inside.values()
        assert "OPENCODE_API_KEY" not in inside and "synthetic-opencode-key" not in inside.values()
        assert inside["HTTPS_PROXY"] == f"http://127.0.0.1:{netns.EGRESS_PORT}"
        assert net.leaks(f"key={KEY}") == ["OPENAI_API_KEY"]  # the leak check still knows the value
        label = net.describe()
        assert label == {"mode": L.PROXY_ONLY, "provider_relay": "none", "provider_route": "egress",
                         "egress_allow": ["models.opencode.ai:443", "opencode.ai:443"],
                         "limits": [netns.EGRESS_RESIDUAL, netns.KEYLESS_LIMIT]}
        assert "for testing" in netns.KEYLESS_LIMIT
        assert "no per-request record and no 429 classification" in netns.KEYLESS_LIMIT
        assert ("your model's provider through `HTTPS_PROXY`, which admits only `models.opencode.ai:443`, "
                "`opencode.ai:443`") in projection.network_text(label)
    finally:
        net.close()


@pytest.mark.skipif(sys.platform == "win32", reason="the relay and the proxy listen on socket files (AF_UNIX)")
@pytest.mark.parametrize(("provider", "names", "network"), [
    ("opencode", ["OPENCODE_API_KEY"], {}),
    ("opencode", [], {"upstreams": {"opencode": "https://gw.example/v1"}}),
    ("openai", ["OPENAI_API_KEY"], {}),
])
def test_a_run_with_a_key_or_a_named_gateway_or_another_provider_keeps_the_relay(provider, names, network):
    net_dir = netns.private_dir()
    os.mkdir(os.path.join(net_dir, L.NET_SHIM))
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir=net_dir)
    net = netns.RunNetwork.start(layout, provider=provider, provider_env=names, policy=policy(**network),
                                 env={n: KEY for n in names}, relay_needed=True,
                                 egress_extra=("models.opencode.ai:443",))
    try:
        label = net.describe()
        assert net.relay is not None and net.provider_base() is not None and net.keyless is None
        assert label["provider_relay"] == "configured" and "provider_route" not in label
        assert label["egress_allow"] == ["models.opencode.ai:443"] and netns.KEYLESS_LIMIT not in label["limits"]
        inside = net.harness_env({**{n: KEY for n in names}, "PATH": "/usr/bin"})
        assert all(inside[n].startswith(relay.SENTINEL_PREFIX) for n in names) and KEY not in inside.values()
    finally:
        net.close()


@pytest.mark.parametrize("variable", ["HTTPS_PROXY", "ALL_PROXY"])
def test_a_keyless_run_with_a_proxy_for_its_upstream_is_refused_and_told_what_to_do(tmp_path, monkeypatch, variable):
    monkeypatch.setattr(sys, "platform", "linux")
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir=str(tmp_path / "aew-net-x"))
    (tmp_path / "aew-net-x").mkdir()
    with pytest.raises(ContainmentUnavailable) as caught:
        netns.RunNetwork.start(layout, provider="opencode", provider_env=[variable], policy=None,
                               env={variable: "http://proxy.example:3128"}, relay_needed=True,
                               egress_extra=("models.opencode.ai:443",))
    assert caught.value.details["reason"] == "keyless_proxy"
    for what_to_do in ("containment.network.upstreams.opencode", "containment.network.mode: shared"):
        assert what_to_do in caught.value.message
    assert "API_KEY" not in caught.value.message  # a key is measured nowhere on this upstream
    assert not (tmp_path / "aew-net-x").exists()  # nothing was started, and nothing is left


@pytest.mark.skipif(sys.platform == "win32", reason="the proxy listens on a socket file (AF_UNIX)")
@pytest.mark.parametrize(("names", "env"), [
    (["NO_PROXY"], {"NO_PROXY": "internal.example"}),
    (["HTTPS_PROXY", "NO_PROXY"], {"HTTPS_PROXY": "http://proxy.example:3128", "NO_PROXY": "opencode.ai"}),
    (["HTTP_PROXY"], {"HTTP_PROXY": "http://proxy.example:3128"}),  # the relay would not use it for https either
])
def test_a_keyless_run_is_not_refused_for_a_proxy_that_does_not_apply_to_its_upstream(names, env):
    net_dir = netns.private_dir()
    os.mkdir(os.path.join(net_dir, L.NET_SHIM))
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir=net_dir)
    net = netns.RunNetwork.start(layout, provider="opencode", provider_env=names, policy=None, env=env,
                                 relay_needed=True, egress_extra=())
    try:
        assert net.keyless == "opencode.ai:443" and net.relay is None
    finally:
        net.close()


def test_a_keyless_runs_model_off_the_allowlist_is_named_and_any_other_route_never_asks():
    layout = replace(BASE, network=L.PROXY_ONLY, net_dir="/tmp/aew-net-x")
    net = netns.RunNetwork(layout, egress_proxy=Egress(["opencode.ai:443"]))  # type: ignore[arg-type]
    net.keyless = "opencode.ai:443"
    assert net.refused_address("https://opencode.ai/inference/openai/v1") is None
    assert net.refused_address("https://OpenCode.AI/v1") is None
    assert net.refused_address("https://elsewhere.example/v1") == "elsewhere.example:443"
    assert net.refused_address("https://opencode.ai:8443/v1") == "opencode.ai:8443"
    assert net.refused_address("not a url") == "an address that is not a URL"
    net.keyless = None
    assert net.refused_address("https://elsewhere.example/v1") is None


def test_the_shim_spec_forwards_the_server_in_and_the_relay_and_egress_out_on_fixed_ports():
    spec = netns.shim_spec("/n", relay_sock=netns.RELAY, egress_sock=netns.EGRESS)
    assert spec == {"in": [{"unix": os.path.join("/n", netns.SERVER), "port": netns.SERVER_PORT}],
                    "out": [{"port": netns.PROVIDER_PORT, "unix": os.path.join("/n", netns.RELAY)},
                            {"port": netns.EGRESS_PORT, "unix": os.path.join("/n", netns.EGRESS)}]}
    argv = netns.shim_argv(spec, ["opencode", "serve"])
    assert argv[:3] == [sys.executable, "-I", "-c"] and argv[-3:] == ["--", "opencode", "serve"]
    with open(netns.SHIM, encoding="utf-8") as f:  # the shim's own text, run with an explicit call to its main
        assert argv[3] == f.read() + "\nsys.exit(main(sys.argv[1:]))\n" and json.loads(argv[4]) == spec
