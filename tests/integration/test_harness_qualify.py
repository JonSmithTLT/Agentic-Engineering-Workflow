"""tools/harness_qualify, the harness qualification tool (a developer tool): its harness-neutral core against a stub
pack, its scripted model, and its OpenCode pack against the fake OpenCode server. The run against the real binary
(regenerating the pinned 2.0.18 fixtures exactly) is the live lane's: tests/live/test_harness_qualify_live.py."""

from __future__ import annotations

import ast
import errno
import http.client
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import fake_opencode
import pytest
from sleep_patch import patch_sleep

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "harness_qualify"
FIXTURES = ROOT / "tests" / "fixtures" / "opencode"
if str(TOOL.parent) not in sys.path:
    sys.path.append(str(TOOL.parent))

import harness_qualify as HQ  # noqa: E402
from harness_qualify import core, model  # noqa: E402
from harness_qualify import opencode as OC  # noqa: E402

# ------------------------------------------------------------------------------------------------- the stub pack


class StubPack:
    """A second harness that is not OpenCode: its own version rule, checks, capabilities, pin and fixture."""

    harness = "stubharness"
    version_source = None

    def __init__(self, behaviour: dict[str, Any]) -> None:
        self.behaviour = behaviour

    def declared(self) -> dict[str, dict[str, Any]]:
        yes = {"status": "yes", "how": "stub"}
        return {"cap_ok": yes, "cap_broken": yes, "cap_vm": yes, "cap_untested": yes,
                "cap_gap": {"status": "gap", "how": "not in this harness", "register": "F99"}}

    def read_version(self, binary: Path, work: Path, env: dict[str, str]) -> str:
        assert env["HOME"].startswith(str(work)) and "STUB_API_KEY" not in env  # the core's private environment
        return binary.read_text(encoding="utf-8").split()[-1]

    def checks(self) -> list[core.Check]:
        b = self.behaviour

        def ok(ctx: core.Context) -> core.Outcome:
            return core.Outcome(core.PASS, {"stub.answer": b["answer"], "stub.version": ctx.version})

        def broken(ctx: core.Context) -> core.Outcome:
            raise RuntimeError("the stub harness crashed")

        def host_fails(ctx: core.Context) -> core.Outcome:
            return core.Outcome(core.FAIL, notes=["the host's own result"])

        checks = [core.Check("stub.ok", ok, ("cap_ok", "cap_gap")),
                  core.Check("stub.vm", ok, ("cap_vm",), platform=core.VM),
                  core.Check("stub.other", ok, ("not_declared",), depth=core.API),
                  core.Check("stub.host", host_fails, scope=core.HOST)]
        if b.get("broken", True):
            checks.insert(1, core.Check("stub.broken", broken, ("cap_broken",)))
        return checks

    def pinned(self, fixtures: Path) -> tuple[str, dict[str, Any]]:
        return "1.0", {**json.loads((fixtures / "stub-1.0.json").read_text(encoding="utf-8")), "stub.feeling": "fine"}

    def render(self, version: str, facts: Any, fixtures: Path) -> dict[str, tuple[bytes | None, str]]:
        keys = ("stub.answer", "stub.version")
        made = core.dump({k: facts[k] for k in keys}) if all(k in facts for k in keys) else None
        return {f"stub-{version}.json": (made, "measured")}

    def unmeasured(self) -> dict[str, str]:
        return {"stub.feeling": "a person's, not a run's"}

    def adoptable(self, facts: Any, pinned: Any) -> list[str]:
        return []


def stub_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: int, **behaviour: Any) -> tuple[Any, ...]:
    monkeypatch.setattr(core, "has_bubblewrap", lambda: False)  # this host's answer is not the test's
    monkeypatch.setenv("STUB_API_KEY", "synthetic-must-not-pass")
    binary = tmp_path / "stub-binary"
    binary.write_text("stubharness 1.0", encoding="utf-8")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(exist_ok=True)
    (fixtures / "stub-1.0.json").write_bytes(core.dump({"stub.answer": 42, "stub.version": "1.0"}))
    return HQ.run(StubPack({"answer": answer, **behaviour}), binary, out=tmp_path / "out", fixtures=fixtures,
                  only=behaviour.get("only"))


def test_the_core_runs_a_second_harness_pack_and_assumes_nothing_of_opencode(tmp_path, monkeypatch):
    record, diff, fixtures, _ = stub_run(tmp_path, monkeypatch, 42)
    by = {r["id"]: r for r in record.checks}
    assert (record.harness, record.version) == ("stubharness", "1.0")
    assert record.binary_sha256 == core.sha256_file(tmp_path / "stub-binary")
    assert by["stub.ok"]["status"] == core.PASS
    assert by["stub.broken"]["status"] == core.ERROR and "the stub harness crashed" in by["stub.broken"]["notes"][0]
    assert by["stub.vm"]["status"] == core.SKIPPED and "bubblewrap" in by["stub.vm"]["notes"][0]
    assert diff.clean and diff.not_measured == {"stub.feeling": "a person's, not a run's"}
    assert fixtures == [{"fixture": "stub-1.0.json", "status": "identical", "how": "measured"}]
    # The core's own modules name no harness: every harness fact is a pack's (``__init__.pack_for`` is the registry).
    for name in ("core.py", "model.py", "neutral.py"):
        tree = ast.parse((TOOL / name).read_text(encoding="utf-8"))
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)] + \
                  [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [m for m in imports if "opencode" in m or "codex" in m], (name, imports)
    assert "opencode" not in (TOOL / "core.py").read_text(encoding="utf-8").lower()


def test_a_declared_capability_with_no_check_is_unchecked_and_a_broken_one_fails(tmp_path, monkeypatch):
    record, *_ = stub_run(tmp_path, monkeypatch, 42)
    caps = {k: v["status"] for k, v in record.capabilities.items()}
    assert caps == {"cap_ok": core.PASS, "cap_broken": core.FAIL, "cap_vm": core.SKIPPED,
                    "cap_untested": core.UNCHECKED, "cap_gap": "gap", "not_declared": "undeclared"}
    # a declared gap reads as a gap with its register row, even where a check covers it
    assert record.capabilities["cap_gap"]["register"] == "F99"
    # a pass says how deep it looked
    assert record.capabilities["cap_ok"]["depth"] == core.BEHAVIOUR and record.capabilities["cap_vm"]["depth"] is None


def test_a_changed_fact_appears_in_the_diff_and_the_fixture_differs(tmp_path, monkeypatch):
    """The ablation: the stub measures 41 where the pin says 42."""
    _, diff, fixtures, _ = stub_run(tmp_path, monkeypatch, 41)
    assert diff.lines()[0] == "~ stub.answer: 42 -> 41"
    assert fixtures[0]["status"] == "differs"


def test_the_private_environment_passes_no_credential_proxy_or_home(tmp_path):
    base = {"PATH": "/bin", "HOME": "/home/operator", "XDG_DATA_HOME": "/home/operator/.local/share",
            "OPENAI_API_KEY": "x", "GITHUB_TOKEN": "x", "HTTPS_PROXY": "http://proxy", "AEW_HOME": "x",
            "OPENCODE_CONFIG": "x", "SOME_SECRET": "x", "LANG": "C.UTF-8"}
    env = core.private_env(tmp_path, base, harness="opencode")
    dropped = {"OPENAI_API_KEY", "GITHUB_TOKEN", "HTTPS_PROXY", "AEW_HOME", "OPENCODE_CONFIG", "SOME_SECRET"}
    assert not dropped & set(env)
    for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
                 "APPDATA", "LOCALAPPDATA", "TMPDIR", "TEMP", "TMP"):
        assert Path(env[name]).is_relative_to(tmp_path), name
    assert env["PATH"] == "/bin" and "127.0.0.1" in env["NO_PROXY"]


