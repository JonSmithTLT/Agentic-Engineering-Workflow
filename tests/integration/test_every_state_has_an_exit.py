"""In every non-terminal Ticket state, the projection offers the Lead a next action or a decision (E133).

The check walks real Tickets through the workflow and reads what the projection says on each, so a new state in
``transitions.STATES`` fails it until it is seeded here. A hint does not count: it is prose nothing parses, so a Lead
cannot rely on it as an exit, and neither can an action or decision whose guard answers BLOCKED. An UNKNOWN answer does
count: the guard could not say, and the call itself still answers. What has no exit today is pinned in ``DEAD_ENDS``
with its reason and the hint it does have; that list may only shrink. Register row E233 owns it (E133 left eleven).

An exit must land (register E233). Every command the walk is offered, an action's or a decision's, parses as the real
CLI takes it and is one a Lead session reaches (``lands``). The walk is made in projects whose execution policy routes
to a harness, as a Lead session's does, and it goes on by the one next step the readable result gives (``follow_next``)
where that step is a command: a never-launched implementer's launch and then its move to RUNNING, the return from a
failed review, a reviewer's dispatch. A move that carries the Lead's reason is never the next step, so the returns
from an inconclusive verification and from an escalation are taken by name, with a reason (``follow``). The verifiers'
dispatches are the reviewer's command with another role or scope: they are parsed, held equal to the hint's, and
asked of their own dispatch decision and of the launch's profile, and not launched here. A relaunch counts as an exit
in whatever state its run ended, as the engine's own guidance offers it. With no execution profile no dispatch is an
exit: one leg walks that, and it is pinned.

COMMIT_READY is walked by integration status and by queue entry state where those differ in what is offered. The walk
does not enumerate every sub-case of every other state."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

import printed_commands as P
from aewflow import Role, assign, create_planned_ticket, implement, review, sample_project, verify
from conftest import Project
from test_integration_stages import custody, lease, verifier_script, verifying  # noqa: F401 (custody is a fixture)
from test_stage_runner import intent, launching

from aew.engine import custody_ops as CO
from aew.engine import transitions as T
from aew.engine.api import Engine
from aew.engine.store import Transition
from aew.harness import contract as K
from aew.harness import lead_broker
from aew.surface import contract, projection, readable, run
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()


def call(p: Project, name: str, **arguments: Any) -> dict[str, Any]:
    return run.run_tool(Engine.discover(p.root), CTX, name, {"expect_rev": p.rev(), **arguments}, token=p.token)


# Where a Ticket has no offered exit: why, and what its hint says today, for whoever closes it.
DEAD_ENDS = {
    "BLOCKED, no plan": {
        "why": "`ticket_start` answers BLOCKED until a plan is accepted, and nothing offers the plan itself: proposing "
               "takes the plan's body and its assurance, and accepting it is to need the operator's confirmation",
        "hint": "propose and accept a plan"},
    "RUNNING, no report": {
        "why": "the review request answers BLOCKED until the implementer reports; there is nothing to do but wait. "
               "Here a worker run by hand leaves no run to wait on; a run that ended without its report offers its "
               "relaunch",
        "hint": "in progress; when its report and checks are in"},
    "COMMIT_READY, prepared, entry awaits the Lead on a report that is not clean": {
        "why": "a requeue or a return to RUNNING is the Lead's judgment on the report; nothing offers either: the "
               "requeue's guard has no query, and no stage starts a return from COMMIT_READY",
        "hint": "awaits the Lead"},
    "REPLAN_REQUIRED": {
        "why": "a new plan revision is the way on; nothing offers it (as for a Ticket with no plan)",
        "hint": "propose and accept a new plan revision"},
    "REVIEW_PENDING, no report, no execution profile": {
        "why": "the dispatch offered launches its worker, and with no execution profile no run has a harness: it is "
               "BLOCKED, with what to configure. Every dispatch is, in such a project; this state stands for them",
        "hint": "dispatch the next planned reviewer card (`aew invoke create T-"},
}
# Only ever lowered: an entry leaves when its exit lands, and this number goes down with it. E133 left eleven; E233's
# first slice took seven, and added the one it found: a project with no execution profile, which E133's walk, made
# in one, counted nowhere.
MOST_DEAD_ENDS = 5
# What a reader puts where an offered command leaves a word to them.
REASON = "the cause is settled"


def offers(found: dict[str, Any]) -> list[str]:
    """What a Lead can rely on as an exit: an action other than waiting, or a decision naming a tool or a command."""
    return [*(a["action"] for a in found["actions"]
              if a["kind"] != contract.WAIT and a.get("availability") != "BLOCKED"),
            *(d["decision"] for d in found["decisions_required"]
              if (d["tool"] or d["cli_fallback"]) and d.get("availability") != "BLOCKED")]


def offered(found: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Every command a projection offers: each action's and each decision's, named."""
    return [*((a["action"], a["cli_fallback"]) for a in found["actions"] if a["cli_fallback"]),
            *((d["decision"], d["cli_fallback"]) for d in found["decisions_required"] if d["cli_fallback"])]


