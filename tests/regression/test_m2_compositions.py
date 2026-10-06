"""M2 composition tests: hierarchy and non-mutating operations exercised in the sequences where the
operator review of the M2 plan (2026-09-27) found holes a per-operation test would miss.

Every scenario checks the cross-operation invariant oracle after each consequential step.
"""

from __future__ import annotations

from pathlib import Path

from aewflow import (
    APPLY_PATCH,
    Role,
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    implement,
    integrate,
    parent_review,
    parent_verify,
    plan_unit,
    prepare_and_validate,
    sample_project,
    submit_record,
    to_commit_ready,
    to_verified,
)
from conftest import git
from invariants import assert_control_invariants

from aew.util import dump_yaml, load_yaml, parse_frontmatter


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


def test_a_class0_plan_is_bound_to_its_ancestors_although_its_path_lists_no_plan_gate(tmp_path):
    """M2 review B1: class 0 paths do not list ``accepted_plan``, but a class 0 unit's accepted plan is bound to
    its ancestors' plans all the same. Record acceptance, publication and closeout refuse a stale binding, and
    the Lead's reconfirmation of each unit is what lets it finish."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative", cls=0)
    story = create_unit(p, "story", "Objective", cls=0, parent=epic)
    plan_unit(p, tmp_path, story)
    look = create_investigation(p, tmp_path, parent=story, cls=0)
    change = create_planned_ticket(p, tmp_path, cls=0, extra=("--parent", story))
    role, _ = dispatch(p, look)
    p.lead("evidence", "ingest", look, "--evidence", submit_record(role, "discovery_record")["evidence"])
    implement(assign(p, change))
    p.lead("work", "transition", change, "--to", "COMMIT_READY")
    prepare_and_validate(p, change)
    before = main_commit(p)
    plan_unit(p, tmp_path, epic, "Epic plan v1: the initiative is narrowed.\n")  # the Epic's first plan
    for wid in (look, change):
        gates = p.ok("gate", "show", wid)
        assert "accepted_plan" not in gates["obligations"]["gates"]  # class 0 path
        assert gates["unmet"] == {"accepted_plan": "STALE"} and epic in gates["plan_binding"]["ancestors"], wid
    refused = err(p, "work", "accept", look)
    assert refused["code"] == "GATE_UNSATISFIED" and epic in refused["details"]["plan_binding"]["ancestors"]
    assert err(p, "integrate", "publish", change)["code"] == "GATE_UNSATISFIED"
    assert main_commit(p) == before and show(p, change)["integration"]["status"] == "validated"
    assert any(a.startswith(f"{look}: an ancestor's plan changed") for a in p.ok("resume", "--json")["next_actions"])
    assert_control_invariants(p)

    p.lead("plan", "reconfirm", look, "--reason", "the question still serves the narrowed initiative")
    p.lead("plan", "reconfirm", change, "--reason", "the change is still in scope")
    p.lead("work", "accept", look)
    p.lead("integrate", "publish", change)
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"
    closing = err(p, "work", "close", story, "--reason", "children done")  # the Story's own plan is stale too
    assert closing["code"] == "GATE_UNSATISFIED" and "plan_binding" in closing["details"]
    p.lead("plan", "reconfirm", story, "--reason", "the objective still serves the initiative")
    p.lead("work", "close", story, "--reason", "children done")
    assert [show(p, w)["state"] for w in (look, change, story)] == ["DONE", "DONE", "DONE"]
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
    # Its observation is gone, and the credential ended with the attempt.
    late = submit_record(Role(p, k3.token, p.root), "discovery_record", expect_ok=False)
    assert late.error["code"] == "STALE_AUTHORITY"
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
                                     extra=("--depends-on", f"{survey}:evidence",
                                            "--depends-on", f"{research}:evidence"))
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
        [(fresh, "CURRENT", "authoritative-source"),
         (p.ok("work", "show", research)["control"]["execution"]["record"]["id"], "UNKNOWN", "external")])
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

    from invariants import cap_violations, m2_violations, with_cold

    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=0)
    survey = create_investigation(p, tmp_path, parent=story, cls=0)
    complete_investigation(p, survey)
    consumer = create_investigation(p, tmp_path, parent=story, cls=0, title="Consumer",
                                    extra=("--depends-on", f"{survey}:evidence"))
    _, out = dispatch(p, consumer)
    state = Engine.discover(p.root).store.read()
    assert m2_violations(p.root, state) == []

    state, _ = with_cold(p.root, state)  # archived units corrupt as well (ADR-0011: the oracle reads both)

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
    assert "was dispatched with dependencies" in broken(
        lambda s: s["work"][consumer]["execution"].update(dependencies=[]))  # rule 14
    assert "not satisfied in the source" in broken(lambda s: s["work"][survey].update(state="READY"))  # rule 14
    gates = p.root / ".aew/policy/gates.yaml"
    policy = load_yaml(gates.read_text(encoding="utf-8"), source="gates")
    gates.write_text(dump_yaml({**policy, "non_mutating_concurrency": 1}), encoding="utf-8", newline="\n")
    p.pin_policy()
    assert cap_violations(p.root, state) == []  # one active executor is within a cap of one
    over = copy.deepcopy(state)
    over["invocations"]["INV-9999"] = dict(over["invocations"][out["invocation"]], work_unit=survey)
    assert "the policy cap is 1" in " | ".join(cap_violations(p.root, over))  # the cap check the walks use


def test_moving_started_work_under_new_dependencies_needs_a_new_dispatch(tmp_path):
    """M2 review B2: re-parenting changes inherited edges, i.e. edits the dependencies of everything moved. For a
    started attempt that is refused, as `work depend` is (ADR-0007); after a replan, the next dispatch waits for
    the inherited prerequisite and consumes its record. A move that leaves dependencies alone is still allowed."""
    p = sample_project(tmp_path)
    prereq = create_investigation(p, tmp_path, title="Prerequisite survey")
    story = create_unit(p, "story", "Objective", cls=1, extra=("--depends-on", f"{prereq}:evidence"))
    plain = create_unit(p, "story", "Holding area", cls=1)
    look = create_investigation(p, tmp_path, title="Started elsewhere")
    role, first = dispatch(p, look)
    refused = err(p, "work", "move", look, "--parent", story, "--reason", "belongs to the objective")
    assert refused["code"] == "ILLEGAL_TRANSITION" and refused["details"]["in_progress"] == [look]
    assert refused["details"]["dependencies"][look] == {"before": [], "after": [f"{prereq}:evidence"]}
    assert show(p, look)["parent"] is None
    p.lead("work", "move", look, "--parent", plain, "--reason", "same dependencies, new home")  # still allowed
    p.lead("plan", "reconfirm", look, "--reason", "same question")
    assert_control_invariants(p)

    p.lead("work", "transition", look, "--to", "REPLAN_REQUIRED", "--reason", "moving under the objective")
    p.lead("work", "move", look, "--parent", story, "--reason", "belongs to the objective")
    plan_unit(p, tmp_path, look, "Same question, now under the objective.\n", reason="moved under the objective")
    u = show(p, look)
    assert u["state"] == "BLOCKED" and u["blocked_by"] == [
        {"kind": "dependency", "id": prereq, "reason": "evidence_not_accepted (READY)", "inherited_from": story}]
    assert p.ok("invoke", "show", first["invocation"])["status"] == "cancelled"  # the old attempt ended
    assert submit_record(role, "discovery_record", expect_ok=False).returncode != 0
    assert_control_invariants(p)

    rec = complete_investigation(p, prereq)
    assert show(p, look)["state"] == "READY"
    _, out = dispatch(p, look)
    assert [(i["id"], i["from"], i["declared_on"]) for i in p.ok("invoke", "show", out["invocation"])["inputs"]] \
        == [(rec, prereq, story)]
    assert show(p, look)["execution"]["dependencies"] == [{"id": prereq, "kind": "evidence"}]
    assert_control_invariants(p)


def test_a_moved_mutating_ticket_is_reassigned_on_a_base_holding_its_inherited_upstream(tmp_path):
    """M2 review B2, M1 rule: a mutating dependent never publishes before its mutating upstream is integrated,
    also when the dependency arrives by a move. The replan releases its workspace (and candidate); the new
    assignment's base contains the upstream's integrated commit."""
    p = sample_project(tmp_path)
    upstream = create_planned_ticket(p, tmp_path, title="Upstream change")
    story = create_unit(p, "story", "Objective", cls=1, extra=("--depends-on", f"{upstream}:mutating"))
    wid, _ = to_commit_ready(p, tmp_path, title="Downstream change", files=APPLY_PATCH)
    prepare_and_validate(p, wid)
    refused = err(p, "work", "move", wid, "--parent", story, "--reason", "belongs to the objective")
    assert refused["code"] == "ILLEGAL_TRANSITION" and refused["details"]["in_progress"] == [wid]
    p.lead("work", "transition", wid, "--to", "REPLAN_REQUIRED", "--reason", "moving under the objective")
    assert show(p, wid)["integration"] is None  # the candidate retired with COMMIT_READY
    p.lead("work", "move", wid, "--parent", story, "--reason", "belongs to the objective")
    plan_unit(p, tmp_path, wid, "Same change, after the upstream.\n", reason="moved under the objective")
    assert show(p, wid)["state"] == "BLOCKED" and show(p, wid)["blocked_by"][0]["inherited_from"] == story
    integrated = integrate(p, to_commit_ready(p, tmp_path, wid=upstream)[0])["integrated_commit"]
    assert show(p, wid)["state"] == "READY"
    ws = p.lead("work", "assign", wid)["workspace"]
    assert git("merge-base", "--is-ancestor", integrated, ws["base_commit"], cwd=p.root) == ""
    assert show(p, wid)["workspace"]["dependencies"] == [{"id": upstream, "kind": "mutating"}]
    assert_control_invariants(p)


def test_promotion_may_not_change_the_dependencies_of_started_descendants(tmp_path):
    """Promotion moves the unit too. A promoted Ticket is replanned in the same commit, so its own edges may
    change; a promoted Story's started descendants are not replanned, so a change of theirs is refused."""
    p = sample_project(tmp_path)
    x = create_investigation(p, tmp_path, title="Epic prerequisite")
    y = create_investigation(p, tmp_path, title="Story prerequisite")
    complete_investigation(p, x)
    complete_investigation(p, y)
    epic = create_unit(p, "epic", "Initiative", cls=1, extra=("--depends-on", f"{x}:evidence"))
    story = create_unit(p, "story", "Objective", cls=1, parent=epic, extra=("--depends-on", f"{y}:evidence"))
    running = create_investigation(p, tmp_path, parent=story, title="Running below the Story")
    dispatch(p, running)
    refused = err(p, "work", "promote", story, "--to", "epic", "--title", "Bigger", "--reason", "grew")
    assert refused["code"] == "ILLEGAL_TRANSITION" and refused["details"]["in_progress"] == [running]
    out = p.lead("work", "promote", running, "--to", "story", "--title", "Its own objective", "--reason", "grew")
    u = show(p, running)
    assert u["state"] == "REPLAN_REQUIRED" and u["parent"] == out["promoted_to"]  # lost the edge to Y, replanned
    assert show(p, out["promoted_to"])["parent"] == epic
    assert_control_invariants(p)


