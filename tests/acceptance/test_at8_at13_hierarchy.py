"""M2 acceptance scenarios AT-8..AT-13 (ADR-0007, ADR-0008; KC §26): the Epic/Story hierarchy and the
non-mutating Ticket path, end to end through the CLI with scripted roles."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aewflow import (APPLY_PATCH, SUBTRACT_PATCH, Role, assign, close_parent, complete_investigation,
                     create_investigation, create_planned_ticket, create_unit, dispatch, implement, integrate,
                     plan_unit, review, sample_project, submit_record, to_commit_ready, verify)
from conftest import git
from invariants import assert_control_invariants
from test_at1_serial_lifecycle import operator_takeover

from aew.util import parse_frontmatter


def show(p, wid):
    return p.ok("work", "show", wid)["control"]


def err(p, *args, token=None):
    res = p.aew(*args, "--token", token or p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


@pytest.mark.acceptance("AT-8")
def test_story_lifecycle_to_closeout(tmp_path):
    """WC §7-§8: parent state is derived; children complete is not acceptance; only the Lead closes."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Calculator v2")
    assert show(p, epic)["state"] == "PLANNING"
    plan_unit(p, tmp_path, epic, "Deliver subtraction, investigated first.\n")
    story = create_unit(p, "story", "Subtraction", cls=2, parent=epic)
    plan_unit(p, tmp_path, story, "1. Investigate calc.core.\n2. Implement subtract().\n")
    survey = create_investigation(p, tmp_path, parent=story)
    build = create_planned_ticket(p, tmp_path, extra=("--parent", story, "--depends-on", f"{survey}:evidence"))
    assert [show(p, w)["state"] for w in (epic, story, build)] == ["IN_PROGRESS", "IN_PROGRESS", "BLOCKED"]

    complete_investigation(p, survey)
    assert show(p, build)["state"] == "READY"
    to_commit_ready(p, tmp_path, wid=build)
    assert show(p, story)["state"] == "IN_PROGRESS"  # COMMIT_READY is not done: nothing is integrated yet
    integrate(p, build)
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING" and show(p, epic)["state"] == "IN_PROGRESS"
    assert_control_invariants(p)

    refused = err(p, "work", "close", story)
    assert refused["code"] == "GATE_UNSATISFIED" and "review_r1" in refused["details"]["unmet"]
    assert err(p, "work", "transition", story, "--to", "DONE")["code"] == "ILLEGAL_TRANSITION"
    resume = p.ok("resume", "--json")
    assert any(a.startswith(f"{story}: all children are DONE/CANCELLED") for a in resume["next_actions"])

    close_parent(p, story)
    assert show(p, story)["state"] == "DONE" and show(p, epic)["state"] == "ACCEPTANCE_PENDING"
    close_parent(p, epic)
    u = show(p, epic)
    assert u["state"] == "DONE"
    meta, _ = parse_frontmatter((p.root / ".aew" / u["closeout"]["record"]).read_text(encoding="utf-8"))
    assert [c["id"] for c in meta["children"]] == [story]
    final = p.ok("resume", "--json")
    assert final["contradictions"] == [] and final["tree"][0].startswith(f"Epic {epic} [DONE]")
    assert_control_invariants(p)


