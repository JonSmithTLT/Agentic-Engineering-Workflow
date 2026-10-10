"""The Ticket stages `ticket_draft` and `ticket_start` (M4-E E5a; plan v3 E5, §10; typed Lead surface design v0.2
§3.1, §3.4).

Each runs through ``run_tool`` exactly as a Lead's call would, against a real project; `ticket_start`'s launch is real
(the fake harness's configured execution policy and a real supervisor). Covered here: what each stage commits and
records, `dispatch.launch` as the step its assignment's commit records (plan v3 §1 and N4: run 1 of the dispatch,
covered by its decision), the stops a launch can end in, stage/primitive equivalence on two copies of one project
(§10), and the side effects each newly declared primitive is observed to have against its declaration (SAE-07)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project
from conftest import Project
from fake_harness import contains_credential
from invariants import assert_control_invariants, load_control
from stage_equivalence import differences, end_state
from test_stage_resolve import resolve, unfinished
from test_stage_runner import call, intent, launching

from aew.engine import faults, harness_ops
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.engine.primitives import spec_for
from aew.errors import IllegalTransition
from aew.harness import runlog

DRAFT: dict[str, Any] = {
    "title": "Add subtract()", "risk_class": 1, "scope": ["calc/**", "tests/**"],
    "goal": ["calc.core.subtract(5, 3) == 2 through the public module"],
    "contract": ["changes stay within calc/ and tests/"],
    "plan": {"body": "1. Add subtract(a, b) to calc/core.py.\n", "affected": ["calc/core.py"], "assurance": "none"}}
HANG = [{"do": "hang"}]  # the implementer's run stays live, and touches nothing, until the test ends it


def control(p: Project) -> dict[str, Any]:
    return load_control(p.root)


def unit(p: Project, wid: str) -> dict[str, Any]:
    return control(p)["work"][wid]


# ---------------------------------------------------------------------------------------------- ticket_draft


def test_ticket_draft_creates_the_ticket_and_proposes_its_plan(tmp_path):
    p = sample_project(tmp_path)
    out = call(p, "ticket_draft", **DRAFT)
    assert out["ok"], out["stopped"]
    assert out["effective_operation_class"] == "JUDGMENT_BEARING"
    assert [s["primitive"] for s in out["completed_steps"]] == ["work.create", "plan.propose"]
    si = intent(p, out)
    wid = si["subject"]["id"]
    assert si["status"] == SI.COMPLETED and si["subject"]["kind"] == "unit" and si["steps"][0]["outputs"]["units"] == [
        wid]
    t = unit(p, wid)
    # Proposed, never accepted: the Ticket waits for the Lead's acceptance (`plan accept`), outside this stage.
    assert t["state"] == "BLOCKED" and t["plan"] is None and [x["status"] for x in t["plans"]] == ["proposed"]
    assert t["stage_intents"][0]["id"] == si["id"]  # its cold record is the new unit's (§2.7)
    assert out["projection"]["subject"] == wid  # the result projects the Ticket it created
    assert_control_invariants(p)


def test_ticket_draft_without_a_plan_plans_only_the_creation(tmp_path):
    p = sample_project(tmp_path)
    out = call(p, "ticket_draft", **{k: v for k, v in DRAFT.items() if k != "plan"})
    assert out["ok"], out["stopped"]
    si = intent(p, out)
    assert [s["primitive"] for s in si["plan"]] == ["work.create"] and si["status"] == SI.COMPLETED
    assert unit(p, si["subject"]["id"])["plans"] == []


def test_a_refused_plan_stops_the_draft_after_the_ticket_it_created(tmp_path):
    """Rule 3: the plan's assurance names a card that does not exist, so `plan.propose` refuses; the Ticket step 1
    created stands (committed steps are never undone) with no plan, and the stage stops at step 2."""
    p = sample_project(tmp_path)
    bad = {**DRAFT, "plan": {**DRAFT["plan"], "assurance": {"review": ["no_such_card"]}}}
    out = call(p, "ticket_draft", **bad)
    assert not out["ok"] and out["stopped"]["at"] == "plan.propose" and out["stopped"]["boundary"] in (
        "refused", "not_found"), out["stopped"]
    si = intent(p, out)
    assert si["status"] == SI.STOPPED and si["stopped"]["n"] == 2 and len(si["steps"]) == 1
    t = unit(p, si["subject"]["id"])
    assert t["state"] == "BLOCKED" and t["plans"] == []
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- ticket_start


@pytest.fixture
def ready(tmp_path, monkeypatch):
    """A READY mutating Ticket in a project whose execution policy launches the fake harness's scripted agent."""
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    lab.script("default", HANG)
    wid = create_planned_ticket(p, tmp_path)
    yield p, lab, wid
    lab.cleanup()


