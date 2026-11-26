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
    monkeypatch.setattr(check, "check_annotations", lambda *_: rows)
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
        if path.parent.name == "workflows" and path.name == "discovery.yml":
            continue
        doc = yaml.safe_load(path.read_text())
        containers = list(doc.get("jobs", {}).values())
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
            condition = ("always() && steps.reports.outcome == 'success'" if step["name"] == "Publish lane report"
                         else "always()")
            assert index > collect and step["if"] == condition, step
            if step["name"] == "Publish lane report":
                assert step["with"]["path"].endswith("-reports") and "inputs.source" not in step["with"]["path"]
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
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"report", "defect"}
    }
    twins = set((*verify.STATE_TWINS.values(), *verify.DEATH_TWINS.values(),
                 *verify.JOB_TWINS.values(), *verify.OTHER_TWINS.values(), *verify.FAILURE_TWINS.values(),
                 *set.union(*verify.PLANTED.values())))
    assert rules == twins


def test_evidence_proof_triggers_only_on_schedule_dispatch_or_evidence_paths():
    import yaml

    proof = yaml.safe_load((ROOT / ".github/workflows/evidence-proof.yml").read_text(encoding="utf-8"))
    dispatch = proof[True]["workflow_dispatch"]
    assert set(dispatch["inputs"]) == {"probe_origin", "probe_scenario", "probe_role"}
    assert proof[True] == {
        "schedule": [{"cron": "41 3 * * *"}],
        "workflow_dispatch": dispatch,
        "pull_request": {"paths": [
            ".github/actions/lane/**",
            ".github/actions/publish-evidence/**",
            ".github/actions/recover-lane/**",
            ".github/workflows/evidence-*.yml",
            "pyproject.toml",
            "tests/helpers/lanes.py",
            "tests/helpers/bounds.py",
            "tests/helpers/watchdog.py",
            "tests/helpers/session_deadline.py",
            "tests/helpers/autopsy.py",
            "tests/helpers/evidence_files.py",
            "tests/helpers/worker_evidence.py",
            "tests/integration/evidence_plants/**",
            "tools/ci/lane_step.py",
            "tools/ci/check_assurance.py",
            "tools/ci/*evidence*",
            "tools/flake_register.py",
        ]},
    }


def test_evidence_proof_cancels_superseded_runs_and_runs_cancel_plants_on_schedule_or_dispatch():
    import yaml

    proof = yaml.safe_load((ROOT / ".github/workflows/evidence-proof.yml").read_text(encoding="utf-8"))
    assert proof["concurrency"] == {
        "group": "${{ inputs.probe_origin && format('evidence-cancel-run-{0}-{1}', inputs.probe_origin, "
                 "inputs.probe_scenario) || format('evidence-proof-{0}', "
                 "github.event.pull_request.number || github.ref) }}",
        "cancel-in-progress": True,
    }
    jobs = proof["jobs"]
    matrix = jobs["plant"]["strategy"]["matrix"]
    assert "cancel" not in matrix["kind"] and all(row["kind"] != "cancel" for row in matrix["include"])
    cancel = jobs["cancel-plant"]
    assert cancel["if"] == ("github.event_name != 'pull_request' && "
                            "(!inputs.probe_origin || inputs.probe_role == 'target')")
    # The start-up control's target alone runs the start-up plant (register E3; #579, M1).
    assert cancel["strategy"]["matrix"]["kind"] == ("${{ inputs.probe_scenario == 'start' && "
                                                    "fromJSON('[\"cancel-start\"]') || fromJSON('[\"cancel\"]') }}")
    assert jobs["run-cancel-control"]["strategy"]["matrix"]["scenario"] == ["manual", "supersede", "start"]
    scenarios = proof[True]["workflow_dispatch"]["inputs"]["probe_scenario"]["options"]
    assert scenarios == ["manual", "supersede", "start"]
    assert cancel["steps"] == jobs["plant"]["steps"]
    assert set(jobs["plant"]["needs"]) == {"cancel-trigger-linux", "cancel-trigger-windows"}
    for platform in ("linux", "windows"):
        ready = f"cancel-ready-{platform}"
        assert jobs[ready]["if"] == "github.event_name != 'pull_request' && !inputs.probe_origin"
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
    assert _load("verify_evidence").rule_ids(_load("evidence_problems").evidence_problems(output)) == {"omission"}


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
    assert stage.stage(source, output) == "gitleaks clean"
    indexes = sorted(output.glob("inventory*.txt"))
    assert len(indexes) > 1 and all(path.stat().st_size <= stage.INDEX_CAP for path in indexes)
    listing = "".join(path.read_text() for path in indexes)
    assert all(f"observation-{i:04}.txt" in listing for i in range(12))
    check = _load("evidence_problems").evidence_problems
    assert check(output) == []
    next(output.glob("inventory-part-*.txt")).unlink()
    assert "inventory" in _load("verify_evidence").rule_ids(check(output))


def test_cap_favors_failed_test_and_preserves_full_overflow(tmp_path, monkeypatch):
    stage = _load("stage_evidence")
    raw = tmp_path / "raw"
    for part in ("autopsy", "failures"):
        (raw / part).mkdir(parents=True, exist_ok=True)
    (raw / "autopsy/aaa.txt").write_bytes(b"a" * 800)
    (raw / "autopsy/failure.txt").write_bytes(b"f" * 720)
    overflow = Path("failures", "f" * 64 + ".txt")
    (raw / overflow).write_bytes(b"x" * 2048)
    monkeypatch.setattr(stage, "scan", lambda *args: {})
    monkeypatch.setattr(stage, "JOB_CAP", 1400)
    monkeypatch.setattr(stage, "INDEX_CAP", 460)
    output = tmp_path / "published"
    assert stage.stage(raw, output) == "gitleaks clean"
    assert (output / "autopsy/failure.txt").stat().st_size == 720
    assert (output / overflow).stat().st_size == 2048
    assert "omitted autopsy/aaa.txt (job cap)" in (output / "inventory.txt").read_text()
    assert sum(p.stat().st_size for p in output.rglob("*") if p.is_file() and p != output / overflow) <= stage.JOB_CAP


def test_decoder_only_finding_masks_its_reported_lines_preserving_siblings(tmp_path):
    import json

    stage = _load("stage_evidence")
    hit = stage.Hit("fixture", 3, b"decoded", 4, decoded=True)
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"cause": "head\nencoded one\nencoded two\ntail", "keep": "useful"}))
    stage.mask_reported_lines(path, [hit])
    assert json.loads(path.read_text()) == {
        "cause": "head\n<redacted:fixture>\n<redacted:fixture>\ntail", "keep": "useful"}
    with pytest.raises(ValueError, match="document types"):
        stage.map_xml('<!DOCTYPE doc [<!ENTITY name "value">]><doc>&name;</doc>', str)


def test_repeated_masks_index_the_source_lines_once(tmp_path):
    stage = _load("stage_evidence")

    class Counted(bytes):
        def count(self, sub, start=0, end=None):
            raise AssertionError("masking repeatedly counted the input")

    source = Counted(b"kept fixture end\n" * 2048)
    text, notes = stage.mask_bytes(source, {b"fixture": "rule"})
    assert text == b"kept <redacted:rule> end\n" * 2048
    assert notes == {("rule", n + 1) for n in range(2048)}
    with pytest.raises(stage.MaskTimeout):
        stage.mask_bytes(source, {b"fixture": "rule"}, deadline=0)


def test_mask_timeout_keeps_verified_siblings_and_records_the_omission(tmp_path, monkeypatch):
    stage = _load("stage_evidence")
    raw = tmp_path / "raw"
    (raw / "autopsy").mkdir(parents=True)
    (raw / "autopsy/context.txt").write_text("context")
    (raw / "autopsy/failure.txt").write_text("controlled fixture")
    hit = Path("autopsy/failure.txt")
    calls = []

    def scan(candidate, *args):
        calls.append(True)
        return {hit: [stage.Hit("rule", 1, b"fixture", 1)]} if (candidate / hit).exists() else {}

    mask = stage.mask

    def bounded(path, *args, **kwargs):
        if path.name == "failure.txt":
            raise stage.MaskTimeout
        return mask(path, *args, **kwargs)

    monkeypatch.setattr(stage, "scan", scan)
    monkeypatch.setattr(stage, "mask", bounded)
    out = tmp_path / "published"
    stage.stage(raw, out)
    assert len(calls) == 2
    assert (out / "autopsy/context.txt").read_text() == "context"
    assert not (out / hit).exists()
    assert "withheld/omitted (masking time budget expired" in (out / "inventory.txt").read_text()


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