def test_an_attempt_is_bound_to_the_dependencies_it_was_dispatched_with(tmp_path):
    """Defense in depth for B2: whatever changes a started Ticket's effective edges (here a corrupted copy of a
    real state; no operation can do it any more), its gate context, and so every guarded transition, accept,
    prepare and publish, refuses until a new dispatch; an attempt recorded without its edges is still checked
    for satisfaction in its own source snapshot."""
    import copy

    import pytest

    from aew.engine.api import Engine
    from aew.errors import GateUnsatisfied

    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", cls=1)
    unfinished = create_investigation(p, tmp_path, title="Unfinished")
    change = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    implement(assign(p, change))
    look = create_investigation(p, tmp_path, parent=story, title="Look")
    dispatch(p, look)
    engine = Engine.discover(p.root)
    state = engine.store.read()
    assert engine.dispatch_binding_problem(state, change) is None
    assert engine.dispatch_binding_problem(state, look) is None
    s = copy.deepcopy(state)
    s["work"][story]["depends_on"].append({"id": unfinished, "kind": "evidence"})
    for wid in (change, look):
        problem = engine.dispatch_binding_problem(s, wid)
        assert problem["added"] == [f"{unfinished}:evidence"] and problem["unsatisfied_at_dispatch_commit"], wid
        gc = engine.gate_context(s, wid)
        with pytest.raises(GateUnsatisfied, match="new dispatch is required"):
            engine._require_gates(gc, gc["obligations"]["gates"], what="probe")
    s["work"][change]["workspace"].pop("dependencies")  # dispatched before bindings were recorded
    legacy = engine.dispatch_binding_problem(s, change)
    assert "added" not in legacy and legacy["unsatisfied_at_dispatch_commit"][0]["id"] == unfinished