@pytest.mark.acceptance("AT-9")
def test_parent_risk_policy_propagation(tmp_path):
    """KC §26: a Class-3 Story with a locally Class-0 Ticket and a Story-level mandatory security review."""
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Session handling", cls=3, extra=("--mandatory-gate", "review_security"))
    plan_unit(p, tmp_path, story)
    tiny = create_planned_ticket(p, tmp_path, title="Small change near sessions", cls=0, extra=("--parent", story))
    ob = p.ok("gate", "show", tiny)["obligations"]
    assert ob["local_class"] == 0 and ob["effective_class"] == 0 and show(p, tiny)["risk_class"] == 0
    assert "review_security" in ob["gates"] and "review_security" in ob["non_waivable"]
    implement(assign(p, tiny))
    assert err(p, "work", "transition", tiny, "--to", "COMMIT_READY")["code"] == "GATE_UNSATISFIED"
    waiver = err(p, "gate", "waive", tiny, "--gate", "review_security", "--reason", "small")
    assert waiver["code"] == "GATE_UNSATISFIED" and "non-waivable" in waiver["message"]
    p.lead("work", "transition", tiny, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", tiny, "--evidence", review(p, tiny, specialty="security"))
    p.lead("work", "transition", tiny, "--to", "COMMIT_READY")
    integrate(p, tiny)
    assert show(p, tiny)["risk_class"] == 0  # the local classification is kept to the end
    assert_control_invariants(p)

    # An explicit minimum descendant class raises the effective minimum only with a recorded rationale.
    res = p.aew("work", "create", "story", "--title", "Billing", "--class", "3", "--min-descendant-class", "2",
                "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode == 2
    floored = create_unit(p, "story", "Billing", cls=3, extra=("--min-descendant-class", "2", "--rationale",
                                                              "money moves through every child"))
    plan_unit(p, tmp_path, floored)
    t = create_planned_ticket(p, tmp_path, title="Rounding", cls=0, extra=("--parent", floored))
    ob = p.ok("gate", "show", t)["obligations"]
    assert ob["local_class"] == 0 and ob["floor"] == 2 and ob["effective_class"] == 2
    assert {"review_r1", "verification_goal_backwards"} <= set(ob["gates"])
    assert "money moves" in p.ok("work", "show", floored)["record"]  # the rationale is recorded with the floor
    unfloored = create_planned_ticket(p, tmp_path, title="Elsewhere", cls=0)
    assert p.ok("gate", "show", unfloored)["obligations"]["effective_class"] == 0
    assert_control_invariants(p)


@pytest.mark.acceptance("AT-10")
def test_ticket_promotion_preserves_identity_evidence_and_reason(tmp_path):
    """KC §26: begin a Ticket; evidence shows hidden cross-component ambiguity; the Lead promotes it."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Calculator v2")
    t = create_planned_ticket(p, tmp_path, title="Add subtract()", extra=("--parent", epic))
    record_before = (p.root / ".aew" / show(p, t)["record"]).read_bytes()
    impl = assign(p, t)
    impl.write(SUBTRACT_PATCH)
    check = impl.check("unit")["evidence"]
    report = impl.submit("implementation_report", {
        "claim": "subtract() also needs the parser and the CLI formatter changed; the plan covers neither",
        "result": "blocked", "producer": {"model": "scripted"},
        "implementation": {"files_changed": sorted(SUBTRACT_PATCH), "checks_run": ["unit"],
                           "deviations": ["parser and CLI formatter are out of scope"],
                           "self_review": {"completed": True, "notes": "stopped at the scope boundary"}}},
        "Hidden cross-component ambiguity: three components are involved.\n")["evidence"]
    res = p.lead("work", "promote", t, "--to", "story", "--title", "Subtraction across parser, core and CLI",
                 "--reason", f"{report}: the change spans three components")
    story = res["promoted_to"]
    s = show(p, story)
    assert s["kind"] == "story" and s["parent"] == epic and s["promoted_from"] == t and s["risk_class"] >= 1
    u = show(p, t)
    assert u["parent"] == story and u["state"] == "REPLAN_REQUIRED"
    assert (p.root / ".aew" / u["record"]).read_bytes() == record_before  # never silently rewritten
    for ev in (check, report):
        assert (p.root / f".aew/evidence/{t}/{ev}.md").exists()
    decision = (p.root / f".aew/decisions/{res['decision']}.md").read_text(encoding="utf-8")
    assert "promotion" in decision and report in decision
    assert_control_invariants(p)

    # Work continues under the new Story: it is planned, the Ticket is replanned, siblings are added.
    plan_unit(p, tmp_path, story, "1. core (the original Ticket)\n2. parser\n3. CLI formatter\n")
    plan_unit(p, tmp_path, t, "Only calc/core.py and its test.\n", reason="narrowed to the core component")
    assert show(p, t)["state"] == "READY" and show(p, t)["workspace"]["status"].startswith("released")
    sibling = create_planned_ticket(p, tmp_path, title="Parser support", extra=("--parent", story))
    assert p.ok("work", "show", story)["children"] == sorted([t, sibling])
    assert_control_invariants(p)


@pytest.mark.acceptance("AT-11")
def test_fresh_session_reconstructs_an_active_hierarchy_and_takeover_interrupts_read_only_work(tmp_path):
    """KC §26: a new Lead recovers the active Epic/Story/Ticket graph, plans, inputs and next action
    without conversational memory; takeover interrupts non-mutating work and nothing is inferred."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Calculator v2")
    plan_unit(p, tmp_path, epic, "Epic plan.\n")
    story = create_unit(p, "story", "Subtraction", parent=epic)
    plan_unit(p, tmp_path, story, "Story plan.\n")
    survey = create_investigation(p, tmp_path, parent=story)
    build = create_planned_ticket(p, tmp_path, extra=("--parent", story, "--depends-on", f"{survey}:evidence"))
    later_story = create_unit(p, "story", "Multiplication", parent=epic, extra=("--depends-on", f"{story}:mutating"))
    later = create_investigation(p, tmp_path, parent=later_story, title="Survey multiplication")
    executor, _ = dispatch(p, survey)
    rec = submit_record(executor, "discovery_record")["evidence"]

    lost = p.token
    p.token = ""  # the Lead session and its only credential are destroyed
    shutil.rmtree(p.root / ".aew/local")
    resume = p.ok("resume", "--json")
    work = {w["id"]: w for w in resume["work"]}
    assert resume["tree"][0].startswith(f"Epic {epic} [IN_PROGRESS]")
    assert work[story]["accepted_plan"]["revision"] == 1 and work[story]["children"] == sorted([survey, build])
    assert work[survey]["execution"]["attempt"] == 1 and work[survey]["execution"]["expected_kind"] == "discovery_record"
    assert work[build]["state"] == "BLOCKED" and work[build]["blocked_by"][0]["id"] == survey
    assert work[later]["blocked_by"][0]["inherited_from"] == later_story
    assert f"{survey}: ingest record {rec} (`aew evidence ingest`)" in resume["next_actions"]
    assert resume["contradictions"] == []

    p.token = operator_takeover(p, "Lead session destroyed (AT-11)")
    assert err(p, "checkpoint", "--next", "x", token=lost)["code"] == "STALE_AUTHORITY"
    assert show(p, survey)["state"] == "INTERRUPTED"
    assert submit_record(Role(p, executor.token, p.root), "discovery_record", expect_ok=False).error["code"] \
        == "STALE_AUTHORITY"
    resume = p.ok("resume", "--json")
    assert any(a.startswith(f"{survey}: ") and "redispatch" in a for a in resume["next_actions"])
    rec_out = p.lead("work", "reconcile", survey, "--to", "RUNNING", "--reason", "one record found, not ingested")
    assert rec_out["inspection"]["records_submitted"] == [rec]
    assert err(p, "evidence", "ingest", survey, "--evidence", rec)["code"] == "GATE_UNSATISFIED"  # never inferred
    again = p.lead("work", "redispatch", survey, "--reason", "continue after takeover")
    fresh = Role(p, again["invocation_token"], Path(again["observation"]["path"]))
    p.lead("evidence", "ingest", survey, "--evidence", submit_record(fresh, "discovery_record")["evidence"])
    p.lead("work", "accept", survey)
    assert show(p, build)["state"] == "READY"
    assert p.ok("resume", "--json")["contradictions"] == []
    assert_control_invariants(p)


@pytest.mark.acceptance("AT-12")
def test_read_only_work_runs_concurrently_and_stays_read_only(tmp_path):
    """WC §8.1/§5: investigation and research run beside the serial mutation slot, each in its own
    observation of the authoritative source; read-only roles cannot mutate, drive control or
    produce another archetype's output; a Planner proposes and only the Lead adopts."""
    p = sample_project(tmp_path)
    mutating = create_planned_ticket(p, tmp_path, title="In-flight change")
    impl = assign(p, mutating)
    impl.write(SUBTRACT_PATCH)
    survey = create_investigation(p, tmp_path, title="Survey")
    research = create_investigation(p, tmp_path, title="pytest capability", card="researcher")
    planning = create_investigation(p, tmp_path, title="Plan apply()", card="planner")
    roles = {w: dispatch(p, w) for w in (survey, research, planning)}
    paths = {Path(out["observation"]["path"]) for _, out in roles.values()}
    assert len(paths) == 3 and impl.workspace not in paths
    for path in paths:
        assert "subtract" not in (path / "calc/core.py").read_text(encoding="utf-8")  # never unintegrated work
    assert err(p, "work", "assign", create_planned_ticket(p, tmp_path, title="Second"))["code"] == "CONCURRENCY_LIMIT"

    investigator, researcher, planner = (roles[w][0] for w in (survey, research, planning))
    for role, wrong in ((investigator, "research_record"), (researcher, "plan_proposal"), (planner, "discovery_record")):
        assert submit_record(role, wrong, expect_ok=False).error["code"] == "PERMISSION_DENIED"
    for role in (investigator, researcher, planner):
        denied = role.aew("work", "transition", survey, "--to", "CANCELLED", "--reason", "x", "--token", role.token,
                          "--expect-rev", str(p.rev()))
        assert denied.error["code"] == "PERMISSION_DENIED"
        assert role.aew("plan", "accept", planning, "--revision", "1", "--token", role.token,
                        "--expect-rev", str(p.rev())).error["code"] == "PERMISSION_DENIED"
    assert researcher.aew("check", "run", "unit").error["code"] == "PERMISSION_DENIED"  # not in its grant
    (investigator.workspace / "calc/core.py").write_text("broken\n", encoding="utf-8", newline="\n")
    assert submit_record(investigator, "discovery_record", expect_ok=False).error["code"] == "OBSERVATION_MUTATED"
    assert_control_invariants(p)

    for role, wid, kind in ((researcher, research, "research_record"), (planner, planning, "plan_proposal")):
        p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, kind)["evidence"])
        p.lead("work", "accept", wid)
    proposal = show(p, planning)["execution"]["record"]["id"]
    target = create_unit(p, "ticket", "Add apply()", extra=("--scope", "calc/**", "--scope", "tests/**",
                                                             "--goal", "apply(subtract, 5, 3) == 2"))
    adopted = p.lead("plan", "adopt", target, "--evidence", proposal, "--from", planning,
                     "--reason", "the Planner's proposal, reviewed by the Lead")
    plan_meta, _ = parse_frontmatter((p.root / ".aew" / adopted["path"]).read_text(encoding="utf-8"))
    assert plan_meta["source_evidence"]["id"] == proposal and show(p, target)["plan"] is None  # proposed only
    p.lead("plan", "accept", target, "--revision", str(adopted["revision_number"]))
    assert show(p, target)["state"] == "READY"
    assert_control_invariants(p)