@pytest.mark.parametrize("late", [None, "monitor", "final-poll"])
def test_a_signal_before_the_cutoff_records_interruption_without_a_cutoff_marker(tmp_path, monkeypatch, late):
    import json
    import signal

    lane = _load("lane_step")
    handlers = {}
    signals = []
    final_poll = False

    def child_status():
        if late == "final-poll" and final_poll:
            handlers[signal.SIGTERM](signal.SIGTERM, None)
        return 0 if late else None

    process = SimpleNamespace(poll=child_status, send_signal=signals.append, kill=lambda: None, wait=lambda **_kw: None)

    def snapshot(_root, *, all_workers=False, **_kw):
        if not all_workers and not late:
            handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}))
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", snapshot)

    def poll(*, final=False):
        nonlocal final_poll
        final_poll = final
        if final and late == "monitor":
            handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(lane.worker_evidence, "Monitor", lambda *_: SimpleNamespace(poll=poll))

    def read_phases(_root, _at):
        assert signals == [signal.SIGTERM]
        return []

    monkeypatch.setattr(lane.worker_evidence, "phases_at_signal", read_phases)
    monkeypatch.setattr(lane, "collect", lambda _root: None)
    monkeypatch.setattr(lane, "identities", lambda _root: [(tmp_path, (123, 456))])
    # The signal is stamped on the workers' phase receipts' clock, never time.monotonic: on Windows before CPython 3.13
    # the two differ, and a monotonic stamp misread the phases (review of #575, minor 1).
    sentinel = 987_654_321
    monkeypatch.setattr(lane, "phase_clock_ns", lambda: sentinel)

    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60) == (0 if late else 143)
    assert signals == ([] if late else [signal.SIGTERM])
    assert not lane.marker(tmp_path, "cutoff").exists()
    record = json.loads((tmp_path / "runner-resources-step-exit.txt").read_text())
    assert record["step_signal"] == ["SIGTERM"]
    observation = record["xdist_at_first_signal"]
    assert observation["monotonic_ns"] == sentinel
    if late:
        assert observation["status"] == "unavailable"
    else:
        assert observation["status"] == "observed" and observation["registered_workers"] == []


def test_a_cancel_collection_with_no_worker_reads_the_phases_at_a_stamp_on_the_phase_clock(tmp_path, monkeypatch):
    # The collection's own stamp, as the supervisor's above: on the workers' phase receipts' clock, never
    # time.monotonic, which differs from it on Windows before CPython 3.13 (#575's follow-on).
    lane = _load("lane_step")
    for name in ("AEW_PYTEST_OUTCOME", "AEW_LANE_RECOVERY_OUTCOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AEW_LANE_JOB_STATUS", "cancelled")
    monkeypatch.setattr(lane, "collect", lambda _root: None)
    sentinel = 987_654_321
    monkeypatch.setattr(lane, "phase_clock_ns", lambda: sentinel)
    stamps = []

    def read_phases(_root, at_ns):
        stamps.append(at_ns)
        return []

    monkeypatch.setattr(lane.worker_evidence, "phases_at_signal", read_phases)
    assert lane.main(["--collect", "--root", str(tmp_path)]) == 0
    assert stamps == [sentinel]


def test_a_windows_supervisor_interrupted_by_sigint_still_collects_and_ends_its_lanes_job(tmp_path, monkeypatch):
    import signal

    lane = _load("lane_step")
    handlers = {}
    ended = []
    collected = []

    def send_signal(signum):
        # Windows' Popen.send_signal: SIGTERM and the console events only.
        raise ValueError(f"Unsupported signal: {signum}")

    class Job:
        def __init__(self, name):
            self.name = name

        def members(self, **_kw):
            return []

        def pids(self):
            return []

        def terminate(self, code):
            ended.append(code)

    process = SimpleNamespace(poll=lambda: None, send_signal=send_signal, kill=lambda: None, wait=lambda **_kw: None)
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="nt", environ={}, getpid=lambda: 99))
    monkeypatch.setattr(lane.proctree, "Job", Job, raising=False)
    monkeypatch.setattr(lane.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", lambda *_a, **_kw: handlers[signal.SIGINT](signal.SIGINT, None))
    monkeypatch.setattr(lane, "host_reading", lambda: None)
    monkeypatch.setattr(lane.worker_evidence, "Monitor", lambda *_: SimpleNamespace(poll=lambda **_kw: None))
    monkeypatch.setattr(lane, "collect", collected.append)
    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60) == 130
    assert collected == [tmp_path] and ended == [130]


def test_a_phase_read_can_outlast_its_budget_without_delaying_cleanup(tmp_path, monkeypatch):
    import threading

    lane = _load("lane_step")
    release, done = threading.Event(), threading.Event()

    def slow(*_):
        release.wait(5)
        done.set()
        return []

    monkeypatch.setattr(lane.worker_evidence, "phases_at_signal", slow)
    monkeypatch.setattr(lane, "POLL_S", 0)
    try:
        result = lane.interrupt_phases(tmp_path, 42)
        assert result == {"monotonic_ns": 42, "status": "unavailable"} and not done.is_set()
    finally:
        release.set()
    assert done.wait(5) and result["status"] == "unavailable"


@pytest.mark.parametrize("history,identity,expected", [
    (None, True, "indeterminate"), ("", True, "indeterminate"),
    ("10 collecting\n", True, "collecting"),
    ("10 collecting\n30 collection-ended\n40 execution-started\n", True, "collecting"),
    ("10 collecting\n15 collection-ended\n", True, "collection-ended"),
    ("10 collecting\n15 collection-ended\n18 execution-started\n", True, "execution-started"),
    ("21 collecting\n", True, "indeterminate"), ("20 collecting\n", True, "indeterminate"),
    ("10 collecting\n", False, "indeterminate"), ("10 collecting", True, "indeterminate"),
    ("15 collecting\n12 collection-ended\n", True, "indeterminate"),
    ("10 collecting\n15 execution-started\n", True, "indeterminate"),
])
def test_worker_phase_at_signal_requires_ordered_receipts_from_the_same_live_worker(tmp_path, monkeypatch,
                                                                                   history, identity, expected):
    import worker_evidence as ev

    directory = tmp_path / "autopsy/session-test"
    directory.mkdir(parents=True)
    (directory / "worker-gw0-pid.txt").write_text("123\n")
    (directory / "worker-gw0-start.txt").write_text("456\n")
    (directory / "worker-123-455-lifecycle.txt").write_text("10 collecting\n")
    if history is not None:
        for phase in session_deadline.WORKER_PHASES:
            history = history.replace(phase, phase + " 7")
        (directory / "worker-123-456-lifecycle.txt").write_text(history)
    monkeypatch.setattr(ev, "_live_phase_writer", lambda path, pid, birth, fd: (pid, birth, fd) == (123, 456, 7)
                        and identity)
    assert ev.phases_at_signal(tmp_path, 20) == [
        {"session": "session-test", "worker": "worker-gw0", "pid": 123, "start": 456, "phase": expected}]


@pytest.mark.parametrize("failed_phase", session_deadline.WORKER_PHASES)
def test_an_incomplete_phase_write_revokes_the_worker_receipt(tmp_path, failed_phase):
    import os

    import proctree
    import worker_evidence as ev

    pid, birth = proctree.identity(os.getpid())
    directory = tmp_path / "autopsy/session-test"
    directory.mkdir(parents=True)
    (directory / "worker-gw0-pid.txt").write_text(f"{pid}\n")
    (directory / "worker-gw0-start.txt").write_text(f"{birth}\n")
    path = directory / f"worker-{pid}-{birth}-lifecycle.txt"
    stream = path.open("xb", buffering=0)

    def write(data):
        if failed_phase.encode() in data:
            raise OSError("receipt unavailable")
        return stream.write(data)

    worker = object.__new__(session_deadline.Worker)
    worker.phase_stream = None
    worker.lifecycle = SimpleNamespace(open=lambda *args, **kwargs: SimpleNamespace(
        write=write, fileno=stream.fileno, close=stream.close))
    for phase in session_deadline.WORKER_PHASES:
        worker._record_phase(phase)
    assert stream.closed
    assert ev.phases_at_signal(tmp_path, session_deadline.phase_clock_ns())[0]["phase"] == "indeterminate"


def test_a_worker_phase_is_read_at_a_later_signal_however_coarse_the_monotonic_tick(tmp_path, monkeypatch):
    """A transition, the next one and a signal read after it never share a stamp, which would read as indeterminate:
    here every time.monotonic reading falls in one tick, as within 15.6 ms on Windows before CPython 3.13 (the
    nightly of 2026-11-25)."""
    import os

    import proctree
    import worker_evidence as ev

    tick = session_deadline.time.monotonic_ns()
    monkeypatch.setattr(session_deadline.time, "monotonic_ns", lambda: tick)
    pid, birth = proctree.identity(os.getpid())
    directory = tmp_path / "autopsy/session-test"
    directory.mkdir(parents=True)
    (directory / "worker-gw0-pid.txt").write_text(f"{pid}\n")
    (directory / "worker-gw0-start.txt").write_text(f"{birth}\n")
    worker = object.__new__(session_deadline.Worker)
    worker.phase_stream = None
    worker.lifecycle = directory / f"worker-{pid}-{birth}-lifecycle.txt"
    try:
        for phase in session_deadline.WORKER_PHASES:
            worker._record_phase(phase)
            assert ev.phases_at_signal(tmp_path, session_deadline.phase_clock_ns())[0]["phase"] == phase
    finally:
        worker._close_phase()
    # The runner's own clock, not the simulated tick: a 15.6 ms one fails here on the Windows lanes.
    assert session_deadline.time.get_clock_info(session_deadline.PHASE_CLOCK).resolution <= 1e-6


