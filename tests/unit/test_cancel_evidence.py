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
                    "staggered": "runner queued past its deadline", "collected": "no active execution window"}[outcome]
        with pytest.raises(RuntimeError, match=expected):
            prove.wait_for_workers("x/y", 42)


@pytest.mark.parametrize("late", [0, 322, 323, -322, 900, 1000, -1000, 1050, 1100, -1100, 1300, "linux-fails-early"])
def test_a_plant_whose_runner_queues_late_still_overlaps_or_is_named_as_queued(monkeypatch, late):
    # Target runs 45513035294 and 45547533341: the Windows plant's runner came 322 s and 323 s after its Linux twin's,
    # which spent the Linux window before both were live. The plants now hold their deadline steps for their twin.
    # A plant that fails before its lane runs (both runners assigned together, the Linux job failing in setup while
    # Windows is still in its own) is not queueing, and is never named so (#564's quick check, m1).
    fails_early = late == "linux-fails-early"
    late = 0 if fails_early else late
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import cancel_evidence_plant

    prove = _load("prove_cancel_evidence")
    steps = yaml.safe_load((ROOT / ".github/workflows/evidence-proof.yml").read_text())["jobs"]["cancel-plant"]["steps"]
    names = [step.get("name") for step in steps]
    barrier = steps[names.index("Wait for the twin plant's runner")]
    assert names.index("Wait for the twin plant's runner") < names.index("The job's deadline")
    assert barrier["if"] == "startsWith(matrix.kind, 'cancel') && inputs.probe_origin"
    assert barrier["env"]["TWIN"].endswith(", ${{ matrix.kind }}, none)")
    assert f"bound={prove.TWIN_BARRIER_SECONDS}\n" in barrier["run"]
    assert barrier["timeout-minutes"] * 60 > prove.TWIN_BARRIER_SECONDS
    waits = []

    def now():
        return sum(waits)

    clock = SimpleNamespace(monotonic=now, time=now, sleep=waits.append)
    monkeypatch.setattr(prove, "time", clock)
    monkeypatch.setattr(cancel_evidence_plant, "time", clock)
    dispatched = 60
    runners = {"ubuntu-24.04": dispatched + max(0, -late), "windows-latest": dispatched + max(0, late)}
    setup = {"ubuntu-24.04": 25, "windows-latest": 40}  # checkout, setup-aew and tools, from the observed runs

    def timeline(os_name):
        twin = runners["windows-latest" if os_name == "ubuntu-24.04" else "ubuntu-24.04"]
        own = runners[os_name]
        opened = max(own, min(twin, own + prove.TWIN_BARRIER_SECONDS)) + 5  # the barrier's poll interval
        return own, opened, opened + setup[os_name]

    def jobs(repo, endpoint):
        rows = []
        for index, os_name in enumerate(("ubuntu-24.04", "windows-latest")):
            own, opened, lane = timeline(os_name)
            at = now()
            # The lane ends at its session deadline and the job concludes after it, as in target run 45547533341.
            row = {"id": index + 1, "name": f"plant ({os_name}, cancel, none)", "runner_id": 7 if at >= own else 0,
                   "conclusion": "failure" if at >= opened + 390 else None, "steps": []}
            if row["conclusion"]:
                row["completed_at"] = datetime.fromtimestamp(opened + 390, UTC).isoformat()
            if fails_early and os_name == "ubuntu-24.04":
                failed = own + 10  # before its deadline step
                row.update(conclusion="failure" if at >= failed else None,
                           completed_at=datetime.fromtimestamp(failed, UTC).isoformat() if at >= failed else None)
                rows.append(row)
                continue
            if at >= opened:
                row["steps"].append({"name": "The job's deadline",
                                     "started_at": datetime.fromtimestamp(opened, UTC).isoformat()})
            if at >= lane:
                row["steps"].append({"name": "Real planted lane",
                                     "status": "in_progress" if at < opened + 370 else "completed",
                                     "started_at": datetime.fromtimestamp(lane, UTC).isoformat()})
                if at >= opened + 370:
                    row["steps"][-1]["completed_at"] = datetime.fromtimestamp(opened + 370, UTC).isoformat()
            rows.append(row)
        return {"jobs": rows}

    monkeypatch.setattr(prove, "_api", jobs)
    if fails_early:
        with pytest.raises(RuntimeError, match="cancellation target finished before its replacement queued") as failed:
            prove.wait_for_workers("x/y", 42)
        assert not isinstance(failed.value, prove.PlantQueued)
    elif abs(late) <= 600:
        assert [job["id"] for job in prove.wait_for_workers("x/y", 42)] == [1, 2]
        trigger = now()
        for os_name in runners:  # the trigger falls inside both plants' live windows
            _own, opened, lane = timeline(os_name)
            assert lane + prove.SENTINEL_READY_S <= trigger
            assert trigger < opened + prove.CANCEL_PLANT_SECONDS - prove.TRIGGER_RESERVE_SECONDS
    else:
        late_plant = "windows-latest" if late > 0 else "ubuntu-24.04"
        with pytest.raises(prove.PlantQueued, match=rf"queued past its deadline: plant \({late_plant}, cancel"):
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


