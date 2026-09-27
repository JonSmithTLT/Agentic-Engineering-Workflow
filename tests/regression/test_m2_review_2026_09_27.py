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

import pytest

from aewflow import (DISCOVERY, Role, complete_investigation, create_investigation, create_planned_ticket,
                     create_unit, dispatch, implement, assign, parent_verify, plan_unit, prepare_and_validate,
                     sample_project, submit_record, to_commit_ready)
from conftest import git


# Open findings (strict: an unexpected pass fails the run, so each fix commit removes its own markers).
B1 = pytest.mark.xfail(strict=True, reason="M2 review blocker 1: class 0 work bypasses stale ancestor plans")
B2 = pytest.mark.xfail(strict=True, reason="M2 review blocker 2: moving active work bypasses inherited dependencies")
MA1 = pytest.mark.xfail(strict=True, reason="M2 review major 1: a parent can close with an unsatisfied dependency")
MA2 = pytest.mark.xfail(strict=True, reason="M2 review major 2: observation mutation after submission lost at ingest")


def unit(p, wid):
    return p.ok("work", "show", wid)["control"]


def attempt(p, *args):
    """A Lead step whose refusal is an acceptable (safe) outcome; returns the CLI result."""
    return p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))


def main_commit(p):
    return git("rev-parse", "refs/heads/main", cwd=p.root)


# ------------------------------------------------------------------ Blocker 1: class 0 work under a stale ancestor plan


@B1
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


@B1
def test_class0_mutating_commit_ready_requires_reconfirmation_after_an_ancestor_plan(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid = create_planned_ticket(p, tmp_path, cls=0, extra=("--parent", story))
    implement(assign(p, wid))
    plan_unit(p, tmp_path, story, "Story plan v1: the objective is narrowed.\n")
    attempt(p, "work", "transition", wid, "--to", "COMMIT_READY")
    assert unit(p, wid)["state"] != "COMMIT_READY", "class 0 COMMIT_READY under a stale ancestor plan binding"


@B1
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


@B1
def test_class0_mutating_prepare_requires_reconfirmation_after_an_ancestor_plan(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid = create_planned_ticket(p, tmp_path, cls=0, extra=("--parent", story))
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    plan_unit(p, tmp_path, story, "Story plan v1: the objective is narrowed.\n")
    attempt(p, "integrate", "prepare", wid)
    assert unit(p, wid).get("integration") is None, "class 0 integration prepared under a stale ancestor plan"


# ------------------------------------------------------------------ Blocker 2: moving started work past inherited dependencies


@B2
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
    assert not (unit(p, wid)["state"] == "DONE" and unit(p, prereq)["state"] != "DONE"), \
        "a moved Ticket completed before its inherited prerequisite"


@B2
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
    assert not (unit(p, wid)["state"] == "DONE" and unit(p, upstream)["state"] != "DONE"), \
        "a moved mutating Ticket published before its inherited mutating upstream integrated"


# ------------------------------------------------------------------ Major 1: late parent edge, then closeout


@MA1
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
    assert not (unit(p, story)["state"] == "DONE" and unit(p, late)["state"] != "DONE"), \
        "a parent closed with an unsatisfied dependency"


# ------------------------------------------------------------------ Major 2: observation mutated between submit and ingest


@MA2
def test_observation_mutated_after_submission_is_refused_at_ingest(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record", DISCOVERY)["evidence"]
    (role.workspace / "calc/core.py").write_text("tampered after submission\n", encoding="utf-8", newline="\n")
    res = attempt(p, "evidence", "ingest", wid, "--evidence", rec)
    assert res.returncode != 0 and res.error["code"] == "OBSERVATION_MUTATED", res.stdout or res.stderr


@MA2
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


@MA2
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
