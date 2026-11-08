"""G3 at the operator endpoint: where G3 counts and the operation is bound, a consumed approval stands in for the typed
code, for one challenge (the G3-C brief's PR C3 and the designer's rulings). The G3 service here is the real one's rules
(``aew_g3.service``) with a stand-in PIN, called directly, so every platform runs it; only its sockets are left out."""

from __future__ import annotations

import copy
import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from aew import errors, g3client, g3standing
from aew.engine.api import Engine
from aew.harness import g3_adapter as G
from aew.harness import operator_client, operator_endpoint
from aew_g3 import wire as G3W
from g3 import PIN, make

MODE = "walk"
ENDED = 60.0


class FakeG3:
    """``g3client``'s calls on the real service's rules, with a counter on each: the confirmer's part is ``decide``."""

    def __init__(self, service: Any) -> None:
        self.service = service
        self.consumed: list[dict[str, Any]] = []
        self.requests = 0
        self.on_decide: Any = None
        self.decision = "APPROVE"

    def request_approval(self, cset: dict[str, Any], sock_path: str | None = None) -> dict[str, Any]:
        self.requests += 1
        status, body = self.service.request({"wire_version": G3W.WIRE, "command_set": cset})
        if status != 201:
            raise g3client._g3_refusal(status, body)
        return body

    def await_decision(self, pending: dict[str, Any], sock_path: str | None = None, **_: Any) -> dict[str, Any]:
        if self.on_decide:
            self.on_decide()
        body = {"decision": "APPROVE", "pin": PIN} if self.decision == "APPROVE" else {"decision": "DECLINE"}
        status, out = self.service.decide(pending["approval_ref"], body)
        if self.decision == "DECLINE":
            assert status == 204, out
            raise errors.OperatorAuthorizationRequired("the operator declined", reason="declined")
        assert status == 200, out
        return out

    def consume(self, **fields: Any) -> Any:
        self.consumed.append(fields)
        status, out = self.service.consume({"wire_version": G3W.WIRE, **fields})
        return SimpleNamespace(result=out["result"] if status == 200 else None,
                               held_why=f"the service answered {status}")


@pytest.fixture
def steered(project, monkeypatch, tmp_path):
    (project.root / ".aew/policy/execution.yaml").open("a", encoding="utf-8").write("\nsteering:\n  mode: crawl\n")
    project.adopt_policy()
    fake = FakeG3(make(tmp_path / "g3").svc)
    monkeypatch.setattr(g3client, "request_approval", fake.request_approval)
    monkeypatch.setattr(g3client, "await_decision", fake.await_decision)
    monkeypatch.setattr(G, "_consume", fake.consume)
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


def _mode(steered) -> str | None:
    from aew.engine import steering

    return steering.effective(steered.engine.store.current())["mode"]


def _records(steered) -> list[dict[str, Any]]:
    return [json.loads(line) for f in sorted((steered.root / "records/steering").glob("*.jsonl"))
            for line in f.read_text(encoding="utf-8").splitlines()]


def test_an_approval_consumed_raises_the_mode_and_its_record_names_the_consent(steered, endpoint):
    out = _raise(steered)
    assert out["mode"] == MODE and _mode(steered) == MODE
    assert endpoint.lines == [], "no code, and nothing on the console"
    assert [f["owner"] for f in steered.fake.consumed] == ["ADC"]
    record = next(r for r in _records(steered) if r.get("source") == "raise")
    origin = record["by"]["principal"]["origin"]
    assert origin["kind"] == "g3" and origin["consent_set_ref"] == steered.fake.consumed[0]["consent_set_ref"]
    assert steered.fake.consumed[0]["operation_ref"].startswith("aew:steering-raise:")


def test_a_replayed_consent_is_refused_by_the_service(steered, endpoint, monkeypatch):
    """The endpoint never takes a consent from a requester, so a replay is the same consent consumed twice."""
    _raise(steered)
    replay = {**steered.fake.consumed[0], "operation_ref": "aew:steering-raise:again"}
    status, out = steered.fake.service.consume({"wire_version": G3W.WIRE, **replay})
    assert status == 200 and out["result"] == "CONSENT_ALREADY_USED"


