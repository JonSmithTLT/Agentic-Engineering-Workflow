"""The StageIntent journal (M4-E E3; plan v3 E3 and §2.7; typed Lead surface design v0.2 §3.4).

A stage call (a typed tool that expands into several primitives) opens an intent as its first commit, by CAS on the
caller's expected revision (rules 1 and 2), binding the call, the state it started from and its planned steps. Each
step then commits with its primitive, in the same transaction: the surface arms :func:`step` around exactly one
primitive call, and this module's finalizer records the step, or refuses the commit, before the transaction lands.
So the journal never claims a step that did not commit, and a step never commits outside its journal.

The finalizer refuses a step whose intent is no longer ACTIVE, whose owning Lead generation is not the current one
(a takeover never continues a stage implicitly: F18 §14), whose key is already recorded (the idempotency key
``<SI>:<n>``: a continued stage never repeats a committed step), that is out of plan order, whose commit is not its
planned primitive's (``step_primitive_mismatch``), whose primitive commits a second time in one armed block
(``step_commits_twice``), that retries a judgment-bearing step or any step of a judgment-bearing stage
(``judgment_replay``: rules 4 and 5), or whose bound legality digest no longer holds (STALE_POLICY: rule 6). The
operational digest is recorded with each step, never enforced.

An intent is hot (control state ``stage_intents``) only while ACTIVE. It ends COMPLETED (every planned step
committed), STOPPED_AT_BOUNDARY (stopped after one or more steps), REFUSED (stopped before any) or ABANDONED (closed by
the Lead's ``resolve``), and in that same commit it is written whole and immutable to its cold home and leaves the hot
state (§2.7):

- a unit subject still hot: ``work/<T>/stage-intents/<SI>.yaml``, with a pointer ``{id, tool, status, path, sha256,
  closed_rev}`` on the unit, which archival carries into the unit's bundle (and the bundle's pins and links);
- a unit subject already archived: the same file, and a history annotation on the unit that names it and its hash;
- no unit (a stage that created none, a project-scoped one): ``records/stage-intents/<SI>.yaml``.

A stop the runner cannot record leaves the intent ACTIVE, for ``resume`` and the Lead's ``resolve``: a crash, a seat
lost to a takeover, or policy drift pending adoption (every Lead commit is refused then, ``lead_txn``).

Resolving an ACTIVE intent (E3c) is the current Lead's explicit choice, never inferred from state (rule 8):

- **abandon** ends it ABANDONED; committed steps are never undone;
- **continue** rechecks it (:meth:`StageIntents.recheck`, the one function ``resume`` reads too): the legality digest it
  bound, the stage contract and plan the surface re-resolves now, the subject unit as its last step left it (another
  primitive moved it: refused), and the run of a launching last step. Authority is the caller's credential and its
  revision the CAS of ``lead_txn``. It then rebinds the intent to the current Lead generation (F18 §14), recorded in
  ``rebound``, and the surface resumes from the first uncommitted step. A launching step's run with no supervisor
  record, or one that is no longer starting or running, is ``launch_failed``: the continue stops the intent there in
  the same commit and never completes it over a run that never started. It never relaunches: a relaunch is the Lead's
  ``harness.launch``, which rotates the credential, so the one lost with the crashed launcher is never used (#142
  review).

The engine never imports the typed surface (tests/unit/test_surface_contract.py): the surface hands the engine plain
data, and this module checks it against the engine's own primitive declarations.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import yaml

from aew.engine import primitives as P
from aew.engine.base import TxnContext
from aew.errors import AEWError, IllegalTransition, IntegrityError, NotFound, StaleAuthority, StalePolicy, UsageError
from aew.harness import contract as K
from aew.harness import runlog
from aew.knowledge.records import format_id
from aew.schemas import validate
from aew.util import load_yaml, sha256_bytes, utc_now

SCHEMA = "aew/stage-intent/v1"
ACTIVE = "ACTIVE"
COMPLETED, STOPPED, REFUSED, ABANDONED = "COMPLETED", "STOPPED_AT_BOUNDARY", "REFUSED", "ABANDONED"
TERMINAL = (COMPLETED, STOPPED, REFUSED, ABANDONED)
RECORDS_DIR = "records/stage-intents"
MAX_STEPS = 16
MAX_REBINDS = 16  # explicit continues of one intent (the schema's bound); past it, abandon and decide anew
LIVE_RUN = (K.STARTING, K.RUNNING)  # a launching step's run its supervisor still holds: anything else never started
OK, NOT_APPLICABLE = "ok", "not_applicable"
CHANNELS = ("mcp", "cli", "direct", "test")  # the surface's ingresses (SurfaceContext), and tests' own
OUTPUTS = ("units", "invocations", "runs")  # what a step records it created, and what a later step may name
REFERENCE = "$from"  # a planned argument {"$from": [m, field]}: the one id step m recorded under field


def cold_rel(intent_id: str, work_id: str | None) -> str:
    """Where an ended intent lives: under its unit, or in ``records/`` when it has none."""
    return f"work/{work_id}/stage-intents/{intent_id}.yaml" if work_id else f"{RECORDS_DIR}/{intent_id}.yaml"


def digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def step_key(intent_id: str, n: int) -> str:
    return f"{intent_id}:{n}"


# ---------------------------------------------------------------------------------------------- the step binding


@dataclass
class StepBinding:
    """One planned step about to run: the surface arms it around exactly one primitive call."""

    intent: str
    n: int
    retried: bool = False
    final: bool = False
    used: bool = field(default=False, compare=False)

    @property
    def key(self) -> str:
        return step_key(self.intent, self.n)


_STEP: ContextVar[StepBinding | None] = ContextVar("aew_stage_step", default=None)


@contextmanager
def step(intent: str, n: int, *, retried: bool = False, final: bool = False) -> Iterator[StepBinding]:
    """Arm step ``n`` of ``intent`` for the primitive called inside the block: its commit records the step (or is
    refused). ``final``: the step is the plan's last and has no effect after its commit, so the same commit completes
    the intent. A primitive that commits twice inside one block is refused at its second commit."""
    binding = StepBinding(intent, n, retried=retried, final=final)
    token = _STEP.set(binding)
    try:
        yield binding
    finally:
        _STEP.reset(token)


def unit_state(unit: dict[str, Any] | None) -> dict[str, Any] | None:
    if not unit or not unit.get("record_sha256"):
        return None
    return {"state": unit["state"], "record_sha256": unit["record_sha256"]}


# ---------------------------------------------------------------------------------------------- the collaborator


class StageIntents:
    def __init__(self, k: Any, *, archive: Any) -> None:
        self.k = k
        self.archive = archive

    # ------------------------------------------------------------------ opening and closing (Lead transactions)

    def open(self, *, token: str, expect_rev: int, tool: str, contract_digest: str, arguments: dict[str, Any],
             judgment_inputs: list[str], base_class: str, effective_class: str, plan: list[dict[str, Any]],
             subject: str | None, ingress: str) -> dict[str, Any]:
        """Open an intent as the stage's first commit (rules 1 and 2): a stale ``expect_rev`` commits nothing. Every
        planned primitive must be declared (an undeclared one is judgment-bearing and has no step runner: fail
        closed), and a unit has at most one ACTIVE intent (a stage is never stacked over an unresolved one)."""
        if ingress not in CHANNELS:
            raise UsageError(f"unknown ingress {ingress!r}", allowed=list(CHANNELS))
        if not plan or len(plan) > MAX_STEPS:
            raise UsageError(f"a stage plans 1 to {MAX_STEPS} steps; this one plans {len(plan)}")
        if base_class not in P.CLASS_RANK or effective_class not in P.CLASS_RANK:
            raise UsageError("a stage's base and effective class are operation classes",
                             allowed=list(P.OPERATION_CLASSES))
        with self.k.lead_txn(token, expect_rev, "stage.open") as ctx:
            state = ctx.state
            if subject is not None and subject not in state["work"]:
                raise NotFound(f"no hot work unit {subject}: a stage's subject is a unit in flight", work_id=subject)
            for other in (state.get("stage_intents") or {}).values():
                if other["subject"]["id"] == subject:  # one per unit, and one with no unit (§2.7: bounded)
                    raise IllegalTransition(
                        f"{subject or 'the project'} already has an unfinished stage, {other['id']} "
                        f"({other['tool']}): resolve it "
                        "first (`resolve` with continue or abandon, or `aew stage continue|abandon`)",
                        reason="open_intent", intent=other["id"])
            steps = []
            state["counters"]["stage_intent"] = state["counters"].get("stage_intent", 0) + 1
            sid = format_id("SI", state["counters"]["stage_intent"])
            for n, planned in enumerate(plan, start=1):
                _check_references(n, planned.get("args") or {})
                spec = P.spec_for(planned["primitive"])
                if spec.primitive_id in P.NOT_STEPS:
                    raise IllegalTransition(f"step {n}, {planned['primitive']}, cannot run as one stage step: "
                                            f"{P.NOT_STEPS[spec.primitive_id]}",
                                            reason="not_a_step", primitive=planned["primitive"])
                if not spec.declared:
                    raise IllegalTransition(f"step {n}, {planned['primitive']}, is not a declared primitive: a stage "
                                            "runs declared primitives only (fail closed)",
                                            reason="undeclared_primitive", primitive=planned["primitive"])
                steps.append({"n": n, "primitive": spec.primitive_id, "operation_class": spec.operation_class,
                              "key": step_key(sid, n), **({"args": planned["args"]} if "args" in planned else {})})
            floor = max([P.CLASS_RANK[base_class], *(P.CLASS_RANK[s["operation_class"]] for s in steps)])
            if P.CLASS_RANK[effective_class] < floor:
                # R5-1 retries only a non-judgment stage: an effective class below its own row or its steps would
                # let a judgment be replayed (§3.4 rules 4 and 5; #140 review, finding 2).
                raise IllegalTransition(
                    f"a stage's effective class is at least its base class and each step's; {effective_class} is "
                    f"below {P.OPERATION_CLASSES[floor]}", reason="class_understated")
            d = self.k.policy_digests()
            intent = {
                "schema": SCHEMA, "id": sid, "tool": tool, "status": ACTIVE, "contract_digest": contract_digest,
                "arguments": arguments, "arguments_digest": digest(arguments), "judgment_inputs": list(judgment_inputs),
                "base_class": base_class, "effective_class": effective_class, "ingress": ingress,
                "caller": dict(ctx.actor), "generation": state["lead"]["generation"],
                "opened": {"expect_rev": expect_rev, "rev": ctx.session.revision + 1, "at": utc_now()},
                "binding": {"legality_digest": d["legality_digest"], "operational_digest": d["operational_digest"],
                            "authorization_digest": None, "obligations_digest": None, "lease": None},
                "subject": {"kind": "unit" if subject else "project", "id": subject,
                            "start": unit_state(state["work"].get(subject)) if subject else None},
                "plan": steps, "steps": [], "retried_after_stale_revision": False, "stopped": None, "rebound": [],
                "resolution": None, "closed": None}
            self._validate(intent)
            state.setdefault("stage_intents", {})[sid] = intent
            ctx.summary = f"stage {tool} opened as {sid}: {len(steps)} step(s)"
            ctx.refs.append(sid)
            revision = ctx.session.revision + 1
        return {"intent": sid, "revision": revision, "binding": dict(intent["binding"])}

    def stop(self, *, token: str, expect_rev: int, intent: str, n: int, boundary: str, code: str, message: str,
             reason: str | None = None) -> dict[str, Any]:
        """Record that the stage stopped at step ``n`` (rule 3: the first refusal stops it), and end the intent:
        REFUSED when no step committed, STOPPED_AT_BOUNDARY otherwise. Committed steps stand."""
        with self.k.lead_txn(token, expect_rev, "stage.stop") as ctx:
            si = self._active(ctx.state, intent, owner=True)
            done = len(si["steps"])
            # The stop is at the next step, or at the last when every step committed and what followed its commit
            # failed (a launch: rule 7). Never at a step that does not exist (#140 review, finding 3).
            if n != done + 1 and not (n == done == len(si["plan"])):
                raise IllegalTransition(f"{intent} cannot stop at step {n}: it committed {done} of "
                                        f"{len(si['plan'])} step(s)", reason="stop_out_of_order")
            si["stopped"] = {"n": n, "boundary": boundary,
                             "error": {"code": code, "message": message[:2000], "reason": reason},
                             "rev": ctx.session.revision + 1, "at": utc_now()}
            status = STOPPED if si["steps"] else REFUSED
            self._end(ctx, si, status)
            ctx.summary = f"stage {si['tool']} ({intent}) stopped at step {n}: {boundary}"
            ctx.refs.append(intent)
            revision = ctx.session.revision + 1
        return {"intent": intent, "status": status, "revision": revision}

    def close(self, *, token: str, expect_rev: int, intent: str) -> dict[str, Any]:
        """End an intent whose every planned step committed, when its last step had an effect after its commit (a
        launch): the commit that records the step cannot also say the stage completed."""
        with self.k.lead_txn(token, expect_rev, "stage.close") as ctx:
            si = self._active(ctx.state, intent, owner=True)
            if len(si["steps"]) != len(si["plan"]):
                raise IllegalTransition(f"{intent} has {len(si['plan']) - len(si['steps'])} step(s) still to run: "
                                        "only a stage whose every step committed completes", reason="incomplete")
            self._end(ctx, si, COMPLETED)
            ctx.summary = f"stage {si['tool']} ({intent}) completed"
            ctx.refs.append(intent)
            revision = ctx.session.revision + 1
        return {"intent": intent, "status": COMPLETED, "revision": revision}

    def abandon(self, *, token: str, expect_rev: int, intent: str, rationale: str) -> dict[str, Any]:
        """Close an intent without running its remaining steps: committed steps are never undone. The current Lead
        may abandon any ACTIVE intent, its own or one a superseded generation left (F18 §14)."""
        if not (rationale and rationale.strip()):
            raise UsageError("abandoning a stage needs a rationale")
        with self.k.lead_txn(token, expect_rev, "stage.abandon") as ctx:
            si = self._active(ctx.state, intent)
            si["resolution"] = {"choice": "abandon", "rationale": rationale.strip()[:2000],
                                "generation": ctx.state["lead"]["generation"], "rev": ctx.session.revision + 1,
                                "at": utc_now()}
            self._end(ctx, si, ABANDONED)
            ctx.summary = f"stage {si['tool']} ({intent}) abandoned after {len(si['steps'])} step(s)"
            ctx.refs.append(intent)
            revision = ctx.session.revision + 1
        return {"intent": intent, "status": ABANDONED, "revision": revision}

    def continue_(self, *, token: str, expect_rev: int, intent: str, contract_digest: str | None,
                  plan: list[dict[str, Any]] | None, rationale: str) -> dict[str, Any]:
        """The current Lead's explicit continue (rule 8; F18 §14): every recheck must pass now, or nothing commits and
        the intent stays ACTIVE for another choice. ``contract_digest`` and ``plan`` are the stage contract and plan
        the surface re-resolved from its catalog now (``None``: it has none for this tool any more).

        The commit rebinds the intent to the current generation. With steps still to run it stays ACTIVE, and the
        surface runs them from the first uncommitted one. With every step committed, it ends here: COMPLETED when the
        last step launched nothing or its run's supervisor still holds it, and STOPPED_AT_BOUNDARY as
        ``launch_failed`` when that run has no supervisor record or has ended (a crash between the launching
        assignment's commit and its supervisor's start: #142 review). A launching step followed by others is checked
        the same way, so no later step runs over a run that never started."""
        if not (rationale and rationale.strip()):
            raise UsageError("continuing a stage needs a rationale")
        with self.k.lead_txn(token, expect_rev, "stage.continue") as ctx:
            state = ctx.state
            si = self._active(state, intent)
            check = self.recheck(state, si, contract_digest=contract_digest, plan=plan)
            _refuse_unless_continuable(si, check)
            rev = ctx.session.revision + 1
            generation = state["lead"]["generation"]
            at = utc_now()
            si["rebound"].append({"from_generation": si["generation"], "to_generation": generation, "rev": rev,
                                  "at": at, "rationale": rationale.strip()[:2000]})
            si["generation"] = generation
            si["resolution"] = {"choice": "continue", "rationale": rationale.strip()[:2000], "generation": generation,
                                "rev": rev, "at": at}
            done, planned = len(si["steps"]), len(si["plan"])
            launch = check["checks"]["launch"]
            if launch["status"] not in (OK, NOT_APPLICABLE):
                si["stopped"] = {"n": done + 1 if done < planned else done, "boundary": "launch_failed",
                                 "error": {"code": "HARNESS_LAUNCH_FAILED", "message": launch["message"][:2000],
                                           "reason": launch["status"]},
                                 "rev": rev, "at": at}
                self._end(ctx, si, STOPPED)
                status = STOPPED
            elif done == planned:
                self._end(ctx, si, COMPLETED)
                status = COMPLETED
            else:
                self._validate(si)
                status = ACTIVE
            ctx.summary = (f"stage {si['tool']} ({intent}) continued by Lead generation {generation}: "
                           + {ACTIVE: f"from step {done + 1}", COMPLETED: "completed",
                              STOPPED: "its launch failed"}[status])
            ctx.refs.append(intent)
        return {"intent": intent, "status": status, "revision": rev, "next": done + 1, "generation": generation,
                "launch": launch}

    # ------------------------------------------------------------------ the rechecks (continue and resume)

    def recheck(self, state: dict[str, Any], si: dict[str, Any], *, contract_digest: str | None,
                plan: list[dict[str, Any]] | None) -> dict[str, Any]:
        """What continuing ``si`` would meet now, read from committed state and the run telemetry of its launching
        step: each recheck's status (``ok``, ``not_applicable`` or why not, with a message), the owning and current
        generations, the next planned step, and the boundary a continue would stop at (``None``: it runs the next
        step; ``completed``: nothing is left to run). The continue's own commit calls this on its transaction's state,
        and ``resume`` on the committed state, so the two never disagree. The guard of the next step is the
        surface's to ask (its availability); this reads no guard."""
        steps, planned = si["steps"], si["plan"]
        checks: dict[str, dict[str, Any]] = {}
        try:
            current = self.k.policy_digests()["legality_digest"]
        except IntegrityError as exc:  # a policy edit nobody adopted yet: every Lead commit is refused meanwhile
            checks["policy"] = {"status": "pending_adoption", "message": exc.message}
        except AEWError as exc:
            checks["policy"] = {"status": "unreadable", "message": exc.message}
        else:
            bound = si["binding"]["legality_digest"]
            checks["policy"] = {"status": OK, "message": "the legality digest it bound is in force"} if (
                current == bound) else {"status": "stale_policy", "bound": bound, "current": current,
                                        "message": "the legality policy changed since it opened"}
        if contract_digest is None:
            checks["contract"] = {"status": "unknown_stage",
                                  "message": f"the surface no longer has a stage {si['tool']} to continue"}
        elif contract_digest != si["contract_digest"]:
            checks["contract"] = {"status": "changed", "message": f"stage {si['tool']}'s contract changed since "
                                                                  "it opened"}
        elif plan is not None and _plan_of(plan) != _plan_of(si["plan"]):
            checks["contract"] = {"status": "plan_changed", "message": f"stage {si['tool']} now plans other steps "
                                                                       "for the same call"}
        else:
            checks["contract"] = {"status": OK, "message": "the stage contract and plan re-resolve unchanged"}
        subject = si["subject"]
        if subject["kind"] != "unit":
            checks["subject"] = {"status": NOT_APPLICABLE, "message": "a project stage"}
        else:
            unit = state["work"].get(subject["id"])
            expected = steps[-1]["subject_after"] if steps else subject["start"]
            if unit is None:
                checks["subject"] = {"status": "gone", "message": f"{subject['id']} is no longer in flight"}
            elif unit_state(unit) != expected:
                checks["subject"] = {"status": "moved", "expected": expected, "now": unit_state(unit),
                                     "message": f"{subject['id']} changed since the stage's last step (another "
                                                "primitive moved it)"}
            else:
                checks["subject"] = {"status": OK, "message": f"{subject['id']} is as the last step left it"}
        checks["launch"] = self._launch_check(steps[-1] if steps else None)
        checks["rebinds"] = {"status": OK, "message": f"{len(si['rebound'])} of {MAX_REBINDS} continues used"} if (
            len(si["rebound"]) < MAX_REBINDS) else {"status": "exhausted",
                                                     "message": f"continued {MAX_REBINDS} times already"}
        nxt = planned[len(steps)] if len(steps) < len(planned) else None
        boundary = None
        if checks["policy"]["status"] == "stale_policy":
            boundary = "stale_policy"
        elif checks["policy"]["status"] != OK:
            boundary = "error"
        elif any(checks[c]["status"] not in (OK, NOT_APPLICABLE) for c in ("contract", "subject", "rebinds")):
            boundary = "refused"
        elif checks["launch"]["status"] not in (OK, NOT_APPLICABLE):
            boundary = "launch_failed"
        elif nxt is None:
            boundary = "completed"
        return {"intent": si["id"], "checks": checks, "owner_generation": si["generation"],
                "current_generation": state["lead"]["generation"],
                "rebind": si["generation"] != state["lead"]["generation"],
                "next_step": None if nxt is None else {k: nxt[k] for k in ("n", "primitive", "operation_class", "key")}
                | ({"args": nxt["args"]} if "args" in nxt else {}),
                "boundary": boundary}

    def recheck_active(self, state: dict[str, Any], intent: str, *, contract_digest: str | None,
                       plan: list[dict[str, Any]] | None) -> dict[str, Any]:
        """:meth:`recheck` of the unfinished intent ``intent`` (NOT_FOUND when it has ended or never existed)."""
        return self.recheck(state, self._active(state, intent), contract_digest=contract_digest, plan=plan)

    def _launch_check(self, last: dict[str, Any] | None) -> dict[str, Any]:
        """The run of a launching last step: its supervisor must still hold it (starting or running). No record
        means no supervisor ever ran; any other status means the run is not live. Only the last committed step can
        hold a run that never started: the executor runs no further step until a launch is in its supervisor's
        custody (#142 review, finding 1)."""
        runs = (last or {}).get("outputs", {}).get("runs") or []
        if not runs:
            return {"status": NOT_APPLICABLE, "message": "its last committed step launched no run"}
        for run in runs:
            observed, _ = runlog.observed_status(runlog.run_dir(self.k.aew_root, run))
            if observed not in LIVE_RUN:
                why = ("no supervisor ever recorded it" if observed == K.UNCONFIRMED
                       else f"its supervisor's record says {observed}")
                return {"status": "no_supervisor" if observed == K.UNCONFIRMED else "not_live", "run": run,
                        "observed": observed,
                        "message": f"step {last['n'] if last else '?'} recorded {run}, but {why}: the launch failed. "
                                   "Relaunch it with `aew harness launch` (the credential rotates), or abandon"}
        return {"status": OK, "runs": list(runs), "message": "its launching step's run is held by its supervisor"}

    # ------------------------------------------------------------------ the step finalizer

    def finalize(self, ctx: TxnContext) -> None:
        """Record the armed step in the commit of its primitive, or refuse that commit. First of the finalizers: a
        refused step is reported for what it is (STALE_POLICY, a stale owner) before any other finalizer judges the
        commit, and a completed intent's pointer is on its unit before archival bundles the unit."""
        binding = _STEP.get()
        if binding is None:
            return
        if binding.used:
            raise IllegalTransition(f"step {binding.key} already committed in this call: a primitive that commits "
                                    "twice cannot run as one stage step", reason="step_commits_twice")
        state = ctx.state
        si = (state.get("stage_intents") or {}).get(binding.intent)
        if si is None or si["status"] != ACTIVE:
            raise IllegalTransition(f"{binding.intent} is not an unfinished stage: no step of it can commit",
                                    reason="terminal", intent=binding.intent)
        if si["generation"] != state["lead"]["generation"]:
            raise StaleAuthority(
                f"{binding.intent} belongs to Lead generation {si['generation']}; this is generation "
                f"{state['lead']['generation']}. A stage is never continued implicitly after a takeover: the current "
                "Lead resolves it (`resolve` continue or abandon)", reason="not_owner", intent=binding.intent)
        if any(s["key"] == binding.key for s in si["steps"]):
            raise IllegalTransition(f"step {binding.key} already committed: a continued stage never repeats one",
                                    reason="step_already_committed", key=binding.key)
        if binding.n != len(si["steps"]) + 1 or binding.n > len(si["plan"]):
            raise IllegalTransition(f"{binding.key} is out of order: {binding.intent} has committed "
                                    f"{len(si['steps'])} of {len(si['plan'])} step(s)", reason="step_out_of_order")
        planned = si["plan"][binding.n - 1]
        if ctx.txn_op not in P.commit_ops(planned["primitive"]) or (
                planned["primitive"] in P.BY_DECISION
                and not any(d.allowed and d.entrypoint == planned["primitive"] for d in ctx.dispatch_decisions)):
            raise IllegalTransition(f"{binding.key} plans {planned['primitive']}; this commit is {ctx.txn_op}: a step "
                                    "commits only its planned primitive (#140 review, finding 1)",
                                    reason="step_primitive_mismatch", planned=planned["primitive"], op=ctx.txn_op)
        if binding.retried and P.JUDGMENT_BEARING in (planned["operation_class"], si["effective_class"]):
            raise IllegalTransition(f"{binding.key} is judgment-bearing or in a judgment-bearing stage: it is never "
                                    "retried after a stale revision (§3.4 rules 4 and 5)", reason="judgment_replay")
        d = self.k.policy_digests()
        if d["legality_digest"] != si["binding"]["legality_digest"]:
            raise StalePolicy(
                f"the legality policy changed since {binding.intent} opened: step {binding.n} ({planned['primitive']}) "
                "is not committed. Read the projection again and decide anew", intent=binding.intent,
                bound=si["binding"]["legality_digest"], current=d["legality_digest"])
        before = ctx.session.committed_view()
        subject = si["subject"]
        outputs = {"units": sorted(set(state["work"]) - set(before["work"])),
                   "invocations": sorted(set(state["invocations"]) - set(before["invocations"])),
                   "runs": sorted(_runs(state) - _runs(before))}
        if subject["kind"] == "project" and len(outputs["units"]) == 1:
            # A stage that creates its unit (ticket_draft) is that unit's from then on (TRA-25 waits for F4).
            subject.update(kind="unit", id=outputs["units"][0])
        record = {"n": binding.n, "key": binding.key, "primitive": planned["primitive"],
                  "operation_class": planned["operation_class"], "revision": ctx.session.revision + 1,
                  "refs": list(ctx.refs)[:64], "summary": ctx.summary, "outputs": outputs,
                  "subject_after": unit_state(state["work"].get(subject["id"])) if subject["id"] else None,
                  "legality_digest": d["legality_digest"], "operational_digest": d["operational_digest"],
                  "at": utc_now()}
        if binding.retried:
            record["retried_after_stale_revision"] = True
            si["retried_after_stale_revision"] = True
        si["steps"].append(record)
        binding.used = True
        if binding.final and len(si["steps"]) == len(si["plan"]):
            self._end(ctx, si, COMPLETED)

    # ------------------------------------------------------------------ reads

    def view(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """The unfinished intents, from the hot state alone (resume and status read nothing cold)."""
        return [dict(si) for _, si in sorted((state.get("stage_intents") or {}).items())]

    def read(self, state: dict[str, Any], intent: str) -> dict[str, Any]:
        """An intent wherever it lives, found without scanning (TIS-35): hot; the project's records; a hot unit's
        pointer; an archived unit's bundle, which links it; or the history annotation of a unit archived before the
        stage ended. A record a pointer or annotation pins by hash is checked against it."""
        hot = (state.get("stage_intents") or {}).get(intent)
        if hot is not None:
            return dict(hot)
        for unit in state["work"].values():  # bounded by live work
            for p in unit.get("stage_intents") or []:
                if p["id"] == intent:
                    return self._load(p["path"], p["sha256"])
        bundle = self.archive.bundle_holding(state, "stage_intents", intent)
        if bundle is not None:
            [p] = [p for p in bundle["unit"].get("stage_intents") or [] if p["id"] == intent]
            return self._load(p["path"], p["sha256"])
        notes = self.archive.index(state).linked("stage_intent", intent) if "cold" in state else []
        if notes:
            rel, _, sha = str(self.archive.record(notes[-1])["note"]).partition(" sha256:")
            return self._load(rel, sha)
        # Last: a stage that never had a unit. Its record is immutable but pinned by no hash (register F15.2): read
        # after every pinned route, so a copy placed here never shadows a unit's (#140 review, finding 5).
        if (self.k.aew_root / RECORDS_DIR / f"{intent}.yaml").is_file():
            return self._load(f"{RECORDS_DIR}/{intent}.yaml", None)
        raise NotFound(f"no stage intent {intent}", intent=intent)

    # ------------------------------------------------------------------ internals

    def _active(self, state: dict[str, Any], intent: str, *, owner: bool = False) -> dict[str, Any]:
        """The unfinished intent ``intent``; with ``owner``, only for the Lead generation that owns it (the runner's
        own bookkeeping: another generation resolves it instead)."""
        si = (state.get("stage_intents") or {}).get(intent)
        if si is None:
            raise NotFound(f"no unfinished stage {intent}: `aew resume` lists them", intent=intent)
        if owner and si["generation"] != state["lead"]["generation"]:
            raise StaleAuthority(f"{intent} belongs to Lead generation {si['generation']}: the current Lead resolves "
                                 "it (`resolve` continue or abandon)", reason="not_owner", intent=intent)
        return si

    def _end(self, ctx: TxnContext, si: dict[str, Any], status: str) -> None:
        """End ``si``: write it whole to its cold home and drop it from the hot state, in this commit."""
        state = ctx.state
        rev = ctx.session.revision + 1
        si["status"] = status
        si["closed"] = {"status": status, "rev": rev, "at": utc_now()}
        self._validate(si)
        wid = si["subject"]["id"]
        unit = state["work"].get(wid) if wid else None
        archived = wid is not None and unit is None and self.archive.bundle(state, wid) is not None
        rel = cold_rel(si["id"], wid if (unit is not None or archived) else None)
        text = yaml.safe_dump(si, sort_keys=False, allow_unicode=True)
        ctx.session.write(rel, text, immutable=True)
        sha = sha256_bytes(text.encode("utf-8"))
        if unit is not None:
            unit.setdefault("stage_intents", []).append({"id": si["id"], "tool": si["tool"], "status": status,
                                                          "path": rel, "sha256": sha, "closed_rev": rev})
        elif archived:
            self.archive.annotate(ctx, wid, "stage_intent", si["id"], note=f"{rel} sha256:{sha}")
        if rel not in ctx.refs:
            ctx.refs.append(rel)
        intents = state["stage_intents"]
        del intents[si["id"]]
        if not intents:
            del state["stage_intents"]

    def _load(self, rel: str, sha: str | None) -> dict[str, Any]:
        raw = (self.k.aew_root / rel).read_bytes()
        if sha is not None and sha256_bytes(raw) != sha:
            raise IntegrityError(f"the stage intent record {rel} does not match its recorded hash", path=rel)
        doc = load_yaml(raw.decode("utf-8"), source=str(self.k.aew_root / rel))
        self._validate(doc)
        return doc

    @staticmethod
    def _validate(si: dict[str, Any]) -> None:
        validate("stage-intent", si, source=f"stage intent {si.get('id')}")


def _check_references(n: int, args: dict[str, Any]) -> None:
    """Refuse a step ``n`` whose argument names what no earlier step of the plan can record: only ``{"$from": [m,
    field]}`` with an integer ``1 <= m < n`` and ``field`` one of :data:`OUTPUTS`. Checked when the intent opens, so a
    bad plan commits nothing, and a continued stage (E3c) resolves only a plan this check accepted (#142 review,
    finding 4)."""
    for name, value in args.items():
        if not (isinstance(value, dict) and REFERENCE in value):
            continue
        ref = value[REFERENCE]
        m, field = ref if isinstance(ref, list | tuple) and len(ref) == 2 else (None, None)
        if set(value) != {REFERENCE} or isinstance(m, bool) or not isinstance(m, int) or field not in OUTPUTS:
            raise UsageError(f"step {n}'s argument {name} is not a step reference: a reference is "
                             f"{{{REFERENCE!r}: [m, field]}}, with m an earlier step's number and field one of "
                             f"{', '.join(OUTPUTS)}", reason="malformed_reference", step=n, argument=name)
        if not 1 <= m < n:
            raise UsageError(f"step {n}'s argument {name} comes from step {m}, which is not an earlier step: a step "
                             "uses only what the steps before it recorded", reason="reference_not_earlier", step=n,
                             argument=name, source=m)


def _plan_of(plan: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """A plan as its steps' primitives and arguments, for comparing a re-resolved plan with the recorded one."""
    return [(p["primitive"], json.dumps(p.get("args") or {}, sort_keys=True, default=str)) for p in plan]


def _refuse_unless_continuable(si: dict[str, Any], check: dict[str, Any]) -> None:
    """Refuse a continue that a recheck forbids: nothing commits and the intent stays ACTIVE. A failed launch is not
    refused here: the continue records it as the stage's ``launch_failed`` stop."""
    checks = check["checks"]
    policy = checks["policy"]
    if policy["status"] == "stale_policy":
        raise StalePolicy(f"the legality policy changed since {si['id']} opened: it is not continued. Abandon it and "
                          "decide anew from the projection", intent=si["id"], bound=policy["bound"],
                          current=policy["current"])
    if policy["status"] != OK:
        raise IntegrityError(f"{si['id']} cannot be continued: {policy['message']}", intent=si["id"])
    for name in ("contract", "subject", "rebinds"):
        if checks[name]["status"] not in (OK, NOT_APPLICABLE):
            reason = {"contract": "contract_changed", "subject": "subject_moved", "rebinds": "continued_too_often"}
            raise IllegalTransition(f"{si['id']} cannot be continued: {checks[name]['message']}. Abandon it "
                                    "(committed steps stand) and decide anew from the projection",
                                    reason=reason[name], intent=si["id"], check=checks[name]["status"])


def _runs(state: dict[str, Any]) -> set[str]:
    return {r["run"] for inv in state["invocations"].values() for r in inv.get("runs") or []}
