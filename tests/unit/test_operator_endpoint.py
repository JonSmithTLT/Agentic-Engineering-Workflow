"""The operator endpoint and steering mode (M4-E E2; plan v3 §2.1, §6; A1 §1; CWR §5, §6).

An autonomy increase is the operator's alone, through the endpoint: nothing else constructs the principal the engine
accepts, a Lead session and the typed surface cannot reach it, an adopted default that raises waits for it, and Run
needs an executable notifier. The Lead may lower its own mode and ask, and asking grants nothing. Every record says
``guarantee: dev``, with the same-uid residuals stated (production authority needs F18.6)."""

from __future__ import annotations

import ast
import json
import os
import re
import stat
import threading
from pathlib import Path
from typing import Any

import pytest
from conftest import IS_WINDOWS, run_aew
from invariants import assert_control_invariants

from aew import errors
from aew.cli.main import build_parser
from aew.engine import steering as S
from aew.engine.api import Engine
from aew.harness import lead_broker, operator_client, operator_endpoint
from aew.surface import contract
from aew.surface.context import NORMAL, SurfaceContext
from aew.surface.errors import AdapterInputError
from aew.surface.run import run_tool
from aew.surface.validate import check_call

SRC = Path(__file__).resolve().parents[2] / "src" / "aew"


def _policy(project, **steering: Any) -> Path:
    path = project.root / ".aew" / "policy" / "execution.yaml"
    text = path.read_text(encoding="utf-8").split("\n# --- e2 test ---\n")[0]
    extra = ""
    if steering.get("mode"):
        extra += f"steering:\n  mode: {steering['mode']}\n"
    if steering.get("notify"):
        extra += "notify:\n  command: " + json.dumps(steering["notify"]) + "\n"
    path.write_text(text + "\n# --- e2 test ---\n" + extra, encoding="utf-8")
    return path


def _adopt(project, **steering: Any) -> Engine:
    _policy(project, **steering)
    project.adopt_policy()
    return Engine.discover(project.root)


def _principal() -> S.OperatorPrincipal:
    return S.OperatorPrincipal(uid=os.getuid() if hasattr(os, "getuid") else None, method="peer_credentials",
                               endpoint_pid=os.getpid(), endpoint_started_at="2026-10-09T00:00:00Z")


def _raise(engine: Engine, mode: str) -> dict[str, Any]:
    bound = engine.steering_raise_preview(mode)
    return engine.steering_raise(_principal(), mode=mode, generation=bound["generation"],
                                 legality_digest=bound["legality_digest"])


def _records(project) -> list[dict[str, Any]]:
    return [json.loads(line) for f in sorted((project.root / ".aew/records/steering").glob("*.jsonl"))
            for line in f.read_text(encoding="utf-8").splitlines()]


def _executable(tmp_path: Path) -> str:
    script = tmp_path / ("notify.cmd" if IS_WINDOWS else "notify")
    script.write_text("@exit 0\n" if IS_WINDOWS else "#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


# ---------------------------------------------------------------------------------------------- the boundary


def test_no_operator_principal_outside_the_endpoint():
    """A1 §6 test 1 (static half): only the endpoint constructs the principal the engine accepts, and only `aew
    operator serve` imports the endpoint. The typed surface offers no raise."""
    constructs, imports = [], []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) \
                    == "OperatorPrincipal":
                constructs.append(rel)
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("operator_endpoint"):
                imports.append(rel)
            if isinstance(node, ast.ImportFrom) and node.module == "aew.harness" and \
                    any(a.name == "operator_endpoint" for a in node.names):
                imports.append(rel)
            if isinstance(node, ast.ClassDef) and any(getattr(b, "id", "") == "OperatorPrincipal" for b in node.bases):
                constructs.append(f"{rel} (a subclass)")
    assert constructs == ["harness/operator_endpoint.py"], constructs
    assert imports == ["cli/operator_commands.py"], imports
    steering = contract.TOOLS["steering"].input_schema["properties"]["action"]["enum"]
    assert not [a for a in steering if "raise" in a and not a.startswith("request")], steering
    assert not [t for t in contract.TOOLS if "raise" in t or "confirm" in t or "grant" in t]


