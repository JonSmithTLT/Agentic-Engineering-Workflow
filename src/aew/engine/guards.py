"""Queryable guards (M4-E E4; typed-lead-surface-design-v0.2 §3.6; idea note v0.4 §12, §13).

A guard decides whether a primitive is legal now. ``DispatchDecision`` was the first queryable one (M4-A); E4 puts the
transition and ingest guards the Ticket stages use on the same substrate, its :class:`~aew.engine.dispatch.Blocker`:

* each migrated guard is a pure ``query(state, work_id, args) -> Blocker | None``. It reads the state it is given and
  the engine's inputs (policy, the sealed evidence store, a workspace's snapshot) and changes nothing. ``args`` is the
  request, and the query records what it found under ``args["found"]`` for the effects that follow, as a dispatch
  guard records its facts;
* the execute path calls the same query inside its own transaction, on that transaction's state, and raises the
  blocker's own error unchanged (its code, message and details); only then does it apply its effects. So a query
  equals the execution by construction for the same revision, generation and policy (§13), and a test checks it per
  guard on seeded states (``tests/integration/test_guard_queries.py``);
* a primitive whose guard is not migrated answers ``UNKNOWN``, never ``BLOCKED`` (frozen decision 3), and so does a
  migrated primitive whose answer depends on a guard that is not (a transition rule's named guard, per unit kind).

**BLOCKED commits nothing, except a blocker carrying a ``disposition``, whose call commits only that disposition and
never the guarded effect** (PR #171 review, finding 1). Today only ``integrate.publish`` has one: a candidate
superseded by a later acceptance (``requeue``: the call retires it and requeues the entry, then raises the same
refusal) and a moved authoritative head (``rebuild``: the call rebuilds the candidate once under the same lease, plan
v3 §2.3, or leaves the entry for the Lead's disposition, and publishes nothing). The answer names it
(``disposition``), so ``explain``, the projection and ``resume`` can say what calling it would do.

A query never raises a refusal: every refusal is its blocker. It raises only what is not a guard's answer, such as an
integrity failure (a policy edit awaiting adoption), and the caller reports that as ``UNKNOWN`` with its code. Anything
else a query raises is an engine defect: it too is ``UNKNOWN`` (``GUARD_QUERY_DEFECT``), logged, and never crashes the
``resume``, ``status`` or projection that asked (PR #170 review, finding 2).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

from aew.engine.dispatch import ENTRYPOINTS, Blocker
from aew.engine.primitives import spec_for
from aew.errors import AEWError, IntegrityError

if TYPE_CHECKING:
    from aew.engine.dispatch import DispatchDecision

AVAILABLE, BLOCKED, UNKNOWN = "AVAILABLE", "BLOCKED", "UNKNOWN"
GUARD_NOT_QUERYABLE = "GUARD_NOT_QUERYABLE"  # the guard has no query form yet: its own commit decides it
GUARD_QUERY_DEFECT = "GUARD_QUERY_DEFECT"  # a query raised something that is not a refusal: an engine defect
DISPOSITION = "disposition"  # a blocker's detail: what its call commits instead of the guarded effect (module doc)
DISPOSITIONS = ("requeue", "rebuild")

log = logging.getLogger(__name__)

GuardQuery = Callable[[dict[str, Any], str, dict[str, Any]], "Blocker | NotQueryable | None"]


class NotQueryable(NamedTuple):
    """A query's answer when the decision rests on a guard that has no query form (for this unit's kind)."""

    guard: str


def refusal(err: AEWError) -> Blocker:
    """The blocker of a refusal: the engine's own error code (durable, ``aew.errors``), message and details, with the
    error itself, which the execute path raises unchanged."""
    return Blocker(err.code, err.message, dict(err.details), err)


def checked(fn: Callable[[], Any]) -> Blocker | None:
    """Run checks that raise, as the execute path always did, and turn the first refusal into its blocker. An integrity
    failure is not a guard's answer: it propagates."""
    try:
        fn()
    except IntegrityError:
        raise
    except AEWError as err:
        return refusal(err)
    return None


