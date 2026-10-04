"""ADR-0011 P2b: finished work leaves the hot state at the commit that finishes it (implementation plan R3-R7).

Every test ends on the invariant oracle, which rebuilds the full state from the hot state and the archive and checks
the archival rules (summaries, derivation, references, frontiers) besides every earlier rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from aewflow import (  # noqa: E402
    close_parent,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    integrate,
    plan_unit,
    sample_project,
    submit_record,
    to_commit_ready,
)
from conftest import git, run_aew  # noqa: E402
from invariants import assert_control_invariants, load_control  # noqa: E402

from aew.engine.base import as_v1  # noqa: E402
from aew.engine.faults import CRASH_EXIT_CODE  # noqa: E402
from aew.engine.store import serialize_control  # noqa: E402
from aew.util import parse_frontmatter, sha256_file  # noqa: E402


def hot(p) -> dict:
    return load_control(p.root)


def show(p, wid: str) -> dict:
    return p.ok("work", "show", wid)["control"]


def test_a_finished_ticket_leaves_the_hot_state_with_its_invocations_and_credentials(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    rec = complete_investigation(p, wid)
    state = hot(p)
    assert state["schema"] == "aew/control/v2" and wid not in state["work"]
    assert not any(inv["work_unit"] == wid for inv in state["invocations"].values())
    assert not any(t["scope"].get("work_unit") == wid for t in state["tokens"].values())
    assert state["cold"]["archived"] == {"cancelled": 0, "done": 1} and state["recent"][-1]["id"] == wid
    assert (p.root / ".aew/work" / wid / "archive.yaml").exists()
    unit = show(p, wid)  # lookups by id read the archive (R7)
    assert unit["state"] == "DONE" and unit["archived"] is True and unit["execution"]["record"]["id"] == rec
    assert p.ok("status", wid, "--json")["work_unit"]["state"] == "DONE"
    assert [i["id"] for i in p.ok("work", "list", "--state", "DONE")["items"]] == [wid]
    finished = p.ok("resume", "--json")["finished"]
    assert (finished["done"], [r["id"] for r in finished["recent"]]) == (1, [wid])
    assert "Finished work (archived): 1 done" in (p.root / ".aew/state/CURRENT.md").read_text(encoding="utf-8")
    refused = p.aew("work", "transition", wid, "--to", "RUNNING", "--token", p.token, "--expect-rev", str(p.rev()))
    assert refused.error["code"] == "ILLEGAL_TRANSITION"  # finished work does not change, archived or not
    assert_control_invariants(p)


def test_an_archived_credential_is_still_stale_authority(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, out = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    assert out["invocation"] not in hot(p)["invocations"]
    # Its observation worktree went with it, so the credential is presented from the project.
    refused = run_aew("-C", str(p.root), "whoami", env={"AEW_INVOCATION_TOKEN": role.token})
    assert refused.returncode != 0 and refused.error["code"] == "STALE_AUTHORITY"  # never "unknown credential"
    shown = p.ok("invoke", "show", out["invocation"])  # and the invocation is still shown (R7)
    assert shown["status"] == "completed"
    assert p.ok("context", "pack", out["invocation"])["matches_recorded"] is True  # its pack regenerates


def test_a_superseded_lead_credential_is_archived_and_still_stale(tmp_path):
    p = sample_project(tmp_path)
    old = p.token
    offer = p.lead("lead", "handoff", "offer")["offer"]
    accepted = p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))
    state = hot(p)
    assert [t["kind"] for t in state["tokens"].values()] == ["lead"]  # only the new Lead's credential stays hot
    assert state["tokens"][accepted["token"].split(".")[1]]["revoked_at"] is None
    res = p.aew("checkpoint", "--token", old, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "STALE_AUTHORITY" and "superseded" in res.error["message"]
    assert_control_invariants(p)


def test_a_parent_derives_and_closes_from_its_archived_children(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective")
    plan_unit(p, tmp_path, story)
    first = create_investigation(p, tmp_path, parent=story)
    complete_investigation(p, first)
    digest_one = p.ok("gate", "show", story)["snapshot"]["children_digest"]
    second = create_investigation(p, tmp_path, parent=story, title="Second survey")
    complete_investigation(p, second)
    summary = hot(p)["work"][story]["archived_children"]
    assert (summary["done"], summary["done_tickets_subtree"]) == (2, 2)
    assert show(p, story)["state"] == "ACCEPTANCE_PENDING"  # derived from the summary: no child is hot
    assert p.ok("gate", "show", story)["snapshot"]["children_digest"] != digest_one
    assert sorted(p.ok("work", "show", story)["children"]) == sorted([first, second])
    close_parent(p, story)
    assert story not in hot(p)["work"]
    unit = show(p, story)
    meta, _ = parse_frontmatter((p.root / ".aew" / unit["closeout"]["record"]).read_text(encoding="utf-8"))
    assert [c["id"] for c in meta["children"]] == sorted([first, second])  # read from their bundles
    assert p.ok("work", "tree", story)["lines"][0].startswith(f"Story {story} [DONE]")
    assert_control_invariants(p)


def test_an_edge_to_archived_work_keeps_its_facts_hot_while_needed(tmp_path):
    p = sample_project(tmp_path)
    survey = create_investigation(p, tmp_path)
    rec = complete_investigation(p, survey)
    consumer = create_investigation(p, tmp_path, title="Consumer", extra=("--depends-on", f"{survey}:evidence"))
    state = hot(p)
    ref = state["archived_refs"][survey]
    assert (ref["state"], ref["record"]["id"], ref["refs"]) == ("DONE", rec, 1)
    assert state["work"][consumer]["state"] == "READY"
    _, out = dispatch(p, consumer)
    assert [i["id"] for i in p.ok("invoke", "show", out["invocation"])["inputs"]] == [rec]  # pinned from the archive
    assert_control_invariants(p)
    p.lead("work", "transition", consumer, "--to", "CANCELLED", "--reason", "no longer needed")
    assert "archived_refs" not in hot(p) or survey not in hot(p)["archived_refs"]  # no hot edge names it any more
    assert_control_invariants(p)


def test_moving_an_archived_ticket_annotates_it_and_updates_both_parents(tmp_path):
    p = sample_project(tmp_path)
    done = create_investigation(p, tmp_path, title="Finished elsewhere")
    complete_investigation(p, done)
    bundle = p.root / ".aew/work" / done / "archive.yaml"
    sha = sha256_file(bundle)
    story = create_unit(p, "story", "Objective")
    plan_unit(p, tmp_path, story)
    create_investigation(p, tmp_path, parent=story)  # keeps the Story open
    p.lead("work", "move", done, "--parent", story, "--reason", "it belongs to the objective")
    unit = show(p, done)
    assert unit["parent"] == story and unit["parent_history"][-1]["to"] == story
    assert hot(p)["work"][story]["archived_children"]["done"] == 1
    assert (p.root / ".aew/work" / done / "annotations/0001.yaml").exists() and sha256_file(bundle) == sha
    assert done in p.ok("work", "show", story)["children"]
    assert_control_invariants(p)


def test_an_edge_to_an_archived_parent_reads_its_integration_frontier(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Deliver subtract")
    plan_unit(p, tmp_path, story)
    wid, _ = to_commit_ready(p, tmp_path, title="Add subtract()", extra=("--parent", story))
    integrated = integrate(p, wid)["integrated_commit"]
    assert hot(p)["work"][story]["integration_frontier"] == {integrated: wid}
    close_parent(p, story)
    downstream = create_planned_ticket(p, tmp_path, title="Use subtract", extra=("--depends-on", f"{story}:mutating"))
    state = hot(p)
    assert state["archived_refs"][story]["integration_frontier"] == {integrated: wid}
    assert state["work"][downstream]["state"] == "READY"  # every integrated commit below the Story is in the base
    assert_control_invariants(p)


def test_a_v1_project_changes_no_work_until_it_is_migrated(tmp_path):
    """P2b kept a v1 project working without archival; P2d refuses its Lead mutations until `aew migrate`, which
    arrives in the same PR (plan §6), and archives from then on."""
    p = sample_project(tmp_path)
    control = p.root / ".aew/state/control.yaml"
    state = load_control(p.root)
    control.write_bytes(serialize_control(as_v1(state)))
    refused = p.aew("work", "create", "ticket", "--title", "Investigate", "--class", "1", "--non-mutating",
                    "--token", p.token, "--expect-rev", str(p.rev()))
    assert refused.error["code"] == "MIGRATION_REQUIRED"
    assert p.lead("migrate")["migrated"] is True
    wid = create_investigation(p, tmp_path)
    complete_investigation(p, wid)
    state = hot(p)
    assert state["schema"] == "aew/control/v2" and wid not in state["work"]
    assert (p.root / ".aew/work" / wid / "archive.yaml").exists()
    assert_control_invariants(p)


def test_a_crash_while_archiving_rolls_forward_to_the_archived_state(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, _ = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    res = run_aew("-C", str(p.root), "work", "accept", wid, "--token", p.token, "--expect-rev", str(p.rev()),
                  env={"AEW_FAULT": "history.after_bundle"})
    assert res.returncode == CRASH_EXIT_CODE
    assert show(p, wid)["state"] == "DONE" and wid not in hot(p)["work"]  # recovery applied the whole transition
    assert_control_invariants(p)


@pytest.mark.parametrize("closed", ["story", "epic"])
def test_reads_of_archived_work_restore_its_archived_ancestors(tmp_path, closed):
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative")
    plan_unit(p, tmp_path, epic)
    story = create_unit(p, "story", "Objective", parent=epic)
    plan_unit(p, tmp_path, story)
    wid = create_investigation(p, tmp_path, parent=story)
    role, out = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    gates = p.ok("gate", "show", wid)["gates"]
    close_parent(p, story)
    if closed == "epic":
        close_parent(p, epic)
    state = hot(p)
    assert story not in state["work"] and (epic in state["work"]) == (closed == "story")
    # Each read restores the unit's archived ancestry (bounded by depth), never the whole history (R7).
    assert p.ok("context", "pack", out["invocation"])["matches_recorded"] is True
    assert p.ok("gate", "show", wid)["gates"] == gates
    assert p.ok("gate", "show", story)  # the archived Story's own gates read its archived Epic too
    assert p.ok("status", wid, "--json")["work_unit"]["parent"] == story
    assert_control_invariants(p)


def worktree_paths(p) -> set[str]:
    listed = git("worktree", "list", "--porcelain", cwd=p.root)
    return {Path(line[len("worktree "):]).resolve().as_posix() for line in listed.splitlines()
            if line.startswith("worktree ")}


def test_a_crash_while_archiving_keeps_the_observation_cleanup_until_it_is_done(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    _, out = dispatch(p, wid)
    obs = Path(out["observation"]["path"])
    assert obs.exists() and obs.resolve().as_posix() in worktree_paths(p)
    res = run_aew("-C", str(p.root), "work", "transition", wid, "--to", "CANCELLED", "--reason", "not needed",
                  "--token", p.token, "--expect-rev", str(p.rev()), env={"AEW_FAULT": "history.after_bundle"})
    assert res.returncode == CRASH_EXIT_CODE
    assert show(p, wid)["state"] == "CANCELLED"  # recovery applies the cancellation and its archival...
    state = hot(p)
    assert out["invocation"] not in state["invocations"]
    # ...but not the removal that was to follow the commit: that obligation is in the committed state.
    assert state["retired_observations"] == [{"invocation": out["invocation"], "path": out["observation"]["path"]}]
    assert obs.exists()
    assert any(out["invocation"] in c and "retired observation" in c
               for c in p.ok("status", "--json")["contradictions"])
    p.lead("checkpoint")  # any Lead commit retries it
    assert not obs.exists() and obs.resolve().as_posix() not in worktree_paths(p)
    p.lead("checkpoint")  # and the next one drops it from the list
    assert hot(p)["retired_observations"] == [] and p.ok("status", "--json")["contradictions"] == []
    assert_control_invariants(p)


def test_views_follow_moves_of_archived_work(tmp_path):
    p = sample_project(tmp_path)
    done = create_investigation(p, tmp_path, title="Finished elsewhere")
    complete_investigation(p, done)
    stories = []
    for title in ("First objective", "Second objective"):
        story = create_unit(p, "story", title)
        plan_unit(p, tmp_path, story)
        create_investigation(p, tmp_path, parent=story, title=f"{title} survey")  # keeps the Story open
        stories.append(story)

    def views() -> tuple[str | None, str | None, bool]:
        listed = {i["id"]: i["parent"] for i in p.ok("work", "list", "--state", "DONE")["items"]}
        recent = {r["id"]: r["parent"] for r in p.ok("resume", "--json")["finished"]["recent"]}
        roots = {n["id"] for n in p.ok("work", "tree")["tree"]}
        return listed[done], recent[done], done in roots

    assert views() == (None, None, True)
    for target in (*stories, "none", stories[1]):  # into a parent, to another, back to the top level, and again
        p.lead("work", "move", done, "--parent", target, "--reason", "regrouped")
        parent = None if target == "none" else target
        assert show(p, done)["parent"] == parent
        assert views() == (parent, parent, parent is None)  # the list, resume and the default tree agree
        assert_control_invariants(p)