def test_a_consume_answered_with_anything_else_is_refused_and_nothing_rises(steered, endpoint, monkeypatch):
    monkeypatch.setattr(G, "_consume", lambda **f: SimpleNamespace(result="CONSENT_SCOPE_MISMATCH", held_why=None))
    with pytest.raises(errors.AEWError) as refused:
        _raise(steered)
    assert "CONSENT_SCOPE_MISMATCH" in refused.value.message and "request it again" in refused.value.message
    assert _mode(steered) != MODE


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
        ask=lambda prompt: __import__("re").findall(r"confirmation code ([0-9A-F]{6})", "".join(endpoint.lines))[-1])
    assert out["mode"] == MODE and steered.fake.requests == 0 and steered.fake.consumed == []
    assert "a weaker launch" in capsys.readouterr().err
    assert "origin" not in next(r for r in _records(steered) if r.get("source") == "raise")["by"]["principal"]


@pytest.mark.parametrize("failure", [errors.Unavailable("no answer", reason="g3_unreachable"),
                                     errors.Unavailable("503", reason="g3_unavailable"),
                                     errors.PermissionDenied("403", reason="g3_peer_not_permitted"),
                                     errors.ValidationFailed("400", reason="g3_refused", status=400)],
                         ids=["no-answer", "503", "403", "400"])
@pytest.mark.parametrize("where", ["request_approval", "await_decision", "consume"])
def test_no_answer_or_a_refused_peer_or_a_bad_request_is_held_at_every_step_and_never_the_code(
        steered, endpoint, monkeypatch, failure, where):
    def fails(*a: Any, **k: Any) -> Any:
        raise failure

    if where == "consume":
        monkeypatch.setattr(G, "_consume", fails)
    else:
        monkeypatch.setattr(g3client, where, fails)
    with pytest.raises(errors.Unavailable) as held:
        _raise(steered)
    assert held.value.details["reason"] == G.HELD, held.value.details
    assert _mode(steered) != MODE and endpoint.lines == [], "nothing raised, and no code shown"


def test_a_decline_is_refused_and_never_becomes_a_console_approval(steered, endpoint):
    steered.fake.decision = "DECLINE"
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert refused.value.details["reason"] == "declined"
    assert endpoint.lines == [] and steered.fake.consumed == [] and _mode(steered) != MODE


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


def test_what_moved_after_the_approval_refuses_before_consume_and_does_not_spend_it(steered, endpoint):
    """Each bound value that moves is named, and a generation that moves between the approval and the consume refuses
    with consume not called."""
    from aew.engine import steering

    bound = steered.engine.steering_raise_preview(MODE)
    assert G.moved(G.raise_set(bound), bound) is None
    later = {**bound, "generation": bound["generation"] + 1}
    assert G.moved(G.raise_set(bound), later) == "lead_generation_ref"
    later = {**bound, "mode_rev": (bound["mode_rev"] or 0) + 1}
    assert G.moved(G.raise_set(bound), later) == "mode_version"
    later = {**bound, "previous": "walk"}
    assert G.moved(G.raise_set(bound), later) == "current_mode"
    assert steering.RANK[None] == steering.RANK["crawl"], "a mode never set is carried as the lowest"

    real = steered.engine.steering_raise_preview

    def moving(mode: str) -> dict[str, Any]:
        return {**real(mode), "generation": bound["generation"] + 1}

    steered.fake.on_decide = lambda: setattr(steered.engine, "steering_raise_preview", moving)
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _raise(steered)
    assert "lead_generation_ref" in refused.value.message and "not spent" in refused.value.message
    assert steered.fake.consumed == [] and _mode(steered) != MODE


def test_the_raise_gets_the_values_the_consent_bound_so_its_own_staleness_refusals_decide(steered):
    bound = steered.engine.steering_raise_preview(MODE)
    values = G.bound_values(G.raise_set(bound))
    assert (values.mode, values.generation, values.legality_digest) == (MODE, bound["generation"],
                                                                        bound["legality_digest"])
    with pytest.raises(errors.AEWError) as stale:
        steered.engine.steering_raise(operator_endpoint.OperatorPrincipal(
            uid=None, method="peer_credentials", endpoint_pid=1, endpoint_started_at="t"), mode=values.mode,
            generation=values.generation + 1, legality_digest=values.legality_digest)
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
