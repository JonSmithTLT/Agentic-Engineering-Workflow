"""The harness-neutral checks: AEW's own suites, run against the binary under test.

- ``conformance``: the harness conformance scenarios' live lane, with the binary given by the pack's variable. The
  lane's model is the scripted model on loopback (its keyless mode), since this tool never passes a live model (the
  private environment drops every ``AEW_`` variable). A run with a skip is reported as ``skipped`` with the counts,
  never as a pass, unless every skip's reason is one the pack names as the driver's own limit.
- ``containment.self_test``: AEW's containment self-test, through its integration tests. It is the host's result, not
  the binary's (``scope: host``): those tests drive the fake server, not the binary under test. Needs bubblewrap, so it
  runs on the VM only.

Both run agents whose bare ``aew`` is AEW's own interpreter's install, without ``PYTHONPATH`` (the product curates
an agent's environment). Where that install is another checkout (an editable install elsewhere, as on a developer's
machine), the suite would judge that checkout's AEW, not this tree's: the check is then reported ``skipped``, not
comparable, before the suite runs, and the record says which ``aew`` the agents would run. Run the tool from an
interpreter with this checkout installed (``pip install -e <checkout>``, as CI's jobs and the scheduled job do).

Both are slow and run with ``--slow``. Each runs pytest in a process tree of its own from the checkout this tool is in,
with a private environment plus the binary's variable, and reports pytest's own counts. A suite that overruns is
killed with everything it started, and its folders are removed either way.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from aew.harness import procs

from .core import BEHAVIOUR, FAIL, HOST, PASS, SKIPPED, VM, Check, Context, Outcome, private_env

ROOT = Path(__file__).resolve().parents[2]
CONTAINMENT = ["tests/integration/test_containment.py"]
SUITE_S = 1800
# pytest's `-rs` line: `SKIPPED [n] <path>:<line>: <reason>`, or with no line number. The path may hold a drive
# letter's colon (`C:\...` on Windows), so it ends at the first `:<digits>: `, else at the first `: `.
_SKIP_LINE = re.compile(r"^SKIPPED \[(\d+)\] (?:.+?:\d+|[^ ]+?): (.*)$")


def _test_name(line: str) -> str:
    """A pytest FAILED or ERROR line's test, as its file's name and its node: the line's path can be a host path (a
    temporary folder's), and the message after it is cut at the terminal's width."""
    node = re.match(r"^(?:FAILED|ERROR) (.+?::\S+)", line)
    if not node:
        return "(unnamed)"
    path, _, rest = node.group(1).partition("::")
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return f"{name}::{rest}"


def agents_aew(env: dict[str, str]) -> str:
    """Which AEW an agent's bare ``aew`` runs: ``this tree``, ``another checkout`` or ``none``. It is AEW's own
    interpreter's import of ``aew`` without ``PYTHONPATH``, as the curated agent environment has it (no host path is
    returned: records are shared)."""
    plain = {k: v for k, v in env.items() if k.upper() != "PYTHONPATH"}
    found = subprocess.run([sys.executable, "-c", "import os, aew; print(os.path.realpath(aew.__file__))"],
                           env=plain, cwd=str(Path(tempfile.gettempdir())), capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    if not found:
        return "none"
    here = os.path.normcase(os.path.realpath(ROOT / "src"))
    return "this tree" if os.path.normcase(found).startswith(here + os.sep) else "another checkout"


def _pytest(ctx: Context, variable: str, paths: list[str], extra: list[str],
            allowed_skips: Mapping[str, int] | None = None, timeout_s: float = SUITE_S) -> Outcome:
    """Run one suite. ``allowed_skips``: each skip reason pattern that is the driver's own limit, with how many tests
    it skips; anything else skipped, a count that differs, or skip lines that do not add up to pytest's own total make
    the run ``skipped``, never a pass."""
    allowed = dict(allowed_skips or {})
    which = agents_aew(ctx.env)
    if which != "this tree":  # the suite would judge another AEW than the one under test
        return Outcome(SKIPPED, facts={}, notes=[
            f"not comparable: an agent's bare `aew` runs {which}, not this tree (AEW's interpreter imports aew from "
            "an install elsewhere); run the tool from an interpreter with this checkout installed (pip install -e)"])
    log = ctx.work / "pytest.log"
    ctx.work.mkdir(parents=True, exist_ok=True)
    # The suite's homes and temporary folders under a short base: its tests bind sockets there (under HOME and
    # basetemp), and a socket's path must fit AF_UNIX's 108 bytes, which a path under the run folder does not. Not
    # under /tmp on POSIX: the containment self-test masks the host's /tmp, so a HOME there is hidden from its runs.
    base = Path(tempfile.mkdtemp(prefix=".hq-", dir=None if sys.platform == "win32" else Path.home()))
    tree = procs.ProcessTree()
    try:
        env = {**private_env(base / "e", ctx.env), variable: str(ctx.binary)}
        env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + os.environ["PYTHONPATH"]
                                                 if os.environ.get("PYTHONPATH") else "")
        with log.open("wb") as fh:
            proc = tree.spawn([sys.executable, "-m", "pytest", *paths, *extra, "-p", "no:xdist", "-q", "-rfEs",
                               "-p", "no:cacheprovider", f"--basetemp={base / 't'}"], cwd=ROOT, env=env,
                              stdout=fh, stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                return Outcome(FAIL, notes=[f"the suite overran {timeout_s:g}s and was killed with what it started"])
    finally:
        tree.kill()  # the suite and anything it started that is still in its tree
        shutil.rmtree(base, ignore_errors=True)
    lines = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    tail = lines[-1:] or [""]
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|skipped|errors?)", tail[0])}
    # a failing test's id only: the rest of pytest's line is its message, cut at the terminal's width, which can hold
    # a host path (records are shared)
    failed = [_test_name(ln) for ln in lines if ln.startswith(("FAILED ", "ERROR "))]
    note = [f"pytest exit {code}: {tail[0]}", *(f"failed: {t}" for t in failed[:5]), "agents' aew: this tree"]
    if code != 0 or counts.get("failed") or counts.get("error") or counts.get("errors"):
        return Outcome(FAIL, notes=note)
    if not counts.get("passed"):
        return Outcome(SKIPPED, notes=[*note, "no test ran: see pytest.log"])
    reasons = [(int(m.group(1)), m.group(2)) for m in map(_SKIP_LINE.match, lines) if m]
    total = counts.get("skipped", 0)
    if sum(n for n, _ in reasons) != total:  # a skip whose line was not read is never taken as allowed
        return Outcome(SKIPPED, notes=[*note, f"the skip lines add up to {sum(n for n, _ in reasons)}, not pytest's "
                                              f"{total}: see pytest.log"])
    unexplained = [(n, why) for n, why in reasons if not any(re.search(p, why) for p in allowed)]
    if unexplained:  # a skipped test proves nothing about this binary
        return Outcome(SKIPPED, notes=[*note, *(f"{n} skipped: {why}" for n, why in unexplained[:3])])
    seen = {p: sum(n for n, why in reasons if re.search(p, why)) for p in allowed}
    off = {p: (allowed[p], n) for p, n in seen.items() if n != allowed[p]}
    if off:  # the driver's limit now skips more (or fewer) tests than the pack expects: look before passing it
        return Outcome(SKIPPED, notes=[*note, *(f"expected {want} skipped by {p!r}, saw {got}"
                                                for p, (want, got) in off.items())])
    return Outcome(PASS, notes=[*note, *(f"{n} skipped, the driver's own limit: {why}" for n, why in reasons)])


def neutral_checks(harness: str, variable: str, *, conformance: list[str],
                   allowed_skips: Mapping[str, int] | None = None) -> list[Check]:
    """``allowed_skips``: each skip reason pattern that is the driver's own limit (an action it cannot drive), with
    how many tests it skips, not a test that did not run for want of something."""
    return [
        Check("conformance", lambda c: _pytest(c, variable, conformance, ["--live"], allowed_skips), depth=BEHAVIOUR,
              slow=True, says=f"the harness conformance scenarios' live lane against this {harness} binary, keyless"),
        Check("containment.self_test", lambda c: _pytest(c, variable, CONTAINMENT, []), platform=VM,
              depth=BEHAVIOUR, slow=True, scope=HOST,
              says="AEW's containment self-test on this host (bubblewrap; it drives the fake server, not the binary)"),
    ]
