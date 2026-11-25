"""The plan assessment record kind (E160 slices 1 and 2; SYS-43): its schema, its revision binding, the one assessment
that counts per revision, and who may submit one (a plan-assessor dispatch only). The entrypoint itself is driven in
``tests/integration/test_plan_assessment_dispatch.py``; the gate that reads ``counting_assessment`` is slice 3."""

from __future__ import annotations

import argparse

import pytest

from aew import roles
from aew.cli.main import build_parser
from aew.engine.authority import ROLE_OPERATIONS
from aew.errors import PermissionDenied, ValidationFailed
from aew.knowledge import context as ctx
from aew.knowledge import evidence as E
from aew.schemas import schema, validate
from aew.util import sha256_text

PLAN = {"accepted": 2, "path": "work/T-0001/plan-v2.md", "sha256": sha256_text("plan v2")}
SNAPSHOT = {"base_revision": "a" * 40, "workspace_id": "T-0001-obs",
            "relevant_inputs_fingerprint": "git-tree:" + "b" * 40}


def assessment(**overrides):
    base = {
        "requirement_trace": [{"requirement": "EW-U04.b", "status": "covered", "plan_reference": "Approach, step 2"}],
        "premises_challenged": [{"premise": "the parser is only called from the CLI", "source": "request",
                                 "challenge": "searched every caller", "outcome": "holds",
                                 "evidence": ["src/app/cli.py:12"]}],
        "findings": [],
    }
    base.update(overrides)
    return base


def sealed(binding_result, *, seq=1, plan=PLAN, role="reviewer"):
    """A sealed record as the submission path writes one: the engine's fields, then the binding's part."""
    meta = {"schema": "aew/evidence/v1", "id": f"INV-0009-assess-{seq}", "kind": E.PLAN_ASSESSMENT,
            "work_unit": "T-0001", "producer": {"role": role, "invocation": "INV-0009"},
            "created_at": "2026-11-25T00:00:00Z", "seq": seq, "plan_revision": E.plan_binding(plan),
            "evaluated_snapshot": SNAPSHOT, "method": {"capability": "plan_assessment"},
            "claim": "assessed the accepted plan", "evidence": [], **binding_result}
    return E.parse_sealed(E.seal(meta, ""), "test")[0]


def test_a_plan_assessment_is_bound_to_the_accepted_revision_and_its_sha256():
    record = sealed(E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment()}))
    assert record["plan_revision"] == {"revision": 2, "sha256": PLAN["sha256"]}
    assert record["plan_revision"] == E.plan_binding(PLAN)  # the binding every record carries, reused
    assert record["result"] == "pass" and record["id"].endswith("-assess-1")


@pytest.mark.parametrize("plan_revision", [None, {"revision": 2}, {"revision": 2, "sha256": "not-a-digest"}])
def test_a_plan_assessment_without_its_revision_binding_never_seals(plan_revision):
    meta = {"schema": "aew/evidence/v1", "id": "INV-0009-assess-1", "kind": E.PLAN_ASSESSMENT, "work_unit": "T-0001",
            "producer": {"role": "reviewer", "invocation": "INV-0009"}, "created_at": "t",
            "evaluated_snapshot": SNAPSHOT, "method": {}, "claim": "c", "result": "pass", "assessment": assessment()}
    if plan_revision is not None:
        meta["plan_revision"] = plan_revision
    with pytest.raises(ValidationFailed):
        E.seal(meta, "")
    with pytest.raises(ValidationFailed):
        E.seal({**meta, "plan_revision": None}, "")


def test_a_plan_assessment_is_the_reviewer_archetypes_and_no_other_roles():
    with pytest.raises(ValidationFailed):
        sealed(E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment()}), role="planner")
    # The schema's archetype and the code's are one fact, held equal here.
    rule = next(r for r in schema("evidence")["allOf"] if r["if"]["properties"].get("kind", {}).get("const")
                == E.PLAN_ASSESSMENT)
    assert rule["then"]["properties"]["producer"]["properties"]["role"]["const"] == E.ASSESSOR_ARCHETYPE
    assert E.ASSESSOR_ARCHETYPE in roles.ARCHETYPES


