"""The request stages, dispositions and anomalies (M4-E E5b; plan v3 E5, §2.4, §6, §10; typed Lead surface design v0.2
§3.1, §3.4).

`ticket_request_review` and `ticket_request_verification` run through ``run_tool`` as a Lead's call would, against a
real project whose execution policy launches the fake harness's scripted agent: what each commits and records, one
invocation and launch per card the effective gates require, stage/primitive equivalence on two copies of one project,
and the side effects of each primitive E5b stages first against its declaration (SAE-07). Then §2.4: the
`requires_disposition` gate input the ingests share, the Lead's disposition and its cold record, and the anomaly record
of its first sources, with what a high anomaly does (and does not) change."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from aewflow import SUBTRACT_PATCH, assign, create_planned_ticket, implement, review, sample_project, verify
from conftest import Project
from fake_harness import contains_credential
from invariants import assert_control_invariants, load_control
from stage_equivalence import differences, end_state, recorded_decisions
from test_stage_runner import call, intent, launching
from test_stages_ticket import HANG, _declared, _effects, _observe, _twins

from aew.engine import disposition_ops as DO
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.errors import WorkspaceMutated
from aew.surface import projection
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()
MINOR = {"id": "F1", "severity": "minor", "summary": "a naming nit", "required": False}


def control(p: Project) -> dict[str, Any]:
    return load_control(p.root)


def unit(p: Project, wid: str) -> dict[str, Any]:
    return control(p)["work"][wid]


def implemented(p: Project, tmp_path: Path) -> tuple[str, Any]:
    """A RUNNING Ticket whose implementer reported (no harness: the implementer's credential is the test's)."""
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    return wid, impl


def mark(p: Project, **block: list[str]) -> None:
    """Gates policy marks ``requires_disposition`` (fixture setup: pinned as the project's starting policy)."""
    gates = p.root / ".aew/policy/gates.yaml"
    lines = "".join(f"  {k}: [{', '.join(v)}]\n" for k, v in block.items())
    gates.write_text(gates.read_text(encoding="utf-8") + f"requires_disposition:\n{lines}", encoding="utf-8",
                     newline="\n")
    p.pin_policy()


@pytest.fixture
def lab_project(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    lab.script("default", HANG)
    yield p, lab
    lab.cleanup()


# ---------------------------------------------------------------------------------------------- the request stages


def test_ticket_request_review_moves_to_review_pending_and_launches_each_reviewer(lab_project, tmp_path):
    """RUNNING -> REVIEW_PENDING, then one reviewer per card the effective gates require, each launched: run 1 is the
    `dispatch.launch` step its dispatch's commit records (plan v3 §1, E5), and every invocation and run is in the
    result."""
    p, _lab = lab_project
    wid, _impl = implemented(p, tmp_path)
    out = call(p, "ticket_request_review", work_id=wid)
    assert out["ok"], out["stopped"]
    assert out["effective_operation_class"] == "POLICY_RESOLVED"
    si = intent(p, out)
    assert [s["primitive"] for s in si["steps"]] == ["work.transition", "invoke.create.mutating", "dispatch.launch"]
    assert si["status"] == SI.COMPLETED and unit(p, wid)["state"] == "REVIEW_PENDING"
    [inv] = si["steps"][1]["outputs"]["invocations"]
    invocation = control(p)["invocations"][inv]
    assert invocation["role"] == "reviewer" and si["steps"][2]["outputs"]["runs"] == [invocation["runs"][0]["run"]]
    assert si["steps"][2]["covered_by"] == 2 and si["plan"][1]["args"]["card"] == invocation["card"]["id"]
    assert not contains_credential(str(out))
    assert_control_invariants(p)


def test_a_request_stage_launches_one_invocation_per_required_card(lab_project, tmp_path):
    """Plan v3 E5's policy-resolved card set: with a second review card staffed, the stage plans and launches two
    reviewers, each with its own dispatch decision and its own run."""
    p, _lab = lab_project
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "staff", wid, "--review", "code_reviewer", "--review", "security_reviewer", "--reason",
           "touches input handling")
    out = call(p, "ticket_request_review", work_id=wid)
    assert out["ok"], out["stopped"]
    si = intent(p, out)
    assert [s["primitive"] for s in si["plan"]] == ["work.transition", *["invoke.create.mutating",
                                                                         "dispatch.launch"] * 2]
    cards = [control(p)["invocations"][s["outputs"]["invocations"][0]]["card"]["id"]
             for s in si["steps"] if s["primitive"] == "invoke.create.mutating"]
    assert cards == ["code_reviewer", "security_reviewer"]
    assert len([s for s in si["steps"] if s["primitive"] == "dispatch.launch" and s["outputs"]["runs"]]) == 2
    assert_control_invariants(p)


def test_ticket_request_verification_accepts_the_review_and_launches_each_verifier(lab_project, tmp_path):
    p, _lab = lab_project
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    evidence = review(p, wid)
    out = call(p, "ticket_request_verification", work_id=wid, review_evidence=evidence)
    assert out["ok"], out["stopped"]
    assert out["effective_operation_class"] == "JUDGMENT_BEARING"
    si = intent(p, out)
    assert [s["primitive"] for s in si["steps"]] == ["review.ingest", "work.transition", "invoke.create.mutating",
                                                     "dispatch.launch"]
    assert si["judgment_inputs"] == ["accept_review_evidence"]
    assert si["binding"]["obligations_digest"].startswith("sha256:")  # a stage that accepts evidence binds them
    assert unit(p, wid)["state"] == "VERIFY_PENDING"
    [inv] = si["steps"][2]["outputs"]["invocations"]
    assert control(p)["invocations"][inv]["role"] == "verifier"
    assert_control_invariants(p)


def test_a_review_that_fails_stops_the_request_after_its_ingest(lab_project, tmp_path):
    """Rule 3: a review that fails is ingested (REVIEW_FAILED), and the transition to VERIFY_PENDING refuses, so the
    stage stops there; the projection said so beforehand (BLOCKED), and the ingest stands."""
    p, _lab = lab_project
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    evidence = review(p, wid, disposition="changes_required",
                      findings=[{"id": "F1", "severity": "major", "summary": "wrong result", "required": True}])
    engine = Engine.discover(p.root)
    explained = R.run_tool(engine, CTX, "explain", {"stage": "ticket_request_verification",
                                                    "arguments": {"work_id": wid, "review_evidence": evidence}})
    assert explained["result"]["availability"] == "BLOCKED"
    out = call(p, "ticket_request_verification", work_id=wid, review_evidence=evidence)
    assert not out["ok"] and out["stopped"]["at"] == "work.transition"
    assert [s["primitive"] for s in out["completed_steps"]] == ["review.ingest"]
    assert unit(p, wid)["state"] == "REVIEW_FAILED" and intent(p, out)["status"] == SI.STOPPED
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- equivalence (§10)


@pytest.mark.parametrize("name", ["ticket_request_review", "ticket_request_verification"])
def test_stage_matches_primitives(tmp_path, monkeypatch, name):
    """Plan v3 §10 (fake harness): the request stage and its primitives run directly, with the same arguments, end in
    the same state, compared without the journal's own records (``stage_equivalence``)."""
    labs: list[Any] = []
    found: dict[str, str] = {}

    def prepare(p: Project) -> None:
        labs.append(launching(p, tmp_path, monkeypatch))
        labs[0].script("default", HANG)
        create_planned_ticket(p, tmp_path)

    staged, direct = _twins(tmp_path, prepare)
    # The same work in each copy, after the copy: each has its own workspace (a copied control state would name the
    # first copy's).
    for p in (staged, direct):
        implement(assign(p, "T-0001"))
        if name == "ticket_request_verification":
            p.lead("work", "transition", "T-0001", "--to", "REVIEW_PENDING")
            found["review"] = review(p, "T-0001")
    decisions = recorded_decisions()
    recorded = decisions.__enter__()
    try:
        e = Engine.discover(direct.root)

        def rev() -> int:
            return int(e.store.read()["revision"])

        # What the two copies' roles produced differs only in the bytes of their reports (a check's duration and its
        # log), never in control state; the stage and its primitives must add no difference to these.
        before = differences(end_state(staged.root, recorded), end_state(direct.root, recorded))
        assert all(d.startswith("/files/evidence/") for d in before), before
        if name == "ticket_request_review":
            out = call(staged, name, work_id="T-0001")
            assert out["ok"], out["stopped"]
            e.work_transition(token=direct.token, expect_rev=rev(), work_id="T-0001", to="REVIEW_PENDING")
            role = "reviewer"
        else:
            out = call(staged, name, work_id="T-0001", review_evidence=found["review"])
            assert out["ok"], out["stopped"]
            e.review_ingest(token=direct.token, expect_rev=rev(), work_id="T-0001", evidence_id=found["review"])
            e.work_transition(token=direct.token, expect_rev=rev(), work_id="T-0001", to="VERIFY_PENDING")
            role = "verifier"
        e.launch_dispatched(e.invoke_create(token=direct.token, expect_rev=rev(), work_id="T-0001", role=role,
                                            launch=True))
        a, b = end_state(staged.root, recorded), end_state(direct.root, recorded)
        assert differences(a, b) == before, "\n".join(sorted(set(differences(a, b)) ^ set(before)))
    finally:
        decisions.__exit__(None, None, None)
        for lab in labs:
            lab.cleanup()
            lab.project = direct  # the copy's runs are its own: end them the same way
            lab.cleanup()


# ---------------------------------------------------------------------------------------------- side effects (SAE-07)


@pytest.mark.parametrize("primitive", ["review.ingest", "verify.ingest", "invoke.create.mutating", "work.dispose"])
def test_declared_effects_cover_observed_effects(tmp_path, primitive):
    """A1 §6 / SAE-07, per primitive E5b stages (or adds) first: what running it is observed to change never exceeds
    what its PrimitiveSpec declares. The ingests complete the reporter's invocation, revoking its credential."""
    p = sample_project(tmp_path)
    mark(p, review_severities=["minor"])
    e = Engine.discover(p.root)
    tok = p.token

    def rev() -> int:
        return int(e.store.read()["revision"])

    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    if primitive == "invoke.create.mutating":
        before = _observe(p)
        e.invoke_create(token=tok, expect_rev=rev(), work_id=wid, role="reviewer")
    elif primitive == "work.dispose":
        evidence = review(p, wid, findings=[MINOR])
        before = _observe(p)
        e.work_dispose(token=tok, expect_rev=rev(), subject=f"{evidence}#F1", choice="accept_risk",
                       rationale="a naming nit")
    elif primitive == "review.ingest":
        evidence = review(p, wid)
        before = _observe(p)
        e.review_ingest(token=tok, expect_rev=rev(), work_id=wid, evidence_id=evidence)
    else:
        first = review(p, wid)
        e.review_ingest(token=tok, expect_rev=rev(), work_id=wid, evidence_id=first)
        p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
        evidence = verify(p, wid)
        before = _observe(p)
        e.verify_ingest(token=tok, expect_rev=rev(), work_id=wid, evidence_id=evidence, scope="ticket")
    seen = _effects(before, _observe(p))
    assert "control_state" in seen and seen <= _declared(primitive), seen
    if primitive in ("review.ingest", "verify.ingest", "invoke.create.mutating"):
        assert "credential" in seen  # revoked by the ingest, issued by the dispatch


# ---------------------------------------------------------------------------------------------- dispositions (§2.4)


def test_by_default_nothing_is_marked_and_nothing_changes(tmp_path):
    """The policy key's default is empty: a minor finding is noted as before, and the review ingests (§9)."""
    p = sample_project(tmp_path)
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid, findings=[MINOR]))
    assert unit(p, wid)["state"] == "REVIEW_PASSED" and "dispositions" not in unit(p, wid)


