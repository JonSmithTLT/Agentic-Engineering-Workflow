"""Assignment, isolated workspaces, serial cap, and workspace authority resolution (WC §8.1; AT-7 part)."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import git, run_aew


def planned_ticket(project, tmp_path, title="Add subtract()"):
    wid = project.lead("work", "create", "ticket", "--title", title, "--class", "1", "--scope", "calc/**")["id"]
    plan = tmp_path / f"{wid}.md"
    plan.write_text("Add the function and a test.\n")
    project.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan))
    project.lead("plan", "accept", wid, "--revision", "1")
    return wid


def test_assign_allocates_attributable_workspace(project, tmp_path):
    wid = planned_ticket(project, tmp_path)
    head = git("rev-parse", "main", cwd=project.root)
    out = project.lead("work", "assign", wid)
    ws = out["workspace"]
    path = Path(ws["path"])
    assert path.is_dir() and ws["branch"] == f"aew/{wid}-1" and ws["base_commit"] == head
    assert git("rev-parse", "HEAD", cwd=path) == head
    snap = ws["base_snapshot"]
    assert snap["base_revision"] == head and snap["relevant_inputs_fingerprint"].startswith("git-tree:")
    assert out["invocation_token"].startswith("aew1.")
    control = project.ok("work", "show", wid)["control"]
    assert control["state"] == "ASSIGNED" and control["implementer_invocation"] == out["invocation"]
    # The workspace lives outside the authoritative worktree and does not dirty it.
    assert project.root not in path.parents
    assert git("status", "--porcelain", "--untracked-files=no", cwd=project.root) == ""


@pytest.mark.acceptance("AT-7")
def test_aew_inside_workspace_resolves_to_authoritative_project(project, tmp_path):
    wid = planned_ticket(project, tmp_path)
    ws = Path(project.lead("work", "assign", wid)["workspace"]["path"])
    res = run_aew("-C", str(ws), "status", "--json")
    assert res.returncode == 0, res.stderr
    assert res.json["work"][wid]["state"] == "ASSIGNED"
    # The marker lives in the worktree's private git dir, not in the working tree.
    assert not list(ws.glob("**/aew-workspace.yaml"))


def test_serial_mutating_cap(project, tmp_path):
    t1 = planned_ticket(project, tmp_path)
    t2 = planned_ticket(project, tmp_path, title="Independent change")
    project.lead("work", "assign", t1)
    res = project.aew("work", "assign", t2, "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 5 and res.error["code"] == "CONCURRENCY_LIMIT"
    assert res.error["details"]["holding"] == [t1]
    # Cancelling the holder releases the slot.
    project.lead("work", "transition", t1, "--to", "CANCELLED", "--reason", "superseded")
    project.lead("work", "assign", t2)


def test_start_requires_active_implementer(project, tmp_path):
    wid = planned_ticket(project, tmp_path)
    project.lead("work", "assign", wid)
    out = project.lead("work", "transition", wid, "--to", "RUNNING")
    assert out["to"] == "RUNNING"


def test_handoff_without_carry_interrupts_and_reconcile_is_bounded(project, tmp_path):
    wid = planned_ticket(project, tmp_path)
    project.lead("work", "assign", wid)
    offer = project.lead("lead", "handoff", "offer")["offer"]
    project.token = project.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev",
                               str(project.rev()))["token"]
    control = project.ok("work", "show", wid)["control"]
    assert control["state"] == "INTERRUPTED" and control["interrupted_from"] == "ASSIGNED"
    res = project.aew("work", "reconcile", wid, "--to", "RUNNING", "--reason", "looks fine",
                      "--token", project.token, "--expect-rev", str(project.rev()))
    assert res.returncode == 5 and res.error["code"] == "GATE_UNSATISFIED"
    out = project.lead("work", "reconcile", wid, "--to", "ASSIGNED", "--reason", "workspace inspected: untouched")
    assert out["inspection"]["exists"] is True and out["inspection"]["changed_since_assignment"] is False


def test_invocation_secret_never_written(project, tmp_path):
    wid = planned_ticket(project, tmp_path)
    token = project.lead("work", "assign", wid)["invocation_token"]
    secret = token.rsplit(".", 1)[1]
    for root in (project.root, project.root.parent):
        for f in root.rglob("*"):
            if f.is_file() and ".git" not in f.parts:
                assert secret not in f.read_bytes().decode("utf-8", "replace"), f


# ---------------------------------------------------------------- M4-C: mutating concurrency above 1


def _concurrency(p, cap):
    from aew.util import dump_yaml, load_yaml

    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": cap}),
                     encoding="utf-8", newline="\n")
    p.pin_policy()


def _own_change(i):
    """Ticket i's change: a module and its focused test of its own, so concurrent Tickets never overlap."""
    return {f"calc/op{i}.py": f"def op{i}():\n    return {i}\n",
            f"tests/test_op{i}.py": f"from calc.op{i} import op{i}\n\n\ndef test_op{i}():\n    assert op{i}() == {i}\n"}


