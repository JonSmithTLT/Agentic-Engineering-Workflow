"""Role catalog queries, Ticket role plans ("staffing"), and dispatch-time card resolution (ADR-0006).

Selection precedence for the *effective* plan:

    non-waivable policy / guardrail requirements        (computed; cannot be removed)
      -> operator constraints (pins, forbids)            (Lead may replace only with a reason + decision)
      -> Lead selection                                  (Ticket needs + card metadata, incl. advisory use_when)
      -> workflow defaults                               (archetype default_card for a required, empty slot)

``use_when`` is advisory metadata for Lead reasoning; nothing here dispatches on it.
Operator attribution recorded through the Lead is attribution, not proof (ADR-0005).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew import roles
from aew.engine import gates as G
from aew.engine import transitions
from aew.engine.base import TxnContext
from aew.policy import consistency
from aew.errors import AEWError, IllegalTransition, NotFound, PermissionDenied, UsageError, ValidationFailed
from aew.util import load_yaml, sha256_bytes

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.work_ops import WorkUnits

SLOTS = ("execute", "review", "verify")


class Roles:
    """The role catalog, role plans (staffing), plan assurance and dispatch-time card resolution (ADR-0006)."""

    def __init__(self, k: Kernel, *, units: WorkUnits) -> None:
        self.k = k
        self.units = units

    def _catalog_rel(self) -> str:
        return (self.k.manifest.get("roles") or {}).get("catalog", "roles/")

    def role_catalog(self) -> roles.Catalog:
        rel = self._catalog_rel()
        return roles.load_catalog(self.k.aew_root / rel, rel_prefix=rel.rstrip("/"))

    def role_list(self) -> dict[str, Any]:
        catalog = self.role_catalog()
        items = [{"id": c.id, "display_name": c.meta["display_name"], "extends": c.archetype, "source": c.source,
                  "version": c.meta.get("version"), "specialty": c.meta.get("specialty"),
                  "use_when": c.meta.get("use_when", []), "skills": c.meta.get("skills", []),
                  "purpose": c.meta["purpose"]}
                 for c in sorted(catalog.cards.values(), key=lambda c: (c.archetype, c.id))]
        return {"cards": items, "archetypes": list(roles.ARCHETYPES), "problems": catalog.problems}

    def role_show(self, card_id: str) -> dict[str, Any]:
        card = self.role_catalog().get(card_id)
        base = roles.archetype(card.archetype)
        return {**card.pin(), "archetype": {"role": base["role"], "authority": base["authority"],
                                            "engine_operations": base["engine_operations"],
                                            "authority_capabilities": base["authority_capabilities"]}}

    def role_validate(self, path: str | None = None) -> dict[str, Any]:
        catalog = self.role_catalog()
        if path is None:
            return {"ok": not catalog.problems, "cards": sorted(catalog.cards), "problems": catalog.problems}
        raw = Path(path).read_bytes()
        meta = load_yaml(raw.decode("utf-8"), source=path)
        try:
            roles.validate_card(meta, source=path)
        except (ValidationFailed, PermissionDenied, NotFound) as exc:
            return {"ok": False, "problems": [exc.message], "details": exc.details}
        existing = catalog.cards.get(meta["role"])
        if existing and existing.sha256 != sha256_bytes(raw):
            return {"ok": False, "problems": [f"card id {meta['role']!r} already exists in the {existing.source} "
                                               f"catalog ({existing.path})"]}
        return {"ok": True, "card": meta["role"], "extends": meta["extends"]}

    @staticmethod
    def _plan(unit: dict[str, Any]) -> dict[str, Any]:
        return unit.setdefault("role_plan", {"execute": [], "review": [], "verify": [], "forbidden": []})

    @staticmethod
    def plan_gates(unit: dict[str, Any]) -> dict[str, str]:
        """Each explicitly planned review/verify card is its own gate (multiple cards per gate)."""
        plan = unit.get("role_plan") or {}
        out = {}
        for slot, prefix in (("review", G.REVIEW_CARD_PREFIX), ("verify", G.VERIFY_CARD_PREFIX)):
            for entry in plan.get(slot, []):
                why = (f"accepted plan v{entry['plan_revision']}" if entry.get("plan_revision") is not None
                       else f"role plan ({entry['selected_by']})")
                out[f"{prefix}{entry['card']}"] = why
        return out

    def resolve_plan_assurance(self, unit: dict[str, Any], *, review: list[str] | None, verify: list[str] | None,
                               none: bool) -> dict[str, list[str]]:
        """The review and verification a plan revision commits to (operator decision, UAT 2026-09-30).

        Every new plan revision declares it: cards for the review and verify slots (``default`` is the
        archetype's default card), or an explicit ``none``. Accepting the plan makes the cards required gates
        (``plan_gates``); a review promised only in the plan's text binds nothing, which is why the declaration
        is required rather than optional.
        """
        review, verify = list(review or []), list(verify or [])
        if none and (review or verify):
            raise UsageError("--assurance none excludes --review and --verify")
        if not none and not (review or verify):
            raise UsageError(
                "declare the plan's assurance: --review <card|default> and/or --verify <card|default>, or "
                "--assurance none. Accepting the plan makes the declared review and verification required gates; "
                "a review or verification promised only in the plan's text binds nothing")
        catalog = self.role_catalog()
        forbidden = {f["card"] for f in (unit.get("role_plan") or {}).get("forbidden", [])}
        out: dict[str, list[str]] = {"review": [], "verify": []}
        for slot, wanted in (("review", review), ("verify", verify)):
            for card_id in wanted:
                if card_id == "default":
                    card_id = roles.default_card("reviewer" if slot == "review" else "verifier") or card_id
                card = catalog.get(card_id)
                self._slot_ok(unit, slot, card)
                if card.id in forbidden:
                    raise PermissionDenied(f"{card.id} is forbidden for this unit; a plan cannot require it")
                if card.id not in out[slot]:
                    out[slot].append(card.id)
        return out

    def bind_plan_assurance(self, unit: dict[str, Any], revision: int,
                            assurance: dict[str, list[str]] | None) -> None:
        """On plan acceptance the accepted revision's declared cards become role-plan entries, so they are
        required gates; entries bound by an earlier revision are released. Plans from before the declaration
        existed have none and bind nothing."""
        plan = self._plan(unit)
        catalog = self.role_catalog()
        forbidden = {f["card"] for f in plan["forbidden"]}
        for slot in ("review", "verify"):
            for entry in list(plan[slot]):
                if entry.get("plan_revision") is None:
                    continue
                if entry["selected_by"] == "plan":
                    plan[slot].remove(entry)
                else:
                    entry.pop("plan_revision")
            for card_id in (assurance or {}).get(slot, []):
                if card_id in forbidden:
                    raise PermissionDenied(f"plan v{revision} requires {card_id} in the {slot} slot, but it is "
                                           "forbidden for this unit; propose a revision without it")
                existing = next((e for e in plan[slot] if e["card"] == card_id), None)
                if existing:
                    existing["plan_revision"] = revision
                else:
                    plan[slot].append({"card": card_id, "version": catalog.get(card_id).meta.get("version"),
                                       "selected_by": "plan", "pinned": True, "plan_revision": revision})

    def _slot_ok(self, unit: dict[str, Any], slot: str, card: roles.Card) -> None:
        allowed = roles.SLOT_ARCHETYPES[slot]
        if slot == "execute":
            if unit["kind"] != "ticket":
                raise UsageError("Stories and Epics are not executed; their Tickets are (WC §7.1)")
            # Authority comes from the executing archetype, never from the Ticket's label (ADR-0008).
            allowed = {"implementer"} if unit.get("mutating") else roles.NON_MUTATING_EXECUTORS
        if card.archetype not in allowed:
            raise UsageError(f"card {card.id} ({card.archetype}) cannot fill the {slot} slot of {unit['title']!r}",
                             allowed_archetypes=sorted(allowed))

    def work_staff(
        self, *, token: str, expect_rev: int, work_id: str,
        execute: list[str] | None = None, review: list[str] | None = None, verify: list[str] | None = None,
        forbid: list[str] | None = None, remove: list[str] | None = None,
        selected_by: str = "lead", pin: bool = False, reason: str | None = None,
    ) -> dict[str, Any]:
        if selected_by not in {"lead", "operator"}:
            raise UsageError("selected_by is lead or operator (policy/workflow entries are computed)")
        with self.k.lead_txn(token, expect_rev, "work.staff", reason=reason) as ctx:
            unit = self.units.unit(ctx.state, work_id)
            if unit["state"] in transitions.TERMINAL:
                raise IllegalTransition(f"{work_id} cannot be staffed in state {unit['state']}")
            if unit["kind"] != "ticket" and execute:
                raise IllegalTransition("Stories and Epics have no execute slot; staff their review/verify gates")
            catalog = self.role_catalog()
            plan = self._plan(unit)
            overrides: list[str] = []

            def overriding(entry: dict[str, Any], what: str) -> None:
                if entry.get("plan_revision") is not None:
                    raise PermissionDenied(f"{what} is required by the accepted plan v{entry['plan_revision']}; "
                                           "only a new plan revision changes the plan's review and verification")
                if entry.get("pinned") and entry["selected_by"] == "operator" and selected_by != "operator":
                    if not (reason and reason.strip()):
                        raise PermissionDenied(f"{what} is an operator pin; the Lead may replace it only with --reason")
                    overrides.append(what)

            for spec in remove or []:
                slot, _, card_id = spec.partition("=")
                if slot not in SLOTS + ("forbidden",):
                    raise UsageError("remove takes slot=card with slot execute|review|verify|forbidden")
                entry = next((e for e in plan[slot] if e["card"] == card_id), None)
                if entry is None:
                    raise NotFound(f"{card_id} is not in the {slot} slot")
                overriding(entry, f"{slot}={card_id}")
                plan[slot].remove(entry)
            for card_id in forbid or []:
                catalog.get(card_id)
                for slot in SLOTS:
                    for entry in [e for e in plan[slot] if e["card"] == card_id]:
                        overriding(entry, f"{slot}={card_id}")
                        plan[slot].remove(entry)
                if not any(f["card"] == card_id for f in plan["forbidden"]):
                    plan["forbidden"].append({"card": card_id, "selected_by": selected_by, "pinned": True,
                                              "reason": reason})
            forbidden = {f["card"] for f in plan["forbidden"]}
            for slot, wanted in (("execute", execute), ("review", review), ("verify", verify)):
                for card_id in wanted or []:
                    card = catalog.get(card_id)
                    self._slot_ok(unit, slot, card)
                    if card_id in forbidden:
                        raise PermissionDenied(f"{card_id} is forbidden for {work_id}",
                                               by=[f for f in plan["forbidden"] if f["card"] == card_id])
                    if slot == "execute":  # serial M1: one executing card per Ticket
                        for entry in list(plan["execute"]):
                            if entry["card"] != card_id:
                                overriding(entry, f"execute={entry['card']}")
                                plan["execute"].remove(entry)
                    existing = next((e for e in plan[slot] if e["card"] == card_id), None)
                    if existing is None:
                        plan[slot].append({"card": card_id, "version": card.meta.get("version"),
                                           "selected_by": selected_by, "pinned": pin})
                    elif selected_by == "operator":
                        # An operator constraint on an already-selected card takes effect (review M7).
                        existing.update(selected_by="operator", pinned=pin, version=card.meta.get("version"))
                    elif pin and not (existing.get("pinned") and existing["selected_by"] == "operator"):
                        existing["pinned"] = True
                    # A Lead re-selecting an operator-pinned card leaves the operator's constraint intact.
            decision = None
            if overrides or selected_by == "operator":
                decision = self.k.new_decision(
                    ctx, "role_plan_change",
                    f"{work_id} role plan changed" + (f"; overrode operator pins {overrides}" if overrides else ""),
                    work_unit=work_id, reason=reason,
                    decided_by=dict(ctx.actor, kind="operator" if selected_by == "operator" else "lead",
                                    recorded_by_lead=True))
            ctx.summary = f"{work_id} staffed"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "role_plan": unit["role_plan"], "decision": decision,
                "revision": ctx.session.committed_revision}

    def effective_role_plan(self, state: dict[str, Any], work_id: str,
                            gc: dict[str, Any] | None = None) -> dict[str, Any]:
        unit = self.units.unit(state, work_id)
        stored = unit.get("role_plan") or {"execute": [], "review": [], "verify": [], "forbidden": []}
        eff = {slot: [dict(e) for e in stored.get(slot, [])] for slot in SLOTS}
        requirements: list[dict[str, Any]] = []
        catalog = self.role_catalog()
        if gc is not None:
            for trig in gc["guardrails"].get("triggered", []):
                if trig.get("card"):
                    if not any(e["card"] == trig["card"] for e in eff["review"]):
                        eff["review"].append({"card": trig["card"], "selected_by": "policy",
                                              "reason": f"guardrail trigger {trig['name']}"})
                else:
                    requirements.append(self._specialty_requirement(catalog, trig["name"], "guardrail trigger"))
            for gate, sources in gc["obligations"]["sources"].items():
                if gate.startswith(G.REVIEW_GATES_PREFIX) and gate not in {"review_r1"} \
                        and not gate.startswith(G.REVIEW_CARD_PREFIX) and any("inherited" in s for s in sources):
                    requirements.append(self._specialty_requirement(catalog, gate[len("review_"):], "ancestor policy"))
        required_gates = set(gc["obligations"]["gates"]) if gc else set()
        # An unstaffed non-mutating Ticket defaults to the investigator: recorded as a workflow default and
        # pinned with its output kind at dispatch (operator review 2026-09-27).
        if unit["kind"] != "ticket":
            execute_default = None
        else:
            execute_default = "implementer" if unit.get("mutating") else "investigator"
        defaults = {"execute": execute_default,
                    "review": "reviewer" if "review_r1" in required_gates else None,
                    "verify": "verifier" if required_gates & set(G.VERIFICATION_GATES) else None}
        for slot, arch in defaults.items():
            if arch and not eff[slot] and roles.default_card(arch):
                eff[slot].append({"card": roles.default_card(arch), "selected_by": "workflow",
                                  "reason": f"default {arch} card for a required gate"})
        return {"stored": stored, "effective": eff, "forbidden": stored.get("forbidden", []),
                "specialty_requirements": requirements,
                "note": "use_when is advisory; policy requirements cannot be removed"}

    @staticmethod
    def _specialty_requirement(catalog: roles.Catalog, specialty: str, why: str) -> dict[str, Any]:
        cards = sorted(c.id for c in catalog.cards.values() if c.meta.get("specialty") == specialty)
        return {"gate": f"review_{specialty}", "selected_by": "policy", "reason": why,
                "satisfied_by": f"any reviewer card with specialty {specialty}", "candidates": cards}

    def resolve_card(self, state: dict[str, Any], work_id: str, slot: str, *, card_id: str | None,
                     role: str | None, gc: dict[str, Any] | None = None) -> roles.Card:
        unit = self.units.unit(state, work_id)
        catalog = self.role_catalog()
        if card_id is None:
            eff = self.effective_role_plan(state, work_id, gc)["effective"][slot]
            pending = [e["card"] for e in eff if not self._card_gate_current(gc, slot, e["card"])]
            if pending:
                card_id = pending[0]
            elif role or eff:
                card_id = roles.default_card(role or catalog.get(eff[0]["card"]).archetype)
            else:
                card_id = roles.default_card({"execute": "implementer", "review": "reviewer",
                                              "verify": "verifier"}[slot])
        card = catalog.get(card_id)
        if role and card.archetype != role:
            raise UsageError(f"card {card.id} extends {card.archetype}, not {role}")
        self._slot_ok(unit, slot, card)
        forbidden = {f["card"] for f in (unit.get("role_plan") or {}).get("forbidden", [])}
        if card.id in forbidden:
            raise PermissionDenied(f"{card.id} is forbidden for {work_id}")
        self._require_operator_pin(unit, work_id, slot, card)
        roles.validate_card(card.meta, source=card.path)  # re-checked at dispatch
        return card

    @staticmethod
    def _require_operator_pin(unit: dict[str, Any], work_id: str, slot: str, card: roles.Card) -> None:
        """Dispatch honours operator pins (review M7).

        The execute slot has one card, so dispatching any other card would silently bypass an operator
        pin: it is refused, and an override goes through ``aew work staff --reason`` (a recorded
        decision). Pinned review/verify cards are enforced as required gates (``plan_gates``), so an
        additional card in those slots does not bypass them.
        """
        if slot != "execute":
            return
        pinned = sorted(e["card"] for e in (unit.get("role_plan") or {}).get("execute", [])
                        if e.get("pinned") and e.get("selected_by") == "operator")
        if pinned and card.id not in pinned:
            raise PermissionDenied(
                f"the operator pinned {pinned} for {work_id}'s execute slot; to dispatch {card.id}, change the role "
                f"plan first with `aew work staff {work_id} --execute {card.id} --reason ...` (a recorded decision)",
                pinned=pinned, requested=card.id)

    @staticmethod
    def _card_gate_current(gc: dict[str, Any] | None, slot: str, card_id: str) -> bool:
        if gc is None or slot == "execute":
            return False
        prefix = G.REVIEW_CARD_PREFIX if slot == "review" else G.VERIFY_CARD_PREFIX
        info = gc["gates"].get(f"{prefix}{card_id}")
        return bool(info) and info["status"] in {G.CURRENT, G.WAIVED}

    @staticmethod
    def _pin_on(ctx: TxnContext, inv_id: str, card: roles.Card) -> None:
        inv = ctx.state["invocations"][inv_id]
        inv["card"] = card.pin()
        inv["specialty"] = card.meta.get("specialty")
        restrict = card.meta.get("restrict") or {}
        inv["allowed_operations"] = restrict.get("operations")
        inv["allowed_checks"] = restrict.get("checks")

    def policy_problems(self) -> list[str]:
        """Contradictions between the policy files and what the engine can evaluate (``policy.consistency``).

        Empty when a policy file is itself invalid: that is reported on its own, and nothing can be compared."""
        try:
            gates, checks = self.k.policy("gates"), self.k.policy("checks")
            specialties = {c.meta["specialty"] for c in self.role_catalog().cards.values() if c.meta.get("specialty")}
        except AEWError:
            return []
        return consistency.problems(gates, checks, specialties)
