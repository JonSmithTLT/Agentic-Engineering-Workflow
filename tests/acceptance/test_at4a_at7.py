"""AT-4a (crash mid control transition through the CLI) and AT-7 (workspace copies never authority)."""

from __future__ import annotations

from pathlib import Path

import pytest

from aewflow import SUBTRACT_PATCH, assign, create_planned_ticket, implement, sample_project


@pytest.mark.acceptance("AT-4a")
@pytest.mark.parametrize(("point", "committed"), [("txn.before_replace", False), ("txn.after_replace", True),
                                                   ("txn.after_apply", True)])
def test_crash_during_cli_transition(tmp_path, point, committed):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    p.lead("work", "assign", wid)
    rev = p.rev()
    res = p.aew("work", "transition", wid, "--to", "RUNNING", "--token", p.token, "--expect-rev", str(rev),
                env={"AEW_FAULT": point})
    assert res.returncode == 86
    control = p.ok("work", "show", wid)
    assert control["control"]["state"] == ("RUNNING" if committed else "ASSIGNED")
    assert control["revision"] == rev + (1 if committed else 0)
    assert (p.root / f".aew/state/log/{control['revision']:06d}.yaml").exists()
    assert "revision " + str(control["revision"]) in (p.root / ".aew/state/CURRENT.md").read_text()
    assert p.ok("status", "--json")["contradictions"] == []


@pytest.mark.acceptance("AT-4a")
def test_crash_during_assignment_leaves_no_hybrid(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    res = p.aew("work", "assign", wid, "--token", p.token, "--expect-rev", str(p.rev()),
                env={"AEW_FAULT": "txn.before_replace"})
    assert res.returncode == 86
    control = p.ok("work", "show", wid)["control"]
    assert control["state"] == "READY" and control["workspace"] is None
    # The orphaned worktree from the crashed attempt is cleared, never adopted.
    out = p.lead("work", "assign", wid)
    assert out["workspace"]["branch"] == f"aew/{wid}-1"
    assert p.ok("work", "show", wid)["control"]["state"] == "ASSIGNED"


@pytest.mark.acceptance("AT-7")
def test_ticket_cannot_write_aew_state_through_its_workspace(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl, {**SUBTRACT_PATCH, ".aew/state/control.yaml": "revision: 999\n"})
    res = p.aew("work", "transition", wid, "--to", "REVIEW_PENDING", "--token", p.token,
                "--expect-rev", str(p.rev()))
    assert res.error["code"] == "GATE_UNSATISFIED"
    assert any(v["path"] == ".aew/state/control.yaml" and v["rule"] == "protected_path"
               for v in res.error["details"]["violations"])
    # The authoritative control state is untouched by the workspace copy.
    assert "revision: 999" not in (p.root / ".aew/state/control.yaml").read_text()
    assert Path(impl.workspace, ".aew/state/control.yaml").exists()
