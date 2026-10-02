"""The explicit seams between the Engine's collaborators (register E5).

What the Engine's mixins once did by overriding each other through the class hierarchy is stated here instead,
and the composition root (``api.Engine``) fills each seam in a fixed, tested order:

* ``StateHooks``: the effects of a work unit's state change, run by ``WorkUnits._set_state`` in order.
* ``GuardTable``: the Lead-transition guard for a guard name and a unit kind.
* ``KindGateContexts``: the gate context of an evidence-only unit (a non-mutating Ticket, a Story or Epic).
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
GateContext = Callable[[dict[str, Any], str], dict[str, Any]]


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


class KindGateContexts:
    """The gate context of each evidence-only kind, provided by the collaborator that owns that kind."""

    def __init__(self) -> None:
        self._by_kind: dict[str, GateContext] = {}

    def register(self, kind: str, context: GateContext) -> None:
        if kind not in (NON_MUTATING, PARENT):
            raise ValueError(f"{kind} has no registered gate context (mutating Tickets use Gates directly)")
        if kind in self._by_kind:
            raise ValueError(f"a gate context is already registered for {kind}")
        self._by_kind[kind] = context

    def get(self, kind: str) -> GateContext:
        return self._by_kind[kind]


class TxnFinalizers:
    """Steps every Lead transaction runs just before its commit, in order (empty until ADR-0011's archival)."""

    def __init__(self) -> None:
        self.steps: list[Callable[[TxnContext], None]] = []

    def run(self, ctx: TxnContext) -> None:
        for step in self.steps:
            step(ctx)
