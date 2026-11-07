"""The harness-neutral checks: AEW's own suites, run against the binary under test.

- ``conformance``: the harness conformance scenarios' live lane, with the binary given by the pack's variable. The
  scenarios that need a real model (``model_step``) skip, since no live model is used here; the scripted ones run.
- ``containment``: the containment self-test's integration tests. Needs bubblewrap, so it runs on the VM only.

Both are slow and run with ``--slow``. Each runs pytest in a child process from the checkout this tool is in, with
the private environment plus the binary's variable, and reports pytest's own counts.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .core import BEHAVIOUR, FAIL, PASS, VM, Check, Context, Outcome

ROOT = Path(__file__).resolve().parents[2]
CONTAINMENT = ["tests/integration/test_containment.py"]
SUITE_S = 1800


def _pytest(ctx: Context, variable: str, paths: list[str], extra: list[str]) -> Outcome:
    env = {**ctx.env, variable: str(ctx.binary)}
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    log = ctx.work / "pytest.log"
    ctx.work.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as fh:
        code = subprocess.run([sys.executable, "-m", "pytest", *paths, *extra, "-p", "no:xdist", "-q",
                               "-p", "no:cacheprovider", f"--basetemp={ctx.work / 'tmp'}"], cwd=ROOT, env=env,
                              stdout=fh, stderr=subprocess.STDOUT, timeout=SUITE_S,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
    tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1:] or [""]
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|errors?)", tail[0])}
    ok = code == 0 and counts.get("passed", 0) > 0  # every test skipped is not a pass
    return Outcome(PASS if ok else FAIL, notes=[f"pytest exit {code}: {tail[0]}"])


def neutral_checks(harness: str, variable: str, *, conformance: list[str]) -> list[Check]:
    return [
        Check("conformance", lambda c: _pytest(c, variable, conformance, ["--live"]), depth=BEHAVIOUR, slow=True,
              says=f"the harness conformance scenarios against this {harness} binary (scripted steps; no model)"),
        Check("containment.self_test", lambda c: _pytest(c, variable, CONTAINMENT, []), platform=VM,
              depth=BEHAVIOUR, slow=True, says="the containment self-test (bubblewrap)"),
    ]
