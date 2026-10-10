"""The invariant oracle itself (tests/helpers/invariants.py) holds on every record shape the engine writes."""

from __future__ import annotations

from pathlib import Path

from invariants import cap_violations


def test_the_concurrency_cap_check_reads_an_engine_custodian_without_a_role(tmp_path: Path):
    """M4-D's `integration_attempt` custodian has a `kind` and no `role`. The seeded hierarchy walks crashed on it
    (`KeyError: 'role'`) whenever the non-mutating cap was set and an integration lease was held (nightly, 2026-10-06
    to 2026-10-09). It is never an executor, so it never counts against the cap."""
    (tmp_path / ".aew" / "policy").mkdir(parents=True)
    (tmp_path / ".aew" / "policy" / "gates.yaml").write_text("non_mutating_concurrency: 1\n", encoding="utf-8")
    state = {"work": {}, "invocations": {
        "INV-1": {"kind": "integration_attempt", "status": "active", "work_unit": "T-0001"},
        "INV-2": {"role": "investigator", "status": "active", "work_unit": "T-0002", "scope": "observation"},
    }}
    assert cap_violations(tmp_path, state) == []
    state["invocations"]["INV-3"] = {"role": "researcher", "status": "active", "work_unit": "T-0003",
                                     "scope": "observation"}
    assert cap_violations(tmp_path, state) == [
        "2 non-mutating Tickets have active executors ['T-0002', 'T-0003']; the policy cap is 1"]
