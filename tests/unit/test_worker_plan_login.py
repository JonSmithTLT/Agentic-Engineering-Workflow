"""The worker plan path uses synthetic rows and a socketpair upstream."""

import json
import socket
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

from aew.engine import dispatch, harness_ops, readiness
from aew.engine.workspace_ops import Invocations
from aew.errors import HarnessIncompatible
from aew.harness import contract, model_list, runlog, steering_loop, supervisor
from aew.harness.containment import netns, relay
from aew.harness.opencode import adapter, capabilities, login
from tests.helpers.lead_session import CREDENTIAL_TABLE
from tests.unit.test_provider_relay import TIMEOUT, ProviderRelay, Seam, headers, read_head

PROFILE = {"profile": "impl", "provider": "openai", "credential": "plan_login"}
ACCESS = "synthetic-plan-access-1111"
EXPORT = "synthetic-unused-export-2222"


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "opencode.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE credential (integration_id, method_id, active, time_updated, value)")
    return {"HOME": str(tmp_path), "OPENCODE_DB": str(db), "OPENAI_API_KEY": EXPORT}


def put(env, value):
    with sqlite3.connect(env["OPENCODE_DB"]) as con:
        con.execute("INSERT INTO credential VALUES ('openai', 'chatgpt-browser', 1, 1, ?)", (json.dumps(value),))


def oauth(hours=120):
    return {"type": "oauth", "access": ACCESS, "expires": int((time.time() + hours * 3600) * 1000),
            "metadata": {"accountID": "synthetic-account"}}


@pytest.mark.parametrize(("value", "cause"), [
    (None, "missing"), ({"type": "key", "key": EXPORT}, "kind_changed"), ({"type": "other"}, "unknown_shape"),
])
def test_mismatch_refuses(store, monkeypatch, value, cause):
    monkeypatch.setattr(netns, "sys", SimpleNamespace(platform="linux"))
    if value is not None:
        put(store, value)
    policy = {"profiles": {"review": {"model": "openai/review"}}}
    with pytest.raises(HarnessIncompatible) as failure:
        netns.check_plan_login(PROFILE, policy, store, on_relay_route=True)
    assert failure.value.details["reason"] == f"plan_login_{cause}"
    assert ACCESS not in str(failure.value) and EXPORT not in str(failure.value)
    if cause == "kind_changed":
        assert "Profiles review on openai use an API key" in str(failure.value)


def test_plan_admission_records_only_the_provider_and_pot_and_explain_names_it(store, monkeypatch):
    put(store, oauth())
    monkeypatch.setattr(netns, "sys", SimpleNamespace(platform="linux"))
    for name in ("HOME", "OPENCODE_DB"):
        monkeypatch.setenv(name, store[name])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    policy = {"provider_env": ["OPENAI_API_KEY"]}
    invocations = Invocations(SimpleNamespace(execution_policy=lambda: (policy, None)), roles=None)
    pin = {**PROFILE, "harness": "opencode"}
    inv = {"execution_profile": pin, "status": "active", "token_id": "token-id"}
    inv_id = "INV-0001"
    state = {"invocations": {inv_id: inv}, "lead": {"generation": 1}}
    checked = invocations.require_launchable(state, inv_id, relaunch=False)
    expected = {"provider": "openai", "credential": "plan_login"}
    assert checked["provider_key_admission"] == expected
    invocations._record_launch_run(SimpleNamespace(state=state, refs=[]), inv_id)
    assert inv["runs"][0]["provider_key_admission"] == expected
    result = SimpleNamespace(facts={"inv": checked}, to_dict=lambda: {}, channel="lead")
    explainer = SimpleNamespace(k=SimpleNamespace(store=SimpleNamespace(current=lambda: state)),
                                decide=lambda *_args, **_kwargs: result)
    assert dispatch.Dispatch.explain(explainer, "harness.launch", "T-0001")["provider_key_source"] == "plan login"
    with pytest.raises(HarnessIncompatible, match="--profile <a plan_login profile>"):
        invocations._require_provider_key({**pin, "credential": "api_key", "rule": "lead:model"}, True)


