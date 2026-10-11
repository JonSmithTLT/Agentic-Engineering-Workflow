"""The run supervisor: one counted run, from its first prompt to its settled cost (F19 plan v5 §2.3 steps 5 to 8,
§2.6, §2.6.1, §2.9; Q7 v0.3.1 §2.4, §9.2; F25 plan v4 §2.6).

The supervisor runs as the evaluator's uid (``aeweval``) and never as the arm. It drives the arm through an
:class:`ArmDriver` (S9 builds R's and R+'s, S13 the A arm's), ends processes through the helpers' contract
(:mod:`aew_eval.helpers`), meters spend through :mod:`aew_eval.spend`, and answers through
:mod:`aew_eval.responder`. It reads infrastructure facts only: nothing here imports scoring, an oracle, a review or
an analysis, and quiescence is decided from the arm's control state, never from whether the work is right.

**The lifecycle.**

1. The task's bytes are checked against the run manifest's ``task_input_sha256``; a mismatch is refused before
   anything starts (nothing then needs shutting down).
2. The driver prepares the arm. From here every exit takes the shutdown order and returns a :class:`Supervision`.
3. **The wall clock starts**, then the task's bytes go as the first prompt, exactly. A driver's
   ``send_first_prompt`` returns once the prompt is admitted, never after the turn.
4. Every ``poll_s`` the supervisor reads ``arm-tap``'s events, polls every meter, totals the spend, applies the
   termination rule and the wall cap, answers the arm's requests, and runs the quiescence machine.
5. Any end takes the shutdown order (:meth:`RunSupervisor._shutdown`), which never raises.

**Who caused a failure** (plan v5 §2.5: a supervisor fault consumes no arm-controlled input). The evaluator's own
paths (``arm-tap``'s helper itself, the spend feed and rule, the state checks) end a run as ``EVALUATOR_FAILURE``. An
exception from the arm-facing driver calls (``observe``, ``deliver``, ``send_continuation``) ends it as
``ARM_FACING_FAILURE``, attributed to the arm. Arm-written data never raises at all: a live file that is malformed,
lower than the evaluator's REST high-water, lower than before, or gone is CF evidence; a worker server whose meter
cannot be built or polled is a source that never answered.

**Per-worker meters** (§2.6.1, R3-M1). ``arm-tap`` reports each OpenCode server ``arm`` runs, with its password from
the server's environment and its loopback port. The supervisor meters every worker server with its own meter and its
own high-water state under the evaluator's state root, in a directory of the run's own made for that meter alone; the
password stays in memory. The meter's root session is the one the worker's run record names, else the server's
earliest session without a parent (R4-m6); every other session is summed as foreign, as for R. A worker server
``arm-tap`` ever reported is never ``never_launched``: one that does not answer is projected as stale (from when
``arm-tap`` first saw it, or from its last sample) until the hard ceiling ends the run (a valid failure, R4-n4), and
one that never answered at all makes the settled total ``unknown``. A worker's live file is a cross-check only and
never lowers the counted cost.

**The shutdown order** (F25 v4 §2.6; plan v5 §2.6, R3-n5), for every end. Each step is attempted whatever happened
before it, and its failure is recorded with its step:

0. read the residual: the evaluator-owned servers' active sessions and every worker meter's ``in_flight``, and the
   proxy's open requests;
1. interrupt the R/R+ session or the Lead's (``resume=false``);
2. supersede the Lead generation, so A's workers take the authority-ended path (never a kill first);
3. take the final samples of the evaluator-owned servers;
4. wait until every worker server has gone (or ``settle_deadline_s`` after step 0), then their final samples;
5. the last reads: one more poll of every meter and one more batch of ``arm-tap``'s mirror;
6. ``arm-kill``, with its proof that no process remains; without the proof the run's processes may still be
   spending, so its cost cannot be complete;
7. ``settle`` with the close time and the residual (a failed settle keeps the last measured figure, ``unknown``,
   never zero); the proxy closes the run's ledger; the counted cost.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aew_eval import spend
from aew_eval.helpers import ArmHelpers, TapEvent, TapLiveFile, TapServer, TapServerGone
from aew_eval.responder import Responder, Response
from aew_eval.schemas import Invalid

TOKEN_KEYS = ("input", "output", "reasoning", "cache_read", "cache_write")
# Ends attributed to the arm. ``arm_failure`` is that attribution only: Q7 §2.4.5's exception (a second quiescence
# whose already-produced deliverable passes the full hidden acceptance) is decided by scoring, never here.
ARM_FAILURES = frozenset({"SECOND_QUIESCENCE", "OPERATOR_ONLY_HALT", "REFUSAL", "GOVERNED_FAILURE",
                          "ARM_FACING_FAILURE"})


# ---------------------------------------------------------------------------------------------- what the driver gives

@dataclass(frozen=True)
class Request:
    """An operator-touching request the arm made, classified by its driver into the responder's classes."""

    id: str
    request_class: str


