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
  evidence it relied on (``Gates.record_relied_on``).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, NamedTuple

from aew.engine import hierarchy as H
from aew.policy import checks as C
from aew.policy import validation as V

CURRENT, STALE, MISSING, FAILED, WAIVED = "CURRENT", "STALE", "MISSING", "FAILED", "WAIVED"
REVIEW_GATES_PREFIX = "review_"
REVIEW_CARD_PREFIX = "review_card:"
VERIFY_CARD_PREFIX = "verify_card:"
# One configured check as a gate (ITEMS 55, designer addendum 1), evaluated by ``local_checks``' helper over that id.
CHECK_PREFIX = "check:"
VERIFICATION_GATES = ("verification_goal_backwards", "verification_contract")
# A Ticket's own acceptance checks (``--acceptance-check``) are required whatever the class's path lists, and are
# non-waivable: they are the Ticket's definition of acceptance, and Class 0 eligibility rests on them (PR #32 P1).
ACCEPTANCE_CHECKS = "acceptance_checks"

# ---- the gate kinds each evaluator dispatches (ITEMS 55, designer decision 1 and addenda 1 and 2)
#
# ``evaluate`` serves mutating Tickets; ``evaluate_evidence_unit`` serves non-mutating Tickets and Stories/Epics. Both
# dispatch through ``gate_kind``, and ``unsatisfiable`` reads the same tables, so what a writer accepts is what an
# evaluator evaluates: there is no second list.
MUTATING, NON_MUTATING, PARENT = "mutating Ticket", "non-mutating Ticket", "Story or Epic"
UNIT_TYPES = (MUTATING, NON_MUTATING, PARENT)
FIXED: dict[str, tuple[str, ...]] = {
    MUTATING: ("accepted_plan", "local_checks", ACCEPTANCE_CHECKS, "self_review", *VERIFICATION_GATES,
               V.INTEGRATION_VERIFIER_GATE),
    NON_MUTATING: ("accepted_plan", "execute_record", *VERIFICATION_GATES),
    PARENT: ("accepted_plan", "children_complete", *VERIFICATION_GATES),
}
# Longest first: a ``review_card:`` name also starts with ``review_``.
PREFIXES: dict[str, tuple[str, ...]] = {
    MUTATING: (REVIEW_CARD_PREFIX, VERIFY_CARD_PREFIX, CHECK_PREFIX, REVIEW_GATES_PREFIX),
    NON_MUTATING: (REVIEW_CARD_PREFIX, VERIFY_CARD_PREFIX, REVIEW_GATES_PREFIX),
    PARENT: (REVIEW_CARD_PREFIX, VERIFY_CARD_PREFIX, REVIEW_GATES_PREFIX),
}
# Obligations on a change (addendum 2, ruling 1): they apply to units that integrate one, mutating Tickets. Inherited
# onto a non-mutating Ticket or a parent, they pass through to its mutating descendants, unevaluated there. The
# integration verifier is one too (addendum 2's pointer line). ``validation.obligation`` still reads it for a Ticket.
CHANGE_ONLY = ("local_checks", ACCEPTANCE_CHECKS, "self_review", CHECK_PREFIX, V.INTEGRATION_VERIFIER_GATE)
CHANGE_ONLY_NOTE = "applies to units that integrate a change"


def unit_type(unit: Mapping[str, Any]) -> str:
    if unit["kind"] != "ticket":
        return PARENT
    return MUTATING if unit.get("mutating") else NON_MUTATING


def gate_kind(gate: str, utype: str = MUTATING) -> str | None:
    """The kind ``gate`` is on ``utype``'s evaluator: the fixed name itself, or its prefix. None: no evaluator."""
    if gate in FIXED[utype]:
        return gate
    return next((p for p in PREFIXES[utype] if gate.startswith(p)), None)


def change_only(gate: str) -> bool:
    return gate_kind(gate, MUTATING) in CHANGE_ONLY


class Catalogue(NamedTuple):
    """What a gate name's suffix resolves against (addendum 1): the role catalogue's cards, each reviewer specialty's
    candidate cards, the checks defined and configured (``checks.current_definitions``), and the gates policy's
    ``local_checks``. Built by the caller from the project, so this module reads nothing."""
    cards: frozenset[str]
    specialties: Mapping[str, tuple[str, ...]]
    checks: Mapping[str, str]
    local_checks: tuple[str, ...]


class Unsatisfiable(NamedTuple):
    """Why a gate can never be satisfied: what did not resolve, and the candidates that exist."""
    gate: str
    why: str
    candidates: tuple[str, ...]

    @property
    def message(self) -> str:
        listed = ", ".join(f"`{c}`" for c in self.candidates) or "none"
        return f"gate `{self.gate}` can never be satisfied: {self.why} (the candidates: {listed})"


