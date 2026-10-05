"""Regressions for the independent review of M4-D slice D1 (ADR-0012), on the store model."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from store_model import init, make_store  # noqa: E402

from aew.engine.store import Transition  # noqa: E402
from aew.errors import ValidationFailed  # noqa: E402


def declared(n: int, bad_at: int) -> list[dict]:
    events = [{"kind": "handoff.recorded", "id": f"H-{i:04d}"} for i in range(n)]
    events[bad_at] = {"kind": "made.up", "id": "X"}
    return events


@pytest.mark.parametrize("bad_at", [0, 69])
def test_f1_a_malformed_event_fails_the_commit_wherever_it_falls_in_an_overflowing_list(tmp_path, bad_at):
    """Review F1: the hot list was validated with control.yaml, the overflow payload never, so the same malformed
    event was refused at position 1 and committed at position 70. Now both fail closed, leaving no trace."""
    store = init(tmp_path)
    with pytest.raises(ValidationFailed), store.session() as s:
        s.state["counters"]["n"] = 1
        s.commit(Transition(op="test.declared", actor={"kind": "test"}, events=declared(70, bad_at)))
    assert make_store(tmp_path).read()["revision"] == 0
    assert not list((tmp_path / "state/log").glob("*.events.yaml"))
    assert not list((tmp_path / "state").glob("txn/*.yaml"))
