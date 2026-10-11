"""The run supervisor's core (register F19; F19 plan v5 S8, its S8a half): the responder's fixed texts and R's
delivery hooks, the quiescence machine, the per-worker meters from ``arm-tap``'s events, both termination tests, the
shutdown order with its last reads, the wall cap, throttle events and the proxy-versus-live cross-check. Everything
runs against fakes of the arm driver, the helpers, F25's feed and the proxy; synthetic values only.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import responder as R  # noqa: E402
from aew_eval import spend  # noqa: E402
from aew_eval.helpers import KillProof, TapLiveFile, TapServer, TapServerGone  # noqa: E402
from aew_eval.schemas import Invalid  # noqa: E402
from aew_eval.supervisor import (  # noqa: E402
    Observation,
    QuiescenceFacts,
    Request,
    RunSupervisor,
    RunTerms,
    earliest_root_session,
)

TASK = b"Fix add so that it adds.\n"
PASSWORD = "worker-password-synthetic-7f3c"
FIXTURE = json.loads((ROOT / "tests/fixtures/opencode/openapi-2.0.18.min.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------- fakes

class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


class Log(list):
    def add(self, *event: Any) -> None:
        self.append(event)


class FakeMeter:
    """A meter whose samples come from ``script(t) -> sample | None``; it logs every poll and final."""

    def __init__(self, name: str, clock: Clock, log: Log, script=None, *, fails_after: float | None = None) -> None:
        self.name, self.clock, self.log = name, clock, log
        self.script = script or (lambda t: {"usd": 0.0, "at": t, "in_flight": 0, "state": "live"})
        self.fails_after = fails_after
        self.sample: dict | None = None

    def poll(self) -> dict | None:
        self.log.add("poll", self.name)
        if self.fails_after is None or self.clock() < self.fails_after:
            fresh = self.script(self.clock())
            if fresh is not None:
                self.sample = {"source": {"id": self.name}, **fresh}
        return self.sample

    def final(self) -> dict:
        self.log.add("final", self.name)
        answered = self.fails_after is None or self.clock() < self.fails_after
        self.poll()
        answered = answered and self.sample is not None
        # As F25's meter: "final" after a successful last read, else "server_gone" with the last figures.
        self.sample = {**(self.sample or {"source": {"id": self.name}, "usd": 0.0, "at": self.clock()}),
                       "state": "final" if answered else "server_gone"}
        return self.sample


class FakeFeed:
    """F25's total_spend and settle over the fakes' samples: usd summed, age from each sample's ``at``."""

    def __init__(self, log: Log, *, completeness: str = "complete") -> None:
        self.log, self.completeness = log, completeness

    def _total(self, samples, now) -> dict:
        sources = [{"id": s["source"]["id"], "state": s.get("state", "live"), "age_s": now - s.get("at", now),
                    "s_pot": s.get("s_pot", 1), "usd": s.get("usd", 0.0)} for s in samples]
        completeness = "unknown" if any(s.get("unknown") for s in samples) else self.completeness
        return {"usd": str(sum(s.get("usd", 0.0) for s in samples)), "completeness": completeness, "reasons": {},
                "in_flight": sum(s.get("in_flight", 0) for s in samples), "d_min_s": None, "sources": sources}

    def total_spend(self, samples, now) -> dict:
        self.log.add("total")
        return self._total(samples, now)

    def settle(self, samples, *, closed_at, residual_sessions_in_flight) -> dict:
        self.log.add("settle", residual_sessions_in_flight)
        return {**self._total(samples, closed_at), "settled": True,
                "residual_sessions_in_flight": residual_sessions_in_flight}


class FakeProxy:
    def __init__(self, log: Log, *, usd: float = 0.0, open_requests: int = 0, estimated: float = 0.0,
                 events=None) -> None:
        self.log, self.usd, self.open, self.estimated = log, usd, open_requests, estimated
        self.events = list(events or [])

    def run_usd(self) -> float:
        return self.usd

    def estimated_usd(self) -> float:
        return self.estimated

    def open_requests(self) -> int:
        self.log.add("proxy_open")
        return self.open

    def throttle_events(self) -> list:
        out, self.events = self.events, []
        return out

    def close(self) -> dict:
        self.log.add("proxy_close")
        return {"usd": self.usd, "estimated_usd": self.estimated}


class FakeHelpers:
    def __init__(self, log: Log, batches=None, *, remaining=()) -> None:
        self.log, self.batches, self.remaining = log, list(batches or []), tuple(remaining)

    def tap(self):
        while True:
            self.log.add("tap")
            yield self.batches.pop(0) if self.batches else []

    def kill(self) -> KillProof:
        self.log.add("kill")
        return KillProof(ended=(4242,), remaining=self.remaining)

    def launch(self, argv, *, env, cwd, stdin=b""):  # S8b
        raise NotImplementedError

    def pack(self):  # S8b
        raise NotImplementedError