@dataclass(frozen=True)
class QuiescenceFacts:
    """Q7 §2.4.5's outcome-blind predicate, as the arm's control state shows it. Nothing here says whether the work
    is right: quiescence never reads correctness. ``turn`` counts the times the arm has returned control, so a second
    quiescence is one that follows the continuation, never the same one seen twice."""

    idle: bool                    # no active model or tool invocation
    infrastructure_pending: bool  # an experiment-owned provider or infrastructure operation is pending
    response_pending: bool        # a fixed-responder interaction is awaiting delivery
    final_signal: bool            # the arm's native final-completion signal
    unfinished: bool              # R/R+: the harness ended without a final report; A: the workflow is non-terminal
    turn: int

    @property
    def nonfinal(self) -> bool:
        return (self.idle and not self.infrastructure_pending and not self.response_pending
                and not self.final_signal and self.unfinished)


@dataclass(frozen=True)
class Observation:
    requests: tuple[Request, ...] = ()
    quiescence: QuiescenceFacts | None = None
    refusal: bool = False            # an explicit refusal or abandonment
    governed_failure: bool = False   # A: a governed terminal failure state


class Meter(Protocol):
    """F25's meter (``aew.harness.usage_live.Meter``): ``poll`` returns the last published sample (``None`` before the
    first), ``final`` the final one."""

    def poll(self) -> dict[str, Any] | None: ...

    def final(self) -> dict[str, Any]: ...


class ArmDriver(Protocol):
    """One arm's session, as the supervisor drives it (S9: R and R+; S13: A). ``send_first_prompt`` returns once the
    prompt is admitted, never after the turn it starts: the supervisor meters and caps the turn."""

    def prepare(self) -> None: ...

    def send_first_prompt(self, task: bytes) -> None: ...

    def observe(self) -> Observation: ...

    def deliver(self, request: Request, response: Response) -> None: ...

    def send_continuation(self, text: str) -> None: ...

    def residual_sessions(self) -> int: ...      # active sessions on the evaluator-owned servers (step 0)

    def interrupt(self) -> None: ...             # step 1, resume=false

    def supersede(self) -> None: ...             # step 2: A supersedes the Lead generation; R does nothing

    def meters(self) -> list[Meter]: ...         # the evaluator-owned servers' meters


MeterFactory = Callable[[TapServer, Path, str | None], Meter]  # (server, state path, root session) -> meter


def earliest_root_session(sessions: list[dict[str, Any]]) -> str | None:
    """The server's earliest session without a parent (R4-m6): a worker's root when its run record names none."""
    roots = [s for s in sessions if not s.get("parentID") and isinstance(s.get("id"), str)]
    roots.sort(key=lambda s: ((s.get("time") or {}).get("created") or 0, s["id"]))
    return roots[0]["id"] if roots else None


def _tokens(sample: Any) -> dict[str, int] | None:
    """A sample's token counts, or ``None`` when they are not an object of non-negative integers (an arm-written live
    file can hold anything)."""
    tokens = sample.get("tokens") if isinstance(sample, dict) else None
    if not isinstance(tokens, dict):
        return None
    out: dict[str, int] = {}
    for key in TOKEN_KEYS:
        value = tokens.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        out[key] = value
    return out


# ---------------------------------------------------------------------------------------------- per-worker meters

@dataclass
class _Worker:
    server: TapServer
    meter: Meter | None              # None when it could not be built: a source that never answers
    first_seen: float
    sample: dict[str, Any] | None = None
    gone: bool = False
    final: dict[str, Any] | None = None
    live: dict[str, int] | None = None  # the live file's last token counts
    live_seen: bool = False
    answered: bool = False  # a poll returned a sample, or the final sample was taken from the server itself