def test_a_superseded_runs_unstarted_matrix_jobs_resolve_to_the_superseding_run_while_assurance_runs(monkeypatch):
    # Run 45339635974: the newer push cancelled `tier` and `static`, whose annotations name ci-480's next run. GitHub
    # then created the lane matrix with its names unrendered and no runner, steps or annotation, and assurance read
    # the run while it was itself still running (no conclusion yet).
    check = _load("check_evidence_run")
    started = [{"id": n, "name": name, "conclusion": "cancelled", "completed_at": "2026-11-15T19:29:05Z",
                "steps": [{"name": "Set up job", "started_at": OLD["created_at"], "conclusion": "success"}]}
               for n, name in ((1, "static"), (2, "tier"))]
    placeholder = "${{ matrix.lane }} ${{ matrix.shard }}/${{ matrix.of }} (${{ matrix.os }})"
    unstarted = [{"id": n, "name": placeholder, "conclusion": "cancelled", "completed_at": "2026-11-15T19:29:05Z",
                  "steps": []} for n in (3, 4)]
    jobs = started + unstarted
    monkeypatch.setattr(CANCEL, "check_annotations", lambda repo, ident: NOTES if ident in (1, 2) else [])
    monkeypatch.setattr(CANCEL, "candidates", lambda *args: [NEW])
    running = {**OLD, "pull_requests": [{"number": 480}], "status": "in_progress", "conclusion": None,
               "updated_at": NEW["created_at"]}
    CANCEL.attach_reasons("test/repo", running, jobs)
    superseded = {"kind": "superseded", "run": NEW["id"], "head_sha": NEW["head_sha"], "event": "pull_request"}
    assert [job["cancel_reason"] for job in jobs] == [superseded] * 4
    rows = []
    assert check.check_jobs(Path("missing"), jobs, score_rows=rows) == []
    assert [row["kind"] for row in rows[2:]] == ["superseded-before-start"] * 2
    # A run that completed without being cancelled was never cancelled whole: its siblings inherit nothing.
    for job in jobs:
        job.pop("cancel_reason")
    CANCEL.attach_reasons("test/repo", {**running, "status": "completed", "conclusion": "failure"}, jobs)
    assert [job["cancel_reason"]["kind"] for job in jobs] == ["superseded", "superseded", "unresolved", "unresolved"]
    assert any("[cancel-reason]" in defect for defect in check.check_jobs(Path("missing"), jobs))


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


@pytest.mark.parametrize("change, expected", [
    ({}, "runner-lost"),
    ({"path": "tests/example.py"}, "unclassified"),
    ({"annotation_level": "warning"}, "unclassified"),
    ({"message": "The action has timed out."}, "unclassified"),
    ({"message": "The operation was canceled."}, "unclassified"),
])
def test_scorecard_excludes_only_a_proven_mid_job_runner_loss(monkeypatch, change, expected):
    # Original attempt 1 of CI 45405842359. GitHub finalized the job without finishing the pytest step.
    step = {"name": "pytest --lane regression --shard 2/3 -n auto", "started_at": "2026-11-24T13:41:30Z",
            "status": "in_progress", "conclusion": None, "completed_at": None}
    job = {"id": 138486559048, "name": "regression 2/3 (windows-latest)", "conclusion": "failure",
           "status": "completed", "steps": [step]}
    annotation = {"path": ".github", "annotation_level": "failure",
                  "message": "The hosted runner lost communication with the server. Anything in your workflow that "
                             "terminates the runner process, starves it for CPU/Memory, or blocks its network access "
                             "can cause this error.", **change}
    monkeypatch.setattr(SCORE, "run_jobs", lambda *args: [job])
    monkeypatch.setattr(SCORE, "_pages", lambda *args: [])
    monkeypatch.setattr(SCORE, "check_annotations", lambda repo, ident: {job["id"]: [annotation]}[ident])
    [row] = SCORE.inspect_run("test/repo", OLD)
    assert row["kind"] == expected
    assert row["A1"] == row["A2"] == ("n/a" if expected == "runner-lost" else "no")
    assert row["missing"] == ["job-evidence"]
    step.update(status="completed", conclusion="failure", completed_at="2026-11-24T14:28:56Z")
    [row] = SCORE.inspect_run("test/repo", OLD)
    assert (row["kind"], row["A1"], row["A2"]) == ("unclassified", "no", "no")


@pytest.mark.parametrize("lost", [False, True])
@pytest.mark.parametrize("failure_case", ["empty", "absent-phase", "unknown-phase", "valid-phase"])
def test_scorecard_preserves_a_surviving_failure_report_and_its_registered_sighting(
    monkeypatch, tmp_path, lost, failure_case
):
    name = "integration 2/8 (ubuntu-latest)"
    job = {"id": 7, "name": name, "conclusion": "failure", "steps": [], "started_at": "2026-11-24T13:41:30Z"}
    if lost:
        job.update(status="completed", steps=[{"name": "pytest --lane integration", "status": "in_progress",
                                              "started_at": "2026-11-24T13:41:30Z", "conclusion": None}])
        monkeypatch.setattr(SCORE, "check_annotations", lambda *args: [
            {"path": ".github", "annotation_level": "failure", "message": SCORE.HOSTED_RUNNER_LOST}])
    node = "test_example.py::test_x"
    failure = {"crash": "case.py:2: ValueError: x", "longrepr": "E   ValueError: x"}
    if failure_case in {"valid-phase", "unknown-phase"}:
        failure["phase"] = "call" if failure_case == "valid-phase" else "unknown"
    phase_record = failure_case == "valid-phase"
    docs = {"runner-resources-job.txt": json.dumps({"job_label": name}),
            "inventory.txt": "typed source names\n",
            "report.json": json.dumps({"schema": "aew/lane-report/v1", "exitstatus": 1, "results": {
                node: {"outcome": "failed", "failures": [] if failure_case == "empty" else [failure]}}})}
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
    assert row["kind"] == ("runner-lost" if lost else "test_failure" if phase_record else "unclassified")
    assert row["A1"] == ("yes" if phase_record else "no")
    assert row["failed_nodes"] == ([node] if phase_record else [])
    assert ("failure-report" in row["missing"]) == (not phase_record)
    assert ("failure-text" in row["missing"]) == (failure_case == "empty")
    assert row["artifacts"] == [200] and row["unreadable_artifacts"] == []
    assert row["unassigned_artifacts"] == [100]

    record = _load("record_cancel_evidence")
    register = tmp_path / "register.yml"
    register.write_text(yaml.safe_dump({"entries": [
        {"id": "known", "scope": "test", "status": "open", "lane": "integration", "platforms": ["linux"], "test": node}
    ]}))
    monkeypatch.setattr(record, "REGISTER_PATH", register)
    record.record_test_sightings(tmp_path, OLD, [row])
    assert (tmp_path / record.INDEX_MEMBER).exists() == phase_record


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


