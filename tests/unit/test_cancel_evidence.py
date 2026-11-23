"""Recorded cancel annotations and the ordinary artifact reader agree about lost versus failed work."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from test_ci_tools import ROOT, _load

CANCEL = _load("cancel_evidence")
SCORE = _load("evidence_scorecard")
OLD = {"id": 43745782428, "run_attempt": 1, "event": "pull_request", "workflow_id": 367481474,
       "head_branch": "feature", "head_sha": "b4bd4ca5502124c2448a07575856c24a86e0ab0c",
       "created_at": "2026-11-15T18:16:07Z", "pull_requests": [], "head_repository": {"id": 1}}
NEW = {**OLD, "id": 43752657105, "head_sha": "f558023460af4ede3c0c2309e47da40fe49fcc88",
       "created_at": "2026-11-15T19:29:00Z"}
NOTES = [{"path": ".github", "message": "The operation was canceled."},
         {"path": ".github", "message": "Canceling since a higher priority waiting request for ci-480 exists"}]


def test_recorded_annotations_supersede_the_generic_cancel_and_require_a_unique_replacement():
    job = {"id": 132913805115}
    assert CANCEL.classify(OLD, job, NOTES, [OLD, NEW]) == {
        "kind": "superseded", "run": NEW["id"], "head_sha": NEW["head_sha"], "event": "pull_request"}
    for candidates in ([], [NEW, {**NEW, "id": 3}], [{**NEW, "head_repository": {"id": 2}}],
                       [{**NEW, "pull_requests": [{"number": 910}]}]):
        assert CANCEL.classify(OLD, job, NOTES, candidates)["kind"] == "unresolved"
    assert CANCEL.classify({**OLD, "actor": {"login": "starter"}}, job, NOTES[:1]) == {
        "kind": "manual-or-api", "message": CANCEL.MANUAL}
    assert CANCEL.classify(OLD, {**job, "cancelled_by": {"login": "controller"}}, NOTES[:1])["actor"] == "controller"
    assert CANCEL.classify(OLD, job, [], [NEW])["kind"] == "unresolved"


def test_queued_cancel_does_not_mask_a_real_failure_in_a_partial_report(tmp_path, monkeypatch):
    check = _load("check_evidence_run")
    name = "integration 2/8 (ubuntu-latest)"
    reason = CANCEL.classify(OLD, {"id": 1}, NOTES, [NEW])
    job = {"name": name, "id": 1, "conclusion": "cancelled", "steps": [], "cancel_reason": reason}
    rows = []
    assert check.check_jobs(tmp_path, [job], score_rows=rows) == []
    assert rows[0]["kind"] == "superseded-before-start"
    assert rows[0]["A1"] == rows[0]["A2"] == "n/a"

    stage = _load("stage_evidence")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "runner-resources-job.txt").write_text(json.dumps({"job_label": name}))
    node = "tests/unit/test_case.py::test_case"
    failure = {"phase": "call", "longrepr": "E   ValueError: retained cause",
               "crash": "test_case.py:5: ValueError: retained cause"}
    doc = {"schema": "aew/lane-report/v1", "complete": False, "exitstatus": None,
           "results": {node: {"outcome": "failed", "failures": [failure]}}}
    (raw / "report.json").write_text(json.dumps(doc))
    out = tmp_path / "downloaded"
    out.mkdir()
    names = out / "evidence-selected-attempt-1-running"
    names.mkdir()
    (names / "job-label-sha256.txt").write_text(hashlib.sha256(name.encode()).hexdigest())
    (names / "inventory.txt").write_text("typed source names\nfinding inventory.txt (publisher)\n"
                                        "finding job-label-sha256.txt (evidence_inputs)\n")
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    stage.stage(raw, out / "evidence-selected-attempt-1")
    stage.stage(raw, out / "lane-report-evidence-selected-attempt-1", reports_only=True)
    rows = []
    defects = check.check_jobs(out, [job], score_rows=rows)
    assert rows[0]["kind"] == "test_failure" and rows[0]["failed_nodes"] == [node] and rows[0]["A1"] == "yes"
    assert rows[0]["A2"] == "no" and any("[death-record]" in d for d in defects)
    rows[0].update(run=OLD["id"], artifacts=[2], missing=["death-record"])
    summary = SCORE.format_rows("test/repo", rows)
    assert "test_failure (superseded by run 43752657105)" in summary and "death-record" in summary
    assert any("[cancel-reason]" in d for d in check.check_jobs(out, [{**job, "cancel_reason": None}]))


def test_archive_reader_confines_artifact_data_and_accounts_for_the_expanded_size(tmp_path):
    def archive(name):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(name, b"a" * 150)
        return stream.getvalue()

    for invalid in ("../outside", "/outside", "X:/outside", "a\\outside"):
        with pytest.raises(ValueError, match="member path"):
            SCORE.read_bundle(archive(invalid), tmp_path, 200)
    with pytest.raises(ValueError, match="read budget"):
        SCORE.read_bundle(archive("report.json"), tmp_path, 99)
    assert SCORE.read_bundle(archive("case/report.json"), tmp_path, 150) == 150
    assert (tmp_path / "case/report.json").stat().st_size == 150


def test_completed_run_recorder_uses_only_default_branch_code_and_read_only_artifacts():
    flow = yaml.safe_load((ROOT / ".github/workflows/evidence-cancel-record.yml").read_text())
    assert flow[True] == {"workflow_run": {"workflows": ["ci", "evidence-proof"], "types": ["completed"]}}
    job = flow["jobs"]["record"]
    assert job["permissions"] == {"contents": "read", "checks": "write", "actions": "read"}
    checkout = job["steps"][0]["with"]
    assert checkout["ref"] == "${{ github.sha }}" and checkout["persist-credentials"] is False
    assert "github.event.workflow_run.head_sha" not in str(job)
    assert all("workflow_run" not in step.get("run", "") for step in job["steps"])


def test_trusted_recorder_index_preserves_the_subject_run_and_only_declared_test_failure(tmp_path, monkeypatch):
    record = _load("record_cancel_evidence")
    import flake_register as flake

    case = "tests/unit/test_x.py::test_known"
    register = tmp_path / "register.yml"
    monkeypatch.setattr(record, "REGISTER_PATH", register)
    register.write_text(yaml.safe_dump({"entries": [
        {"id": "known", "scope": "test", "status": "open", "lane": "integration", "platforms": ["linux"],
         "test": case}]}))
    row = {"kind": "test_failure", "started_at": "2026-11-15T19:12:36Z", "job": 132913805115,
           "name": "integration 2/8 (ubuntu-latest)", "failed_nodes": [case + "[one]", "some/unregistered/node"]}
    record.record_test_sightings(tmp_path, OLD, [row, {**row, "kind": "superseded-before-start"}])
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.write(tmp_path / flake.INDEX_MEMBER, flake.INDEX_MEMBER)
    [found] = flake.index_sightings(stream.getvalue(), 99, recorder=True)
    assert found == ("known", {"run": OLD["id"], "job": row["job"], "at": row["started_at"],
                               "observation": "failed before cancellation"})
    with pytest.raises(flake.InvalidRegister):
        list(flake.index_sightings(stream.getvalue(), 99))


def test_queued_jobs_can_inherit_only_a_confirmed_whole_run_replacement(monkeypatch):
    superseded = CANCEL.classify(OLD, {}, NOTES, [NEW])
    jobs = [{"id": n, "conclusion": "cancelled"} for n in range(3)]
    outcomes = [superseded, CANCEL.classify(OLD, {}, NOTES[:1]), CANCEL.classify(OLD, {}, [])]
    monkeypatch.setattr(CANCEL, "observe", lambda repo, run, job, jobs: outcomes[job["id"]])
    CANCEL.attach_reasons("test/repo", {**OLD, "conclusion": "cancelled"}, jobs)
    assert [j["cancel_reason"] for j in jobs] == [superseded] * 3
    outcomes[0] = {**superseded, "run": OLD["id"]}
    CANCEL.attach_reasons("test/repo", {**OLD, "conclusion": "cancelled"}, jobs)
    assert [j["cancel_reason"] for j in jobs] == outcomes


def test_collector_reason_must_agree_with_the_completed_run(tmp_path):
    checker = _load("evidence_problems")
    superseded = CANCEL.classify(OLD, {}, NOTES, [NEW])
    record = tmp_path / CANCEL.REASON_FILE
    record.write_text(json.dumps(superseded))
    assert not any("[cancel-reason]" in p for p in checker.evidence_problems(
        tmp_path, kind="cancel", cancel_reason=superseded))
    assert any("[cancel-reason]" in p for p in checker.evidence_problems(
        tmp_path, kind="cancel", cancel_reason=CANCEL.classify(OLD, {}, NOTES[:1])))


def test_replaying_the_recorder_updates_only_its_own_check(monkeypatch):
    record = _load("record_cancel_evidence")
    rows = [{"run": OLD["id"], "job": 1, "kind": "manual/API cancel", "A1": "n/a", "A2": "n/a",
             "missing": [], "artifacts": []}]
    monkeypatch.setattr(record, "inspect_run", lambda repo, run: rows)
    checks = [{"external_id": "other", "id": 5, "app": {"slug": "github-actions"}}]
    monkeypatch.setattr(record, "_pages", lambda repo, endpoint, key: checks if key == "check_runs" else [{"id": 3}])
    calls = []
    monkeypatch.setattr(record, "_gh_read", lambda flag, method, endpoint, arg, path:
                        calls.append((method, endpoint, json.loads(Path(path).read_text()))))
    record.record("test/repo", OLD)
    method, url, payload = calls[-1]
    assert (method, url, payload["head_sha"]) == ("POST", "repos/test/repo/check-runs", OLD["head_sha"])
    assert "/artifacts/3" in payload["output"]["summary"]
    checks.extend([{"id": 9, "external_id": payload["external_id"], "app": {"slug": "github-actions"}},
                   {"id": 99, "external_id": payload["external_id"], "app": {"slug": "unrelated"}}])
    record.record("test/repo", OLD)
    method, url, update = calls[-1]
    assert (method, url) == ("PATCH", "repos/test/repo/check-runs/9")
    assert update == {k: v for k, v in payload.items() if k != "head_sha"}


def test_scorecard_cli_selects_the_jobs_original_attempt_and_skips_plants(monkeypatch, capsys):
    attempt = 2
    run = {**OLD, "run_attempt": attempt, "path": ".github/workflows/ci.yml", "conclusion": "cancelled"}
    job = {"id": 7, "run_id": OLD["id"], "run_attempt": attempt, "name": "queued", "conclusion": "cancelled",
           "steps": []}
    plant = {**run, "id": 99, "path": ".github/workflows/evidence-proof.yml"}
    data = {"actions/jobs/7": job, "actions/jobs/10": {**job, "run_id": 99},
            f"actions/runs/{OLD['id']}/attempts/2": run, "actions/runs/99/attempts/2": plant}
    monkeypatch.setattr(SCORE, "_api", lambda repo, path: data[path])
    monkeypatch.setattr(SCORE, "run_jobs",
                        lambda repo, ident, which: [job] if ident == run["id"] and which == attempt else [])
    import cancel_evidence as cancel

    monkeypatch.setattr(cancel, "check_annotations", lambda repo, ident: NOTES)
    monkeypatch.setattr(cancel, "candidates", lambda *args: [NEW])
    monkeypatch.setattr(SCORE, "download_artifacts", lambda repo, run, jobs, root: ({7: []}, []))
    assert SCORE.main(["--repo", "test/repo", "--jobs", "7", "10"]) == 0
    out = capsys.readouterr().out
    assert "superseded-before-start" in out and "f558023460af" in out and "| n/a | n/a |" in out
    assert "/runs/99" not in out
