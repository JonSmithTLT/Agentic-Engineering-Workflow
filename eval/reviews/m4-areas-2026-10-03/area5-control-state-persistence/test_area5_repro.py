"""Area 5 (control-state persistence) reproductions against the frozen tree at a6cdc64.

Run from the review folder:
    venv/Scripts/python -m pytest repro/test_area5_repro.py -q -p no:cacheprovider --rootdir repro -s
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import _env  # noqa: F401
from conftest import Project, make_git_repo


def new_project(tmp_path: Path) -> Project:
    repo = make_git_repo(tmp_path / "repo", {"README.md": "# fixture\n", "docs/adr/0001-use-aew.md": "# ADR 1\n"})
    p = Project(repo)
    p.ok("init")
    p.token = p.ok("lead", "acquire", "--expect-rev", "0", "--session-label", "lead-a")["token"]
    return p


# R1 ------------------------------------------------------------------------------------------------------------------

def test_r1_an_edit_after_the_last_transition_applied_is_reported_as_a_transition_in_progress_and_blocks_adopt(tmp_path):
    """store.py:374-409: recovery re-applies the LAST transition's staged writes on every read. A write that was
    fully applied and then edited out of band (the operator's reviewed manual edit of project.yaml, which
    `manifest adopt` exists for) is indistinguishable from an interrupted apply, so every read fails closed with
    'modified outside AEW while a transition was being applied', including the documented remedy."""
    p = new_project(tmp_path)
    cands = p.ok("authority", "list")["candidates"]
    cand = next(c for c in cands if c["status"] == "proposed")
    p.lead("authority", "accept", cand["id"], "--class", "decisions")      # rewrites project.yaml (staged, mutable)
    assert p.ok("lead", "show")["revision"] >= 2                            # the rewrite is applied and readable
    manifest = p.root / ".aew" / "project.yaml"
    original = manifest.read_bytes()
    manifest.write_bytes(original + b"# reviewed manual edit\n")
    res = p.aew("lead", "show")
    assert res.returncode != 0, res.stdout
    assert res.error["code"] == "INTEGRITY_ERROR" and "being applied" in res.error["message"], res.stderr
    # the documented remedy for a manual manifest edit is refused by the same recovery check
    res = p.aew("manifest", "adopt", "--reason", "reviewed edit", "--token", p.token, "--expect-rev", "2")
    assert res.error["code"] == "INTEGRITY_ERROR" and "being applied" in res.error["message"], res.stderr
    # restore the file: the project is readable again (nothing was lost; the message was wrong)
    manifest.write_bytes(original)
    p.ok("lead", "show")
    # the same edit one commit later gives the intended answer: a pin mismatch that `manifest adopt` resolves
    p.lead("checkpoint", "--next", "x")
    manifest.write_bytes(manifest.read_bytes() + b"# reviewed manual edit\n")
    p.ok("lead", "show")
    res = p.aew("checkpoint", "--next", "y", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and "manifest adopt" in res.error["message"]
    p.lead("manifest", "adopt", "--reason", "reviewed edit")


# R3 ------------------------------------------------------------------------------------------------------------------

HOLD = r"""
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], isolation_level=None)
conn.execute("BEGIN IMMEDIATE")
time.sleep(float(sys.argv[2]))
"""


def test_r3_a_busy_derived_index_refuses_an_authoritative_commit(tmp_path):
    """archive_ops.py:632-650 + index.py:82-95: a Lead commit that needs a cold fact syncs the derived SQLite index
    inside the control transaction; a reader holding the index's write lock for longer than 30 s makes the commit
    fail with LOCK_TIMEOUT, although the index is derived and 'never authority'."""
    p = new_project(tmp_path)
    a = p.lead("work", "create", "ticket", "--title", "A", "--class", "1", "--goal", "g", "--contract", "c",
               "--scope", "docs/**")["id"]
    p.lead("work", "transition", a, "--to", "CANCELLED", "--reason", "done with it")                 # archived: A is now cold
    index = p.root / ".aew" / "local" / "history.sqlite"
    p.ok("history", "list")                                                 # builds the index
    assert index.exists()
    holder = subprocess.Popen([sys.executable, "-c", HOLD, str(index), "60"],
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        time.sleep(1.0)
        t0 = time.monotonic()
        res = p.aew("work", "create", "ticket", "--title", "B", "--class", "1", "--goal", "g", "--contract", "c",
                    "--scope", "docs/**", "--depends-on", a, "--token", p.token, "--expect-rev", str(p.rev()))
        waited = time.monotonic() - t0
    finally:
        holder.kill()
    assert res.returncode != 0, res.stdout
    print(f"work create with an edge to archived work: {res.error['code']} after {waited:.0f}s")
    assert res.error["code"] == "LOCK_TIMEOUT", res.stderr
    assert waited > 25