def lands(seen: dict[str, dict[str, Any]]) -> list[str]:
    """What is wrong with the commands ``seen`` offers: one the real CLI does not take as offered, once its
    placeholders are filled (``printed_commands``), or one no Lead session reaches (the broker's own lists)."""
    reachable = lead_broker.LEAD_REACHABLE | set(lead_broker.RELAYED_READS)
    out = []
    for label, found in seen.items():
        for name, argv in offered(found):
            command = "aew " + shlex.join(argv)
            try:
                parsed = P.parse(command, fenced=False)
            except P.PrintedCommandError as exc:
                out.append(f"{label}: {name} offers `{command}`, which does not run as offered: {exc}")
                continue
            out += [f"{label}: {name} offers `{command}`, which no Lead session reaches"
                    for ns in parsed if lead_broker.command_path(ns) not in reachable]
    return out


def follow(p: Project, found: dict[str, Any], action: str, **arguments: Any) -> Any:
    """Run the one move of ``found`` named ``action`` (with ``arguments``) as it is offered: AVAILABLE, and its own
    command, with the Lead's reason where it leaves one."""
    [move] = [a for a in found["actions"] if a["action"] == action
              and all(a["arguments"].get(k) == v for k, v in arguments.items())]
    assert move["availability"] == "AVAILABLE", move
    return p.ok(*(REASON if word == "<reason>" else word for word in move["cli_fallback"]),
                env={"AEW_LEAD_TOKEN": p.token})


def follow_next(p: Project, found: dict[str, Any], *command: str) -> Any:
    """Do what a Lead reading the result would: run its one next step, which is ``command`` printed whole (#612
    review, F1: the walk follows the step the product gives, never a move picked by name)."""
    line = found["next"]
    assert line.startswith("next: aew " + " ".join(command) + " "), line
    return p.ok(*shlex.split(line.removeprefix("next: aew ")), env={"AEW_LEAD_TOKEN": p.token})


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


def status(p: Project, wid: str) -> dict[str, Any]:
    return run.run_tool(Engine.discover(p.root), CTX, "status", {"work_id": wid})


def walk(tmp_path: Path, monkeypatch: Any, held: dict[str, str]) -> dict[str, dict[str, Any]]:
    """The walk, in projects whose execution policy routes to the fake harness, as a Lead session's does: a dispatch
    the projection offers launches its worker, so it is an exit only where a launch has a harness (#612 review, F2).
    Their workers are still run by hand where the walk needs their reports. One leg has no execution profile."""
    labs: list[Any] = []
    try:
        return _walk(tmp_path, monkeypatch, held, labs)
    finally:
        for lab in labs:
            lab.cleanup()