def test_model_list_cache_keys_distinguish_the_usage_pots(tmp_path):
    binary = tmp_path / "binary"
    binary.write_bytes(b"fake")
    cls = SimpleNamespace(model_list_binary=lambda: binary, projected_config=lambda _: {})
    assert model_list.cache_key(cls, {}, PROFILE) != model_list.cache_key(cls, {}, {**PROFILE, "credential": "api_key"})


def test_plan_login_must_outlive_the_deadline(store, monkeypatch):
    monkeypatch.setattr(netns, "sys", SimpleNamespace(platform="linux"))
    put(store, oauth(hours=1))
    with pytest.raises(HarnessIncompatible, match="cannot cover this launch") as failure:
        netns.check_plan_login({**PROFILE, "deadline_s": 3600}, {}, store, on_relay_route=True)
    assert failure.value.details["reason"] == "plan_login_expired"


@pytest.mark.parametrize(("platform", "text"), [
    ("linux", "needs the provider relay on Linux"), ("win32", "isn't served on Windows yet"),
])
def test_plan_login_requires_a_relay(store, monkeypatch, platform, text):
    with monkeypatch.context() as patch:
        patch.setattr(netns, "sys", SimpleNamespace(platform=platform))
        with pytest.raises(HarnessIncompatible, match=text):
            netns.check_plan_login(PROFILE, {}, store, on_relay_route=False)


def test_policy_cannot_redirect_the_plan_relay(store):
    policy = {"containment": {"network": {"upstreams": {"openai": "http://127.0.0.1:9/backend-api/codex"}}}}
    with pytest.raises(HarnessIncompatible, match="override is set") as failure:
        netns.check_plan_login(PROFILE, policy, store, on_relay_route=True)
    assert failure.value.details["reason"] == "plan_login_override"


def test_a_plan_relaunch_refuses_an_override_adopted_after_the_pin(tmp_path):
    policy = {"containment": {"network": {"upstreams": {"openai": "http://127.0.0.1:9/backend-api/codex"}}}}
    with pytest.raises(HarnessIncompatible, match="override is set") as failure:
        supervisor.contain_launch(
            policy, adapter.OpenCodeAdapter, provider="openai", provider_env=[], role="implementer", scope="ticket",
            workspace=str(tmp_path), run_dir=tmp_path, scratch=str(tmp_path), bridge_dir=None, bridge=None,
            project=tmp_path, aew_root=tmp_path, kind="worker_run", execution_profile=PROFILE,
            key_admission={"provider": "openai", "credential": "plan_login"},
        )
    assert failure.value.details["reason"] == "plan_login_override"


@pytest.mark.parametrize("retryable", [False, True])
def test_worker_unreadable_refusal_preserves_retryability_without_host_details(store, monkeypatch, retryable):
    resolver = login.StoredLogin("openai", store)

    def unreadable():
        raise relay.Unavailable(store["OPENCODE_DB"], cause="unreadable", retryable=retryable)

    monkeypatch.setattr(resolver, "deciding_login", unreadable)
    with pytest.raises(relay.Unavailable) as failure:
        resolver.worker_grant()
    assert failure.value.cause == "unreadable"
    assert failure.value.retryable is retryable
    assert store["OPENCODE_DB"] not in str(failure.value)
    assert ("Try again" in str(failure.value)) is retryable


def test_an_unreadable_store_is_refused_at_admission(store, monkeypatch, tmp_path):
    monkeypatch.setattr(netns, "sys", SimpleNamespace(platform="linux"))
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database")
    with pytest.raises(HarnessIncompatible, match="stored login could not be read") as failure:
        netns.check_plan_login(PROFILE, {}, {**store, "OPENCODE_DB": str(bad)}, on_relay_route=True)
    assert failure.value.details["reason"] == "plan_login_unreadable"
    assert str(bad) not in str(failure.value) and "Try again" not in str(failure.value)


