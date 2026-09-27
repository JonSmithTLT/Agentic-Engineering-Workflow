"""M2 composition tests: hierarchy and non-mutating operations exercised in the sequences where the
operator review of the M2 plan (2026-09-27) found holes a per-operation test would miss.

Every scenario checks the cross-operation invariant oracle after each consequential step.
"""

from __future__ import annotations

from pathlib import Path

from aewflow import (APPLY_PATCH, Role, complete_investigation, create_investigation, create_planned_ticket,
                     create_unit, dispatch, integrate, parent_review, parent_verify, plan_unit, prepare_and_validate,
                     sample_project, submit_record, to_commit_ready, to_verified)
from conftest import git
from invariants import assert_control_invariants

from aew.util import parse_frontmatter


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def err(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def handoff(p):
    offer = p.lead("lead", "handoff", "offer")["offer"]
    p.token = p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))["token"]


def main_commit(p):
    return git("rev-parse", "refs/heads/main", cwd=p.root)


def test_an_ancestors_first_plan_acceptance_stales_every_descendant_plan(tmp_path):
    """Operator review #1: a plan bound to "no ancestor plan yet" is bound to exactly that. An ancestor's
    first acceptance may change the intent the descendant was planned under, so it fails closed too."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    story = create_unit(p, "story", "Objective", parent=epic)
    plan_unit(p, tmp_path, story, "Story plan v1.\n")
    waiting = create_investigation(p, tmp_path, parent=story)  # READY, bound to {story: v1, epic: none}
    inflight, _ = to_verified(p, tmp_path, extra=("--parent", story))  # mutating, VERIFIED
    looking = create_investigation(p, tmp_path, parent=story, title="In-flight look")
    dispatch(p, looking)  # non-mutating, RUNNING
    assert show(p, waiting)["plan"]["ancestor_plans"][epic] is None
    assert_control_invariants(p)

    plan_unit(p, tmp_path, epic, "Epic plan v1: the objective is narrowed.\n")  # the first Epic plan
    for wid in (story, waiting, inflight):
        gate = p.ok("gate", "show", wid)["gates"]["accepted_plan"]
        assert gate["status"] == "STALE" and epic in gate["detail"]["ancestors"], wid
    assert show(p, waiting)["state"] == "BLOCKED" and show(p, waiting)["blocked_by"][0]["kind"] == "plan_binding_stale"
    assert err(p, "work", "dispatch", waiting)["code"] == "ILLEGAL_TRANSITION"
    assert err(p, "work", "redispatch", looking, "--reason", "fresh look")["code"] == "GATE_UNSATISFIED"
    refused = err(p, "work", "transition", inflight, "--to", "COMMIT_READY")
    assert refused["code"] == "GATE_UNSATISFIED" and "accepted_plan" in str(refused["details"])
    assert_control_invariants(p)

    # Reconfirming the Story does not reconfirm its children: each binding is the Lead's explicit decision.
    p.lead("plan", "reconfirm", story, "--reason", "the Story still serves the narrowed objective")
    assert p.ok("gate", "show", waiting)["gates"]["accepted_plan"]["status"] == "STALE"
    p.lead("plan", "reconfirm", waiting, "--reason", "the investigation question is unchanged")
    p.lead("plan", "reconfirm", inflight, "--reason", "the change is still in scope")
    p.lead("plan", "reconfirm", looking, "--reason", "the question still stands")
    p.lead("work", "redispatch", looking, "--reason", "look again under the narrowed objective")
    assert show(p, waiting)["state"] == "READY"
    p.lead("work", "transition", inflight, "--to", "COMMIT_READY")
    assert_control_invariants(p)

    # Superseding the Story's plan stales its children again (the M1-style supersede case).
    plan_unit(p, tmp_path, story, "Story plan v2.\n", reason="scope refined")
    assert show(p, waiting)["state"] == "BLOCKED"
    assert err(p, "integrate", "prepare", inflight)["code"] == "GATE_UNSATISFIED"
    assert_control_invariants(p)


def test_redispatch_supersedes_the_attempt_and_everything_it_produced(tmp_path):
    """Operator review #2 (the M1 review lesson applied to observation work): an attempt owns one
    invocation, one credential and one observation; superseding it retires all three and its records."""
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    k1, first = dispatch(p, wid)
    e1 = submit_record(k1, "discovery_record")["evidence"]
    assert err(p, "invoke", "create", wid, "--card", "investigator")["code"] == "ILLEGAL_TRANSITION"  # one executor
    second = p.lead("work", "redispatch", wid, "--reason", "the first look skipped the tests")
    assert second["superseded"]["attempt"] == 1 and second["execution"]["attempt"] == 2
    assert p.ok("invoke", "show", first["invocation"])["status"] == "superseded"
    assert not Path(first["observation"]["path"]).exists()  # O1 removed
    straggler = Role(p, k1.token, p.root)
    assert submit_record(straggler, "discovery_record", expect_ok=False).error["code"] == "STALE_AUTHORITY"
    assert straggler.aew("check", "run", "unit").error["code"] == "STALE_AUTHORITY"
    replay = err(p, "evidence", "ingest", wid, "--evidence", e1)
    assert replay["code"] == "GATE_UNSATISFIED" and replay["details"]["attempt"]["current_attempt"] == 2
    assert p.ok("gate", "show", wid)["gates"]["execute_record"]["status"] == "MISSING"  # E1 satisfies nothing
    assert err(p, "work", "accept", wid)["code"] == "GATE_UNSATISFIED"
    assert_control_invariants(p)

    k2 = Role(p, second["invocation_token"], Path(second["observation"]["path"]))
    e2 = submit_record(k2, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", e2)
    assert_control_invariants(p)
    # An ingested record is superseded with its attempt, too.
    third = p.lead("work", "redispatch", wid, "--reason", "the record answered the wrong question")
    assert p.ok("gate", "show", wid)["gates"]["execute_record"]["status"] == "MISSING"
    for old in (e1, e2):
        assert err(p, "evidence", "ingest", wid, "--evidence", old)["code"] == "GATE_UNSATISFIED"
    k3 = Role(p, third["invocation_token"], Path(third["observation"]["path"]))
    e3 = submit_record(k3, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", e3)
    p.lead("work", "accept", wid)
    u = show(p, wid)
    assert u["state"] == "DONE" and u["execution"]["record"]["id"] == e3
    assert [h["attempt"] for h in u["execution_history"]] == [1, 2]
    meta, _ = parse_frontmatter((p.root / ".aew" / u["completion_record"]).read_text(encoding="utf-8"))
    assert meta["accepted_record"]["id"] == e3 and e1 not in meta["basis"] and e2 not in meta["basis"]
    assert [(a["attempt"], a["record"]) for a in meta["superseded_attempts"]] == [(1, None), (2, e2)]
    assert submit_record(Role(p, k3.token, p.root), "discovery_record", expect_ok=False).error["code"]         == "STALE_AUTHORITY"  # its observation is gone, and the credential ended with the attempt
    assert err(p, "evidence", "ingest", wid, "--evidence", e1)["code"] == "ILLEGAL_TRANSITION"
    assert_control_invariants(p)


def test_a_stale_source_bound_input_blocks_dispatch_until_refreshed_or_acknowledged(tmp_path):
    """Operator review #3: an accepted investigation satisfies the dependency edge, but a consumer is
    dispatched against the current source only with CURRENT inputs, or with the Lead's acknowledgement
    for exactly that authoritative commit. External research keeps UNKNOWN (external) semantics."""
    p = sample_project(tmp_path)
    survey = create_investigation(p, tmp_path, title="Survey calc")
    rec = complete_investigation(p, survey)
    research = create_investigation(p, tmp_path, title="pytest capability", card="researcher")
    complete_investigation(p, research, kind="research_record")
    implement_it = create_planned_ticket(p, tmp_path, title="Build on the survey",
                                         extra=("--depends-on", f"{survey}:evidence"))
    follow_up = create_investigation(p, tmp_path, title="Follow-up question",
                                     extra=("--depends-on", f"{survey}:evidence", "--depends-on", f"{research}:evidence"))
    assert show(p, implement_it)["state"] == "READY" and show(p, follow_up)["state"] == "READY"

    first, _ = to_commit_ready(p, tmp_path, title="Change calc first")
    integrate(p, first)  # calc/core.py changes under the survey's observed paths
    refused = err(p, "work", "assign", implement_it)
    assert refused["code"] == "INPUT_STALE"
    stale = refused["details"]["inputs"][0]
    assert stale["id"] == rec and stale["freshness"] == "STALE" and "calc/core.py" in stale["changed_paths"]
    assert show(p, implement_it)["state"] == "READY"  # the edge is satisfied; only the dispatch is refused
    assert err(p, "work", "dispatch", follow_up)["code"] == "INPUT_STALE"
    resume = p.ok("resume", "--json")  # a fresh session sees why, and what to do
    entry = next(w for w in resume["work"] if w["id"] == implement_it)
    assert [(i["id"], i["blocks_dispatch"]) for i in entry["inputs"]] == [(rec, True)]
    assert any(a.startswith(f"{implement_it}: input {rec} from {survey} is STALE") for a in resume["next_actions"])
    assert_control_invariants(p)

    ack = p.lead("work", "acknowledge-input", implement_it, "--input", rec, "--from", survey,
                 "--reason", "rechecked: add() is unchanged by the subtract change")
    assert ack["commit"] == main_commit(p)
    second, _ = to_commit_ready(p, tmp_path, title="Change calc again", files=APPLY_PATCH)
    integrate(p, second)  # the acknowledgement covered the previous commit only
    assert err(p, "work", "assign", implement_it)["code"] == "INPUT_STALE"
    ack2 = p.lead("work", "acknowledge-input", implement_it, "--input", rec, "--from", survey,
                  "--reason", "rechecked again after apply() landed")
    out = p.lead("work", "assign", implement_it)
    pinned = p.ok("invoke", "show", out["invocation"])["inputs"]
    assert [(i["id"], i["freshness"], i["acknowledgement"]) for i in pinned] == [(rec, "STALE", ack2["decision"])]
    assert_control_invariants(p)

    # Refresh instead of acknowledging: a new CURRENT survey replaces the stale one on the edge.
    resurvey = create_investigation(p, tmp_path, title="Survey calc again")
    fresh = complete_investigation(p, resurvey)
    p.lead("work", "depend", follow_up, "--remove", survey, "--reason", "superseded by the new survey")
    p.lead("work", "depend", follow_up, "--add", f"{resurvey}:evidence", "--reason", "current survey")
    _, dispatched = dispatch(p, follow_up)
    inputs = p.ok("invoke", "show", dispatched["invocation"])["inputs"]
    assert sorted((i["id"], i["freshness"], i["basis"]) for i in inputs) == sorted(
        [(fresh, "CURRENT", "authoritative-source"), (p.ok("work", "show", research)["control"]["execution"]["record"]["id"],
                                         "UNKNOWN", "external")])
    assert_control_invariants(p)


def test_a_records_own_freshness_gates_its_acceptance(tmp_path):
    """A discovery ingested before an integration changed its observed paths is STALE at accept time;
    the Lead refreshes it with a new attempt (nothing is silently accepted)."""
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, _ = dispatch(p, wid)
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
    other, _ = to_commit_ready(p, tmp_path, title="Concurrent mutating work")
    integrate(p, other)
    assert p.ok("gate", "show", wid)["gates"]["execute_record"]["status"] == "STALE"
    assert err(p, "work", "accept", wid)["code"] == "GATE_UNSATISFIED"
    again = p.lead("work", "redispatch", wid, "--reason", "calc changed under the survey")
    assert again["observation"]["commit"] == main_commit(p)
    fresh = Role(p, again["invocation_token"], Path(again["observation"]["path"]))
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(fresh, "discovery_record")["evidence"])
    p.lead("work", "accept", wid)
    assert show(p, wid)["state"] == "DONE"
    assert_control_invariants(p)


def test_handoff_ends_a_read_only_attempt_and_success_is_never_inferred(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    k1, first = dispatch(p, wid)
    e1 = submit_record(k1, "discovery_record")["evidence"]  # submitted, never ingested
    story = create_unit(p, "story", "Objective", cls=1)
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    reviewer = p.lead("invoke", "create", story, "--role", "reviewer")["invocation"]
    handoff(p)  # nothing carried
    u = show(p, wid)
    assert u["state"] == "INTERRUPTED" and u["interrupted_from"] == "RUNNING"
    assert p.ok("invoke", "show", first["invocation"])["status"] == "interrupted"
    assert submit_record(Role(p, k1.token, p.root), "discovery_record", expect_ok=False).error["code"] \
        == "STALE_AUTHORITY"
    # A parent's phase is derived: losing its reviewer leaves the review gate missing, nothing more.
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"
    assert p.ok("invoke", "show", reviewer)["status"] == "interrupted"
    assert_control_invariants(p)

    assert err(p, "evidence", "ingest", wid, "--evidence", e1)["code"] == "ILLEGAL_TRANSITION"
    rec = p.lead("work", "reconcile", wid, "--to", "RUNNING", "--reason", "observation inspected: one record submitted")
    assert rec["inspection"]["attempt"] == 1 and rec["inspection"]["records_submitted"] == [e1]
    assert err(p, "evidence", "ingest", wid, "--evidence", e1)["code"] == "GATE_UNSATISFIED"  # the attempt ended
    assert err(p, "work", "accept", wid)["code"] == "GATE_UNSATISFIED"
    again = p.lead("work", "redispatch", wid, "--reason", "continue after the handoff")
    k2 = Role(p, again["invocation_token"], Path(again["observation"]["path"]))
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(k2, "discovery_record")["evidence"])
    p.lead("work", "accept", wid)
    p.lead("review", "ingest", story, "--evidence", parent_review(p, story))
    p.lead("verify", "ingest", story, "--evidence", parent_verify(p, story))
    p.lead("work", "close", story, "--reason", "gates passed after the handoff")
    assert [show(p, w)["state"] for w in (wid, story)] == ["DONE", "DONE"]
    assert_control_invariants(p)


def test_a_moved_done_child_is_reviewed_with_its_own_integrated_change(tmp_path):
    """Operator review #4: parent review covers every child's output, including a child integrated
    before the parent's baseline, and a change of the child set makes earlier parent reviews STALE."""
    p = sample_project(tmp_path)
    early, _ = to_commit_ready(p, tmp_path, title="Early subtract")
    integrated = integrate(p, early)["integrated_commit"]
    story = create_unit(p, "story", "Arithmetic", cls=1)
    plan_unit(p, tmp_path, story)
    assert show(p, story)["baseline_commit"] == integrated  # the early child predates the baseline
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    p.lead("review", "ingest", story, "--evidence", parent_review(p, story))
    assert p.ok("gate", "show", story)["gates"]["review_r1"]["status"] == "CURRENT"
    p.lead("work", "move", early, "--parent", story, "--reason", "the subtract work belongs to this objective")
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"
    assert p.ok("gate", "show", story)["gates"]["review_r1"]["status"] == "STALE"  # the child set changed
    out = p.lead("invoke", "create", story, "--role", "reviewer")
    pack = (p.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert f"### {early} — its own integrated change (`{integrated}`)" in pack
    assert "+def subtract(a, b):" in pack and "integrated before this parent's baseline" in pack
    assert "supplementary context only" in pack
    assert_control_invariants(p)


def test_parent_cancellation_waits_for_an_in_progress_publish(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    wid, _ = to_commit_ready(p, tmp_path, extra=("--parent", story))
    prepare_and_validate(p, wid)
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()),
                env={"AEW_FAULT": "integrate.after_publishing_record"})
    assert res.returncode == 86
    refused = err(p, "work", "cancel", story, "--reason", "objective dropped")
    assert refused["code"] == "ILLEGAL_TRANSITION" and refused["details"]["publishing"] == [wid]
    assert_control_invariants(p)
    p.lead("integrate", "reconcile", wid)
    p.lead("work", "cancel", story, "--reason", "objective dropped after the publish completed")
    assert [show(p, w)["state"] for w in (story, wid)] == ["CANCELLED", "DONE"]  # DONE children stay DONE
    assert_control_invariants(p)


