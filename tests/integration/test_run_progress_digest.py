"""A run's progress digest end to end (steering design §2): the real OpenCode adapter and supervisor against the fake
V2 server, whose ``write`` steps record 2.0.18's tool parts (``state.input.path``, as the steering PR 1 probe measured
them). The run's meter writes ``progress.json`` beside its usage sample, from the same poll."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from aewflow import create_planned_ticket
from fake_harness import HarnessLab, credential_hits
from harness_conformance import FakeOpenCodeDriver

from aew.engine.api import Engine
from aew.harness import contract as K
from aew.harness import progress as P
from aew.harness import runlog, wake_queue
from aew.harness.lead_broker import POLL_S, LeadBroker


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def test_a_workers_writes_reach_its_progress_digest_and_its_end_is_a_trigger(lab: HarnessLab, tmp_path: Path):
    lab.script("default", {"steps": [{"do": "write", "files": {"calc/extra.py": "X = 1\n"}},
                                     {"do": "write", "files": {"src/b/x.py": "Y = 2\n"}}],
                           "server": {"tool_parts": True, "live_usage": {}}})
    wid = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.wait(run)
    digest = runlog.read_progress(runlog.run_dir(lab.aew_root, run))
    assert digest is not None and digest["run"] == run
    assert digest["files_touched"] == {"paths": ["calc/extra.py", "src/b/x.py"], "count": 2}
    assert digest["state"] == P.ENDED and digest["steps"] >= 2
    assert [t["why"] for t in digest["triggers"]][-1] == P.RUN_ENDED


def test_a_trigger_tells_a_lead_that_is_woken_to_end_its_turn_and_not_to_wait(
        lab: HarnessLab, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The review's m10: where a broker posts wakes, a wait's trigger doesn't send the Lead back to `harness_wait`."""
    lab.script("default", {"steps": [{"do": "write", "files": {"src/b/x.py": "Y = 2\n"}}, {"do": "hang"}],
                           "server": {"tool_parts": True, "live_usage": {}}})
    wid = create_planned_ticket(lab.project, tmp_path, scope=("src/a/**",))
    launch = lab.lead("work", "assign", wid, "--launch")["launch"]
    run = launch["run"]
    monkeypatch.setattr(wake_queue, "some_broker_posts", lambda root: True)
    try:
        out = Engine.discover(lab.root).harness_wait(run, timeout=120, triggers=True)
        assert out["next_action"] == K.trigger_step([K.OUT_OF_SCOPE], run, [],
                                                    then=K.wake_step([run], after_a_start=False)), out
        assert "harness_wait" not in out["next_action"], out
    finally:
        lab.lead("invoke", "cancel", launch["invocation"], "--reason", "the test is over")
        lab.wait(run)


class _RecordingPoster:
    """A poster that takes every wake when the Lead isn't in a turn. Nothing else here is stubbed."""

    def __init__(self) -> None:
        self.posts: list[str] = []
        self.turn = False
        self.made = 0

    def new_id(self) -> str:
        self.made += 1
        return f"msg_{self.made}"

    def busy(self) -> bool:
        return self.turn

    def post(self, wake_id: str, text: str) -> str:
        self.posts.append(text)
        return "ses_this"

    def landed(self, wake_id: str) -> str:
        return wake_queue.DELIVERED

    def whys(self) -> list[list[str]]:
        return [json.loads(text.splitlines()[1])["why"] for text in self.posts]


