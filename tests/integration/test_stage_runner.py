"""The stage executor (M4-E E3b; plan v3 E3; typed Lead surface design v0.2 §3.4 rules 1 to 8; R5-1).

No stage tool is built yet (E4 and E5 build the Ticket stages), so the stages here are probes: catalogue rows and
planners registered for the test alone, over the primitives that have step runners (``checkpoint``, ``work.assign``).
Each runs through ``run_tool``, exactly as a Lead's call would, against a real project. A test that needs another
actor's commit between two steps wraps a step runner so the commit lands just before the step's own. A launching
assignment runs for real: the fake harness's configured execution policy, a real supervisor, and failures injected
where a launch really fails (#142 review, finding 1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from aewflow import NOT_THE_DEFAULT_CAP, create_planned_ticket, sample_project
from fake_harness import HarnessLab, contains_credential
from invariants import assert_control_invariants, load_control

import aew.operator
from aew.engine import harness_ops
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.harness import runlog
from aew.surface import contract, stage
from aew.surface import run as R
from aew.surface.context import SurfaceContext
from aew.surface.errors import AdapterInputError

CTX = SurfaceContext.outside_session()
WORK = contract.WORK_ID


def _probe(name: str, base: str, expands_to: tuple[str, ...], *, judgments: tuple[str, ...] = (),
           unit: bool = False) -> contract.Tool:
    props: dict[str, Any] = {"note": {"type": "string"}}
    if unit:
        props |= {"work_id": WORK, "execution": contract.EXECUTION, "launch": {"type": "boolean"}}
    return contract.Tool(name, contract.STAGE, base, f"a probe stage ({name})",
                         contract._obj(props, ("work_id",) if unit else ()),
                         expands_to=expands_to, required_judgments=judgments, promotes=("execution",) if unit else (),
                         mutates=True, progression=True)


def _notes(a: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"primitive": "checkpoint", "args": {"note": f"{a.get('note', '')} 1", "next": "step 2"}},
            {"primitive": "checkpoint", "args": {"note": f"{a.get('note', '')} 2", "next": "done"}}]


def _start(a: dict[str, Any]) -> list[dict[str, Any]]:
    assign = {"work_id": a["work_id"], **({"launch": True} if a.get("launch") else {}),
              **({"execution": a["execution"]} if "execution" in a else {})}
    return [{"primitive": "checkpoint", "args": {"note": "before the assignment", "next": f"assign {a['work_id']}"}},
            {"primitive": "work.assign", "args": assign}]


def _named(a: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"primitive": "work.assign", "args": {"work_id": a["work_id"]}},
            {"primitive": "checkpoint", "args": {"note": "after", "next": {"$from": [1, "invocations"]}}}]


PROBES = {
    "probe_notes": (_probe("probe_notes", contract.MECHANICAL, ("checkpoint", "checkpoint")), _notes),
    "probe_start": (_probe("probe_start", contract.POLICY_RESOLVED, ("checkpoint", "work.assign"), unit=True), _start),
    "probe_judged": (_probe("probe_judged", contract.JUDGMENT_BEARING, ("checkpoint", "work.assign"),
                            judgments=("ticket_proposition",), unit=True), _start),
    "probe_named": (_probe("probe_named", contract.POLICY_RESOLVED, ("work.assign", "checkpoint"), unit=True), _named),
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    for name, (row, planner) in PROBES.items():
        monkeypatch.setitem(contract.TOOLS, name, row)
        monkeypatch.setitem(stage.STAGES, name, planner)
    return sample_project(tmp_path)


def call(p, name: str, **arguments: Any) -> dict[str, Any]:
    engine = Engine.discover(p.root)
    wid = arguments.get("work_id")
    if "prior_value" not in arguments:
        if name == "ticket_request_review":
            arguments["prior_value"] = "RUNNING"
        elif name == "ticket_request_verification" and "review_evidence" not in arguments and wid:
            if engine.prior_value("work_transition", wid) == "REVIEW_PASSED":
                arguments["prior_value"] = "REVIEW_PASSED"
        elif name == "ticket_prepare" and "verification_evidence" not in arguments and wid:
            state = engine.prior_value("work_transition", wid)
            if state in {"REVIEW_PASSED", "VERIFIED"}:
                arguments["prior_value"] = state
    return R.run_tool(engine, CTX, name, arguments, token=p.token)


def intent(p, result: dict[str, Any]) -> dict[str, Any]:
    return Engine.discover(p.root).stage_intent(result["stage_intent_id"])


def hot(p) -> dict[str, Any]:
    return load_control(p.root).get("stage_intents") or {}


def intervene(monkeypatch, primitive: str, *, times: int = 1,
              before: Callable[[Any], None] | None = None) -> list[int]:
    """Wrap ``primitive``'s step runner: for its first ``times`` calls, another commit lands just before the step's
    own (a checkpoint by default). Return the revisions observed when the step was entered."""
    real = stage.STEP_RUNNERS[primitive]
    seen: list[int] = []

    def wrapped(c, args):
        seen.append(int(c.engine.store.current()["revision"]))
        if len(seen) <= times:
            armed = SI._STEP.set(None)  # another actor's commit is not the step: it runs outside the step's binding
            try:
                if before is not None:
                    before(c)
                else:
                    c.engine.checkpoint(token=c.token(), note="another actor's commit")
            finally:
                SI._STEP.reset(armed)
        return real(c, args)

    monkeypatch.setitem(stage.STEP_RUNNERS, primitive, wrapped)
    return seen


def legality_edit(p) -> None:
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + f"mutating_concurrency: {NOT_THE_DEFAULT_CAP}\n",
                     encoding="utf-8")


def launching(p, tmp_path, monkeypatch) -> HarnessLab:
    """A configured execution policy routed to the fake harness, registered in this process too: the stage's
    assignment launches a real supervised run. The caller ends its runs (``lab.cleanup()``)."""
    lab = HarnessLab.create(p, tmp_path)
    for k, v in lab.env.items():
        monkeypatch.setenv(k, v)
    return lab


def take_over(c) -> None:
    """The operator takes the Lead seat over (a new generation): the caller's credential no longer holds it."""
    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        c.engine.lead_takeover(reason="the Lead's session was lost", session_label="operator")
    finally:
        aew.operator.authorize = original