def test_the_m2_oracle_rules_are_not_vacuous(tmp_path):
    """Each M2 oracle rule fires on a state that breaks it (corrupted copies of a real state; nothing is
    committed), so a green composition or walk means the rules held, not that they cannot fail."""
    import copy

    from aew.engine.api import Engine
    from invariants import m2_violations

    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=0)
    survey = create_investigation(p, tmp_path, parent=story, cls=0)
    complete_investigation(p, survey)
    consumer = create_investigation(p, tmp_path, parent=story, cls=0, title="Consumer",
                                    extra=("--depends-on", f"{survey}:evidence"))
    _, out = dispatch(p, consumer)
    state = Engine.discover(p.root).store.read()
    assert m2_violations(p.root, state) == []

    def broken(mutate):
        s = copy.deepcopy(state)
        mutate(s)
        return " | ".join(m2_violations(p.root, s))

    closed = broken(lambda s: s["work"][story].update(state="DONE", closeout={"decision": "DEC-X"}))
    assert "open descendants" in closed and "invocations below it are active" in closed  # rule 7
    assert "holds a workspace/integration/implementer" in broken(
        lambda s: s["work"][consumer].update(implementer_invocation="INV-9999"))  # rule 8
    assert "current attempt is 7" in broken(lambda s: s["work"][consumer]["execution"].update(attempt=7))  # rule 9
    assert "not the pinned output" in broken(
        lambda s: s["work"][survey]["execution"].update(expected_kind="research_record"))  # rule 10
    assert "without an acknowledgement" in broken(
        lambda s: s["invocations"][out["invocation"]]["inputs"][0].update(freshness="STALE"))  # rule 13
    assert "still marked active" in broken(
        lambda s: s["invocations"][out["invocation"]].update(status="cancelled"))  # rule 12
