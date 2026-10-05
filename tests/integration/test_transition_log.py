"""ADR-0012 (M4-D slice D1): the transition log as the outbox, on real projects.

Every commit leaves one typed, chained record; an oversized transition keeps its complete events outside hot state;
damage fails closed; the cursor is the revision; a commit wakes a waiter in another process; and an older engine
refuses an outbox-era control file."""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))

from aewflow import create_planned_ticket, integrate, sample_project, to_commit_ready  # noqa: E402
from invariants import assert_control_invariants, load_control  # noqa: E402

from aew.engine import outbox  # noqa: E402
from aew.engine.store import ControlStore, Transition, serialize_control  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def log(p, *args: str) -> dict:
    return p.ok("history", "log", *args, "--json")


def kinds(transitions: list[dict]) -> set[str]:
    return {e["kind"] for t in transitions for e in t["events"]}


def test_a_ticket_from_creation_to_done_leaves_one_typed_chained_record_per_commit(tmp_path):
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    integrate(p, wid)
    state = load_control(p.root)
    out = log(p, "--since", "0")
    assert [t["revision"] for t in out["transitions"]] == list(range(1, state["revision"] + 1))
    assert out["next"] == state["revision"]
    # what happened, typed: the unit's moves, its archival, its invocations and credentials, the history append, the
    # decisions recorded and the evidence the Lead ingested
    assert {"lead.generation", "work.state", "invocation.status", "credential.revoked", "history.appended",
            "unit.archived", "decision.recorded", "evidence.ingested"} <= kinds(out["transitions"])
    moves = [(e["from"], e["to"]) for t in out["transitions"] for e in t["events"]
             if e["kind"] == "work.state" and e["id"] == wid]
    assert moves[0] == (None, "BLOCKED") and moves[-1] == ("COMMIT_READY", "DONE")
    # the chain: from genesis at the outbox's start, each record's h commits to the one before
    prev = outbox.GENESIS_H
    assert state["outbox"] == {"schema": outbox.OUTBOX_SCHEMA, "since": 0}
    for revision in range(0, state["revision"] + 1):
        raw = outbox._read_record(p.root / ".aew", revision)
        assert raw["h"] == outbox.transition_hash(prev, raw)
        prev = raw["h"]
    assert state["last_transition"]["h"] == prev
    assert_control_invariants(p)


def test_the_cursor_pages_and_kind_narrows(tmp_path):
    p = sample_project(tmp_path)
    for i in range(3):
        create_planned_ticket(p, tmp_path, title=f"Ticket {i}")
    rev = load_control(p.root)["revision"]
    first = log(p, "--since", "0", "--limit", "2")
    assert [t["revision"] for t in first["transitions"]] == [1, 2] and first["next"] == 2
    rest = log(p, "--since", str(first["next"]))
    assert [t["revision"] for t in rest["transitions"]] == list(range(3, rev + 1))
    narrowed = log(p, "--since", "0", "--kind", "decision.recorded")["transitions"]
    assert narrowed and all({e["kind"] for e in t["events"]} == {"decision.recorded"} for t in narrowed)
    assert log(p, "--since", str(rev))["transitions"] == []
    assert p.aew("history", "log", "--since", str(rev + 1)).error["code"] == "USAGE"
    assert p.aew("history", "log", "--since", "0", "--kind", "made.up").error["code"] == "USAGE"


def big_commit(p, n: int = 70) -> int:
    """One transition that creates ``n`` units: more events than the hot bound."""
    wid = create_planned_ticket(p, p.root.parent, title="template")
    store = ControlStore(p.root / ".aew")
    with store.session() as s:
        template = s.state["work"][wid]
        for i in range(n):
            s.state["work"][f"T-9{i:03d}"] = dict(template, id=f"T-9{i:03d}")
        return s.commit(Transition(op="test.bulk", actor={"kind": "test"}))


def test_an_oversized_transition_keeps_its_complete_events_outside_hot_state(tmp_path):
    p = sample_project(tmp_path)
    rev = big_commit(p)
    state = load_control(p.root)
    last = state["last_transition"]
    assert len(last["events"]) == outbox.MAX_HOT_EVENTS
    overflow = last["event_overflow"]
    assert overflow["event_count"] == 70 and overflow["counts_by_kind"] == {"work.state": 70}
    sidecar = p.root / ".aew" / overflow["path"]
    assert outbox.sha256_bytes(sidecar.read_bytes()) == overflow["sha256"]
    [t] = log(p, "--since", str(rev - 1))["transitions"]
    assert len(t["events"]) == 70 and t["events"][:64] == last["events"]