def _until(predicate, seconds: float = 60.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not predicate():
        time.sleep(0.05)
    return bool(predicate())


def test_a_real_dispatch_under_a_real_broker_says_end_your_turn_and_the_wake_comes(lab: HarnessLab, tmp_path: Path):
    """The next step the product prints, followed: a real dispatch, worker, `live_runs` and broker thread (review, m4).
    And the Lead's own cancel is no news to wake it with (review, m6)."""
    lab.script("default", {"steps": [{"do": "write", "files": {"src/b/x.py": "Y = 2\n"}}, {"do": "hang"}],
                           "server": {"tool_parts": True, "live_usage": {}}})
    wid = create_planned_ticket(lab.project, tmp_path, scope=("src/a/**",))
    poster = _RecordingPoster()
    broker = LeadBroker(Engine.discover(lab.root), lab.project.token)
    broker.start()
    try:
        broker.start_wakes(poster)
        assigned = lab.lead("work", "assign", wid, "--launch")
        launch = assigned["launch"]
        run = launch["run"]
        assert assigned["next_action"] == K.wake_step([run])
        assert _until(poster.whys), "no wake reached the poster"
        assert poster.whys() == [[K.OUT_OF_SCOPE]]
        lab.lead("invoke", "cancel", launch["invocation"], "--reason", "the Lead stops it itself")
        lab.wait(run)
        time.sleep(3 * POLL_S)
        assert poster.whys() == [[K.OUT_OF_SCOPE]]
    finally:
        broker.close()
    assert Engine.discover(lab.root).wakes_reach_lead() is False and wake_queue.serving(lab.aew_root) is None


def test_a_real_run_ending_wakes_the_lead_unless_a_wait_already_told_it(lab: HarnessLab, tmp_path: Path):
    """Review, m6. Two runs under one broker: one whose end only a wake can tell, one a short wait returned."""
    lab.script("default", {"steps": [{"do": "write", "files": {"calc/extra.py": "X = 1\n"}}],
                           "server": {"tool_parts": True, "live_usage": {}}})
    wid = create_planned_ticket(lab.project, tmp_path)
    poster = _RecordingPoster()
    broker = LeadBroker(Engine.discover(lab.root), lab.project.token)
    broker.start()
    try:
        broker.start_wakes(poster)
        poster.turn = True  # the Lead is in its turn, taking a short wait
        run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
        out = Engine.discover(lab.root).harness_wait(run, timeout=120, triggers=True)
        assert out["why"] == [K.RUN_ENDED], out
        time.sleep(3 * POLL_S)  # a wake gathered during the wait is waiting for the turn's end
        poster.turn = False
        time.sleep(3 * POLL_S)
        assert poster.posts == []
    finally:
        broker.close()


def test_the_lead_catches_a_drift_and_steers_it(lab: HarnessLab, tmp_path: Path):
    """The steering design's §8 acceptance case, steps 1 and 2 (steering PR 1): a worker on a Ticket scoped to
    ``src/a/`` writes ``src/b/x.py``, and the Lead's wait (the typed tool's, with triggers) returns while the run still
    works, with ``why: [out_of_scope]`` and a digest that names the file, as changed now and outside the scope. Steps 3
    to 6 (the steer, its delivery, the revert, the end inside scope) need the push wake: steering PR 2."""
    lab.script("default", {"steps": [{"do": "write", "files": {"src/b/x.py": "Y = 2\n"}}, {"do": "hang"}],
                           "server": {"tool_parts": True, "live_usage": {}}})
    wid = create_planned_ticket(lab.project, tmp_path, scope=("src/a/**",))
    launch = lab.lead("work", "assign", wid, "--launch")["launch"]
    run = launch["run"]
    try:
        out = Engine.discover(lab.root).harness_wait(run, timeout=120, triggers=True)
        assert out["run"] == run and out["status"] == "running" and not out["timed_out"], out
        assert out["why"] == [K.OUT_OF_SCOPE] and [t["path"] for t in out["triggers"]] == ["src/b/x.py"], out
        digest = out["runs"][run]
        assert digest["out_of_scope"] == ["src/b/x.py"], digest
        assert digest["changed_now"] == {"paths": ["src/b/x.py"], "count": 1}, digest
        assert out["next_action"] == K.trigger_step([K.OUT_OF_SCOPE], run, []), out
    finally:
        lab.lead("invoke", "cancel", launch["invocation"], "--reason", "the drift test is over")
        lab.wait(run)
