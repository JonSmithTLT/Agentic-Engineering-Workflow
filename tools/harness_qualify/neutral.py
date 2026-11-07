"""The harness-neutral checks: AEW's own suites, run against the binary under test.

- ``conformance``: the harness conformance scenarios' live lane, with the binary given by the pack's variable. That
  lane drives each scenario with a keyed live model (``AEW_LIVE_OPENCODE_MODEL``), which this tool never passes (the
  private environment drops every ``AEW_`` variable), so on 2.0.18 16 of its 17 tests skip. A run with any skip is
  reported as ``skipped`` with the counts, never as a pass. Follow-on: point the lane's model at the scripted model.
- ``containment.self_test``: AEW's containment self-test, through its integration tests. It is harness-neutral: those
  tests drive the fake server, not the binary under test. Needs bubblewrap, so it runs on the VM only.

Both are slow and run with ``--slow``. Each runs pytest in a child process from the checkout this tool is in, with
the private environment plus the binary's variable, and reports pytest's own counts.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .core import BEHAVIOUR, FAIL, PASS, SKIPPED, VM, Check, Context, Outcome

ROOT = Path(__file__).resolve().parents[2]
CONTAINMENT = ["tests/integration/test_containment.py"]
SUITE_S = 1800


def _pytest(ctx: Context, variable: str, paths: list[str], extra: list[str]) -> Outcome:
    env = {**ctx.env, variable: str(ctx.binary)}
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    log = ctx.work / "pytest.log"
    ctx.work.mkdir(parents=True, exist_ok=True)
    # A short base for the suite's own temporary folders: a socket's path must fit AF_UNIX's ~108 bytes, which a
    # path under the run folder does not.
    base = Path(tempfile.mkdtemp(prefix="hq-"))
    with log.open("wb") as fh:
        code = subprocess.run([sys.executable, "-m", "pytest", *paths, *extra, "-p", "no:xdist", "-q",
                               "-p", "no:cacheprovider", f"--basetemp={base / 't'}"], cwd=ROOT, env=env,
                              stdout=fh, stderr=subprocess.STDOUT, timeout=SUITE_S,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
    shutil.rmtree(base, ignore_errors=True)
    tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:] or [""]
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|errors?)", tail[0])}
    note = [f"pytest exit {code}: {tail[0]}"]
    if code != 0 or counts.get("failed") or counts.get("error") or counts.get("errors"):
        return Outcome(FAIL, notes=note)
    if counts.get("skipped") or not counts.get("passed"):  # a skipped test proves nothing about this binary
        return Outcome(SKIPPED, notes=[*note, "not every test ran: see the skip reasons in pytest.log"])
    return Outcome(PASS, notes=note)


def neutral_checks(harness: str, variable: str, *, conformance: list[str]) -> list[Check]:
    return [
        Check("conformance", lambda c: _pytest(c, variable, conformance, ["--live"]), depth=BEHAVIOUR, slow=True,
              says=f"the harness conformance scenarios' live lane against this {harness} binary"),
        Check("containment.self_test", lambda c: _pytest(c, variable, CONTAINMENT, []), platform=VM,
              depth=BEHAVIOUR, slow=True,
              says="AEW's containment self-test (bubblewrap; harness-neutral: it drives the fake server)"),
    ]
