"""The explicit seams between the Engine's collaborators (register E5).

What the Engine's mixins once did by overriding each other through the class hierarchy is stated here instead,
and the composition root (``api.Engine``) fills each seam in a fixed, tested order:

* ``StateHooks``: the effects of a work unit's state change, run by ``WorkUnits.set_state`` in order.
* ``GuardTable``: the Lead-transition guard for a guard name and a unit kind.
* ``KindRegistry``: the handler of each kind-dependent operation (gate context, invocation, ingest, verification
  classification, next actions) for each unit kind.
* ``TxnFinalizers``: steps run inside every Lead transaction just before it commits (ADR-0011 attaches here).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

from aew.errors import GateUnsatisfied

if TYPE_CHECKING:
    from aew.engine.base import TxnContext

MUTATING = "mutating"  # a mutating Ticket
NON_MUTATING = "non_mutating"  # an evidence-only Ticket (ADR-0008)
PARENT = "parent"  # a Story or Epic (ADR-0007)
KINDS = (MUTATING, NON_MUTATING, PARENT)


def kind_of(unit: dict[str, Any]) -> str:
    if unit["kind"] != "ticket":
        return PARENT
    return MUTATING if unit.get("mutating") else NON_MUTATING


BeforeHook = Callable[[dict[str, Any], dict[str, str]], None]
AfterHook = Callable[[dict[str, Any], dict[str, Any], dict[str, str], "str | None"], None]
Guard = Callable[["TxnContext", str, dict[str, Any], str], None]


class StateHooks:
    """Effects of a state change, in registration order: ``before`` may refuse it, ``after`` applies its effects."""

    def __init__(self) -> None:
        self.before: list[BeforeHook] = []
        self.after: list[AfterHook] = []

    def run_before(self, unit: dict[str, Any], change: dict[str, str]) -> None:
        for hook in self.before:
            hook(unit, change)

    def run_after(self, state: dict[str, Any], unit: dict[str, Any], change: dict[str, str],
                  reason: str | None) -> None:
        for hook in self.after:
            hook(state, unit, change, reason)


class GuardRegistration(NamedTuple):
    name: str
    guard: Guard
    kinds: tuple[str, ...] = KINDS
    replace: bool = False


class GuardTable:
    """The guard for each (guard name, unit kind). A kind-specific entry replaces the general one only when it is
    registered with ``replace=True``, so an accidental double registration is refused."""

    def __init__(self) -> None:
        self._table: dict[tuple[str, str], Guard] = {}

    def register(self, name: str, guard: Guard, kinds: tuple[str, ...] = KINDS, *, replace: bool = False) -> None:
        for kind in kinds:
            if kind not in KINDS:
                raise ValueError(f"unknown unit kind {kind}")
            if (name, kind) in self._table and not replace:
                raise ValueError(f"guard {name} is already registered for {kind}")
            self._table[(name, kind)] = guard

    def register_all(self, registrations: list[GuardRegistration]) -> None:
        for r in registrations:
            self.register(r.name, r.guard, r.kinds, replace=r.replace)

    def resolve(self, name: str, unit: dict[str, Any]) -> Guard:
        guard = self._table.get((name, kind_of(unit)))
        if guard is None:
            raise GateUnsatisfied(f"guard {name} is not available")
        return guard

    def table(self) -> dict[tuple[str, str], Guard]:
        return dict(self._table)


# The operations whose code depends on the unit's kind (ADR-0007, ADR-0008); each is registered for every kind.
GATE_CONTEXT = "gate_context"  # (state, work_id) -> the unit's gate context
INVOKE = "invoke"  # dispatch a bounded invocation for the unit (keyword arguments of ``invoke create``)
INGEST = "ingest"  # the Lead ingests a review or verification report (``kind``: review | verification)
CLASSIFY_VERIFICATION = "classify_verification"  # the Lead classifies a failed verification
NEXT_ACTIONS = "next_actions"  # (state, work_id, unit) -> the unit's next actions for ``resume`` and ``status``
KIND_OPERATIONS = (GATE_CONTEXT, INVOKE, INGEST, CLASSIFY_VERIFICATION, NEXT_ACTIONS)


class KindRegistration(NamedTuple):
    operation: str
    kind: str
    handler: Callable[..., Any]


class KindRegistry:
    """The one place a unit's kind selects the code that handles an operation on it. Each (operation, kind) pair is
    registered exactly once, by the collaborator that owns that kind's behaviour, and ``require_complete`` refuses a
    composition that leaves a pair out."""

    def __init__(self) -> None:
        self._table: dict[tuple[str, str], Callable[..., Any]] = {}

    def register(self, operation: str, kind: str, handler: Callable[..., Any]) -> None:
        if operation not in KIND_OPERATIONS:
            raise ValueError(f"unknown kind operation {operation}")
        if kind not in KINDS:
            raise ValueError(f"unknown unit kind {kind}")
        if (operation, kind) in self._table:
            raise ValueError(f"{operation} is already registered for {kind}")
        self._table[(operation, kind)] = handler

    def register_all(self, registrations: list[KindRegistration]) -> None:
        for r in registrations:
            self.register(r.operation, r.kind, r.handler)

    def require_complete(self) -> None:
        missing = [(op, kind) for op in KIND_OPERATIONS for kind in KINDS if (op, kind) not in self._table]
        if missing:
            raise ValueError(f"kind operations without a handler: {missing}")

    def resolve(self, operation: str, unit: dict[str, Any]) -> Callable[..., Any]:
        return self._table[(operation, kind_of(unit))]

    def resolve_evidence_only(self, operation: str, unit: dict[str, Any]) -> Callable[..., Any]:
        """The handler of an evidence-only unit: a Story or Epic's, otherwise a non-mutating Ticket's (the facade's
        ``evidence_gate_context``, ``invoke_evidence_unit`` and ``ingest_evidence_unit_report``). As before E5, a
        mutating Ticket gets the non-mutating handler, whose dispatch and ingest refuse it."""
        return self._table[(operation, PARENT if kind_of(unit) == PARENT else NON_MUTATING)]

    def table(self) -> dict[tuple[str, str], Callable[..., Any]]:
        return dict(self._table)


class TxnFinalizers:
    """Steps every Lead transaction runs just before its commit, in order (empty until ADR-0011's archival)."""

    def __init__(self) -> None:
        self.steps: list[Callable[[TxnContext], None]] = []

    def run(self, ctx: TxnContext) -> None:
        for step in self.steps:
            step(ctx)
