"""Coordination threads across the end of their invocations (register F9, F9-A MS2; ADR-0017 D7, D9, D11, D12; F9-A
plan v4 D-16, D-31, D-35, D-38, D-39).

Every commit that ends an invocation seals its thread: the seal finalizer before archival, the explicit calls on the
direct paths (takeover, handoff acceptance, acquire), and the commit check that seals a missed ending by fallback on a
hot unit and refuses one in an archiving commit. The seal pins the thread's bytes, archival pins the seal, and the
worker messages no Lead was shown stay in the bounded hot list until a Lead-credentialed result carries them. The
adoption that enables messaging registers the project, so an engine before this slice refuses it. With messaging never
enabled, nothing here changes a byte.

Projects are built in process through the engine's own commands, as in ``test_coordination_store.py``.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from invariants import assert_control_invariants, coordination_violations, load_control, with_cold
from jsonschema import Draft202012Validator
from test_coordination_store import CP, OPERATOR, World, set_messaging, world

import aew.operator
from aew import util
from aew.coordination import layout as L
from aew.engine import faults
from aew.engine import stage_intents as SI
from aew.engine.store import ControlStore, Transition
from aew.errors import (
    IllegalTransition,
    IntegrityError,
    MessagingDisabled,
    NotAWorker,
    StaleAuthority,
    ThreadUnsealed,
)

ROOT = Path(__file__).resolve().parents[2]
PRE_MS2_SCHEMA = ROOT / "tests/fixtures/baseline/control.schema.22ab997.json"  # main before MS2 (#160 merged)
PRE_MS2_TRANSITION = ROOT / "tests/fixtures/baseline/transition.schema.22ab997.json"
ZERO = "0" * 64


@pytest.fixture
def w(tmp_path) -> World:
    return world(tmp_path)


# ---------------------------------------------------------------------------------------------- helpers


def talk(w: World, inv: str, token: str, *, replies: int = 1, body: str = "Check shutdown while recv() blocks.") -> \
        tuple[str, list[str]]:
    """A Lead message to ``inv`` and ``replies`` worker replies to it: the thread exists, and the replies are unseen."""
    lead = w.send(body, to=inv)["message"]["id"]
    out = [w.reply(lead, f"reply {n}", invocation_token=token)["message"]["id"] for n in range(1, replies + 1)]
    return lead, out


def state(w: World) -> dict[str, Any]:
    return w.e.store.read()


def pointer(w: World, wid: str, inv: str) -> dict[str, Any] | None:
    return w.e._coordination.seal_pointer(state(w), wid, inv)


def seal_of(w: World, wid: str, inv: str) -> dict[str, Any]:
    p = pointer(w, wid, inv)
    assert p is not None, f"{inv}'s thread is not sealed"
    raw = (w.root / ".aew" / p["seal"]).read_bytes()
    assert util.sha256_bytes(raw) == p["sha256"]
    return util.load_yaml(raw.decode("utf-8"))


def thread_bytes(w: World, wid: str, inv: str) -> bytes:
    return (w.root / ".aew" / L.thread_rel(wid, inv)).read_bytes()


def log_record(w: World, revision: int) -> dict[str, Any]:
    from aew.engine import outbox

    record = outbox.read_record(w.root / ".aew", revision)
    assert record is not None
    return record


def fallback_events(w: World) -> list[dict[str, Any]]:
    from aew.engine import outbox

    return [e for r in outbox.read_transitions(w.root / ".aew", -1, w.rev(), outbox=state(w).get("outbox"))
            for e in r["events"] if e["kind"] == L.SEAL_FALLBACK]


def implement(w: World, token: str | None = None, workspace: Path | None = None) -> None:
    for rel, text in CP.PATCH.items():
        ((workspace or w.workspace) / rel).write_text(text, encoding="utf-8", newline="\n")
    w.e.check_run(invocation_token=token or w.worker, check_id="unit")
    w.e.submit(invocation_token=token or w.worker, kind="implementation_report", text=CP.submission(CP.REPORT))


def verification(w: World, token: str, scope: str) -> str:
    checks = [w.e.check_run(invocation_token=token, check_id="unit")["evidence"]]
    claims = [{"type": "goal_backwards", "claim": "subtract works", "result": "pass", "checks": checks[:1]}]
    if scope == "ticket":
        checks.append(w.e.check_run(invocation_token=token, check_id="guardrails")["evidence"])
        claims.append({"type": "contract", "claim": "scope respected", "result": "pass", "checks": checks[1:]})
    return w.e.submit(invocation_token=token, kind="verification", text=CP.submission({
        "claim": "behavior verified", "producer": {"model": "test"},
        "verification": {"scope": scope, "claims": claims}}))["evidence"]


def non_mutating(w: World) -> tuple[str, str, str]:
    """A non-mutating Ticket dispatched to its executor: (unit, invocation, credential)."""
    wid = w.lead("work_create", kind="ticket", title="Investigate subtract()", risk_class=1, mutating=False,
                 scope_paths=["calc/**"], goal_backwards=["the cause is known"],
                 contract=["read only"])["id"]
    w.lead("plan_propose", no_assurance=True, work_id=wid, body="1. Read calc/core.py.\n")
    w.lead("plan_accept", work_id=wid, revision=1)
    out = w.lead("work_dispatch", work_id=wid)
    return wid, out["invocation"], out["invocation_token"]


def takeover(w: World, monkeypatch) -> None:
    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator-tty (test)"})
    w.token = w.e.lead_takeover(expect_rev=w.rev(), reason="the seat was lost", session_label="lead-b")["token"]


def to_commit_ready(w: World) -> None:
    implement(w)
    w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    reviewer = w.lead("invoke_create", work_id=w.wid, role="reviewer")["invocation_token"]
    review = w.e.submit(invocation_token=reviewer, kind="review", text=CP.submission(CP.REVIEW))["evidence"]
    w.lead("review_ingest", work_id=w.wid, evidence_id=review)
    w.lead("work_transition", work_id=w.wid, to="VERIFY_PENDING")
    verifier = w.lead("invoke_create", work_id=w.wid, role="verifier")["invocation_token"]
    w.lead("verify_ingest", work_id=w.wid, evidence_id=verification(w, verifier, "ticket"))
    w.lead("work_transition", work_id=w.wid, to="COMMIT_READY")


# ---------------------------------------------------------------------------------------------- every ending path
# Each case messages the invocation it ends (and its worker replies), then ends it through one path. It returns the
# (unit, invocation) pairs whose threads that commit must have sealed.

Ending = Callable[[World, Any], list[tuple[str, str]]]


def _cancel(w: World, mp: Any) -> list[tuple[str, str]]:
    talk(w, w.inv, w.worker)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop this attempt")
    return [(w.wid, w.inv)]


def _unit_cancel_archived(w: World, mp: Any) -> list[tuple[str, str]]:
    talk(w, w.inv, w.worker)
    w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    assert w.wid not in state(w)["work"]  # archived in the same commit
    return [(w.wid, w.inv)]


def _redispatch(w: World, mp: Any) -> list[tuple[str, str]]:
    wid, inv, token = non_mutating(w)
    talk(w, inv, token)
    w.lead("work_redispatch", work_id=wid, reason="a fresh attempt")
    return [(wid, inv)]


def _transition(w: World, mp: Any) -> list[tuple[str, str]]:
    talk(w, w.inv, w.worker)
    implement(w)
    w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")  # the implementer's report is ingested: it ends
    return [(w.wid, w.inv)]


def _retirement(w: World, mp: Any) -> list[tuple[str, str]]:
    talk(w, w.inv, w.worker)
    w.lead("work_transition", work_id=w.wid, to="REPLAN_REQUIRED", reason="the plan missed a case")
    w.lead("plan_propose", no_assurance=True, work_id=w.wid, body=CP.PLAN + "3. Cover negatives.\n",
           affected_paths=["calc/core.py"], reason="cover negatives")
    w.lead("plan_accept", work_id=w.wid, revision=2)  # the old attempt's workspace and invocations are retired
    return [(w.wid, w.inv)]


def _stage_step(w: World, mp: Any) -> list[tuple[str, str]]:
    wid, inv, token = non_mutating(w)
    talk(w, inv, token)
    si = w.e.stage_open(token=w.token, expect_rev=w.rev(), tool="probe", contract_digest=ZERO, arguments={},
                        judgment_inputs=["supersession_reason"], base_class="JUDGMENT_BEARING",
                        effective_class="JUDGMENT_BEARING", plan=[{"primitive": "work.redispatch"}], subject=wid,
                        ingress="test")["intent"]
    with SI.step(si, 1, final=True):
        w.lead("work_redispatch", work_id=wid, reason="a fresh attempt, as a stage step")
    return [(wid, inv)]


def _queue_retirement_ends_custodian_children(w: World, mp: Any) -> list[tuple[str, str]]:
    to_commit_ready(w)
    w.lead("integrate_prepare", work_id=w.wid)
    out = w.lead("invoke_create", work_id=w.wid, role="verifier", scope="integration")
    child = state(w)["invocations"][out["invocation"]]
    assert child.get("custodian"), "the integration verifier is the custodian's role-bearing child"
    talk(w, out["invocation"], out["invocation_token"])
    w.lead("work_transition", work_id=w.wid, to="RUNNING", reason="rework before integration")
    assert state(w)["invocations"][out["invocation"]]["status"] != "active"
    return [(w.wid, out["invocation"])]


def _takeover(w: World, mp: Any) -> list[tuple[str, str]]:
    talk(w, w.inv, w.worker)
    takeover(w, mp)
    return [(w.wid, w.inv)]


def _handoff_not_carried(w: World, mp: Any) -> list[tuple[str, str]]:
    talk(w, w.inv, w.worker)
    offer = w.lead("lead_handoff_offer", carry_invocations=[])["offer"]
    w.token = w.e.lead_handoff_accept(offer=offer, expect_rev=w.rev(), session_label="lead-b")["token"]
    return [(w.wid, w.inv)]


ENDINGS: dict[str, Ending] = {
    "cancel": _cancel, "unit_cancel_archived": _unit_cancel_archived, "redispatch": _redispatch,
    "transition": _transition, "retirement": _retirement, "stage_step": _stage_step,
    "queue_retirement_ends_custodian_children": _queue_retirement_ends_custodian_children, "takeover": _takeover,
    "handoff_not_carried": _handoff_not_carried,
}


@pytest.mark.parametrize("path", list(ENDINGS))
def test_every_invocation_ending_commit_seals_its_thread(tmp_path, monkeypatch, path):
    """D-16 (F1, N1): whichever path ends a messaged invocation seals its thread in that same commit: the seal record
    pins the thread's bytes, the unit (hot, or in its bundle once archived) points at it, the commit's refs name it, and
    no seal came from the commit check's fallback. The oracle (rules 51 to 57) holds after."""
    w = world(tmp_path, checks=path in ("transition", "queue_retirement_ends_custodian_children"))
    ended = ENDINGS[path](w, monkeypatch)
    for wid, inv in ended:
        seal = seal_of(w, wid, inv)
        raw = thread_bytes(w, wid, inv)
        assert seal["invocation"] == inv and seal["thread"] == {"path": L.thread_rel(wid, inv),
                                                                 "sha256": util.sha256_bytes(raw), "size": len(raw)}
        assert pointer(w, wid, inv)["seal"] in log_record(w, seal["closed_rev"])["refs"]
    assert fallback_events(w) == []
    assert_control_invariants(w)


