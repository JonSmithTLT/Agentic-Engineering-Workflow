"""Published evidence distinguishes an event from a timer that was only armed."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import session_deadline
import watchdog
from evidence_files import ARMED_NOTE, state
from test_ci_tools import ROOT, _load


@pytest.mark.parametrize("message,path,level,expected", [
    ("The action has timed out.", ".github", "failure", True),
    ("The action has timed out.", "tests/test_sample.py", "failure", False),
    ("The action has timed out.", ".github", "warning", False),
    ("The action timed out in a test.", ".github", "failure", False),
    ("The action 'Run a test' has timed out after 2 minutes.", ".github", "failure", True),
])
def test_recognizes_hosted_timeout_annotation(monkeypatch, message, path, level, expected):
    check = _load("check_evidence_run")
    rows = [{"message": message, "path": path, "annotation_level": level}]
    monkeypatch.setattr(check, "_pages", lambda *_: rows)
    assert check.hosted_step_timeout("owner/repo", {"check_run_url": "https://host/123"}) is expected


@pytest.mark.parametrize("payload,expected", [
    (b"", "empty"),
    (b"armed 2026-01-01T00:00:00Z for 60s; a dump below records a fire\n", "armed-placeholder"),
    (b"armed now for 60s; a dump below records a fire\nTimeout (0:01:00)!\n<no Python frame>\n", "finding"),
    (b'armed\nThread 123:\n  File "tests/unit/test_a.py", line 12 in test_wait\n', "finding"),
])
def test_deadline_state_requires_frames(payload, expected):
    assert state(Path("controller-deadline-stacks.txt"), payload) == expected


def test_a_deadline_arm_is_written_once_and_an_unfired_file_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(session_deadline.faulthandler, "dump_traceback_later", lambda *a, **kw: None)
    monkeypatch.setattr(session_deadline.faulthandler, "cancel_dump_traceback_later", lambda: None)
    timer = session_deadline.Stacks(tmp_path / "deadline.txt", session_deadline.time.monotonic() + 60)
    timer.arm()
    before = timer.path.read_bytes()
    assert b"armed " in before and ARMED_NOTE.encode() in before
    timer.arm()
    assert timer.path.read_bytes() == before
    timer.drop()
    assert not timer.path.exists()


def test_an_arm_header_never_claims_the_watchdog_fired(tmp_path):
    config = SimpleNamespace(getoption=lambda *args: str(tmp_path) if args[0] == "aew_hang_dir" else None)
    timer = watchdog.HangWatchdog(config, 600)
    timer.started = watchdog.time.monotonic()
    header = timer._header(SimpleNamespace(nodeid="tests/unit/test_a.py::test_wait"))
    assert "started " in header and "limit 600s; a dump below records a fire" in header
    assert "was still running" not in header and "every thread's stack" not in header


def test_a_fired_deadline_file_keeps_the_dump_and_a_truthful_header(tmp_path, monkeypatch):
    def fire(_delay, *, file):
        file.write('Timeout (0:00:01)!\n  File "tests/unit/test_a.py", line 2 in test_wait\n')
        file.flush()

    monkeypatch.setattr(session_deadline.faulthandler, "dump_traceback_later", fire)
    monkeypatch.setattr(session_deadline.faulthandler, "cancel_dump_traceback_later", lambda: None)
    timer = session_deadline.Stacks(tmp_path / "worker-gw0-deadline-stacks.txt", watchdog.time.monotonic() + 60)
    timer.arm()
    timer.drop()
    data = timer.path.read_bytes()
    assert ARMED_NOTE.encode() in data.splitlines()[0] and b"not fired" not in data.splitlines()[0]
    assert b"Timeout (" in data and state(timer.path, data) == "finding"


@pytest.mark.parametrize("label", ["finding", "armed-placeholder", "empty"])
def test_every_published_state_has_an_ablated_twin(tmp_path, label):
    check = _load("evidence_problems")
    payloads = {"finding": 'Thread 123:\n  File "tests/unit/test_a.py", line 12 in test_wait\n',
                "armed-placeholder": "armed now for 600s; a dump below records a fire\n", "empty": ""}
    (tmp_path / "hang-gw0-123.txt").write_text(payloads[label])
    inventory = tmp_path / "inventory.txt"
    inventory.write_text(f"gitleaks clean\nfinding inventory.txt (publisher)\n{label} hang-gw0-123.txt (watchdog)\n")
    assert check.evidence_problems(tmp_path) == []
    inventory.write_text("gitleaks clean\nfinding inventory.txt (publisher)\n")
    assert any("hang-gw0-123.txt: missing or false publication state" in p for p in check.evidence_problems(tmp_path))


def test_retained_workflows_use_lane_action_and_keep_names_and_reports_on_collect_failure():
    import yaml

    sources = [*(ROOT / ".github/workflows").glob("*.yml"),
               *(ROOT / ".github/actions").glob("*/action.yml")]
    for path in sources:
        if path.parent.name == "workflows" and path.name in {"discovery.yml", "unit-isolation-audit.yml"}:
            continue
        doc = yaml.safe_load(path.read_text())
        containers = [job for name, job in doc.get("jobs", {}).items()
                      if (path.name, name) != ("ci.yml", "fastbase")]
        if "runs" in doc:
            containers.append(doc["runs"])
        for job in containers:
            for step in job.get("steps", []):
                assert "-m pytest" not in step.get("run", ""), (path, step)
    lane = yaml.safe_load((ROOT / ".github/actions/lane/action.yml").read_text())["runs"]["steps"]
    collect = next(i for i, step in enumerate(lane) if "--collect" in step.get("run", ""))
    for index, step in enumerate(lane):
        if index >= collect:
            assert step.get("if", "").startswith("always()"), step
        if "upload-artifact" in step.get("uses", "") or step["name"] == "Prepare owned evidence inputs":
            assert index > collect and step["if"] == "always()", step
    publisher = yaml.safe_load((ROOT / ".github/actions/publish-evidence/action.yml").read_text())
    assert all(step.get("if", "").startswith("always()") for step in publisher["runs"]["steps"])
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    [download] = [step for step in ci["jobs"]["assurance"]["steps"]
                  if step.get("with", {}).get("path") == "evidence-artifacts"]
    assert download["with"]["pattern"] == "*evidence-*-attempt-${{ github.run_attempt }}*"


def test_each_checker_rule_names_a_hosted_ablation():
    import ast

    verify = _load("verify_evidence")
    rules = {
        node.args[0].value for name in ("evidence_problems", "check_evidence_run")
        for node in ast.walk(ast.parse((ROOT / "tools/ci" / f"{name}.py").read_text(encoding="utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "report"
    }
    twins = set((*verify.STATE_TWINS.values(), *verify.DEATH_TWINS.values(),
                 *verify.JOB_TWINS.values(), *verify.OTHER_TWINS.values()))
    assert rules == twins


def test_evidence_proof_triggers_only_on_schedule_dispatch_or_evidence_paths():
    import yaml

    proof = yaml.safe_load((ROOT / ".github/workflows/evidence-proof.yml").read_text(encoding="utf-8"))
    assert proof[True] == {
        "schedule": [{"cron": "41 3 * * *"}],
        "workflow_dispatch": None,
        "pull_request": {"paths": [
            ".github/actions/lane/**",
            ".github/actions/publish-evidence/**",
            ".github/actions/recover-lane/**",
            ".github/workflows/evidence-*.yml",
            "tests/helpers/watchdog.py",
            "tests/helpers/session_deadline.py",
            "tests/helpers/autopsy.py",
            "tests/helpers/evidence_files.py",
            "tests/helpers/worker_evidence.py",
            "tests/integration/evidence_plants/**",
            "tools/ci/lane_step.py",
            "tools/ci/*evidence*",
            "tools/flake_register.py",
        ]},
    }


def test_evidence_proof_cancels_superseded_runs_and_runs_cancel_plants_on_schedule_or_dispatch():
    import yaml

    proof = yaml.safe_load((ROOT / ".github/workflows/evidence-proof.yml").read_text(encoding="utf-8"))
    assert proof["concurrency"] == {
        "group": "evidence-proof-${{ github.event.pull_request.number || github.ref }}",
        "cancel-in-progress": True,
    }
    jobs = proof["jobs"]
    matrix = jobs["plant"]["strategy"]["matrix"]
    assert "cancel" not in matrix["kind"] and all(row["kind"] != "cancel" for row in matrix["include"])
    cancel = jobs["cancel-plant"]
    assert cancel["if"] == "github.event_name != 'pull_request'" and cancel["strategy"]["matrix"]["kind"] == ["cancel"]
    assert cancel["steps"] == jobs["plant"]["steps"]
    assert set(jobs["plant"]["needs"]) == {"cancel-trigger-linux", "cancel-trigger-windows"}
    for platform in ("linux", "windows"):
        ready = f"cancel-ready-{platform}"
        assert jobs[ready]["if"] == "github.event_name != 'pull_request'"
        trigger = jobs[f"cancel-trigger-{platform}"]
        assert trigger["needs"] == ready and trigger.get("if", "success()") == "success()"


def test_the_publication_budget_detects_an_unbounded_post_test_step(tmp_path):
    import bounds
    import yaml

    source = ROOT / ".github/workflows/ci.yml"
    doc = yaml.safe_load(source.read_text())
    assert bounds.job_deadline_problems(source.parent) == []
    doc["jobs"]["lanes"]["steps"][-1].pop("timeout-minutes")
    lane = next(step for step in doc["jobs"]["lanes"]["steps"] if step.get("uses") == "./.github/actions/lane")
    lane["timeout-minutes"] -= 1
    (tmp_path / "ci.yml").write_text(yaml.safe_dump(doc))
    problems = bounds.job_deadline_problems(tmp_path)
    assert any("no timeout-minutes" in problem for problem in problems)
    assert any("lane step needs" in problem for problem in problems)


def test_priority_preparation_keeps_deadline_stacks_and_the_publisher_labels_every_file(tmp_path, monkeypatch):
    import json

    stage = _load("stage_evidence")
    inputs = _load("evidence_inputs")
    source = tmp_path / "source"
    session = source / "autopsy/session-123-test"
    session.mkdir(parents=True)
    (source / "hang-gw0-123.txt").write_text("aew hang watchdog: tests/unit/test_a.py::test_wait started now; "
                                            "limit 600s; a dump below records a fire; monotonic 1\n")
    (session / "worker-gw0-deadline-stacks.txt").write_bytes(b"")
    (session / "stacks.gw0-1.txt").write_text('Thread 123:\n  File "tests/unit/test_a.py", line 2 in test_wait\n')
    (session / "reason.gw0-1.txt").write_text("tests/unit/test_a.py::test_wait: deadline passed\n")
    (session / "oversized.txt").write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    (source / "runner-resources-job.txt").write_text(json.dumps({"job_label": "integration 1/1 (ubuntu-latest)"}))
    present, priority = inputs.prepare(source, tmp_path / "job-watchdog-input")
    assert present and priority
    assert (tmp_path / "job-watchdog-input/autopsy/session-123-test/stacks.gw0-1.txt").exists()
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    output = tmp_path / "published"
    assert stage.stage(tmp_path / "job-watchdog-input", output) == "gitleaks clean"
    inventory = (output / "inventory.txt").read_text()
    assert "armed-placeholder hang-gw0-123.txt" in inventory
    assert "empty autopsy/session-123-test/worker-gw0-deadline-stacks.txt" in inventory
    assert "finding autopsy/session-123-test/stacks.gw0-1.txt" in inventory
    assert "omitted autopsy/session-123-test/oversized.txt" in inventory
    assert _load("evidence_problems").evidence_problems(output) == []


@pytest.mark.parametrize("omissions", [False, True])
def test_state_and_omission_rows_respect_the_inventory_cap(tmp_path, monkeypatch, omissions):
    stage = _load("stage_evidence")
    source = tmp_path / "source"
    autopsy = source / "autopsy"
    autopsy.mkdir(parents=True)
    for i in range(12):
        (autopsy / f"observation-{i:04}.txt").write_bytes(b"\x00" if omissions else b"observed")
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    monkeypatch.setattr(stage, "INDEX_CAP", 270)
    output = tmp_path / "published"
    assert stage.stage(source, output) == "evidence defect: inventory cap exceeded"
    inventory = output / "inventory.txt"
    assert list(output.iterdir()) == [inventory]
    assert inventory.stat().st_size <= stage.INDEX_CAP
    assert "observation-" not in inventory.read_text()
    assert "evidence defect: [cap] inventory cap exceeded" in _load("evidence_problems").evidence_problems(output)


def test_a_lost_scanned_bundle_is_still_matched_to_its_job_by_typed_source_names(tmp_path):
    import hashlib
    import json

    check = _load("check_evidence_run")
    label = "integration 1/1 (ubuntu-latest)"
    names = tmp_path / "plant-attempt-1-running"
    names.mkdir()
    (names / "job-label-sha256.txt").write_text(hashlib.sha256(label.encode()).hexdigest())
    (names / "running-123.txt").write_text("tests/unit/test_a.py::test_wait\n")
    inventory = names / "inventory.txt"
    listing = "typed source names\nfinding inventory.txt (publisher)\nfinding job-label-sha256.txt (evidence_inputs)\n"
    inventory.write_text(listing + "finding running-123.txt (watchdog)\n")
    check_states = _load("evidence_problems").evidence_problems
    assert check_states(names) == []
    inventory.write_text(listing)
    assert any("running-123.txt: missing or false publication state" in defect for defect in check_states(names))
    scanned = tmp_path / "plant-attempt-1-watchdog"
    scanned.mkdir()
    (scanned / "inventory.txt").write_text("gitleaks scan unavailable\n")
    jobs = [{"name": label, "conclusion": "failure", "steps": []}]
    found = check.check_jobs(tmp_path, jobs)
    assert any("scan unavailable" in defect for defect in found), json.dumps(found)


def test_collection_failure_preserves_names_even_when_a_live_file_disappears(tmp_path, monkeypatch):
    inputs = _load("evidence_inputs")
    source = tmp_path / "source"
    source.mkdir()
    (source / "hang-gw0-1.txt").write_text("working file\n")
    (source / "running-1.txt").write_text("tests/unit/test_a.py::test_wait\n")

    def vanished(*_args):
        raise FileNotFoundError("writer moved it")

    monkeypatch.setattr(inputs.shutil, "copyfile", vanished)
    inputs.prepare(source, tmp_path / "evidence-watchdog-input", job="fast", collection="failure")
    names = tmp_path / "evidence-names"
    assert (names / "running-1.txt").read_text() == "tests/unit/test_a.py::test_wait\n"
    assert (names / "collection-incomplete.txt").is_file()
    assert _load("verify_evidence").rule_ids(_load("evidence_problems").evidence_problems(names)) == {"collection"}


@pytest.mark.parametrize("code,ablation,rule", [(70, None, "job-kind"), (1, "stacks", "job-ablation")],
                         ids=["death-marker", "real-lane-ablation"])
def test_assurance_detects_missing_death_kind_and_live_ablation(tmp_path, code, ablation, rule):
    import json

    inputs = _load("evidence_inputs")
    source = tmp_path / "source"
    source.mkdir()
    job = {"name": "fast 1/1 (ubuntu-latest)", "conclusion": "failure", "steps": []}
    bundles = tmp_path / "bundles"
    inputs.prepare(source, bundles / "lane-watchdog-input", job=job["name"])
    names = (bundles / "lane-names").rename(bundles / "lane-running")
    record = names / "runner-resources-step-exit.txt"
    record.write_text(json.dumps({"command_exit": code, "ablation": ablation}), encoding="utf-8")
    verify = _load("verify_evidence")
    verify.label(names / "inventory.txt", record, "lane_step")
    assert verify.rule_ids(_load("check_evidence_run").check_jobs(bundles, [job])) == {rule}


def test_an_interrupted_protocol_keeps_its_truthful_header_and_source_name(tmp_path, monkeypatch):
    class Plugins:
        def get_plugin(self, name):
            return None

    config = SimpleNamespace(pluginmanager=Plugins(),
                             getoption=lambda *args: str(tmp_path) if args[0] == "aew_hang_dir" else None)
    monkeypatch.setattr(watchdog, "USE_ALARM", False)
    monkeypatch.setattr(watchdog.faulthandler, "dump_traceback_later", lambda *args, **kwargs: None)
    monkeypatch.setattr(watchdog.faulthandler, "cancel_dump_traceback_later", lambda: None)
    guard = watchdog.HangWatchdog(config, 600)
    guard.running = tmp_path / "running-123.txt"
    protocol = guard.pytest_runtest_protocol(SimpleNamespace(nodeid="tests/unit/test_a.py::test_wait"), None)
    next(protocol)
    with pytest.raises(KeyboardInterrupt):
        protocol.throw(KeyboardInterrupt())
    guard.pytest_unconfigure(config)
    assert "limit 600s; a dump below records a fire" in guard.path.read_text()
    assert guard.running.read_text() == "tests/unit/test_a.py::test_wait\n"


def test_a_standalone_watchdog_cannot_overwrite_the_enclosing_workers_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("AEW_RUNNING_TESTS_DIR", str(tmp_path))
    config = SimpleNamespace(getoption=lambda *args: str(tmp_path) if args[0] == "aew_hang_dir" else None)
    assert watchdog.HangWatchdog(config, 600).running is None


def test_a_worker_gets_a_timeout_snapshot_for_each_new_test(tmp_path, monkeypatch):
    lane = _load("lane_step")
    session = tmp_path / "autopsy/session-123-test"
    session.mkdir(parents=True)
    monkeypatch.setattr(lane, "identities", lambda root: [(session, (123, 456))])
    monkeypatch.setattr(lane, "session_directories", lambda root: [session])
    monkeypatch.setattr(lane.proctree, "same", lambda identity: True)
    monkeypatch.setattr(lane.time, "monotonic", lambda: 1000)
    calls = []

    def spy(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='  File "tests/unit/test_a.py", line 2 in test_wait\n')

    monkeypatch.setattr(lane.shutil, "which", lambda _name: "py-spy")
    monkeypatch.setattr(lane.subprocess, "run", spy)
    seen = set()
    path = tmp_path / "hang-gw0-123.txt"
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_args: str(tmp_path)), 10)
    guard.started = 500
    path.write_text(guard._header(SimpleNamespace(nodeid="tests/unit/test_a.py::test_first")))
    lane.snapshot(tmp_path, seen=seen)
    guard.started = 501
    path.write_text(guard._header(SimpleNamespace(nodeid="tests/unit/test_a.py::test_second")))
    lane.snapshot(tmp_path, seen=seen)
    lane.snapshot(tmp_path, seen=seen)
    assert len(calls) == 2
    assert all("--full-filenames" in call for call in calls)
    assert "test_second" in (tmp_path / "snapshots/123.txt").read_text()


def test_the_hosted_verifier_uses_downloaded_lane_observations(tmp_path, capsys):
    from io import BytesIO

    lane = _load("lane_step")
    verify = _load("verify_evidence")
    heartbeat = {}
    lane.relay_heartbeat(BytesIO(b"evidence-heartbeat 1 98.0\nevidence-heartbeat 2 99.0\n"
                                  b"evidence-heartbeat 3 100.0\nevidence-gil-enter 100.1\n"), heartbeat)
    assert "evidence-gil-enter 100.1" in capsys.readouterr().err
    lane.record_exit(tmp_path, 70, None, [], lane_exit=70, heartbeat=heartbeat)
    assert verify.observation_problems(tmp_path, "Windows", "hang") == []
    lane.record_exit(tmp_path, -9, None, [], lane_exit=71, heartbeat=None)
    assert verify.observation_problems(tmp_path, "Linux", "time-limit") == []
    assert "expected lane exit 70" in verify.observation_problems(tmp_path, "Linux", "deadline")[0]
    lane.relay_heartbeat(BytesIO(b"evidence-heartbeat 4 102.0\n"), heartbeat)
    lane.record_exit(tmp_path, 70, None, [], lane_exit=70, heartbeat=heartbeat)
    assert "heartbeat did not stall" in verify.observation_problems(tmp_path, "Windows", "hang")[0]


def test_a_cutoff_snapshot_needs_the_full_tagged_test_path(tmp_path):
    check = _load("evidence_problems")
    node = "tests/integration/evidence_plants/deaths.py::test_death"
    (tmp_path / "running-123.txt").write_text(node + "\n")
    directory = tmp_path / "snapshots"
    directory.mkdir()
    snapshot = directory / "123.txt"
    (tmp_path / "inventory.txt").write_text("finding inventory.txt (publisher)\nfinding running-123.txt (watchdog)\n"
                                           "finding snapshots/123.txt (lane_step)\n")
    snapshot.write_text(f"snapshot 0.0 for {node}[time-limit], running 35.0s\n    test_death (deaths.py:59)\n")
    assert any("no stack" in defect for defect in check.evidence_problems(tmp_path, require_stacks=True))
    snapshot.write_text(f"snapshot 0.0 for {node}[time-limit], running 35.0s\n"
                        "    test_death (D:\\a\\repo\\tests\\integration\\evidence_plants\\deaths.py:59)\n")
    assert check.evidence_problems(tmp_path, require_stacks=True) == []


@pytest.mark.parametrize("scanner_only", [False, True])
def test_evidence_tools_install_independently_and_report_unavailable(tmp_path, monkeypatch, scanner_only):
    installer = _load("install_evidence")
    output = tmp_path / "outputs"
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_PATH", str(tmp_path / "path"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))

    def offline(_target):
        raise OSError("unavailable")

    monkeypatch.setattr(installer, "install_scanner", offline)
    calls = []
    monkeypatch.setattr(installer, "install_spy", calls.append)
    installer.main(scanner_only=scanner_only)
    assert output.read_text().splitlines() == (["scanner=false"] if scanner_only else ["scanner=false", "spy=true"])
    assert calls == ([] if scanner_only else [tmp_path / "evidence-tools"])


def test_an_unregistered_writer_fails_after_the_real_staging_filter(tmp_path, monkeypatch):
    stage = _load("stage_evidence")
    source = tmp_path / "source"
    source.mkdir()
    (source / "new-writer.txt").write_text("unexpected evidence writer\n")
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    published = tmp_path / "published"
    stage.stage(source, published)
    assert any("unlisted writer" in problem for problem in _load("evidence_problems").evidence_problems(published))


def test_looped_sessions_use_the_same_writer_registry():
    from evidence_files import owner

    assert owner(Path("rep-1/autopsy/session-123-test/controller-deadline-stacks.txt")) is not None
    assert owner(Path("real/autopsy/test_case/stacks.gw0-1.txt")) is not None


def test_a_parameter_that_mentions_file_does_not_become_a_captured_stack(tmp_path):
    config = SimpleNamespace(getoption=lambda *args: str(tmp_path) if args[0] == "aew_hang_dir" else None)
    guard = watchdog.HangWatchdog(config, 600)
    guard.started = watchdog.time.monotonic()
    node = 'tests/unit/test_a.py::test_wait[File "pretend.py"]'
    guard.path.write_text(guard._header(SimpleNamespace(nodeid=node)))
    report = SimpleNamespace(longrepr="worker crashed")
    guard.pytest_handlecrashitem(node, report, None)
    assert "stacks recorded" not in report.longrepr
    assert "armed-placeholder; no Python stack frames captured" in report.longrepr


def test_a_fixture_only_stack_does_not_stand_in_for_the_running_tests_frame(tmp_path):
    node = "tests/unit/test_a.py::test_wait"
    path = tmp_path / "hang-gw0-123.txt"
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_args: str(tmp_path)), 10)
    path.write_text(guard._header(SimpleNamespace(nodeid=node))
                    + '  File "tests/unit/test_a.py", line 1 in setup_fixture\n')
    (tmp_path / "inventory.txt").write_text("gitleaks clean\nfinding inventory.txt (publisher)\n"
                                          "finding hang-gw0-123.txt (watchdog)\n")
    assert any("no stack" in defect for defect in _load("evidence_problems").evidence_problems(
        tmp_path, require_stacks=True))


def test_a_red_custom_named_lane_cannot_lose_all_its_artifacts_silently(tmp_path):
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    fast = next(step for step in workflow["jobs"]["core"]["steps"]
                if step.get("uses") == "./.github/actions/lane" and "--lane fast" in step["with"]["command"])
    job = {"name": "fast 1/1 (ubuntu-latest)", "conclusion": "failure",
           "steps": [{"name": fast["name"], "started_at": "2026-01-01T00:00:00Z", "conclusion": "failure"}]}
    problems = _load("check_evidence_run").check_jobs(tmp_path, [job])
    assert any("no published evidence" in problem for problem in problems)


def test_a_successful_death_plant_still_requires_published_evidence(tmp_path):
    job = {"name": "plant (windows-latest, deadline, none)", "conclusion": "success",
           "steps": [{"name": "Real planted lane", "started_at": "2026-01-01T00:00:00Z", "conclusion": "success"}]}
    check = _load("check_evidence_run").check_jobs
    assert check(tmp_path, [job]) == []
    assert _load("verify_evidence").rule_ids(check(tmp_path, [job], include_success=True)) == {"job-evidence"}


def test_a_signal_before_the_cutoff_records_interruption_without_a_cutoff_marker(tmp_path, monkeypatch):
    import json
    import signal

    lane = _load("lane_step")
    handlers = {}
    signals = []
    process = SimpleNamespace(poll=lambda: None, send_signal=signals.append,
                              kill=lambda: None, wait=lambda **_kw: None)

    def snapshot(_root, *, all_workers=False, **_kw):
        if not all_workers:
            handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}))
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", snapshot)
    monkeypatch.setattr(lane, "collect", lambda _root: None)
    monkeypatch.setattr(lane, "identities", lambda _root: [(tmp_path, (123, 456))])

    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60) == 143
    assert signals == [signal.SIGTERM]
    assert not lane.marker(tmp_path, "cutoff").exists()
    record = json.loads((tmp_path / "runner-resources-step-exit.txt").read_text())
    assert record["step_signal"] == ["SIGTERM"]


def test_bounded_worker_ring_keeps_the_previous_node_and_matches_its_identity(tmp_path, monkeypatch):
    import json

    import worker_evidence as ev
    session = tmp_path / "autopsy/session-test"
    session.mkdir(parents=True)
    first = ev.Worker(session, 100, 110, "tests/test_a.py::test_first", 1, 120)
    last = ev.Worker(session, 100, 110, "tests/test_a.py::test_last", 2, 120)
    monkeypatch.setattr(ev, "RING_BYTES", 1000)
    frame = "process with private argv\n    test_first (tests/test_a.py:4)"
    for at in range(20):
        assert ev.save_sample(tmp_path, first, at, 1, "unelevated", frame, reason="periodic")
    path = ev.ring_path(tmp_path, first)
    assert path.stat().st_size <= ev.RING_BYTES
    assert path.read_text().startswith(ev.DROPPED) and "private argv" not in path.read_text()
    ev.record(tmp_path, last, "worker-killed", 20, exit=-9, signal=9)
    record = json.loads((session / "worker-killed-100.txt").read_text())
    assert record["node"] == last.node and record["snapshot_node"] == first.node and record["age_s"] == 1
    check = _load("evidence_problems").evidence_problems
    assert not any("[snapshot" in why for why in check(tmp_path, kind="worker-killed"))
    path.write_text(path.read_text().replace('"start": 110', '"start": 111'))
    assert any("[snapshot]" in why for why in check(tmp_path, kind="worker-killed"))


def test_file_classes_preserve_scanned_and_priority_publication(tmp_path, monkeypatch):
    from evidence_files import owner, priority, publishable

    stage, inputs = _load("stage_evidence"), _load("evidence_inputs")
    check = _load("evidence_problems").evidence_problems
    source = tmp_path / "source"
    cases = {
        "snapshots/123.txt": (True, True), "autopsy/session-1/worker-killed-123.txt": (True, True),
        "autopsy/case/reason.txt": (True, True), "harness-runs/case/info.txt": (True, False),
        "junit.xml": (True, False), "dispatch.txt": (True, False), "running-123.txt": (False, False),
        "report.json": (False, False),
    }
    for name, expected in cases.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("tests/test_a.py::test_a\n")
        assert owner(Path(name)) and (publishable(Path(name)), priority(Path(name))) == expected
    monkeypatch.setattr(stage, "scan", lambda *_args: {})
    partial = tmp_path / "partial"
    inputs.prepare(source, partial)
    for selected, bundle, idx in [(source, "out", 0), (partial, "out-watchdog", 1)]:
        target = tmp_path / bundle
        stage.stage(selected, target)
        assert {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()
                and p.name != "inventory.txt"} == {name for name, flags in cases.items() if flags[idx]}
        assert check(target) == []


def test_final_cgroup_read_keeps_a_kill_between_the_last_poll_and_exit(tmp_path, monkeypatch):
    import json

    import worker_evidence as ev

    group = tmp_path / "group"
    group.mkdir()
    for name, value in {"memory.current": "70", "memory.max": "100",
                        "memory.events": "oom 0\noom_kill 0\n"}.items():
        (group / name).write_text(value)
    monkeypatch.setattr(ev, "cgroup", lambda: group)
    monkeypatch.setattr(ev, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(ev, "dmesg_victim", lambda: "unavailable")
    monitor = ev.Monitor(tmp_path, None, lambda: set())
    monitor.poll()
    monitor.members.add((123, 456))
    (group / "memory.events").write_text("oom 1\noom_kill 1\n")
    monitor.poll(final=True)
    event = json.loads((tmp_path / "runner-resources-oom.txt").read_text())
    assert (event["oom_kill_before"], event["oom_kill_after"], event["members"]) == (0, 1, [[123, 456]])
    assert event["kernel_victim"] == "unavailable"


def test_no_xdist_controller_is_the_worker_only_while_its_own_watchdog_is_active(tmp_path):
    import os

    import proctree
    import worker_evidence as ev

    pid, birth = proctree.identity(os.getpid())
    directory = tmp_path / "autopsy/session-test"
    directory.mkdir(parents=True)
    for name, value in [("controller-pid", pid), ("controller-start", birth),
                        ("sentinel-pid", pid + 1), ("sentinel-start", birth + 1)]:
        (directory / f"{name}.txt").write_text(str(value))
    assert list(ev.workers(tmp_path)) == []
    node = "tests/test_a.py::test_wait[serial]"
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_args: str(tmp_path)), 10)
    (tmp_path / f"hang-main-{pid}.txt").write_text(guard._header(SimpleNamespace(nodeid=node)))
    [serial] = ev.workers(tmp_path)
    assert serial.identity == (pid, birth) and serial.node == node


@pytest.mark.parametrize("victim,expected", [(101, {101}), ("unavailable", set()), ("no matching worker", set())])
@pytest.mark.parametrize("sample_second", [False, True])
def test_one_cgroup_increase_does_not_label_a_second_simultaneous_crash(
        tmp_path, monkeypatch, victim, expected, sample_second):
    import json

    import worker_evidence as ev

    source = tmp_path / "source"
    directory = source / "autopsy/session-test"
    directory.mkdir(parents=True)
    for gateway, pid in enumerate((101, 202)):
        worker = ev.Worker(directory, pid, 23, f"tests/test_a.py::test_case[{pid}]", 0, 0)
        if pid == 101 or sample_second:
            assert ev.save_sample(source, worker, 9, 1, "unelevated", "    test_case (tests/test_a.py:4)",
                                  reason="periodic")
        ev.record(source, worker, "worker-killed", 10, signal=9)
        (directory.parent / f"worker-gw{gateway}-down.txt").write_text("worker crashed\n")
        (directory / f"worker-gw{gateway}-pid.txt").write_text(str(pid))
        (directory / f"worker-gw{gateway}-start.txt").write_text("23")
    event = {"at": 10, "members": [[101, 23], [202, 23]], "oom_kill_before": 0, "oom_kill_after": 1,
             "kernel_victim": victim}
    (source / "runner-resources-oom.txt").write_text(json.dumps(event))
    ev.record_oom(source)
    assert {int(path.stem.split("-")[1]) for path in directory.glob("oom-*.txt")} == expected
    (source / "runner-resources-job.txt").write_text(json.dumps({"job_label": "mixed"}))
    bundles = tmp_path / "bundles"
    bundles.mkdir()
    stage = _load("stage_evidence")
    monkeypatch.setattr(stage, "scan", lambda *_: {})
    assert stage.stage(source, bundles / "full") == "gitleaks clean"
    defects = _load("check_evidence_run").check_jobs(bundles, [{"name": "mixed", "conclusion": "failure"}])
    if sample_second:
        assert defects == []
    else:
        assert _load("verify_evidence").rule_ids(defects) == {"snapshot", "snapshot-age", "snapshot-label"}
        assert all("worker-killed pid 202" in defect for defect in defects)


@pytest.mark.parametrize("pid,birth,param,began,reason", [
    (202, 12, "current", 5., "periodic"), (101, 12, "current", 5., "warning"),
    (202, 11, "current", 5., "warning"), (202, 12, "old", 5., "warning"),
    (202, 12, "current", 4., "warning"), (202, 12, "current", 5., "warning"),
])
def test_only_the_current_invocations_own_warning_sample_can_satisfy_a_deadline(tmp_path, pid, birth, param, began,
                                                                              reason):
    import worker_evidence as ev

    directory = tmp_path / "autopsy/session-test"
    directory.mkdir(parents=True)
    (directory / "worker-gw0-pid.txt").write_text("202")
    (directory / "worker-gw0-start.txt").write_text("12")
    (directory / "session-deadline.txt").write_text("deadline")
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_args: str(tmp_path)), 10)
    guard.started = 5.
    active = SimpleNamespace(nodeid="tests/test_a.py::test_a[current]")
    (tmp_path / "hang-gw0-202.txt").write_text(guard._header(active))
    worker = ev.Worker(directory, pid, birth, f"tests/test_a.py::test_a[{param}]", began, 10)
    ev.save_sample(tmp_path, worker, 20, 10, "unelevated", "    test_a (tests/test_a.py:3)", reason=reason)
    check = _load("evidence_problems").evidence_problems
    defects = check(tmp_path, kind="deadline", require_stacks=True)
    assert (not any("[stacks]" in row for row in defects)) == (
        pid == 202 and birth == 12 and param == "current" and began == 5 and reason == "warning")


def test_deployed_lanes_recover_with_the_same_inputs_in_a_separate_bounded_step():
    import yaml

    for path in (ROOT / ".github/workflows").glob("*.yml"):
        for job in yaml.safe_load(path.read_text())["jobs"].values():
            steps = job.get("steps", [])
            for i, lane in enumerate(steps):
                if lane.get("uses") != "./.github/actions/lane":
                    continue
                if path.name == "evidence-proof.yml" and lane.get("id") != "timed":
                    continue
                following = steps[i + 1]
                assert following["uses"] == "./.github/actions/recover-lane" and following["timeout-minutes"] == 11
                for key in ("job-label", "source", "artifact"):
                    assert following["with"][key] == lane["with"][key], (path, key)
                assert following["if"].startswith("always() && ") and f"steps.{lane['id']}.outputs.finished" in (
                    following["if"])
                assert f"steps.{lane['id']}.outcome" in following["with"]["outcome"]


def test_republishing_the_same_report_keeps_one_observation_while_different_reports_remain(tmp_path):
    import json

    reader = _load("check_assurance")
    report = {"schema": reader.REPORT_SCHEMA, "platform": "linux", "lane": "fast", "attempt": 1, "exitstatus": 1}
    first = tmp_path / "lane-report-example-attempt-1/fast.json"
    second = tmp_path / "lane-report-example-attempt-1-recovered/fast.json"
    for file in (first, second):
        file.parent.mkdir()
        file.write_text(json.dumps(report))
    assert len(reader.load_reports(tmp_path)) == 1
    second.write_text(json.dumps({**report, "exitstatus": 2}))
    assert len(reader.load_reports(tmp_path)) == 2
    first.unlink()
    assert reader.load_reports(tmp_path)[0]["exitstatus"] == 2