# PR #601's run 45786034180: cancelled after ten minutes with no job and no `cancelled_by`, its one successor created
# a second before it concluded.
JOBLESS = {**OLD, "path": ".github/workflows/ci.yml", "conclusion": "cancelled", "status": "completed",
           "updated_at": "2026-11-15T19:29:01Z", "pull_requests": [{"number": 480}]}


def _record_jobless(monkeypatch, run, history):
    """Record a cancelled run with no job against a run history; return the check and the history queries made."""
    record = _load("record_cancel_evidence")
    monkeypatch.setattr(record, "inspect_run", lambda *args: [])
    monkeypatch.setattr(record, "run_jobs", lambda *args: [])
    monkeypatch.setattr(record, "_pages", lambda *args: [])
    asked = []
    monkeypatch.setattr(CANCEL, "candidates", lambda *args: asked.append(args) or [run, *history])
    monkeypatch.setattr(CANCEL, "commit_pulls", lambda repo, sha: [])
    payload = []
    monkeypatch.setattr(record, "_gh_read", lambda *args: payload.append(json.loads(Path(args[-1]).read_text())))
    assert record.record("test/repo", run) == []
    return payload[0], asked


def test_a_run_superseded_before_any_job_names_its_unique_successor_and_is_no_gap(monkeypatch):
    check, asked = _record_jobless(monkeypatch, JOBLESS, [NEW])
    assert check["conclusion"] == "success" and check["output"]["title"].endswith("0 red jobs, 0 evidence gaps")
    summary = check["output"]["summary"]
    assert f"Superseded before any job was recorded, by run {NEW['id']} at f558023460af (pull_request)." in summary
    assert "[cancel-reason]" not in summary and "evidence defect" not in summary
    # The successor is looked for only within the cancelled run's own life, in its own workflow, branch and event.
    assert asked == [("test/repo", OLD["workflow_id"], "feature", "pull_request", JOBLESS["created_at"],
                      JOBLESS["updated_at"])]


def test_a_jobless_cancel_with_two_possible_successors_stays_an_attribution_gap(monkeypatch):
    check, asked = _record_jobless(monkeypatch, JOBLESS, [NEW, {**NEW, "id": NEW["id"] + 1}])
    assert asked and check["conclusion"] == "failure"
    assert "Cancelled before any job was recorded" in check["output"]["summary"]
    assert "[cancel-reason] no available cancellation attribution" in check["output"]["summary"]
    assert "Superseded" not in check["output"]["summary"]


@pytest.mark.parametrize("history", [
    [],
    [{**NEW, "pull_requests": [{"number": 910}]}],  # another pull request's run of the same branch
    [{**NEW, "head_repository": {"id": 2}}],  # a fork's run
    [{**NEW, "event": "push"}],
    [{**NEW, "workflow_id": 1}],
    [{**NEW, "created_at": "2026-11-15T18:00:00Z"}],  # created before the cancelled run: it cannot have replaced it
    [{**NEW, "pull_requests": []}],  # its group cannot be established
    # Created in the cancelled run's own second with a lower id: its predecessor, never its successor (#615, finding 2).
    [{**NEW, "id": OLD["id"] - 1, "created_at": OLD["created_at"]}],
], ids=["none", "other-pr", "fork", "push", "other-workflow", "earlier", "no-group", "same-second-predecessor"])
def test_a_jobless_cancel_with_no_established_successor_stays_an_attribution_gap(monkeypatch, history):
    check, asked = _record_jobless(monkeypatch, JOBLESS, history)
    assert asked and check["conclusion"] == "failure"
    assert "[cancel-reason] no available cancellation attribution" in check["output"]["summary"]
    assert "Superseded" not in check["output"]["summary"]


def test_a_same_second_run_with_a_higher_id_is_still_the_jobless_runs_successor(monkeypatch):
    # The other side of the id order: created in the same second, after the cancelled run.
    check, _ = _record_jobless(monkeypatch, JOBLESS, [{**NEW, "created_at": JOBLESS["created_at"]}])
    assert check["conclusion"] == "success" and f"by run {NEW['id']} at" in check["output"]["summary"]


