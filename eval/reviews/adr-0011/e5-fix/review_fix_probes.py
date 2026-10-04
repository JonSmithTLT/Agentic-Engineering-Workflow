"""Independent routing checks for fb4c912; disposable review artifact."""
from pathlib import Path
from types import SimpleNamespace

from aew.engine.api import Engine
from aew.engine.seams import (
    CLASSIFY_VERIFICATION, GATE_CONTEXT, INGEST, INVOKE, NEXT_ACTIONS,
    MUTATING, NON_MUTATING, PARENT,
)
from aew.errors import NotFound, UsageError


engine = Engine(Path.cwd(), Path.cwd() / "not-a-project")
units = {
    "T-0001": {"kind": "ticket", "mutating": True},
    "T-0002": {"kind": "ticket", "mutating": False},
    "S-0001": {"kind": "story"},
    "E-0001": {"kind": "epic"},
}
expected_kinds = {"T-0001": MUTATING, "T-0002": NON_MUTATING,
                  "S-0001": PARENT, "E-0001": PARENT}
state = {"work": units, "lead": {"status": "active"}}
engine._evidence.k = SimpleNamespace(store=SimpleNamespace(read=lambda: state))
engine._resume.k = SimpleNamespace(
    manifest={"authority": {"candidates": []}},
    policy=lambda name: {"checks": {}},
)
engine._resume.roles = SimpleNamespace(policy_problems=lambda: [])
engine._resume.harness = SimpleNamespace(harness_resume=lambda state: [])
kinds = engine._gates.kinds
calls = []


def sentinel(key):
    def handler(*args, **kwargs):
        calls.append((key, args, kwargs))
        if key[0] == NEXT_ACTIONS:
            return [key[1]]
        return {"routed": key}
    return handler


for key in kinds.table():
    kinds._table[key] = sentinel(key)

count = 0
for work_id, kind in expected_kinds.items():
    auth = {"token": "lead-token", "expect_rev": 42, "work_id": work_id}
    ev_only_kind = PARENT if kind == PARENT else NON_MUTATING
    cases = [
        (GATE_CONTEXT, kind, lambda: engine.gate_context(state, work_id)),
        (GATE_CONTEXT, ev_only_kind, lambda: engine.evidence_gate_context(state, work_id)),
        (INVOKE, kind, lambda: engine.invoke_create(**auth, role="verifier", card="v", scope="ticket",
                                                   execution_profile={"profile": "p"}, launch=True)),
        (INVOKE, ev_only_kind, lambda: engine.invoke_evidence_unit(**auth, role="reviewer", card="r",
                                                                 scope="ticket")),
        (INGEST, kind, lambda: engine.review_ingest(**auth, evidence_id="EV-r")),
        (INGEST, kind, lambda: engine.verify_ingest(**auth, evidence_id="EV-v")),
        (INGEST, ev_only_kind, lambda: engine.ingest_evidence_unit_report(**auth, evidence_id="EV-r", kind="review")),
        (CLASSIFY_VERIFICATION, kind, lambda: engine.verify_classify(**auth, classification="LOCAL_IMPLEMENTATION_DEFECT",
                                                                     reason="reviewed failure")),
    ]
    for op, routed_kind, call in cases:
        calls.clear()
        result = call()
        assert result == {"routed": (op, routed_kind)}, (work_id, op, result)
        assert len(calls) == 1
        _, args, kwargs = calls[0]
        if op == GATE_CONTEXT:
            assert args == (state, work_id)
        else:
            assert all(kwargs[k] == v for k, v in auth.items())
            if op == INVOKE and routed_kind == kind and kwargs["role"] == "verifier":
                assert kwargs["execution_profile"] == {"profile": "p"} and kwargs["launch"] is True
            if op == INGEST:
                assert kwargs["kind"] in {"review", "verification"}
        count += 1

calls.clear()
actions = engine.next_actions(state)
assert actions == [f"{wid}: {expected_kinds[wid]}" for wid in sorted(units)]
assert len(calls) == 4
count += 4

for args in ({"classification": "not-valid", "reason": "r"},
             {"classification": "LOCAL_IMPLEMENTATION_DEFECT", "reason": " "}):
    calls.clear()
    try:
        engine.verify_classify(token="t", expect_rev=42, work_id="T-0001", **args)
    except UsageError:
        assert calls == []
    else:
        raise AssertionError("invalid classification input was dispatched")
    count += 1

calls.clear()
try:
    engine.invoke_create(token="t", expect_rev=42, work_id="T-9999")
except NotFound:
    assert calls == []
else:
    raise AssertionError("unknown work unit was dispatched")
count += 1
print(f"PASS: {count} public routing and validation checks across both Ticket kinds, Story, and Epic")
