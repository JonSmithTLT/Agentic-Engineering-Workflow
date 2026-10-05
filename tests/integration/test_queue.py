"""The integration queue and its lease (M4-D slice D3; M4 report §2.6 and §6; the M4-D plan §1.2; ADR-0004 amendment).

Each COMMIT_READY mutating Ticket has one live queue entry, served FIFO among runnable entries; at most one entry
holds the lease, kept by an engine custody invocation (``integration_attempt``: no harness, model, role or
credential); the post-integration verifier is its child; a dead custodian is reconciled, never timed out; the
ISO-004 checkout-sync lock is serialization only. The oracle (rules 34-38) runs after every step.
"""

from __future__ import annotations

import pytest
from aewflow import (
    create_planned_ticket,
    integrate,
    prepare_and_validate,
    sample_project,
    to_commit_ready,
    verify,
)
from conftest import git
from invariants import assert_control_invariants


def _concurrency(p, cap):
    from aew.util import dump_yaml, load_yaml

    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": cap}),
                     encoding="utf-8", newline="\n")


def _own_change(i):
    return {f"calc/op{i}.py": f"def op{i}():\n    return {i}\n",
            f"tests/test_op{i}.py": f"from calc.op{i} import op{i}\n\n\ndef test_op{i}():\n    assert op{i}() == {i}\n"}


def control(p) -> dict:
    from invariants import load_control

    return load_control(p.root)


def entry(p, wid):
    q = control(p).get("queue") or {}
    return next(((qid, e) for qid, e in q.get("entries", {}).items() if e["work"] == wid), (None, None))


def refused(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def tickets(p, tmp_path, n):
    """``n`` mutating Tickets of independent changes, all COMMIT_READY, in order."""
    _concurrency(p, n)
    wids = [create_planned_ticket(p, tmp_path, title=f"Add op{i}") for i in range(n)]
    for i, wid in enumerate(wids):
        to_commit_ready(p, tmp_path, wid=wid, files=_own_change(i))
    return wids


@pytest.fixture
def calc(tmp_path):
    return sample_project(tmp_path)


def test_the_lease_is_held_by_an_engine_custody_invocation_from_prepare_to_done(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    qid, e = entry(calc, wid)
    assert e["state"] == "QUEUED" and e["seq"] == 1 and e["attempts"] == []
    assert control(calc)["queue"]["lease"] is None
    assert_control_invariants(calc)

    out = calc.lead("integrate", "prepare", wid)
    assert out["queue"]["entry"] == qid and out["queue"]["state"] == "LEASED"
    assert out["dispatch"]["entrypoint"] == "integrate.prepare" and out["dispatch"]["allowed"]
    state = control(calc)
    custodian = state["queue"]["lease"]["custodian"]
    inv = state["invocations"][custodian]
    # Not a role invocation: executed by the engine, with no harness, model, role or credential.
    assert inv["kind"] == "integration_attempt" and inv["execution"] == "engine" and inv["queue_entry"] == qid
    assert not {"role", "token_id", "execution_profile", "runs"} & set(inv)
    assert inv["dispatch"]["entrypoint"] == "integrate.prepare"  # admitted by the grant's own decision
    assert custodian in state["work"][wid]["invocations"]
    assert state["queue"]["entries"][qid]["attempts"][-1]["candidate"] == state["work"][wid]["integration"]["candidate"]
    assert_control_invariants(calc)

    # The post-integration verifier is the custodian's child.
    calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, scope="integration"))
    verifiers = [i for i, v in control(calc)["invocations"].items() if v.get("scope") == "integration"]
    assert [control(calc)["invocations"][i]["custodian"] for i in verifiers] == [custodian]
    assert_control_invariants(calc)

    done = calc.lead("integrate", "publish", wid)
    assert done["state"] == "DONE"
    state = control(calc)
    assert state["queue"]["entries"] == {} and state["queue"]["lease"] is None
    unit = state["work"].get(wid)
    if unit is not None:  # still hot (archival keeps it while recent): the retired entry went with the unit
        [retired] = unit["queue_history"]
        assert retired["id"] == qid and retired["state"] == "RETIRED"
        assert retired["attempts"][-1]["result"] == "integrated"
        assert state["invocations"][custodian]["status"] == "completed"
    assert_control_invariants(calc)

    # The queue's changes are typed events in the transition log (ADR-0012 D2).
    log = calc.ok("history", "log", "--since", "0", "--kind", "queue.entry", "--kind", "queue.lease")
    kinds = [(ev["kind"], ev.get("from"), ev.get("to"), ev.get("entry")) for r in log["transitions"]
             for ev in r["events"]]
    assert ("queue.entry", None, "QUEUED", None) in kinds and ("queue.entry", "QUEUED", "LEASED", None) in kinds
    assert ("queue.entry", "LEASED", None, None) in kinds  # retired at DONE
    assert ("queue.lease", None, None, qid) in kinds and ("queue.lease", None, None, None) in kinds