def test_edge_edits_wait_for_unstarted_work_and_closeout_waits_for_dependencies(tmp_path):
    """M2 review major 1: ADR-0007 allows an edge edit only while every affected Ticket is BLOCKED, READY or
    REPLAN_REQUIRED; a finished child completed without the new edge, so the edit is refused (a cancelled
    child never runs again and is not affected). Independently, a parent never closes while its own or
    inherited dependencies are unsatisfied: moving a DONE child under it (still allowed) cannot close it early."""
    p = sample_project(tmp_path)
    x = create_investigation(p, tmp_path, title="Unfinished prerequisite", cls=0)
    other = create_unit(p, "story", "Other", cls=0)
    finished = create_investigation(p, tmp_path, parent=other, cls=0, title="Finished child")
    complete_investigation(p, finished)
    refused = err(p, "work", "depend", other, "--add", f"{x}:evidence", "--reason", "found late")
    assert refused["code"] == "ILLEGAL_TRANSITION" and refused["details"]["affected"] == {finished: "DONE"}
    assert show(p, other)["depends_on"] == []
    third = create_unit(p, "story", "Third", cls=0)
    dropped = create_investigation(p, tmp_path, parent=third, cls=0, title="Dropped")
    p.lead("work", "transition", dropped, "--to", "CANCELLED", "--reason", "not needed")
    waiting = create_investigation(p, tmp_path, parent=third, cls=0, title="Waiting")
    p.lead("work", "depend", third, "--add", f"{x}:evidence", "--reason", "the survey comes first")
    assert show(p, waiting)["state"] == "BLOCKED"
    assert_control_invariants(p)

    story = create_unit(p, "story", "Objective", cls=0, extra=("--depends-on", f"{x}:evidence"))
    early = create_investigation(p, tmp_path, cls=0, title="Done before it was filed here")
    complete_investigation(p, early)
    p.lead("work", "move", early, "--parent", story, "--reason", "belongs to the objective")
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"
    closing = err(p, "work", "close", story, "--reason", "children done")
    assert closing["code"] == "DEPENDENCY_UNSATISFIED" and closing["details"]["blockers"][0]["id"] == x
    assert any(a.startswith(f"{story}: waiting on {x}") for a in p.ok("resume", "--json")["next_actions"])
    assert_control_invariants(p)
    complete_investigation(p, x)
    p.lead("work", "close", story, "--reason", "children done and the prerequisite accepted")
    assert show(p, story)["state"] == "DONE"
    assert_control_invariants(p)