def test_hosted_warning_attach_records_only_process_outcomes(tmp_path, monkeypatch):
    import sys

    if sys.platform != "linux":
        pytest.skip("hosted Linux attach routes")
    lane = _load("lane_step")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("PATH", str(tmp_path))
    failures = []
    assert lane.attach(42, failures=failures) is None
    assert failures == ["py-spy executable missing"]
    spy = tmp_path / "py-spy"
    spy.write_text("#!/bin/sh\necho 'private argument (os error 13)' >&2\nexit 1\n")
    spy.chmod(0o700)
    failures.clear()
    assert lane.attach(42, failures=failures) is None
    assert failures == ["unelevated: exit 1 (os error 13)", "sudo -n: launch error 2"]
    sudo = tmp_path / "sudo"
    sudo.write_text("#!/bin/sh\nexit 0\n")
    sudo.chmod(0o700)
    failures.clear()
    assert lane.attach(42, failures=failures) is None
    assert failures == ["unelevated: exit 1 (os error 13)", "sudo -n: empty dump"]
    sudo.write_text("#!/bin/sh\nexec /bin/sleep 2\n")
    failures.clear()
    assert lane.attach(42, timeout=0.2, failures=failures) is None
    assert failures[-1] == "sudo -n: timed out"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_worker_attach_survives_invalid_utf8_in_py_spy_output(monkeypatch, exit_code):
    import subprocess
    import sys

    lane = _load("lane_step")
    run = subprocess.run
    monkeypatch.setattr(lane.shutil, "which", lambda _name: sys.executable)
    dump = b"Thread 7 (active)\n    m\xc3\xa9thod (tests/test_sample.py:10)\n"
    if not exit_code:
        dump += b"    damaged\xf9\n"
    error = b"private argument\xf9 (os error 13)\n" if exit_code else b""
    script = (f"import sys; sys.stdout.buffer.write({dump!r}); sys.stderr.buffer.write({error!r}); "
              f"sys.exit({exit_code})")

    def py_spy(_argv, **kwargs):
        return run([sys.executable, "-c", script], **kwargs)

    monkeypatch.setattr(lane.subprocess, "run", py_spy)
    failures = []
    observed = lane.attach(42, allow_sudo=False, failures=failures)
    if exit_code:
        assert observed is None
        assert failures == ["unelevated: exit 1 (os error 13)"]
    else:
        assert observed == ("unelevated", "Thread 7 (active)\n    méthod (tests/test_sample.py:10)\n    damaged�\n")
        assert failures == []


@pytest.mark.parametrize("fault", [None, "unavailable", "prior-unavailable", "changed-node", "support-frame",
                                   "empty-then-error", "support-then-error", "partial-first", "lost-record", "exited"])
def test_linux_interrupt_samples_four_owned_workers_before_delivery(tmp_path, monkeypatch, fault):
    import json
    import signal
    import sys
    import threading

    lane = _load("lane_step")
    verify = _load("verify_evidence")
    ev = lane.worker_evidence
    session = tmp_path / "autopsy/session-test"
    session.mkdir(parents=True)
    pids = list(range(101, 105))
    participants = {pid: (pid, pid * 2) for pid in pids}
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
    for index, (pid, birth) in enumerate(participants.values()):
        (session / f"worker-gw{index}-pid.txt").write_text(str(pid))
        (session / f"worker-gw{index}-start.txt").write_text(str(birth))
        (tmp_path / f"hang-gw{index}-{pid}.txt").write_text(
            guard._header(SimpleNamespace(nodeid=f"tests/test_a.py::test_case[{pid}]")))

    handlers = {}
    signals = []
    together = threading.Barrier(4)

    calls = dict.fromkeys(pids, 0)

    def attach(pid, *, timeout, failures):
        assert not signals and 0 < timeout <= 3
        calls[pid] += 1
        if calls[pid] == 1:
            together.wait(timeout=2)
        if pid == pids[0]:
            if fault in {"empty-then-error", "support-then-error"}:
                if calls[pid] == 1:
                    dump = "Process 101: private argv"
                    if fault == "support-then-error":
                        dump += "\n    support (tests/helpers/support.py:4)"
                    return "unelevated", dump
                failures.append("sudo -n: exit 1 (os error 3)")
                return None
            if fault in {"unavailable", "prior-unavailable"}:
                failures.append("sudo -n: exit 1 (os error 3)")
                return None
            if fault == "changed-node":
                (tmp_path / f"hang-gw0-{pid}.txt").write_text(
                    guard._header(SimpleNamespace(nodeid="tests/test_a.py::test_next")))
            if fault == "exited":
                participants.pop(pid)
                return None
            if fault == "support-frame" or (fault == "partial-first" and calls[pid] == 1):
                return "unelevated", "    support (tests/helpers/support.py:4)"
        return "unelevated", "    test_case (tests/test_a.py:4)"

    def deliver(signum):
        assert len(list(session.glob("interrupted-*.txt"))) == 4
        signals.append(signum)

    process = SimpleNamespace(poll=lambda: None, send_signal=deliver, kill=lambda: None, wait=lambda **_: None)
    monkeypatch.setattr(lane, "sys", SimpleNamespace(platform="linux", stdout=sys.stdout, stderr=sys.stderr))
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}, getpid=lambda: 99))
    monkeypatch.setattr(lane.proctree, "identity", lambda pid: (pid, 1))
    monkeypatch.setattr(lane.proctree, "table", lambda: {})
    monkeypatch.setattr(lane.proctree, "descendants", lambda *_: [SimpleNamespace(identity=i)
                                                                 for i in participants.values()])
    monkeypatch.setattr(lane.proctree, "same", lambda identity: identity in participants.values())
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", lambda *_args, **_kw: handlers[signal.SIGTERM](signal.SIGTERM, None))
    monkeypatch.setattr(lane, "collect", lambda _: None)
    monkeypatch.setattr(lane, "memory_used", lambda: None)
    monkeypatch.setattr(lane, "attach", attach)
    monkeypatch.setattr(ev, "Monitor", lambda *_: SimpleNamespace(poll=lambda **_: None))
    first = tmp_path / "snapshots/101-unavailable.txt"
    if fault == "prior-unavailable":
        first.parent.mkdir()
        first.write_text("prior timeout snapshot failure\n")
    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60) == 143
    assert signals == [signal.SIGTERM]
    if fault == "lost-record":
        (session / "interrupted-101.txt").unlink()
    failures = verify.observe_cancel(tmp_path, "Linux", [])
    if fault == "lost-record":
        assert failures == ["Linux: cancellation did not observe all four registered workers alive"]
    elif fault in {"unavailable", "prior-unavailable", "changed-node", "support-frame",
                  "empty-then-error", "support-then-error", "exited"}:
        # The warning's typed outcome says why, bound to this observation (register E3, #561's quick check).
        why = {"changed-node": " (warning outcome: straddled a test change)",
               "exited": " (warning outcome: exited during its attach)",
               "support-frame": " (warning outcome: indeterminate)",
               "support-then-error": " (warning outcome: indeterminate)"}.get(fault, "")
        assert failures == [f"Linux: no pre-signal test stack for worker 101 at tests/test_a.py::test_case[101]{why}"]
        outcome = tmp_path / "snapshots/101-202-warning-outcome.txt"
        assert outcome.exists() == bool(why)
        if why:
            row = json.loads(outcome.read_text())
            observed = json.loads((session / "interrupted-101.txt").read_text())
            assert row["reason"] == "warning" and row["collect_at"] == observed["collect_at"]
            assert row["node"] == "tests/test_a.py::test_case[101]" and "private argv" not in outcome.read_text()
    else:
        assert failures == []
        assert not list((tmp_path / "snapshots").glob("*-warning-outcome.txt"))
    if fault == "partial-first":
        assert calls == {101: 2, 102: 1, 103: 1, 104: 1}
    assert first.exists() == (fault in {"unavailable", "prior-unavailable", "empty-then-error"})
    if fault in {"unavailable", "prior-unavailable"}:
        if fault == "prior-unavailable":
            assert first.read_text() == "prior timeout snapshot failure\n"
            [first] = first.parent.glob("101-*-warning-unavailable.txt")
        note = first.read_text()
        assert note.count("sudo -n: exit 1 (os error 3)") == calls[101]
        assert len(note.splitlines()) == 1
    if fault in {"empty-then-error", "support-then-error"}:
        if fault == "support-then-error":
            [first] = first.parent.glob("101-*-warning-attach.txt")
            assert "support.py:4" in (first.parent / "101.txt").read_text()
        note = first.read_text()
        assert "private argv" not in note
        assert ("dump has no Python frames" if fault == "empty-then-error" else "dump has no active test frame") in note
        assert note.count("sudo -n: exit 1 (os error 3)") == 2


SUPPORT = "    support (tests/helpers/support.py:4)\n"
# The frames under pytest 9.1 and xdist 3.8, innermost first, as py-spy prints them.
PROTOCOL = ("    _multicall (pluggy/_callers.py:121)\n    call_and_report (_pytest/runner.py:245)\n"
            "    runtestprotocol (_pytest/runner.py:136)\n    pytest_runtest_protocol (_pytest/runner.py:117)\n"
            "    run_one_test (xdist/remote.py:227)\n    pytest_runtestloop (xdist/remote.py:206)\n")
PHASE_DUMPS = {
    "setup": SUPPORT + "    pytest_runtest_setup (_pytest/runner.py:183)\n" + PROTOCOL,
    "teardown": SUPPORT + "    pytest_runtest_teardown (_pytest/runner.py:195)\n" + PROTOCOL,
    "between tests": ("    wait (threading.py:359)\n    get (xdist/remote.py:90)\n"
                      "    run_one_test (xdist/remote.py:214)\n    pytest_runtestloop (xdist/remote.py:206)\n"),
    "call": SUPPORT + "    pytest_runtest_call (_pytest/runner.py:178)\n" + PROTOCOL,
    "indeterminate": SUPPORT,  # a dump that lost the main thread: no pytest frame at all
}
LIVE_STACK = "evidence defect: [live-stack] cancelled-{}.txt: live worker lacks its interruption stack"
# What a live-stack defect adds when the cancellation collection left a typed outcome for the observation.
NAMED = " (cancel collection outcome: {})"


