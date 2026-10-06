"""A tiny deterministic workload over ControlStore, shared by in-process and subprocess tests.

Each transaction k (1-based) bumps ``counters.n`` to k, creates the immutable
record ``records/item-<k>.md`` and replaces the mutable ``manifest.txt``. It also
declares transition events (ADR-0012): one, or 70 on every even k, so that the
complete set overflows the hot bound and is staged as a sidecar; every crash point
then also covers an overflow transition. The renderer derives ``state/CURRENT.md``.
``check_invariants`` asserts that the observable files agree exactly with the
committed revision (no hybrid states), and the outbox oracle rules 24 to 27;
``reader_race_violations`` is rule 28, over modelled sealing/crash interleavings.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aew import SPEC_SET
from aew.engine import log_compact, outbox
from aew.engine.store import ControlStore, Transition
from aew.errors import AEWError
from aew.util import sha256_bytes


def initial_state() -> dict[str, Any]:
    return {
        "schema": "aew/control/v1",
        "project_id": "store-test",
        "spec_set": SPEC_SET,
        "revision": 0,
        "manifest_sha256": "0" * 64,
        "lead": {
            "schema": "aew/lead/v1",
            "status": "vacant",
            "generation": 0,
            "session_label": None,
            "token_id": None,
            "acquired_at": None,
            "handoff": None,
        },
        "tokens": {},
        "counters": {"n": 0},
        "work": {},
        "invocations": {},
        "last_transition": {
            "revision": 0, "at": "t", "actor": {"kind": "init"}, "op": "init",
            "summary": None, "reason": None, "refs": [], "txn": None,
        },
    }


def render(state: dict[str, Any]) -> dict[str, str]:
    return {"state/CURRENT.md": f"revision {state['revision']} n {state['counters']['n']}\n"}


def make_store(root: Path) -> ControlStore:
    return ControlStore(root, renderer=render, lock_timeout=120)


def item_content(k: int) -> str:
    return f"item {k}\n" + ("payload line\n" * 20)


def declared(k: int) -> list[dict[str, Any]]:
    return [{"kind": "decision.recorded", "id": f"D-{k:04d}-{i:02d}", "type": "model"}
            for i in range(70 if k % 2 == 0 else 1)]


def one_transaction(store: ControlStore, *, expect_rev: int | None = None) -> int:
    with store.session() as s:
        k = s.state["counters"]["n"] + 1
        s.state["counters"]["n"] = k
        s.write(f"records/item-{k}.md", item_content(k))
        s.write("manifest.txt", f"n={k}\n", immutable=False)
        return s.commit(Transition(op="bump", actor={"kind": "test"}, events=declared(k)), expect_rev=expect_rev)


def check_invariants(root: Path, *, synthetic_through: int = 0, window: int | None = None) -> int:
    """``synthetic_through``: revisions up to it were appended by ``log_fixture.extend_log``, not by this workload, so
    they have no item record and carry their own events.

    ``window``: check only the newest ``window`` revisions' records and transitions (and the chain link into them);
    every whole-store rule (the counters, leftovers, the views, segment fidelity) still holds in full. One transaction,
    crashed anywhere, can only touch its own revision: a caller that ran the full check before it can check the window
    after it, and the full check again now and then, which proves nothing older changed. Without it the check reads the
    whole history, so a long randomized run is quadratic (the nightly crash job timed out from PR #53 on)."""
    store = make_store(root)
    state = store.read()
    n = state["counters"]["n"]
    assert state["revision"] == n, (state["revision"], n)
    view = outbox.LogView(root, state["outbox"]["since"], retries=0)
    first = 1 if window is None else max(1, n - window + 1)
    for k in range(first, n + 1):
        if k > synthetic_through:
            assert (root / f"records/item-{k}.md").read_text() == item_content(k), k
        assert view.resolve(k) is not None, f"log {k} missing, unsealed and sealed"
    assert not (root / f"records/item-{n + 1}.md").exists(), "uncommitted write leaked"
    manifest = root / "manifest.txt"
    if n > synthetic_through:
        assert manifest.read_text() == f"n={n}\n"
    elif not synthetic_through:
        assert not manifest.exists()
    assert (root / "state/CURRENT.md").read_text() == render(state)["state/CURRENT.md"]
    txn_dir = root / "state/txn"
    if txn_dir.exists():
        assert all(int(f.stem) <= n for f in txn_dir.glob("*.yaml")), "uncommitted redo record left"
    leftovers = [p for p in root.rglob(".*.tmp")]
    assert not leftovers, leftovers
    if n:
        assert outbox_violations(root, state, expected=declared, synthetic_through=synthetic_through,
                                 from_revision=first - 1) == []
    return n


def outbox_violations(root: Path, state: dict[str, Any], *, expected=None, synthetic_through: int = 0,
                      from_revision: int = 0) -> list[str]:
    """ADR-0012's oracle rules over a store's transition log. 24: exactly one logical transition per revision from
    the outbox's start, chained, the newest equal to ``last_transition``, whichever physical representation holds it
    (equivalent where both do). 25 (when ``expected`` gives each revision's events): the complete events are exactly
    those. 26: the hot list is bounded, and an overflow's payload holds the complete set its descriptor names. 27:
    every sealed segment's fidelity (``segment_violations``). ``from_revision``: the transitions after it only, the
    chain checked from its record (``check_invariants``' window)."""
    problems: list[str] = []
    start = state["outbox"]["since"]
    last = None
    view = outbox.LogView(root, start, retries=0)
    try:
        for record in outbox.read_transitions(root, max(start - 1 if start else 0, from_revision), state["revision"],
                                              outbox=state["outbox"]):
            last = record
            hot = state["last_transition"] if record["revision"] == state["revision"] else None
            raw = view.resolve(record["revision"]) or {}
            if len(raw.get("events") or []) > outbox.MAX_HOT_EVENTS:
                problems.append(f"26: revision {record['revision']} holds {len(raw['events'])} hot events")
            if (raw.get("event_overflow") is None) != (len(record["events"] or []) <= outbox.MAX_HOT_EVENTS):
                problems.append(f"26: revision {record['revision']}'s overflow does not match its event count")
            fidelity = expected is not None and record["revision"] >= max(start, 1, synthetic_through + 1)
            if fidelity and record["events"] != expected(record["revision"]):
                problems.append(f"25: revision {record['revision']}'s events are not the transaction's")
            if hot is not None and raw != hot:
                problems.append("24: the newest record differs from last_transition")
    except Exception as exc:  # noqa: BLE001 (the oracle reports, it does not crash)
        problems.append(f"24: {exc}")
    if last is None or last["revision"] != state["revision"]:
        problems.append("24: the log does not reach the current revision")
    return problems + segment_violations(root, state)


def segment_violations(root: Path, state: dict[str, Any]) -> list[str]:
    """27. Segment fidelity: segments are contiguous from segment 0 except where a segment from before the outbox
    could not be sealed (a pre-outbox record is missing or invalid: ``log_compact.Unsealable``), each holds exactly 256
    logical transitions that pass its schemas, every overflow payload is preserved and digest-verified, and the chain
    continues unchanged across every segment boundary. 24 (the coexistence half): an unsealed copy still present beside
    its segment is equivalent to the sealed one."""
    problems: list[str] = []
    since = state["outbox"]["since"]
    listing = log_compact.scan(root)
    for gap in sorted(set(range(max(listing.segments, default=-1))) - listing.segments):
        span = range(gap * outbox.SEGMENT_SIZE, (gap + 1) * outbox.SEGMENT_SIZE)
        if not any(r < since and r not in listing.records for r in span) and not all(r < since for r in span):
            problems.append(f"27: segment {gap} is missing below a sealed one, and nothing makes it unsealable")
    view = outbox.LogView(root, since, retries=0)
    for index in sorted(listing.segments):
        try:
            segment = _verified_segment(root, index, since)
            if segment.prev_h is not None and (view.resolve(segment.first - 1) or {}).get("h") != segment.prev_h:
                problems.append(f"27: segment {index} does not continue the chain from revision {segment.first - 1}")
            log_compact.verify_against_unsealed(root, segment, since)
        except AEWError as exc:
            problems.append(f"27: segment {index}: {exc}")
    return problems


_VERIFIED: dict[tuple[str, int | None, str], outbox.Segment] = {}  # (path, since, file sha256) -> fully verified


def _verified_segment(root: Path, index: int, since: int | None) -> outbox.Segment:
    """A segment checked with its full schemas once per content (segments are immutable; the schemas cost a second or
    more per segment, and the oracle runs after every step of a walk)."""
    path = root / outbox.segment_path(index)
    key = (str(path.resolve()), since, sha256_bytes(path.read_bytes()))
    if key not in _VERIFIED:
        segment = outbox.load_segment(root, index, since, schema=True)
        assert segment is not None
        _VERIFIED[key] = segment
    return _VERIFIED[key]


# ---------------------------------------------------------------------------------------------- rule 28

def compaction_steps(root: Path, since: int, revision: int, window: int,
                     rng: random.Random | None = None) -> Iterator[dict[str, Any]]:
    """One compaction run as a sequence of durable steps (``log_compact.seal_steps`` per eligible segment, without the
    control lock: the model interleaves in one process). With ``rng`` it may crash, i.e. stop for good, after any
    step."""
    for index in range(log_compact.eligible_segments(revision, window)):
        listing = log_compact.scan(root)
        if index in listing.segments and not listing.leftovers(index):
            continue
        for step in log_compact.seal_steps(root, index, since):
            yield step
            if rng is not None and rng.random() < 0.01:
                return


def reader_race_violations(root: Path, state: dict[str, Any], *, rng: random.Random, window: int,
                           readers: int = 3) -> list[str]:
    """28. Reader race safety over modelled interleavings: lockless readers walk the log from random cursors while
    compaction runs (and crashes, and is run again) between ANY two of their file accesses, as ``rng`` chooses. The
    readers never retry here, so no sleep papers over a missing representation: every revision must resolve to exactly
    the logical transition (record and complete events) it was before sealing, or the reader must fail with an
    explicit error, which counts as a violation too since nothing here is corrupt. Afterwards the log is sealed as far
    as ``window`` allows."""
    since, revision = state["outbox"]["since"], state["revision"]
    truth = {r["revision"]: r for r in outbox.read_transitions(root, since - 1 if since else 0, revision,
                                                               outbox=state["outbox"])}
    problems: list[str] = []
    compactor: Iterator[dict[str, Any]] | None = None
    busy = False
    original = outbox.read_optional

    def step_compactor() -> None:
        nonlocal compactor, busy
        if busy:  # the compactor's own reads do not interleave with themselves
            return
        busy = True
        try:
            for _ in range(rng.choice((0, 0, 1, 1, 2, 5))):
                if compactor is None:
                    compactor = compaction_steps(root, since, revision, window, rng)
                if next(compactor, None) is None:
                    compactor = None  # finished, or crashed: a later run resumes
        finally:
            busy = False

    def interleaved(path: Path) -> bytes | None:
        step_compactor()
        return original(path)

    outbox.read_optional = interleaved
    try:
        for _ in range(readers):
            cursor = rng.randrange(max(since, 0), revision)
            try:
                for record in outbox.read_transitions(root, cursor, revision, outbox=state["outbox"], retries=0):
                    if record != truth[record["revision"]]:
                        problems.append(f"28: revision {record['revision']} read differently while sealing")
            except AEWError as exc:
                problems.append(f"28: a lockless reader from revision {cursor} failed while sealing: {exc}")
    finally:
        outbox.read_optional = original
    for _ in compaction_steps(root, since, revision, window):  # finish what a crash left
        pass
    return problems


def init(root: Path) -> ControlStore:
    store = make_store(root)
    store.create(initial_state(), {})
    return store