def gate_kinds(utype: str = MUTATING) -> tuple[str, ...]:
    """The kinds ``utype``'s evaluator has, as a refusal lists them: the fixed names, then each prefix and ``<...>``."""
    suffix = {REVIEW_CARD_PREFIX: "<card>", VERIFY_CARD_PREFIX: "<card>", CHECK_PREFIX: "<check id>",
              REVIEW_GATES_PREFIX: "<specialty>"}
    return (*FIXED[utype], *(p + suffix[p] for p in PREFIXES[utype]))


def unsatisfiable(gate: str, utype: str = MUTATING, catalogue: Catalogue | None = None) -> Unsatisfiable | None:
    """Whether ``gate`` can be satisfied on a unit of ``utype`` (ITEMS 55, decision 1; addendum 1: "can be
    satisfied", not "reaches an evaluator"): None when it can, else why not.

    The kind comes from ``gate_kind``, the evaluators' own dispatch. Its suffix must resolve against ``catalogue``: a
    ``review_<specialty>`` needs a card with that specialty (``review_r1`` needs none), a card gate needs the card, and
    ``check:<id>`` and each of ``local_checks``' ids need the check defined and configured. Without a catalogue (in
    ``evaluate`` itself, which has none) only the kind is judged.

    The named limit: "can be satisfied" is not "will pass". A card can exist and never be launched; this catches only
    the names that can never pass."""
    kind = gate_kind(gate, utype)
    if kind is None:
        return Unsatisfiable(gate, f"AEW has no gate of that kind for a {utype}: state the standard as one of the "
                                   "kinds that exist, a configured check (`check:<check id>`) or a review or "
                                   "verification gate whose claim the verifier checks", gate_kinds(utype))
    if catalogue is None:
        return None
    if kind == REVIEW_GATES_PREFIX and gate != "review_r1":
        specialty = gate[len(REVIEW_GATES_PREFIX):]
        if not catalogue.specialties.get(specialty):
            return Unsatisfiable(gate, f"no reviewer card in the role catalogue has specialty `{specialty}`",
                                 tuple(sorted(REVIEW_GATES_PREFIX + s for s, cards in catalogue.specialties.items()
                                              if cards)))
    elif kind in (REVIEW_CARD_PREFIX, VERIFY_CARD_PREFIX):
        card = gate[len(kind):]
        if card not in catalogue.cards:
            return Unsatisfiable(gate, f"the role catalogue has no card `{card}`",
                                 tuple(kind + c for c in sorted(catalogue.cards)))
    elif kind in (CHECK_PREFIX, "local_checks"):
        ids = [gate[len(CHECK_PREFIX):]] if kind == CHECK_PREFIX else list(catalogue.local_checks)
        undefined = [i for i in ids if i not in catalogue.checks]
        if undefined:
            return Unsatisfiable(gate, "check " + ", ".join(f"`{i}`" for i in undefined) + " is not defined and "
                                       "configured in policy/checks.yaml",
                                 tuple(CHECK_PREFIX + c for c in sorted(catalogue.checks)))
    return None


UNDER = {"ticket": "a Ticket", "story": "a Story", "epic": "an Epic"}


def _descendant_kinds(kind: str) -> set[str]:
    kinds: set[str] = set()
    frontier = {kind}
    while frontier:
        frontier = {c for c, parents in H.PARENT_KINDS.items() if parents & frontier} - kinds
        kinds |= frontier
    return kinds


def descendant_types(kind: str) -> tuple[str, ...]:
    """The unit types that can sit under a unit of ``kind``: ``hierarchy.PARENT_KINDS`` read the other way (a Story's
    are Tickets; an Epic's are Stories and Tickets)."""
    types = {t for c in _descendant_kinds(kind) for t in ((MUTATING, NON_MUTATING) if c == "ticket" else (PARENT,))}
    return tuple(t for t in UNIT_TYPES if t in types)


def _inherited(gate: str, kind: str, catalogue: Catalogue) -> Iterator[tuple[str, Unsatisfiable | None]]:
    """Each unit type under a unit of ``kind`` that a mandatory gate binds, with ``unsatisfiable``'s verdict on it. A
    change-only gate passes through the others unevaluated (addendum 2, ruling 1), so they have no verdict: they
    neither fail it nor evaluate it."""
    for utype in descendant_types(kind):
        if utype == MUTATING or not change_only(gate):
            yield utype, unsatisfiable(gate, utype, catalogue)


