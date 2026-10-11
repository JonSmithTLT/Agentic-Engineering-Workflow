"""The steering loop (M4-E E7b; CWR §7, §11; A1 §2 to §4; plan v3 E7 and §6; amendment 1, E7b's row and §2).

The loop advances only what the projection says is legal and needs no judgment, and stops for the same reasons in
every mode: steering decides who confirms, never what is legal. Walk auto-runs only bookkeeping (fail closed); E7b has
no confirmation, so an action that needs one never runs. The envelope bounds an activation; Run needs a live endpoint,
an executable notifier and hard deadlines. Every auto-run step is a normal stage call, attributed to the loop, and its
committed effects are checked against its declarations.

Most cases drive the real loop and the real stage runner over projections the test controls (``Scripted``); the probe
stages are the stage runner tests' (two checkpoints: bookkeeping only). The real projector, and real supervised runs,
are used where the guarantee is about them."""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from aewflow import create_planned_ticket, sample_project
from fake_harness import POLICY, HarnessLab
from invariants import load_control
from legality_modules import legality_modules
from notifier import Console, raise_to, recorder, seed, until
from test_stage_resolve import drift
from test_stage_runner import PROBES, intervene

from aew.engine import outbox
from aew.engine import primitives as P
from aew.engine.api import Engine
from aew.engine.primitives import PrimitiveSpec
from aew.harness import event_spool, operator_endpoint, runlog
from aew.harness import steering_loop as L
from aew.surface import contract, stage
from aew.surface import run as R
from aew.surface.context import SurfaceContext
from aew.surface.projection import project as real_project

SRC = Path(__file__).resolve().parents[2] / "src" / "aew"
CTX = SurfaceContext.outside_session()


# ---------------------------------------------------------------------------------------------- fixtures and helpers


def policy_text(project: Any, *, mode: str = "crawl", command: list[str] | None = None,
                envelope: dict[str, int] | None = None, notify: bool = True) -> None:
    """Write the execution policy's steering, envelope and notifier, then have the operator adopt it."""
    path = project.root / ".aew" / "policy" / "execution.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    doc["steering"] = {"mode": mode, **({"envelope": envelope} if envelope else {})}
    if notify and command:
        doc["notify"] = {"command": command}
    else:
        doc.pop("notify", None)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8", newline="\n")
    project.adopt_policy()


@pytest.fixture
def p(project, tmp_path, monkeypatch):
    """A project with the probe stages registered, steering adopted at crawl and an executable notifier."""
    for name, (row, planner) in PROBES.items():
        monkeypatch.setitem(contract.TOOLS, name, row)
        monkeypatch.setitem(stage.STAGES, name, planner)
    command, _ = recorder(tmp_path)
    project.extra["notify"] = command
    policy_text(project, command=command)
    return project


@pytest.fixture
def endpoint(project):
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=Console(), dev=True, timeout=10)
    ep.start()
    yield ep
    ep.close()


def mode(project: Any, to: str) -> None:
    """The effective mode, as the operator raises it at the endpoint (or the Lead lowers it)."""
    e = Engine.discover(project.root)
    if to == "crawl":
        return
    raise_to(e, to)


def action(name: str, args: dict[str, Any], *, availability: str = "AVAILABLE", auto: bool = True) -> dict[str, Any]:
    return {"action": name, "kind": "stage", "arguments": args, "operation_class": "MECHANICAL",
            "availability": availability, "callable": True, "auto_runnable": auto, "reason_codes": [],
            "cli_fallback": None}


def projection(subject: str, rev: int, *, actions: list[dict[str, Any]] | None = None, state: str = "READY",
               decisions: list[dict[str, Any]] | None = None, blockers: list[dict[str, Any]] | None = None,
               anomalies: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"revision": rev, "generation": 1, "subject": subject, "state": state, "actions": list(actions or []),
            "decisions_required": list(decisions or []), "blockers": list(blockers or []),
            "anomalies": list(anomalies or []), "hints": [], "runs": []}


