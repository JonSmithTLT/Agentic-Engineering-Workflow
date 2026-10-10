"""Stage availability composed per step from queryable guards (M4-E E4; plan v3 E4; frozen decision 3).

The composition and its declarations, against a fake engine whose guards answer as each test programs them: the
migrated stage table matches the catalog, ``produced_by`` names only earlier steps and known inputs, a later step is
queried with what its producers would leave, a launch is covered by its dispatch decision, and an unmigrated guard
makes a stage UNKNOWN, never BLOCKED. The guards themselves are checked against their execute paths in
``tests/integration/test_guard_queries.py``."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest
from guard_reads import GUARD_READS

from aew.engine.dispatch import Blocker
from aew.engine.guards import AVAILABLE, BLOCKED, GUARD_NOT_QUERYABLE, UNKNOWN, GuardQueries, NotQueryable
from aew.engine.seams import MUTATING, NON_MUTATING, GuardTable
from aew.errors import GateUnsatisfied, IntegrityError
from aew.surface import availability as SA
from aew.surface import contract
from aew.surface.classify import auto_runnable, effective_class


class FakeEngine:
    """Answers each primitive's guard as programmed (AVAILABLE by default) and records the state each query saw."""

    def __init__(self, state: dict[str, Any], answers: dict[str, str] | None = None,
                 found: dict[str, dict[str, Any]] | None = None) -> None:
        self.store = SimpleNamespace(read=lambda: state)
        self.answers = answers or {}
        self.found = found or {}
        self.seen: list[tuple[str, str | None, dict[str, Any]]] = []

    gate_memo = staticmethod(contextlib.nullcontext)
    mode = "verifier"

    def validation_mode(self, work_id, *, state=None):
        return self.mode

    def candidate_overlay(self, state, work_id):
        return {**state, "work": {**state["work"], work_id: {**state["work"][work_id],
                                                             "integration": {"status": "prepared"}}}}

    def guard_query(self, primitive, work_id, args, *, state=None):
        self.seen.append((primitive, work_id, state))
        if primitive in self.found:
            args["found"] = self.found[primitive]
        answer = self.answers.get(primitive, AVAILABLE)
        blockers = [{"code": "GATE_UNSATISFIED", "message": "no"}] if answer == BLOCKED else []
        codes = {BLOCKED: ["GATE_UNSATISFIED"], UNKNOWN: [GUARD_NOT_QUERYABLE]}.get(answer, [])
        return {"availability": answer, "reason_codes": codes, "blocking_conditions": blockers}


def _state(st: str = "READY") -> dict[str, Any]:
    return {"revision": 7, "work": {"T-0001": {"kind": "ticket", "mutating": True, "state": st, "evidence": []}},
            "invocations": {}}


def test_the_migrated_stage_table_matches_the_catalog():
    for name, steps in SA.STAGES.items():
        t = contract.tool(name)
        assert t is not None and len(steps) == len(t.expands_to) == len(t.produced_by), name
    # E4a migrated the four Ticket stages E5 builds; E4b adds the integration stages E6a builds.
    assert set(SA.STAGES) == {"ticket_draft", "ticket_start", "ticket_request_review", "ticket_request_verification",
                              "ticket_prepare", "integration_publish"}
    for t in contract.TOOLS.values():
        for n, step in enumerate(t.produced_by, start=1):
            assert all(name in contract.STEP_INPUTS and 1 <= m < n for name, m in step), t.name
            if (contract.DISPATCH, n - 1) in step:  # only a launch is covered by the decision before it
                assert t.expands_to[n - 1] == "dispatch.launch", t.name


@pytest.mark.parametrize("bad", [((), ((contract.STATE, 2),)), ((), (("nope", 1),)), ((),)])
def test_a_produced_by_that_names_a_later_step_or_an_unknown_input_is_refused(bad):
    row = contract.Tool("probe", contract.STAGE, contract.MECHANICAL, "a probe", contract._obj({}),
                        expands_to=("checkpoint", "checkpoint"), produced_by=bad)
    with pytest.raises(ValueError, match="produced_by"):
        contract._catalog(row)