def test_damage_to_an_overflow_or_a_record_fails_closed(tmp_path):
    p = sample_project(tmp_path)
    rev = big_commit(p)
    sidecar = p.root / ".aew" / load_control(p.root)["last_transition"]["event_overflow"]["path"]
    original = sidecar.read_bytes()
    sidecar.write_bytes(original.replace(b"T-9000", b"T-9999"))
    assert p.aew("history", "log", "--since", str(rev - 1)).error["code"] == "INTEGRITY_ERROR"
    sidecar.write_bytes(original)
    record = p.root / f".aew/state/log/{rev - 1:06d}.yaml"
    record.write_text(record.read_text(encoding="utf-8").replace("op: ", "op: x", 1), encoding="utf-8")
    assert p.aew("history", "log", "--since", "0").error["code"] == "INTEGRITY_ERROR"


def test_a_project_from_before_the_outbox_starts_its_chain_at_its_next_commit(tmp_path):
    p = sample_project(tmp_path)
    control = p.root / ".aew/state/control.yaml"
    state = load_control(p.root)
    state.pop("outbox")
    state["last_transition"] = {k: v for k, v in state["last_transition"].items()
                                if k not in {"schema", "events", "event_overflow", "h"}}
    control.write_bytes(serialize_control(state))
    old_rev = state["revision"]
    create_planned_ticket(p, tmp_path)
    after = load_control(p.root)
    assert after["outbox"]["since"] == old_rev + 1
    assert log(p, "--since", str(old_rev))["transitions"][0]["revision"] == old_rev + 1
    assert_control_invariants(p)


def test_an_older_engine_refuses_an_outbox_era_control_file(tmp_path):
    """ADR-0012 D10. The baseline engine (42239e1) closes the control file's top level but left `last_transition`
    open, so it is the `outbox` marker that makes it refuse the file: it can never commit over the chain without
    extending it."""
    from jsonschema import Draft202012Validator

    baseline = json.loads((ROOT / "tests/fixtures/baseline/control.schema.42239e1.json").read_text(encoding="utf-8"))
    p = sample_project(tmp_path)
    state = load_control(p.root)
    errors = [e.message for e in Draft202012Validator(baseline).iter_errors(state)]
    assert errors == ["Additional properties are not allowed ('outbox' was unexpected)"]
    assert baseline["properties"]["last_transition"].get("additionalProperties", True) is not False


WAITER = """
import sys, time
from pathlib import Path
from aew.engine import outbox
from aew.engine.store import ControlStore
root, since = Path(sys.argv[1]), int(sys.argv[2])
store = ControlStore(root)
print("ready", flush=True)
got = outbox.wait_for(lambda: store.read()["revision"] > since, root, timeout=20)
print(f"{time.time():.6f} {got}", flush=True)
"""