def assert_launch_failed_with_its_run_standing(p, out: dict[str, Any], wid: str) -> str:
    """Rule 7: the stage stopped as launch_failed after the assignment committed; the run that commit recorded stands,
    on the intent, in the result and in control state, and no credential is anywhere in the result."""
    assert not out["ok"] and out["stopped"]["boundary"] == "launch_failed", out["stopped"]
    error = out["stopped"]["error"]
    assert error["code"] == "HARNESS_LAUNCH_FAILED" and error["details"]["committed"] is True
    si = intent(p, out)
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 2 and si["stopped"]["n"] == 2
    invocation = load_control(p.root)["work"][wid]["implementer_invocation"]
    [run] = load_control(p.root)["invocations"][invocation]["runs"]
    assert run["kind"] == "dispatch" and error["details"]["run"] == run["run"]
    assert si["steps"][1]["outputs"] == {"units": [], "invocations": [invocation], "runs": [run["run"]]}
    assert {f"invocation:{invocation}", f"run:{run['run']}"} <= set(out["completed_steps"][1]["refs"])
    assert out["result"]["status"] == "STOPPED_AT_BOUNDARY" and not contains_credential(str(out))
    return run["run"]


def unready_ticket(p) -> str:
    """A Ticket with no accepted plan: the assignment's dispatch decision refuses it."""
    return p.lead("work", "create", "ticket", "--title", "No plan yet", "--class", "1", "--goal", "a goal",
                  "--contract", "a contract", "--scope", "calc/**")["id"]


# ---------------------------------------------------------------------------------------------- rules 1 to 8

def rule_retired_input(p, tmp_path, monkeypatch):
    """The typed ingress refuses the retired project revision before an intent can open."""
    rev = p.rev()
    with pytest.raises(AdapterInputError) as exc:
        call(p, "probe_notes", expect_rev=rev)
    assert exc.value.code == "INVALID_ARGUMENTS" and p.rev() == rev
    assert "stage_intents" not in load_control(p.root) and "stage_intent" not in load_control(p.root)["counters"]