def test_release_and_migrate_end_no_invocation(w):
    """G1: `lead release` refuses while any invocation is active, and `migrate` on a v2 project changes no invocation's
    status, so neither needs a seal case: the threads stay live and unsealed."""
    talk(w, w.inv, w.worker)
    with pytest.raises(IllegalTransition):
        w.lead("lead_release")
    before = {i: v["status"] for i, v in state(w)["invocations"].items()}
    w.e.migrate(token=w.token, expect_rev=w.rev())
    assert {i: v["status"] for i, v in state(w)["invocations"].items()} == before
    assert pointer(w, w.wid, w.inv) is None and "coordination" not in state(w)["work"][w.wid]
    assert_control_invariants(w)


def test_cancelling_a_unit_seals_and_bundles_its_threads_in_one_history_append(w):
    """N1: the seal runs before archival, so the pointer is in the unit's bundle; the commit appends to the history
    once (archival's own entry), and no annotation is written."""
    talk(w, w.inv, w.worker)
    count = state(w)["cold"]["root"]["count"]
    w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    after = state(w)
    assert after["cold"]["root"]["count"] == count + 1  # the unit's bundle, and nothing else
    bundle = w.e.archive.bundle(after, w.wid)
    assert [p["invocation"] for p in bundle["unit"]["coordination"]] == [w.inv]
    assert not list((w.root / ".aew/history").glob("annotations/**/*.yaml"))
    events = log_record(w, after["revision"])["events"]
    assert [e["kind"] for e in events].count("history.appended") == 1
    assert_control_invariants(w)


def test_a_missed_call_on_a_hot_unit_seals_by_fallback_and_records_the_event(w):
    """R3: a direct session that ends a messaged invocation and skips ``seal_ending`` still commits: the commit check
    seals the thread itself, puts the pointer and the unseen entries in the serialized state, and records a
    ``coordination.seal_fallback`` event naming the invocation and the operation."""
    _, replies = talk(w, w.inv, w.worker)
    with w.e.store.session() as s:
        inv = s.state["invocations"][w.inv]
        inv["status"] = "interrupted"
        s.state["tokens"][inv["token_id"]]["revoked_at"] = util.utc_now()
        s.state["tokens"][inv["token_id"]]["revoke_reason"] = "a path that forgot its seal"
        projected = dict(s.state)  # a projection, as end_lead_credentials and archival hand the commit
        projected["work"] = dict(s.state["work"])
        projected["work"][w.wid] = dict(s.state["work"][w.wid])
        rev = s.commit(Transition(op="test.forgot_seal", actor={"kind": "test"}), state=projected)
    committed = load_control(w.root)
    assert [p["invocation"] for p in committed["work"][w.wid]["coordination"]] == [w.inv]
    assert [e["message"] for e in committed["coordination_unseen"]["entries"]] == replies
    record = log_record(w, rev)
    assert {"kind": L.SEAL_FALLBACK, "invocation": w.inv, "op": "test.forgot_seal"} in record["events"]
    assert committed["work"][w.wid]["coordination"][0]["seal"] in record["refs"]
    full, _ = with_cold(w.root, committed)
    problems = coordination_violations(w.root, committed, full)
    assert any("fallback" in p for p in problems)  # C6 reports it, so CI's walk fails on it
    assert coordination_violations(w.root, committed, full, fallback_allowed=True) == []