def test_a_read_only_invocation_is_checked_for_mutation_until_its_report_is_ingested(tmp_path):
    """M2 review major 2: the observation is re-fingerprinted when a report is ingested, not only when it is
    submitted, on every read-only path (executor, record reviewer, parent reviewer), and review/verification
    submissions are checked like records. A report whose observation can no longer be checked (its invocation
    ended first) is not ingested either; the attempt or the reviewer is replaced."""
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path, cls=2)
    p.lead("work", "staff", wid, "--review", "code_reviewer")
    k1, _ = dispatch(p, wid)
    e1 = submit_record(k1, "discovery_record")["evidence"]
    (k1.workspace / "calc/core.py").write_text("tampered after submission\n", encoding="utf-8", newline="\n")
    refused = err(p, "evidence", "ingest", wid, "--evidence", e1)
    assert refused["code"] == "OBSERVATION_MUTATED" and "calc/core.py" in refused["details"]["changed"]
    again = p.lead("work", "redispatch", wid, "--reason", "the executor changed its observation")
    k2 = Role(p, again["invocation_token"], Path(again["observation"]["path"]))
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(k2, "discovery_record")["evidence"])
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    assert_control_invariants(p)

    review = {"claim": "facts are supported", "review": {"independence": "R1", "disposition": "pass",
                                                          "findings": [], "resolved_findings": []}}
    rv = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    r1 = Role(p, rv["invocation_token"], Path(rv["observation"]["path"]))
    (r1.workspace / "calc/core.py").write_text("tampered before review\n", encoding="utf-8", newline="\n")
    assert r1.submit("review", review, expect_ok=False).error["code"] == "OBSERVATION_MUTATED"
    rv2 = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    ev = Role(p, rv2["invocation_token"], Path(rv2["observation"]["path"])).submit("review", review)["evidence"]
    p.lead("invoke", "cancel", rv2["invocation"], "--reason", "reviewer lost")
    assert err(p, "review", "ingest", wid, "--evidence", ev)["code"] == "GATE_UNSATISFIED"  # cannot be rechecked
    rv3 = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    p.lead("review", "ingest", wid, "--evidence",
           Role(p, rv3["invocation_token"], Path(rv3["observation"]["path"])).submit("review", review)["evidence"])
    p.lead("work", "accept", wid)
    assert show(p, wid)["state"] == "DONE"
    assert_control_invariants(p)

    story = create_unit(p, "story", "Objective", cls=1)
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    out = p.lead("invoke", "create", story, "--role", "verifier")
    ver = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    unit_ev = ver.check("unit")["evidence"]
    (ver.workspace / "calc/core.py").write_text("tampered after the check\n", encoding="utf-8", newline="\n")
    claims = [{"type": t, "claim": "holds", "result": "pass", "checks": [unit_ev]}
              for t in ("goal_backwards", "contract")]
    rejected = ver.submit("verification",
                          {"claim": "acceptance", "verification": {"scope": "parent", "claims": claims}},
                          expect_ok=False)
    assert rejected.error["code"] == "OBSERVATION_MUTATED"
    assert_control_invariants(p)