LANE_JOB = "aew-session-1-evidence-lane-report-Windows-integration-7"


def _session_job(monkeypatch, session, members, *, recorded=LANE_JOB):
    """The Windows session job, as the OS reports it: ``members`` are the identities it holds now."""
    opened = []

    class Job:
        @classmethod
        def open(cls, name):
            opened.append(name)
            return SimpleNamespace(holds=lambda identity: name == LANE_JOB and identity in members,
                                   close=lambda: None)

    (session / "session-job.txt").write_text(recorded + "\n")
    monkeypatch.setenv(session_deadline.JOB_NAMESPACE_ENV, LANE_JOB)
    monkeypatch.setattr(session_deadline.proctree, "IS_WINDOWS", True)
    monkeypatch.setattr(session_deadline.proctree, "Job", Job, raising=False)
    return opened


def _cancel_collection(tmp_path, monkeypatch, attach, *, pids=(101,), sampled=(101,), controller=False,
                       policy=None, periodic=None, same=None, job=None):
    """Run the Windows cancellation collection (lane_step --collect) on Linux, through a fake attach."""
    import json

    lane = _load("lane_step")
    ev = lane.worker_evidence
    session = tmp_path / "autopsy/session-test"
    session.mkdir(parents=True)
    if job is not None:
        job(monkeypatch, session)
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
    live = {(pid, pid * 2) for pid in pids}
    for index, pid in enumerate(pids):
        node = f"tests/test_a.py::test_case[{pid}]"
        name, gateway = ("controller", "main") if controller else (f"worker-gw{index}", f"gw{index}")
        (session / f"{name}-pid.txt").write_text(str(pid))
        (session / f"{name}-start.txt").write_text(str(pid * 2))
        (tmp_path / f"hang-{gateway}-{pid}.txt").write_text(guard._header(SimpleNamespace(nodeid=node)))
        if pid in sampled:
            worker = ev.Worker(session, pid, pid * 2, node, 0, 120)
            assert ev.save_sample(tmp_path, worker, lane.time.time() - 30, 1, "unelevated",
                                  "    test_case (tests/test_a.py:4)\n", reason="periodic")
    for name in ("GH_TOKEN", "AEW_PYTEST_OUTCOME", "AEW_EVIDENCE_PLANT", "AEW_LANE_RECOVERY_OUTCOME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AEW_LANE_JOB_STATUS", "cancelled")
    monkeypatch.setattr(lane.proctree, "same", same(live) if same else lambda identity: identity in live)
    if policy is not None:
        (tmp_path / "runner-resources-sampling.txt").write_text(json.dumps(policy))
    if periodic is not None:
        # The supervisor's own sampler, under the lane's policy, before the cancellation.
        monkeypatch.setenv("AEW_WORKER_SNAPSHOTS", "1")
        monkeypatch.setattr(ev, "cgroup", lambda: None)
        ev.Monitor(tmp_path, lambda pid, **kw: periodic(pid, live=live, **kw), lambda: set(live)).poll()
    monkeypatch.setattr(lane, "collect", lambda _: None)
    monkeypatch.setattr(lane, "attach", lambda pid, **kw: attach(pid, live=live, **kw))
    assert lane.main(["--collect", "--root", str(tmp_path)]) == 0
    records = {pid: json.loads((session / f"cancelled-{pid}.txt").read_text()) for pid in pids}
    outcomes = {pid: json.loads(path.read_text()) for pid in pids
                if (path := tmp_path / "snapshots" / f"{pid}-{pid * 2}-cancel-outcome.txt").exists()}
    return records, outcomes, _live_stack(tmp_path)


def _live_stack(root):
    check = _load("evidence_problems").evidence_problems
    return [why for why in check(root, kind="cancel") if "[live-stack]" in why]


def _forge(root, pid, old, new):
    path = root / "snapshots" / f"{pid}-{pid * 2}-cancel-outcome.txt"
    path.write_text(path.read_text().replace(old, new))


def test_a_windows_cancel_collection_retries_an_attach_that_failed(tmp_path, monkeypatch):
    calls = []

    def attach(pid, *, live, failures, **_):
        calls.append(pid)
        if len(calls) == 1:
            failures.append("unelevated: exit 1 (os error 5)")
            return None
        return "unelevated", "    test_case (tests/test_a.py:4)\n"

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert calls == [101, 101] and records[101]["alive_when_observed"]
    assert defects == [] and outcomes == {} and not (tmp_path / "snapshots/101-unavailable.txt").exists()


def test_a_failed_cancel_collection_attach_leaves_a_typed_unavailable_marker(tmp_path, monkeypatch):
    calls = []

    def attach(pid, *, live, failures, **_):
        calls.append(pid)
        failures.append("unelevated: exit 1 (os error 5)")
        return None

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    note = (tmp_path / "snapshots/101-unavailable.txt").read_text()
    assert note.startswith("evidence defect: py-spy unavailable for tests/test_a.py::test_case[101] (attempts: ")
    assert note.count("unelevated: exit 1 (os error 5)") == len(calls) == 3 and len(note.splitlines()) == 1
    # Still a defect: the marker names why the stack is missing, it does not excuse it.
    assert defects == [LIVE_STACK.format(101)]


def test_a_cancel_collection_that_spent_its_budget_before_the_first_attach_leaves_a_typed_unavailable_marker(
        tmp_path, monkeypatch):
    import worker_evidence as ev

    monkeypatch.setattr(ev, "CAPTURE_BUDGET_S", 0)
    calls = []
    records, outcomes, defects = _cancel_collection(
        tmp_path, monkeypatch, lambda pid, **_: calls.append(pid))
    assert calls == []
    assert (tmp_path / "snapshots/101-unavailable.txt").read_text() == (
        "evidence defect: py-spy unavailable for tests/test_a.py::test_case[101] "
        "(attempts: shared budget spent before its first attach)\n")
    assert defects == [LIVE_STACK.format(101)]


def test_alive_when_observed_is_decided_before_the_capture(tmp_path, monkeypatch):
    def attach(pid, *, live, failures, **_):
        live.discard((pid, pid * 2))  # the worker exits while it is being attached
        failures.append("unelevated: exit 1 (os error 87)")
        return None

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert records[101]["alive_when_observed"] is True
    assert outcomes[101]["outcome"] == "exited during its attach"
    assert outcomes[101]["attempts"] == ["unelevated: exit 1 (os error 87)"]
    assert defects == [LIVE_STACK.format(101) + NAMED.format("exited during its attach")]


def test_a_worker_that_exits_before_its_attach_is_typed_and_still_owes_its_stack(tmp_path, monkeypatch):
    def same(live):
        asked = []

        def check(identity):
            asked.append(identity)
            return identity in live and len(asked) == 1  # alive when observed, gone by its attach
        return check

    calls = []
    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, lambda pid, **_: calls.append(pid),
                                                    same=same)
    assert calls == [] and records[101]["alive_when_observed"] is True
    assert outcomes[101]["outcome"] == "exited before its attach"
    assert defects == [LIVE_STACK.format(101) + NAMED.format("exited before its attach")]


def _change_test(tmp_path, pid, name):
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
    (tmp_path / f"hang-gw0-{pid}.txt").write_text(guard._header(SimpleNamespace(nodeid=f"tests/test_a.py::{name}")))


def test_a_dump_taken_before_a_later_attempt_straddles_a_test_change_is_retained(tmp_path, monkeypatch):
    calls = []

    def attach(pid, *, live, failures, **_):
        calls.append(pid)
        if len(calls) > 1:  # every later attempt straddles a test change, so the budget's attempts run out
            _change_test(tmp_path, pid, f"test_next_{len(calls)}")
        return "unelevated", PHASE_DUMPS["call"]

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert calls == [101, 101, 101] and outcomes[101]["outcome"] == "straddled a test change"
    # The kept dump is the first test's, so the observation and the outcome stay that test's.
    assert records[101]["node"] == outcomes[101]["node"] == "tests/test_a.py::test_case[101]"
    ring = (tmp_path / "snapshots/101.txt").read_text()
    assert '"reason": "cancel collection"' in ring and "pytest_runtest_call" in ring
    assert defects == [LIVE_STACK.format(101) + NAMED.format("straddled a test change")]


def test_a_cancel_collection_that_straddles_a_test_change_retries_against_the_next_test(tmp_path, monkeypatch):
    from evidence_files import entries

    calls = []

    def attach(pid, *, live, failures, **_):
        calls.append(pid)
        if len(calls) == 1:  # the dump straddles: the worker finishes test_case[101] and starts test_next
            _change_test(tmp_path, pid, "test_next")
            return "unelevated", "    test_case (tests/test_a.py:4)\n"
        return "unelevated", "    test_next (tests/test_a.py:9)\n"

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert calls == [101, 101] and outcomes == {} and defects == []
    assert records[101]["node"] == "tests/test_a.py::test_next"
    assert records[101]["straddled_from"] == "tests/test_a.py::test_case[101]"
    collected = [row for row, _ in entries((tmp_path / "snapshots/101.txt").read_text())
                 if row["reason"] == "cancel collection"]
    # The straddling dump is never kept: a stack of one test never answers an observation of another.
    assert [row["node"] for row in collected] == ["tests/test_a.py::test_next"]