def test_a_marked_finding_holds_the_ingest_until_the_lead_disposes_of_it(tmp_path):
    """The gate input both paths share: the primitive and the stage refuse to advance past an undisposed marked
    finding (DISPOSITION_REQUIRED), the guard query says so beforehand, and after the Lead's disposition (through
    `resolve`) the stage advances. A required finding is never disposed of."""
    p = sample_project(tmp_path)
    mark(p, review_severities=["minor", "observation"])
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    evidence = review(p, wid, findings=[MINOR])
    engine = Engine.discover(p.root)
    rev = p.rev()
    refused = p.aew("review", "ingest", wid, "--evidence", evidence, "--token", p.token, "--expect-rev", str(rev))
    assert refused.returncode != 0 and "DISPOSITION_REQUIRED" in (refused.stdout + refused.stderr)
    answer = engine.guard_query("review.ingest", wid, {"evidence": evidence})
    assert answer["availability"] == "BLOCKED" and answer["reason_codes"] == ["DISPOSITION_REQUIRED"]
    assert answer["blocking_conditions"][0]["details"]["items"][0]["id"] == f"{evidence}#F1"
    explained = R.run_tool(engine, CTX, "explain", {"stage": "ticket_request_verification",
                                                    "arguments": {"work_id": wid, "review_evidence": evidence}})
    assert explained["result"]["availability"] == "BLOCKED"
    out = R.run_tool(engine, CTX, "ticket_request_verification",
                     {"expect_rev": p.rev(), "work_id": wid, "review_evidence": evidence}, token=p.token)
    assert not out["ok"] and out["stopped"]["error"]["code"] == "DISPOSITION_REQUIRED" and not out["completed_steps"]
    assert unit(p, wid)["state"] == "REVIEW_PENDING" and p.rev() == rev + 2  # the intent opened and stopped
    disposed = R.run_tool(engine, CTX, "resolve", {"expect_rev": p.rev(), "subject": f"{evidence}#F1",
                                                   "choice": "accept_risk", "rationale": "a naming nit"},
                          token=p.token)
    assert disposed["ok"], disposed["stopped"]
    assert [s["primitive"] for s in disposed["completed_steps"]] == ["work.dispose"]
    assert disposed["stage_intent_id"] is None  # one transaction: no stage intent
    [pointer] = unit(p, wid)["dispositions"]
    assert pointer["subject"] == f"{evidence}#F1" and pointer["choice"] == "accept_risk"
    record = engine.disposition(f"{evidence}#F1")
    assert record["subject"] == {"id": f"{evidence}#F1", "kind": "finding", "evidence": evidence}
    assert record["generation"] == control(p)["lead"]["generation"] and record["rationale"] == "a naming nit"
    assert (p.root / ".aew" / pointer["path"]).is_file()
    projection.clear_cache()
    out = R.run_tool(engine, CTX, "ticket_request_verification",
                     {"expect_rev": p.rev(), "work_id": wid, "review_evidence": evidence}, token=p.token)
    assert out["completed_steps"][0]["primitive"] == "review.ingest"
    assert unit(p, wid)["state"] in ("VERIFY_PENDING", "REVIEW_PASSED")
    assert_control_invariants(p)


