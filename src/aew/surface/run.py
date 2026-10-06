"""The one runner of the typed Lead surface (typed-lead-surface-design-v0.2 §2, §3.3, §3.6; F15.1).

``run_tool`` is the only code that knows what a tool does: one engine call per built tool in F15.1. A transport
validates nothing of its own beyond framing and calls this; the same function serves the MCP server (through the
Lead broker) and ``aew lead tool``.

Every well-formed call returns a ``StageResult``, engine refusals included: the engine's own code and message, the
steps that committed, and a fresh ``ActionProjection``. A call that is not well formed (an unknown, designed or
concealed tool; arguments outside the tool's schema) raises :class:`~aew.surface.validate.AdapterInputError` before
anything runs. Only an implementation defect escapes as anything else. Nothing is retried in F15.1.

The Lead credential is a separate argument, never part of the context, and reaches only the engine call that needs
it. Results are scrubbed of credential-bearing keys and credential strings before they leave.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from aew import errors
from aew.engine.primitives import spec_for
from aew.harness.contract import redact
from aew.schemas import validate
from aew.surface import SURFACE
from aew.surface.classify import effective_class
from aew.surface.context import SurfaceContext
from aew.surface.projection import project
from aew.surface.validate import check_call

SECRET_KEYS = frozenset({"token", "invocation_token", "offer", "secret", "credential"})
DEFAULT_WAIT_S = 600


class Call:
    """One invocation, as a tool's runner sees it."""

    def __init__(self, engine: Any, ctx: SurfaceContext, arguments: dict[str, Any], token: str | None) -> None:
        self.engine, self.ctx, self.a, self._token = engine, ctx, arguments, token
        self.steps: list[dict[str, Any]] = []
        self.subject: str | None = None

    def token(self) -> str:
        return self._token or ""  # without one the engine refuses the mutation (its own check, its own code)

    def committed(self, primitive: str, out: dict[str, Any], summary: str, refs: list[str]) -> None:
        self.steps.append({"primitive": primitive, "operation_class": spec_for(primitive).operation_class,
                           "revision": out.get("revision"), "summary": summary, "refs": refs})


Runner = Callable[[Call], Any]


def _status(c: Call) -> Any:
    c.subject = c.a.get("work_id")
    return c.engine.status(c.a.get("work_id"))


def _resume(c: Call) -> Any:
    return c.engine.resume(session=c.ctx.lead_session)


def _work_show(c: Call) -> Any:
    c.subject = c.a["work_id"]
    return c.engine.work_show(c.a["work_id"])


def _explain(c: Call) -> Any:
    c.subject = c.a.get("work_id")
    return c.engine.dispatch_explain(c.a.get("work_id") or "", entrypoint=c.a.get("entrypoint"),
                                     role=c.a.get("role"), card=c.a.get("card"),
                                     scope=c.a.get("scope") or "ticket", invocation=c.a.get("invocation"))


def _harness_status(c: Call) -> Any:
    return c.engine.harness_status(c.a.get("invocation"))


def _harness_wait(c: Call) -> Any:
    runs = list(c.a["runs"])
    return c.engine.harness_wait(runs[0] if len(runs) == 1 else runs,
                                 timeout=float(c.a.get("timeout_s") or DEFAULT_WAIT_S), any_=len(runs) > 1)


def _checkpoint(c: Call) -> Any:
    out = c.engine.checkpoint(token=c.token(), expect_rev=c.a["expect_rev"], note=c.a.get("note") or "",
                              next_action=c.a.get("next"))
    c.committed("checkpoint", out, f"checkpoint {out.get('checkpoint')}", [str(out.get("checkpoint"))])
    return out


RUNNERS: dict[str, Runner] = {
    "status": _status, "resume": _resume, "work_show": _work_show, "explain": _explain,
    "harness_status": _harness_status, "harness_wait": _harness_wait, "checkpoint": _checkpoint,
}


def boundary_of(exc: errors.AEWError) -> str:
    """Where an engine refusal stops a call (design §3.3's vocabulary)."""
    if isinstance(exc, errors.StaleRevision):
        return "stale_revision"
    if isinstance(exc, errors.StaleAuthority):
        return "stale_authority"
    if isinstance(exc, errors.PermissionDenied):
        return "permission"
    if isinstance(exc, errors.NotFound):
        return "not_found"
    if isinstance(exc, errors.HarnessLaunchFailed):
        return "launch_failed"
    if isinstance(exc, errors.IllegalTransition | errors.UsageError | errors.ValidationFailed):
        return "refused"
    return "error"


def scrub(value: Any) -> Any:
    """``value`` without credential-bearing keys, and with credential strings redacted."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value


def _error(exc: errors.AEWError) -> dict[str, Any]:
    return {"code": exc.code, "message": redact(exc.message), "details": scrub(dict(exc.details))}


def run_tool(engine: Any, ctx: SurfaceContext, name: Any, arguments: Any, *, token: str | None = None
             ) -> dict[str, Any]:
    """Run one typed tool call and return its ``StageResult`` (or raise ``AdapterInputError`` before anything runs)."""
    t = check_call(name, arguments, ctx.profile)
    call = Call(engine, ctx, copy.deepcopy(arguments), token)
    payload: Any = None
    stopped: dict[str, Any] | None = None
    current = int((engine.store.read().get("lead") or {}).get("generation") or 0)
    if ctx.generation is not None and ctx.generation != current:
        # The caller acts for a Lead generation that is no longer current: nothing runs (the engine would refuse a
        # mutation anyway, and a read must not be presented as the stale Lead's view).
        exc: errors.AEWError = errors.StaleAuthority(
            f"this surface acts for Lead generation {ctx.generation}, but the current generation is {current}",
            generation=ctx.generation, current=current)
        stopped = {"at": t.name, "boundary": boundary_of(exc), "error": _error(exc)}
    else:
        try:
            payload = RUNNERS[t.name](call)
        except errors.AEWError as refusal:
            at = call.steps[-1]["primitive"] if call.steps else t.name
            stopped = {"at": at, "boundary": boundary_of(refusal), "error": _error(refusal)}
    projection = _projection(engine, ctx, call.subject if stopped is None else None)
    result = {
        "ok": stopped is None, "surface": SURFACE, "tool": t.name, "base_operation_class": t.base_class,
        "effective_operation_class": effective_class(t, call.a), "revision": projection["revision"],
        "generation": projection["generation"], "stage_intent_id": None, "policy_binding": None,
        "completed_steps": call.steps, "stopped": stopped,
        "result": scrub(payload) if isinstance(payload, dict) else None, "projection": projection,
    }
    validate("surface", result, source=f"the {t.name} result")
    return result


def _projection(engine: Any, ctx: SurfaceContext, subject: str | None) -> dict[str, Any]:
    """The projection for the call's subject, or for the project when the subject cannot be projected (a refused
    call naming a unit that does not exist)."""
    if subject:
        try:
            return project(engine, ctx, subject)
        except errors.NotFound:
            pass
    return project(engine, ctx, None)