def rule_intent_first(p, tmp_path, monkeypatch):
    """Rule 2: the intent is the first commit, and the steps run from the revision it returned (no self-inflicted
    stale revision); the last step's commit completes the stage."""
    rev = p.rev()
    out = call(p, "probe_notes", note="probe")
    assert out["ok"] and out["stopped"] is None, out["stopped"]
    si = intent(p, out)
    assert si["status"] == "COMPLETED" and si["opened"] == {**si["opened"], "rev": rev + 1}
    assert [s["revision"] for s in out["completed_steps"]] == [rev + 2, rev + 3] == [s["revision"] for s in si["steps"]]
    assert out["revision"] == rev + 3 and si["closed"]["rev"] == rev + 3 and hot(p) == {}
    digests = Engine.discover(p.root).policy_digests()
    assert out["policy_binding"]["legality_digest"] == digests["legality_digest"].removeprefix("sha256:")
    assert si["tool"] == "probe_notes" and si["ingress"] == CTX.ingress and si["effective_class"] == "MECHANICAL"


def rule_first_refusal(p, tmp_path, monkeypatch):
    """Rule 3: a refused primitive stops the stage; the committed step stands and the intent records the stop."""
    wid = unready_ticket(p)
    out = call(p, "probe_start", work_id=wid)
    assert not out["ok"] and out["stopped"]["at"] == "work.assign", out["stopped"]
    si = intent(p, out)
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 1 and si["stopped"]["n"] == 2
    assert si["stopped"]["error"]["code"] == out["stopped"]["error"]["code"]
    assert [s["primitive"] for s in out["completed_steps"]] == ["checkpoint"]
    assert load_control(p.root)["next_action"] == f"assign {wid}"  # the committed step is never rolled back
    assert load_control(p.root)["work"][wid]["state"] != "ASSIGNED"


def rule_unrelated_writer(p, tmp_path, monkeypatch):
    """A checkpoint during a policy-resolved assignment never requires that assignment to be attempted twice."""
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign")
    out = call(p, "probe_start", work_id=wid)
    assert out["ok"], out["stopped"]
    assert len(seen) == 1
    si = intent(p, out)
    assert si["status"] == "COMPLETED" and "retried_after_stale_revision" not in si
    assert all("retried_after_stale_revision" not in s for s in si["steps"] + out["completed_steps"])
    assert load_control(p.root)["work"][wid]["state"] == "ASSIGNED"


def rule_no_replay(p, tmp_path, monkeypatch):
    """A competing assignment refuses the judgment's step once. The first step and other writer's work stand."""
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign", before=lambda c: c.engine.work_assign(token=c.token(), work_id=wid))
    out = call(p, "probe_judged", work_id=wid)
    assert not out["ok"] and out["stopped"]["boundary"] == "refused" and len(seen) == 1
    si = intent(p, out)
    assert si["effective_class"] == "JUDGMENT_BEARING" and si["status"] == SI.STOPPED
    assert [s["primitive"] for s in si["steps"]] == ["checkpoint"]
    assert "retried_after_stale_revision" not in si and load_control(p.root)["work"][wid]["state"] == "ASSIGNED"


def rule_drift(p, tmp_path, monkeypatch):
    """Rule 6: a legality policy adopted between two steps stops the stage as STALE_POLICY, whether the next step
    reaches its commit (the journal refuses it) or meets the stale revision the adoption left (the executor checks
    the binding before any retry)."""
    def adopt(c):
        legality_edit(p)
        p.adopt_policy()

    seen = intervene(monkeypatch, "checkpoint", times=2, before=lambda c: adopt(c) if len(seen) == 2 else None)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_policy", out["stopped"]
    si = intent(p, out)
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 1 and len(seen) == 2
    assert si["stopped"]["error"]["code"] == "STALE_POLICY"


def rule_launch_failed(p, tmp_path, monkeypatch):
    """Rule 7: the assignment commits its dispatch and run 1, and the real launch then fails (the run's supervisor
    takes custody, but the harness cannot start: the fake harness has no script for it). The stage stops as
    launch_failed at that step, and the recorded run stands, as its supervisor recorded it."""
    lab = launching(p, tmp_path, monkeypatch)
    try:
        wid = create_planned_ticket(p, tmp_path)
        out = call(p, "probe_start", work_id=wid, launch=True)
        run = assert_launch_failed_with_its_run_standing(p, out, wid)
        assert lab.record(run)["status"] == "launch_failed" and "no fake script" in lab.record(run)["reason"]
    finally:
        lab.cleanup()


