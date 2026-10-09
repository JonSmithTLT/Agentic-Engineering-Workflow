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
from aew.errors import IllegalTransition, IntegrityError, NotFound, StaleAuthority, StalePolicy, UsageError
from aew.knowledge.records import format_id
from aew.schemas import validate
from aew.util import load_yaml, sha256_bytes, utc_now

SCHEMA = "aew/stage-intent/v1"
ACTIVE = "ACTIVE"
COMPLETED, STOPPED, REFUSED, ABANDONED = "COMPLETED", "STOPPED_AT_BOUNDARY", "REFUSED", "ABANDONED"
TERMINAL = (COMPLETED, STOPPED, REFUSED, ABANDONED)
RECORDS_DIR = "records/stage-intents"
MAX_STEPS = 16
CHANNELS = ("mcp", "cli", "direct", "test")  # the surface's ingresses (SurfaceContext), and tests' own


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


def _runs(state: dict[str, Any]) -> set[str]:
    return {r["run"] for inv in state["invocations"].values() for r in inv.get("runs") or []}