@pytest.mark.parametrize(("platform", "expected"), [("linux", "WARN"), ("win32", "FAIL")])
def test_doctor_distinguishes_conditional_and_unavailable_plan_routes(store, monkeypatch, platform, expected):
    put(store, oauth())
    monkeypatch.setattr(netns, "sys", SimpleNamespace(platform=platform))
    for name in ("HOME", "OPENCODE_DB"):
        monkeypatch.setenv(name, store[name])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    policy = {"profiles": {"impl": {"provider": "openai", "model": "synthetic-model", "credential": "plan_login"}},
              "harness": "opencode", "provider_env": ["OPENAI_API_KEY"], "containment": {"mode": "allow_weaker"}}
    rows = {row["check"]: row for row in readiness.readiness_checks(policy)}
    assert rows["provider-key"]["status"] == expected
    text = "shared with any Lead on the same login" if platform == "linux" else "Windows"
    assert text in rows["provider-key"]["detail"]
    assert "OPENAI_API_KEY" not in rows["provider-env"]["detail"]


def test_plan_relay_sends_only_the_resolved_login_and_does_not_fall_back(store, tmp_path, monkeypatch):
    put(store, oauth())
    monkeypatch.setattr(netns, "sys", SimpleNamespace(platform="linux"))
    seam = Seam()
    monkeypatch.setitem(netns.REFRESHING_UPSTREAMS, "openai", "http://fake.example/backend-api/codex")
    monkeypatch.setattr(netns, "listen", lambda _: None)
    monkeypatch.setattr(ProviderRelay, "start", lambda self: self)
    monkeypatch.setattr(relay, "ProviderRelay", lambda target, credentials, **options: ProviderRelay(
        target, credentials, connect=seam, head_timeout=TIMEOUT, **options))
    layout = SimpleNamespace(network=netns.PROXY_ONLY, net_dir=str(tmp_path / "net"))
    plan = netns.check_plan_login(PROFILE, {}, store, on_relay_route=True)
    network = netns.RunNetwork.start(layout, provider="openai", provider_env=["OPENAI_API_KEY"],
                                    policy={}, env=store, relay_needed=True, plan=plan)
    client, served = socket.socketpair()
    client.settimeout(TIMEOUT)
    thread = threading.Thread(target=network.relay.handle, args=(served,), daemon=True)
    thread.start()
    try:
        sentinel = network.login_sentinels["openai"]
        assert "OPENAI_API_KEY" not in network.harness_env({})
        assert network.leaks(ACCESS, EXPORT) == ["OPENAI_API_KEY", "openai login"]
        assert network.describe()["provider_key_source"] == "plan login"
        client.sendall(f"POST /backend-api/codex/probe HTTP/1.1\r\nHost: localhost\r\n"
                       f"Authorization: Bearer {sentinel}\r\nContent-Length: 0\r\n\r\n".encode())
        upstream = seam.upstream()
        head, _ = read_head(upstream)
        assert ("authorization", f"Bearer {ACCESS}") in headers(head)
        assert ("chatgpt-account-id", "synthetic-account") in headers(head)
        assert EXPORT.encode() not in head
        upstream.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        upstream.close()
        response, _ = read_head(client)
        assert response.startswith(b"HTTP/1.1 401 ")
        thread.join(TIMEOUT)
        assert not thread.is_alive()
        assert seam.calls == [("fake.example", 80)]
    finally:
        client.close()
        served.close()
        if seam.far is not None:
            seam.far.close()
        thread.join(TIMEOUT)
        network.close()


