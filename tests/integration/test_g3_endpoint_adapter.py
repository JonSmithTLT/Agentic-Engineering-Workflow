"""G3 at the operator endpoint: where G3 counts and the operation is bound, a consumed approval stands in for the typed
code, for one challenge (the G3-C brief's PR C3 and the designer's rulings). The G3 service here is the real one's rules
(``aew_g3.service``) with a stand-in PIN, called directly, so every platform runs it; only its sockets are left out."""

from __future__ import annotations

import copy
import json
import re
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from aew import errors, g3client, g3standing
from aew.engine import steering
from aew.engine.api import Engine
from aew.harness import g3_adapter as G
from aew.harness import operator_client, operator_endpoint
from aew_g3 import wire as G3W
from g3 import PIN, make

MODE = "walk"
ENDED = 60.0
REAL_STANDING = g3standing.standing


class FakeG3:
    """``g3client``'s calls on the real service's rules, with a counter on each: the confirmer's part is ``decide``."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.consumed: list[dict[str, Any]] = []
        self.requests = 0
        self.keys: list[str] = []
        self.on_decide: Any = None
        self.on_request: Any = None
        self.decision = "APPROVE"
        self.undecided = False  # the operator has not decided: the wait goes on, on the endpoint's own ``sleep``

    def request_approval(self, cset: dict[str, Any], sock_path: str | None = None) -> dict[str, Any]:
        self.requests += 1
        self.keys.append(cset["client_request_key"])
        if self.on_request:
            self.on_request()
        status, body = self.service.request({"wire_version": G3W.WIRE, "command_set": cset})
        if status != 201:
            raise g3client._g3_refusal(status, body)
        return body

    def await_decision(self, pending: dict[str, Any], sock_path: str | None = None, *, sleep: Any = time.sleep,
                       **_: Any) -> dict[str, Any]:
        deadline = time.monotonic() + ENDED
        while self.undecided:
            assert time.monotonic() < deadline, "the wait did not end"
            sleep(0.01)
        if self.on_decide:
            self.on_decide()
        body = {"decision": "APPROVE", "pin": PIN} if self.decision == "APPROVE" else {"decision": "DECLINE"}
        status, out = self.service.decide(pending["approval_ref"], body)
        if self.decision == "DECLINE":
            assert status == 204, out
            raise errors.OperatorAuthorizationRequired("the operator declined", reason="declined")
        assert status == 200, out
        return out

    def wire(self, sock_path: str | None, method: str, path: str, body: Any = None, **_: Any) -> tuple[int, Any]:
        """The one request left on ``g3client``'s wire, so the real ``consume`` reads the service's answer."""
        assert (method, path) == ("POST", "/g3/v1/consume")
        self.consumed.append(body)
        return self.service.consume(body)


@pytest.fixture
def steered(project, monkeypatch, tmp_path):
    (project.root / ".aew/policy/execution.yaml").open("a", encoding="utf-8").write("\nsteering:\n  mode: crawl\n")
    project.adopt_policy()
    fake = FakeG3(make(tmp_path / "g3").svc)
    monkeypatch.setattr(g3client, "request_approval", fake.request_approval)
    monkeypatch.setattr(g3client, "await_decision", fake.await_decision)
    monkeypatch.setattr(g3client, "_g3", fake.wire)
    monkeypatch.setattr(g3standing, "standing", lambda *a, **k: g3standing.Standing(True))
    return SimpleNamespace(project=project, fake=fake, engine=Engine.discover(project.root), root=project.root / ".aew")


@pytest.fixture
def endpoint(steered):
    lines: list[str] = []
    ep = operator_endpoint.OperatorEndpoint(steered.engine, console=lines.append, dev=True, timeout=30)
    ep.start()
    yield SimpleNamespace(ep=ep, lines=lines)
    ep.close()


def _no_typing(prompt: str) -> str:
    raise AssertionError("no code is typed on the G3 path")


def _raise(steered, ask=_no_typing) -> dict[str, Any]:
    return operator_client.request_raise(steered.root, MODE, ask=ask, requester="test")


def _no_code(lines: list[str]) -> bool:
    return "confirmation code" not in "".join(lines)


def _mode(steered) -> str | None:
    return steering.effective(steered.engine.store.current())["mode"]


def _records(steered) -> list[dict[str, Any]]:
    return [json.loads(line) for f in sorted((steered.root / "records/steering").glob("*.jsonl"))
            for line in f.read_text(encoding="utf-8").splitlines()]


def test_an_approval_consumed_raises_the_mode_and_its_record_names_the_consent(steered, endpoint):
    out = _raise(steered)
    assert out["mode"] == MODE and _mode(steered) == MODE
    assert _no_code(endpoint.lines), "no code"
    assert any(f"steering mode raised to {MODE}" in line and "G3 approval" in line for line in endpoint.lines)
    assert [f["owner"] for f in steered.fake.consumed] == ["ADC"]
    record = next(r for r in _records(steered) if r.get("source") == "raise")
    origin = record["by"]["principal"]["origin"]
    assert origin["kind"] == "g3" and origin["consent_set_ref"] == steered.fake.consumed[0]["consent_set_ref"]
    assert steered.fake.consumed[0]["operation_ref"].startswith("aew:steering-raise:")


def test_a_replayed_consent_is_refused_by_the_service(steered, endpoint):
    """The endpoint never takes a consent from a requester, so a replay is the same consent consumed twice."""
    _raise(steered)
    replay = {**steered.fake.consumed[0], "operation_ref": "aew:steering-raise:again"}
    status, out = steered.fake.service.consume(replay)
    assert status == 200 and out["result"] == "CONSENT_ALREADY_USED"


@pytest.mark.parametrize("result", [r for r in g3client.CONSUME_RESULTS if r != "CONSUMED"])
def test_a_consume_answered_with_anything_else_is_refused_and_nothing_rises(steered, endpoint, monkeypatch, result):
    monkeypatch.setattr(g3client, "_g3", lambda *a, **k: (200, {"wire_version": G3W.WIRE, "result": result}))
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert result in refused.value.message and "request it again" in refused.value.message
    assert refused.value.details["reason"] == G.REFUSED
    assert ("new approval" in refused.value.message) == (result == "CONSENT_ALREADY_USED")
    assert _mode(steered) != MODE and _no_code(endpoint.lines)
    assert any(result in line for line in endpoint.lines), "the console says how it ended"


def test_a_reply_lost_after_the_member_was_used_is_held_and_the_next_request_takes_a_new_approval(steered, endpoint,
                                                                                                  monkeypatch):
    real = steered.fake.wire

    def lost(*a: Any, **k: Any) -> Any:
        real(*a, **k)
        raise errors.Unavailable("the G3 service did not answer", reason="g3_unreachable")

    monkeypatch.setattr(g3client, "_g3", lost)
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert held.value.details["reason"] == G.HELD and "new approval" in held.value.message
    assert G.EVERY_REQUEST in held.value.message
    assert _mode(steered) != MODE and _no_code(endpoint.lines)
    status, out = steered.fake.service.consume(steered.fake.consumed[0])
    assert status == 200 and out["result"] == "CONSENT_ALREADY_USED", "the lost reply's member stays used"

    monkeypatch.setattr(g3client, "_g3", real)
    assert _raise(steered)["mode"] == MODE
    assert steered.fake.requests == 2
    assert steered.fake.consumed[0]["consent_set_ref"] != steered.fake.consumed[1]["consent_set_ref"]


def test_an_approval_for_other_arguments_is_refused_by_the_service(steered):
    """The set's digest covers the target, so a consent for one mode cannot be consumed for another."""
    bound = steered.engine.steering_raise_preview(MODE)
    approved, record = G.approve(G.raise_set(bound), lambda p: None)
    other = copy.deepcopy(approved)
    other["intents"][0]["target"]["mode"] = "RUN"
    member = other["intents"][0]
    status, out = steered.fake.service.consume({
        "wire_version": G3W.WIRE, "consent_set_ref": other["consent_set_ref"], "set_digest": G.W.set_digest(other),
        "recipient_ref": other["recipient_ref"], "installation_ref": other["installation_ref"],
        "intent_ref": member["intent_ref"], "origin_proof_ref": member["origin_proof_ref"], "owner": "ADC",
        "operation_ref": "aew:steering-raise:other"})
    assert status == 200 and out["result"] == "CONSENT_SCOPE_MISMATCH"


