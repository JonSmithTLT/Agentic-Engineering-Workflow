"""The scripted Lead's steering-on policy (register E375; vertical-uat.md §2 and §3, "Steering on").

With steering on, a wait the projection marks ``woken`` ends the Lead's turn until a wake or the operator arrives (the
operator's answer to the V-01 burn-down's Q1), and a BLOCKED loop stop is a decline only when its blocker is still
present after the run ends (its Q10). The loop's own selection (``steering_loop.select``) and stop codes decide what a
stop means; the projections here are the shapes it reads."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import fake_opencode
import pytest
from vertical import lead as L
from vertical.lead import Lead, WakeChannel
from vertical.ledger import Ledger

from aew.harness import contract as K
from aew.harness import steering_loop as LOOP
from aew.harness.opencode.lead_wake import LeadPoster

T, REV = "T-0001", 9
WAIT_ACTION = {"action": "harness_wait", "kind": "wait", "availability": "AVAILABLE", "callable": True,
               "arguments": {"runs": ["R-INV-0001-1"]}, "woken": True}
PUSH = {"action": "ticket_request_review", "kind": "stage", "availability": "AVAILABLE", "callable": True,
        "auto_runnable": True, "arguments": {"work_id": T, "expect_rev": REV}}
GATE = {"code": "GATE_UNSATISFIED", "message": "RUNNING -> REVIEW_PENDING: gates not satisfied"}
STOP = {"code": LOOP.BLOCKED, "message": f"{T}: GATE_UNSATISFIED: ...", "subject": T, "revision": REV,
        "at": "2026-11-26T18:34:06Z", "condition": "c1"}


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(L, "POLL_S", 0.001)


class _Wakes:
    """The wake channel, answered by the test: each look returns the next list of wake ids."""

    def __init__(self, looks: list[list[str]]) -> None:
        self.looks = looks

    def news(self) -> list[str]:
        return self.looks.pop(0) if self.looks else []


class _Lead(Lead):
    """The Lead with its typed surface answered by the test: ``status`` of the project and of the Ticket come from
    ``reads`` (each called with the number of reads so far), and every other call is recorded."""

    def __init__(self, tmp: Path, *, steering: bool = True, project: Any = None, unit: Any = None) -> None:
        super().__init__({"events": str(tmp / "events.jsonl"), "chat": str(tmp / "chat"), "steering": steering})
        self.subject, self.step, self.tools = T, f"{T}:RUNNING", []
        self.project, self.unit = project, unit
        self.calls: list[tuple[str, dict[str, Any], bool]] = []
        self.reads = 0

    def call(self, tool: str, arguments: dict[str, Any], *, offered: bool = False, mechanical: bool = False,
             why: str = "") -> dict[str, Any]:
        if tool == "status":
            self.reads += 1
            return (self.unit if arguments.get("work_id") else self.project)(self.reads)
        self.calls.append((tool, arguments, mechanical))
        self.event("call", via="mcp", tool=tool, arguments=arguments, offered=offered, mechanical=mechanical,
                   ok=True)
        return {"ok": True}

    def events(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines()]

    def kinds(self) -> list[str]:
        return [e["kind"] for e in self.events()]


def _ticket(*actions: dict[str, Any], blockers: list[dict[str, Any]] | None = None,
            run: str = K.ENDED_WITH_EVIDENCE) -> dict[str, Any]:
    """The Ticket's projection, with its run in status ``run`` (the projection's ``runs``, which say whether a run is
    live; the wait it offers for a live run is listed or not by the test)."""
    return {"revision": REV, "subject": T, "state": "RUNNING", "actions": list(actions), "blockers": blockers or [],
            "decisions_required": [], "anomalies": [], "hints": [],
            "runs": [{"run": "R-INV-0001-1", "work_unit": T, "role": "implementer", "status": run}]}


def _project(stop: dict[str, Any] | None, revision: int = REV) -> dict[str, Any]:
    loop = {"status": "stopped", "stop": stop} if stop else {"status": "running"}
    return {"projection": {"revision": revision, "subject": "project", "actions": [], "blockers": [],
                           "decisions_required": [], "anomalies": []},
            "result": {"steering": {"loop": loop}}}


def _ledger(lead: _Lead) -> Ledger:
    ledger = Ledger("unit", steering=True)
    for event in lead.events():
        ledger.lead_event(event)
    return ledger


# ---------------------------------------------------------------------------------------------- the woken wait (Q1)


def test_with_steering_on_the_scripted_lead_waits_out_a_woken_wait_instead_of_calling_harness_wait(
        tmp_path: Path) -> None:
    ticket = _ticket(WAIT_ACTION, run=K.RUNNING)
    lead = _Lead(tmp_path, unit=lambda n: {"projection": ticket, "result": {}})
    lead.wakes = _Wakes([[], [], ["msg_wake"]])  # type: ignore[assignment]  # the wake lands on the third look
    assert lead.tick()
    assert lead.calls == []  # harness_wait was never called
    assert lead.kinds()[-2:] == ["turn_ended", "woken"]
    assert lead.events()[-1]["wakes"] == ["msg_wake"]
    assert _ledger(lead).counts()["mechanical_calls"] == 0


def test_an_operator_line_ends_the_woken_wait_too(tmp_path: Path) -> None:
    ticket = _ticket(WAIT_ACTION, run=K.RUNNING)
    lead = _Lead(tmp_path, unit=lambda n: {"projection": ticket, "result": {}})
    lead.wakes = _Wakes([])  # type: ignore[assignment]
    lead.inbox.put({"text": "Where do things stand?"})
    assert lead.tick()
    assert lead.calls == []
    assert lead.events()[-1] == {**lead.events()[-1], "kind": "heard", "text": "Where do things stand?"}


def test_a_woken_wait_with_no_wake_in_its_bound_is_called_and_counted(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing wake is recorded, and the wait is called as before: the counter shows it."""
    monkeypatch.setattr(L, "WAKE_WAIT_S", 0.05)
    ticket = _ticket(WAIT_ACTION, run=K.RUNNING)
    lead = _Lead(tmp_path, unit=lambda n: {"projection": ticket, "result": {}})
    lead.wakes = _Wakes([])  # type: ignore[assignment]
    assert lead.tick()
    assert [c[0] for c in lead.calls] == ["harness_wait"]
    assert "wake_missed" in lead.kinds()
    assert _ledger(lead).counts()["mechanical_calls"] == 1


