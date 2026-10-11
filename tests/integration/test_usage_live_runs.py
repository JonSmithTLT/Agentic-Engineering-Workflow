"""A supervised OpenCode run, end to end, leaves its live usage beside its record (F25 for M4-H, slice L2): the real
supervisor, adapter and meter against the fake V2 server, whose model steps add to their session's totals."""

from __future__ import annotations

import pytest
from aewflow import create_planned_ticket
from fake_harness import credential_hits
from harness_conformance import IMPLEMENT, FakeOpenCodeDriver

from aew import schemas
from aew.harness import runlog

RUN = "R-INV-0001-1"


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def test_a_finished_run_leaves_a_final_sample_that_matches_its_record(lab, tmp_path):
    lab.script(RUN, {"steps": IMPLEMENT, "server": {"live_usage": {}}})
    wid = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    assert lab.wait(run)["status"] == "ended_with_evidence"
    record = lab.record(run)
    sample = runlog.read_live(runlog.run_dir(lab.aew_root, run))
    assert sample is not None
    schemas.validate("usage-live", sample, source="live sample")
    assert (sample["state"], sample["prompt_state"]) == ("final", "posted")
    assert sample["source"] == {"kind": "run", "id": run}
    usage = record["result"]["usage_record"]
    # A run without foreign sessions: the final sample and the run record are the same usage (plan v4 L1/L2).
    assert usage["foreign_sessions"] == 0 and sample["sessions"] == 1
    assert sample["tokens"] == usage["tokens"] and sample["steps"] == usage["steps"] > 0
    assert sample["token_semantics"] == usage["token_semantics"]
