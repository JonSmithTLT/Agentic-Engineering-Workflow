"""ADR-0012 D6 (M4-D slice D2): sealing the transition log into segments, and the lockless reader that resolves either
representation (D3), on a store model with a synthesized long log. The window is small here (``compact(window=...)``)
so that segments of the real size (256) appear without thousands of revisions; the CLI always uses 4,096."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from log_fixture import extend_log  # noqa: E402
from store_model import (  # noqa: E402
    check_invariants,
    init,
    make_store,
    one_transaction,
    outbox_violations,
    reader_race_violations,
    segment_violations,
)

from aew.engine import log_compact, outbox  # noqa: E402
from aew.engine.faults import InjectedFault  # noqa: E402
from aew.errors import IntegrityError  # noqa: E402
from aew.util import dump_yaml, load_yaml  # noqa: E402

WINDOW = 8
SEG = outbox.SEGMENT_SIZE


def long_log(root: Path, revisions: int = 2 * SEG + 40, *, overflow_every: int = 37) -> dict:
    init(root)
    return extend_log(root, revisions, overflow_every=overflow_every)


def everything(root: Path, state: dict) -> list[dict]:
    return list(outbox.read_transitions(root, 0, state["revision"], outbox=state["outbox"]))


def names(root: Path) -> set[str]:
    return {p.name for p in (root / "state/log").iterdir()}


# ---------------------------------------------------------------------------------------------- write, verify, prune

def test_compaction_seals_whole_segments_behind_the_window_and_every_transition_reads_the_same(tmp_path):
    state = long_log(tmp_path)
    before = everything(tmp_path, state)
    result = log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert result["sealed"] == [0, 1] and result["pruned"] == 2 * SEG and result["pending"] == []
    assert result["unsealed"] == state["revision"] + 1 - 2 * SEG
    files = names(tmp_path)
    assert {"seg-000000.yaml", "seg-000001.yaml"} <= files and "seg-000002.yaml" not in files
    assert not any(f"{r:06d}.yaml" in files or f"{r:06d}.events.yaml" in files for r in range(2 * SEG))
    assert f"{2 * SEG:06d}.yaml" in files  # the window and the partial segment before it stay unsealed
    assert everything(tmp_path, state) == before  # overflow events too: complete, from the sealed payload
    overflowing = [t for t in before if t["revision"] < 2 * SEG and t.get("event_overflow")]
    assert overflowing and all(len(t["events"]) == 70 for t in overflowing)
    assert outbox_violations(tmp_path, state) == []
    # idempotent: nothing left to do
    again = log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert again["sealed"] == [] and again["resumed"] == [] and names(tmp_path) == files


def test_a_segment_holds_the_records_exactly_and_the_overflow_payload_bytes(tmp_path):
    state = long_log(tmp_path)
    records = {r: (tmp_path / outbox.record_path(r)).read_bytes() for r in range(SEG)}
    payloads = {r: (tmp_path / outbox.overflow_path(r)).read_bytes() for r in range(SEG) if r and r % 37 == 0}
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    segment = outbox.load_segment(tmp_path, 0, state["outbox"]["since"], schema=True)
    assert segment is not None and segment.first == 0 and len(segment.records) == SEG
    assert all(segment.record(r) == load_yaml(raw.decode()) for r, raw in records.items())
    assert {r: t.encode() for r, t in segment.payloads.items()} == payloads
    assert segment.head_h == segment.record(SEG - 1)["h"] and segment.prev_h is None
    second = outbox.load_segment(tmp_path, 1, state["outbox"]["since"])
    assert second is not None and second.prev_h == segment.head_h  # the chain continues, never re-minted


def test_the_commit_path_never_seals(tmp_path):
    long_log(tmp_path)
    store = make_store(tmp_path)
    one_transaction(store)
    assert not any(n.startswith("seg-") for n in names(tmp_path))


def test_sealing_refuses_a_segment_with_a_missing_record_and_writes_nothing(tmp_path):
    long_log(tmp_path)
    (tmp_path / outbox.record_path(17)).unlink()
    with pytest.raises(IntegrityError, match="incomplete history"):
        log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert not (tmp_path / outbox.segment_path(0)).exists()
    assert (tmp_path / outbox.record_path(16)).exists()


def test_sealing_refuses_a_broken_chain(tmp_path):
    long_log(tmp_path)
    path = tmp_path / outbox.record_path(30)
    path.write_bytes(path.read_bytes().replace(b"synthetic transition 30", b"synthetic transition 3O"))
    with pytest.raises(IntegrityError, match="chain is broken"):
        log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert not (tmp_path / outbox.segment_path(0)).exists()


def test_a_leftover_unsealed_copy_that_disagrees_stops_pruning(tmp_path):
    """Pruning resumes only over equivalent copies: a leftover that differs from its sealed copy is corruption."""
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    leftover = dict(outbox.read_record(tmp_path, 5), summary="not what was sealed")
    (tmp_path / outbox.record_path(5)).write_bytes(dump_yaml(leftover).encode())
    with pytest.raises(IntegrityError, match="disagree"):
        log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert (tmp_path / outbox.record_path(5)).exists()
    assert any("27: segment 0" in p for p in segment_violations(tmp_path, state))


def test_a_stray_sidecar_beside_a_segment_stops_pruning(tmp_path):
    long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    (tmp_path / outbox.overflow_path(5)).write_bytes(b"schema: aew/transition-events/v1\n")
    with pytest.raises(IntegrityError, match="disagree"):
        log_compact.compact(make_store(tmp_path), window=WINDOW)


def test_the_window_bounds(tmp_path):
    assert log_compact.eligible_segments(4095 + 255) == 0
    assert log_compact.eligible_segments(4096 + 255) == 1
    assert log_compact.eligible_segments(60_000) == (60_000 - 4096 + 1) // 256
    with pytest.raises(Exception, match="at least the newest"):
        log_compact.compact(init(tmp_path), window=0)


# ---------------------------------------------------------------------------------------------- the reader (D3)

def test_resolution_order_unsealed_then_sealed_with_equivalence_when_both_exist(tmp_path):
    state = long_log(tmp_path)
    since = state["outbox"]["since"]
    unsealed = outbox.read_record(tmp_path, 9, since=since)
    assert unsealed is not None and not (tmp_path / outbox.segment_path(0)).exists()  # only unsealed
    # both, equivalent (a crash after the segment was published): either resolves, the same
    for _ in log_compact.seal_steps(tmp_path, 0, since):
        break
    assert (tmp_path / outbox.segment_path(0)).exists() and (tmp_path / outbox.record_path(9)).exists()
    assert outbox.read_record(tmp_path, 9, since=since) == unsealed
    # only sealed
    for _ in log_compact.seal_steps(tmp_path, 0, since):
        pass
    assert not (tmp_path / outbox.record_path(9)).exists()
    assert outbox.read_record(tmp_path, 9, since=since) == unsealed


def test_a_view_refreshes_a_segment_it_saw_absent(tmp_path):
    """The refresh of D3 step 2: a reader that looked for segment 0 before it existed still finds a revision whose
    unsealed file sealing has since removed."""
    state = long_log(tmp_path)
    view = outbox.LogView(tmp_path, state["outbox"]["since"], retries=0)
    first = view.record(3)  # the view now knows segment 0 as absent
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert view.record(3) == first and view.record(4)["revision"] == 4
    assert len(view.events(view.record(37))) == 70  # an overflow, its sidecar gone: the sealed payload


def test_disagreeing_copies_fail_closed(tmp_path):
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    other = dict(outbox.read_record(tmp_path, 12), summary="altered")
    (tmp_path / outbox.record_path(12)).write_bytes(dump_yaml(other).encode())
    with pytest.raises(IntegrityError, match="disagree"):
        everything(tmp_path, state)


def test_a_revision_in_neither_representation_is_incomplete_history_not_a_gap(tmp_path):
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    (tmp_path / outbox.record_path(2 * SEG + 3)).unlink()  # in the unsealed part: no segment holds it
    with pytest.raises(IntegrityError, match="incomplete history"):
        list(outbox.read_transitions(tmp_path, 2 * SEG, state["revision"], outbox=state["outbox"], retries=1))
    # and a missing segment while its files are gone
    (tmp_path / outbox.segment_path(1)).rename(tmp_path / "kept.yaml")
    with pytest.raises(IntegrityError, match="incomplete history"):
        list(outbox.read_transitions(tmp_path, SEG + 3, SEG + 5, outbox=state["outbox"], retries=0))


def rewrite_segment(root: Path, index: int, change) -> None:
    path = root / outbox.segment_path(index)
    doc = load_yaml(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_bytes(dump_yaml(doc).encode())


def test_a_chain_broken_across_a_segment_boundary_fails_closed(tmp_path):
    """Segment 1 re-chained from a different head is internally consistent, but does not continue segment 0."""
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)

    def rechain(doc):
        doc["prev_h"] = h = "f" * 64
        for record in doc["transitions"]:
            h = outbox.seal(record, h)["h"]
        doc["head_h"] = h

    rewrite_segment(tmp_path, 1, rechain)
    assert outbox.load_segment(tmp_path, 1, 0) is not None  # self-consistent
    with pytest.raises(IntegrityError, match="chain is broken"):
        list(outbox.read_transitions(tmp_path, SEG - 3, SEG + 3, outbox=state["outbox"]))
    assert any("does not continue the chain" in p for p in segment_violations(tmp_path, state))


def test_a_tampered_overflow_payload_inside_a_segment_fails_closed(tmp_path):
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    rewrite_segment(tmp_path, 0, lambda doc: doc["overflow"].update(
        {"37": doc["overflow"]["37"].replace("D-000037-00", "D-000037-99")}))
    with pytest.raises(IntegrityError, match="digest"):
        list(outbox.read_transitions(tmp_path, 36, 37, outbox=state["outbox"]))
    assert any("27: segment 0" in p for p in segment_violations(tmp_path, state))


def test_a_tampered_record_inside_a_segment_fails_closed(tmp_path):
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    rewrite_segment(tmp_path, 0, lambda doc: doc["transitions"][40].update(summary="rewritten history"))
    with pytest.raises(IntegrityError, match="chain is broken"):
        list(outbox.read_transitions(tmp_path, 0, 1, outbox=state["outbox"]))


def test_a_segment_that_is_not_a_segment_fails_closed(tmp_path):
    state = long_log(tmp_path)
    log_compact.compact(make_store(tmp_path), window=WINDOW)
    rewrite_segment(tmp_path, 0, lambda doc: doc["transitions"].pop())
    with pytest.raises(IntegrityError, match="not a valid sealed segment"):
        list(outbox.read_transitions(tmp_path, 0, 1, outbox=state["outbox"]))
    (tmp_path / outbox.segment_path(0)).write_bytes(b"\x00: [")
    with pytest.raises(IntegrityError, match="not a readable sealed segment"):
        list(outbox.read_transitions(tmp_path, 0, 1, outbox=state["outbox"]))


# ---------------------------------------------------------------------------------------------- fault points (D9)

@pytest.mark.parametrize("point", ["log.seal.after_segment", "log.seal.mid_prune"])
def test_a_crash_at_each_sealing_point_leaves_a_readable_log_and_a_rerun_completes(tmp_path, monkeypatch, point):
    state = long_log(tmp_path)
    before = everything(tmp_path, state)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    monkeypatch.setenv("AEW_FAULT", point)
    with pytest.raises(InjectedFault):
        log_compact.compact(make_store(tmp_path), window=WINDOW)
    monkeypatch.delenv("AEW_FAULT")
    files = names(tmp_path)
    assert "seg-000000.yaml" in files  # durable before any file was removed
    present = [r for r in range(SEG) if f"{r:06d}.yaml" in files]
    assert present == (list(range(SEG)) if point == "log.seal.after_segment" else list(range(SEG // 2, SEG)))
    assert everything(tmp_path, state) == before
    assert outbox_violations(tmp_path, state) == []
    result = log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert result["resumed"] == [0] and result["sealed"] == [1]
    assert everything(tmp_path, state) == before and outbox_violations(tmp_path, state) == []


# ---------------------------------------------------------------------------------------------- rule 28

@pytest.mark.parametrize("seed", [1, 2, 3])
def test_rule_28_a_lockless_reader_never_sees_a_false_gap_under_modelled_interleavings(tmp_path, seed):
    state = long_log(tmp_path, 2 * SEG + 20, overflow_every=13)
    assert reader_race_violations(tmp_path, state, rng=random.Random(seed), window=WINDOW) == []
    assert log_compact.scan(tmp_path).segments == {0, 1}
    assert outbox_violations(tmp_path, state) == []


def test_rule_28_has_teeth_a_reader_that_does_not_refresh_its_sealed_view_is_caught(tmp_path, monkeypatch):
    """Without D3's refresh (a segment once seen absent is never looked up again), the model finds a false gap."""
    original = outbox.LogView.segment
    monkeypatch.setattr(outbox.LogView, "segment", lambda self, index, refresh=False: original(self, index))
    found: list[str] = []
    for seed in range(1, 9):
        root = tmp_path / str(seed)
        state = long_log(root, 2 * SEG + 20, overflow_every=13)
        found += reader_race_violations(root, state, rng=random.Random(seed), window=WINDOW)
        if found:
            break
    assert any("incomplete history" in p or "missing" in p for p in found), found