def test_a_jobless_re_run_attempt_is_never_attributed_from_history(monkeypatch):
    # A re-run keeps the first attempt's created_at, so a run that is newer than the first attempt and older than the
    # re-run would fall inside its window; it cannot have replaced the re-run (#615, finding 1).
    rerun = {**JOBLESS, "run_attempt": 2, "run_started_at": "2026-11-15T20:00:00Z",
             "updated_at": "2026-11-15T20:05:00Z"}
    check, asked = _record_jobless(monkeypatch, rerun, [NEW])
    assert NEW["created_at"] < rerun["run_started_at"]
    assert not asked and check["conclusion"] == "failure"
    assert "[cancel-reason] no available cancellation attribution" in check["output"]["summary"]
    assert "Superseded" not in check["output"]["summary"]


@pytest.mark.parametrize("change", [
    {"path": ".github/workflows/evidence-proof.yml"},  # ci_group names ci.yml's group only
    {"event": "workflow_dispatch"},
    {"event": "push"},  # a push run's group is its own commit: nothing supersedes it
    {"conclusion": "failure"},
    {"pull_requests": [{"number": 480}, {"number": 481}]},  # two groups: neither is established
], ids=["other-workflow", "dispatch", "push", "not-cancelled", "two-prs"])
def test_a_jobless_run_outside_a_pull_requests_ci_group_is_never_attributed_from_history(monkeypatch, change):
    check, asked = _record_jobless(monkeypatch, {**JOBLESS, **change}, [NEW])
    assert not asked and check["conclusion"] == "failure"
    assert "[cancel-reason] no available cancellation attribution" in check["output"]["summary"]


def test_a_jobless_manual_cancel_keeps_its_actor_and_asks_no_run_history(monkeypatch):
    check, asked = _record_jobless(monkeypatch, {**JOBLESS, "cancelled_by": {"login": "operator"}}, [NEW])
    assert not asked and check["conclusion"] == "success"
    assert "Actor: operator." in check["output"]["summary"] and "Superseded" not in check["output"]["summary"]


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


def test_a_failed_read_does_not_end_the_cancel_controls_wait_before_its_deadline(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    import flake_register

    prove = _load("prove_cancel_evidence")
    waits = []
    monkeypatch.setattr(prove, "time", SimpleNamespace(monotonic=lambda: sum(waits), sleep=waits.append))
    answers = iter([subprocess.CalledProcessError(1, ["gh", "api"]), subprocess.TimeoutExpired(["gh", "api"], 45),
                    None, {"id": 42}])

    def find():
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert prove.poll(find, 60, "the target run") == {"id": 42} and len(waits) == 3

    def failing():
        raise flake_register.GhReadError(1, ["gh", "api"], b"", b"gh: Not Found (HTTP 404)\n")

    with pytest.raises(RuntimeError, match=r"the target run; the last read failed: .*HTTP 404"):
        prove.poll(failing, 60, "the target run")

    def wrong():
        raise RuntimeError("controlled pytest lane has no active execution window")

    with pytest.raises(RuntimeError, match="no active execution window"):  # a finding still ends the wait at once
        prove.poll(wrong, 60, "the lanes")


def test_a_failed_gh_read_names_gh_s_own_error(monkeypatch):
    import subprocess

    import flake_register

    def run(argv, **_kw):
        raise subprocess.CalledProcessError(1, argv, b"", b"gh: Server Error (HTTP 502)\n")

    monkeypatch.setattr(flake_register.subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError, match=r"exit status 1: gh: Server Error \(HTTP 502\)") as raised:
        flake_register._gh_read("repos/o/r/actions/runs/1/attempts/1/jobs")
    assert raised.value.stderr == b"gh: Server Error (HTTP 502)\n"  # _pages still reads the raw text


# A lane cancelled while its sessions start (register E3): superseded CI run 45590135545 cancelled ten lanes 37 to 96 s
# into their pytest step, each with "[death-record] cancel: no pre-cleanup worker observation" and "[running] missing
# running test name", since no worker was in a test to observe or name.
BEFORE = "integration 8/8 (ubuntu-latest)"


def _starting_lane(raw, layout):
    """A lane root as a cancellation finds it while its sessions start. ``layout`` names the sessions' state."""
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "runner-resources-job.txt").write_text(json.dumps({"job_label": BEFORE}))
    if layout == "no session":
        return []
    session = raw / "autopsy/session-42-abc"
    session.mkdir(parents=True)
    (session / "session-started.txt").write_text("started")
    (session / "controller-pid.txt").write_text("42")
    (session / "controller-start.txt").write_text("4200")
    if layout == "serial":
        return []
    (session / "worker-count.txt").write_text("2\n")
    rows = []
    phase = {"collecting": "collecting", "collection ended": "collection-ended", "executing": "execution-started",
             "finished": "collection-ended", "workers not up": None}[layout]
    for index, pid in enumerate((101, 102) if phase else ()):
        (session / f"worker-gw{index}-pid.txt").write_text(f"{pid}\n")
        (session / f"worker-gw{index}-start.txt").write_text(f"{pid * 2}\n")
        (session / f"worker-{pid}-{pid * 2}-lifecycle.txt").write_text(
            "".join(f"{stamp} {name} 7\n" for stamp, name in enumerate(
                ("collecting", "collection-ended", "execution-started")[:("collecting", "collection-ended",
                                                                         "execution-started").index(phase) + 1],
                start=10)))
        rows.append({"session": session.name, "worker": f"worker-gw{index}", "pid": pid, "start": pid * 2,
                     "phase": phase})
    if layout == "finished":
        (session / "session-finished.txt").write_text("2026-11-25 10:02:37 pid 42: the session finished (exit 1);")
    return rows