def test_ticket_start_assigns_launches_and_moves_the_ticket_to_running(ready):
    """Three steps in two commits: the assignment's commit records run 1 as the `dispatch.launch` step (covered by
    its decision, plan v3 §1), its run goes to its supervisor, and then ASSIGNED -> RUNNING completes the stage."""
    p, lab, wid = ready
    out = call(p, "ticket_start", work_id=wid)
    assert out["ok"], out["stopped"]
    assert out["effective_operation_class"] == "POLICY_RESOLVED"
    si = intent(p, out)
    assign, launch, transition = si["steps"]
    assert (assign["primitive"], launch["primitive"], transition["primitive"]) == (
        "work.assign", "dispatch.launch", "work.transition")
    assert launch["covered_by"] == 1 and launch["revision"] == assign["revision"] < transition["revision"]
    inv = unit(p, wid)["implementer_invocation"]
    [run] = control(p)["invocations"][inv]["runs"]
    assert assign["outputs"] == {"units": [], "invocations": [inv], "runs": []}
    assert launch["outputs"] == {"units": [], "invocations": [], "runs": [run["run"]]}
    assert run["dispatch"]["entrypoint"] == "dispatch.launch" and run["dispatch"]["covered_by"] == "work.assign"
    assert si["status"] == SI.COMPLETED and unit(p, wid)["state"] == "RUNNING"
    assert runlog.observed_status(runlog.run_dir(p.root / ".aew", run["run"]))[0] in ("starting", "running")
    assert [s["primitive"] for s in out["completed_steps"]] == ["work.assign", "dispatch.launch", "work.transition"]
    assert not contains_credential(str(out))
    assert_control_invariants(p)


def test_an_execution_override_makes_the_start_judgment_bearing(ready):
    p, lab, wid = ready
    out = call(p, "ticket_start", work_id=wid, execution={"profile": "standard"})
    assert out["ok"], out["stopped"]
    assert out["effective_operation_class"] == "JUDGMENT_BEARING"
    assert intent(p, out)["judgment_inputs"] == ["execution"]


def test_a_launch_that_fails_stops_the_start_before_running(ready, monkeypatch):
    """Rule 7: the assignment and run 1 committed, the run's supervisor could not start, so the stage stops as
    launch_failed at the transition. The Ticket stays ASSIGNED: never RUNNING over a run that never started."""
    p, lab, wid = ready

    def no_process(*_, **__):
        raise OSError("no process slot")

    monkeypatch.setattr(harness_ops.procs, "spawn_detached", no_process)
    out = call(p, "ticket_start", work_id=wid)
    assert not out["ok"] and out["stopped"]["boundary"] == "launch_failed" and out["stopped"]["at"] == "work.assign"
    si = intent(p, out)
    assert si["status"] == SI.STOPPED and si["stopped"]["n"] == 3 and len(si["steps"]) == 2
    assert unit(p, wid)["state"] == "ASSIGNED"
    assert_control_invariants(p)


def test_a_start_that_crashed_before_its_supervisor_continues_only_to_launch_failed(ready, monkeypatch):
    """A crash between the assignment's commit and its supervisor's start leaves the intent ACTIVE with both the
    assignment and its launch recorded. `resume` says a continue would stop at launch_failed, and it does: the
    transition to RUNNING is never run over a run that never started, and the continue never relaunches."""
    p, lab, wid = ready
    monkeypatch.setenv("AEW_FAULT", "harness.launch.after_commit")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(faults.InjectedFault):
        call(p, "ticket_start", work_id=wid)
    monkeypatch.delenv("AEW_FAULT")
    [sid] = list(control(p)["stage_intents"])
    row = unfinished(p)[sid]
    assert row["steps_committed"] == 2 and row["boundary"] == "launch_failed" and not row["safe_to_continue"]
    out = resolve(p, sid, "continue")
    assert not out["ok"] and out["stopped"]["boundary"] == "launch_failed"
    assert Engine.discover(p.root).stage_intent(sid)["status"] == SI.STOPPED and unit(p, wid)["state"] == "ASSIGNED"
    assert_control_invariants(p)


