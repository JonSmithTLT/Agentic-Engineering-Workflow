"""Composition tests for the 2026-09-26 review: operations that are individually tested,
exercised in the sequences where the review found unguarded interactions.

Every scenario ends with the cross-operation invariant oracle.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aewflow import (SUBTRACT_PATCH, assign, create_planned_ticket, implement, integrate, prepare_and_validate,
                     redispatch_implementer, review, sample_project, to_commit_ready, verify)
from conftest import git
from invariants import assert_control_invariants


def unit(p, wid):
    return p.ok("work", "show", wid)["control"]


def main_commit(p):
    return git("rev-parse", "refs/heads/main", cwd=p.root)


def crash_after_publishing_record(p, wid):
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()),
                env={"AEW_FAULT": "integrate.after_publishing_record"})
    assert res.returncode == 86
    assert unit(p, wid)["integration"]["status"] == "publishing"


def test_invariants_hold_on_the_normal_serial_lifecycle(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    assert_control_invariants(p)
    integrate(p, wid)
    assert_control_invariants(p)


def test_interleaved_writer_makes_finalization_stale_before_any_git_side_effect(tmp_path):
    """M1: a revision committed between the publishing record and finalization is detected under
    the lock before the CAS; the ref and the authoritative worktree are untouched until a
    reconcile with the current revision."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    crash_after_publishing_record(p, wid)
    stale_rev = p.rev()
    p.lead("checkpoint", "--next", "another Lead write lands in between")
    before = (p.root / "calc/core.py").read_bytes()
    res = p.aew("integrate", "reconcile", wid, "--token", p.token, "--expect-rev", str(stale_rev))
    assert res.error["code"] == "STALE_REVISION"
    assert main_commit(p) == integ["base"]
    assert (p.root / "calc/core.py").read_bytes() == before
    out = p.lead("integrate", "reconcile", wid)
    assert out["state"] == "DONE" and main_commit(p) == integ["candidate"]
    assert_control_invariants(p)


MULTIPLY_PATCH = {
    **SUBTRACT_PATCH,
    "calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "\n\ndef multiply(a, b):\n    return a * b\n",
    "tests/test_multiply.py": "from calc.core import multiply\n\n\ndef test_multiply():\n"
                              "    assert multiply(3, 4) == 12\n",
}


def back_to_commit_ready_with(p, wid, files):
    impl = redispatch_implementer(p, wid)
    implement(impl, files)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    return impl


