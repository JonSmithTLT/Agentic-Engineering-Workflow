"""Resuming and resolving an unfinished stage (M4-E E3c; plan v3 E3; typed Lead surface design v0.2 §3.4 rule 8).

A stage left ACTIVE (its executor crashed, its seat was lost) is listed by ``resume`` with whether a continue would
pass its rechecks now, and settled only by the current Lead's explicit ``resolve`` (or ``aew stage continue|abandon``):
never inferred from state. The probes are test_stage_runner's: catalogue rows and planners registered for the test
alone, over the primitives that have step runners. A crash is a fault raised mid-call (a ``BaseException``, so nothing
in the executor records a stop), leaving exactly the durable state a dead process leaves."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from aewflow import create_planned_ticket, sample_project
from fake_harness import contains_credential
from invariants import assert_control_invariants, load_control
from stage_equivalence import differences, end_state
from test_stage_runner import PROBES, call, hot, intent, intervene, launching

import aew.operator
from aew.engine import faults, harness_ops
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.errors import StaleAuthority
from aew.harness import runlog
from aew.surface import contract, stage
from aew.surface import run as R
from aew.surface.context import SurfaceContext
from aew.surface.validate import AdapterInputError, check_call

CTX = SurfaceContext.outside_session()


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name, (row, planner) in PROBES.items():
        monkeypatch.setitem(contract.TOOLS, name, row)
        monkeypatch.setitem(stage.STAGES, name, planner)
    return sample_project(tmp_path)


def resolve(p, sid: str, choice: str, *, token: str | None = None, rationale: str = "the stage is still wanted",
            **extra: Any) -> dict[str, Any]:
    arguments = {"expect_rev": p.rev(), "subject": sid, "choice": choice, "rationale": rationale, **extra}
    return R.run_tool(Engine.discover(p.root), CTX, "resolve", arguments, token=token or p.token)


def unfinished(p) -> dict[str, dict[str, Any]]:
    out = R.run_tool(Engine.discover(p.root), CTX, "resume", {})
    assert out["ok"], out["stopped"]
    return {s["intent"]: s for s in out["result"]["stage_intents"]}


def crash_at(monkeypatch, primitive: str, *, call_no: int = 1) -> None:
    """The process dies as step runner ``primitive`` is entered for the ``call_no``-th time: the steps before it have
    committed, and nothing after it runs or is recorded."""
    real = stage.STEP_RUNNERS[primitive]
    calls = [0]

    def dying(c, args, rev):
        calls[0] += 1
        if calls[0] == call_no:
            raise faults.InjectedFault(f"crash before {primitive}")
        return real(c, args, rev)

    monkeypatch.setitem(stage.STEP_RUNNERS, primitive, dying)


def crashed_stage(p, monkeypatch, name: str, primitive: str, *, call_no: int = 1, **arguments: Any) -> str:
    """Run stage ``name`` until the process dies at ``primitive``; returns the intent it leaves ACTIVE."""
    crash_at(monkeypatch, primitive, call_no=call_no)
    with pytest.raises(faults.InjectedFault):
        call(p, name, **arguments)
    monkeypatch.undo()  # the restart: a new process, with the real step runners and the probes registered again
    for probe, (row, planner) in PROBES.items():
        monkeypatch.setitem(contract.TOOLS, probe, row)
        monkeypatch.setitem(stage.STAGES, probe, planner)
    [sid] = list(hot(p))
    return sid


def take_over(p) -> str:
    """The operator takes the seat over (a new generation); returns the new Lead's credential."""
    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        return Engine.discover(p.root).lead_takeover(expect_rev=p.rev(), reason="the Lead's session was lost",
                                                     session_label="lead-b")["token"]
    finally:
        aew.operator.authorize = original


# ---------------------------------------------------------------------------------------------- resume


