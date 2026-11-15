"""`aew notify file PATH`, the headless notifier for an endpoint with no desktop session: one JSON line per event, never
its reason; `--check` says whether the path can take them; Run's notifier gate passes with it on a host with no desktop
session; it is bounded and rotated like the delivery log; a delivery it cannot make is the notifier's failure."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from aew.cli.main import main
from aew.engine import steering
from aew.harness import desktop_notifier as D
from aew.harness import file_notifier as F
from aew.harness import notify, procs

EVENT = {"schema": "aew/notify-event/v1", "event": "raise_requested", "project_id": "demo", "subject": "SR-1",
         "reason": "the Lead's own words", "ref": "run", "revision": 7, "at": "2026-11-11T00:00:00Z",
         "source": "control_state", "authenticated": True}


def test_an_event_is_appended_as_one_line_without_its_reason(tmp_path, monkeypatch, capsys):
    path = tmp_path / "new" / "dir" / "events.jsonl"  # its parents are made
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(EVENT).encode())))
    assert main(["notify", "file", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["appended"] == str(path)
    F.append({**EVENT, "event": "hard_deadline", "subject": "R-INV-0001-1"}, str(path))
    text = path.read_text(encoding="utf-8")
    first, second = (json.loads(line) for line in text.splitlines())
    title, body = D.text(EVENT)
    assert (first["title"], first["body"], first["event"], first["subject"], first["revision"]) == (
        title, body, "raise_requested", "SR-1", 7)
    assert second["event"] == "hard_deadline" and second["authenticated"] is True
    assert "the Lead's own words" not in text and "reason" not in first


def test_check_says_whether_the_path_can_take_the_events_and_writes_nothing(tmp_path, capsys):
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    for path, why in [("relative/events.jsonl", "is not absolute"),
                      (str(blocker / "events.jsonl"), "is not a directory it can write"),
                      (str(tmp_path), "is not a regular file")]:
        out = F.availability(path)
        assert out["available"] is False and why in out["why"] and out["fix"] == F.FIX, (path, out)
    path = tmp_path / "later" / "events.jsonl"
    assert main(["notify", "file", str(path), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["available"] is True
    assert not path.parent.exists(), "a check writes nothing"


def test_run_s_notifier_gate_passes_with_it_on_a_host_with_no_desktop_session(tmp_path, monkeypatch):
    for name in D.SESSION_VARS:
        monkeypatch.delenv(name, raising=False)
    desktop = steering.notifier_problem({"notify": {"command": list(D.COMMAND)}})
    assert desktop is not None and "aew, notify, file" in desktop, "the desktop one is refused, naming this one"
    command = ["aew", "notify", "file", str(tmp_path / "events.jsonl")]
    assert steering.notifier_problem({"notify": {"command": command}}) is None
    bad = steering.notifier_problem({"notify": {"command": ["aew", "notify", "file", "relative.jsonl"]}})
    assert bad is not None and "is not absolute" in bad
    assert D.runnable(command) == [sys.executable, *procs.ENGINE_PYTHON_FLAGS, "-m", "aew", "notify", "file",
                                   command[3]], "the endpoint runs it as its own engine"


def test_it_is_bounded_and_rotated_like_the_delivery_log(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "LOG_MAX_BYTES", 600)
    path = tmp_path / "events.jsonl"
    for n in range(12):
        F.append({**EVENT, "subject": f"SR-{n}"}, str(path))
    kept = [path, *(path.with_name(f"{path.name}.{n}") for n in range(1, notify.LOG_KEEP + 1))]
    assert all(p.exists() for p in kept) and not path.with_name(f"{path.name}.{notify.LOG_KEEP + 1}").exists()
    assert all(p.stat().st_size <= 600 for p in kept)
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["subject"] == "SR-11"


def test_it_is_recognised_by_its_argv_with_one_path(tmp_path):
    assert F.matches(["aew", "notify", "file", str(Path(tmp_path))])
    assert F.matches(["/usr/local/bin/aew", "notify", "file", "/x"]) and not F.matches(["aew", "notify", "file"])
    assert not F.matches(["aew", "notify", "desktop", "/x"])
