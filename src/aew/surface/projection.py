"""``ActionProjection``: what is known to be available, blocked or not yet queryable (design v0.2 §3.3, §8, §12.3).

The one projection module: every ``StageResult`` and the typed ``status`` use it, and later the dashboard's
``/attention`` and the scheduler. It derives only from accepted query surfaces (``status``, ``DispatchDecision``,
committed state, the sealed evidence store) and explicit local telemetry; it is not a second planner. Its parts, by
how their answer can change:

* **control part** (cached): the subject's committed state, its dependency blockers, and the decisions it requires.
  It depends only on the committed control file and the project's policy and manifest files, so it is keyed on their
  identities and recomputed only when one changes (a commit, a policy edit), never per call;
* **overlays** (read on every call in F15.1), because their inputs change without a commit:
  - legality: a stage's availability, composed per step from the guards its steps' commits evaluate
    (:mod:`aew.surface.availability`, M4-E E4): the dispatch decisions and the migrated transition and ingest guards.
    Those read repository inputs, workspaces, the authoritative head and the sealed evidence store; a stage whose
    guards are not all queryable is ``UNKNOWN``, never ``BLOCKED``;
  - telemetry: the runs, and the engine's guidance (hints, contradictions), which reads run telemetry and submitted
    evidence. Heartbeats and submissions change them without a commit or a wake; U1's event watermark will key them;
  - evidence: the reports a decision binds, resolved by kind, scope and producing run in the sealed evidence store;
  - the Lead's own moves where no stage and no report takes a Ticket on (register E233): a transition, a dispatch or
    a launch, each a primitive with its command and its guard's answer.

Separately from availability (legality), each action says whether the caller can call it on its surface profile
(``callable``, presentation only) and whether a stage runner may advance it without judgment (``auto_runnable``,
never for a query or a wait, never dependent on the profile). Decisions never carry a default, and each states its
owner (``owner``: ``lead`` or ``operator``; register E335), read from the primitives it carries out, and names what its
call takes from that owner's judgment (``judgment_inputs``; register E388), read from the call's schema.
"""

from __future__ import annotations

import os
import shlex
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from aew.engine import approval
from aew.engine import hierarchy as H
from aew.engine import operator_decisions as OD
from aew.engine import queue_ops as Q
from aew.engine import scope_ops as SC
from aew.engine import transitions as T
from aew.engine.guards import GUARD_NOT_QUERYABLE
from aew.engine.primitives import JUDGMENT_BEARING, spec_for
from aew.engine.work_ops import awaiting_acceptance
from aew.errors import AEWError
from aew.harness import contract as K
from aew.knowledge import evidence as E
from aew.owners import OPERATOR, owner_of
from aew.surface import availability as SA
from aew.surface import contract, stage
from aew.surface.classify import AVAILABLE, BLOCKED, UNKNOWN, auto_runnable, effective_class
from aew.surface.context import SurfaceContext
from aew.util import utc_now

LIVE = K.LIVE_RUNS
CACHE_SIZE = 64
__all__ = ["GUARD_NOT_QUERYABLE", "clear_cache", "control_key", "project"]  # the reason code of an unqueryable guard

_cache: OrderedDict[tuple[str, str], tuple[Any, dict[str, Any]]] = OrderedDict()
_lock = threading.Lock()


# ---------------------------------------------------------------------------------------------- identities