def test_raise_is_refused_from_a_lead_session_and_the_typed_surface(project):
    """A1 §6: a model Lead cannot raise its mode. The broker refuses the raise and the endpoint's own commands (and
    only them: lowering stays Lead-reachable); the typed tool has no raise; the engine refuses any other value."""
    parser = build_parser()
    for argv in (["lead", "mode", "raise", "walk"], ["operator", "serve", "--dev"], ["operator", "ping"]):
        refusal = lead_broker.refuses_locally(parser.parse_args(argv))
        assert refusal and "operator endpoint" in refusal, argv
    assert lead_broker.refuses_locally(parser.parse_args(["lead", "mode", "lower", "crawl", "--expect-rev", "1"])) \
        is None
    res = run_aew("-C", str(project.root), "lead", "mode", "raise", "walk",
                  env={"AEW_LEAD_BROKER": "x", "AEW_LEAD_BROKER_KEY": "y"})
    assert res.returncode != 0 and "operator endpoint" in res.stderr, res.stderr
    with pytest.raises(AdapterInputError) as refused:
        check_call("steering", {"expect_rev": 1, "action": "raise", "mode": "run"}, NORMAL)
    assert refused.value.code == "INVALID_ARGUMENTS"
    engine = _adopt(project, mode="walk")

    class Lookalike:  # what a caller that is not the endpoint could build
        uid, method, endpoint_pid, endpoint_started_at, guarantee = 0, "peer_credentials", 1, "x", "dev"

    bound = engine.steering_raise_preview("walk")
    for fake in (Lookalike(), {"uid": 0, "guarantee": "dev"}, None):
        with pytest.raises(errors.PermissionDenied):
            engine.steering_raise(fake, mode="walk", generation=bound["generation"],  # type: ignore[arg-type]
                                  legality_digest=bound["legality_digest"])
    assert engine.steering_view()["effective"] is None


def test_mode_commands_refuse_while_steering_is_not_configured(project):
    """Decision 3: absent is legacy/manual behaviour, not a fourth mode; status shows nothing new."""
    engine = Engine.discover(project.root)
    for call in (lambda: engine.steering_raise_preview("walk"),
                 lambda: engine.steering_lower(token=project.token, expect_rev=project.rev(), mode="crawl"),
                 lambda: engine.steering_request(token=project.token, expect_rev=project.rev(), kind="raise",
                                                 mode="walk", rationale="r")):
        with pytest.raises(errors.SteeringNotConfigured):
            call()
    assert "steering" not in engine.status()
    assert "steering" not in engine.store.read()


# ---------------------------------------------------------------------------------------------- the mode


def test_adopted_raise_waits_for_the_endpoint(project):
    """N1: adopting a default that raises changes nothing until the endpoint records a raise; adopting one that does
    not is the standing mode at once (absent to crawl is not a raise)."""
    engine = _adopt(project, mode="walk")
    view = engine.steering_view()
    assert view["effective"] is None and view["default"] == "walk"
    assert "raise pending at the operator endpoint" in view["pending_raise"]
    assert _records(project) == []
    engine = _adopt(project, mode="crawl")
    assert engine.steering_view()["effective"] == "crawl" and "pending_raise" not in engine.steering_view()
    (record,) = _records(project)
    assert record["source"] == "default" and record["previous"] is None and record["new"] == "crawl"
    engine = _adopt(project, mode="run")
    view = engine.steering_view()
    assert view["effective"] == "crawl" and "policy default `run`; effective `crawl`" in view["pending_raise"]
    assert len(_records(project)) == 1
    text = run_aew("-C", str(project.root), "status").stdout
    assert "Steering: effective crawl" in text and "raise pending" in text
    assert_control_invariants(project)