def test_an_operation_with_no_binding_never_takes_the_g3_path(steered):
    assert G.choose("capability_change", {"anything": True}) == (False, None)
    assert G.choose("ping", None) == (False, None)
    assert set(G.BINDINGS) == {"mode_raise"}


def test_where_the_standing_fails_the_typed_code_runs_with_the_reason(steered, endpoint, monkeypatch, capsys):
    monkeypatch.setattr(g3standing, "standing",
                        lambda *a, **k: g3standing.Standing(False, 3, "a weaker launch", "wait"))
    out = operator_client.request_raise(
        steered.root, MODE, requester="test",
        ask=lambda prompt: re.findall(r"confirmation code ([0-9A-F]{6})", "".join(endpoint.lines))[-1])
    assert out["mode"] == MODE and steered.fake.requests == 0 and steered.fake.consumed == []
    assert "a weaker launch" in capsys.readouterr().err
    assert "origin" not in next(r for r in _records(steered) if r.get("source") == "raise")["by"]["principal"]


@pytest.mark.parametrize("failure", [errors.Unavailable("no answer", reason="g3_unreachable"),
                                     errors.Unavailable("503", reason="g3_unavailable"),
                                     errors.PermissionDenied("403", reason="g3_peer_not_permitted"),
                                     errors.ValidationFailed("400", reason="g3_refused", status=400),
                                     errors.ValidationFailed("a 403 with no code", reason="g3_refused", status=403)],
                         ids=["no-answer", "503", "403", "400", "403-no-code"])