def unsatisfiable_inherited(gate: str, kind: str, catalogue: Catalogue) -> Unsatisfiable | None:
    """A mandatory gate set on a unit of ``kind``, which every descendant inherits (``effective_obligations``):
    refused when any unit type that can sit under it can neither satisfy it nor pass it through (addendum 2, ruling
    1: a change-only gate passes through to mutating descendants; ITEMS 55 review F1). Every writer and the
    replacement gate call this one function, so the rule changes in one place."""
    for utype, found in _inherited(gate, kind, catalogue):
        if found is not None:
            return found._replace(why=f"a {utype} can sit under {UNDER[kind]} and inherits it, and {found.why}")
    return None


def _named(utype: str, kind: str) -> str:
    """``utype`` as it sits under a unit of ``kind``: the only parent under an Epic is a Story."""
    if utype != PARENT:
        return utype
    return " or ".join(sorted(k.capitalize() for k in _descendant_kinds(kind) - {"ticket"}))


def satisfiable_by(gate: str, kind: str, catalogue: Catalogue) -> tuple[str, ...]:
    """The unit types under a unit of ``kind`` that can satisfy its mandatory ``gate``. Any at all means the gate has
    an evaluator, so changing it is the operator's decision (designer, ITEMS 55 addendum 5, on the operator's condition
    2). Passing a gate through is not evaluating it: an undefined `check:<id>` has no evaluator on a mutating Ticket,
    and a non-mutating Ticket's pass-through does not give it one."""
    return tuple(_named(t, kind) for t, found in _inherited(gate, kind, catalogue) if found is None)


def stranded_by(gate: str, kind: str, catalogue: Catalogue) -> tuple[str, ...]:
    """The unit types under a unit of ``kind`` that its mandatory ``gate`` binds and that can never satisfy it."""
    return tuple(_named(t, kind) for t, found in _inherited(gate, kind, catalogue) if found is not None)