def test_step_one_is_queried_on_the_current_state_and_a_later_step_with_what_its_producers_leave():
    state = _state("READY")
    engine = FakeEngine(state)
    out = SA.stage_availability(engine, "ticket_start", {"work_id": "T-0001"})
    assert out["availability"] == AVAILABLE and [s["n"] for s in out["steps"]] == [1, 2, 3]
    [(p1, w1, s1), (p3, w3, s3)] = engine.seen  # dispatch.launch is covered by step 1's decision: not queried
    assert (p1, w1, p3, w3) == ("work.assign", "T-0001", "work.transition", "T-0001")
    assert s1 is state  # the current state, as committed
    unit = s3["work"]["T-0001"]
    assert unit["state"] == "ASSIGNED" and s3["invocations"][unit["implementer_invocation"]]["status"] == "active"
    assert state["work"]["T-0001"]["state"] == "READY" and state["invocations"] == {}  # never the real state
    assert out["steps"][1] == {"n": 2, "primitive": "dispatch.launch", "produced_by": {contract.DISPATCH: 1},
                               "covered_by": 1, "availability": AVAILABLE, "reason_codes": [],
                               "blocking_conditions": []}


def test_an_ingest_step_produces_the_state_its_outcome_implies_and_its_evidence_reference():
    ref = {"id": "EV-0009", "kind": "review", "sha256": "ab"}
    engine = FakeEngine(_state("REVIEW_PENDING"), found={"review.ingest": {"to": "REVIEW_PASSED", "ref": ref}})
    out = SA.stage_availability(engine, "ticket_request_verification",
                                {"work_id": "T-0001", "review_evidence": "EV-0009"})
    assert out["availability"] == AVAILABLE
    seen = {p: s for p, _w, s in engine.seen}
    assert seen["work.transition"]["work"]["T-0001"]["state"] == "REVIEW_PASSED"
    assert seen["work.transition"]["work"]["T-0001"]["evidence"] == [ref]
    assert seen["invoke.create.mutating"]["work"]["T-0001"]["state"] == "VERIFY_PENDING"


def test_a_created_unit_is_what_the_plan_step_is_queried_on():
    unit = {"kind": "ticket", "state": "BLOCKED", "plans": []}
    engine = FakeEngine({"revision": 1, "work": {}, "invocations": {}},
                        found={"work.create": {"work_id": "T-0004", "unit": unit}})
    plan = {"body": "1. do it", "assurance": "none"}
    out = SA.stage_availability(engine, "ticket_draft", {"title": "t", "risk_class": 1, "plan": plan})
    assert out["availability"] == AVAILABLE
    (_p, w1, _s), (p2, w2, s2) = engine.seen
    assert w1 is None and (p2, w2) == ("plan.propose", "T-0004") and s2["work"]["T-0004"] == unit
    without = SA.stage_availability(FakeEngine({"revision": 1, "work": {}}), "ticket_draft",
                                    {"title": "t", "risk_class": 1})
    assert without["steps"][1]["planned"] is False and without["availability"] == AVAILABLE


def test_a_step_whose_producer_found_nothing_is_unknown_and_a_blocked_step_blocks_the_stage():
    engine = FakeEngine({"revision": 1, "work": {}}, answers={"work.create": BLOCKED})
    out = SA.stage_availability(engine, "ticket_draft",
                                {"title": "t", "risk_class": 1, "plan": {"body": "b", "assurance": "none"}})
    assert out["availability"] == BLOCKED and out["steps"][1]["availability"] == UNKNOWN
    assert out["steps"][1]["reason_codes"] == [SA.INPUT_NOT_PRODUCED]
    assert out["blockers"][0]["code"] == "GATE_UNSATISFIED"


def test_an_unmigrated_guard_makes_the_stage_unknown_never_blocked_and_never_auto_runnable():
    engine = FakeEngine(_state("RUNNING"), answers={"work.transition": UNKNOWN})
    out = SA.stage_availability(engine, "ticket_request_review", {"work_id": "T-0001"})
    assert out["availability"] == UNKNOWN and out["reason_codes"] == [GUARD_NOT_QUERYABLE]
    t = contract.tool("ticket_request_review")
    assert not auto_runnable(t, out["availability"], effective_class(t, {}))
    assert SA.stage_availability(engine, "ticket_prepare", {"work_id": "T-0001"})["availability"] == UNKNOWN