def test_a_missed_call_in_an_archiving_commit_is_refused(w, monkeypatch):
    """R3: when the unit of an unsealed ending leaves the hot state in the same commit, its bundle is already written,
    so the commit check refuses (THREAD_UNSEALED) and nothing is committed."""
    talk(w, w.inv, w.worker)
    steps = w.e._k.finalizers.steps  # without the finalizer that would seal: a path that missed its call
    monkeypatch.setattr(w.e._k.finalizers, "steps", [f for f in steps if f != w.e._coordination.finalize])
    before = w.control_bytes()
    with pytest.raises(ThreadUnsealed) as exc:
        w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    assert exc.value.code == "THREAD_UNSEALED" and exc.value.details["reason"] == "archived_unsealed"
    assert exc.value.details["invocations"] == [w.inv]
    assert w.control_bytes() == before


def test_a_store_without_the_injected_seal_refuses_instead_of_sealing(w):
    """R3: a store built without the kernel's sealing function (the perf tool) refuses an unsealed ending; it never
    creates a thread, so it never meets one in practice."""
    talk(w, w.inv, w.worker)
    bare = ControlStore(w.root / ".aew")
    before = w.control_bytes()
    with pytest.raises(ThreadUnsealed) as exc, bare.session() as s:
        s.state["invocations"][w.inv]["status"] = "interrupted"
        s.commit(Transition(op="test.bare", actor={"kind": "test"}))
    assert exc.value.details["reason"] == "no_seal_function" and w.control_bytes() == before


def test_a_commit_ending_an_invocation_without_a_thread_needs_no_seal(w):
    """N1: an invocation that never had a thread ends as before: no seal, no pointer, no hot list."""
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    after = state(w)
    assert "coordination" not in after["work"][w.wid] and L.UNSEEN_KEY not in after
    assert not list((w.root / ".aew/work").glob("*/coordination/*.seal-*.yaml"))


@pytest.mark.parametrize("path", ["acquire", "handoff_accept", "takeover"])
def test_the_direct_commit_paths_archive_no_unit(w, monkeypatch, path):
    """N1: the direct paths' history entries are Lead-credential entries only: none archives a unit, so their seal's
    pointer always lands on a hot unit."""
    talk(w, w.inv, w.worker)
    if path == "acquire":
        w.lead("invoke_cancel", invocation=w.inv, reason="release the seat")
        w.lead("lead_release")
        w.token = w.e.lead_acquire(expect_rev=w.rev(), session_label="lead-c")["token"]
    elif path == "handoff_accept":
        offer = w.lead("lead_handoff_offer", carry_invocations=[])["offer"]
        w.token = w.e.lead_handoff_accept(offer=offer, expect_rev=w.rev(), session_label="lead-b")["token"]
    else:
        takeover(w, monkeypatch)
    entries = w.e.archive.index(state(w)).list(limit=100)
    newest = max(e["seq"] for e in entries)
    assert next(e for e in entries if e["seq"] == newest)["kind"] == "lead"
    assert not any(e["kind"] == "unit" for e in entries)
    assert w.wid in state(w)["work"] and pointer(w, w.wid, w.inv) is not None
    assert_control_invariants(w)


def test_seal_ending_is_idempotent_within_a_session(w):
    """N1: a second call in the same session (a direct path that also runs the finalizers) seals nothing twice."""
    talk(w, w.inv, w.worker)
    with w.e.store.session() as s:
        w.e._lead._interrupt_invocations(s.state, "a test ending")
        refs: list[str] = []
        assert w.e._coordination.seal_ending(s, refs) == [w.inv]
        assert w.e._coordination.seal_ending(s, refs) == []
        assert len(refs) == 1 and len(s.state["work"][w.wid]["coordination"]) == 1
        s.commit(Transition(op="test.idempotent", actor={"kind": "test"}, refs=refs))
    assert fallback_events(w) == []
    assert_control_invariants(w)


def test_the_takeover_preview_writes_no_seal(w):
    """G3: the refusal that words a takeover's cost runs the takeover's interruption on a copy of the state; nothing
    is sealed or written."""
    talk(w, w.inv, w.worker)
    before = sorted((w.root / ".aew/work").rglob("*"))
    with pytest.raises(Exception) as exc:
        w.e.lead_acquire(expect_rev=w.rev(), session_label="lead-b")
    assert w.inv in exc.value.details["active_invocations"]
    assert sorted((w.root / ".aew/work").rglob("*")) == before


def test_a_carried_invocation_stays_live_and_old_generation_messages_derive_superseded(w):
    """F1, D-14: a handoff's carried invocation is not sealed; when it ends later, the old generation's never-delivered
    message is sealed as undeliverable for ``sender_superseded``, and the new generation's as ``invocation_ended``."""
    old = w.send("from generation 1")["message"]["id"]
    offer = w.lead("lead_handoff_offer", carry_invocations=[w.inv])["offer"]
    w.token = w.e.lead_handoff_accept(offer=offer, expect_rev=w.rev(), session_label="lead-b")["token"]
    assert pointer(w, w.wid, w.inv) is None and state(w)["invocations"][w.inv]["status"] == "active"
    new = w.send("from generation 2")["message"]["id"]
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert seal_of(w, w.wid, w.inv)["undeliverable"] == [{"message": old, "reason": "sender_superseded"},
                                                          {"message": new, "reason": "invocation_ended"}]
    assert_control_invariants(w)


def _fact(w: World, inv: str, fact: dict[str, Any]) -> None:
    """A fact a later slice's writer records (POSTED by MS5's supervisor; DELIVERED by MS4 to MS6), written through the
    engine's own fact writer under the lock."""
    from aew.engine.coordination_ops import read_thread

    with w.e.store.session() as s:
        thread = read_thread(w.root / ".aew", w.wid, inv)
        w.e._coordination._write_fact(s.state, thread, fact)


def test_undelivered_never_posted_messages_become_undeliverable_at_seal(w):
    """D-13: a Lead message never posted, never delivered and never answered is sealed as undeliverable; one the
    worker replied to evidently reached it and is not."""
    answered, _ = talk(w, w.inv, w.worker)
    silent = w.send("never delivered")["message"]["id"]
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert seal_of(w, w.wid, w.inv)["undeliverable"] == [{"message": silent, "reason": "invocation_ended"}]
    assert answered not in json.dumps(seal_of(w, w.wid, w.inv)["undeliverable"])


def test_a_posted_unconfirmed_message_stays_posted_at_seal(w):
    """F5: a message posted but never confirmed delivered stays POSTED (outcome unknown), never undeliverable."""
    posted = w.send("posted, then the run died")["message"]["id"]
    _fact(w, w.inv, {"kind": "POSTED", "message": posted, "run": "R-INV-0001-1", "generation": 1,
                     "checked_rev": w.rev()})
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert seal_of(w, w.wid, w.inv)["undeliverable"] == []
    assert [f["kind"] for f in w.e.message_thread(w.inv)["messages"][0]["facts"]] == ["RECORDED", "POSTED"]