def _walk(tmp_path: Path, monkeypatch: Any, held: dict[str, str], labs: list[Any]) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}

    def _project(tmp_path: Path, name: str) -> Project:
        (tmp_path / name).mkdir()
        p = sample_project(tmp_path / name)
        labs.append(launching(p, tmp_path / name, monkeypatch))
        return p

    def look(p: Project, wid: str, label: str | None = None) -> None:
        """The Ticket's projection, with the one next step the readable result gives a Lead for it (``next``)."""
        projection.clear_cache()
        result = status(p, wid)
        seen[label or result["projection"]["state"]] = {**result["projection"],
                                                        "next": readable.render(result).split("\n")[1]}

    p = _project(tmp_path, "path")
    wid = p.lead("work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g", "--contract", "c",
                 "--scope", "calc/**")["id"]
    look(p, wid, "BLOCKED, no plan")
    wid = create_planned_ticket(p, tmp_path / "path")
    look(p, wid)
    assigned = p.lead("work", "assign", wid)
    look(p, wid)
    # By hand here: this leg's implementer is run by hand for its report, so the walk does not take the launch that
    # is the next step. The "launched" leg below does, and goes on to RUNNING by the next step after it.
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
    follow_next(p, seen["REVIEW_FAILED"], "work", "transition")
    look(p, wid, "RUNNING, sent back with findings")

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
    follow(p, seen["VERIFICATION_INCONCLUSIVE"], "work.transition", to="VERIFY_PENDING")
    look(p, wid, "VERIFY_PENDING, returned from an inconclusive verification")

    p = _project(tmp_path, "hubs")
    wid = create_planned_ticket(p, tmp_path / "hubs")
    assign(p, wid)
    p.lead("work", "transition", wid, "--to", "ESCALATED", "--reason", "the operator's call")
    look(p, wid)
    follow(p, seen["ESCALATED"], "work.transition", to="RUNNING")  # no later than the phase it left
    assert Engine.discover(p.root).status(wid)["work_unit"]["state"] == "RUNNING"  # "RUNNING, no report" again
    p.lead("work", "transition", wid, "--to", "REPLAN_REQUIRED", "--reason", "the plan is wrong")
    look(p, wid)
    # A takeover is what interrupts a Ticket, run for real by tests/acceptance/test_at8_at13_hierarchy.py's
    # test_fresh_session_reconstructs_an_active_hierarchy_and_takeover_interrupts_read_only_work. The state is what this
    # check needs, so it is seeded with one plain commit.
    engine = Engine.discover(p.root)
    with engine.store.session() as s:
        s.state["work"][wid].update(state="INTERRUPTED", interrupted_from="RUNNING")
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="seeded for the exits check"))
    look(p, wid)

    # What a real verifier and the real custody step leave: an entry the custodian routed either way.
    def routed(name: str, result: str, label: str) -> None:
        (tmp_path / name).mkdir()
        p = sample_project(tmp_path / name)
        lab = launching(p, tmp_path / name, monkeypatch)
        sync = tmp_path / name / "sync"
        sync.mkdir(exist_ok=True)
        try:
            wid, report = verifying(p, tmp_path / name)
            lab.script("default", verifier_script(sync, result))
            out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report)
            assert out["ok"], out["stopped"]
            custodian = lease(p)["custodian"]
            [run] = intent(p, out)["steps"][4]["outputs"]["runs"]
            lab.until(lambda: (sync / "ready").exists(), "wait.condition", what="the verifier to report")
            (sync / "release").touch()
            lab.wait(run)
            assert Engine.discover(p.root).custody_step(custodian, held[custodian])[0] == CO.ACTED
            look(p, wid, label)
        finally:
            lab.cleanup()

    # The dispatch and the launch the projection offers, each run as offered where a harness is routed, and each
    # reaching what it says: a reviewer at work, and an implementer launched, moved to RUNNING and, when its run ends
    # with no report, offered its relaunch.
    def lab_project(name: str) -> tuple[Project, Any, Path]:
        (tmp_path / name).mkdir()
        p = sample_project(tmp_path / name)
        lab = launching(p, tmp_path / name, monkeypatch)
        sync = tmp_path / name / "sync"
        sync.mkdir(exist_ok=True)
        lab.script("default", [{"do": "wait_file", "path": str(sync / "release"), "ready": str(sync / "ready")}])
        return p, lab, sync

    def live(p: Project, wid: str, role: str) -> str:
        """The live run of ``role`` the projection shows, which its wait names."""
        projection.clear_cache()
        found = projection.project(Engine.discover(p.root), CTX, wid)
        [run] = [r["run"] for r in found["runs"] if r["role"] == role and r["status"] in K.LIVE_RUNS]
        assert [a["arguments"]["runs"] for a in found["actions"] if a["kind"] == contract.WAIT] == [[run]]
        return run

    p, lab, sync = lab_project("dispatched")
    try:
        wid = create_planned_ticket(p, tmp_path / "dispatched")
        implement(assign(p, wid))
        p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        look(p, wid, "REVIEW_PENDING, no report and no live run, a harness routed")
        follow_next(p, seen["REVIEW_PENDING, no report and no live run, a harness routed"], "invoke", "create")
        lab.until(lambda: (sync / "ready").exists(), "wait.condition", what="the reviewer to start")
        run = live(p, wid, "reviewer")
        (sync / "release").touch()
        lab.wait(run)
    finally:
        lab.cleanup()

    p, lab, sync = lab_project("launched")
    try:
        wid = create_planned_ticket(p, tmp_path / "launched")
        p.lead("work", "assign", wid)  # no `--launch`: an implementer no harness was launched for
        look(p, wid, "ASSIGNED, never launched")
        follow_next(p, seen["ASSIGNED, never launched"], "harness", "launch")  # the launch first, as the hint says
        lab.until(lambda: (sync / "ready").exists(), "wait.condition", what="the implementer to start")
        run = live(p, wid, "implementer")
        look(p, wid, "ASSIGNED, launched")
        assert "harness.launch" not in offers(seen["ASSIGNED, launched"]), "a live run is never offered a launch"
        follow_next(p, seen["ASSIGNED, launched"], "work", "transition")
        (sync / "release").touch()
        lab.wait(run)
        look(p, wid, "RUNNING, its run ended with no report")
    finally:
        lab.cleanup()

    # No execution profile (workers run by hand): the dispatch's launch has no harness, so it is no exit, and the
    # blocker says what to configure.
    (tmp_path / "by-hand").mkdir()
    p = sample_project(tmp_path / "by-hand")
    wid = create_planned_ticket(p, tmp_path / "by-hand")
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    look(p, wid, "REVIEW_PENDING, no report, no execution profile")
    [offered_] = [a["cli_fallback"] for a in seen["REVIEW_PENDING, no report, no execution profile"]["actions"]
                  if a["action"] == "invoke.create.mutating"]
    tried = p.aew(*offered_, env={"AEW_LEAD_TOKEN": p.token})  # run as offered, it is refused: the BLOCKED is true
    assert tried.returncode != 0 and "has no execution profile" in tried.stdout + tried.stderr, tried

    routed("routed-clean", "pass", "COMMIT_READY, prepared, entry VALIDATED")
    routed("routed-failing", "fail", "COMMIT_READY, prepared, entry awaits the Lead on a report that is not clean")
    return seen


