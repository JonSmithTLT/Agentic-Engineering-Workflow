"""Regressions from the control-state persistence review (area 5, 2026-10-03): P1 to P3."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from conftest import Project, make_git_repo


def new_project(tmp_path: Path) -> Project:
    repo = make_git_repo(tmp_path / "repo", {"README.md": "# fixture\n", "docs/adr/0001-use-aew.md": "# ADR 1\n"})
    p = Project(repo)
    p.ok("init")
    p.token = p.ok("lead", "acquire", "--expect-rev", "0", "--session-label", "lead-a")["token"]
    return p


def test_a_manual_manifest_edit_right_after_a_transition_reaches_manifest_adopt(tmp_path):
    """P1: `authority accept` stages a rewrite of project.yaml. A reviewed manual edit made right after it is a pin
    mismatch that `manifest adopt` resolves, not "modified while a transition was being applied" on every read."""
    p = new_project(tmp_path)
    cand = next(c for c in p.ok("authority", "list")["candidates"] if c["status"] == "proposed")
    p.lead("authority", "accept", cand["id"], "--class", "decisions")  # the last transition staged project.yaml
    manifest = p.root / ".aew" / "project.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"# reviewed manual edit\n")
    p.ok("lead", "show")  # reads work
    res = p.aew("checkpoint", "--next", "y", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and "manifest adopt" in res.error["message"], res.stderr
    p.lead("manifest", "adopt", "--reason", "reviewed edit")
    assert manifest.read_bytes().endswith(b"# reviewed manual edit\n")
    p.lead("checkpoint", "--next", "z")


HOLD = r"""
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN IMMEDIATE")
open(sys.argv[2], "w").close()
time.sleep(float(sys.argv[3]))
"""


def test_a_busy_history_index_does_not_fail_an_authoritative_commit(tmp_path):
    """P3: a Lead commit that needs a cold fact (an edge to archived work) builds a private index from the history
    when another process holds the shared one, instead of failing with LOCK_TIMEOUT after 30 s."""
    p = new_project(tmp_path)
    a = p.lead("work", "create", "ticket", "--title", "A", "--class", "1", "--goal", "g", "--contract", "c",
               "--scope", "docs/**")["id"]
    p.lead("work", "transition", a, "--to", "CANCELLED", "--reason", "done with it")  # A is archived: a cold fact
    index = p.root / ".aew" / "local" / "history.sqlite"
    p.ok("history", "list")  # builds the shared index
    ready = tmp_path / "holding"
    holder = subprocess.Popen([sys.executable, "-c", HOLD, str(index), str(ready), "60"],
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + 30
        while not ready.exists():
            assert holder.poll() is None and time.monotonic() < deadline, "the index holder did not start"
            time.sleep(0.05)
        t0 = time.monotonic()
        b = p.lead("work", "create", "ticket", "--title", "B", "--class", "1", "--goal", "g", "--contract", "c",
                   "--scope", "docs/**", "--depends-on", a)["id"]
        waited = time.monotonic() - t0
    finally:
        holder.kill()
        holder.wait()
    assert waited < 20, waited  # a short wait, then the private index; never the 30 s timeout
    assert a in str(p.ok("work", "show", b))