class FakeDriver:
    """An arm whose observations come from ``script(tick) -> Observation``."""

    def __init__(self, clock: Clock, log: Log, script=None, *, meter: FakeMeter | None = None,
                 prepare_s: float = 0.0, residual: int = 1) -> None:
        self.clock, self.log, self.script = clock, log, script or (lambda tick: Observation())
        self.meter = meter or FakeMeter("own", clock, log)
        self.prepare_s, self.residual = prepare_s, residual
        self.tick = 0
        self.sent: list[bytes] = []
        self.delivered: list[tuple[Request, R.Response]] = []
        self.continuations: list[str] = []

    def prepare(self) -> None:
        self.log.add("prepare")
        self.clock.t += self.prepare_s

    def send_first_prompt(self, task: bytes) -> None:
        self.log.add("first_prompt")
        self.sent.append(task)

    def observe(self) -> Observation:
        self.tick += 1
        return self.script(self.tick)

    def deliver(self, request: Request, response: R.Response) -> None:
        self.delivered.append((request, response))

    def send_continuation(self, text: str) -> None:
        self.continuations.append(text)

    def residual_sessions(self) -> int:
        self.log.add("residual")
        return self.residual

    def interrupt(self) -> None:
        self.log.add("interrupt")

    def supersede(self) -> None:
        self.log.add("supersede")

    def meters(self) -> list:
        return [self.meter]


def terms(**over) -> spend.SpendTerms:
    base = {"cap_usd": 10.0, "s_pot_arm": 1, "c_usd": 0.01, "c_choice": "c_ceil", "d_floor_s": 1.0,
            "reconciliation_margin": 0.05, "layer": "b"}
    return spend.SpendTerms(**{**base, **over})


def supervisor(tmp_path: Path, *, clock: Clock | None = None, log: Log | None = None, driver=None, helpers=None,
               feed=None, proxy=None, factory=None, wall_s: float = 3600.0, **spend_over) -> tuple:
    clock, log = clock or Clock(), log if log is not None else Log()
    driver = driver or FakeDriver(clock, log)
    made: dict[str, Any] = {}

    def default_factory(server: TapServer, state_path: Path, root_session: str | None) -> FakeMeter:
        meter = FakeMeter(f"worker:{server.key}", clock, log)
        made[server.key] = {"meter": meter, "state_path": state_path, "root_session": root_session}
        return meter

    sup = RunSupervisor(
        terms=RunTerms(run_id="demo/r1", partition="arm-r", task_input_sha256=hashlib.sha256(TASK).hexdigest(),
                       wall_s=wall_s),
        spend_terms=terms(**spend_over), driver=driver, helpers=helpers or FakeHelpers(log),
        feed=feed or FakeFeed(log), proxy=proxy, responder=R.Responder(R.DRAFT),
        meter_factory=factory or default_factory, state_root=tmp_path / "state", worker_s_pot=2,
        clock=clock, sleep=clock.sleep, unsealed_responder_for_tests=True)
    return sup, driver, log, clock, made


def quiet(turn: int, *, final: bool = False) -> Observation:
    return Observation(quiescence=QuiescenceFacts(idle=True, infrastructure_pending=False, response_pending=False,
                                                  final_signal=final, unfinished=not final, turn=turn))


def finishes(tick: int) -> Observation:
    return quiet(tick, final=tick >= 3)


def server(n: int, *, root: str | None = "ses_root", run_dir: str = "runs/w1") -> TapServer:
    return TapServer(pid=100 + n, start_time=str(5000 + n), port=40000 + n, run_dir=run_dir, root_session=root,
                     password=PASSWORD)


# ---------------------------------------------------------------------------------------------- task and responder

def test_every_arm_receives_exactly_the_sealed_task_bytes(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, finishes)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    sup.run(TASK)
    assert driver.sent == [TASK]
    other = FakeDriver(clock, Log(), finishes)
    sup2, *_ = supervisor(tmp_path / "b", clock=clock, driver=other)
    with pytest.raises(Invalid, match="task_input_sha256"):
        sup2.run(TASK + b" ")  # one byte off: nothing is prepared or sent
    assert other.sent == [] and ("prepare",) not in other.log


def test_a_clarification_gets_exactly_the_fixed_text(tmp_path):
    q7 = ("No additional task information is available. Proceed using the task, repository, and authorized "
          "environment. Make the safest reasonable assumption consistent with the stated objective.")
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: Observation(requests=(Request("frm_1", "clarify"),)) if t == 1
                        else finishes(t))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    sup.run(TASK)
    [(request, response)] = driver.delivered
    assert request.id == "frm_1" and response.text == q7 and not response.halt
    # R's hook: cancel the question form, then admit the text as the next input, through the pinned operations only.
    client = RecordingClient()
    R.OpenCodeDelivery(client).clarify("ses_1", "frm_1", response.text)
    assert client.calls[0] == ("DELETE", "/api/session/ses_1/form/frm_1", None)
    assert client.calls[1] == ("POST", "/api/session/ses_1/prompt", {"text": q7})
    validate_body("/api/session/{sessionID}/prompt", client.calls[1][2])


def test_an_out_of_envelope_request_gets_exactly_the_denial(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: Observation(requests=(Request("per_1", "deny"),)) if t == 1
                        else finishes(t))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    sup.run(TASK)
    [(_, response)] = driver.delivered
    assert response.text == R.DRAFT["texts"]["denial"]["text"]
    client = RecordingClient()
    R.OpenCodeDelivery(client).deny("ses_1", "per_1", response.text)
    assert client.calls == [("POST", "/api/session/ses_1/permission/per_1/reply",
                             {"decision": "reject", "message": response.text})]
    validate_body("/api/session/{sessionID}/permission/{requestID}/reply", client.calls[0][2])
    # The draft denial is unsealed: no counted or calibration run may use it.
    with pytest.raises(Invalid, match="unsealed draft"):
        R.Responder.for_counted_run(R.DRAFT)
    flagged = json.loads(json.dumps(R.DRAFT))
    flagged["texts"]["denial"]["sealed"] = True  # the flag alone is not proof: the draft text is refused verbatim
    with pytest.raises(Invalid, match="unsealed draft"):
        R.Responder.for_counted_run(flagged)
    sealed = json.loads(json.dumps(flagged))
    sealed["texts"]["denial"]["text"] = "A sealed denial text (synthetic)."
    assert R.Responder.for_counted_run(sealed).answer("deny").text == "A sealed denial text (synthetic)."