def test_a_wake_channel_that_keeps_failing_is_recorded_once_per_new_error(tmp_path: Path) -> None:
    """A server that does not answer is looked at again every poll; each error is recorded when it changes, not on
    every look."""
    errors = [OSError("refused")] * 5 + [ValueError("bad json")] * 3 + [OSError("refused")]

    class Failing:
        def news(self) -> list[str]:
            if errors:
                raise errors.pop(0)
            return ["msg_wake"]

    lead = _Lead(tmp_path, unit=lambda n: {"projection": _ticket(WAIT_ACTION, run=K.RUNNING), "result": {}})
    lead.wakes = Failing()  # type: ignore[assignment]
    assert lead.tick()
    assert [e["error"] for e in lead.events() if e["kind"] == "wake_read_error"] == [
        "OSError: refused", "ValueError: bad json", "OSError: refused"]
    assert lead.kinds()[-1] == "woken"


@pytest.mark.parametrize("steering", [False, True], ids=["steering-off", "no-wake-channel"])
def test_without_steering_or_a_wake_channel_the_woken_wait_is_called(tmp_path: Path, steering: bool) -> None:
    ticket = _ticket(WAIT_ACTION, run=K.RUNNING)
    lead = _Lead(tmp_path, steering=steering, unit=lambda n: {"projection": ticket, "result": {}})
    assert lead.wakes is None
    assert lead.tick()
    assert [(c[0], c[2]) for c in lead.calls] == [("harness_wait", True)]


