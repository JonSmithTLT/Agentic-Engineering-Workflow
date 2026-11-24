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
       "created_at": "2026-11-15T19:29:00Z", "pull_requests": [{"number": 480}]}
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
    recorded_manual = [{"path": ".github", "message": "The run was canceled by @github-actions[bot]."}, *NOTES[:1]]
    assert CANCEL.classify(OLD, job, recorded_manual)["actor"] == "github-actions[bot]"
    assert "actor" not in CANCEL.classify(OLD, job, [{**recorded_manual[0], "path": "file.txt"}, *NOTES[:1]])
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

    # The controller snapshot during shutdown retains the failed phase and its
    # partial report (null exit status), even though all planned workers finished.
    session = raw / "autopsy/session-42-abc"
    session.mkdir(parents=True)
    for filename, value in {"session-started": "started", "worker-count": "1", "worker-gw0-pid": "43",
                            "worker-gw0-exit": "pid 43: worker gw0 finished its session (exit 1);"}.items():
        (session / f"{filename}.txt").write_text(value)
    priority = tmp_path / "priority-watchdog-input"
    _load("evidence_inputs").prepare(raw, priority, job=name)
    stage.stage(priority, out / "evidence-selected-attempt-1-watchdog")
    rows = []
    assert not check.check_jobs(out, [job], score_rows=rows)
    assert (rows[0]["A1"], rows[0]["A2"]) == ("yes", "n/a")


def test_an_assurance_dependency_install_does_not_start_pytest(tmp_path):
    check = _load("check_evidence_run")
    step = {"name": 'Run python -m pip install "PyYAML>=6.0" "pytest>=8"', "started_at": "2026-11-23",
            "conclusion": "success"}
    job = {"id": 7, "name": "assurance", "conclusion": "failure", "steps": [step]}
    rows = []
    assert check.check_jobs(tmp_path, [job], score_rows=rows) == []
    assert (rows[0]["A1"], rows[0]["A2"]) == ("n/a", "n/a")
    step["name"] = "Run python -m pytest tests"
    assert any("[job-evidence]" in p for p in check.check_jobs(tmp_path, [job]))


def test_cancel_after_pytest_needs_a_completed_report_and_matching_session(tmp_path, monkeypatch):
    check = _load("check_evidence_run")
    stage = _load("stage_evidence")
    raw = tmp_path / "raw"
    session = raw / "autopsy/session-42-abc"
    session.mkdir(parents=True)
    job = {"id": 7, "name": "integration 1/1 (windows-latest)", "conclusion": "cancelled", "steps": [],
           "cancel_reason": CANCEL.classify(OLD, {"id": 7}, NOTES, [NEW])}
    (raw / "runner-resources-job.txt").write_text(json.dumps({"job_label": job["name"]}))
    (session / "controller-pid.txt").write_text("42")
    (session / "session-started.txt").write_text("started")
    (session / "session-finished.txt").write_text("2026-11-23 10:20:12 pid 42: the session finished (exit None);")
    (raw / "report.json").write_text(json.dumps({"schema": "aew/lane-report/v1", "complete": True,
                                                  "exitstatus": 0, "results": {}}))
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    root = tmp_path / "published"
    root.mkdir()
    stage.stage(raw, root / "evidence-attempt-1")
    stage.stage(raw, root / "lane-report-evidence-attempt-1", reports_only=True)
    rows = []
    assert check.check_jobs(root, [job], score_rows=rows) == []
    assert rows[0]["kind"].endswith("after tests") and rows[0]["A2"] == "n/a"
    assert any("[cancel-reason]" in p for p in check.check_jobs(root, [{**job, "cancel_reason": None}]))
    # The full upload can be lost after the priority upload. A fully successful
    # lane can also have published only the report and names when a later step is canceled.
    (root / "evidence-attempt-1").rename(tmp_path / "withheld-full-upload")
    priority = tmp_path / "priority-watchdog-input"
    _load("evidence_inputs").prepare(raw, priority, job=job["name"])
    saved = root / "evidence-attempt-1-watchdog"
    stage.stage(priority, saved)
    assert not check.check_jobs(root, [job])
    published = saved / "autopsy/session-42-abc"
    (published / "controller-pid.txt").write_text("77")
    assert any("[death-record]" in p for p in check.check_jobs(root, [job]))
    successful = {"name": "Run python -m pytest tests", "conclusion": "success", "started_at": OLD["created_at"]}
    later = {"name": "Publish coverage", "conclusion": "cancelled", "started_at": OLD["created_at"]}
    post = {**successful, "name": "Post pytest --lane integration"}
    assert not check.check_jobs(root, [{**job, "steps": [successful, later, post]}])
    (published / "controller-pid.txt").write_text("42")
    (published / "cancelled-43.txt").write_text("{}")
    assert any("[death-record]" in p for p in check.check_jobs(root, [job]))


