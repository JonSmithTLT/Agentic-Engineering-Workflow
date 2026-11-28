"""A review of a named local ref as a non-mutating Ticket, through the real CLI (register E168; SYS-45; the designer's
decision of 2026-11-06, (d); ADR-0008 as amended): created naming a ref, pinned to its commit at dispatch, observed
read-only at that commit, reviewed by the branch reviewer, accepted, and printed as written."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from aewflow import Role, create_unit, integrate, plan_unit, sample_project, to_commit_ready
from conftest import git
from invariants import assert_control_invariants

from aew.knowledge import evidence as E

REVIEW = {"claim": "feature/x adds subtract with a test", "result": "pass", "producer": {"model": "scripted-reviewer"},
          "ref_review": {"summary": "adds subtract(a, b) to calc/core.py",
                         "findings": [{"id": "F1", "severity": "major", "summary": "no test for negatives",
                                       "location": "calc/core.py:3"}],
                         "requirement_trace": [{"requirement": "subtract exists", "status": "covered"}],
                         "checked": ["read the diff from the merge-base"], "not_checked": ["performance"]}}


def branch(p, name: str = "feature/x", text: str = "def subtract(a, b):\n    return a - b\n") -> str:
    """A branch off main with one commit, made in a worktree of its own so the operator's checkout stays on main."""
    where = p.root.parent / f"wt-{name.replace('/', '-')}"
    git("worktree", "add", "-q", "-b", name, str(where), "main", cwd=p.root)
    (where / "calc" / "sub.py").write_text(text, encoding="utf-8")
    git("add", "calc/sub.py", cwd=where)
    git("commit", "-q", "-m", f"work on {name}", cwd=where)
    return git("rev-parse", "HEAD", cwd=where)


def create_ref_review(p, tmp_path: Path, ref: str = "feature/x", *extra: str) -> str:
    wid = create_unit(p, "ticket", f"Review {ref}", cls=1,
                      extra=("--non-mutating", "--review-ref", ref, "--goal", "subtract exists", *extra))
    plan_unit(p, tmp_path, wid, "Review the branch against the requirement.\n")
    return wid


def dispatch(p, wid: str, *args: str) -> tuple[Role, dict]:
    out = p.lead("work", "dispatch", wid, *args)
    p.lead("work", "transition", wid, "--to", "RUNNING")
    return Role(p, out["invocation_token"], Path(out["observation"]["path"])), out