def test_the_responder_never_answers_an_unclassified_request_or_a_changed_fixed_text():
    with pytest.raises(Invalid, match="never invents an answer"):
        R.Responder(R.DRAFT).answer("other")
    changed = json.loads(json.dumps(R.DRAFT))
    changed["texts"]["clarification"] = "Here is a hint."
    with pytest.raises(Invalid, match="responder contract"):
        R.Responder(changed)


def test_an_operator_only_decision_ends_the_run_as_an_arm_failure(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: Observation(requests=(Request("req_9", "operator_only"),)))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    result = sup.run(TASK)
    assert result.end == "OPERATOR_ONLY_HALT" and result.arm_failure
    assert driver.delivered == []  # nothing is simulated


def test_one_continuation_then_the_second_quiescence_ends_the_run(tmp_path):
    continuation = ("If the task is complete, give your final completion report and stop. Otherwise continue "
                    "working from the current workspace. No additional task information is available.")
    clock, log = Clock(), Log()
    turns = {1: 1, 2: 1, 3: 1, 4: 2}  # the same quiescence seen thrice, then a new one after the arm worked on
    driver = FakeDriver(clock, log, lambda t: quiet(turns.get(t, 2)))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    result = sup.run(TASK)
    assert driver.continuations == [continuation]
    assert result.end == "SECOND_QUIESCENCE" and result.arm_failure and result.continuation_sent
    # A final signal ends the run as completion, with no continuation.
    clock2, log2 = Clock(), Log()
    driver2 = FakeDriver(clock2, log2, lambda t: quiet(1, final=True))
    result2 = supervisor(tmp_path / "b", clock=clock2, log=log2, driver=driver2)[0].run(TASK)
    assert result2.end == "FINAL_COMPLETION" and not result2.arm_failure and driver2.continuations == []


def test_quiescence_never_reads_correctness():
    fields = {f.name for f in dataclasses.fields(QuiescenceFacts)}
    assert fields == {"idle", "infrastructure_pending", "response_pending", "final_signal", "unfinished", "turn"}
    forbidden = {"hidden", "score_child", "runner", "analysis", "campaign", "release", "transport"}
    for module in ("supervisor", "spend", "responder", "helpers"):
        tree = ast.parse((ROOT / "eval" / "aew_eval" / f"{module}.py").read_text(encoding="utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        names |= {(n.module or "").split(".")[-1] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        names |= {a.name.split(".")[-1] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not names & forbidden, (module, names & forbidden)


# ---------------------------------------------------------------------------------------------- per-worker meters

def test_aeweval_meters_every_worker_server_with_its_own_high_water_state(tmp_path):
    clock, log = Clock(), Log()
    helpers = FakeHelpers(log, [[server(1), server(2, run_dir="runs/w2")]])
    driver = FakeDriver(clock, log, finishes)
    sup, _, _, _, made = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=helpers)
    sup.run(TASK)
    assert set(made) == {server(1).key, server(2).key}
    paths = {m["state_path"] for m in made.values()}
    assert len(paths) == 2 and all(p.parent.parent == tmp_path / "state" / "runs" / "demo" / "r1" / "meters"
                                   for p in paths)
    assert all(("poll", f"worker:{k}") in log for k in made)


def test_a_forged_low_worker_live_file_never_lowers_the_counted_cost(tmp_path):
    clock, log = Clock(), Log()

    def factory(srv, state_path, root):
        return FakeMeter("worker", clock, log, lambda t: {"usd": 4.0, "at": t, "tokens": {"input": 900, "output": 90}})

    batches = [[server(1)], [], [TapLiveFile("runs/w1", {"tokens": {"input": 10, "output": 1}, "usd": 0.01})]]
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=t >= 4))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=FakeHelpers(log, batches),
                         factory=factory)
    result = sup.run(TASK)
    assert result.cost["counted_usd"] == pytest.approx(4.0)  # the evaluator's REST figure, never the live file
    assert {"kind": "WORKER_LIVE_FILE_BELOW_REST", "worker": server(1).key,
            "categories": ["input", "output"]} in result.cf_evidence


def test_a_seen_worker_server_is_never_never_launched(tmp_path):
    clock, log = Clock(), Log()

    def factory(srv, state_path, root):
        return FakeMeter("worker", clock, log, lambda t: None)  # never answers

    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=FakeHelpers(log, [[server(1)]]),
                         factory=factory)
    result = sup.run(TASK)
    assert result.settled["completeness"] == "unknown"
    assert result.settled["reasons"]["seen_never_sampled"] == 1
    assert result.cost["charged_usd"] == 10.0  # unknown under layer (b) is charged at the cap