class Scripted:
    """A projector that offers, on T-0001, what ``offer`` returns at the current revision (or nothing)."""

    def __init__(self, offer: Any, **unit: Any) -> None:
        self.offer, self.unit = offer, unit

    def __call__(self, engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        actions = self.offer(rev)
        return projection("project", rev), [projection("T-0001", rev, actions=actions, **self.unit)]


def notes(rev: int) -> list[dict[str, Any]]:
    return [action("probe_notes", {"expect_rev": rev, "note": "auto"})]


class Spy:
    """An executor that records what it would run and runs nothing."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, engine: Any, ctx: Any, name: str, arguments: dict[str, Any], **kw: Any) -> dict[str, Any]:
        self.calls.append(name)
        return {"ok": True, "stopped": None, "stage_intent_id": None, "revision": arguments.get("expect_rev")}


def loop(project: Any, projector: Any = None, *, executor: Any = None, clock: Any = None) -> L.SteeringLoop:
    e = Engine.discover(project.root)
    kw: dict[str, Any] = {"projector": projector or L._project_all}
    if executor is not None:
        kw["executor"] = executor
    if clock is not None:
        kw["clock"] = clock
    return L.SteeringLoop(e, generation=int(e.store.read()["lead"]["generation"]), session_label="lead-a",
                          token=lambda: project.token, poll_s=0.2, **kw)


def hot_intents(project: Any) -> dict[str, Any]:
    return load_control(project.root).get("stage_intents") or {}


def spooled(project: Any) -> list[dict[str, Any]]:
    path = event_spool.file_of(project.root / ".aew", event_spool.BROKER)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# ---------------------------------------------------------------------------------------------- Walk and confirmation


@pytest.mark.parametrize("case", ["undeclared", "unknown_class", "no_class", "outside_allow_list"])
def test_walk_confirms_unknown_or_undeclared_effects(p, monkeypatch, case):
    """A1 §2 / CWR §3 (`never_executes`; E7c adds `pending_and_notified`): Walk auto-runs only actions whose every
    declared effect is in {control_state}; an undeclared primitive, an unknown class, no class or a class outside the
    allow-list needs confirmation, and E7b never executes such an action. A bookkeeping-only stage runs."""
    mode(p, "walk")
    primitive = {"undeclared": "probe.nothing", "unknown_class": "probe.network", "no_class": "probe.silent",
                 "outside_allow_list": "work.assign"}[case]
    if case == "unknown_class":
        monkeypatch.setitem(P.SPECS, primitive, PrimitiveSpec(primitive, P.MECHANICAL, (), (), (),
                                                              "control_state+network_egress", "expected_revision",
                                                              None))
    if case == "no_class":
        monkeypatch.setitem(P.SPECS, primitive, PrimitiveSpec(primitive, P.MECHANICAL, (), (), (), "",
                                                              "expected_revision", None))
    row = PROBES["probe_notes"][0]._replace(name="probe_effect", expands_to=(primitive,))
    monkeypatch.setitem(contract.TOOLS, "probe_effect", row)
    spy = Spy()
    stop = loop(p, Scripted(lambda rev: [action("probe_effect", {"expect_rev": rev})]), executor=spy).activate()
    assert stop.code == L.CONFIRMATION_UNAVAILABLE and spy.calls == [], stop
    assert any(x["event"] == "loop_stopped" and L.CONFIRMATION_UNAVAILABLE in x["reason"] for x in spooled(p))
    ran = loop(p, Scripted(notes)).activate()  # control_state only: Walk runs it (until the repetition bound)
    assert ran.code == L.REPETITION, ran


@pytest.mark.parametrize("case", ["walk", "run"])
def test_confirm_before_actions_never_execute(p, endpoint, case):
    """Amendment 1, m3: when confirm_before(a) holds the action is never executed; the loop stops with
    CONFIRMATION_UNAVAILABLE (recorded in loop.json and the spool). ``run``: the mode in force when the action comes
    up is what counts, so a Lead that lowers Run to Walk stops a dispatching action from auto-running."""
    mode(p, "walk" if case == "walk" else "run")
    if case == "run":
        e = Engine.discover(p.root)
        e.steering_lower(token=p.token, expect_rev=p.rev(), mode="walk", rationale="the Lead restricts itself")
    spy = Spy()
    lp = loop(p, Scripted(lambda rev: [action("probe_start", {"expect_rev": rev, "work_id": "T-0001"})]),
              executor=spy)
    stop = lp.activate()
    assert stop.code == L.CONFIRMATION_UNAVAILABLE and spy.calls == [] and "work.assign" in stop.message
    state = json.loads((p.root / ".aew/local/steering/loop.json").read_text(encoding="utf-8"))
    assert state["status"] == "stopped" and state["stop"]["code"] == L.CONFIRMATION_UNAVAILABLE
    assert Engine.discover(p.root).status()["steering"]["loop"]["stop"]["code"] == L.CONFIRMATION_UNAVAILABLE


# ---------------------------------------------------------------------------------------------- the stop set (CWR §11)


def _corpus(rev: int) -> dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Projection states and what each stops on, whatever the mode."""
    eligible = notes(rev)
    high = {"code": "WORKSPACE_MUTATED", "message": "x", "details": {"anomaly": "ANM-0001", "severity": "high",
                                                                     "subject": "T-0001", "opened_rev": 1}}
    return {
        "high_anomaly": (projection("project", rev, anomalies=[high]), [projection("T-0001", rev, actions=eligible)]),
        "contradiction": (projection("project", rev, blockers=[{"code": "CONTRADICTION", "message": "x"}]),
                          [projection("T-0001", rev, actions=eligible)]),
        "decision": (projection("project", rev), [projection("T-0001", rev, actions=eligible, decisions=[
            {"decision": "PUBLISH", "evidence": [], "subject": "T-0001"}])]),
        "blocker": (projection("project", rev), [projection("T-0001", rev, actions=[action(
            "probe_notes", {"expect_rev": rev}, availability="BLOCKED", auto=False)], blockers=[
            {"code": "PROTECTED_CONDITION_OVERLAP", "message": "x"}])]),
        "unknown": (projection("project", rev), [projection("T-0001", rev, actions=[action(
            "probe_notes", {"expect_rev": rev}, availability="UNKNOWN", auto=False)])]),
        "judgment": (projection("project", rev), [projection("T-0001", rev, actions=[action(
            "probe_judged", {"expect_rev": rev, "work_id": "T-0001"}, auto=False)])]),
        "nothing": (projection("project", rev), [projection("T-0001", rev)]),
        "eligible": (projection("project", rev), [projection("T-0001", rev, actions=eligible)]),
    }


def test_stop_sets_identical_across_modes(p, endpoint):
    """CWR §11: on the same projections, Crawl, Walk and Run stop for the same reason, with the same message; only
    the confirmation differs (Crawl confirms the eligible bookkeeping step, Walk and Run run it)."""
    seen: dict[str, dict[str, Any]] = {}
    for m in ("crawl", "walk", "run"):
        if m != "crawl":
            mode(p, m)
        for name in _corpus(0):
            spy = Spy()
            got = loop(p, lambda e, c, s, name=name: _corpus(int(s["revision"]))[name], executor=spy).tick(
                L.Activation("LA-test", time.monotonic()))
            seen.setdefault(name, {})[m] = (got.code, got.message) if isinstance(got, L.Stop) else ("ran", spy.calls)
    for name, by_mode in seen.items():
        if name == "eligible":
            assert by_mode["crawl"][0] == L.CONFIRMATION_UNAVAILABLE
            assert by_mode["walk"] == by_mode["run"] == ("ran", ["probe_notes"]), by_mode
        else:
            assert by_mode["crawl"] == by_mode["walk"] == by_mode["run"], (name, by_mode)
    assert seen["high_anomaly"]["run"][0] == L.ANOMALY_HIGH and seen["blocker"]["run"][0] == L.BLOCKED


def test_loop_never_executes_judgment_or_unknown(p, endpoint):
    """CWR §11: zero execution of an action that is not auto-runnable (judgment-bearing) or whose availability is
    UNKNOWN, in Run itself."""
    mode(p, "run")
    for name in ("judgment", "unknown", "blocker"):
        spy = Spy()
        stop = loop(p, lambda e, c, s, name=name: _corpus(int(s["revision"]))[name], executor=spy).activate()
        assert spy.calls == [] and stop.code in (L.IDLE, L.UNKNOWN, L.BLOCKED), (name, stop)


@pytest.fixture
def calc(tmp_path, monkeypatch):
    """The sample project (its guardrails protect vendor/**), steering adopted at crawl with a notifier."""
    p = sample_project(tmp_path)
    command, _ = recorder(tmp_path)
    p.extra["notify"] = command
    policy_text(p, command=command)
    return p


def test_protected_path_overlap_stops_every_mode(calc, tmp_path):
    """CWR §11: a Ticket whose scope overlaps a protected path is BLOCKED by its dispatch guard, and the loop stops
    on that blocker in every mode, for the same reason, executing nothing."""
    wid = create_planned_ticket(calc, tmp_path, scope=("vendor/**",))
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(calc.root), console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        stops = []
        for m in ("crawl", "walk", "run"):
            if m != "crawl":
                mode(calc, m)
            spy = Spy()
            stop = loop(calc, executor=spy).activate()
            stops.append((stop.code, stop.message))
            assert spy.calls == []
    finally:
        ep.close()
    assert stops[0] == stops[1] == stops[2] and stops[0][0] == L.BLOCKED, stops
    assert "PROTECTED_CONDITION_OVERLAP" in stops[0][1] and wid in stops[0][1]


def test_high_anomaly_stops_every_mode(calc, tmp_path):
    """CWR §11 / plan v3 §2.4: an open high anomaly stops the loop in every mode, for the same reason, before any
    action is chosen, though a Ticket is ready to start."""
    create_planned_ticket(calc, tmp_path)

    def high(state: dict[str, Any]) -> None:
        state["counters"]["anomaly"] = 1
        state["anomalies"] = {"ANM-0001": {"id": "ANM-0001", "source": "WORKSPACE_MUTATED", "severity": "high",
                                           "subject": None, "detail": "seeded", "details": {}, "key": "k" * 32,
                                           "opened_at": "2026-10-11T00:00:00Z", "rev": 1, "disposition": None}}

    seed(calc, high)
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(calc.root), console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        stops = []
        for m in ("crawl", "walk", "run"):
            if m != "crawl":
                mode(calc, m)
            stop = loop(calc, executor=Spy()).activate()
            stops.append((stop.code, stop.message))
    finally:
        ep.close()
    assert stops[0] == stops[1] == stops[2] and stops[0][0] == L.ANOMALY_HIGH, stops


def test_mode_never_changes_a_guard_gate_or_transition(calc, tmp_path):
    """CWR §11 / A1 §6: raising or lowering the mode changes no guard, dispatch decision, stage availability or
    projected legality: only who confirms."""
    wid = create_planned_ticket(calc, tmp_path)

    def legality() -> Any:
        e = Engine.discover(calc.root)
        proj = real_project(e, CTX, wid)
        return ([e.guard_query(prim, wid, {"work_id": wid})["availability"] for prim in ("work.assign",)],
                {k: v for k, v in e.dispatch_explain(wid).items() if k not in ("revision", "generation")},
                [(a["action"], a["availability"], a["auto_runnable"], a["reason_codes"]) for a in proj["actions"]],
                proj["blockers"])

    before = legality()
    for m in ("walk", "run"):
        mode(calc, m)
        assert legality() == before, m
    Engine.discover(calc.root).steering_lower(token=calc.token, expect_rev=calc.rev(), mode="crawl")
    assert legality() == before


def test_legality_modules_never_import_steering():
    """CWR §11's static boundary: no legality, gate, transition, dispatch, plan-assurance, lint, evidence-acceptance
    or publication module (nor the policy package) imports the steering mode or the loop."""
    banned = {"aew.engine.steering", "aew.harness.steering_loop"}
    found = []
    for path in legality_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                     [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
                     if isinstance(node, ast.ImportFrom) and node.module else [])
            found += [(path.name, n) for n in names if n in banned]
    assert found == []


# ---------------------------------------------------------------------------------------------- the envelope (A1 §3)


def test_repetition_stops_after_n(p):
    """A1 §3.1: the same action on the same subject in the same state runs at most repetition_n (2) times with no
    other commit in between; the loop then stops, with attention, without a workflow transition."""
    mode(p, "walk")
    lp = loop(p, Scripted(notes))
    stop = lp.activate()
    assert stop.code == L.REPETITION and [x["action"] for x in lp.executed] == ["probe_notes"] * 2, stop
    assert [x["event"] for x in spooled(p)] == ["loop_stopped"]
    rev = p.rev()
    Engine.discover(p.root).checkpoint(token=p.token, expect_rev=rev, note="the Lead acts", next_action=None)
    again = loop(p, Scripted(notes)).activate()  # a commit not the loop's: progress the key cannot see, a new count
    assert again.code == L.REPETITION


@pytest.mark.parametrize("case", ["deadline", "max_actions"])
def test_envelope_exhaustion_stops_the_loop(p, case):
    """A1 §3 / plan v3 E7 (M8.4): an activation past loop_deadline_s, or at max_auto_actions, stops with attention
    and a notification; nothing else changes."""
    command = p.extra["notify"]
    policy_text(p, command=command, envelope={"loop_deadline_s": 60, "max_auto_actions": 1, "repetition_n": 10}
                if case == "max_actions" else {"loop_deadline_s": 60, "repetition_n": 10})
    mode(p, "walk")
    now = [1000.0]

    def clock() -> float:
        return now[0]

    def offer(rev: int) -> list[dict[str, Any]]:
        now[0] += 45.0  # each tick takes 45 s of the activation's time
        return notes(rev)

    lp = loop(p, Scripted(offer), clock=clock)
    stop = lp.activate()
    expected = L.MAX_AUTO_ACTIONS if case == "max_actions" else L.LOOP_DEADLINE
    assert stop.code == expected and len(lp.executed) == (1 if case == "max_actions" else 2), (stop, lp.executed)
    assert spooled(p)[-1]["reason"].startswith(expected)


# ---------------------------------------------------------------------------------------------- Run's conditions


def test_loop_refuses_run_without_a_live_endpoint(p):
    """Plan v3 §2.8 / E7 (N3): at each activation in Run the operator endpoint must answer, or the loop does not
    auto-run and stops with NOTIFIER_UNAVAILABLE; with the endpoint live it runs."""
    mode(p, "run")
    spy = Spy()
    stop = loop(p, Scripted(notes), executor=spy).activate()
    assert stop.code == L.NOTIFIER_UNAVAILABLE and spy.calls == [] and "operator endpoint" in stop.message, stop
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(p.root), console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        ran = loop(p, Scripted(notes)).activate()
    finally:
        ep.close()
    assert ran.code == L.REPETITION


def test_run_never_auto_starts_a_run_without_a_hard_deadline(p, endpoint):
    """A1 §3.2 / plan v3 E7: in Run, a dispatching action is refused (NO_HARD_DEADLINE) unless every execution
    profile policy routing can pick sets deadline_s; nothing is executed."""
    mode(p, "run")
    spy = Spy()
    stop = loop(p, Scripted(lambda rev: [action("ticket_start", {"expect_rev": rev, "work_id": "T-0001"})]),
                executor=spy).activate()
    assert stop.code == L.NO_HARD_DEADLINE and spy.calls == [], stop


# ---------------------------------------------------------------------------------------------- execution (CWR §7)


def test_auto_run_steps_are_attributed(p):
    """CWR §7, §11: every auto-run step is a normal stage call with its own StageIntent and history, attributed to
    the loop's activation, the steering mode and its record, the generation it was granted to, the policy digests and
    the projection it executed, in the intent's cold record and its commit's summary."""
    mode(p, "walk")
    lp = loop(p, Scripted(notes))
    lp.activate()
    sid = lp.executed[0]["intent"]
    e = Engine.discover(p.root)
    si = e.stage_intent(sid)
    assert si["status"] == "COMPLETED" and len(si["steps"]) == 2
    auto = si["auto_run"]
    view = e.steering_view()
    assert auto["by"] == "steering_loop" and auto["mode"] == "walk" and auto["mode_record"] == view["record"]
    assert auto["mode_generation"] == 1 and auto["projection"]["action"] == "probe_notes"
    assert auto["legality_digest"] == si["binding"]["legality_digest"] == e.policy_digests()["legality_digest"]
    record = outbox.read_record(p.root / ".aew", si["opened"]["rev"])
    assert record is not None and "auto-run by the steering loop in walk" in record["summary"]
    cold = list((p.root / ".aew/records/stage-intents").rglob(f"{sid}*"))
    assert cold and "steering_loop" in cold[0].read_text(encoding="utf-8")


def test_policy_drift_between_steps_is_stale_policy(p, monkeypatch):
    """CWR §11 (the loop's case; E3 built the Lead's): a legality policy adopted between two steps of an auto-run
    stage stops it as STALE_POLICY, and the loop stops on it: no step runs under a policy the stage did not bind."""
    mode(p, "walk")
    seen = intervene(monkeypatch, "checkpoint", times=2, before=lambda c: drift(p) if len(seen) == 2 else None)
    lp = loop(p, Scripted(notes))
    stop = lp.activate()
    assert stop.code == L.STALE_POLICY, stop
    si = Engine.discover(p.root).stage_intent(lp.executed[0]["intent"])
    assert si["status"] == "STOPPED_AT_BOUNDARY" and len(si["steps"]) == 1
    assert si["stopped"]["error"]["code"] == "STALE_POLICY"


def test_mode_change_mid_step_leaves_the_step(p, monkeypatch):
    """A3 / CWR §8: a mode changed while an auto-run stage is between its steps does not invalidate it. The mode is
    operational, so nothing is STALE_POLICY and the stage's binding is unchanged; the committed step stands. The
    change is a commit like any other, so the next step meets the ordinary CAS rule (a checkpoint's guard has no query
    form, so R5-1 does not retry it, and the stage stops there as STALE_REVISION). The next tick obeys the new mode."""
    mode(p, "walk")
    e = Engine.discover(p.root)
    digest = e.policy_digests()["legality_digest"]

    def lower(c: Any) -> None:
        if len(seen) == 2:
            e.steering_lower(token=p.token, expect_rev=int(e.store.read()["revision"]), mode="crawl")

    seen = intervene(monkeypatch, "checkpoint", times=2, before=lower)
    lp = loop(p, Scripted(notes))
    stop = lp.tick(L.Activation("LA-test", time.monotonic()))
    assert isinstance(stop, L.Stop) and stop.code == L.ACTION_STOPPED and "STALE_REVISION" in stop.message, stop
    first = Engine.discover(p.root).stage_intent(lp.executed[0]["intent"])
    assert len(first["steps"]) == 1 and first["stopped"]["error"]["code"] == "STALE_REVISION"  # never STALE_POLICY
    assert first["binding"]["legality_digest"] == digest == Engine.discover(p.root).policy_digests()["legality_digest"]
    assert Engine.discover(p.root).steering_view()["effective"] == "crawl"
    after = lp.tick(L.Activation("LA-next", time.monotonic()))
    assert isinstance(after, L.Stop) and after.code == L.CONFIRMATION_UNAVAILABLE


def test_loop_commit_stales_a_judgment_call_which_is_never_replayed(p):
    """Plan v3 §2.7 (n5): the loop's commit is real progress and stales the Lead's expect_rev. The Lead's
    judgment-bearing call then fails STALE_REVISION with nothing committed, and nothing replays it: not the stage
    runner (rule 5), not the loop (it never runs a judgment)."""
    mode(p, "walk")
    rev = p.rev()
    lp = loop(p, Scripted(notes))
    lp.activate()
    out = R.run_tool(Engine.discover(p.root), CTX, "ticket_draft",
                     {"expect_rev": rev, "title": "A judgment", "risk_class": 1}, token=p.token)
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_revision" and out["stage_intent_id"] is None
    assert not [u for u in load_control(p.root)["work"].values() if u.get("title") == "A judgment"]
    assert {x["action"] for x in lp.executed} == {"probe_notes"}


def test_two_intents_in_flight(p, monkeypatch):
    """Plan v3 §2.7: the bound on intents in flight is two, the Lead's call and one the loop auto-runs. The loop
    never advances a unit with an unfinished stage (the Lead's to resolve) and never stacks a second on it; the two
    are each checked by CAS, and the Lead's resolves afterwards as usual."""
    mode(p, "walk")
    wid = create_planned_ticket(p, p.root.parent)
    e = Engine.discover(p.root)
    lead = e.stage_open(token=p.token, expect_rev=p.rev(), tool="probe_start", contract_digest="0" * 64,
                        arguments={"work_id": wid}, judgment_inputs=[], base_class="POLICY_RESOLVED",
                        effective_class="POLICY_RESOLVED", subject=wid, ingress="test",
                        plan=[{"primitive": "checkpoint", "args": {}}, {"primitive": "work.assign",
                                                                         "args": {"work_id": wid}}])["intent"]
    counts: list[int] = []
    intervene(monkeypatch, "checkpoint", times=1, before=lambda c: counts.append(len(hot_intents(p))))

    def offer(engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        held = real_project(engine, ctx, wid)  # the Lead's unit: its unfinished stage is a decision
        return projection("project", rev), [held, projection("T-9999", rev, actions=notes(rev))]

    lp = loop(p, offer)
    lp.tick(L.Activation("LA-test", time.monotonic()))
    assert counts and max(counts) == 2, counts  # the Lead's, and the loop's while it ran
    assert [x["subject"] for x in lp.executed] == ["T-9999"]
    assert e.stage_intent(lead)["status"] == "ACTIVE" and len(hot_intents(p)) == 1
    out = R.run_tool(Engine.discover(p.root), CTX, "resolve", {"expect_rev": p.rev(), "subject": lead,
                                                                "choice": "abandon", "rationale": "done"},
                     token=p.token)
    assert out["ok"], out["stopped"]


# ---------------------------------------------------------------------------------------------- real runs


def _run_lab(tmp_path, monkeypatch, *, deadline_s: float | None = 600) -> tuple[Any, HarnessLab, str]:
    """A sample project routed to the fake harness, steering adopted at crawl with a notifier, a planned Ticket, the
    mode raised to run, and the operator endpoint started by the caller."""
    p = sample_project(tmp_path)
    command, _ = recorder(tmp_path)
    profile = {**POLICY["profiles"]["standard"], **({"deadline_s": deadline_s} if deadline_s else {})}
    lab = HarnessLab.create(p, tmp_path, policy={**POLICY, "profiles": {"standard": profile},
                                                 "steering": {"mode": "crawl"}, "notify": {"command": command}})
    for k, v in lab.env.items():
        monkeypatch.setenv(k, v)
    wid = create_planned_ticket(p, tmp_path)
    raise_to(Engine.discover(p.root), "run")
    return p, lab, wid


def test_runtime_excess_opens_an_anomaly(tmp_path, monkeypatch):
    """A1 §2.1 / SAE-07 at runtime: an auto-run step whose commit shows an effect its primitives do not declare
    (here, as if the dispatch and its launch declared neither a credential nor a process) opens a high anomaly and
    stops the loop with attention. The real projection's `ticket_start` is what the loop ran, on the steering loop's
    dispatch channel."""
    p, lab, wid = _run_lab(tmp_path, monkeypatch)
    lab.script("default", [{"do": "hang"}])
    for prim in ("work.assign", "dispatch.launch"):
        monkeypatch.setitem(P.SPECS, prim, P.SPECS[prim]._replace(side_effect_class="control_state+workspace"))
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(p.root), console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        lp = loop(p)
        stop = lp.activate()
        assert stop.code == L.SIDE_EFFECT_UNDECLARED, stop
        assert [x["action"] for x in lp.executed] == ["ticket_start"]
        state = load_control(p.root)
        [an] = [a for a in (state.get("anomalies") or {}).values() if a["source"] == "SIDE_EFFECT_UNDECLARED"]
        assert an["severity"] == "high" and an["subject"] == wid and "harness_process" in an["detail"]
        inv = state["invocations"][state["work"][wid]["implementer_invocation"]]
        assert inv["dispatch"]["channel"] == L.CHANNEL
        si = Engine.discover(p.root).stage_intent(lp.executed[0]["intent"])
        assert si["auto_run"]["mode"] == "run" and si["auto_run"]["projection"]["subject"] == wid
        assert spooled(p)[-1]["reason"].startswith(L.SIDE_EFFECT_UNDECLARED)
        assert loop(p).activate().code == L.ANOMALY_HIGH  # and it holds every mode until disposed of
    finally:
        ep.close()
        lab.cleanup()


def test_hard_deadline_terminates_and_releases_no_lease(tmp_path, monkeypatch):
    """A1 §3.2: a run past its profile's hard deadline is terminated by its supervisor and a low anomaly is recorded
    (by the next Lead commit); nothing is advanced, released or relaunched, and the invocation is left for the
    Lead's reconciliation."""
    p, lab, wid = _run_lab(tmp_path, monkeypatch, deadline_s=1.5)
    lab.script("default", [{"do": "hang"}])
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(p.root), console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        lp = loop(p)
        lp.activate()
        assert [x["action"] for x in lp.executed] == ["ticket_start"]
        state = load_control(p.root)
        inv_id = state["work"][wid]["implementer_invocation"]
        [run] = [r["run"] for r in state["invocations"][inv_id]["runs"]]
        until(lambda: (runlog.read_record(runlog.run_dir(p.root / ".aew", run)) or {}).get("status") == "terminated",
              60, "the hard deadline")
        before = load_control(p.root)
        Engine.discover(p.root).checkpoint(token=p.token, expect_rev=p.rev(), note="after the deadline",
                                           next_action=None)
        after = load_control(p.root)
        [an] = [a for a in after["anomalies"].values() if a["source"] == "HARD_DEADLINE"]
        assert an["severity"] == "low" and an["subject"] == wid
        assert after["work"][wid]["state"] == before["work"][wid]["state"] == "RUNNING"
        assert after["invocations"][inv_id]["status"] == "active" and len(after["invocations"][inv_id]["runs"]) == 1
        assert (after.get("queue") or {}).get("lease") == (before.get("queue") or {}).get("lease")
        assert loop(p).activate().code in (L.DECISION_REQUIRED, L.BLOCKED)  # the Lead's to reconcile, never relaunched
        assert len(load_control(p.root)["invocations"][inv_id]["runs"]) == 1
    finally:
        ep.close()
        lab.cleanup()


def test_the_loop_runs_in_the_broker_and_stops_with_its_session(p, tmp_path):
    """Plan v3 E7 (M8.1): the loop runs in the Lead broker, woken by a committed Lead tool call; it acts for the
    session's credential, and stops when the broker closes."""
    from aew.harness import lead_broker

    mode(p, "walk")
    broker = lead_broker.LeadBroker(Engine.discover(p.root), p.token)
    assert broker.loop is not None
    broker.loop._project = Scripted(notes)
    loop_json = p.root / ".aew/local/steering/loop.json"
    broker.start()
    try:
        until(lambda: loop_json.exists() and len(broker.loop.executed) == 2, 30, "the first activation")
        time.sleep(3 * lead_broker.POLL_S)  # its own commits are no wake: a second activation would show here
        assert len(broker.loop.executed) == 2
        out = broker._tool({"name": "checkpoint", "arguments": json.dumps({"expect_rev": p.rev(), "note": "Lead"}),
                            "ingress": "cli", "profile": "normal"})
        assert out["stage_result"]["ok"]
        until(lambda: len(broker.loop.executed) == 4, 30, "the activation the Lead's commit wakes")
    finally:
        broker.close()
    assert broker.loop._thread is not None and not broker.loop._thread.is_alive()
    assert [x["action"] for x in broker.loop.executed] == ["probe_notes"] * 4
    assert json.loads((p.root / ".aew/local/steering/loop.json").read_text())["stop"]["code"] == L.REPETITION


def test_a_project_without_steering_records_nothing(project):
    """Decision 3: with no steering mode the loop does nothing and writes nothing."""
    stop = loop(project, executor=Spy()).activate()
    assert stop.code == L.OFF and not (project.root / ".aew/local/steering/loop.json").exists()
    assert not event_spool.file_of(project.root / ".aew", event_spool.BROKER).exists()

