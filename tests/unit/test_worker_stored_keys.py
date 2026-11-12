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
from aew.harness.opencode.adapter import OpenCodeAdapter, server_env

SYNTHETIC = "SYNTHETIC-NOT-A-KEY"
VARIABLE = "OPENAI_API_KEY"


@dataclass(repr=False)
class Store:
    path: Path
    env: dict[str, str] = field(repr=False)

    def put(self, provider: str, active: int, updated: int, value: dict[str, str]) -> None:
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO credential (integration_id, active, time_updated, value) VALUES (?, ?, ?, ?)",
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
        con = connect(path, **options)
        # Core SQL only. Neither JSON1 nor a window-function implementation is required.
        con.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_FUNCTION
                           else sqlite3.SQLITE_OK)
        return con

    monkeypatch.setattr(login.sqlite3, "connect", observed_connect)
    before = store.path.read_bytes()
    keys, why = login.worker_keys(store.env, {"openai"})
    assert not why and set(keys) == {"openai"}
    assert keys["openai"].generation == (1, 10)
    assert keys["openai"].secret == SYNTHETIC
    assert SYNTHETIC not in repr(keys)
    assert store.path.read_bytes() == before
    assert calls == [{"uri": True, "timeout": login.BUSY_TIMEOUT_S}]


def test_worker_wal_read_preserves_database_content(store):
    con = sqlite3.connect(store.path)
    try:
        assert con.execute("PRAGMA journal_mode=wal").fetchone() == ("wal",)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        expected = con.execute("SELECT * FROM credential").fetchall()
    finally:
        con.close()
    before = store.path.read_bytes()
    keys, why = login.worker_keys(store.env, {"openai"})
    assert not why and keys["openai"].secret == SYNTHETIC
    assert store.path.read_bytes() == before
    con = sqlite3.connect(f"{store.path.as_uri()}?mode=ro", uri=True)
    try:
        assert con.execute("SELECT * FROM credential").fetchall() == expected
    finally:
        con.close()


def test_worker_store_does_not_fall_back_past_deciding_row(store):
    store.put("openai", 1, 11, {"type": "oauth", "access": SYNTHETIC})
    unsupported = ({}, {"openai": "the stored OpenCode login has no supported API-key row"})
    assert login.worker_keys(store.env, {"openai"}) == unsupported
    store.put("openai", 1, 12, {"type": "unknown"})
    assert login.worker_keys(store.env, {"openai"}) == unsupported


def test_worker_store_reports_missing_and_locked_without_a_path(store, monkeypatch):
    assert login.worker_keys(store.env, {"anthropic"}) == (
        {}, {"anthropic": "the stored OpenCode API-key row is missing"},
    )
    monkeypatch.setattr(login, "BUSY_TIMEOUT_S", 0.01)
    con = sqlite3.connect(store.path)
    try:
        con.execute("BEGIN EXCLUSIVE")
        keys, why = login.worker_keys(store.env, {"openai"})
    finally:
        con.close()
    assert keys == {} and why == {"openai": "the stored OpenCode login database is locked"}


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


def test_doctor_snapshot_returns_only_the_requested_provider(store):
    store.put("anthropic", 1, 20, {"type": "key", "key": SYNTHETIC})
    with netns.doctor_key_snapshot():
        both, _ = netns.doctor_worker_keys(store.env, {"openai", "anthropic"})
        selected, _ = netns.doctor_worker_keys(store.env, {"anthropic"})
        assert set(both) == {"openai", "anthropic"}
        assert selected == {"anthropic": both["anthropic"]}
        with pytest.raises(AssertionError, match="preload all candidate providers"):
            netns.doctor_worker_keys(store.env, {"google"})


def test_doctor_warns_when_a_stored_key_depends_on_allow_weaker_containment(store, monkeypatch):
    install_store_env(store, monkeypatch)
    policy = {"harness": "opencode", "provider_env": [VARIABLE],
              "containment": {"mode": "allow_weaker"},
              "profiles": {"standard": {"provider": "openai", "model": "synthetic-model"}}}
    rows = {row["check"]: row for row in readiness.readiness_checks(policy)}
    for name in ("provider-env", "provider-key"):
        assert rows[name]["status"] == "WARN"
        assert "provider_key_missing" in rows[name]["detail"]
        assert "named export" in rows[name]["detail"]


def test_admission_explains_the_stored_login_remedy_and_override(store, monkeypatch):
    install_store_env(store, monkeypatch)
    monkeypatch.setenv("OPENCODE_DB", str(store.path.with_name("absent.db")))
    policy = {"harness": "opencode", "provider_env": [VARIABLE]}
    invocations = Invocations(SimpleNamespace(execution_policy=lambda: (policy, None)),
                              roles=None)  # type: ignore[arg-type]
    state = {"invocations": {"INV-1": {"status": "active", "execution_profile": {
        "harness": "opencode", "provider": "openai", "model": "synthetic-model",
    }}}}
    with pytest.raises(HarnessIncompatible, match="opencode auth login openai.*API-key method") as missing:
        invocations.require_launchable(state, "INV-1", relaunch=False)
    assert missing.value.details["reason"] == "provider_key_missing"
    policy["containment"] = {"network": {"upstreams": {"openai": "http://127.0.0.1:1234"}}}
    with pytest.raises(HarnessIncompatible, match="used only with the built-in upstream") as override:
        invocations.require_launchable(state, "INV-1", relaunch=False)
    assert override.value.details["reason"] == "provider_env"


