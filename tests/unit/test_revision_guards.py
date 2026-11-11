"""Regressions for the engine's in-lock revision-class guards."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from aew.engine.nonmutating_ops import NonMutating
from aew.errors import GateUnsatisfied


class ReachedFreshnessCheck(Exception):
    pass


@pytest.mark.parametrize("matches", [True, False])
def test_plan_adopt_compares_the_loaded_evidence_with_the_accepted_sha(matches):
    proposal = {"id": "E-0001", "kind": "plan_proposal", "sha256": "accepted"}
    source = {"kind": "ticket", "mutating": False, "state": "DONE", "execution": {"record": proposal}}
    target = {"state": "PROPOSED"}
    ev = {"_sha256": "accepted" if matches else "modified"}

    def authoritative_commit():
        raise ReachedFreshnessCheck

    ctx = SimpleNamespace(state={})
    commands = NonMutating.__new__(NonMutating)
    commands.k = SimpleNamespace(lead_txn=lambda *args, **kwargs: nullcontext(ctx),
                                 authoritative_commit=authoritative_commit)
    commands.units = SimpleNamespace(unit=lambda *args: target, view=lambda *args: source)
    commands.roles = SimpleNamespace(resolve_plan_assurance=lambda *args, **kwargs: {})
    commands.inputs = SimpleNamespace(find_unit_evidence=lambda *args: ev)
    refusal = ReachedFreshnessCheck if matches else GateUnsatisfied
    with pytest.raises(refusal) as exc:
        commands.plan_adopt(token="synthetic", expect_rev=1, work_id="T-0002", evidence_id="E-0001", source="T-0001")
    if not matches:
        assert exc.value.details == {"evidence": "E-0001", "expected": "accepted", "current": "modified"}