def test_rule_28_has_teeth_pruning_before_the_segment_is_durable_is_caught(tmp_path, monkeypatch):
    """The order is the guarantee: a compactor that removed the per-revision files before its segment was durable
    and crashed in between would leave neither representation, which the oracle reports as incomplete history."""
    state = long_log(tmp_path, 2 * SEG + 20)

    def prune_then_crash(path, text):
        for r in range(SEG):
            (tmp_path / outbox.record_path(r)).unlink(missing_ok=True)
        raise InjectedFault("between pruning and publishing")

    monkeypatch.setattr(log_compact, "create_exclusive", prune_then_crash)
    with pytest.raises(InjectedFault):
        log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert any("incomplete history" in p for p in outbox_violations(tmp_path, state))


# ---------------------------------------------------------------------------------------------- seeded walk

@pytest.mark.exploratory
def test_seeded_walk_commits_compactions_crashes_and_racing_readers(tmp_path, monkeypatch):
    """Merge gate: seed 20261004, 40 steps; the nightly job rotates AEW_SEAL_SEED and raises AEW_SEAL_STEPS. Each step
    commits (possibly crashing at a commit point), compacts (possibly crashing at a sealing point, with a window that
    varies), or races a modelled lockless reader against a compaction; the store invariants and rules 24 to 28 hold
    after every step."""
    import os

    rng = random.Random(int(os.environ.get("AEW_SEAL_SEED", "20261004")))
    base = 2 * SEG - 12  # the walk's own commits (some crashed after the commit point and repaired) fill segment 1
    long_log(tmp_path, base, overflow_every=11)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    commit_points = ["txn.after_replace", "log.overflow_unpublished", "txn.after_log", None, None]
    seal_points = ["log.seal.after_segment", "log.seal.mid_prune", None]
    for _ in range(int(os.environ.get("AEW_SEAL_STEPS", "40"))):
        action = rng.choice(["commit", "commit", "compact", "race"])
        window = rng.choice([1, 8, 64])
        point = rng.choice(commit_points if action == "commit" else seal_points)
        if point and action != "race":
            monkeypatch.setenv("AEW_FAULT", point)
        try:
            if action == "commit":
                one_transaction(make_store(tmp_path))
            elif action == "compact":
                log_compact.compact(make_store(tmp_path), window=window)
            else:
                state = make_store(tmp_path).read()
                assert reader_race_violations(tmp_path, state, rng=rng, window=window, readers=1) == []
        except InjectedFault:
            pass
        monkeypatch.delenv("AEW_FAULT", raising=False)
        check_invariants(tmp_path, synthetic_through=base)


