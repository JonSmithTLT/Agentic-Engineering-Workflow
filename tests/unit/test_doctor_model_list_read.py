"""`aew doctor`'s read of the model list, without a server: a weaker read enters the register of weaker contexts as a
launch does, and its server is given the marker (G3 addendum 7; register E153), and the adapter's answer on a catalog
that settled with nothing to offer (review of #367). The sandbox, the process tree and the server are stood in for."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew.errors import HarnessLaunchFailed
from aew.harness import containment, model_list, procs
from aew.harness import weaker_register as W
from aew.harness.containment import netns
from aew.harness.opencode import adapter as A


class _Tree:
    def __init__(self, **_: Any) -> None:
        pass

    def kill(self) -> None:
        pass

    def survivors(self) -> list[int]:
        return []


def test_a_weaker_model_list_read_is_live_in_the_register_while_it_runs_and_its_server_carries_the_marker(
        tmp_path, monkeypatch):
    """The read goes through the launch's own `contain_launch`; a stand-in adapter sees what its server would get."""
    seen: list[dict[str, Any]] = []

    class Adapter(A.OpenCodeAdapter):
        def __init__(self, *_: Any) -> None:
            pass

        def read_model_list(self, contract: Any, agent_env: dict[str, str], *, until: float) -> dict[str, Any]:
            marker = Path(agent_env[W.MARKER])
            seen.append({"marker": marker, "label": json.loads(marker.read_text(encoding="utf-8")),
                         "live": [e["kind"] for e in W.read().live], "run_dir": Path(contract.run_dir)})
            return {"version": "stand-in", "complete": True, "empty": False, "models": []}

    weaker = containment.label(contained=False, reason="the execution policy allows weaker runs")
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, weaker))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")  # an owner that held the whole tree
    monkeypatch.setattr(netns, "provider_key_missing", lambda *a, **kw: None)
    monkeypatch.setattr(procs, "ProcessTree", _Tree)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew", repo_root=tmp_path)
    pin = {"harness": "opencode", "provider": "fakeprov", "model": "fake-model"}
    out = model_list.read(engine, {}, pin, Adapter)
    [given] = seen
    assert out["complete"]
    assert given["marker"] == given["run_dir"] / "label.json" and given["label"] == weaker, "its marker names its label"
    assert "doctor_model_list" in given["live"], "entered before its server started"
    assert "doctor_model_list" not in [e["kind"] for e in W.read().live], "ended once the read returned"
    [ended] = [json.loads(f.read_text(encoding="utf-8")) for f in W.root().glob("doctor_model_list-*.json")]
    assert ended["outcome"] == "clean"
    assert not given["run_dir"].exists()


def test_a_model_list_reads_relay_records_the_policy_sha_its_pin_was_resolved_from(tmp_path, monkeypatch):
    """The read's containment gets the pin's ``policy_sha256``, the sha of the policy read that resolved it, for its
    relay's record (review of #542, m3)."""
    from aew.harness import supervisor

    given: list[str | None] = []
    real = supervisor.contain_launch

    def spy(*args: Any, **kw: Any) -> Any:
        given.append(kw.get("policy_sha256"))
        return real(*args, **kw)

    class Adapter(A.OpenCodeAdapter):
        def __init__(self, *_: Any) -> None:
            pass

        def read_model_list(self, contract: Any, agent_env: dict[str, str], *, until: float) -> dict[str, Any]:
            return {"version": "stand-in", "complete": True, "empty": False, "models": []}

    monkeypatch.setattr(supervisor, "contain_launch", spy)
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, containment.label(contained=False, reason="x")))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")
    monkeypatch.setattr(netns, "provider_key_missing", lambda *a, **kw: None)
    monkeypatch.setattr(procs, "ProcessTree", _Tree)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew", repo_root=tmp_path)
    pin = {"harness": "opencode", "provider": "fakeprov", "model": "fake-model", "policy_sha256": "ef" * 32}
    model_list.read(engine, {}, pin, Adapter)
    assert given == ["ef" * 32]