class WorkerMeters:
    """Every worker server ``arm-tap`` reports, metered by the evaluator with its own meter and state (§2.6.1)."""

    def __init__(self, factory: MeterFactory, state_root: Path, *, run_id: str, s_pot: int,
                 clock: Callable[[], float]) -> None:
        self.factory = factory
        self.state_root = Path(state_root)
        self.run_parts = ("runs", *run_id.split("/"))
        self.s_pot = s_pot
        self.clock = clock
        self.workers: dict[str, _Worker] = {}
        self.cf_evidence: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def observe(self, events: list[TapEvent]) -> None:
        for event in events:
            if isinstance(event, TapServer) and event.key not in self.workers:
                self._add(event)
            elif isinstance(event, TapServerGone) and event.key in self.workers:
                self.workers[event.key].gone = True
            elif isinstance(event, TapLiveFile):
                self._cross_check(event)

    def _add(self, server: TapServer) -> None:
        """A new worker server: its own meter, with state in a fresh directory of this run (never one another run or
        meter used). The state directory is the evaluator's own: a failure there is the evaluator's and raises. A
        meter that cannot be built from what ``arm-tap`` read (arm-influenced) leaves a source that never answers."""
        state_dir = spend.private_dir(self.state_root, *self.run_parts, "meters", f"worker-{len(self.workers)}",
                                      fresh=True)
        try:
            meter: Meter | None = self.factory(server, state_dir / "meter-state.json", server.root_session)
        except Exception as exc:  # noqa: BLE001 (arm-influenced input: recorded, the source never answers)
            meter = None
            self.cf_evidence.append({"kind": "WORKER_METER_UNBUILDABLE", "worker": server.key,
                                     "error": f"{type(exc).__name__}"})
        self.workers[server.key] = _Worker(server, meter, self.clock())

    def _cross_check(self, event: TapLiveFile) -> None:
        """A worker's live file against the evaluator's REST high-water and its own last reading (§2.6.1): malformed,
        lower than REST, lower than before, or gone after it was seen is CF evidence. It never raises and the counted
        figure never reads it."""
        for w in self.workers.values():
            if w.server.run_dir != event.run_dir:
                continue
            if event.sample is None:
                if w.live_seen:
                    self.cf_evidence.append({"kind": "WORKER_LIVE_FILE_VANISHED", "worker": w.server.key})
                continue
            w.live_seen = True
            live = _tokens(event.sample)
            if live is None:
                self.cf_evidence.append({"kind": "WORKER_LIVE_FILE_MALFORMED", "worker": w.server.key})
                continue
            rest = _tokens(w.sample) or {}
            below = [k for k in TOKEN_KEYS if live[k] < rest.get(k, 0)]
            if below:
                self.cf_evidence.append({"kind": "WORKER_LIVE_FILE_BELOW_REST", "worker": w.server.key,
                                         "categories": below})
            if w.live is not None:
                decreased = [k for k in TOKEN_KEYS if live[k] < w.live[k]]
                if decreased:
                    self.cf_evidence.append({"kind": "WORKER_LIVE_FILE_DECREASED", "worker": w.server.key,
                                             "categories": decreased})
            w.live = {k: max(live[k], (w.live or {}).get(k, 0)) for k in TOKEN_KEYS}

    def poll(self) -> None:
        for w in self.workers.values():
            if w.final is None and w.meter is not None:
                try:
                    fresh = w.meter.poll()
                except Exception as exc:  # noqa: BLE001 (its server is the arm's: the source just ages)
                    self.errors.append({"at": "worker_poll", "worker": w.server.key, "error": type(exc).__name__})
                    continue
                if fresh is not None:
                    w.sample, w.answered = fresh, True

    def finalize(self) -> None:
        for w in self.workers.values():
            if w.final is not None:
                continue
            final = None
            if w.meter is not None:
                try:
                    final = w.meter.final()
                except Exception as exc:  # noqa: BLE001 (its last sample stands, and ages)
                    self.errors.append({"at": "worker_final", "worker": w.server.key, "error": type(exc).__name__})
            w.final = final or w.sample or {}
            w.sample = final or w.sample
            w.answered = w.answered or (final or {}).get("state") == "final"

    def samples(self) -> list[dict[str, Any]]:
        return [w.sample for w in self.workers.values() if w.sample is not None]

    def unreached(self) -> list[dict[str, Any]]:
        """Workers seen and never sampled: a stale source each, aged from when ``arm-tap`` first saw it."""
        now = self.clock()
        return [{"id": w.server.key, "state": spend.GONE, "age_s": now - w.first_seen, "s_pot": self.s_pot}
                for w in self.workers.values() if not w.answered and now - w.first_seen > 0]

    def never_sampled(self) -> list[str]:
        return [w.server.key for w in self.workers.values() if not w.answered]

    def in_flight(self) -> int:
        total = 0
        for w in self.workers.values():
            value = (w.sample or {}).get("in_flight")
            total += value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0
        return total

    def all_gone(self) -> bool:
        return all(w.gone for w in self.workers.values())