@pytest.mark.parametrize("where", ["request_approval", "await_decision"])
def test_no_answer_or_a_refused_peer_or_a_bad_request_is_held_before_consume_and_never_the_code(
        steered, endpoint, monkeypatch, failure, where):
    def fails(*a: Any, **k: Any) -> Any:
        raise failure

    monkeypatch.setattr(g3client, where, fails)
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert held.value.details["reason"] == G.HELD, held.value.details
    assert _mode(steered) != MODE and _no_code(endpoint.lines), "nothing raised, and no code shown"
    older = where == "request_approval" and failure.details.get("status") == 400
    assert (g3standing.INSTALL in held.value.message) == older, "only a refused set is taken for an older service"


def test_a_service_older_than_the_overlay_holds_and_names_the_reinstall(steered, endpoint, monkeypatch):
    """Planted: the service reads the sealed files only. The standing counts, so the code is not offered, and asking
    again gets the same answer: the reply gives the reason and the fix (ruling 1)."""
    from aew.stg02 import adopted
    from aew_g3 import wire as service_wire

    monkeypatch.setattr(service_wire, "o01_errors", lambda body: adopted.o01_errors("CommandSet", body))
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    message = held.value.message
    assert held.value.details["reason"] == G.HELD and "STRUCTURAL" in message
    assert g3standing.INSTALL in message and "keeps the ledger" in message and "request it again" not in message
    assert steered.fake.requests == 1 and steered.fake.consumed == [] and _no_code(endpoint.lines)