@pytest.mark.parametrize("damage", ["torn_tail", "broken_chain"])
def test_a_damaged_thread_is_sealed_and_never_blocks_the_ending_commit(w, damage):
    """F13a: a torn tail or a line that breaks the chain never refuses the ending: the thread is sealed ``damaged``
    with the verified prefix's length, the commit check passes, and the reads show the verified prefix only."""
    talk(w, w.inv, w.worker)
    path = w.thread_path()
    good = path.read_bytes()
    path.write_bytes(good + (b'{"type":"message","h":"' if damage == "torn_tail" else b'{"type":"fact","h":"00"}\n'))
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    seal = seal_of(w, w.wid, w.inv)
    assert seal["damaged"] is True and seal["verified_bytes"] == len(good) and seal["lines"] == 2
    assert seal["thread"]["size"] == len(path.read_bytes())
    assert [m["id"] for m in w.e.message_thread(w.inv)["messages"]] == [f"MSG-{w.inv}-1", f"MSG-{w.inv}-2"]
    assert fallback_events(w) == []
    assert_control_invariants(w)


def test_the_redo_record_holds_only_the_seal_records_path_and_hash(w, monkeypatch):
    """F13d: the seal is prewritten and referenced by path and hash: the redo record never carries thread bytes."""
    talk(w, w.inv, w.worker, body="X" * 3000)
    staged: list[bytes] = []
    real = util.atomic_write

    def spy(path, data, *a, **kw):
        if "state/txn/" in Path(path).as_posix():
            staged.append(data if isinstance(data, bytes) else data.encode())
        return real(path, data, *a, **kw)

    monkeypatch.setattr("aew.engine.store.atomic_write", spy)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    p = pointer(w, w.wid, w.inv)
    assert staged and all(b"X" * 100 not in raw for raw in staged)
    redo = util.load_yaml(next(r for r in staged if b"prewritten" in r).decode())
    assert {"path": p["seal"], "sha256": p["sha256"]} in redo["prewritten"]


@pytest.mark.parametrize("point", ["txn.before_stage", "txn.before_replace"])
def test_a_failed_commit_leaves_an_unreferenced_seal_and_a_writable_thread(w, monkeypatch, point):
    """N1 (crash safety): a seal written before a commit that never lands is an unreferenced, benign file; the
    invocation stays active, its thread writable, and a retry seals it (the same bytes give the same record)."""
    lead, _ = talk(w, w.inv, w.worker)
    monkeypatch.setenv("AEW_FAULT", point)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    with pytest.raises(faults.InjectedFault):
        w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    monkeypatch.delenv("AEW_FAULT")
    seals = list((w.root / ".aew/work").glob(f"*/coordination/{w.inv}.seal-*.yaml"))
    assert len(seals) == 1 and state(w)["invocations"][w.inv]["status"] == "active"
    assert pointer(w, w.wid, w.inv) is None
    w.reply(lead, "still writable")
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert seal_of(w, w.wid, w.inv)["messages"] == 3
    assert_control_invariants(w)


def test_a_sealed_thread_accepts_nothing(w):
    """D-16: once sealed, a thread takes no message and no fact: the Lead's recipient is no longer active, the worker's
    credential is revoked, and the engine's writers refuse a sealed thread by itself."""
    from aew.engine.coordination_ops import read_thread

    lead, _ = talk(w, w.inv, w.worker)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    sealed = thread_bytes(w, w.wid, w.inv)
    with pytest.raises(IllegalTransition):
        w.send("after the end")
    with pytest.raises(StaleAuthority):
        w.reply(lead, "after the end")
    with pytest.raises(IllegalTransition) as exc, w.e.store.session() as s:
        w.e._coordination._write_fact(s.state, read_thread(w.root / ".aew", w.wid, w.inv),
                                      {"kind": "DELIVERED", "message": lead, "via": "live"})
    assert exc.value.details["reason"] == "thread_sealed"
    assert thread_bytes(w, w.wid, w.inv) == sealed


def test_the_seal_records_the_threads_hash_and_size(w):
    """N4: the seal names the thread exactly as sealed: its sha256 and size, its chain head and line count."""
    from aew.engine.coordination_ops import read_thread

    talk(w, w.inv, w.worker, replies=2)
    thread = read_thread(w.root / ".aew", w.wid, w.inv)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    seal = seal_of(w, w.wid, w.inv)
    raw = thread_bytes(w, w.wid, w.inv)
    assert seal["thread"] == {"path": L.thread_rel(w.wid, w.inv), "sha256": util.sha256_bytes(raw), "size": len(raw)}
    assert (seal["head"], seal["lines"], seal["messages"], seal["damaged"]) == (thread.head, 3, 3, False)
    assert seal["closed_rev"] == w.rev() and pointer(w, w.wid, w.inv)["closed_rev"] == w.rev()


def test_a_full_history_verification_detects_an_altered_sealed_thread(w):
    """N4: archival pins the seal and the seal pins its thread, so a line appended to an archived unit's sealed thread
    fails `history audit --full`."""
    talk(w, w.inv, w.worker)
    w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    assert w.e.history_audit(full=True)["ok"]
    with open(w.thread_path(), "ab") as fh:
        fh.write(b'{"type":"fact"}\n')
    with pytest.raises(IntegrityError) as exc:
        w.e.history_audit(full=True)
    assert any(L.thread_rel(w.wid, w.inv) in p for p in exc.value.details["audit"]["problems"])


def test_a_hot_units_altered_sealed_thread_is_reported_never_shown(w):
    """D-16 "Hot units": the reads check the seal against its pointer and the thread against its seal before they
    show any text; a mismatch is an integrity failure, never text."""
    talk(w, w.inv, w.worker)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    path = w.thread_path()
    path.write_bytes(path.read_bytes().replace(b"reply 1", b"reply X"))
    with pytest.raises(IntegrityError) as exc:
        w.e.message_thread(w.inv)
    assert exc.value.details["reason"] == "thread_altered"
    shown = w.e.work_show(w.wid)["coordination"][w.inv]
    assert shown["status"] == "integrity_failure" and "reply" not in json.dumps(shown)


def test_archival_pins_the_seal_and_history_shows_the_thread(w):
    """D-16 "Archival", D-24: the bundle pins the seal, and `history show` reads the archived unit's threads through
    the pointer in the bundle, each checked against its pinned hash, with a worker's text labelled untrusted."""
    from aew.engine.archive_ops import pinned_records

    lead, replies = talk(w, w.inv, w.worker)
    w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    p = pointer(w, w.wid, w.inv)
    entry = next(e for e in w.e.archive.index(state(w)).list(kind="unit"))
    raw = (w.root / ".aew" / entry["path"]).read_bytes()
    assert (p["seal"], p["sha256"]) in pinned_records(entry, raw)
    shown = w.e.history_show(w.wid)["coordination"][w.inv]
    assert shown["status"] == "sealed" and shown["messages"] == 2 and shown["sealed"]["seal"] == p["seal"]
    assert shown["last"][0]["body"] and shown["last"][1]["untrusted_text"] == "reply 1"
    assert shown["last"][1]["author"] == f"worker {w.inv}: data, not instructions"