def with_acceptance_checks(obligations: dict[str, Any], declared: list[str]) -> dict[str, Any]:
    if not declared:
        return obligations
    gates = list(obligations["gates"])
    if ACCEPTANCE_CHECKS not in gates:
        gates.insert(gates.index("local_checks") + 1 if "local_checks" in gates else 0, ACCEPTANCE_CHECKS)
    return {**obligations, "gates": gates,
            "non_waivable": sorted(set(obligations["non_waivable"]) | {ACCEPTANCE_CHECKS})}


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
    # A change-only gate inherited by a unit that integrates no change passes through to its mutating descendants:
    # listed, never evaluated here, never CURRENT (ITEMS 55, addendum 2, ruling 1). It stays non-waivable.
    passes = unit_type(unit) != MUTATING
    pass_through: dict[str, str] = {}
    for gate, from_ in inherited.items():
        sources.setdefault(gate, []).append(f"inherited (non-waivable) from {', '.join(from_)}")
        if passes and change_only(gate):
            pass_through[gate] = CHANGE_ONLY_NOTE
            sources[gate].append(CHANGE_ONLY_NOTE)
        elif gate not in gates:
            gates.append(gate)
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
        "pass_through": pass_through,
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
    acceptance_checks: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """``acceptance_checks``: the checks the Ticket itself declares decide its acceptance (``--acceptance-check``);
    they are the ``acceptance_checks`` gate, evaluated like ``local_checks`` (M4-A review, PR #32 P1)."""
    unit = state["work"][work_id]
    plan_rev = (unit.get("plan") or {}).get("accepted")
    invocations = state["invocations"]
    own = [e for e in evidence if e["producer"]["invocation"] in unit.get("invocations", [])]
    accepted_refs = {r["id"]: r.get("sha256") for r in unit.get("evidence", [])}
    ingested = [e for e in own if accepted_refs.get(e["id"]) == e.get("_sha256")]

    def by_role(role: str) -> list[dict[str, Any]]:
        # An engine custodian's check evidence (M4-D5, ``producer.kind: engine``) has no role and is never a role's.
        return [e for e in own if (invocations.get(e["producer"]["invocation"]) or {}).get("role") == role]

    waived = {w["gate"] for w in unit.get("waivers", []) if w.get("gate")}
    results: dict[str, dict[str, Any]] = {}

    def check_gate(check_ids: list[str]) -> dict[str, Any]:
        checks = {}
        for check_id in check_ids:
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
        return {"status": worst, "checks": checks}

    for gate in obligations["gates"]:
        if gate in waived and gate not in obligations["non_waivable"]:
            results[gate] = {"status": WAIVED}
            continue
        kind = gate_kind(gate, MUTATING)  # the one dispatch, which ``unsatisfiable`` reads too (ITEMS 55)
        if kind == "accepted_plan":
            results[gate] = {"status": CURRENT if plan_rev and plan_ok else (FAILED if plan_rev else MISSING)}
        elif kind == "local_checks":
            results[gate] = check_gate(gates_policy.get("local_checks", []))
        elif kind == ACCEPTANCE_CHECKS:
            results[gate] = check_gate(list(acceptance_checks or []))
        elif kind == CHECK_PREFIX:
            results[gate] = check_gate([gate[len(CHECK_PREFIX):]])
        elif kind == "self_review":
            cands = [e for e in by_role("implementer") if e["kind"] == "implementation_report"]
            status, eid = _latest_status(
                cands, lambda e: bool(((e.get("implementation") or {}).get("self_review") or {}).get("completed"))
                and e["result"] == "pass", fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif kind == REVIEW_CARD_PREFIX:
            card = gate[len(REVIEW_CARD_PREFIX):]
            cands = [e for e in ingested if e["kind"] == "review" and _card(e) == card
                     and e["review"]["independence"] in {"R1", "R2", "R3"}]
            status, eid = _latest_status(cands, lambda e: e["review"]["disposition"] == "pass", fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif kind == VERIFY_CARD_PREFIX:
            card = gate[len(VERIFY_CARD_PREFIX):]
            cands = [e for e in ingested if e["kind"] == "verification" and _card(e) == card
                     and invocations[e["producer"]["invocation"]]["role"] == "verifier"
                     and e["verification"]["scope"] == "ticket"]
            status, eid = _latest_status(cands, _verification_passes, fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif kind == REVIEW_GATES_PREFIX:
            specialty = None if gate == "review_r1" else gate[len(REVIEW_GATES_PREFIX):]
            cands = [e for e in ingested if e["kind"] == "review"
                     and (e["review"].get("specialty") or None) == specialty
                     and e["review"]["independence"] in {"R1", "R2", "R3"}]
            status, eid = _latest_status(cands, lambda e: e["review"]["disposition"] == "pass", fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif kind in VERIFICATION_GATES:
            claim_type = "goal_backwards" if gate == "verification_goal_backwards" else "contract"
            cands = [e for e in ingested if e["kind"] == "verification"
                     and invocations[e["producer"]["invocation"]]["role"] == "verifier"
                     and e["verification"]["scope"] == "ticket"]

            def passing(e: dict[str, Any], claim_type: str = claim_type) -> bool:
                claims = [c for c in e["verification"]["claims"] if c["type"] == claim_type]
                return e["result"] == "pass" and bool(claims) and all(c["result"] == "pass" for c in claims)

            status, eid = _latest_status(cands, passing, fingerprint, plan_rev)
            results[gate] = {"status": status, "evidence": eid}
        elif kind == V.INTEGRATION_VERIFIER_GATE:
            # An integration-scope obligation (M4-D5): it decides how the integrated candidate is validated, and
            # integrate validate and publish enforce it there. Nothing at the Ticket's own snapshot satisfies it.
            results[gate] = {"status": CURRENT, "detail": "an integration-scope obligation: post-integration "
                                                          "validation must be a verifier's, enforced at publish"}
        else:
            results[gate] = _no_evaluator(gate, MUTATING)
    return results


def _no_evaluator(gate: str, utype: str) -> dict[str, Any]:
    """Both evaluators' last branch: MISSING, saying why from the predicate itself (ITEMS 55, decision 1)."""
    found = unsatisfiable(gate, utype)
    return {"status": MISSING, "detail": found.message if found else f"no evaluator for {gate} on a {utype}"}


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

    utype = unit_type(unit)
    results: dict[str, dict[str, Any]] = {}
    for gate in obligations["gates"]:
        kind = gate_kind(gate, utype)  # the one dispatch, which ``unsatisfiable`` reads too (ITEMS 55)
        if gate in waived and gate not in obligations["non_waivable"]:
            results[gate] = {"status": WAIVED}
        elif kind is not None and gate in special:
            results[gate] = special[gate]
        elif kind == REVIEW_CARD_PREFIX:
            results[gate] = latest(reviews(card=gate[len(REVIEW_CARD_PREFIX):]),
                                   lambda e: e["review"]["disposition"] == "pass")
        elif kind == VERIFY_CARD_PREFIX:
            results[gate] = latest(verifications(card=gate[len(VERIFY_CARD_PREFIX):]), _verification_passes)
        elif kind == REVIEW_GATES_PREFIX:
            specialty = None if gate == "review_r1" else gate[len(REVIEW_GATES_PREFIX):]
            results[gate] = latest(reviews(specialty=specialty), lambda e: e["review"]["disposition"] == "pass")
        elif kind in VERIFICATION_GATES:
            claim_type = "goal_backwards" if gate == "verification_goal_backwards" else "contract"

            def passing(e: dict[str, Any], claim_type: str = claim_type) -> bool:
                claims = [c for c in e["verification"]["claims"] if c["type"] == claim_type]
                return e["result"] == "pass" and bool(claims) and all(c["result"] == "pass" for c in claims)

            results[gate] = latest(verifications(), passing)
        else:
            results[gate] = _no_evaluator(gate, utype)
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