# ---------------------------------------------------------------------------------------------- review of PR #60

def pre_outbox_log(root: Path, *, pre: int = 300, to: int = 3 * SEG + 20) -> dict:
    """A log whose first ``pre + 1`` revisions are from before the outbox: the chain starts at ``pre + 1``."""
    from log_fixture import strip_outbox

    init(root)
    extend_log(root, pre)
    strip_outbox(root)
    one_transaction(make_store(root))  # the first outbox-era commit
    return extend_log(root, to, overflow_every=37)


def test_item1_a_missing_pre_outbox_record_skips_its_segment_and_compaction_goes_on(tmp_path):
    """A record from before the outbox was never protected (ADR-0012 D1): its loss makes only its own segment
    unsealable. Later segments still seal, the reader still reads from the guarantee's start, and the window counts
    from the newest sealed segment."""
    state = pre_outbox_log(tmp_path)
    since = state["outbox"]["since"]
    assert since == 301
    (tmp_path / outbox.record_path(17)).unlink()
    result = log_compact.compact(make_store(tmp_path), window=WINDOW)
    assert result["sealed"] == [1, 2]
    assert [(u["segment"], u["revision"]) for u in result["unsealable"]] == [(0, 17)]
    assert "before the outbox began" in result["unsealable"][0]["reason"]
    assert result["segments"] == 2 and result["unsealed"] == state["revision"] + 1 - 3 * SEG
    assert (tmp_path / outbox.record_path(18)).exists()  # segment 0 stays unsealed
    # across the sealed boundary from the guarantee's start; segment 1 holds both pre- and outbox-era records
    records = list(outbox.read_transitions(tmp_path, since - 1, state["revision"], outbox=state["outbox"]))
    assert [r["revision"] for r in records] == list(range(since, state["revision"] + 1))
    assert outbox_violations(tmp_path, state) == []
    assert log_compact.window_status(tmp_path, state["revision"])[0] == "PASS"
    again = log_compact.compact(make_store(tmp_path), window=WINDOW)  # reported again, never fatal
    assert again["sealed"] == [] and [u["segment"] for u in again["unsealable"]] == [0]


