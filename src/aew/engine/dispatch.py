"""One legality source for dispatch: ``DispatchDecision`` (M4-A; plan-assurance decisions §3.5, v0.4 §17.1).

Every way to give a role new authority over a unit (a new invocation, or a harness run holding an invocation's
credential) is a declared **dispatch entrypoint** below. Each entrypoint names its guards, in order; each guard is a
side-effect-free check registered by the collaborator that owns it. ``Dispatch.decide`` evaluates them against one
state and returns a typed decision. The dispatch itself calls ``decide`` inside its own transaction and ``require``s
it; ``aew dispatch explain`` calls the same ``decide`` on the committed state, so a query equals the execution.

Enforcement does not rest on the routes remembering to ask. The ``Dispatch.finalize`` transaction finalizer refuses
to commit any transaction that creates an invocation or a harness run without an allowed decision for it, computed
in that transaction against that revision, through a registered entrypoint (``DISPATCH_UNDECIDED``). The decision is
recorded on the invocation (``dispatch``) and on the run, so a dispatch's legality stays attributable. An old ALLOW
is never reused: there is no cache, and a decision is bound to the revision it was computed against.

During the evaluation period (decisions §3.5) the predicate is permissive except for the checks every route made
before M4 (now migrated in, with their error codes and order unchanged), hard protected-condition failures, and Class
0 eligibility where Class 0 is requested. It is not called ``ASSURED``.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

from aew.engine.reasons import REASONS, require_known
from aew.errors import AEWError, DispatchRefused, DispatchUndecided, NotFound, UsageError

if TYPE_CHECKING:
    from aew.engine.base import Kernel, TxnContext

# Who carried the dispatch to the engine: the CLI, the Lead broker's relay, or a direct engine call (tests).
_CHANNEL: contextvars.ContextVar[str] = contextvars.ContextVar("aew_dispatch_channel", default="direct")


@contextlib.contextmanager
def channel(name: str) -> Iterator[None]:
    """Mark the dispatches made inside this block as carried by ``name`` (recorded with the decision)."""
    token = _CHANNEL.set(name)
    try:
        yield
    finally:
        _CHANNEL.reset(token)


# --------------------------------------------------------------------------------------------- the registry

MUTATION = ("protected.overlap", "assurance.triggers", "class0.eligible")  # new in M4-A; evaluated after the rest


class Entrypoint(NamedTuple):
    name: str
    surface: str  # "cli": reached by the CLI command ``cli``; "internal": reached from inside another operation
    cli: tuple[str, ...] | None
    guards: tuple[str, ...]
    description: str
    covered_by: str | None = None  # an internal entrypoint whose authority comes from another entrypoint's decision


ENTRYPOINTS: dict[str, Entrypoint] = {e.name: e for e in (
    Entrypoint("work.assign", "cli", ("work", "assign"),
               ("assign.kind", "transition.assign", "source.commit", "readiness", "workspace.free", "cap.mutating",
                "card.implementer", "inputs.current", *MUTATION),
               "READY -> ASSIGNED for a mutating Ticket: a mutation workspace and an implementer"),
    Entrypoint("work.dispatch", "cli", ("work", "dispatch"),
               ("nm.kind", "transition.assign", "source.commit", "readiness", "plan.binding", "dependencies",
                "inputs.current", "card.executor", "cap.non_mutating"),
               "READY -> ASSIGNED for a non-mutating Ticket: an executor and its observation"),
    Entrypoint("work.redispatch", "cli", ("work", "redispatch"),
               ("nm.kind", "redispatch.state", "source.commit", "plan.binding", "dependencies", "inputs.current",
                "card.executor", "cap.non_mutating"),
               "a non-mutating Ticket's next attempt, superseding the current one"),
    Entrypoint("invoke.create.mutating", "cli", ("invoke", "create"),
               ("invoke.slot", "card.slot", "inputs.current", "workspace.live", *MUTATION),
               "an implementer, reviewer or verifier for a mutating Ticket (or its integration candidate)"),
    Entrypoint("invoke.create.non_mutating", "cli", ("invoke", "create"),
               ("nm.invoke",),
               "a reviewer or verifier of a non-mutating Ticket's record"),
    Entrypoint("invoke.create.parent", "cli", ("invoke", "create"),
               ("parent.acceptance", "card.parent", "dependencies.parent", "inputs.current"),
               "a reviewer or verifier of a Story's or Epic's acceptance"),
    Entrypoint("harness.launch", "cli", ("harness", "launch"),
               ("launch.launchable", "launch.pack", "launch.not_live", *MUTATION),
               "a harness run for an active invocation (launch or relaunch): the credential is rotated to it"),
    Entrypoint("dispatch.launch", "internal", None, (),
               "run 1 of a dispatch made with --launch, inside that dispatch's transaction", covered_by="dispatch"),
    Entrypoint("lead_broker.relay", "internal", None, (),
               "a Lead session's dispatch, relayed by the Lead broker to the CLI entrypoint it names",
               covered_by="cli"),
)}

# CLI command paths that dispatch, and the entrypoints each may reach (the unit's kind selects among them).
CLI_DISPATCHES: dict[tuple[str, ...], tuple[str, ...]] = {}
for _e in ENTRYPOINTS.values():
    if _e.cli:
        CLI_DISPATCHES[_e.cli] = (*CLI_DISPATCHES.get(_e.cli, ()), _e.name)

INVOKE_ENTRYPOINT = {"mutating": "invoke.create.mutating", "non_mutating": "invoke.create.non_mutating",
                     "parent": "invoke.create.parent"}


# --------------------------------------------------------------------------------------------- the decision

@dataclass
class Blocker:
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    error: AEWError | None = None  # a migrated check's own error, raised unchanged by ``require``

    def to_dict(self) -> dict[str, Any]:
        out = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


@dataclass
class DispatchDecision:
    entrypoint: str
    work_id: str
    revision: int
    generation: int | None
    channel: str
    blocking: list[Blocker] = field(default_factory=list)
    obligations: list[dict[str, Any]] = field(default_factory=list)
    dependency_digests: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)  # what the guards found (base commit, inputs, card): not data

    @property
    def allowed(self) -> bool:
        return not self.blocking

    @property
    def reason_codes(self) -> list[str]:
        return sorted({b.code for b in self.blocking} | {o["code"] for o in self.obligations})

    def to_dict(self) -> dict[str, Any]:
        return {"entrypoint": self.entrypoint, "work_id": self.work_id, "allowed": self.allowed,
                "effective_obligations": list(self.obligations),
                "blocking_conditions": [b.to_dict() for b in self.blocking],
                "reason_codes": self.reason_codes, "dependency_digests": dict(self.dependency_digests),
                "revision": self.revision, "generation": self.generation}

    def digest(self) -> str:
        body = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()

    def provenance(self) -> dict[str, Any]:
        """What the invocation or run records about the decision that admitted it."""
        return {"entrypoint": self.entrypoint, "channel": self.channel, "revision": self.revision,
                "generation": self.generation, "decision": self.digest(),
                "obligations": [o["code"] for o in self.obligations]}

    def require(self) -> DispatchDecision:
        """Raise when not allowed: a migrated check's own error first (so its code and message are unchanged),
        otherwise ``DISPATCH_REFUSED`` naming every blocking condition."""
        if self.allowed:
            return self
        first = self.blocking[0]
        if first.error is not None:
            raise first.error
        raise DispatchRefused(
            f"{self.work_id} cannot be dispatched ({self.entrypoint}): "
            + "; ".join(b.message for b in self.blocking),
            work_id=self.work_id, entrypoint=self.entrypoint, reason_codes=self.reason_codes,
            blocking_conditions=[b.to_dict() for b in self.blocking],
            effective_obligations=list(self.obligations))


# A guard: (state, work_id, facts) -> None (pass), a Blocker, a list of Blockers, or obligations via ``facts``.
Guard = Callable[[dict[str, Any], str, dict[str, Any]], "Blocker | list[Blocker] | None"]


class GuardRegistration(NamedTuple):
    name: str
    guard: Guard


def blocker_from(err: AEWError) -> Blocker:
    code = err.code if err.code in REASONS else "ILLEGAL_TRANSITION"
    return Blocker(code, err.message, dict(err.details), err)


def checked(fn: Callable[[], Any]) -> Blocker | None:
    """Run a check that raises (a migrated pre-M4 check) and turn its refusal into a blocker carrying the error."""
    try:
        fn()
    except AEWError as err:
        return blocker_from(err)
    return None


class Dispatch:
    """The dispatch predicate, its guard registry, and the commit-time check that every new invocation and run was
    admitted by it."""

    def __init__(self, k: Kernel) -> None:
        self.k = k
        self._guards: dict[str, Guard] = {}

    # ---- registration (the composition root registers every collaborator's guards)

    def register_all(self, registrations: list[GuardRegistration]) -> None:
        for r in registrations:
            if r.name in self._guards:
                raise ValueError(f"dispatch guard {r.name} is already registered")
            self._guards[r.name] = r.guard

    def require_complete(self) -> None:
        missing = sorted({g for e in ENTRYPOINTS.values() for g in e.guards} - set(self._guards))
        if missing:
            raise ValueError(f"dispatch guards without an implementation: {missing}")

    def guard_names(self) -> set[str]:
        return set(self._guards)

    # ---- the predicate

    def decide(self, state: dict[str, Any], entrypoint: str, work_id: str, **args: Any) -> DispatchDecision:
        """Evaluate ``entrypoint``'s guards against ``state``. No side effects: the same call answers ``explain``.

        The migrated pre-M4 checks are sequential preconditions: the first that refuses ends the evaluation, as the
        routes did before (later checks read what earlier ones found). The M4 assurance checks then all run, so a
        refusal names every condition at once."""
        entry = ENTRYPOINTS.get(entrypoint)
        if entry is None:
            raise UsageError(f"unknown dispatch entrypoint {entrypoint}", known=sorted(ENTRYPOINTS))
        if work_id not in state["work"]:
            raise NotFound(f"no work unit {work_id}")
        decision = DispatchDecision(entrypoint=entrypoint, work_id=work_id, revision=state["revision"],
                                    generation=(state.get("lead") or {}).get("generation"), channel=_CHANNEL.get())
        facts: dict[str, Any] = {**args, "entrypoint": entrypoint, "obligations": decision.obligations,
                                 "digests": decision.dependency_digests}
        decision.facts = facts
        for name in entry.guards:
            result = self._guards[name](state, work_id, facts)
            found = [result] if isinstance(result, Blocker) else list(result or [])
            for b in found:
                require_known(b.code)
            decision.blocking.extend(found)
            if found and name not in MUTATION:
                break
        for o in decision.obligations:
            require_known(o["code"])
        decision.dependency_digests.update(self._policy_digests())
        return decision

    def _policy_digests(self) -> dict[str, Any]:
        from aew.util import sha256_file

        names = ("gates", "guardrails", "checks")
        return {"policy": {n: sha256_file(self.k.aew_root / self.k.manifest["policy"][n]) for n in names
                           if n in self.k.manifest.get("policy", {})}}

    def decide_in(self, ctx: TxnContext, entrypoint: str, work_id: str, **args: Any) -> DispatchDecision:
        """Decide inside a dispatch transaction, record the decision for the commit check, and require it."""
        decision = self.decide(ctx.state, entrypoint, work_id, **args)
        ctx.dispatch_decisions.append(decision)
        return decision.require()

    def explain(self, entrypoint: str, work_id: str, **args: Any) -> dict[str, Any]:
        decision = self.decide(self.k.store.read(), entrypoint, work_id, **args)
        return {"ok": True, **decision.to_dict(), "channel": decision.channel}

    # ---- the commit check (a transaction finalizer)

    def finalize(self, ctx: TxnContext) -> None:
        """Refuse a commit that creates an invocation or a harness run no recorded decision admitted, and record each
        admitting decision on what it admitted."""
        before = ctx.session.committed_view().get("invocations") or {}
        allowed = [d for d in ctx.dispatch_decisions if d.allowed]
        for d in allowed:
            if d.revision != ctx.session.revision:  # never an old ALLOW
                raise DispatchUndecided(f"a dispatch decision for {d.work_id} was computed at revision {d.revision}, "
                                        f"not this transaction's {ctx.session.revision}")
        for inv_id, inv in ctx.state.get("invocations", {}).items():
            old = before.get(inv_id)
            if old is None:
                d = self._admitting(allowed, inv["work_unit"], invocation=None)
                if d is None:
                    raise DispatchUndecided(
                        f"{inv_id} was created for {inv['work_unit']} without a dispatch decision: every dispatch "
                        "route must decide through a registered entrypoint (aew.engine.dispatch)",
                        invocation=inv_id, work_unit=inv["work_unit"])
                inv["dispatch"] = d.provenance()
            new_runs = (inv.get("runs") or [])[len((old or {}).get("runs") or []):]
            for run in new_runs:
                if old is None:  # run 1 of a dispatch made with --launch: admitted by that dispatch's decision
                    run["dispatch"] = {**inv["dispatch"], "entrypoint": "dispatch.launch",
                                       "covered_by": inv["dispatch"]["entrypoint"]}
                    continue
                d = self._admitting(allowed, inv["work_unit"], invocation=inv_id)
                if d is None:
                    raise DispatchUndecided(
                        f"run {run.get('run')} of {inv_id} was started without a dispatch decision",
                        invocation=inv_id, run=run.get("run"))
                run["dispatch"] = d.provenance()

    @staticmethod
    def _admitting(allowed: list[DispatchDecision], work_id: str, *, invocation: str | None) -> DispatchDecision | None:
        for d in allowed:
            if d.work_id != work_id:
                continue
            if invocation is None and d.entrypoint != "harness.launch":
                return d
            if invocation is not None and d.entrypoint == "harness.launch" and d.facts.get("invocation") == invocation:
                return d
        return None
