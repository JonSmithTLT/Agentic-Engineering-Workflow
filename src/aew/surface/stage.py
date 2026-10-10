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
  availability the surface cannot query (a guard not migrated to a query, E4) is UNKNOWN, and UNKNOWN never
  retries. The retried step carries ``retried_after_stale_revision`` on the intent and in
  ``completed_steps``.
- **Policy drift** stops as STALE_POLICY (rule 6), and **a launch that fails after its dispatch committed** stops as
  ``launch_failed`` (rule 7): the committed run identity stands. A dispatch made with ``launch`` records run 1 in its
  own commit (``dispatch.launch``: plan v3 §1 and E4, inside the dispatch's transaction and covered by its decision);
  its step runner then hands that run to its supervisor, so the stage never goes on, or completes, over a run that
  never started (#142 review, finding 1).
- **A stop the executor cannot record** (the seat was lost, a policy edit awaits adoption, the journal refused the
  bookkeeping itself) leaves the intent ACTIVE for ``resume`` and the Lead's ``resolve`` (E3c): the result says so.
  A refusal met while deciding on a retry (reading the binding with a policy edit pending) stops the stage the same
  way, with its committed steps reported (#142 review, finding 2).

The plan comes from the stage's planner (``STAGES``), and each planned primitive needs a step runner
(``STEP_RUNNERS``); both are checked before anything commits. A planned step's argument may be ``{"$from": [m,
field]}``: the single unit, invocation or run that step ``m`` recorded in the journal, so a continued stage (E3c)
resolves it from durable state, never from this call's memory. The journal refuses a reference to a step that is not
an earlier one, or to a field no step records, when the intent opens (#142 review, finding 4).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aew import errors
from aew.engine import stage_intents as SI
from aew.engine.guards import GUARD_NOT_QUERYABLE
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
    out = c.engine.work_assign(token=c.token(), expect_rev=rev, work_id=a["work_id"],
                               execution_profile=a.get("execution"), launch=launches(a))
    if not launches(a):
        return out
    # The commit recorded run 1 with the credential the dispatch issued, which exists only in ``out``: hand it to the
    # run's supervisor now, exactly as `aew work assign --launch` does. A failure raises HarnessLaunchFailed with the
    # recorded run (rule 7); the credential never reaches the result (#142 review, finding 1).
    return c.engine.launch_dispatched(out)


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
    return _run_steps(c, intent, plan, 1, rev)


def _run_steps(c: Call, intent: str, plan: list[dict[str, Any]], first: int, rev: int) -> dict[str, Any]:
    """Run ``plan`` from step ``first`` (1 for a new stage; the first uncommitted step for a continued one) from
    revision ``rev``, stopping at the first refusal, and complete the intent when the last step launched."""
    outputs: list[dict[str, Any]] = []
    final = False
    for n, step in enumerate(plan, start=1):
        if n < first:  # committed before this call: a continued stage never repeats a step (its key is recorded)
            continue
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
                try:
                    drift = _drift(c, intent)
                    retry = drift is None and not retried and _retryable(c, intent, step["primitive"], args)
                except errors.AEWError as unchecked:
                    # Deciding on the retry was itself refused (a policy edit awaiting adoption fails every digest
                    # read): the stage stops on that refusal like any other, never escaping with its committed steps
                    # unreported (#142 review, finding 2).
                    return _stop(c, intent, n, step["primitive"], unchecked, outputs)
                if drift is not None:  # rule 6 before rule 4: the stage never runs on under a policy it did not bind
                    return _stop(c, intent, n, step["primitive"], drift, outputs)
                if not retry:
                    return _stop(c, intent, n, step["primitive"], refusal, outputs)
                retried, rev = True, _revision(c)
            except errors.HarnessLaunchFailed as failed:
                # Rule 7: the dispatch committed (its run is recorded); the stage stops, the run identity stands.
                return _stop(c, intent, n, step["primitive"], failed, outputs, boundary="launch_failed")
            except errors.AEWError as refusal:
                return _stop(c, intent, n, step["primitive"], refusal, outputs)
        outputs.append(out)
        rev = out["revision"]
    if not final:  # the last step launched: its commit could not also complete the stage
        _end(c, lambda r: c.engine.stage_close(token=c.token(), expect_rev=r, intent=intent))
    return _payload(c, intent, outputs)


def _resolve(c: Call, intent: str, args: dict[str, Any]) -> dict[str, Any]:
    return _resolve_args(c.engine, intent, args)


def _resolve_args(engine: Any, intent: str, args: dict[str, Any]) -> dict[str, Any]:
    """``args`` with each ``{"$from": [m, field]}`` replaced by the one id step ``m`` recorded under ``field``."""
    out: dict[str, Any] = {}
    for name, value in args.items():
        if isinstance(value, dict) and set(value) == {"$from"}:
            m, field = value["$from"]  # its form and order were checked when the intent opened
            steps = engine.stage_intent(intent)["steps"]
            ids = steps[m - 1]["outputs"][field] if 0 < m <= len(steps) else []
            if len(ids) != 1:
                raise errors.IllegalTransition(f"{name} comes from step {m}'s {field}, which recorded {len(ids)} "
                                               "id(s), not one", reason="unresolved_argument", step=m, field=field)
            value = ids[0]
        out[name] = value
    return out


def availability(c: Call, primitive: str, args: dict[str, Any]) -> str:
    """Whether ``primitive`` with ``args`` is legal now, asked of the guard its own commit evaluates: a dispatch
    decision, or a migrated transition or ingest guard (E4). Any other guard is UNKNOWN."""
    return guard_status(c.engine, primitive, args)[0]


def guard_status(engine: Any, primitive: str, args: dict[str, Any]) -> tuple[str, list[str]]:
    """:func:`availability`, with the reason codes of a guard that refuses, or of one that could not answer (M4-E E4:
    ``Engine.guard_query``; ``GUARD_NOT_QUERYABLE``, ``GUARD_QUERY_DEFECT``, ``INTEGRITY_ERROR``, ...)."""
    answer = engine.guard_query(primitive, args.get("work_id"), dict(args))
    return answer["availability"], [] if answer["availability"] == AVAILABLE else list(answer["reason_codes"])


def _unknown_guard(reasons: list[str]) -> dict[str, Any]:
    """The ``guard`` recheck when the guard could not answer: why, by its code (PR #170 re-review, finding 1)."""
    if reasons == [GUARD_NOT_QUERYABLE]:
        message = "its guard has no query form: its own commit decides"
    else:
        message = (f"its guard could not be asked now ({', '.join(reasons) or 'no reason given'}): its own commit "
                   "decides")
    return {"status": UNKNOWN_STATUS, "reason_codes": reasons, "message": message}


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


# ---------------------------------------------------------------------------------------------- resume and resolve
# (M4-E E3c; typed surface §3.4 rule 8: a replacement Lead explicitly continues or abandons, never inferred)

PASSING = ("ok", "not_applicable", "not_queryable")  # not_queryable: the step's own commit decides its guard
UNKNOWN_STATUS = "not_queryable"


def _contract_now(si: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]] | None, list[str]]:
    """The stage contract and plan ``si``'s tool resolves to now: its catalog row's digest and its planner's plan for
    the recorded arguments (``(None, None)`` when this surface has no such stage any more), and the remaining steps'
    primitives that have no step runner here (a continue could not run them)."""
    t, planner = contract.tool(si["tool"]), STAGES.get(si["tool"])
    if t is None or not t.built or planner is None:
        return None, None, []
    plan = [{"primitive": p["primitive"], "args": p.get("args") or {}} for p in planner(dict(si["arguments"]))]
    missing = sorted({p["primitive"] for p in plan[len(si["steps"]):] if p["primitive"] not in STEP_RUNNERS})
    return contract_digest(t), plan, missing