def test_a_server_that_fails_to_start_is_waited_for_once_across_profiles(tmp_path, monkeypatch):
    """Review of E137, F3: a harness that cannot start is the same answer for every profile of its provider."""
    tries: list[str] = []

    class Adapter(A.OpenCodeAdapter):
        def __init__(self, *_: Any) -> None:
            pass

        def read_model_list(self, contract: Any, agent_env: dict[str, str], *, until: float) -> dict[str, Any]:
            tries.append(contract.execution_profile["model"])
            raise HarnessLaunchFailed("the stand-in server did not start")

    def resolve(policy: dict[str, Any], sha: str, *, request: dict[str, str], **_: Any) -> dict[str, Any]:
        return {"harness": "opencode", "provider": "fakeprov", "model": policy["profiles"][request["profile"]]}

    monkeypatch.setattr(containment, "establish", lambda **kw: (None, containment.label(contained=False, reason="x")))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")
    monkeypatch.setattr(netns, "provider_key_missing", lambda *a, **kw: None)
    monkeypatch.setattr(procs, "ProcessTree", _Tree)
    monkeypatch.setattr(model_list.X, "resolve", resolve)
    monkeypatch.setattr(model_list.registry, "load", lambda harness: Adapter)
    monkeypatch.setattr(model_list, "cache_key", lambda cls, policy, pin: pin["model"])
    policy = {"profiles": {"one": "first-model", "two": "second-model"}}
    engine = SimpleNamespace(aew_root=tmp_path / ".aew", repo_root=tmp_path, execution_policy=lambda: (policy, "sha"))
    row = next(r for r in model_list.doctor_rows(engine) if r["check"] == model_list.CHECK)
    assert tries == ["first-model"], tries
    assert row["status"] == "FAIL" and "the stand-in server did not start" in row["detail"], row
    assert "profile two: the same harness and provider as profile one, not waited for again" in row["detail"], row


def test_a_profile_a_list_already_read_names_is_answered_by_it_after_a_sibling_waited(tmp_path, monkeypatch):
    """E133's review, m9: the list that names it is in hand, so there is nothing to wait for."""
    tries: list[str] = []

    class Adapter(A.OpenCodeAdapter):
        def __init__(self, *_: Any) -> None:
            pass

        def read_model_list(self, contract: Any, agent_env: dict[str, str], *, until: float) -> dict[str, Any]:
            tries.append(contract.execution_profile["model"])
            raise HarnessLaunchFailed("the stand-in server did not start")

    def resolve(policy: dict[str, Any], sha: str, *, request: dict[str, str], **_: Any) -> dict[str, Any]:
        return {"harness": "opencode", "provider": "fakeprov", "model": policy["profiles"][request["profile"]]}

    monkeypatch.setattr(containment, "establish", lambda **kw: (None, containment.label(contained=False, reason="x")))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")
    monkeypatch.setattr(netns, "provider_key_missing", lambda *a, **kw: None)
    monkeypatch.setattr(procs, "ProcessTree", _Tree)
    monkeypatch.setattr(model_list.X, "resolve", resolve)
    monkeypatch.setattr(model_list.registry, "load", lambda harness: Adapter)
    monkeypatch.setattr(model_list, "cache_key", lambda cls, policy, pin: pin["model"])
    root = tmp_path / ".aew"
    cache = root / model_list.CACHE_REL
    cache.parent.mkdir(parents=True)
    listed = [{"providerID": "fakeprov", "id": m, "variants": [], "enabled": True} for m in ("model-a", "model-c")]
    cache.write_text(json.dumps({"model-a": {"read_at": "2026-11-08T00:00:00Z", "version": "1", "complete": True,
                                             "models": listed}}), encoding="utf-8")
    policy = {"profiles": {"a": "model-a", "b": "model-b", "c": "model-c"}}
    engine = SimpleNamespace(aew_root=root, repo_root=tmp_path, execution_policy=lambda: (policy, "sha"))
    row = next(r for r in model_list.doctor_rows(engine) if r["check"] == model_list.CHECK)
    assert tries == ["model-b"], tries
    assert "profile b: the harness did not start" in row["detail"] and "profile c" not in row["detail"], row


class _Catalog:
    def __init__(self, models: list[dict[str, Any]]) -> None:
        self.models = models

    def get(self, *_: Any) -> dict[str, Any]:
        return {"data": self.models}


def _reading(models: list[dict[str, Any]], *, relayed: bool) -> A.OpenCodeAdapter:
    adapter = A.OpenCodeAdapter.__new__(A.OpenCodeAdapter)
    adapter._start_server = lambda *a, **kw: None  # type: ignore[method-assign]
    adapter._probe_version = lambda: ("stand-in", None)  # type: ignore[method-assign]
    adapter.client = _Catalog(models)  # type: ignore[assignment]
    adapter.server = SimpleNamespace(close=lambda wait_s: None)  # type: ignore[assignment]
    adapter.directory = "."
    adapter._relayed = relayed
    return adapter


@pytest.mark.parametrize(("models", "relayed"), [
    ([], False),
    # A relayed catalog can hold only the entry AEW's own projection made up: the server does not offer it.
    ([{"providerID": "fakeprov", "id": "fake-model", "name": "fake-model"}], True)],
    ids=["nothing listed", "only what the relay projection named"])