def test_a_straddle_with_no_dump_of_the_next_test_still_owes_its_stack(tmp_path, monkeypatch):
    calls = []

    def attach(pid, *, live, failures, **_):
        calls.append(pid)
        if len(calls) == 1:
            _change_test(tmp_path, pid, "test_next")
            return "unelevated", "    test_case (tests/test_a.py:4)\n"
        failures.append("unelevated: exit 1 (os error 5)")
        return None

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert calls == [101, 101, 101] and outcomes[101]["outcome"] == "straddled a test change"
    assert records[101]["node"] == "tests/test_a.py::test_case[101]" and "straddled_from" not in records[101]
    assert '"reason": "cancel collection"' not in (tmp_path / "snapshots/101.txt").read_text()
    assert defects == [LIVE_STACK.format(101) + NAMED.format("straddled a test change")]


def test_a_straddle_is_never_followed_into_another_workers_test(tmp_path, monkeypatch):
    # #561's quick check, m5: the follow matches the straddling worker's own identity, never another worker's change.
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
    every = "    test_case (tests/test_a.py:4)\n    test_other (tests/test_a.py:11)\n"
    straddled = []

    def attach(pid, *, live, failures, **_):
        if pid == 101 and not straddled:
            straddled.append(pid)
            # Worker 101 leaves its test with no next one yet, while worker 102 changes test.
            (tmp_path / "hang-gw0-101.txt").unlink()
            (tmp_path / "hang-gw1-102.txt").write_text(
                guard._header(SimpleNamespace(nodeid="tests/test_a.py::test_other")))
        return "unelevated", every

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach, pids=(101, 102),
                                                    sampled=(101, 102))
    assert straddled == [101] and outcomes[101]["outcome"] == "straddled a test change"
    assert records[101]["node"] == "tests/test_a.py::test_case[101]" and "straddled_from" not in records[101]
    assert all(row["pid"] == 101 for row, _ in _entries(tmp_path / "snapshots/101.txt"))
    assert LIVE_STACK.format(101) + NAMED.format("straddled a test change") in defects


def _entries(path):
    from evidence_files import entries

    return list(entries(path.read_text()))


@pytest.mark.parametrize("controller", [False, True])
def test_a_worker_never_sampled_in_the_ring_gets_a_typed_marker_not_a_demand(tmp_path, monkeypatch, controller):
    import worker_evidence as ev
    from evidence_files import NOT_SAMPLED

    calls = []
    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, lambda pid, **_: calls.append(pid),
                                                    sampled=(), controller=controller, policy={"periodic": False})
    assert calls == [] and records[101]["alive_when_observed"]
    assert outcomes == {101: {"reason": "cancel collection", "pid": 101, "start": 202,
                              "node": "tests/test_a.py::test_case[101]", "outcome": NOT_SAMPLED,
                              "collect_at": records[101]["collect_at"], "attempts": []}}
    assert defects == []
    # The excuse answers only its own observation.
    record = tmp_path / "autopsy/session-test/cancelled-101.txt"
    original = record.read_text()
    record.write_text(original.replace(f'"collect_at": {records[101]["collect_at"]}', '"collect_at": 1.0'))
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101)]
    record.write_text(original)
    # The bundle must bear the outcome out: a retained sample of that identity makes it a demand again.
    worker = ev.Worker(tmp_path / "autopsy/session-test", 101, 202, "tests/test_a.py::test_case[101]", 0, 120)
    assert ev.save_sample(tmp_path, worker, 1, 1, "unelevated", "    test_case (tests/test_a.py:4)\n",
                          reason="periodic")
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101) + NAMED.format(NOT_SAMPLED)]


def test_a_worker_its_lane_samples_but_never_sampled_still_owes_its_stack(tmp_path, monkeypatch):
    from evidence_files import SAMPLING_GAP

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, lambda pid, **_: None, sampled=(),
                                                    policy={"periodic": True})
    assert outcomes[101]["outcome"] == SAMPLING_GAP
    assert defects == [LIVE_STACK.format(101) + NAMED.format(SAMPLING_GAP)]
    # A not-sampled claim the lane's recorded policy contradicts is refused.
    _forge(tmp_path, 101, SAMPLING_GAP, "not sampled in the owned tree")
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101) + NAMED.format("not sampled in the owned tree")]


def _pid_problems(root, pid):
    check = _load("evidence_problems").evidence_problems
    return [why for why in check(root, kind="cancel")
            if ("[live-stack]" in why or "[snapshot" in why) and (f"-{pid}.txt" in why or f"pid {pid}:" in why)]


def test_a_worker_too_new_for_its_first_sample_is_attached_when_its_session_job_holds_it(tmp_path, monkeypatch):
    # Integration 7/14, job 139072636221: a hosted cancel killed the supervisor outright, before its periodic sampler
    # reached workers born seconds earlier, so the collection refused them as never sampled.
    calls = []

    def attach(pid, *, live, **_):
        calls.append(pid)
        return "unelevated", "    test_case (tests/test_a.py:4)\n"

    def job(monkeypatch, session):
        _session_job(monkeypatch, session, {(101, 202)})

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach, sampled=(),
                                                    policy={"periodic": True}, job=job)
    assert calls == [101] and outcomes == {} and records[101]["admitted_by"] == "session job"
    # Its cancel-collection sample is in the ring before its observation is recorded.
    assert records[101]["snapshot_node"] == records[101]["node"] and records[101]["age_s"] >= 0
    assert _pid_problems(tmp_path, 101) == []


@pytest.mark.parametrize("case", ["not a member", "another job's marker", "no lane name"])
def test_a_never_sampled_worker_outside_its_session_job_is_never_attached(tmp_path, monkeypatch, case):
    from evidence_files import SAMPLING_GAP

    calls = []
    opened = []

    def job(monkeypatch, session):
        # Only the OS's answer for the job the lane step named admits a worker: not a marker naming another job.
        members = set() if case == "not a member" else {(101, 202)}
        opened.append(_session_job(monkeypatch, session, members,
                                   recorded="aew-session-other" if case == "another job's marker" else LANE_JOB))
        if case == "no lane name":
            monkeypatch.delenv(session_deadline.JOB_NAMESPACE_ENV)

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, lambda pid, **_: calls.append(pid),
                                                    sampled=(), policy={"periodic": True}, job=job)
    assert calls == [] and "admitted_by" not in records[101]
    assert opened[0] == ([LANE_JOB] if case == "not a member" else [])
    assert outcomes[101]["outcome"] == SAMPLING_GAP and defects == [LIVE_STACK.format(101) + NAMED.format(SAMPLING_GAP)]


def test_a_frameless_periodic_dump_is_recorded_as_a_failed_attach_and_not_kept(tmp_path, monkeypatch):
    import json

    import worker_evidence as ev

    session = tmp_path / "autopsy/session-test"
    session.mkdir(parents=True)
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
    (session / "worker-gw0-pid.txt").write_text("101")
    (session / "worker-gw0-start.txt").write_text("202")
    (tmp_path / "hang-gw0-101.txt").write_text(guard._header(SimpleNamespace(nodeid="tests/test_a.py::test_case")))
    monkeypatch.setattr(ev.proctree, "same", lambda identity: identity == (101, 202))
    [worker] = ev.workers(tmp_path)
    calls = []

    def attach(pid, *, failures):
        calls.append(pid)
        return "unelevated", "Process 101: private argv\nThread 7 (idle)\n"  # py-spy's header, no Python frame

    for reason in ("periodic", "memory pressure"):
        assert ev.capture(tmp_path, [worker], attach, reason=reason, allowed={worker.identity}) == {}
    assert calls == [101, 101] and not ev.ring_path(tmp_path, worker).exists()
    failure = json.loads((tmp_path / "snapshots/101-202-sampling-failures.txt").read_text())
    assert failure["reason"] == "periodic" and failure["attempts"] == ["unelevated: dump has no Python frames"]
    assert "private argv" not in (tmp_path / "snapshots/101-202-sampling-failures.txt").read_text()


def test_the_sampling_policy_is_recorded_before_the_lane_starts(tmp_path, monkeypatch):
    import json

    lane = _load("lane_step")
    monkeypatch.delenv("AEW_EVIDENCE_PLANT", raising=False)
    monkeypatch.setenv("AEW_WORKER_SNAPSHOTS", "1")
    monkeypatch.setattr(lane.worker_evidence, "cgroup", lambda: None)
    policy = tmp_path / "runner-resources-sampling.txt"
    policy.write_text(json.dumps({"periodic": False}))  # left by an earlier step in the same root
    seen = []

    def start(*_args, **_kwargs):
        seen.append(json.loads(policy.read_text()))
        raise OSError("the lane is not started in this test")

    monkeypatch.setattr(lane.subprocess, "Popen", start)
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}, getpid=lambda: 99))
    with pytest.raises(OSError, match="not started"):
        lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60)
    assert seen == [{"periodic": True}]
    assert not list(tmp_path.glob("*.tmp"))