# ---------------------------------------------------------------------------------------------- quiescence

class Quiescence:
    """Q7 §2.4.5: the first non-final quiescence gets the continuation, once; a second, after the arm has returned
    control again, ends the run, attributed to the arm. A final signal ends it as completion."""

    def __init__(self) -> None:
        self.continued_at_turn: int | None = None

    def step(self, facts: QuiescenceFacts) -> str | None:
        """``"continue"``, an end reason, or ``None``."""
        if facts.idle and facts.final_signal and not facts.response_pending:
            return "FINAL_COMPLETION"
        if not facts.nonfinal:
            return None
        if self.continued_at_turn is None:
            self.continued_at_turn = facts.turn
            return "continue"
        return "SECOND_QUIESCENCE" if facts.turn > self.continued_at_turn else None


# ---------------------------------------------------------------------------------------------- the supervisor

@dataclass
class Supervision:
    """What a supervised run produced, for its record (the classifier, S7, reads ``end``). ``arm_failure`` is the
    end's attribution to the arm; whether a second quiescence's deliverable rescues the run is scoring's (Q7
    §2.4.5)."""

    end: str
    arm_failure: bool
    wall_s: float | None
    first_prompt_at: float | None
    responses: list[dict[str, Any]] = field(default_factory=list)
    continuation_sent: bool = False
    shutdown: list[dict[str, Any]] = field(default_factory=list)
    residual_sessions_in_flight: int = 0
    proxy_open_at_close: int = 0
    kill: dict[str, Any] = field(default_factory=dict)
    settled: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    last_check: dict[str, Any] = field(default_factory=dict)
    throttle_events: list[dict[str, Any]] = field(default_factory=list)
    cf_evidence: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)  # each failure, with its step or component


@dataclass(frozen=True)
class RunTerms:
    run_id: str
    partition: str
    task_input_sha256: str
    wall_s: float


