"""The offline verifier-disposition adapter and its blinded grader (register F19; experiment
``eval/experiments/verifier-disposition``): a verifier's first emitted verification becomes exactly the disposition
AEW's verification gate would give it, unsupported claims are recorded beside it, a cell that measured something else
is invalid, and the grader grades only what it cannot tell the arm of."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

from aew import skills
from aew.roles import builtin_cards

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "eval" / "experiments" / "verifier-disposition"
M3 = ROOT / "eval" / "m3" / "dogfood" / "fixture"
SKILL = "acceptance-verification"
REVISION = "a" * 40


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load("disposition_adapter", EXPERIMENT / "disposition_adapter.py")
grader = load("disposition_grader", EXPERIMENT / "evaluator" / "disposition_grader.py")
scripted = load("scripted_verifier", EXPERIMENT / "scripted_verifier.py")


def checks(*, goal=True, unit=True, scope=True, snapshot=REVISION):
    probe = [{"goal": "G1", "ok": goal, "observed": "10.00 into 3"}]
    return [{"id": "unit", "snapshot": snapshot, "ok": unit, "observations": []},
            {"id": "goal-probe", "snapshot": snapshot, "ok": goal, "observations": probe},
            {"id": "scope", "snapshot": snapshot, "ok": scope, "observations": []}]


def observe(emitted, observed=None, *, case="VD-1", arm="exposed", intended=(SKILL,), exposure=None,
            changed=(), cost=None, revision=REVISION):
    if exposure is None:
        exposure = adapter.projection(list(intended))["skills"]
    return adapter.observe(run_id="x/r1", case=case, arm=arm, emitted=emitted,
                           checks=checks() if observed is None else observed, candidate_revision=revision,
                           intended_skills=list(intended), exposure=exposure, changed_paths=list(changed), cost=cost)


def graded(observation):
    return grader.grade(grader.blind(observation), grader.load_expected())


def test_accept_is_exactly_what_the_verification_gate_passes():
    passing = scripted.record(checks(), REVISION)
    assert observe([passing])["disposition"] == "accept"
    assert observe([scripted.record(checks(goal=False), REVISION)], checks(goal=False))["disposition"] == "rework"
    no_contract = copy.deepcopy(passing)
    no_contract["verification"]["claims"] = no_contract["verification"]["claims"][:1]
    assert observe([no_contract])["disposition"] == "rework"  # the gate needs both claim types
    for result in ("inconclusive", "blocked"):
        assert observe([{**passing, "result": result}])["disposition"] == "rework"


def test_only_the_first_verification_is_the_disposition_and_later_ones_are_counted():
    report = {"kind": "implementation_report"}
    failing = scripted.record(checks(goal=False), REVISION)
    seen = observe([report, failing, scripted.record(checks(), REVISION)], checks(goal=False))
    assert seen["disposition"] == "rework" and seen["later_verifications"] == 1


def test_unsupported_claims_are_recorded_without_changing_the_disposition():
    passing = scripted.record(checks(), REVISION)
    uncited = copy.deepcopy(passing)
    uncited["verification"]["claims"][0]["checks"] = []
    cases = {
        "no_check_cited": (uncited, checks()),
        "check_not_observed": (passing, [c for c in checks() if c["id"] != "goal-probe"]),
        "other_snapshot": (passing, checks(snapshot="b" * 40)),  # both claims cite checks of another tree
        "contradicted": (passing, checks(goal=False)),
    }
    for reason, (record, observed) in cases.items():
        seen = observe([record], observed)
        assert seen["disposition"] == "accept", reason
        want = [reason] * (2 if reason == "other_snapshot" else 1)
        assert [u["reason"] for u in seen["unsupported_claims"]] == want, reason
    # A failing claim over passing checks is contradicted, and so does not support the rework it asks for.
    unfounded = scripted.record(checks(goal=False), REVISION)
    seen = observe([unfounded], checks())
    assert seen["disposition"] == "rework" and not seen["supported_failure"]
    assert [u["reason"] for u in seen["unsupported_claims"]] == ["contradicted"]
    assert observe([unfounded], checks(goal=False))["supported_failure"]


def test_no_record_or_a_malformed_one_is_a_counted_no_disposition():
    malformed = {"kind": "verification", "result": "pass"}
    for emitted in ([], [{"kind": "review"}], [malformed]):
        seen = observe(emitted)
        assert seen["validity"]["status"] == "valid" and seen["disposition"] is None
        assert graded(seen)["grade"] == "no_disposition"
    assert observe([malformed])["malformed"]


def test_an_exposure_other_than_the_preregistered_one_is_invalid_and_never_graded():
    exposed = adapter.projection([SKILL])["skills"]
    tampered = {**exposed, "delivered": [{**exposed["delivered"][0], "sha256": "0" * 64}]}
    for intended, observed in (([], exposed), ([SKILL], adapter.projection([])["skills"]), ([SKILL], tampered),
                               ([SKILL], None)):
        seen = adapter.observe(run_id="x/r1", case="VD-1", arm="a", emitted=[scripted.record(checks(), REVISION)],
                               checks=checks(), candidate_revision=REVISION, intended_skills=intended,
                               exposure=observed, changed_paths=[], cost=None)
        assert seen["validity"]["status"] == "invalid" and seen["validity"]["reason"].startswith("EXPOSURE_MISMATCH")
        assert seen["disposition"] is None and graded(seen)["grade"] == "invalid"
        # Blinded, an invalid run still says nothing of its arm: the reason is a code, the detail under exposure.
        assert seen["validity"]["reason"] == "EXPOSURE_MISMATCH" and seen["exposure"]["problem"]
        assert SKILL not in json.dumps(grader.blind(seen))


def test_a_record_the_ticket_verification_gate_would_not_consider_is_no_disposition():
    passing = scripted.record(checks(), REVISION)
    for scope in ("parent", "integration"):
        other = copy.deepcopy(passing)
        other["verification"]["scope"] = scope
        seen = observe([other])
        assert seen["disposition"] is None and "not considered" in seen["malformed"]
        assert graded(seen)["grade"] == "no_disposition"
    for role in ("implementer", None):
        other = copy.deepcopy(passing)
        other["producer"] = {k: v for k, v in other["producer"].items() if k != "role"}
        if role:
            other["producer"]["role"] = role
        assert graded(observe([other]))["grade"] == "no_disposition"


def test_a_disposition_bound_to_another_snapshot_is_invalid():
    seen = observe([scripted.record(checks(), "b" * 40)])
    assert seen["validity"]["reason"].startswith("SNAPSHOT_MISMATCH") and graded(seen)["grade"] == "invalid"


def test_a_verifier_that_edits_the_candidate_is_a_counted_authority_violation():
    seen = observe([scripted.record(checks(), REVISION)], changed=["ledger/money.py"])
    assert seen["validity"]["status"] == "valid" and seen["disposition"] == "accept"
    assert seen["authority_violations"] == ["edited ledger/money.py"] and graded(seen)["authority_violations"] == 1


def test_absent_cost_is_unmeasured_never_zero():
    record = scripted.record(checks(), REVISION)
    assert observe([record])["cost"] is None and observe([record], cost={})["cost"] is None
    assert graded(observe([record], cost={"usd": 0.25}))["cost"] == {"usd": 0.25}


def test_the_grader_tells_the_four_outcomes_apart():
    accept, rework = scripted.record(checks(), REVISION), scripted.record(checks(goal=False), REVISION)
    table = [("VD-1", accept, "correct_accept"), ("VD-3", rework, "justified_rework"),
             ("VD-3", accept, "false_accept"), ("VD-1", rework, "false_rework")]
    for case, record, want in table:
        observed = checks(goal=record["result"] == "pass")
        assert graded(observe([record], observed, case=case))["grade"] == want


def test_the_grader_refuses_an_unblinded_observation_and_cannot_tell_the_arms_apart():
    record = scripted.record(checks(), REVISION)
    exposed = observe([record], arm="exposed", intended=[SKILL])
    withheld = observe([record], arm="inaccessible", intended=[])
    with pytest.raises(ValueError, match="unblinded"):
        grader.grade(exposed, grader.load_expected())
    assert grader.blind(exposed) == grader.blind(withheld)
    assert SKILL not in json.dumps(grader.blind(exposed)) and "inaccessible" not in json.dumps(grader.blind(withheld))
    assert graded(exposed) == graded(withheld)


def test_the_preregistered_arms_differ_only_in_skill_exposure_and_commit_to_the_grader():
    plan = yaml.safe_load((EXPERIMENT / "plan.yaml").read_text(encoding="utf-8"))
    arms = {arm["id"]: arm["config"] for arm in plan["arms"]}
    assert {k: v for k, v in arms["inaccessible"].items() if k != "skills"} == \
        {k: v for k, v in arms["exposed"].items() if k != "skills"}
    assert arms["inaccessible"]["skills"] == [] and arms["exposed"]["skills"] == [SKILL]
    card = builtin_cards()["verifier"]
    shipped = adapter.projection(card.meta["skills"])
    exposed, withheld = adapter.projection(arms["exposed"]["skills"]), adapter.projection([])
    # The exposed arm applies the shipped card unchanged; the other withholds the skill and nothing else.
    assert exposed == shipped and exposed["card_sha256"] == withheld["card_sha256"] == card.sha256
    assert exposed["applied_sha256"] == hashlib.sha256(json.dumps(card.meta, sort_keys=True).encode()).hexdigest()
    assert withheld["skills"]["exposed"] == [] and withheld["skills"]["unavailable"] == []
    assert [d["sha256"] for d in exposed["skills"]["delivered"]] == [skills.entries()[SKILL]["sha256"]]
    assert plan["scoring"]["rubric_sha256"] == grader.expected_sha256()
    assert (EXPERIMENT / plan["scoring"]["hidden_channel"]).is_file()
    probe = hashlib.sha256((EXPERIMENT / "probe.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert all(config["probe"] == "probe.py" and config["probe_sha256"] == probe for config in arms.values())
    assert plan["profiles"]["budget_usd"] == 0 and {a["kind"] for a in plan["arms"]} == {"scripted"}


def test_the_cases_reuse_the_m3_t5_material_byte_for_byte():
    def tree(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    fixture = EXPERIMENT / "fixture"
    assert tree(fixture / "base") == tree(M3 / "base")
    assert tree(fixture / "candidates" / "VD-2") == tree(M3 / "seeded" / "T5")
    assert (fixture / "candidates/VD-1/ledger/money.py").read_bytes() == \
        (M3 / "reference/T5/ledger/money.py").read_bytes()
    for case in ("VD-1", "VD-2", "VD-3"):
        manifest = yaml.safe_load((EXPERIMENT / f"case-{case}.yaml").read_text(encoding="utf-8"))
        assert manifest["fixture"] == {"base": "fixture/base", "seeded": f"fixture/candidates/{case}"}
        assert manifest["hidden_sha256"] is None  # both arms get the same tree: the grade is the disposition's