def test_a_worker_server_unreachable_mid_run_ends_the_run_as_a_valid_failure(tmp_path):
    clock, log = Clock(), Log()

    def factory(srv, state_path, root):
        return FakeMeter("worker", clock, log, fails_after=clock() + 3)  # answers, then stops

    driver = FakeDriver(clock, log)  # never quiescent: only the stale worker can end it
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=FakeHelpers(log, [[server(1)]]),
                         factory=factory)
    result = sup.run(TASK)
    assert result.end == "STALE_CEILING" and not result.arm_failure
    assert result.last_check["oldest_age_s"] > 30


def test_an_extra_root_session_on_a_worker_server_is_summed_like_r(tmp_path):
    clock, log = Clock(), Log()
    sessions = [{"id": "ses_b", "time": {"created": 20}}, {"id": "ses_a", "time": {"created": 10}},
                {"id": "ses_c", "parentID": "ses_a", "time": {"created": 5}}]
    assert earliest_root_session(sessions) == "ses_a"  # when the run record names none (R4-m6)
    roots: list[str | None] = []

    def factory(srv, state_path, root):
        roots.append(root)  # the meter sums every other session as foreign, as F25 does for R
        return FakeMeter("worker", clock, log, lambda t: {"usd": 1.5, "at": t, "foreign_usd": 0.5})

    driver = FakeDriver(clock, log, lambda t: quiet(t, final=t >= 2))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver,
                         helpers=FakeHelpers(log, [[server(1, root="ses_record")]]), factory=factory)
    result = sup.run(TASK)
    assert roots == ["ses_record"]
    assert result.settled["completeness"] == "complete" and result.cost["counted_usd"] == pytest.approx(1.5)


def test_worker_passwords_never_reach_disk(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, finishes)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver,
                         helpers=FakeHelpers(log, [[server(1)], [TapServerGone(server(1).key)]]))
    result = sup.run(TASK)
    assert PASSWORD not in repr(server(1))
    assert PASSWORD not in json.dumps(dataclasses.asdict(result), default=str)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert PASSWORD.encode() not in path.read_bytes(), path


def test_meter_state_and_its_parents_are_aeweval_owned(tmp_path):
    state = spend.private_dir(tmp_path / "state", "meters", "worker-0")
    spend.require_private(state, tmp_path / "state")
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(state).st_mode) == 0o700
        os.chmod(tmp_path / "state" / "meters", 0o777)  # noqa: S103 (the permissive mode is what is refused)
        with pytest.raises(Invalid, match="writable by others"):
            spend.require_private(state, tmp_path / "state")
        os.chmod(tmp_path / "state" / "meters", 0o700)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    linked = tmp_path / "state" / "meters" / "worker-1"
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(elsewhere), str(linked))
    else:
        os.symlink(elsewhere, linked, target_is_directory=True)
    with pytest.raises(Invalid, match="is a link"):
        spend.require_private(linked, tmp_path / "state")


# ---------------------------------------------------------------------------------------------- termination

def test_the_cap_terminates_at_usd_plus_projection_plus_guard_and_records_overshoot(tmp_path):
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 9.0 + (t - 1000) * 0.5, "at": t})
    driver = FakeDriver(clock, log, meter=meter)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, cap_usd=10.0, c_usd=0.1)
    result = sup.run(TASK)
    figures = result.last_check
    # guard = S_pot_arm 1 × k 2 × c 0.1 × (⌊(2+1+3)/1⌋ + 2) = 1.6, so the run ends once usd reaches 8.4.
    assert result.end == "USD_CAP" and figures["guard"] == pytest.approx(1.6)
    assert figures["usd"] + figures["projection"] + figures["guard"] >= 10.0
    assert figures["usd"] == pytest.approx(9.0)
    assert result.cost["overshoot_usd"] == pytest.approx(max(0.0, result.cost["counted_usd"] - 10.0))


def test_the_proxy_test_ends_the_run_when_proxy_spend_reaches_the_cap(tmp_path):
    clock, log = Clock(), Log()
    proxy = FakeProxy(log, usd=9.95, open_requests=1)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, proxy=proxy, layer="c", c_usd=0.1, cap_usd=10.0)
    result = sup.run(TASK)
    assert result.end == "PROXY_CAP"
    assert result.cost["source"] == "proxy" and result.cost["counted_usd"] == pytest.approx(9.95)


def test_the_guard_uses_the_preregistered_s_pot_arm():
    t = terms(s_pot_arm=3, c_usd=0.1)
    assert spend.guard(t, d_min_s=None, max_in_flight=50) == pytest.approx(3 * 2 * 0.1 * 8)
    assert spend.guard(t, d_min_s=0.5, max_in_flight=0) == pytest.approx(3 * 2 * 0.1 * 14)  # d = min(d_min, d_floor)
    total = {"usd": "0", "completeness": "complete", "in_flight": 1, "s_pot_present": 40,
             "sources": [{"id": "a", "s_pot": 20, "age_s": 0.1}]}
    assert spend.check(t, total, max_in_flight=1, proxy=None).figures["guard"] == pytest.approx(4.8)
    hard = terms(s_pot_arm=3, c_usd=0.1, s_pot_hard=6)  # R without a sealed cap key: max(S_pot_arm, in_flight)
    assert spend.guard(hard, d_min_s=None, max_in_flight=5) == pytest.approx(5 * 2 * 0.1 * 8)