def test_every_non_terminal_state_offers_an_exit_or_is_pinned_with_its_reason(tmp_path, monkeypatch, custody):  # noqa: F811
    seen = walk(tmp_path, monkeypatch, custody)
    assert "PUBLISH" in offers(seen["COMMIT_READY, prepared, entry VALIDATED"])
    assert differences(seen, DEAD_ENDS, MOST_DEAD_ENDS) == []
    assert lands(seen) == []
    # What each state E233 took off the list is offered, by name, and what follows the moves the walk made.
    for label, move in {"ASSIGNED": "work.transition", "REVIEW_FAILED": "work.transition",
                        "VERIFICATION_INCONCLUSIVE": "work.transition", "ESCALATED": "work.transition",
                        "REVIEW_PENDING, no report and no live run": "invoke.create.mutating",
                        "VERIFY_PENDING, no report and no live run": "invoke.create.mutating",
                        "COMMIT_READY, prepared with no report": "invoke.create.mutating",
                        "RUNNING, sent back with findings": "invoke.create.mutating",
                        "VERIFY_PENDING, returned from an inconclusive verification": "invoke.create.mutating",
                        "ASSIGNED, never launched": "harness.launch",
                        "RUNNING, its run ended with no report": "harness.launch"}.items():
        assert move in offers(seen[label]), (label, seen[label]["actions"])
    # The launch comes first where an implementer was never launched, and the next step is the launch (F1).
    assert [a["action"] for a in seen["ASSIGNED, never launched"]["actions"]][:2] == ["harness.launch",
                                                                                       "work.transition"]
    # With no execution profile the dispatch is refused at its launch, so it is BLOCKED and says what to configure.
    by_hand = seen["REVIEW_PENDING, no report, no execution profile"]
    [refused] = [a for a in by_hand["actions"] if a["action"] == "invoke.create.mutating"]
    assert refused["availability"] == "BLOCKED" and refused["reason_codes"] == ["ILLEGAL_TRANSITION"], refused
    assert any("configure policy/execution.yaml" in b["message"] for b in by_hand["blockers"]), by_hand["blockers"]
    dispatches = {label: a["arguments"] for label, found in seen.items() for a in found["actions"]
                  if a["action"] == "invoke.create.mutating"}
    assert dispatches["VERIFY_PENDING, no report and no live run"] == {
        "work_id": seen["VERIFY_PENDING, no report and no live run"]["subject"], "role": "verifier", "scope": "ticket"}
    assert dispatches["COMMIT_READY, prepared with no report"]["scope"] == "integration"
    # One owner: a move's command is the one the engine's hint for the Ticket names, at this projection's revision.
    for label, found in seen.items():
        for a in found["actions"]:
            if a["kind"] == contract.PRIMITIVE:
                words = list(a["cli_fallback"])
                if "--prior-value" in words:  # the binding to the state or run it was offered on, which no hint prints
                    del words[words.index("--prior-value"):words.index("--prior-value") + 2]
                rev = words.index("--expect-rev")
                printed = "aew " + " ".join([*words[:rev], K.EXPECT_REV, *words[rev + 2:]])
                assert any(f"`{printed}`" in hint for hint in found["hints"]), (label, printed, found["hints"])
    # A return or a regression carries the Lead's reason: judgment-bearing, so never a stage runner's to take.
    for found in seen.values():
        for a in found["actions"]:
            if a["kind"] == contract.PRIMITIVE:
                assert not a["auto_runnable"] and not a["callable"], a
                assert (a["operation_class"] == "JUDGMENT_BEARING") == ("<reason>" in a["cli_fallback"]), a
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
    blocked = {**open_exit, "actions": [{"action": "ticket_start", "kind": contract.STAGE, "availability": "BLOCKED"}],
               "decisions_required": [{"decision": "PUBLISH", "tool": "integration_publish", "cli_fallback": ["x"],
                                       "availability": "BLOCKED"}]}
    assert offers(blocked) == [], "what its guard refuses is not an exit"
    # An exit that does not land: a command the CLI does not take as offered, and one no Lead session reaches.

    def offering(argv: list[str]) -> dict[str, Any]:
        return {"READY": {**open_exit, "actions": [{"action": "work.transition", "cli_fallback": argv}]}}
    assert lands(offering(["work", "transition", "T-0001", "--to", "RUNNING", "--expect-rev", "3"])) == []
    [incomplete] = lands(offering(["work", "transition", "T-0001", "--expect-rev", "3"]))
    assert incomplete.startswith("READY: work.transition offers `aew work transition T-0001 --expect-rev 3`, which "
                                 "does not run as offered")
    [unfilled] = lands(offering(["work", "transition", "T-0001", "--to", "<somewhere>", "--expect-rev", "3"]))
    assert "a placeholder that is not in PLACEHOLDERS" in unfilled
    assert lands(offering(["lead", "release", "--expect-rev", "3"])) == [
        "READY: work.transition offers `aew lead release --expect-rev 3`, which no Lead session reaches"]
    decided = {"READY": {**open_exit, "actions": [], "decisions_required": [
        {"decision": "PUBLISH", "cli_fallback": ["integrate", "publish", "--expect-rev", "3"]}]}}
    assert [x.split(":")[1].strip().split(" ")[0] for x in lands(decided)] == ["PUBLISH"], "a decision's command too"
