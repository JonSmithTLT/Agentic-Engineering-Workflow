"""Two mutating workers at the default cap (register F10; ADR-0003's amendment of 2026-11-07; HEB-06.c).

The default `mutating_concurrency` is 2 and nothing here sets it: a project as `init` makes it runs two workers whose
scopes cannot meet at once, each in its own worktree, and they integrate one after the other through the queue's lease;
a pair whose scopes can meet is held by the launch conflict check (E151). The workers are the scripted fake harness,
so no model is called.
"""

from __future__ import annotations

import pytest
from aewflow import create_planned_ticket, integrate, review, sample_project, verify
from conftest import git
from fake_harness import HarnessLab
from invariants import assert_control_invariants

from aew.knowledge.manifest import DEFAULT_GATES
from aew.util import load_yaml

ONE = {"calc/one.py": "ONE = 1\n",
       "tests/test_one.py": "from calc.one import ONE\n\n\ndef test_one():\n    assert ONE == 1\n"}
TWO = {"calc/two.py": "TWO = 2\n",
       "tests/test_two.py": "from calc.two import TWO\n\n\ndef test_two():\n    assert TWO == 2\n"}


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def worker(files: dict[str, str], here: str, other: str) -> list[dict]:
    """A scripted implementer that announces itself, waits until the other worker has announced itself too (so the
    two are provably running at the same time), then writes its files, runs the unit check and reports."""
    return [{"do": "touch", "path": here},
            {"do": "wait_file", "path": other, "timeout": 120},
            {"do": "write", "files": files}, {"do": "check", "id": "unit"},
            {"do": "submit", "kind": "implementation_report", "meta": {
                "claim": "added the constant with a focused test", "result": "pass",
                "producer": {"model": "fake-model", "harness": "fake"},
                "implementation": {"files_changed": sorted(files), "checks_run": ["unit"], "deviations": [],
                                   "self_review": {"completed": True, "notes": "diff matches plan"}}}}]


def to_commit_ready(p, wid: str) -> None:
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")


def test_init_writes_the_default_cap_and_doctor_reports_what_admission_enforces(lab):
    """The cap a new project gets is `DEFAULT_GATES`'s (never restated), and doctor reports that cap."""
    gates = load_yaml((lab.root / ".aew/policy/gates.yaml").read_text(encoding="utf-8"))
    assert gates["mutating_concurrency"] == DEFAULT_GATES["mutating_concurrency"] == 2
    [check] = [c for c in lab.ok("doctor", "--json")["checks"] if c["check"] == "mutating-concurrency"]
    assert check["detail"].startswith("2: up to 2 mutating Ticket(s)"), check


def test_at_the_default_cap_a_disjoint_pair_runs_at_once_and_integrates_one_after_the_other(lab, tmp_path):
    p = lab.project
    first = create_planned_ticket(p, tmp_path, title="Add one", scope=tuple(ONE))
    second = create_planned_ticket(p, tmp_path, title="Add two", scope=tuple(TWO))
    sync = tmp_path / "sync"
    lab.script("R-INV-0001-1", worker(ONE, str(sync / "one-running"), str(sync / "two-running")))
    lab.script("R-INV-0002-1", worker(TWO, str(sync / "two-running"), str(sync / "one-running")))
    runs = []
    for wid in (first, second):
        runs.append(lab.lead("work", "assign", wid, "--launch")["launch"]["run"])
        p.lead("work", "transition", wid, "--to", "RUNNING")
    # Each run waits for the other's announcement before it writes, so both ending with evidence proves both ran at
    # once: at a cap of 1 the second assignment is refused and the first run waits out its timeout.
    for run in runs:
        assert lab.wait(run)["status"] == "ended_with_evidence", lab.record(run)
    # The planted control: the cap is 2, not unlimited, so a third mutating Ticket meets it.
    third = create_planned_ticket(p, tmp_path, title="Add three", scope=("calc/three.py",))
    res = p.aew("work", "assign", third, "--expect-rev", str(p.rev()), env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode == 5 and res.error["code"] == "CONCURRENCY_LIMIT", res.error
    assert "mutating concurrency is 2" in res.error["message"]
    assert res.error["details"]["holding"] == sorted([first, second])

    for wid in (first, second):
        to_commit_ready(p, wid)
    one = integrate(p, first)
    two = integrate(p, second)  # built on the head the first moved, through the same lease
    assert git("rev-parse", f"{two['integrated_commit']}~1", cwd=p.root) == one["integrated_commit"]
    tree = git("ls-tree", "-r", "--name-only", "main", cwd=p.root).splitlines()
    assert set(ONE) | set(TWO) <= set(tree)
    assert_control_invariants(p)


def test_at_the_default_cap_an_overlapping_pair_is_held_by_the_launch_conflict_check(lab, tmp_path):
    p = lab.project
    first = create_planned_ticket(p, tmp_path, title="Add one", scope=("calc/**", "tests/**"))
    second = create_planned_ticket(p, tmp_path, title="Add two", scope=tuple(TWO))
    p.lead("work", "assign", first)
    rev = p.rev()
    res = p.aew("work", "assign", second, "--expect-rev", str(rev), env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode == 5 and res.error["code"] == "DISPATCH_REFUSED", res.error
    assert "FILES_CONFLICT" in res.error["details"]["reason_codes"], res.error  # E151's hold, not the cap's
    assert p.rev() == rev and p.ok("work", "show", second)["control"]["state"] == "READY"
    assert_control_invariants(p)