@pytest.mark.parametrize(("plan", "why"), [
    ([{"primitive": "checkpoint", "args": {}}, {"primitive": "dispatch.launch", "args": {}}], "after a checkpoint"),
    ([{"primitive": "work.assign", "args": {"work_id": "T-0001"}}, {"primitive": "dispatch.launch", "args": {}}],
     "after an assignment made without launch"),
    ([{"primitive": "dispatch.launch", "args": {}}], "first"),
], ids=["checkpoint", "no_launch", "first"])
def test_a_launch_is_planned_only_after_a_dispatch_made_with_launch(tmp_path, plan, why):
    """`dispatch.launch` has no commit of its own (plan v3 §1): a plan that names it anywhere but after a dispatch made
    with `launch` is refused when the intent opens, and nothing commits."""
    p = sample_project(tmp_path)
    create_planned_ticket(p, tmp_path)
    e = Engine.discover(p.root)
    rev = int(e.store.read()["revision"])
    with pytest.raises(IllegalTransition) as exc:
        e.stage_open(token=p.token, expect_rev=rev, tool="probe", contract_digest="x", arguments={},
                     judgment_inputs=[], base_class="POLICY_RESOLVED", effective_class="POLICY_RESOLVED", plan=plan,
                     subject=None, ingress="test")
    assert exc.value.details["reason"] == "not_covered", why
    assert int(e.store.read()["revision"]) == rev


# ---------------------------------------------------------------------------------------------- equivalence (§10)


def _twins(tmp_path: Path, prepare: Callable[[Project], None]) -> tuple[Project, Project]:
    """Two identical projects: one prepared, then copied whole (its repository, history and control state), so their
    commits, ids and credentials are the same and only their locations differ."""
    first = sample_project(tmp_path / "stage")
    prepare(first)
    second = tmp_path / "primitives" / "repo"
    shutil.copytree(first.root, second)
    return first, Project(second, first.token)


@pytest.mark.parametrize("name", ["ticket_draft", "ticket_start"])
def test_stage_matches_primitives(tmp_path, monkeypatch, name):
    """Plan v3 §10 (fake harness): a stage and its primitives run directly, with the same arguments, end in the same
    state, compared without the journal's own records (``stage_equivalence``)."""
    labs = []

    def prepare(p: Project) -> None:
        if name == "ticket_start":
            labs.append(launching(p, tmp_path, monkeypatch))
            labs[0].script("default", HANG)
            create_planned_ticket(p, tmp_path)

    staged, direct = _twins(tmp_path, prepare)
    try:
        e = Engine.discover(direct.root)

        def rev() -> int:
            return int(e.store.read()["revision"])

        if name == "ticket_draft":
            assert call(staged, "ticket_draft", **DRAFT)["ok"]
            made = e.work_create(token=direct.token, expect_rev=rev(), kind="ticket", title=DRAFT["title"],
                                 risk_class=1, mutating=True, scope_paths=DRAFT["scope"], goal_backwards=DRAFT["goal"],
                                 contract=DRAFT["contract"], body="")
            e.plan_propose(token=direct.token, expect_rev=rev(), work_id=made["id"], body=DRAFT["plan"]["body"],
                           affected_paths=DRAFT["plan"]["affected"], no_assurance=True)
        else:
            out = call(staged, "ticket_start", work_id="T-0001")
            assert out["ok"], out["stopped"]
            e.launch_dispatched(e.work_assign(token=direct.token, expect_rev=rev(), work_id="T-0001", launch=True))
            e.work_transition(token=direct.token, expect_rev=rev(), work_id="T-0001", to="RUNNING")
        a, b = end_state(staged.root), end_state(direct.root)
        assert differences(a, b) == [], "\n".join(differences(a, b))
    finally:
        for lab in labs:
            lab.cleanup()
            if name == "ticket_start":  # the copy's runs are its own: end them the same way
                lab.project = direct
                lab.cleanup()