def test_a_worker_due_for_periodic_sampling_whose_attaches_all_failed_still_raises_live_stack(tmp_path, monkeypatch):
    import json

    periodic_calls = []

    def periodic(pid, *, live, failures):
        periodic_calls.append(pid)
        failures.append("unelevated: exit 1 (os error 5)")
        return None

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, lambda pid, **_: None, sampled=(),
                                                    periodic=periodic)
    assert periodic_calls == [101]
    failure = json.loads((tmp_path / "snapshots/101-202-sampling-failures.txt").read_text())
    assert failure["reason"] == "periodic" and failure["attempts"] == ["unelevated: exit 1 (os error 5)"]
    assert defects == [LIVE_STACK.format(101) + NAMED.format("never sampled although its lane's policy samples it")]
    # Even under a policy that excludes the worker, a failed sampling attach refuses the not-sampled excuse.
    (tmp_path / "runner-resources-sampling.txt").write_text(json.dumps({"periodic": False}))
    _forge(tmp_path, 101, outcomes[101]["outcome"], "not sampled in the owned tree")
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101) + NAMED.format("not sampled in the owned tree")]
    (tmp_path / "snapshots/101-202-sampling-failures.txt").unlink()
    assert _live_stack(tmp_path) == []


@pytest.mark.parametrize("phase", ["teardown", "setup", "between tests"])
def test_a_worker_in_teardown_is_reported_as_teardown_not_a_missing_stack(tmp_path, monkeypatch, phase):
    calls = []

    def attach(pid, *, live, **_):
        calls.append(pid)
        return "unelevated", PHASE_DUMPS[phase]

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert calls == [101], "a worker outside its test's call is not asked again for a frame it cannot give"
    assert outcomes[101]["outcome"] == phase and defects == []
    assert '"reason": "cancel collection"' in (tmp_path / "snapshots/101.txt").read_text()
    # The outcome is accepted only when the retained frames classify so: a claim the frames contradict is a defect.
    other = next(name for name in ("setup", "teardown") if name != phase)
    _forge(tmp_path, 101, f'"outcome": "{phase}"', f'"outcome": "{other}"')
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101) + NAMED.format(other)]


@pytest.mark.parametrize("phase", ["call", "indeterminate"])
def test_a_worker_mid_call_without_its_frame_is_still_a_live_stack_defect(tmp_path, monkeypatch, phase):
    calls = []

    def attach(pid, *, live, **_):
        calls.append(pid)
        return "unelevated", PHASE_DUMPS[phase]

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert len(calls) == 3, "a dump inside the call is retried for the test's frame"
    assert outcomes[101]["outcome"] == phase
    assert outcomes[101]["attempts"] == ["unelevated: dump has no active test frame"] * 3
    assert defects == [LIVE_STACK.format(101) + NAMED.format(phase)]
    # Even a forged outside-call outcome cannot excuse a worker whose retained frames show it inside the call.
    _forge(tmp_path, 101, f'"outcome": "{phase}"', '"outcome": "teardown"')
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101) + NAMED.format("teardown")]


def _linux_interrupt(tmp_path, monkeypatch, first_dump):
    """Run the Linux lane supervisor over four live workers, each inside a test's protocol, to its SIGTERM: its
    pre-signal warning attaches through a fake py-spy that gives worker 101 ``first_dump`` and the others their
    test's frame. Returns each worker's number of attaches."""
    import signal
    import sys

    lane = _load("lane_step")
    session = tmp_path / "autopsy/session-test"
    session.mkdir(parents=True)
    pids = list(range(101, 105))
    identities = [(pid, pid * 2) for pid in pids]
    guard = watchdog.HangWatchdog(SimpleNamespace(getoption=lambda *_: str(tmp_path)), 120)
    for index, (pid, birth) in enumerate(identities):
        (session / f"worker-gw{index}-pid.txt").write_text(str(pid))
        (session / f"worker-gw{index}-start.txt").write_text(str(birth))
        (tmp_path / f"hang-gw{index}-{pid}.txt").write_text(
            guard._header(SimpleNamespace(nodeid=f"tests/test_a.py::test_case[{pid}]")))
    handlers, signals = {}, []
    calls = dict.fromkeys(pids, 0)

    def attach(pid, *, timeout, failures):
        assert not signals, "the warning is taken before the signal is forwarded"
        calls[pid] += 1
        return "unelevated", first_dump if pid == 101 else "    test_case (tests/test_a.py:4)"

    process = SimpleNamespace(poll=lambda: None, send_signal=signals.append, kill=lambda: None, wait=lambda **_: None)
    monkeypatch.setattr(lane, "sys", SimpleNamespace(platform="linux", stdout=sys.stdout, stderr=sys.stderr))
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}, getpid=lambda: 99))
    monkeypatch.setattr(lane.proctree, "identity", lambda pid: (pid, 1))
    monkeypatch.setattr(lane.proctree, "table", lambda: {})
    monkeypatch.setattr(lane.proctree, "descendants", lambda *_: [SimpleNamespace(identity=i) for i in identities])
    monkeypatch.setattr(lane.proctree, "same", lambda identity: identity in identities)
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", lambda *_args, **_kw: handlers[signal.SIGTERM](signal.SIGTERM, None))
    monkeypatch.setattr(lane, "collect", lambda _: None)
    monkeypatch.setattr(lane, "memory_used", lambda: None)
    monkeypatch.setattr(lane, "attach", attach)
    monkeypatch.setattr(lane.worker_evidence, "Monitor", lambda *_: SimpleNamespace(poll=lambda **_: None))
    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 60) == 143
    assert signals == [signal.SIGTERM] and len(list(session.glob("interrupted-*.txt"))) == 4
    return calls


LINUX_STACK = "evidence defect: [live-stack] interrupted-101.txt: live worker lacks its interruption stack"


@pytest.mark.parametrize("phase", ["setup", "teardown"])
def test_a_linux_worker_in_setup_or_teardown_at_the_signal_is_not_a_missing_stack(tmp_path, monkeypatch, phase):
    """A Linux worker the cancel signal catches in fixture setup or teardown has no test-function frame to give. Its
    warning's typed outcome, with the retained warning stack that classifies the same, is accepted as the Windows
    collection's is (the operator, 2026-11-26; flake-register linux-cancel-live-stack, reproduced with a worker in a
    fixture's setup)."""
    import json

    calls = _linux_interrupt(tmp_path, monkeypatch, PHASE_DUMPS[phase])
    assert calls == dict.fromkeys(range(101, 105), 1), "a worker outside its call is not asked again for the frame"
    outcome = tmp_path / "snapshots/101-202-warning-outcome.txt"
    observed = json.loads((tmp_path / "autopsy/session-test/interrupted-101.txt").read_text())
    row = json.loads(outcome.read_text())
    assert (row["outcome"], row["reason"], row["collect_at"]) == (phase, "warning", observed["collect_at"])
    assert '"reason": "warning"' in (tmp_path / "snapshots/101.txt").read_text()
    assert _live_stack(tmp_path) == []
    # The hosted proof's own reading of its Linux plant accepts exactly what the check accepts.
    assert _load("verify_evidence").observe_cancel(tmp_path, "Linux", []) == []
    # Accepted only while the bundle bears it out: an outcome the retained frames contradict, one of another
    # observation, or one whose stack is gone is still a missing stack, and the defect names the outcome.
    kept = outcome.read_text()
    other = next(name for name in ("setup", "teardown") if name != phase)
    outcome.write_text(kept.replace(f'"outcome": "{phase}"', f'"outcome": "{other}"'))
    assert _live_stack(tmp_path) == [f"{LINUX_STACK} (warning outcome: {other})"]
    outcome.write_text(kept.replace(f'"collect_at": {observed["collect_at"]}', '"collect_at": 1.0'))
    assert _live_stack(tmp_path) == [LINUX_STACK]
    # The outcome is this worker's and this test's alone: one that names another test or another worker excuses
    # nothing (review of #617, m2).
    node = '"node": "tests/test_a.py::test_case[101]"'
    assert node in kept and '"pid": 101' in kept
    outcome.write_text(kept.replace(node, '"node": "tests/test_a.py::test_case[102]"'))
    assert _live_stack(tmp_path) == [LINUX_STACK]
    outcome.write_text(kept.replace('"pid": 101', '"pid": 102'))
    assert _live_stack(tmp_path) == [LINUX_STACK]
    outcome.write_text(kept)
    assert _live_stack(tmp_path) == []
    (tmp_path / "snapshots/101.txt").unlink()
    assert _live_stack(tmp_path) == [f"{LINUX_STACK} (warning outcome: {phase})"]
    assert _load("verify_evidence").observe_cancel(tmp_path, "Linux", []) == [
        f"Linux: no pre-signal test stack for worker 101 at tests/test_a.py::test_case[101] (warning outcome: {phase})"]


@pytest.mark.parametrize("phase", ["call", "indeterminate", "between tests"])
def test_a_linux_worker_inside_its_call_without_its_test_frame_still_owes_its_stack(tmp_path, monkeypatch, phase):
    """The rule is not loosened beyond setup and teardown: a dump inside the test's call that lost the test's frame,
    one with no pytest frame at all, and one the frames place between tests while the worker is still inside a
    test's protocol all stay a live-stack defect on Linux, which names the warning's outcome."""
    import json

    calls = _linux_interrupt(tmp_path, monkeypatch, PHASE_DUMPS[phase])
    assert calls[101] == 3, "a dump that does not show the worker in setup or teardown is retried for the frame"
    row = json.loads((tmp_path / "snapshots/101-202-warning-outcome.txt").read_text())
    assert row["outcome"] == phase
    assert _live_stack(tmp_path) == [f"{LINUX_STACK} (warning outcome: {phase})"]
    # Even a forged setup outcome cannot excuse a worker whose retained frames do not show it in setup.
    outcome = tmp_path / "snapshots/101-202-warning-outcome.txt"
    outcome.write_text(outcome.read_text().replace(f'"outcome": "{phase}"', '"outcome": "setup"'))
    assert _live_stack(tmp_path) == [f"{LINUX_STACK} (warning outcome: setup)"]
    assert _load("verify_evidence").observe_cancel(tmp_path, "Linux", []) == [
        "Linux: no pre-signal test stack for worker 101 at tests/test_a.py::test_case[101] (warning outcome: setup)"]