def test_all_planned_workers_must_have_finished_before_cancellation(tmp_path):
    from types import SimpleNamespace

    from session_deadline import Controller

    check = _load("check_evidence_run")
    (tmp_path / "session-started.txt").write_text("started")
    Controller.pytest_xdist_setupnodes(SimpleNamespace(dir=tmp_path), None, [object(), object()])
    for index, pid in enumerate((31, 55)):
        (tmp_path / f"worker-gw{index}-pid.txt").write_text(str(pid))
        assert not check.finished_tests([tmp_path], False)
        (tmp_path / f"worker-gw{index}-exit.txt").write_text(
            f"2026-11-23 10:20:12 pid {pid}: worker gw{index} finished its session (exit 0);")
    assert check.finished_tests([tmp_path], False)
    (tmp_path / "worker-gw1-pid.txt").write_text("56")
    assert not check.finished_tests([tmp_path], False)


@pytest.mark.parametrize("queue_seconds,outcome", [(660, "ready"), (1300, "allocation"), (660, "finished"),
                                                     (660, "staggered"), (660, "collected")])
def test_cancel_control_times_runner_allocation_separately_from_running_workers(monkeypatch, queue_seconds, outcome):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import cancel_evidence_plant

    prove = _load("prove_cancel_evidence")
    workflow = yaml.safe_load((ROOT / ".github/workflows/evidence-proof.yml").read_text())
    deadline_step = next(step for step in workflow["jobs"]["cancel-plant"]["steps"]
                         if step.get("name") == "The job's deadline")
    assert f"+ {prove.CANCEL_PLANT_SECONDS} " in deadline_step["run"]
    waits = []

    def now():
        return sum(waits)

    clock = SimpleNamespace(monotonic=now, time=now, sleep=waits.append)
    monkeypatch.setattr(prove, "time", clock)
    monkeypatch.setattr(cancel_evidence_plant, "time", clock)

    def jobs(repo, endpoint):
        assert endpoint == "actions/runs/42/attempts/1/jobs?per_page=100"
        rows = [{"name": "unrelated", "runner_id": 7, "conclusion": "success"}]
        for index, os_name in enumerate(("ubuntu-24.04", "windows-latest")):
            offset = index * (305 if outcome == "staggered" else 10)
            running = now() >= queue_seconds + offset
            start = datetime.fromtimestamp(queue_seconds + offset, UTC).isoformat()
            rows.append({"id": index + 1, "name": f"plant ({os_name}, cancel, none)",
                         "runner_id": 7 if running else 0,
                         "conclusion": "failure" if running and outcome == "finished" else None,
                         "steps": [{"name": "The job's deadline", "started_at": start}, {
                             "name": "Real planted lane", "started_at": start,
                             "status": "completed" if outcome == "collected" else "in_progress"}] if running else []})
        return {"jobs": rows}

    monkeypatch.setattr(prove, "_api", jobs)
    if outcome == "ready":
        assert [job["id"] for job in prove.wait_for_workers("x/y", 42)] == [1, 2]
        assert now() == queue_seconds + 10 + prove.SENTINEL_READY_S
    else:
        expected = {"allocation": "runner to be assigned", "finished": "target finished",
                    "staggered": "no overlapping time", "collected": "no active execution window"}[outcome]
        with pytest.raises(RuntimeError, match=expected):
            prove.wait_for_workers("x/y", 42)


