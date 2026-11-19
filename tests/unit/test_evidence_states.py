"""Published evidence distinguishes an event from a timer that was only armed."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import session_deadline
import watchdog
from evidence_files import state
from test_ci_tools import ROOT, _load


@pytest.mark.parametrize("payload,expected", [
    (b"", "empty"),
    (b"armed 2026-01-01T00:00:00Z for 60s; not fired\n", "armed-placeholder"),
    (b"armed now for 60s; not fired\nTimeout (0:01:00)!\n<no Python frame>\n", "finding"),
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
    assert b"armed " in before and b"not fired" in before
    timer.arm()
    assert timer.path.read_bytes() == before
    timer.drop()
    assert not timer.path.exists()


def test_an_arm_header_never_claims_the_watchdog_fired(tmp_path):
    config = SimpleNamespace(getoption=lambda *args: str(tmp_path) if args[0] == "aew_hang_dir" else None)
    timer = watchdog.HangWatchdog(config, 600)
    timer.started = watchdog.time.monotonic()
    header = timer._header(SimpleNamespace(nodeid="tests/unit/test_a.py::test_wait"))
    assert "started " in header and "limit 600s; not fired" in header
    assert "was still running" not in header and "every thread's stack" not in header


@pytest.mark.parametrize("label", ["finding", "armed-placeholder", "empty"])
def test_every_published_state_has_an_ablated_twin(tmp_path, label):
    check = _load("check_assurance")
    payloads = {"finding": 'Thread 123:\n  File "tests/unit/test_a.py", line 12 in test_wait\n',
                "armed-placeholder": "armed now for 600s; not fired\n", "empty": ""}
    (tmp_path / "hang-gw0-123.txt").write_text(payloads[label])
    inventory = tmp_path / "inventory.txt"
    inventory.write_text(f"gitleaks clean\n{label} hang-gw0-123.txt (watchdog)\n")
    assert check.evidence_problems(tmp_path) == []
    inventory.write_text("gitleaks clean\n")
    assert any("publication state" in p for p in check.evidence_problems(tmp_path))


def test_every_workflow_pytest_step_uses_the_lane_action_and_all_publication_is_unconditional():
    import yaml

    sources = [*(ROOT / ".github/workflows").glob("*.yml"),
               *(ROOT / ".github/actions").glob("*/action.yml")]
    for path in sources:
        doc = yaml.safe_load(path.read_text())
        containers = [*doc.get("jobs", {}).values()]
        if "runs" in doc:
            containers.append(doc["runs"])
        for job in containers:
            for step in job.get("steps", []):
                assert "-m pytest" not in step.get("run", ""), (path, step)
    lane = yaml.safe_load((ROOT / ".github/actions/lane/action.yml").read_text())["runs"]["steps"]
    collect = next(i for i, step in enumerate(lane) if "--collect" in step.get("run", ""))
    for index, step in enumerate(lane):
        if index:
            assert step.get("if", "").startswith("always()"), step
        if "upload-artifact" in step.get("uses", ""):
            assert index > collect
    publisher = yaml.safe_load((ROOT / ".github/actions/publish-evidence/action.yml").read_text())
    assert all(step.get("if", "").startswith("always()") for step in publisher["runs"]["steps"])


def test_dropping_an_ablation_expectation_fails_the_hosted_verifier(monkeypatch):
    verify = _load("verify_evidence")
    problems = ["evidence defect: hang-gw0.txt: false publication state"]
    assert verify.ablation_problem("zero-byte", problems) is None
    monkeypatch.delitem(verify.ABLATIONS, "zero-byte")
    assert "has no expectation" in verify.ablation_problem("zero-byte", problems)


def test_the_publication_budget_detects_an_unbounded_post_test_step(tmp_path):
    import bounds
    import yaml

    source = ROOT / ".github/workflows/ci.yml"
    doc = yaml.safe_load(source.read_text())
    assert bounds.job_deadline_problems(source.parent) == []
    doc["jobs"]["lanes"]["steps"][-1].pop("timeout-minutes")
    (tmp_path / "ci.yml").write_text(yaml.safe_dump(doc))
    assert any("no timeout-minutes" in problem for problem in bounds.job_deadline_problems(tmp_path))


def test_priority_preparation_keeps_deadline_stacks_and_the_publisher_labels_every_file(tmp_path, monkeypatch):
    import json

    stage = _load("stage_evidence")
    inputs = _load("evidence_inputs")
    source = tmp_path / "source"
    session = source / "autopsy/session-123-test"
    session.mkdir(parents=True)
    (source / "hang-gw0-123.txt").write_text("aew hang watchdog: tests/unit/test_a.py::test_wait started now; "
                                            "limit 600s; not fired; monotonic 1\n")
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
    assert _load("check_assurance").evidence_problems(output) == []


def test_a_lost_scanned_bundle_is_still_matched_to_its_job_by_typed_source_names(tmp_path):
    import hashlib
    import json

    check = _load("check_evidence_run")
    label = "integration 1/1 (ubuntu-latest)"
    names = tmp_path / "plant-attempt-1-running"
    names.mkdir()
    (names / "job-label-sha256.txt").write_text(hashlib.sha256(label.encode()).hexdigest())
    (names / "running-123.txt").write_text("tests/unit/test_a.py::test_wait\n")
    (names / "inventory.txt").write_text("typed source names\nfinding job-label-sha256.txt (evidence_inputs)\n"
                                        "finding running-123.txt (watchdog)\n")
    scanned = tmp_path / "plant-attempt-1-watchdog"
    scanned.mkdir()
    (scanned / "inventory.txt").write_text("gitleaks scan unavailable\n")
    jobs = [{"name": label, "conclusion": "failure", "steps": []}]
    found = check.check_jobs(tmp_path, jobs)
    assert any("scan unavailable" in defect for defect in found), json.dumps(found)


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
    assert "limit 600s; not fired" in guard.path.read_text()
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

    monkeypatch.setattr(lane.subprocess, "run", spy)
    seen = set()
    path = tmp_path / "hang-gw0-123.txt"
    path.write_text("aew hang watchdog: tests/unit/test_a.py::test_first started now; "
                    "limit 10s; not fired; monotonic 500\n")
    lane.snapshot(tmp_path, seen=seen)
    path.write_text("aew hang watchdog: tests/unit/test_a.py::test_second started now; "
                    "limit 10s; not fired; monotonic 501\n")
    lane.snapshot(tmp_path, seen=seen)
    lane.snapshot(tmp_path, seen=seen)
    assert len(calls) == 2
    assert "test_second" in (tmp_path / "snapshots/123.txt").read_text()


def test_an_unregistered_writer_fails_after_the_real_staging_filter(tmp_path, monkeypatch):
    stage = _load("stage_evidence")
    source = tmp_path / "source"
    source.mkdir()
    (source / "new-writer.txt").write_text("unexpected evidence writer\n")
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    published = tmp_path / "published"
    stage.stage(source, published)
    assert any("unlisted writer" in problem for problem in _load("check_assurance").evidence_problems(published))


def test_looped_sessions_use_the_same_writer_registry():
    from evidence_files import owner

    assert owner(Path("rep-1/autopsy/session-123-test/controller-deadline-stacks.txt")) is not None
    assert owner(Path("real/autopsy/test_case/stacks.gw0-1.txt")) is not None