def test_resume_lists_an_unfinished_stage_with_its_rechecks(project, monkeypatch):
    """`resume` lists each nonterminal intent: safe_to_continue (every recheck passes now), the policy and guard
    status, the next planned step and boundary, and the owning generation; `aew resume` lists the same."""
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    row = unfinished(p)[sid]
    assert row["safe_to_continue"] is True and row["failing"] == [] and row["boundary"] is None
    assert (row["steps_committed"], row["steps_planned"]) == (1, 2)
    assert row["next_step"]["n"] == 2 and row["next_step"]["primitive"] == "checkpoint"
    assert row["policy"]["status"] == "ok" and row["checks"]["guard"]["status"] == "not_queryable"
    assert (row["owner_generation"], row["current_generation"], row["rebind"]) == (1, 1, False)
    assert set(row["checks"]) == {"policy", "contract", "runners", "subject", "launch", "rebinds", "guard"}
    assert row["unknown_checks"] == ["guard"]  # counted as passing, and named (#166 review, finding 6)
    projection = R.run_tool(Engine.discover(p.root), CTX, "status", {})["projection"]
    [decision] = [d for d in projection["decisions_required"] if d["decision"] == "RESOLVE_STAGE"]
    assert decision["tool"] == "resolve" and decision["evidence"] == [sid] and decision["default"] == "NONE"
    assert decision["arguments"] == {"expect_rev": p.rev(), "subject": sid}  # no choice: never a default
    cli = p.ok("resume", "--json")  # another process, where the test's probe stage does not exist
    assert [s["intent"] for s in cli["stage_intents"]] == [sid] and cli["stage_intents"][0]["failing"] == ["contract"]
    assert cli["stage_intents"][0]["checks"]["contract"]["status"] == "unknown_stage"
    assert "no longer has a stage probe_notes" in cli["stage_intents"][0]["checks"]["contract"]["message"]
    assert any(sid in a and "aew stage continue|abandon" in a for a in cli["next_actions"])
    assert sid in p.aew("resume").stdout  # the rendered view names it too
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- continue and abandon


def test_continue_runs_the_stage_from_its_first_uncommitted_step(project, monkeypatch):
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    first = hot(p)[sid]["steps"][0]
    out = resolve(p, sid, "continue")
    assert out["ok"], out["stopped"]
    si = Engine.discover(p.root).stage_intent(sid)
    assert si["status"] == "COMPLETED" and [s["key"] for s in si["steps"]] == [f"{sid}:1", f"{sid}:2"]
    assert si["steps"][0] == first  # the committed step was never run again
    assert si["rebound"] == [{**si["rebound"][0], "from_generation": 1, "to_generation": 1,
                              "rationale": "the stage is still wanted"}]
    assert si["resolution"]["choice"] == "continue" and si["resolution"]["rev"] == si["rebound"][0]["rev"]
    assert out["stage_intent_id"] == sid and out["tool"] == "resolve"
    assert out["effective_operation_class"] == "JUDGMENT_BEARING"
    assert [s["primitive"] for s in out["completed_steps"]] == ["checkpoint", "checkpoint"]
    assert load_control(p.root)["next_action"] == "done" and hot(p) == {}
    assert_control_invariants(p)


def test_abandon_closes_the_intent_and_never_undoes_a_committed_step(project, monkeypatch):
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    out = resolve(p, sid, "abandon", rationale="no longer wanted")
    assert out["ok"] and out["result"]["status"] == "ABANDONED", out["stopped"]
    si = Engine.discover(p.root).stage_intent(sid)
    assert si["status"] == "ABANDONED" and len(si["steps"]) == 1 and si["rebound"] == []
    assert si["resolution"]["rationale"] == "no longer wanted"
    assert load_control(p.root)["next_action"] == "step 2"  # step 1's effect stands
    again = resolve(p, sid, "continue")
    assert not again["ok"] and again["stopped"]["boundary"] == "not_found"  # an ended stage is never continued
    assert_control_invariants(p)


def test_takeover_mid_stage_needs_explicit_continue(project, monkeypatch):
    """TLS-26 / F18 §14: a stage left by a superseded generation is never continued implicitly. The new Lead cannot
    stack another stage on it or commit its next step; `resume` names the owner; only its explicit continue rebinds
    the intent to the new generation, and the remaining step then runs."""
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    p.token = take_over(p)
    stacked = call(p, "probe_notes")
    assert not stacked["ok"] and stacked["stopped"]["error"]["details"]["reason"] == "open_intent"
    with pytest.raises(StaleAuthority) as exc, SI.step(sid, 2, final=True):
        Engine.discover(p.root).checkpoint(token=p.token, expect_rev=p.rev(), note="implicit")
    assert exc.value.details["reason"] == "not_owner"
    row = unfinished(p)[sid]
    assert (row["owner_generation"], row["current_generation"], row["rebind"]) == (1, 2, True)
    assert row["safe_to_continue"]
    out = resolve(p, sid, "continue", rationale="the new Lead still wants it")
    assert out["ok"], out["stopped"]
    si = Engine.discover(p.root).stage_intent(sid)
    assert si["status"] == "COMPLETED" and si["generation"] == 2
    assert [(r["from_generation"], r["to_generation"]) for r in si["rebound"]] == [(1, 2)]
    assert_control_invariants(p)


