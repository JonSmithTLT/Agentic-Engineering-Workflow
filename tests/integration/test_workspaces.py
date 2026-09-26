"""Assignment, isolated workspaces, serial cap, and workspace authority resolution (WC §8.1; AT-7 part)."""

from __future__ import annotations

import pytest

from pathlib import Path

from conftest import git, run_aew


def planned_ticket(project, tmp_path, title="Add subtract()"):
    wid = project.lead("work", "create", "ticket", "--title", title, "--class", "1", "--scope", "calc/**")["id"]
    plan = tmp_path / f"{wid}.md"
    plan.write_text("Add the function and a test.\n")
    project.lead("plan", "propose", wid, "--file", str(plan))
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