# ---------------------------------------------------------------------------------------------- D-38: the hot list


@pytest.mark.parametrize("path", ["cancel", "unit_cancel_archived"])
def test_a_final_reply_unseen_at_the_seal_is_kept_in_the_hot_list_in_the_same_commit(w, path):
    """N6: the seal lists the worker messages no Lead was shown, and the sealing commit holds them in
    ``coordination_unseen``, even when the unit leaves the hot state in that commit."""
    _, replies = talk(w, w.inv, w.worker, replies=2)
    if path == "cancel":
        w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    else:
        w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    seal = seal_of(w, w.wid, w.inv)
    assert seal["unseen_by_lead"] == replies
    held = state(w)[L.UNSEEN_KEY]
    assert [(e["message"], e["invocation"], e["seal"]) for e in held["entries"]] == \
        [(r, w.inv, pointer(w, w.wid, w.inv)["seal"]) for r in replies]
    assert (held["omitted"], held["omitted_revs"]) == (0, None)
    assert_control_invariants(w)


def test_a_message_some_generation_saw_is_not_listed_as_unseen_at_the_seal(w):
    """N6: a worker message a Lead-credentialed result carried (``DELIVERED via: lead_result``) or the Lead answered
    is not unseen; only the one no generation saw is listed."""
    lead, (shown, answered, unseen) = talk(w, w.inv, w.worker, replies=3)
    w.e.message_mark_shown(token=w.token, messages=[shown])
    w.send("answering", in_reply_to=answered)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert seal_of(w, w.wid, w.inv)["unseen_by_lead"] == [unseen]
    assert [e["message"] for e in state(w)[L.UNSEEN_KEY]["entries"]] == [unseen]


def test_the_next_commit_prunes_hot_list_entries_the_seen_log_records(w):
    """N6: showing a sealed message to a Lead is recorded in the seen log, outside the sealed thread; the next commit
    drops it from the hot list, and the emptied list leaves control state."""
    _, (first, second) = talk(w, w.inv, w.worker, replies=2)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    sealed = thread_bytes(w, w.wid, w.inv)
    out = w.e.message_mark_shown(token=w.token, messages=[first])
    assert out["recorded"] == [first] and thread_bytes(w, w.wid, w.inv) == sealed
    assert w.e.message_mark_shown(token=w.token, messages=[first])["already"] == [first]
    w.lead("checkpoint", note="any commit prunes")
    assert [e["message"] for e in state(w)[L.UNSEEN_KEY]["entries"]] == [second]
    w.e.message_mark_shown(token=w.token, messages=[second])
    w.lead("checkpoint", note="and again")
    assert L.UNSEEN_KEY not in state(w)
    assert_control_invariants(w)


def _flood(w: World, inv: str, token: str, n: int) -> list[str]:
    lead = w.send("report as you go", to=inv)["message"]["id"]
    return [w.reply(lead, f"note {k}", invocation_token=token)["message"]["id"] for k in range(n)]


def test_coordination_unseen_stays_bounded_without_a_broker(w):
    """R1: 25 settled replies no Lead-credentialed call showed leave 20 entries, ``omitted: 5`` and the range of the
    sealing revisions they came from; the key never exceeds its cap. Each omitted one stays listed in its seal."""
    first = _flood(w, w.inv, w.worker, 20)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    wid, inv, token = non_mutating(w)
    second = _flood(w, inv, token, 5)
    w.lead("work_redispatch", work_id=wid, reason="a fresh attempt")
    held = state(w)[L.UNSEEN_KEY]
    assert [e["message"] for e in held["entries"]] == first
    assert held["omitted"] == 5 and held["omitted_revs"] == [w.rev(), w.rev()]
    assert seal_of(w, wid, inv)["unseen_by_lead"] == second
    assert_control_invariants(w)


def test_the_unseen_recovery_read_lists_the_omitted_and_clears_the_count(w, monkeypatch):
    """R1: `aew message unseen` walks only the transition-log records in ``omitted_revs``, lists the omitted messages
    from their seals, and a Lead-credentialed run records them shown, so the next commit resets ``omitted``. An
    operator's run without the credential records nothing."""
    from aew.engine import outbox

    _flood(w, w.inv, w.worker, 20)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    wid, inv, token = non_mutating(w)
    second = _flood(w, inv, token, 5)
    w.lead("work_redispatch", work_id=wid, reason="a fresh attempt")
    revs = state(w)[L.UNSEEN_KEY]["omitted_revs"]
    walked: list[tuple[int, int]] = []
    real = outbox.read_transitions
    monkeypatch.setattr(outbox, "read_transitions",
                        lambda root, since, through, **kw: walked.append((since, through)) or real(root, since,
                                                                                                    through, **kw))
    operator = w.e.message_unseen()
    assert [m["message"] for m in operator["messages"]] == second and operator["recorded"] is False
    assert walked == [(revs[0] - 1, revs[1])]
    assert operator["messages"][0]["untrusted_text"] == "note 0"
    w.lead("checkpoint", note="nothing was recorded")
    assert state(w)[L.UNSEEN_KEY]["omitted"] == 5
    lead = w.e.message_unseen(token=w.token)
    assert lead["recorded"] is True
    w.lead("checkpoint", note="the recovery clears the count")
    held = state(w)[L.UNSEEN_KEY]
    assert (held["omitted"], held["omitted_revs"], len(held["entries"])) == (0, None, 20)
    assert w.e.message_unseen()["messages"] == []
    assert_control_invariants(w)


def test_every_seal_path_is_in_its_commits_refs(w, monkeypatch):
    """R1: each sealing commit names its seal in the transition's refs, on a Lead transaction and on a direct path, so
    the transition log names every seal."""
    talk(w, w.inv, w.worker)
    wid, inv, token = non_mutating(w)
    talk(w, inv, token)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert pointer(w, w.wid, w.inv)["seal"] in log_record(w, w.rev())["refs"]
    takeover(w, monkeypatch)
    assert pointer(w, wid, inv)["seal"] in log_record(w, w.rev())["refs"]


# ---------------------------------------------------------------------------------------------- D-31: the marker


def test_the_projection_stats_one_marker_and_globs_no_unit_directory(w, monkeypatch):
    """N5: whether the reads show coordination is one stat of the project marker; no read globs the unit directories
    (only `doctor`, an explicit command, lists them)."""
    talk(w, w.inv, w.worker)
    globbed: list[str] = []
    real = Path.glob
    monkeypatch.setattr(Path, "glob", lambda self, pattern, *a, **kw: globbed.append(pattern) or real(self, pattern,
                                                                                                       *a, **kw))
    shown = w.e.work_show(w.wid)
    assert shown["coordination"][w.inv]["status"] == "live"
    assert not [g for g in globbed if "coordination" in g or g.startswith("*/")]


def test_a_deleted_marker_never_lets_a_thread_end_unsealed(w):
    """N5: the seal and the commit check stat the ending invocation's own thread, never the marker: a marker deleted
    outside AEW changes nothing about sealing (and the oracle reports the deletion)."""
    talk(w, w.inv, w.worker)
    (w.root / ".aew" / L.MARKER_REL).unlink()
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert pointer(w, w.wid, w.inv) is not None and fallback_events(w) == []
    full, _ = with_cold(w.root, load_control(w.root))
    assert any("marker" in p for p in coordination_violations(w.root, load_control(w.root), full))


