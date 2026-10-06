"""``ActionProjection``: what is known to be available, blocked or not yet queryable (design v0.2 §3.3, §8, §12.3).

The one projection module: every ``StageResult`` and the typed ``status`` use it, and later the dashboard's
``/attention`` and the scheduler. It derives only from accepted query surfaces (``status``, ``DispatchDecision``,
committed state) and explicit local telemetry; it is not a second planner. Three parts, by how their answer can
change:

* **control part** (cached): the subject's state, the engine's hints, blockers, and the transition and decision
  actions whose guards are not yet queryable (``UNKNOWN``, never ``BLOCKED``). It depends only on the committed
  control file and the project's policy and manifest files, so it is keyed on their identities and recomputed only
  when one changes (a commit, a policy edit), never per call;
* **legality overlay** (never cached in F15.1): dispatch availability, asked of ``DispatchDecision`` on every call.
  Its guards also read repository inputs and the authoritative head, which change without a commit; F15.4's
  ``legality_digest`` is what will let it be keyed;
* **run overlay** (never cached in F15.1): local run telemetry. Heartbeats change liveness without a commit or a wake;
  when U1's run health lands, its event watermark keys this part.

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

from aew.engine.primitives import spec_for
from aew.errors import AEWError
from aew.harness import contract as K
from aew.surface import contract
from aew.surface.classify import AVAILABLE, BLOCKED, UNKNOWN, auto_runnable, effective_class
from aew.surface.context import SurfaceContext
from aew.util import utc_now

GUARD_NOT_QUERYABLE = "GUARD_NOT_QUERYABLE"  # the action's guard has no query form yet (migrates in F15.2)
LIVE = (K.STARTING, K.RUNNING)
CACHE_SIZE = 64

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
              cli_fallback: list[str] | None, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"decision": name, "subject": subject, "evidence": list(evidence or []), "tool": tool,
            "arguments": arguments, "availability": UNKNOWN, "default": "NONE", "cli_fallback": cli_fallback}


def _blocker(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"code": code, "message": message}
    if details:
        out["details"] = details
    return out


# ---------------------------------------------------------------------------------------------- the control part

def _control_part(engine: Any, subject: str) -> dict[str, Any]:
    report = engine.status()
    lead = report.get("lead") or {}
    part: dict[str, Any] = {"revision": report["revision"], "generation": int(lead.get("generation") or 0),
                            "subject": subject, "state": None, "unit": None, "actions": [], "decisions": [],
                            "blockers": [], "hints": []}
    if subject == "project":
        part["hints"] = [str(a) for a in report.get("next_actions") or []]
        for c in report.get("contradictions") or []:
            part["blockers"].append(_blocker("CONTRADICTION", str(c)))
        return part
    unit = engine.status(subject)["work_unit"]
    prefix = f"{subject}: "
    part["hints"] = [a[len(prefix):] for a in (str(x) for x in report.get("next_actions") or [])
                     if a.startswith(prefix)]
    part["state"] = unit.get("state")
    part["unit"] = {"kind": unit.get("kind"), "mutating": bool(unit.get("mutating")),
                    "integration": dict(unit.get("integration") or {})}
    for b in unit.get("blocked_by") or []:
        kind = str(b.get("kind") or "blocked")
        part["blockers"].append(_blocker(kind.upper(), kind.replace("_", " "),
                                         {k: v for k, v in b.items() if k != "kind"}))
    if unit.get("kind") == "ticket":
        _ticket_actions(part, subject, int(report["revision"]))
    return part


def _ticket_actions(part: dict[str, Any], wid: str, rev: int) -> None:
    """Transitions and decisions whose guards are not queryable yet: present, UNKNOWN, never auto-runnable. Each is
    named by its stable typed tool (so the vocabulary does not change when F15.2 builds it) with the primitive command
    that does it today. Evidence for review and verification decisions comes from the run overlay."""
    st, mutating = part["state"], part["unit"]["mutating"]
    r = str(rev)
    if st == "RUNNING" and mutating:
        part["actions"].append(_action(
            "ticket_request_review", {"expect_rev": rev, "work_id": wid}, kind=contract.STAGE, availability=UNKNOWN,
            reason_codes=[GUARD_NOT_QUERYABLE],
            cli_fallback=["work", "transition", wid, "--to", "REVIEW_PENDING", "--expect-rev", r]))
    elif st == "REVIEW_PENDING":
        part["decisions"].append({"decision": "ACCEPT_REVIEW_EVIDENCE", "role": "reviewer",
                                  "tool": "ticket_request_verification", "argument": "review_evidence",
                                  "cli": ["review", "ingest", wid, "--evidence", "{evidence}", "--expect-rev", r]})
    elif st == "VERIFY_PENDING":
        part["decisions"].append({"decision": "ACCEPT_VERIFICATION", "role": "verifier", "tool": "ticket_prepare",
                                  "argument": "verification_evidence",
                                  "cli": ["verify", "ingest", wid, "--evidence", "{evidence}", "--expect-rev", r]})
    elif st == "VERIFICATION_FAILED":
        part["decisions"].append({"decision": "CLASSIFY_FAILURE", "tool": None,
                                  "cli": ["verify", "classify", wid, "--as", "<classification>", "--reason",
                                          "<why>", "--expect-rev", r]})
    elif st == "COMMIT_READY" and (part["unit"]["integration"].get("status") == "prepared"):
        candidate = part["unit"]["integration"].get("candidate")
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

def _dispatch_action(engine: Any, part: dict[str, Any], wid: str) -> tuple[dict[str, Any] | None,
                                                                            list[dict[str, Any]]]:
    """The subject's next dispatch, answered by ``DispatchDecision`` now: allowed is AVAILABLE, refused is BLOCKED
    with its conditions, and anything the predicate cannot answer is UNKNOWN (never BLOCKED)."""
    unit = part["unit"]
    if unit is None or unit["kind"] != "ticket" or part["state"] not in ("READY", "BLOCKED"):
        return None, []
    rev = part["revision"]
    entrypoint = "work.assign" if unit["mutating"] else "work.dispatch"
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
    cli = ["work", "assign" if entrypoint == "work.assign" else "dispatch", wid, "--launch", "--expect-rev", str(rev)]
    if entrypoint == "work.assign":
        return _action("ticket_start", {"expect_rev": rev, "work_id": wid}, kind=contract.STAGE,
                       availability=availability, reason_codes=reasons, cli_fallback=cli), blockers
    return _action(entrypoint, {"work_id": wid}, kind=contract.PRIMITIVE, availability=availability,
                   reason_codes=reasons, cli_fallback=cli if entrypoint == "work.dispatch" else None), blockers


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


# ---------------------------------------------------------------------------------------------- assembly

def project(engine: Any, ctx: SurfaceContext, subject: str | None = None) -> dict[str, Any]:
    """The ``ActionProjection`` for ``subject`` (a work unit id) or the project."""
    subject = subject or "project"
    part = _cached_control_part(engine, subject)
    actions = [dict(a) for a in part["actions"]]
    blockers = [dict(b) for b in part["blockers"]]
    dispatch, dispatch_blockers = _dispatch_action(engine, part, subject)
    if dispatch is not None:
        actions.insert(0, dispatch)
        blockers.extend(dispatch_blockers)
    runs = _runs(engine, subject)
    live = [r["run"] for r in runs if r["status"] in LIVE]
    if live:
        actions.append(_action("harness_wait", {"runs": live}, kind=contract.WAIT, availability=AVAILABLE,
                               reason_codes=[], cli_fallback=["harness", "wait", *live,
                                                              *(["--any"] if len(live) > 1 else [])]))
    for a in actions:
        a["callable"] = contract.callable_on(contract.tool(a["action"]), ctx.profile)
    return {"revision": part["revision"], "generation": part["generation"], "subject": subject,
            "state": part["state"], "actions": actions, "decisions_required": _decisions(part, subject, runs),
            "blockers": blockers, "anomalies": [], "hints": list(part["hints"]), "runs": runs}


def _decisions(part: dict[str, Any], subject: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for d in part["decisions"]:
        if "role" in d:  # one decision per inspected report a finished run of that role produced
            reports = sorted({e for r in runs if r["role"] == d["role"] and r["status"] == K.ENDED_WITH_EVIDENCE
                              for e in r["evidence"]})
            for e in reports:
                out.append(_decision(
                    d["decision"], subject, tool=d["tool"], evidence=[e],
                    arguments={"expect_rev": part["revision"], "work_id": subject, d["argument"]: e},
                    cli_fallback=[x.replace("{evidence}", e) for x in d["cli"]]))
        else:
            out.append(_decision(d["decision"], subject, tool=d["tool"], arguments=d.get("arguments"),
                                 cli_fallback=list(d["cli"])))
    return out

