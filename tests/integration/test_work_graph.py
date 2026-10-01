"""Work records, plan revisions, readiness and derived parent state (WC §7-§9; KC §9, §12)."""

from __future__ import annotations

from pathlib import Path


def body_file(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def make_ticket(project, *extra: str, title: str = "Add subtract()") -> str:
    return project.lead("work", "create", "ticket", "--title", title, "--class", "1", *extra)["id"]


def accept_plan(project, tmp_path, wid: str, text: str = "Implement it.\n") -> None:
    rev = project.lead("plan", "propose", "--assurance", "none", wid, "--file", body_file(tmp_path, f"{wid}-plan.md", text))
    project.lead("plan", "accept", wid, "--revision", str(rev["revision_number"]))


def test_ticket_blocked_until_plan_accepted(project, tmp_path):
    wid = make_ticket(project, "--scope", "calc/**", "--goal", "subtract(5,3) == 2")
    show = project.ok("work", "show", wid)
    assert show["control"]["state"] == "BLOCKED"
    assert show["control"]["blocked_by"] == [{"kind": "plan_not_accepted"}]
    assert "subtract(5,3) == 2" in show["record"]
    accept_plan(project, tmp_path, wid)
    assert project.ok("work", "show", wid)["control"]["state"] == "READY"
    assert [i["id"] for i in project.ok("work", "ready")["items"]] == [wid]
    current = (project.root / ".aew/state/CURRENT.md").read_text()
    assert "READY" in current and wid in current


def test_mutating_dependency_blocks_until_upstream_done(project, tmp_path):
    t1 = make_ticket(project)
    t2 = make_ticket(project, "--depends-on", t1, title="Use subtract in apply()")
    accept_plan(project, tmp_path, t1)
    accept_plan(project, tmp_path, t2)
    show = project.ok("work", "show", t2)["control"]
    assert show["state"] == "BLOCKED"
    assert show["depends_on"] == [{"id": t1, "kind": "mutating"}]
    assert show["blocked_by"][0]["id"] == t1 and show["blocked_by"][0]["reason"].startswith("not_done")


def test_generic_transition_cannot_impersonate_operations(project, tmp_path):
    wid = make_ticket(project)
    accept_plan(project, tmp_path, wid)
    res = project.aew("work", "transition", wid, "--to", "ASSIGNED", "--token", project.token,
                      "--expect-rev", str(project.rev()))
    assert res.returncode == 5
    assert res.error["code"] == "ILLEGAL_TRANSITION"
    assert res.error["details"]["required_operation"] == "assign"


def test_cancel_requires_reason_and_records_decision(project, tmp_path):
    wid = make_ticket(project)
    res = project.aew("work", "transition", wid, "--to", "CANCELLED", "--token", project.token,
                      "--expect-rev", str(project.rev()))
    assert res.returncode == 2 and res.error["code"] == "USAGE"
    out = project.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "duplicate")
    decision = (project.root / f".aew/decisions/{out['decision']}.md").read_text()
    assert "cancellation" in decision and "duplicate" in decision


def test_plan_revisions_are_immutable_and_hash_pinned(project, tmp_path):
    wid = make_ticket(project)
    accept_plan(project, tmp_path, wid, "Original plan.\n")
    plan = project.root / f".aew/work/{wid}/plan-v1.md"
    plan.write_text(plan.read_text() + "\nsneaky edit\n")
    contradictions = project.ok("status", "--json")["contradictions"]
    assert any("accepted plan v1 was modified" in c for c in contradictions)


def test_new_plan_revision_must_state_reason_and_supersede(project, tmp_path):
    wid = make_ticket(project)
    accept_plan(project, tmp_path, wid)
    res = project.aew("plan", "propose", "--assurance", "none", wid, "--file", body_file(tmp_path, "v2.md", "v2\n"),
                      "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 2
    out = project.lead("plan", "propose", "--assurance", "none", wid, "--file", body_file(tmp_path, "v2.md", "v2\n"),
                       "--reason", "runtime evidence disproved assumption X")
    assert out["revision_number"] == 2
    project.lead("plan", "accept", wid, "--revision", "2")
    plans = project.ok("work", "show", wid)["control"]["plans"]
    assert [p["status"] for p in plans] == ["superseded", "accepted"]
    assert "supersedes: 1" in (project.root / f".aew/work/{wid}/plan-v2.md").read_text()


def test_story_rollup_and_inherited_policy_representation(project, tmp_path):
    res = project.aew("work", "create", "story", "--title", "Accounting", "--class", "3",
                      "--min-descendant-class", "2", "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 2  # a floor needs a rationale
    story = project.lead("work", "create", "story", "--title", "Accounting", "--class", "3",
                         "--mandatory-gate", "review_security", "--min-descendant-class", "2",
                         "--rationale", "crosses the auth boundary")["id"]
    t1 = make_ticket(project, "--parent", story)
    rollup = project.ok("work", "show", story)["rollup"]
    assert rollup["derived_state"] == "IN_PROGRESS" and rollup["children_by_state"] == {"BLOCKED": 1}
    res = project.aew("work", "transition", story, "--to", "CANCELLED", "--reason", "x",
                      "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 5  # parent state is derived, never hand-maintained
    assert project.ok("work", "show", t1)["control"]["risk_class"] == 1  # local class is preserved