# ---------------------------------------------------------------------------------------------- D-39: registration


def _with_keys(tmp_path: Path, key: str) -> dict[str, Any]:
    w = world(tmp_path)
    talk(w, w.inv, w.worker)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    s = load_control(w.root)
    present = {"coordination_store": "coordination_store" in s, "coordination_unseen": L.UNSEEN_KEY in s,
               "unit_coordination": bool(s["work"][w.wid].get("coordination"))}
    assert present[key], f"the walk did not reach a state holding {key}"
    return s


def pre_ms2_validator(baseline: dict[str, Any]) -> Draft202012Validator:
    """The control schema of main before MS2 with the schemas it refers to as they were then: the transition record's
    (vendored beside it); the others it names did not change."""
    from referencing import Resource

    from aew.schemas import _registry

    transition = json.loads(PRE_MS2_TRANSITION.read_text(encoding="utf-8"))
    registry = _registry().with_resource(transition["$id"], Resource.from_contents(transition))
    return Draft202012Validator(baseline, registry=registry)


@pytest.mark.parametrize("key", ["coordination_store", "coordination_unseen", "unit_coordination"])
def test_an_engine_before_ms2_refuses_a_state_holding_the_coordination_keys(tmp_path, key):
    """R4, D-16, D-38: an engine built before thread sealing (main at 22ab997, its control schema vendored) refuses a
    control state that holds any coordination key, at its first read, so it can never end a messaged invocation
    without a seal. Its schema leaves a unit's keys open, so a state with the unit's pointer is refused through the
    registration key, which every such state holds (C6: a thread implies it)."""
    s = _with_keys(tmp_path, key)
    baseline = json.loads(PRE_MS2_SCHEMA.read_text(encoding="utf-8"))
    old = pre_ms2_validator(baseline)
    errors = [e.message for e in old.iter_errors(s)]
    top = "coordination_unseen" if key == "coordination_unseen" else "coordination_store"
    assert any("Additional properties are not allowed" in e and f"'{top}'" in e for e in errors), errors
    stripped = {k: v for k, v in s.items() if k not in ("coordination_store", "coordination_unseen")}
    if key == "unit_coordination":  # the old schema alone would accept the pointer: the key is what protects it
        assert stripped["work"][next(iter(stripped["work"]))].get("coordination")
    assert [e.message for e in old.iter_errors(stripped)] == [], "the old engine refuses the keys and nothing else"


def test_adopting_messaging_enabled_commits_the_coordination_store_key_once(tmp_path):
    """D-39: the adoption that leaves the switch enabled registers the project in its own commit, naming its decision;
    a later adoption (of `disabled`, or of an unrelated edit) neither rewrites nor removes it."""
    w = world(tmp_path, messaging=None)
    assert "coordination_store" not in state(w)
    set_messaging(w.root, "enabled")
    out = w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="turn messaging on", authorization=OPERATOR)
    key = state(w)["coordination_store"]
    assert key == {"since_rev": out["revision"], "decision": out["decision"]}
    set_messaging(w.root, "disabled")
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="turn messaging off", authorization=OPERATOR)
    assert state(w)["coordination_store"] == key
    set_messaging(w.root, "enabled")
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="on again", authorization=OPERATOR)
    assert state(w)["coordination_store"] == key


@pytest.mark.parametrize("setting", [None, "disabled"])
def test_an_adoption_that_leaves_messaging_off_writes_no_key(tmp_path, setting):
    """D-39 "Off and never enabled": an adoption that leaves the switch absent or disabled registers nothing."""
    w = world(tmp_path, messaging=setting)
    (w.root / ".aew/policy/gates.yaml").write_bytes((w.root / ".aew/policy/gates.yaml").read_bytes() + b"# edit\n")
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="an unrelated edit", authorization=OPERATOR)
    assert "coordination_store" not in state(w)


def test_recording_needs_the_coordination_store_key(w):
    """D-39, D-31: from MS2 on, recording also needs the registration key; a project that adopted `enabled` under an
    engine between MS1 and MS2 has the switch but no key, and is refused `not_registered` until the operator adopts
    a real edit; `doctor` names that fix."""
    s = load_control(w.root)
    s.pop("coordination_store")
    from aew.engine.store import serialize_control

    (w.root / ".aew/state/control.yaml").write_bytes(serialize_control(s))
    with pytest.raises(MessagingDisabled) as exc:
        w.send()
    assert exc.value.details["reason"] == "not_registered" and w.coordination_files() == []
    check = next(c for c in w.e.doctor_checks() if c["check"] == "coordination")
    assert check["status"] == "WARN" and "manifest adopt" in check["detail"] and "comment" in check["detail"]
    policy = w.root / ".aew/policy/execution.yaml"
    policy.write_bytes(policy.read_bytes() + b"# reviewed\n")
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="register messaging", authorization=OPERATOR)
    assert w.send()["ok"]


def test_doctor_and_c6_report_an_ended_invocation_with_an_unsealed_thread(w):
    """D-39 backstop: an invocation no longer active whose thread no seal pins (here: control state rolled back by
    hand around the seal) is named by `doctor` and by the oracle; doctor reports, it never seals."""
    talk(w, w.inv, w.worker)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    s = load_control(w.root)
    s["work"][w.wid].pop("coordination")
    s.pop(L.UNSEEN_KEY, None)
    from aew.engine.store import serialize_control

    (w.root / ".aew/state/control.yaml").write_bytes(serialize_control(s))
    check = next(c for c in w.e.doctor_checks() if c["check"] == "coordination")
    assert check["status"] == "FAIL" and f"{w.inv} ended but its thread" in check["detail"]
    full, _ = with_cold(w.root, s)
    assert any(f"{w.inv} is cancelled but its thread has no seal" in p
               for p in coordination_violations(w.root, s, full))
    assert load_control(w.root) == s  # reported, not sealed


# ---------------------------------------------------------------------------------------------- the switch (D-31)


CRASHING_WRITER = """
import os, sys
from pathlib import Path
from aew.engine.api import Engine
from aew.engine import coordination_ops as C
real = C._append_line
def append_then_die(path, line):
    real(path, line)
    os._exit(3)
C._append_line = append_then_die
e = Engine.discover(Path(sys.argv[1]))
e.message_record_lead(token=sys.argv[2], expect_rev=int(sys.argv[3]), to=sys.argv[4], body="before the crash")
"""


def test_a_supervisor_crash_never_erases_a_thread(w):
    """Invariant 11: a process that dies right after its append leaves the thread intact and readable; the next
    ending seals it with that message."""
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])}
    done = subprocess.run([sys.executable, "-c", CRASHING_WRITER, str(w.root), w.token, str(w.rev()), w.inv],
                          env=env, capture_output=True, text=True, timeout=120, **kwargs)
    assert done.returncode == 3, done.stderr
    assert [m["body"] for m in w.e.message_thread(w.inv)["messages"]] == ["before the crash"]
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert seal_of(w, w.wid, w.inv)["messages"] == 1


