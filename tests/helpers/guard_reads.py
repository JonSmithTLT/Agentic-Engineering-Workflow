"""What each guard query reads of its arguments (M4-E E4; PR #170's clearing review, the observation).

``GUARD_READS`` is the list the stage-planner agreement check (``tests/unit/test_stage_availability.py``) holds the
planners to. It is kept honest mechanically: the equivalence cases (``tests/integration/test_guard_queries.py``) ask
every query through a ``RecordingArgs`` and assert the keys it read are a subset of its entry, so a query that starts
reading a new argument fails there until this list says so.
"""

from __future__ import annotations

from typing import Any

# A dispatch decision reads its role, card and scope; the migrated queries their request's fields. A planner's other
# arguments (`launch`, `execution`) no guard reads.
DISPATCH_READS = frozenset({"work_id", "role", "card", "scope"})
GUARD_READS: dict[str, frozenset[str]] = {
    "work.assign": DISPATCH_READS, "invoke.create.mutating": DISPATCH_READS, "dispatch.launch": frozenset(),
    "work.transition": frozenset({"work_id", "to", "reason"}),
    "review.ingest": frozenset({"work_id", "evidence"}),
    "verify.ingest": frozenset({"work_id", "evidence"}),
    "verify.ingest.integration": frozenset({"work_id", "evidence"}),
    "integrate.prepare": frozenset({"work_id"}),
    "integrate.publish": frozenset({"work_id"}),
    "work.create": frozenset({"kind", "title", "risk_class", "mutating", "parent", "depends_on", "scope_paths",
                              "goal_backwards", "contract", "mandatory_gates", "min_descendant_class", "rationale",
                              "external_refs", "body", "card", "promoted_from", "acceptance_checks",
                              "acceptance_inputs", "class0_assertions"}),
    "plan.propose": frozenset({"work_id", "body", "reason", "affected_paths", "review", "verify", "no_assurance"}),
}
FOUND = "found"  # where a query records what it found: written, never an input


class RecordingArgs(dict[str, Any]):
    """A query's arguments that remember which keys the query read (``get``, ``[]``, ``in``)."""

    def __init__(self, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self.read: set[str] = set()

    def get(self, key: Any, default: Any = None) -> Any:
        self.read.add(key)
        return super().get(key, default)

    def __getitem__(self, key: Any) -> Any:
        self.read.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        self.read.add(str(key))
        return super().__contains__(key)

    def inputs_read(self) -> set[str]:
        return self.read - {FOUND}