def test_a_stale_source_is_projected_with_its_own_s_pot_until_the_hard_ceiling():
    t = terms(c_usd=0.1, cap_usd=100.0)
    stale = {"usd": "1", "completeness": "lower_bound", "in_flight": 0,
             "sources": [{"id": "w", "s_pot": 3, "age_s": 10.0}, {"id": "own", "s_pot": 1, "age_s": 0.5}]}
    checked = spend.check(t, stale, max_in_flight=0, proxy=None)
    assert checked.reason is None and checked.figures["projection"] == pytest.approx(3 * 2 * 0.1 * 12)
    past = {**stale, "sources": [{"id": "w", "s_pot": 3, "age_s": 31.0}]}
    assert spend.check(t, past, max_in_flight=0, proxy=None).reason == "STALE_CEILING"


def test_exceeding_s_pot_hard_ends_the_run_as_s_pot_exceeded(tmp_path):
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 0.0, "at": t, "in_flight": 7})
    driver = FakeDriver(clock, log, meter=meter)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, s_pot_arm=3, s_pot_hard=6)
    result = sup.run(TASK)
    assert result.end == "S_POT_EXCEEDED" and not result.arm_failure


def test_an_unknown_total_terminates_at_once(tmp_path):
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 0.0, "at": t, "unknown": True})
    driver = FakeDriver(clock, log, meter=meter)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    result = sup.run(TASK)
    assert result.end == "UNKNOWN_TOTAL" and driver.tick == 0  # ended at the first check, before any observation


def test_the_wall_clock_starts_at_the_first_prompt(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, prepare_s=500.0)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, wall_s=100.0)
    result = sup.run(TASK)
    assert result.end == "WALL_CAP"
    assert result.first_prompt_at == pytest.approx(1500.0) and 100.0 <= result.wall_s <= 101.0


def test_throttle_events_are_recorded_per_run_with_their_partition(tmp_path):
    clock, log = Clock(), Log()
    proxy = FakeProxy(log, events=[{"at": 1.0, "kind": "429"}, {"at": 2.0, "kind": "retry"}])
    driver = FakeDriver(clock, log, finishes)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, proxy=proxy, layer="c")
    result = sup.run(TASK)
    assert result.throttle_events == [{"at": 1.0, "kind": "429", "run_id": "demo/r1", "partition": "arm-r"},
                                      {"at": 2.0, "kind": "retry", "run_id": "demo/r1", "partition": "arm-r"}]


# ---------------------------------------------------------------------------------------------- the shutdown order

ENDS = {
    "FINAL_COMPLETION": ({}, lambda t: quiet(t, final=True), None),
    "SECOND_QUIESCENCE": ({}, lambda t: quiet(t), None),
    "OPERATOR_ONLY_HALT": ({}, lambda t: Observation(requests=(Request("q", "operator_only"),)), None),
    "REFUSAL": ({}, lambda t: Observation(refusal=True), None),
    "WALL_CAP": ({"wall_s": 5.0}, None, None),
    "USD_CAP": ({}, None, 20.0),
    "PROXY_CAP": ({"layer": "c"}, None, None),
}


@pytest.mark.parametrize("end", sorted(ENDS))
def test_every_counted_run_end_follows_the_shutdown_order_and_settles_within_the_deadline(tmp_path, end):
    over, script, own_usd = ENDS[end]
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, (lambda t: {"usd": own_usd, "at": t}) if own_usd else None)
    driver = FakeDriver(clock, log, script, meter=meter)
    proxy = FakeProxy(log, usd=11.0 if end == "PROXY_CAP" else 0.0)
    helpers = FakeHelpers(log, [[server(1)]] + [[]] * 8 + [[TapServerGone(server(1).key)]])
    wall = over.pop("wall_s", 3600.0)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, proxy=proxy, helpers=helpers, wall_s=wall,
                         **{"layer": "c", **over})
    result = sup.run(TASK)
    assert result.end == end
    steps = [s["step"] for s in result.shutdown]
    assert steps == ["residual", "interrupt", "supersede", "final_samples", "workers_final", "last_reads", "kill",
                     "settle", "proxy_closed"]
    assert result.shutdown[-1]["at"] - result.shutdown[0]["at"] <= terms().settle_deadline_s + terms().poll_s
    assert result.kill == {"ended": 1, "remaining": [], "proven": True}


def test_residual_sessions_in_flight_is_read_before_the_first_interrupt(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True), residual=2)
    helpers = FakeHelpers(log, [[server(1)]])

    def factory(srv, state_path, root):
        return FakeMeter("worker", clock, log, lambda t: {"usd": 0.0, "at": t, "in_flight": 1})

    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=helpers, factory=factory)
    result = sup.run(TASK)
    assert log.index(("residual",)) < log.index(("interrupt",))
    shutdown = log[log.index(("residual",)) - 1:]
    assert ("poll", "worker") in log[:log.index(("interrupt",))] and shutdown
    assert result.residual_sessions_in_flight == 3  # the evaluator-owned server's 2 and the worker's 1
    assert result.settled["residual_sessions_in_flight"] == 3


