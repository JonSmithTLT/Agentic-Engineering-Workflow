"""The dispatch predicate's own refusals (M4-A; register E2 coverage): a guard registry that is wrong fails at
composition, an unknown entrypoint or unit is refused before any guard runs, and the commit check refuses a harness run
that no decision for that invocation admitted, even when a decision for another unit or invocation was made."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from aew.engine.dispatch import ENTRYPOINTS, Dispatch, DispatchDecision, GuardRegistration
from aew.errors import DispatchUndecided, NotFound, UsageError


def _pass(state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> None:
    return None


def _dispatch() -> Dispatch:
    return Dispatch(SimpleNamespace(aew_root=None, manifest={}))  # type: ignore[arg-type]


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
