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

A check result also proves only the check's definition that ran (its command, working directory and timeout in
``policy/checks.yaml``, recorded as ``check.definition_sha256``). When the definition changes, an in-flight Ticket
must satisfy the new one: a result for the old definition is STALE (decision (a), independent audit I1).

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

from aew.policy import checks as C

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


def effective_class(state: dict[str, Any], work_id: str) -> int:
    """A unit's risk class raised to the highest min_descendant_class floor of its ancestors."""
    floors = [(state["work"][anc].get("policy") or {}).get("min_descendant_class") for anc in ancestors(state, work_id)]
    return max([state["work"][work_id]["risk_class"], *(f for f in floors if f is not None)])


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
    check_definitions: dict[str, str],
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
                if check_id not in check_definitions:
                    # Say why it can never pass, rather than a bare MISSING (UAT 2026-09-30, policy consistency).
                    checks[check_id] = {"status": MISSING, "evidence": None,
                                        "reason": f"check `{check_id}` is not defined and configured in "
                                                  "policy/checks.yaml, so no result can satisfy it"}
                    continue
                cands = [e for e in by_role("implementer")
                         if e["kind"] == "check_result" and e["check"]["check_id"] == check_id]
                # A result proves the check as it was defined when it ran; only the current definition counts
                # (decision (a), independent audit I1).
                defined = [e for e in cands if C.proves_current_definition(e, check_definitions)]
                status, eid = _latest_status(defined, lambda e: e["result"] == "pass", fingerprint, plan_rev)
                checks[check_id] = {"status": status, "evidence": eid}
                earlier = [e for e in cands if e["result"] == "pass" and e not in defined]
                if status == MISSING and earlier:
                    checks[check_id] = {"status": STALE, "evidence": earlier[-1]["id"],
                                        "reason": "the check's definition in policy/checks.yaml changed after it "
                                                  "passed; run it again"}
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


def path_table(gates_policy: dict[str, Any], unit: dict[str, Any]) -> dict[str, list[str]]:
    """The risk-path table for a unit's type: mutating Tickets (M1), non-mutating Tickets, or parents.

    Projects created before M2 have no ``non_mutating_paths``/``parent_paths``; the built-in defaults apply.
    """
    from aew.knowledge.manifest import DEFAULT_GATES  # local import: manifest imports nothing from engine

    if unit["kind"] != "ticket":
        return gates_policy.get("parent_paths") or DEFAULT_GATES["parent_paths"]
    if not unit.get("mutating"):
        return gates_policy.get("non_mutating_paths") or DEFAULT_GATES["non_mutating_paths"]
    return gates_policy["risk_paths"]


def evaluate_evidence_unit(
    state: dict[str, Any],
    work_id: str,
    evidence: list[dict[str, Any]],
    *,
    obligations: dict[str, Any],
    special: dict[str, dict[str, Any]],
    is_current: Any,
) -> dict[str, dict[str, Any]]:
    """Gate status for a non-mutating Ticket or a Story/Epic (ADR-0007/0008). M1's ``evaluate`` is untouched.

    ``special`` supplies engine-computed gates (``accepted_plan``, ``execute_record``, ``children_complete``).
    ``is_current(e)`` decides whether a review/verification report still applies: for a non-mutating
    Ticket its subject must be the currently accepted execute record; for a parent it must be bound to the
    current parent snapshot (source + children digest). As in M1, only reports the Lead **ingested**
    (id + sha256 pinned on the unit) count, and plan revision must match.
    """
    unit = state["work"][work_id]
    plan_rev = (unit.get("plan") or {}).get("accepted")
    invocations = state["invocations"]
    accepted_refs = {r["id"]: r.get("sha256") for r in unit.get("evidence", [])}
    ingested = [e for e in evidence if accepted_refs.get(e["id"]) == e.get("_sha256")]
    waived = {w["gate"] for w in unit.get("waivers", []) if w.get("gate")}
    scope = "parent" if unit["kind"] != "ticket" else "ticket"

    def latest(cands: list[dict[str, Any]], passing: Any) -> dict[str, Any]:
        current = [e for e in cands if is_current(e) and (e.get("plan_revision") or {}).get("revision") == plan_rev]
        if current:
            return {"status": CURRENT if passing(current[-1]) else FAILED, "evidence": current[-1]["id"]}
        if any(passing(e) for e in cands):
            return {"status": STALE, "evidence": [e for e in cands if passing(e)][-1]["id"]}
        return {"status": MISSING, "evidence": None}

    def reviews(card: str | None = None, specialty: Any = False) -> list[dict[str, Any]]:
        out = [e for e in ingested if e["kind"] == "review" and e["review"]["independence"] in {"R1", "R2", "R3"}]
        if card is not None:
            out = [e for e in out if _card(e) == card]
        if specialty is not False:
            out = [e for e in out if (e["review"].get("specialty") or None) == specialty]
        return out

    def verifications(card: str | None = None) -> list[dict[str, Any]]:
        out = [e for e in ingested if e["kind"] == "verification" and e["verification"]["scope"] == scope
               and invocations[e["producer"]["invocation"]]["role"] == "verifier"]
        return [e for e in out if _card(e) == card] if card is not None else out

    results: dict[str, dict[str, Any]] = {}
    for gate in obligations["gates"]:
        if gate in waived and gate not in obligations["non_waivable"]:
            results[gate] = {"status": WAIVED}
        elif gate in special:
            results[gate] = special[gate]
        elif gate.startswith(REVIEW_CARD_PREFIX):
            results[gate] = latest(reviews(card=gate[len(REVIEW_CARD_PREFIX):]),
                                   lambda e: e["review"]["disposition"] == "pass")
        elif gate.startswith(VERIFY_CARD_PREFIX):
            results[gate] = latest(verifications(card=gate[len(VERIFY_CARD_PREFIX):]), _verification_passes)
        elif gate.startswith(REVIEW_GATES_PREFIX):
            specialty = None if gate == "review_r1" else gate[len(REVIEW_GATES_PREFIX):]
            results[gate] = latest(reviews(specialty=specialty), lambda e: e["review"]["disposition"] == "pass")
        elif gate in VERIFICATION_GATES:
            claim_type = "goal_backwards" if gate == "verification_goal_backwards" else "contract"

            def passing(e: dict[str, Any], claim_type: str = claim_type) -> bool:
                claims = [c for c in e["verification"]["claims"] if c["type"] == claim_type]
                return e["result"] == "pass" and bool(claims) and all(c["result"] == "pass" for c in claims)

            results[gate] = latest(verifications(), passing)
        else:
            results[gate] = {"status": MISSING, "detail": f"no evaluator for {gate} on this unit type"}
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