def test_threads_stay_readable_after_the_switch_is_turned_off(w):
    """F7, D-31: turning the switch off stops new records only; a thread is still sealed when its invocation ends,
    and the reads still show it, because a thread exists."""
    lead, _ = talk(w, w.inv, w.worker)
    set_messaging(w.root, "disabled")
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="turn messaging off", authorization=OPERATOR)
    with pytest.raises(MessagingDisabled):
        w.send("after off")
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert pointer(w, w.wid, w.inv) is not None
    assert w.e.work_show(w.wid)["coordination"][w.inv]["status"] == "sealed"
    assert [m["id"] for m in w.e.message_thread(w.inv)["messages"]][0] == lead
    assert w.e.message_list(w.wid)["threads"][w.inv]["messages"] == 2


def test_the_operator_reconstructs_a_tickets_coordination_from_the_ticket(w):
    """Invariant 21 (engine reads): from the Ticket alone the operator lists its threads, hot or archived, and reads
    each one with its seal."""
    talk(w, w.inv, w.worker)
    w.lead("work_transition", work_id=w.wid, to="CANCELLED", reason="no longer needed")
    listed = w.e.message_list(w.wid)
    assert list(listed["threads"]) == [w.inv] and listed["threads"][w.inv]["status"] == "sealed"
    thread = w.e.message_thread(w.inv)
    assert len(thread["messages"]) == 2 and thread["sealed"]["seal"] == pointer(w, w.wid, w.inv)["seal"]


def test_a_review_records_the_lead_messages_it_received(tmp_path):
    """F17, D-35: the evidence an invocation submits records the Lead messages it had before (posted or delivered to
    it, or answered by it), with each message's digest, kind and way in; a message it never had is not listed, and a
    submission cannot supply the field itself."""
    from aew.history.manifest import canonical_json

    w = world(tmp_path, checks=True)
    implement(w)
    w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")
    out = w.lead("invoke_create", work_id=w.wid, role="reviewer")
    reviewer, rinv = out["invocation_token"], out["invocation"]
    delivered = w.send("focus on the shutdown path", to=rinv)["message"]
    answered, _ = talk(w, rinv, reviewer)
    unseen = w.send("never delivered", to=rinv)["message"]["id"]
    with w.e.store.session() as s:
        from aew.engine.coordination_ops import read_thread

        w.e._coordination._write_fact(s.state, read_thread(w.root / ".aew", w.wid, rinv),
                                      {"kind": "DELIVERED", "message": delivered["id"], "via": "live"})
    with pytest.raises(Exception) as forged:
        w.e.submit(invocation_token=reviewer, kind="review", text=CP.submission({**CP.REVIEW,
                                                                                  "coordination_inputs": []}))
    assert "coordination_inputs" in str(forged.value.details)
    evidence = w.e.submit(invocation_token=reviewer, kind="review", text=CP.submission(CP.REVIEW))["evidence"]
    meta, _ = util.parse_frontmatter((w.root / ".aew/evidence" / w.wid / f"{evidence}.md").read_text(encoding="utf-8"))
    assert meta["coordination_inputs"] == [
        {"message": delivered["id"], "sha256": util.sha256_bytes(canonical_json(delivered)), "kind": "instruction",
         "via": "live"},
        {"message": answered, "sha256": meta["coordination_inputs"][1]["sha256"], "kind": "instruction",
         "via": "replied"}]
    assert unseen not in json.dumps(meta["coordination_inputs"])


def test_with_messaging_never_enabled_work_show_help_and_control_state_are_byte_identical(tmp_path):
    """Off means absent (D-31, D-39): with messaging never enabled, an invocation's ending commits exactly what it did
    before MS2 (no pointer, no hot list, no registration key, no marker, no seen log, no seal), `work show` has no
    coordination field, `doctor` no coordination line, `aew message` does not exist, and an adoption that leaves the
    switch absent writes no key."""
    from aew.cli.main import build_parser, coordination_reads_for

    w = world(tmp_path, messaging=None)
    assert "coordination" not in w.e.work_show(w.wid)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    s = load_control(w.root)
    assert not {"coordination_store", "coordination_unseen"} & set(s) and "coordination" not in s["work"][w.wid]
    assert w.coordination_files() == []
    assert not (w.root / ".aew/coordination").exists()
    assert "coordination" not in w.e.work_show(w.wid)
    assert all(c["check"] != "coordination" for c in w.e.doctor_checks())
    argv = ["-C", str(w.root), "message", "list", "--work", w.wid]
    assert coordination_reads_for(argv) is False
    assert build_parser().format_help() == build_parser(coordination_reads=False).format_help()
    assert "message" not in commands(build_parser()) and "message" in commands(build_parser(coordination_reads=True))
    with pytest.raises(SystemExit):
        build_parser(coordination_reads=coordination_reads_for(argv)).parse_args(argv)


def commands(parser) -> set[str]:
    import argparse

    return {name for a in parser._actions if isinstance(a, argparse._SubParsersAction) for name in a.choices}


def test_the_operator_reads_exist_only_while_on_and_never_inside_a_run(w, monkeypatch, tmp_path):
    """D-21, D-24, D-31: `aew message` is registered only for a project whose switch is on or that holds a thread,
    and never inside a worker's run (no worker is offered reads of other threads)."""
    from aew.cli.main import coordination_reads_for

    argv = ["-C", str(w.root), "message", "thread", w.inv]
    assert coordination_reads_for(argv) is True
    assert coordination_reads_for(["-C", str(w.root), "status"]) is False  # only a message command pays for it
    monkeypatch.setenv("AEW_AGENT_ENDPOINT", "inside-a-run")
    assert coordination_reads_for(argv) is False
    monkeypatch.delenv("AEW_AGENT_ENDPOINT")
    assert coordination_reads_for(["-C", str(tmp_path / "nowhere"), "message", "thread", "INV-0001"]) is False


# ---------------------------------------------------------------------------------------------- the walk (R3)


