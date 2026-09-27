"""Harness building blocks in isolation (ADR-0009): bridge protocol, agent environment, supervisor
environment, adapter registry, run liveness, and credential rotation."""

from __future__ import annotations

import json
import os
import pickle
import time
from multiprocessing.connection import Client

import pytest

from aew import errors
from aew.engine.authority import issue_token, require_invocation, rotate_invocation_token
from aew.engine.harness_ops import supervisor_env
from aew.harness import agentenv, bridge, registry, runlog
from aew.harness import contract as K

CRED = "aew1.tk_0123456789abcdef." + "A" * 43


# ------------------------------------------------------------------ bridge protocol

@pytest.mark.parametrize("request_, code", [
    ({"op": "submit", "args": {"kind": "review", "text": "x", "invocation": "INV-9"}}, "USAGE"),
    ({"op": "whoami", "args": {}, "run": "R-INV-9-1"}, "USAGE"),
    ({"op": "whoami", "args": {"credential": CRED}}, "USAGE"),
    ({"op": "check.run", "args": {"check_id": 7}}, "USAGE"),
    ({"op": "lead.acquire", "args": {}}, "PERMISSION_DENIED"),
    ({"op": "invoke.create", "args": {}}, "PERMISSION_DENIED"),
    (["whoami"], "USAGE"),
])
def test_bridge_requests_are_exact_and_cannot_name_an_identity(request_, code):
    with pytest.raises(errors.AEWError) as exc:
        bridge.validate_request(request_)
    assert exc.value.code == code


def test_bridge_offers_exactly_three_operations():
    assert set(bridge.OPERATIONS) == {"whoami", "check.run", "submit"}
    assert bridge.validate_request({"op": "submit", "args": {"kind": "k", "text": "t"}}) == (
        "submit", {"kind": "k", "text": "t"})


def test_errors_cross_the_bridge_with_their_code_and_exit_status():
    err = bridge.rebuild_error(errors.StaleAuthority("rotated", run="R-1").to_dict())
    assert isinstance(err, errors.StaleAuthority) and err.exit_code == 3 and err.details == {"run": "R-1"}
    odd = bridge.rebuild_error({"code": "BRIDGE_ERROR", "message": "boom"})
    assert odd.code == "BRIDGE_ERROR" and odd.message == "boom"


def test_redaction_removes_any_credential_string():
    assert K.redact(f"token={CRED}; again {CRED}") == "token=aew1.<redacted>; again aew1.<redacted>"
    assert K.CREDENTIAL_RE.search(CRED)


@pytest.fixture
def server():
    calls = []

    def handler(op, args):
        calls.append((op, args))
        if op == "submit":
            raise errors.StaleAuthority(f"refused, credential {CRED} is dead")
        return {"echo": op, "secret_in_result": CRED}

    srv = bridge.BridgeServer(handler)
    srv.start()
    yield srv, calls
    srv.close()


def test_bridge_round_trip_redacts_and_refuses(server):
    srv, calls = server
    result = bridge.call("whoami", {}, endpoint=srv.address, key=srv.key_hex)
    assert result == {"echo": "whoami", "secret_in_result": "aew1.<redacted>"}
    with pytest.raises(errors.StaleAuthority) as exc:
        bridge.call("submit", {"kind": "k", "text": "t"}, endpoint=srv.address, key=srv.key_hex)
    assert "aew1.<redacted>" in exc.value.message and CRED not in exc.value.message
    assert [c[0] for c in calls] == ["whoami", "submit"] and (srv.requests, srv.refused) == (2, 1)


def test_bridge_refuses_a_foreign_key(server):
    srv, calls = server
    with pytest.raises(errors.PermissionDenied):
        bridge.call("whoami", {}, endpoint=srv.address, key=os.urandom(32).hex())
    assert not calls


class _Plant:
    """Unpickling this creates a file: proof of code execution inside the supervisor."""

    def __init__(self, path):
        self.path = path

    def __reduce__(self):
        return (open, (self.path, "w"))


def test_bridge_never_unpickles(server, tmp_path):
    srv, calls = server
    planted = tmp_path / "planted"
    family = "AF_PIPE" if srv.address.startswith("\\\\.\\pipe\\") else "AF_UNIX"
    conn = Client(srv.address, family=family, authkey=srv.key)
    conn.send_bytes(pickle.dumps(_Plant(str(planted))))
    reply = json.loads(conn.recv_bytes().decode("utf-8"))
    conn.close()
    assert reply["ok"] is False and reply["error"]["code"] == "USAGE"
    assert not planted.exists() and not calls


def test_a_closed_bridge_is_stale_authority(server):
    srv, _ = server
    srv.close()
    deadline = time.monotonic() + 10
    while True:
        try:
            bridge.call("whoami", {}, endpoint=srv.address, key=srv.key_hex)
        except errors.StaleAuthority:
            break
        assert time.monotonic() < deadline, "the bridge kept serving after close()"
        time.sleep(0.05)


# ------------------------------------------------------------------ environments

