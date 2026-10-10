"""What each guard query reads of its arguments (M4-E E4; PR #170's clearing review, the observation).

``GUARD_READS`` is the list the stage-planner agreement check (``tests/unit/test_stage_availability.py``) holds the
planners to. It is kept honest mechanically: the equivalence cases (``tests/integration/test_guard_queries.py``) ask
every query through a ``RecordingArgs`` and assert the keys it read are a subset of its entry, so a query that starts
reading a new argument fails there until this list says so.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
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


class RecordingArgs(MutableMapping[str, Any]):
    """A query's arguments that remember which keys the query read. A mapping, not a ``dict`` subclass, so every
    access goes through a recorded method (``dict(a)`` and ``{**a}`` take no C fast path): ``[]``, ``get`` and ``in``
    record the key; ``keys``, ``values``, ``items``, iteration and ``copy`` record every key (PR #171 review,
    finding 5). Writing (``found``, through ``setdefault``) is not reading."""

    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})
        self.read: set[str] = set()

    def __getitem__(self, key: str) -> Any:
        self.read.add(key)
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        del self._data[key]

    def __iter__(self) -> Iterator[str]:
        self.read.update(self._data)
        return iter(list(self._data))

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        self.read.add(str(key))
        return key in self._data

    def copy(self) -> dict[str, Any]:
        self.read.update(self._data)
        return dict(self._data)

    def data(self) -> dict[str, Any]:
        """The arguments as they stand (what the query found included), read without recording."""
        return dict(self._data)

    def inputs_read(self) -> set[str]:
        return self.read - {FOUND}
