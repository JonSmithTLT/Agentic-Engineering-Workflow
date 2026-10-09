"""The stage executor (M4-E E3b; plan v3 E3; typed Lead surface design v0.2 §3.4 rules 1 to 8; R5-1).

No stage tool is built yet (E4 and E5 build the Ticket stages), so the stages here are probes: catalogue rows and
planners registered for the test alone, over the primitives that have step runners (``checkpoint``, ``work.assign``).
Each runs through ``run_tool``, exactly as a Lead's call would, against a real project. A test that needs another
actor's commit between two steps wraps a step runner so the commit lands just before the step's own."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project
from invariants import assert_control_invariants, load_control

import aew.operator
from aew import errors
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.surface import contract, stage
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()
REV = contract.EXPECT_REV
WORK = contract.WORK_ID


def _probe(name: str, base: str, expands_to: tuple[str, ...], *, judgments: tuple[str, ...] = (),
           unit: bool = False) -> contract.Tool:
    props: dict[str, Any] = {"expect_rev": REV, "note": {"type": "string"}}
    if unit:
        props |= {"work_id": WORK, "execution": contract.EXECUTION, "launch": {"type": "boolean"}}
    return contract.Tool(name, contract.STAGE, base, f"a probe stage ({name})",
                         contract._obj(props, ("expect_rev", "work_id") if unit else ("expect_rev",)),
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
    arguments.setdefault("expect_rev", p.rev())
    return R.run_tool(Engine.discover(p.root), CTX, name, arguments, token=p.token)


def intent(p, result: dict[str, Any]) -> dict[str, Any]:
    return Engine.discover(p.root).stage_intent(result["stage_intent_id"])


def hot(p) -> dict[str, Any]:
    return load_control(p.root).get("stage_intents") or {}


def intervene(monkeypatch, primitive: str, *, times: int = 1,
              before: Callable[[Any], None] | None = None) -> list[int]:
    """Wrap ``primitive``'s step runner: for its first ``times`` calls, another commit lands just before the step's
    own (a checkpoint by default), so the step runs on a stale revision. Returns the revisions it ran on."""
    real = stage.STEP_RUNNERS[primitive]
    seen: list[int] = []

    def wrapped(c, args, rev):
        seen.append(rev)
        if len(seen) <= times:
            armed = SI._STEP.set(None)  # another actor's commit is not the step: it runs outside the step's binding
            try:
                if before is not None:
                    before(c)
                else:
                    current = int(c.engine.store.read()["revision"])
                    c.engine.checkpoint(token=c.token(), expect_rev=current, note="another actor's commit")
            finally:
                SI._STEP.reset(armed)
        return real(c, args, rev)

    monkeypatch.setitem(stage.STEP_RUNNERS, primitive, wrapped)
    return seen


def legality_edit(p) -> None:
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + "mutating_concurrency: 2\n", encoding="utf-8")


def unready_ticket(p) -> str:
    """A Ticket with no accepted plan: the assignment's dispatch decision refuses it."""
    return p.lead("work", "create", "ticket", "--title", "No plan yet", "--class", "1", "--goal", "a goal",
                  "--contract", "a contract", "--scope", "calc/**")["id"]


# ---------------------------------------------------------------------------------------------- rules 1 to 8

def rule_cas(p, tmp_path, monkeypatch):
    """Rule 1: a stale ``expect_rev`` opens no intent and commits nothing."""
    rev = p.rev()
    out = call(p, "probe_notes", expect_rev=rev - 1)
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_revision"
    assert out["stage_intent_id"] is None and out["completed_steps"] == [] and p.rev() == rev
    assert "stage_intents" not in load_control(p.root) and "stage_intent" not in load_control(p.root)["counters"]


def rule_intent_first(p, tmp_path, monkeypatch):
    """Rule 2: the intent is the first commit, and the steps run from the revision it returned (no self-inflicted
    stale revision); the last step's commit completes the stage."""
    rev = p.rev()
    out = call(p, "probe_notes", note="probe")
    assert out["ok"] and out["stopped"] is None, out["stopped"]
    si = intent(p, out)
    assert si["status"] == "COMPLETED" and si["opened"] == {**si["opened"], "expect_rev": rev, "rev": rev + 1}
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


