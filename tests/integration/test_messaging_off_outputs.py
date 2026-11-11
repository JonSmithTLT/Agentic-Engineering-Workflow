"""Consolidated seeded JSON/text/projection off pin, captured from eea24ef1 before worker/attention changes.

This seed has an active assignment and no harness run: its wait refusal is pinned, not a fabricated run result.
Real ended-run behavior is covered by run_progress_digest and lead_relayed_reads. Normalized volatile values and
the no-run limit are declared by messaging_off_snapshot; this is not an oracle for every possible project state.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import worker_surface
from test_coordination_store import world

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/fixtures/baseline/messaging-off-outputs.json"


@pytest.mark.parametrize("messaging", [None, "disabled"])
def test_never_enabled_seeded_outputs_match_the_pre_worker_json_text_and_projection_pin(tmp_path, messaging):
    w = world(tmp_path, messaging=messaging)
    before = worker_surface.snapshot(w.root / ".aew")
    output = subprocess.run([sys.executable, "-B", str(ROOT / "tests/helpers/messaging_off_snapshot.py"),
                             str(w.root), w.wid], capture_output=True, text=True, timeout=60,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert output.returncode == 0, output.stderr
    expected = json.loads(GOLDEN.read_bytes())["absent" if messaging is None else "disabled"]
    assert json.loads(output.stdout) == expected
    assert not worker_surface.changes(before, worker_surface.snapshot(w.root / ".aew"))
    assert not (w.root / ".aew/coordination").exists()
