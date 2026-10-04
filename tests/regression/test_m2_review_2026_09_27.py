"""Probes from the independent M2 review (2026-09-27), preserved as regressions.

Provenance: the M2 review report ("AEW Milestone 2 review", reviewed branch ``impl/m2-hierarchy`` at
``9553cb7``) and its probe script ``M2_independent_probe.py``. The script itself was not available in
this repository, so each probe below is reconstructed from the report's sequence table. Like the
original, each one runs the reported sequence through the public CLI and asserts the SAFE outcome. It
does not assume which step refuses: every step is attempted, and the probe fails only if the unsafe end
state is reached. They were imported as strict xfails, and the commit fixing each finding removed its
markers (see docs/implementation/review-response-2026-09-27.md).
"""

from __future__ import annotations

from pathlib import Path

from aewflow import (
    DISCOVERY,
    Role,
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    implement,
    parent_verify,
    plan_unit,
    prepare_and_validate,
    sample_project,
    submit_record,
    to_commit_ready,
)
from conftest import git


def unit(p, wid):
    return p.ok("work", "show", wid)["control"]


def attempt(p, *args):
    """A Lead step whose refusal is an acceptable (safe) outcome; returns the CLI result."""
    return p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))


def main_commit(p):
    return git("rev-parse", "refs/heads/main", cwd=p.root)


# ------------------------------------------------------------------ Blocker 1: class 0 work under a stale ancestor plan