def test_the_brokers_poster_finds_the_tuis_session_and_its_wake_reaches_the_lead(tmp_path: Path) -> None:
    """The fake TUI's wake channel end to end: the TUI opens its session on the Lead's (fake) server, AEW's own poster
    picks that session and posts a wake there as it posts every wake, and the channel hears it once."""
    app = fake_opencode.local_app(tmp_path)
    app.knobs.pop("live_usage", None)  # the server as the Lead's is started: the session's times are its own
    server = ThreadingHTTPServer(("127.0.0.1", 0), fake_opencode.handler_for(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        channel = WakeChannel(f"http://127.0.0.1:{server.server_address[1]}", app.password)
        launched = fake_opencode.now_ms() - 1  # as the vertical's poster: sessions touched since the Lead launched
        session = channel.open()

        class Client:  # the poster's client, on the same routes
            def get(self, path: str) -> Any:
                return app.route("GET", path, {}, None)[1]

            def post(self, path: str, body: Any) -> Any:
                return app.route("POST", path, {}, body)[1]

        poster = LeadPoster(lambda: Client(), since_ms=launched)  # type: ignore[arg-type,return-value]
        assert poster.session() == session
        assert channel.news() == []
        poster.post("msg_wake1", "AEW wake: run R-INV-0001-1 ended")
        assert channel.news() == ["msg_wake1"]
        assert channel.news() == []  # heard once
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------------------------- the BLOCKED stop (Q10)


def test_a_blocked_stop_whose_blocker_clears_by_the_runs_end_is_not_a_decline(tmp_path: Path) -> None:
    """The run is live, then it ends and the gate's blocker goes with it, then the loop acts. The Lead never takes the
    stop as a decline and pushes nothing."""
    phases = [_ticket(PUSH, WAIT_ACTION, blockers=[GATE], run=K.RUNNING)] * 3 + [_ticket(PUSH)] * 3

    def project(n: int) -> dict[str, Any]:
        return _project(STOP, revision=REV if n < 12 else REV + 1)  # the loop acts at last

    lead = _Lead(tmp_path, project=project,
                 unit=lambda n: {"projection": phases[min(len(phases) - 1, lead.reads // 2)]})
    assert lead.loop_acts({"revision": REV})
    assert "loop_declined" not in lead.kinds()
    readings = [e["now"] for e in lead.events() if e["kind"] == "loop_blocked"]
    assert readings[0] == {"code": LOOP.BLOCKED, "message": f"{T}: GATE_UNSATISFIED: {GATE['message']}",
                           "run_live": True, "stands": False}
    assert readings[-1] == {"action": PUSH["action"], "stands": False}
    assert lead.calls == []


def test_the_leads_push_after_a_self_clearing_blocked_stop_is_a_counted_mechanical_call(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Driven through the Lead's own turn: the blocker clears when the run ends, the loop has not acted within the
    Lead's bound, and the Lead pushes the step itself. The stop was no decline, so the push is a mechanical call."""
    monkeypatch.setattr(L, "LOOP_WAIT_S", 0.05)
    phases = [_ticket(PUSH, WAIT_ACTION, blockers=[GATE], run=K.RUNNING)] * 3 + [_ticket(PUSH)]
    lead = _Lead(tmp_path, project=lambda n: _project(STOP),
                 unit=lambda n: {"projection": phases[min(len(phases) - 1, n // 2)], "result": {}})
    assert lead.tick()
    declined = [e for e in lead.events() if e["kind"] == "loop_declined"]
    assert len(declined) == 1 and declined[0]["stop"] is None and not declined[0]["now"]["stands"]
    assert [(c[0], c[2]) for c in lead.calls] == [(PUSH["action"], True)]
    assert _ledger(lead).counts()["mechanical_calls"] == 1


def test_a_live_run_keeps_a_blocked_stop_from_being_a_decline_even_with_no_wait_offered(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Whether a run is live is the projection's ``runs`` with the contract's ``LIVE_RUNS``, not the wait it offers: a
    profile that cannot call ``harness_wait`` still has a live run, and its blocker can still clear when it ends."""
    monkeypatch.setattr(LOOP, "COARSE_S", 0.0)
    monkeypatch.setattr(L, "LOOP_WAIT_S", 0.05)
    lead = _Lead(tmp_path, project=lambda n: _project(STOP),
                 unit=lambda n: {"projection": _ticket(PUSH, blockers=[GATE], run=K.STARTING)})
    assert not lead.loop_acts({"revision": REV})
    declined = [e for e in lead.events() if e["kind"] == "loop_declined"]
    assert len(declined) == 1 and declined[0]["stop"] is None  # only the Lead's own bound ended the wait
    assert declined[0]["now"]["run_live"] and not declined[0]["now"]["stands"]


def test_a_blocked_stop_whose_blocker_is_still_present_after_the_run_ends_is_a_decline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No live run, the blocker stands through one of the loop's own looks: the loop declined, and the Lead pushes."""
    monkeypatch.setattr(LOOP, "COARSE_S", 0.02)
    lead = _Lead(tmp_path, project=lambda n: _project(STOP),
                 unit=lambda n: {"projection": _ticket(PUSH, blockers=[GATE])})
    assert not lead.loop_acts({"revision": REV})
    declined = [e for e in lead.events() if e["kind"] == "loop_declined"]
    assert len(declined) == 1 and declined[0]["stop"] == STOP and declined[0]["now"]["stands"]


def test_a_blocked_stop_is_not_a_decline_before_the_loop_has_looked_again(tmp_path: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """The blocker read once with no live run is not yet a decline: the loop re-projects within its own look."""
    monkeypatch.setattr(L, "LOOP_WAIT_S", 0.05)
    lead = _Lead(tmp_path, project=lambda n: _project(STOP),
                 unit=lambda n: {"projection": _ticket(PUSH, blockers=[GATE])})
    assert not lead.loop_acts({"revision": REV})
    declined = [e for e in lead.events() if e["kind"] == "loop_declined"]
    assert len(declined) == 1 and declined[0]["stop"] is None  # only the Lead's own bound ended the wait


@pytest.mark.parametrize("code", [LOOP.DECISION_REQUIRED, LOOP.UNKNOWN, LOOP.CONFIRMATION_UNAVAILABLE])
def test_any_other_loop_stop_is_a_decline_at_once(tmp_path: Path, code: str) -> None:
    lead = _Lead(tmp_path, project=lambda n: _project({**STOP, "code": code}),
                 unit=lambda n: {"projection": _ticket(PUSH)})
    assert not lead.loop_acts({"revision": REV})
    assert lead.kinds() == ["loop_declined"]


# ---------------------------------------------------------------------------------------------- judgment inputs (E388)


def test_the_scripted_lead_fills_a_decisions_judgment_inputs_choosing_an_option_and_writing_the_rationale(
        tmp_path: Path) -> None:
    """Register E388 (spec v2): a decision of the Lead's that names judgment inputs is called with the projection's
    arguments, the first offered option for its choice and a rationale in the Lead's own words, never a schema."""
    decision = {"decision": "RESOLVE_STAGE", "subject": T, "owner": "lead", "evidence": ["SI-0002"],
                "tool": "resolve", "arguments": {"subject": "SI-0002"},
                "availability": "AVAILABLE", "default": "NONE", "cli_fallback": None,
                "judgment_inputs": {"choice": {"options": ["continue", "abandon"]},
                                    "rationale": {"type": "string", "description": "free text"}}}
    lead = _Lead(tmp_path)
    lead.tools = ["resolve"]
    assert lead.own_decision(decision)
    [(tool, arguments, _)] = lead.calls
    assert tool == "resolve" and arguments["choice"] == "continue" and arguments["subject"] == "SI-0002"
    assert isinstance(arguments["rationale"], str) and arguments["rationale"].strip()
    assert [e["inputs"] for e in lead.events() if e["kind"] == "judgment"] == [["choice", "rationale"]]
