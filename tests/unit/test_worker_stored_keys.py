"""Synthetic worker keys are selected and read in the host process."""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from aew.engine import readiness
from aew.engine.harness_ops import Harness
from aew.engine.workspace_ops import Invocations
from aew.errors import HarnessIncompatible
from aew.harness import supervisor
from aew.harness.containment import netns
from aew.harness.opencode import login
from aew.harness.opencode.adapter import OpenCodeAdapter

SYNTHETIC = "SYNTHETIC-NOT-A-KEY"
VARIABLE = "OPENAI_API_KEY"


@dataclass(repr=False)
class Store:
    path: Path
    env: dict[str, str] = field(repr=False)

    def put(self, provider: str, active: int, updated: int, value: dict[str, str]) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO credential VALUES (?, ?, ?, ?)",
                        (provider, active, updated, json.dumps(value)))


@pytest.fixture
def store(tmp_path):
    home = tmp_path / "home"
    xdg = tmp_path / "data"
    path = xdg / "opencode" / "opencode.db"
    home.mkdir()
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE credential (integration_id TEXT, active INTEGER, time_updated INTEGER, value TEXT)")
    result = Store(path, {"HOME": str(home), "XDG_DATA_HOME": str(xdg)})
    result.put("openai", 1, 10, {"type": "key", "key": SYNTHETIC})
    return result


def test_worker_store_uses_read_only_timeout_and_keeps_generation(store, monkeypatch):
    connect = sqlite3.connect
    calls = []

    def observed_connect(path, **options):
        calls.append(options)
        assert path.endswith("?mode=ro")
        return connect(path, **options)

    monkeypatch.setattr(login.sqlite3, "connect", observed_connect)
    before = store.path.read_bytes()
    keys, why = login.worker_keys(store.env, {"openai"})
    assert why is None and set(keys) == {"openai"}
    assert keys["openai"].generation == (1, 10)
    assert keys["openai"].secret == SYNTHETIC
    assert SYNTHETIC not in repr(keys)
    assert store.path.read_bytes() == before
    assert calls == [{"uri": True, "timeout": login.BUSY_TIMEOUT_S}]


def test_worker_store_does_not_fall_back_past_deciding_row(store):
    store.put("openai", 1, 11, {"type": "oauth", "access": SYNTHETIC})
    unsupported = ({}, "the stored OpenCode login has no supported API-key row")
    assert login.worker_keys(store.env, {"openai"}) == unsupported
    store.put("openai", 1, 12, {"type": "unknown"})
    assert login.worker_keys(store.env, {"openai"}) == unsupported


def test_worker_store_reports_missing_and_locked_without_a_path(store, monkeypatch):
    assert login.worker_keys(store.env, {"anthropic"}) == ({}, "the stored OpenCode API-key row is missing")
    monkeypatch.setattr(login, "BUSY_TIMEOUT_S", 0.01)
    con = sqlite3.connect(store.path)
    try:
        con.execute("BEGIN EXCLUSIVE")
        keys, why = login.worker_keys(store.env, {"openai"})
    finally:
        con.close()
    assert keys == {} and why == "the stored OpenCode login database is locked"


def test_worker_key_selector_precedence_and_upstream(store, monkeypatch):
    monkeypatch.setattr(netns.sys, "platform", "linux")
    key, reason = netns.resolve_worker_key("openai", [VARIABLE], store.env, {}, on_relay_route=True)
    assert key is not None and reason is None
    monkeypatch.setattr(login, "worker_keys", lambda *_: pytest.fail("store lookup was unauthorized"))
    assert netns.resolve_worker_key("openai", [], store.env, {}, on_relay_route=True) == (None, None)
    exported = {**store.env, VARIABLE: SYNTHETIC}
    assert netns.resolve_worker_key("openai", [VARIABLE], exported, {}, on_relay_route=True) == (None, None)
    override = {"containment": {"network": {"upstreams": {"openai": "http://127.0.0.1:1234"}}}}
    assert netns.resolve_worker_key("openai", [VARIABLE], store.env, override, on_relay_route=True) == (None, None)
    for mode in (netns.SHARED, netns.ISOLATED):
        policy = {"containment": {"network": {"mode": mode}}}
        assert netns.resolve_worker_key("openai", [VARIABLE], store.env, policy, on_relay_route=True) == (None, None)
    assert netns.resolve_worker_key("openai", [VARIABLE], store.env, {}, on_relay_route=False) == (None, None)
    assert netns.resolve_worker_key("cert-only", [VARIABLE], store.env, {}, on_relay_route=True) == (None, None)
    monkeypatch.setattr(netns.sys, "platform", "win32")
    assert netns.resolve_worker_key("openai", [VARIABLE], store.env, {}, on_relay_route=True) == (None, None)