def test_class0_nonmutating_completion_requires_reconfirmation_after_an_ancestor_plan(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid = create_investigation(p, tmp_path, parent=story, cls=0)  # bound to {story: none}
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    plan_unit(p, tmp_path, story, "Story plan v1: the objective is narrowed.\n")  # the Story's first plan
    assert attempt(p, "work", "redispatch", wid, "--reason", "look again").error["code"] == "GATE_UNSATISFIED"
    attempt(p, "evidence", "ingest", wid, "--evidence", rec)
    attempt(p, "work", "accept", wid)
    assert unit(p, wid)["state"] != "DONE", "class 0 record accepted under a stale ancestor plan binding"


def test_class0_mutating_commit_ready_requires_reconfirmation_after_an_ancestor_plan(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid = create_planned_ticket(p, tmp_path, cls=0, extra=("--parent", story))
    implement(assign(p, wid))
    plan_unit(p, tmp_path, story, "Story plan v1: the objective is narrowed.\n")
    attempt(p, "work", "transition", wid, "--to", "COMMIT_READY")
    assert unit(p, wid)["state"] != "COMMIT_READY", "class 0 COMMIT_READY under a stale ancestor plan binding"


def test_class0_mutating_publication_requires_reconfirmation_after_an_ancestor_plan(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid = create_planned_ticket(p, tmp_path, cls=0, extra=("--parent", story))
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    prepare_and_validate(p, wid)
    before = main_commit(p)
    plan_unit(p, tmp_path, story, "Story plan v1: the objective is narrowed.\n")
    attempt(p, "integrate", "publish", wid)
    assert unit(p, wid)["state"] != "DONE" and main_commit(p) == before, \
        "class 0 candidate published to DONE under a stale ancestor plan binding"


def test_class0_mutating_prepare_requires_reconfirmation_after_an_ancestor_plan(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid = create_planned_ticket(p, tmp_path, cls=0, extra=("--parent", story))
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    plan_unit(p, tmp_path, story, "Story plan v1: the objective is narrowed.\n")
    attempt(p, "integrate", "prepare", wid)
    assert unit(p, wid).get("integration") is None, "class 0 integration prepared under a stale ancestor plan"


# ---------------------------------------------------- Blocker 2: moving started work past inherited dependencies


def test_moved_running_ticket_cannot_finish_before_its_inherited_prerequisite(tmp_path):
    p = sample_project(tmp_path)
    prereq = create_investigation(p, tmp_path, title="Prerequisite survey")  # READY, never finished
    story = create_unit(p, "story", "Objective", cls=1, extra=("--depends-on", f"{prereq}:evidence"))
    wid = create_investigation(p, tmp_path, title="Started elsewhere")
    role, _ = dispatch(p, wid)  # RUNNING, dispatched without the prerequisite
    attempt(p, "work", "move", wid, "--parent", story, "--reason", "belongs to the objective")
    attempt(p, "plan", "reconfirm", wid, "--reason", "still the same question")
    rec = submit_record(role, "discovery_record", expect_ok=False)
    if rec.returncode == 0:
        attempt(p, "evidence", "ingest", wid, "--evidence", rec.json["evidence"])
    attempt(p, "work", "accept", wid)
    moved = unit(p, wid)
    assert not (moved["state"] == "DONE" and moved["parent"] == story and unit(p, prereq)["state"] != "DONE"), \
        "a moved Ticket completed before its inherited prerequisite"


def test_moved_mutating_ticket_cannot_publish_before_its_inherited_mutating_upstream(tmp_path):
    p = sample_project(tmp_path)
    upstream = create_planned_ticket(p, tmp_path, title="Upstream change")  # READY, never integrated
    story = create_unit(p, "story", "Objective", cls=1, extra=("--depends-on", f"{upstream}:mutating"))
    wid, _ = to_commit_ready(p, tmp_path, title="Downstream change")
    attempt(p, "work", "move", wid, "--parent", story, "--reason", "belongs to the objective")
    attempt(p, "plan", "reconfirm", wid, "--reason", "still in scope")
    if attempt(p, "integrate", "prepare", wid).returncode == 0:
        out = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
        integ = unit(p, wid)["integration"]
        ver = Role(p, out["invocation_token"], Path(integ["workspace"]))
        ev = ver.check("unit")["evidence"]
        rep = ver.submit("verification", {"claim": "integrated", "verification": {"scope": "integration", "claims": [
            {"type": "goal_backwards", "claim": "tests pass", "result": "pass", "checks": [ev]}]}}, expect_ok=False)
        if rep.returncode == 0:
            attempt(p, "verify", "ingest", wid, "--evidence", rep.json["evidence"])
        attempt(p, "integrate", "publish", wid)
    moved = unit(p, wid)
    assert not (moved["state"] == "DONE" and moved["parent"] == story and unit(p, upstream)["state"] != "DONE"), \
        "a moved mutating Ticket published before its inherited mutating upstream integrated"


# ------------------------------------------------------------------ Major 1: late parent edge, then closeout


def test_parent_cannot_close_with_a_dependency_added_after_its_child_finished(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    late = create_investigation(p, tmp_path, title="Unfinished prerequisite")
    attempt(p, "work", "depend", story, "--add", f"{late}:evidence", "--reason", "found late")
    out = p.lead("invoke", "create", story, "--role", "reviewer")
    rev = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    ev = rev.submit("review", {"claim": "ok", "review": {"independence": "R1", "disposition": "pass",
                                                          "findings": [], "resolved_findings": []}})["evidence"]
    p.lead("review", "ingest", story, "--evidence", ev)
    p.lead("verify", "ingest", story, "--evidence", parent_verify(p, story))
    attempt(p, "work", "close", story, "--reason", "gates passed")
    closed = unit(p, story)
    assert not (closed["state"] == "DONE" and late in [e["id"] for e in closed["depends_on"]]
                and unit(p, late)["state"] != "DONE"), "a parent closed with an unsatisfied dependency"


# ---------------------------------------------------- Major 2: observation mutated between submit and ingest


def test_observation_mutated_after_submission_is_refused_at_ingest(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record", DISCOVERY)["evidence"]
    (role.workspace / "calc/core.py").write_text("tampered after submission\n", encoding="utf-8", newline="\n")
    res = attempt(p, "evidence", "ingest", wid, "--evidence", rec)
    assert res.returncode != 0 and res.error["code"] == "OBSERVATION_MUTATED", res.stdout or res.stderr


def test_record_reviewer_observation_mutated_after_submission_is_refused_at_ingest(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path, cls=2)
    p.lead("work", "staff", wid, "--review", "code_reviewer")
    role, _ = dispatch(p, wid)
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    rv = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    reviewer = Role(p, rv["invocation_token"], Path(rv["observation"]["path"]))
    ev = reviewer.submit("review", {"claim": "facts are supported", "review": {
        "independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}})["evidence"]
    (reviewer.workspace / "calc/core.py").write_text("tampered after review\n", encoding="utf-8", newline="\n")
    res = attempt(p, "review", "ingest", wid, "--evidence", ev)
    assert res.returncode != 0 and res.error["code"] == "OBSERVATION_MUTATED", res.stdout or res.stderr


def test_parent_reviewer_observation_mutated_after_submission_is_refused_at_ingest(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    out = p.lead("invoke", "create", story, "--role", "reviewer")
    rev = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    ev = rev.submit("review", {"claim": "ok", "review": {"independence": "R1", "disposition": "pass",
                                                          "findings": [], "resolved_findings": []}})["evidence"]
    (rev.workspace / "calc/core.py").write_text("tampered after review\n", encoding="utf-8", newline="\n")
    res = attempt(p, "review", "ingest", story, "--evidence", ev)
    assert res.returncode != 0 and res.error["code"] == "OBSERVATION_MUTATED", res.stdout or res.stderr


# ------------------------------------------------------------------ Re-review of 0552116 (M2_followup_probe.py)
# The follow-up probes, with the reviewer's bodies and this repository's imports. The three early-refusal
# probes confirm that the fixes refuse at the move or edge edit and leave the structure unchanged.


def _cap_nonmutating_concurrency(p, cap):
    from aew.util import dump_yaml, load_yaml

    policy = p.root / ".aew/policy/gates.yaml"
    gates = load_yaml(policy.read_text(encoding="utf-8"), source="gates")
    gates["non_mutating_concurrency"] = cap
    policy.write_text(dump_yaml(gates), encoding="utf-8")


def test_redispatch_respects_nonmutating_concurrency_after_ingest(tmp_path):
    """Re-review Major: with a cap of one, A's record ingested (its executor ended), B dispatched, then A
    redispatched. Redispatch skipped the cap check and left two active executors."""
    p = sample_project(tmp_path)
    _cap_nonmutating_concurrency(p, 1)
    first = create_investigation(p, tmp_path, title="First")
    second = create_investigation(p, tmp_path, title="Second")
    role, _ = dispatch(p, first)
    record = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", first, "--evidence", record)
    dispatch(p, second)
    result = attempt(p, "work", "redispatch", first, "--reason", "refresh first record")
    assert result.returncode != 0, "redispatch exceeded the configured concurrency cap: " + result.stdout
    assert result.error["code"] == "CONCURRENCY_LIMIT", result.stderr
    assert unit(p, first)["execution"]["record"]["id"] == record  # the refused redispatch changed nothing


def test_redispatch_replacing_active_attempt_stays_within_cap(tmp_path):
    """Control: a redispatch that replaces its own active executor is within a cap of one."""
    p = sample_project(tmp_path)
    _cap_nonmutating_concurrency(p, 1)
    child = create_investigation(p, tmp_path)
    _, first = dispatch(p, child)
    second = p.lead("work", "redispatch", child, "--reason", "refresh")
    assert second["execution"]["attempt"] == 2
    assert p.ok("invoke", "show", first["invocation"])["status"] == "superseded"
    assert p.ok("invoke", "show", second["invocation"])["status"] == "active"


def test_started_nonmutating_move_refusal_preserves_parent(tmp_path):
    p = sample_project(tmp_path)
    upstream = create_investigation(p, tmp_path, title="Unfinished upstream")
    parent = create_unit(p, "story", "Depends on upstream", cls=0)
    p.lead("work", "depend", parent, "--add", f"{upstream}:evidence", "--reason", "upstream required")
    child = create_investigation(p, tmp_path, title="Consumer")
    dispatch(p, child)
    result = attempt(p, "work", "move", child, "--parent", parent, "--reason", "join scope")
    assert result.error["code"] == "ILLEGAL_TRANSITION"
    assert unit(p, child)["parent"] is None


def test_finished_child_blocks_late_parent_dependency_edit(tmp_path):
    p = sample_project(tmp_path)
    parent = create_unit(p, "story", "Dependent parent", cls=0)
    child = create_investigation(p, tmp_path, parent=parent, cls=0)
    complete_investigation(p, child)
    upstream = create_investigation(p, tmp_path, title="Unfinished prerequisite")
    result = attempt(p, "work", "depend", parent, "--add", f"{upstream}:evidence", "--reason", "late")
    assert result.error["code"] == "ILLEGAL_TRANSITION"
    assert unit(p, parent)["depends_on"] == []


def test_started_mutating_move_refusal_preserves_parent(tmp_path):
    p = sample_project(tmp_path)
    upstream = create_planned_ticket(p, tmp_path, title="Upstream mutation", cls=0)
    parent = create_unit(p, "story", "Waits for upstream", cls=0)
    p.lead("work", "depend", parent, "--add", f"{upstream}:mutating", "--reason", "needs integrated upstream")
    child = create_planned_ticket(p, tmp_path, title="Consumer mutation", cls=0)
    assign(p, child)
    result = attempt(p, "work", "move", child, "--parent", parent, "--reason", "scope expanded")
    assert result.error["code"] == "ILLEGAL_TRANSITION"
    assert unit(p, child)["parent"] is None


def test_parent_acceptance_evidence_waits_for_its_dependency_output(tmp_path):
    """Re-review contract question (M2_followup_probe.py line 13), decided by the operator: parent review and
    verification are downstream assignments of the parent's dependencies (WC §8). The reviewer's sequence is
    attempted step by step; the safe end state is that the parent never closes on acceptance reports that were
    dispatched before its prerequisite was accepted."""
    p = sample_project(tmp_path)
    prerequisite = create_investigation(p, tmp_path, title="Prerequisite survey", cls=0)
    parent = create_unit(p, "story", "Dependent objective", cls=1, extra=("--depends-on", f"{prerequisite}:evidence"))
    plan_unit(p, tmp_path, parent)
    child = create_investigation(p, tmp_path, title="Completed child", cls=0)
    complete_investigation(p, child)
    p.lead("work", "move", child, "--parent", parent, "--reason", "accept this result")
    early = []
    for role in ("reviewer", "verifier"):
        out = attempt(p, "invoke", "create", parent, "--role", role)
        if out.returncode == 0:  # the unfixed engine dispatched it: produce and ingest the early report
            actor = Role(p, out.json["invocation_token"], Path(out.json["observation"]["path"]))
            if role == "reviewer":
                ev = actor.submit("review", {"claim": "early", "review": {"independence": "R1", "disposition": "pass",
                                                                         "findings": [], "resolved_findings": []}})
            else:
                check = actor.check("unit")["evidence"]
                ev = actor.submit("verification", {"claim": "early", "verification": {"scope": "parent", "claims": [
                    {"type": "goal_backwards", "claim": "met", "result": "pass", "checks": [check]},
                    {"type": "contract", "claim": "held", "result": "pass", "checks": [check]}]}})
            early.append(attempt(p, "review" if role == "reviewer" else "verify", "ingest", parent, "--evidence",
                                 ev["evidence"]))
        else:
            assert out.error["code"] == "DEPENDENCY_UNSATISFIED", out.stderr
    assert attempt(p, "work", "close", parent, "--reason", "gates passed").returncode != 0
    complete_investigation(p, prerequisite)
    attempt(p, "work", "close", parent, "--reason", "prerequisite finished")
    assert unit(p, parent)["state"] != "DONE", "parent closed on reports that predate its prerequisite output"
