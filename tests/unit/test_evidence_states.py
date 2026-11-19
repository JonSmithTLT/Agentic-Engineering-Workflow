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

    for path in (ROOT / ".github/workflows").glob("*.yml"):
        doc = yaml.safe_load(path.read_text())
        for job in doc.get("jobs", {}).values():
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
