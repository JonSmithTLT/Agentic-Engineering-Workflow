"""The steering loop (M4-E E7b; CWR §7; A1 §2 to §4; plan v3 E7 and its amendment 1, E7b).

The loop runs in the Lead broker (``LeadBroker``), the supervisor-side process that holds the Lead credential, never
in the MCP process or the model's shell. It advances the workflow with the actions the projection already says are
legal and need no judgment, and stops for everything else. Steering decides **who confirms** an already-legal action;
it never decides what is legal (CWR §2): nothing here is read by a guard, a gate, a transition, a dispatch or an ingest
(``test_legality_modules_never_import_steering``).

**When it runs.** On its own thread, woken by a committed Lead tool call and by a change it sees within ``POLL_S`` (a
commit's control file, or the wake file a run record changes). With no steering mode in force (legacy/manual, decision
3) it does nothing. An **activation** is the run of ticks from a wake to a stop; the envelope is counted per activation.

**One tick** (CWR §7):

1. Read the projections: the project's and every live Ticket's (``aew.surface.projection``).
2. **Stop** for the same reasons in every mode (CWR §2, §11: identical stop sets; :func:`select`): stale authority or
   policy; an open high anomaly anywhere (§2.4); a project-level blocker or decision. A Ticket with a decision, a
   blocker or an action whose availability is UNKNOWN is never advanced; when no Ticket has an eligible action
   (AVAILABLE and ``auto_runnable``), the loop stops, naming the first reason it met.
3. Select the first eligible action, Tickets in id order.
4. ``confirm_before`` (``steering.confirmation_reason``): Crawl always, Walk unless every declared effect of every
   primitive is in ``{control_state}`` (A1 §2, fail closed), Run never. **E7b has no confirmation (amendment 1, m3):**
   such an action is never executed, and the loop stops with ``CONFIRMATION_UNAVAILABLE``. E7c replaces that stop.
5. The envelope (A1 §3): the activation's deadline, its action count, and the repetition key ``(action, arguments,
   subject, subject state)``, counted from the last commit not made by the loop. In Run, at each activation, the
   notifier must be executable and the operator endpoint must answer (``NOTIFIER_UNAVAILABLE``; plan v3 §2.8, m4),
   and a dispatching action needs every profile routing can pick to set ``deadline_s`` (``NO_HARD_DEADLINE``, A1
   §3.2).
6. Execute it as a normal stage call (``run_tool``), with the projection's ``expect_rev``, a StageIntent, and the
   loop's attribution on that intent (``auto_run``: activation, mode and its record and generation, digests,
   projection) and on its dispatches (channel ``steering_loop``). It is the same call a Lead makes, checked the same
   way: R5-1 is the stage executor's, and a judgment is never replayed (it is never auto-run at all).
7. **Runtime declaration check (SAE-07):** each committed step's typed events must stay within what its primitives
   declare; an excess is recorded as a high anomaly and stops the loop.

**Interaction with the Lead's ``expect_rev`` (n5):** the loop's commits are real progress and stale the Lead's next call
(``STALE_REVISION``); the Lead re-reads and re-judges, nothing replays. The loop runs on an engine of its own, so a
Lead's call and the loop's are each one stage, CAS-checked: at most two intents in flight (plan v3 §2.7).

**What it records:** its state (``.aew/local/steering/loop.json``: running or stopped, and why; never control state,
§2.7), and a ``loop_stopped`` line in the broker's event spool for a stop that needs attention, so the operator
endpoint notifies (§2.8). A stop that returns control to the Lead in the ordinary way (a decision, a blocker, an
unknown, nothing to do) is recorded but not notified.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew import errors
from aew.engine import steering as S
from aew.engine.primitives import spec_for
from aew.harness import event_spool
from aew.util import replace_with_retry, sha256_bytes, utc_now

# Stop codes. The first group returns control to the Lead in the ordinary way; the rest need attention (notified).
OFF = "STEERING_OFF"  # no steering mode in force: the loop does nothing and records nothing (decision 3)
IDLE = "NOTHING_TO_DO"
DECISION_REQUIRED = "DECISION_REQUIRED"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"
QUIET = frozenset({OFF, IDLE, DECISION_REQUIRED, BLOCKED, UNKNOWN})
ANOMALY_HIGH = "ANOMALY_HIGH"
STALE_AUTHORITY = "STALE_AUTHORITY"
STALE_POLICY = "STALE_POLICY"
CONFIRMATION_UNAVAILABLE = "CONFIRMATION_UNAVAILABLE"  # E7b: confirm_before holds and no confirmation exists yet (m3)
NOTIFIER_UNAVAILABLE = "NOTIFIER_UNAVAILABLE"
NO_HARD_DEADLINE = "NO_HARD_DEADLINE"
LOOP_DEADLINE = "LOOP_DEADLINE"
MAX_AUTO_ACTIONS = "MAX_AUTO_ACTIONS"
REPETITION = "REPETITION"
SIDE_EFFECT_UNDECLARED = "SIDE_EFFECT_UNDECLARED"
ACTION_STOPPED = "ACTION_STOPPED"  # the executed stage stopped (refused, launch_failed): the Lead reads its result
CHANNEL = "steering_loop"  # the dispatch channel of an auto-run step (provenance only, never legality)
STALE_RETRIES = 3  # another actor's commits between the projection and the call: re-project, a few times
TERMINAL_STATES = frozenset({"DONE", "CANCELLED"})


@dataclass(frozen=True)
class Stop:
    code: str
    message: str
    subject: str = "project"

    @property
    def attention(self) -> bool:
        return self.code not in QUIET


@dataclass(frozen=True)
class Choice:
    action: dict[str, Any]
    subject: str
    projection: dict[str, Any]


@dataclass
class Activation:
    id: str
    started: float
    actions: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    run_checked: bool = False
    last_own_rev: int | None = None


# ---------------------------------------------------------------------------------------------- selection (CWR §7)


def select(project: dict[str, Any], units: list[dict[str, Any]]) -> Choice | Stop:
    """Steps 2 and 3 of a tick, the same in every mode: the first eligible action, or why there is none. ``project``
    is the project's projection, ``units`` each live Ticket's."""
    high = [a for a in project.get("anomalies") or [] if (a.get("details") or {}).get("severity") == "high"]
    if high:
        a = high[0]["details"]
        return Stop(ANOMALY_HIGH, f"open high anomaly {a.get('anomaly')} ({high[0]['code']}): every mode stops "
                                  "until the Lead disposes of it (plan v3 §2.4)", a.get("subject") or "project")
    if project.get("blockers"):
        b = project["blockers"][0]
        return Stop(BLOCKED, f"{b['code']}: {b['message']}")
    owned = {e for u in units for d in u.get("decisions_required") or [] for e in d.get("evidence") or []}
    loose = [d for d in project.get("decisions_required") or [] if not set(d.get("evidence") or []) & owned]
    if loose:
        return Stop(DECISION_REQUIRED, f"{loose[0]['decision']} ({', '.join(loose[0].get('evidence') or [])}) is "
                                       "the Lead's")
    first: Stop | None = None
    for p in sorted(units, key=lambda u: str(u.get("subject"))):
        subject = str(p.get("subject"))
        actions = p.get("actions") or []
        why: Stop | None = None
        if p.get("decisions_required"):
            d = p["decisions_required"][0]
            why = Stop(DECISION_REQUIRED, f"{subject}: {d['decision']} is the Lead's", subject)
        elif p.get("blockers"):
            b = p["blockers"][0]
            why = Stop(BLOCKED, f"{subject}: {b['code']}: {b['message']}", subject)
        elif any(a.get("availability") == "UNKNOWN" for a in actions):
            a = next(a for a in actions if a.get("availability") == "UNKNOWN")
            why = Stop(UNKNOWN, f"{subject}: {a['action']} is UNKNOWN ({', '.join(a.get('reason_codes') or [])}): "
                                "never runnable", subject)
        else:
            eligible = [a for a in actions if a.get("availability") == "AVAILABLE" and a.get("auto_runnable")]
            if eligible:
                return Choice(eligible[0], subject, p)
        first = first or why
    return first or Stop(IDLE, "no eligible action")


def repetition_key(choice: Choice) -> str:
    """``(action, arguments, subject, subject state)``: the same key again means no progress (A1 §3.1)."""
    args = {k: v for k, v in (choice.action.get("arguments") or {}).items() if k != "expect_rev"}
    return sha256_bytes(json.dumps([choice.action["action"], args, choice.subject, choice.projection.get("state")],
                                   sort_keys=True, default=str).encode("utf-8"))[:32]


# Typed events of a commit (ADR-0012 D2) and the side-effect class each shows (SAE-07, at runtime). A run recorded is a
# process to be started under a new credential; anything else a commit records is control state.
EVENT_EFFECTS = {"run.added": frozenset({"harness_process", "credential"}),
                 "credential.revoked": frozenset({"credential"})}


def observed_effects(events: list[dict[str, Any]]) -> set[str]:
    out = {"control_state"}
    for e in events:
        out |= EVENT_EFFECTS.get(str(e.get("kind")), frozenset())
    return out


def declared_effects(primitives: list[str]) -> set[str]:
    return {e for p in primitives for e in spec_for(p).side_effect_class.split("+") if e}


# ---------------------------------------------------------------------------------------------- the loop


Projector = Callable[[Any, Any, dict[str, Any]], tuple[dict[str, Any], list[dict[str, Any]]]]
Executor = Callable[..., dict[str, Any]]


class SteeringLoop:
    """One broker's loop, on ``engine`` (its own, never the broker's: they run on different threads). ``token``
    returns the broker's credential, empty once the broker closes. ``projector`` and ``executor`` are the
    projection and the runner (tests may pass their own); ``clock`` is monotonic."""

    def __init__(self, engine: Any, *, generation: int, session_label: str | None, token: Callable[[], str],
                 poll_s: float, projector: Projector | None = None,
                 executor: Executor | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.engine = engine
        self.aew_root = Path(engine.aew_root)
        self.generation = generation
        self.session_label = session_label
        self._token = token
        self.poll_s = poll_s
        self._project = projector or _project_all
        self._execute = executor or _run
        self._clock = clock
        self._wake = threading.Event()
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen: Any = None
        self._last_stop: tuple[str, str, int] | None = None
        self._activations = 0
        self.executed: list[dict[str, Any]] = []  # what this loop ran: (action, subject, intent), for tests and status

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_forever, name="aew-steering-loop", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        """A committed Lead tool call (plan v3 E7, M8.1): look now."""
        self._wake.set()

    def close(self, timeout: float = 60.0) -> None:
        """Stop; an action in flight finishes first (a stage is never cut between its steps by the loop)."""
        self._closed.set()
        self._wake.set()
        if self._thread is not None and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _changed(self) -> bool:
        from aew.engine import outbox

        seen = (self.engine.store.control_identity(), outbox.wake_mark(self.aew_root))
        changed, self._seen = seen != self._seen, seen
        return changed

    def _run_forever(self) -> None:
        while not self._closed.is_set():
            woken = self._wake.wait(self.poll_s)
            self._wake.clear()
            if self._closed.is_set():
                return
            if not (woken or self._changed()):
                continue
            try:
                stop = self.activate()
            except Exception as exc:  # noqa: BLE001  a defect stops the loop visibly, never the broker
                stop = Stop(ACTION_STOPPED, f"the steering loop failed: {type(exc).__name__}: {exc}")
                self._record(stop, None, None)
            # Its own commits are no reason to look again: an activation re-projects after each of them, and a new
            # one would restart the envelope. A Lead's commit wakes it (``wake``); others show at the next change.
            self._changed()
            if stop.code == STALE_AUTHORITY:
                return

    # ------------------------------------------------------------------ one activation

    def activate(self) -> Stop:
        """Tick until a stop, and record it. Returns the stop."""
        self._activations += 1
        act = Activation(id=f"LA-{os.getpid()}-{self._activations}", started=self._clock())
        stale = 0
        while True:
            outcome = self.tick(act)
            if isinstance(outcome, Stop):
                self._record(outcome, act, self._mode())
                return outcome
            if outcome.get("stale"):
                stale += 1
                if stale >= STALE_RETRIES:
                    stop = Stop(ACTION_STOPPED, "the projection kept moving under the loop's calls "
                                                f"({STALE_RETRIES} stale revisions in a row): it waits for the next "
                                                "change")
                    self._record(stop, act, self._mode())
                    return stop
                continue
            stale = 0

    def _mode(self) -> str | None:
        try:
            return S.effective(self.engine.store.read())["mode"]
        except errors.AEWError:
            return None

    def tick(self, act: Activation) -> Stop | dict[str, Any]:
        """One evaluation: a stop, or the action it executed (``{"stale": True}`` when another actor's commit beat
        the call: nothing ran, and the next tick re-projects)."""
        if self._closed.is_set():
            return Stop(OFF, "the broker is closing")  # recorded as nothing: the session ended, not the loop
        lost = self._authority_lost()
        if lost:
            return Stop(STALE_AUTHORITY, f"this Lead session no longer holds Lead authority: {lost}")
        state = self.engine.store.read()
        now = S.effective(state)
        mode = now["mode"]
        if mode is None:
            return Stop(OFF, "no steering mode is in force (legacy/manual behaviour)")
        if act.last_own_rev is not None and int(state["revision"]) != act.last_own_rev:
            act.counts.clear()  # a commit the loop did not make: progress the repetition key cannot see
        act.last_own_rev = None
        try:
            policy, _ = self.engine.execution_policy()
            digests = self.engine.policy_digests()
        except errors.AEWError as exc:  # a policy edit awaiting adoption, or one the pin refuses
            return Stop(STALE_POLICY, f"{exc.code}: {exc.message}")
        bounds = S.envelope(policy)
        if self._clock() - act.started > bounds["loop_deadline_s"]:
            return Stop(LOOP_DEADLINE, f"this activation ran past loop_deadline_s ({bounds['loop_deadline_s']}s); "
                                       "it returns control (A1 §3.2)")
        if act.actions >= bounds["max_auto_actions"]:
            return Stop(MAX_AUTO_ACTIONS, f"this activation executed max_auto_actions ({bounds['max_auto_actions']}) "
                                          "(A1 §3)")
        ctx = self._ctx()
        project, units = self._project(self.engine, ctx, state)
        picked = select(project, units)
        if isinstance(picked, Stop):
            return picked
        from aew.surface import contract

        t = contract.tool(picked.action["action"])
        assert t is not None  # auto_runnable is never true for an unknown tool (surface.classify)
        why = S.confirmation_reason(mode, t.expands_to)
        if why is not None:
            return Stop(CONFIRMATION_UNAVAILABLE, f"{picked.action['action']} on {picked.subject} needs a "
                                                  f"confirmation ({why}); confirmation arrives with M4-E E7c, so it is "
                                                  "never executed here", picked.subject)
        if mode == "run":
            refused = self._run_checks(act, policy, t)
            if refused is not None:
                return Stop(refused[0], refused[1], picked.subject)
        key = repetition_key(picked)
        if act.counts.get(key, 0) >= bounds["repetition_n"]:
            return Stop(REPETITION, f"{picked.action['action']} on {picked.subject} in state "
                                    f"{picked.projection.get('state')} would run more than repetition_n "
                                    f"({bounds['repetition_n']}) times with no progress (A1 §3.1)", picked.subject)
        return self._do(act, picked, mode, now, digests, key)

    def _run_checks(self, act: Activation, policy: dict[str, Any] | None, t: Any) -> tuple[str, str] | None:
        """Run's own conditions: at each activation the notifier is executable and the endpoint answers (plan v3
        §2.8, m4); a dispatching action needs a hard deadline on every profile routing can pick (A1 §3.2)."""
        if not act.run_checked:
            problem = S.notifier_problem(policy)
            if problem:
                return NOTIFIER_UNAVAILABLE, f"unattended Run needs an executable notifier: {problem}"
            from aew.harness import operator_client

            try:
                operator_client.ping(self.aew_root)
            except errors.AEWError as exc:
                return NOTIFIER_UNAVAILABLE, ("unattended Run needs the operator endpoint, which delivers its "
                                              f"notifications, to be live: {exc.message}")
            act.run_checked = True
        if t.dispatches:
            missing = S.profiles_without_deadline(policy)
            if missing:
                return NO_HARD_DEADLINE, (f"{t.name} would start a run, but execution profile(s) {', '.join(missing)} "
                                          "set no deadline_s: Run never auto-starts a run without a hard deadline "
                                          "(A1 §3.2)")
        return None

    def _do(self, act: Activation, picked: Choice, mode: str, now: dict[str, Any], digests: dict[str, str],
            key: str) -> Stop | dict[str, Any]:
        from aew.engine import dispatch

        attribution = {"by": CHANNEL, "activation": act.id, "mode": mode, "mode_record": now.get("record"),
                       "mode_generation": now.get("generation"), "legality_digest": digests["legality_digest"],
                       "operational_digest": digests["operational_digest"],
                       "projection": {"revision": int(picked.projection["revision"]), "subject": picked.subject,
                                      "action": picked.action["action"]}}
        with dispatch.channel(CHANNEL):
            result = self._execute(self.engine, self._ctx(), picked.action["action"],
                                   dict(picked.action["arguments"]), token=self._token(), auto_run=attribution)
        stopped = result.get("stopped")
        if result.get("stage_intent_id") is None and stopped and stopped.get("boundary") == "stale_revision":
            return {"stale": True}  # another actor committed first: nothing ran (the intent never opened)
        act.actions += 1
        act.counts[key] = act.counts.get(key, 0) + 1
        act.last_own_rev = int(result.get("revision") or 0)
        self.executed.append({"action": picked.action["action"], "subject": picked.subject,
                              "intent": result.get("stage_intent_id"), "ok": result.get("ok")})
        excess = self._declaration_check(result, picked.subject)
        if excess is not None:
            return excess
        if stopped:
            code = STALE_POLICY if stopped.get("boundary") == "stale_policy" else (
                STALE_AUTHORITY if stopped.get("boundary") == "stale_authority" else ACTION_STOPPED)
            err = stopped.get("error") or {}
            return Stop(code, f"{picked.action['action']} on {picked.subject} stopped at {stopped.get('at')} "
                              f"({stopped.get('boundary')}): {err.get('code')}: {err.get('message')}", picked.subject)
        return result

    def _declaration_check(self, result: dict[str, Any], subject: str) -> Stop | None:
        """SAE-07 at runtime: each step's commit, by its typed events, within what its primitives declare. A
        launch planned after its dispatch shares that commit, so the commit is held to both."""
        from aew.engine import outbox

        intent = result.get("stage_intent_id")
        if not intent:
            return None
        si = self.engine.stage_intent(intent)
        by_rev: dict[int, list[str]] = {}
        for s in si["steps"]:
            by_rev.setdefault(int(s["revision"]), []).append(s["primitive"])
        state = self.engine.store.read()
        for rev, primitives in sorted(by_rev.items()):
            record = outbox.read_record(self.aew_root, rev, since=(state.get("outbox") or {}).get("since"))
            if record is None:
                continue
            events = outbox.complete_events(self.aew_root, record) or []
            excess = sorted(observed_effects(events) - declared_effects(primitives))
            if excess:
                detail = (f"{si['tool']} step(s) {', '.join(primitives)} committed revision {rev} with "
                          f"{', '.join(excess)}, which they do not declare")
                self.engine.anomaly_record_violation(token=self._token(), subject=subject, detail=detail,
                                                     details={"work_id": subject})
                return Stop(SIDE_EFFECT_UNDECLARED, detail + " (SAE-07): recorded as a high anomaly", subject)
        return None

    def _authority_lost(self) -> str | None:
        """Why the broker's credential no longer holds the Lead seat (lost authority only), or ``None``."""
        from aew.engine.authority import require_lead

        try:
            require_lead(self.engine.store.read(), self._token(), archived=self.engine.archived_credential)
        except errors.StaleAuthority as exc:
            return exc.message
        except errors.AEWError:
            return None
        return None

    def _ctx(self) -> Any:
        from aew.surface.context import NORMAL, SurfaceContext

        return SurfaceContext(lead_session={"holds": True, "generation": self.generation,
                                            "session_label": self.session_label},
                              generation=self.generation, profile=NORMAL, ingress="direct")

    # ------------------------------------------------------------------ records

    def _record(self, stop: Stop, act: Activation | None, mode: str | None) -> None:
        """``loop.json``, and a ``loop_stopped`` spool line for a stop that needs attention, once per stop (its code,
        subject and the revision it was met at). With steering off, nothing is written."""
        if stop.code == OFF:
            return
        try:
            revision = int(self.engine.store.read()["revision"])
        except errors.AEWError:
            revision = -1
        data = {"schema": S.LOOP_SCHEMA, "status": "idle" if stop.code == IDLE else "stopped", "mode": mode,
                "activation": act.id if act else None, "actions": act.actions if act else 0,
                "stop": {"code": stop.code, "message": stop.message[:2000], "subject": stop.subject,
                         "revision": revision, "at": utc_now()},
                "updated_at": utc_now()}
        _write(self.aew_root / S.LOOP_REL, data)
        mark = (stop.code, stop.subject, revision)
        if stop.attention and mark != self._last_stop:
            event_spool.append(self.aew_root, event_spool.BROKER, "loop_stopped", subject=stop.subject,
                               reason=f"{stop.code}: {stop.message}", ref=act.id if act else None)
        self._last_stop = mark


def _write(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, sort_keys=True, default=str) + "\n", encoding="utf-8")
        replace_with_retry(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _project_all(engine: Any, ctx: Any, state: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The project's projection and every live Ticket's, from the committed state now."""
    from aew.surface.projection import project

    tickets = sorted(w for w, u in state["work"].items() if u.get("kind") == "ticket"
                     and u.get("state") not in TERMINAL_STATES)
    return project(engine, ctx, None), [project(engine, ctx, w) for w in tickets]


def _run(engine: Any, ctx: Any, name: str, arguments: dict[str, Any], *, token: str,
         auto_run: dict[str, Any]) -> dict[str, Any]:
    from aew.surface.run import run_tool

    return run_tool(engine, ctx, name, arguments, token=token, auto_run=auto_run)