def test_a_live_stack_defect_names_its_typed_outcome(tmp_path, monkeypatch):
    """A sighting says why from the check's own message, with no artifact download: each interruption's typed outcome
    for that observation, by the interruption's name, and nothing when none was left."""
    calls = []

    def attach(pid, *, live, **_):
        calls.append(pid)
        return "unelevated", PHASE_DUMPS["call"]

    records, outcomes, defects = _cancel_collection(tmp_path, monkeypatch, attach)
    assert defects == [LIVE_STACK.format(101) + " (cancel collection outcome: call)"]
    (tmp_path / "snapshots/101-202-cancel-outcome.txt").unlink()
    assert _live_stack(tmp_path) == [LIVE_STACK.format(101)]


def test_the_linux_cancel_plant_holds_half_its_cases_in_a_fixtures_setup():
    """The proof's Linux plant can catch a worker outside its call: the planted test requests the fixture, an odd
    case spends its seconds in that fixture's setup and none in its call, an even case the reverse, and no case's
    length changes, so the plant still outlasts its deadline. The hosted proof cannot show this by itself, since it
    does not require a worker outside its call (review of #617, m3)."""
    import json
    import subprocess
    import sys

    # The plant is imported in a process of its own, as its kind: the fixture's own function is called with the
    # request pytest would give it, and the planted test with the arguments pytest would, under a recording sleep.
    code = """
import importlib.util, inspect, json, os, sys, types
os.environ["AEW_EVIDENCE_PLANT"] = sys.argv[2]
os.environ.pop("PYTEST_XDIST_WORKER", None)
spec = importlib.util.spec_from_file_location("deaths", sys.argv[1])
plant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plant)
slept = []
plant.time.sleep = slept.append
fixture = plant.planted_setup
setup = getattr(fixture, "_get_wrapped_function", lambda: getattr(fixture, "__wrapped__", fixture))()
cases = []
for step in range(4):
    request = types.SimpleNamespace(node=types.SimpleNamespace(callspec=types.SimpleNamespace(params={"step": step})))
    setup(request)
    in_setup, slept[:] = list(slept), []
    plant.test_death(sys.argv[2], step, request, None)
    in_call, slept[:] = list(slept), []
    cases.append([in_setup, in_call])
print(json.dumps({"requested": "planted_setup" in inspect.signature(plant.test_death).parameters, "cases": cases}))
"""
    plant = str(ROOT / "tests/integration/evidence_plants/deaths.py")
    seen = {kind: json.loads(subprocess.run(
        [sys.executable, "-c", code, plant, kind], capture_output=True, text=True, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout) for kind in ("cancel", "time-limit-github")}
    in_call = [[[], [2]], [[], [3]], [[], [4]], [[], [5]]]
    held = [[[], [2]], [[3], []], [[], [4]], [[5], []]]  # odd cases: their seconds in setup, none in the call
    assert seen["cancel"] == {"requested": True, "cases": held if sys.platform == "linux" else in_call}
    assert seen["time-limit-github"] == {"requested": True, "cases": in_call}  # every other kind is unchanged


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
        "report.json": (True, False),
    }
    for name, expected in cases.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "tests/test_a.py::test_a\n")
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
    assert serial.identity == (pid, birth) and serial.node == node and serial.controller


def _lane_snapshot_mode(os_name, workflow, plant=None, explicit=None):
    """Evaluate the lane action's AEW_WORKER_SNAPSHOTS expression (its one owner) for a hosted runner."""
    import re

    import yaml

    action = yaml.safe_load((ROOT / ".github/actions/lane/action.yml").read_text(encoding="utf-8"))
    step = next(step for step in action["runs"]["steps"] if step.get("id") == "pytest")
    expression = " ".join(step["env"]["AEW_WORKER_SNAPSHOTS"].split()).removeprefix("${{").removesuffix("}}")
    # GitHub's && and || return an operand, as Python's and/or do; an unset env value is null, so falsy.
    expression = re.sub(r"!(?!=)", " not ", expression.replace("&&", " and ").replace("||", " or "))
    context = {"env": SimpleNamespace(AEW_WORKER_SNAPSHOTS=explicit, AEW_EVIDENCE_PLANT=plant),
               "runner": SimpleNamespace(environment="github-hosted", os=os_name),
               "github": SimpleNamespace(workflow=workflow)}
    return eval(expression, {"__builtins__": {}}, context)  # noqa: S307 - the repository's own action, no input


def _periodically_sampled(tmp_path, monkeypatch, mode, plant=None):
    import worker_evidence as ev

    if plant:
        monkeypatch.setenv("AEW_EVIDENCE_PLANT", plant)
    else:
        monkeypatch.delenv("AEW_EVIDENCE_PLANT", raising=False)
    monkeypatch.setenv("AEW_WORKER_SNAPSHOTS", mode)
    monkeypatch.setattr(ev, "cgroup", lambda: None)
    candidates = [ev.Worker(tmp_path, pid, 100, "test.py::test_case", 0, 120, controller=pid == 1)
                  for pid in (1, 2)]
    monkeypatch.setattr(ev, "workers", lambda root: iter(candidates))
    sampled = []

    def capture(root, due, attach, *, reason, allowed):
        sampled.extend(worker.pid for worker in due)
        return {worker.identity for worker in due}

    monkeypatch.setattr(ev, "capture", capture)
    ev.Monitor(tmp_path, None, lambda: {w.identity for w in candidates}).poll()
    return sampled


@pytest.mark.parametrize("os_name,workflow,plant,explicit,expected", [
    ("Windows", "ci", None, None, [1, 2]), ("Windows", "evidence-proof", "cancel", None, [1, 2]),
    ("Linux", "ci", None, None, [1, 2]), ("Linux", "evidence-proof", "cancel", None, [1, 2]),
    ("Windows", "evidence-proof", "cancel", "0", []), ("Windows", "nightly", None, None, []),
])
def test_periodic_sampling_selects_the_same_workers_in_ci_and_its_cancel_control(
        tmp_path, monkeypatch, os_name, workflow, plant, explicit, expected):
    mode = _lane_snapshot_mode(os_name, workflow, plant, explicit)
    assert _periodically_sampled(tmp_path, monkeypatch, mode, plant) == expected


def test_hosted_windows_ci_samples_its_serial_controller_periodically(tmp_path, monkeypatch):
    import json

    # Operator, 2026-11-25 (register E3): every attach is --nonblocking, so the serial controller is sampled too.
    mode = _lane_snapshot_mode("Windows", "ci")
    assert mode == _lane_snapshot_mode("Linux", "ci") == "1"
    assert 1 in _periodically_sampled(tmp_path, monkeypatch, mode), "worker 1 is the serial lane's controller"
    assert json.loads((tmp_path / "runner-resources-sampling.txt").read_text()) == {"periodic": True}


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


# ------------------------------------------------------------- the Windows host-resource stop (register E3). The
# Windows API is stubbed, so these run on every platform.

def _host(**changes):
    reading = {"commit_bytes": 10 * 1024 ** 3, "commit_limit_bytes": 24 * 1024 ** 3,
               "physical_available_bytes": 6 * 1024 ** 3, "kernel_paged_bytes": 1, "kernel_nonpaged_bytes": 1,
               "handles": 90_000, "processes": 250, "threads": 3_000, "free_disk_bytes": 12 * 1024 ** 3}
    return {**reading, **changes}


def test_a_windows_host_reading_reports_bytes_and_counts_from_the_performance_counters(monkeypatch):
    import ctypes
    import struct

    lane = _load("lane_step")
    # PERFORMANCE_INFORMATION as psapi.h lays it out, written as raw bytes, so a wrong field order or width in the
    # structure misreads them: DWORD cb; ten SIZE_T (CommitTotal ... PageSize); three DWORD counts. 104 bytes on
    # 64-bit Windows, 56 on 32-bit.
    wide = ctypes.sizeof(ctypes.c_void_p) == 8
    layout = "<I4x10Q3I4x" if wide else "<I10I3I"
    assert struct.calcsize(layout) == (104 if wide else 56)
    # cb, CommitTotal, CommitLimit, CommitPeak, PhysicalTotal, PhysicalAvailable, SystemCache, KernelTotal,
    # KernelPaged, KernelNonpaged, PageSize, HandleCount, ProcessCount, ThreadCount
    fields = (struct.calcsize(layout), 3, 8, 9, 16, 2, 5, 6, 1, 1, 4096, 70_000, 210, 2_400)

    def performance_info(pointer, size):
        assert size == struct.calcsize(layout)
        ctypes.memmove(pointer, struct.pack(layout, *fields), size)
        return 1

    monkeypatch.setattr(lane, "os", SimpleNamespace(name="nt", environ={"RUNNER_TEMP": "D:/a/_temp"}))
    monkeypatch.setattr(lane.shutil, "disk_usage", lambda path: SimpleNamespace(free=5 * 1024 ** 3)
                        if path == "D:/a/_temp" else pytest.fail(path))
    assert lane.host_reading(performance_info) == {
        "commit_bytes": 3 * 4096, "commit_limit_bytes": 8 * 4096, "physical_available_bytes": 2 * 4096,
        "kernel_paged_bytes": 4096, "kernel_nonpaged_bytes": 4096, "handles": 70_000, "processes": 210,
        "threads": 2_400, "free_disk_bytes": 5 * 1024 ** 3}


