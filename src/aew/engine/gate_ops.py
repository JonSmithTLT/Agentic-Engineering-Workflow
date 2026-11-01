"""A parent's mandatory gate that can never be satisfied: found at dispatch, in doctor, resume and status, and replaced
on the record (ITEMS 55: a parent's gate with no evaluator blocks every descendant).

* **The predicate** is ``gates.unsatisfiable`` over the catalogue as it is now (``Roles.gate_catalogue``): read again
  at each use, because cards and checks change after a gate is written (designer, addendum 1).
* **The backstop** (designer, decision 1): dispatch refuses a unit whose inherited gates include one that can never be
  satisfied on its unit type (``gates.satisfiable``), so state written before ``work create`` refused such a name is
  caught before it costs a run.
* **The open item** (designer, addendum 4): each such gate is an item ``<parent>#gate:<gate>`` that the backstop's
  refusal, ``aew doctor``, ``resume`` and status name, with what a replacement would make stale. It is ``resolve``'s
  subject.
* **The replacement** (operator, option (b), 2026-11-01; designer, addenda 2 to 4): ``resolve`` with the choice
  ``replace_gate`` (the primitive ``work.gate_replace``) replaces a parent's mandatory gate that can never be satisfied
  with one that can, under the record's five conditions:

  1. replace, never drop: the new gate passes the predicate;
  2. only a gate that can never be satisfied: changing any other gate, or dropping one, stays the operator's decision;
  3. recorded: an immutable correction record beside the unit (``work/<S>/gate-corrections/<GC>.yaml``) names the
     unit, both gates, the reason, the actor and the revision the write expected; control state's ``policy`` points to
     it. The unit's record and its ``record_sha256`` never change (addendum 2, ruling 2);
  4. children re-evaluate only that gate: evidence is matched to each child's own snapshot and plan revision
     (``gates._matches``), never to the parent's policy. A child invocation in flight renders the inherited gates in
     its pack, so its next launch is refused: the open item (before), the result and the record name each one with the
     commands that re-dispatch it (addendum 3, option (c));
  5. found and named: the backstop's refusal and doctor's listing name the item and this route.

  The actor is whoever holds the Lead seat through the typed surface: the Lead, or the operator (addendum 4; the
  operator's terminal proof without the Lead's credential is ITEMS 54's).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.engine.dispatch import Blocker, GuardRegistration, checked
from aew.engine.guards import require
from aew.errors import IllegalTransition, NotFound, OperatorAuthorizationRequired, UsageError, ValidationFailed
from aew.knowledge.records import format_id
from aew.schemas import validate
from aew.util import safe_dump_yaml, sha256_bytes, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel, TxnContext
    from aew.engine.ports import RolesPort, WorkUnitsPort

SCHEMA = "aew/gate-correction/v1"
CORRECTIONS = "corrections"  # in a parent's control-state ``policy``: the pointers to its correction records
OP = "work.gate_replace"
CHOICE = "replace_gate"  # ``resolve``'s choice (aew.surface.contract)
REASON = "GATE_UNSATISFIABLE"  # the backstop's dispatch reason code (``reasons.REASONS``)
ITEM = "#gate:"  # an open item's id: ``<parent>#gate:<gate>``
MAX_TEXT = 2000
HOW_TO_STATE = ("state the standard as a gate AEW can satisfy: a configured check (`check:<check id>`, defined and "
                "configured in policy/checks.yaml), or a goal or contract claim (`--goal`, `--contract`) that the "
                "verifier checks under `verification_goal_backwards` or `verification_contract`")


def cold_rel(correction: str, work_id: str) -> str:
    return f"work/{work_id}/gate-corrections/{correction}.yaml"


def item_id(owner: str, gate: str) -> str:
    return f"{owner}{ITEM}{gate}"


def parse_item(subject: str) -> tuple[str, str] | None:
    owner, sep, gate = subject.partition(ITEM)
    return (owner, gate) if sep and owner and gate else None


def remedy(owner: str, gate: str) -> str:
    """How the item is settled: the typed call, and its form from a shell (no shell sees the arguments)."""
    return (f"settle `{item_id(owner, gate)}` with the typed `resolve` tool: choice `{CHOICE}`, the gate that carries "
            "its standard as `replacement`, a `rationale` and `expect_rev` (from `aew status`); from a shell, "
            "`aew lead tool resolve --arguments -` with those arguments as JSON on standard input. `aew status` lists "
            "the live invocations it would make stale")


def owners(state: dict[str, Any], work_id: str, gate: str) -> list[str]:
    """The ancestors of ``work_id`` that set ``gate`` as a mandatory gate, nearest first."""
    return [a for a in H.ancestors(state, work_id)
            if gate in ((state["work"][a].get("policy") or {}).get("mandatory_gates") or [])]


def stuck(state: dict[str, Any], work_id: str, catalogue: G.Catalogue) -> list[dict[str, Any]]:
    """The gates ``work_id`` inherits that can never be satisfied on its unit type, each with its owners. Only an
    inherited gate can be one: a class path's gates are the policy's, which ``policy.consistency`` judges."""
    obligations = G.effective_obligations(state, work_id, {"risk_paths": defaultdict(list)})
    utype = G.unit_type(state["work"][work_id])
    out = []
    for gate in obligations["gates"]:
        found = G.unsatisfiable(gate, utype, catalogue)
        if found is not None:
            out.append({"gate": gate, "owners": owners(state, work_id, gate), "why": found.why,
                        "candidates": list(found.candidates), "unit_type": utype})
    return out


def stale_invocations(state: dict[str, Any], work_id: str, gate: str) -> list[dict[str, Any]]:
    """Every active invocation under ``work_id``, whose pack renders the inherited gates, with the commands that
    re-dispatch it, complete and parser-valid: a non-mutating executor's attempt is superseded; any other invocation is
    cancelled and dispatched again with its card (addendum 3)."""
    under = set(H.descendants(state, work_id))
    why = f"{work_id}'s mandatory gate `{gate}` was replaced on the record, so this invocation's context pack changed"
    rev = "--expect-rev <revision from aew status>"
    out = []
    for inv_id, inv in sorted(state["invocations"].items()):
        if inv.get("status") != "active" or inv.get("work_unit") not in under:
            continue
        wid = inv["work_unit"]
        unit = state["work"][wid]
        if unit["kind"] == "ticket" and not unit.get("mutating") and inv.get("scope") == "observation":
            commands = [f"aew work redispatch {wid} --launch {rev} --fields -"]
        else:
            card = (inv.get("card") or {}).get("id")
            pick = f"--card {card}" if card else f"--role {inv['role']}"
            scope = " --scope integration" if inv.get("scope") == "integration" else ""
            commands = [f"aew invoke cancel {inv_id} {rev} --fields -",
                        f"aew invoke create {wid} {pick}{scope} --launch {rev}"]
        out.append({"invocation": inv_id, "work_id": wid, "role": inv.get("role"), "commands": commands,
                    "fields": {"reason": why}})
    return out


def open_items(state: dict[str, Any], catalogue: G.Catalogue) -> list[dict[str, Any]]:
    """Every live parent's mandatory gate that no descendant can satisfy, and every gate a live unit inherits that its
    own type can never satisfy: one item per (parent, gate), with the units stuck on it, whether this route can
    replace it (condition 2), and the invocations a replacement would make stale (its preview)."""
    items: dict[tuple[str, str], dict[str, Any]] = {}

    def item(owner: str, gate: str, why: str, candidates: list[str]) -> dict[str, Any]:
        found = items.get((owner, gate))
        if found is None:
            found = items[(owner, gate)] = {
                "id": item_id(owner, gate), "work_id": owner, "gate": gate, "why": why, "candidates": candidates,
                "replaceable": G.unsatisfiable_inherited(gate, catalogue) is not None, "stuck_units": [],
                "stale_invocations": stale_invocations(state, owner, gate)}
        return found

    for wid, unit in sorted(state["work"].items()):
        if unit.get("state") in H.TERMINAL:
            continue
        for gate in (unit.get("policy") or {}).get("mandatory_gates") or []:
            found = G.unsatisfiable_inherited(gate, catalogue)
            if found is not None:
                item(wid, gate, found.why, list(found.candidates))
        for s in stuck(state, wid, catalogue):
            for owner in s["owners"]:
                item(owner, s["gate"], s["why"], s["candidates"])["stuck_units"].append(wid)
    return [items[k] for k in sorted(items)]


def doctor(state: dict[str, Any], catalogue: G.Catalogue) -> tuple[str, str]:
    """``aew doctor``'s listing (decision 1; condition 5): each open item, the parent that set it, the units stuck on
    it, and this route as the remedy (or, for a gate that can be satisfied, the operator's decision)."""
    lines = []
    for i in open_items(state, catalogue):
        units = f" (stuck: {', '.join(i['stuck_units'])})" if i["stuck_units"] else ""
        how = (remedy(i["work_id"], i["gate"]) if i["replaceable"] else
               "it can be satisfied on another unit type, so changing it is the operator's decision, not this route")
        lines.append(f"{i['work_id']} sets mandatory gate `{i['gate']}`{units}, which can never be satisfied: "
                     f"{i['why']}; {how}.")
    if not lines:
        return "PASS", "every live unit's inherited gates can be satisfied"
    return "FAIL", " ".join(lines)


class GateRepair:
    """The dispatch backstop, the open items, and the recorded replacement (ITEMS 55)."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, roles: RolesPort) -> None:
        self.k = k
        self.units = units
        self.roles = roles

    # ---- the backstop and the open items

    def dispatch_guards(self) -> list[GuardRegistration]:
        return [GuardRegistration("gates.satisfiable", self.guard_satisfiable)]

    def guard_satisfiable(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> list[Blocker] | None:
        """A unit whose inherited gate can never be satisfied on its type is not dispatched: nothing it produces could
        complete it (decision 1's backstop, for state written before the refusal at the write)."""
        found = stuck(state, work_id, self.roles.gate_catalogue())
        return [Blocker(REASON, f"{work_id} inherits gate `{s['gate']}` from {', '.join(s['owners'])}, which can never "
                                f"be satisfied on a {s['unit_type']}: {s['why']}. Nothing this dispatch produces could "
                                "complete it; " + "; ".join(remedy(o, s["gate"]) for o in s["owners"]),
                        {"gate": s["gate"], "owners": s["owners"], "candidates": s["candidates"],
                         "items": [item_id(o, s["gate"]) for o in s["owners"]]})
                for s in found] or None

    def gate_items(self, state: dict[str, Any], subject: str | None = None) -> list[dict[str, Any]]:
        """The open items (all of them, or those whose parent or a stuck unit is ``subject``); none when the catalogue
        cannot be read now (doctor reports that on its own)."""
        try:
            catalogue = self.roles.gate_catalogue()
        except NotFound:
            return []
        return [i for i in open_items(state, catalogue)
                if subject in (None, "project", i["work_id"]) or subject in i["stuck_units"]]

    # ---- the replacement

    def replace_query(self, state: dict[str, Any], work_id: str | None, args: dict[str, Any]) -> Blocker | None:
        """``work.gate_replace`` with ``args`` (``subject``, ``replacement``, ``rationale``), under the five
        conditions. It records the parent, the new gate list and the invocations it makes stale in ``args["found"]``;
        ``work_id`` is unused (the subject names it)."""
        def check() -> None:
            subject, replacement = str(args.get("subject") or ""), args.get("replacement")
            parsed = parse_item(subject)
            if parsed is None:
                raise UsageError(f"`{subject}` is not a stuck gate: its item is `<parent>{ITEM}<gate>`, as `aew "
                                 "status` and `aew doctor` name it", subject=subject)
            owner, gate = parsed
            if not (args.get("rationale") or "").strip():
                raise UsageError("a gate replacement needs the reason the new gate carries the same standard")
            if not replacement:
                raise UsageError("a gate is replaced, never dropped (ITEMS 55, option (b), condition 1): name the gate "
                                 "that carries its standard as `replacement`; dropping a gate is the operator's "
                                 "decision")
            unit = self.units.unit(state, owner)
            if unit["state"] in H.TERMINAL:
                raise IllegalTransition(f"{owner} is {unit['state']}; a finished unit keeps its gates")
            gates = list((unit.get("policy") or {}).get("mandatory_gates") or [])
            if gate not in gates:
                set_by = owners(state, owner, gate)
                raise NotFound(f"`{gate}` is not a mandatory gate of {owner}"
                               + (f"; {', '.join(set_by)} sets it, so its item is `{item_id(set_by[0], gate)}`"
                                  if set_by else "")
                               + f". {owner}'s mandatory gates: " + (", ".join(f"`{g}`" for g in gates) or "none"),
                               work_id=owner, gate=gate, mandatory_gates=gates, set_by=set_by)
            catalogue = self.roles.gate_catalogue()
            if G.unsatisfiable_inherited(gate, catalogue) is None:
                raise OperatorAuthorizationRequired(
                    f"`{gate}` can be satisfied, so this route does not apply: it replaces only a gate that can never "
                    "be satisfied (ITEMS 55, option (b), condition 2). Changing or dropping any other gate stays the "
                    "operator's decision", work_id=owner, gate=gate)
            found = G.unsatisfiable_inherited(replacement, catalogue)
            if found is not None:
                raise ValidationFailed(f"the replacement {found.message}; {HOW_TO_STATE}", work_id=owner,
                                       gate=replacement, candidates=list(found.candidates))
            if replacement in gates:
                raise OperatorAuthorizationRequired(
                    f"`{replacement}` is already a mandatory gate of {owner}, so this would drop `{gate}` without a "
                    "replacement: that is the operator's decision (condition 2)", work_id=owner, gate=gate)
            args.setdefault("found", {}).update(work_id=owner, gate=gate,
                                                gates=[replacement if g == gate else g for g in gates],
                                                stale_invocations=stale_invocations(state, owner, gate))

        return checked(check)

    def gate_replace(self, *, token: str, expect_rev: int, subject: str, replacement: str | None,
                     rationale: str) -> dict[str, Any]:
        args: dict[str, Any] = {"subject": subject, "replacement": replacement, "rationale": rationale}
        with self.k.lead_txn(token, expect_rev, OP, reason=rationale) as ctx:
            require(self.replace_query(ctx.state, None, args))  # the guard (predicate and conditions), then the write
            found = args["found"]
            owner = found["work_id"]
            unit = ctx.state["work"][owner]
            ctx.state["counters"]["gate_correction"] = ctx.state["counters"].get("gate_correction", 0) + 1
            gc = format_id("GC", ctx.state["counters"]["gate_correction"])
            rev = ctx.session.revision + 1
            record = {"schema": SCHEMA, "id": gc, "work_unit": owner, "replaced": found["gate"], "with": replacement,
                      "reason": rationale.strip()[:MAX_TEXT], "by": dict(ctx.actor),
                      "generation": ctx.state["lead"]["generation"], "expected_revision": expect_rev, "rev": rev,
                      "at": utc_now(), "stale_invocations": found["stale_invocations"]}
            validate("gate-correction", record, source=f"gate correction {gc}")
            self._write(ctx, unit, record, found["gates"])
            ctx.summary = f"{owner} mandatory gate `{found['gate']}` replaced by `{replacement}` ({gc})"
            self.units.before_commit(ctx)
        return {"ok": True, "subject": subject, "work_id": owner, "correction": gc, "replaced": found["gate"],
                "with": replacement, "mandatory_gates": found["gates"],
                "stale_invocations": found["stale_invocations"], "revision": ctx.session.committed_revision}

    @staticmethod
    def _write(ctx: TxnContext, unit: dict[str, Any], record: dict[str, Any], gates: list[str]) -> None:
        """The record, immutable, beside the unit; control state's policy takes the new gates and a pointer to it."""
        rel = cold_rel(record["id"], record["work_unit"])
        text = safe_dump_yaml(record, source=f"gate correction record {record['id']}")
        ctx.session.write(rel, text, immutable=True)
        policy = unit["policy"]
        policy["mandatory_gates"] = gates
        policy.setdefault(CORRECTIONS, []).append(
            {"id": record["id"], "replaced": record["replaced"], "with": record["with"], "path": rel,
             "sha256": sha256_bytes(text.encode("utf-8")), "rev": record["rev"]})
        ctx.refs.append(rel)