def test_a_raise_lasts_only_for_the_generation_it_was_granted_to(project):
    """P2: when the generation ends, the mode falls back to the standing mode; the next generation needs a fresh
    raise. The record names everything A1 §1.3 requires."""
    engine = _adopt(project, mode="crawl")
    out = _raise(engine, "walk")
    assert out["guarantee"] == "dev" and engine.steering_view()["effective"] == "walk"
    record = _records(project)[-1]
    assert record["source"] == "raise" and record["by"]["principal"]["guarantee"] == "dev"
    assert {record["previous"], record["new"], record["generation"]} == {"crawl", "walk", 1}
    assert record["legality_digest"].startswith("sha256:") and record["operational_digest"].startswith("sha256:")
    assert record["revision"] == out["revision"] == engine.store.read()["revision"]
    assert record["by"]["principal"]["endpoint"]["pid"] == os.getpid()
    project.ok("lead", "release", "--token", project.token, "--expect-rev", str(project.rev()))
    project.token = project.ok("lead", "acquire", "--expect-rev", str(project.rev()))["token"]
    view = engine.steering_view()
    assert view["effective"] == "crawl" and view["ended_override"]["mode"] == "walk"
    assert_control_invariants(project)


def test_a_raise_binds_the_generation_and_legality_it_was_shown(project):
    engine = _adopt(project, mode="crawl")
    bound = engine.steering_raise_preview("walk")
    with pytest.raises(errors.StaleAuthority):
        engine.steering_raise(_principal(), mode="walk", generation=bound["generation"] + 1,
                              legality_digest=bound["legality_digest"])
    with pytest.raises(errors.StaleAuthority) as stale:
        engine.steering_raise(_principal(), mode="walk", generation=bound["generation"],
                              legality_digest="sha256:" + "0" * 64)
    assert stale.value.details["reason"] == "stale_policy"
    _raise(engine, "walk")
    with pytest.raises(errors.IllegalTransition):
        _raise(engine, "walk")  # not a raise any more
    assert engine.steering_view()["effective"] == "walk"


def test_run_needs_an_executable_notifier(project, tmp_path):
    """Decision 1: unattended Run needs a configured notifier whose argv[0] resolves to an executable file."""
    engine = _adopt(project, mode="crawl")
    with pytest.raises(errors.IllegalTransition) as refused:
        engine.steering_raise_preview("run")
    assert refused.value.details["reason"] == "notifier_unavailable"
    missing = tmp_path / "no-such-notifier"
    engine = _adopt(project, mode="crawl", notify=[str(missing), "--event"])
    with pytest.raises(errors.IllegalTransition) as refused:
        engine.steering_raise_preview("run")
    assert "does not resolve to an executable file" in refused.value.message
    engine = _adopt(project, mode="crawl", notify=[_executable(tmp_path)])
    assert _raise(engine, "run")["mode"] == "run"


def test_a_lead_lowers_its_mode(project):
    """A1 §6: a Lead lowers its mode for its own generation, through the typed tool or the command; only lower."""
    engine = _adopt(project, mode="crawl")
    _raise(engine, "walk")
    ctx = SurfaceContext(profile=NORMAL, generation=1, lead_session=None)
    out = run_tool(engine, ctx, "steering", {"expect_rev": project.rev(), "action": "lower", "mode": "crawl",
                                             "rationale": "the next change touches the schema"}, token=project.token)
    assert out["ok"], out["stopped"]
    assert out["completed_steps"][0]["primitive"] == "steering"
    assert out["effective_operation_class"] == "MECHANICAL"
    view = engine.steering_view()
    assert view["effective"] == "crawl" and view["source"] == "lower"
    record = _records(project)[-1]
    assert record["by"] == {"kind": "lead", "generation": 1} and record["rationale"]
    refused = run_tool(engine, ctx, "steering", {"expect_rev": project.rev(), "action": "lower", "mode": "walk"},
                       token=project.token)
    assert not refused["ok"] and refused["stopped"]["error"]["code"] == "ILLEGAL_TRANSITION"
    res = run_aew("-C", str(project.root), "lead", "mode", "lower", "walk", "--token", project.token,
                  "--expect-rev", str(project.rev()))
    assert res.returncode != 0 and "is not lower" in res.stderr
    assert_control_invariants(project)


