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

Inside a Lead session the broker passes two hooks for ``harness_wait`` (F15.1 plan §4.3): ``serial``, the section in
which every engine call runs, and ``cancelled``, why the session's authority has gone (or ``None``). The wait then
observes the runs in single serialized checks and blocks between them on the wake file alone, so a long wait never
holds the broker. Without hooks (an operator's own shell) the engine's own blocking wait is used.
"""

from __future__ import annotations

import contextlib
import copy
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from aew import errors
from aew.engine import outbox
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
OBSERVE_EVERY_S = 2.0  # a cooperative wait re-checks the runs at least this often, as the engine's own wait does
TICK_S = 0.025

Serial = Callable[[], AbstractContextManager[Any]]
RunCli = Callable[[list[str], str], dict[str, Any]]  # (argv, stdin) -> {"result", "json"}: the broker's run_cli


class Call:
    """One invocation, as a tool's runner sees it."""

    def __init__(self, engine: Any, ctx: SurfaceContext, arguments: dict[str, Any], token: str | None, *,
                 serial: Serial | None = None, cancelled: Callable[[], str | None] | None = None,
                 run_cli: RunCli | None = None) -> None:
        self.engine, self.ctx, self.a, self._token = engine, ctx, arguments, token
        self.serial: Serial = serial or contextlib.nullcontext
        self.cancelled = cancelled
        self.run_cli = run_cli
        self.steps: list[dict[str, Any]] = []
        self.subject: str | None = None
        self.unsuccessful: dict[str, Any] | None = None  # a command that answered ``ok: false`` (the cli escape)

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
    target: str | list[str] = runs[0] if len(runs) == 1 else runs
    timeout = float(c.a.get("timeout_s") or DEFAULT_WAIT_S)
    if c.cancelled is None:  # no broker to keep free: the engine's own blocking wait
        return c.engine.harness_wait(target, timeout=timeout, any_=len(runs) > 1)
    deadline = time.monotonic() + timeout
    wake_root = Path(c.engine.aew_root)
    while True:
        with c.serial():  # one two-lane check (a timeout of 0 checks exactly once)
            why = c.cancelled()
            if why:
                raise errors.StaleAuthority(f"this Lead session no longer holds Lead authority: {why}")
            out = c.engine.harness_wait(target, timeout=0, any_=len(runs) > 1)
        if not out.get("timed_out") or time.monotonic() >= deadline:
            return out
        mark, since = outbox.wake_mark(wake_root), time.monotonic()  # block on the wake file alone: no engine state
        while time.monotonic() < min(deadline, since + OBSERVE_EVERY_S):
            time.sleep(TICK_S)
            if outbox.wake_mark(wake_root) != mark:
                break


def _cli(c: Call) -> Any:
    """The recovery escape: one `aew` command through the broker's own ``run_cli``, with every refusal it has. What
    it changed is the command's own answer; its revision is reported when the command states one.

    A command that answers ``ok: false`` (the direct CLI exits nonzero for it) did not do what was asked, though it
    may have committed something on the way (``integrate publish`` after the head moved commits one rebuild and asks
    for revalidation): its step stays recorded and the call stops there, never reported as a success (PR #93
    review)."""
    if c.run_cli is None:
        raise errors.UsageError("the cli escape needs the Lead broker or an operator's own credential")
    argv = list(c.a["argv"])
    reply = c.run_cli(argv, c.a.get("stdin") or "")
    output = reply.get("result")
    revision = output.get("revision") if isinstance(output, dict) else None
    words = next((argv[:i] for i, a in enumerate(argv) if a.startswith("-")), argv)[:3]  # the command, not values
    c.steps.append({"primitive": "aew " + " ".join(words),
                    "operation_class": spec_for("cli").operation_class,
                    "revision": revision if isinstance(revision, int) else None,
                    "summary": "a primitive command (recovery)", "refs": []})
    if isinstance(output, dict) and output.get("ok") is False:
        problems = output.get("problems")
        message = output.get("next") or ("; ".join(map(str, problems)) if isinstance(problems, list) else "")
        c.unsuccessful = {"code": "NOT_COMPLETED", "message": str(message or "the command answered ok: false"),
                          "details": {}}
    return {"argv": argv, "output": output}


def _checkpoint(c: Call) -> Any:
    out = c.engine.checkpoint(token=c.token(), expect_rev=c.a["expect_rev"], note=c.a.get("note") or "",
                              next_action=c.a.get("next"))
    c.committed("checkpoint", out, f"checkpoint {out.get('checkpoint')}", [str(out.get("checkpoint"))])
    return out


def _steering(c: Call) -> Any:
    """The Lead's own steering (M4-E E2; A1 §1.2): lower its mode, or record a request. A request grants nothing; only
    the operator raises or confirms, at the operator endpoint."""
    action = c.a["action"]
    if action == "lower":
        out = c.engine.steering_lower(token=c.token(), expect_rev=c.a["expect_rev"], mode=c.a["mode"],
                                      rationale=c.a.get("rationale") or "")
        c.committed("steering", out, f"steering mode lowered to {out.get('mode')}", [str(out.get("record"))])
        return out
    kind = "raise" if action == "request_raise" else "confirmation"
    out = c.engine.steering_request(token=c.token(), expect_rev=c.a["expect_rev"], kind=kind,
                                    rationale=c.a["rationale"], mode=c.a.get("mode"), action_ref=c.a.get("action_ref"))
    c.committed("steering", out, f"steering request {out.get('request')} recorded (grants nothing)",
                [str(out.get("request"))])
    return out


RUNNERS: dict[str, Runner] = {
    "status": _status, "resume": _resume, "work_show": _work_show, "explain": _explain,
    "harness_status": _harness_status, "harness_wait": _harness_wait, "checkpoint": _checkpoint,
    "steering": _steering, "cli": _cli,
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


def run_tool(engine: Any, ctx: SurfaceContext, name: Any, arguments: Any, *, token: str | None = None,
             serial: Serial | None = None, cancelled: Callable[[], str | None] | None = None,
             run_cli: RunCli | None = None) -> dict[str, Any]:
    """Run one typed tool call and return its ``StageResult`` (or raise ``AdapterInputError`` before anything runs).

    ``serial`` and ``cancelled`` are the broker's hooks for a cooperative wait (module docstring); ``run_cli`` runs
    the recovery escape's command with the broker's refusals."""
    t = check_call(name, arguments, ctx.profile)
    call = Call(engine, ctx, copy.deepcopy(arguments), token, serial=serial, cancelled=cancelled, run_cli=run_cli)
    payload: Any = None
    stopped: dict[str, Any] | None = None
    with call.serial():
        stale = _stale(engine, ctx)
    if stale is not None:
        # Nothing runs: the engine would refuse a mutation, and a read must not be presented as the lost Lead's view.
        stopped = {"at": t.name, "boundary": boundary_of(stale), "error": _error(stale)}
    else:
        try:
            payload = RUNNERS[t.name](call)
        except errors.AEWError as refusal:
            at = call.steps[-1]["primitive"] if call.steps else t.name
            stopped = {"at": at, "boundary": boundary_of(refusal), "error": _error(refusal)}
        if stopped is None and call.unsuccessful is not None:
            stopped = {"at": call.steps[-1]["primitive"], "boundary": "refused", "error": call.unsuccessful}
    with call.serial():
        projection = _projection(engine, ctx, call.subject if stopped is None else None)
    # The whole result is scrubbed, not only the payload: the projection's hints and the engine's messages carry
    # authored text too (PR #88 review).
    result = scrub({
        "ok": stopped is None, "surface": SURFACE, "tool": t.name, "base_operation_class": t.base_class,
        "effective_operation_class": effective_class(t, call.a), "revision": projection["revision"],
        "generation": projection["generation"], "stage_intent_id": None, "policy_binding": None,
        "completed_steps": call.steps, "stopped": stopped,
        "result": payload if isinstance(payload, dict) else None, "projection": projection,
    })
    validate("surface", result, source=f"the {t.name} result")
    return result


def _stale(engine: Any, ctx: SurfaceContext) -> errors.AEWError | None:
    """Why the caller no longer acts for the current Lead, or ``None``: its session reports lost authority, or it
    acts for a generation that is no longer current."""
    session = ctx.lead_session
    if session is not None and not session.get("holds"):
        return errors.StaleAuthority("this Lead session no longer holds Lead authority: "
                                     f"{session.get('detail') or 'the seat moved on'}")
    current = int((engine.store.read().get("lead") or {}).get("generation") or 0)
    if ctx.generation is not None and ctx.generation != current:
        return errors.StaleAuthority(
            f"this surface acts for Lead generation {ctx.generation}, but the current generation is {current}",
            generation=ctx.generation, current=current)
    return None


def _projection(engine: Any, ctx: SurfaceContext, subject: str | None) -> dict[str, Any]:
    """The projection for the call's subject, or for the project when the subject cannot be projected (a refused
    call naming a unit that does not exist)."""
    if subject:
        try:
            return project(engine, ctx, subject)
        except errors.NotFound:
            pass
    return project(engine, ctx, None)