def test_regression_after_validation_supersedes_the_candidate_and_the_new_work_is_published(tmp_path):
    """B1: validated candidate -> regression -> newly verified snapshot -> publish integrates the NEW work."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    old = prepare_and_validate(p, wid)
    p.lead("work", "transition", wid, "--to", "RUNNING", "--reason", "additional required behavior")
    u = unit(p, wid)
    assert u["integration"] is None
    assert u["integration_history"][-1]["status"] == "superseded"
    impl = back_to_commit_ready_with(p, wid, MULTIPLY_PATCH)
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "ILLEGAL_TRANSITION" and impl.workspace.exists()
    new = prepare_and_validate(p, wid)
    assert new["attempt"] == old["attempt"] + 1 and new["binding"]["commit_ready_seq"] == 2
    p.lead("integrate", "publish", wid)
    assert "def multiply" in (p.root / "calc/core.py").read_text(encoding="utf-8")
    assert not Path(old["workspace"]).exists()
    assert_control_invariants(p)


def test_state_cannot_leave_commit_ready_while_a_publish_is_pending(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    crash_after_publishing_record(p, wid)
    for to in ("RUNNING", "CANCELLED", "REPLAN_REQUIRED"):
        res = p.aew("work", "transition", wid, "--to", to, "--reason", "try to abandon the publish",
                    "--token", p.token, "--expect-rev", str(p.rev()))
        assert res.error["code"] == "ILLEGAL_TRANSITION", (to, res.stderr)
        assert "integrate reconcile" in res.error["message"]
    assert p.lead("integrate", "reconcile", wid)["state"] == "DONE"
    assert_control_invariants(p)


def test_workspace_holding_unintegrated_changes_is_retained_and_reported(tmp_path):
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    impl.write({"calc/extra.py": "LATE = True\n"})  # appears after the candidate was built
    p.lead("integrate", "publish", wid)
    ws = unit(p, wid)["workspace"]
    assert ws["status"].startswith("retained") and ws["retained"]["dirty"]
    assert (impl.workspace / "calc/extra.py").exists()
    assert any("retained after integration" in c for c in p.ok("status", "--json")["contradictions"])
    assert not (p.root / "calc/extra.py").exists()
    assert_control_invariants(p)


def test_candidate_bound_to_an_earlier_acceptance_is_superseded_at_publish(tmp_path):
    """Defense in depth: a candidate whose binding no longer matches (e.g. legacy/unbound state) never publishes."""
    from aew.engine.api import Engine
    from aew.engine.store import Transition

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    engine = Engine.discover(p.root)
    with engine.store.session() as s:  # simulate a record bound to an earlier COMMIT_READY
        s.state["work"][wid]["commit_ready_seq"] += 1
        s.commit(Transition(op="test.legacy_state", actor={"kind": "test"}))
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "STALE_CANDIDATE"
    assert main_commit(p) == integ["base"]
    u = unit(p, wid)
    assert u["integration"] is None and u["integration_history"][-1]["status"] == "superseded"


def replan(p, wid, tmp_path, revision):
    p.lead("work", "transition", wid, "--to", "REPLAN_REQUIRED", "--reason", f"revise approach ({revision})")
    plan = tmp_path / f"{wid}-plan-v{revision}.md"
    plan.write_text(f"Revised approach {revision}.\n", encoding="utf-8")
    p.lead("plan", "propose", wid, "--file", str(plan), "--reason", "new requirement")
    p.lead("plan", "accept", wid, "--revision", str(revision))


def test_repeated_replan_and_interruption_cycles_keep_the_serial_boundary(tmp_path):
    """M2 compositions: assign -> replan -> assign -> handoff -> reconcile, repeatedly, under the oracle."""
    p = sample_project(tmp_path)
    first = create_planned_ticket(p, tmp_path)
    old_roles = []
    for revision in (2, 3):
        impl = assign(p, first)
        impl.write(SUBTRACT_PATCH)  # partial work under the plan about to be replaced
        replan(p, first, tmp_path, revision)
        u = unit(p, first)
        assert u["state"] == "READY" and u["workspace"]["status"].startswith("released (replanned")
        assert_control_invariants(p)
        old_roles.append(impl)
    for impl in old_roles:  # superseded credentials never act again, on any workspace
        res = impl.aew("check", "run", "guardrails")
        assert res.returncode != 0, res.stdout
    second = create_planned_ticket(p, tmp_path, title="Second mutating ticket")
    impl2 = assign(p, second)
    res = p.aew("work", "assign", first, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "CONCURRENCY_LIMIT"
    offer = p.lead("lead", "handoff", "offer")["offer"]
    p.token = p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))["token"]
    assert unit(p, second)["state"] == "INTERRUPTED"
    assert impl2.aew("check", "run", "guardrails").returncode != 0
    p.lead("work", "reconcile", second, "--to", "RUNNING", "--reason", "inspected the workspace; continue")
    fresh = redispatch_implementer(p, second)
    assert fresh.ok("check", "run", "guardrails")["evaluated_snapshot"]["workspace_id"] == \
        unit(p, second)["workspace"]["id"]
    assert_control_invariants(p)


def test_invocation_is_never_retargeted_to_another_workspace(tmp_path):
    """Defense in depth: even with a live credential, an invocation acts only on the workspace it was
    dispatched for (here the Ticket's workspace stopped being live under it)."""
    from aew.engine.api import Engine
    from aew.engine.store import Transition

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    engine = Engine.discover(p.root)
    with engine.store.session() as s:  # simulate a record whose workspace was released without revocation
        s.state["work"][wid]["workspace"]["status"] = "released (test)"
        s.commit(Transition(op="test.legacy_state", actor={"kind": "test"}))
    res = impl.aew("check", "run", "guardrails")
    assert res.error["code"] == "PERMISSION_DENIED"
    assert "no longer the Ticket's live workspace" in res.error["message"]


def handoff(p):
    offer = p.lead("lead", "handoff", "offer")["offer"]
    p.token = p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))["token"]


