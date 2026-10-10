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
  - evidence: the reports a decision binds, resolved by kind, scope and producing run in the sealed evidence store.

Separately from availability (legality), each action says whether the caller can call it on its surface profile
(``callable``, presentation only) and whether a stage runner may advance it without judgment (``auto_runnable``,
never for a query or a wait, never dependent on the profile). Decisions never carry a default.
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from aew.engine.guards import GUARD_NOT_QUERYABLE
from aew.engine.primitives import spec_for
from aew.errors import AEWError
from aew.harness import contract as K
from aew.knowledge import evidence as E
from aew.surface import availability as SA
from aew.surface import contract
from aew.surface.classify import AVAILABLE, BLOCKED, UNKNOWN, auto_runnable, effective_class
from aew.surface.context import SurfaceContext
from aew.util import utc_now

LIVE = (K.STARTING, K.RUNNING)
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
            cli_fallback: list[str] | None) -> dict[str, Any]:
    t = contract.tool(name)
    klass = effective_class(t, arguments) if t is not None else spec_for(name).operation_class
    return {"action": name, "kind": kind, "arguments": arguments, "operation_class": klass,
            "availability": availability, "callable": False,
            "auto_runnable": auto_runnable(t, availability, klass),
            "reason_codes": sorted(set(reason_codes)), "cli_fallback": cli_fallback}


def _decision(name: str, subject: str, *, tool: str | None, arguments: dict[str, Any] | None,
              cli_fallback: list[str] | None, evidence: list[str] | None = None,
              availability: str = UNKNOWN) -> dict[str, Any]:
    return {"decision": name, "subject": subject, "evidence": list(evidence or []), "tool": tool,
            "arguments": arguments, "availability": availability, "default": "NONE", "cli_fallback": cli_fallback}


def _blocker(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "message": message}
    if details:
        out["details"] = details
    return out


# ---------------------------------------------------------------------------------------------- the control part

def _control_part(engine: Any, subject: str) -> dict[str, Any]:
    """Committed facts only: nothing here may read run telemetry, submitted evidence or repository inputs."""
    state = engine.store.read()
    part: dict[str, Any] = {"revision": state["revision"],
                            "generation": int((state.get("lead") or {}).get("generation") or 0),
                            "subject": subject, "state": None, "unit": None, "actions": [], "decisions": [],
                            "blockers": []}
    _stage_decisions(part, state, subject)
    if subject == "project":
        return part
    unit = engine.status(subject)["work_unit"]  # hot, or archived as it stands now
    part["state"] = unit.get("state")
    part["unit"] = {"kind": unit.get("kind"), "mutating": bool(unit.get("mutating")),
                    "integration": dict(unit.get("integration") or {})}
    for b in unit.get("blocked_by") or []:
        kind = str(b.get("kind") or "blocked")
        part["blockers"].append(_blocker(kind.upper(), kind.replace("_", " "),
                                         {k: v for k, v in b.items() if k != "kind"}))
    if unit.get("kind") == "ticket":
        _ticket_actions(part, subject, int(part["revision"]))
    return part


def _stage_decisions(part: dict[str, Any], state: dict[str, Any], subject: str) -> None:
    """An unfinished stage of the subject (every one, for the project) is the current Lead's to resolve, continue or
    abandon, never inferred (M4-E E3c; §3.4 rule 8). The decision names the intent and carries no choice: no
    default."""
    r = str(part["revision"])
    for sid, si in sorted((state.get("stage_intents") or {}).items()):
        if subject == "project" or si["subject"]["id"] == subject:
            part["decisions"].append({"decision": "RESOLVE_STAGE", "tool": "resolve", "evidence": [sid],
                                      "arguments": {"expect_rev": part["revision"], "subject": sid},
                                      "cli": ["stage", "<continue|abandon>", sid, "--rationale", "<why>",
                                              "--expect-rev", r]})


def _ticket_actions(part: dict[str, Any], wid: str, rev: int) -> None:
    """The decisions a Ticket's state requires, each named by its stable typed tool (so the vocabulary does not change
    when F15.2 builds it) with the primitive command that does it today. A decision that accepts a report is completed
    per report by the evidence overlay, which also asks its stage's availability (E4); a decision whose stage is not
    migrated stays UNKNOWN. The stage actions are the legality overlay's (:func:`_stage_actions`)."""
    st = part["state"]
    integration = part["unit"]["integration"]
    r = str(rev)
    if st == "REVIEW_PENDING":
        part["decisions"].append({"decision": "ACCEPT_REVIEW_EVIDENCE", "role": "reviewer", "kind": "review",
                                  "scope": None, "tool": "ticket_request_verification", "argument": "review_evidence",
                                  "cli": ["review", "ingest", wid, "--evidence", "{evidence}", "--expect-rev", r]})
    elif st == "VERIFY_PENDING":
        part["decisions"].append({"decision": "ACCEPT_VERIFICATION", "role": "verifier", "kind": "verification",
                                  "scope": "ticket", "tool": "ticket_prepare", "argument": "verification_evidence",
                                  "cli": ["verify", "ingest", wid, "--evidence", "{evidence}", "--expect-rev", r]})
    elif st == "VERIFICATION_FAILED":
        part["decisions"].append({"decision": "CLASSIFY_FAILURE", "tool": None,
                                  "cli": ["verify", "classify", wid, "--as", "<classification>", "--reason",
                                          "<why>", "--expect-rev", r]})
    elif st == "COMMIT_READY" and integration.get("status") == "prepared":
        # A prepared candidate is validated after integration before it may be published (the engine's own guidance):
        # by an integration verifier, whose report is the decision offered here, or, in checks mode, by the engine's
        # own validation (D5), which needs no Lead decision. Publication is offered only once it is validated.
        part["decisions"].append({"decision": "ACCEPT_VERIFICATION", "role": "verifier", "kind": "verification",
                                  "scope": "integration", "tool": None, "argument": None,
                                  "cli": ["verify", "ingest", wid, "--evidence", "{evidence}", "--expect-rev", r]})
    elif st == "COMMIT_READY" and integration.get("status") == "validated":
        candidate = integration.get("candidate")
        part["decisions"].append({"decision": "PUBLISH", "tool": "integration_publish",
                                  "arguments": {"expect_rev": rev, "work_id": wid,
                                                **({"prepared_candidate": str(candidate)} if candidate else {})},
                                  "cli": ["integrate", "publish", wid, "--expect-rev", r]})
    elif st == "INTERRUPTED":
        part["decisions"].append({"decision": "RECONCILE", "tool": None,
                                  "cli": ["work", "reconcile", wid, "--to", "<phase>", "--expect-rev", r]})


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
    report = engine.status()
    lines = [str(x) for x in report.get("next_actions") or []]
    if subject == "project":
        return lines, [_blocker("CONTRADICTION", str(c)) for c in report.get("contradictions") or []]
    prefix = f"{subject}: "
    return [a[len(prefix):] for a in lines if a.startswith(prefix)], []


