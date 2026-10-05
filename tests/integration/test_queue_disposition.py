"""What survives a head move, and the Lead's disposition of queue entries (M4-D slice D4; M4 report §2.6 and §2.7; the
M4-D plan §2; ADR-0004 amendment).

The first head move under a lease is answered by one automatic rebuild that keeps the lease, its custodian and the
entry's place; a second move, a conflict, changed legality or an inconclusive validation releases the lease to
AWAITING_DISPOSITION, where nothing holds up the entries behind it. The Lead defers, requeues and reorders entries:
scheduling, never eligibility. The oracle (rules 34-39) runs after every step.
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
from invariants import assert_control_invariants, load_control


def control(p) -> dict:
    return load_control(p.root)


def entry(p, wid):
    q = control(p).get("queue") or {}
    return next(((qid, e) for qid, e in q.get("entries", {}).items() if e["work"] == wid), (None, None))


def run(p, *args, **kw):
    return p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()), **kw)


def refused(p, *args):
    res = run(p, *args)
    assert res.returncode != 0, res.stdout
    return res.error


def outside_commit(p, name="NOTES.md", text="an unrelated commit\n"):
    """A commit on the authoritative branch that AEW did not make: the head moves."""
    path = p.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    git("add", name, cwd=p.root)
    git("commit", "-q", "-m", f"outside: {name}", cwd=p.root)
    return git("rev-parse", "HEAD", cwd=p.root)


def _concurrency(p, cap):
    from aew.util import dump_yaml, load_yaml

    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": cap}),
                     encoding="utf-8", newline="\n")


def _own_change(i):
    return {f"calc/op{i}.py": f"def op{i}():\n    return {i}\n",
            f"tests/test_op{i}.py": f"from calc.op{i} import op{i}\n\n\ndef test_op{i}():\n    assert op{i}() == {i}\n"}


def tickets(p, tmp_path, n):
    _concurrency(p, n)
    wids = [create_planned_ticket(p, tmp_path, title=f"Add op{i}") for i in range(n)]
    for i, wid in enumerate(wids):
        to_commit_ready(p, tmp_path, wid=wid, files=_own_change(i))
    return wids


def validate_and_publish(p, wid):
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, scope="integration"))
    out = p.lead("integrate", "publish", wid)
    assert out["state"] == "DONE", out
    return out


@pytest.fixture
def calc(tmp_path):
    return sample_project(tmp_path)


# ------------------------------------------------------------------------------------------ the one automatic rebuild

def test_the_first_head_move_rebuilds_once_under_the_same_lease_custodian_and_place(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    old = prepare_and_validate(calc, wid)
    qid, before = entry(calc, wid)
    lease = control(calc)["queue"]["lease"]
    head = outside_commit(calc)
    res = run(calc, "integrate", "publish", wid)
    assert res.json["ok"] is False and res.json["rebuilt"] is True, res.stdout
    integ = res.json["integration"]
    assert integ["status"] == "prepared" and integ["base"] == head and integ["candidate"] != old["candidate"]
    qid2, after = entry(calc, wid)
    assert qid2 == qid and after["state"] == "LEASED" and after["rebuilds_used"] == 1
    assert (after["seq"], after["commit_ready_seq"]) == (before["seq"], before["commit_ready_seq"])
    assert control(calc)["queue"]["lease"] == lease  # no release, no new custodian
    retired = control(calc)["work"][wid]["integration_history"][-1]
    assert retired["candidate"] == old["candidate"] and "rebuilt once" in retired["retired"]["reason"]
    assert_control_invariants(calc)
    # Ticket work product is reused; integration validation is not: it reruns on the rebuilt candidate.
    assert refused(calc, "integrate", "publish", wid)["code"] == "GATE_UNSATISFIED"
    validate_and_publish(calc, wid)
    assert_control_invariants(calc)


def test_the_rebuild_records_its_own_fresh_decision_and_the_custodian_keeps_the_grants(calc, tmp_path):
    """ADR-0004: the rebuild's fresh integrate.prepare decision is retained, on the attempt and on the rebuilt
    candidate, with its revision and its dependency and policy digests; the custodian's grant decision is unchanged
    (independent review of #77: Dispatch.finalize records only on what a transaction creates, and a rebuild creates
    neither an invocation nor a run)."""
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    custodian = control(calc)["queue"]["lease"]["custodian"]
    grant = control(calc)["invocations"][custodian]["dispatch"]
    head = outside_commit(calc)
    assert run(calc, "integrate", "publish", wid).json["rebuilt"] is True
    state = control(calc)  # read back from disk
    assert state["invocations"][custodian]["dispatch"] == grant
    _, after = entry(calc, wid)
    admission = after["attempts"][-1]["rebuild_admission"]
    assert admission == state["work"][wid]["integration"]["admission"]
    assert admission["entrypoint"] == "integrate.prepare" and admission["rebuild"] is True
    assert admission["revision"] > grant["revision"] and admission["decision"] != grant["decision"]
    assert admission["head"] == head and set(admission["dependency_digests"]["policy"]) == {"gates", "guardrails",
                                                                                            "checks"}
    assert_control_invariants(calc)
    validate_and_publish(calc, wid)
    assert_control_invariants(calc)


def test_a_second_head_move_waits_for_the_lead_and_requeue_returns_it_to_its_place(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    outside_commit(calc, "NOTES.md")
    assert run(calc, "integrate", "publish", wid).json["rebuilt"] is True
    _, before = entry(calc, wid)
    custodian = control(calc)["queue"]["lease"]["custodian"]
    outside_commit(calc, "MORE.md")
    err = refused(calc, "integrate", "publish", wid)
    assert err["code"] == "STALE_CANDIDATE" and err["details"]["why"] == "head_moved_again"
    _, e = entry(calc, wid)
    assert e["state"] == "AWAITING_DISPOSITION" and e["disposition"]["reason"] == "head_moved_again"
    assert control(calc)["queue"]["lease"] is None
    assert control(calc)["invocations"][custodian]["status"] == "completed"
    assert_control_invariants(calc)
    out = calc.lead("integrate", "requeue", wid, "--reason", "the outside commits are done")
    assert out["to"] == "QUEUED" and entry(calc, wid)[1]["seq"] == before["seq"]
    assert entry(calc, wid)[1]["disposition"] is None
    assert_control_invariants(calc)
    prepared = calc.lead("integrate", "prepare", wid)
    assert prepared["queue"]["custodian"] != custodian and entry(calc, wid)[1]["rebuilds_used"] == 0
    validate_and_publish(calc, wid)
    assert_control_invariants(calc)


def test_a_rebuild_that_conflicts_waits_for_the_lead_and_is_never_resolved(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    prepare_and_validate(calc, wid)
    outside_commit(calc, "calc/core.py", "def add(a, b):\n    return b + a\n")  # the Ticket changes this file too
    err = refused(calc, "integrate", "publish", wid)
    assert err["code"] == "STALE_CANDIDATE" and err["details"]["why"] == "conflict"
    _, e = entry(calc, wid)
    assert e["state"] == "AWAITING_DISPOSITION" and e["disposition"]["reason"] == "conflict"
    assert control(calc)["work"][wid]["integration"]["status"] == "conflict"
    assert control(calc)["queue"]["lease"] is None
    assert_control_invariants(calc)


def test_a_publish_interrupted_before_its_cas_is_rebuilt_by_reconcile_when_the_head_moved(calc, tmp_path):
    """The head moves between the publishing record and the CAS: nothing was published, so reconcile answers with the
    one automatic rebuild under the still-live lease."""
    wid, _ = to_commit_ready(calc, tmp_path)
    old = prepare_and_validate(calc, wid)
    res = run(calc, "integrate", "publish", wid, env={"AEW_FAULT": "integrate.after_publishing_record"})
    assert res.returncode == 86
    head = outside_commit(calc)
    out = run(calc, "integrate", "reconcile", wid)
    assert out.json["rebuilt"] is True and out.json["integration"]["base"] == head, out.stdout
    assert git("rev-parse", "HEAD", cwd=calc.root) == head  # never published
    assert git("branch", "--contains", old["candidate"], cwd=calc.root) == ""
    assert entry(calc, wid)[1]["rebuilds_used"] == 1
    assert_control_invariants(calc)
    validate_and_publish(calc, wid)
    assert_control_invariants(calc)


# ------------------------------------------------------------------------- inconclusive validation, no head-of-line

def test_an_inconclusive_integration_validation_releases_the_lease_for_the_next_entry(tmp_path):
    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    p.lead("integrate", "prepare", first)
    p.lead("verify", "ingest", first, "--evidence",
           verify(p, first, scope="integration", goal_result="inconclusive"))
    _, e = entry(p, first)
    assert e["state"] == "AWAITING_DISPOSITION" and e["disposition"]["reason"] == "validation_inconclusive"
    assert control(p)["queue"]["lease"] is None
    assert_control_invariants(p)
    integrate(p, second)  # nothing holds it up
    p.lead("integrate", "requeue", first, "--reason", "rerun the validation")
    integrate(p, first)
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------- the Lead's queue commands

def test_a_deferred_entry_holds_up_nobody_and_requeue_keeps_its_place(tmp_path):
    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    _, before = entry(p, first)
    out = p.lead("integrate", "defer", first, "--reason", "waiting for the release branch")
    assert (out["from"], out["to"]) == ("QUEUED", "DEFERRED")
    assert control(p)["work"][first]["state"] == "COMMIT_READY"  # scheduling, never eligibility
    assert_control_invariants(p)
    assert refused(p, "integrate", "prepare", first)["code"] == "ILLEGAL_TRANSITION"  # until requeued
    integrate(p, second)
    p.lead("integrate", "requeue", first, "--reason", "the release branch is cut")
    assert entry(p, first)[1]["seq"] == before["seq"]
    integrate(p, first)
    assert_control_invariants(p)


def test_deferring_a_leased_entry_gives_up_its_lease_and_retires_its_candidate(tmp_path):
    p = sample_project(tmp_path)
    first, second = tickets(p, tmp_path, 2)
    prepared = p.lead("integrate", "prepare", first)
    custodian = prepared["queue"]["custodian"]
    p.lead("integrate", "defer", first, "--reason", "let the next one through")
    state = control(p)
    assert state["queue"]["lease"] is None and state["invocations"][custodian]["status"] == "completed"
    assert state["work"][first]["integration"] is None
    assert "deferred by the Lead" in state["work"][first]["integration_history"][-1]["retired"]["reason"]
    assert_control_invariants(p)
    integrate(p, second)
    p.lead("integrate", "requeue", first, "--reason", "its turn again")
    integrate(p, first)
    assert_control_invariants(p)


def test_reorder_moves_an_entry_ahead_with_fresh_positions(tmp_path):
    p = sample_project(tmp_path)
    a, b, c = tickets(p, tmp_path, 3)
    out = p.lead("integrate", "reorder", c, "--first", "--reason", "it unblocks the others")
    assert out["order"] == [c, a, b]
    seqs = [entry(p, w)[1]["seq"] for w in (c, a, b)]
    assert seqs == sorted(seqs) and len(set(seqs)) == 3
    assert_control_invariants(p)
    assert refused(p, "integrate", "prepare", a)["code"] == "QUEUE_ORDER"
    integrate(p, c)
    p.lead("integrate", "reorder", b, "--before", a, "--reason", "smaller change first")
    assert refused(p, "integrate", "prepare", a)["code"] == "QUEUE_ORDER"
    integrate(p, b)
    integrate(p, a)
    assert_control_invariants(p)


def test_queue_commands_refuse_what_they_cannot_do(calc, tmp_path):
    wid, _ = to_commit_ready(calc, tmp_path)
    assert refused(calc, "integrate", "requeue", wid, "--reason", "x")["code"] == "ILLEGAL_TRANSITION"  # QUEUED
    calc.lead("integrate", "defer", wid, "--reason", "later")
    assert refused(calc, "integrate", "defer", wid, "--reason", "again")["code"] == "ILLEGAL_TRANSITION"
    assert refused(calc, "integrate", "reorder", wid, "--before", wid, "--reason", "x")["code"] == "ILLEGAL_TRANSITION"
    other = create_planned_ticket(calc, tmp_path, title="Not committed yet")
    assert refused(calc, "integrate", "defer", other, "--reason", "x")["code"] == "ILLEGAL_TRANSITION"
    assert calc.aew("integrate", "defer", wid, "--token", calc.token).returncode != 0  # --reason is required
    assert_control_invariants(calc)
