"""The dispatch predicate's own refusals (M4-A; register E2 coverage): a guard registry that is wrong fails at
composition, an unknown entrypoint or unit is refused before any guard runs, and the commit check refuses a harness run
that no decision for that invocation admitted, even when a decision for another unit or invocation was made."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from aew.engine.dispatch import CREATES_SCOPE, ENTRYPOINTS, Dispatch, DispatchDecision, GuardRegistration
from aew.errors import DispatchUndecided, NotFound, UsageError


def _pass(state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> None:
    return None


def _dispatch(legality: str = "L", operational: str = "O") -> Dispatch:
    digests = {"legality_digest": legality, "operational_digest": operational}
    return Dispatch(SimpleNamespace(aew_root=None, manifest={}, policy_digests=lambda: dict(digests)))  # type: ignore[arg-type]


def _decision(work_id: str, entrypoint: str, revision: int = 7, **facts: Any) -> DispatchDecision:
    return DispatchDecision(entrypoint=entrypoint, work_id=work_id, revision=revision, generation=1, channel="direct",
                            facts=facts)


def _ctx(before: dict[str, Any], after: dict[str, Any], decisions: list[DispatchDecision], revision: int = 7) -> Any:
    session = SimpleNamespace(revision=revision, committed_view=lambda: {"invocations": before})
    return SimpleNamespace(session=session, state={"invocations": after}, dispatch_decisions=decisions)


def test_a_guard_registered_twice_is_a_composition_error():
    d = _dispatch()
    d.register_all([GuardRegistration("readiness", _pass)])
    with pytest.raises(ValueError, match="readiness is already registered"):
        d.register_all([GuardRegistration("readiness", _pass)])


def test_an_entrypoint_guard_without_an_implementation_is_a_composition_error():
    d = _dispatch()
    with pytest.raises(ValueError, match="without an implementation"):
        d.require_complete()
    d.register_all([GuardRegistration(g, _pass) for g in sorted({g for e in ENTRYPOINTS.values() for g in e.guards})])
    d.require_complete()


def test_every_entrypoint_that_creates_an_invocation_declares_the_scope_it_creates():
    """Admission binds the new invocation's scope (PR #32 review, P2): a new creating entrypoint must say which."""
    # harness.launch creates a run, not an invocation; integrate.prepare creates the lease's engine custody
    # invocation, which has no scope or role and is admitted by its own rule (M4-D).
    creating = {n for n, e in ENTRYPOINTS.items() if not e.covered_by and n not in {"harness.launch",
                                                                                    "integrate.prepare"}}
    assert set(CREATES_SCOPE) == creating
    assert {s for s in CREATES_SCOPE.values() if s} <= {"ticket", "observation", "parent"}


def test_a_wrapper_entrypoint_cannot_be_decided_on_its_own():
    state = {"revision": 3, "work": {"T-0001": {}}}
    for name, entry in ENTRYPOINTS.items():
        if entry.covered_by:
            with pytest.raises(UsageError, match="covered by"):
                _dispatch().decide(state, name, "T-0001")


def test_an_unknown_entrypoint_or_unit_is_refused_before_any_guard_runs():
    d = _dispatch()  # no guards registered: reaching one would raise KeyError
    state = {"revision": 3, "work": {"T-0001": {}}}
    with pytest.raises(UsageError) as unknown:
        d.decide(state, "work.teleport", "T-0001")
    assert "work.assign" in unknown.value.details["known"]
    with pytest.raises(NotFound):
        d.decide(state, "work.assign", "T-0404")


def test_a_new_run_needs_a_harness_launch_decision_for_its_own_invocation():
    old = {"I-0001": {"work_unit": "T-0001", "runs": [{"run": 1}]}}

    def after() -> dict[str, Any]:
        return {"I-0001": {"work_unit": "T-0001", "runs": [{"run": 1}, {"run": 2}]}}

    elsewhere = [_decision("T-0002", "harness.launch", invocation="I-0009"),  # another unit's launch
                 _decision("T-0001", "harness.launch", invocation="I-0002"),  # this unit, another invocation
                 _decision("T-0001", "work.assign")]  # this unit, but not a launch
    with pytest.raises(DispatchUndecided) as refused:
        _dispatch().finalize(_ctx(old, after(), elsewhere))
    assert refused.value.details == {"invocation": "I-0001", "run": 2}

    state = after()
    _dispatch().finalize(_ctx(old, state, [*elsewhere, _decision("T-0001", "harness.launch", invocation="I-0001")]))
    assert state["I-0001"]["runs"][1]["dispatch"]["entrypoint"] == "harness.launch"
    assert "dispatch" not in state["I-0001"]["runs"][0]  # an existing run is not re-attributed


def test_admission_binds_the_workspace_the_guards_resolved():
    """D5: a decision whose guards resolved a workspace admits only an invocation for that workspace."""
    card = SimpleNamespace(id="code_reviewer", sha256="c" * 64, archetype="reviewer")
    d = _decision("T-0001", "invoke.create.mutating", card=card, role="reviewer", scope="ticket",
                  workspace="/w/T-0001", workspace_id="ws-1")
    inv = {"work_unit": "T-0001", "role": "reviewer", "scope": "ticket", "card": {"id": card.id, "sha256": card.sha256},
           "workspace": "/w/T-0001", "workspace_id": "ws-1"}
    assert Dispatch._admitting_invocation([d], inv, set()) is d
    assert Dispatch._admitting_invocation([d], {**inv, "workspace": "/w/other", "workspace_id": "ws-2"}, set()) is None


def test_the_assurance_guards_refuse_to_run_without_the_archetype():
    """D7: an entrypoint that reaches the assurance guards without resolving the archetype is an engine defect, not
    a silent pass."""
    from aew.errors import IntegrityError

    d = _dispatch()
    d.register_all([GuardRegistration(g, _pass) for g in sorted({g for e in ENTRYPOINTS.values() for g in e.guards})])
    with pytest.raises(IntegrityError, match="without resolving the archetype"):
        d.decide({"revision": 3, "work": {"T-0001": {}}}, "work.assign", "T-0001")


def test_a_decision_is_stale_only_when_legality_affecting_policy_changed():
    """A3 §3 and §9: the commit check binds a decision to the legality digest it was made under. An operational
    change (a different operational digest) admits the decision; a legality change refuses it."""
    old = {"I-0001": {"work_unit": "T-0001", "runs": [{"run": 1}]}}

    def admit(decided: dict[str, str]) -> dict[str, Any]:
        state = {"I-0001": {"work_unit": "T-0001", "runs": [{"run": 1}, {"run": 2}]}}
        launch = _decision("T-0001", "harness.launch", invocation="I-0001")
        launch.dependency_digests.update(decided)
        _dispatch().finalize(_ctx(old, state, [launch]))
        return state["I-0001"]["runs"][1]["dispatch"]

    recorded = admit({"legality_digest": "L", "operational_digest": "old operational"})
    assert recorded["legality_digest"] == "L" and recorded["operational_digest"] == "old operational"
    with pytest.raises(DispatchUndecided, match="legality-affecting policy"):
        admit({"legality_digest": "old legality", "operational_digest": "O"})