def test_agent_environment_is_an_allowlist():
    base = {"PATH": os.pathsep.join(["/usr/bin", "/bin"]), "HOME": "/home/u", "USERPROFILE": "C:/u",
            "SYSTEMROOT": "C:/Windows", "AEW_LEAD_TOKEN": CRED, "AEW_INVOCATION_TOKEN": CRED,
            "OPENAI_API_KEY": "sk-secret", "ANTHROPIC_API_KEY": "sk-ant", "OPENCODE_SERVER_PASSWORD": "pw",
            "AEW_HARNESS_ADAPTERS": "x=y:Z", "AEW_PAUSE": "p=f", "AWS_SECRET_ACCESS_KEY": "s", "GITHUB_TOKEN": "g"}
    env = agentenv.build(base, endpoint="ep", key_hex="ab", invocation="INV-1", run="R-INV-1-1", work_unit="T-1")
    assert not K.CREDENTIAL_RE.search(json.dumps(env))
    for leaked in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                   "OPENCODE_SERVER_PASSWORD", "AEW_HARNESS_ADAPTERS", "AEW_PAUSE", "AWS_SECRET_ACCESS_KEY",
                   "GITHUB_TOKEN"):
        assert leaked not in env
    assert env["AEW_AGENT_ENDPOINT"] == "ep" and env["AEW_RUN"] == "R-INV-1-1"
    assert env["PATH"].split(os.pathsep)[0] == os.path.dirname(__import__("sys").executable)


def test_supervisor_environment_drops_every_credential_bearing_variable():
    env = supervisor_env({"AEW_LEAD_TOKEN": CRED, "AEW_INVOCATION_TOKEN": CRED, "MY_SAVED_TOKEN": f"x {CRED}",
                          "AEW_AGENT_KEY": "k", "OPENAI_API_KEY": "sk", "PATH": "/bin"})
    assert env == {"OPENAI_API_KEY": "sk", "PATH": "/bin"}  # provider keys stay with the harness server side


# ------------------------------------------------------------------ registry

def test_registry_resolves_builtin_and_configured_adapters(monkeypatch, tmp_path):
    monkeypatch.delenv(registry.ENV, raising=False)
    assert set(registry.specs()) == {"opencode"}
    with pytest.raises(errors.HarnessIncompatible):
        registry.load("nope")
    mod = tmp_path / "adapter_mod.py"
    mod.write_text("from aew.harness.base import HarnessAdapter\n"
                   "class A(HarnessAdapter):\n"
                   "    name = 'a'\n"
                   "    def launch(self, c, e): return {}\n"
                   "    def inspect(self): return {'alive': False}\n"
                   "    def terminate(self): pass\n"
                   "class NotOne: pass\n", encoding="utf-8")
    monkeypatch.setenv(registry.ENV, f"a={mod}:A;bad={mod}:NotOne;missing={tmp_path / 'x.py'}:X")
    assert registry.load("a").name == "a"
    for name in ("bad", "missing"):
        with pytest.raises(errors.HarnessIncompatible):
            registry.load(name)


# ------------------------------------------------------------------ run liveness

def test_observed_status_and_liveness(tmp_path, monkeypatch):
    d = tmp_path / "R-INV-1-1"
    assert runlog.observed_status(d) == (K.UNCONFIRMED, None)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    assert runlog.may_be_live(d, now) and not runlog.may_be_live(d, old)  # unconfirmed: live only while fresh
    d.mkdir()
    runlog.write_record(d, {"status": K.RUNNING})
    assert runlog.observed_status(d)[0] == K.LOST  # no heartbeat
    runlog.beat(d)
    assert runlog.observed_status(d)[0] == K.RUNNING and runlog.may_be_live(d, old)
    monkeypatch.setattr(runlog, "STALE_AFTER_S", 0.0)
    time.sleep(0.01)
    assert runlog.observed_status(d)[0] == K.LOST and not runlog.may_be_live(d, now)
    runlog.write_record(d, {"status": K.TERMINATED, "credential": CRED})
    status, record = runlog.observed_status(d)
    assert status == K.TERMINATED and record["credential"] == "aew1.<redacted>"  # records are redacted on write


# ------------------------------------------------------------------ rotation

def _state():
    state = {"lead": {"generation": 1}, "tokens": {}, "invocations": {}}
    token = issue_token(state, "invocation", {"invocation_id": "INV-1", "role": "implementer", "work_unit": "T-1",
                                              "generation": 1})
    state["invocations"]["INV-1"] = {"status": "active", "token_id": token.split(".")[1], "role": "implementer",
                                     "work_unit": "T-1"}
    return state, token


def test_rotation_reissues_the_same_scope_and_kills_the_old_credential():
    state, old = _state()
    new = rotate_invocation_token(state, "INV-1", "rotated: R-INV-1-2")
    assert new != old and state["tokens"][new.split(".")[1]]["scope"] == state["tokens"][old.split(".")[1]]["scope"]
    assert require_invocation(state, new, "check.run")[0] == "INV-1"
    with pytest.raises(errors.StaleAuthority) as exc:
        require_invocation(state, old, "check.run")
    assert "rotated: R-INV-1-2" in exc.value.message