def test_item1_a_missing_outbox_era_record_still_stops_compaction(tmp_path):
    state = pre_outbox_log(tmp_path)
    (tmp_path / outbox.record_path(state["outbox"]["since"] + 5)).unlink()  # in segment 1, after the chain began
    with pytest.raises(IntegrityError, match="incomplete history"):
        log_compact.compact(make_store(tmp_path), window=WINDOW)


@pytest.mark.parametrize("point", ["txn.after_replace", "txn.after_apply"])
def test_item5_a_repaired_record_is_sealed_and_read_back_through_its_segment(tmp_path, monkeypatch, point):
    """PR #60 review item 5 (OBX-40, "repaired logs"): a commit that dies after its commit point but before its log
    record is written leaves the record missing; recovery repairs it from last_transition; it is then sealed like
    any other record, and read back through the segment it is exactly the committed transition."""
    from aew.engine.store import CONTROL_REL, deserialize_control

    long_log(tmp_path, SEG - 5)
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    monkeypatch.setenv("AEW_FAULT", point)
    with pytest.raises(InjectedFault):
        one_transaction(make_store(tmp_path))
    monkeypatch.delenv("AEW_FAULT")
    lost = SEG - 4
    assert not (tmp_path / outbox.record_path(lost)).exists()  # committed, its record never written
    raw = (tmp_path / CONTROL_REL).read_bytes()
    committed = deserialize_control(raw, source=CONTROL_REL)["last_transition"]
    assert committed["revision"] == lost and committed["event_overflow"] is not None  # an overflow, too
    store = make_store(tmp_path)
    store.read()  # recovery repairs the record (and publishes the staged overflow payload)
    assert outbox._read_record(tmp_path, lost) == committed
    while store.read()["revision"] < SEG + 2:
        one_transaction(store)
    result = log_compact.compact(make_store(tmp_path), window=1)
    assert result["sealed"] == [0]
    assert not (tmp_path / outbox.record_path(lost)).exists()
    assert not (tmp_path / outbox.overflow_path(lost)).exists()
    segment = outbox.load_segment(tmp_path, 0, 0, schema=True)
    assert segment is not None and segment.record(lost) == committed
    state = make_store(tmp_path).read()
    [read_back] = outbox.read_transitions(tmp_path, lost - 1, lost, outbox=state["outbox"])
    assert {k: v for k, v in read_back.items() if k != "events"} == {k: v for k, v in committed.items()
                                                                      if k != "events"}
    assert len(read_back["events"]) == 70  # the complete set, from the sealed payload
    check_invariants(tmp_path, synthetic_through=SEG - 5)