@pytest.mark.parametrize("stage", ["ticket_request_verification", "ticket_draft", "ticket_prepare",
                                   "integration_publish"])
def test_a_judgment_bearing_stage_is_never_auto_runnable_however_available(stage):
    """m2: migration gives these stages AVAILABLE or BLOCKED, never auto_runnable (the class decides that)."""
    t = contract.tool(stage)
    built = t._replace(status=contract.BUILT)
    assert effective_class(built, {}) == contract.JUDGMENT_BEARING
    assert not auto_runnable(built, AVAILABLE, effective_class(built, {}))


# ---------------------------------------------------------------------------------------------- the substrate

def test_a_guard_table_entry_replaced_without_a_query_is_not_queryable_for_that_kind():
    guards = GuardTable()
    guards.register("g", lambda *a: None, query=lambda state, wid, args: None)
    guards.register("g", lambda *a: None, (NON_MUTATING,), replace=True)
    assert guards.query_for("g", {"kind": "ticket", "mutating": True}) is not None
    assert guards.query_for("g", {"kind": "ticket", "mutating": False}) is None
    assert set(guards.queries()) == {("g", MUTATING), ("g", "parent")}


def test_the_answer_is_tri_state_and_an_integrity_failure_is_never_a_blocker():
    def decide(state, entrypoint, work_id, **_a):
        return SimpleNamespace(allowed=False, blocking=[Blocker("CONCURRENCY_LIMIT", "cap")],
                               reason_codes=["CONCURRENCY_LIMIT"])

    queries = GuardQueries(decide)
    queries.register("work.transition", lambda s, w, a: Blocker("GATE_UNSATISFIED", "no", {}, GateUnsatisfied("no")))
    queries.register("review.ingest", lambda s, w, a: NotQueryable("ready_for_review"))
    queries.register("plan.propose", lambda s, w, a: None)

    def broken(s, w, a):
        raise IntegrityError("a policy edit awaits adoption")

    queries.register("work.create", broken)
    with pytest.raises(ValueError):
        queries.register("plan.propose", lambda s, w, a: None)
    state = {"revision": 3}
    assert queries.answer(state, "work.transition", "T-0001", {})["availability"] == BLOCKED
    unknown = queries.answer(state, "review.ingest", "T-0001", {})
    assert unknown["availability"] == UNKNOWN and unknown["not_queryable"] == "ready_for_review"
    assert queries.answer(state, "plan.propose", "T-0001", {})["availability"] == AVAILABLE
    integrity = queries.answer(state, "work.create", None, {})
    assert integrity["availability"] == UNKNOWN and integrity["reason_codes"] == ["INTEGRITY_ERROR"]
    dispatch = queries.answer(state, "work.assign", "T-0001", {})
    assert dispatch["availability"] == BLOCKED and dispatch["reason_codes"] == ["CONCURRENCY_LIMIT"]
    assert queries.answer(state, "dispatch.launch", "T-0001", {})["availability"] == UNKNOWN  # covered, not asked
    assert queries.answer(state, "verify.classify", "T-0001", {})["reason_codes"] == [GUARD_NOT_QUERYABLE]


def test_a_query_that_raises_a_defect_answers_unknown_and_is_logged(caplog):
    """PR #170 review, finding 2: an exception that is not a refusal never escapes into resume or status."""
    def decide(*_a, **_k):
        raise AssertionError("not asked")

    queries = GuardQueries(decide)

    def broken(s, w, a):
        return a["title"]  # a KeyError: an engine defect, not a refusal

    queries.register("work.create", broken)
    with caplog.at_level("ERROR", logger="aew.engine.guards"):
        answer = queries.answer({"revision": 1}, "work.create", None, {})
    assert answer["availability"] == UNKNOWN and answer["reason_codes"] == ["GUARD_QUERY_DEFECT"]
    assert "KeyError" in answer["unanswered"]["message"] and "work.create" in caplog.text


