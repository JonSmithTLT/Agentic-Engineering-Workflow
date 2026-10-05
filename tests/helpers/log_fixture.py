"""Long transition logs without thousands of commits (ADR-0012 D6 tests and the git-cost measurement).

``extend_log`` appends synthetic logical transitions to an existing control state: each record is shaped like a real
one (a transaction reference with one write, a typed event, and every ``overflow_every``-th one an overflow of 70
events with its sidecar), chained from the committed head, and the control state is rewritten at the new revision with
the newest record as its ``last_transition``. Files are written directly, without fsync: a fixture, not a commit. The
result is a valid store: it reads, recovers, commits on top, and every oracle rule holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine import outbox
from aew.engine.store import CONTROL_REL, deserialize_control, serialize_control
from aew.util import dump_yaml, sha256_bytes


def synthetic_record(revision: int, *, overflow: bool, last: bool) -> tuple[dict[str, Any], str | None]:
    """A record for ``revision`` (without ``h``) and its overflow payload text, if any."""
    if overflow:
        full = [{"kind": "decision.recorded", "id": f"D-{revision:06d}-{i:02d}", "type": "model"} for i in range(70)]
        events, descriptor, text = outbox.bound(revision, full)
    else:
        events = [{"kind": "work.state", "id": f"T-{revision % 9973:04d}", "unit": "ticket", "from": "READY",
                   "to": "RUNNING"}]
        descriptor, text = None, None
    digest = sha256_bytes(f"synthetic {revision}".encode())
    txn = None if last else {  # the newest record names no redo record: recovery has nothing to roll forward
        "path": f"state/txn/{revision:06d}.yaml", "sha256": digest,
        "writes": [{"path": f"work/T-{revision % 9973:04d}/ticket.md", "before": digest, "after": digest}]}
    record = {"schema": outbox.TRANSITION_SCHEMA, "revision": revision, "at": "2026-10-04T00:00:00Z",
              "actor": {"kind": "lead", "session_label": "fixture", "generation": 1}, "op": "work.transition",
              "summary": f"synthetic transition {revision}", "reason": None, "refs": [], "txn": txn, "events": events,
              "event_overflow": descriptor}
    return record, text


def extend_log(aew_root: Path, to_revision: int, *, overflow_every: int = 0) -> dict[str, Any]:
    """Append synthetic transitions up to ``to_revision`` and commit the control state there. Returns the state."""
    control = aew_root / CONTROL_REL
    state = deserialize_control(control.read_bytes(), source=str(control))
    assert state.get("outbox"), "extend_log needs an outbox-era control state"
    prev_h = state["last_transition"]["h"]
    log_dir = aew_root / outbox.LOG_DIR
    record: dict[str, Any] | None = None
    for revision in range(state["revision"] + 1, to_revision + 1):
        record, text = synthetic_record(revision, overflow=bool(overflow_every) and revision % overflow_every == 0,
                                        last=revision == to_revision)
        outbox.seal(record, prev_h)
        prev_h = record["h"]
        (log_dir / f"{revision:06d}.yaml").write_bytes(dump_yaml(record).encode("utf-8"))
        if text is not None:
            (aew_root / record["event_overflow"]["path"]).write_bytes(text.encode("utf-8"))
    if record is not None:
        state["revision"] = to_revision
        state["last_transition"] = record
        if "counters" in state and "n" in state["counters"]:
            state["counters"]["n"] = to_revision  # the store model's counter follows its revision
        control.write_bytes(serialize_control(state))
    return state