@pytest.mark.parametrize("case", [
    "match", "no_endpoint", "empty", "extra", "wrong_id", "wrong_access", "wrong_refresh",
])
def test_plan_credential_check_verifies_exactly_the_synthetic_row(case):
    row = {"id": "cred_aew_openai", "value": {"access": "synthetic-sentinel", "refresh": login.RELAY_NO_REFRESH}}
    if case == "wrong_id":
        row["id"] = "unexpected"
    if case in {"wrong_access", "wrong_refresh"}:
        row["value"][case.removeprefix("wrong_")] = "unexpected"
    items = [] if case == "empty" else [row, row] if case == "extra" else [row]
    tree = SimpleNamespace(network=SimpleNamespace(login_sentinels={"openai": "synthetic-sentinel"}))
    worker = SimpleNamespace(tree=tree, client=SimpleNamespace(get=lambda _: {"data": items}))
    spec = {"paths": {} if case == "no_endpoint" else {adapter.CREDENTIALS: {"get": {}}}}
    if case == "match":
        assert adapter.OpenCodeAdapter._stored_credentials(worker, spec) == 1
    else:
        with pytest.raises(HarnessIncompatible, match="could not verify"):
            adapter.OpenCodeAdapter._stored_credentials(worker, spec)


def test_old_run_end_without_cause_still_loads(tmp_path):
    old = {"schema": contract.RUN_SCHEMA, "status": contract.CRASHED, "reason": "old end"}
    (tmp_path / runlog.RECORD).write_text(json.dumps(old), encoding="utf-8")
    loaded = runlog.read_record(tmp_path)
    assert loaded == old
    assert contract.plan_login_failure(loaded.get("cause"), "openai", "INV-0001") is None


@pytest.mark.parametrize("cause", contract.PLAN_LOGIN_FAILURES)
def test_resolver_cause_reaches_a_failed_end_even_without_an_auth_reason(cause, tmp_path, monkeypatch):
    aew_root = tmp_path / ".aew"
    run = "R-INV-0001-1"
    directory = runlog.run_dir(aew_root, run)
    directory.mkdir(parents=True)
    record = {"execution_profile": PROFILE, "containment": {"network": {}}}
    network = SimpleNamespace(decisions=lambda: {"relay": {"credential:" + cause.removeprefix("plan_login_"): 1}},
                              refused=lambda: None, retryable_pending=lambda: True)
    worker = SimpleNamespace(
        inv_id="INV-0001", _ending=threading.Event(), _checks=SimpleNamespace(end=lambda: None),
        bridge=None, adapter=None,
        tree=SimpleNamespace(kill=lambda: None, network=network), weaker=None, run_dir=directory, record=record,
        _record_usage=lambda: None, _compare_effective=lambda: None, _evidence=lambda: [],
        _event=lambda *args, **kwargs: None, _drop_credential=lambda: None,
        _save=lambda: runlog.write_record(directory, record),
    )
    supervisor.Supervisor._end(worker, contract.CRASHED, "fake worker failed")
    ended = runlog.read_record(directory)
    assert ended["cause"] == cause and "reason_code" not in ended
    assert ended["reason"] == "fake worker failed"
    assert contract.PLAN_LOGIN_FAILURES[cause] in ended["next_action"]
    assert contract.PLAN_LOGIN_FAILURES[cause] in harness_ops._headline(run, contract.CRASHED, ended)
    state = {"invocations": {"INV-0001": {
        "status": "active", "token_id": "token-id", "execution_profile": PROFILE,
        "work_unit": "T-0001", "runs": [{"run": run, "token_id": "token-id"}],
    }}}
    loop = SimpleNamespace(aew_root=aew_root, engine=SimpleNamespace(store=SimpleNamespace(current=lambda: state)),
                           _closed=threading.Event(), _snapshot=lambda: None, _authority_lost=lambda: None)
    monkeypatch.setattr(steering_loop.S, "effective", lambda _: {"mode": "run"})
    stop = steering_loop.SteeringLoop.tick(loop, SimpleNamespace())
    assert stop.code == steering_loop.PLAN_LOGIN_FAILED and stop.attention
    assert contract.PLAN_LOGIN_FAILURES[cause] in stop.message
    assert f"aew harness launch INV-0001 {contract.EXPECT_REV}" in stop.message
    assert "aew invoke cancel INV-0001" in stop.message
    if cause.endswith("_retryable"):
        assert "Wait until the store is available" in stop.message and "auth login" not in stop.message
        network.retryable_pending = lambda: False
        supervisor.Supervisor._end(worker, contract.CRASHED, "unrelated failure after recovery")
        assert "cause" not in record and record["reason"] == "unrelated failure after recovery"