def test_a_catalog_that_settled_with_nothing_to_offer_is_empty_and_never_complete(monkeypatch, models, relayed):
    """The adapter's half of review of #367, F1: `read` turns this answer into its red row, and only a complete list is
    cached, so an answer that said complete here would be cached as a lasting one."""
    monkeypatch.setattr(A, "CATALOG_WAIT_S", -1.0)  # the wait has run out: settled
    contract = SimpleNamespace(execution_profile={"provider": "fakeprov", "model": "fake-model"})
    out = _reading(models, relayed=relayed).read_model_list(contract, {}, until=A.time.monotonic() + 60)
    assert out["complete"] is False and out["empty"] is True and out["models"] == []


@pytest.mark.parametrize("started", [False, True])
def test_a_failure_caught_after_the_start_deadline_is_the_deadline_row_and_names_its_cause(tmp_path, monkeypatch,
                                                                                        started):
    """Review of the start-deadline fix, M1 and M2: a real failure caught once the deadline passed keeps its cause in
    the deadline row, and the row sends the operator to the catalog's network only if the server had started."""

    class Adapter(A.OpenCodeAdapter):
        def __init__(self, *_: Any) -> None:
            pass

        def read_model_list(self, contract: Any, agent_env: dict[str, str], *, until: float) -> dict[str, Any]:
            if started:
                self.server = SimpleNamespace()  # type: ignore[assignment]  (a server that came up, then failed)
            raise OSError("synthetic spawn failure")

    monkeypatch.setenv("AEW_RUN_START_S", "0")  # the deadline has passed by the time the stand-in fails
    monkeypatch.setattr(containment, "establish", lambda **kw: (None, containment.label(contained=False, reason="x")))
    monkeypatch.setattr(W, "ownership_of", lambda label: "subreaper")
    monkeypatch.setattr(netns, "provider_key_missing", lambda *a, **kw: None)
    monkeypatch.setattr(procs, "ProcessTree", _Tree)
    engine = SimpleNamespace(aew_root=tmp_path / ".aew", repo_root=tmp_path)
    pin = {"harness": "opencode", "provider": "fakeprov", "model": "fake-model"}
    with pytest.raises(model_list._Unread) as unread:
        model_list.read(engine, {}, pin, Adapter)
    detail = str(unread.value)
    assert "the model list was not read within 0s, a launch's own start deadline (AEW_RUN_START_S)" in detail, detail
    assert "(what ended it: OSError: synthetic spawn failure)" in detail, detail
    assert ("the harness's model catalog" in detail) is started, detail
    assert ("had not started by then, so raise AEW_RUN_START_S" in detail) is not started, detail
    assert unread.value.red and unread.value.waited


@pytest.mark.parametrize(("provider", "plan", "header", "value"), [
    ("anthropic", False, "x-api-key", "synthetic-sentinel"),
    ("google", False, "x-goog-api-key", "synthetic-sentinel"),
    ("openai", True, "Authorization", "Bearer synthetic-sentinel"),
    ("opencode", False, "Authorization", "Bearer synthetic-sentinel"),
])
def test_models_probe_uses_the_providers_credential_header(provider, plan, header, value, monkeypatch):
    from contextlib import nullcontext

    from aew.harness import doctor_relay
    from aew.harness.opencode import capabilities

    sent = []

    class Connection:
        def request(self, method, path, *, headers):
            sent.append((method, path, headers))

        def getresponse(self):
            return nullcontext(SimpleNamespace(status=200, getheader=lambda _: None))

        def close(self):
            pass

    monkeypatch.setattr(doctor_relay, "UnixConnection", lambda path, timeout: Connection())
    service = SimpleNamespace(upstream=SimpleNamespace(path="/base"), listener=SimpleNamespace(getsockname=lambda: "x"),
                              counts=lambda: {})
    network = SimpleNamespace(lead=False, relay=service,
                              login_sentinels={provider: "synthetic-sentinel"} if plan else {},
                              sentinels={} if plan else {netns.PROVIDER_KEY_ENV[provider]: "synthetic-sentinel"})

    row = doctor_relay.request(network, provider, route="test", source="test", until=doctor_relay.time.monotonic() + 5)
    [request] = sent
    method, path, headers = request
    assert method == "GET" and path == "/base/models" + (f"?client_version={capabilities.TESTED_VERSIONS[0]}" if plan
                                                        else "")
    assert headers[header] == value and (headers.get("anthropic-version") == "2023-06-01") == (provider == "anthropic")
    assert row["status"] == "PASS" and "synthetic-sentinel" not in str(row)