def test_worker_refuses_a_free_catalog_model_before_starting_the_session():
    catalog = [{"providerID": "opencode", "id": "synthetic-model", "variants": [], "enabled": True,
                "cost": [{"input": 0, "output": 0}]}]
    worker = SimpleNamespace(client=object(), _location_list=lambda _: catalog, _relayed=False, _relay=None,
                             token_semantics={}, meter=None)
    profile = {"provider": "opencode", "model": "synthetic-model"}
    with pytest.raises(HarnessIncompatible, match="verified paid base price"):
        OpenCodeAdapter._await_model(worker, profile)  # type: ignore[arg-type]
    catalog[0]["cost"][0]["output"] = 1
    assert OpenCodeAdapter._await_model(worker, profile)["catalog_size"] == 1  # type: ignore[arg-type]


def install_store_env(store, monkeypatch):
    monkeypatch.setattr(netns.sys, "platform", "linux")
    monkeypatch.delenv(VARIABLE, raising=False)
    monkeypatch.setenv("OPENCODE_DB", str(store.path))


def test_doctor_shares_one_store_read_with_its_model_probe(store, monkeypatch):
    install_store_env(store, monkeypatch)
    policy = {"harness": "opencode", "provider_env": [VARIABLE],
              "profiles": {"standard": {"provider": "openai", "model": "synthetic-model"}}}
    worker_keys = login.worker_keys
    calls = []

    def counted(env, providers):
        calls.append(providers)
        return worker_keys(env, providers)

    monkeypatch.setattr(login, "worker_keys", counted)
    with netns.doctor_key_snapshot():
        rows = {row["check"]: row for row in readiness.readiness_checks(policy)}
        key, why = netns.resolve_worker_key("openai", [VARIABLE], store.env, policy, on_relay_route=True)
        assert key is not None and why is None
    assert calls == [{"openai"}]
    assert "stored OpenCode login" in rows["provider-env"]["detail"]
    assert "one rate-limit bucket per model" in rows["provider-key"]["detail"]
    assert SYNTHETIC not in repr(rows)


@pytest.mark.parametrize("between", ["rotate", "remove", "weaker"])
def test_admission_and_spawn_use_separate_reads(store, monkeypatch, tmp_path, between):
    install_store_env(store, monkeypatch)
    policy = {"harness": "opencode", "provider_env": [VARIABLE],
              "profiles": {"standard": {"provider": "openai", "model": "synthetic-model"}}}
    profile = {"harness": "opencode", **policy["profiles"]["standard"]}
    inv = {"status": "active", "execution_profile": profile}
    state = {"invocations": {"INV-1": inv}}
    kernel = SimpleNamespace(execution_policy=lambda: (policy, None), store=SimpleNamespace(current=lambda: state))
    invocations = Invocations(kernel, roles=None)  # type: ignore[arg-type]
    worker_keys = login.worker_keys
    calls = []

    def counted(env, providers):
        calls.append(providers)
        return worker_keys(env, providers)

    monkeypatch.setattr(login, "worker_keys", counted)
    admitted = invocations.require_launchable(state, "INV-1", relaunch=False)
    run = {"run": "R-1", **invocations.provider_key_admission(admitted)}
    assert "provider_key_admission" not in inv
    assert SYNTHETIC not in repr(run)
    inv["runs"] = [run]
    if between == "rotate":
        store.put("openai", 1, 20, {"type": "key", "key": SYNTHETIC + "-ROTATED"})
    elif between == "remove":
        with sqlite3.connect(store.path) as con:
            con.execute("DELETE FROM credential")
    layout = None if between == "weaker" else SimpleNamespace(private_network=True, net_dir=None)
    monkeypatch.setattr(supervisor.containment, "establish", lambda **_: (layout, {"network": {}}))
    monkeypatch.setattr(supervisor.weaker_register, "enter_if_weaker", lambda *_, **__: None)
    monkeypatch.setattr(supervisor.weaker_register, "ownership_of", lambda _: None)

    def feed(*_, stored, **__):
        assert between == "rotate" and stored.secret == SYNTHETIC + "-ROTATED"
        return SimpleNamespace(describe=lambda: {"provider_key_source": "stored OpenCode login"})

    monkeypatch.setattr(netns.RunNetwork, "start", feed)
    arguments = {
        "provider": "openai", "provider_env": [VARIABLE], "role": "implementer", "scope": "ticket",
        "workspace": str(tmp_path), "run_dir": tmp_path, "scratch": str(tmp_path),
        "bridge_dir": None, "bridge": None, "project": tmp_path, "aew_root": tmp_path,
        "kind": "worker_run", "key_admission": run["provider_key_admission"],
    }
    if between == "rotate":
        _, label, _, _ = supervisor.contain_launch(policy, OpenCodeAdapter, **arguments)
        assert label["network"]["provider_key_note"] == "the stored OpenCode login changed after admission"
        host = SimpleNamespace(k=kernel, invocations=invocations)
        result = Harness._with_readiness(host, {"run": "R-1", "invocation": "INV-1"})  # type: ignore[arg-type]
        assert "readiness" not in result and SYNTHETIC not in repr((label, result))
    else:
        message = "needs the provider relay" if between == "weaker" else "changed after admission"
        with pytest.raises(HarnessIncompatible, match=message) as caught:
            supervisor.contain_launch(policy, OpenCodeAdapter, **arguments)
        assert SYNTHETIC not in str(caught.value)
    assert calls == [{"openai"}] * (1 if between == "weaker" else 2)