@pytest.mark.parametrize("intervening", ["on_another_subject", "on_the_subject"])
def test_continue_after_an_intervening_primitive(project, tmp_path, monkeypatch, intervening):
    """TIS-32: a primitive issued after the crash and before the continuation. One that leaves the stage's unit as
    its last step left it lets the stage continue; one that moved the unit makes the continue refuse
    (``subject_moved``) with nothing committed, and the stage is then abandoned, never inferred complete."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    sid = crashed_stage(p, monkeypatch, "probe_start", "work.assign", work_id=wid)
    if intervening == "on_the_subject":
        p.lead("work", "assign", wid)
    else:
        p.lead("checkpoint", "--next", "something else")
    row = unfinished(p)[sid]
    rev = p.rev()
    out = resolve(p, sid, "continue")
    if intervening == "on_another_subject":
        assert row["safe_to_continue"] and row["checks"]["guard"]["status"] == "ok"
        assert out["ok"], out["stopped"]
        assert Engine.discover(p.root).stage_intent(sid)["status"] == "COMPLETED"
        assert load_control(p.root)["work"][wid]["state"] == "ASSIGNED"
    else:
        assert not row["safe_to_continue"] and row["failing"] == ["subject"] and row["boundary"] == "refused"
        assert row["checks"]["subject"]["status"] == "moved"
        assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "subject_moved"
        assert p.rev() == rev and hot(p)[sid]["status"] == "ACTIVE" and hot(p)[sid]["rebound"] == []
        assert resolve(p, sid, "abandon", rationale="the Ticket moved on")["ok"]
    assert_control_invariants(p)


def test_continue_is_refused_while_the_next_steps_guard_refuses_it(project, tmp_path, monkeypatch):
    """The gates: the next step's dispatch decision is asked before anything commits. Another Ticket took the only
    mutating slot, so the stage's assignment is BLOCKED now: the continue refuses and the intent is unchanged."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    other = create_planned_ticket(p, tmp_path, title="Add multiply()")
    sid = crashed_stage(p, monkeypatch, "probe_start", "work.assign", work_id=wid)
    p.lead("work", "assign", other)  # mutating_concurrency 1: the slot is taken
    row = unfinished(p)[sid]
    assert row["checks"]["guard"]["status"] == "blocked" and not row["safe_to_continue"]
    rev = p.rev()
    out = resolve(p, sid, "continue")
    assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "next_step_blocked"
    assert p.rev() == rev and hot(p)[sid]["rebound"] == []
    assert_control_invariants(p)