def test_parent_acceptance_is_a_downstream_assignment_of_its_dependencies(tmp_path):
    """Operator decision after the M2 re-review (ADR-0007): a Story's reviewer and verifier are downstream
    assignments of the Story's own and inherited dependencies (WC §8: satisfied only when the upstream output is
    in the downstream assignment's recorded input/source snapshot). They wait for them, consume the prerequisite
    records under the ADR-0008 input rule, and their reports are bound to the dependencies they ran under."""
    import copy

    from invariants import m2_violations, with_cold

    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    survey = create_investigation(p, tmp_path, title="Prerequisite survey")
    story = create_unit(p, "story", "Objective", cls=1, extra=("--depends-on", f"{survey}:evidence"))
    plan_unit(p, tmp_path, story)
    finished = create_investigation(p, tmp_path, title="Finished elsewhere")
    complete_investigation(p, finished)
    p.lead("work", "move", finished, "--parent", story, "--reason", "belongs to the objective")
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"
    for role in ("reviewer", "verifier"):
        refused = err(p, "invoke", "create", story, "--role", role)
        assert refused["code"] == "DEPENDENCY_UNSATISFIED" and refused["details"]["blockers"][0]["id"] == survey
    actions = [a for a in p.ok("resume", "--json")["next_actions"] if a.startswith(f"{story}: ")]
    assert any(f"waiting on {survey}" in a and "acceptance review" in a for a in actions)
    assert not any("invoke create" in a for a in actions)  # resume does not advise a refused dispatch
    assert_control_invariants(p)

    rec = complete_investigation(p, survey)
    other, _ = to_commit_ready(p, tmp_path, title="Change calc")
    integrate(p, other)  # changes what the survey observed: STALE for the Story's acceptance, too
    stale = err(p, "invoke", "create", story, "--role", "reviewer")
    assert stale["code"] == "INPUT_STALE" and stale["details"]["inputs"][0]["id"] == rec
    ack = p.lead("work", "acknowledge-input", story, "--input", rec, "--from", survey,
                 "--reason", "rechecked: the survey's facts about add() still hold")
    out = p.lead("invoke", "create", story, "--role", "reviewer")
    pinned = p.ok("invoke", "show", out["invocation"])["inputs"]
    assert [(i["id"], i["from"], i["acknowledgement"]) for i in pinned] == [(rec, survey, ack["decision"])]
    assert rec in (p.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")  # the reviewer sees it
    reviewer = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    review_ev = reviewer.submit("review", {"claim": "objective met", "review": {
        "independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}})["evidence"]
    p.lead("review", "ingest", story, "--evidence", review_ev)
    p.lead("verify", "ingest", story, "--evidence", parent_verify(p, story))
    p.lead("work", "close", story, "--reason", "the prerequisite and the children are accepted")
    meta, _ = parse_frontmatter((p.root / ".aew" / show(p, story)["closeout"]["record"]).read_text(encoding="utf-8"))
    assert [(d["id"], d["kind"], d["state"]) for d in meta["dependencies"]] == [(survey, "evidence", "DONE")]
    assert meta["basis"]["review_r1"] == review_ev
    assert_control_invariants(p)

    # Reports are bound to the dependencies they ran under: a move that adds an inherited edge makes them STALE.
    epic = create_unit(p, "epic", "Programme", cls=0, extra=("--depends-on", f"{survey}:evidence"))
    free = create_unit(p, "story", "Free-standing", cls=1)
    plan_unit(p, tmp_path, free)
    complete_investigation(p, create_investigation(p, tmp_path, parent=free, title="Its child"))
    p.lead("review", "ingest", free, "--evidence", parent_review(p, free))
    p.lead("verify", "ingest", free, "--evidence", parent_verify(p, free))
    p.lead("work", "move", free, "--parent", epic, "--reason", "part of the programme")
    p.lead("plan", "reconfirm", free, "--reason", "same objective inside the programme")
    gates = p.ok("gate", "show", free)["gates"]
    assert gates["review_r1"]["status"] == "STALE" and gates["verification_goal_backwards"]["status"] == "STALE"
    assert err(p, "work", "close", free, "--reason", "reports predate the new dependency")["code"] == "GATE_UNSATISFIED"
    p.lead("work", "acknowledge-input", free, "--input", rec, "--from", survey, "--reason", "rechecked as above")
    p.lead("review", "ingest", free, "--evidence", parent_review(p, free))
    p.lead("verify", "ingest", free, "--evidence", parent_verify(p, free))
    p.lead("work", "close", free, "--reason", "accepted under the programme's dependencies")
    assert show(p, free)["state"] == "DONE"
    assert_control_invariants(p)

    state, _ = with_cold(p.root, Engine.discover(p.root).store.read())  # oracle rule 16 is not vacuous
    bad = copy.deepcopy(state)
    bad["invocations"][out["invocation"]]["dependencies"] = []
    assert "dispatched under dependencies" in " | ".join(m2_violations(p.root, bad))