def test_only_a_plan_assessor_dispatch_may_submit_a_plan_assessment_and_a_code_reviewer_never():
    # The reviewer archetype holds the grant (its YAML and ROLE_OPERATIONS are held equal by test_roles), but the kind
    # belongs to the assessor's scope alone: a reviewer of a change, at any other scope, never submits one.
    assert f"submit.{E.PLAN_ASSESSMENT}" in ROLE_OPERATIONS[E.ASSESSOR_ARCHETYPE]
    assert all(f"submit.{E.PLAN_ASSESSMENT}" not in ops for role, ops in ROLE_OPERATIONS.items()
               if role != E.ASSESSOR_ARCHETYPE)
    for scope in ("ticket", "observation", "parent", "integration", None):
        assert E.kinds_for("reviewer", scope) == {"review"}
        with pytest.raises(PermissionDenied) as exc:
            E.check_submission("reviewer", E.PLAN_ASSESSMENT, {"claim": "c"}, scope=scope)
        assert exc.value.details["reason"] == "not_a_plan_assessment_dispatch"
    assert E.kinds_for("reviewer", E.ASSESSMENT_SCOPE) == {E.PLAN_ASSESSMENT}
    E.check_submission("reviewer", E.PLAN_ASSESSMENT, {"claim": "c"}, scope=E.ASSESSMENT_SCOPE)
    with pytest.raises(PermissionDenied) as exc:
        E.check_submission("reviewer", "review", {"claim": "c"}, scope=E.ASSESSMENT_SCOPE)
    assert exc.value.details["reason"] == "plan_assessment_dispatch"
    with pytest.raises(PermissionDenied):  # no other archetype at the assessor's scope either
        E.check_submission("planner", E.PLAN_ASSESSMENT, {"claim": "c"}, scope=E.ASSESSMENT_SCOPE)
    top = next(a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    submit = next(a for a in top.choices["submit"]._actions if "--kind" in a.option_strings)
    assert submit.choices and E.PLAN_ASSESSMENT in submit.choices


def test_the_assessor_card_extends_the_assessor_archetype_and_is_narrowed_to_the_assessment():
    card = roles.builtin_cards()[E.ASSESSOR_CARD]
    assert card.archetype == E.ASSESSOR_ARCHETYPE and card.meta["outputs"] == [E.PLAN_ASSESSMENT]
    assert set(card.meta["restrict"]["operations"]) == {f"submit.{E.PLAN_ASSESSMENT}", "context.read"}
    others = [c for c in roles.builtin_cards().values() if c.id != E.ASSESSOR_CARD]
    assert all(E.PLAN_ASSESSMENT not in (c.meta.get("outputs") or []) for c in others)


def test_the_assessors_report_format_is_what_the_engine_accepts():
    kind, template = ctx.output_template(E.ASSESSOR_ARCHETYPE, E.ASSESSMENT_SCOPE)
    assert kind == E.PLAN_ASSESSMENT and ctx.output_template("reviewer", "ticket")[0] == "review"
    E.check_submission("reviewer", kind, template, scope=E.ASSESSMENT_SCOPE)
    out = E.plan_assessment_binding("T-0001", PLAN, template)  # the gap it shows cites its finding
    assert out["result"] == "pass"


def test_there_is_nothing_to_assess_without_an_accepted_plan():
    for plan in (None, {}):
        with pytest.raises(ValidationFailed) as exc:
            E.plan_assessment_binding("T-0001", plan, {"assessment": assessment()})
        assert exc.value.details["reason"] == "no_accepted_plan"


@pytest.mark.parametrize("section", [
    None,
    {"premises_challenged": [], "findings": []},                         # no requirement trace
    {k: v for k, v in assessment().items() if k != "findings"},         # no findings field
    assessment(findings={"id": "A1", "severity": "minor", "summary": "s"}),  # findings that are not a list
    assessment(requirement_trace=[]),                                    # a trace of nothing
    assessment(findings=[{"id": "A1", "severity": "fatal", "summary": "x"}]),
    assessment(premises_challenged=[{"premise": "p", "source": "hearsay", "challenge": "c", "outcome": "holds"}]),
    assessment(verdict="pass"),                                          # no field beyond the three
])
def test_a_malformed_assessment_is_refused_before_it_is_read(section):
    with pytest.raises(ValidationFailed):
        E.plan_assessment_binding("T-0001", PLAN, {"assessment": section})


@pytest.mark.parametrize("section", [
    assessment(requirement_trace=[{"requirement": "EW-U04.d", "status": "missing"}]),
    assessment(requirement_trace=[{"requirement": "EW-U04.d", "status": "partial", "finding": "A9"}]),
    assessment(premises_challenged=[{"premise": "p", "source": "plan", "challenge": "c", "outcome": "fails"}]),
])
def test_a_gap_in_the_trace_or_a_failed_premise_is_never_silent(section):
    with pytest.raises(ValidationFailed) as exc:
        E.plan_assessment_binding("T-0001", PLAN, {"assessment": section})
    assert exc.value.details["reason"] == "gap_without_finding"


def test_a_gap_that_cites_its_finding_is_recorded():
    finding = {"id": "A1", "severity": "minor", "summary": "the plan leaves the migration of old parents out"}
    out = E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment(
        requirement_trace=[{"requirement": "EW-U04.d", "status": "partial", "finding": "A1"}], findings=[finding])})
    assert out["result"] == "pass" and out["assessment"]["findings"] == [{**finding, "required": False}]


def test_finding_ids_are_unique_within_an_assessment():
    finding = {"id": "A1", "severity": "minor", "summary": "s"}
    with pytest.raises(ValidationFailed) as exc:
        E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment(findings=[finding, finding])})
    assert exc.value.details["reason"] == "duplicate_finding"


