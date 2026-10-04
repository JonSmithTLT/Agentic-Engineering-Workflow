"""Resume (Lead reconstruction), next actions, checkpoints, existing-authority projects (KC §15.1, §19, §26)."""

from __future__ import annotations

import pytest
from aewflow import assign, create_planned_ticket, implement, sample_project
from conftest import Project, make_git_repo


def test_fresh_project_resume_is_honest_about_what_is_missing(repo):
    p = Project(repo)
    p.ok("init")
    r = p.ok("resume", "--json")
    assert r["order"][0] == "project_manifest" and r["order"][-1] == "next_actions"
    assert r["lead"]["status"] == "vacant"
    assert any("aew lead acquire" in a for a in r["next_actions"])
    assert any("classify authority candidates" in a for a in r["next_actions"])
    assert any("configure checks" in a for a in r["next_actions"])
    fresh = {k["name"]: k["freshness"] for k in r["derived_knowledge"]}
    assert fresh["project_overview"] == "AUTHORED" and fresh["codebase_map"] == "UNAVAILABLE"
    text = p.aew("resume").stdout
    assert "AEW resume" in text and "Next actions" in text


def test_checkpoint_records_note_and_next_action(tmp_path):
    p = sample_project(tmp_path)
    out = p.lead("checkpoint", "--next", "plan the subtract Ticket")
    assert (p.root / ".aew" / out["checkpoint"]).exists()
    r = p.ok("resume", "--json")
    assert r["lead_note"] == "plan the subtract Ticket"
    assert r["latest_handoff"]["path"] == out["checkpoint"]
    assert "Lead's next action: plan the subtract Ticket" in (p.root / ".aew/state/CURRENT.md").read_text()


def test_next_actions_surface_unignested_evidence(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    from aewflow import review

    ev = review(p, wid)
    actions = p.ok("resume", "--json")["next_actions"]
    assert f"{wid}: ingest review {ev} (`aew review ingest`)" in actions


@pytest.mark.acceptance("KC-existing-authority")
def test_existing_authority_project_is_referenced_not_duplicated(tmp_path):
    repo = make_git_repo(tmp_path / "mature", {
        "README.md": "# mature\n",
        "docs/contracts/api-v2.md": "# API contract v2\n",
        "docs/adr/0007-storage.md": "# ADR 7\n",
        "src/app.py": "print('app')\n",
    })
    p = Project(repo)
    cands = {c["path"]: c for c in p.ok("init")["authority_candidates"]}
    contracts = cands["docs/contracts/"]
    assert contracts["suggested_class"] == "contracts" and contracts["confidence"] == "high"
    p.token = p.ok("lead", "acquire", "--expect-rev", "0")["token"]
    p.lead("authority", "accept", cands["docs/contracts/"]["id"], "--class", "contracts")
    p.lead("authority", "accept", cands["docs/adr/"]["id"], "--class", "decisions")
    r = p.ok("resume", "--json")
    assert {a["path"] for a in r["accepted_authority"]} == {"docs/contracts/", "docs/adr/"}
    # Referenced, not copied into .aew.
    assert not list((repo / ".aew").rglob("api-v2.md")) and not list((repo / ".aew").rglob("0007-storage.md"))
