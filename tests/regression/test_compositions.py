"""Composition tests for the 2026-09-26 review: operations that are individually tested,
exercised in the sequences where the review found unguarded interactions.

Every scenario ends with the cross-operation invariant oracle.
"""

from __future__ import annotations

from aewflow import integrate, prepare_and_validate, sample_project, to_commit_ready
from conftest import git
from invariants import assert_control_invariants


def unit(p, wid):
    return p.ok("work", "show", wid)["control"]


def main_commit(p):
    return git("rev-parse", "refs/heads/main", cwd=p.root)


def crash_after_publishing_record(p, wid):
    res = p.aew("integrate", "publish", wid, "--token", p.token, "--expect-rev", str(p.rev()),
                env={"AEW_FAULT": "integrate.after_publishing_record"})
    assert res.returncode == 86
    assert unit(p, wid)["integration"]["status"] == "publishing"


def test_invariants_hold_on_the_normal_serial_lifecycle(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    assert_control_invariants(p)
    integrate(p, wid)
    assert_control_invariants(p)


def test_interleaved_writer_makes_finalization_stale_before_any_git_side_effect(tmp_path):
    """M1: a revision committed between the publishing record and finalization is detected under
    the lock before the CAS; the ref and the authoritative worktree are untouched until a
    reconcile with the current revision."""
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integ = prepare_and_validate(p, wid)
    crash_after_publishing_record(p, wid)
    stale_rev = p.rev()
    p.lead("checkpoint", "--next", "another Lead write lands in between")
    before = (p.root / "calc/core.py").read_bytes()
    res = p.aew("integrate", "reconcile", wid, "--token", p.token, "--expect-rev", str(stale_rev))
    assert res.error["code"] == "STALE_REVISION"
    assert main_commit(p) == integ["base"]
    assert (p.root / "calc/core.py").read_bytes() == before
    out = p.lead("integrate", "reconcile", wid)
    assert out["state"] == "DONE" and main_commit(p) == integ["candidate"]
    assert_control_invariants(p)