def every_ref_and_reflog(p) -> dict[str, str]:
    """For-each-ref, HEAD, the worktree list and every reflog's bytes of the test project's repository: what a
    non-mutating review never writes."""
    git_dir = p.root / ".git"
    logs = {str(f.relative_to(git_dir)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in (git_dir / "logs").rglob("*") if f.is_file()}
    return {"refs": git("for-each-ref", "--format=%(refname) %(objectname)", cwd=p.root),
            "head": (git_dir / "HEAD").read_text(encoding="utf-8"), **logs,
            "branch_worktrees": "\n".join(line for line in git("worktree", "list", "--porcelain",
                                                                 cwd=p.root).splitlines()
                                          if line.startswith("branch "))}


def test_a_ref_review_runs_from_create_to_done_and_its_body_prints_as_written(tmp_path):
    p = sample_project(tmp_path)
    tip = branch(p)
    wid = create_ref_review(p, tmp_path)
    control = p.ok("work", "show", wid)["control"]
    assert control["review_ref"] == "refs/heads/feature/x"
    role, out = dispatch(p, wid)
    execution = out["execution"]
    assert execution["expected_kind"] == E.REF_REVIEW and execution["card"]["id"] == E.REF_REVIEW_CARD
    assert execution["selected_by"] == "workflow-default"
    pin = execution["ref_pin"]
    assert pin["commit"] == tip and pin["merge_base"] == git("rev-parse", "main", cwd=p.root)
    assert out["observation"]["commit"] == tip and git("rev-parse", "HEAD", cwd=role.workspace) == tip
    pack = (p.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert "## The ref under review" in pack and "+def subtract(a, b):" in pack
    assert "aew submit --kind ref_review" in pack and "submit.discovery_record" not in pack
    body = "The branch adds subtract.\n\nIt lacks a negative test.\n"
    sealed = role.submit(E.REF_REVIEW, REVIEW, body)
    p.lead("evidence", "ingest", wid, "--evidence", sealed["evidence"])
    p.lead("work", "accept", wid)
    assert p.ok("work", "show", wid)["control"]["state"] == "DONE"
    printed = p.aew("record", "body", sealed["evidence"])
    assert printed.returncode == 0 and printed.stdout == body
    record = (p.root / ".aew" / "evidence" / wid / f"{sealed['evidence']}.md").read_text(encoding="utf-8")
    assert "verdict: findings" in record and f"commit: {tip}" in record
    assert_control_invariants(p)


def test_a_ref_review_never_moves_or_writes_any_ref(tmp_path):
    p = sample_project(tmp_path)
    branch(p)
    wid = create_ref_review(p, tmp_path)
    before = every_ref_and_reflog(p)
    status_before = git("status", "--porcelain=v2", cwd=p.root)
    role, _ = dispatch(p, wid)
    sealed = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")
    p.lead("evidence", "ingest", wid, "--evidence", sealed["evidence"])
    p.lead("work", "accept", wid)
    git("worktree", "prune", cwd=p.root)
    assert every_ref_and_reflog(p) == before
    assert git("status", "--porcelain=v2", cwd=p.root) == status_before
    assert_control_invariants(p)


def test_a_ref_review_whose_observation_changed_is_refused_at_submit_and_at_ingest(tmp_path):
    p = sample_project(tmp_path)
    branch(p)
    wid = create_ref_review(p, tmp_path)
    role, _ = dispatch(p, wid)
    (role.workspace / "calc" / "sub.py").write_text("tampered\n", encoding="utf-8")
    refused = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n", expect_ok=False)
    assert refused.error["code"] == "OBSERVATION_MUTATED"
    git("checkout", "--", "calc/sub.py", cwd=role.workspace)
    sealed = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")
    (role.workspace / "calc" / "sub.py").write_text("tampered after\n", encoding="utf-8")
    res = p.aew(*p.lead_args("evidence", "ingest", wid, "--evidence", sealed["evidence"]),
                env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode != 0 and res.error["code"] == "OBSERVATION_MUTATED"
    assert_control_invariants(p)


def test_a_reviewer_of_a_ref_review_observes_the_pinned_commit(tmp_path):
    p = sample_project(tmp_path)
    tip = branch(p)
    wid = create_ref_review(p, tmp_path)
    p.lead("work", "staff", wid, "--review", "code_reviewer")
    role, _ = dispatch(p, wid)
    sealed = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")
    p.lead("evidence", "ingest", wid, "--evidence", sealed["evidence"])
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    out = p.lead("invoke", "create", wid, "--role", "reviewer")
    assert out["observation"]["commit"] == tip
    pack = (p.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert "+def subtract(a, b):" in pack and "verdict: findings" in pack
    assert_control_invariants(p)


def test_a_ref_review_that_depends_on_work_integrated_after_its_branch_point_is_judged_at_the_authoritative_commit(
        tmp_path):
    """Review of #661, m4: the review's dependencies are judged where its dispatch judged them, the authoritative
    commit, never at the reviewed ref's commit, which forked before the dependency was integrated."""
    p = sample_project(tmp_path)
    tip = branch(p)  # forks from main before the dependency is integrated
    dep, _ = to_commit_ready(p, tmp_path)
    integrated = integrate(p, dep)["integrated_commit"]
    wid = create_ref_review(p, tmp_path, "feature/x", "--depends-on", f"{dep}:mutating")
    role, out = dispatch(p, wid)
    pin = out["execution"]["ref_pin"]
    assert pin["commit"] == tip and git("merge-base", "--is-ancestor", integrated, pin["authoritative_commit"],
                                        cwd=p.root) == ""
    assert subprocess.run(["git", "merge-base", "--is-ancestor", integrated, tip], cwd=p.root).returncode == 1
    sealed = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")
    p.lead("evidence", "ingest", wid, "--evidence", sealed["evidence"])
    p.lead("work", "accept", wid)
    assert p.ok("work", "show", wid)["control"]["state"] == "DONE"
    assert_control_invariants(p)