def test_requests_grant_nothing(project):
    """A1 §1.3: a Lead-requested increase is a request, not authority. One raise request is open at a time; requests
    are bounded; the arguments each action takes are checked before anything runs."""
    engine = _adopt(project, mode="crawl")
    ctx = SurfaceContext(profile=NORMAL, generation=1, lead_session=None)

    def call(**args: Any) -> dict[str, Any]:
        return run_tool(engine, ctx, "steering", {"expect_rev": project.rev(), **args}, token=project.token)

    assert call(action="request_raise", mode="walk", rationale="routine edits")["ok"]
    assert call(action="request_raise", mode="run", rationale="unattended overnight")["ok"]
    assert call(action="request_confirmation", action_ref="ticket_start T-0001", rationale="needs a look")["ok"]
    view = engine.steering_view()
    assert view["effective"] == "crawl"
    assert [(r["kind"], r.get("mode")) for r in view["requests"]] == [("raise", "run"), ("confirmation", None)]
    assert any(r["kind"] == "request_closed" and "replaced" in r["closed"] for r in _records(project))
    for bad in ({"action": "request_raise", "mode": "run"}, {"action": "lower"},
                {"action": "request_confirmation", "rationale": "r"},
                {"action": "lower", "mode": "crawl", "action_ref": "x"}):
        with pytest.raises(AdapterInputError):
            check_call("steering", {"expect_rev": 1, **bad}, NORMAL)
    for i in range(S.MAX_REQUESTS - 2):
        assert call(action="request_confirmation", action_ref=f"step {i}", rationale="r")["ok"]
    over = call(action="request_confirmation", action_ref="one too many", rationale="r")
    assert not over["ok"] and len(engine.store.read()["steering"]["requests"]) == S.MAX_REQUESTS
    assert engine.steering_view()["effective"] == "crawl"
    assert_control_invariants(project)


def test_every_operator_record_is_guarantee_dev():
    """§7: nothing in M4-E produces a label other than dev; a principal has no way to carry another."""
    assert S.GUARANTEE == "dev" and _principal().guarantee == "dev"
    assert "guarantee" not in S.OperatorPrincipal.__dataclass_fields__
    labels = set()
    for path in SRC.rglob("*.py"):
        labels |= set(re.findall(r"""["']guarantee["']\s*:\s*["'](\w+)["']""", path.read_text(encoding="utf-8")))
    assert labels <= {"dev"}, labels


# ---------------------------------------------------------------------------------------------- the endpoint


class Console:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str) -> None:
        self.lines.append(text)

    def code(self) -> str:
        found = re.findall(r"confirmation code ([0-9A-F]{6})", "".join(self.lines))
        assert found, self.lines
        return found[-1]


@pytest.fixture
def endpoint(project):
    engine = Engine.discover(project.root)
    console = Console()
    ep = operator_endpoint.OperatorEndpoint(engine, console=console, dev=True, timeout=10)
    ep.start()
    yield ep, console
    ep.close()


def test_the_endpoint_starts_only_with_dev_and_never_in_a_lead_session(project, monkeypatch):
    engine = Engine.discover(project.root)
    with pytest.raises(errors.OperatorAuthorizationRequired):
        operator_endpoint.OperatorEndpoint(engine, console=print, dev=False)
    monkeypatch.setenv("AEW_LEAD_BROKER", "somewhere")
    with pytest.raises(errors.PermissionDenied) as refused:
        operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
    assert "Lead session" in refused.value.message
    assert operator_endpoint._is_lead_session(["/usr/bin/python3", "-m", "aew", "lead", "session", "--acquire"])
    assert operator_endpoint._is_lead_session(["/venv/bin/aew", "opencode", "--acquire"])
    assert not operator_endpoint._is_lead_session(["/venv/bin/aew", "lead", "mode", "raise", "walk"])


