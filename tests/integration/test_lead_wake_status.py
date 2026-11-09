"""`aew status` shows the Lead's wakes (steering design r4 §1): a wake that never lands is visible to the operator."""

from __future__ import annotations

import json
import sys
import threading
import time

from aew.harness import contract as K
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

    monkeypatch.setattr(sys, "platform", "linux")  # the fallback's line is the same read everywhere wakes are posted
    assert _next_after_launch(project) == K.no_broker_step(["run-1"])  # on by default, and no broker posts
    assert "no broker is posting wakes here" in _next_after_launch(project)
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_OFF)
    assert _next_after_launch(project).startswith("wait on run-1 with `harness_wait`")  # off: no fallback to explain
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_ON)
    from aew.engine.api import Engine

    generation = int(Engine.discover(project.root).store.current()["lead"]["generation"])
    Q.mark_serving(project.root / ".aew", generation)
    monkeypatch.setattr(broker_liveness, "read", lambda root: {"generation": generation})
    monkeypatch.setattr(broker_liveness, "judge", lambda record, **kw: None)
    assert _next_after_launch(project).startswith("end your turn: AEW wakes you when run-1")
    text = "\n".join(Q.render({"broker_posting": True}))
    assert "the broker posts them" in text and "`lead.push_wake: off`" in text  # the off switch, where it's looked for
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_OFF)
    assert _next_after_launch(project).startswith("wait on run-1")  # a broker posts, and the switch says off
    monkeypatch.setattr(X, "push_wake", lambda policy: X.PUSH_WAKE_ON)
    assert Q.status(project.root / ".aew", generation=generation) is None  # no wake was ever recorded
    monkeypatch.setattr(broker_liveness, "judge", lambda record, **kw: object())  # crashed, stale or closed
    assert _next_after_launch(project) == K.no_broker_step(["run-1"])


def _engine_of(project):
    from aew.engine.api import Engine

    return Engine.discover(project.root)


def test_a_project_that_names_no_lead_key_has_wakes_on_after_an_upgrade(project, monkeypatch):
    """The migration (steering PR 3): `aew init` never wrote the key, so this is every existing project. Its digests
    are the goldens' (test_coordination_store), and its Lead is told of wakes and gets a poster."""
    from aew.harness.opencode import lead as L
    from aew.harness.opencode import projection as P
    from aew.policy import execution as X

    monkeypatch.setattr(sys, "platform", "linux")
    engine = _engine_of(project)
    policy = engine.execution_policy()[0]
    assert "lead" not in (policy or {})
    assert X.push_wake(policy) == X.PUSH_WAKE_ON and L.pushes_wakes(engine) is True
    assert L.lead_poster(policy, "password", unix="socket") is not None
    assert Q.HEADER in P.lead_config(push_wake=L.pushes_wakes(engine))["agents"][P.LEAD_AGENT]["system"]


def test_a_project_with_a_typed_off_stays_off_and_keeps_the_wait(project, monkeypatch):
    from aew.harness.opencode import lead as L
    from aew.harness.opencode import projection as P
    from aew.policy import execution as X

    monkeypatch.setattr(sys, "platform", "linux")
    path = project.root / ".aew" / X.REL_PATH
    path.write_bytes(path.read_bytes().rstrip(b"\n") + b"\nlead:\n  push_wake: off\n")
    project.adopt_policy()
    engine = _engine_of(project)
    policy = engine.execution_policy()[0]
    assert X.push_wake(policy) == X.PUSH_WAKE_OFF and L.pushes_wakes(engine) is False
    assert L.lead_poster(policy, "password", unix="socket") is None
    assert engine._harness._wait_on(["run-1"]) == K.wait_step(["run-1"])
    system = P.lead_config(push_wake=L.pushes_wakes(engine))["agents"][P.LEAD_AGENT]["system"]
    assert Q.HEADER not in system and "do not end your turn" in system


def test_a_mark_from_another_generations_broker_says_nothing_of_this_one(project, monkeypatch):
    """A crash leaves its mark, and the record is the next broker's, which judge passes as another generation's."""
    from aew.harness import broker_liveness

    root = project.root / ".aew"
    Q.mark_serving(root, 3)
    monkeypatch.setattr(broker_liveness, "read", lambda r: {"generation": 4})
    monkeypatch.setattr(broker_liveness, "judge", lambda record, **kw: None)
    assert Q.some_broker_posts(root) is False


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


class _QuietPoster(_Poster):
    """A poster that takes every wake: nothing is ever busy, and each call says it was asked."""

    def busy(self) -> bool:
        self.asked.set()
        return False

    def landed(self, wake_id: str) -> str:
        return Q.WAITING

    def post(self, wake_id: str, text: str) -> str:
        return "ses_1"


def test_a_switch_turned_off_mid_session_stops_the_posts_and_on_again_resumes_them(project, monkeypatch):
    """Read each pass (the review's note for PR 3): the mark goes, so `aew status` and the Lead's next step agree."""
    from aew.harness.lead_broker import LeadBroker
    from aew.policy import execution as X

    root = project.root / ".aew"
    engine = _engine_of(project)
    broker = LeadBroker(engine, project.token)
    state = {"switch": X.PUSH_WAKE_ON}
    monkeypatch.setattr(X, "push_wake", lambda policy: state["switch"])
    broker.start()
    try:
        broker.start_wakes(_QuietPoster())

        def until(predicate) -> None:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and not predicate():
                time.sleep(0.05)
            assert predicate()

        assert Q.serving(root) == broker.generation
        state["switch"] = X.PUSH_WAKE_OFF
        until(lambda: Q.serving(root) is None)
        state["switch"] = X.PUSH_WAKE_ON
        until(lambda: Q.serving(root) == broker.generation)
    finally:
        broker.close()


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