@pytest.mark.parametrize("where", ["request_approval", "await_decision", "_g3"])
def test_doing_what_a_held_reply_says_raises_the_mode_with_a_new_set_and_key(steered, endpoint, monkeypatch, where):
    """The way on is the operator's own: once the service answers, one more `aew lead mode raise` works, with nothing
    left over from the held one to conflict with."""
    real = getattr(g3client, where)
    monkeypatch.setattr(g3client, where, _raises(errors.Unavailable("no answer", reason="g3_unreachable")))
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    reply = held.value.message
    assert "once that is fixed" in reply or G.EVERY_REQUEST in reply
    with pytest.raises(errors.Unavailable):
        _raise(steered)  # not yet fixed: the same answer, as the reply says
    assert _mode(steered) != MODE

    monkeypatch.setattr(g3client, where, real)
    assert _raise(steered)["mode"] == MODE
    assert len(steered.fake.consumed) == 1
    assert len(steered.fake.keys) == len(set(steered.fake.keys)), "each request is a set of its own"


def test_doing_what_a_refusal_says_raises_the_mode(steered, endpoint):
    """What moved refuses with "request it again", at once: the next request binds the new values."""
    real = steered.engine.steering_raise_preview
    bound = real(MODE)

    def moved_once(mode: str) -> dict[str, Any]:
        steered.engine.steering_raise_preview = real
        return {**real(mode), "generation": bound["generation"] + 1}

    steered.fake.on_decide = lambda: setattr(steered.engine, "steering_raise_preview", moved_once)
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert "request it again" in refused.value.message
    steered.fake.on_decide = None
    assert _raise(steered)["mode"] == MODE


def _raises(failure: Exception) -> Any:
    def fails(*a: Any, **k: Any) -> Any:
        raise failure

    return fails


@pytest.mark.parametrize("wire", [
    _raises(errors.Unavailable("no answer", reason="g3_unreachable")),
    _raises(errors.Unavailable("an unreadable answer", reason="g3_not_g3")),
    _raises(errors.PermissionDenied("not this account's", reason="g3_peer_not_permitted")),
    lambda *a, **k: (503, {"code": "G3_UNAVAILABLE"}),
    lambda *a, **k: (403, {"code": "PEER_NOT_PERMITTED"}),
    lambda *a, **k: (400, {"code": "BAD_REQUEST"}),
    lambda *a, **k: (200, ["not", "an", "answer"]),
    lambda *a, **k: (200, {"wire_version": G3W.WIRE, "result": "CONSUMED"}),
], ids=["no-answer", "not-g3", "peer", "503", "403", "400", "not-a-result", "consumed-without-its-time"])
def test_a_consume_that_gets_no_result_is_held_and_never_the_code(steered, endpoint, monkeypatch, wire):
    monkeypatch.setattr(g3client, "_g3", wire)
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert held.value.details["reason"] == G.HELD, held.value.details
    assert "new approval" in held.value.message, "the client's way on reaches the operator"
    assert G.EVERY_REQUEST in held.value.message
    assert _mode(steered) != MODE and _no_code(endpoint.lines), "nothing raised, and no code shown"


def test_a_decline_is_refused_and_never_becomes_a_console_approval(steered, endpoint):
    steered.fake.decision = "DECLINE"
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert refused.value.details["reason"] == "declined"
    assert _no_code(endpoint.lines) and steered.fake.consumed == [] and _mode(steered) != MODE
    assert any("declined" in line for line in endpoint.lines), "the console says how it ended"