# ---------------------------------------------------------------------------------------------- one question asked
# PR #170 review, finding 3: `explain` and the projection ask a step's guard with `availability.STAGES`' arguments;
# `resume`'s recheck and R5-1 ask it with the stage planner's (`aew.surface.stage.STAGES`). The two must agree, so
# both paths ask the same question. Vacuous until E5a registers the first Ticket stage planner, then binding: E5a's
# obligation is to keep this green (recorded in the register's F15.2 row).

CALLS = {
    "ticket_draft": [{"title": "t", "risk_class": 1, "scope": ["calc/**"], "goal": ["g"], "contract": ["c"]},
                     {"title": "t", "risk_class": 0, "non_mutating": True, "parent": "S-0001", "card": "investigator",
                      "plan": {"body": "1. x", "affected": ["calc/core.py"], "assurance": "none", "reason": "r"}},
                     {"title": "t", "risk_class": 2, "plan": {"body": "b", "assurance": {"review": ["default"]}}}],
    "ticket_start": [{"work_id": "T-0001"}, {"work_id": "T-0002", "execution": {"model": "p/m"}}],
    "ticket_request_review": [{"work_id": "T-0001"}],
    "ticket_request_verification": [{"work_id": "T-0001", "review_evidence": "EV-0003"}],
    "ticket_prepare": [{"work_id": "T-0001", "verification_evidence": "EV-0004"}],
    "integration_publish": [{"work_id": "T-0001", "prepared_candidate": "c0ffee"}],
}


def disagreements(stage_planners: dict[str, Any]) -> list[str]:
    """Where a planner's step arguments differ from the arguments the step's guard is asked with, both ways: every
    argument the availability builder gives must be the planner's too (the same value, or an earlier step's output,
    `$from`, where `produced_by` says that step produces it), and the planner gives no argument a guard reads that
    the builder does not give (PR #170 re-review, finding 2)."""
    out = []
    for name in sorted(set(SA.STAGES) & set(stage_planners)):
        t = contract.tool(name)
        for call in CALLS[name]:
            plan = stage_planners[name](dict(call, expect_rev=1))
            if [p["primitive"] for p in plan] != list(t.expands_to):
                out.append(f"{name}: planned {[p['primitive'] for p in plan]}")
                continue
            for n, (build, step) in enumerate(zip(SA.STAGES[name], plan, strict=True), start=1):
                asked, given = build(call), step.get("args") or {}
                for key, value in (asked or {}).items():
                    got = given.get(key)
                    produced = isinstance(got, dict) and set(got) == {"$from"} and any(
                        m == got["$from"][0] for _input, m in t.produced_by[n - 1])
                    if got != value and not produced and not (value is None and key not in given):
                        out.append(f"{name} step {n} {key}: guard asked {value!r}, planner gives {got!r}")
                for key in sorted(set(given) & GUARD_READS[t.expands_to[n - 1]] - set(asked or {})):
                    out.append(f"{name} step {n} {key}: planner gives {given[key]!r}, which the guard reads but is "
                               "never asked with")
    return out


def test_the_stage_planners_ask_the_guards_what_availability_asks():
    from aew.surface import stage

    assert set(CALLS) == set(SA.STAGES)
    assert disagreements(stage.STAGES) == []


def test_the_agreement_check_binds_a_planner_that_differs():
    def start(a: dict[str, Any]) -> list[dict[str, Any]]:  # forgets the launch, and names the target state wrongly
        return [{"primitive": "work.assign", "args": {"work_id": a["work_id"]}},
                {"primitive": "dispatch.launch", "args": {"work_id": a["work_id"]}},
                {"primitive": "work.transition", "args": {"work_id": a["work_id"], "to": "ASSIGNED"}}]

    found = disagreements({"ticket_start": start})
    assert any("step 1 launch" in d for d in found) and any("step 3 to" in d for d in found)