def test_a_continued_dispatch_step_still_meets_its_own_dispatch_decision(project, tmp_path, monkeypatch):
    """`aew stage continue` is not a dispatch entrypoint: it reaches dispatch only through the registered primitive of
    each remaining step, whose own commit takes the dispatch decision (the M4-A choke point). With the surface's
    pre-check out of the way (its guard read as not queryable), the assignment's own decision still refuses it: the
    stage stops at that step, nothing is assigned and no invocation is created."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    other = create_planned_ticket(p, tmp_path, title="Add multiply()")
    sid = crashed_stage(p, monkeypatch, "probe_start", "work.assign", work_id=wid)
    p.lead("work", "assign", other)  # mutating_concurrency 1: the slot is taken
    monkeypatch.setattr(stage, "guard_check", lambda engine, primitive, args: {
        "status": stage.UNKNOWN_STATUS, "reason_codes": ["GUARD_NOT_QUERYABLE"], "availability": "UNKNOWN",
        "message": "read as not queryable"})
    invocations = set(load_control(p.root)["invocations"])
    out = resolve(p, sid, "continue")
    assert not out["ok"] and out["stopped"]["at"] == "work.assign", out["stopped"]
    assert out["stopped"]["boundary"] == "refused"
    si = Engine.discover(p.root).stage_intent(sid)
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 1 and si["rebound"]
    state = load_control(p.root)
    assert state["work"][wid]["state"] == "READY" and set(state["invocations"]) == invocations
    assert_control_invariants(p)


@pytest.mark.parametrize("change", ["contract", "plan", "gone"])
def test_continue_re_resolves_the_stage_contract(project, monkeypatch, change):
    """A stage contract that changed since the intent opened (a new schema), a planner that now plans other steps for
    the same call, or a stage this surface no longer has: the continue refuses with nothing committed."""
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    row, planner = PROBES["probe_notes"]
    if change == "contract":
        schema = contract._obj({**row.input_schema["properties"], "extra": {"type": "string"}}, ("expect_rev",))
        monkeypatch.setitem(contract.TOOLS, "probe_notes", row._replace(input_schema=schema))
    elif change == "plan":
        monkeypatch.setitem(stage.STAGES, "probe_notes", lambda a: [{**s, "args": {**s["args"], "next": "other"}}
                                                                     for s in planner(a)])
    else:
        monkeypatch.delitem(stage.STAGES, "probe_notes")
    assert unfinished(p)[sid]["checks"]["contract"]["status"] == {
        "contract": "changed", "plan": "plan_changed", "gone": "unknown_stage"}[change]
    rev = p.rev()
    out = resolve(p, sid, "continue")
    assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "contract_changed"
    assert p.rev() == rev and hot(p)[sid]["status"] == "ACTIVE"


def test_resume_shows_the_bound_call_a_continue_endorses(project, tmp_path, monkeypatch):
    """#166 review, finding 4: a judgment-bearing stage left by generation 1. Before generation 2 endorses it with a
    continue, its `resume` row shows the call: the bound arguments, the judgment inputs and both classes."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    sid = crashed_stage(p, monkeypatch, "probe_judged", "work.assign", work_id=wid)
    p.token = take_over(p)
    bound = hot(p)[sid]
    row = unfinished(p)[sid]
    assert row["arguments"] == bound["arguments"] and row["arguments"]["work_id"] == wid
    assert row["judgment_inputs"] == ["ticket_proposition"] == bound["judgment_inputs"]
    assert (row["base_class"], row["effective_class"]) == ("JUDGMENT_BEARING", "JUDGMENT_BEARING")
    assert row["rebind"] and not contains_credential(str(row))
    out = resolve(p, sid, "continue", rationale="generation 2 read the call and endorses it")
    assert out["ok"], out["stopped"]
    assert_control_invariants(p)


def test_a_remaining_step_with_no_step_runner_is_named_as_such(project, monkeypatch):
    """#166 review, finding 5: the stage still exists, but a remaining step has no step runner here. `resume` says so
    (`runners: no_step_runner`, the contract itself unchanged), and the continue refuses with that reason, committing
    nothing."""
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    monkeypatch.delitem(stage.STEP_RUNNERS, "checkpoint")
    row = unfinished(p)[sid]
    assert row["checks"]["contract"]["status"] == "ok" and row["failing"] == ["runners"]
    assert row["checks"]["runners"]["status"] == "no_step_runner"
    assert row["checks"]["runners"]["primitives"] == ["checkpoint"]
    rev = p.rev()
    out = resolve(p, sid, "continue")
    assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "no_step_runner"
    assert "no step runner here for checkpoint" in out["stopped"]["error"]["message"]
    assert p.rev() == rev and hot(p)[sid]["rebound"] == []


# ---------------------------------------------------------------------------------------------- policy drift


def drift(p) -> None:
    """A legality edit the operator adopts: the legality digest in force moves (each time to a new value)."""
    gates = p.root / ".aew/policy/gates.yaml"
    doc = yaml.safe_load(gates.read_text(encoding="utf-8"))
    doc["mutating_concurrency"] = int(doc.get("mutating_concurrency") or 1) + 1
    gates.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8", newline="\n")
    p.adopt_policy()


def drift_before_continue(p, monkeypatch) -> None:
    """A crash after step 1, a legality change, then the continue: refused as STALE_POLICY, nothing committed; the
    stage is then abandoned."""
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    drift(p)
    row = unfinished(p)[sid]
    assert row["policy"]["status"] == "stale_policy" and row["boundary"] == "stale_policy"
    assert not row["safe_to_continue"] and row["failing"] == ["policy"]
    rev = p.rev()
    out = resolve(p, sid, "continue")
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_policy", out["stopped"]
    assert p.rev() == rev and len(hot(p)[sid]["steps"]) == 1 and hot(p)[sid]["rebound"] == []
    assert resolve(p, sid, "abandon", rationale="its policy moved")["ok"]


def test_policy_drift_between_steps_is_stale_policy(project, monkeypatch):
    """CWR §11 (E3's part): a legality policy adopted between two steps stops the running stage as STALE_POLICY, and
    one adopted between a crash and the continue refuses the continue as STALE_POLICY: in neither case does a step
    run under a policy the stage did not bind."""
    p = project
    seen = intervene(monkeypatch, "checkpoint", times=2, before=lambda c: drift(p) if len(seen) == 2 else None)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_policy", out["stopped"]
    assert intent(p, out)["status"] == "STOPPED_AT_BOUNDARY" and len(intent(p, out)["steps"]) == 1
    drift_before_continue(p, monkeypatch)
    assert_control_invariants(p)


