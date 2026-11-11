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
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from aewflow import (
    create_planned_ticket,
    sample_project,
    set_mutating_concurrency,
    stand_in_containment,
    without_steering,
)
from fake_harness import POLICY, HarnessLab
from invariants import load_control
from legality_modules import legality_modules
from notifier import Console, loop_chain, raise_to, recorder, seed, until
from racing_read import read_json_or_none
from test_stage_resolve import drift
from test_stage_runner import PROBES, call, intent, intervene, launching
from test_stages_request import implemented, seed_anomaly
from test_stages_ticket import HANG

from aew.engine import outbox
from aew.engine import primitives as P
from aew.engine import steering as S
from aew.engine.api import Engine
from aew.engine.primitives import PrimitiveSpec
from aew.harness import contract as K
from aew.harness import event_spool, operator_endpoint, runlog
from aew.harness import steering_loop as L
from aew.harness import wake_queue as W
from aew.history.index import INDEX_REL
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


class Acted:
    """The real stage runner, and an event set once a step returned: a test waits on what the loop did, never on how
    long it took (``HANG_S`` only bounds a hang)."""

    def __init__(self) -> None:
        self.done = threading.Event()

    def __call__(self, *args: Any, **kw: Any) -> dict[str, Any]:
        try:
            return L._run(*args, **kw)
        finally:
            self.done.set()


HANG_S = 60.0  # a guard against a hang on an event, never a timing expectation

NO_LOOK = 3600.0  # the coarse look out of the way: what a test waits on can only come from a wake or a commit


def activation_wait_s(lp: L.SteeringLoop) -> float:
    """How long a test waits for an activation of ``lp`` to show: the poll that wakes it, one wait for the control lock
    at its own store's lock timeout (``ControlStore``'s, 60 s by default: each tick reads and commits under that lock),
    and one more poll for its work. A literal 30 s sat below a single lock wait (the flake audit at c71ebc7e, §3 row
    12: "timed out waiting for the first activation", Windows, 2026-10-26).

    What it does not budget, each a stated edge (batch 5's m1 and m2):
    - the actions' own work, and any wait they make outside the control lock: a history index open there waits on
      SQLite under ``HistoryIndex``'s own timeout, not on this lock. The 11-08 sighting (main at dce6224c, job
      128630180357, Windows, the job at 19:58 of its 20 minutes) stalled about 60 s in one such open, with no other
      holder in its process, where this test's median is 8.33 s; the census found the first activation at 1.8 to 2.4 s
      with only the loop opening the index, so it is counted as runner starvation, not this window's to absorb;
    - a chain of activations: the repetition test's wait covers ``repetition_n + 1`` activations, each after a poll,
      so ``repetition_n - 1`` of its polls and all of their work fall outside this window, and a lock wait ending
      within that much of the lock timeout still exceeds it;
    - the waits on what the loop does that still use ``HANG_S`` (a literal 60 s, one lock wait at the default):
      ``Acted.done``, ``Looks``, the closing test's drain and the loop thread's join. They bound a hang, never a
      timing expectation."""
    return lp.engine.store.lock_timeout + 2 * lp.poll_s


class Looks:
    """Counts the loop's quiet looks: a poll that no wake ended and that found nothing moved (``_changed`` false). The
    loop looks only between activations and with no wake pending, so once it has looked quietly, whatever came
    before (a commit included) has had its chance to start an activation. A test that claims nothing more happened
    waits for one such look, never a sleep a slow runner can end too early (the flake audit's rank 4); ``HANG_S``
    only bounds a hang."""

    def __init__(self, lp: L.SteeringLoop) -> None:
        self.quiet = 0
        self._cv = threading.Condition()
        self._real = lp._changed
        lp._changed = self._changed  # type: ignore[method-assign]

    def _changed(self) -> bool:
        changed = self._real()
        if not changed:
            with self._cv:
                self.quiet += 1
                self._cv.notify_all()
        return changed

    def another(self) -> None:
        """Wait for a quiet look that starts after this call."""
        with self._cv:
            seen = self.quiet
            assert self._cv.wait_for(lambda: self.quiet > seen, HANG_S), "the loop never looked again"


def loop(project: Any, projector: Any = None, *, executor: Any = None, clock: Any = None,
         coarse_s: float = NO_LOOK) -> L.SteeringLoop:
    e = Engine.discover(project.root)
    kw: dict[str, Any] = {"projector": projector or L._project_all, "coarse_s": coarse_s}
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


# ---------------------------------------------------------------------------------------------- the order (E227)


DRAFT = {"title": "Add subtract()", "risk_class": 1, "scope": ["calc/**", "tests/**"],
         "goal": ["calc.core.subtract(5, 3) == 2 through the public module"]}


