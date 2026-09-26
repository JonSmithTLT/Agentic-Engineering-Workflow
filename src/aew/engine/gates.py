"""Effective obligations and gate evaluation against the *current* evaluated snapshot.

Effective obligations (WC §7.4):

    local risk-class path
  + inherited non-waivable ancestor gates/guardrails
  + any explicit parent minimum-class floor
  + review gates triggered by guardrail paths

A gate is satisfied only by passing evidence whose evaluated-snapshot fingerprint
equals the workspace's *current* fingerprint and whose plan revision equals the
accepted one (WC §9.9, invariant 7). Otherwise the gate is STALE (passing evidence
exists for another snapshot/plan), FAILED (the latest evidence for this snapshot
fails) or MISSING. Evidence is never modified; staleness is computed.

Which evidence may satisfy a gate (review 2026-09-26 M4; KC §7.2/§16):

* review and verification gates count only reports the Lead has **ingested** —
  their id and sha256 are pinned in the Ticket's accepted evidence refs. A sealed
  submission that was never ingested (or whose bytes changed) satisfies nothing,
  so one ingest can never retire another required report that still awaits its
  own ingestion checks;
* ``local_checks`` and ``self_review`` count the implementer's submissions: their
  acceptance *is* the Lead's RUNNING -> REVIEW/VERIFY transition, which pins the
  evidence it relied on (``_record_relied_on``).
"""

from __future__ import annotations

from typing import Any

CURRENT, STALE, MISSING, FAILED, WAIVED = "CURRENT", "STALE", "MISSING", "FAILED", "WAIVED"
REVIEW_GATES_PREFIX = "review_"
REVIEW_CARD_PREFIX = "review_card:"
VERIFY_CARD_PREFIX = "verify_card:"
VERIFICATION_GATES = ("verification_goal_backwards", "verification_contract")


def _card(e: dict[str, Any]) -> str | None:
    return (e["producer"].get("role_card") or {}).get("id")


def _verification_passes(e: dict[str, Any]) -> bool:
    types = {c["type"] for c in e["verification"]["claims"]}
    return (e["result"] == "pass" and {"goal_backwards", "contract"} <= types
            and all(c["result"] == "pass" for c in e["verification"]["claims"]))


def ancestors(state: dict[str, Any], work_id: str) -> list[str]:
    out = []
    parent = state["work"][work_id].get("parent")
    while parent:
        out.append(parent)
        parent = state["work"][parent].get("parent")
    return out


def effective_obligations(
    state: dict[str, Any], work_id: str, gates_policy: dict[str, Any], triggered: list[str] | None = None,
    plan_gates: dict[str, str] | None = None,
) -> dict[str, Any]:
    unit = state["work"][work_id]
    local = unit["risk_class"]
    floor = None
    inherited: dict[str, list[str]] = {}
    for anc in ancestors(state, work_id):
        policy = state["work"][anc].get("policy") or {}
        if policy.get("min_descendant_class") is not None:
            floor = max(floor or 0, policy["min_descendant_class"])
        for gate in policy.get("mandatory_gates", []):
            inherited.setdefault(gate, []).append(anc)
    effective_class = max(local, floor) if floor is not None else local
    gates = list(gates_policy["risk_paths"][str(effective_class)])
    sources = {g: [f"class {effective_class} path"] for g in gates}
    for gate, from_ in inherited.items():
        if gate not in gates:
            gates.append(gate)
        sources.setdefault(gate, []).append(f"inherited (non-waivable) from {', '.join(from_)}")
    for gate in triggered or []:
        if gate not in gates:
            gates.append(gate)
        sources.setdefault(gate, []).append("triggered by guardrail review_triggers (policy)")
    for gate, why in (plan_gates or {}).items():
        if gate not in gates:
            gates.append(gate)
        sources.setdefault(gate, []).append(why)
    return {
        "local_class": local,
        "floor": floor,
        "effective_class": effective_class,
        "gates": gates,
        "non_waivable": sorted(inherited),
        "sources": sources,
    }


def _matches(e: dict[str, Any], fingerprint: str | None, plan_rev: int | None) -> bool:
    snap = e["evaluated_snapshot"]["relevant_inputs_fingerprint"]
    rev = (e.get("plan_revision") or {}).get("revision")
    return fingerprint is not None and snap == fingerprint and rev == plan_rev


def _latest_status(
    candidates: list[dict[str, Any]], passing: Any, fingerprint: str | None, plan_rev: int | None
) -> tuple[str, str | None]:
    """Status from the latest candidate for the current snapshot, else STALE/MISSING."""
    current = [e for e in candidates if _matches(e, fingerprint, plan_rev)]
    if current:
        latest = current[-1]
        return (CURRENT if passing(latest) else FAILED), latest["id"]
    if any(passing(e) for e in candidates):
        return STALE, [e for e in candidates if passing(e)][-1]["id"]
    return MISSING, None