def _published(tmp_path, raw, monkeypatch):
    stage = _load("stage_evidence")
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    root = tmp_path / "published"
    root.mkdir()
    # As the lane action publishes: the running names, the priority (watchdog) bundle, the reports and the full bundle.
    priority = tmp_path / "evidence-before-attempt-1-watchdog-input"
    _load("evidence_inputs").prepare(raw, priority, job=BEFORE)
    (tmp_path / "evidence-before-attempt-1-names").rename(root / "evidence-before-attempt-1-running")
    stage.stage(priority, root / "evidence-before-attempt-1-watchdog")
    stage.stage(raw, root / "evidence-before-attempt-1")
    stage.stage(raw, root / "lane-report-evidence-before-attempt-1", reports_only=True)
    return root


def _cancelled_lane_job():
    return {"id": 139124033808, "name": BEFORE, "conclusion": "cancelled", "steps": [],
            "cancel_reason": CANCEL.classify(OLD, {"id": 139124033808}, NOTES, [NEW])}


def _collect(raw, rows, monkeypatch):
    import sys

    lane = _load("lane_step")
    monkeypatch.setenv("AEW_LANE_JOB_STATUS", "cancelled")
    monkeypatch.setenv("AEW_LANE_JOB_LABEL", BEFORE)
    monkeypatch.setattr(sys.modules["cancel_evidence"], "collect_reason", lambda *_: None)
    monkeypatch.setattr(lane, "collect", lambda _: None)
    monkeypatch.setattr(lane.worker_evidence, "phases_at_signal", lambda root, at_ns: rows)
    assert lane.main(["--collect", "--root", str(raw)]) == 0


NOTHING_RAN = {"schema": "aew/lane-report/v1", "complete": True, "exitstatus": 2, "collected": [], "results": {}}


@pytest.mark.parametrize("layout", ["no session", "workers not up", "collecting", "collection ended", "finished"])
def test_a_lane_cancelled_before_any_test_started_has_complete_typed_evidence(tmp_path, monkeypatch, layout):
    # "finished": interrupted gracefully during start-up, the session finished with a report of no results (#579, M1).
    raw = tmp_path / "raw"
    rows = _starting_lane(raw, layout)
    if layout == "finished":
        (raw / "report.json").write_text(json.dumps(NOTHING_RAN))
        rows = []  # its workers are gone: no live phase is read, and its own files decide
    _collect(raw, rows, monkeypatch)
    record = json.loads((raw / "runner-resources-before-tests.txt").read_text())
    assert record["outcome"] == "cancelled before any test started" and record["observed_by"] == "cancel collection"
    assert [len(s["workers"]) for s in record["sessions"]] == {"no session": [], "workers not up": [0]}.get(layout, [2])
    check = _load("check_evidence_run")
    rows = []
    assert check.check_jobs(_published(tmp_path, raw, monkeypatch), [_cancelled_lane_job()], score_rows=rows) == []
    assert rows[0]["kind"] == f"superseded (by run {NEW['id']}) before tests" and rows[0]["A2"] == "yes"


@pytest.mark.parametrize("layout", ["serial", "executing", "finished without a report", "finished after a test",
                                    "finished without a receipt", "finished past execution",
                                    "finished with an incomplete report", "finished with a result collected nothing"])
def test_a_cancelled_lane_whose_tests_may_have_begun_is_never_typed_before_tests(tmp_path, monkeypatch, layout):
    # A serial controller runs its own tests and keeps no lifecycle receipt, and a worker past its first test has begun
    # its tests. A finished session is shown not to have begun one only by its receipts and its lane report. None of
    # these is shown to stand before its first test, so the gap stays a defect.
    raw = tmp_path / "raw"
    rows = _starting_lane(raw, "executing" if layout == "finished past execution" else layout.split()[0])
    result = {"tests/test_a.py::test_a": {"outcome": "passed"}}
    if layout == "finished past execution":
        # A worker's receipt reached its first test's protocol (#579 quick check, m4).
        (raw / "autopsy/session-42-abc/session-finished.txt").write_text("finished\n")
        (raw / "report.json").write_text(json.dumps(NOTHING_RAN))
    elif layout == "finished with an incomplete report":
        (raw / "report.json").write_text(json.dumps({**NOTHING_RAN, "complete": False}))
    elif layout == "finished with a result collected nothing":
        # Under xdist the controller fills `collected` only as each worker goes down, so an empty list proves nothing.
        (raw / "report.json").write_text(json.dumps({**NOTHING_RAN, "results": result}))
    elif layout == "finished after a test":
        (raw / "report.json").write_text(json.dumps({**NOTHING_RAN, "collected": ["tests/test_a.py::test_a"],
                                                     "results": {"tests/test_a.py::test_a": {"outcome": "passed"}}}))
    elif layout == "finished without a receipt":
        (raw / "report.json").write_text(json.dumps(NOTHING_RAN))
        (raw / "autopsy/session-42-abc/worker-102-204-lifecycle.txt").unlink()
    _collect(raw, rows if layout.split()[0] != "finished" else [], monkeypatch)
    assert not (raw / "runner-resources-before-tests.txt").exists()
    check = _load("check_evidence_run")
    defects = check.check_jobs(_published(tmp_path, raw, monkeypatch), [_cancelled_lane_job()])
    assert any("[death-record] cancel: no pre-cleanup worker observation" in d for d in defects)
    assert any("[running] missing running test name" in d for d in defects)