def test_same_uid_residuals_are_recorded(project, endpoint):
    """N5: ping, status and doctor carry the label and every residual a same-uid Lead keeps."""
    ep, _ = endpoint
    info = operator_client.ping(project.root / ".aew")
    assert info["guarantee"] == "dev" and info["pid"] == os.getpid()
    assert info["residuals"] == list(operator_client.RESIDUALS) and len(info["residuals"]) == 4
    engine = _adopt(project, mode="crawl")
    assert engine.status()["steering"]["operator_endpoint"] == {
        "running": True, "pid": os.getpid(), "started_at": ep.started_at, "guarantee": "dev"}
    row = next(c for c in engine.doctor_checks() if c["check"] == "operator-endpoint")
    assert row["status"] == "WARN" and "guarantee dev" in row["detail"] and "F18.6" in row["detail"]
    assert all(r in row["detail"] for r in operator_client.RESIDUALS)


def test_a_raise_through_the_endpoint_needs_the_code_shown_on_its_console(project, endpoint):
    ep, console = endpoint
    _adopt(project, mode="crawl")
    prompts: list[str] = []

    def wrong(prompt: str) -> str:
        prompts.append(prompt)
        return "000000"

    with pytest.raises(errors.PermissionDenied):
        operator_client.request_raise(project.root / ".aew", "walk", ask=wrong, requester="test")
    code = console.code()
    assert code not in "".join(prompts)  # the code is on the endpoint's console, never at the requester
    assert Engine.discover(project.root).steering_view()["effective"] == "crawl"

    def right(prompt: str) -> str:
        prompts.append(prompt)
        return console.code()

    out = operator_client.request_raise(project.root / ".aew", "walk", ask=right, requester="test")
    assert out["mode"] == "walk" and out["guarantee"] == "dev"
    assert console.code() not in "".join(prompts)
    assert "generation 1" in "".join(console.lines) and "legality digest" in "".join(console.lines)
    with pytest.raises(errors.IllegalTransition):  # refused before the operator is asked: not a raise
        operator_client.request_raise(project.root / ".aew", "walk", ask=right, requester="test")


@pytest.mark.skipif(IS_WINDOWS, reason="the peer check reads POSIX peer credentials; the named pipe is labelled dev")
def test_the_peer_check_refuses_another_principal_before_any_challenge(project, endpoint):
    """The mechanism the stand-in live test proves across users: a connection whose peer is not the operator
    principal is refused before anything is read or shown."""
    ep, console = endpoint
    _adopt(project, mode="crawl")
    ep.uid = (ep.uid or 0) + 4242  # as if the connecting process were another user
    with pytest.raises(errors.PermissionDenied) as refused:
        operator_client.request_raise(project.root / ".aew", "walk", ask=lambda p: "x", requester="test")
    assert refused.value.details["reason"] == "peer_check" and console.lines == []
    with pytest.raises(errors.PermissionDenied):
        operator_client.ping(project.root / ".aew")


@pytest.mark.skipif(IS_WINDOWS, reason="the socket directory's mode is a POSIX property")
def test_the_endpoint_socket_lives_in_a_private_directory(endpoint):
    ep, _ = endpoint
    directory = Path(ep.address).parent
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700 and directory.stat().st_uid == os.getuid()