def test_interruption_keeps_a_review_failure_and_revokes_the_sibling_reviewer(tmp_path):
    """M5 generalized: a state determined by ingested evidence survives the loss of an unrelated invocation."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    p.lead("work", "staff", wid, "--review", "code_reviewer", "--review", "security_reviewer")
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    sibling = p.lead("invoke", "create", wid, "--card", "security_reviewer")["invocation"]
    failing = review(p, wid, card="code_reviewer", disposition="changes_required",
                     findings=[{"id": "F1", "severity": "major", "summary": "edge case missing"}])
    p.lead("review", "ingest", wid, "--evidence", failing)
    assert unit(p, wid)["state"] == "REVIEW_FAILED"
    handoff(p)
    u = unit(p, wid)
    assert u["state"] == "REVIEW_FAILED" and "interrupted_from" not in u
    assert p.ok("invoke", "show", sibling)["status"] == "interrupted"
    assert u["history"][-1]["event"] == "invocation_interrupted"
    assert_control_invariants(p)


def test_handoff_while_publishing_keeps_commit_ready_and_reconcile_completes(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    straggler = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")["invocation"]
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, scope="integration"))
    crash_after_publishing_record(p, wid)
    handoff(p)
    u = unit(p, wid)
    assert u["state"] == "COMMIT_READY" and u["integration"]["status"] == "publishing"
    assert p.ok("invoke", "show", straggler)["status"] == "interrupted"
    assert p.lead("integrate", "reconcile", wid)["state"] == "DONE"
    assert_control_invariants(p)


def test_submitted_but_uningested_reports_satisfy_no_gate(tmp_path):
    """M4: review and verification gates count only reports the Lead ingested (ids + sha256 pinned)."""
    from aew.util import dump_yaml

    p = sample_project(tmp_path)
    (p.root / ".aew/roles/strict_verifier.yaml").write_text(dump_yaml({
        "schema": "aew/role/v1", "role": "strict_verifier", "display_name": "Strict Verifier", "version": 1,
        "extends": "verifier", "purpose": "Second, independent acceptance verification.",
    }), encoding="utf-8", newline="\n")
    wid = create_planned_ticket(p, tmp_path)
    p.lead("work", "staff", wid, "--verify", "verifier", "--verify", "strict_verifier")
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    submitted = review(p, wid)
    gates = p.ok("gate", "show", wid)
    assert gates["gates"]["review_r1"]["status"] == "MISSING" and submitted in gates["evidence_ids"]
    p.lead("review", "ingest", wid, "--evidence", submitted)
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    # Both verifier cards submit before either is ingested.
    strict = verify(p, wid, card="strict_verifier")
    plain = verify(p, wid, card="verifier")
    out = p.lead("verify", "ingest", wid, "--evidence", plain)
    assert out["transition"] is None and "verify_card:strict_verifier" in out["pending_verifications"]
    assert unit(p, wid)["state"] == "VERIFY_PENDING"
    out = p.lead("verify", "ingest", wid, "--evidence", strict)
    assert out["transition"]["to"] == "VERIFIED"
    assert {e["id"] for e in unit(p, wid)["evidence"]} >= {plain, strict, submitted}
    assert_control_invariants(p)


def test_lead_override_of_an_operator_pin_goes_through_a_recorded_decision(tmp_path):
    """M7: dispatch honours the operator pin; replacing it needs --reason and leaves a decision."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    p.lead("work", "staff", wid, "--execute", "c_engineer")
    p.lead("work", "staff", wid, "--execute", "c_engineer", "--by", "operator", "--pin")
    p.lead("work", "staff", wid, "--execute", "c_engineer")  # a Lead re-selection keeps the operator pin
    entry = unit(p, wid)["role_plan"]["execute"][0]
    assert entry["selected_by"] == "operator" and entry["pinned"] is True
    assign(p, wid)
    p.lead("invoke", "cancel", unit(p, wid)["implementer_invocation"], "--reason", "fresh bounded attempt")
    res = p.aew("invoke", "create", wid, "--card", "python_engineer", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "PERMISSION_DENIED" and "work staff" in res.error["message"]
    res = p.aew("work", "staff", wid, "--execute", "python_engineer", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "PERMISSION_DENIED"  # no reason: the pin stands
    out = p.lead("work", "staff", wid, "--execute", "python_engineer", "--reason", "operator agreed: Python work")
    assert out["decision"]
    assert p.lead("invoke", "create", wid, "--card", "python_engineer")["role_card"] == "python_engineer"
    assert_control_invariants(p)


def _authority_project(tmp_path):
    from conftest import Project, make_git_repo

    repo = make_git_repo(tmp_path / "repo", {"README.md": "# fixture\n", "docs/adr/0001.md": "# decision\n"})
    proj = Project(repo)
    candidates = proj.ok("init")["authority_candidates"]
    proj.token = proj.ok("lead", "acquire", "--expect-rev", "0")["token"]
    return proj, next(c for c in candidates if c["path"] == "docs/adr/")


def test_long_lived_engine_never_serves_an_older_manifest(tmp_path):
    """M8: an engine instance reloads project.yaml with every locked session."""
    from aew.engine.api import Engine

    proj, candidate = _authority_project(tmp_path)
    reader = Engine.discover(proj.root)
    assert reader.authority_list()["accepted"] == []
    writer = Engine.discover(proj.root)
    writer.authority_accept(token=proj.token, expect_rev=proj.rev(), candidate_id=candidate["id"], klass="decisions")
    assert [a["path"] for a in reader.authority_list()["accepted"]] == ["docs/adr/"]
    assert [a["path"] for a in reader.resume()["accepted_authority"]] == ["docs/adr/"]


def test_first_resume_after_a_crash_mid_manifest_apply_shows_the_committed_authority(tmp_path):
    proj, candidate = _authority_project(tmp_path)
    res = proj.aew("authority", "accept", candidate["id"], "--class", "decisions",
                   "--token", proj.token, "--expect-rev", str(proj.rev()), env={"AEW_FAULT": "txn.mid_apply"})
    assert res.returncode == 86
    first = proj.ok("resume", "--json")
    assert [a["path"] for a in first["accepted_authority"]] == ["docs/adr/"]
    assert first["contradictions"] == []
    checks = {c["check"]: c["status"] for c in proj.aew("doctor", "--json").json["checks"]}
    assert checks["manifest"] == "PASS" and checks["manifest-pin"] == "PASS"


# ------------------------------------------------------------------ re-review (e7e723c) residuals


def test_prepare_refuses_a_workspace_index_that_hides_edits(tmp_path):
    """B1 residual, neighbor path: `git add` would leave assume-unchanged edits out of the Ticket commit."""
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    git("update-index", "--assume-unchanged", "calc/core.py", cwd=impl.workspace)
    res = p.aew("integrate", "prepare", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and "calc/core.py" in res.error["details"]["paths"]
    assert unit(p, wid)["integration"] is None
    assert git("ls-files", "-v", "calc/core.py", cwd=impl.workspace).startswith("h ")  # flags are not cleared for us


def test_done_cleanup_retains_a_workspace_whose_content_cannot_be_verified(tmp_path):
    """B1 residual: removal needs positive proof from content; a sparse entry makes that impossible."""
    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    prepare_and_validate(p, wid)
    git("update-index", "--skip-worktree", "README.md", cwd=impl.workspace)
    p.lead("integrate", "publish", wid)
    ws = unit(p, wid)["workspace"]
    assert ws["status"] == "retained (content could not be verified)" and "skip-worktree" in ws["retained"]["reason"]
    assert impl.workspace.exists()
    assert any("retained after integration" in c for c in p.ok("status", "--json")["contradictions"])
    assert_control_invariants(p)


def test_workspace_inspection_reads_content_not_index_flags(tmp_path):
    from aew.workspace import worktrees

    p = sample_project(tmp_path)
    wid, impl = to_commit_ready(p, tmp_path)
    head = git("rev-parse", "HEAD", cwd=impl.workspace)
    git("add", "-A", cwd=impl.workspace)
    git("commit", "-qm", "wip", cwd=impl.workspace)
    assert worktrees.inspect(str(impl.workspace), head)["dirty"] is False
    git("update-index", "--assume-unchanged", "calc/core.py", cwd=impl.workspace)
    (impl.workspace / "calc/core.py").write_text("# hidden edit\n", encoding="utf-8", newline="\n")
    assert git("status", "--porcelain", cwd=impl.workspace) == ""  # what git status would have claimed
    assert worktrees.inspect(str(impl.workspace), head)["dirty"] is True
    assert git("ls-files", "-v", "calc/core.py", cwd=impl.workspace).startswith("h ")


def test_retiring_a_candidate_ends_its_verifiers_write_authority(tmp_path):
    """M2 residual: a retired candidate's integration verifier is revoked; history is kept."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    straggler = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    assert p.ok("invoke", "show", straggler["invocation"])["integration_attempt"] == 1
    p.lead("work", "transition", wid, "--to", "RUNNING", "--reason", "supersede the candidate")
    assert p.ok("invoke", "show", straggler["invocation"])["status"] == "cancelled"
    assert_control_invariants(p)


@pytest.mark.parametrize("kind", ["review", "verification"])
def test_reports_are_written_only_for_a_live_workspace(tmp_path, kind):
    """M2 residual, defense in depth: review/verification submission is bound to the invocation's live
    workspace even if its credential were somehow still valid (simulated legacy state)."""
    from aew.engine.api import Engine
    from aew.engine.store import Transition
    from aewflow import Role
    from aew.util import dump_yaml

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    if kind == "verification":
        p.lead("review", "ingest", wid, "--evidence", review(p, wid))
        p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    role = "reviewer" if kind == "review" else "verifier"
    out = p.lead("invoke", "create", wid, "--role", role)
    agent = Role(p, out["invocation_token"], Path(unit(p, wid)["workspace"]["path"]))
    checks = [agent.check("unit")["evidence"]] if kind == "verification" else []
    engine = Engine.discover(p.root)
    with engine.store.session() as sess:
        sess.state["work"][wid]["workspace"]["status"] = "released (test)"
        sess.commit(Transition(op="test.legacy_state", actor={"kind": "test"}))
    meta = ({"review": {"independence": "R1", "disposition": "pass", "findings": []}} if kind == "review" else
            {"verification": {"scope": "ticket", "claims": [
                {"type": "goal_backwards", "claim": "g", "result": "pass", "checks": checks},
                {"type": "contract", "claim": "c", "result": "pass", "checks": checks}]}})
    res = agent.submit(kind, meta, expect_ok=False)
    assert res.error["code"] == "PERMISSION_DENIED" and "no longer the Ticket's live workspace" in res.error["message"]


def test_review_from_a_superseded_plan_is_not_accepted_for_identical_new_work(tmp_path):
    """R1, ticket-scope analogue: same bytes, earlier plan and attempt -> the old review stays history."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    old_review = review(p, wid, disposition="changes_required",
                        findings=[{"id": "F1", "severity": "major", "summary": "from the old plan"}])
    replan(p, wid, tmp_path, 2)
    implement(assign(p, wid))  # identical bytes -> identical fingerprint
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    res = p.aew("review", "ingest", wid, "--evidence", old_review, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "GATE_UNSATISFIED" and {"plan", "workspace"} <= set(res.error["details"])
    u = unit(p, wid)
    assert u["state"] == "REVIEW_PENDING" and not u.get("findings")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    assert unit(p, wid)["state"] == "REVIEW_PASSED"
    assert_control_invariants(p)


def test_publication_refuses_a_validation_record_not_produced_for_the_candidate(tmp_path):
    """R1, publication boundary (defense in depth): a recorded validation must come from this candidate's
    own integration verifier, even when fingerprints match (simulated legacy state)."""
    from aew.engine.api import Engine
    from aew.engine.store import Transition

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    ticket_scope_report = next(e["id"] for e in unit(p, wid)["evidence"] if e["kind"] == "verification")
    engine = Engine.discover(p.root)
    with engine.store.session() as sess:
        sess.state["work"][wid]["integration"]["post_integration_evidence"] = ticket_scope_report
        sess.commit(Transition(op="test.legacy_state", actor={"kind": "test"}))
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] in {"GATE_UNSATISFIED"}, res.stderr
    assert main_commit(p) == integ["base"]
