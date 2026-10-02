"""ADR-0011 P2d: `aew migrate` moves a project built by the M3 code (control state v1) to v2 in one transaction
(implementation plan R8, §3).

The projects are the perf tool's template (``tools/perf/control_plane.py``), which the M3 code builds in process, plus
cloned DONE and planned Tickets. Every test ends on the invariant oracle, which rebuilds the full state from the hot
state and the archive.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "helpers"))
sys.path.insert(0, str(ROOT / "tools" / "perf"))

import control_plane as CP  # noqa: E402
from conftest import run_aew  # noqa: E402
from invariants import assert_control_invariants, load_control, with_cold  # noqa: E402

from aew.engine.api import Engine  # noqa: E402
from aew.engine.faults import CRASH_EXIT_CODE  # noqa: E402
from aew.engine.store import serialize_control  # noqa: E402
from aew.history.store import History  # noqa: E402

V1, V2 = "aew/control/v1", "aew/control/v2"
# Every fault point a migration passes, in order: the pre-written bundles, the commit, the sealed segment and the tail
# applied after it, and what follows the commit.
FAULTS = ["history.after_prewrite", "txn.before_stage", "txn.after_stage", "txn.before_replace", "txn.after_replace",
          "txn.mid_apply", "history.mid_seal", "history.after_tail", "txn.after_apply", "txn.after_log",
          "txn.after_render"]
TERMINAL = {"DONE", "CANCELLED"}


def aew(t: CP.Template, *args: str, fault: str | None = None) -> Any:
    """The CLI, as the Lead runs it (the credential in the environment)."""
    env = {"AEW_LEAD_TOKEN": t.token, **({"AEW_FAULT": fault} if fault else {})}
    return run_aew("-C", str(t.root), *args, env=env)


def migrate(t: CP.Template, *, fault: str | None = None) -> Any:
    return aew(t, "migrate", "--expect-rev", str(read(t)["revision"]), fault=fault)


def read(t: CP.Template) -> dict[str, Any]:
    """The state after recovery (a read rolls an interrupted commit forward or discards it)."""
    return Engine.discover(t.root).store.read()


def full(t: CP.Template) -> dict[str, Any]:
    state, problems = with_cold(t.root, load_control(t.root))
    assert not problems, problems
    return state


def v1_project(tmp_path: Path, *, done: int = 4, planned: int = 2, hierarchy: bool = False) -> CP.Template:
    t = CP.make_template(tmp_path / "repo", hierarchy=hierarchy)
    CP.add_units(t.root, done=done, planned=planned)
    assert load_control(t.root)["schema"] == V1
    return t


def comparable(state: dict[str, Any]) -> dict[str, Any]:
    """What a migration must keep: every unit, invocation and credential, apart from the summaries v2 adds."""
    added = {"archived_children", "integration_frontier", "legacy_digest", "completion_sha256"}
    return {"work": {w: {k: v for k, v in u.items() if k not in added} for w, u in state["work"].items()},
            "invocations": state["invocations"], "tokens": state["tokens"]}


def test_a_v1_project_refuses_the_leads_mutations_until_it_is_migrated(tmp_path):
    t = v1_project(tmp_path)
    refused = aew(t, "work", "create", "ticket", "--title", "New work", "--class", "1",
                  "--expect-rev", str(t.rev()))
    assert refused.error["code"] == "MIGRATION_REQUIRED", refused.stderr
    assert refused.error["details"]["next_action"] == "aew migrate --expect-rev N"
    actions = aew(t, "resume", "--json").json["next_actions"]
    assert any("aew migrate --expect-rev N" in a for a in actions)
    # Reads work, and so do what the Lead needs to reach the migration: the seat, and ending work in flight.
    assert aew(t, "status", "--json").returncode == 0 and aew(t, "work", "tree").returncode == 0
    inv = next(i for i, v in read(t)["invocations"].items() if v["work_unit"] == "T-0003" and v["status"] == "active")
    cancelled = aew(t, "invoke", "cancel", inv, "--reason", "not needed", "--expect-rev", str(t.rev()))
    assert cancelled.returncode == 0, cancelled.stderr
    assert_control_invariants(t)


def test_migrating_archives_the_finished_work_and_keeps_everything_else(tmp_path):
    t = v1_project(tmp_path, done=6, planned=2)
    before = load_control(t.root)
    finished = sorted(w for w, u in before["work"].items() if u["state"] in TERMINAL)
    out = migrate(t)
    assert out.returncode == 0, out.stderr
    res = out.json
    assert res["migrated"] is True and res["archived"]["units"] == len(finished) == 7
    after = load_control(t.root)
    assert after["schema"] == V2 and not set(finished) & set(after["work"])
    assert after["cold"]["archived"] == {"cancelled": 0, "done": 7} and after["cold"]["root"]["count"] == 7
    assert [r["id"] for r in after["recent"]] == finished
    # Nothing is lost: the full state (hot plus archive) is the v1 state, apart from what v2 adds.
    assert comparable(full(t)) == comparable(before)
    # R8: the bundles were written before the commit and are referenced by hash; the redo record and
    # last_transition stay bounded.
    txn = after["last_transition"]["txn"]
    assert after["last_transition"]["op"] == "migrate"
    assert txn["prewritten"]["count"] == 7 and len(txn["writes"]) <= 3
    assert History(t.root / ".aew").verify(after["cold"]["root"]).ok
    full_audit = aew(t, "history", "audit", "--full")  # every record the bundles pin verifies too
    assert full_audit.returncode == 0 and full_audit.json["ok"] is True, full_audit.stderr
    assert after["cold"]["first_at"] and after["cold"]["unverified_since"] == after["cold"]["first_at"]
    # The Lead works again; a second migration does nothing.
    again = migrate(t)
    assert again.returncode == 0 and again.json["migrated"] is False and read(t)["revision"] == after["revision"]
    created = aew(t, "work", "create", "ticket", "--title", "New work", "--class", "1",
                  "--expect-rev", str(t.rev()))
    assert created.returncode == 0, created.stderr
    shown = aew(t, "work", "show", "T-0001").json["control"]  # lookups by id read the archive (R7)
    assert shown["state"] == "DONE" and shown["archived"] is True
    assert_control_invariants(t)


def crash_matrix(t: CP.Template, faults: list[str]) -> None:
    """Crash a migration of ``t`` at each fault point in turn, from the same v1 project: each leaves v1 (before the
    commit point; the retry rewrites the same bundles, R8) or the whole of v2 (after it), and the history root is the
    one a clean migration makes, every time."""
    before = comparable(load_control(t.root))
    snap = CP.Snapshot(t.root)
    clean = migrate(t)
    assert clean.returncode == 0, clean.stderr
    expected = load_control(t.root)["cold"]["root"]
    snap.restore()
    for fault in faults:
        crashed = migrate(t, fault=fault)
        assert crashed.returncode == CRASH_EXIT_CODE, (fault, crashed.stderr)
        state = read(t)  # recovery
        if state["schema"] == V1:
            assert FAULTS.index(fault) < FAULTS.index("txn.after_replace"), fault
            assert comparable(load_control(t.root)) == before
            retried = migrate(t)
            assert retried.returncode == 0, (fault, retried.stderr)
        else:
            assert FAULTS.index(fault) >= FAULTS.index("txn.after_replace"), fault
        after = load_control(t.root)
        assert after["schema"] == V2 and after["cold"]["root"] == expected, fault
        assert comparable(full(t)) == before, fault
        assert_control_invariants(t)
        snap.restore()


def test_a_crash_at_any_point_of_a_migration_leaves_v1_or_the_whole_of_v2(tmp_path):
    crash_matrix(v1_project(tmp_path), [f for f in FAULTS if f != "history.mid_seal"])


def test_a_crash_while_a_migration_seals_a_segment(tmp_path):
    t = v1_project(tmp_path, done=255, planned=0)  # 256 finished units: the commit seals exactly one segment
    crash_matrix(t, ["history.mid_seal"])
    assert migrate(t).returncode == 0
    root = load_control(t.root)["cold"]["root"]
    assert root["count"] == 256 and root["sealed_head"]["seq"] == 1


def test_a_migration_waits_for_live_runs(tmp_path):
    t = v1_project(tmp_path)
    control = t.root / ".aew/state/control.yaml"
    original = control.read_bytes()
    state = load_control(t.root)
    inv = next(i for i, v in state["invocations"].items() if v["work_unit"] == "T-0003" and v["status"] == "active")
    # A run launched moments ago, whose supervisor has written no record yet, may hold custody (as launch assumes).
    state["invocations"][inv]["runs"] = [{"run": f"R-{inv}-1", "token_id": state["invocations"][inv]["token_id"],
                                          "launched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]
    control.write_bytes(serialize_control(state))
    refused = migrate(t)
    assert refused.error["code"] == "ILLEGAL_TRANSITION" and refused.error["details"]["runs"] == [f"R-{inv}-1"]
    assert load_control(t.root)["schema"] == V1
    control.write_bytes(original)  # the run is gone
    assert migrate(t).returncode == 0
    assert_control_invariants(t)


# ---------------------------------------------------------------------------------------------- parents (R3)

def parent_review(t: CP.Template, wid: str) -> str:
    token = t.role(wid, "reviewer")
    return t.eng.submit(invocation_token=token, kind="review", text=CP.submission(
        {"claim": f"{wid} acceptance review", "producer": {"model": "perf"},
         "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}))["evidence"]


def parent_verification(t: CP.Template, wid: str) -> str:
    token = t.role(wid, "verifier")
    check = t.eng.check_run(invocation_token=token, check_id="unit")["evidence"]
    claims = [{"type": "goal_backwards", "claim": "the objective is met", "result": "pass", "checks": [check]},
              {"type": "contract", "claim": "contracts hold", "result": "pass", "checks": [check]}]
    return t.eng.submit(invocation_token=token, kind="verification", text=CP.submission(
        {"claim": f"{wid} acceptance", "producer": {"model": "perf"},
         "verification": {"scope": "parent", "claims": claims}}))["evidence"]


def gates(eng: Engine, wid: str) -> dict[str, str]:
    return {g: v["status"] for g, v in eng.gate_show(wid)["gates"].items()}


def test_parent_evidence_bound_before_the_migration_stays_current_until_the_child_set_changes(tmp_path):
    """R3: a parent's children digest changes form at v2, so each open parent keeps its v1 digest as an alias for the
    v2 digest it had at migration."""
    t = CP.Template(tmp_path / "repo")
    epic = t.parent_unit("epic", "Initiative", None)
    story = t.parent_unit("story", "Objective", epic)
    t.done(t.planned("Add subtract()", parent=story))
    t.lead("review_ingest", work_id=story, evidence_id=parent_review(t, story))
    t.lead("verify_ingest", work_id=story, evidence_id=parent_verification(t, story))
    before = gates(Engine.discover(t.root), story)
    assert before["review_r1"] == "CURRENT" and "STALE" not in before.values(), before
    assert migrate(t).returncode == 0
    legacy = load_control(t.root)["work"][story]["legacy_digest"]
    assert legacy["v1"] != legacy["v2_at_migration"]
    assert gates(Engine.discover(t.root), story) == before
    assert_control_invariants(t)
    # Closing it relies on that evidence; a new child would have made it stale instead.
    closed = aew(t, "work", "close", story, "--reason", "acceptance gates passed", "--expect-rev", str(t.rev()))
    assert closed.returncode == 0, closed.stderr
    assert story not in load_control(t.root)["work"]
    assert_control_invariants(t)


def test_a_new_child_after_the_migration_makes_the_parent_evidence_stale(tmp_path):
    t = CP.Template(tmp_path / "repo")
    story = t.parent_unit("story", "Objective", None)
    t.done(t.planned("Add subtract()", parent=story))
    t.lead("review_ingest", work_id=story, evidence_id=parent_review(t, story))
    assert migrate(t).returncode == 0
    added = aew(t, "work", "create", "ticket", "--title", "Follow-up", "--class", "1", "--parent", story,
                "--expect-rev", str(t.rev()))
    assert added.returncode == 0, added.stderr
    assert gates(Engine.discover(t.root), story)["review_r1"] == "STALE"
    assert_control_invariants(t)


@pytest.mark.parametrize("cls", ["LOCAL_IMPLEMENTATION_DEFECT"])
def test_a_classified_parent_failure_still_needs_a_new_child_after_the_migration(tmp_path, cls):
    """``_classification_unmet`` compares the child set with the one the failure was classified against: the v1
    digest recorded then still names the same children after the migration (it must not read as changed)."""
    t = CP.Template(tmp_path / "repo")
    story = t.parent_unit("story", "Objective", None)
    t.done(t.planned("Add subtract()", parent=story))
    token = t.role(story, "verifier")
    check = t.eng.check_run(invocation_token=token, check_id="unit")["evidence"]
    failed = t.eng.submit(invocation_token=token, kind="verification", text=CP.submission(
        {"claim": f"{story} acceptance", "producer": {"model": "perf"},
         "verification": {"scope": "parent", "claims": [
             {"type": "goal_backwards", "claim": "the objective is met", "result": "fail", "checks": [check]},
             {"type": "contract", "claim": "contracts hold", "result": "pass", "checks": [check]}]}}))["evidence"]
    t.lead("verify_ingest", work_id=story, evidence_id=failed)
    t.lead("verify_classify", work_id=story, classification=cls, reason="a child's change is wrong")
    assert migrate(t).returncode == 0
    t.lead("review_ingest", work_id=story, evidence_id=parent_review(t, story))
    t.lead("verify_ingest", work_id=story, evidence_id=parent_verification(t, story))
    refused = aew(t, "work", "close", story, "--reason", "gates passed", "--expect-rev", str(t.rev()))
    assert refused.returncode != 0 and "remediation child" in refused.error["message"], refused.stderr
    assert_control_invariants(t)