def test_an_ingested_marked_finding_holds_the_next_advance(tmp_path):
    """A report that does not advance (another review is outstanding, or it fails) is ingested and records its marked
    finding; the review that would advance is refused until that finding is disposed of, and the projection lists it
    as a decision with no default."""
    p = sample_project(tmp_path)
    mark(p, review_severities=["minor"])
    wid, impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    failing = review(p, wid, disposition="changes_required",
                     findings=[MINOR, {"id": "F2", "severity": "major", "summary": "wrong", "required": True}])
    p.lead("review", "ingest", wid, "--evidence", failing)  # REVIEW_FAILED: no advance, recorded
    assert unit(p, wid)["state"] == "REVIEW_FAILED"
    status = R.run_tool(Engine.discover(p.root), CTX, "status", {"work_id": wid})["projection"]
    dispose = [d for d in status["decisions_required"] if d["decision"] == "DISPOSE_FINDING"]
    assert [d["arguments"]["subject"] for d in dispose] == [f"{failing}#F1"]
    assert dispose[0]["default"] == "NONE" and dispose[0]["tool"] == "resolve"
    assert unit(p, wid)["findings"][0]["status"] == "noted"
    p.lead("work", "transition", wid, "--to", "RUNNING", "--reason", "fix the major finding")
    from aewflow import redispatch_implementer
    impl = redispatch_implementer(p, wid)
    implement(impl, {**SUBTRACT_PATCH, "calc/extra.py": "X = 1\n"})
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    passing = review(p, wid, resolved=[f"{failing}#F2"])
    refused = p.aew("review", "ingest", wid, "--evidence", passing, "--token", p.token, "--expect-rev", str(p.rev()))
    assert refused.returncode != 0 and "DISPOSITION_REQUIRED" in (refused.stdout + refused.stderr)
    p.lead("work", "dispose", f"{failing}#F1", "--choice", "follow_up", "--follow-up",
           create_planned_ticket(p, tmp_path, title="Rename"), "--rationale", "renamed separately")
    p.lead("review", "ingest", wid, "--evidence", passing)
    assert unit(p, wid)["state"] == "REVIEW_PASSED"
    assert_control_invariants(p)