def rule_takeover(p, tmp_path, monkeypatch):
    """Rule 8, the executor's part: a seat lost mid-stage stops the call, and the stop it cannot record (the
    credential is stale) leaves the intent ACTIVE for the new Lead's explicit resolve (E3c)."""
    intervene(monkeypatch, "checkpoint", times=2, before=lambda c: take_over(c) if hot(p) and
              hot(p)[next(iter(hot(p)))]["steps"] else None)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_authority", out["stopped"]
    si = intent(p, out)
    assert si["status"] == "ACTIVE" and len(si["steps"]) == 1 and si["generation"] == 1
    assert out["result"]["left_active"]["code"] == "STALE_AUTHORITY"
    assert list(hot(p)) == [out["stage_intent_id"]]


RULES = {"retired_input": rule_retired_input, "intent_first": rule_intent_first, "first_refusal": rule_first_refusal,
         "unrelated_writer": rule_unrelated_writer, "no_replay": rule_no_replay, "drift": rule_drift,
         "launch_failed": rule_launch_failed, "takeover": rule_takeover}


@pytest.mark.parametrize("rule", list(RULES))
def test_stage_intent_rules(project, tmp_path, monkeypatch, rule):
    """TLS-14 / §3.4 rules 1 to 8, each through run_tool; the control invariants hold after every one."""
    RULES[rule](project, tmp_path, monkeypatch)
    assert_control_invariants(project)


# ---------------------------------------------------------------------------------------------- R5-1, the rest

def test_a_judgment_bearing_stage_does_not_repeat_a_refused_step(project, tmp_path, monkeypatch):
    p = project
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign", before=lambda c: c.engine.work_assign(token=c.token(), work_id=wid))
    out = call(p, "probe_start", work_id=wid, execution={"effort": "high"})
    assert out["effective_operation_class"] == "JUDGMENT_BEARING" and len(seen) == 1
    assert not out["ok"] and out["stopped"]["boundary"] == "refused"
    assert intent(p, out)["judgment_inputs"] == ["execution"]


def test_a_step_without_a_query_still_uses_its_actual_transaction(project, monkeypatch):
    p = project
    seen = intervene(monkeypatch, "checkpoint", times=2)
    out = call(p, "probe_notes")
    assert len(seen) == 2 and out["ok"]
    assert len(intent(p, out)["steps"]) == 2 and "retried_after_stale_revision" not in intent(p, out)


def test_a_competing_assignment_stops_at_the_dispatch_guard(project, tmp_path, monkeypatch):
    """The other commit assigned the unit itself. Its assignment uses its own dispatch guard."""
    p = project
    wid = create_planned_ticket(p, tmp_path)

    def assign_first(c):
        c.engine.work_assign(token=c.token(), work_id=wid)

    seen = intervene(monkeypatch, "work.assign", before=assign_first)
    out = call(p, "probe_start", work_id=wid)
    assert len(seen) == 1 and not out["ok"] and out["stopped"]["boundary"] == "refused"
    assert intent(p, out)["status"] == SI.STOPPED
    assert out["stopped"]["error"]["details"].get("reason") != "resolve_stage"
    assert hot(p) == {}
    again = call(p, "probe_start", work_id=wid)
    assert again["stopped"]["error"]["details"].get("reason") != "open_intent"