class RunSupervisor:
    def __init__(self, *, terms: RunTerms, spend_terms: spend.SpendTerms, driver: ArmDriver, helpers: ArmHelpers,
                 feed: spend.SpendFeed, proxy: spend.ProxyFeed | None, responder: Responder,
                 meter_factory: MeterFactory, state_root: Path, worker_s_pot: int,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep, unsealed_responder_for_tests: bool = False) -> None:
        if spend_terms.layer == "a":
            raise Invalid("layer (a) is not admissible for counted runs: only a partition's limit bounds the arm, and "
                          "the counted cost under the fallback layers is a lower bound")
        if spend_terms.layer == "c" and proxy is None:
            raise Invalid("layer (c) needs the run's proxy ledger")
        if not responder.counted and not unsealed_responder_for_tests:
            raise Invalid("a counted run takes a responder built through Responder.for_counted_run (the sealed "
                          "denial), never one built from a contract directly")
        self.terms, self.spend_terms = terms, spend_terms
        self.driver, self.helpers, self.feed, self.proxy = driver, helpers, feed, proxy
        self.responder = responder
        self.clock, self.sleep = clock, sleep
        self.workers = WorkerMeters(meter_factory, state_root, run_id=terms.run_id, s_pot=worker_s_pot, clock=clock)
        self.quiescence = Quiescence()
        self.max_in_flight = 0
        self.last_usd: float | None = None
        self._tap: Iterator[list[TapEvent]] | None = None

    # ------------------------------------------------------------------ reading

    def _tap_batch(self) -> None:
        if self._tap is None:
            self._tap = self.helpers.tap()
        try:
            self.workers.observe(next(self._tap))
        except StopIteration:
            pass

    def _own_samples(self, result: Supervision) -> list[dict[str, Any]]:
        """The evaluator-owned servers' samples. Their servers run as the arm: a meter that raises is a source that
        ages, never a supervisor fault."""
        out = []
        for meter in self.driver.meters():
            try:
                sample = meter.poll()
            except Exception as exc:  # noqa: BLE001 (arm-influenced: recorded, the source ages)
                result.errors.append({"at": "own_poll", "error": type(exc).__name__})
                continue
            if sample is not None:
                out.append(sample)
        return out

    def _throttle(self, result: Supervision) -> None:
        if self.proxy is None:
            return
        for event in self.proxy.throttle_events():
            result.throttle_events.append({**event, "run_id": self.terms.run_id, "partition": self.terms.partition})

    # ------------------------------------------------------------------ the run

    def run(self, task: bytes) -> Supervision:
        if hashlib.sha256(task).hexdigest() != self.terms.task_input_sha256:
            raise Invalid("the task bytes are not the run manifest's (task_input_sha256): nothing is sent")
        result = Supervision(end="", arm_failure=False, wall_s=None, first_prompt_at=None)
        end: str | None = None
        try:
            self.driver.prepare()
        except Exception as exc:  # noqa: BLE001 (before any model runs: an environment failure, then the shutdown)
            end = "PREPARE_FAILED"
            result.errors.append({"at": "prepare", "error": f"{type(exc).__name__}: {exc}"[-600:]})
        started = self.clock()  # before the prompt: a prompt call that blocks is already supervised and capped
        if end is None:
            result.first_prompt_at = started
            try:
                self.driver.send_first_prompt(task)
            except Exception as exc:  # noqa: BLE001 (it may have been admitted: the shutdown order runs)
                end = "FIRST_PROMPT_FAILED"
                result.errors.append({"at": "first_prompt", "error": f"{type(exc).__name__}: {exc}"[-600:]})
        while end is None:
            end = self._tick(result, started)
            if end is None:
                self.sleep(self.spend_terms.poll_s)
        result.end = end
        result.arm_failure = end in ARM_FAILURES
        result.wall_s = round(self.clock() - started, 3)
        try:
            self._shutdown(result)
        except Exception as exc:  # noqa: BLE001 (the record survives a defect in the shutdown itself)
            result.errors.append({"at": "shutdown", "error": f"{type(exc).__name__}: {exc}"[-600:]})
            self._unresolved(result, "shutdown_failed")
        return result

    def _tick(self, result: Supervision, started: float) -> str | None:
        try:  # the evaluator's own paths: arm-tap's helper, the spend feed and rule
            self._tap_batch()
            samples = self._own_samples(result)
            self.workers.poll()
            total = dict(self.feed.total_spend(samples + self.workers.samples(), self.clock()))
            total["sources"] = list(total.get("sources") or []) + self.workers.unreached()
            self.max_in_flight = max(self.max_in_flight, int(total.get("in_flight") or 0))
            checked = spend.check(self.spend_terms, total, max_in_flight=self.max_in_flight, proxy=self.proxy)
            result.last_check = checked.figures
            self.last_usd = checked.figures["usd"]
            self._throttle(result)
        except Exception as exc:  # noqa: BLE001 (consumes no arm-controlled input: the evaluator's own fault)
            result.errors.append({"at": "tick", "component": "evaluator",
                                  "error": f"{type(exc).__name__}: {exc}"[-600:]})
            return "EVALUATOR_FAILURE"
        if checked.reason is not None:
            return checked.reason
        if self.clock() - started >= self.terms.wall_s:
            return "WALL_CAP"
        try:
            return self._observe(result)
        except Exception as exc:  # noqa: BLE001 (the arm-facing driver calls: attributed to the arm)
            result.errors.append({"at": "tick", "component": "driver",
                                  "error": f"{type(exc).__name__}: {exc}"[-600:]})
            return "ARM_FACING_FAILURE"

    def _observe(self, result: Supervision) -> str | None:
        seen = self.driver.observe()
        for request in seen.requests:
            response = self.responder.answer(request.request_class)
            result.responses.append({"request": request.id, "class": request.request_class, "halt": response.halt})
            if response.halt:
                return "OPERATOR_ONLY_HALT"
            self.driver.deliver(request, response)
        if seen.refusal:
            return "REFUSAL"
        if seen.governed_failure:
            return "GOVERNED_FAILURE"
        if seen.quiescence is not None:
            step = self.quiescence.step(seen.quiescence)
            if step == "continue":
                self.driver.send_continuation(self.responder.continuation)
                result.continuation_sent = True
            elif step is not None:
                return step
        return None

    # ------------------------------------------------------------------ the shutdown order

    def _step(self, result: Supervision, name: str, **facts: Any) -> None:
        result.shutdown.append({"step": name, "at": self.clock(), **facts})

    def _attempt(self, result: Supervision, name: str, call: Callable[[], Any], default: Any = None) -> Any:
        """One shutdown action; a failure is recorded and the order goes on, so the kill and the settle always
        happen."""
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 (recorded; the next steps still run)
            result.errors.append({"at": name, "error": f"{type(exc).__name__}: {exc}"[-600:]})
            return default

    def _unresolved(self, result: Supervision, reason: str) -> None:
        """No counted figure could be resolved: the run is charged its cap, and nothing reads as complete."""
        result.cost.update({"counted_usd": None, "counted_resolved": False, "charged_usd": self.spend_terms.cap_usd,
                            "unresolved_reason": reason})

    def _shutdown(self, result: Supervision) -> None:
        t0 = self.clock()
        deadline = t0 + self.spend_terms.settle_deadline_s
        # 0. The residual, before any interrupt. One that cannot be read is counted as the full S_pot_arm.
        self._attempt(result, "residual", self.workers.poll)
        own = self._attempt(result, "residual", self.driver.residual_sessions, self.spend_terms.s_pot_arm)
        own = own if isinstance(own, int) and not isinstance(own, bool) and own >= 0 else self.spend_terms.s_pot_arm
        result.residual_sessions_in_flight = own + self.workers.in_flight()
        result.proxy_open_at_close = (self._attempt(result, "residual", self.proxy.open_requests, 0)
                                      if self.proxy is not None else 0)
        self._step(result, "residual", sessions=result.residual_sessions_in_flight,
                   proxy_open=result.proxy_open_at_close)
        # 1. Interrupt the evaluator-owned session; 2. supersede the Lead generation.
        self._attempt(result, "interrupt", self.driver.interrupt)
        self._step(result, "interrupt")
        self._attempt(result, "supersede", self.driver.supersede)
        self._step(result, "supersede")
        # 3. The evaluator-owned servers' final samples.
        own_final = []
        for meter in self._attempt(result, "final_samples", self.driver.meters, []):
            sample = self._attempt(result, "final_samples", meter.final)
            if sample is None:  # its last sample stands, and ages
                sample = self._attempt(result, "final_samples", meter.poll)
            if sample is not None:
                own_final.append(sample)
        self._step(result, "final_samples", sources=len(own_final))
        # 4. Wait for the worker servers to go (or the deadline), then their final samples.
        while not self.workers.all_gone() and self.clock() < deadline:
            self.sleep(self.spend_terms.poll_s)
            self._attempt(result, "workers_final", self._tap_batch)
            self._attempt(result, "workers_final", self.workers.poll)
        self._attempt(result, "workers_final", self.workers.finalize)
        self._step(result, "workers_final", gone=self.workers.all_gone())
        # 5. The last reads: every meter once more, and arm-tap's mirror.
        last = self._attempt(result, "last_reads", lambda: self._own_samples(result)) or own_final
        self._attempt(result, "last_reads", self._tap_batch)
        samples = last + self.workers.samples()
        self._step(result, "last_reads", samples=len(samples))
        # 6. arm-kill, with its proof.
        proof = self._attempt(result, "kill", self.helpers.kill)
        if proof is None:
            result.kill = {"ended": 0, "remaining": None}  # no proof: the run's processes may still be spending
            result.cf_evidence.append({"kind": "ARM_KILL_UNPROVEN"})
        else:
            result.kill = {"ended": len(proof.ended), "remaining": list(proof.remaining)}
            if proof.remaining:
                result.cf_evidence.append({"kind": "ARM_PROCESSES_SURVIVED", "pids": list(proof.remaining)})
        self._step(result, "kill", remaining=None if proof is None else len(proof.remaining))
        # 7. Settle, then the proxy closes the run's ledger, then the counted cost.
        settled = self._settled(result, samples, proof)
        result.settled = settled
        self._step(result, "settle", completeness=settled["completeness"])
        proxy_usd = None
        if self.proxy is not None:
            ledger = self._attempt(result, "proxy_close", self.proxy.close)
            if isinstance(ledger, dict):
                proxy_usd = self._attempt(result, "proxy_close", lambda: spend.usd(ledger.get("usd")))
                estimated = self._attempt(result, "proxy_close", lambda: spend.usd(ledger.get("estimated_usd", 0)))
                result.cost["proxy_ledger"] = ledger
                live = settled.get("usd")
                if proxy_usd is not None and live is not None and estimated is not None:
                    result.cost["proxy_live_divergence"] = spend.divergence(
                        self.spend_terms, proxy_usd=proxy_usd, live_usd=spend.usd(live),
                        residual_sessions=result.residual_sessions_in_flight,
                        open_at_close=result.proxy_open_at_close, estimated_usd=estimated)
                    if result.cost["proxy_live_divergence"]["exceeds"]:
                        result.cf_evidence.append({"kind": "PROXY_LIVE_DIVERGENCE",
                                                   **result.cost["proxy_live_divergence"]})
            self._attempt(result, "proxy_close", lambda: self._throttle(result))
            self._step(result, "proxy_closed", resolved=proxy_usd is not None)
        cost = self._attempt(result, "counted", lambda: spend.counted(self.spend_terms, settled, proxy_usd))
        if cost is None:
            self._unresolved(result, "counted_failed")
        else:
            result.cost.update(cost)
            if cost.get("lower_bound"):
                result.cf_evidence.append({"kind": "COUNTED_COST_LOWER_BOUND", "layer": self.spend_terms.layer})
        counted_usd = result.cost.get("counted_usd")
        result.cost["overshoot_usd"] = (max(0.0, counted_usd - self.spend_terms.cap_usd)
                                        if isinstance(counted_usd, float) and math.isfinite(counted_usd) else None)
        result.cost["residual_bound_usd"] = (result.residual_sessions_in_flight * self.spend_terms.k_assumed
                                             * self.spend_terms.c_usd)
        result.cf_evidence.extend(self.workers.cf_evidence)
        result.errors.extend(self.workers.errors)

    def _settled(self, result: Supervision, samples: list[dict[str, Any]], proof: Any) -> dict[str, Any]:
        """F25's settle, checked. A failed or malformed settle keeps the last measured figure as ``unknown``, never
        zero; with no kill proof, or a worker server that never answered, the total is ``unknown`` too."""
        settled = self._attempt(result, "settle", lambda: dict(self.feed.settle(
            samples, closed_at=self.clock(), residual_sessions_in_flight=result.residual_sessions_in_flight)))
        reasons: dict[str, Any] = {}
        if isinstance(settled, dict):
            try:
                spend.usd(settled.get("usd"))
                if settled.get("completeness") not in ("complete", "lower_bound", "unknown"):
                    raise Invalid("a settled total's completeness is complete, lower_bound or unknown")
            except Invalid as exc:
                result.errors.append({"at": "settle", "error": str(exc)[-600:]})
                settled = None
        if not isinstance(settled, dict):
            settled = {"usd": None if self.last_usd is None else str(self.last_usd), "completeness": "unknown",
                       "reasons": {}}
            reasons["settle_failed"] = 1
        if proof is None:
            reasons["kill_unproven"] = 1
        never = self.workers.never_sampled()
        if never:  # a seen worker server is never never_launched (§2.6.1)
            reasons["seen_never_sampled"] = len(never)
        if reasons:
            settled["completeness"] = "unknown"
            settled["reasons"] = {**(settled.get("reasons") or {}), **reasons}
        return settled