def test_the_last_meter_and_mirror_reads_precede_settle(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    sup.run(TASK)
    finals = log.index(("final", "own"))
    settle = next(i for i, e in enumerate(log) if e[0] == "settle")
    kill = log.index(("kill",))
    between = log[finals + 1:kill]
    assert ("poll", "own") in between and ("tap",) in between  # the last reads
    assert finals < kill < settle


# ---------------------------------------------------------------------------------------------- the CF cross-check

@pytest.mark.parametrize(("proxy_usd", "exceeds"), [(5.0, True), (2.05, False)])
def test_a_proxy_live_divergence_above_tolerance_is_cf_evidence(tmp_path, proxy_usd, exceeds):
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 2.0, "at": t})
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True), meter=meter, residual=0)
    proxy = FakeProxy(log, usd=proxy_usd)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, proxy=proxy, layer="c", c_usd=0.01,
                         reconciliation_margin=0.05)
    result = sup.run(TASK)
    div = result.cost["proxy_live_divergence"]
    assert div["proxy_usd"] == pytest.approx(proxy_usd) and div["live_usd"] == pytest.approx(2.0)
    assert div["exceeds"] is exceeds
    assert any(e["kind"] == "PROXY_LIVE_DIVERGENCE" for e in result.cf_evidence) is exceeds
    assert result.cost["counted_usd"] == pytest.approx(proxy_usd)  # under (c), the proxy's ledger is counted


# ---------------------------------------------------------------------------------------------- helpers for R's hooks

class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def post(self, path: str, body: Any = None, params: dict | None = None) -> Any:
        self.calls.append(("POST", path, body))

    def delete(self, path: str) -> Any:
        self.calls.append(("DELETE", path, None))


def validate_body(path: str, body: dict) -> None:
    """A request body against the pinned OpenCode 2.0.18 operation's schema."""
    schema = FIXTURE["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
    jsonschema.Draft202012Validator({**schema, "components": FIXTURE["components"]}).validate(body)


def test_a_failing_shutdown_step_never_stops_the_kill_or_the_settle(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True))
    driver.interrupt = lambda: (_ for _ in ()).throw(ConnectionError("server gone"))  # type: ignore[method-assign]
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    result = sup.run(TASK)
    assert result.end == "FINAL_COMPLETION" and [e["at"] for e in result.errors] == ["interrupt"]
    assert ("kill",) in log and any(e[0] == "settle" for e in log)  # the kill and the settle still happened
    assert [s["step"] for s in result.shutdown][-2:] == ["kill", "settle"]


# ---------------------------------------------------------------------------------------------- PR #196 review

SHUTDOWN_STEPS = ["residual", "interrupt", "supersede", "final_samples", "workers_final", "last_reads", "kill",
                  "settle", "proxy_closed"]


def _raise(exc: Exception):
    def call(*args: Any, **kwargs: Any) -> Any:
        raise exc
    return call


def _prepare_fails(driver: FakeDriver, feed: FakeFeed) -> None:
    driver.prepare = _raise(RuntimeError("the endpoint reported an error after it started"))  # type: ignore


def _prompt_fails(driver: FakeDriver, feed: FakeFeed) -> None:
    driver.send_first_prompt = _raise(TimeoutError("the reply timed out after admission"))  # type: ignore


def _feed_fails(driver: FakeDriver, feed: FakeFeed) -> None:
    feed.total_spend = _raise(RuntimeError("the spend feed failed"))  # type: ignore


def _observe_fails(driver: FakeDriver, feed: FakeFeed) -> None:
    driver.script = _raise(ValueError("the arm's server sent junk"))


FAILURE_ENDS = {
    "PREPARE_FAILED": (_prepare_fails, False),
    "FIRST_PROMPT_FAILED": (_prompt_fails, False),
    "EVALUATOR_FAILURE": (_feed_fails, False),
    "ARM_FACING_FAILURE": (_observe_fails, False),
}


@pytest.mark.parametrize("end", sorted(FAILURE_ENDS))
def test_every_exit_from_run_takes_the_shutdown_order_and_returns_a_record(tmp_path, end):
    inject, arm_failure = FAILURE_ENDS[end]
    clock, log = Clock(), Log()
    driver, feed, proxy = FakeDriver(clock, log), FakeFeed(log), FakeProxy(log, usd=0.5)
    inject(driver, feed)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, feed=feed, proxy=proxy, layer="c")
    result = sup.run(TASK)
    assert result.end == end and result.arm_failure is arm_failure
    assert [s["step"] for s in result.shutdown] == SHUTDOWN_STEPS
    assert ("kill",) in log and ("proxy_close",) in log and result.cost["counted_usd"] == pytest.approx(0.5)


def test_the_wall_clock_runs_while_the_first_prompt_blocks(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log)

    def blocking(task: bytes) -> None:  # a driver that wrongly waits for the turn: still supervised and capped
        clock.t += 200.0

    driver.send_first_prompt = blocking  # type: ignore[method-assign]
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, wall_s=100.0)
    result = sup.run(TASK)
    assert result.end == "WALL_CAP" and result.wall_s >= 200.0


@pytest.mark.parametrize("sample", [{"tokens": {"input": "lots"}}, {"tokens": [1, 2]}, [1, 2], {"tokens": None},
                                    {"tokens": {"input": -5}}, {"tokens": {"output": True}}])
def test_a_malformed_live_file_is_cf_evidence_never_a_supervisor_fault(tmp_path, sample):
    clock, log = Clock(), Log()
    batches = [[server(1)], [TapLiveFile("runs/w1", sample)]]  # type: ignore[arg-type]
    driver = FakeDriver(clock, log, lambda t: quiet(1, final=t >= 3))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=FakeHelpers(log, batches))
    result = sup.run(TASK)
    assert result.end == "FINAL_COMPLETION"
    assert {"kind": "WORKER_LIVE_FILE_MALFORMED", "worker": server(1).key} in result.cf_evidence