def test_the_agreement_check_binds_a_planner_that_adds_what_a_guard_reads():
    """The other direction: a planner that asks a step's guard more than availability does (a card for the reviewer's
    decision, a reason for the transition) changes the question resume and R5-1 ask. Arguments no guard reads
    (`launch`, `execution`) are the planner's own."""
    def review(a: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"primitive": "work.transition", "args": {"work_id": a["work_id"], "to": "REVIEW_PENDING",
                                                          "reason": "ready"}},
                {"primitive": "invoke.create.mutating", "args": {"work_id": a["work_id"], "role": "reviewer",
                                                                 "card": "security_reviewer", "launch": True,
                                                                 "execution": {"model": "p/m"}}},
                {"primitive": "dispatch.launch", "args": {"work_id": a["work_id"]}}]

    found = disagreements({"ticket_request_review": review})
    assert any("step 1 reason" in d for d in found) and any("step 2 card" in d for d in found)
    assert not any("launch" in d or "execution" in d for d in found)
    assert set(GUARD_READS) >= {p for steps in SA.STAGES for p in contract.tool(steps).expands_to}


@pytest.mark.parametrize(("codes", "says"), [
    (["GUARD_NOT_QUERYABLE"], "has no query form"),
    (["GUARD_QUERY_DEFECT"], "could not be asked now (GUARD_QUERY_DEFECT)"),
    (["INTEGRITY_ERROR"], "could not be asked now (INTEGRITY_ERROR)"),
])
def test_resume_says_why_a_guard_is_unknown_by_its_code(codes, says):
    """PR #170 re-review, finding 1: an UNKNOWN guard recheck carries its reason codes, and its message says which
    kind of UNKNOWN it is (no query form, a defect, a policy edit awaiting adoption), never only the first."""
    from aew.surface import stage

    engine = SimpleNamespace(guard_query=lambda primitive, work_id, args: {
        "availability": UNKNOWN, "reason_codes": codes, "blocking_conditions": []})
    found, reasons = stage.guard_status(engine, "work.transition", {"work_id": "T-0001"})
    assert (found, reasons) == (UNKNOWN, codes)
    check = stage._unknown_guard(reasons)
    assert check["status"] == stage.UNKNOWN_STATUS and check["reason_codes"] == codes and says in check["message"]


def test_recording_args_see_every_key_a_query_reads():
    """The mechanical check behind GUARD_READS: a query's reads (get, [], in) are recorded; what it records under
    `found` is not an input."""
    from guard_reads import RecordingArgs

    args = RecordingArgs({"work_id": "T-0001", "to": "RUNNING"})
    assert args.get("reason") is None and args["to"] == "RUNNING" and "card" not in args
    args.setdefault("found", {})["rule"] = 1
    assert args.inputs_read() == {"reason", "to", "card"}



@pytest.mark.parametrize("mode", ["checks", "verifier"])
def test_ticket_prepare_plans_the_integration_verifier_in_verifier_mode_only(mode):
    """Plan v3 §2.3: in checks mode the custodian validates, outside the stage, so steps 4 and 5 are not planned; in
    verifier mode the verifier's decision is asked on the candidate and lease step 3 produces, after the acceptance
    and COMMIT_READY state step 2 produces."""
    ref = {"id": "EV-0004", "kind": "verification", "sha256": "ab"}
    engine = FakeEngine(_state("VERIFY_PENDING"), found={
        "verify.ingest": {"to": "VERIFIED", "ref": ref},
        "work.transition": {"gate_context": {"snapshot": {"relevant_inputs_fingerprint": "f"}, "gates": {}}}})
    engine.mode = mode
    out = SA.stage_availability(engine, "ticket_prepare", {"work_id": "T-0001", "verification_evidence": "EV-0004"})
    assert out["availability"] == AVAILABLE
    seen = {p: s for p, _w, s in engine.seen}
    prepared_on = seen["integrate.prepare"]["work"]["T-0001"]
    assert prepared_on["state"] == "COMMIT_READY" and prepared_on["commit_ready_seq"] == 1
    assert prepared_on["commit_ready_snapshot"] == {"relevant_inputs_fingerprint": "f"}
    if mode == "checks":
        assert [s.get("planned", True) for s in out["steps"]] == [True, True, True, False, False]
        assert "invoke.create.mutating" not in seen
    else:
        assert seen["invoke.create.mutating"]["work"]["T-0001"]["integration"] == {"status": "prepared"}
        assert out["steps"][4]["covered_by"] == 4