@pytest.mark.parametrize("gap", ["before_step_1", "before_step_2", "before_continue"])
def test_drift_seeded_between_every_substep(project, monkeypatch, gap):
    """TIS-34: a legality change seeded after the stage's expansion and before each substep, and before its
    continuation, stops it as STALE_POLICY with only the steps before the change committed."""
    p = project
    if gap == "before_continue":
        drift_before_continue(p, monkeypatch)
    else:
        committed = 0 if gap == "before_step_1" else 1
        seen = intervene(monkeypatch, "checkpoint", times=2,
                         before=lambda c: drift(p) if len(seen) == committed + 1 else None)
        out = call(p, "probe_notes")
        assert not out["ok"] and out["stopped"]["boundary"] == "stale_policy", out["stopped"]
        si = intent(p, out)
        assert len(si["steps"]) == committed and si["stopped"]["error"]["code"] == "STALE_POLICY"
        assert si["status"] == ("REFUSED" if committed == 0 else "STOPPED_AT_BOUNDARY")
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- the #142 obligations


def crashed_launch(p, tmp_path, monkeypatch, when: str):
    """A launching stage (a checkpoint, then an assignment with launch) whose process dies after the assignment
    committed run 1: before its supervisor started (``never_started``: the credential died with the process), or after
    the launch and before the stage could complete (``live``: the run still runs; ``ended``: its run then ended)."""
    lab = launching(p, tmp_path, monkeypatch)
    wid = create_planned_ticket(p, tmp_path)
    lab.script("default", [{"do": "sleep", "s": 120}] if when == "live" else [{"do": "note", "text": "done"}])
    real_end = stage._end

    def dying(c, record):
        raise faults.InjectedFault("crash before the stage completes")

    if when == "never_started":
        monkeypatch.setenv("AEW_FAULT", "harness.launch.after_commit")
        monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    else:
        monkeypatch.setattr(stage, "_end", dying)
    with pytest.raises(faults.InjectedFault):
        call(p, "probe_start", work_id=wid, launch=True)
    monkeypatch.delenv("AEW_FAULT", raising=False)
    monkeypatch.setattr(stage, "_end", real_end)
    [sid] = list(hot(p))
    si = hot(p)[sid]
    assert si["status"] == "ACTIVE" and len(si["steps"]) == len(si["plan"]) == 2
    [run] = si["steps"][1]["outputs"]["runs"]
    if when == "ended":
        lab.until(lambda: runlog.observed_status(runlog.run_dir(p.root / ".aew", run))[0] not in SI.LIVE_RUN,
                  what=f"{run} to end")
    return lab, wid, sid, run


@pytest.mark.parametrize("when", ["never_started", "ended", "live"])
def test_continue_never_completes_a_stage_over_a_run_that_never_started(project, tmp_path, monkeypatch, when):
    """#142 review, obligation (a): every step of the launching stage committed and run 1 is recorded. Its supervisor
    never started, or its record has ended: the continue stops the intent as ``launch_failed`` in its own commit,
    never COMPLETED, with the run standing, and `resume` says so first. Only a run its supervisor still holds lets
    the continue complete the stage."""
    p = project
    lab, wid, sid, run = crashed_launch(p, tmp_path, monkeypatch, when)
    try:
        row = unfinished(p)[sid]
        if when == "never_started":
            assert runlog.read_record(runlog.run_dir(p.root / ".aew", run)) is None  # no supervisor ever ran
        out = resolve(p, sid, "continue")
        si = Engine.discover(p.root).stage_intent(sid)
        if when == "live":
            assert row["safe_to_continue"] and row["boundary"] == "completed"
            assert out["ok"] and si["status"] == "COMPLETED", out["stopped"]
        else:
            assert not row["safe_to_continue"] and row["boundary"] == "launch_failed" and row["failing"] == ["launch"]
            assert row["checks"]["launch"]["status"] == ("no_supervisor" if when == "never_started" else "not_live")
            assert not out["ok"] and out["stopped"]["boundary"] == "launch_failed", out["stopped"]
            assert out["stopped"]["at"] == "work.assign"
            error = out["stopped"]["error"]
            assert error["code"] == "HARNESS_LAUNCH_FAILED" and error["details"]["run"] == run
            if when == "ended":  # it may have finished its work: no blind relaunch advice (#166 review, finding 3)
                assert "Read `harness_status` and the run's report before deciding" in error["message"]
                assert "the launch failed" not in error["message"]
            else:
                assert "the launch failed. Relaunch it with `aew harness launch`" in error["message"]
            assert error["details"]["committed"] is True
            assert si["status"] == "STOPPED_AT_BOUNDARY" and si["stopped"]["boundary"] == "launch_failed"
            assert si["stopped"]["n"] == 2 and si["resolution"]["choice"] == "continue"
            inv = load_control(p.root)["work"][wid]["implementer_invocation"]
            assert [r["run"] for r in load_control(p.root)["invocations"][inv]["runs"]] == [run]  # it stands
        assert not contains_credential(str(out))
    finally:
        lab.cleanup()
    assert_control_invariants(p)