def test_a_standing_that_fails_after_the_approval_holds_and_the_next_request_takes_the_code(steered, endpoint,
                                                                                           monkeypatch):
    calls: list[int] = []

    def standing(*a: Any, **k: Any) -> g3standing.Standing:
        calls.append(1)
        return g3standing.Standing(len(calls) == 1, None if len(calls) == 1 else 3, "a weaker launch", "wait")

    monkeypatch.setattr(g3standing, "standing", standing)
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert held.value.details["reason"] == G.HELD and "a weaker launch" in held.value.message
    assert "typed code" in held.value.message
    assert steered.fake.consumed == [] and _mode(steered) != MODE, "consume is not called"
    assert "request it again" not in held.value.message, "the next request is what it names, and it takes the code"

    out = operator_client.request_raise(
        steered.root, MODE, requester="test",
        ask=lambda prompt: re.findall(r"confirmation code ([0-9A-F]{6})", "".join(endpoint.lines))[-1])
    assert out["mode"] == MODE and steered.fake.consumed == [], "doing what the reply says raises it by the code"


def test_what_moved_after_the_approval_refuses_before_consume_and_does_not_spend_it(steered, endpoint):
    """Each bound value that moves is named, and a generation that moves between the approval and the consume refuses
    with consume not called."""
    bound = steered.engine.steering_raise_preview(MODE)
    assert G.moved(G.raise_set(bound), bound) is None
    later = {**bound, "generation": bound["generation"] + 1}
    assert G.moved(G.raise_set(bound), later) == "the Lead generation"
    later = {**bound, "mode_rev": (bound["mode_rev"] or 0) + 1}
    assert G.moved(G.raise_set(bound), later) == "the current mode's record"
    later = {**bound, "previous": "walk"}
    assert G.moved(G.raise_set(bound), later) == "the current mode"
    later = {**bound, "legality_digest": "f" * 64}
    assert G.moved(G.raise_set(bound), later) == "the adopted policy's legality digest"
    assert steering.RANK[None] == steering.RANK["crawl"], "a mode never set is carried as the lowest"

    real = steered.engine.steering_raise_preview

    def moving(mode: str) -> dict[str, Any]:
        return {**real(mode), "generation": bound["generation"] + 1}

    steered.fake.on_decide = lambda: setattr(steered.engine, "steering_raise_preview", moving)
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert "the Lead generation moved" in refused.value.message and "not spent" in refused.value.message
    assert steered.fake.consumed == [] and _mode(steered) != MODE


def _principal() -> Any:
    return operator_endpoint.OperatorPrincipal(uid=None, method="peer_credentials", endpoint_pid=1,
                                               endpoint_started_at="t")


def test_a_mode_that_left_and_came_back_during_the_wait_refuses_on_its_version(steered, endpoint):
    """The current mode reads the same, so only the record's version shows it moved (I6-06.a): real records, between
    the approval and the consume."""
    engine, project = steered.engine, steered.project

    def left_and_back() -> None:
        now = engine.steering_raise_preview(MODE)
        engine.steering_raise(_principal(), mode=MODE, generation=now["generation"],
                              legality_digest=now["legality_digest"])
        engine.steering_lower(token=project.token, expect_rev=project.rev(), mode="crawl")

    steered.fake.on_decide = left_and_back
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert "the current mode's record moved" in refused.value.message and "not spent" in refused.value.message
    assert steered.fake.consumed == [] and _mode(steered) == "crawl"


def test_a_policy_adopted_during_the_wait_refuses_and_does_not_spend_the_approval(steered, endpoint):
    steered.fake.on_decide = lambda: _policy(steered.project, mode="allow_weaker")  # the digest covers this field
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert "the adopted policy's legality digest moved" in refused.value.message
    assert "not spent" in refused.value.message and "reason_ref" not in refused.value.message
    assert steered.fake.consumed == [] and _mode(steered) != MODE


def _policy(project, **containment) -> None:
    path = project.root / ".aew/policy/execution.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    doc["containment"] = {**(doc.get("containment") or {}), **containment}
    path.write_bytes(yaml.safe_dump(doc).encode())
    project.adopt_policy()


@pytest.fixture
def judged(steered, monkeypatch):
    """The real standing, on the project's real policy: only the host's conditions, 1 and 3, are stood in."""
    monkeypatch.setattr(g3standing, "standing", REAL_STANDING)
    monkeypatch.setattr(g3standing, "installed", lambda platform=None: None)
    monkeypatch.setattr(g3standing, "no_weaker_context", lambda now=None: None)
    return steered


