"""A failed harness test names its runs' state and keeps their files (tests/helpers/harness_diagnostics.py; register
E3): a Windows failure on 2026-10-09 said only "no transcript step 2", and the run directory that would have told a
stalled supervisor (``lost``) from a crashed one was deleted with the test's ``tmp_path``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import harness_diagnostics as D
import lanes
from conftest import IS_WINDOWS

from aew.harness import runlog

HELPERS = Path(lanes.__file__).resolve().parent
TOKEN = "aew1.tk_" + "0" * 16 + "." + "A" * 43  # built here: no credential-shaped string sits in any file


class Lab:
    """What the diagnostics read from a HarnessLab: its project root and AEW root."""

    def __init__(self, root: Path) -> None:
        self.root, self.aew_root = root, root / ".aew"


def a_run(lab: Lab, run: str, *, status: str = "running", beat: bool = False) -> Path:
    directory = runlog.run_dir(lab.aew_root, run)
    (directory / "harness").mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps({"run": run, "status": status, "reason": "watch loop stalled",
                                                    "supervisor_pid": 4242}), encoding="utf-8")
    (directory / "supervisor.log").write_text("Traceback (most recent call last):\nPermissionError: heartbeat\n"
                                              f"credential {TOKEN}\n", encoding="utf-8")
    (directory / "harness" / "transcript.jsonl").write_text('{"i": 0}\n{"i": 1}\n', encoding="utf-8")
    if beat:
        runlog.beat(directory)
    return directory


def test_a_run_is_described_by_its_record_what_an_observer_sees_and_its_logs(tmp_path):
    lab = Lab(tmp_path)
    text = D.describe_run(a_run(lab, "R-INV-0001-1"))
    assert "recorded running, observed lost, heartbeat absent" in text  # the record alone would say "running"
    assert "watch loop stalled" in text and "supervisor_pid 4242" in text
    assert "PermissionError: heartbeat" in text and '{"i": 1}' in text
    assert TOKEN not in text and "aew1.<redacted>" in text


def test_the_evidence_is_copied_redacted_and_never_as_json(tmp_path):
    lab = Lab(tmp_path / "proj")
    a_run(lab, "R-INV-0001-1", beat=True)
    copied, failed = D.copy_evidence(lab, tmp_path / "out")
    assert not failed
    names = sorted(p.name for p in copied)
    assert names == ["harness__transcript.jsonl.txt", "heartbeat.txt", "run.json.txt", "supervisor.log.txt"]
    assert not list((tmp_path / "out").rglob("*.json"))  # the assurance tools read every *.json as a lane report
    assert all(TOKEN not in p.read_text(encoding="utf-8") for p in copied)


def test_a_credential_cut_by_a_bound_is_still_redacted(tmp_path):
    """#136 review, F1: redaction runs on the whole text before a line is cut to its bound or a file to its tail, so
    a credential straddling the cut never leaves a piece the pattern no longer matches."""
    lab = Lab(tmp_path / "proj")
    directory = a_run(lab, "R-INV-0001-1")
    secret = TOKEN.split(".")[-1]
    line = "x" * (D.LINE_CHARS - 30) + TOKEN + " tail"  # the token straddles the 300-character cut
    (directory / "harness" / "transcript.jsonl").write_text(line + "\n", encoding="utf-8")
    (directory / "harness" / "agent.log").write_text("y" * 10 + TOKEN + "z" * D.MAX_COPY_BYTES, encoding="utf-8")
    text = D.describe_run(directory)
    copied, failed = D.copy_evidence(lab, tmp_path / "out")
    assert not failed
    for out in [text, *(p.read_text(encoding="utf-8") for p in copied)]:
        assert secret[:12] not in out


def test_a_file_whose_last_line_outruns_the_bound_keeps_that_line(tmp_path):
    """#136 re-review, F5: cutting to a line boundary must never leave nothing, as it did for a long last line."""
    lab = Lab(tmp_path / "proj")
    directory = a_run(lab, "R-INV-0001-1")
    (directory / "harness" / "agent.log").write_text("first\n" + "q" * (D.MAX_COPY_BYTES + 10) + "\n",
                                                     encoding="utf-8")
    copied, _ = D.copy_evidence(lab, tmp_path / "out")
    text = next(p for p in copied if p.name == "harness__agent.log.txt").read_text(encoding="utf-8")
    assert text.startswith("[… earlier text not copied]") and text.count("q") > D.MAX_COPY_BYTES - 100


