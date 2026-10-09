"""The stage executor of the typed Lead surface (M4-E E3b; plan v3 E3; typed-lead-surface-design-v0.2 §3.4).

A stage is one tool call that expands into several primitives, each its own durable transition. The executor opens
the call's StageIntent by CAS on the caller's ``expect_rev`` (rules 1 and 2: a stale one commits nothing), then runs
the planned primitives in order from the revision the intent's commit returned, each with its step armed
(:func:`aew.engine.stage_intents.step`), so the journal records the step in the primitive's own commit or the commit
does not land.

- **First refusal stops** (rule 3): committed steps stand, and the intent records the stop boundary.
- **A later STALE_REVISION** is retried once (rule 4; R5-1, all five conditions): the step is MECHANICAL or
  POLICY_RESOLVED, the stage's effective class is not judgment-bearing (rule 5: a judgment is never replayed, nor any
  step of a stage that carries one), the bound legality digest is unchanged, the caller's authority still holds (its
  generation, and the intent's), and the action is AVAILABLE at the current revision with the same arguments. An
  availability the surface cannot query yet (a guard that is not a dispatch decision: E4 migrates them) is UNKNOWN,
  and UNKNOWN never retries. The retried step carries ``retried_after_stale_revision`` on the intent and in
  ``completed_steps``.
- **Policy drift** stops as STALE_POLICY (rule 6), and **a launch that fails after its dispatch committed** stops as
  ``launch_failed`` (rule 7): the committed run identity stands.
- **A stop the executor cannot record** (the seat was lost, a policy edit awaits adoption, the journal refused the
  bookkeeping itself) leaves the intent ACTIVE for ``resume`` and the Lead's ``resolve`` (E3c): the result says so.

The plan comes from the stage's planner (``STAGES``), and each planned primitive needs a step runner
(``STEP_RUNNERS``); both are checked before anything commits. A planned step's argument may be ``{"$from": [m,
field]}``: the single unit, invocation or run that step ``m`` recorded in the journal, so a continued stage (E3c)
resolves it from durable state, never from this call's memory.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aew import errors
from aew.engine import stage_intents as SI
from aew.engine.primitives import JUDGMENT_BEARING, spec_for
from aew.harness.contract import redact
from aew.surface import contract
from aew.surface.classify import AVAILABLE, BLOCKED, UNKNOWN, effective_class
from aew.util import sha256_bytes

if TYPE_CHECKING:
    from aew.surface.run import Call

StepRunner = Callable[["Call", dict[str, Any], int], dict[str, Any]]  # (call, step arguments, expect_rev) -> output
Planner = Callable[[dict[str, Any]], list[dict[str, Any]]]  # the call's arguments -> [{primitive, args}]

STOP_ATTEMPTS = 3  # recording a stop is the journal's bookkeeping, not a step: it follows the revision a few times


# ---------------------------------------------------------------------------------------------- step runners

def _checkpoint(c: Call, a: dict[str, Any], rev: int) -> dict[str, Any]:
    return c.engine.checkpoint(token=c.token(), expect_rev=rev, note=a.get("note") or "", next_action=a.get("next"))


def _assign(c: Call, a: dict[str, Any], rev: int) -> dict[str, Any]:
    return c.engine.work_assign(token=c.token(), expect_rev=rev, work_id=a["work_id"],
                                execution_profile=a.get("execution"), launch=bool(a.get("launch")))


STEP_RUNNERS: dict[str, StepRunner] = {"checkpoint": _checkpoint, "work.assign": _assign}

# The built stage tools and their planners. None is built yet: E4 and E5 build the Ticket stages over this executor
# once their guards are queryable and their primitives declared. Tests register probe stages here.
STAGES: dict[str, Planner] = {}


def contract_digest(t: contract.Tool) -> str:
    """The stage's contract as the intent binds it: everything but its presentation (the description)."""
    row = {"name": t.name, "kind": t.kind, "base_class": t.base_class, "input_schema": t.input_schema,
           "expands_to": list(t.expands_to), "required_judgments": list(t.required_judgments),
           "promotes": list(t.promotes)}
    return sha256_bytes(json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def launches(args: dict[str, Any]) -> bool:
    """Whether the step has an effect after its commit (a launch): its commit cannot also complete the stage."""
    return bool(args.get("launch"))


# ---------------------------------------------------------------------------------------------- the executor

def run_stage(c: Call, t: contract.Tool, plan: list[dict[str, Any]]) -> dict[str, Any]:
    """Run stage ``t`` with ``plan``. Engine refusals before the intent opens propagate (nothing committed); after it
    opens, they stop the stage and are reported on ``c.stopped``."""
    planned = [p["primitive"] for p in plan]
    if planned != list(t.expands_to):
        raise errors.UsageError(f"stage {t.name} planned {planned}, but its contract expands to "
                                f"{list(t.expands_to)}")
    missing = [p for p in planned if p not in STEP_RUNNERS]
    if missing:
        raise errors.UsageError(f"stage {t.name} plans {missing}, which have no step runner")
    a = c.a
    c.subject = a.get("work_id")
    judgments = [*t.required_judgments, *(name for name in t.promotes if name in a)]
    opened = c.engine.stage_open(
        token=c.token(), expect_rev=a["expect_rev"], tool=t.name, contract_digest=contract_digest(t), arguments=a,
        judgment_inputs=judgments, base_class=t.base_class, effective_class=effective_class(t, a),
        plan=[{"primitive": p["primitive"], "args": p.get("args") or {}} for p in plan], subject=c.subject,
        ingress=c.ctx.ingress)
    intent, rev = opened["intent"], opened["revision"]
    c.intent, c.binding = intent, opened["binding"]
    outputs: list[dict[str, Any]] = []
    for n, step in enumerate(plan, start=1):
        try:
            args = _resolve(c, intent, step.get("args") or {})
        except errors.AEWError as refusal:
            return _stop(c, intent, n, step["primitive"], refusal, outputs)
        final = n == len(plan) and not launches(args)
        retried = False
        while True:
            try:
                with SI.step(intent, n, retried=retried, final=final):
                    out = STEP_RUNNERS[step["primitive"]](c, args, rev)
                break
            except errors.StaleRevision as refusal:
                drift = _drift(c, intent)
                if drift is not None:  # rule 6 before rule 4: the stage never runs on under a policy it did not bind
                    return _stop(c, intent, n, step["primitive"], drift, outputs)
                if retried or not _retryable(c, intent, step["primitive"], args):
                    return _stop(c, intent, n, step["primitive"], refusal, outputs)
                retried, rev = True, _revision(c)
            except errors.HarnessLaunchFailed as failed:
                # Rule 7: the dispatch committed (its run is recorded); the stage stops, the run identity stands.
                return _stop(c, intent, n, step["primitive"], failed, outputs, boundary="launch_failed")
            except errors.AEWError as refusal:
                return _stop(c, intent, n, step["primitive"], refusal, outputs)
        outputs.append(out)
        rev = out["revision"]
    if launches(_resolve(c, intent, plan[-1].get("args") or {})):
        _end(c, lambda r: c.engine.stage_close(token=c.token(), expect_rev=r, intent=intent))
    return _payload(c, intent, outputs)


def _resolve(c: Call, intent: str, args: dict[str, Any]) -> dict[str, Any]:
    """``args`` with each ``{"$from": [m, field]}`` replaced by the one id step ``m`` recorded under ``field``."""
    out: dict[str, Any] = {}
    for name, value in args.items():
        if isinstance(value, dict) and set(value) == {"$from"}:
            m, field = value["$from"]
            steps = c.engine.stage_intent(intent)["steps"]
            ids = steps[m - 1]["outputs"][field] if 0 < m <= len(steps) else []
            if len(ids) != 1:
                raise errors.IllegalTransition(f"{name} comes from step {m}'s {field}, which recorded {len(ids)} "
                                               "id(s), not one", reason="unresolved_argument", step=m, field=field)
            value = ids[0]
        out[name] = value
    return out


def availability(c: Call, primitive: str, args: dict[str, Any]) -> str:
    """Whether ``primitive`` with ``args`` is legal now, asked of the predicate its own commit evaluates. Only dispatch
    decisions are queryable yet; every other guard is UNKNOWN (E4 migrates them)."""
    guard = spec_for(primitive).guard_id
    if guard is None or guard not in contract.EXPLAINABLE or not args.get("work_id"):
        return UNKNOWN
    try:
        decision = c.engine.dispatch_explain(args["work_id"], entrypoint=guard)
    except errors.AEWError:
        return UNKNOWN
    return AVAILABLE if decision.get("allowed") else BLOCKED


def _drift(c: Call, intent: str) -> errors.StalePolicy | None:
    """STALE_POLICY when the legality digest in force is not the one ``intent`` bound (rule 6)."""
    bound = c.engine.stage_intent(intent)["binding"]["legality_digest"]
    current = c.engine.policy_digests()["legality_digest"]
    if current == bound:
        return None
    return errors.StalePolicy(f"the legality policy changed since {intent} opened: its next step is not run. Read "
                              "the projection again and decide anew", intent=intent, bound=bound, current=current)


def _retryable(c: Call, intent: str, primitive: str, args: dict[str, Any]) -> bool:
    """R5-1's five conditions, each read now (the legality digest is checked first, by :func:`_drift`)."""
    from aew.surface.run import _stale  # the runner's own authority check (run imports this module)

    si = c.engine.stage_intent(intent)
    if JUDGMENT_BEARING in (spec_for(primitive).operation_class, si["effective_class"]):
        return False
    if c.engine.policy_digests()["legality_digest"] != si["binding"]["legality_digest"]:
        return False
    if _stale(c.engine, c.ctx) is not None:
        return False
    if si["generation"] != int(c.engine.store.read()["lead"]["generation"]):
        return False
    return availability(c, primitive, args) == AVAILABLE


def _revision(c: Call) -> int:
    return int(c.engine.store.read()["revision"])


def _stop(c: Call, intent: str, n: int, primitive: str, exc: errors.AEWError, outputs: list[dict[str, Any]], *,
          boundary: str | None = None) -> dict[str, Any]:
    """Stop the stage at step ``n`` and end its intent, or leave it ACTIVE when the stop cannot be recorded. A step
    that committed before its failure (a launch) stops the stage at the next step, or at itself when it was the
    last."""
    from aew.surface.run import _error, boundary_of

    where = boundary or boundary_of(exc)
    c.stopped = {"at": primitive, "boundary": where, "error": _error(exc)}
    si = c.engine.stage_intent(intent)
    done = len(si["steps"])
    at = done + 1 if done < len(si["plan"]) else done
    _end(c, lambda r: c.engine.stage_stop(token=c.token(), expect_rev=r, intent=intent, n=at, boundary=where,
                                          code=exc.code, message=redact(exc.message), reason=exc.details.get("reason")))
    return _payload(c, intent, outputs)


def _end(c: Call, record: Callable[[int], dict[str, Any]]) -> None:
    """Record the intent's end, following the revision across others' commits; a refusal of any other kind leaves the
    intent ACTIVE, and says why."""
    for _ in range(STOP_ATTEMPTS):
        try:
            record(_revision(c))
            return
        except errors.StaleRevision as exc:
            c.left_active = exc
        except errors.AEWError as exc:
            c.left_active = exc
            return


def _payload(c: Call, intent: str, outputs: list[dict[str, Any]]) -> dict[str, Any]:
    si = c.engine.stage_intent(intent)
    c.steps = [{"primitive": s["primitive"], "operation_class": s["operation_class"], "revision": s["revision"],
                "summary": s["summary"] or "", "refs": list(s["refs"]),
                **({"retried_after_stale_revision": True} if s.get("retried_after_stale_revision") else {})}
               for s in si["steps"]]
    out: dict[str, Any] = {"intent": intent, "status": si["status"], "steps": outputs}
    if si["status"] == SI.ACTIVE:
        left = c.left_active
        out["left_active"] = {"code": left.code, "message": left.message} if left is not None else None
    return out