def test_seed_is_built_once_and_only_private_copies_hold_sentinels(tmp_path, monkeypatch):
    monkeypatch.setattr(capabilities, "PLAN_LOGIN_QUALIFIED_VERSIONS", capabilities.TESTED_VERSIONS)
    commands = []

    def spawn(argv, *, env, **_):
        commands.append(argv[1:])
        if argv[1:] == ["--version"]:
            return SimpleNamespace(returncode=0, communicate=lambda **_: (capabilities.TESTED_VERSIONS[0], ""))
        db = login.db_path(env)
        db.parent.mkdir(parents=True)
        with sqlite3.connect(db) as con:
            con.execute(CREDENTIAL_TABLE)
        return SimpleNamespace(returncode=0, communicate=lambda **_: ("", ""))

    harness = tmp_path / ".aew" / "local" / "harness"
    for name in ("run-one", "run-two"):
        run = harness / "runs" / name
        state = run / "harness"
        state.mkdir(parents=True)
        data = state / "xdg-data"
        worker = SimpleNamespace(tree=SimpleNamespace(spawn=spawn), run_dir=run, state_dir=state,
                                 directory=str(tmp_path))
        adapter.OpenCodeAdapter._seed_plan_login(worker, ["fake-opencode"], {"XDG_DATA_HOME": str(data)},
                                                "openai", name + "-sentinel")
        with sqlite3.connect(data / "opencode" / login.DB) as con:
            row_id, value = con.execute("SELECT id, value FROM credential").fetchone()
        assert row_id == "cred_aew_openai"
        assert json.loads(value)["access"] == name + "-sentinel"
    assert commands.count(["session", "list"]) == 1
    seed, = (harness / "plan-login-seeds").glob("*.db")
    with sqlite3.connect(seed) as con:
        assert con.execute("SELECT id FROM credential").fetchall() == []


def test_a_missing_seed_is_a_named_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(capabilities, "PLAN_LOGIN_QUALIFIED_VERSIONS", capabilities.TESTED_VERSIONS)
    run = tmp_path / "runs" / "run"
    state = run / "harness"
    state.mkdir(parents=True)
    worker = SimpleNamespace(
        run_dir=run, state_dir=state, directory=str(tmp_path),
        tree=SimpleNamespace(spawn=lambda *args, **kwargs: SimpleNamespace(
            returncode=0, communicate=lambda **_: (capabilities.TESTED_VERSIONS[0], ""))),
    )
    with pytest.raises(HarnessIncompatible, match="could not prepare") as failure:
        adapter.OpenCodeAdapter._seed_plan_login(worker, ["fake-opencode"], {}, "openai", "synthetic-sentinel")
    assert failure.value.details["reason"] == "plan_login_seed"


def test_seed_refuses_an_unqualified_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(capabilities, "PLAN_LOGIN_QUALIFIED_VERSIONS", capabilities.TESTED_VERSIONS)
    monkeypatch.setattr(capabilities, "TESTED_VERSIONS", ("2.3.0",))
    worker = SimpleNamespace(
        state_dir=tmp_path, directory=str(tmp_path),
        tree=SimpleNamespace(spawn=lambda *args, **kwargs: SimpleNamespace(
            returncode=0, communicate=lambda **_: ("v2.3.0", ""))),
    )
    with pytest.raises(HarnessIncompatible, match="binary is not qualified") as failure:
        adapter.OpenCodeAdapter._seed_plan_login(worker, ["fake-opencode"], {}, "openai", "synthetic-sentinel")
    assert failure.value.details["reason"] == "plan_login_version"