def test_archive_reader_confines_artifact_data_and_accounts_for_the_expanded_size(tmp_path):
    def archive(name):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            member = zipfile.ZipInfo(name)
            member.filename = name  # keep identical on-disk spellings on Windows and Linux
            member.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(member, b"a" * 150)
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
    assert job["permissions"] == {"contents": "read", "checks": "write", "actions": "read", "pull-requests": "read"}
    checkout = job["steps"][0]["with"]
    assert checkout["ref"] == "${{ github.sha }}" and checkout["persist-credentials"] is False
    assert "github.event.workflow_run.head_sha" not in str(job)
    assert all("workflow_run" not in step.get("run", "") for step in job["steps"])
    full = next(s for s in job["steps"] if s.get("with", {}).get("path") == "${{ runner.temp }}/cancel-check/")
    assert full["if"] == "${{ !cancelled() }}"


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


def test_missing_candidate_group_requires_an_independent_commit_to_pr_mapping(monkeypatch):
    raw = {**NEW, "pull_requests": []}
    assert CANCEL.classify(OLD, {}, NOTES, [raw])["kind"] == "unresolved"
    prs = [{"number": 480, "head": {"ref": NEW["head_branch"], "repo": {"id": 1}}}]
    monkeypatch.setattr(CANCEL, "commit_pulls", lambda repo, sha: prs)
    assert CANCEL.classify(OLD, {}, NOTES, [CANCEL.with_pull_group("test/repo", raw)])["run"] == NEW["id"]
    prs.append({"number": 481, "head": {"ref": NEW["head_branch"], "repo": {"id": 1}}})
    assert CANCEL.classify(OLD, {}, NOTES, [CANCEL.with_pull_group("test/repo", raw)])["kind"] == "unresolved"


def test_scorecard_reads_surviving_report_without_a_running_index_and_isolates_unrelated_loss(tmp_path, monkeypatch):
    name = "integration 2/8 (ubuntu-latest)"
    job = {"id": 7, "name": name, "conclusion": "failure", "steps": []}
    docs = {"runner-resources-job.txt": json.dumps({"job_label": name}),
            "inventory.txt": "typed source names\n",
            "report.json": json.dumps({"schema": "aew/lane-report/v1", "exitstatus": 1, "results": {
                "test_example.py::test_x": {"outcome": "failed", "failures": [
                    {"phase": "call", "crash": "case.py:2: ValueError: x", "longrepr": "E   ValueError: x"}]}}})}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for path, data in docs.items():
            archive.writestr(path, data)
    raw = stream.getvalue()
    artifacts = [{"id": 100, "name": "evidence-windows-attempt-1-running", "expired": True, "size_in_bytes": 15},
                 {"id": 200, "name": "lane-report-evidence-linux-attempt-1", "expired": False,
                  "size_in_bytes": len(raw)}]
    monkeypatch.setattr(SCORE, "run_jobs", lambda *args: [job])
    monkeypatch.setattr(SCORE, "_pages", lambda *args: artifacts)
    monkeypatch.setattr(SCORE, "_gh_read", lambda url: raw)
    [row] = SCORE.inspect_run("test/repo", OLD, {7})
    assert row["A1"] == "yes" and row["failed_nodes"] == ["test_example.py::test_x"]
    assert row["artifacts"] == [200] and row["unreadable_artifacts"] == []
    assert row["unassigned_artifacts"] == [100]


@pytest.mark.parametrize("trusted", [True, False])
def test_recorder_selects_event_attempt_and_keeps_pr_sightings_out_of_main_index(monkeypatch, tmp_path, trusted):
    import sys

    record = _load("record_cancel_evidence")
    repo = {"full_name": "test/repo"}
    run = {**OLD, "run_attempt": 2, "path": ".github/workflows/ci.yml", "conclusion": "cancelled",
           "repository": repo, "head_repository": repo, "event": "push" if trusted else "pull_request",
           "head_branch": "main" if trusted else "feature"}
    monkeypatch.setenv("GITHUB_REPOSITORY", repo["full_name"])
    argv = ["record", "--run", str(run["id"]), "--attempt", "2", "--index-dir", str(tmp_path),
            "--report-dir", str(tmp_path)]
    monkeypatch.setattr(sys, "argv", argv)
    expected = f"actions/runs/{run['id']}/attempts/2"
    monkeypatch.setattr(record, "_api", lambda repo, endpoint: {expected: run}[endpoint])
    calls = []
    monkeypatch.setattr(record, "record", lambda repo, selected, dest: calls.append("check") or [])
    monkeypatch.setattr(record, "record_test_sightings", lambda *args: calls.append("index"))
    record.main()
    assert calls == (["check", "index"] if trusted else ["check"])