def test_a_continued_launch_relaunches_only_through_harness_launch_with_a_rotated_credential(
        project, tmp_path, monkeypatch):
    """#142 review, the relaunch rule: the continue never relaunches a run and never uses the credential lost with
    the crashed launcher (it starts no supervisor and records no run). The relaunch is the Lead's `harness.launch`,
    which records run 2 under a rotated credential and revokes run 1's."""
    p = project
    lab, wid, sid, run = crashed_launch(p, tmp_path, monkeypatch, "never_started")
    try:
        inv = load_control(p.root)["work"][wid]["implementer_invocation"]
        lost = load_control(p.root)["invocations"][inv]["token_id"]
        spawned: list[Any] = []
        real_spawn = harness_ops.procs.spawn_detached
        monkeypatch.setattr(harness_ops.procs, "spawn_detached", lambda *a, **k: spawned.append(a) or real_spawn(
            *a, **k))
        out = resolve(p, sid, "continue")
        assert out["stopped"]["boundary"] == "launch_failed" and spawned == []  # no supervisor, no credential use
        after = load_control(p.root)["invocations"][inv]
        assert [r["run"] for r in after["runs"]] == [run] and after["token_id"] == lost
        assert out["projection"] and not contains_credential(str(out))
        lab.script("default", [{"do": "note", "text": "relaunched"}])
        # Run 1 was recorded moments ago with no record yet, so it may still be starting: the relaunch replaces it
        # (`aew harness launch --replace`), revoking its credential either way.
        relaunched = Engine.discover(p.root).harness_launch(token=p.token, expect_rev=p.rev(), invocation=inv,
                                                            replace=True)
        state = load_control(p.root)
        second = state["invocations"][inv]["runs"][-1]
        assert relaunched["run"] == second["run"] != run and second["kind"] == "relaunch" and len(spawned) == 1
        assert second["token_id"] != lost and state["tokens"][lost]["revoked_at"] is not None
        assert "rotated" in state["tokens"][lost]["revoke_reason"]
    finally:
        lab.cleanup()
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- the transports