@pytest.mark.parametrize("case", ["required", "unmarked", "twice", "unknown_follow_up", "own_ticket", "no_such"])
def test_a_disposition_is_refused_unless_it_names_a_marked_open_item(tmp_path, case):
    p = sample_project(tmp_path)
    mark(p, review_severities=["minor"])
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    evidence = review(p, wid, disposition="changes_required", findings=[
        MINOR, {"id": "F2", "severity": "blocker", "summary": "x", "required": True},
        {"id": "F3", "severity": "observation", "summary": "y", "required": False}])
    subject, extra, reason = {
        "required": (f"{evidence}#F2", {}, "not_marked"),
        "unmarked": (f"{evidence}#F3", {}, "not_marked"),
        "twice": (f"{evidence}#F1", {}, "already_disposed"),
        "unknown_follow_up": (f"{evidence}#F1", {"choice": "follow_up", "follow_up": "T-0099"}, None),
        "own_ticket": (f"{evidence}#F1", {"choice": "follow_up", "follow_up": wid}, "follow_up_is_subject"),
        "no_such": (f"{evidence}#F9", {}, None),
    }[case]
    if case == "twice":
        p.lead("work", "dispose", subject, "--choice", "not_applicable", "--rationale", "out of scope")
    rev = p.rev()
    out = R.run_tool(Engine.discover(p.root), CTX, "resolve", {"expect_rev": rev, "subject": subject,
                                                               "choice": "accept_risk", "rationale": "r", **extra},
                     token=p.token)
    assert not out["ok"] and p.rev() == rev
    if reason:
        assert out["stopped"]["error"]["details"]["reason"] == reason
    else:
        assert out["stopped"]["error"]["code"] == "NOT_FOUND"