def test_the_real_standing_judges_this_projects_policy_at_the_challenge(judged, capsys):
    """A policy that does count is the real-wire tests' (Linux: Windows has no containment, so nothing counts there)."""
    _policy(judged.project, mode="allow_weaker")
    lines: list[str] = []
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(judged.project.root), console=lines.append, dev=True,
                                            timeout=30)
    ep.start()
    try:
        out = operator_client.request_raise(
            judged.root, MODE, requester="test",
            ask=lambda prompt: re.findall(r"confirmation code ([0-9A-F]{6})", "".join(lines))[-1])
    finally:
        ep.close()
    assert out["mode"] == MODE and judged.fake.requests == 0, "a project that lets launches run weaker takes the code"
    assert "containment.mode" in capsys.readouterr().err


def test_the_real_standing_judges_the_projects_policy_again_before_consume(judged):
    _policy(judged.project, mode="required", network={"mode": "proxy_only"})
    policy, _ = judged.engine.execution_policy()
    approved, record = G.approve(G.raise_set(judged.engine.steering_raise_preview(MODE)), lambda p: None)
    with pytest.raises(errors.Unavailable) as held:
        G.consume_member(approved, record, {**policy, "containment": {"mode": "allow_weaker"}})
    assert held.value.details["reason"] == G.HELD and "containment.mode" in held.value.message
    assert judged.fake.consumed == []


def test_a_requester_that_has_gone_ends_the_wait_and_says_so_and_frees_the_endpoint(steered, endpoint):
    steered.fake.undecided = True
    conn = operator_client._connect(steered.root)
    operator_client._send(conn, "mode_raise", {"mode": MODE, "requester": "test"})
    approval = operator_client._reply(conn)["approval_ref"]
    conn.close()
    deadline = time.monotonic() + ENDED
    while not any("has gone" in line for line in endpoint.lines):
        assert time.monotonic() < deadline, "the wait did not end"
        time.sleep(0.01)
    assert any(approval in line for line in endpoint.lines) and steered.fake.consumed == [] and _mode(steered) != MODE
    steered.fake.undecided = False
    assert _raise(steered)["mode"] == MODE, "the endpoint is free again"


def test_a_requester_gone_before_the_acknowledgement_still_says_how_it_ended(steered, endpoint):
    conn = operator_client._connect(steered.root)
    steered.fake.on_request = conn.close  # gone once the approval exists, before the endpoint can say so
    operator_client._send(conn, "mode_raise", {"mode": MODE, "requester": "test"})
    deadline = time.monotonic() + ENDED
    while not any("has gone" in line for line in endpoint.lines):
        assert time.monotonic() < deadline, "the console did not say how it ended"
        time.sleep(0.01)
    steered.fake.on_request = None
    assert steered.fake.consumed == [] and _mode(steered) != MODE
    assert _raise(steered)["mode"] == MODE, "the endpoint is free again"


@pytest.mark.parametrize("failure", [errors.PermissionDenied("not this account's", reason="g3_peer_not_permitted"),
                                     errors.ValidationFailed("a 403 with no code", reason="g3_refused", status=403)],
                         ids=["peer", "403-no-code"])
def test_a_hold_for_the_wrong_account_names_the_step_that_fixes_it(steered, endpoint, monkeypatch, failure):
    monkeypatch.setattr(g3client, "request_approval", _raises(failure))
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert "--operator" in held.value.message and "outside any sandbox" in held.value.message
    assert "once that is fixed" not in held.value.message