def test_a_stage_with_an_unchanged_subject_but_a_blocked_next_guard_ends(project, tmp_path, monkeypatch):
    """F1: another Ticket's assignment blocks the guard without moving this subject; don't retain a dead end."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    other = create_planned_ticket(p, tmp_path)

    def occupy(c):
        c.engine.work_assign(token=c.token(), work_id=other)

    seen = intervene(monkeypatch, "work.assign", before=occupy)
    out = call(p, "probe_start", work_id=wid)
    assert len(seen) == 1 and not out["ok"] and out["stopped"]["boundary"] == "refused"
    assert load_control(p.root)["work"][wid]["state"] == "READY"
    assert Engine.discover(p.root).guard_query("work.assign", wid, {"work_id": wid})["availability"] == "BLOCKED"
    assert intent(p, out)["status"] == SI.STOPPED and hot(p) == {}
    again = call(p, "probe_start", work_id=wid)
    assert again["stopped"]["error"]["details"].get("reason") != "open_intent"


def test_a_pending_policy_edit_leaves_the_intent_for_resolve(project, monkeypatch):
    """A policy edit not yet adopted refuses every Lead commit, the stop included: the intent stays ACTIVE, and the
    result says why."""
    p = project
    intervene(monkeypatch, "checkpoint", times=2,
              before=lambda c: legality_edit(p) if hot(p) and hot(p)[next(iter(hot(p)))]["steps"] else None)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["result"]["left_active"]["code"] == "INTEGRITY_ERROR"
    assert intent(p, out)["status"] == "ACTIVE"


def test_a_pending_policy_edit_after_an_unrelated_write_preserves_committed_steps(project, monkeypatch):
    """Another commit lands, then a policy file is edited and not yet adopted: step 2 meets STALE_REVISION (the
    revision is checked before the policy pins), and reading the binding to decide on a retry is refused
    (INTEGRITY_ERROR). The stage stops at step 2 on that refusal with step 1 reported, and the stop it cannot record
    leaves the intent ACTIVE, saying why (#142 review, finding 2)."""
    p = project

    def other_commit_then_edit(c):
        if hot(p) and hot(p)[next(iter(hot(p)))]["steps"]:
            c.engine.checkpoint(token=c.token(), note="other")
            legality_edit(p)

    intervene(monkeypatch, "checkpoint", times=2, before=other_commit_then_edit)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["at"] == "checkpoint", out["stopped"]
    assert out["stopped"]["error"]["code"] == "INTEGRITY_ERROR"
    assert [s["primitive"] for s in out["completed_steps"]] == ["checkpoint"]
    assert out["result"]["status"] == "ACTIVE" and out["result"]["left_active"]["code"] == "INTEGRITY_ERROR"
    si = intent(p, out)
    assert si["status"] == "ACTIVE" and len(si["steps"]) == 1


# ---------------------------------------------------------------------------------------------- the plan

def test_a_step_argument_comes_from_an_earlier_steps_journal_record(project, tmp_path):
    p = project
    wid = create_planned_ticket(p, tmp_path)
    out = call(p, "probe_named", work_id=wid)
    assert out["ok"], out["stopped"]
    invocation = load_control(p.root)["work"][wid]["implementer_invocation"]
    assert load_control(p.root)["next_action"] == invocation
    assert intent(p, out)["plan"][1]["args"]["next"] == {"$from": [1, "invocations"]}
    assert_control_invariants(p)


def test_a_launching_last_step_starts_its_run_before_the_stage_completes(project, tmp_path, monkeypatch):
    """A launching assignment hands the run its commit recorded to a real supervisor; only then does the executor
    complete the stage, in a commit of its own (the step's commit cannot: its launch follows it). The result carries
    the launch, never the credential (#142 review, finding 1)."""
    p = project
    lab = launching(p, tmp_path, monkeypatch)
    try:
        wid = create_planned_ticket(p, tmp_path)
        lab.script("default", [{"do": "aew", "args": ["whoami"]}])
        out = call(p, "probe_start", work_id=wid, launch=True)
        assert out["ok"], out["stopped"]
        si = intent(p, out)
        assert si["status"] == "COMPLETED" and si["closed"]["rev"] == si["steps"][1]["revision"] + 1
        launch = out["result"]["steps"][1]["launch"]
        assert launch["status"] in ("starting", "running") and si["steps"][1]["outputs"]["runs"] == [launch["run"]]
        assert lab.record(launch["run"]).get("status") and not contains_credential(str(out))
        assert "invocation_token" not in out["result"]["steps"][1]
    finally:
        lab.cleanup()
    assert_control_invariants(p)


def test_a_supervisor_that_cannot_start_stops_the_stage_as_launch_failed(project, tmp_path, monkeypatch):
    """Rule 7 at the launch's first fault point: the run's supervisor process cannot be started at all. The dispatch
    and run 1 are committed, so the stage stops as launch_failed with the run standing (relaunching it is the Lead's
    `aew harness launch`, which rotates the credential), never as COMPLETED over a run that never started."""
    p = project
    lab = launching(p, tmp_path, monkeypatch)
    try:
        wid = create_planned_ticket(p, tmp_path)

        def no_process(*_, **__):
            raise OSError("no process slot")

        monkeypatch.setattr(harness_ops.procs, "spawn_detached", no_process)
        out = call(p, "probe_start", work_id=wid, launch=True)
        run = assert_launch_failed_with_its_run_standing(p, out, wid)
        assert "could not start" in out["stopped"]["error"]["message"]
        assert runlog.read_record(runlog.run_dir(p.root / ".aew", run)) is None  # no supervisor ever ran
    finally:
        lab.cleanup()
    assert_control_invariants(p)


def test_a_plan_that_breaks_the_stage_contract_commits_nothing(project, monkeypatch):
    p = project
    monkeypatch.setitem(stage.STAGES, "probe_notes", lambda a: [{"primitive": "checkpoint", "args": {}}])
    rev = p.rev()
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["error"]["code"] == "USAGE" and p.rev() == rev
    assert out["stage_intent_id"] is None


@pytest.mark.parametrize(("args", "reason"), [
    ({"next": {"$from": [2, "invocations"]}}, "reference_not_earlier"),  # the step itself
    ({"next": {"$from": [3, "invocations"]}}, "reference_not_earlier"),  # a later step (and one not planned)
    ({"next": {"$from": [0, "invocations"]}}, "reference_not_earlier"),
    ({"next": {"$from": [1, "workspaces"]}}, "malformed_reference"),  # no step records that field
    ({"next": {"$from": ["1", "invocations"]}}, "malformed_reference"),  # not an integer step number
    ({"next": {"$from": [1.0, "invocations"]}}, "malformed_reference"),
    ({"next": {"$from": [True, "invocations"]}}, "malformed_reference"),
    ({"next": {"$from": [1]}}, "malformed_reference"),
    ({"next": {"$from": [1, "invocations"], "else": "x"}}, "malformed_reference"),
], ids=["self", "forward", "zero", "unknown_field", "string_step", "float_step", "bool_step", "short", "extra_key"])
def test_a_plan_with_a_bad_step_reference_commits_nothing(project, monkeypatch, args, reason):
    """A ``$from`` that names the step itself, a later one, a field no step records, or a step that is not an integer
    is refused when the intent opens, with its reason: no step commits first, and no defect escapes later (#142
    review, finding 4)."""
    p = project
    wid = unready_ticket(p)
    monkeypatch.setitem(stage.STAGES, "probe_named", lambda a: [
        {"primitive": "work.assign", "args": {"work_id": a["work_id"]}},
        {"primitive": "checkpoint", "args": {"note": "after", **args}}])
    rev = p.rev()
    out = call(p, "probe_named", work_id=wid)
    assert not out["ok"] and out["stopped"]["at"] == "probe_named", out["stopped"]
    error = out["stopped"]["error"]
    assert error["code"] == "USAGE" and error["details"]["reason"] == reason and error["details"]["step"] == 2
    assert out["stage_intent_id"] is None and out["completed_steps"] == [] and p.rev() == rev
    assert "stage_intents" not in load_control(p.root) and "stage_intent" not in load_control(p.root)["counters"]


def test_a_forward_reference_in_the_first_step_commits_nothing(project, monkeypatch):
    p = project
    wid = unready_ticket(p)
    monkeypatch.setitem(stage.STAGES, "probe_named", lambda a: [
        {"primitive": "work.assign", "args": {"work_id": {"$from": [2, "units"]}}},
        {"primitive": "checkpoint", "args": {"note": "after"}}])
    rev = p.rev()
    out = call(p, "probe_named", work_id=wid)
    assert (out["stopped"]["error"]["details"]["step"], out["stopped"]["error"]["details"]["reason"]) == (
        1, "reference_not_earlier")
    assert out["stage_intent_id"] is None and p.rev() == rev