def evaluate(
    state: dict[str, Any],
    work_id: str,
    evidence: list[dict[str, Any]],
    *,
    obligations: dict[str, Any],
    gates_policy: dict[str, Any],
    fingerprint: str | None,
    plan_ok: bool,
) -> dict[str, dict[str, Any]]:
    unit = state["work"][work_id]
    plan_rev = (unit.get("plan") or {}).get("accepted")
    invocations = state["invocations"]
    own = [e for e in evidence if e["producer"]["invocation"] in unit.get("invocations", [])]
    accepted_refs = {r["id"]: r.get("sha256") for r in unit.get("evidence", [])}
    ingested = [e for e in own if accepted_refs.get(e["id"]) == e.get("_sha256")]

    def by_role(role: str) -> list[dict[str, Any]]:
        return [e for e in own if invocations[e["producer"]["invocation"]]["role"] == role]

    waived = {w["gate"] for w in unit.get("waivers", []) if w.get("gate")}
    results: dict[str, dict[str, Any]] = {}

    for gate in obligations["gates"]:
        if gate in waived and gate not in obligations["non_waivable"]:
            results[gate] = {"status": WAIVED}
            continue
        if gate == "accepted_plan":
            results[gate] = {"status": CURRENT if plan_rev and plan_ok else (FAILED if plan_rev else MISSING)}
        elif gate == "local_checks":
            checks = {}
            for check_id in gates_policy.get("local_checks", []):
                cands = [e for e in by_role("implementer")
                         if e["kind"] == "check_result" and e["check"]["check_id"] == check_id]
                status, eid = _latest_status(cands, lambda e: e["result"] == "pass", fingerprint, plan_rev)
                checks[check_id] = {"status": status, "evidence": eid}
            worst = _worst([c["status"] for c in checks.values()]) if checks else CURRENT
            results[gate] = {"status": worst, "checks": checks}
        elif gate == "self_review":
            cands = [e for e in by_role("implementer") if e["kind"] == "implementation_report"]
            status, eid = _latest_status(
                cands, lambda e: bool(((e.get("implementation") or {}).get("self_review") or {}).get("completed"))
                and e["result"] == "pass", fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif gate.startswith(REVIEW_CARD_PREFIX):
            card = gate[len(REVIEW_CARD_PREFIX):]
            cands = [e for e in ingested if e["kind"] == "review" and _card(e) == card
                     and e["review"]["independence"] in {"R1", "R2", "R3"}]
            status, eid = _latest_status(cands, lambda e: e["review"]["disposition"] == "pass", fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif gate.startswith(VERIFY_CARD_PREFIX):
            card = gate[len(VERIFY_CARD_PREFIX):]
            cands = [e for e in ingested if e["kind"] == "verification" and _card(e) == card
                     and invocations[e["producer"]["invocation"]]["role"] == "verifier"
                     and e["verification"]["scope"] == "ticket"]
            status, eid = _latest_status(cands, _verification_passes, fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif gate.startswith(REVIEW_GATES_PREFIX):
            specialty = None if gate == "review_r1" else gate[len(REVIEW_GATES_PREFIX):]
            cands = [e for e in ingested if e["kind"] == "review"
                     and (e["review"].get("specialty") or None) == specialty
                     and e["review"]["independence"] in {"R1", "R2", "R3"}]
            status, eid = _latest_status(cands, lambda e: e["review"]["disposition"] == "pass", fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif gate in VERIFICATION_GATES:
            claim_type = "goal_backwards" if gate == "verification_goal_backwards" else "contract"
            cands = [e for e in ingested if e["kind"] == "verification"
                     and invocations[e["producer"]["invocation"]]["role"] == "verifier"
                     and e["verification"]["scope"] == "ticket"]

            def passing(e: dict[str, Any], claim_type: str = claim_type) -> bool:
                claims = [c for c in e["verification"]["claims"] if c["type"] == claim_type]
                return e["result"] == "pass" and bool(claims) and all(c["result"] == "pass" for c in claims)

            status, eid = _latest_status(cands, passing, fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        else:
            results[gate] = {"status": MISSING, "detail": "no evaluator for this gate in M1"}
    return results


def _worst(statuses: list[str]) -> str:
    for s in (FAILED, MISSING, STALE):
        if s in statuses:
            return s
    return CURRENT


def unmet(results: dict[str, dict[str, Any]], gates: list[str] | None = None) -> dict[str, str]:
    names = gates if gates is not None else list(results)
    return {g: results[g]["status"] for g in names if g in results and results[g]["status"] not in {CURRENT, WAIVED}}


def open_required_findings(unit: dict[str, Any]) -> list[dict[str, Any]]:
    waived = {w["finding"] for w in unit.get("waivers", []) if w.get("finding")}
    return [f for f in unit.get("findings", []) if f["required"] and f["status"] == "open" and f["id"] not in waived]
