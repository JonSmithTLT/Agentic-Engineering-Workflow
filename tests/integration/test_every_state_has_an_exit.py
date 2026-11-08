"""In every non-terminal Ticket state, the projection offers the Lead a next action or a decision (E133).

The check walks real Tickets through the workflow and reads what the projection says on each, so a new state in
``transitions.STATES`` fails it until it is seeded here. A hint does not count: it is prose nothing parses, so a Lead
cannot rely on it as an exit. What has no exit today is pinned in ``DEAD_ENDS`` with its reason and the hint it does
have; that list may only shrink. A row, "the Lead's exits", owns it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aewflow import Role, assign, create_planned_ticket, implement, review, sample_project, verify
from conftest import Project

from aew.engine import transitions as T
from aew.engine.api import Engine
from aew.engine.store import Transition
from aew.surface import contract, projection
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()

# Where a Ticket has no offered exit: why, and what its hint says today, for whoever closes it.
DEAD_ENDS = {
    "ASSIGNED": {
        "why": "assigned but not moved on: `ticket_start` passes through here, and no stage starts from it",
        "hint": "launch the implementer from its pack (INV-0001), then move to RUNNING"},
    "REVIEW_PENDING, no report and no live run": {
        "why": "the reviewer's report or run is what offers something; a lost run leaves nothing",
        "hint": "dispatch the next planned reviewer card (`aew invoke create`)"},
    "REVIEW_FAILED": {
        "why": "rework has no typed home: `ticket_start` does not fit it (`work.assign` starts from READY)",
        "hint": "return to RUNNING and dispatch an implementer with the findings"},
    "VERIFY_PENDING, no report and no live run": {
        "why": "the verifier's report or run is what offers something; a lost run leaves nothing",
        "hint": "dispatch the next planned verifier card (`aew invoke create`)"},
    "VERIFICATION_INCONCLUSIVE": {
        "why": "the return to VERIFY_PENDING needs a reason and the Lead's judgment; nothing offers it",
        "hint": "resolve the environment/evidence blocker, then return to VERIFY_PENDING"},
    "COMMIT_READY, prepared with no report": {
        "why": "a prepared candidate's verifier is launched by a stage that already ran; nothing offers it again",
        "hint": "dispatch post-integration verification (`aew invoke create"},
    "ESCALATED": {
        "why": "the return is the Lead's decision after the escalation's outcome; nothing offers it",
        "hint": "record the escalation outcome and return the Ticket"},
    "REPLAN_REQUIRED": {
        "why": "a new plan revision is the way on; nothing offers it",
        "hint": "propose and accept a new plan revision"},
}
# Only ever lowered: an entry leaves when its exit lands, and this number goes down with it.
MOST_DEAD_ENDS = 8


def offers(found: dict[str, Any]) -> list[str]:
    """What a Lead can rely on as an exit: an action other than waiting, or a decision naming a tool or a command."""
    return [*(a["action"] for a in found["actions"] if a["kind"] != contract.WAIT),
            *(d["decision"] for d in found["decisions_required"] if d["tool"] or d["cli_fallback"])]


def differences(seen: dict[str, dict[str, Any]], pinned: dict[str, Any], most: int) -> list[str]:
    """What is wrong with ``pinned`` against what the projection offered: a new dead end, one that has an exit now, a
    state no walk reached, or a list that grew."""
    dead = {label for label, found in seen.items() if not offers(found)}
    states = {found["state"] for found in seen.values()}
    return [*(f"{label}: the projection offers no exit, and it is not pinned" for label in sorted(dead - set(pinned))),
            *(f"{label}: has an exit now: remove it, and lower MOST_DEAD_ENDS" for label in sorted(set(pinned) - dead)),
            *(f"{state}: no walk reaches this state" for state in sorted(set(T.STATES) - T.TERMINAL - states)),
            *([f"the pinned list holds {len(pinned)}, more than {most}: it may only shrink"] if len(pinned) > most
              else [])]


def _project(tmp_path: Path, name: str) -> Project:
    (tmp_path / name).mkdir()
    return sample_project(tmp_path / name)


def walk(tmp_path: Path) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    def look(p: Project, wid: str, label: str | None = None) -> None:
        projection.clear_cache()
        found = projection.project(Engine.discover(p.root), CTX, wid)
        seen[label or found["state"]] = found

    p = _project(tmp_path, "path")
    wid = p.lead("work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g", "--contract", "c",
                 "--scope", "calc/**")["id"]
    look(p, wid, "BLOCKED, no plan")
    wid = create_planned_ticket(p, tmp_path / "path")
    look(p, wid)
    assigned = p.lead("work", "assign", wid)
    look(p, wid)
    p.lead("work", "transition", wid, "--to", "RUNNING")
    look(p, wid, "RUNNING, no report")
    implement(Role(p, assigned["invocation_token"], Path(assigned["workspace"]["path"])))
    look(p, wid, "RUNNING, reported")
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    look(p, wid, "REVIEW_PENDING, no report and no live run")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    look(p, wid)
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    look(p, wid, "VERIFY_PENDING, no report and no live run")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
    look(p, wid)
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    look(p, wid, "COMMIT_READY, no candidate")
    p.lead("integrate", "prepare", wid)
    look(p, wid, "COMMIT_READY, prepared with no report")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, scope="integration"))
    look(p, wid, "COMMIT_READY, validated")

    p = _project(tmp_path, "failed-review")
    wid = create_planned_ticket(p, tmp_path / "failed-review")
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    finding = {"id": "F-1", "severity": "major", "summary": "the change is wrong"}
    p.lead("review", "ingest", wid, "--evidence", review(p, wid, disposition="changes_required", findings=[finding]))
    look(p, wid)

    p = _project(tmp_path, "failed-verification")
    wid = create_planned_ticket(p, tmp_path / "failed-verification")
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, goal_result="fail"))
    look(p, wid)
    p.lead("verify", "classify", wid, "--as", "ENVIRONMENT_OR_EVIDENCE_BLOCKED", "--reason", "the check could not run")
    look(p, wid)

    p = _project(tmp_path, "hubs")
    wid = create_planned_ticket(p, tmp_path / "hubs")
    assign(p, wid)
    p.lead("work", "transition", wid, "--to", "ESCALATED", "--reason", "the operator's call")
    look(p, wid)
    p.lead("work", "transition", wid, "--to", "REPLAN_REQUIRED", "--reason", "the plan is wrong")
    look(p, wid)
    # A takeover is what interrupts a Ticket: the state is what the check needs, so it is seeded with one plain commit.
    engine = Engine.discover(p.root)
    with engine.store.session() as s:
        s.state["work"][wid].update(state="INTERRUPTED", interrupted_from="RUNNING")
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="seeded for the exits check"))
    look(p, wid)
    return seen


def test_every_non_terminal_state_offers_an_exit_or_is_pinned_with_its_reason(tmp_path):
    seen = walk(tmp_path)
    assert differences(seen, DEAD_ENDS, MOST_DEAD_ENDS) == []
    for label, pinned in DEAD_ENDS.items():  # what each hint says today, read from the projection and not remembered
        assert any(pinned["hint"] in hint for hint in seen[label]["hints"]), (label, seen[label]["hints"])


def test_the_check_fails_on_a_new_dead_end_a_closed_one_a_missing_state_and_a_longer_list():
    """Planted: no project is needed to prove the check can fail."""
    open_exit = {"state": "READY", "actions": [{"action": "ticket_start", "kind": contract.STAGE}],
                 "decisions_required": []}
    seen = {state: {**open_exit, "state": state} for state in sorted(set(T.STATES) - T.TERMINAL)}
    assert differences(seen, {}, 0) == []
    dead = {**open_exit, "state": "READY", "actions": []}
    assert differences({**seen, "READY": dead}, {}, 0) == ["READY: the projection offers no exit, and it is not pinned"]
    assert differences({**seen, "READY": dead}, {"READY": {}}, 1) == []
    assert differences(seen, {"READY": {}}, 1) == ["READY: has an exit now: remove it, and lower MOST_DEAD_ENDS"]
    missing = {k: v for k, v in seen.items() if k != "ESCALATED"}
    assert differences(missing, {}, 0) == ["ESCALATED: no walk reaches this state"]
    assert differences({**seen, "READY": dead}, {"READY": {}}, 0)[-1].endswith("it may only shrink")
    waiting = {**open_exit, "actions": [{"action": "harness_wait", "kind": contract.WAIT}]}
    assert offers(waiting) == [], "waiting is not an exit"
    hinted = {**open_exit, "actions": [], "hints": ["do the next thing"]}
    assert offers(hinted) == [], "a hint is not an exit"
