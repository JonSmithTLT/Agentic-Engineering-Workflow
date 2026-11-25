"""Consolidated seeded JSON/text/projection off pin.

Originally captured from merged main f1ff2dd3 and refreshed for E327's plan.reconfirm approval fields, and for maps
on by default (ADR-0015): the resume's codebase_map row names init's first map, CURRENT, where it said UNAVAILABLE;
and for E126, where `work_show` gained the Ticket's `effective_scope` (in its JSON and the typed text, nothing else);
and for E293, where the resume's codebase_map row gained `evidence_class` (in its JSON and the typed text); and for
E160, where the resume's role catalog gained the built-in `plan_assessor` card (its JSON and the typed text only).

This seed has an active assignment and no harness run: its wait refusal is pinned, not a fabricated run result.
Real ended-run behavior is covered by run_progress_digest and lead_relayed_reads. Normalized volatile values and
the no-run limit are declared by messaging_off_snapshot; this is not an oracle for every possible project state.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import autopsy
import proctree
import pytest
import snapshot_process
import worker_surface
from test_coordination_store import world

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/fixtures/baseline/messaging-off-outputs.json"


@pytest.mark.autopsy(children_only=True)
@pytest.mark.parametrize("messaging", [None, "disabled"])
def test_never_enabled_seeded_outputs_match_the_json_text_and_projection_pin(tmp_path, messaging):
    w = world(tmp_path, messaging=messaging)
    before = worker_surface.snapshot(w.root / ".aew")
    output = snapshot_process.run(ROOT / "tests/helpers/messaging_off_snapshot.py", [str(w.root), w.wid],
                                  autopsy.child_dir())
    assert output.returncode == 0, output.stderr
    expected = json.loads(GOLDEN.read_bytes())["absent" if messaging is None else "disabled"]
    assert json.loads(output.stdout) == expected
    assert not worker_surface.changes(before, worker_surface.snapshot(w.root / ".aew"))
    assert not (w.root / ".aew/coordination").exists()


def test_snapshot_timeouts_retain_the_helper_state_before_cleanup(tmp_path):
    hangs = tmp_path / "reports"
    base = tmp_path / "inner"
    plant = Path(__file__).with_name("messaging_snapshot_plant.py")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:xdist", "-p", "no:cacheprovider",
                             "--basetemp", str(base), "--hang-dir", str(hangs), str(plant)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=180,
                            env={k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 1 and "3 failed" in result.stdout, result.stdout + result.stderr
    for case in ("blocked", "exited", "stalled"):
        pid, start, holder, holder_start = map(int, (base / f"expected-{case}.txt").read_text().split())
        [directory] = [d for d in (hangs / "autopsy").iterdir() if f"_{case}_" in d.name]
        [state] = (directory / "harness").rglob("project.yaml.txt")
        assert state.read_text(encoding="utf-8") == "project: seeded"
        children = directory / "children"
        record = (children / "snapshot-timeout.txt").read_text(encoding="utf-8")
        assert f"helper pid={pid} " in record, record
        assert "stdout reader stream closed=False" in record, record
        assert "TimeoutExpired" in next(directory.glob("failure.*")).read_text(encoding="utf-8")
        assert (children / "probe.txt").read_text(encoding="utf-8") == "<redacted>"
        if case == "exited":
            assert "state=exited(0)" in record and f"descendant pid={holder} " in record, record
            if sys.platform == "win32":
                assert f"descendant pid={holder} current_ppid={pid}" in record, record
        else:
            assert "state=running" in record, record
            assert any("in block_in_snapshot" in stack.read_text(encoding="utf-8")
                       for stack in children.glob(f"stacks-{pid}.*.txt"))
        if case == "stalled":
            assert "descendant observation unavailable: TimeoutExpired" in record, record
        assert_gone((pid, start))
        assert_gone((holder, holder_start))


def assert_gone(original: tuple[int, int]) -> None:
    assert not proctree.same(original), f"snapshot process {original} survived cleanup"


def test_snapshot_cleanup_distinguishes_a_survivor_from_a_reused_pid():
    current = proctree.identity(os.getpid())
    assert current is not None
    pid, birth = current
    assert_gone((pid, birth - 1))  # the current process reused the earlier identity's PID
    with pytest.raises(AssertionError, match="survived cleanup"):
        assert_gone(current)