MULTIPLY = {"calc/mul.py": "def multiply(a, b):\n    return a * b\n",
            "tests/test_mul.py": "from calc.mul import multiply\n\n\ndef test_multiply():\n"
                                 "    assert multiply(3, 4) == 12\n"}


@pytest.mark.acceptance("AT-13")
def test_representative_backlog_is_representable_and_executable(tmp_path):
    """A generic backlog in the shape of the SPT remediation backlog (no SPT concepts in core): an Epic of
    Stories mixing investigation, research, planning and implementation Tickets, Story-level
    dependencies, external references, the KC §26 T1,T2 -> T3 + T4 graph, and a standalone small Ticket."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Toolchain readiness", extra=("--external-ref", "backlog:EPIC-1"))
    plan_unit(p, tmp_path, epic, "Stories A then B; audit at the end.\n")
    a = create_unit(p, "story", "A: arithmetic core", cls=2, parent=epic, extra=("--external-ref", "backlog:P0-1"))
    plan_unit(p, tmp_path, a, "T1 subtract, T2 survey, T3 apply (after T1, T2), T4 research.\n")
    t1 = create_planned_ticket(p, tmp_path, title="T1 subtract", extra=("--parent", a))
    t2 = create_investigation(p, tmp_path, parent=a, title="T2 survey callers")
    t3 = create_planned_ticket(p, tmp_path, title="T3 apply", extra=("--parent", a, "--depends-on", t1,
                                                                    "--depends-on", f"{t2}:evidence"))
    t4 = create_investigation(p, tmp_path, parent=a, title="T4 pytest capability", card="researcher")
    b = create_unit(p, "story", "B: multiplication", cls=1, parent=epic,
                    extra=("--depends-on", f"{a}:mutating", "--external-ref", "backlog:P1-4"))
    plan_unit(p, tmp_path, b)
    b_plan = create_investigation(p, tmp_path, parent=b, title="Plan multiplication", card="planner")
    b_build = create_unit(p, "ticket", "Implement multiply()", parent=b,
                          extra=("--scope", "calc/**", "--scope", "tests/**", "--goal", "multiply(3, 4) == 12"))
    audit = create_investigation(p, tmp_path, parent=epic, title="Audit the delivered toolchain",
                                 extra=("--depends-on", f"{b}:evidence"))
    small = create_planned_ticket(p, tmp_path, title="Fix README typo", cls=0, scope=("README.md",))
    assert show(p, small)["parent"] is None  # small work stays small: no artificial Story or Epic
    tree = p.ok("work", "tree")["lines"]
    units = (epic, a, t1, t2, t3, t4, b, b_plan, b_build, audit, small)
    assert tree[0].startswith(f"Epic {epic}") and all(any(f" {w} " in line for line in tree) for w in units)
    assert "backlog:P1-4" in p.ok("work", "show", b)["record"]  # external refs and priorities stay external
    assert show(p, b_plan)["state"] == "BLOCKED" and show(p, audit)["state"] == "BLOCKED"  # inherited / Story edge
    assert_control_invariants(p)

    # Story A: T1 mutating, T2 evidence -> T3; T4 independent.
    complete_investigation(p, t2)
    complete_investigation(p, t4, kind="research_record")
    to_commit_ready(p, tmp_path, wid=t1)
    assert show(p, t3)["state"] == "BLOCKED"  # T1 is COMMIT_READY but not integrated
    t1_commit = integrate(p, t1)["integrated_commit"]
    assert show(p, t3)["state"] == "READY"
    # T2 surveyed calc/ before T1 changed it: the edge is satisfied, but T3 is not dispatched on it blindly.
    stale = err(p, "work", "assign", t3)
    assert stale["code"] == "INPUT_STALE" and stale["details"]["inputs"][0]["from"] == t2
    survey_record = show(p, t2)["execution"]["record"]["id"]
    ack = p.lead("work", "acknowledge-input", t3, "--input", survey_record, "--from", t2,
                 "--reason", "rechecked: T1 only added subtract(); the surveyed callers are unchanged")
    impl = assign(p, t3)
    ws = show(p, t3)["workspace"]
    assert git("merge-base", "--is-ancestor", t1_commit, ws["base_commit"], cwd=p.root) == ""  # T1 in the snapshot
    inputs = p.ok("invoke", "show", show(p, t3)["implementer_invocation"])["inputs"]
    assert [(i["from"], i["acknowledgement"]) for i in inputs] == [(t2, ack["decision"])]
    implement(impl, APPLY_PATCH)
    p.lead("work", "transition", t3, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", t3, "--evidence", review(p, t3))
    p.lead("work", "transition", t3, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", t3, "--evidence", verify(p, t3))
    p.lead("work", "transition", t3, "--to", "COMMIT_READY")
    integrate(p, t3)
    assert show(p, a)["state"] == "ACCEPTANCE_PENDING"
    assert show(p, b_plan)["state"] == "BLOCKED"  # Story A's children are done; Story A is not closed
    close_parent(p, a)
    assert show(p, b_plan)["state"] == "READY"
    assert_control_invariants(p)

    # Story B: a Planner proposes, the Lead adopts, an implementer delivers.
    proposal = complete_investigation(p, b_plan, kind="plan_proposal")
    rev = p.lead("plan", "adopt", b_build, "--evidence", proposal, "--from", b_plan)["revision_number"]
    p.lead("plan", "accept", b_build, "--revision", str(rev))
    to_commit_ready(p, tmp_path, wid=b_build, files=MULTIPLY)
    integrate(p, b_build)
    close_parent(p, b)
    complete_investigation(p, audit)
    close_parent(p, epic)
    implement(assign(p, small), {"README.md": "# calc\n\nA tiny calculator.\n"})
    p.lead("work", "transition", small, "--to", "COMMIT_READY")  # class 0: proportionate gates only
    integrate(p, small)
    final = p.ok("resume", "--json")
    assert {w["id"]: w["state"] for w in final["work"]}[epic] == "DONE"
    assert all(w["state"] in {"DONE", "CANCELLED"} for w in final["work"])
    assert final["contradictions"] == []
    assert_control_invariants(p)