@pytest.mark.parametrize("observation", ["not verified: an external route exists",
                                      "NOT blocked: a connection out succeeded under --unshare-net",
                                      "not verified: external-egress observation failed (TimeoutError)"])
def test_unverified_isolation_starts_no_binary_or_model(tmp_path, monkeypatch, observation):
    monkeypatch.setenv(core.NETWORK_BLOCKED_ENV, "1")
    monkeypatch.setattr(core, "network_state", lambda: observation)
    pack = StubPack({"answer": 42})
    monkeypatch.setattr(pack, "read_version", lambda *a: pytest.fail("started the binary before verifying isolation"))
    binary = tmp_path / "binary"
    binary.touch()
    with pytest.raises(core.NetworkIsolationError, match="not verified|NOT blocked"):
        core.qualify(pack, binary, out=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_verified_isolation_is_observed_before_version_and_preserved_in_the_record(tmp_path, monkeypatch):
    order = []
    verified = "blocked: run under bwrap --unshare-net (verified: loopback only, no external route, egress denied)"
    monkeypatch.setenv(core.NETWORK_BLOCKED_ENV, "1")

    def observe():
        order.append("isolation")
        return verified

    monkeypatch.setattr(core, "network_state", observe)
    pack = StubPack({"answer": 42, "broken": False})

    def version(*args):
        assert order == ["isolation"]
        order.append("version")
        return "1.0"

    monkeypatch.setattr(pack, "read_version", version)
    binary = tmp_path / "binary"
    binary.touch()
    record = core.qualify(pack, binary, out=tmp_path / "out", only=["stub.ok"])
    assert record.network == verified and order == ["isolation", "version"]


@pytest.mark.parametrize(("interfaces", "route", "denial", "expected"), [
    (["lo"], "", errno.ENETUNREACH, "blocked:"),
    (["lo"], "", errno.EHOSTUNREACH, "blocked:"),
    (["lo", "eth0"], "", errno.ENETUNREACH, "not verified: interfaces"),
    (["lo"], "eth0 00000000 01000000", errno.ENETUNREACH, "not verified: an external route"),
    (["lo"], "", errno.ETIMEDOUT, "not verified: external-egress"),
    (["lo"], "", None, "NOT blocked:"),
])
def test_network_verification_requires_all_observations(monkeypatch, interfaces, route, denial, expected):
    monkeypatch.setenv(core.NETWORK_BLOCKED_ENV, "1")
    monkeypatch.setattr(core.sys, "platform", "linux")

    def read(path, **kwargs):
        if path.name == "dev":
            return "header\nheader\n" + "\n".join(n + ": 0" for n in interfaces)
        return "header\n" + route if path.name == "route" else ""

    monkeypatch.setattr(Path, "read_text", read)
    original = core.socket.create_connection

    def connect(address, **kwargs):
        if address[0] == "192.0.2.1":
            if denial is not None:
                raise OSError(denial, "scripted denial")
            return original(listener.getsockname(), **kwargs)
        return original(address, **kwargs)

    # A passing external connection is also planted without ever making an external request.
    with core.socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        monkeypatch.setattr(core.socket, "create_connection", connect)
        assert core.network_state().startswith(expected)


# ---------------------------------------------------------------------------------------------- the scripted model

def _sse(llm: Any, body: dict[str, Any]) -> list[dict[str, Any]]:
    conn = http.client.HTTPConnection(llm.base_url.split("//")[1].split("/")[0], timeout=10)
    conn.request("POST", "/v1/responses", json.dumps(body), {"Content-Type": "application/json"})
    text = conn.getresponse().read().decode()
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_the_scripted_model_calls_the_offered_tool_and_reports_the_usage_it_was_given():
    usage = {"input_tokens": 9, "input_tokens_details": {"cached_tokens": 4}, "output_tokens": 3,
             "output_tokens_details": {"reasoning_tokens": 1}}
    llm = model.start("responses", [{"call": ["shell", "write"], "arguments": {"$path": "/w/a.txt"}, "usage": usage}])
    try:
        tools = [{"type": "function", "name": "write", "parameters": {"properties": {"filePath": {}, "content": {}}}}]
        events = _sse(llm, {"model": "m", "stream": True, "tools": tools, "input": []})
        aux = _sse(llm, {"model": "m", "stream": True, "input": []})  # a title request: no tools
        conn = http.client.HTTPConnection(llm.base_url.split("//")[1].split("/")[0], timeout=10)
        conn.request("GET", "/v1/responses", headers={"Upgrade": "websocket", "Connection": "Upgrade"})
        assert conn.getresponse().status == 501
    finally:
        llm.close()
    call = next(e["item"] for e in events if e["type"] == "response.output_item.done")
    assert (call["type"], call["name"], json.loads(call["arguments"])) == ("function_call", "write",
                                                                         {"filePath": "/w/a.txt"})
    assert events[-1]["response"]["usage"] == {**usage, "total_tokens": 12}
    assert aux[-1]["response"]["usage"]["input_tokens"] == 0
    assert llm.upgrades == 1 and [r["main"] for r in llm.requests if r["method"] == "POST"] == [True, False]
    assert all("Authorization" not in json.dumps(r) or r["auth"] in ("present", "absent") for r in llm.requests)


def test_scripted_parallel_calls_have_distinct_identity_and_output_indexes():
    llm = model.ResponsesModel([])
    try:
        events = llm._events({"calls": [
            {"call": ["shell"], "arguments": {"command": "first"}},
            {"call": ["shell"], "arguments": {"command": "second"}}]}, {"shell": {}}, {})
    finally:
        llm.close()
    calls = [e for e in events if e["type"] == "response.output_item.done"]
    assert [e["output_index"] for e in calls] == [0, 1]
    assert len({e["item"]["call_id"] for e in calls}) == 2
    assert [json.loads(e["item"]["arguments"])["command"] for e in calls] == ["first", "second"]
    assert events[-1]["response"]["output"] == [e["item"] for e in calls]
    assert [e["sequence_number"] for e in events] == list(range(len(events)))


@pytest.mark.serial
def test_the_scripted_response_pauses_at_a_tool_owned_gate():
    import threading

    entered, release = threading.Event(), threading.Event()
    llm = model.start("responses", [{"text": "released", "entered": entered, "release": release}])
    result = []
    worker = threading.Thread(target=lambda: result.extend(_sse(llm, {"tools": [{"name": "shell"}]})))
    try:
        worker.start()
        assert entered.wait(5) and not result
        release.set()
        worker.join(5)
        assert not worker.is_alive() and result[-1]["response"]["output"][0]["content"][0]["text"] == "released"
    finally:
        release.set()
        worker.join(5)
        llm.close()


@pytest.mark.parametrize("name", ["steer_boundary", "queue_boundary"])
def test_messaging_boundaries_have_passing_controls_and_each_fact_can_fail(tmp_path, monkeypatch, name):
    from harness_qualify import messaging

    expected = {key: True for keys in messaging.BOUNDARY_FACTS.values() for key in keys}
    measured = dict(expected)
    monkeypatch.setattr(messaging, "boundary_measurement", lambda ctx: dict(measured))

    def check():
        ctx = core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6")
        return next(c for c in OC.OpenCodePack(FIXTURES).checks() if c.id == "messaging." + name).run(ctx)

    assert check().status == core.PASS
    for key in messaging.BOUNDARY_FACTS[name]:
        measured = {**expected, key: False}
        outcome = check()
        assert outcome.status == core.FAIL and outcome.notes == [key]
        measured = {k: v for k, v in expected.items() if k != key}
        assert check().status == core.FAIL  # missing evidence cannot pass either


@pytest.mark.parametrize("name", ["prompt_identity", "held_resume"])
def test_messaging_identity_and_hold_checks_fail_each_unsafe_observation(tmp_path, monkeypatch, name):
    from harness_qualify import messaging

    expected = {mode + "." + key: True for mode in ("steer", "queue")
                for key in (*messaging.IDENTITY_FACTS, *messaging.HELD_FACTS)}
    measured = dict(expected)
    monkeypatch.setattr(messaging, "identity_measurement", lambda ctx: dict(measured))

    def check():
        ctx = core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6")
        return next(c for c in OC.OpenCodePack(FIXTURES).checks() if c.id == "messaging." + name).run(ctx)

    assert check().status == core.PASS
    keys = messaging.IDENTITY_FACTS if name == "prompt_identity" else messaging.HELD_FACTS
    for mode in ("steer", "queue"):
        for key in keys:
            key = mode + "." + key
            measured = {**expected, key: False}
            outcome = check()
            assert outcome.status == core.FAIL and outcome.notes == [key]
            measured = {k: v for k, v in expected.items() if k != key}
            assert check().status == core.FAIL


@pytest.mark.parametrize(("responses", "expected", "calls"), [
    ([(200, {"id": "msg_1"})], "admitted", 1),
    ([(404, {"_tag": "MessageNotFoundError"})], "pending", 1),
    ([(404, {"_tag": "SessionNotFoundError"})], "session_lost", 1),
    ([(404, {}), (200, {"id": "session"})], "pending", 2),
    ([(404, {}), (404, {})], "session_lost", 2),
    ([(404, {"_tag": "Unknown"}), (503, {})], "unknown", 2),
    ([(503, {})], "unknown", 1),
])
def test_messaging_admission_never_promotes_untagged_or_missing_results(monkeypatch, responses, expected, calls):
    from harness_qualify import messaging

    seen = []
    replies = iter(responses)

    def request(server, method, path):
        seen.append((method, path))
        return next(replies)

    monkeypatch.setattr(messaging, "http", request)
    assert messaging.admission(None, "session", "msg_1") == expected
    assert len(seen) == calls
    if calls == 2:
        assert seen[-1] == ("GET", "/api/session/session")


def test_session_loss_check_fails_each_unsafe_observation(tmp_path, monkeypatch):
    from harness_qualify import messaging

    expected = {mode + "." + key: True for mode in ("steer", "queue") for key in messaging.LOSS_FACTS}
    measured = dict(expected)
    monkeypatch.setattr(messaging, "loss_measurement", lambda ctx: dict(measured))
    ctx = core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6")
    assert messaging.loss_check(ctx).status == core.PASS
    for key in expected:
        measured = {**expected, key: False}
        out = messaging.loss_check(ctx)
        assert out.status == core.FAIL and out.notes == [key]


def binding_events():
    def frame(kind, **values):
        return {"type": "session." + kind, "data": {"sessionID": "ses_1", "assistantMessageID": "step_1", **values}}

    return [frame("step.started"), frame("tool.input.started", id="call_1", name="shell"),
            frame("tool.called", id="call_1"), frame("tool.input.started", id="call_2", name="shell"),
            frame("tool.called", id="call_2"), frame("tool.failed", id="call_2"),
            frame("tool.success", id="call_1"), frame("step.ended"), frame("execution.succeeded")]


@pytest.mark.parametrize("mutation", ["none", "missing_call", "misbound_call", "misbound_end", "missing_end",
                                     "early_step_end", "early_execution_end", "missing_execution_end",
                                     "no_parallel", "no_failure", "no_success", "no_reconnect", "same_process",
                                     "no_process_observation"])
def test_wait_binding_check_uses_scripted_event_identity_and_order(tmp_path, monkeypatch, mutation):
    from harness_qualify import messaging

    events = binding_events()
    if mutation == "missing_call":
        events.pop(2)
    elif mutation == "misbound_call":
        events[2]["data"]["assistantMessageID"] = "other_step"
    elif mutation == "misbound_end":
        events[7]["data"]["assistantMessageID"] = "other_step"
    elif mutation == "missing_end":
        events.pop(7)
    elif mutation == "early_step_end":
        events.insert(5, events.pop(7))
    elif mutation == "early_execution_end":
        events.insert(5, events.pop(8))
    elif mutation == "missing_execution_end":
        events.pop(8)
    elif mutation == "no_parallel":
        events.insert(3, events.pop(6))
    elif mutation == "no_failure":
        events[5]["type"] = "session.tool.success"
    elif mutation == "no_success":
        events[6]["type"] = "session.tool.failed"

    def measure(ctx):
        return {**messaging.binding_facts(events), "short_call_ends_before_step": True,
                "real_shell_child_started": True, "distinct_shell_child": mutation != "same_process",
                "process_observation": None if mutation == "no_process_observation" else {
                    "child_alive_after_timeout": True, "parent_alive_after_timeout": False},
                "stream_drop_and_reconnect": mutation != "no_reconnect"}

    monkeypatch.setattr(messaging, "binding_measurement", measure)
    outcome = messaging.binding_check(core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6"))
    assert outcome.status == (core.PASS if mutation == "none" else core.FAIL), outcome


@pytest.mark.parametrize(("default", "short", "default_stopped", "short_stopped", "status"), [
    (120, 1, True, True, core.PASS), (60, 1, True, True, core.PASS),
    (30, 1, True, True, core.FAIL), (float("nan"), 1, True, True, core.FAIL),
    (120, 120, True, True, core.FAIL), (120, 1, False, True, core.FAIL),
    (120, 1, True, False, core.FAIL), (True, 1, True, True, core.FAIL),
])
def test_shell_timeout_check_cannot_claim_an_unmeasured_or_unsafe_budget(
        tmp_path, monkeypatch, default, short, default_stopped, short_stopped, status):
    from harness_qualify import messaging

    monkeypatch.setattr(messaging, "timeout_measurement", lambda ctx: {
        "default_seconds": default, "short_seconds": short, "default_stopped_before_completion": default_stopped,
        "short_stopped_before_completion": short_stopped})
    out = messaging.timeout_check(core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6"))
    assert out.status == status
    if status == core.PASS:
        assert 0 < out.facts["measurement.shell_timeout"]["maximum_safe_wait_seconds"] <= min(90, default - 30)


def test_the_messaging_pack_has_all_seven_behaviour_checks_and_no_enum_substitute():
    checks = [c for c in OC.OpenCodePack(FIXTURES).checks() if c.id.startswith("messaging.")]
    assert [c.id for c in checks] == ["messaging." + name for name in (
        "steer_boundary", "queue_boundary", "prompt_identity", "held_resume", "session_loss", "wait_binding",
        "shell_timeout")]
    assert all(c.depth == core.BEHAVIOUR and c.measures == (c.id,) for c in checks)


@pytest.mark.parametrize(("mutation", "name"), [
    ("none", "steer_boundary"), ("none", "queue_boundary"),
    ("model_admission", "steer_boundary"), ("model_cancelled", "steer_boundary"),
    ("shell_admission", "steer_boundary"), ("shell_cancelled", "steer_boundary"),
    ("shell_failed", "steer_boundary"), ("tool_output_truncated", "steer_boundary"), ("steer_late", "steer_boundary"),
    ("steer_reordered", "steer_boundary"), ("queue_early", "queue_boundary"),
    ("queue_reordered", "queue_boundary"), ("queue_overtakes", "queue_boundary"),
])
def test_boundary_checks_fail_raw_transcript_and_request_violations(tmp_path, monkeypatch, mutation, name):
    from harness_qualify import messaging

    ids = {n: "msg_" + n for n in ("initial", "s1", "s2", "q1", "q2")}
    users = list(ids.values())
    following = "HQ_s1 HQ_s2 HQ_FOREGROUND_COMPLETED"
    during_model, during_shell = set(), set()
    started = completed = True
    exits = [0]
    if mutation == "model_admission":
        during_model.add(ids["s1"])
    elif mutation == "model_cancelled":
        started = False
    elif mutation == "shell_admission":
        during_shell.add(ids["s1"])
    elif mutation == "shell_cancelled":
        completed = False
    elif mutation == "shell_failed":
        exits = [137]
    elif mutation == "tool_output_truncated":
        following = "HQ_s1 HQ_s2"
    elif mutation == "steer_late":
        following = "HQ_s1"
    elif mutation == "steer_reordered":
        users[1:3] = reversed(users[1:3])
    elif mutation == "queue_early":
        following += " HQ_q1"
    elif mutation == "queue_reordered":
        users[3:5] = reversed(users[3:5])
    elif mutation == "queue_overtakes":
        users = [ids[n] for n in ("initial", "q1", "s1", "s2", "q2")]
    monkeypatch.setattr(messaging, "boundary_measurement", lambda ctx: messaging.boundary_facts(
        ids, during_model, during_shell, set(), users, following, started, completed, exits))
    ctx = core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6")
    assert messaging.boundary_check(ctx, name).status == (core.PASS if mutation == "none" else core.FAIL)


class MessagingServerSeam:
    """Deterministic raw server-result seam for the qualifier, not the worker adapter's fake V2 fidelity claim."""

    def __init__(self, llm, mutation):
        self.client = self
        self.llm = llm
        self.mutation = mutation
        self.sessions = {}
        self.items = {}
        self.owners = {}

    def get(self, path, params=None):
        if path == "/api/model":
            return {"data": [{"id": OC.MODEL}]}
        if path == "/api/session/active":
            return {"data": {}}
        if path.endswith("/message"):
            return {"data": list(self.sessions[path.split("/")[3]])}
        return {"id": path.split("/")[3]}

    def post(self, path, body):
        if path == "/api/session":
            sid = "session_" + str(len(self.sessions))
            self.sessions[sid] = []
            return {"id": sid}
        return self.request("POST", path, body)[1]

    def delete(self, path):
        self.sessions.pop(path.split("/")[3])

    def request(self, method, path, body=None):
        pieces = path.split("/")
        sid = pieces[3]
        if method == "GET":
            if sid not in self.sessions:
                return 404, {"_tag": "MessageNotFoundError" if self.mutation == "lost_as_message" else
                             "SessionNotFoundError"}
            if len(pieces) == 4:
                return 200, {"id": sid}
            message = next((m for m in self.sessions[sid] if m["id"] == pieces[-1]), None)
            if message is not None:
                return 200, message
            if self.mutation == "false_admission":
                return 200, {"id": pieces[-1]}
            return 404, {"_tag": "SessionNotFoundError" if self.mutation == "message_as_lost" else
                         "MessageNotFoundError"}
        mid = body["id"]
        if mid in self.owners and self.owners[mid] != sid:
            return (200, self.items[mid]) if self.mutation == "conflict_accepted" else (409, {"_tag": "ConflictError"})
        duplicate = mid in self.items
        if duplicate and self.mutation in ("changed_pending_accepted", "changed_admitted_accepted"):
            admitted = any(m["id"] == mid for m in self.sessions[sid])
            if (admitted and self.mutation == "changed_admitted_accepted") or (
                    not admitted and self.mutation == "changed_pending_accepted"):
                self.items[mid] = {**self.items[mid], "payload": body}
        if not duplicate:
            self.owners[mid] = sid
            self.items[mid] = {"id": mid, "sessionID": sid, "type": "user", "delivery": body.get("delivery", "steer"),
                               "time": {"created": len(self.items)}, "payload": dict(body)}
        if body.get("resume") is not False or (duplicate and self.mutation == "retry_wakes"):
            self.llm.requests.append({"main": True})
            pending = [item for key, item in self.items.items() if self.owners[key] == sid and not any(
                m["id"] == key for m in self.sessions[sid])]
            if self.mutation == "wake_first":
                pending.reverse()
            for item in pending:
                payload = item["payload"]
                self.sessions[sid].append({"type": "user", "id": item["id"], "text": payload["text"],
                                           "metadata": {} if self.mutation == "metadata_dropped" else
                                           payload.get("metadata", {})})
        item = self.items[mid]
        admitted = duplicate and any(m["id"] == mid for m in self.sessions[sid])
        if admitted and self.mutation == "envelope_defaults":
            item = {**item, "payload": {**item["payload"], "agents": [], "files": [], "skills": []}}
        elif admitted and self.mutation == "admitted_time_changed":
            item = {**item, "time": {"created": item["time"]["created"] + 1}}
        elif admitted and self.mutation == "admitted_mode_changed":
            item = {**item, "delivery": "queue" if item["delivery"] == "steer" else "steer"}
        return 200, item


@pytest.mark.parametrize(("mutation", "name"), [
    ("none", "prompt_identity"), ("none", "held_resume"), ("metadata_dropped", "prompt_identity"),
    ("changed_pending_accepted", "prompt_identity"), ("changed_admitted_accepted", "prompt_identity"),
    ("conflict_accepted", "prompt_identity"), ("retry_wakes", "held_resume"), ("wake_first", "held_resume"),
    ("envelope_defaults", "prompt_identity"), ("admitted_time_changed", "prompt_identity"),
    ("admitted_mode_changed", "prompt_identity"),
    ("false_admission", "prompt_identity"), ("none", "session_loss"),
    ("message_as_lost", "session_loss"), ("lost_as_message", "session_loss"),
])
def test_messaging_checks_fail_scripted_server_payload_and_admission_violations(tmp_path, monkeypatch, mutation, name):
    import contextlib
    from types import SimpleNamespace

    from harness_qualify import messaging

    llm = SimpleNamespace(requests=[], base_url="http://127.0.0.1:1/v1", close=lambda: None)
    server = MessagingServerSeam(llm, mutation)
    monkeypatch.setattr(messaging.model, "start", lambda *a: llm)
    monkeypatch.setattr(OC, "serve", lambda *a, **k: contextlib.nullcontext(server))
    monkeypatch.setattr(messaging, "http", lambda srv, method, path, body=None: srv.request(method, path, body))
    patch_sleep(monkeypatch, messaging)
    ctx = core.Context(tmp_path / "binary", tmp_path, {}, "2.2.6")
    check = next(c for c in OC.OpenCodePack(FIXTURES).checks() if c.id == "messaging." + name)
    result = check.run(ctx)
    assert result.status == (core.PASS if mutation in ("none", "envelope_defaults") else core.FAIL), result


def test_messaging_semantics_render_pin_and_diff_without_overwriting_unrelated_fixtures(tmp_path):
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    pack = OC.OpenCodePack(fixtures)
    fact = {"messaging.steer_boundary": {"steer_fifo": True}}
    rendered = pack.render("2.2.6", fact, fixtures)
    payload, _ = rendered["messaging-2.2.6.json"]
    assert payload == core.dump({"harness": "opencode", "version": "2.2.6", "facts": fact})
    assert not {"openapi-2.2.6.min.json", "tool-parts-2.2.6.json", "store-2.2.6.json"} & set(rendered)
    path = fixtures / "messaging-2.2.6.json"
    path.write_bytes(payload)
    _, pinned = pack.pinned(fixtures)
    assert pinned["messaging.steer_boundary"] == fact["messaging.steer_boundary"]
    changed = {"messaging.steer_boundary": {"steer_fifo": False}}
    assert core.fact_diff(changed, pinned).lines()[0] == "~ messaging.steer_boundary.steer_fifo: true -> false"


def test_the_initial_linux_messaging_record_retains_failures_and_never_claims_binding_support():
    path = FIXTURES / "messaging-2.2.6-linux-initial.json"
    raw = path.read_bytes()
    doc = json.loads(raw)
    assert core.sha256_file(path) == "49c36810fd43a45e0fa45d3ffccd86f6aea4fc9868a11fa5a29cebe10a2113a7"
    assert doc["facts"]["record.public_copy"]["raw_record_digest"] == (
        "bb28a742b7d2395b6bdfdab05d1925de37a1b54beab31b4b8978deea0e605132")
    assert doc["schema"] == core.SCHEMA and doc["verdict"]["binary"] == core.FAIL
    assert doc["version"] == "2.2.6" and doc["platform"] == "linux"
    assert doc["aew_revision"] == "1e5de25752e89ee76d320d82f51a2e13e6631d90"
    assert doc["binary_sha256"] == "50503d24577fa4117a7c95ee85b2cd679606a87eacf20ca54ed5db5c9e1cf895"
    assert doc["network"] == ("blocked: run under bwrap --unshare-net "
                              "(verified: loopback only, no external route, egress denied)")
    selected = {r["id"]: r["status"] for r in doc["checks"] if r["status"] != core.SKIPPED}
    assert len(selected) == 10 and [k for k, v in selected.items() if v == core.FAIL] == [
        "messaging.prompt_identity", "messaging.held_resume"]
    assert all(v == core.PASS for k, v in selected.items() if k not in (
        "messaging.prompt_identity", "messaging.held_resume"))
    assert doc["capabilities"]["report_step_and_shell_calls"]["status"] == "gap"
    timeout = doc["facts"]["measurement.shell_timeout"]
    assert 0 < timeout["maximum_safe_wait_seconds"] <= min(90, timeout["default_seconds"] - 30)
    assert doc["facts"]["openapi.min"] == json.loads((FIXTURES / "openapi-2.2.6.min.json").read_text(encoding="utf-8"))
    assert not any(word in raw.decode() for word in ("/home/", "/mnt/", "C:\\Users", "AEW-plans", "AEW-reviews"))


def test_the_corrected_linux_record_preserves_the_post_admission_response_contradiction():
    path = FIXTURES / "messaging-2.2.6-linux.json"
    raw = path.read_bytes()
    doc = json.loads(raw)
    assert core.sha256_file(path) == "29ef41ae1ce5e73cc8c6b2dd1a03b379b48eacc3e2e0bb4543ae937c7a432ef2"
    assert doc["schema"] == core.SCHEMA and doc["verdict"]["binary"] == core.FAIL
    assert doc["aew_revision"] == "e1be99c878ed321eb11d029e842af0ea33d81d6c"
    assert doc["platform"] == "linux" and doc["version"] == "2.2.6"
    assert "verified: loopback only, no external route, egress denied" in doc["network"]
    assert sum(r["status"] == core.PASS for r in doc["checks"]) == 9
    assert [r["id"] for r in doc["checks"] if r["status"] == core.FAIL] == ["messaging.prompt_identity"]
    assert doc["capabilities"]["report_step_and_shell_calls"]["status"] == "gap"
    facts = doc["facts"]
    assert facts["record.public_copy"]["raw_record_digest"] == (
        "97b6ce4147051e1de6099a689e97635acb64b753ea392b6058194359b274efc4")
    for mode in ("steer", "queue"):
        measured = facts["measurement.prompt_identity"][mode]
        first, retried, changed = (measured[k] for k in ("first", "admitted_retry", "admitted_changed"))
        assert measured["admitted_retry_status"] == measured["admitted_changed_status"] == 200
        assert retried["time"]["created"] != first["time"]["created"]
        assert retried["delivery"] == first["delivery"] == mode
        assert changed["delivery"] != first["delivery"]
        assert first["id"] == retried["id"] == changed["id"]
        assert first["sessionID"] == retried["sessionID"] == changed["sessionID"]
        assert first["payload"] == retried["payload"] == changed["payload"]
        assert facts["messaging.held_resume"][mode + ".staged_first"] is True
    assert not any(word in raw.decode() for word in ("/home/", "/mnt/", "C:\\Users", "AEW-plans", "AEW-reviews"))


# --------------------------------------------------------------------------------- the OpenCode pack, offline parts

def test_the_pinned_fixtures_layouts_are_reproduced_from_their_own_data():
    """The pack writes each fixture as the pinned one is laid out, so a regeneration is byte for byte."""
    usage = (FIXTURES / "usage-2.0.18-openai.json").read_bytes()
    assert (OC._render_json(json.loads(usage)) + "\n").encode() == usage
    pinned = (FIXTURES / "openapi-2.0.18.min.json").read_bytes()
    spec = json.loads(pinned)
    trimmed = OC.trim(spec, version="2.0.18", full_sha256=spec["x-aew-fixture"]["full_sha256"])
    assert core.dump(trimmed) == pinned  # the trimming is the pin's: trimming the trimmed document changes nothing


def test_the_pinned_usage_is_disjoint_and_a_changed_stored_count_is_not():
    cases = json.loads((FIXTURES / "usage-2.0.18-openai.json").read_text(encoding="utf-8"))["cases"]
    assert OC.classify(cases) == "disjoint"
    cases[0]["stored"]["input"] += cases[0]["raw"]["input_tokens_details"]["cached_tokens"]  # input counted inclusive
    assert OC.classify(cases) == "unknown"


def test_a_doctored_pin_shows_the_changed_fact_in_the_diff(tmp_path):
    """The ablation through the pack's own pin reader: one stored count changed in a copy of the fixtures."""
    doctored = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, doctored)
    path = doctored / f"usage-{OC.C.TESTED_VERSIONS[0]}-openai.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    was = doc["cases"][0]["stored"]["input"]
    doc["cases"][0]["stored"]["input"] = was + 1
    path.write_text(json.dumps(doc), encoding="utf-8")
    pack = OC.OpenCodePack(FIXTURES)
    _, measured = pack.pinned(FIXTURES)
    _, pinned = pack.pinned(doctored)
    assert core.fact_diff(measured, pinned).lines() == [f"~ usage.openai.cases[0].stored.input: {was + 1} -> {was}"]


def test_the_feed_gives_the_version_and_each_files_digest():
    text = ("version: 9.8.7\nfiles:\n  - url: opencode-desktop-linux-x86_64.rpm\n    sha512: c2hhNTEy\n"
            "    size: 123\npath: opencode-desktop-linux-x86_64.rpm\n")
    feed = OC.Feed(fetch=lambda url: text)
    assert feed.latest() == [core.Release("9.8.7", OC.FEED.rsplit("/", 1)[0] + "/opencode-desktop-linux-x86_64.rpm",
                                          "c2hhNTEy", "sha512", 123)]


def test_every_capability_opencode_declares_is_reported_and_the_checks_split_by_platform():
    pack = OC.OpenCodePack(FIXTURES)
    checks = pack.checks()
    keyed = {c for check in checks for c in check.capabilities}
    assert keyed <= set(pack.declared())
    assert {"attach_to_operator_session", "mark_non_operator_input"} == set(pack.declared()) - keyed  # unchecked
    assert [c.id for c in checks if c.platform == core.VM] == ["containment.self_test"]


# ----------------------------------------------------------------------------- the OpenCode pack, fake server

API_CHECKS = ["api.openapi", "api.wake_idle_session", "api.queue_until_turn_end", "api.steer_running_turn",
              "api.interrupt_turn", "api.read_model_list", "usage.live_citations", "ripgrep.download"]


def fake_binary(tmp_path: Path, knobs: dict[str, Any] | None = None) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "default.json").write_text(json.dumps({"steps": [], "server": knobs or {}}), encoding="utf-8")
    return fake_opencode.write_launcher(tmp_path / "bin", scripts)


def test_the_opencode_pack_against_the_fake_server_measures_its_api_and_names_what_it_cannot(tmp_path):
    record, diff, fixtures, _ = HQ.run(OC.OpenCodePack(FIXTURES), fake_binary(tmp_path), out=tmp_path / "out",
                                       fixtures=FIXTURES, only=API_CHECKS)
    by = {r["id"]: r["status"] for r in record.checks}
    assert record.version == OC.C.TESTED_VERSIONS[0]
    assert {k: by[k] for k in API_CHECKS[:6]} == dict.fromkeys(API_CHECKS[:6], core.PASS)
    # the fake is not the build the citations were read from: not comparable, never a pass or a changed fact
    assert by["usage.live_citations"] == core.SKIPPED and by["ripgrep.download"] == core.FAIL
    assert diff.not_measured["live_usage.bundle_identifiers"].startswith("usage.live_citations skipped: not comparable")
    assert by["usage.openai"] == core.SKIPPED  # not selected: never reported as passed
    # The fake serves the pinned trimmed document, so the trimming reproduces it; only the full document's hash
    # (which the fake cannot have) differs.
    changed = [d for d in diff.changed if d.fact == "openapi.min"]
    assert [d.path for d in changed] == [".x-aew-fixture.full_sha256"]
    assert record.capabilities["read_progress"]["status"] == core.SKIPPED
    assert record.capabilities["attach_to_operator_session"]["status"] == core.UNCHECKED
    assert "login.oauth_shape" in record.unmeasured


def test_an_operation_the_served_api_drops_fails_its_capability_and_shows_in_the_diff(tmp_path):
    """The ablation through a served document: the fake drops session.interrupt."""
    binary = fake_binary(tmp_path, {"openapi_drop": ["POST /api/session/{sessionID}/interrupt"]})
    record, diff, *_ = HQ.run(OC.OpenCodePack(FIXTURES), binary, out=tmp_path / "out", fixtures=FIXTURES,
                              only=["api.openapi", "api.interrupt_turn"])
    assert record.capabilities["interrupt_turn"]["status"] == core.FAIL
    assert "- openapi.min.paths./api/session/{sessionID}/interrupt: " in "\n".join(diff.lines())
    assert "operation POST /api/session/{sessionID}/interrupt is missing" in record.facts["openapi.problems"]


def test_the_cli_writes_the_record_diff_and_report(tmp_path):
    out = tmp_path / "out"
    code = HQ_main(["--binary", str(fake_binary(tmp_path)), "--out", str(out), "--only", "api.openapi"])
    record = json.loads((out / "record.json").read_text(encoding="utf-8"))
    assert code == 1  # the fake's full-document hash differs from the pin's
    assert record["schema"] == core.SCHEMA and record["harness"] == "opencode" and record["binary_sha256"]
    assert (out / "diff.txt").read_text(encoding="utf-8").startswith("~ openapi.min.x-aew-fixture.full_sha256")
    assert "Capabilities (declared by the adapter):" in (out / "report.txt").read_text(encoding="utf-8")


def HQ_main(argv: list[str]) -> int:  # noqa: N802
    import importlib

    return importlib.import_module("harness_qualify.__main__").main(argv)


SKIPPING = "import pytest\n\ndef test_a():\n    pass\n\n@pytest.mark.skip('{}')\ndef test_b():\n    pass\n"


@pytest.mark.parametrize(("body", "status"), [
    ("def test_a():\n    pass\n", core.PASS),
    (SKIPPING.format("needs a model"), core.SKIPPED),
    (SKIPPING.format("the driver cannot drive this"), core.PASS),  # a skip the pack names as the driver's own limit
    ("def test_a():\n    assert False\n", core.FAIL),
])
def test_a_suite_run_with_any_skip_is_reported_skipped_never_passed(tmp_path, monkeypatch, body, status):
    from harness_qualify import neutral

    monkeypatch.setattr(neutral, "agents_aew", lambda env: "this tree")  # CI's install; a developer's may differ
    suite = tmp_path / "suite" / "test_suite.py"
    suite.parent.mkdir()
    suite.write_text(body, encoding="utf-8")
    ctx = core.Context(binary=tmp_path / "bin", work=tmp_path / "work", env=core.private_env(tmp_path / "env"),
                       version="1")
    out = neutral._pytest(ctx, "STUB_BIN", [str(suite)], ["--rootdir", str(suite.parent)],
                          allowed_skips={r"^the driver cannot drive": 1} if "cannot drive" in body else {})
    assert out.status == status, out.notes


def test_in_the_binary_the_citations_were_read_from_a_missing_identifier_fails(tmp_path):
    binary = tmp_path / "bundle.bin"
    binary.write_bytes(b"...yield*e.project(hd,(i)=>Pc(r))...")
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    cite = "opencode-cli 9.9.9 (bundled JavaScript)"
    doc = {"source": {"binary_sha256": core.sha256_file(binary), "evidence": [
        {"id": "E1", "file": cite, "identifier": "yield*e.project(hd,(i)=>Pc(r))"},
        {"id": "E2", "file": cite, "identifier": "session.step.ended"},
        {"id": "E3", "file": "packages/core/src/x.ts", "lines": "1-2"}]}}  # a source citation: carried, not searched
    (fixtures / "live-usage-9.9.9.json").write_text(json.dumps(doc), encoding="utf-8")
    ctx = core.Context(binary=binary, work=tmp_path / "w", env={}, version="9.9.9")
    out = OC.check_live_usage_citations(ctx, fixtures, "9.9.9")
    assert (out.status, out.facts, out.notes) == (core.FAIL, {"live_usage.bundle_identifiers": {"E1": True,
                                                                                               "E2": False}},
                                                  ["not in this binary: E2"])


def test_the_login_store_is_pinned_to_the_credential_table_aew_owns():
    from aew.harness.opencode import login

    _, pinned = OC.OpenCodePack(FIXTURES).pinned(FIXTURES)
    assert pinned["login.store"]["schema"] == [list(c) for c in login.CREDENTIAL_SCHEMA]
    # every column AEW's SQL names is one of the table's
    assert set(login.CREDENTIAL_COLUMNS) <= {name for name, _ in pinned["login.store"]["schema"]}


# ------------------------------------------------------------------- verdicts, exit codes and the published record


def test_a_host_check_never_decides_the_binarys_verdict_or_exit_code(tmp_path, monkeypatch):
    record, diff, fixtures, adopt = stub_run(tmp_path, monkeypatch, 42, broken=False)
    assert core.verdict(record, diff) == {"binary": core.PASS, "host": core.FAIL}
    assert core.exit_code(record, diff) == core.EXIT_OK
    assert "[host result, not the binary's]" in core.report(record, diff, fixtures, adopt)


def test_an_only_id_that_is_no_check_is_a_usage_error_never_a_clean_run(tmp_path, monkeypatch):
    with pytest.raises(core.UnknownCheck, match="stub.okk"):
        stub_run(tmp_path, monkeypatch, 42, only=["stub.okk"])
    code = HQ_main(["--binary", str(fake_binary(tmp_path)), "--out", str(tmp_path / "o"), "--only", "api.opneapi"])
    assert code == core.EXIT_USAGE and not (tmp_path / "o" / "record.json").exists()


def test_a_run_where_no_binary_check_ran_says_nothing_was_qualified(tmp_path, monkeypatch):
    record, diff, *_ = stub_run(tmp_path, monkeypatch, 42, only=["stub.vm", "stub.host"])  # skipped off the VM; host
    assert core.verdict(record, diff)["binary"] == core.NOT_RUN
    assert core.exit_code(record, diff) == core.EXIT_NOTHING_RAN


def test_the_published_record_carries_the_diff_as_data_the_revision_and_the_network_state(tmp_path, monkeypatch):
    monkeypatch.delenv(core.NETWORK_BLOCKED_ENV, raising=False)
    record, diff, fixtures, adopt = stub_run(tmp_path, monkeypatch, 41)
    doc = core.document(record, diff, fixtures, adopt)
    assert doc["schema"] == core.SCHEMA and doc["verdict"]["binary"] == core.FAIL
    assert doc["diff"]["changed"] == [{"fact": "stub.answer", "path": "", "pinned": 42, "measured": 41,
                                       "kind": "changed"}]
    assert doc["diff"]["lines"][0] == "~ stub.answer: 42 -> 41"
    assert doc["network"].startswith("not blocked") and "aew_revision" in doc
    json.dumps(doc)  # publishable as it is


def test_a_server_that_names_no_version_is_refused_never_recorded_as_none(tmp_path, monkeypatch):
    import contextlib

    class Server:
        class client:  # noqa: N801
            @staticmethod
            def get(path: str) -> dict[str, Any]:
                return {"version": None}

    monkeypatch.setattr(OC, "serve", lambda *a, **k: contextlib.nullcontext(Server()))
    with pytest.raises(ValueError, match="names no version"):
        OC.read_version(tmp_path / "bin", tmp_path, {})


def test_the_trim_keeps_only_what_the_adapter_probes_from_a_superset(monkeypatch):
    """The regeneration proof measured from a superset, never the pin (review of #357, minor 2): the served 2.0.18
    document as saved on 2026-10-24 (a sorted re-dump, so its own hash is not the pin's), plus a planted operation and
    schema nothing references, trims to the pinned fixture byte for byte."""
    pinned = (FIXTURES / "openapi-2.0.18.min.json").read_bytes()
    full = json.loads((FIXTURES / "openapi-2.0.18.served.json").read_text(encoding="utf-8"))
    assert len(full["paths"]) > 17 and len(full["components"]["schemas"]) > 132  # a real superset
    full["paths"]["/api/aew-planted"] = {"get": {"operationId": "planted",
                                                 "responses": {"200": {"content": {"application/json": {"schema": {
                                                     "$ref": "#/components/schemas/Planted.Reached"}}}}}}}
    full["components"]["schemas"]["Planted.Reached"] = {"type": "object"}
    full["components"]["schemas"]["Planted.Orphan"] = {"type": "string"}
    trimmed = OC.trim(full, version="2.0.18", full_sha256=json.loads(pinned)["x-aew-fixture"]["full_sha256"])
    assert "/api/aew-planted" not in trimmed["paths"]
    assert not {"Planted.Reached", "Planted.Orphan"} & set(trimmed["components"]["schemas"])
    assert core.dump(trimmed) == pinned
    # a schema reached only through a probed enum's name is a seed of its own: kept while the probe names it
    full["components"]["schemas"]["Planted.EnumOnly"] = {"enum": ["x"], "type": "string"}
    monkeypatch.setattr(OC.C, "REQUIRED_ENUMS", {**OC.C.REQUIRED_ENUMS, "Planted.EnumOnly": frozenset({"x"})})
    assert "Planted.EnumOnly" in OC.trim(full, version="2.0.18", full_sha256="")["components"]["schemas"]


def test_a_suite_whose_agents_would_run_another_aew_is_not_comparable_and_does_not_run(tmp_path, monkeypatch):
    """A qualification never judges another checkout's AEW: the agents' bare `aew` is AEW's interpreter's install."""
    from harness_qualify import neutral

    monkeypatch.setattr(neutral, "agents_aew", lambda env: "another checkout")
    suite = tmp_path / "test_never_runs.py"
    suite.write_text("def test_a():\n    raise SystemExit('ran')\n", encoding="utf-8")
    ctx = core.Context(binary=tmp_path / "bin", work=tmp_path / "work", env=core.private_env(tmp_path / "env"),
                       version="1")
    out = neutral._pytest(ctx, "STUB_BIN", [str(suite)], [])
    assert out.status == core.SKIPPED and out.notes[0].startswith("not comparable: an agent's bare `aew` runs another")
    assert not (tmp_path / "work" / "pytest.log").exists()
    assert neutral.agents_aew(core.private_env(tmp_path / "env2")) in ("this tree", "another checkout", "none")


@pytest.mark.parametrize("line", [
    r"SKIPPED [2] C:\Users\runner\t\test_suite.py:5: the driver cannot drive this",  # Windows: a drive's colon
    "SKIPPED [2] /home/runner/t/test_suite.py:5: the driver cannot drive this",
    r"SKIPPED [2] tests\helpers\test_suite.py: the driver cannot drive this",  # no line number
])
def test_a_skip_line_is_read_whatever_the_platform_spells_its_path(line):
    from harness_qualify import neutral

    m = neutral._SKIP_LINE.match(line)
    assert m is not None and (m.group(1), m.group(2)) == ("2", "the driver cannot drive this")


def test_an_allowed_skip_that_now_skips_more_tests_is_not_passed(tmp_path, monkeypatch):
    from harness_qualify import neutral

    monkeypatch.setattr(neutral, "agents_aew", lambda env: "this tree")
    suite = tmp_path / "suite" / "test_suite.py"
    suite.parent.mkdir()
    suite.write_text("import pytest\n\ndef test_a():\n    pass\n\n@pytest.mark.skip('the driver cannot drive x')\n"
                     "def test_b():\n    pass\n\n@pytest.mark.skip('the driver cannot drive y')\ndef test_c():\n"
                     "    pass\n", encoding="utf-8")
    ctx = core.Context(binary=tmp_path / "bin", work=tmp_path / "work", env=core.private_env(tmp_path / "env"),
                       version="1")
    out = neutral._pytest(ctx, "STUB_BIN", [str(suite)], ["--rootdir", str(suite.parent)],
                          allowed_skips={r"^the driver cannot drive": 1})
    assert out.status == core.SKIPPED and "expected 1 skipped by '^the driver cannot drive', saw 2" in out.notes


def test_a_failing_suite_records_each_failing_test_by_its_id_only(tmp_path, monkeypatch):
    from harness_qualify import neutral

    monkeypatch.setattr(neutral, "agents_aew", lambda env: "this tree")
    suite = tmp_path / "suite" / "test_suite.py"
    suite.parent.mkdir()
    suite.write_text(f"def test_a():\n    assert False, {str(tmp_path)!r}\n", encoding="utf-8")
    ctx = core.Context(binary=tmp_path / "bin", work=tmp_path / "work", env=core.private_env(tmp_path / "env"),
                       version="1")
    out = neutral._pytest(ctx, "STUB_BIN", [str(suite)], ["--rootdir", str(suite.parent)])
    assert out.status == core.FAIL and "failed: test_suite.py::test_a" in out.notes
    assert not [n for n in out.notes if str(tmp_path) in n]  # the message, which named a host path, is not kept


def test_an_overrunning_suite_fails_and_leaves_no_folder_and_no_process(tmp_path, monkeypatch):
    """Review of #357, minor 3 (and of #359, n2): the suite and what it started are killed, its folder removed."""
    import time

    from harness_qualify import neutral

    from aew.harness import procs

    monkeypatch.setattr(neutral, "agents_aew", lambda env: "this tree")
    made: list[Path] = []
    real = neutral.tempfile.mkdtemp

    def mkdtemp(**kw: Any) -> str:
        made.append(Path(real(**kw)))
        return str(made[-1])

    monkeypatch.setattr(neutral.tempfile, "mkdtemp", mkdtemp)
    pid_file = tmp_path / "child.pid"
    suite = tmp_path / "suite" / "test_slow.py"
    suite.parent.mkdir()
    suite.write_text(
        "import pathlib, subprocess, sys, time\n\ndef test_slow():\n"
        "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
        f"    pathlib.Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "    time.sleep(600)\n", encoding="utf-8")
    ctx = core.Context(binary=tmp_path / "bin", work=tmp_path / "work", env=core.private_env(tmp_path / "env"),
                       version="1")
    out = neutral._pytest(ctx, "STUB_BIN", [str(suite)], ["--rootdir", str(suite.parent)], timeout_s=20)
    assert out.status == core.FAIL and "overran 20s" in out.notes[0]
    assert made and not made[0].exists()
    assert pid_file.exists(), "the suite started no child before the deadline"
    child = int(pid_file.read_text())
    deadline = time.monotonic() + 10
    while procs.pid_alive(child) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not procs.pid_alive(child)


def test_the_feed_as_it_is_served_gives_absolute_download_urls():
    """The live feed's shape (2026-11-07): absolute URLs, sha512 and size per file, then the version."""
    text = ("files:\n  - url: https://example.invalid/files/bin/9.8.7/opencode-desktop-win-x64.exe\n"
            "    sha512: c2hhNTEy\n    size: 267155312\nreleaseDate: 2026-11-06T23:28:16.000Z\nversion: 9.8.7\n")
    assert OC.parse_feed(text) == [core.Release("9.8.7", "https://example.invalid/files/bin/9.8.7/"
                                                "opencode-desktop-win-x64.exe", "c2hhNTEy", "sha512", 267155312)]


# ------------------------------------------------------------------------------------------------- feature verdicts


def test_the_feature_verdicts_record_is_readable_and_the_report_names_it():
    """The verdicts a bump gives (the operator, 2026-11-07: committed, one owner) are read by the tool, each from the
    closed set (the rows they name are checked against the register in tests/unit/test_register.py)."""
    from harness_qualify import verdicts

    recorded = verdicts.load("opencode")
    assert "2.2.6" in recorded and len(recorded["2.2.6"]) >= 20
    assert verdicts.lines("opencode", "2.2.6")[0].startswith(f"  {len(recorded['2.2.6'])} recorded for 2.2.6 (")
    assert "none recorded for 9.9.9" in verdicts.lines("opencode", "9.9.9")[0]
    assert verdicts.load("stubharness") == {}


def test_a_verdict_outside_the_closed_set_is_refused(tmp_path, monkeypatch):
    from harness_qualify import verdicts

    (tmp_path / "opencode.yaml").write_text(
        "schema: aew/harness-verdicts/v1\nharness: opencode\nversions:\n  '1.0.0':\n    verdicts:\n"
        "      - {feature: x, verdict: maybe, reason: y, row: null}\n", encoding="utf-8")
    monkeypatch.setattr(verdicts, "HERE", tmp_path)
    with pytest.raises(ValueError, match="one of"):
        verdicts.load("opencode")