def test_a_meter_that_raises_on_an_arm_server_is_a_source_that_ages_never_a_fault(tmp_path):
    clock, log = Clock(), Log()

    class Broken(FakeMeter):
        def poll(self) -> dict | None:
            raise ValueError("the arm's server answered junk")

    driver = FakeDriver(clock, log, meter=Broken("own", clock, log))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver,
                         factory=lambda srv, path, root: Broken("worker", clock, log),
                         helpers=FakeHelpers(log, [[server(1)]]))
    result = sup.run(TASK)
    assert result.end == "STALE_CEILING" and not result.arm_failure  # the worker never answered: projected, then ended
    assert any(e["at"] == "own_poll" for e in result.errors)


def test_a_finished_worker_never_ends_a_still_working_run_at_the_stale_ceiling(tmp_path):
    clock, log = Clock(), Log()

    class Finished(FakeMeter):
        def poll(self) -> dict | None:  # the worker finished at once: its last sample is final, and only ages
            self.sample = self.sample or {"source": {"id": "worker"}, "usd": 0.3, "at": self.clock(), "state": "final"}
            return self.sample

    driver = FakeDriver(clock, log)  # the Lead keeps working
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, wall_s=120.0,
                         factory=lambda srv, path, root: Finished("worker", clock, log),
                         helpers=FakeHelpers(log, [[server(1)]]))
    result = sup.run(TASK)
    assert result.end == "WALL_CAP" and result.last_check["projection"] == 0.0
    assert spend.projection(terms(), [{"state": "final", "age_s": 500.0, "s_pot": 4}], d_min_s=None) == 0.0


def test_a_failed_proxy_close_still_returns_the_record_and_charges_the_cap(tmp_path):
    clock, log = Clock(), Log()
    proxy = FakeProxy(log, usd=1.0)
    proxy.close = _raise(ConnectionError("the proxy restarted"))  # type: ignore[method-assign]
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, proxy=proxy, layer="c")
    result = sup.run(TASK)
    assert result.cost["counted_usd"] is None and result.cost["counted_resolved"] is False
    assert result.cost["charged_usd"] == 10.0 and any(e["at"] == "proxy_close" for e in result.errors)
    assert [s["step"] for s in result.shutdown] == SHUTDOWN_STEPS


@pytest.mark.parametrize("layer", ["b", "c"])
def test_a_failed_settle_keeps_the_last_measured_figure_never_zero(tmp_path, layer):
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 3.0, "at": t})
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=t >= 2), meter=meter, residual=0)
    feed = FakeFeed(log)
    feed.settle = _raise(RuntimeError("settle failed"))  # type: ignore[method-assign]
    proxy = FakeProxy(log, usd=3.0) if layer == "c" else None
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, feed=feed, proxy=proxy, layer=layer)
    result = sup.run(TASK)
    assert result.settled["completeness"] == "unknown" and result.settled["reasons"]["settle_failed"] == 1
    assert result.cost["live_usd"] == pytest.approx(3.0)
    if layer == "b":
        assert result.cost["counted_usd"] == pytest.approx(3.0) and result.cost["charged_usd"] == 10.0
    else:  # no false divergence: the live cross-check is the last measured figure, not zero
        assert result.cost["proxy_live_divergence"]["exceeds"] is False


def test_a_missing_kill_proof_makes_the_cost_unknown_and_charges_the_cap(tmp_path):
    clock, log = Clock(), Log()
    helpers = FakeHelpers(log)
    helpers.kill = _raise(PermissionError("sudo refused"))  # type: ignore[method-assign]
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 1.0, "at": t})
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True), meter=meter)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=helpers)
    result = sup.run(TASK)
    assert result.kill == {"ended": 0, "remaining": None, "proven": False}
    assert result.settled["completeness"] == "unknown" and result.settled["reasons"]["kill_unproven"] == 1
    assert result.cost["charged_usd"] == 10.0
    # the helper failed: an infrastructure fact, never evidence against the arm (layer (b)'s lower-bound note aside)
    assert [e for e in result.cf_evidence if e["kind"] != "COUNTED_COST_LOWER_BOUND"] == []


def test_a_counted_run_takes_only_a_responder_built_through_the_sealed_path(tmp_path):
    clock, log = Clock(), Log()
    base = dict(terms=RunTerms(run_id="demo/r1", partition="p", task_input_sha256="0" * 64, wall_s=1.0),
                spend_terms=terms(), driver=FakeDriver(clock, log), helpers=FakeHelpers(log), feed=FakeFeed(log),
                proxy=None, meter_factory=lambda *a: None, state_root=tmp_path, worker_s_pot=1)
    with pytest.raises(Invalid, match="for_counted_run"):
        RunSupervisor(**base, responder=R.Responder(R.DRAFT))  # type: ignore[arg-type]
    sealed = json.loads(json.dumps(R.DRAFT))
    sealed["texts"]["denial"] = {"text": "A sealed denial text (synthetic).", "sealed": True}
    RunSupervisor(**base, responder=R.Responder.for_counted_run(sealed))  # type: ignore[arg-type]