def _stage_actions(engine: Any, part: dict[str, Any], wid: str) -> tuple[list[dict[str, Any]],
                                                                            list[dict[str, Any]]]:
    """The subject's next stage (or, for a non-mutating Ticket, its next dispatch), with its availability now: a
    stage's is composed per step from its guards (M4-E E4), a dispatch's is its ``DispatchDecision``. Allowed is
    AVAILABLE, refused is BLOCKED with its conditions, and anything a guard cannot answer is UNKNOWN (never
    BLOCKED)."""
    unit = part["unit"]
    if unit is None or unit["kind"] != "ticket":
        return [], []
    rev, st = part["revision"], part["state"]
    r = str(rev)
    if unit["mutating"] and st in ("READY", "BLOCKED"):
        stage, cli = "ticket_start", ["work", "assign", wid, "--launch", "--expect-rev", r]
    elif unit["mutating"] and st == "RUNNING":
        stage, cli = "ticket_request_review", ["work", "transition", wid, "--to", "REVIEW_PENDING", "--expect-rev", r]
    elif not unit["mutating"] and st in ("READY", "BLOCKED"):
        return _nm_dispatch(engine, part, wid)
    else:
        return [], []
    found = SA.stage_availability(engine, stage, {"work_id": wid})
    action = _action(stage, {"expect_rev": rev, "work_id": wid}, kind=contract.STAGE,
                     availability=found["availability"], reason_codes=found["reason_codes"], cli_fallback=cli)
    blockers = [_blocker(b["code"], b["message"], b.get("details")) for b in found["blockers"]]
    return [action], blockers


def _nm_dispatch(engine: Any, part: dict[str, Any], wid: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A non-mutating Ticket's dispatch, answered by ``DispatchDecision`` now (no stage dispatches one)."""
    rev = part["revision"]
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
    cli = ["work", "dispatch", wid, "--launch", "--expect-rev", str(rev)] if entrypoint == "work.dispatch" else None
    return [_action(entrypoint, {"work_id": wid}, kind=contract.PRIMITIVE, availability=availability,
                    reason_codes=reasons, cli_fallback=cli)], blockers


def _runs(engine: Any, subject: str) -> list[dict[str, Any]]:
    """Local run telemetry, read now: the latest run of every active invocation (of the subject)."""
    observed_at = utc_now()
    out = []
    for r in engine.harness_resume(engine.store.read()):
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


def _decisions(engine: Any, part: dict[str, Any], subject: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for d in part["decisions"]:
        if "role" not in d:
            arguments = d.get("arguments")
            found = UNKNOWN
            if arguments is not None and d["tool"] and SA.migrated(d["tool"]):  # PUBLISH: its stage's (M4-E E4b)
                found = SA.stage_availability(engine, d["tool"], {k: v for k, v in arguments.items()
                                                                  if k != "expect_rev"})["availability"]
            out.append(_decision(d["decision"], subject, tool=d["tool"], arguments=arguments,
                                 cli_fallback=list(d["cli"]), evidence=d.get("evidence"), availability=found))
            continue
        for e in _reports(engine, subject, runs, d):  # one decision per report, bound to it
            arguments = ({"expect_rev": part["revision"], "work_id": subject, d["argument"]: e}
                         if d["argument"] else None)
            found = UNKNOWN
            if arguments is not None and SA.migrated(d["tool"]):  # its stage's availability with this report (E4)
                found = SA.stage_availability(engine, d["tool"], {k: v for k, v in arguments.items()
                                                                  if k != "expect_rev"})["availability"]
            out.append(_decision(d["decision"], subject, tool=d["tool"], evidence=[e], arguments=arguments,
                                 cli_fallback=[x.replace("{evidence}", e) for x in d["cli"]], availability=found))
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
    live = [r["run"] for r in runs if r["status"] in LIVE]
    if live:
        actions.append(_action("harness_wait", {"runs": live}, kind=contract.WAIT, availability=AVAILABLE,
                               reason_codes=[], cli_fallback=["harness", "wait", *live,
                                                              *(["--any"] if len(live) > 1 else [])]))
    for a in actions:
        a["callable"] = contract.callable_on(contract.tool(a["action"]), ctx.profile)
    return {"revision": part["revision"], "generation": part["generation"], "subject": subject,
            "state": part["state"], "actions": actions, "decisions_required": _decisions(engine, part, subject, runs),
            "blockers": blockers, "anomalies": [], "hints": hints, "runs": runs}