def test_entries_are_served_fifo_and_one_lease_at_a_time(tmp_path):
    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    assert entry(p, first)[1]["seq"] < entry(p, second)[1]["seq"]
    err = refused(p, "integrate", "prepare", second)
    assert err["code"] == "QUEUE_ORDER" and err["details"]["ahead"] == first
    explained = p.ok("dispatch", "explain", second, "--entrypoint", "integrate.prepare")
    assert explained["reason_codes"] == ["QUEUE_ORDER"]  # the query equals the execution
    p.lead("integrate", "prepare", first)
    err = refused(p, "integrate", "prepare", second)
    assert err["code"] == "LEASE_HELD" and err["details"]["holder"] == first
    assert_control_invariants(p)
    p.lead("verify", "ingest", first, "--evidence", verify(p, first, scope="integration"))
    p.lead("integrate", "publish", first)
    integrate(p, second)  # the lease is free and second is the head now
    assert_control_invariants(p)


def test_a_conflict_releases_the_lease_and_never_blocks_the_entries_behind_it(tmp_path):
    """No head-of-line blocking: an AWAITING_DISPOSITION entry holds up no independent one."""
    p = sample_project(tmp_path)
    _concurrency(p, 3)
    a = create_planned_ticket(p, tmp_path, title="Rewrite add, one way")
    b = create_planned_ticket(p, tmp_path, title="Rewrite add, another way")
    c = create_planned_ticket(p, tmp_path, title="Add op9")
    to_commit_ready(p, tmp_path, wid=a, files={"calc/core.py": "def add(a, b):\n    return b + a\n"})
    to_commit_ready(p, tmp_path, wid=b, files={"calc/core.py": "def add(a, b):\n    return sum((a, b))\n"})
    to_commit_ready(p, tmp_path, wid=c, files=_own_change(9))
    integrate(p, a)
    res = p.aew("integrate", "prepare", b, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.json["integration"]["status"] == "conflict"
    qid, e = entry(p, b)
    assert e["state"] == "AWAITING_DISPOSITION" and e["disposition"]["reason"] == "conflict"
    assert e["disposition"]["detail"]["paths"] == ["calc/core.py"]
    assert control(p)["queue"]["lease"] is None
    assert_control_invariants(p)
    # c is behind b, but b awaits the Lead: c integrates. b cannot take the lease until it is disposed of.
    integrate(p, c)
    assert refused(p, "integrate", "prepare", b)["code"] == "ILLEGAL_TRANSITION"
    # The Lead's disposition here: a new implementation attempt. Leaving COMMIT_READY retires the entry.
    p.lead("work", "transition", b, "--to", "RUNNING", "--reason", "rebase onto the published add")
    assert entry(p, b) == (None, None)
    [retired] = control(p)["work"][b]["queue_history"]
    assert retired["id"] == qid and retired["state"] == "RETIRED"
    assert_control_invariants(p)


def test_an_earlier_entry_that_cannot_integrate_now_does_not_hold_up_a_later_one(tmp_path):
    """FIFO is among runnable entries: an earlier QUEUED entry whose integration is not legal now is skipped."""
    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    ws = control(p)["work"][first]["workspace"]["path"]
    from pathlib import Path

    (Path(ws) / "calc" / "op0.py").write_text("def op0():\n    return 'changed after COMMIT_READY'\n",
                                               encoding="utf-8", newline="\n")
    assert refused(p, "integrate", "prepare", first)["code"] == "GATE_UNSATISFIED"
    integrate(p, second)
    assert_control_invariants(p)


def test_a_stale_candidate_keeps_its_place_and_prepares_again(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    qid, before = entry(calc, wid)
    (calc.root / "NOTES.md").write_text("an unrelated commit\n", encoding="utf-8", newline="\n")
    git("add", "NOTES.md", cwd=calc.root)
    git("commit", "-q", "-m", "unrelated", cwd=calc.root)
    assert refused(calc, "integrate", "publish", wid)["code"] == "STALE_CANDIDATE"
    _, after = entry(calc, wid)
    assert after["state"] == "QUEUED" and after["seq"] == before["seq"]
    assert after["attempts"][-1]["result"] == "stale_candidate" and control(calc)["queue"]["lease"] is None
    assert_control_invariants(calc)
    integrate(calc, wid)
    assert_control_invariants(calc)


def test_a_dead_custodian_is_reconciled_never_released_by_time(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    custodian = control(calc)["queue"]["lease"]["custodian"]
    calc.lead("invoke", "cancel", custodian, "--reason", "the custodian is lost")
    lease = control(calc)["queue"]["lease"]
    assert lease["custodian"] == custodian and lease["reconcile"]["reason"] == f"custodian {custodian} is cancelled"
    assert_control_invariants(calc)
    err = refused(calc, "integrate", "publish", wid)
    assert err["code"] == "LEASE_RECONCILE_REQUIRED"
    err = refused(calc, "integrate", "prepare", wid)
    assert err["code"] == "ILLEGAL_TRANSITION"  # it still has its (now unpublishable) validated candidate
    out = calc.lead("integrate", "reconcile", wid)
    assert out["reconciled"] == "lease" and out["queue"]["state"] == "QUEUED"
    state = control(calc)
    assert state["queue"]["lease"] is None and state["work"][wid]["integration"] is None
    assert state["work"][wid]["integration_history"][-1]["status"] == "superseded"
    assert_control_invariants(calc)
    integrate(calc, wid)  # a new custodian, a new candidate, a new validation
    assert_control_invariants(calc)


def test_a_takeover_kills_the_custodian_and_the_new_lead_reconciles(calc, tmp_path):
    import aew.operator
    from aew.engine.api import Engine

    wid, _ = to_commit_ready(calc, tmp_path)
    calc.lead("integrate", "prepare", wid)
    custodian = control(calc)["queue"]["lease"]["custodian"]
    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        calc.token = Engine.discover(calc.root).lead_takeover(expect_rev=calc.rev(), reason="lost session",
                                                              session_label="operator")["token"]
    finally:
        aew.operator.authorize = original
    state = control(calc)
    assert state["invocations"][custodian]["status"] == "interrupted"
    assert state["queue"]["lease"]["reconcile"] is not None
    assert_control_invariants(calc)
    calc.lead("integrate", "reconcile", wid)
    integrate(calc, wid)
    assert_control_invariants(calc)


def test_leaving_commit_ready_retires_the_entry_and_releases_its_lease(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    calc.lead("integrate", "prepare", wid)
    custodian = control(calc)["queue"]["lease"]["custodian"]
    calc.lead("work", "transition", wid, "--to", "RUNNING", "--reason", "more work")
    state = control(calc)
    assert state["queue"]["entries"] == {} and state["queue"]["lease"] is None
    assert state["invocations"][custodian]["status"] == "cancelled"
    assert state["work"][wid]["queue_history"][-1]["attempts"][-1]["result"] == "retired (RUNNING)"
    assert_control_invariants(calc)


def test_post_integration_verification_runs_only_under_a_live_lease(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    calc.lead("integrate", "prepare", wid)
    res = calc.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    verifier = res["invocation"]
    custodian = control(calc)["queue"]["lease"]["custodian"]
    assert control(calc)["invocations"][verifier]["custodian"] == custodian
    calc.lead("invoke", "cancel", custodian, "--reason", "lost")
    # The dead custodian's child lost its authority with it, and no new verifier is dispatched under that lease.
    assert control(calc)["invocations"][verifier]["status"] == "cancelled"
    err = refused(calc, "invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    assert err["code"] == "LEASE_RECONCILE_REQUIRED"
    assert_control_invariants(calc)


def test_the_checkout_sync_lock_is_serialization_only(tmp_path):
    """AEW-INV-ISO-004 (M4-B6): holding the lock without an allowed decision changes nothing; a holder a crash left
    behind is a stale owner, reconciled at the next sync; the lock is never left held after a publish."""
    from aew.util import dump_yaml

    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    lock = p.root / ".aew/local/checkout-sync.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(dump_yaml({"custodian": "IA-9999", "entry": "Q-9999", "work": second}), encoding="utf-8")
    # The lock grants nothing: second is still behind first, and publishing still needs the lease.
    assert refused(p, "integrate", "prepare", second)["code"] == "QUEUE_ORDER"
    prepare_and_validate(p, first)
    assert refused(p, "integrate", "publish", second)["code"] == "ILLEGAL_TRANSITION"
    # The stale owner (no such active custodian) is reconciled by the next sync; the lock is released after it.
    p.lead("integrate", "publish", first)
    assert not lock.exists()
    assert_control_invariants(p)


def test_a_project_from_before_the_queue_queues_its_commit_ready_tickets_on_the_next_lead_commit(calc, tmp_path):
    """A COMMIT_READY Ticket of a project the pre-queue engine wrote (no ``queue`` key) is enqueued by the next Lead
    transaction, and integrates under a lease like any other."""
    from aew.engine.store import serialize_control

    wid, _ = to_commit_ready(calc, tmp_path)
    path = calc.root / ".aew/state/control.yaml"
    state = control(calc)
    state.pop("queue")
    state["counters"].pop("queue_entry", None)
    path.write_bytes(serialize_control(state))
    assert "queue" not in control(calc)
    assert_control_invariants(calc)  # the oracle accepts a project that has not queued anything yet
    out = calc.lead("integrate", "prepare", wid)
    assert out["queue"]["state"] == "LEASED" and out["queue"]["seq"] == 1
    assert_control_invariants(calc)


def test_a_candidate_changing_more_paths_than_one_publish_may_sync_is_refused_at_prepare(calc, tmp_path):
    """Register E34 (note 9): a publish holds the control lock while it syncs every changed path, so the number of
    paths is bounded (gates.yaml `max_publish_paths`), and a larger candidate is refused before anything is published:
    no lease is kept, and the entry waits for the Lead's disposition (committed, so the queue knows)."""
    _max_publish_paths(calc, 1)
    wid, _ = to_commit_ready(calc, tmp_path, files=_own_change(1))  # two paths
    err = refused(calc, "integrate", "prepare", wid)
    assert err["code"] == "GATE_UNSATISFIED" and err["details"]["changed"] == 2 and err["details"]["limit"] == 1
    assert err["details"]["queue"]["state"] == "AWAITING_DISPOSITION"
    _, e = entry(calc, wid)
    assert control(calc)["queue"]["lease"] is None and e["state"] == "AWAITING_DISPOSITION"
    assert e["disposition"]["reason"] == "refused" and e["disposition"]["detail"]["code"] == "GATE_UNSATISFIED"
    assert e["attempts"][-1]["result"] == "refused" and control(calc)["work"][wid]["integration"] is None
    assert_control_invariants(calc)


def _max_publish_paths(p, n):
    from aew.util import dump_yaml, load_yaml

    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "max_publish_paths": n}),
                     encoding="utf-8", newline="\n")


def test_a_candidate_refused_at_admission_never_holds_up_an_independent_entry(tmp_path):
    """Independent review of PR #65: a refusal found only after the merge (the publish path bound, protected paths,
    case-only renames) used to roll back and leave the entry QUEUED and still "runnable", so FIFO refused every later
    independent entry with QUEUE_ORDER. The refusal now commits the entry to AWAITING_DISPOSITION."""
    p = sample_project(tmp_path)
    _concurrency(p, 2)
    _max_publish_paths(p, 1)
    big = create_planned_ticket(p, tmp_path, title="Add op1 and its test")
    small = create_planned_ticket(p, tmp_path, title="Add op9")
    to_commit_ready(p, tmp_path, wid=big, files=_own_change(1))  # two paths
    to_commit_ready(p, tmp_path, wid=small, files={"calc/op9.py": "def op9():\n    return 9\n"})
    assert refused(p, "integrate", "prepare", big)["code"] == "GATE_UNSATISFIED"
    integrate(p, small)  # was QUEUE_ORDER: "big ... can integrate now"
    assert_control_invariants(p)


@pytest.mark.parametrize("status", ["prepared", "validated"])
def test_a_candidate_prepared_before_the_queue_existed_is_replaced_under_it(calc, tmp_path, status):
    """Independent review of PR #65: a project upgraded with an open candidate (prepared, or validated) that no lease
    holds gets a QUEUED entry, but prepare refused the open candidate and verification and publication need the lease,
    so the accepted work was stranded. Prepare now retires the unleased candidate and builds a new one under a lease:
    fresh checks and custody, never adoption."""
    from aew.engine.store import serialize_control

    wid, _ = to_commit_ready(calc, tmp_path)
    if status == "prepared":
        calc.lead("integrate", "prepare", wid)
    else:
        prepare_and_validate(calc, wid)
    # What the pre-queue engine wrote: the same candidate, with no queue, no lease and no custodian.
    state = control(calc)
    assert state["work"][wid]["integration"]["status"] == status
    custodian = state["queue"]["lease"]["custodian"]
    state.pop("queue")
    state["counters"].pop("queue_entry", None)
    state["invocations"][custodian]["status"] = "completed"
    for inv in state["invocations"].values():
        if inv.get("custodian") == custodian and inv["status"] == "active":
            inv["status"] = "completed"
    (calc.root / ".aew/state/control.yaml").write_bytes(serialize_control(state))
    assert refused(calc, "integrate", "publish", wid)["code"] == "LEASE_NOT_HELD"
    assert entry(calc, wid) == (None, None)  # the refusal committed nothing; the next Lead commit enqueues it
    out = calc.lead("integrate", "prepare", wid)
    assert out["queue"]["state"] == "LEASED" and out["integration"]["status"] == "prepared"
    retired = control(calc)["work"][wid]["integration_history"][-1]
    assert "before the integration queue" in retired["retired"]["reason"]
    assert_control_invariants(calc)
    calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, scope="integration"))
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"
    assert_control_invariants(calc)