def test_the_dashboard_flags_a_report_with_an_undisposed_marked_item(tmp_path):
    """The dashboard's hard-coded `requires_disposition: false` is the real value now (plan v3 §2.7), read through
    `aew.dashboard`'s read API."""
    from aew.dashboard.projections import Projector
    from aew.dashboard.reader import StateReader

    p = sample_project(tmp_path)
    mark(p, review_severities=["minor"])
    wid, _impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    evidence = review(p, wid, findings=[MINOR])
    plain = review(p, wid)

    def flags() -> dict[str, bool]:
        projector = Projector(StateReader(Engine.discover(p.root)).snapshot())
        return {m["id"]: projector.evidence_item(m, "", unit(p, wid))["requires_disposition"]
                for m, _ in projector._hot_evidence(wid) if m["kind"] == "review"}

    assert flags() == {evidence: True, plain: False}
    p.lead("work", "dispose", f"{evidence}#F1", "--choice", "accept_risk", "--rationale", "a nit")
    assert flags() == {evidence: False, plain: False}


# ---------------------------------------------------------------------------------------------- anomalies (§2.4)


def _reviewer(p: Project, wid: str) -> Any:
    from aewflow import Role

    out = p.lead("invoke", "create", wid, "--role", "reviewer")
    return Role(p, out["invocation_token"], Path(p.ok("work", "show", wid)["control"]["workspace"]["path"]))


def test_a_reviewer_that_mutates_its_workspace_opens_a_high_anomaly(tmp_path):
    """WORKSPACE_MUTATED met by a worker (its submission is refused, unchanged) is a signal the next Lead commit records
    as a high anomaly. It adds no guard: the Lead's next primitive still runs; the subject's projected actions are
    never auto-runnable while it is open; the Lead disposes of it, which moves it cold (TIS-35)."""
    p = sample_project(tmp_path)
    wid, impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    reviewer = _reviewer(p, wid)
    reviewer.write({"calc/core.py": "def add(a, b):\n    return a - b\n"})
    res = reviewer.submit("review", {"claim": "c", "review": {"independence": "R1", "disposition": "pass",
                                                              "findings": []}}, expect_ok=False)
    assert res.returncode != 0 and "WORKSPACE_MUTATED" in (res.stdout + res.stderr)
    assert "anomalies" not in control(p)  # a worker commits no control state
    p.lead("checkpoint", "--next", "after the reviewer's refusal")
    [an] = control(p)["anomalies"].values()
    assert (an["source"], an["severity"], an["subject"]) == ("WORKSPACE_MUTATED", "high", wid)
    assert not list((p.root / ".aew" / DO.SPOOL_REL).glob("*.json"))  # recorded once, then gone
    p.lead("checkpoint", "--next", "again")
    assert len(control(p)["anomalies"]) == 1
    status = R.run_tool(Engine.discover(p.root), CTX, "status", {"work_id": wid})["projection"]
    assert [a["details"]["anomaly"] for a in status["anomalies"]] == [an["id"]]
    assert any(d["decision"] == "DISPOSE_ANOMALY" for d in status["decisions_required"])
    out = R.run_tool(Engine.discover(p.root), CTX, "resolve", {"expect_rev": p.rev(), "subject": an["id"],
                                                               "choice": "not_applicable",
                                                               "rationale": "the reviewer was replaced"},
                     token=p.token)
    assert out["ok"], out["stopped"]
    assert "anomalies" not in control(p)
    record = Engine.discover(p.root).disposition(an["id"])
    assert record["anomaly"]["id"] == an["id"] and record["anomaly"]["disposition"]["choice"] == "not_applicable"
    assert_control_invariants(p)