def test_no_known_ending_path_needs_the_seal_fallback(tmp_path, monkeypatch):
    """R3, the store-model walk: every kind of invocation that can be a recipient is messaged (an implementer, a
    reviewer and a verifier, a non-mutating executor, a custodian's role-bearing child, a carried and an uncarried
    invocation across a handoff) while the custody invocation is refused; the ending paths run (ingest, cancel,
    redispatch, transition, queue retirement, handoff acceptance, takeover); every ended thread is sealed, and no
    transition carries a ``coordination.seal_fallback`` event."""
    w = world(tmp_path, checks=True)
    talk(w, w.inv, w.worker)
    implement(w)
    w.lead("work_transition", work_id=w.wid, to="REVIEW_PENDING")  # the implementer ends by its report's ingest
    out = w.lead("invoke_create", work_id=w.wid, role="reviewer")
    talk(w, out["invocation"], out["invocation_token"])
    review = w.e.submit(invocation_token=out["invocation_token"], kind="review",
                        text=CP.submission(CP.REVIEW))["evidence"]
    w.lead("review_ingest", work_id=w.wid, evidence_id=review)  # the reviewer ends by ingest
    w.lead("work_transition", work_id=w.wid, to="VERIFY_PENDING")
    out = w.lead("invoke_create", work_id=w.wid, role="verifier")
    talk(w, out["invocation"], out["invocation_token"])
    w.lead("verify_ingest", work_id=w.wid, evidence_id=verification(w, out["invocation_token"], "ticket"))
    w.lead("work_transition", work_id=w.wid, to="COMMIT_READY")
    w.lead("integrate_prepare", work_id=w.wid)
    custodian = next(i for i, v in state(w)["invocations"].items()
                     if v.get("kind") == "integration_attempt" and v["status"] == "active")
    with pytest.raises(NotAWorker):
        w.send(to=custodian)
    out = w.lead("invoke_create", work_id=w.wid, role="verifier", scope="integration")
    talk(w, out["invocation"], out["invocation_token"])
    w.lead("work_transition", work_id=w.wid, to="RUNNING", reason="rework")  # queue retirement ends the child
    wid, inv, token = non_mutating(w)
    talk(w, inv, token)
    again = w.lead("work_redispatch", work_id=wid, reason="a fresh attempt")  # the old attempt ends
    carried = again["invocation"]
    talk(w, carried, again["invocation_token"])
    other_wid, uncarried, other_token = non_mutating(w)
    talk(w, uncarried, other_token)
    offer = w.lead("lead_handoff_offer", carry_invocations=[carried])["offer"]
    w.token = w.e.lead_handoff_accept(offer=offer, expect_rev=w.rev(), session_label="lead-b")["token"]
    assert pointer(w, wid, carried) is None and pointer(w, other_wid, uncarried) is not None
    takeover(w, monkeypatch)  # ends the carried attempt too
    ended = [(u, i) for u, unit in [*state(w)["work"].items()] for i in unit.get("invocations") or []
             if (w.root / ".aew" / L.thread_rel(u, i)).is_file()]
    assert len(ended) >= 7
    for u, i in ended:
        assert state(w)["invocations"][i]["status"] != "active" and pointer(w, u, i) is not None, i
    assert fallback_events(w) == []
    assert_control_invariants(w)
    assert copy.deepcopy(state(w)).get(L.UNSEEN_KEY)  # the replies nobody showed are held for the Lead


# ---------------------------------------------------------------------------------------------- PR #167 review fixes


@pytest.mark.parametrize("how", ["shown_live_before_seal", "lead_replied_before_seal"])
def test_marking_a_sealed_message_the_seal_does_not_list_records_nothing(w, how):
    """Review finding 1: after the seal, only a message its seal lists as unseen goes to the seen log. One a Lead was
    shown live, or answered, before the seal is `already`: no line, the seen log stays bounded, and rule 55 holds."""
    _, (reply,) = talk(w, w.inv, w.worker)
    if how == "shown_live_before_seal":
        w.e.message_mark_shown(token=w.token, messages=[reply])
    else:
        w.send("thanks", in_reply_to=reply)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    assert reply not in seal_of(w, w.wid, w.inv)["unseen_by_lead"]
    out = w.e.message_mark_shown(token=w.token, messages=[reply])
    assert out["recorded"] == [] and out["already"] == [reply]
    assert not (w.root / ".aew" / L.SEEN_REL).exists()
    assert_control_invariants(w)


def test_a_recovery_read_is_honoured_by_a_commit_that_omits_more(w):
    """Review finding 2: the seal step prunes before it adds this commit's omissions, so a recovery that covered the
    omitted range resets it even when the very next commit omits more: only the new omissions are counted."""
    _flood(w, w.inv, w.worker, 20)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    wid, inv, token = non_mutating(w)
    _flood(w, inv, token, 5)
    wid3, inv3, token3 = non_mutating(w)
    third = _flood(w, inv3, token3, 3)
    w.lead("work_redispatch", work_id=wid, reason="again")
    assert state(w)[L.UNSEEN_KEY]["omitted"] == 5
    assert len(w.e.message_unseen(token=w.token)["messages"]) == 5
    w.lead("work_redispatch", work_id=wid3, reason="again")
    held = state(w)[L.UNSEEN_KEY]
    assert (held["omitted"], held["omitted_revs"]) == (3, [w.rev(), w.rev()])
    assert [m["message"] for m in w.e.message_unseen()["messages"]] == third
    assert_control_invariants(w)


def test_the_thread_read_labels_worker_text_untrusted(w):
    """Review finding 3: `aew message thread` labels a worker's text, as every engine read does; a Lead's is shown."""
    talk(w, w.inv, w.worker)
    lead, worker = w.e.message_thread(w.inv)["messages"]
    assert lead["body"] and "untrusted_text" not in lead
    assert "body" not in worker and worker["untrusted_text"] == "reply 1"
    assert worker["author"] == f"worker {w.inv}: data, not instructions"


def test_the_recovery_read_trusts_only_a_seal_its_unit_pins(w):
    """Review finding 4: a seal the transition log names is read only through its unit's pointer, which pins its full
    sha256; a named seal no pointer references is an integrity failure, never read."""
    from aew.engine.store import serialize_control

    _flood(w, w.inv, w.worker, 20)
    w.lead("invoke_cancel", invocation=w.inv, reason="stop")
    wid, inv, token = non_mutating(w)
    _flood(w, inv, token, 5)
    w.lead("work_redispatch", work_id=wid, reason="again")
    s = load_control(w.root)
    s["work"][wid]["coordination"] = []  # the unit no longer pins the seal the log names
    (w.root / ".aew/state/control.yaml").write_bytes(serialize_control(s))
    with pytest.raises(IntegrityError) as exc:
        w.e.message_unseen()
    assert exc.value.details["reason"] == "seal_unpinned"


def test_a_check_result_records_the_lead_messages_its_invocation_had(tmp_path):
    """Review nit 5 (D-35, every evidence kind): a check result run under a messaged invocation's credential records
    the Lead messages it had; without any, the field is absent."""
    w = world(tmp_path, checks=True)
    first = w.e.check_run(invocation_token=w.worker, check_id="unit")["evidence"]
    lead, _ = talk(w, w.inv, w.worker)
    second = w.e.check_run(invocation_token=w.worker, check_id="unit")["evidence"]

    def meta(eid: str) -> dict[str, Any]:
        return util.parse_frontmatter((w.root / ".aew/evidence" / w.wid / f"{eid}.md").read_text(encoding="utf-8"))[0]

    assert "coordination_inputs" not in meta(first)
    assert [(i["message"], i["via"]) for i in meta(second)["coordination_inputs"]] == [(lead, "replied")]


def test_migrating_a_v1_project_that_adopted_messaging_registers_it(tmp_path):
    """Review nit 6 (D-39): a v1 project cannot hold the v2-only key, so its adoption of `enabled` registers nothing;
    the migration that makes it v2 registers it (`via: migrate`), recording then works, and doctor has nothing to
    blame."""
    from aew.engine.base import as_v1
    from aew.engine.store import serialize_control

    w = world(tmp_path, messaging=None)
    (w.root / ".aew/state/control.yaml").write_bytes(serialize_control(as_v1(load_control(w.root))))
    set_messaging(w.root, "enabled")
    w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="messaging on, while v1", authorization=OPERATOR)
    assert "coordination_store" not in state(w)
    out = w.e.migrate(token=w.token, expect_rev=w.rev())
    assert state(w)["coordination_store"] == {"since_rev": out["revision"], "decision": None, "via": "migrate"}
    assert w.send()["ok"]
    assert next(c for c in w.e.doctor_checks() if c["check"] == "coordination")["status"] == "PASS"
    assert_control_invariants(w)