@pytest.mark.parametrize("contradiction", ["execution started", "unlisted session", "unlisted worker", "running name",
                                           "torn record", "finished", "test result", "collection error",
                                           "receipt missing", "start mismatch", "receipt short of the phase",
                                           "a test's autopsy"])
def test_a_before_tests_record_the_bundle_contradicts_is_a_defect(tmp_path, monkeypatch, contradiction):
    raw = tmp_path / "raw"
    _collect(raw, _starting_lane(raw, "collection ended" if contradiction == "receipt short of the phase"
                                 else "collecting"), monkeypatch)
    session = raw / "autopsy/session-42-abc"
    if contradiction == "receipt missing":
        (session / "worker-101-202-lifecycle.txt").unlink()
    elif contradiction == "start mismatch":
        (session / "worker-gw0-start.txt").write_text("999\n")
    elif contradiction == "receipt short of the phase":
        (session / "worker-101-202-lifecycle.txt").write_text("10 collecting 7\n")
    elif contradiction == "a test's autopsy":
        test = raw / "autopsy/tests_unit_test_a.py_test_a-0123"
        test.mkdir()
        (test / "reason.txt").write_text("[gw0 pid 101] tests/unit/test_a.py::test_a: failed in call\n")
    elif contradiction == "execution started":
        with (session / "worker-101-202-lifecycle.txt").open("a") as receipt:
            receipt.write("30 collection-ended 7\n40 execution-started 7\n")
    elif contradiction == "unlisted session":
        other = raw / "autopsy/session-77-def"
        other.mkdir()
        (other / "session-started.txt").write_text("started")
    elif contradiction == "unlisted worker":
        (session / "worker-gw2-pid.txt").write_text("103\n")
    elif contradiction == "running name":
        (raw / "running-101.txt").write_text("tests/integration/test_a.py::test_case\n")
    elif contradiction in {"test result", "collection error"}:
        phase = "collect" if contradiction == "collection error" else "call"
        failure = {"phase": phase, "longrepr": "E   ValueError: cause", "crash": "test_a.py:5: ValueError: cause"}
        (raw / "report.json").write_text(json.dumps({
            "schema": "aew/lane-report/v1", "complete": False, "exitstatus": None,
            "results": {"tests/test_a.py::test_a": {"outcome": "failed", "failures": [failure]}}}))
    elif contradiction == "torn record":
        (raw / "runner-resources-before-tests.txt").write_text('{"outcome": "cancelled before any test started"}\n')
    else:
        (session / "session-finished.txt").write_text("finished")
    check = _load("check_evidence_run")
    rows = []
    defects = check.check_jobs(_published(tmp_path, raw, monkeypatch), [_cancelled_lane_job()], score_rows=rows)
    if contradiction == "collection error":
        # Collection fails before any test starts, so it never contradicts the record; the failure is still reported.
        assert not any("[before-tests]" in d for d in defects) and rows[0]["failed_nodes"]
    elif contradiction == "running name":
        # A running name is a death marker: the cancellation is checked as one that interrupted a test.
        assert rows[0]["kind"] == f"superseded (by run {NEW['id']})" and defects
    else:
        assert any("[before-tests]" in d for d in defects) and rows[0]["A2"] == "no"
        if contradiction == "a test's autopsy":
            assert any("[before-tests] autopsy/tests_unit_test_a.py_test_a-0123: a test's autopsy" in d
                       for d in defects), defects


@pytest.mark.parametrize("bounded_read", ["observed", "unavailable"])
def test_the_linux_supervisor_records_a_cancel_before_tests_at_the_signal(tmp_path, monkeypatch, bounded_read):
    import signal
    import sys
    from types import SimpleNamespace

    lane = _load("lane_step")
    rows = _starting_lane(tmp_path, "collecting")
    handlers, signals = {}, []
    process = SimpleNamespace(poll=lambda: None, send_signal=signals.append, kill=lambda: None, wait=lambda **_: None)
    monkeypatch.setattr(lane, "sys", SimpleNamespace(platform="linux", stdout=sys.stdout, stderr=sys.stderr))
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}, getpid=lambda: 99))
    monkeypatch.setattr(lane.proctree, "identity", lambda pid: (pid, 1))
    monkeypatch.setattr(lane.proctree, "table", lambda: {})
    monkeypatch.setattr(lane.proctree, "descendants", lambda *_: [])
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", lambda *_args, **_kw: handlers[signal.SIGINT](signal.SIGINT, None))
    monkeypatch.setattr(lane, "collect", lambda _: None)
    monkeypatch.setattr(lane, "memory_used", lambda: None)
    monkeypatch.setattr(lane.worker_evidence, "phases_at_signal", lambda root, at_ns: rows)
    monkeypatch.setattr(lane.worker_evidence, "Monitor", lambda *_: SimpleNamespace(poll=lambda **_: None))
    if bounded_read == "unavailable":
        # The bounded read of the phases ran out: the supervisor reads them itself, from the receipts.
        monkeypatch.setattr(lane, "interrupt_phases", lambda root, at: {"monotonic_ns": at, "status": "unavailable"})
    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60) == 130
    assert signals == [signal.SIGINT]
    record = json.loads((tmp_path / "runner-resources-before-tests.txt").read_text())
    assert record["observed_by"] == "warning"
    assert [(w["worker"], w["phase"]) for w in record["sessions"][0]["workers"]] == [
        ("worker-gw0", "collecting"), ("worker-gw1", "collecting")]