def rule_stale_retry(p, tmp_path, monkeypatch):
    """Rule 4 and R5-1: a non-judgment step of a non-judgment stage, still AVAILABLE with the same arguments, is
    retried once after a stale revision, and the retry is recorded on the intent and in the result."""
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign")
    out = call(p, "probe_start", work_id=wid)
    assert out["ok"], out["stopped"]
    assert len(seen) == 2 and seen[1] == seen[0] + 1  # the retry ran on the revision the other commit left
    si = intent(p, out)
    assert si["status"] == "COMPLETED" and si["retried_after_stale_revision"]
    assert si["steps"][1]["retried_after_stale_revision"] and "retried_after_stale_revision" not in si["steps"][0]
    assert out["completed_steps"][1]["retried_after_stale_revision"] is True
    assert load_control(p.root)["work"][wid]["state"] == "ASSIGNED"


def rule_no_replay(p, tmp_path, monkeypatch):
    """Rule 5 (BRP-03): a judgment-bearing stage never retries, not even a policy-resolved step inside it."""
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign")
    out = call(p, "probe_judged", work_id=wid)
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_revision" and len(seen) == 1
    si = intent(p, out)
    assert si["effective_class"] == "JUDGMENT_BEARING" and si["status"] == "STOPPED_AT_BOUNDARY"
    assert not si["retried_after_stale_revision"] and load_control(p.root)["work"][wid]["state"] == "READY"


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
    """Rule 7: a launch that fails after its dispatch committed stops the stage as launch_failed; the committed
    assignment and its invocation stand, on the intent and in the result."""
    wid = create_planned_ticket(p, tmp_path)
    real = stage.STEP_RUNNERS["work.assign"]

    def launch_fails(c, args, rev):
        out = real(c, {**args, "launch": False}, rev)  # the dispatch commits; its supervisor never takes custody
        raise errors.HarnessLaunchFailed(f"{out['invocation']}'s supervisor never acknowledged custody")

    monkeypatch.setitem(stage.STEP_RUNNERS, "work.assign", launch_fails)
    out = call(p, "probe_start", work_id=wid, launch=True)
    assert not out["ok"] and out["stopped"]["boundary"] == "launch_failed", out["stopped"]
    si = intent(p, out)
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 2 and si["stopped"]["n"] == 2
    invocation = load_control(p.root)["work"][wid]["implementer_invocation"]
    assert si["steps"][1]["outputs"]["invocations"] == [invocation]
    assert f"invocation:{invocation}" in out["completed_steps"][1]["refs"]


def rule_takeover(p, tmp_path, monkeypatch):
    """Rule 8, the executor's part: a seat lost mid-stage stops the call, and the stop it cannot record (the
    credential is stale) leaves the intent ACTIVE for the new Lead's explicit resolve (E3c)."""
    def take_over(c):
        original = aew.operator.authorize
        aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
        try:
            c.engine.lead_takeover(expect_rev=int(c.engine.store.read()["revision"]),
                                   reason="the Lead's session was lost", session_label="operator")
        finally:
            aew.operator.authorize = original

    intervene(monkeypatch, "checkpoint", times=2, before=lambda c: take_over(c) if hot(p) and
              hot(p)[next(iter(hot(p)))]["steps"] else None)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_authority", out["stopped"]
    si = intent(p, out)
    assert si["status"] == "ACTIVE" and len(si["steps"]) == 1 and si["generation"] == 1
    assert out["result"]["left_active"]["code"] == "STALE_AUTHORITY"
    assert list(hot(p)) == [out["stage_intent_id"]]


RULES = {"cas": rule_cas, "intent_first": rule_intent_first, "first_refusal": rule_first_refusal,
         "stale_retry": rule_stale_retry, "no_replay": rule_no_replay, "drift": rule_drift,
         "launch_failed": rule_launch_failed, "takeover": rule_takeover}


@pytest.mark.parametrize("rule", list(RULES))
def test_stage_intent_rules(project, tmp_path, monkeypatch, rule):
    """TLS-14 / §3.4 rules 1 to 8, each through run_tool; the control invariants hold after every one."""
    RULES[rule](project, tmp_path, monkeypatch)
    assert_control_invariants(project)


# ---------------------------------------------------------------------------------------------- R5-1, the rest