def test_refreshing_login_decides_for_both_readers_and_only_recommends_an_export(store, monkeypatch):
    install_store_env(store, monkeypatch)
    with sqlite3.connect(store.path) as con:
        con.execute("ALTER TABLE credential ADD COLUMN method_id TEXT")
    store.put("openai", 1, 10, {"type": "oauth", "access": SYNTHETIC, "expires": 1000})
    entries, why = login.stored(store.env)
    assert why is None and [(entry.integration, entry.kind) for entry in entries] == [("openai", "oauth")]
    keys, unavailable = login.worker_keys(store.env, {"openai"})
    assert keys == {} and unavailable == {"openai": login.REFRESHING_LOGIN}
    policy = {"harness": "opencode", "provider_env": [VARIABLE],
              "profiles": {"standard": {"provider": "openai", "model": "synthetic-model"}}}
    rows = {row["check"]: row for row in readiness.readiness_checks(policy)}
    issue = "the stored login is a refreshing (ChatGPT) login; set OPENAI_API_KEY"
    assert issue in rows["provider-key"]["detail"]
    invocations = Invocations(SimpleNamespace(execution_policy=lambda: (policy, None)),
                              roles=None)  # type: ignore[arg-type]
    state = {"invocations": {"INV-1": {"status": "active", "execution_profile": {
        "harness": "opencode", **policy["profiles"]["standard"],
    }}}}
    with pytest.raises(HarnessIncompatible) as caught:
        invocations.require_launchable(state, "INV-1", relaunch=False)
    assert issue in str(caught.value)
    assert "opencode auth login" not in str(caught.value) + repr(rows)
    assert SYNTHETIC not in str(caught.value) + repr(rows)


def test_a_two_provider_policy_with_both_logins_stored_starts_each_from_its_own_row(store, monkeypatch, tmp_path):
    install_store_env(store, monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store.put("anthropic", 1, 20, {"type": "key", "key": SYNTHETIC + "-SECOND"})
    names = [VARIABLE, "ANTHROPIC_API_KEY"]
    policy = {"harness": "opencode", "provider_env": names, "profiles": {
        provider: {"provider": provider, "model": "synthetic-model"} for provider in ("openai", "anthropic")
    }}
    invocations = Invocations(SimpleNamespace(execution_policy=lambda: (policy, None)),
                              roles=None)  # type: ignore[arg-type]
    rows = {row["check"]: row for row in readiness.readiness_checks(policy)}
    assert rows["provider-env"]["status"] == rows["provider-key"]["status"] == "PASS"
    assert readiness.readiness_findings(policy, admitted={"openai"}) == []
    for provider, profile in policy["profiles"].items():
        state = {"invocations": {"INV-1": {"status": "active", "execution_profile": {
            "harness": "opencode", **profile,
        }}}}
        admitted = invocations.require_launchable(state, "INV-1", relaunch=False)
        assert admitted["provider_key_admission"]["provider"] == provider
        own = netns.PROVIDER_KEY_ENV[provider]
        # The selected name is removed before server_env because the relay supplies it.
        env = server_env({}, tmp_path / provider, provider_env=[name for name in names if name != own],
                         config={}, password="synthetic-password", provider=provider)
        assert not set(names) & env.keys()


def test_allow_weaker_fallback_does_not_need_another_providers_export(tmp_path):
    names = [VARIABLE, "ANTHROPIC_API_KEY"]
    env = server_env({VARIABLE: SYNTHETIC}, tmp_path, provider_env=names, config={},
                     password="synthetic-password", provider="openai")
    assert env[VARIABLE] == SYNTHETIC and "ANTHROPIC_API_KEY" not in env


def test_a_custom_provider_run_keeps_todays_handling(tmp_path):
    names = [VARIABLE, "ANTHROPIC_API_KEY"]
    with pytest.raises(HarnessIncompatible, match="ANTHROPIC_API_KEY"):
        server_env({VARIABLE: SYNTHETIC}, tmp_path, provider_env=names, config={},
                   password="synthetic-password", provider="custom")


@pytest.mark.parametrize("between", ["rotate", "remove", "weaker"])
def test_each_launch_read_asks_only_for_the_pinned_provider(store, monkeypatch, tmp_path, between):
    install_store_env(store, monkeypatch)
    store.put("anthropic", 1, 20, {"type": "key", "key": SYNTHETIC + "-OTHER"})
    policy = {"harness": "opencode", "provider_env": [VARIABLE, "ANTHROPIC_API_KEY"],
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
        "provider": "openai", "provider_env": policy["provider_env"], "role": "implementer", "scope": "ticket",
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