def test_a_hold_for_an_answer_that_is_not_g3s_names_where_to_look_and_the_install(steered, endpoint, monkeypatch):
    monkeypatch.setattr(g3client, "await_decision",
                        _raises(errors.Unavailable("not the G3 wire's", reason="g3_not_g3")))
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert "systemctl status aew-g3.service" in held.value.message and g3standing.INSTALL in held.value.message
    assert "once that is fixed" not in held.value.message


def test_the_busy_refusal_stops_naming_an_approval_once_its_request_has_ended(steered, endpoint, monkeypatch):
    """A later typed challenge is the one to answer: deciding a finished approval would change nothing."""
    steered.fake.decision = "DECLINE"
    with pytest.raises(errors.OperatorAuthorizationRequired):
        _raise(steered)
    monkeypatch.setattr(g3standing, "standing",
                        lambda *a, **k: g3standing.Standing(False, 3, "a weaker launch", "wait"))
    conn = operator_client._connect(steered.root)
    try:
        operator_client._send(conn, "mode_raise", {"mode": MODE, "requester": "test"})
        assert operator_client._reply(conn)["challenge"] == "shown"
        with pytest.raises(errors.PermissionDenied) as busy:
            _raise(steered)
        assert "confirmer" not in busy.value.message and "g3:approval" not in busy.value.message
        assert "another request" in busy.value.message
    finally:
        conn.close()


def test_a_requester_gone_when_the_approval_arrives_spends_nothing(steered, endpoint):
    conn = operator_client._connect(steered.root)
    steered.fake.on_decide = conn.close  # gone between the operator's approval and the consume
    operator_client._send(conn, "mode_raise", {"mode": MODE, "requester": "test"})
    deadline = time.monotonic() + ENDED
    while not any("has gone" in line for line in endpoint.lines):
        assert time.monotonic() < deadline, "the request did not end"
        time.sleep(0.01)
    assert steered.fake.consumed == [] and _mode(steered) != MODE


def test_while_an_approval_waits_the_busy_refusal_names_it_and_the_confirmer(steered, endpoint):
    steered.fake.undecided = True
    conn = operator_client._connect(steered.root)
    try:
        operator_client._send(conn, "mode_raise", {"mode": MODE, "requester": "test"})
        approval = operator_client._reply(conn)["approval_ref"]
        with pytest.raises(errors.PermissionDenied) as busy:
            _raise(steered)
        assert approval in busy.value.message and "decline" in busy.value.message and "confirmer" in busy.value.message
    finally:
        steered.fake.undecided = False
        conn.close()


def test_the_raise_gets_the_values_the_consent_bound_so_its_own_staleness_refusals_decide(steered):
    bound = steered.engine.steering_raise_preview(MODE)
    values = G.bound_values(G.raise_set(bound))
    assert (values.mode, values.generation, values.legality_digest) == (MODE, bound["generation"],
                                                                        bound["legality_digest"])
    with pytest.raises(errors.AEWError) as stale:
        steered.engine.steering_raise(_principal(), mode=values.mode, generation=values.generation + 1,
                                      legality_digest=values.legality_digest)
    assert "generation" in stale.value.message


def test_a_concurrent_request_waits_its_turn_on_the_g3_path_too(steered, endpoint):
    entered, leave = threading.Event(), threading.Event()

    def hold() -> None:
        entered.set()
        leave.wait(ENDED)

    steered.fake.on_decide = hold
    first: list[Any] = []
    t = threading.Thread(target=lambda: first.append(_raise(steered)), daemon=True)
    t.start()
    assert entered.wait(ENDED)
    with pytest.raises(errors.PermissionDenied) as busy:
        _raise(steered)
    assert "another request" in busy.value.message
    leave.set()
    t.join(ENDED)
    assert first and first[0]["mode"] == MODE


def test_the_lead_is_told_who_decides_and_how(steered):
    project = steered.project
    said = steered.engine.steering_request(token=project.token, expect_rev=project.rev(), kind="raise",
                                           rationale="the work is ready", mode=MODE)
    assert f"aew lead mode raise {MODE}" in said["next"]