def test_two_tests_whose_ids_differ_only_in_punctuation_keep_separate_evidence():
    """#136 review, F2: parametrized ids such as ``[a/b]`` and ``[a b]`` map to one readable name; the full id's
    digest keeps their directories apart."""
    a, b = D._safe("t.py::test[a/b]"), D._safe("t.py::test[a b]")
    assert a != b and a.startswith("t.py_test_a_b_-") and b.startswith("t.py_test_a_b_-")
    assert len(D._safe("x" * 500)) <= 131


def test_one_unreadable_file_never_stops_the_rest_of_the_copy(tmp_path, monkeypatch):
    """#136 review, F3: a read that fails (on Windows, a collision with the supervisor's replace of run.json) is
    reported, and every other file is still copied."""
    lab = Lab(tmp_path / "proj")
    a_run(lab, "R-INV-0001-1")
    real = D._read

    def flaky(path):
        if path.name == "run.json":
            raise PermissionError(13, "sharing violation", str(path))
        return real(path)

    monkeypatch.setattr(D, "_read", flaky)
    copied, failed = D.copy_evidence(lab, tmp_path / "out")
    assert [f.split(":")[0] for f in failed] == ["R-INV-0001-1/run.json"]
    assert sorted(p.name for p in copied) == ["harness__transcript.jsonl.txt", "supervisor.log.txt"]


CONFTEST = f'''
import sys
sys.path.insert(0, {str(HELPERS)!r})
import pytest
import harness_diagnostics
import lanes


def pytest_addoption(parser):
    lanes.addoption(parser)
    harness_diagnostics.addoption(parser)


def pytest_configure(config):
    lanes.configure(config)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    harness_diagnostics.report(item, outcome.get_result())


def pytest_runtest_logfinish(nodeid, location):
    harness_diagnostics.forget()
'''
TESTS = '''
import json
from pathlib import Path

import harness_diagnostics
from aew.harness import runlog


class Lab:
    def __init__(self, root):
        self.root, self.aew_root = root, root / ".aew"


def lab_with_a_run(tmp_path):
    lab = Lab(tmp_path)
    harness_diagnostics.register(lab)
    d = runlog.run_dir(lab.aew_root, "R-INV-0001-1")
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"status": "crashed", "reason": "supervisor error: boom"}))
    (d / "supervisor.log").write_text("Traceback\\nRuntimeError: boom\\n")


def test_fails(tmp_path):
    lab_with_a_run(tmp_path)
    assert False, "no transcript step 2"


def test_passes(tmp_path):
    lab_with_a_run(tmp_path)


def test_fails_without_a_lab():
    assert False
'''


def test_a_failed_harness_test_reports_its_runs_and_keeps_their_files_where_ci_uploads(tmp_path):
    root = tmp_path / "proj"
    (root / "tests" / "unit").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (root / "tests" / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    (root / "tests" / "unit" / "test_d.py").write_text(TESTS, encoding="utf-8")
    reports = root / "reports"  # inside the checkout: the copies are the session's own output (#136 review, F4)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))}
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                           "--lane-report", str(reports / "r.json"), "tests"], cwd=root, env=env,
                          capture_output=True, text=True, timeout=240, **kwargs)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "aew harness runs" in out and "recorded crashed" in out and "supervisor error: boom" in out, out
    assert "isolation guard" not in out, out
    kept = reports / "harness-runs"
    dirs = sorted(p.name for p in kept.iterdir())
    # Only the failed test that had a lab keeps files.
    assert len(dirs) == 1 and "test_fails-" in dirs[0] and dirs[0].endswith("-call"), dirs
    assert (kept / dirs[0] / "R-INV-0001-1" / "supervisor.log.txt").read_text(encoding="utf-8").endswith("boom\n")
    sys.path.insert(0, str(HELPERS.parents[1] / "tools" / "ci"))
    import check_assurance

    assert [r["_source"] for r in check_assurance.load_reports(reports)] == ["r.json"]  # the copies are not reports
