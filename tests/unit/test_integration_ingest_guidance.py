"""Focused, store-free coverage for integration verification refusal guidance."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from aew.engine.evidence_ops import EvidenceCommands
from aew.errors import IllegalTransition


class _Gates:
    def __init__(self, evidence: dict[str, Any]) -> None:
        self.evidence = evidence

    def find_evidence(self, _work_id: str, _evidence_id: str) -> dict[str, Any]:
        return self.evidence


class _Queue:
    def __init__(self, lease: dict[str, Any] | None) -> None:
        self.lease = lease

    def sync(self, _state: dict[str, Any]) -> None:
        pass

    def require_live_lease(self, _state: dict[str, Any], _work_id: str, _what: str) -> dict[str, Any] | None:
        if self.lease is None:
            raise IllegalTransition("no live lease")
        return self.lease


_LIVE = object()


def _query(state: dict[str, Any], evidence_id: str, *, lease: dict[str, Any] | None | object = _LIVE) -> Any:
    if lease is _LIVE:
        lease = {"custodian": "lead"}
    evidence = {
        "id": evidence_id,
        "kind": "verification",
        "producer": {"invocation": "INV-1"},
        "verification": {"scope": "integration"},
        "evaluated_snapshot": {"relevant_inputs_fingerprint": "candidate"},
    }
    commands = EvidenceCommands.__new__(EvidenceCommands)
    commands.gates = _Gates(evidence)
    commands.queue = _Queue(lease)
    commands.k = type("Kernel", (), {})()
    commands.k.policy = lambda _name: {}
    commands._verification_outcome = lambda *_args: (None, "validated", False)
    commands.gates.require_bound_report = lambda *_args, **_kwargs: None
    commands.gates.require_current_binding = lambda *_args, **_kwargs: None
    commands.invocations = type("Invocations", (), {})()
    commands.invocations.current_snapshot = lambda _unit: {"relevant_inputs_fingerprint": "candidate"}
    commands.invocations.snapshot_of = lambda *_args: {"relevant_inputs_fingerprint": "candidate"}
    return commands._query_ticket_verification(state, "T-1", {"evidence": evidence_id})


def _state(*, status: str | None, state: str = "COMMIT_READY", evidence: str | None = "EV-1") -> dict[str, Any]:
    integration = {"status": status}
    if evidence is not None:
        integration["post_integration_evidence"] = evidence
    return {"work": {"T-1": {"state": state, "integration": integration}},
            "invocations": {"INV-1": {"role": "verifier", "work_unit": "T-1"}}}


def test_already_ingested_live_candidate_guidance_is_specific_and_pure() -> None:
    state = _state(status="validated")
    before = copy.deepcopy(state)

    blocker = _query(state, "EV-1")

    assert blocker.error.code == "ILLEGAL_TRANSITION"
    assert "integration verification is already ingested" in blocker.message
    assert "candidate is leased for publishing" in blocker.message
    assert "aew integrate publish T-1 --expect-rev N" in blocker.message
    assert "ingest again" in blocker.message
    assert state == before


@pytest.mark.parametrize(
    ("status", "unit_state", "evidence_id", "lease"),
    [
        (None, "COMMIT_READY", "EV-1", {"custodian": "lead"}),
        ("validated", "VERIFY_PENDING", "EV-1", {"custodian": "lead"}),
        ("validated", "COMMIT_READY", "EV-other", {"custodian": "lead"}),
        ("validated", "COMMIT_READY", "EV-1", None),
    ],
)
def test_nearby_states_and_evidence_keep_original_never_prepared_guidance(
    status: str | None, unit_state: str, evidence_id: str, lease: dict[str, Any] | None
) -> None:
    state = _state(status=status, state=unit_state)
    blocker = _query(state, evidence_id, lease=lease)

    assert blocker.error.code == "ILLEGAL_TRANSITION"
    assert blocker.message == "T-1 has no prepared integration candidate"