def test_aew_stage_continue_and_abandon_are_the_resolve_tool(project, monkeypatch):
    """CLI parity (typed surface §5): `aew stage continue|abandon` runs the same runner and returns the same
    StageResult as the typed `resolve`."""
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    res = p.aew("stage", "abandon", sid, "--rationale", "from the shell", "--token", p.token,
                "--expect-rev", str(p.rev()))
    assert res.returncode == 0, res.stderr
    out = res.json
    assert out["surface"] == "aew/surface/v1" and out["tool"] == "resolve" and out["ok"]
    assert out["stage_intent_id"] == sid and out["result"]["status"] == "ABANDONED"
    res = p.aew("stage", "continue", sid, "--rationale", "again", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode == 1 and res.json["stopped"]["boundary"] == "not_found"  # a StageResult, ok false
    blank = p.aew("stage", "abandon", sid, "--rationale", "  ", "--token", p.token, "--expect-rev", str(p.rev()))
    assert blank.returncode != 0 and blank.error["code"] == "INVALID_ARGUMENTS"


def test_a_blank_rationale_is_an_input_error_that_reaches_nothing():
    with pytest.raises(AdapterInputError) as exc:
        check_call("resolve", {"expect_rev": 1, "subject": "SI-0001", "choice": "continue", "rationale": " \n"},
                   "normal")
    assert exc.value.code == "INVALID_ARGUMENTS"
    with pytest.raises(AdapterInputError):
        check_call("resolve", {"expect_rev": 1, "subject": "SI-0001", "choice": "accept_risk", "rationale": "x"},
                   "normal")  # E5's dispositions are not built


# ---------------------------------------------------------------------------------------------- equivalence (M11.5)


def test_a_continued_stage_ends_where_an_uninterrupted_one_and_its_primitives_do(tmp_path, monkeypatch):
    """Plan v3 M11.5: compared without the journal's own records (its hot and cold intent, its counter and pointers,
    and the revisions its commits add), a stage that crashed and was continued, the same stage run whole, and its
    primitives run directly all end in the same state."""
    for name, (row, planner) in PROBES.items():
        monkeypatch.setitem(contract.TOOLS, name, row)
        monkeypatch.setitem(stage.STAGES, name, planner)
    whole, continued, direct = (sample_project(tmp_path / n) for n in ("whole", "continued", "direct"))
    assert call(whole, "probe_notes", note="n")["ok"]
    sid = crashed_stage(continued, monkeypatch, "probe_notes", "checkpoint", call_no=2, note="n")
    assert resolve(continued, sid, "continue")["ok"]
    e = Engine.discover(direct.root)
    for step in PROBES["probe_notes"][1]({"note": "n"}):
        e.checkpoint(token=direct.token, expect_rev=direct.rev(), note=step["args"]["note"],
                     next_action=step["args"]["next"])
    views = [end_state(x.root) for x in (whole, continued, direct)]
    assert differences(views[0], views[1]) == [] and differences(views[0], views[2]) == []
    assert load_control(whole.root)["revision"] < load_control(continued.root)["revision"]  # the continue's commit


def test_the_resolution_invariant_catches_a_broken_record(project, monkeypatch):
    """Invariant 51 can fail: a continue with no resolution, a rebind that skips its owner, and an abandon recorded on
    an intent that is still ACTIVE are each reported."""
    from invariants import stage_intent_violations

    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    state = load_control(p.root)
    si = state["stage_intents"][sid]
    rev = si["steps"][-1]["revision"]
    assert stage_intent_violations(p.root, state, state) == []
    si["rebound"] = [{"from_generation": 1, "to_generation": 1, "rev": rev, "at": "t", "rationale": "r"}]
    assert any("no resolution" in v for v in stage_intent_violations(p.root, state, state))
    si["rebound"][0]["from_generation"] = 2
    assert any("rebinds generation 2" in v for v in stage_intent_violations(p.root, state, state))
    si["rebound"] = []
    si["resolution"] = {"choice": "abandon", "rationale": "r", "generation": 1, "rev": rev, "at": "t"}
    assert any("ACTIVE with resolution abandon" in v for v in stage_intent_violations(p.root, state, state))


def test_the_equivalence_view_keeps_real_differences():
    """#166 review, finding 1 (the reviewer's states): the view removes only the journal's records and what its commits
    move, by path. A unit's plan revision, the archive's counts, a token's revocation and an invocation's closing
    still compare unequal; a time stays null or not."""
    from stage_equivalence import _clean

    a = {"work": {"T-1": {"plans": [{"revision": 1, "sha256": "x"}], "state": "DONE"}},
         "cold": {"root": "r1", "archived": {"done": 1}},
         "tokens": {"t1": {"revoked_at": "2026-10-10", "revoke_reason": "rotated"}},
         "invocations": {"I-1": {"closed_at": "2026-10-10"}}}
    b = {"work": {"T-1": {"plans": [{"revision": 2, "sha256": "x"}], "state": "DONE"}},
         "cold": {"root": "r2", "archived": {"done": 0}},
         "tokens": {"t1": {"revoked_at": None, "revoke_reason": None}},
         "invocations": {"I-1": {"closed_at": None}}}
    found = differences(_clean(a, "/p"), _clean(b, "/p"))
    assert sorted(d.split(":")[0] for d in found) == [
        "/cold/archived/done", "/invocations/I-1/closed_at", "/tokens/t1/revoke_reason", "/tokens/t1/revoked_at",
        "/work/T-1/plans"]
    # What it does drop: the top-level revision, the history head, the journal's records; times only by value.
    c = {**b, "revision": 9, "cold": {"root": "r9", "archived": {"done": 0}}, "stage_intents": {"SI-0001": {}},
         "invocations": {"I-1": {"closed_at": None}}, "counters": {"stage_intent": 3}}
    assert differences(_clean(b, "/p"), _clean(c, "/p")) == ["/counters: only in the second"]
    t1, t2 = ({"tokens": {"tk_" + "a" * 16: {"revoked_at": None}}, "lead": {"token_id": "tk_" + "a" * 16}},
              {"tokens": {"tk_" + "b" * 16: {"revoked_at": None}}, "lead": {"token_id": "tk_" + "b" * 16}})
    assert differences(_clean(t1, "/p"), _clean(t2, "/p")) == []  # ids are ordinals, references kept
    # E5a: a dispatch's revision is normalised by value, never dropped; its decision digest is recomputed over the
    # recorded decision with the revision substituted, so two decisions that differ only by revision compare equal,
    # any other difference in them still shows, and a digest of no recorded decision compares as it is (PR #177
    # review, finding 3). A hash names a file only when it is that file's (any other hash still compares).
    from stage_equivalence import _Normaliser

    body = {"entrypoint": "work.assign", "work_id": "T-1", "allowed": True, "revision": 4}
    known = {"sha256:a": body, "sha256:b": {**body, "revision": 5}, "sha256:c": {**body, "work_id": "T-2"}}
    d1 = {"invocations": {"I-1": {"dispatch": {"revision": 4, "decision": "sha256:a", "channel": "direct"}}}}
    d2 = {"invocations": {"I-1": {"dispatch": {"revision": 5, "decision": "sha256:b", "channel": "lead_mcp"}}}}
    assert differences(_Normaliser("/p", decisions=known)(d1), _Normaliser("/p", decisions=known)(d2)) == [
        "/invocations/I-1/dispatch/channel: 'direct' != 'lead_mcp'"]
    d4 = {"invocations": {"I-1": {"dispatch": {"revision": 5, "decision": "sha256:c", "channel": "direct"}}}}
    assert [d.split(":")[0] for d in differences(_Normaliser("/p", decisions=known)(d1),
                                                  _Normaliser("/p", decisions=known)(d4))] == [
        "/invocations/I-1/dispatch/decision"]  # another unit's decision
    assert [d.split(":")[0] for d in differences(_clean(d1, "/p"), _clean(d2, "/p"))] == [
        "/invocations/I-1/dispatch/channel", "/invocations/I-1/dispatch/decision"]  # unrecorded: as it is
    d3 = {"invocations": {"I-1": {"dispatch": {"channel": "direct"}}}}
    assert differences(_clean(d1, "/p"), _clean(d3, "/p")) == [
        "/invocations/I-1/dispatch/decision: only in the first",
        "/invocations/I-1/dispatch/revision: only in the first"]

    named = _Normaliser("/p", files={"a" * 64: "<sha256 of work/T-1/ticket.md>"})
    assert named({"record_sha256": "a" * 64}) == {"record_sha256": "<sha256 of work/T-1/ticket.md>"}
    assert named({"record_sha256": "b" * 64}) == {"record_sha256": "b" * 64}


@pytest.mark.parametrize("disposition", ["rebuild", "requeue", None])
def test_resume_and_continue_agree_on_a_step_blocked_with_a_disposition(project, monkeypatch, disposition):
    """PR #171 re-review, finding 1: a next step whose guard is BLOCKED with a disposition passes with a stated
    consequence. `resume` calls it safe to continue, with the boundary naming the disposition and a message saying what
    the continue commits, and `resolve continue` runs the step. A plainly BLOCKED step is unsafe, `refused`, and the
    continue is refused (`next_step_blocked`), committing nothing."""
    p = project
    sid = crashed_stage(p, monkeypatch, "probe_notes", "checkpoint", call_no=2)
    answer = {"availability": "BLOCKED", "reason_codes": ["STALE_CANDIDATE"], "blocking_conditions": [],
              **({"disposition": disposition} if disposition else {})}
    monkeypatch.setattr(Engine, "guard_query", lambda self, primitive, work_id, args=None, *, state=None: answer)
    row = unfinished(p)[sid]
    guard = row["checks"]["guard"]
    if disposition is None:
        assert (row["safe_to_continue"], row["failing"], row["boundary"]) == (False, ["guard"], "refused")
        rev = p.rev()
        out = resolve(p, sid, "continue")
        assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "next_step_blocked"
        assert p.rev() == rev
        return
    assert row["safe_to_continue"] is True and row["failing"] == []
    assert row["boundary"] == f"disposition:{disposition}" and guard["disposition"] == disposition
    assert {"rebuild": "rebuild", "requeue": "requeue"}[disposition] in guard["message"]
    out = resolve(p, sid, "continue")
    assert out["ok"], out["stopped"]
    assert Engine.discover(p.root).stage_intent(sid)["status"] == "COMPLETED"