def _stat(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def control_key(engine: Any) -> tuple[Any, ...]:
    """What the control part depends on: the committed control file, the manifest and every policy file. Taken before
    the reads it stands for, so a change between the two costs a recomputation, never a stale answer."""
    root = Path(engine.aew_root)
    policy = root / "policy"
    files: list[tuple[str, Any]] = []
    if policy.is_dir():
        for dirpath, _dirs, names in os.walk(policy):
            files.extend((os.path.join(dirpath, n), _stat(Path(dirpath) / n)) for n in sorted(names))
    return (engine.store.control_identity(), _stat(root / "project.yaml"), tuple(sorted(files)))


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# ---------------------------------------------------------------------------------------------- builders

def _action(name: str, arguments: dict[str, Any], *, kind: str, availability: str, reason_codes: list[str],
            cli_fallback: list[str] | None, judgment: bool = False) -> dict[str, Any]:
    """``judgment``: this call of a primitive carries the Lead's reason, so it is judgment-bearing whatever the
    primitive's base class (a regression's `--reason`)."""
    t = contract.tool(name)
    klass = effective_class(t, arguments) if t is not None else spec_for(name).operation_class
    if judgment:
        klass = JUDGMENT_BEARING
    return {"action": name, "kind": kind, "arguments": arguments, "operation_class": klass,
            "availability": availability, "callable": False,
            "auto_runnable": auto_runnable(t, availability, klass),
            "reason_codes": sorted(set(reason_codes)), "cli_fallback": cli_fallback}


# The primitives each decision kind carries out, from which its one owner is read (register E335; the designer's
# ruling of 2026-11-11: one owner per decision kind, from one table of primitive owners,
# ``owners.PRIMITIVE_OWNERS``). PUBLISH accepts the integration verifier's report and publishes, or publishes a
# validated candidate. PLAN accepts a proposed plan revision (register E351; the kind's name is the operator's ruling of
# 2026-11-26).
DECISION_PRIMITIVES: dict[str, tuple[str, ...]] = {
    "PLAN": ("plan.accept",),
    "ACCEPT_REVIEW_EVIDENCE": ("review.ingest",),
    "ACCEPT_VERIFICATION": ("verify.ingest",),
    "PUBLISH": ("integrate.publish", "verify.ingest.integration"),
    "FINISH_PUBLISH": ("integrate.reconcile",),
    "CLASSIFY_FAILURE": ("verify.classify",),
    "RECONCILE": ("work.reconcile",),
    "RESOLVE_STAGE": ("stage.resolve",),
    "DISPOSE_ANOMALY": ("work.dispose",),
    "DISPOSE_FINDING": ("work.dispose",),
    "DISPOSE_CLAIM": ("work.dispose",),
    "REPLACE_GATE": ("work.gate_replace",),
    "ADD_SCOPE": ("work.scope_add",),
}


def decision_owner(name: str) -> str:
    """A decision kind's one owner, read from its primitives' owners. A kind with no primitives here, or whose
    primitives name different owners, is the operator's: an unstated owner never falls to the Lead."""
    owners = {owner_of(p) for p in DECISION_PRIMITIVES.get(name, ())}
    return owners.pop() if len(owners) == 1 else OPERATOR


def judgment_inputs(name: str, tool: str | None, arguments: dict[str, Any] | None) -> dict[str, Any] | None:
    """What a decision's `resolve` call takes from whoever decides it (register E388; the vertical's spec v2): each
    field `resolve`'s schema requires that the decision's arguments leave out. With those filled in, the call has every
    field the schema requires; a choice can need more, which only the adapter checks and whose refusal names it
    (`follow_up` its Ticket; a REPLACE_GATE its ``approval_options`` entry). The ``choice`` offers as ``options`` only
    the choices that run the decision's primitives (``contract.RESOLVE_CHOICE_PRIMITIVE``, read through
    ``DECISION_PRIMITIVES``); any other field, the rationale, is offered as its schema, for the decider to write. None
    when the arguments are whole, or there is no call to fill: a decision never carries a default, so nothing here is a
    value.

    The limit: only `resolve`, whose required fields beyond those a decision supplies are all judgments (the result
    schema's ``judgment_inputs`` names exactly those). Any other tool's decision names none, whatever its arguments
    leave out: a field missing there (a mechanical fact such as a prepared candidate) is never offered as a judgment
    (the quick check of #630, m1)."""
    t = contract.tool(tool) if tool else None
    if t is None or arguments is None or t.name != "resolve":
        return None
    schema = t.input_schema
    primitives = DECISION_PRIMITIVES.get(name, ())
    out: dict[str, Any] = {}
    for field in schema.get("required") or ():
        if field in arguments:
            continue
        prop = schema["properties"][field]
        if field == "choice":
            out[field] = {"options": list(contract.choices_running(*primitives) if primitives else prop["enum"])}
        else:
            out[field] = dict(prop)
    return out or None


def _decision(name: str, subject: str, *, tool: str | None, arguments: dict[str, Any] | None,
              cli_fallback: list[str] | None, evidence: list[str] | None = None,
              availability: str = UNKNOWN) -> dict[str, Any]:
    out = {"decision": name, "subject": subject, "owner": decision_owner(name), "evidence": list(evidence or []),
           "tool": tool, "arguments": arguments, "availability": availability, "default": "NONE",
           "cli_fallback": cli_fallback}
    if inputs := judgment_inputs(name, tool, arguments):
        out["judgment_inputs"] = inputs
    return out


def _blocker(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "message": message}
    if details:
        out["details"] = details
    return out


# ---------------------------------------------------------------------------------------------- the control part

def _control_part(engine: Any, subject: str) -> dict[str, Any]:
    """Committed facts only: nothing here may read run telemetry, submitted evidence or repository inputs."""
    state = engine.store.current()
    part: dict[str, Any] = {"revision": state["revision"],
                            "generation": int((state.get("lead") or {}).get("generation") or 0),
                            "subject": subject, "state": None, "unit": None, "actions": [], "decisions": [],
                            "blockers": [], "anomalies": _anomalies(state, subject)}
    _stage_decisions(part, state, subject)
    _anomaly_decisions(part, engine, state)
    _gate_decisions(part, engine, state, subject)
    if subject == "project":
        return part
    unit = engine.status(subject)["work_unit"]  # hot, or archived as it stands now
    part["state"] = unit.get("state")
    entry = Q.entry_of(state, subject)[1] or {}
    part["unit"] = {"kind": unit.get("kind"), "mutating": bool(unit.get("mutating")),
                    "integration": dict(unit.get("integration") or {}),
                    "validated_report": (entry.get("validated") or {}).get("report")}
    if unit.get("parent") is not None:
        part["unit"]["parent"] = unit["parent"]
    if SC.added_listing(unit):  # a live Ticket's adds, listed, never counted (E126)
        part["unit"]["scope_added"] = SC.added_listing(unit)
    if entry:
        part["unit"]["queue_state"] = entry["state"]
    for b in unit.get("blocked_by") or []:
        kind = str(b.get("kind") or "blocked")
        part["blockers"].append(_blocker(kind.upper(), kind.replace("_", " "),
                                         {k: v for k, v in b.items() if k != "kind"}))
    if subject in state["work"]:
        _plan_decisions(part, state["work"][subject], subject)
    if unit.get("kind") == "ticket":
        _ticket_actions(part, subject)
        if subject in state["work"]:  # the marked findings the Ticket records and the Lead has not disposed of (E5b)
            part["decisions"].extend(_dispose(item, engine, state=state)
                                     for item in _items(engine, subject, state=state))
    return part


def _items(engine: Any, subject: str, **kw: Any) -> list[dict[str, Any]]:
    """The marked items not disposed of, or none when they cannot be read now (a policy edit awaiting adoption, an
    evidence integrity problem): the projection never fails on them, and the ingest's own guard still decides."""
    try:
        return list(engine.disposition_items(subject, **kw))
    except AEWError:
        return []


def _disposal_refusal(engine: Any, anomaly: str) -> dict[str, Any] | None:
    try:
        return engine.anomaly_disposal_refusal(anomaly)
    except AEWError as exc:  # it could not be asked now: say so, never AVAILABLE
        return {"code": exc.code, "message": exc.message, "details": dict(exc.details)}


def _anomalies(state: dict[str, Any], subject: str) -> list[dict[str, Any]]:
    """The open anomalies that concern the subject (every one, for the project), committed facts (M4-E E5b)."""
    return [dict(a) for _, a in sorted((state.get("anomalies") or {}).items())
            if subject == "project" or a.get("subject") in (subject, None)]


def _anomaly_decisions(part: dict[str, Any], engine: Any, state: dict[str, Any]) -> None:
    """An open anomaly is the Lead's to dispose of (plan v3 §2.4): a decision with no default."""
    for a in part["anomalies"]:
        try:
            shown = engine.disposition_approval(a["id"], state=state)
        except AEWError:
            shown = None
        args = {"subject": a["id"]}
        argv = ["work", "dispose", a["id"], "--choice", "<accept_risk|follow_up|not_applicable>",
                "--rationale", "<why>"]
        if shown is not None:
            args["approval_digest"] = shown["digest"]
            argv.extend(["--approval-digest", shown["digest"]])
        part["decisions"].append({"decision": "DISPOSE_ANOMALY", "tool": "resolve", "evidence": [a["id"]],
                                  "arguments": args, "cli": argv})


def _gate_decisions(part: dict[str, Any], engine: Any, state: dict[str, Any], subject: str) -> None:
    """A parent's mandatory gate that no unit type under it can satisfy is replaced on the record (ITEMS 55; designer,
    addendum 4): a decision naming the item, whose replacement gate is a judgment (no default) and whose owner is the
    owner table's (``decision_owner``), and a blocker whose details say why, the candidates, the units stuck on it and
    the live invocations a replacement would make stale (its preview, addendum 3). A gate some unit type can satisfy
    is the operator's (addendum 5): the decision is blocked, and the blocker names those unit types."""
    try:
        items = engine.gate_items(subject, state=state)
    except AEWError:  # the catalogue or policy cannot be read now: doctor says so
        items = []
    for i in items:
        args = {"subject": i["id"], "choice": "replace_gate"}
        choices = {name: {**args, "replacement": name, "approval_digest": shown["digest"]}
                   for name, shown in i["approval_subjects"].items()}
        if len(choices) == 1:
            args = next(iter(choices.values()))
        part["decisions"].append({
            "decision": "REPLACE_GATE", "tool": "resolve", "evidence": [i["id"]],
            "arguments": args, "availability": AVAILABLE if i["replaceable"] else BLOCKED,
            "approval_options": choices, "cli": ["lead", "tool", "resolve", "--arguments", "-"]})
        part["blockers"].append(_blocker(
            "GATE_UNSATISFIABLE",
            f"{i['work_id']}'s mandatory gate `{i['gate']}` {i['verdict']}: {i['why']}; {i['route']}",
            {k: i[k] for k in ("id", "work_id", "gate", "candidates", "replaceable", "satisfiable_by", "stranded_by",
                               "stuck_units", "stale_invocations")}
            | {"approval_digests": {name: row["digest"] for name, row in i["approval_subjects"].items()}}))


def _dispose(item: dict[str, Any], engine: Any, *,
             state: dict[str, Any] | None = None) -> dict[str, Any]:
    """A finding or claim policy marks ``requires_disposition``, not disposed of yet: the Lead's decision (§2.4)."""
    args = {"subject": item["id"]}
    argv = ["work", "dispose", item["id"], "--choice", "<accept_risk|follow_up|not_applicable>",
            "--rationale", "<why>"]
    try:
        shown = engine.disposition_approval(item["id"], state=state)
    except AEWError:
        pass
    else:
        args["approval_digest"] = shown["digest"]
        argv.extend(["--approval-digest", shown["digest"]])
    return {"decision": "DISPOSE_FINDING" if item["kind"] == "finding" else "DISPOSE_CLAIM", "tool": "resolve",
            "evidence": [item["id"]], "arguments": args, "availability": AVAILABLE, "cli": argv}


def _plan_decisions(part: dict[str, Any], unit: dict[str, Any], wid: str) -> None:
    """A proposed plan revision that ``plan accept`` would take now (``work_ops.awaiting_acceptance``) is the PLAN
    decision (register E351): the operator's (``decision_owner``; the operator's ruling of 2026-11-26), with no
    default. Its command is the acceptance bound to the plan's SHA-256 (``approval.command``), which the operator runs
    at their own terminal, or which a Lead session runs once the operator has confirmed that plan: ``ask_operator``
    is the confirmation's command (``operator_decisions.command``), which a Lead session's acceptance waits for."""
    for plan in awaiting_acceptance(unit):
        n = int(plan["revision"])
        part["decisions"].append({
            "decision": "PLAN", "tool": None, "arguments": None, "evidence": [str(plan["path"])],
            "availability": AVAILABLE, "ask_operator": OD.command(OD.PLAN, wid, n),
            "cli": approval.command("plan.accept", wid, str(plan["sha256"]), "--revision", str(n))})


def _stage_decisions(part: dict[str, Any], state: dict[str, Any], subject: str) -> None:
    """An unfinished stage of the subject (every one, for the project) is the current Lead's to resolve, continue or
    abandon, never inferred (M4-E E3c; §3.4 rule 8). The decision names the intent and carries no choice: no
    default."""
    for sid, si in sorted((state.get("stage_intents") or {}).items()):
        if subject == "project" or si["subject"]["id"] == subject:
            part["decisions"].append({"decision": "RESOLVE_STAGE", "tool": "resolve", "evidence": [sid],
                                      "arguments": {"subject": sid},
                                      "cli": ["stage", "continue", sid, "--rationale", "<why>"],
                                      "stopped": stage.kept_stop(si)})


def _ticket_actions(part: dict[str, Any], wid: str) -> None:
    """The decisions a Ticket's state requires, each named by its stable typed tool (so the vocabulary does not change
    when F15.2 builds it) with the primitive command that does it today. A decision that accepts a report is completed
    per report by the evidence overlay, which also asks its stage's availability (E4); a decision whose stage is not
    migrated stays UNKNOWN. The stage actions are the legality overlay's (:func:`_stage_actions`)."""
    st = part["state"]
    integration = part["unit"]["integration"]
    if st == "REVIEW_PENDING":
        part["decisions"].append({"decision": "ACCEPT_REVIEW_EVIDENCE", "role": "reviewer", "kind": "review",
                                  "scope": None, "tool": "ticket_request_verification", "argument": "review_evidence",
                                  "cli": ["review", "ingest", wid, "--evidence", "{evidence}"]})
    elif st == "VERIFY_PENDING":
        part["decisions"].append({"decision": "ACCEPT_VERIFICATION", "role": "verifier", "kind": "verification",
                                  "scope": "ticket", "tool": "ticket_prepare", "argument": "verification_evidence",
                                  "cli": ["verify", "ingest", wid, "--evidence", "{evidence}"]})
    elif st == "VERIFICATION_FAILED":
        part["decisions"].append({"decision": "CLASSIFY_FAILURE", "tool": None,
                                  "cli": ["verify", "classify", wid, "--as", "<classification>", "--reason",
                                          "<why>", "--approval-digest", "<shown digest>"]})
    elif st == "COMMIT_READY" and integration.get("status") == "prepared":
        # A prepared candidate is validated after integration before it may be published (the engine's own guidance):
        # by an integration verifier, or, in checks mode, by the engine's own validation (D5), which needs no Lead
        # decision. Publication is offered once the verifier has reported: its tool accepts the report and publishes.
        # The report is read from the run until the custodian routes it, and from the entry after (E133's review, M1).
        # The shell takes this in two: its command accepts the report, and the validated candidate's PUBLISH follows.
        candidate = {"prepared_candidate": str(integration["candidate"])} if integration.get("candidate") else {}
        routed = part["unit"].get("validated_report")
        if routed:
            part["decisions"].append({"decision": "PUBLISH", "tool": "integration_publish", "evidence": [routed],
                                      "arguments": {"work_id": wid, **candidate,
                                                    "verification_evidence": routed},
                                      "cli": ["verify", "ingest", wid, "--evidence", routed]})
        else:
            part["decisions"].append({"decision": "PUBLISH", "role": "verifier", "kind": "verification",
                                      "scope": "integration", "tool": "integration_publish",
                                      "argument": "verification_evidence", "with": candidate,
                                      "cli": ["verify", "ingest", wid, "--evidence", "{evidence}"]})
    elif st == "COMMIT_READY" and integration.get("status") == "validated":
        candidate = integration.get("candidate")
        argv = ["integrate", "publish", wid]
        if candidate:
            argv.extend(["--candidate", str(candidate)])
        part["decisions"].append({"decision": "PUBLISH", "tool": "integration_publish",
                                  "arguments": {"work_id": wid,
                                                **({"prepared_candidate": str(candidate)} if candidate else {})},
                                  "cli": argv})
    elif st == "COMMIT_READY" and integration.get("status") == "publishing":
        # A publish that recorded its intent and did not finish (E137): no stage takes it from here, so without this
        # the projection offers nothing while the lease holds up every other integration.
        part["decisions"].append({"decision": "FINISH_PUBLISH", "tool": None,
                                  "cli": ["integrate", "reconcile", wid]})
    elif st == "INTERRUPTED":
        part["decisions"].append({"decision": "RECONCILE", "tool": None,
                                  "cli": ["work", "reconcile", wid, "--to", "<phase>", "--reason", "<reason>"]})


def _cached_control_part(engine: Any, subject: str) -> dict[str, Any]:
    key = control_key(engine)
    slot = (str(engine.aew_root), subject)
    with _lock:
        hit = _cache.get(slot)
        if hit is not None and hit[0] == key:
            _cache.move_to_end(slot)
            return hit[1]
    part = _control_part(engine, subject)
    with _lock:
        _cache[slot] = (key, part)
        _cache.move_to_end(slot)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return part


# ---------------------------------------------------------------------------------------------- the overlays

def _guidance(engine: Any, subject: str) -> tuple[list[str], list[dict[str, Any]]]:
    """The engine's own guidance, read now: it reflects run telemetry and submitted evidence, which change without a
    commit. Hints are for a reader and never parsed; contradictions are blockers of the project."""
    report = engine.status(usage=False, relay=False)  # the guidance only, without either telemetry projection
    lines = [str(x) for x in report.get("next_actions") or []]
    if subject == "project":
        return lines, [_blocker("CONTRADICTION", str(c)) for c in report.get("contradictions") or []]
    prefix = f"{subject}: "
    return [a[len(prefix):] for a in lines if a.startswith(prefix)], []


_LATER_START = frozenset(state for starts in SA.STARTS_AT.values() for state in starts)


def _stage_actions(engine: Any, part: dict[str, Any], wid: str) -> tuple[list[dict[str, Any]],
                                                                            list[dict[str, Any]]]:
    """The subject's next stage (or, for a non-mutating Ticket, its next dispatch), with its availability now: a
    stage's is composed per step from its guards (M4-E E4), a dispatch's is its ``DispatchDecision``. Allowed is
    AVAILABLE, refused is BLOCKED with its conditions, and anything a guard cannot answer is UNKNOWN (never
    BLOCKED)."""
    unit = part["unit"]
    if unit is None or unit["kind"] != "ticket":
        return [], []
    st = part["state"]
    if unit["mutating"] and st in ("READY", "BLOCKED"):
        stage, cli = "ticket_start", ["work", "assign", wid, "--launch"]
    elif unit["mutating"] and st == "RUNNING":
        stage, cli = "ticket_request_review", ["work", "transition", wid, "--to", "REVIEW_PENDING"]
    elif not unit["mutating"] and st in ("READY", "BLOCKED"):
        return _nm_dispatch(engine, part, wid)
    elif unit["mutating"] and st in _LATER_START and not (
            st == "COMMIT_READY" and unit["integration"].get("status") in SA.HAS_CANDIDATE):
        # A Ticket past a stage's first steps (E133): which stage takes it on depends on what its class requires.
        fit = engine.stage_fit(engine.store.current(), wid)
        to = "VERIFY_PENDING" if st == "REVIEW_PASSED" and (fit is None or fit.verification) else "COMMIT_READY"
        stage = T.stage_for(st, to, fit) or ("ticket_prepare" if st == "COMMIT_READY" else None)
        if stage is None:
            return [], []
        cli = (["integrate", "prepare", wid] if st == "COMMIT_READY"
               else ["work", "transition", wid, "--to", to])
    else:
        return [], []
    args = {"work_id": wid}
    if cli[:2] == ["work", "transition"]:
        cli.extend(["--prior-value", st])
        args["prior_value"] = st
    found = SA.stage_availability(engine, stage, args)
    action = _action(stage, args, kind=contract.STAGE,
                     availability=found["availability"], reason_codes=found["reason_codes"], cli_fallback=cli)
    blockers = [_blocker(b["code"], b["message"], b.get("details")) for b in found["blockers"]]
    return [action], blockers


def _nm_dispatch(engine: Any, part: dict[str, Any], wid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A non-mutating Ticket's dispatch, answered by ``DispatchDecision`` now (no stage dispatches one)."""
    entrypoint = "work.dispatch"
    blockers: list[dict[str, Any]] = []
    try:
        decision = engine.dispatch_explain(wid)
        entrypoint = str(decision.get("entrypoint") or entrypoint)
        availability = AVAILABLE if decision.get("allowed") else BLOCKED
        reasons = [str(c) for c in decision.get("reason_codes") or []]
        if availability == BLOCKED:
            blockers = [_blocker(b["code"], b["message"], b.get("details")) for b in
                        decision.get("blocking_conditions") or []]
    except AEWError as exc:
        availability, reasons = UNKNOWN, [exc.code]
    cli = ["work", "dispatch", wid, "--launch"] if entrypoint == "work.dispatch" else None
    return [_action(entrypoint, {"work_id": wid}, kind=contract.PRIMITIVE, availability=availability,
                    reason_codes=reasons, cli_fallback=cli)], blockers


def _argv(command: str) -> list[str]:
    """The engine's printed command, as the argv the projection offers after ``aew``."""
    return shlex.split(command)[1:]


def _asked(engine: Any, ask: Any) -> tuple[str, list[str]]:
    """A dispatch decision as an availability and its reason codes; one that cannot be asked now is UNKNOWN."""
    try:
        decision = ask()
    except AEWError as exc:
        return UNKNOWN, [exc.code]
    return (AVAILABLE if decision.get("allowed") else BLOCKED), [str(c) for c in decision.get("reason_codes") or []]


def _lead_moves(engine: Any, part: dict[str, Any], wid: str,
                runs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The Lead's own moves for a mutating Ticket that no stage and no report takes on (register E233; E133 left
    these states with a hint and nothing a Lead can rely on). Each is a primitive with its whole command, never
    auto-runnable, and with the availability its own guard answers now:

    * its transitions on from a state no stage starts from (``transitions.lead_moves``): ASSIGNED to RUNNING, a failed
      review back to RUNNING, an inconclusive verification back to VERIFY_PENDING, and a return from escalation,
      each with the Lead's reason where its edge requires one, which makes it judgment-bearing;
    * the dispatch of the worker its state waits on, where none works on it (``Engine.worker_needed``);
    * the launch of an active invocation that has no live run and nothing to ingest: one whose latest run ended
      without its output (``contract.relaunchable``), and in ASSIGNED the implementer no harness was launched for
      (``Engine.harness_unlaunched``). Past ASSIGNED an invocation with no run is a worker run by hand from its pack,
      which the engine's guidance leaves to report.

    A dispatch's command launches its worker, so it is BLOCKED, with the refusal as a blocker, while the execution
    policy pins no profile for it (``Engine.launch_refusal``): its own decision does not ask that. Nothing else here
    adds a blocker: a move its guard refuses is listed BLOCKED with the guard's reason codes, and the stop is the
    engine's to state when the move is tried. Read now: the dispatch decisions read policy and telemetry."""
    unit = part["unit"]
    if unit is None or unit["kind"] != "ticket" or not unit["mutating"] or part["state"] in T.TERMINAL:
        return [], []
    st = str(part["state"])
    state = engine.store.current()
    moves, blockers = [], []
    for dst in T.lead_moves(st):
        reason = T.RULES[(st, dst)].reason_required
        found = engine.guard_query("work.transition", wid, {"to": dst, **({"reason": "<reason>"} if reason else {})},
                                   state=state)
        # The engine's own command, held to the state it was offered in. The exits walk parses every argv offered
        # (``lands``); the static printed-command check reads only a literal list at the key.
        cli = _argv(str(T.command(st, dst, wid)))
        moves.append(_action("work.transition", {"work_id": wid, "to": dst, "prior_value": st},
                             kind=contract.PRIMITIVE, availability=found["availability"],
                             reason_codes=found["reason_codes"], judgment=reason, cli_fallback=cli))
    try:
        needed = engine.worker_needed(state, wid)
        unlaunchable = engine.launch_refusal(state, wid, needed.role) if needed is not None else None
    except AEWError:  # the gates or the policy cannot be read now: the engine's own guidance says so
        needed = unlaunchable = None
    if needed is not None:
        found = engine.guard_query("invoke.create.mutating", wid, {"role": needed.role, "scope": needed.scope},
                                   state=state)
        availability, reasons = found["availability"], list(found["reason_codes"])
        if unlaunchable is not None and availability != BLOCKED:
            # The command launches, and its launch would be refused in the dispatch's own transaction: no exit.
            availability, reasons = BLOCKED, [*reasons, unlaunchable.code]
            blockers.append(_blocker(unlaunchable.code, unlaunchable.message, dict(unlaunchable.details)))
        moves.append(_action("invoke.create.mutating", {"work_id": wid, "role": needed.role, "scope": needed.scope},
                             kind=contract.PRIMITIVE, availability=availability, reason_codes=reasons,
                             cli_fallback=_argv(needed.command)))
    ended = {r["invocation"] for r in runs if K.relaunchable(r["status"])}
    unlaunched = set(engine.harness_unlaunched(state, wid) if st == "ASSIGNED" else ())
    invocations = state.get("invocations") or {}  # a run read a moment ago may name one this state no longer holds
    first = []
    for invocation in sorted(ended | unlaunched):
        availability, reasons = _asked(engine, lambda i=invocation: engine.dispatch_explain(wid, invocation=i))
        prior = approval.run_value(invocations.get(invocation) or {})
        cli = _argv(K.launch_command(invocation, prior))
        launch = _action("harness.launch", {"invocation": invocation, "prior_value": prior}, kind=contract.PRIMITIVE,
                         availability=availability, reason_codes=reasons, cli_fallback=cli)
        # An implementer no harness was launched for is launched before the Ticket moves to RUNNING, as the hint
        # says: past ASSIGNED its launch is no longer offered (#612 review, F1).
        (first if invocation in unlaunched and availability == AVAILABLE else moves).append(launch)
    return [*first, *moves], blockers


def _runs(engine: Any, subject: str) -> list[dict[str, Any]]:
    """Local run telemetry, read now: the latest run of every active invocation (of the subject)."""
    observed_at = utc_now()
    out = []
    for r in engine.harness_resume(engine.store.current()):
        if subject != "project" and r.get("work_unit") != subject:
            continue
        out.append({"run": str(r["run"]), "invocation": str(r["invocation"]), "work_unit": str(r["work_unit"]),
                    "role": str(r["role"]), "status": str(r["status"]),
                    "reason": None if r.get("reason") is None else str(r["reason"]),
                    "evidence": [str(e) for e in r.get("evidence") or []], "source": "local_telemetry",
                    "observed_at": observed_at})
    return out


def _reports(engine: Any, subject: str, runs: list[dict[str, Any]], d: dict[str, Any]) -> list[str]:
    """The reports a decision may accept: in the sealed evidence store, of the decision's kind (and verification
    scope), produced by the current run of an active invocation of the decision's role that has ended with its
    evidence. A check result or any other record a run produced is never offered as a report."""
    runs_of_role = {r["run"] for r in runs if r["role"] == d["role"] and r["status"] == K.ENDED_WITH_EVIDENCE}
    if not runs_of_role:
        return []
    out = []
    for e in E.scan(Path(engine.aew_root), subject)[0]:
        if e.get("kind") != d["kind"] or (e.get("producer") or {}).get("run") not in runs_of_role:
            continue
        if d["scope"] is not None and (e.get("verification") or {}).get("scope") != d["scope"]:
            continue
        out.append(str(e["id"]))
    return sorted(out)


# The edge each Ticket decision's stage takes, by decision and report scope.
_DECISION_EDGE = {("ACCEPT_REVIEW_EVIDENCE", None): ("REVIEW_PENDING", "REVIEW_PASSED"),
                  ("ACCEPT_VERIFICATION", "ticket"): ("VERIFY_PENDING", "VERIFIED"),
                  ("PUBLISH", "integration"): ("COMMIT_READY", "DONE"),
                  ("PUBLISH", None): ("COMMIT_READY", "DONE")}


def _fitting(d: dict[str, Any], fit: T.Fit | None) -> dict[str, Any]:
    """The decision as offered: its stage only where that stage is a whole step for this Ticket now, as the engine's
    hints name it (E130; #331 review F1), else its command alone. Read now: it reads the gates."""
    edge = _DECISION_EDGE.get((d["decision"], d.get("scope")))
    if edge is None or not d.get("tool") or T.stage_for(*edge, fit):
        return d
    return {**d, "tool": None, **({"argument": None} if "argument" in d else {}),
            **({"arguments": None} if "arguments" in d else {})}


def _decisions(engine: Any, part: dict[str, Any], subject: str, runs: list[dict[str, Any]],
               blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The decisions required, each with its stage's availability where the stage is migrated. A decision's stage
    that is blocked adds its blockers (with any ``disposition`` its call would commit instead, PR #171 review) to
    ``blockers``."""
    out = []
    listed = {e for d in part["decisions"] for e in d.get("evidence") or [] if d["decision"].startswith("DISPOSE")}
    state = engine.store.current() if part["state"] else None
    fit = engine.stage_fit(state, subject) if state is not None else None
    for d in map(lambda d: _fitting(d, fit), part["decisions"]):
        if "role" not in d:
            arguments = d.get("arguments")
            argv = list(d["cli"])
            found = d.get("availability", UNKNOWN)
            if d["decision"] == "RESOLVE_STAGE" and arguments:
                try:
                    shown = stage.assess(engine, engine.stage_intent(arguments["subject"]))["approval"]
                except AEWError:
                    pass
                else:
                    arguments = {**arguments, "approval_digest": shown["digest"]}
                    argv += ["--approval-digest", shown["digest"]]
            if d["decision"] == "DISPOSE_ANOMALY":  # the disposal's own query, read now: a live contradiction (m4)
                refused = _disposal_refusal(engine, d["evidence"][0])
                found = BLOCKED if refused else AVAILABLE
                if refused:
                    blockers.append(_blocker(refused["code"], refused["message"], refused["details"]))
            if d["decision"] == "CLASSIFY_FAILURE":
                shown = engine.approval_subject(subject, "verify.classify")
                if shown is not None:
                    argv[-1] = shown["digest"]
            if arguments is not None and d["tool"] and SA.migrated(d["tool"]):  # PUBLISH: its stage's (M4-E E4b)
                composed = SA.stage_availability(engine, d["tool"], arguments)
                found = composed["availability"]
                blockers.extend(_blocker(b["code"], b["message"], b.get("details")) for b in composed["blockers"])
            out.append(_decision(d["decision"], subject, tool=d["tool"], arguments=arguments,
                                 cli_fallback=argv, evidence=d.get("evidence"), availability=found))
            if "stopped" in d:
                out[-1]["stopped"] = d["stopped"]
            if "approval_options" in d:
                out[-1]["approval_options"] = d["approval_options"]
            if "ask_operator" in d:
                out[-1]["ask_operator"] = d["ask_operator"]
            continue
        for e in _reports(engine, subject, runs, d):  # one decision per report, bound to it
            arguments = ({"work_id": subject, d["argument"]: e, **d.get("with", {})}
                         if d["argument"] else None)
            found = UNKNOWN
            if arguments is not None and SA.migrated(d["tool"]):  # its stage's availability with this report (E4)
                found = SA.stage_availability(engine, d["tool"], arguments)["availability"]
            out.append(_decision(d["decision"], subject, tool=d["tool"], evidence=[e], arguments=arguments,
                                 cli_fallback=[x.replace("{evidence}", e) for x in d["cli"]], availability=found))
            # The report's own marked items, which its acceptance would refuse to advance past (M4-E E5b, §2.4).
            for item in _items(engine, subject, evidence=[e], state=state):
                if item["evidence"] == e and item["id"] not in listed:
                    listed.add(item["id"])
                    x = _dispose(item, engine, state=state)
                    out.append(_decision(x["decision"], subject, tool=x["tool"], evidence=x["evidence"],
                                         arguments=x["arguments"], cli_fallback=x["cli"], availability=AVAILABLE))
    return out


def _scope_decisions(engine: Any, part: dict[str, Any], subject: str,
                     blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A test path the Ticket's change touches outside its scope can be added to the scope on the record (register
    E126; the designer's decisions of 2026-11-03, §2, "The door"): one decision per such path, while the gate context
    reports it, with the add's own query for its availability. Its rationale is a judgment, so it has no default, and
    its owner is the owner table's (``decision_owner``); a
    path the add would refuse, one that needs a sign-off included, is BLOCKED and adds the refusal to ``blockers``.
    Read now: it reads the workspace. A path that is not test code, or not one exact printable path (rule 1), is not
    offered: the guardrail's refusal says what to do with it."""
    unit = part["unit"]
    if unit is None or unit["kind"] != "ticket" or not unit["mutating"] or part["state"] in H.TERMINAL:
        return []
    state = engine.store.current()
    if not (state["work"].get(subject) or {}).get("workspace"):
        return []
    try:
        violations = engine.gate_context(state, subject)["guardrails"]["violations"]
    except AEWError:  # the gate context cannot be read now: the stage's own blockers say so
        return []
    out = []
    for path in sorted({v["path"] for v in violations if v["rule"] == "outside_ticket_scope"}):
        if not SC.test_code(path) or SC.exact_path_problem(path) is not None:  # rule 1, a newline included
            continue
        args = {"subject": SC.item_id(subject, path), "choice": SC.CHOICE}
        found = engine.guard_query(SC.OP, None, {"subject": args["subject"], "rationale": "(the Lead's reason)"},
                                   state=state)
        blockers.extend(_blocker(b["code"], b["message"], b.get("details")) for b in found["blocking_conditions"])
        out.append(_decision("ADD_SCOPE", subject, tool="resolve", arguments=args, evidence=[args["subject"]],
                             cli_fallback=["lead", "tool", "resolve", "--arguments", "-"],
                             availability=found["availability"]))
    return out


# ---------------------------------------------------------------------------------------------- assembly

def project(engine: Any, ctx: SurfaceContext, subject: str | None = None) -> dict[str, Any]:
    """The ``ActionProjection`` for ``subject`` (a work unit id) or the project: one read-only answer, so a gate
    context its parts ask of the same state is computed once (``Engine.gate_memo``)."""
    with engine.gate_memo():
        return _project(engine, ctx, subject)


def _project(engine: Any, ctx: SurfaceContext, subject: str | None) -> dict[str, Any]:
    subject = subject or "project"
    part = _cached_control_part(engine, subject)
    actions = [dict(a) for a in part["actions"]]
    blockers = [dict(b) for b in part["blockers"]]
    hints, contradictions = _guidance(engine, subject)
    blockers.extend(contradictions)
    staged, stage_blockers = _stage_actions(engine, part, subject)
    actions[:0] = staged
    blockers.extend(stage_blockers)
    runs = _runs(engine, subject)
    moves, unlaunchable = _lead_moves(engine, part, subject, runs)
    actions.extend(moves)
    blockers.extend(unlaunchable)
    live = [r["run"] for r in runs if r["status"] in LIVE]
    if live:
        actions.append(_action("harness_wait", {"runs": live}, kind=contract.WAIT, availability=AVAILABLE,
                               reason_codes=[], cli_fallback=["harness", "wait", *live,
                                                              *(["--any"] if len(live) > 1 else [])]))
        if engine.wakes_reach_lead():  # the wait stays on offer; the readable next step is the turn's end
            actions[-1]["woken"] = True
    # A high anomaly about the subject (or the project) is an open obligation: no action of it auto-runs, its
    # availability unchanged (plan v3 §2.4, n6). The steering loop stops on it too (E7).
    held = any(a["severity"] == "high" for a in part["anomalies"])
    for a in actions:
        a["callable"] = contract.callable_on(contract.tool(a["action"]), ctx.profile)
        if held:
            a["auto_runnable"] = False
    out = {"revision": part["revision"], "generation": part["generation"], "subject": subject,
             "state": part["state"], "actions": actions,
             "decisions_required": [*_decisions(engine, part, subject, runs, blockers),
                                    *_scope_decisions(engine, part, subject, blockers)], "blockers": blockers,
             "anomalies": [_anomaly(a) for a in part["anomalies"]], "hints": hints, "runs": runs}
    if part["unit"]:
        bindings = {key: part["unit"][key] for key in ("parent", "queue_state", "scope_added") if key in part["unit"]}
        if bindings:
            out["unit"] = bindings
        fallback = {}
        if queue_state := bindings.get("queue_state"):
            if queue_state != "DEFERRED" and part["unit"]["integration"].get("status") != "publishing":
                fallback["integrate.defer"] = approval.bound_argv(
                    ("integrate", "defer", subject, "--reason", "<reason>"), queue_state)
            if queue_state in {"DEFERRED", "AWAITING_DISPOSITION", "VALIDATED"}:
                fallback["integrate.requeue"] = approval.bound_argv(
                    ("integrate", "requeue", subject, "--reason", "<reason>"), queue_state)
        if fallback:
            out["cli_fallback"] = fallback
    coordination = engine.message_attention(work_id=None if subject == "project" else subject)
    if coordination is not None:
        out["coordination"] = coordination
        ids = [m["id"] for m in coordination["awaiting_lead"]]
        if ids:
            hints.append(f"{len(ids)} worker message(s) await the Lead: {', '.join(ids)}")
    return out


def _anomaly(a: dict[str, Any]) -> dict[str, Any]:
    """An open anomaly as the projection lists it (a blocker's shape: its source is the code)."""
    return _blocker(str(a["source"]), str(a["detail"]), {"anomaly": a["id"], "severity": a["severity"],
                                                          "subject": a["subject"], "opened_rev": a["rev"]})
