"""The plan assessment record kind (E160 slice 1; SYS-43): its schema, its revision binding, and the one assessment that
counts per revision. The assessor entrypoint (slice 2) and the gate that reads ``counting_assessment`` (slice 3) are
later pull requests of the series."""

from __future__ import annotations

import pytest

from aew import roles
from aew.engine.authority import ROLE_OPERATIONS
from aew.errors import ValidationFailed
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


def test_no_credential_may_submit_a_plan_assessment_before_the_assessor_entrypoint():
    # Slice 2 grants it to a plan-assessor dispatch only; until then no role, a code reviewer included, may submit one,
    # and a review run's expected kinds stay what they were.
    assert all(f"submit.{E.PLAN_ASSESSMENT}" not in ops for ops in ROLE_OPERATIONS.values())
    assert all(E.PLAN_ASSESSMENT not in kinds for kinds in E.ROLE_KINDS.values())
    assert all(E.PLAN_ASSESSMENT not in roles.archetype(a)["evidence_kinds"] for a in roles.ARCHETYPES
               if "evidence_kinds" in roles.archetype(a))


def test_there_is_nothing_to_assess_without_an_accepted_plan():
    for plan in (None, {}):
        with pytest.raises(ValidationFailed) as exc:
            E.plan_assessment_binding("T-0001", plan, {"assessment": assessment()})
        assert exc.value.details["reason"] == "no_accepted_plan"


@pytest.mark.parametrize("section", [
    None,
    {"premises_challenged": [], "findings": []},                         # no requirement trace
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