@pytest.mark.serial
def test_a_commit_wakes_a_waiter_in_another_process_within_50_ms(tmp_path):
    """ADR-0012's wake criterion: commit to wake across two processes, median under 50 ms (against the 0.2 s poll)."""
    p = sample_project(tmp_path)
    aew_root = p.root / ".aew"
    store = ControlStore(aew_root)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]))
    latencies = []
    for _ in range(5):
        since = store.read()["revision"]
        waiter = subprocess.Popen([sys.executable, "-c", WAITER, str(aew_root), str(since)], stdout=subprocess.PIPE,
                                  text=True, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert waiter.stdout is not None
        assert waiter.stdout.readline().strip() == "ready"
        time.sleep(0.3)  # the waiter is blocked on the wake file
        with store.session() as s:
            s.state["counters"]["handoff"] = s.state["counters"].get("handoff", 0)
            s.commit(Transition(op="test.tick", actor={"kind": "test"}))
            committed = time.time()
        woke, ok = waiter.stdout.readline().split()
        waiter.wait(timeout=20)
        assert ok == "True"
        latencies.append(float(woke) - committed)
    assert statistics.median(latencies) < 0.05, latencies


# ---------------------------------------------------------------------------------------------- review of PR #53

def test_a_page_whose_cursor_record_is_missing_fails_instead_of_skipping_the_chain_check(tmp_path):
    """The chain continues from the record the cursor names. Without it, the first record of the page would be
    returned unchecked, and a page that stops before the current revision is never compared with last_transition."""
    p = sample_project(tmp_path)
    for i in range(2):
        create_planned_ticket(p, tmp_path, title=f"Ticket {i}")
    log_dir = p.root / ".aew/state/log"
    (log_dir / "000000.yaml").rename(log_dir / "000000.yaml.kept")
    first = log_dir / "000001.yaml"
    first.write_text(first.read_text(encoding="utf-8").replace("summary: ", "summary: altered ", 1), encoding="utf-8")
    assert p.aew("history", "log", "--since", "0", "--limit", "1").error["code"] == "INTEGRITY_ERROR"
    (log_dir / "000000.yaml.kept").rename(log_dir / "000000.yaml")
    assert p.aew("history", "log", "--since", "0", "--limit", "1").error["code"] == "INTEGRITY_ERROR"  # the altered one


def transfer_events(p, revision: int) -> list[dict]:
    [t] = log(p, "--since", str(revision - 1), "--limit", "1")["transitions"]
    return t["events"]


def test_a_handoff_and_a_takeover_record_their_decision_and_the_credentials_they_revoke(tmp_path):
    """Both commit outside lead_txn, and both archive the ended credentials before committing: the decision each
    records and the revocations must still reach the transition's events."""
    import aew.operator
    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    old_lead = p.token.split(".")[1]
    offer = p.lead("lead", "handoff", "offer")["offer"]
    accepted = p.ok("lead", "handoff", "accept", "--offer", offer, "--expect-rev", str(p.rev()))
    events = transfer_events(p, accepted["revision"])
    assert {"kind": "decision.recorded", "id": accepted["decision"], "type": "authority_transfer"} in events
    revoked = {e["id"] for e in events if e["kind"] == "credential.revoked"}
    assert {old_lead, offer.split(".")[1]} <= revoked
    narrowed = log(p, "--since", "0", "--kind", "decision.recorded")["transitions"]
    assert accepted["revision"] in [t["revision"] for t in narrowed]

    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        taken = Engine.discover(p.root).lead_takeover(expect_rev=p.rev(), reason="review of PR #53",
                                                      session_label="operator")
    finally:
        aew.operator.authorize = original
    events = transfer_events(p, taken["revision"])
    assert {"kind": "decision.recorded", "id": taken["decision"], "type": "authority_transfer"} in events
    assert accepted["token"].split(".")[1] in {e["id"] for e in events if e["kind"] == "credential.revoked"}
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- D1 review (M4-D2)

def test_f2_a_missing_pre_outbox_record_names_where_the_guarantee_begins(tmp_path):
    """Review F2: completeness is guaranteed from outbox.since (ADR-0012 D1). A project from before the outbox that
    lost a pre-outbox record still fails a read from 0 (no gap is skipped), but the error names the cursor from which
    the log is complete, and reading from there works."""
    p = sample_project(tmp_path)
    create_planned_ticket(p, tmp_path)
    control = p.root / ".aew/state/control.yaml"
    state = load_control(p.root)
    state.pop("outbox")
    state["last_transition"] = {k: v for k, v in state["last_transition"].items()
                                if k not in {"schema", "events", "event_overflow", "h"}}
    control.write_bytes(serialize_control(state))
    (p.root / ".aew/state/log/000001.yaml").unlink()
    create_planned_ticket(p, tmp_path, title="the first outbox-era commit")
    start = load_control(p.root)["outbox"]["since"]
    res = p.aew("history", "log", "--since", "0", "--json")
    assert res.error["code"] == "INTEGRITY_ERROR"
    assert f"guaranteed complete from revision {start}" in res.error["message"]
    assert res.error["details"]["resume_since"] == start - 1
    out = log(p, "--since", str(start - 1))
    assert out["transitions"][0]["revision"] == start


def test_f3_a_follower_does_not_take_the_control_lock_on_spurious_wakes(tmp_path):
    """Review F3: `--follow` re-ran the store's locked read (recovery, render) on every wake, and every run-record
    write wakes. It now stats control.yaml on a wake and reads only when the file changed: a burst of spurious wakes
    costs no read, and a commit is still returned."""
    import threading

    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    engine = Engine.discover(p.root)
    store = engine._k.store
    reads = {"n": 0}
    original = store.read

    def counted_read():
        reads["n"] += 1
        return original()

    store.read = counted_read  # type: ignore[method-assign]
    since = load_control(p.root)["revision"]
    stop = threading.Event()

    def spurious_wakes():
        while not stop.is_set():
            outbox.bump_wake(p.root / ".aew")  # what a supervisor's run-record write does
            time.sleep(0.05)

    waker = threading.Thread(target=spurious_wakes, daemon=True)
    waker.start()
    try:
        out = engine.history_log(since=since, follow=True, timeout=1.5)
    finally:
        stop.set()
        waker.join()
    assert out["transitions"] == []
    assert reads["n"] == 1, reads  # the read that found the current revision, none per wake

    def commit_soon():
        time.sleep(0.5)
        create_planned_ticket(p, tmp_path, title="woken")

    committer = threading.Thread(target=commit_soon)
    committer.start()
    out = engine.history_log(since=since, follow=True, timeout=30)
    committer.join()
    assert out["transitions"] and out["transitions"][0]["revision"] == since + 1
