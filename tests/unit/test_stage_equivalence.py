"""The stage/primitive comparison itself (tests/helpers/stage_equivalence.py): what it normalises still compares."""

from __future__ import annotations

from typing import Any

from stage_equivalence import _clean, _Normaliser, differences, history_record


def _run(start: float | None, pid: int = 7) -> dict[str, Any]:
    return {"id": "IV-0001-1", "state": "committed", "executor": {"host_pid": pid, "start_time": start, "host": "h"}}


def _state(start: float | None, pid: int = 7) -> dict[str, Any]:
    run = _run(start, pid)
    return {"work": {"T-0001": {"integration": {"current_validation_run": run, "diagnostic_run": run},
                                "integration_history": [{"current_validation_run": run}]}}}


def test_a_validation_executors_start_time_compares_as_a_time_wherever_its_record_is_kept():
    """A validation run's executor records its process's start time, which Linux derives from the wall clock's boot
    time: a clock step between the twins' runs in one process moves it (WSL2 was measured stepping it by 3 s about
    every 35 s: the flake of `test_stage_matches_primitives[integration_publish-done]`). It compares as a time on the
    hot record, in the integration history and on the archived unit; a null still differs from a time, and the
    executor's other fields still compare."""
    a, b = _clean(_state(1792806723.99), "/p"), _clean(_state(1792806726.99), "/p")
    assert differences(a, b) == []
    assert a["work"]["T-0001"]["integration"]["current_validation_run"]["executor"]["start_time"] == "<time>"
    assert differences(a, _clean(_state(None), "/p"))
    assert differences(a, _clean(_state(1792806723.99, pid=8), "/p"))
    archived = [history_record("work/T-0001/archive.yaml", {"unit": {"integration": {"current_validation_run":
                                                                                    _run(start)}}}, _Normaliser("/p"))
                for start in (1792806723.99, 1792806726.99)]
    assert differences(*archived) == []


def test_lead_start_keeps_process_identity_in_first_seen_order():
    def snapshot(pid, start_id):
        return {"lead": {"start": {"pid": pid, "start_id": start_id, "generation": 3}},
                "unrelated": {"pid": 7, "start_id": "keep"}}

    first = _Normaliser("/p")([snapshot(7, "first"), snapshot(7, "reused"), snapshot(7, "first")])
    second = _Normaliser("/p")([snapshot(12, "new"), snapshot(34, "other"), snapshot(12, "new")])
    assert first == second
    assert [item["lead"]["start"] for item in first] == [
        {"pid": f"<process-{ordinal}>", "start_id": f"<process-{ordinal}>", "generation": 3}
        for ordinal in (1, 2, 1)
    ]
    assert first[0]["unrelated"] == {"pid": 7, "start_id": "keep"}

    changed = _Normaliser("/p")([snapshot(7, "first"), snapshot(7, "reused"), snapshot(7, "reused")])
    assert differences(first, changed)
    unknown = _clean(snapshot(7, None), "/p")
    assert unknown["lead"]["start"] == {"pid": "<process-1>", "start_id": None, "generation": 3}
    assert differences(first[0], unknown)
