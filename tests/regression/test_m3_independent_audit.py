"""Findings of the designer's independent M3 audit (`docs/implementation/m3-independent-audit-2026-09-29.md`).

Each regression was written, and seen failing, before its fix.
"""

from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest

from aew.policy import checks

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# A check whose process starts a child, then either hangs (and times out) or exits at once. The child waits, then
# writes a marker: it must never get the chance, because the check's evidence is sealed when the check returns.
PARENT = textwrap.dedent("""\
    import subprocess, sys, time
    child = "import time, pathlib, sys; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('child continued')"
    subprocess.Popen([sys.executable, "-c", child, sys.argv[1]], creationflags={flags},
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(float(sys.argv[2]))
""").format(flags=NO_WINDOW)


@pytest.mark.parametrize("parent_runs_s, timeout_s", [(30, 0.5), (0, 30)], ids=["parent-times-out", "parent-exits"])
def test_a_check_leaves_no_process_behind_when_it_returns(tmp_path, parent_runs_s, timeout_s):
    """I2. A check timing out (or its parent exiting) left its descendants running: `subprocess.run` ends only
    the direct child. The engine then took the after-snapshot and sealed the evidence while a descendant could
    still change the workspace. Every process a check starts must be gone when the check returns."""
    marker = tmp_path / "marker.txt"
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    cfg = {"command": ["{python}", str(script), str(marker), str(parent_runs_s)], "timeout_s": timeout_s}
    result = checks.run(cfg, tmp_path)
    if parent_runs_s:
        assert result["exit_code"] is None and "TIMEOUT" in result["log"]
    else:
        assert result["exit_code"] == 0
    time.sleep(1.5)  # well past the child's 0.8 s
    assert not marker.exists(), "a process the check started outlived the check"
