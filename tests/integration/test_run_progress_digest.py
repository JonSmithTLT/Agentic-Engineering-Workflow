"""A run's progress digest end to end (steering design §2): the real OpenCode adapter and supervisor against the fake
V2 server, whose ``write`` steps record 2.0.18's tool parts (``state.input.path``, as the steering PR 1 probe measured
them). The run's meter writes ``progress.json`` beside its usage sample, from the same poll."""

from __future__ import annotations

from pathlib import Path

import pytest
from aewflow import create_planned_ticket
from fake_harness import HarnessLab, credential_hits
from harness_conformance import FakeOpenCodeDriver

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
