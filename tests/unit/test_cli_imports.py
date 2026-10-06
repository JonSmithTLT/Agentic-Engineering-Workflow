"""The CLI imports only what a command uses (CI redesign P2).

Every `aew` command builds the whole argument parser, and every test step and Lead tool call is an `aew` process: an
import the parser pulls in is paid by all of them. The property enforced here is architectural, not a time budget:
building the parser and running an ordinary engine command never imports the dashboard's server stack or the doctor,
which only their own commands use. (The time it buys is measured, not asserted: about 120 ms of a 0.9 s `aew status`.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEAVY = ("aew.dashboard.server", "aew.dashboard.service", "aew.dashboard.control", "aew.dashboard.projections",
         "aew.dashboard.reader", "aew.doctor")

PROBE = """
import json, sys
from aew.cli.main import build_parser
build_parser()
import aew.engine.api  # what an ordinary command imports to do its work
print(json.dumps(sorted(m for m in sys.modules if m.startswith("aew."))))
"""


def test_building_the_parser_and_the_engine_imports_no_dashboard_server_or_doctor():
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    out = subprocess.run([sys.executable, "-c", PROBE], capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, **kwargs)
    loaded = set(json.loads(out.stdout.strip().splitlines()[-1]))
    assert not loaded & set(HEAVY), sorted(loaded & set(HEAVY))
    assert "aew.cli.dashboard_commands" in loaded  # the dashboard commands are registered, just not their server