def test_worker_meter_state_is_run_scoped_and_never_reused(tmp_path):
    first, *_ = supervisor(tmp_path, helpers=FakeHelpers(Log(), [[server(1)]]))
    first.workers.observe([server(1)])
    path = tmp_path / "state" / "runs" / "demo" / "r1" / "meters" / "worker-0"
    assert path.is_dir()
    again, *_ = supervisor(tmp_path)  # the same run id over the same state root: never the old state
    with pytest.raises(Invalid, match="made fresh"):
        again.workers.observe([server(1)])
    other = RunSupervisor(
        terms=RunTerms(run_id="demo/r2", partition="p", task_input_sha256="0" * 64, wall_s=1.0), spend_terms=terms(),
        driver=FakeDriver(Clock(), Log()), helpers=FakeHelpers(Log()), feed=FakeFeed(Log()), proxy=None,
        responder=R.Responder(R.DRAFT), meter_factory=lambda srv, p, r: FakeMeter("w", Clock(), Log()),
        state_root=tmp_path / "state", worker_s_pot=1, unsealed_responder_for_tests=True)
    other.workers.observe([server(1)])
    assert (tmp_path / "state" / "runs" / "demo" / "r2" / "meters" / "worker-0").is_dir()


def test_a_live_file_that_decreases_is_cf_evidence(tmp_path):
    clock, log = Clock(), Log()

    def factory(srv, state_path, root):
        return FakeMeter("worker", clock, log, lambda t: {"usd": 0.1, "at": t, "tokens": {"input": 300}})

    batches = [[server(1)], [TapLiveFile("runs/w1", {"tokens": {"input": 900}})],
               [TapLiveFile("runs/w1", {"tokens": {"input": 400}})]]
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=t >= 4))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=FakeHelpers(log, batches),
                         factory=factory)
    result = sup.run(TASK)
    decreased = {"kind": "WORKER_LIVE_FILE_DECREASED", "worker": server(1).key, "categories": ["input"]}
    assert decreased in result.cf_evidence


def test_the_counted_cost_under_the_fallback_layers_is_a_lower_bound_and_layer_a_is_refused(tmp_path):
    clock, log = Clock(), Log()
    meter = FakeMeter("own", clock, log, lambda t: {"usd": 2.0, "at": t})
    driver = FakeDriver(clock, log, lambda t: quiet(t, final=True), meter=meter)
    result = supervisor(tmp_path, clock=clock, log=log, driver=driver, layer="b")[0].run(TASK)
    assert result.cost["lower_bound"] is True and result.cost["counted_usd"] == pytest.approx(2.0)
    assert {"kind": "COUNTED_COST_LOWER_BOUND", "layer": "b"} in result.cf_evidence
    with pytest.raises(Invalid, match="layer \\(a\\) is not admissible"):
        supervisor(tmp_path / "a", layer="a")
    with pytest.raises(Invalid, match="not admissible"):
        spend.counted(terms(layer="a"), {"usd": "1", "completeness": "complete"}, None)


def test_the_supervisor_modules_read_no_file_but_their_own_state_checks():
    """The static half of S8's aeweval_never_opens_an_arm_owned_path (the full test, through the helpers, is S8b's):
    no module of the core reads or lists a file; the only filesystem calls are spend.private_dir's mkdir and
    require_private's lstat, under the evaluator's state root."""
    forbidden = {"open", "read_text", "read_bytes", "write_text", "write_bytes", "iterdir", "glob", "rglob", "walk",
                 "scandir", "listdir", "readlink", "stat", "exists", "is_file", "is_dir"}
    for module in ("supervisor", "spend", "responder", "helpers"):
        tree = ast.parse((ROOT / "eval" / "aew_eval" / f"{module}.py").read_text(encoding="utf-8"))
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                calls.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        assert not calls & forbidden, (module, calls & forbidden)


def test_an_abort_still_takes_the_shutdown_order_and_is_re_raised(tmp_path):
    clock, log = Clock(), Log()

    def interrupted(tick: int) -> Observation:
        raise KeyboardInterrupt

    driver = FakeDriver(clock, log, interrupted)
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, proxy=FakeProxy(log, usd=0.2), layer="c")
    with pytest.raises(KeyboardInterrupt):
        sup.run(TASK)
    result = sup.result
    assert result.end == "EVALUATOR_ABORTED" and not result.arm_failure
    assert [s["step"] for s in result.shutdown] == SHUTDOWN_STEPS
    assert ("kill",) in log and ("proxy_close",) in log


def test_an_unclassified_request_is_an_instrument_defect_never_an_arm_failure(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: Observation(requests=(Request("req_1", "unclassified"),)))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver)
    result = sup.run(TASK)
    assert result.end == "INSTRUMENT_DEFECT" and not result.arm_failure
    assert result.errors[0]["component"] == "classifier" and driver.delivered == []


def test_an_unbuildable_worker_meter_is_a_diagnostic_never_cf_evidence(tmp_path):
    clock, log = Clock(), Log()
    driver = FakeDriver(clock, log, lambda t: quiet(1, final=t >= 2))
    sup, *_ = supervisor(tmp_path, clock=clock, log=log, driver=driver, helpers=FakeHelpers(log, [[server(1)]]),
                         factory=_raise(RuntimeError("the evaluator's factory has a defect")))
    result = sup.run(TASK)
    assert [e for e in result.cf_evidence if e["kind"] != "COUNTED_COST_LOWER_BOUND"] == []
    assert any(e["at"] == "worker_meter" for e in result.errors)
    assert result.settled["completeness"] == "unknown"  # the seen server never answered: never never_launched
