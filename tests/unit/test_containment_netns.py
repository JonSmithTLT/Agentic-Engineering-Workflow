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

from aew.errors import ContainmentUnavailable, ValidationFailed
from aew.harness.containment import layout as L
from aew.harness.containment import netns, relay
from aew.harness.containment.egress import Allowlist

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


def test_the_shim_spec_forwards_the_server_in_and_the_relay_and_egress_out_on_fixed_ports():
    spec = netns.shim_spec("/n", relay_sock=netns.RELAY, egress_sock=netns.EGRESS)
    assert spec == {"in": [{"unix": os.path.join("/n", netns.SERVER), "port": netns.SERVER_PORT}],
                    "out": [{"port": netns.PROVIDER_PORT, "unix": os.path.join("/n", netns.RELAY)},
                            {"port": netns.EGRESS_PORT, "unix": os.path.join("/n", netns.EGRESS)}]}
    argv = netns.shim_argv(spec, ["opencode", "serve"])
    assert argv[:3] == [sys.executable, "-I", "-c"] and argv[-3:] == ["--", "opencode", "serve"]
    with open(netns.SHIM, encoding="utf-8") as f:  # the shim's own text, run with an explicit call to its main
        assert argv[3] == f.read() + "\nsys.exit(main(sys.argv[1:]))\n" and json.loads(argv[4]) == spec