def require(found: Blocker | NotQueryable | None) -> None:
    """The execute path's use of a query: raise the blocker's own error. ``NotQueryable`` passes: the caller then runs
    the guard that has no query form, in the transaction, as before E4."""
    if isinstance(found, Blocker):
        assert found.error is not None  # every guard blocker carries the refusal it stands for
        raise found.error


class GuardQueries:
    """The migrated guards, by primitive id, and the one answer a caller reads: AVAILABLE, BLOCKED or UNKNOWN.

    A dispatch primitive's guard is its ``DispatchDecision`` (asked through ``decide``); a primitive registered here is
    answered by its query; anything else is ``UNKNOWN``."""

    def __init__(self, decide: Callable[..., DispatchDecision]) -> None:
        self._decide = decide
        self._queries: dict[str, GuardQuery] = {}

    def register(self, primitive: str, query: GuardQuery) -> None:
        # A primitive's guard may be migrated before the primitive is declared: E5 declares `work.create`,
        # `plan.propose`, `work.transition` and `review.ingest` with the stages that first run them (plan v3 E5).
        if primitive in self._queries:
            raise ValueError(f"the guard of {primitive} is already registered")
        self._queries[primitive] = query

    def migrated(self) -> list[str]:
        return sorted(self._queries)

    def query_for(self, primitive: str) -> GuardQuery | None:
        return self._queries.get(primitive)

    def answer(self, state: dict[str, Any], primitive: str, work_id: str | None,
               args: dict[str, Any]) -> dict[str, Any]:
        """Whether ``primitive`` with ``args`` is legal on ``state`` now. ``args`` keeps what the query found."""
        query = self._queries.get(primitive)
        guard = spec_for(primitive).guard_id
        out: dict[str, Any] = {"primitive": primitive, "work_id": work_id, "revision": state.get("revision"),
                               "guard": primitive if query is not None else guard}
        try:
            if query is not None:
                found = query(state, work_id or "", args)
            elif guard in ENTRYPOINTS and not ENTRYPOINTS[guard].covered_by and work_id:
                decision = self._decide(state, guard, work_id, role=args.get("role"), card_id=args.get("card"),
                                        scope=args.get("scope") or "ticket")
                return {**out, "availability": AVAILABLE if decision.allowed else BLOCKED,
                        "blocking_conditions": [b.to_dict() for b in decision.blocking],
                        "reason_codes": decision.reason_codes}
            else:
                found = NotQueryable(guard or primitive)
        except AEWError as err:  # not a guard's answer (an integrity failure, a decision that cannot be asked)
            return {**out, "availability": UNKNOWN, "blocking_conditions": [], "reason_codes": [err.code],
                    "unanswered": {"code": err.code, "message": err.message}}
        except Exception as err:  # noqa: BLE001  a defect answers UNKNOWN and is logged, never crashing resume or status
            log.exception("guard query of %s for %s raised %s", primitive, work_id, type(err).__name__)
            return {**out, "availability": UNKNOWN, "blocking_conditions": [], "reason_codes": [GUARD_QUERY_DEFECT],
                    "unanswered": {"code": GUARD_QUERY_DEFECT, "message": f"{type(err).__name__}: {err}"}}
        if isinstance(found, NotQueryable):
            return {**out, "availability": UNKNOWN, "blocking_conditions": [], "reason_codes": [GUARD_NOT_QUERYABLE],
                    "not_queryable": found.guard}
        if found is not None:
            disposition = found.details.get(DISPOSITION)
            return {**out, "availability": BLOCKED, "blocking_conditions": [found.to_dict()],
                    "reason_codes": [found.code], **({DISPOSITION: disposition} if disposition else {})}
        return {**out, "availability": AVAILABLE, "blocking_conditions": [], "reason_codes": []}