def test_default_branch_check_withholds_unscanned_details_but_records_the_rule(monkeypatch):
    record = _load("record_cancel_evidence")
    rows = [{"job": 7, "missing": ["failure-text"], "defects": [
        "evidence defect: [failure-text] tests/foo.py::test_case[private fixture] (call): no retained failure text"]}]
    monkeypatch.setattr(record, "stage", lambda source, checked: checked.mkdir())
    record.scan_details(rows)
    assert rows[0]["missing"] == ["failure-text", "scan-unavailable"]
    assert rows[0]["defects"] == ["evidence defect: [scan-unavailable] defect details withheld"]


def test_empty_canceled_attempt_records_the_unavailable_cause_without_inventing_a_job(monkeypatch):
    record = _load("record_cancel_evidence")
    monkeypatch.setattr(record, "inspect_run", lambda *args: [])
    monkeypatch.setattr(record, "run_jobs", lambda *args: [])
    monkeypatch.setattr(record, "_pages", lambda *args: [])
    payload = []
    monkeypatch.setattr(record, "_gh_read", lambda *args: payload.append(json.loads(Path(args[-1]).read_text())))
    assert record.record("test/repo", OLD) == []
    assert payload[0]["conclusion"] == "failure"
    assert "Cancelled before any job was recorded" in payload[0]["output"]["summary"]
    assert "[cancel-reason]" in payload[0]["output"]["summary"]


def test_oversized_check_keeps_full_scanned_diagnostics_and_links_the_record(monkeypatch, tmp_path):
    record = _load("record_cancel_evidence")
    rows = [{"run": OLD["id"], "job": 7, "kind": "test_failure", "A1": "no", "A2": "n/a", "artifacts": [],
             "defects": [f"evidence defect: [failure-text] case_{n} (call): missing cause" for n in range(1300)],
             "missing": ["failure-text"]}]
    monkeypatch.setattr(record, "inspect_run", lambda *args: rows)
    monkeypatch.setattr(record, "scan_details", lambda rows: None)
    monkeypatch.setattr(record, "_pages", lambda *args: [])
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    payload = []
    monkeypatch.setattr(record, "_gh_read", lambda *args: payload.append(json.loads(Path(args[-1]).read_text())))
    record.record("test/repo", OLD, tmp_path)
    assert "case_1299 (call)" in (tmp_path / "evidence.md").read_text()
    assert "actions/runs/123/attempts/2" in payload[0]["output"]["summary"]


def test_skipped_pytest_timestamp_is_not_a_worker_start_and_an_unclassified_death_stays_unknown(tmp_path):
    check = _load("check_evidence_run")
    job = {"id": 7, "name": "test job", "conclusion": "cancelled", "cancel_reason": CANCEL.classify(OLD, {}, NOTES[:1]),
           "steps": [{"name": "Set up Python", "started_at": OLD["created_at"], "conclusion": "cancelled"},
                     {"name": "fast lane (unit, schemas, store model, frozen-spec pin)",
                      "started_at": OLD["created_at"], "conclusion": "skipped"}]}
    rows = []
    assert check.check_jobs(tmp_path, [job], score_rows=rows) == []
    assert rows[0]["A2"] == "n/a"
    full = tmp_path / "evidence-one-attempt-1"
    full.mkdir()
    (full / "runner-resources-job.txt").write_text(json.dumps({"job_label": job["name"]}))
    (full / "runner-resources-lane-exit.txt").write_text(json.dumps({"lane_exit": 64}))
    rows = []
    check.check_jobs(tmp_path, [{**job, "conclusion": "failure"}], score_rows=rows)
    assert rows[0]["kind"] == "unclassified" and any("[job-kind]" in d for d in rows[0]["missing"])