def test_one_endpoint_per_project_and_a_stale_locator_is_replaced_only_when_its_process_is_gone(project, endpoint):
    ep, _ = endpoint
    engine = Engine.discover(project.root)
    with pytest.raises(errors.PermissionDenied) as refused:
        operator_endpoint.OperatorEndpoint(engine, console=print, dev=True).start()
    assert "another operator endpoint" in refused.value.message
    ep.close()
    locator = operator_client.locator_path(project.root / ".aew")
    assert not locator.exists()
    dead = {"schema": operator_client.LOCATOR_SCHEMA, "address": "/nowhere", "family": "AF_UNIX", "pid": 2 ** 22 + 7,
            "process_started": 1.0, "started_at": "x", "uid": 0, "guarantee": "dev"}
    locator.write_text(json.dumps(dead), encoding="utf-8")
    again = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
    again.start()
    try:
        assert operator_client.read_locator(locator)["pid"] == os.getpid()
    finally:
        again.close()


def test_concurrent_starters_claim_the_project_once(project):
    """Review of #134, finding 1: starters racing for one project never both serve. Exactly one claims the endpoint
    lock; the locator names that one; every other starter is refused."""
    engine = Engine.discover(project.root)
    barrier, started, refused = threading.Barrier(6), [], []

    def start() -> None:
        ep = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
        barrier.wait(10)
        try:
            ep.start()
            started.append(ep)
        except errors.PermissionDenied as exc:
            refused.append(exc)

    threads = [threading.Thread(target=start) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    try:
        assert len(started) == 1 and len(refused) == 5, (started, refused)
        locator = operator_client.read_locator(operator_client.locator_path(project.root / ".aew"))
        assert locator is not None and locator["address"] == started[0].address
        assert operator_client.ping(project.root / ".aew")["pid"] == os.getpid()
    finally:
        for ep in started:
            ep.close()


def test_an_unreadable_locator_is_never_taken_for_a_claim(project, endpoint):
    """Review of #134, finding 1: an unreadable locator does not decide anything. While the live endpoint holds the
    lock, a starter is refused whatever the file says; once no one holds it, the file is stale by proof and replaced."""
    ep, _ = endpoint
    engine = Engine.discover(project.root)
    locator = operator_client.locator_path(project.root / ".aew")
    for junk in ("", "{not json", json.dumps({"schema": "other"})):
        locator.write_text(junk, encoding="utf-8")
        with pytest.raises(errors.PermissionDenied):
            operator_endpoint.OperatorEndpoint(engine, console=print, dev=True).start()
    ep.close()
    locator.write_text("", encoding="utf-8")  # as a starter that died mid-write would leave it
    again = operator_endpoint.OperatorEndpoint(engine, console=print, dev=True)
    again.start()
    try:
        assert operator_client.read_locator(locator)["address"] == again.address
    finally:
        again.close()
    assert not locator.exists()


def test_one_challenge_at_a_time(project, endpoint):
    ep, console = endpoint
    _adopt(project, mode="crawl")
    started, release = threading.Event(), threading.Event()
    results: list[Any] = []

    def slow(prompt: str) -> str:
        started.set()
        release.wait(10)
        return console.code()

    worker = threading.Thread(target=lambda: results.append(
        operator_client.request_raise(project.root / ".aew", "walk", ask=slow, requester="first")))
    worker.start()
    assert started.wait(10)
    with pytest.raises(errors.PermissionDenied) as busy:
        operator_client.request_raise(project.root / ".aew", "walk", ask=lambda p: "x", requester="second")
    assert "waiting for the operator" in busy.value.message
    release.set()
    worker.join(20)
    assert results and results[0]["mode"] == "walk"


def test_the_endpoint_accepts_only_its_operations(project, endpoint):
    from multiprocessing.connection import Client

    ep, _ = endpoint
    for message in (b"not json", json.dumps({"op": "confirm", "args": {}}).encode(),
                    json.dumps({"op": "ping"}).encode()):
        conn = Client(ep.address, family=ep.family)
        try:
            conn.send_bytes(message)
            reply = json.loads(conn.recv_bytes())
        finally:
            conn.close()
        assert reply["ok"] is False, message
    assert ep.refused == 3
