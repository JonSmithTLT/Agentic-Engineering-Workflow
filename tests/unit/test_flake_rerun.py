"""The lane verdict and assurance independently enforce the flake policy."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "ci"))
import check_assurance as assurance  # noqa: E402
import flake_assurance as policy  # noqa: E402
import flake_rerun as rerun  # noqa: E402

FILE = "tests/unit/test_flake_probe.py"
NODE = FILE + "::test_probe"
OTHER = FILE + "::test_other"
JOB = {"id": 25, "started_at": "2026-11-11T12:34:56Z"}


def register(node=NODE, platform=None, *, scope="test"):
    return {"entries": [{"id": "probe", "test": node, "status": "open", "scope": scope,
                         "platforms": [platform or rerun.PLATFORMS[sys.platform]], "lane": "fast"}]}


def report(root, *, attempt=1, exitstatus=1, problems=(), nodes=(NODE,)):
    path = root / f"attempt-{attempt}" / "fast.json"
    path.parent.mkdir(parents=True)
    payload = {"schema": rerun.LANE_SCHEMA, "platform": sys.platform, "lane": "fast",
               "attempt": attempt, "shard": "1/1", "exitstatus": exitstatus, "session_problems": list(problems),
               "collected": list(nodes),
               "results": {node: {"outcome": "passed" if not exitstatus else "failed", "duration": 0.1}
                           for node in nodes}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def record(path, node=NODE, **overrides):
    data = json.loads(path.read_text(encoding="utf-8"))
    record_path = rerun.rerun_root(path) / str(len(list(rerun.rerun_root(path).glob("*")))) / "result.json"
    record_path.parent.mkdir(parents=True)
    evidence = {"schema": rerun.RERUN_SCHEMA, "platform": data["platform"], "exitstatus": 0,
                "process_exit": 0, "lane_report": rerun.report_identity(data), "session_problems": [],
                "collected": [node], "results": {node: "passed"}, **overrides}
    record_path.write_text(json.dumps(evidence), encoding="utf-8")
    return record_path


def marker(root, kind):
    path = root / "autopsy" / "session-12-abc" / f"{kind}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pid 123: process-name\n", encoding="utf-8")


def judge(root, doc, changed=()):
    reports = assurance.all_reports(root)
    latest = assurance.latest_attempts(reports)
    verdict = policy.Assessment()
    policy.assess_reports(verdict, root, doc, set(changed), reports, latest,
                          {policy.report_key(r): JOB for r in reports})
    errors, _ = assurance.check(latest, {}, [sys.platform], forgiven=verdict.forgiven)
    return verdict, [*errors, *verdict.problems]


@pytest.mark.parametrize("case", ["known", "unknown", "wrong-platform", "failed-again", "tripwire", "checkout-guard",
                                  "mixed", "changed", "no-record", "wrong-record-platform", "wrong-attempt",
                                  "wrong-shard", "left-running", "session-only", "deadline", "duplicate-record",
                                  "rerun-left-running"])
def test_only_a_registered_exact_clean_rerun_can_satisfy_assurance(tmp_path, case):
    path = report(tmp_path, exitstatus=70 if case == "deadline" else 1,
                  problems=[case] if case in ("tripwire", "checkout-guard") else [],
                  nodes=(NODE, OTHER) if case == "mixed" else (NODE,))
    wrong_platform = "linux" if sys.platform == "win32" else "windows"
    doc = register(platform=wrong_platform if case == "wrong-platform" else None,
                   scope="session" if case == "session-only" else "test")
    if case == "unknown":
        doc = {"entries": []}
    if case != "no-record":
        changes: dict[str, Any] = {}
        if case == "failed-again":
            changes = {"exitstatus": 1, "process_exit": 1, "results": {NODE: "failed"}}
        if case == "wrong-record-platform":
            changes = {"platform": "other"}
        if case in ("wrong-attempt", "wrong-shard"):
            identity = rerun.report_identity(json.loads(path.read_text(encoding="utf-8")))
            identity.update({"attempt": 2} if case == "wrong-attempt" else {"shard": "2/2"})
            changes = {"lane_report": identity}
        evidence = record(path, **changes)
        if case == "rerun-left-running":
            marker(evidence.parent, "left-running")
    if case == "mixed":
        record(path, OTHER)
    if case == "left-running":
        marker(path.parent, "left-running")
    if case == "duplicate-record":
        record(path)
    verdict, errors = judge(tmp_path, doc, [FILE] if case == "changed" else [])
    assert (not errors) == (case == "known"), errors
    assert len(assurance.all_reports(tmp_path)) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["results"][NODE]["outcome"] == "failed"
    if case == "known":
        assert verdict.sightings == [dict(JOB_ID, observation=NODE)]
        assert "`" + NODE + "`" in verdict.summary()
    if case == "unknown":
        assert "passed alone" in verdict.summary()
        assert not verdict.sightings
    if case == "mixed":
        assert not verdict.forgiven


JOB_ID = {"entry": "probe", "job": JOB["id"], "at": JOB["started_at"]}


@pytest.mark.parametrize("marker_name", sorted(rerun.MARKERS))
def test_green_session_markers_are_visible_and_count_as_one_sighting(tmp_path, marker_name):
    path = report(tmp_path, exitstatus=0)
    marker(path.parent, marker_name)
    verdict, errors = judge(tmp_path, register(scope="session"))
    assert not errors
    assert marker_name in verdict.summary() and "process-name" in verdict.summary()
    assert verdict.sightings == [JOB_ID]


def test_a_later_attempt_cannot_hide_an_unregistered_failure_even_after_resharding(tmp_path):
    report(tmp_path)
    path = report(tmp_path, attempt=2, exitstatus=0)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["shard"] = "1/2"
    path.write_text(json.dumps(data), encoding="utf-8")
    reports = assurance.all_reports(tmp_path)
    assert assurance.latest_attempts(reports) == [reports[1]]
    for doc, blocked in [({"entries": []}, True), (register(), False)]:
        result = policy.Assessment()
        policy.assess_reports(result, tmp_path, doc, set(), reports, reports[1:],
                              {policy.report_key(reports[0]): JOB})
        assert bool(result.problems) is blocked


def test_a_passing_attempt_cannot_hide_an_earlier_isolation_failure(tmp_path):
    report(tmp_path, problems=["git isolation tripwire"])
    report(tmp_path, attempt=2, exitstatus=0)
    verdict, errors = judge(tmp_path, register())
    assert errors == [f"{sys.platform}: fast had a session failure in earlier attempt 1"]
    assert not verdict.sightings


@pytest.mark.parametrize("case", [
    "failed-alone", "failed-with-marker", "passed-alone", "absent", "wrong-attempt", "error-alone",
])
def test_earlier_registered_failure_uses_its_own_isolated_record(tmp_path, case):
    path = report(tmp_path)
    if case in ("failed-alone", "failed-with-marker", "error-alone", "wrong-attempt"):
        identity = rerun.report_identity(json.loads(path.read_text(encoding="utf-8")))
        if case == "wrong-attempt":
            identity["attempt"] = 2
        evidence = record(path, exitstatus=1, process_exit=1, lane_report=identity,
                          results={NODE: "error" if case == "error-alone" else "failed"})
        if case == "failed-with-marker":
            marker(evidence.parent, "left-running")
    elif case == "passed-alone":
        record(path)
    report(tmp_path, attempt=2, exitstatus=0)
    verdict, errors = judge(tmp_path, register())
    if case in ("failed-alone", "failed-with-marker", "error-alone"):
        assert len(errors) == 1 and "failed twice in attempt 1" in errors[0]
        assert not verdict.sightings
    else:
        assert not errors
        assert "failed in earlier attempt 1" in verdict.summary()
        assert verdict.sightings == [{**JOB_ID, "observation": NODE}]


@pytest.mark.parametrize("status,problems", [(2, ()), (1, ("xdist worker stopped unexpectedly",))])
def test_a_later_pass_clears_an_interrupted_earlier_session(tmp_path, status, problems):
    report(tmp_path, exitstatus=status, problems=problems, nodes=())
    report(tmp_path, attempt=2, exitstatus=0)
    verdict, errors = judge(tmp_path, {"entries": []})
    assert not errors and not verdict.sightings
    assert f"ended in earlier attempt 1 with exit {status}" in verdict.summary()


@pytest.mark.parametrize("status", [0, 1])
def test_main_fetch_failure_only_prevents_forgiveness(tmp_path, monkeypatch, status):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("REUSE_RUN", raising=False)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    path = report(tmp_path, exitstatus=status)
    if status:
        record(path)
    calls = []

    def unavailable():
        calls.append("fetch")
        raise subprocess.CalledProcessError(1, ["git", "fetch"])

    monkeypatch.setattr(rerun, "tip_register", unavailable)
    history = assurance.all_reports(tmp_path)
    verdict = policy.assess(tmp_path, history, history, "push")
    assert not verdict.problems and not verdict.forgiven
    assert calls == (["fetch"] if status else [])
    errors, _ = assurance.check(history, {}, [sys.platform], forgiven=verdict.forgiven)
    assert bool(errors) is bool(status)


@pytest.mark.parametrize("known,named,setup,changed,expected", [
    (True, "", False, False, False), (False, "", False, False, True),
    (True, NODE, False, False, False), (True, NODE, False, True, True),
    (True, OTHER, False, False, True), (False, "", True, False, False),
])
def test_earlier_hang_needs_a_session_entry_and_a_named_test_needs_its_own_entry(
    tmp_path, known, named, setup, changed, expected,
):
    report(tmp_path, attempt=2, exitstatus=0)
    latest = assurance.all_reports(tmp_path)
    key = (sys.platform, "fast", "1/1", 1)
    folder = policy.artifact_path(tmp_path, key)
    if named:
        reason = folder / "autopsy" / "test-hash" / "reason.txt"
        reason.parent.mkdir(parents=True)
        reason.write_text(f"[gw1 pid 123] {named}: the session deadline passed\n", encoding="utf-8")
    doc = register(scope="session") if known else {"entries": []}
    if named:
        doc["entries"].extend(register()["entries"])
    job = {**JOB, "name": "fast 1/1 (ubuntu-latest)", "conclusion": "timed_out",
           "html_url": "https://example.invalid/old-job",
           "steps": [{"name": "setup" if setup else "fast lane", "started_at": JOB["started_at"]}]}
    result = policy.Assessment()
    policy.assess_hangs(result, tmp_path, doc, {FILE} if changed else set(), latest, latest, {key: job}, "o/r")
    assert bool(result.problems) is expected
    assert ("https://example.invalid/old-job" in result.summary()) is not setup
    assert bool(result.sightings) is (known and not setup)


@pytest.mark.parametrize("message,hung", [
    ("The runner has stopped hearing from this job", True), ("Cancelled by operator", False),
])
def test_earlier_cancelled_pytest_job_needs_no_response_evidence(tmp_path, monkeypatch, message, hung):
    report(tmp_path, attempt=2, exitstatus=0)
    latest = assurance.all_reports(tmp_path)
    key = (sys.platform, "fast", "1/1", 1)
    job = {**JOB, "name": "fast 1/1 (ubuntu-latest)", "conclusion": "cancelled",
           "html_url": "https://example.invalid/old-job",
           "steps": [{"name": "fast lane", "started_at": JOB["started_at"], "conclusion": "cancelled"}]}
    monkeypatch.setattr(policy, "pages", lambda endpoint: (
        [{"message": message}] if endpoint.endswith("/check-runs/25/annotations") else pytest.fail(endpoint)
    ))
    result = policy.Assessment()
    policy.assess_hangs(result, tmp_path, register(scope="session"), set(), latest, latest, {key: job}, "o/r")
    assert bool(result.sightings) is hung
    assert not result.problems


@pytest.mark.parametrize("outcome,write_report", [("success", False), ("cancelled", False), ("failure", False),
                                                   ("failure", True)])
def test_lane_does_not_try_to_recover_cancellation_missing_report_or_a_deadline(
    tmp_path, monkeypatch, outcome, write_report,
):
    path = report(tmp_path, exitstatus=70) if write_report else tmp_path / "absent.json"
    monkeypatch.setattr(rerun, "tip_register", lambda: pytest.fail("unexpected fetch"))
    assert rerun.decide(path, outcome, "", "HEAD", False, True) == int(outcome != "success")


def test_evidence_runs_at_most_three_distinct_nodes_and_never_turns_the_lane_green(tmp_path, monkeypatch, capsys):
    nodes = tuple(f"{FILE}::test_probe[{index}]" for index in range(5))
    path = report(tmp_path, nodes=nodes)
    monkeypatch.setattr(rerun, "tip_register", lambda: register(nodes[-1]))
    monkeypatch.setenv("AEW_JOB_DEADLINE", "1")
    called = []
    monkeypatch.setattr(rerun, "run_once", lambda _, node, *_args: called.append(node) or True)
    assert rerun.decide(path, "failure", "", "HEAD", False, True) == 1
    assert called == [nodes[-1], *nodes[:3]]
    assert capsys.readouterr().out.count("evidence only") == 3
    called.clear()
    assert rerun.decide(path, "failure", "", "HEAD", False, False) == 1
    assert called == [nodes[-1]]


def test_an_exhausted_budget_does_not_start_pytest(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rerun.subprocess, "run", lambda *_a, **_kw: pytest.fail("unexpected process"))
    assert not rerun.run_once({}, NODE, tmp_path / "rerun", time.time() - 1, False)
    assert "not re-run (budget)" in capsys.readouterr().out


def test_a_timed_out_child_cannot_pass_and_is_started_without_a_window_on_windows(tmp_path, monkeypatch, capsys):
    from bounds import DEADLINE_MARGIN_S, SESSION_END_MARGINS

    def timeout(command, **options):
        assert command[-2:] == ["--", NODE]
        assert "-p" in command and "no:xdist" in command
        assert options["stdin"] == subprocess.DEVNULL
        assert options["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
        session = int(command[command.index("--session-deadline") + 1])
        assert options["timeout"] == session + DEADLINE_MARGIN_S * SESSION_END_MARGINS
        raise subprocess.TimeoutExpired(command, options["timeout"])

    monkeypatch.setattr(rerun.subprocess, "run", timeout)
    assert not rerun.run_once({}, NODE, tmp_path / "rerun", time.time() + 30, False)
    assert "re-run exceeded the session deadline and autopsy margins" in capsys.readouterr().out


@pytest.mark.parametrize("registered,passes,covered", [
    (True, True, True), (False, True, False), (True, False, False),
])
def test_the_actual_isolated_pytest_path_emits_one_report_and_leaves_the_original(
    tmp_path, monkeypatch, registered, passes, covered,
):
    # The first session creates the flag and fails. The isolated session can pass only if it sees that flag
    # and selects exactly the probe node.
    test = tmp_path / FILE
    test.parent.mkdir(parents=True)
    test.write_text(
        "from pathlib import Path\n\n"
        "def test_probe():\n"
        "    flag = Path('first-session')\n"
        "    seen = flag.exists()\n"
        "    flag.touch()\n"
        f"    assert seen and {passes}\n\n"
        "def test_other():\n    assert False\n", encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text(
        "import lanes\nimport session_deadline\nimport watchdog\n"
        "def pytest_addoption(parser):\n    lanes.addoption(parser)\n"
        "    session_deadline.addoption(parser)\n    watchdog.addoption(parser)\n"
        "def pytest_configure(config):\n    lanes.configure(config)\n", encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(
        [str(ROOT / "tests" / "helpers"), str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]
    ))
    monkeypatch.setenv("AEW_JOB_DEADLINE", str(time.time() + 90))
    coverage_dir = tmp_path / "coverage"
    if covered:
        import importlib.util

        covered = importlib.util.find_spec("coverage") is not None
    if covered:
        coverage_dir.mkdir()
        monkeypatch.setenv("COVERAGE_FILE", str(coverage_dir / ".coverage"))
        (tmp_path / ".coveragerc").write_text("[run]\nparallel = True\n", encoding="utf-8")
    monkeypatch.setattr(rerun, "tip_register", register if registered else lambda: {"entries": []})
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    path = tmp_path / "original" / "fast.json"
    wrapper = ["coverage", "run", "-m", "pytest"] if covered else ["pytest"]
    initial = subprocess.run([sys.executable, "-m", *wrapper, "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                              "--lane", "fast", "--shard", "1/1", f"--lane-report={path}", NODE],
                             check=False, timeout=60, stdin=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert initial.returncode == 1
    coverage_before = set(coverage_dir.glob(".coverage.*"))
    original = path.read_bytes()
    assert rerun.decide(path, "failure", "", "HEAD", covered, True) == int(not (registered and passes))
    assert path.read_bytes() == original
    evidence = list(rerun.rerun_root(path).glob("*/result.json"))
    assert len(evidence) == 1
    assert json.loads(evidence[0].read_text(encoding="utf-8"))["results"] == {NODE: "passed" if passes else "failed"}
    verdict, errors = judge(tmp_path, register() if registered else {"entries": []})
    assert (not errors) == (registered and passes), errors
    assert bool(verdict.sightings) == (registered and passes)
    if covered:
        import coverage

        assert len(set(coverage_dir.glob(".coverage.*")) - coverage_before) == 1
        data = coverage.Coverage(data_file=str(coverage_dir / ".coverage"))
        data.combine(strict=True)
        assert 7 in (data.get_data().lines(str(test.resolve())) or [])


def test_failed_main_fetch_refuses_before_starting_any_rerun(tmp_path, monkeypatch):
    def refuse(*args):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(rerun, "git", refuse)
    monkeypatch.setattr(rerun, "run_once", lambda *_args: pytest.fail("unexpected re-run"))
    assert rerun.main(["--outcome", "failure", "--report", str(report(tmp_path)), "--evidence"]) == 1


def test_the_shallow_pr_checkout_reads_main_and_differs_against_its_first_parent(tmp_path, monkeypatch):
    import yaml

    origin = tmp_path / "origin"
    origin.mkdir()
    monkeypatch.chdir(origin)
    rerun.git("init", "-b", "main")
    rerun.git("config", "user.email", "aew-test@invalid")
    rerun.git("config", "user.name", "CI test")
    test = Path(FILE)
    test.parent.mkdir(parents=True)
    test.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    pin = Path("tests/flake-register.yaml")
    entry = register()["entries"][0]
    entry.update({"class": "test", "cause": "unknown", "owner": "tests",
                  "evidence": [{"run": 12, "job": 34, "at": JOB["started_at"]}]})
    pin.write_text(yaml.safe_dump({"schema": rerun.flake_register.SCHEMA, "entries": [entry], "census": []}),
                   encoding="utf-8")
    rerun.git("add", "tests")
    rerun.git("commit", "-m", "main's register")
    rerun.git("switch", "-c", "topic")
    test.write_text("def test_probe():\n    assert False\n", encoding="utf-8")
    pin.write_text("forged register\n", encoding="utf-8")
    rerun.git("add", "tests")
    rerun.git("commit", "-m", "change test and pin")
    rerun.git("switch", "-c", "pr-merge", "main")
    rerun.git("merge", "--no-ff", "topic")
    monkeypatch.chdir(tmp_path)
    rerun.git("clone", "--depth=2", "--branch", "pr-merge", origin.as_uri(), "ci")
    monkeypatch.chdir(tmp_path / "ci")
    assert rerun.git("rev-parse", "--is-shallow-repository").strip() == "true"
    assert rerun.tip_register()["entries"] == [entry]
    assert rerun.changed_paths("pull_request", "HEAD") == {FILE, "tests/flake-register.yaml"}


def test_pr_own_registered_failure_stays_red_and_does_not_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(rerun, "tip_register", register)
    monkeypatch.setattr(rerun, "changed_paths", lambda *_args: {FILE})
    monkeypatch.setenv("AEW_JOB_DEADLINE", "1")
    monkeypatch.setattr(rerun, "run_once", lambda *_args: pytest.fail("unexpected re-run"))
    assert rerun.decide(report(tmp_path), "failure", "pull_request", "HEAD", False, True) == 1


@pytest.mark.parametrize("case", [
    "candidate", "changed", "registered", "unreadable", "malformed", "reuse", "success", "stall",
])
def test_previous_pr_run_candidates_are_observational_and_only_record_readable_unchanged_new_cases(
    tmp_path, monkeypatch, case,
):
    current = tmp_path / "current"
    report(current, exitstatus=0)
    latest = assurance.all_reports(current)
    monkeypatch.setenv("PR_NUMBER", "4")
    monkeypatch.setenv("PR_HEAD_REF", "a-branch")
    runs = {"workflow_runs": [{
        "id": 12, "status": "completed", "event": "pull_request", "path": ".github/workflows/ci.yml",
        "head_repository": {"full_name": "o/r"}, "repository": {"full_name": "o/r"},
        "head_branch": "a-branch", "conclusion": "success" if case == "success" else "failure",
    }]}
    calls = []

    def gh(*args):
        if args[0] == "api":
            return json.dumps(runs)
        calls.append(args[:3])
        if case == "unreadable":
            raise OSError("expired")
        if case == "stall":
            raise subprocess.TimeoutExpired(args, 60)
        path = report(Path(args[-1]))
        if case == "malformed":
            path.write_text("[]", encoding="utf-8")

        return ""

    monkeypatch.setattr(policy, "gh", gh)
    monkeypatch.setattr(rerun.flake_register, "_api", lambda repo, endpoint: (
        {"head": {"ref": "a-branch", "repo": {"full_name": "o/r"}}}
        if (repo, endpoint) == ("o/r", "pulls/4") else pytest.fail(endpoint)
    ))
    verdict = policy.Assessment()
    policy.previous_run(verdict, current, latest, register() if case == "registered" else {"entries": []},
                        {FILE} if case == "changed" else set(), "o/r", 13, "12" if case == "reuse" else "")
    assert not verdict.problems and not verdict.forgiven and not verdict.sightings
    assert calls == ([] if case in ("reuse", "success") else [("run", "download", "12")])
    assert bool(verdict.candidates) is (case == "candidate")
    assert ("Likely new flake" in verdict.summary()) is (case == "candidate")
    assert ("could not be read" in verdict.summary()) is (case in ("unreadable", "malformed", "stall"))
    path = tmp_path / "candidates.json"
    policy.publish_candidates(path, verdict)
    assert path.exists() is (case == "candidate")


def test_a_forged_candidate_cannot_change_the_gate_or_become_a_sighting(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    lane = tmp_path / "lane"
    path = report(lane)
    record(path)
    candidate = tmp_path / "candidate" / "candidates.json"
    monkeypatch.setenv("PR_NUMBER", "4")
    policy.publish_candidates(candidate, policy.Assessment(candidates=[
        {"test": NODE, "platform": rerun.PLATFORMS[sys.platform]}
    ]))
    skips = tmp_path / "skips.yaml"
    skips.write_text(f"schema: {assurance.SKIPS_SCHEMA}\n", encoding="utf-8")
    monkeypatch.setattr(rerun, "tip_register", lambda: {"entries": []})
    args = [str(tmp_path), "--skips", str(skips), "--require", sys.platform, "--flake-policy"]
    assert assurance.main(args) == 1
    path = report(tmp_path / "passing", exitstatus=0)
    verdict = policy.Assessment(candidates=[{"test": NODE, "platform": rerun.PLATFORMS[sys.platform]}])
    monkeypatch.setattr(policy, "assess", lambda *_args: verdict)
    monkeypatch.setattr(policy, "publish_candidates",
                        lambda *_args: (_ for _ in ()).throw(OSError("candidate disk write failed")))
    assert assurance.main([str(path.parent), *args[1:], "--candidates", str(candidate)]) == 0


def test_pr_sighting_index_binds_the_pr_and_preserves_earlier_attempt_evidence(tmp_path, monkeypatch):
    for key, value in {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REPOSITORY": "o/r",
                       "GITHUB_RUN_ID": "13", "GITHUB_RUN_ATTEMPT": "2", "PR_NUMBER": "4"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("REUSE_RUN", raising=False)
    monkeypatch.setattr(policy, "pages", lambda *_args: [{"name": "flake-sighting-index", "expired": False}])
    earlier = {**JOB_ID, "observation": NODE}

    def download(*args):
        assert args[:3] == ("run", "download", "13")
        path = Path(args[-1]) / "sightings.json"
        path.write_text(json.dumps({"pr": 4, "sightings": [earlier]}), encoding="utf-8")
        return ""

    monkeypatch.setattr(policy, "gh", download)
    new = {**JOB_ID, "job": 26}
    current = {**earlier, "at": "2026-11-11T23:45:56Z"}
    path = tmp_path / "sightings.json"
    policy.publish(path, policy.Assessment(sightings=[current, new]))
    assert json.loads(path.read_text(encoding="utf-8")) == {"pr": 4, "sightings": [earlier, new]}