# ---------------------------------------------------------------------------------------------- side effects (SAE-07)


def _observe(p: Project) -> dict[str, Any]:
    """What each declared effect class covers, as observable now (``PrimitiveSpec.side_effect_class``)."""
    e = Engine.discover(p.root)
    state = e.store.read()
    ws = e._k.workspaces_root()
    runs = p.root / ".aew" / runlog.RUNS_REL
    return {"control_state": json.dumps(state, sort_keys=True, default=str),
            "credential": (repr(sorted(state["tokens"].items())),
                           sorted((r["run"], r.get("token_id")) for inv in state["invocations"].values()
                                  for r in inv.get("runs") or [])),
            "workspace": sorted(x.name for x in ws.iterdir()) if ws.is_dir() else [],
            "harness_process": sorted(x.name for x in runs.iterdir() if (x / "supervisor.log").exists())
            if runs.is_dir() else [],
            "authoritative_ref": e.authoritative_commit()}  # the integration branch's head


def _effects(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    return {k for k in before if before[k] != after[k]}


def _declared(primitive: str) -> set[str]:
    return set(spec_for(primitive).side_effect_class.split("+"))


@pytest.mark.parametrize("primitive", ["work.create", "plan.propose", "work.transition", "dispatch.launch"])
def test_declared_effects_cover_observed_effects(tmp_path, monkeypatch, primitive):
    """A1 §6 / SAE-07, per primitive E5a stages: what running it is observed to change never exceeds what its
    PrimitiveSpec declares. `dispatch.launch` is observed as what an assignment made with launch changes beyond the
    same assignment made without (two copies of one project), since it commits in its dispatch's transaction."""
    labs = []

    def prepare(p: Project) -> None:
        labs.append(launching(p, tmp_path, monkeypatch))
        labs[0].script("default", HANG)
        create_planned_ticket(p, tmp_path)

    p, twin = _twins(tmp_path, prepare)
    e = Engine.discover(p.root)
    tok = p.token

    def rev() -> int:
        return int(e.store.read()["revision"])

    try:
        if primitive == "dispatch.launch":
            Engine.discover(twin.root).work_assign(token=tok, expect_rev=int(Engine.discover(twin.root).store.read()[
                "revision"]), work_id="T-0001")
            before = _observe(p)
            e.launch_dispatched(e.work_assign(token=tok, expect_rev=rev(), work_id="T-0001", launch=True))
            launched = _effects(before, _observe(p))
            assert launched <= _declared("work.assign") | _declared("dispatch.launch"), launched
            beyond = _effects(_observe(twin), _observe(p))  # the same assignment, with and without its launch
            assert beyond <= _declared("dispatch.launch") and "harness_process" in beyond, beyond
            return
        before = _observe(p)
        if primitive == "work.create":
            e.work_create(token=tok, expect_rev=rev(), kind="ticket", title="Another", risk_class=1)
        elif primitive == "plan.propose":
            e.plan_propose(token=tok, expect_rev=rev(), work_id="T-0001", body="2. Another revision.\n",
                           reason="a second plan", no_assurance=True)
        else:
            e.work_assign(token=tok, expect_rev=rev(), work_id="T-0001")
            before = _observe(p)
            e.work_transition(token=tok, expect_rev=rev(), work_id="T-0001", to="RUNNING")
        seen = _effects(before, _observe(p))
        assert "control_state" in seen and seen <= _declared(primitive), seen
        if primitive == "work.transition":  # a cancellation revokes the attempt's credentials: declared, and observed
            before = _observe(p)
            e.work_transition(token=tok, expect_rev=rev(), work_id="T-0001", to="CANCELLED", reason="not needed")
            seen = _effects(before, _observe(p))
            assert seen <= _declared(primitive) and "credential" in seen, seen
    finally:
        for lab in labs:
            lab.cleanup()