def test_run_wide_manual_actor_covers_queued_siblings_but_a_job_actor_alone_cannot(monkeypatch):
    run = {**OLD, "conclusion": "cancelled"}
    jobs = [{"id": n, "conclusion": "cancelled"} for n in range(2)]
    service = {"path": ".github", "message": "The run was canceled by @github-actions[bot]."}
    missing = CANCEL.classify(run, jobs[1], [])
    outcomes = [CANCEL.classify(run, jobs[0], [service, *NOTES[:1]]), missing]
    monkeypatch.setattr(CANCEL, "observe", lambda repo, run, job, jobs: outcomes[job["id"]])
    CANCEL.attach_reasons("test/repo", run, jobs)
    assert jobs[1]["cancel_reason"] == outcomes[0] and jobs[1]["cancel_reason"]["actor"] == "github-actions[bot]"
    outcomes[0] = CANCEL.classify(run, {**jobs[0], "cancelled_by": {"login": "job-user"}}, NOTES[:1])
    CANCEL.attach_reasons("test/repo", run, jobs)
    assert jobs[1]["cancel_reason"] == missing


def test_completed_parent_finds_only_its_own_original_attempts(monkeypatch):
    record = _load("record_cancel_evidence")
    repo = "test/repo"
    parent = {**OLD, "status": "completed", "updated_at": NEW["created_at"]}
    base = {**OLD, "event": "workflow_dispatch", "actor": {"login": "github-actions[bot]"},
            "head_repository": {"full_name": repo}, "conclusion": "cancelled", "run_attempt": 3}
    children = {n: {**base, "id": n, "display_title": f"evidence-cancel-run-{OLD['id']}-1-{s}-target"}
                for n, s in ((101, "manual"), (102, "supersede"))}
    runs = [*children.values(), {**children[101], "id": 105, "head_sha": NEW["head_sha"]},
            {**children[102], "id": 106, "actor": {"login": "operator"}},
            {**children[101], "id": 107, "head_branch": "other"}]
    monkeypatch.setattr(record, "_pages", lambda *args: runs)
    attempts = {f"actions/runs/{n}/attempts/1": {**r, "run_attempt": 1} for n, r in children.items()}
    monkeypatch.setattr(record, "_api", lambda repo, endpoint: attempts[endpoint])
    found = record.proof_subjects(repo, parent)
    assert {s: (r["id"], r["run_attempt"]) for s, r in found.items()} == {"manual": (101, 1), "supersede": (102, 1)}
    runs.append({**children[101], "id": 108})
    assert list(record.proof_subjects(repo, parent)) == ["supersede"]


def test_parent_observer_records_and_reads_back_both_sources_but_premerge_probe_only_reads(monkeypatch, tmp_path):
    record = _load("record_cancel_evidence")
    children = {s: {**OLD, "id": n} for s, n in (("manual", 101), ("supersede", 102))}
    logged = []
    persisted = []
    monkeypatch.setattr(record, "proof_subjects", lambda *args: children)

    def inspect(repo, child):
        logged.append(child["id"])
        reason = ({"kind": "manual-or-api", "actor": "github-actions[bot]"} if child["id"] == 101 else
                  {"kind": "superseded", "run": 200, "event": "workflow_dispatch", "head_sha": child["head_sha"]})
        return [{"name": f"plant ({os}, cancel, none)", "A2": "yes", "missing": [],
                 "artifacts": [123], "cancel_reason": reason} for os in ("ubuntu-24.04", "windows-latest")]

    def write(repo, child, path):
        persisted.append(child["id"])
        return inspect(repo, child)

    def checks(repo, endpoint, key):
        return [{"id": n + 10, "external_id": f"aew-evidence-run-{n}-attempt-1",
                 "app": {"slug": "github-actions"}, "conclusion": "success"} for n in persisted]

    monkeypatch.setattr(record, "inspect_run", inspect)
    monkeypatch.setattr(record, "record", write)
    monkeypatch.setattr(record, "_pages", checks)
    record.record_proof_children("test/repo", OLD, tmp_path, publish=False)
    assert logged == [101, 102] and persisted == []
    record.record_proof_children("test/repo", OLD, tmp_path)
    assert persisted == [101, 102]