def test_a_failed_performance_query_or_a_host_other_than_windows_gives_no_reading(monkeypatch):
    lane = _load("lane_step")
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}))
    assert lane.host_reading(lambda *_: pytest.fail("queried off Windows")) is None
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="nt", environ={}))
    assert lane.host_reading(lambda *_: 0) is None
    assert "free_disk_bytes" not in lane.host_reading(lambda *_: 1)  # no RUNNER_TEMP: the other limits still hold


@pytest.mark.parametrize("resource,below,at", [
    ("commit_bytes", 22 * 1024 ** 3, 23 * 1024 ** 3),
    ("handles", 999_999, 1_000_000),
    ("processes", 999, 1_000),
    ("free_disk_bytes", 2 * 1024 ** 3, 2 * 1024 ** 3 - 1),
])
def test_each_host_limit_names_its_resource_only_once_reached(resource, below, at):
    lane = _load("lane_step")
    assert lane.host_crossed(_host()) == []
    assert lane.host_crossed(_host(**{resource: below})) == []
    assert [row["resource"] for row in lane.host_crossed(_host(**{resource: at}))] == [resource]
    assert lane.host_crossed(_host(**{resource: at}))[0]["value"] == at


def test_the_host_peak_keeps_each_high_water_mark_and_the_least_free_disk():
    lane = _load("lane_step")
    peak = lane.host_peak(None, _host(handles=5, free_disk_bytes=9))
    peak = lane.host_peak(peak, _host(handles=3, free_disk_bytes=4, processes=900))
    peak = lane.host_peak(peak, _host(handles=4, free_disk_bytes=7))
    assert (peak["handles"], peak["free_disk_bytes"], peak["processes"]) == (5, 4, 900)


def test_a_crossed_host_limit_stops_the_lane_early_with_its_own_exit_and_names_the_running_tests(tmp_path,
                                                                                                 monkeypatch, capsys):
    import json
    import sys

    lane = _load("lane_step")
    session = tmp_path / "autopsy/session-test"
    session.mkdir(parents=True)
    (tmp_path / "running-321.txt").write_text("tests/regression/test_a.py::test_case\n")
    readings = iter([_host(processes=400), _host(processes=1_200)])
    snapshots, collected, killed = [], [], []
    process = SimpleNamespace(poll=lambda: None, send_signal=pytest.fail, kill=lambda: killed.append(True),
                              wait=lambda **_: None)
    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}, getpid=lambda: 99))
    monkeypatch.setattr(lane, "sys", SimpleNamespace(platform="win32", stdout=sys.stdout, stderr=sys.stderr))
    monkeypatch.setattr(lane, "POLL_S", 0)
    monkeypatch.setattr(lane, "HOST_POLL_S", 0)
    monkeypatch.setattr(lane, "host_reading", lambda: next(readings))
    monkeypatch.setattr(lane, "memory_used", lambda: None)
    monkeypatch.setattr(lane.signal, "signal", lambda *_: None)
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", lambda _root, *, all_workers=False, **_kw: snapshots.append(all_workers))
    monkeypatch.setattr(lane, "collect", collected.append)
    monkeypatch.setattr(lane, "identities", lambda _root: [(session, (123, 456))])
    monkeypatch.setattr(lane.worker_evidence, "Monitor", lambda *_: SimpleNamespace(poll=lambda **_: None))
    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 600) == 72
    assert lane.HOST_RESOURCES_EXIT == 72 != lane.SUPERVISOR_CUTOFF_EXIT
    assert snapshots[-1] is True and collected == [tmp_path] and killed  # the cutoff's capture and cleanup
    assert not lane.marker(session, "cutoff").exists()  # not a time limit: the evidence check must not say so
    stop = json.loads((tmp_path / lane.HOST_STOP_FILE).read_text())
    assert stop["crossed"] == [{"resource": "processes", "value": 1_200, "limit": lane.HOST_PROCESSES}]
    assert stop["running_tests"] == ["tests/regression/test_a.py::test_case"] and stop["exit"] == 72
    record = json.loads((tmp_path / "runner-resources-step-exit.txt").read_text())
    assert record["lane_exit"] == 72 and record["host_resources_peak"]["processes"] == 1_200
    assert record["step_signal"] == [] and "xdist_at_first_signal" not in record  # no signal was received
    assert "stopped for the host's resources" in capsys.readouterr().out


def test_a_signal_received_with_a_crossed_host_limit_is_an_interruption_and_no_host_stop(tmp_path, monkeypatch):
    import json
    import signal
    import sys

    lane = _load("lane_step")
    handlers, signals = {}, []
    process = SimpleNamespace(poll=lambda: None, send_signal=signals.append, kill=lambda: None, wait=lambda **_: None)

    def snapshot(_root, *, all_workers=False, **_kw):
        if not all_workers:
            handlers[signal.SIGTERM](signal.SIGTERM, None)  # the signal lands before this pass's host reading

    monkeypatch.setattr(lane, "os", SimpleNamespace(name="posix", environ={}, getpid=lambda: 99))
    monkeypatch.setattr(lane, "sys", SimpleNamespace(platform="win32", stdout=sys.stdout, stderr=sys.stderr))
    monkeypatch.setattr(lane, "host_reading", lambda: _host(processes=5_000, handles=5_000_000))
    monkeypatch.setattr(lane, "memory_used", lambda: None)
    monkeypatch.setattr(lane.signal, "signal", lambda signum, handler: handlers.setdefault(signum, handler))
    monkeypatch.setattr(lane.subprocess, "Popen", lambda *_args, **_kw: process)
    monkeypatch.setattr(lane, "snapshot", snapshot)
    monkeypatch.setattr(lane, "collect", lambda _root: None)
    monkeypatch.setattr(lane, "identities", lambda _root: [])
    monkeypatch.setattr(lane.worker_evidence, "Monitor", lambda *_: SimpleNamespace(poll=lambda **_: None))
    assert lane.supervise(tmp_path, "bash", tmp_path / "command.sh", lane.time.time() + 600) == 128 + signal.SIGTERM
    assert signals == [signal.SIGTERM] and not (tmp_path / lane.HOST_STOP_FILE).exists()
    record = json.loads((tmp_path / "runner-resources-step-exit.txt").read_text())
    assert record["lane_exit"] == 128 + signal.SIGTERM and record["step_signal"] == ["SIGTERM"]
    assert record["host_resources_peak"]["processes"] == 5_000  # the reading is still kept, as a peak


def test_the_running_names_have_one_reader_that_drops_odd_names_and_links(tmp_path, monkeypatch):
    import os

    # a lane under the lane step publishes its own running directory, which running_tests would read instead
    monkeypatch.delenv("AEW_RUNNING_TESTS_DIR", raising=False)

    import watchdog

    (tmp_path / "running-11.txt").write_text("tests/regression/test_a.py::test_case\n")
    (tmp_path / "running-12.txt").write_text("tests/regression/test_a.py::test_case[secret-param]\n")
    (tmp_path / "running-x.txt").write_text("tests/regression/test_a.py::test_other\n")
    try:
        os.symlink(tmp_path / "running-11.txt", tmp_path / "running-13.txt")
    except OSError:  # a Windows account without the symlink privilege: the name and content cases still hold
        pass
    assert watchdog.running_names(tmp_path) == {"running-11.txt": "tests/regression/test_a.py::test_case",
                                                "running-12.txt": "<unrecognized test>"}
    lane = _load("lane_step")
    assert lane.running_tests(tmp_path) == ["<unrecognized test>", "tests/regression/test_a.py::test_case"]
    names = tmp_path / "out-names"
    _load("evidence_inputs").prepare(tmp_path, tmp_path / "out-watchdog-input", copy_priority=False)
    assert sorted(path.name for path in names.glob("running-*.txt")) == ["running-11.txt", "running-12.txt"]


def test_a_lane_stopped_for_host_resources_is_its_own_death_kind_not_an_unclassified_one(tmp_path):
    import json

    check = _load("check_evidence_run")
    job = {"id": 7, "name": "regression 2/3 (windows-latest)", "conclusion": "failure"}
    full = tmp_path / "evidence-one-attempt-1"
    full.mkdir()
    (full / "runner-resources-job.txt").write_text(json.dumps({"job_label": job["name"]}))
    (full / "runner-resources-lane-exit.txt").write_text(json.dumps({"lane_exit": 72}))
    rows = []
    check.check_jobs(tmp_path, [job], score_rows=rows)
    assert rows[0]["kind"] == "unclassified" and any("[job-kind]" in d for d in rows[0]["missing"])
    (full / _load("lane_step").HOST_STOP_FILE).write_text(json.dumps({"crossed": [{"resource": "processes"}]}))
    rows = []
    check.check_jobs(tmp_path, [job], score_rows=rows)
    assert rows[0]["kind"] == "host-resources" and not any("[job-kind]" in d for d in rows[0]["missing"])