@pytest.mark.parametrize("sign", ["watchdog header", "running name"])
def test_a_before_tests_record_is_never_written_while_a_test_is_in_flight(tmp_path, sign):
    from types import SimpleNamespace

    import watchdog
    import worker_evidence

    rows = _starting_lane(tmp_path, "collecting")
    if sign == "watchdog header":
        guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
        (tmp_path / "hang-gw0-101.txt").write_text(guard._header(SimpleNamespace(nodeid="tests/test_a.py::test_a")))
    else:
        (tmp_path / "running-101.txt").write_text("tests/test_a.py::test_a\n")
    assert not worker_evidence.before_tests(tmp_path, 1.0, rows, observer="cancel collection")
    assert not (tmp_path / "runner-resources-before-tests.txt").exists()


@pytest.mark.parametrize("ran", ["lane report", "finished session"])
def test_the_hosted_twin_finds_a_lane_whose_tests_ran_claimed_as_cancelled_before_them(tmp_path, monkeypatch, ran):
    verify = _load("verify_evidence")
    raw = tmp_path / "raw"
    _starting_lane(raw, "finished" if ran == "finished session" else "no session")
    if ran == "lane report":
        (raw / "report.json").write_text(json.dumps({"schema": "aew/lane-report/v1", "complete": True, "exitstatus": 0,
                                                      "results": {"tests/test_a.py::test_a": {"outcome": "passed"}}}))
    root = _published(tmp_path, raw, monkeypatch)
    if ran == "lane report":
        # As a hosted normal plant publishes: a passing lane has no priority (watchdog) bundle.
        import shutil

        shutil.rmtree(root / "evidence-before-attempt-1-watchdog")
    assert verify.before_tests_twin(root) == []
    for path in root.rglob("report.json"):
        path.unlink()
    for path in root.rglob("session-finished.txt"):
        path.unlink()
    # With nothing left that shows a test ran, the claim stands: the twin reports that its ablation survived.
    [survived] = verify.before_tests_twin(root)
    assert survived.startswith("before-tests: before-tests ablation survived:") and "[before-tests]" not in survived


@pytest.mark.parametrize("branch", ["watchdog header", "interruption record", "running name"])
def test_the_checker_finds_each_sign_of_a_test_outside_the_sessions(tmp_path, monkeypatch, branch):
    # Called directly, as the hosted proof does: each sign is its own before-tests contradiction (#579, m2).
    from types import SimpleNamespace

    import watchdog

    evidence_problems = _load("evidence_problems").evidence_problems
    raw = tmp_path / "raw"
    _collect(raw, _starting_lane(raw, "collecting"), monkeypatch)
    root = _published(tmp_path, raw, monkeypatch)
    assert not [p for p in evidence_problems(root, kind="cancel-before-tests") if "[before-tests]" in p]
    bundle = root / "evidence-before-attempt-1"
    if branch == "watchdog header":
        guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
        (bundle / "hang-gw0-101.txt").write_text(guard._header(SimpleNamespace(nodeid="tests/test_a.py::test_a")))
        expected = "hang-gw0-101.txt: a test was in flight"
    elif branch == "interruption record":
        (bundle / "cancelled-101.txt").write_text("{}\n")
        expected = "cancelled-101.txt: a worker was observed in a test"
    else:
        (bundle / "running-101.txt").write_text("tests/test_a.py::test_a\n")
        expected = "a running test name was published"
    assert f"evidence defect: [before-tests] {expected}" in evidence_problems(root, kind="cancel-before-tests")


def test_every_lane_command_keeps_its_sessions_where_the_collection_looks():
    """The before-tests record reads no session under the lane root as "pytest had not registered one". That holds
    only while every command the lane action runs passes --session-deadline, and its hang directory (--hang-dir, else
    the lane report's directory) is the lane root or one level under it, where session_directories looks (#579, m3)."""
    import re
    import shlex

    import bounds

    seen, problems = 0, []
    for workflow in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for job in yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"].values():
            for step in job.get("steps") or []:
                if step.get("uses") != "./.github/actions/lane":
                    continue
                source = re.sub(r"\$\{\{[^}]*\}\}", "X", step["with"]["source"]).rstrip("/")
                for command, _ in bounds._commands(str(step["with"]["command"])):
                    seen += 1
                    argv = shlex.split(re.sub(r"\$\{\{[^}]*\}\}", "X", command))
                    hang = bounds._option(argv, "--hang-dir") or (bounds._option(argv, "--lane-report") or "")
                    hang = hang.rstrip("/") if bounds._option(argv, "--hang-dir") else hang.rsplit("/", 1)[0]
                    below = hang.removeprefix(source + "/") if hang.startswith(source + "/") else None
                    if bounds._option(argv, "--session-deadline") is None or not (
                            hang == source or below is not None and "/" not in below):
                        problems.append(f"{workflow.name}: {command[:80]}")
    assert seen >= 10 and problems == [], problems


