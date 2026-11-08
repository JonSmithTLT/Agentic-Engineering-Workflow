"""`aew status` shows the Lead's wakes (steering design r4 §1): a wake that never lands is visible to the operator."""

from __future__ import annotations

import json
import threading
import time

from aew.harness import wake_queue as Q


def test_status_shows_an_outstanding_wake_and_says_nothing_before_any(project):
    assert "lead_wakes" not in project.aew("status", "--json").json
    assert "Lead wakes" not in project.aew("status").stdout
    path = project.root / ".aew" / Q.WAKES_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": Q.SCHEMA, "marks": {"run-1": {}},
                                "wake": {"id": "wake-1", "phase": Q.PENDING, "why": ["out_of_scope"]}}),
                    encoding="utf-8", newline="\n")
    report = project.aew("status", "--json").json
    assert report["lead_wakes"]["outstanding"] == {"id": "wake-1", "phase": Q.PENDING, "why": ["out_of_scope"]}
    text = project.aew("status").stdout
    assert "Lead wakes: watching run-1; none posted yet; no broker is posting them" in text
    assert "! outstanding wake wake-1: pending (out_of_scope)" in text


def _next_after_launch(project) -> str:
    from aew.engine.api import Engine

    engine = Engine.discover(project.root)
    return engine._harness._wait_on(["run-1"])


def test_a_lead_is_told_to_end_its_turn_only_while_a_wake_would_reach_it(project, monkeypatch):
    """The fallback (steering design r4 §1): the switch off, or no broker posting, and the Lead waits with
    `harness_wait`. A crashed broker's mark doesn't count: its liveness record says it is gone."""
    from aew.harness import broker_liveness
    from aew.policy import execution as X

    assert _next_after_launch(project).startswith("wait on run-1 with `harness_wait`")  # off by default
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_ON)
    assert _next_after_launch(project).startswith("wait on run-1")  # on, and no broker posts
    from aew.engine.api import Engine

    generation = int(Engine.discover(project.root).store.current()["lead"]["generation"])
    Q.mark_serving(project.root / ".aew", generation)
    monkeypatch.setattr(broker_liveness, "read", lambda root: {"generation": generation})
    monkeypatch.setattr(broker_liveness, "judge", lambda record, **kw: None)
    assert _next_after_launch(project).startswith("end your turn: AEW wakes you when run-1")
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_OFF)
    assert _next_after_launch(project).startswith("wait on run-1")  # a broker posts, and the switch says off
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_ON)
    assert Q.status(project.root / ".aew", generation=generation) is None  # no wake was ever recorded
    monkeypatch.setattr(broker_liveness, "judge", lambda record, **kw: object())  # crashed, stale or closed
    assert _next_after_launch(project).startswith("wait on run-1")


class _Poster:
    """A poster whose server keeps failing: the session goes on, and the status line says so."""

    def __init__(self) -> None:
        self.asked = threading.Event()

    def new_id(self) -> str:
        return "msg_1"

    def busy(self) -> bool:
        return True

    def post(self, wake_id: str, text: str) -> str:
        raise AssertionError("nothing to post")

    def landed(self, wake_id: str) -> str:
        self.asked.set()
        raise OSError("the server hiccuped")


def test_the_brokers_wake_thread_survives_a_failing_pass_and_clears_its_mark_on_close(project):
    from aew.engine.api import Engine
    from aew.harness.lead_broker import LeadBroker

    root = project.root / ".aew"
    path = root / Q.WAKES_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": Q.SCHEMA, "wake": {"id": "msg_1", "phase": Q.POSTED, "why": ["quiet"],
                                                             "runs": {}}}), encoding="utf-8", newline="\n")
    engine = Engine.discover(project.root)
    broker = LeadBroker(engine, project.token)
    poster = _Poster()
    broker.start()
    try:
        broker.start_wakes(poster)
        assert Q.serving(root) == broker.generation
        assert poster.asked.wait(30)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not (Q.status(root) or {}).get("last_failure"):
            time.sleep(0.1)
        assert Q.status(root)["last_failure"]["why"] == "OSError: the server hiccuped"
        assert broker._wakes.is_alive()
    finally:
        broker.close()
    assert Q.serving(root) is None and not broker._wakes.is_alive()


def test_a_real_takeover_ends_the_old_brokers_wake_thread_and_its_close_leaves_the_new_mark(project, monkeypatch):
    """The seat is taken through the engine, as `aew lead takeover` takes it. A superseded session must spend no more
    turns, and its exit must not tell the new Lead that no broker posts."""
    from notifier import takeover

    from aew.engine.api import Engine
    from aew.harness.lead_broker import POLL_S, LeadBroker

    root = project.root / ".aew"
    poster = _Poster()
    broker = LeadBroker(Engine.discover(project.root), project.token)
    broker.start()
    try:
        broker.start_wakes(poster)
        generation = broker.generation
        takeover(project, monkeypatch)
        broker._wakes.join(POLL_S * 20)
        assert not broker._wakes.is_alive(), "still posting into a session that lost the seat"
        Q.mark_serving(root, generation + 1)  # the new session's broker
    finally:
        broker.close()
    assert Q.serving(root) == generation + 1