def test_judgment_bearing_stages_never_retry(project, tmp_path, monkeypatch):
    """BRP-03 / M5: an execution override promotes a policy-resolved stage to judgment-bearing, and then its
    policy-resolved assignment is never retried."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign")
    out = call(p, "probe_start", work_id=wid, execution={"effort": "high"})
    assert out["effective_operation_class"] == "JUDGMENT_BEARING" and len(seen) == 1
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_revision"
    assert intent(p, out)["judgment_inputs"] == ["execution"]


def test_a_stale_retry_happens_at_most_once(project, tmp_path, monkeypatch):
    p = project
    wid = create_planned_ticket(p, tmp_path)
    seen = intervene(monkeypatch, "work.assign", times=2)
    out = call(p, "probe_start", work_id=wid)
    assert len(seen) == 2 and not out["ok"] and out["stopped"]["boundary"] == "stale_revision"
    si = intent(p, out)
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 1
    assert_control_invariants(p)


def test_a_step_whose_availability_is_unknown_is_never_retried(project, monkeypatch):
    """R5-1's fifth condition: a checkpoint's guard is not a queryable decision yet, so its availability is UNKNOWN,
    and UNKNOWN never retries (E4 migrates the guards)."""
    p = project
    seen = intervene(monkeypatch, "checkpoint", times=2, before=lambda c: c.engine.checkpoint(
        token=c.token(), expect_rev=int(c.engine.store.read()["revision"]), note="x") if hot(p) and
        hot(p)[next(iter(hot(p)))]["steps"] else None)
    out = call(p, "probe_notes")
    assert len(seen) == 2 and not out["ok"] and out["stopped"]["boundary"] == "stale_revision"
    assert len(intent(p, out)["steps"]) == 1


def test_a_stale_retry_needs_the_action_still_available(project, tmp_path, monkeypatch):
    """R5-1: the other commit assigned the unit itself, so the stage's assignment is no longer AVAILABLE: no retry."""
    p = project
    wid = create_planned_ticket(p, tmp_path)

    def assign_first(c):
        c.engine.work_assign(token=c.token(), expect_rev=int(c.engine.store.read()["revision"]), work_id=wid)

    seen = intervene(monkeypatch, "work.assign", before=assign_first)
    out = call(p, "probe_start", work_id=wid)
    assert len(seen) == 1 and not out["ok"] and out["stopped"]["boundary"] == "stale_revision"
    assert intent(p, out)["status"] == "STOPPED_AT_BOUNDARY"


def test_a_pending_policy_edit_leaves_the_intent_for_resolve(project, monkeypatch):
    """A policy edit not yet adopted refuses every Lead commit, the stop included: the intent stays ACTIVE, and the
    result says why."""
    p = project
    intervene(monkeypatch, "checkpoint", times=2,
              before=lambda c: legality_edit(p) if hot(p) and hot(p)[next(iter(hot(p)))]["steps"] else None)
    out = call(p, "probe_notes")
    assert not out["ok"] and out["result"]["left_active"]["code"] == "INTEGRITY_ERROR"
    assert intent(p, out)["status"] == "ACTIVE"


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


def test_a_launching_last_step_completes_the_stage_in_its_own_commit(project, tmp_path, monkeypatch):
    """A step with an effect after its commit cannot complete the stage in that commit: the executor closes it."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    real = stage.STEP_RUNNERS["work.assign"]
    monkeypatch.setitem(stage.STEP_RUNNERS, "work.assign", lambda c, args, rev: real(c, {**args, "launch": False}, rev))
    out = call(p, "probe_start", work_id=wid, launch=True)
    assert out["ok"], out["stopped"]
    si = intent(p, out)
    assert si["status"] == "COMPLETED" and si["closed"]["rev"] == si["steps"][1]["revision"] + 1


def test_a_plan_that_breaks_the_stage_contract_commits_nothing(project, monkeypatch):
    p = project
    monkeypatch.setitem(stage.STAGES, "probe_notes", lambda a: [{"primitive": "checkpoint", "args": {}}])
    rev = p.rev()
    out = call(p, "probe_notes")
    assert not out["ok"] and out["stopped"]["error"]["code"] == "USAGE" and p.rev() == rev
    assert out["stage_intent_id"] is None