def _runners_check(missing: list[str]) -> dict[str, Any]:
    if not missing:
        return {"status": "ok", "message": "every remaining step has a step runner"}
    return {"status": "no_step_runner", "primitives": missing,
            "message": f"no step runner here for {', '.join(missing)}: a continue could not run the remaining steps"}


def assess(engine: Any, si: dict[str, Any]) -> dict[str, Any]:
    """One unfinished intent as ``resume`` lists it, all result payload (nothing here is advertised in `tools/list`).

    - ``safe_to_continue``: every recheck a continue makes passes now, **counting a check that cannot be answered yet
      as passing**; such checks are listed in ``unknown_checks`` (only ``guard``, when the next step's guard is
      neither a dispatch decision nor migrated to a query, E4: the step's own commit then decides, and a refusal stops
      the stage, rule 3).
    - each recheck (the policy, the stage contract and plan, the step runners, the subject, a launching step's run, the
      continue count, the next step's guard), the next planned step and the boundary a continue would stop at;
    - the call a continue endorses: its bound ``arguments``, ``judgment_inputs`` and classes (#166 review, finding 4);
    - the owning and current generations."""
    digest_now, plan_now, missing = _contract_now(si)
    check = engine.stage_recheck(si["id"], contract_digest=digest_now, plan=plan_now)
    checks = dict(check["checks"])
    checks["runners"] = _runners_check(missing)
    nxt = check["next_step"]
    if nxt is None or check["boundary"] is not None or missing:
        checks["guard"] = {"status": "not_applicable", "message": "no step would run"}
    else:
        try:
            args = _resolve_args(engine, si["id"], nxt.get("args") or {})
        except errors.AEWError as exc:
            checks["guard"] = {"status": "unresolved", "message": exc.message}
        else:
            found, reasons = guard_status(engine, nxt["primitive"], args)
            checks["guard"] = {AVAILABLE: {"status": "ok", "message": "its guard allows it now"},
                               UNKNOWN: _unknown_guard(reasons),
                               BLOCKED: {"status": "blocked", "reason_codes": reasons,
                                         "message": "its guard refuses it now"}}[found]
            checks["guard"]["availability"] = found
    failing = [name for name, v in checks.items() if v["status"] not in PASSING]
    boundary = check["boundary"] or ("refused" if failing else None)
    return {"intent": si["id"], "tool": si["tool"], "subject": si["subject"]["id"], "status": si["status"],
            "arguments": dict(si["arguments"]), "judgment_inputs": list(si["judgment_inputs"]),
            "base_class": si["base_class"], "effective_class": si["effective_class"],
            "steps_committed": len(si["steps"]), "steps_planned": len(si["plan"]),
            "safe_to_continue": not failing, "failing": failing,
            "unknown_checks": [name for name, v in checks.items() if v["status"] == UNKNOWN_STATUS],
            "checks": checks,
            "policy": {"legality_digest": si["binding"]["legality_digest"], "status": checks["policy"]["status"]},
            "next_step": nxt, "boundary": boundary, "owner_generation": check["owner_generation"],
            "current_generation": check["current_generation"], "rebind": check["rebind"],
            "opened": dict(si["opened"]), "rebound": list(si["rebound"])}