@pytest.mark.parametrize("n", [2, 4])
def test_concurrent_mutating_tickets_work_in_their_own_workspaces_and_integrate_in_turn(tmp_path, n):
    """M4-C: with `mutating_concurrency: n`, n mutating Tickets hold live workspaces at once, each in its own
    worktree; the next one is refused at the cap. They integrate one after another: each later candidate is built on
    the authoritative head its predecessors moved, and the oracle holds at every step."""
    from aewflow import assign, create_planned_ticket, implement, integrate, review, sample_project, verify
    from invariants import assert_control_invariants

    p = sample_project(tmp_path)
    _concurrency(p, n)
    tickets = [create_planned_ticket(p, tmp_path, title=f"Add op{i}") for i in range(n)]
    roles = [assign(p, wid) for wid in tickets]
    assert len({r.workspace for r in roles}) == n  # one worktree each
    extra = create_planned_ticket(p, tmp_path, title="One too many")
    res = p.aew("work", "assign", extra, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "CONCURRENCY_LIMIT" and sorted(res.error["details"]["holding"]) == sorted(tickets)
    assert res.error["details"]["cap"] == n
    assert_control_invariants(p)
    for i, (wid, role) in enumerate(zip(tickets, roles, strict=True)):
        implement(role, _own_change(i))
        p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        p.lead("review", "ingest", wid, "--evidence", review(p, wid))
        p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
        p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
        p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    assert_control_invariants(p)
    heads = []
    for wid in tickets:
        out = integrate(p, wid)
        heads.append(out["integrated_commit"])
        assert_control_invariants(p)
    for i, later in enumerate(heads[1:], start=1):  # each candidate is built on the head its predecessor moved
        assert git("merge-base", "--is-ancestor", heads[i - 1], later, cwd=p.root) == ""
    assert git("rev-parse", "main", cwd=p.root) == heads[-1]
    for i in range(n):
        assert (p.root / f"calc/op{i}.py").exists()
    p.lead("work", "assign", extra)  # the slots are free again


def test_concurrent_tickets_that_change_the_same_lines_conflict_at_integration_and_publish_nothing(tmp_path):
    """M4-C: two concurrent Tickets that rewrite the same file both reach COMMIT_READY. The first integrates; the
    second's candidate, built on the moved head, conflicts and is recorded as a conflict. Nothing of it is published
    and the authoritative checkout is untouched."""
    from aewflow import create_planned_ticket, integrate, sample_project, to_commit_ready
    from invariants import assert_control_invariants

    p = sample_project(tmp_path)
    _concurrency(p, 2)
    first = create_planned_ticket(p, tmp_path, title="Rewrite add, one way")
    second = create_planned_ticket(p, tmp_path, title="Rewrite add, another way")
    to_commit_ready(p, tmp_path, wid=first, files={"calc/core.py": "def add(a, b):\n    return b + a\n"})
    to_commit_ready(p, tmp_path, wid=second, files={"calc/core.py": "def add(a, b):\n    return sum((a, b))\n"})
    integrate(p, first)
    head = git("rev-parse", "main", cwd=p.root)
    res = p.aew("integrate", "prepare", second, "--token", p.token, "--expect-rev", str(p.rev()))
    out = res.json
    assert res.returncode == 1 and out["ok"] is False and out["integration"]["status"] == "conflict"
    assert out["integration"]["conflict_paths"] == ["calc/core.py"]
    assert git("rev-parse", "main", cwd=p.root) == head
    assert git("status", "--porcelain", "--untracked-files=no", cwd=p.root) == ""
    assert_control_invariants(p)


def test_a_workspace_path_too_long_for_git_is_named_as_such(tmp_path, monkeypatch):
    """M4-C (spike fact 4): git's failure on a long worktree path becomes a GitError that says what to change."""
    from aew.errors import GitError
    from aew.workspace import worktrees

    def too_big(*args, **kw):
        raise GitError("git worktree add failed (128)", stderr="fatal: '$GIT_DIR' too big")

    monkeypatch.setattr(worktrees.git, "git", too_big)
    with pytest.raises(GitError) as exc:
        worktrees._add(tmp_path, tmp_path / "deep" / "T-0001-1", "--detach", "x", "HEAD")
    assert "too long for git" in exc.value.message and "workspaces.root" in exc.value.message
    assert exc.value.details["length"] == len(str(tmp_path / "deep" / "T-0001-1"))

    def other(*args, **kw):
        raise GitError("git worktree add failed (128)", stderr="fatal: invalid reference: nope")

    monkeypatch.setattr(worktrees.git, "git", other)
    with pytest.raises(GitError, match="failed"):
        worktrees._add(tmp_path, tmp_path / "x", "--detach", "x", "nope")


def test_lowering_the_cap_drains_admitted_work_and_only_gates_new_admissions(tmp_path):
    """M4-C (operator, 2026-10-04): the cap is an admission rule. Lowered from 4 to 1 while four workspaces are live,
    the four stay legal and keep working; a new assignment is refused until occupancy is below the new cap, then
    admission resumes."""
    from aewflow import assign, create_planned_ticket, implement, sample_project
    from invariants import assert_control_invariants

    p = sample_project(tmp_path)
    _concurrency(p, 4)
    tickets = [create_planned_ticket(p, tmp_path, title=f"Add op{i}") for i in range(4)]
    roles = [assign(p, wid) for wid in tickets]
    _concurrency(p, 1)
    assert_control_invariants(p)  # nothing illegal happened: work admitted under cap 4 stays admitted
    implement(roles[0], _own_change(0))  # and it keeps working
    newcomer = create_planned_ticket(p, tmp_path, title="Arrives after the cap was lowered")
    for wid in tickets:  # drain: refused at 4, 3, 2 and 1 live workspaces (the new cap is 1)
        res = p.aew("work", "assign", newcomer, "--token", p.token, "--expect-rev", str(p.rev()))
        assert res.error["code"] == "CONCURRENCY_LIMIT" and res.error["details"]["cap"] == 1, res.stderr
        p.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "draining after the cap was lowered")
        assert_control_invariants(p)
    p.lead("work", "assign", newcomer)  # below the cap again: admission resumes
    assert_control_invariants(p)
