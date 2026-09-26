"""Controlled integration: validate, then publish by ref CAS (WC §8, §8.1, §13; D-op-2; AT-2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aewflow import (
    APPLY_PATCH,
    SUBTRACT_PATCH,
    create_planned_ticket,
    integrate,
    prepare_and_validate,
    sample_project,
    to_commit_ready,
    to_verified,
)
from conftest import git



@pytest.fixture
def calc(tmp_path):
    return sample_project(tmp_path)


def main_commit(p) -> str:
    return git("rev-parse", "refs/heads/main", cwd=p.root)


def state_of(p, wid) -> dict:
    return p.ok("work", "show", wid)["control"]


def test_full_integration_to_done(calc, tmp_path):
    wid, impl = to_commit_ready(calc, tmp_path)
    base = main_commit(calc)
    # An unrelated local edit in the authoritative worktree must survive publication.
    readme = calc.root / "README.md"
    readme.write_text(readme.read_text() + "local note\n", encoding="utf-8", newline="\n")
    out = integrate(calc, wid)
    merged = out["integrated_commit"]
    assert main_commit(calc) == merged and git("rev-parse", f"{merged}^1", cwd=calc.root) == base
    control = state_of(calc, wid)
    assert control["state"] == "DONE"
    assert control["integration"]["status"] == "integrated" and control["integration"]["cas"] == "published"
    # The authoritative worktree now holds the integrated change; the unrelated edit is intact.
    assert "def subtract" in (calc.root / "calc/core.py").read_text()
    assert readme.read_text().endswith("local note\n")
    assert git("diff", "--name-only", "HEAD", "--", "calc", "tests", cwd=calc.root) == ""
    completion = (calc.root / f".aew/work/{wid}/completion.md").read_text()
    assert merged in completion and "post_integration_evidence" in completion
    # Workspaces are removed; the Ticket branch is kept for provenance.
    assert not Path(control["workspace"]["path"]).exists()
    assert git("rev-parse", "--verify", f"aew/{wid}-1", cwd=calc.root)


def test_dirty_authoritative_path_blocks_publication(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    core = calc.root / "calc/core.py"
    core.write_text(core.read_text() + "# someone's local edit\n", encoding="utf-8", newline="\n")
    before = main_commit(calc)
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR"
    assert main_commit(calc) == before and core.read_text().endswith("# someone's local edit\n")


@pytest.mark.acceptance("AT-2")
def test_unintegrated_dependency_stays_blocked(calc, tmp_path):
    """AT-2: an upstream mutating Ticket passing its isolated checks does not unblock dependent work."""
    t1, _ = to_commit_ready(calc, tmp_path)
    t2 = create_planned_ticket(calc, tmp_path, title="Add apply() using subtract", extra=("--depends-on", t1))
    control = state_of(calc, t2)
    assert control["state"] == "BLOCKED"
    assert control["blocked_by"] == [{"kind": "dependency", "id": t1, "reason": "not_integrated"}]
    res = calc.aew("work", "assign", t2, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.error["code"] == "ILLEGAL_TRANSITION"

    # Published but crashed before DONE: the output is in the lineage, but required integration
    # validation has not been recorded as complete -> still blocked.
    prepare_and_validate(calc, t1)
    res = calc.aew("integrate", "publish", t1, "--token", calc.token, "--expect-rev", str(calc.rev()),
                   env={"AEW_FAULT": "integrate.before_done"})
    assert res.returncode == 86
    assert state_of(calc, t1)["state"] == "COMMIT_READY"
    calc.ok("work", "list")  # reads (with recovery) do not change control state
    assert state_of(calc, t2)["state"] == "BLOCKED"

    calc.lead("integrate", "reconcile", t1)
    m1 = state_of(calc, t1)["integration"]["commit"]
    assert state_of(calc, t1)["state"] == "DONE" and state_of(calc, t2)["state"] == "READY"
    wid2, _ = to_verified(calc, tmp_path, wid=t2, files=APPLY_PATCH)
    base = state_of(calc, t2)["workspace"]["base_commit"]
    assert git("merge-base", "--is-ancestor", m1, base, cwd=calc.root) == ""  # contains T1's output


@pytest.mark.acceptance("AT-2")
def test_dependency_requires_output_in_recorded_snapshot(calc, tmp_path):
    t1, _ = to_commit_ready(calc, tmp_path)
    before = main_commit(calc)
    integrate(calc, t1)
    t3 = create_planned_ticket(calc, tmp_path, title="Depends on T1", extra=("--depends-on", t1))
    assert state_of(calc, t3)["state"] == "READY"
    # Lineage rewritten below T1's integrated commit: DONE alone is not enough.
    after = main_commit(calc)
    git("update-ref", "refs/heads/main", before, cwd=calc.root)
    res = calc.aew("work", "assign", t3, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.error["code"] == "DEPENDENCY_UNSATISFIED"
    assert res.error["details"]["blockers"][0]["reason"] == "not_in_source_snapshot"
    git("update-ref", "refs/heads/main", after, cwd=calc.root)


def test_moved_ref_makes_candidate_stale(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    integ = prepare_and_validate(calc, wid)
    # A third party advances the authoritative branch after validation.
    (calc.root / "NOTES.txt").write_text("unrelated\n")
    git("add", "NOTES.txt", cwd=calc.root)
    git("commit", "-q", "-m", "third-party commit", cwd=calc.root)
    moved = main_commit(calc)
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.error["code"] == "STALE_CANDIDATE"
    assert main_commit(calc) == moved
    assert state_of(calc, wid)["integration"]["status"] == "stale_candidate"
    # Rebuild on the new base and revalidate.
    out = integrate(calc, wid)
    assert git("rev-parse", f"{out['integrated_commit']}^1", cwd=calc.root) == moved


@pytest.mark.acceptance("AT-4b")
def test_superseded_lead_cannot_publish(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    old = calc.token
    offer = calc.lead("lead", "handoff", "offer")["offer"]
    calc.token = calc.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(calc.rev()))["token"]
    before = main_commit(calc)
    res = calc.aew("integrate", "publish", wid, "--token", old, "--expect-rev", str(calc.rev()))
    assert res.error["code"] == "STALE_AUTHORITY"
    assert main_commit(calc) == before


@pytest.mark.parametrize("point", ["integrate.after_publishing_record", "integrate.after_cas",
                                   "integrate.mid_sync", "integrate.before_done"])
@pytest.mark.acceptance("AT-4a")
def test_crash_during_publish_reconciles(calc, tmp_path, point):
    wid, _ = to_commit_ready(calc, tmp_path)
    integ = prepare_and_validate(calc, wid)
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()),
                   env={"AEW_FAULT": point})
    assert res.returncode == 86
    expected_ref = integ["base"] if point == "integrate.after_publishing_record" else integ["candidate"]
    assert main_commit(calc) == expected_ref
    assert state_of(calc, wid)["integration"]["status"] == "publishing"
    out = calc.lead("integrate", "reconcile", wid)
    assert out["state"] == "DONE" and main_commit(calc) == integ["candidate"]
    assert git("diff", "--name-only", "HEAD", "--", "calc", "tests", cwd=calc.root) == ""
    assert git("diff", "--cached", "--name-only", "HEAD", "--", "calc", "tests", cwd=calc.root) == ""


def test_merge_conflict_is_recorded_not_forced(calc, tmp_path):
    wid, impl = to_verified(calc, tmp_path)
    calc.lead("work", "transition", wid, "--to", "COMMIT_READY")
    core = calc.root / "calc/core.py"
    core.write_text("def add(a, b):\n    return b + a\n", encoding="utf-8", newline="\n")
    git("commit", "-q", "-am", "conflicting change", cwd=calc.root)
    out = calc.aew("integrate", "prepare", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert out.returncode == 1 and out.json["ok"] is False
    control = state_of(calc, wid)
    assert control["state"] == "COMMIT_READY" and control["integration"]["status"] == "conflict"
    assert "calc/core.py" in control["integration"]["conflict_paths"]
    calc.lead("work", "transition", wid, "--to", "RUNNING", "--reason", "rebase onto conflicting main change")
