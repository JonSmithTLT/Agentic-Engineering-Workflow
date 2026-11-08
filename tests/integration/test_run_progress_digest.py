"""A run's progress digest end to end (steering design §2): the real OpenCode adapter and supervisor against the fake
V2 server, whose ``write`` steps record 2.0.18's tool parts (``state.input.path``, as the steering PR 1 probe measured
them). The run's meter writes ``progress.json`` beside its usage sample, from the same poll."""

from __future__ import annotations

from pathlib import Path

import pytest
from aewflow import create_planned_ticket
from fake_harness import HarnessLab, credential_hits
from harness_conformance import FakeOpenCodeDriver

from aew.engine.api import Engine
from aew.harness import contract as K
from aew.harness import progress as P
from aew.harness import runlog


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