def test_the_loop_starts_the_critical_ticket_first_whatever_the_ids(p):
    """Register E227, through the real tick (review of the priority PR, m4): two Tickets drafted through
    `ticket_draft`, the later one critical; the loop projects them from the committed state, ranks them by that state
    and takes the critical one first, though its id is higher. Each Ticket is offered one bookkeeping step, so Walk
    runs it with no confirmation."""
    ids = []
    for extra in ({}, {"priority": "critical", "priority_reason": "the release waits on it"}):
        out = call(p, "ticket_draft", **DRAFT, **extra)
        assert out["ok"], out.get("stopped")
        ids.append(intent(p, out)["subject"]["id"])
    normal, critical = ids
    assert normal < critical

    def projector(engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        _, real = L._project_all(engine, ctx, state)
        subjects = {str(unit["subject"]) for unit in real}
        assert subjects >= {normal, critical}, subjects
        offered = {str(unit["subject"]): [action("probe_notes", {"expect_rev": rev, "note": unit["subject"]})]
                   for unit in real}
        return projection("project", rev), [projection(s, rev, actions=offered[s]) for s in offered]

    took: list[str] = []

    def executor(engine: Any, ctx: Any, name: str, arguments: dict[str, Any], **kw: Any) -> dict[str, Any]:
        took.append(arguments["note"])
        return {"ok": True, "stopped": None, "stage_intent_id": None, "revision": arguments.get("expect_rev")}

    mode(p, "walk")
    loop(p, projector, executor=executor).activate()
    assert took and took[0] == critical, took


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
    assert stop_lines(p) == []  # recorded, but held from the spool until E7c (L.HELD_UNTIL_E7C)
    ran = loop(p, Scripted(notes)).activate()  # control_state only: Walk runs it (until the repetition bound)
    assert ran.code == L.REPETITION, ran


@pytest.mark.parametrize("case", ["walk", "run"])
def test_confirm_before_actions_never_execute(p, endpoint, case):
    """Amendment 1, m3: when confirm_before(a) holds the action is never executed; the loop stops with
    CONFIRMATION_UNAVAILABLE (recorded in loop.json; held from the spool until E7c). ``run``: the mode in force when the
    action comes up is what counts, so a Lead that lowers Run to Walk stops a dispatching action from auto-running."""
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


def test_under_run_a_ticket_held_for_a_conflict_is_started_by_the_loop_once_released(tmp_path, monkeypatch):
    """E228's proof: under Run, a Ticket whose scope meets a live Ticket's is held by the launch conflict check
    (FILES_CONFLICT, CNI-03.a), and the loop stops on that hold, starting nothing for it; once the live Ticket is
    cancelled, which releases its workspace, the same loop's next activation starts the held one through the real
    tool (no recorder: it is RUNNING with a run on the fake harness), with no Lead call in between."""
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    lab.script("default", HANG)
    try:
        set_mutating_concurrency(p, 3)
        command, _ = recorder(tmp_path)
        bounded(p, command)
        first = create_planned_ticket(p, tmp_path, title="Add subtract()", scope=("calc/**", "tests/**"))
        second = create_planned_ticket(p, tmp_path, title="Add two", scope=("calc/two.py", "tests/test_two.py"))
        p.lead("work", "assign", first)
        raise_to(Engine.discover(p.root), "run")
        ep = operator_endpoint.OperatorEndpoint(Engine.discover(p.root), console=Console(), dev=True, timeout=10)
        ep.start()
        try:
            lp = loop(p)  # one loop for both activations, as the broker keeps one
            stop = lp.activate()
            assert stop.code == L.BLOCKED and stop.subject == second and "FILES_CONFLICT" in stop.message, stop
            assert not [x for x in lp.executed if x["subject"] == second], lp.executed
            p.lead("work", "transition", first, "--to", "CANCELLED", "--reason", "the objective moved elsewhere")
            lp.activate()
        finally:
            ep.close()
        started = [x for x in lp.executed if (x["action"], x["subject"]) == ("ticket_start", second)]
        assert started and started[0]["ok"], lp.executed
        control = load_control(p.root)
        assert control["work"][second]["state"] == "RUNNING", control["work"][second]
        invocations = [i for i in control["invocations"].values() if i["work_unit"] == second]
        assert invocations and invocations[-1]["runs"], invocations  # the run the start launched is recorded
    finally:
        lab.cleanup()


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


def test_under_run_the_loop_takes_in_an_implementer_run_itself(tmp_path, monkeypatch):
    """CL-R07's last bullet (review of E228's PR, M3): under Run the loop auto-runs `ticket_request_review` on a
    RUNNING Ticket whose implementer reported, and that stage's transition guard ingests the run, so the loop will
    take the run's end in itself (``will_ingest``), derived from the guards, not from names; under Walk, or for a
    READY Ticket, it won't."""
    sp = sample_project(tmp_path)
    command, _ = recorder(tmp_path)
    policy_text(sp, command=command)
    wid, _ = implemented(sp, tmp_path)
    bounded(sp, command)
    e = Engine.discover(sp.root)
    raise_to(e, "walk")
    assert not loop(sp).will_ingest(e.store.current(), wid)  # Walk confirms it: the Lead's
    raise_to(e, "run")
    state = e.store.current()
    assert loop(sp).will_ingest(state, wid)
    offered = [a for a in L._project_all(e, loop(sp)._ctx(), state)[1][0]["actions"] if a.get("auto_runnable")]
    assert [a["action"] for a in offered] == ["ticket_request_review"]
    assert L.ingesting_action(state, offered[0]) and not L.ingesting_action(
        state, action("ticket_start", {"work_id": wid}))
    spy = Spy()
    ep = operator_endpoint.OperatorEndpoint(e, console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        stop = loop(sp, executor=spy).activate()
    finally:
        ep.close()
    # the loop takes it: every profile sets deadline_s, so Run's own checks let the step run
    assert "ticket_request_review" in spy.calls, (stop, spy.calls)


def test_under_run_the_loop_auto_runs_ticket_request_review_through_the_real_tool(tmp_path, monkeypatch):
    """E228: the loop under Run auto-runs `ticket_request_review` itself, through ``run_tool`` as a Lead's call would
    (no spy): the Ticket whose implementer reported moves to REVIEW_PENDING, its reviewer is launched on the fake
    harness, and the stage is attributed to the loop."""
    sp = sample_project(tmp_path)
    lab = launching(sp, tmp_path, monkeypatch)
    lab.script("default", HANG)
    try:
        command, _ = recorder(tmp_path)
        wid, _ = implemented(sp, tmp_path)
        bounded(sp, command)
        e = Engine.discover(sp.root)
        raise_to(e, "run")
        ep = operator_endpoint.OperatorEndpoint(e, console=Console(), dev=True, timeout=10)
        ep.start()
        try:
            lp = loop(sp)
            lp.activate()
        finally:
            ep.close()
        first = lp.executed[0]
        assert (first["action"], first["subject"], first["ok"]) == ("ticket_request_review", wid, True), lp.executed
        assert load_control(sp.root)["work"][wid]["state"] == "REVIEW_PENDING"
        si = e.stage_intent(first["intent"])
        assert [s["primitive"] for s in si["steps"]] == ["work.transition", "invoke.create.mutating",
                                                         "dispatch.launch"], si
        assert si["steps"][2]["outputs"]["runs"], si  # the reviewer was launched
        assert si["auto_run"]["mode"] == "run", si  # attributed to the loop, under Run
    finally:
        lab.cleanup()


def bounded(project: Any, command: list[str]) -> None:
    """A configured execution policy whose every profile sets ``deadline_s``, so Run may auto-run a step that starts a
    run (A1 §3.2), with steering and the notifier as ``policy_text`` writes them."""
    path = project.root / ".aew" / "policy" / "execution.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    doc.update({k: v for k, v in POLICY.items() if k != "profiles"})
    doc["profiles"] = {"standard": {**POLICY["profiles"]["standard"], "deadline_s": 600}}
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8", newline="\n")
    policy_text(project, command=command)


def _held_ahead(tmp_path: Path, held: str) -> tuple[Any, str, str | None]:
    """A Run project whose T-0002 is RUNNING with its implementer reported, and a stop the loop meets first: an
    earlier READY Ticket (no profile sets deadline_s, so its start stops at NO_HARD_DEADLINE), an open high
    anomaly, or (``own_stop``) none here: the test's projector holds the loop on the Ticket's own blocker."""
    sp = sample_project(tmp_path)
    command, _ = recorder(tmp_path)
    policy_text(sp, command=command)
    (tmp_path / "ahead").mkdir()
    first = create_planned_ticket(sp, tmp_path / "ahead", scope=("docs/**",)) if held == "ticket_ahead" else None
    wid, _ = implemented(sp, tmp_path)
    if held == "project_anomaly":
        seed_anomaly(sp, None)
    raise_to(Engine.discover(sp.root), "run")
    return sp, wid, first


@pytest.mark.parametrize("held", ["ticket_ahead", "project_anomaly", "own_stop"])
def test_a_loop_held_on_a_told_stop_ahead_of_the_ticket_leaves_its_run_end_to_the_lead(tmp_path, held):
    """Quick check of E228's PR, QC-M1 (the reviewer's q2): the loop is held, every activation, on a stop it already
    told (the same occurrence), ahead of the Ticket's `ticket_request_review`, so it never takes the run in until the
    Lead acts. ``will_ingest`` says so, and the queue keeps the run's end for the Lead. The second quick check's
    QC2-n1: a told stop about the Ticket itself holds it the same way, though its own projection offers the step."""
    sp, wid, first = _held_ahead(tmp_path, held)
    e = Engine.discover(sp.root)
    spy = Spy()
    ep = operator_endpoint.OperatorEndpoint(e, console=Console(), dev=True, timeout=10)
    ep.start()

    def own_blocker(engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        return projection("project", rev), [projection(wid, rev, state="RUNNING", blockers=[
            {"code": "FILES_CONFLICT", "message": "held"}])]

    try:
        lp = loop(sp, own_blocker if held == "own_stop" else None, executor=spy)
        s1 = lp.activate()
        r1 = recorded(sp)
        s2 = lp.activate()
        r2 = recorded(sp)
    finally:
        ep.close()
    assert s1 == s2, (s1, s2)
    if held == "own_stop":
        assert s1.subject == wid and s1.code == L.BLOCKED, s1
    elif first:
        assert s1.subject == first and s1.code == L.NO_HARD_DEADLINE, s1
    else:
        assert s1.code == L.ANOMALY_HIGH, s1
    assert r1["occurrence"] == r2["occurrence"], "the held stop is one occurrence: told once"
    assert "ticket_request_review" not in spy.calls
    assert not lp.will_ingest(e.store.current(), wid)


def test_the_loop_takes_in_only_a_run_whose_step_it_auto_runs(p, monkeypatch):
    """Quick check of E228's PR, QC-m1: `ticket_request_verification` ingests the run (its guard is in the set) but
    bears judgment, so the loop never auto-runs it: a RUNNING Ticket offering it leaves the run's end to the Lead."""
    from aew.surface import projection as pj

    mode(p, "run")
    state = Engine.discover(p.root).store.current()
    state["work"] = {"T-0001": {"kind": "ticket", "state": "RUNNING"}}  # what the guards see of it
    offered: list[dict[str, Any]] = []
    monkeypatch.setattr(pj, "project", lambda engine, ctx, subject: {"actions": offered})
    verification = action("ticket_request_verification", {"work_id": "T-0001"}, auto=False)
    assert L.ingesting_action(state, verification)
    offered[:] = [verification]
    assert not loop(p).will_ingest(state, "T-0001")
    offered[:] = [{**verification, "auto_runnable": True}]  # the same step, were it auto-run, would be the loop's
    assert loop(p).will_ingest(state, "T-0001")


def test_an_endpoint_lost_mid_activation_stops_run_before_its_next_action(p, endpoint, monkeypatch):
    """Register E228: in Run the endpoint is asked before every auto-run action, not once per activation, so an
    endpoint that goes away after the first action stops the loop (NOTIFIER_UNAVAILABLE) before the second runs."""
    from aew import errors
    from aew.harness import operator_client

    mode(p, "run")
    real, asked = operator_client.ping, []

    def ping(aew_root: Path) -> dict[str, Any]:
        asked.append(1)
        if len(asked) > 1:
            raise errors.NotFound("no operator endpoint answers (it went away)")
        return real(aew_root)

    monkeypatch.setattr(operator_client, "ping", ping)
    lp = loop(p, Scripted(notes))
    stop = lp.activate()
    assert stop.code == L.NOTIFIER_UNAVAILABLE and "it went away" in stop.message, stop
    assert [x["action"] for x in lp.executed] == ["probe_notes"] and len(asked) == 2


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


def test_a_mode_change_is_never_stale_policy(p, monkeypatch):
    """A3 §6: the mode is operational, so a mode changed between an auto-run stage's steps never makes it
    STALE_POLICY and leaves its binding unchanged; the committed step stands, and the next tick obeys the new mode.
    The change is itself a commit, so the next step meets the ordinary CAS: here a probe whose checkpoint guard has no
    query form, which R5-1 cannot re-ask, so the probe stops as STALE_REVISION. A stage R5-1 can re-ask completes:
    ``test_mode_change_mid_step_leaves_the_step``."""
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


# ---------------------------------------------------------------------------------------------- occurrences (CL-R07)


def recorded(project: Any) -> dict[str, Any]:
    return json.loads((project.root / ".aew" / S.LOOP_REL).read_text(encoding="utf-8"))["stop"]


class Turns:
    """A projector that offers, on each call, the next of ``script``'s projections of T-0001 and T-0002 (the last
    one repeats): ``"act"`` offers a bookkeeping step, ``"blocked"`` a blocker."""

    def __init__(self, *script: dict[str, str]) -> None:
        self.script, self.calls = list(script), 0

    def __call__(self, engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        turn = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        units = []
        for subject, what in sorted(turn.items()):
            if what == "act":
                units.append(projection(subject, rev, actions=[action("probe_notes", {"expect_rev": rev,
                                                                                        "note": subject})]))
            else:
                units.append(projection(subject, rev, blockers=[{"code": "FILES_CONFLICT", "message": "held"}]))
        return projection("project", rev), units


def test_a_stuck_stop_keeps_its_occurrence_however_often_it_is_recorded(p):
    """Review of E228's PR, M2: the loop records the same stop on every look while it is stuck; it is one
    occurrence, so the Lead is told it once."""
    mode(p, "walk")
    lp = loop(p, Turns({"T-0001": "blocked"}), executor=Spy())
    first = lp.activate()
    assert first.code == L.BLOCKED and recorded(p)["occurrence"] == 1
    for _ in range(3):
        lp.activate()
    assert recorded(p)["occurrence"] == 1 and recorded(p)["condition"] == L.condition_key(first)


def test_acting_on_a_stops_subject_then_stopping_there_again_is_a_new_occurrence(p):
    """Review of E228's PR, M2: within one activation the loop acts on T-0001 and stops on it again, with no record
    between: that is a new occurrence, so a Lead told of the first is told of the second."""
    mode(p, "walk")
    lp = loop(p, Turns({"T-0001": "blocked"}, {"T-0001": "act"}, {"T-0001": "blocked"}), executor=Spy())
    lp.activate()
    assert recorded(p)["occurrence"] == 1
    lp.activate()  # acts on T-0001, then stops on the same condition
    assert recorded(p)["occurrence"] == 2


def test_an_action_on_another_subject_never_moves_a_stuck_stops_occurrence(p):
    """A busy activation doesn't re-tell a stuck Ticket's stop: the loop acting on T-0002 leaves T-0001's occurrence
    as it was."""
    mode(p, "walk")
    lp = loop(p, Turns({"T-0001": "blocked", "T-0002": "blocked"}, {"T-0001": "blocked", "T-0002": "act"},
                       {"T-0001": "blocked", "T-0002": "blocked"}), executor=Spy())
    lp.activate()
    before = recorded(p)
    lp.activate()
    after = recorded(p)
    assert after["subject"] == before["subject"] == "T-0001" and after["occurrence"] == before["occurrence"] == 1


class ProjectHeld:
    """A projector that offers, on each call, the next of ``script``'s turns (the last one repeats): ``"project"`` a
    project-level blocker, ``"act"`` a bookkeeping step on T-0001, ``"idle"`` nothing."""

    def __init__(self, *script: str) -> None:
        self.script, self.calls = list(script), 0

    def __call__(self, engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        turn = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if turn == "project":
            return projection("project", rev, blockers=[{"code": "POLICY_DRIFT", "message": "held"}]), []
        if turn == "act":
            return projection("project", rev), [projection("T-0001", rev, actions=[
                action("probe_notes", {"expect_rev": rev, "note": "T-0001"})])]
        return projection("project", rev), []


def test_a_project_stop_after_the_loop_acted_on_anything_is_a_new_occurrence(p):
    """Quick check of E228's PR, QC-m2: ``select`` returns a project stop before any choice, so an action on any
    subject means the project stop had cleared: the same project stop again is a new occurrence."""
    mode(p, "walk")
    lp = loop(p, ProjectHeld("project", "act", "project"), executor=Spy())
    lp.activate()
    assert recorded(p)["subject"] == "project" and recorded(p)["occurrence"] == 1
    lp.activate()  # acts on T-0001, then the project stop again
    assert recorded(p)["subject"] == "project" and recorded(p)["occurrence"] == 2


def test_a_stop_recorded_after_an_idle_record_is_a_new_occurrence(p):
    """Quick check of E228's PR, QC-M1: the premise that lets ``will_ingest`` leave a run to an idle loop. Whatever
    stop the loop records next, though it is one the Lead was told before, is a new occurrence, so it wakes."""
    mode(p, "walk")
    lp = loop(p, Turns({"T-0001": "blocked"}, {}, {"T-0001": "blocked"}), executor=Spy())
    lp.activate()
    assert recorded(p)["occurrence"] == 1
    assert lp.activate().code == L.IDLE
    lp.activate()
    assert recorded(p)["code"] == L.BLOCKED and recorded(p)["occurrence"] > 1


def test_the_loops_record_redacts_before_its_cut(p):
    """Review of E228's PR, m4 (the quick check's q4): a synthetic credential straddling the record's 2000-character
    cut is redacted first, so no fragment of it survives."""
    key = "aew1.tk_" + "0123456789abcdef" + "." + "S" * 30  # synthetic
    filler = "x" * (2000 - len("T-0001: FILES_CONFLICT: ") - 1 - 12)  # the key's body straddles character 2000

    def held(engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rev = int(state["revision"])
        return projection("project", rev), [projection("T-0001", rev, blockers=[
            {"code": "FILES_CONFLICT", "message": filler + " " + key}])]

    mode(p, "walk")
    loop(p, held, executor=Spy()).activate()
    raw = (p.root / ".aew" / S.LOOP_REL).read_text(encoding="utf-8")
    assert "tk_0123" not in raw and len(recorded(p)["message"]) <= 2000


def test_a_restarted_broker_in_the_same_generation_keeps_the_occurrence(p):
    """The occurrence is read from the loop's own last record, so a new loop of the same generation (a broker
    restart) keeps it, and doesn't tell the Lead again."""
    mode(p, "walk")
    loop(p, Turns({"T-0001": "blocked"}), executor=Spy()).activate()
    loop(p, Turns({"T-0001": "blocked"}), executor=Spy()).activate()
    assert recorded(p)["occurrence"] == 1


def test_a_stop_only_the_lead_can_clear_is_reported_ahead_of_one_that_clears_itself():
    """Review of the priority PR, m6: with nothing eligible, a Ticket's decision is the stop reported, though an
    earlier Ticket is BLOCKED on a conflict that can clear without the Lead."""
    units = [projection("T-0001", 3, blockers=[{"code": "FILES_CONFLICT", "message": "held"}]),
             projection("T-0002", 3, decisions=[{"decision": "plan_acceptance", "evidence": []}])]
    stop = L.select(projection("project", 3), units)
    assert stop.code == L.DECISION_REQUIRED and stop.subject == "T-0002", stop
    alone = L.select(projection("project", 3), units[:1])
    assert alone.code == L.BLOCKED and alone.subject == "T-0001"


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


RUN_ONLY = 1.5  # a Run-scoped deadline short enough to end a hanging run inside the test


def _run_scoped_lab(tmp_path, monkeypatch, *, run: bool) -> tuple[Any, HarnessLab, str]:
    """A sample project on the fake harness whose profile's deadline is Run's alone (``deadline_scope: run``, as first
    configuration writes it), a planned Ticket, and the mode raised to Run or left at crawl."""
    p = sample_project(tmp_path)
    command, _ = recorder(tmp_path)
    profile = {**POLICY["profiles"]["standard"], "deadline_s": RUN_ONLY, "deadline_scope": "run"}
    lab = HarnessLab.create(p, tmp_path, policy={**POLICY, "profiles": {"standard": profile},
                                                 "steering": {"mode": "crawl"}, "notify": {"command": command}})
    for k, v in lab.env.items():
        monkeypatch.setenv(k, v)
    wid = create_planned_ticket(p, tmp_path)
    if run:
        raise_to(Engine.discover(p.root), "run")
    lab.script("default", HANG)
    return p, lab, wid


def test_a_run_started_under_run_keeps_its_deadline_when_run_ends_during_its_launch(tmp_path, monkeypatch):
    """Quick check of E228's third PR, M1: the Run-only deadline is decided at custody, from the state custody was
    checked against, never after the launch. Run is lowered while the supervisor is held after launching the
    harness, and the run still ends at its deadline."""
    p, lab, wid = _run_scoped_lab(tmp_path, monkeypatch, run=True)
    held = tmp_path / "launched-held"
    held.write_text("hold", encoding="utf-8")
    try:
        res = lab.lead_res("work", "assign", wid, "--launch", env={
            "AEW_FAULT": "harness.launch.after_handoff", "AEW_PAUSE": f"harness.supervisor.launched={held}"})
        assert res.returncode == 86, res.stdout  # the launcher ends at the hand-off; its supervisor goes on
        lab.until(lambda: Path(f"{held}.reached").exists(), what="the supervisor held after its launch")
        Engine.discover(p.root).steering_lower(token=p.token, expect_rev=p.rev(), mode="crawl",
                                               rationale="Run ends while the harness starts")
        held.unlink()
        run = lab.until(lambda: next(iter(load_control(p.root)["invocations"].values()))["runs"][0]["run"],
                        what="the run recorded")
        record = lab.until(lambda: (r := lab.record(run)).get("status") == "terminated" and r, what="the deadline")
        assert f"deadline of {RUN_ONLY}s exceeded" in record["reason"], record
    finally:
        held.unlink(missing_ok=True)
        lab.cleanup()


def test_an_attended_run_never_gets_a_run_only_deadline(tmp_path, monkeypatch):
    """Quick check of E228's third PR, M2: the supervisor's watch applies the deadline decided for the run, not the
    profile's as written: under crawl a Run-scoped deadline bounds nothing, so a run is still running well past it.
    (An absence, read after three times the deadline: a slow runner can only delay a wrong termination, never fail
    this test; the planted control is the test above, where the same deadline ends the run.)"""
    p, lab, wid = _run_scoped_lab(tmp_path, monkeypatch, run=False)
    try:
        run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
        lab.until(lambda: lab.record(run).get("status") == "running", what="the run running")
        time.sleep(3 * RUN_ONLY)
        record = lab.record(run)
        assert record.get("status") == "running", record
    finally:
        lab.cleanup()


def test_the_loop_runs_in_the_broker_and_stops_with_its_session(p, tmp_path):
    """Plan v3 E7 (M8.1): the loop runs in the Lead broker, woken by a committed Lead tool call; it acts for the
    session's credential, and stops when the broker closes."""
    from aew.harness import lead_broker

    mode(p, "walk")
    broker = lead_broker.LeadBroker(Engine.discover(p.root), p.token)
    assert broker.loop is not None
    broker.loop._project = Scripted(notes)
    looks = Looks(broker.loop)
    loop_json = p.root / ".aew/local/steering/loop.json"
    broker.start()
    try:
        until(lambda: loop_json.exists() and len(broker.loop.executed) == 2, activation_wait_s(broker.loop),
              "the first activation", describe=loop_chain(broker))
        looks.another()  # its own commits are no wake: a second activation would have run before this look
        assert len(broker.loop.executed) == 2
        out = broker._tool({"name": "checkpoint", "arguments": json.dumps({"expect_rev": p.rev(), "note": "Lead"}),
                            "ingress": "cli", "profile": "normal"})
        assert out["stage_result"]["ok"]
        until(lambda: len(broker.loop.executed) == 4, activation_wait_s(broker.loop),
              "the activation the Lead's commit wakes", describe=loop_chain(broker))
    finally:
        broker.close()
    assert broker.loop._thread is not None and not broker.loop._thread.is_alive()
    assert [x["action"] for x in broker.loop.executed] == ["probe_notes"] * 4
    assert json.loads((p.root / ".aew/local/steering/loop.json").read_text())["stop"]["code"] == L.REPETITION


def test_a_project_without_steering_records_nothing(project):
    """Decision 3: with no steering mode the loop does nothing and writes nothing."""
    without_steering(project)
    stop = loop(project, executor=Spy()).activate()
    assert stop.code == L.OFF and not (project.root / ".aew/local/steering/loop.json").exists()
    assert not event_spool.file_of(project.root / ".aew", event_spool.BROKER).exists()


# ---------------------------------------------------------------------------------------------- review of PR #199


def stop_lines(project: Any) -> list[str]:
    return [x["reason"] for x in spooled(project) if x["event"] == "loop_stopped"]


def test_a_standing_stop_is_notified_once(p, monkeypatch):
    """F1: one standing condition (T-0001's start needs a confirmation E7b cannot give) is one occurrence, notified
    once, however many unrelated commits wake the loop meanwhile: each moves the revision, never the condition. The
    stop is notified as it will be once E7c lifts the hold (``HELD_UNTIL_E7C`` emptied here)."""
    monkeypatch.setattr(L, "HELD_UNTIL_E7C", frozenset())
    mode(p, "walk")
    lp = loop(p, Scripted(lambda rev: [action("probe_start", {"expect_rev": rev, "work_id": "T-0001"})]))
    assert lp.activate().code == L.CONFIRMATION_UNAVAILABLE
    e = Engine.discover(p.root)
    for n in range(5):  # the Lead works elsewhere; each of its commits wakes the loop (lead_broker._tool)
        e.checkpoint(token=p.token, expect_rev=p.rev(), note=f"Lead work {n}", next_action=None)
        assert lp.activate().code == L.CONFIRMATION_UNAVAILABLE
    assert len(stop_lines(p)) == 1, stop_lines(p)


class Poster:
    """The Lead session the wake queue posts into: idle, and every post lands."""

    def __init__(self) -> None:
        self.posts: list[str] = []

    def busy(self) -> bool:
        return False

    def post(self, wake_id: str, text: str) -> str:
        self.posts.append(text)
        return "ses_1"

    def landed(self, wake_id: str) -> str:
        return W.DELIVERED


def lead_wake(project: Any) -> tuple[W.WakeQueue, Poster]:
    """One tick of the Lead broker's wake queue over the project as the loop left it."""
    poster = Poster()
    q = W.WakeQueue(project.root / ".aew", poster=poster, state=lambda: Engine.discover(project.root).store.read(),
                    quiet_s=lambda: 1200, clock=time.time)
    q.tick()
    return q, poster


def test_until_e7c_a_crawl_confirmation_stop_is_recorded_but_neither_notified_nor_woken(p, tmp_path):
    """The operator's ruling on the quick check of E228's fourth PR, QC-1 (c): under crawl, from ``aew init``, a
    planned Ticket stops the loop with ``CONFIRMATION_UNAVAILABLE``, which nothing can act on until E7c (no
    confirmation exists, and crawl cannot be lowered). It is recorded, so ``status`` shows it, but it writes no spool
    line (no toast) and gathers no ``loop_waiting`` wake for the Lead."""
    create_planned_ticket(p, tmp_path, title="Add subtract()", scope=("calc/**", "tests/**"))
    spy = Spy()
    stop = loop(p, executor=spy).activate()
    assert stop.code == L.CONFIRMATION_UNAVAILABLE and stop.attention and spy.calls == [], stop
    assert Engine.discover(p.root).status()["steering"]["loop"]["stop"]["code"] == L.CONFIRMATION_UNAVAILABLE
    assert spooled(p) == []
    q, poster = lead_wake(p)
    assert q.doc["wake"] is None and poster.posts == [], q.doc


def test_any_other_stop_is_still_notified_and_wakes_the_lead(p):
    """The hold is that one code's: a stop with any other reason (here the envelope's ``REPETITION``) still writes its
    spool line and is posted to the Lead as ``loop_waiting``."""
    mode(p, "walk")
    stop = loop(p, Scripted(notes)).activate()
    assert stop.code == L.REPETITION, stop
    assert [x["event"] for x in spooled(p)] == ["loop_stopped"]
    q, poster = lead_wake(p)
    assert len(poster.posts) == 1 and K.LOOP_WAITING in poster.posts[0], q.doc


def test_a_quiet_stop_never_resets_what_was_notified(p):
    """F2: an attention stop, a quiet stop, then the same attention stop is one occurrence, notified once: what was
    notified is kept across quiet stops and activations."""
    mode(p, "run")  # no operator endpoint: NOTIFIER_UNAVAILABLE whenever an action is eligible
    current: dict[str, Any] = {}

    def projector(e: Any, c: Any, s: dict[str, Any]) -> Any:
        rev = int(s["revision"])
        return projection("project", rev), [projection("T-0001", rev, actions=current["offer"](rev))]

    lp = loop(p, projector)
    codes = []
    for offer in (notes, lambda rev: [], notes):
        current["offer"] = offer
        codes.append(lp.activate().code)
    assert codes == [L.NOTIFIER_UNAVAILABLE, L.IDLE, L.NOTIFIER_UNAVAILABLE]
    assert len(stop_lines(p)) == 1, stop_lines(p)


def test_a_change_after_the_last_read_is_never_lost(p):
    """F3: a change made by another actor after the loop's last read in an activation (a run record's wake mark,
    moved while the final tick projects) is looked at: only what a tick has read counts as seen, so the loop acts on
    the action that change made eligible. The coarse look is off, so the wake is the only way in, and the projector
    bumps until the mark has moved: a bump can fail on Windows (``outbox.bump_wake``), which is the next test's case."""
    mode(p, "walk")
    root = p.root / ".aew"
    calls, moved = {"n": 0}, []

    def projector(e: Any, c: Any, s: dict[str, Any]) -> Any:
        calls["n"] += 1
        rev = int(s["revision"])
        if calls["n"] == 1:  # the activation's only tick: nothing to do as of its read ...
            before = outbox.wake_mark(root)
            for _ in range(100):  # ... then a run record moves, and its wake with it
                outbox.bump_wake(root)
                if outbox.wake_mark(root) != before:
                    moved.append(True)
                    break
            return projection("project", rev), [projection("T-0001", rev)]
        return projection("project", rev), [projection("T-0001", rev, actions=notes(rev))]

    acted = Acted()
    lp = loop(p, projector, executor=acted)
    lp.start()
    try:
        assert acted.done.wait(HANG_S), "the change after the last read was never acted on"
    finally:
        lp.close()
    assert moved and lp.executed[0]["action"] == "probe_notes", (moved, lp.executed)


@pytest.mark.parametrize("case", ["bump_failed", "mark_cannot_see_it"])
def test_a_change_whose_wake_is_lost_is_still_acted_on(p, monkeypatch, case):
    """The wake is advisory (PR #199's Windows CI failure): on Windows a bump fails while another handle is open on
    the wake file, and the mark does not move; and a mark can only see what changes it (a change landing in the same
    timestamp tick as the tick's snapshot, were the mark a timestamp). Either way the loop's coarse look projects,
    sees it would select something else, and acts on what the change made eligible."""
    mode(p, "walk")
    root = p.root / ".aew"
    if case == "mark_cannot_see_it":
        monkeypatch.setattr(outbox, "wake_mark", lambda aew_root: (0, 0, 0))  # every bump in the snapshot's tick
    calls = {"n": 0}

    def projector(e: Any, c: Any, s: dict[str, Any]) -> Any:
        calls["n"] += 1
        rev = int(s["revision"])
        if calls["n"] == 1:  # the activation's only tick reads nothing to do; then a run record moves ...
            if case == "mark_cannot_see_it":
                outbox.bump_wake(root)  # ... and bumps a wake the mark cannot see
            return projection("project", rev), [projection("T-0001", rev)]  # (bump_failed: no wake at all)
        return projection("project", rev), [projection("T-0001", rev, actions=notes(rev))]

    acted = Acted()
    lp = loop(p, projector, executor=acted, coarse_s=0.05)
    lp.start()
    try:
        assert acted.done.wait(HANG_S), "a change whose wake was lost was never acted on"
    finally:
        lp.close()
    assert lp.executed[0]["action"] == "probe_notes", lp.executed


def test_a_coarse_look_that_finds_nothing_new_never_restarts_the_envelope(p):
    """The coarse look starts an activation only when the projection selects something other than the last tick
    did. After a repetition stop it selects the same action, so many looks later that action has still run only
    repetition_n times, in one activation (A1 §3.1): a look is never a wake."""
    mode(p, "walk")
    looks = threading.Semaphore(0)
    scripted = Scripted(notes)

    def projector(e: Any, c: Any, s: dict[str, Any]) -> Any:
        looks.release()
        return scripted(e, c, s)

    lp = loop(p, projector, coarse_s=0.01)
    lp.start()
    try:
        for _ in range(3 + 20):  # the activation's three ticks, then twenty coarse looks
            assert looks.acquire(timeout=HANG_S), "the loop stopped looking"
    finally:
        lp.close()
    assert [x["action"] for x in lp.executed] == ["probe_notes"] * 2, lp.executed
    assert lp._activations == 1
    assert json.loads((p.root / ".aew/local/steering/loop.json").read_text())["stop"]["code"] == L.REPETITION


def test_no_new_action_starts_once_the_broker_is_closing(p):
    """F4: once `LeadBroker.close()` begins, the loop starts no auto-run action with the session's credential, even
    while the bridge drains a request still in flight (up to 60 s) and another actor's commit wakes it."""
    from aew.harness import lead_broker

    mode(p, "walk")
    broker = lead_broker.LeadBroker(Engine.discover(p.root), p.token)
    assert broker.loop is not None
    broker.loop._project = Scripted(notes)
    release = threading.Event()
    broker.start()
    try:
        until(lambda: len(broker.loop.executed) == 2, activation_wait_s(broker.loop), "the first activation",
              describe=loop_chain(broker))
        real_drain = broker.server.drain
        draining = threading.Event()

        def drain(t: float) -> Any:  # a Lead request still in flight
            draining.set()
            release.wait(8)
            return real_drain(t)

        broker.server.drain = drain
        closer = threading.Thread(target=broker.close)
        closer.start()
        # close() has begun (its drain follows the loop's request_stop): an event, never a sleep, orders the commit
        # after it
        assert draining.wait(HANG_S), "close() never reached the drain"
        Engine.discover(p.root).checkpoint(token=p.token, expect_rev=p.rev(), note="another actor's commit",
                                           next_action=None)
        # close() asked the loop to stop before its drain, so the loop ends whatever wakes it, and once it has ended
        # nothing more can start: its end, never a sleep, says when to count, while the drain still holds close()
        assert broker.loop._thread is not None
        broker.loop._thread.join(HANG_S)
        assert not broker.loop._thread.is_alive(), "the loop went on after close() began"
        ran_while_closing = len(broker.loop.executed) - 2
        release.set()
        closer.join(30)
    finally:
        release.set()
    assert ran_while_closing == 0, f"{ran_while_closing} auto-run action(s) started after close() began"
    assert not closer.is_alive()


def test_the_loops_own_commits_never_restart_the_envelope(p, endpoint):
    """F3's other side: an activation woken only by the loop's own last commits resumes the one before it, so its
    envelope goes on. A stage that commits its first step and is refused at its second, every time, runs at most
    repetition_n (2) times, then the loop stops; without this every own commit would start a fresh envelope."""
    mode(p, "run")
    wid = Engine.discover(p.root).work_create(token=p.token, expect_rev=p.rev(), kind="ticket", title="Unplanned",
                                              risk_class=1)["id"]  # not READY: its assignment is always refused
    lp = loop(p, Scripted(lambda rev: [action("probe_start", {"expect_rev": rev, "work_id": wid})]))
    looks = Looks(lp)
    lp.start()
    try:
        path = p.root / ".aew/local/steering/loop.json"  # the loop replaces it; a racing read is "not yet"
        until(lambda: ((read_json_or_none(path) or {}).get("stop") or {}).get("code") == L.REPETITION,
              activation_wait_s(lp), "the repetition stop")
        looks.another()  # nothing moves now: a further activation would have run before this look
    finally:
        lp.close()
    assert [x["action"] for x in lp.executed] == ["probe_start"] * 2, lp.executed
    assert not any(x["ok"] for x in lp.executed)


def test_mode_change_mid_step_leaves_the_step(tmp_path, monkeypatch):
    """A3 §4, §6 / CWR §8: changing the mode does not interrupt an executing action. Run is lowered to Walk between
    `ticket_start`'s steps: the stage completes, its next step retried once under R5-1 (its guard is re-asked and the
    mode changed no legality), with its binding unchanged and nothing STALE_POLICY; the next tick follows Walk."""
    p, lab, wid = _run_lab(tmp_path, monkeypatch)
    lab.script("default", [{"do": "hang"}])
    e = Engine.discover(p.root)
    digest = e.policy_digests()["legality_digest"]

    def lower(c: Any) -> None:
        e.steering_lower(token=p.token, expect_rev=int(e.store.read()["revision"]), mode="walk")

    ep = operator_endpoint.OperatorEndpoint(Engine.discover(p.root), console=Console(), dev=True, timeout=10)
    ep.start()
    try:
        intervene(monkeypatch, "work.transition", times=1, before=lower)
        lp = loop(p)
        ran = lp.tick(L.Activation("LA-a3", time.monotonic()))
        assert isinstance(ran, dict) and ran["ok"], ran
        si = Engine.discover(p.root).stage_intent(lp.executed[0]["intent"])
        assert si["status"] == "COMPLETED" and si["stopped"] is None
        assert [s["primitive"] for s in si["steps"]] == ["work.assign", "dispatch.launch", "work.transition"]
        assert si["steps"][-1].get("retried_after_stale_revision") is True
        assert si["binding"]["legality_digest"] == digest == Engine.discover(p.root).policy_digests()[
            "legality_digest"]
        assert Engine.discover(p.root).steering_view()["effective"] == "walk"
        after = loop(p, Scripted(lambda rev: [action("ticket_start", {"expect_rev": rev, "work_id": "T-0001"})]),
                     executor=Spy()).tick(L.Activation("LA-next", time.monotonic()))
        assert isinstance(after, L.Stop) and after.code == L.CONFIRMATION_UNAVAILABLE  # Walk confirms a dispatch
    finally:
        ep.close()
        lab.cleanup()


# ---------------------------------------------------------------------------------------------- the live catalog (F7)


def _dummy(prop: dict[str, Any]) -> Any:
    if "enum" in prop:
        return prop["enum"][0]
    kind = prop.get("type")
    return {"integer": 1, "boolean": True, "array": ["x"], "object": {}}.get(kind, "x") if kind != "string" else "x"


def _arguments(t: contract.Tool) -> dict[str, Any]:
    """Arguments for ``t`` with every property its schema has (so a planner plans every optional step)."""
    props = t.input_schema.get("properties") or {}
    a = {name: _dummy(prop) for name, prop in props.items() if name not in ("execution", "plan")}
    a["work_id"] = "T-0001"
    if "plan" in props:
        a["plan"] = {"body": "a plan", "assurance": "none"}
    return a


def test_the_live_catalog_meets_what_the_loop_relies_on():
    """Amendment 1, E7b's row (review of PR #199, F7): over every built progression tool of the live catalog, so that
    E6a's and E6b's stages are checked as they join it, what the loop reads agrees with what runs. Every primitive a
    stage's planner emits is in its `expands_to` (Walk's confirmation reads `expands_to`, the runtime check the
    steps); a tool `dispatches` exactly when its plan launches a run (Run's hard-deadline check reads `dispatches`);
    and in Walk such a tool needs a confirmation exactly when a primitive it can run changes more than control state."""
    from aew.engine.steering import WALK_ALLOWED, confirmation_reason
    from aew.surface.classify import AVAILABLE, auto_runnable, effective_class
    from aew.surface.contract import JUDGMENT_BEARING

    checked = []
    for t in contract.TOOLS.values():
        if not (t.built and t.progression):
            continue
        planner = stage.STAGES.get(t.name)
        if planner is None:
            planned = list(t.expands_to)
        else:
            a = _arguments(t)
            plan = planner(a, ["card-a", "card-b"]) if t.name in stage.SA.CARDS else planner(a)
            planned = [step["primitive"] for step in plan]
            assert set(planned) <= set(t.expands_to), (t.name, planned, t.expands_to)
        assert t.dispatches == ("dispatch.launch" in planned or "dispatch.launch" in t.expands_to), t.name
        beyond = any(not P.spec_for(x).declared or set(P.spec_for(x).side_effect_class.split("+")) - WALK_ALLOWED
                     for x in t.expands_to)
        assert (confirmation_reason("walk", t.expands_to) is not None) == beyond, t.name
        assert confirmation_reason("crawl", t.expands_to) is not None and confirmation_reason("run", t.expands_to) \
            is None
        if t.required_judgments or t.base_class == JUDGMENT_BEARING:  # the loop never runs a judgment (m2)
            assert not auto_runnable(t, AVAILABLE, effective_class(t, _arguments(t))), t.name
        checked.append(t.name)
    assert {"ticket_start", "ticket_request_review", "ticket_prepare", "integration_publish"} <= set(checked), checked


# ---------------------------------------------------------------------------------------------- the runtime check (F5)


def test_every_event_kind_maps_to_a_side_effect_class():
    """SAE-07 at runtime is total: every typed event kind a commit can carry maps to the classes it shows, a sealed
    thread's fallback among them (coordination_record); an unmapped kind fails closed."""
    assert set(L.EVENT_EFFECTS) == set(outbox.DERIVED_KINDS) | set(outbox.DECLARED_KINDS)
    assert L.EVENT_EFFECTS["coordination.seal_fallback"] == {"coordination_record"}
    with pytest.raises(L.Unmapped):
        L.observed_effects([{"kind": "something.new"}])


@pytest.mark.parametrize("case", ["unreadable", "no_events", "unmapped_kind"])
def test_the_runtime_check_fails_closed(p, monkeypatch, case):
    """Plan v3 E7 / A1 §2.1 (review of PR #199, F5): a step whose commit cannot be read with its events, or carries an
    event kind no class maps, is never passed: the loop stops with attention, DECLARATION_UNCHECKED."""
    from aew import errors

    mode(p, "walk")
    real = outbox.read_transitions

    def read(*args: Any, **kw: Any) -> Any:
        if case == "unreadable":
            raise errors.IntegrityError("the transition hash chain is broken")
        for record in real(*args, **kw):
            yield {**record, "events": None} if case == "no_events" else {
                **record, "events": [*record["events"], {"kind": "something.new"}]}

    monkeypatch.setattr(outbox, "read_transitions", read)
    lp = loop(p, Scripted(notes))
    stop = lp.activate()
    assert stop.code == L.DECLARATION_UNCHECKED and lp.executed, stop
    assert stop_lines(p)[-1].startswith(L.DECLARATION_UNCHECKED)
    assert not (load_control(p.root).get("anomalies") or {})  # unchecked is not a violation: no anomaly


# ---------------------------------------------------------------------------------------------- supersession (F8)


def test_a_superseded_loop_writes_nothing_shared(p, monkeypatch):
    """Review of PR #199, F8: once its generation is superseded (here by a takeover while an auto-run stage is between
    its steps), the old session's loop appends nothing to the broker's spool file, never overwrites `loop.json`, and
    notifies nothing: the takeover is the endpoint's to notify (`generation_ended`). `status` shows no loop state
    another generation wrote."""
    from notifier import takeover

    mode(p, "walk")
    old_token = p.token
    e = Engine.discover(p.root)
    lp = L.SteeringLoop(e, generation=1, session_label="lead-a", token=lambda: old_token, poll_s=0.2,
                        projector=Scripted(notes))
    assert lp.activate().code == L.REPETITION  # it wrote its state and one notification
    loop_json = p.root / ".aew/local/steering/loop.json"
    spool = event_spool.file_of(p.root / ".aew", event_spool.BROKER)
    before = (loop_json.read_bytes(), spool.read_bytes())
    assert json.loads(before[0])["generation"] == 1
    Engine.discover(p.root).checkpoint(token=old_token, expect_rev=p.rev(), note="the Lead acts", next_action=None)
    seen = intervene(monkeypatch, "checkpoint", times=2,
                     before=lambda c: takeover(p, monkeypatch) if len(seen) == 2 else None)
    stop = lp.activate()  # a new activation: its stage is cut by the takeover, and the loop finds itself superseded
    assert stop.code == L.STALE_AUTHORITY, stop
    assert lp.activate().code == L.STALE_AUTHORITY
    assert (loop_json.read_bytes(), spool.read_bytes()) == before
    assert "loop" not in (Engine.discover(p.root).steering_view() or {})


@pytest.mark.serial  # its property is timing: the loop's self-check against a held history index
def test_a_superseded_loops_self_check_answers_from_the_hot_state_while_the_history_index_is_held(project,
                                                                                                    monkeypatch):
    """Review of #284, M1: the loop looked its superseded credential up in the archive, through the history index,
    whose SQLite busy wait (30 s) ran out as a `LockTimeout` that `_authority_lost` took as "still the Lead": with the
    index held, `broker.close()` waited 29.7 s for the loop. A takeover moves the credential out of the hot token
    table, so the check answers from the hot state alone (`require_held_lead`): lost, within its read's lock timeout,
    while another connection holds the index."""
    from notifier import takeover

    old_token = project.token
    e = Engine.discover(project.root)
    e.store.lock_timeout = 10.0  # the check's one wait, its read, and well under the index's 30 s
    lp = L.SteeringLoop(e, generation=1, session_label="lead-a", token=lambda: old_token, poll_s=0.2)
    root = project.root / ".aew"
    (root / INDEX_REL).parent.mkdir(parents=True, exist_ok=True)
    held = sqlite3.connect(root / INDEX_REL, timeout=10, isolation_level=None)  # its own take may wait, bounded
    try:
        held.execute("BEGIN EXCLUSIVE")
        takeover(project, monkeypatch)
        started = time.monotonic()
        lost = lp._authority_lost()
        elapsed = time.monotonic() - started
    finally:
        held.close()
    assert lost == "Lead authority superseded; this credential can no longer change control state", lost
    assert elapsed < e.store.lock_timeout, elapsed


def test_an_activation_that_returned_control_is_never_resumed(p):
    """Review of PR #199, R1: only an activation whose final tick committed is resumed. One that ran an action and
    then returned control quietly (nothing to do) is over: a later wake that is no commit (a run record moved) starts
    a fresh activation with a fresh envelope, which runs what became eligible, never the old deadline."""
    mode(p, "walk")
    now = [1000.0]
    calls = {"n": 0}

    def projector(e: Any, c: Any, s: dict[str, Any]) -> Any:
        rev = int(s["revision"])
        calls["n"] += 1
        return projection("project", rev), [projection("T-0001", rev, actions=notes(rev) if calls["n"] != 2 else [])]

    lp = loop(p, projector, clock=lambda: now[0])
    first = lp.activate()
    assert first.code == L.IDLE and len(lp.executed) == 1, first
    now[0] += 4000.0  # past the default loop_deadline_s (3600) since that activation started
    outbox.bump_wake(p.root / ".aew")  # a run record moved; no commit
    second = lp.activate()
    assert second.code != L.LOOP_DEADLINE and len(lp.executed) >= 2, (second.code, second.message)


def test_a_condition_still_recurring_is_never_forgotten_first(p, monkeypatch):
    """Review of PR #199, R2: what was notified is forgotten least recently met first, so a standing condition that
    keeps recurring stays notified once while 64 other conditions come and go. The standing stop is notified as it
    will be once E7c lifts the hold (``HELD_UNTIL_E7C`` emptied here)."""
    monkeypatch.setattr(L, "HELD_UNTIL_E7C", frozenset())
    mode(p, "walk")
    lp = loop(p, Scripted(lambda rev: []))
    standing = L.Stop(L.CONFIRMATION_UNAVAILABLE, "T-0001's start needs a confirmation", "T-0001", "ticket_start", "d")
    lp._record(standing, None, "walk")
    for i in range(L.NOTIFIED_MAX):
        lp._record(L.Stop(L.ACTION_STOPPED, f"other condition {i}", f"T-{i:04d}", "probe_notes", f"{i}"), None, "walk")
        if i % 8 == 0:
            lp._record(standing, None, "walk")  # it recurs all along: still the same occurrence
    lp._record(standing, None, "walk")
    assert sum(1 for x in stop_lines(p) if "T-0001's start" in x) == 1


@pytest.mark.parametrize("found", ["before_the_stage", "inside_a_step"])
def test_a_dead_custodian_ended_under_an_auto_run_step(tmp_path, monkeypatch, found):
    """M4-E E6a's custody sweep (the queue's ``sync``, a finalizer of every Lead transaction) ends a custodian whose
    worker is gone and revokes its custody credential in whichever transaction first sees it (S2).

    ``before_the_stage``: a custodian already dead when the loop picks its step is ended by the stage's opening
    commit, which records the intent and is no step's, so the step commits stay control state and the loop goes on.
    ``inside_a_step``: one found dead only by a step's own commit (its worker died between the stage's opening and
    that step) puts the revocation in the step's commit, which SAE-07 holds to the step's declarations: the loop
    stops, failing closed, with SIDE_EFFECT_UNDECLARED and a high anomaly the Lead disposes of. That window is the
    residual; closing it needs provenance on finalizer events, not a weaker check."""
    from test_integration_stages import checks_mode, prepared
    from test_validation_checks import CONTAINED

    from aew.engine import api as engine_api
    from aew.harness import procs

    held: dict[str, str] = {}
    monkeypatch.setattr(engine_api, "spawn_worker",
                        lambda repo, aew_root, custodian, credential: held.__setitem__(custodian, credential))
    stand_in_containment(monkeypatch, CONTAINED)
    p = sample_project(tmp_path)
    checks_mode(p)
    _wid, custodian, _out = prepared(p, tmp_path)
    Engine.discover(p.root).custody_register(held[custodian])
    for name, (row, planner) in PROBES.items():
        monkeypatch.setitem(contract.TOOLS, name, row)
        monkeypatch.setitem(stage.STAGES, name, planner)
    command, _ = recorder(tmp_path)
    p.extra["notify"] = command
    policy_text(p, mode="walk", command=command)
    mode(p, "walk")
    control = load_control(p.root)
    assert control["queue"]["lease"]["reconcile"] is None and control["invocations"][custodian]["status"] == "active"
    token_id = control["queue"]["lease"]["custody"]["token_id"]
    before = p.rev()

    gone = {"yes": found == "before_the_stage"}  # the custody worker is gone from this moment on
    monkeypatch.setattr(procs, "same_process", lambda pid, started: not gone["yes"])
    if found == "inside_a_step":
        real_open = Engine.stage_open

        def open_then_die(self: Any, **kw: Any) -> Any:
            out = real_open(self, **kw)
            gone["yes"] = True
            return out

        monkeypatch.setattr(Engine, "stage_open", open_then_die)
    lp = loop(p, Scripted(notes))
    stop = lp.activate()

    control = load_control(p.root)
    assert control["invocations"][custodian]["status"] == "interrupted"
    assert control["queue"]["lease"]["reconcile"] is not None
    assert control["tokens"][token_id]["revoked_at"] is not None
    e = Engine.discover(p.root)
    steps = {int(s["revision"]) for x in lp.executed for s in e.stage_intent(x["intent"])["steps"]}
    revoked = [r["revision"] for r in outbox.read_transitions(p.root / ".aew", before, p.rev(),
                                                              outbox=control.get("outbox"))
               if any(ev["kind"] == "credential.revoked" and ev.get("id") == token_id for ev in r.get("events") or [])]
    assert len(revoked) == 1, revoked
    if found == "before_the_stage":
        assert stop.code == L.REPETITION, stop  # both steps ran: no SIDE_EFFECT_UNDECLARED, no DECLARATION_UNCHECKED
        assert revoked[0] not in steps, (revoked, steps)
    else:
        assert stop.code == L.SIDE_EFFECT_UNDECLARED and "credential" in stop.message, stop
        assert revoked[0] in steps, (revoked, steps)