@pytest.mark.parametrize("outcome", ["held", "twin late", "ended early"])
def test_the_start_up_control_cancels_only_once_both_lanes_hold_their_collection(monkeypatch, outcome):
    # The hosted row for the before-tests record (#579, M1): both start-up lanes run START_READY_SECONDS before the
    # control cancels, inside the plant's hold; a lane that ended first is named, as runner queueing when its twin
    # was not yet held, and never passes.
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import cancel_evidence_plant

    prove = _load("prove_cancel_evidence")
    import importlib.util

    spec = importlib.util.spec_from_file_location("startup", ROOT / "tests/integration/evidence_plants/startup.py")
    startup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(startup)  # outside a start-up plant its import holds nothing
    assert prove.START_READY_SECONDS + 60 < startup.HOLD_S < prove.CANCEL_PLANT_SECONDS
    waits = []

    def now():
        return sum(waits)

    clock = SimpleNamespace(monotonic=now, time=now, sleep=waits.append)
    monkeypatch.setattr(prove, "time", clock)
    monkeypatch.setattr(cancel_evidence_plant, "time", clock)

    def jobs(repo, endpoint):
        rows = []
        for index, os_name in enumerate(("ubuntu-24.04", "windows-latest")):
            # "ended early": Windows has held its collection long enough when Linux's lane ends.
            started = 30 + (400 if outcome == "twin late" else -60 if outcome == "ended early" else 0) * index
            running = now() >= started
            ended = outcome == "ended early" and index == 0 and now() >= started + 40
            stamp = datetime.fromtimestamp(started, UTC).isoformat()
            rows.append({"id": index + 1, "name": f"plant ({os_name}, cancel-start, none)", "runner_id": 7,
                         "conclusion": None, "steps": [{
                             "name": "Real planted lane", "started_at": stamp if running else None,
                             "status": "completed" if ended else "in_progress"}]})
        return {"jobs": rows}

    monkeypatch.setattr(prove, "_api", jobs)
    if outcome == "held":
        assert [job["id"] for job in prove.wait_for_start_up("x/y", 42)] == [1, 2]
        assert now() >= 30 + prove.START_READY_SECONDS
    elif outcome == "twin late":
        # Linux's lane ends at its deadline while Windows has no lane yet: the queueing is named.
        def late(repo, endpoint):
            rows = jobs(repo, endpoint)
            if now() >= 30 + 360:
                rows["jobs"][0]["steps"][0]["status"] = "completed"
            return rows

        monkeypatch.setattr(prove, "_api", late)
        with pytest.raises(prove.PlantQueued, match="cancel-start, none\\) was not held"):
            prove.wait_for_start_up("x/y", 42)
    else:
        with pytest.raises(RuntimeError, match="lane ended before its start-up cancellation") as failed:
            prove.wait_for_start_up("x/y", 42)
        assert not isinstance(failed.value, prove.PlantQueued)


def test_a_controller_ended_by_the_cancellation_still_lets_the_lane_be_typed_before_tests(tmp_path, monkeypatch):
    # The sentinel writes abnormal-exit when the cancellation ends the controller unfinished: that is the cancellation's
    # own death, not a test interrupted, so it does not keep the lane from its before-tests typing (#579, M1).
    raw = tmp_path / "raw"
    _collect(raw, _starting_lane(raw, "collecting"), monkeypatch)
    (raw / "autopsy/session-42-abc/abnormal-exit.txt").write_text("the controller is gone without session-finished\n")
    check = _load("check_evidence_run")
    rows = []
    assert check.check_jobs(_published(tmp_path, raw, monkeypatch), [_cancelled_lane_job()], score_rows=rows) == []
    assert rows[0]["kind"] == f"superseded (by run {NEW['id']}) before tests" and rows[0]["A2"] == "yes"


@pytest.mark.parametrize("kind", ["manual-or-api cancel", "manual-or-api cancel before tests"])
def test_the_start_up_control_fails_a_target_not_typed_before_tests(monkeypatch, kind):
    # The start-up control's accepted side (#579 quick check, m5): a target job with complete evidence that is not
    # typed "before tests" fails the control.
    prove = _load("prove_cancel_evidence")
    monkeypatch.setenv("GITHUB_REPOSITORY", "x/y")
    monkeypatch.setenv("GITHUB_RUN_ID", "7")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    parent = {"workflow_id": 3, "head_sha": "a" * 40, "head_branch": "b",
              "path": ".github/workflows/evidence-proof.yml"}
    target = {"id": 42, "status": "completed", "conclusion": "cancelled", "run_attempt": 1}
    monkeypatch.setattr(prove, "_api", lambda repo, endpoint: parent if endpoint == "actions/runs/7" else target)
    monkeypatch.setattr(prove, "dispatch", lambda *args: None)
    monkeypatch.setattr(prove, "target_run", lambda *args: target)
    monkeypatch.setattr(prove, "wait_for_start_up", lambda repo, ident: [{"id": 1}, {"id": 2}])
    monkeypatch.setattr(prove, "_gh_read", lambda *args: b"HTTP/2 200\r\ndate: Wed, 25 Nov 2026 14:40:00 GMT\r\n")
    reason = {"kind": "manual-or-api", "message": CANCEL.MANUAL, "actor": "github-actions[bot]"}
    rows = [{"job": job, "missing": [], "cancel_reason": reason, "A2": "yes", "artifacts": [9],
             "kind": kind.replace("manual-or-api ", "superseded (by run 1) ")} for job in (1, 2)]
    monkeypatch.setattr(prove, "inspect_run", lambda *args, **kwargs: rows)
    monkeypatch.setattr(prove, "run_jobs", lambda *args: [])
    monkeypatch.setattr(prove, "classify", lambda *args: {"kind": "unresolved"})
    if kind.endswith("before tests"):
        prove.main("start")
    else:
        with pytest.raises(RuntimeError, match="was not typed as cancelled before tests"):
            prove.main("start")