def test_a_lead_call_refused_with_workspace_mutated_records_an_anomaly(tmp_path):
    """A Lead transaction refused with WORKSPACE_MUTATED (a reviewer dispatched over unreported changes) is recorded
    in a commit of its own, under the same credential; the refusal itself is unchanged."""
    p = sample_project(tmp_path)
    wid, impl = implemented(p, tmp_path)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    impl.write({"calc/core.py": "def add(a, b):\n    return a + b + 0\n"})
    rev = p.rev()
    res = p.aew("invoke", "create", wid, "--role", "reviewer", "--token", p.token, "--expect-rev", str(rev))
    assert res.returncode != 0 and "WORKSPACE_MUTATED" in (res.stdout + res.stderr)
    assert p.rev() == rev + 1
    [an] = control(p)["anomalies"].values()
    assert an["source"] == "WORKSPACE_MUTATED" and an["subject"] == wid
    assert control(p)["last_transition"]["op"] == "anomaly.record"


def test_a_contradiction_is_recorded_and_disposed_of_only_once_it_is_gone(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    record = p.root / ".aew" / unit(p, wid)["record"]
    original = record.read_bytes()
    record.write_bytes(original + b"\n# edited outside AEW\n")
    p.lead("checkpoint", "--next", "next commit")
    [an] = control(p)["anomalies"].values()
    assert an["source"] == "CONTRADICTION" and an["subject"] == wid and an["severity"] == "high"
    out = R.run_tool(Engine.discover(p.root), CTX, "resolve", {"expect_rev": p.rev(), "subject": an["id"],
                                                               "choice": "accept_risk", "rationale": "r"},
                     token=p.token)
    assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "still_live"
    record.write_bytes(original)
    p.lead("work", "dispose", an["id"], "--choice", "not_applicable", "--rationale", "restored")
    assert "anomalies" not in control(p)


def test_a_high_anomaly_stops_auto_run_and_changes_no_availability(lab_project, tmp_path):
    """n6: a high anomaly adds no primitive guard. The READY Ticket's start stays AVAILABLE, but is not auto-runnable
    while the anomaly is open; the Lead can still run it, by explicit judgment."""
    p, _lab = lab_project
    wid = create_planned_ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    before = R.run_tool(engine, CTX, "status", {"work_id": wid})["projection"]["actions"][0]
    assert before["action"] == "ticket_start" and before["availability"] == "AVAILABLE" and before["auto_runnable"]
    DO.signal(p.root / ".aew", WorkspaceMutated("seeded", work_id=wid), wid)
    p.lead("checkpoint", "--next", "records the signal")
    projection.clear_cache()
    after = R.run_tool(engine, CTX, "status", {"work_id": wid})["projection"]
    action = after["actions"][0]
    assert action["availability"] == "AVAILABLE" and not action["auto_runnable"]
    assert after["anomalies"] and after["anomalies"][0]["details"]["severity"] == "high"
    out = call(p, "ticket_start", work_id=wid)
    assert out["ok"], out["stopped"]  # no guard: the Lead's explicit call runs
    assert control(p)["anomalies"]


def test_disposed_anomalies_leave_hot_state_and_read_cold_quickly(tmp_path):
    """TIS-35: only open anomalies are hot; each disposed one leaves it in the same commit, and its cold record is
    found without scanning (a pointer on its live Ticket)."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    ids = []
    for n in range(8):
        DO.signal(p.root / ".aew", WorkspaceMutated(f"seeded {n}", work_id=wid, changed=[str(n)]), wid)
        p.lead("checkpoint", "--next", f"records signal {n}")
        ids.append(max(control(p)["anomalies"]))
    assert len(control(p)["anomalies"]) == 8
    for an in ids:
        engine.work_dispose(token=p.token, expect_rev=p.rev(), subject=an, choice="not_applicable",
                            rationale="seeded")
    state = control(p)
    assert "anomalies" not in state and len(state["work"][wid]["dispositions"]) == 8
    started = time.perf_counter()
    for an in ids:
        assert engine.disposition(an)["anomaly"]["id"] == an
    assert (time.perf_counter() - started) / len(ids) < 0.5
    assert_control_invariants(p)
