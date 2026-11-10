"""Status and every wait exit expose recorded capability gaps in text, without changing progress or run outcomes."""

from __future__ import annotations

import copy

import pytest
from aewflow import create_planned_ticket, own_scope, sample_project
from fake_harness import HarnessLab

from aew.engine.api import Engine
from aew.harness import progress as P
from aew.harness import runlog
from aew.surface import readable
from aew.util import dump_yaml, load_yaml


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def person(payload):
    # The actual readable writer needs only the StageResult's payload for this section, not a model or real harness.
    return readable.render({"tool": "harness_wait", "result": payload}).split("\n\n" + readable.JSON_MARKER)[0]


def test_status_timeout_trigger_and_wait_any_keep_each_runs_recorded_capability_gaps(lab, tmp_path, monkeypatch):
    gates = lab.aew_root / "policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": 2}),
                     encoding="utf-8", newline="\n")
    lab.project.pin_policy()
    cards = lab.aew_root / "roles"
    cards.mkdir(exist_ok=True)
    (cards / "fixture_engineer.yaml").write_text(dump_yaml({
        "schema": "aew/role/v1", "role": "fixture_engineer", "display_name": "Fixture Engineer", "version": 1,
        "extends": "implementer", "purpose": "Test capability disclosure.", "skills": ["fixture-style"],
        "required_capabilities": ["source_mutation", "targeted_test_execution"]}), encoding="utf-8")
    releases, runs = [], []
    for i in range(2):
        # HarnessLab shares only `sync` for handshakes; Linux gives the worker a private /tmp elsewhere.
        started, release = tmp_path / "sync" / f"started-{i}", tmp_path / "sync" / f"release-{i}"
        run = f"R-INV-000{i + 1}-1"
        lab.script(run, [{"do": "touch", "path": str(started)},
                         {"do": "wait_file", "path": str(release), "timeout": 300}])
        wid = create_planned_ticket(lab.project, tmp_path, scope=own_scope(i), extra=("--card", "fixture_engineer"))
        assert lab.lead("work", "assign", wid, "--launch")["launch"]["run"] == run
        lab.until(started.exists, what="the real fake worker to start")
        releases.append(release)
        runs.append(run)
    engine = Engine.discover(lab.root)
    original = runlog.observed_status

    def observed(directory):
        # Supply a historical missing-tool label at the record-read boundary, independent of the host's tool install.
        # Liveness, skill delivery, workers, waits, progress handling and control state are real.
        status, record = original(directory)
        record = copy.deepcopy(record)
        assert record is not None
        record.setdefault("containment", {})["missing_tools"] = {"detail": [
            {"command": "rg", "served": "stub", "reason": "declined"}]}
        return status, record

    monkeypatch.setattr(runlog, "observed_status", observed)
    before = engine.store.current()["revision"]
    status = engine.harness_status()
    for run in runs:
        assert f"missing tool: {run}: rg" in person(status)
        assert f"missing skill: {run}: fixture-style; not_shipped" in person(status)
    timed = engine.harness_wait(runs, any_=True, timeout=0)
    assert timed["timed_out"] and set(timed["run_capabilities"]) == set(runs)
    assert "tools: 2; skills: 2; runs: 2" in person(timed)
    assert set(timed["runs"]) == set(runs), "progress digests keep their existing collection"
    single = engine.harness_wait(runs[0], timeout=0)
    assert single["timed_out"] and "tools: 1; skills: 1; runs: 1" in person(single)

    # A synthetic progress observation reaches the real trigger filter; no timing or external harness probe.
    digest = {"state": "busy", "out_of_scope": ["outside.py"], "trigger_seq": 1,
              "triggers": [{"seq": 1, "why": P.OUT_OF_SCOPE, "path": "outside.py"}]}
    with monkeypatch.context() as patch:
        patch.setattr(runlog, "read_progress", lambda directory: digest if directory.name == runs[0] else None)
        trigger = engine.harness_wait(runs, any_=True, triggers=True, timeout=0)
    assert not trigger["timed_out"] and trigger["triggers"] == digest["triggers"]
    assert trigger["runs"][runs[0]] == digest
    assert "tools: 2; skills: 2; runs: 2" in person(trigger)
    assert engine.store.current()["revision"] == before, "advisory disclosure changes no workflow state"

    releases[0].write_text("go", encoding="utf-8")
    lab.wait(runs[0])
    ended = engine.harness_wait(runs, any_=True, timeout=0)
    assert ended["run"] == runs[0] and ended["status"] == "ended_without_evidence"
    assert ended["still_running"] == [runs[1]]
    assert ended["missing_tools"] == ended["run_capabilities"][runs[0]]["missing_tools"]
    assert "tools: 2; skills: 2; runs: 2" in person(ended), "the still-running run's gaps are not lost"
    assert "AEW's pinned copy:" in person(ended)
    for run in runs:
        assert f"missing skill: {run}: fixture-style; not_shipped" in person(ended)
    releases[1].write_text("go", encoding="utf-8")
    lab.wait(runs[1])
