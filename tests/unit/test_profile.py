"""`AEW_PROFILE` (M3 step 7): exclusive phase accounting, and a record that names a command by its leading words
only, so no option value (a credential passed with --token included) ever reaches the profile file."""

from __future__ import annotations

import json

from aew import profile
from aew.cli import main as cli

FORGED = "aew1.tk_" + "0" * 16 + "." + "S" * 43


def test_command_words_keep_no_option_or_value():
    assert profile.command_words(["-C", "/some/dir", "work", "assign", "T-0001", "--token", FORGED]) == "work assign"
    assert profile.command_words(["--token", FORGED, "status"]) == ""
    assert profile.command_words(["resume", "--json"]) == "resume"
    assert profile.command_words(["harness", "wait", "R-INV-0001-1"]) == "harness wait"


def test_phases_are_exclusive(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(profile.time, "perf_counter", lambda: now[0])

    def spend(s: float) -> None:
        now[0] += s

    profile.start()
    spend(1)                           # compute
    with profile.phase("recover"):
        spend(2)
        with profile.phase("parse"):
            spend(5)
        spend(3)
    summary = profile.stop()
    assert summary["total_s"] == 11
    assert {k: v for k, v in summary["phases_s"].items() if v} == {"recover": 5, "parse": 5, "compute": 1}


def test_a_profiled_command_writes_one_record_without_its_arguments(tmp_path, monkeypatch):
    out = tmp_path / "profile.jsonl"
    monkeypatch.setenv(profile.ENV, str(out))
    code = cli.main(["-C", str(tmp_path), "checkpoint", "--next", "x", "--token", FORGED, "--expect-rev", "0"])
    assert code != 0  # not a project: the command fails, and is still recorded
    [line] = out.read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert (record["schema"], record["command"], record["exit"]) == (profile.SCHEMA, "checkpoint", code)
    assert FORGED not in line and str(tmp_path) not in line
    assert profile.active() is None