@pytest.mark.parametrize("severity", ["blocker", "major"])
def test_a_blocker_or_major_finding_is_required_and_fails_the_assessment(severity):
    submitted = {"assessment": assessment(findings=[{"id": "A1", "severity": severity, "summary": "s",
                                                     "required": False}])}
    out = E.plan_assessment_binding("T-0001", PLAN, submitted)
    assert out["result"] == "fail" and out["assessment"]["findings"][0]["required"] is True
    assert submitted["assessment"]["findings"][0]["required"] is False  # the submission itself is never changed


def test_one_assessment_counts_per_revision():
    passing = E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment()})
    failing = E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment(
        findings=[{"id": "A1", "severity": "major", "summary": "s"}])})
    first, second = sealed(failing, seq=3), sealed(passing, seq=5)
    # The first recorded assessment of the revision counts; a later, kinder one never replaces it.
    assert E.counting_assessment([second, first], PLAN)["id"] == first["id"]


def test_an_assessment_of_another_revision_never_counts_for_this_one():
    earlier = {"accepted": 1, "path": "work/T-0001/plan-v1.md", "sha256": sha256_text("plan v1")}
    same_number = {**PLAN, "sha256": sha256_text("plan v2, edited")}
    binding = E.plan_assessment_binding("T-0001", PLAN, {"assessment": assessment()})
    records = [sealed(binding, seq=1, plan=earlier), sealed(binding, seq=2, plan=same_number)]
    assert E.counting_assessment(records, PLAN) is None
    assert E.counting_assessment(records, earlier)["seq"] == 1
    assert E.counting_assessment(records, None) is None
    review = {**records[0], "kind": "review"}  # only a plan assessment counts (slice 3 adds the planner-review credit)
    assert E.counting_assessment([review], earlier) is None


def test_the_submitter_never_supplies_the_revision_binding_or_the_result():
    assert "plan_revision" in E.ENGINE_OWNED
    assert E.SUBMITTER_KEYS[E.PLAN_ASSESSMENT] & {"plan_revision", "result"} == set()


def test_a_review_still_validates_against_the_shared_finding_shape():
    validate("evidence", {
        "schema": "aew/evidence/v1", "id": "INV-0001-review-1", "kind": "review", "work_unit": "T-0001",
        "producer": {"role": "reviewer", "invocation": "INV-0001"}, "created_at": "t", "evaluated_snapshot": SNAPSHOT,
        "method": {}, "claim": "c", "result": "fail",
        "review": {"independence": "R1", "disposition": "changes_required",
                   "findings": [{"id": "F1", "severity": "major", "summary": "s", "required": True}]},
    }, source="review")
    with pytest.raises(ValidationFailed):
        validate("evidence", {
            "schema": "aew/evidence/v1", "id": "INV-0001-review-1", "kind": "review", "work_unit": "T-0001",
            "producer": {"role": "reviewer", "invocation": "INV-0001"}, "created_at": "t",
            "evaluated_snapshot": SNAPSHOT, "method": {}, "claim": "c", "result": "fail",
            "review": {"independence": "R1", "disposition": "changes_required",
                       "findings": [{"id": "F1", "severity": "fatal", "summary": "s", "required": True}]},
        }, source="review")


def test_a_lead_session_cannot_relay_plan_assess_until_its_typed_tool():
    # E160 slice 2a: the command takes the Lead credential and is not Lead-reachable, so a Lead session's broker refuses
    # it, saying why and what to do; slice 2b gives the Lead its typed tool. Like every dispatch, a relay would need
    # --launch.
    from aew.errors import PermissionDenied as Refused
    from aew.harness import lead_broker

    assert frozenset({"plan", "assess"}) not in lead_broker.LEAD_REACHABLE
    assert frozenset({"plan", "assess"}) in lead_broker.DISPATCHES
    argv = ["plan", "assess", "T-0001", "--launch", "--expect-rev", "3"]
    refusal = lead_broker.refuses_locally(build_parser().parse_args(argv))
    assert refusal == ("`aew plan assess` reaches a Lead session through its typed tool, which is not built yet; "
                       "until it is, ask the operator to run it at their own terminal")
    with pytest.raises(Refused) as exc:  # the broker applies the same check before anything runs
        lead_broker.run_cli(object(), "token", argv, ".", "", channel="lead_broker")
    assert exc.value.message == refusal


def test_a_plan_assessor_whose_pack_drifted_is_dispatched_again_by_its_own_entrypoint():
    from aew.engine import gate_ops

    state = {"work": {"T-0001": {"kind": "ticket", "mutating": True}}}
    inv = {"work_unit": "T-0001", "scope": E.ASSESSMENT_SCOPE, "role": "reviewer", "card": {"id": E.ASSESSOR_CARD}}
    commands = gate_ops.redispatch_commands(state, "INV-0003", inv)
    assert commands[0].startswith("aew invoke cancel INV-0003")
    assert commands[1].startswith(f"aew plan assess T-0001 --card {E.ASSESSOR_CARD} --launch")
