"""Which declared primitives a stage step can run (M4-E E3; #140 re-review, finding 1).

A stage step is one primitive in one Lead transaction, and the journal checks the transaction's op against the
planned primitive's. So every declared primitive is either refused at a stage's opening (``NOT_STEPS``), or every op
``commit_ops`` names for it is an op some Lead transaction in the engine is entered under: a map that named an op no
transaction uses would open stages whose steps could never commit."""

from __future__ import annotations

import re
from pathlib import Path

from aew.engine import primitives as P

ENGINE = Path(P.__file__).resolve().parent
LEAD_TXN_OP = re.compile(r"lead_txn\(\s*[^,()]+,\s*[^,()]+,\s*\"([a-z_.]+)\"")


def lead_txn_ops() -> set[str]:
    return {m.group(1) for f in ENGINE.glob("*.py") for m in LEAD_TXN_OP.finditer(f.read_text(encoding="utf-8"))}


def test_every_declared_primitive_is_a_runnable_step_or_refused_at_opening():
    ops = lead_txn_ops()
    assert {"checkpoint", "work.assign", "steering.lower", "invoke.create"} <= ops  # the scan finds the engine's ops
    missing = {p: sorted(P.commit_ops(p) - ops) for p in P.SPECS
               if p not in P.NOT_STEPS and P.commit_ops(p) - ops}
    assert not missing, f"primitives whose commit op no Lead transaction is entered under: {missing}"
    assert set(P.NOT_STEPS) <= set(P.SPECS)  # only declared primitives are listed as not steps
    assert P.BY_DECISION <= {p for p in P.SPECS if P.SPECS[p].guard_id == p}  # each has a decision of its own name


def test_a_creation_step_commits_only_the_variant_its_decision_names():
    """#140 re-review: the three creations commit under one op and the engine chooses among them by the unit's kind,
    so a step planned as one is committed only when the transaction's dispatch decision names that one."""
    from types import SimpleNamespace

    import pytest

    from aew.engine import stage_intents as SI
    from aew.engine.dispatch import DispatchDecision
    from aew.errors import IllegalTransition

    class Reached(Exception):
        """The step passed the primitive check and went on to the policy check."""

    def k():
        return SimpleNamespace(policy_digests=lambda: (_ for _ in ()).throw(Reached()))

    def ctx(entrypoint):
        intent = {"id": "SI-0001", "status": "ACTIVE", "generation": 1, "steps": [],
                  "plan": [{"n": 1, "primitive": "invoke.create.mutating", "operation_class": "POLICY_RESOLVED",
                            "key": "SI-0001:1"}]}
        decision = DispatchDecision(entrypoint=entrypoint, work_id="T-0001", revision=1, generation=1, channel="cli")
        return SimpleNamespace(state={"stage_intents": {"SI-0001": intent}, "lead": {"generation": 1}},
                               txn_op="invoke.create", dispatch_decisions=[decision])

    journal = SI.StageIntents(k(), archive=None)
    with SI.step("SI-0001", 1), pytest.raises(IllegalTransition) as exc:
        journal.finalize(ctx("invoke.create.non_mutating"))
    assert exc.value.details["reason"] == "step_primitive_mismatch"
    with SI.step("SI-0001", 1), pytest.raises(Reached):
        journal.finalize(ctx("invoke.create.mutating"))