def unfinished(engine: Any) -> list[dict[str, Any]]:
    """Every unfinished stage, assessed (``resume``: the typed tool and ``aew resume`` both add it)."""
    return [assess(engine, si) for si in engine.stage_intents_view()]


def resolve_stage(c: Call) -> dict[str, Any]:
    """The ``resolve`` tool for a stage: the current Lead's explicit continue or abandon (rule 8).

    - **abandon** ends the intent ABANDONED; its committed steps stand.
    - **continue** re-resolves the stage contract and plan from this surface's catalog, refuses a next step whose
      guard refuses it now (nothing commits), and has the engine recheck the rest and rebind the intent to the current
      generation in one commit (F18 §14). It then runs the remaining steps from the first uncommitted one, under the
      same rules as a new stage (§3.4 rules 3 to 7). With every step committed, that commit ends the stage itself:
      completed, or stopped as ``launch_failed`` when a launching step's run never started or has ended. A continue
      never relaunches a run: that is `aew harness launch`, which rotates the credential (#142 review)."""
    from aew.surface.run import _error

    a = c.a
    sid = a["subject"]
    si = c.engine.stage_intent(sid)
    c.intent, c.subject, c.binding = sid, si["subject"]["id"], dict(si["binding"])
    if a["choice"] == "abandon":
        c.engine.stage_abandon(token=c.token(), expect_rev=a["expect_rev"], intent=sid, rationale=a["rationale"])
        return _payload(c, sid, [])
    digest_now, plan_now, missing = _contract_now(si)
    if si["status"] == SI.ACTIVE and missing:
        raise errors.IllegalTransition(f"{sid} cannot be continued: {_runners_check(missing)['message']}",
                                       reason="no_step_runner", intent=sid, primitives=missing)
    if si["status"] == SI.ACTIVE and plan_now is not None:
        guard = assess(c.engine, si)["checks"]["guard"]
        if guard["status"] == "blocked":
            raise errors.IllegalTransition(
                f"{sid} cannot be continued: its next step is refused now "
                f"({', '.join(guard['reason_codes']) or 'by its guard'}). Abandon it (committed steps "
                "stand) and decide anew from the projection", reason="next_step_blocked", intent=sid,
                reason_codes=guard["reason_codes"])
    out = c.engine.stage_continue(token=c.token(), expect_rev=a["expect_rev"], intent=sid,
                                  contract_digest=digest_now, plan=plan_now, rationale=a["rationale"])
    if out["status"] == SI.STOPPED:  # the launching step's run never started, or has ended: never completed
        launch = out["launch"]
        failed = errors.HarnessLaunchFailed(launch["message"], run=launch["run"], committed=True,
                                            observed=launch["observed"], reason=launch["status"])
        c.stopped = {"at": c.engine.stage_intent(sid)["steps"][-1]["primitive"], "boundary": "launch_failed",
                     "error": _error(failed)}
    if out["status"] != SI.ACTIVE:
        return _payload(c, sid, [])
    return _run_steps(c, sid, si["plan"], out["next"], out["revision"])
