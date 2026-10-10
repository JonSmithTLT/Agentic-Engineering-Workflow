"""Work graph operations: Epic/Story/Ticket records, plan revisions, Lead transitions (WC §7-§9; KC §9, §12)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aew import profile
from aew.engine import dependencies as deps
from aew.engine import hierarchy as H
from aew.engine import transitions
from aew.engine.base import TxnContext
from aew.engine.dependencies import readiness_blockers, recompute_readiness
from aew.engine.guards import NotQueryable, checked, refusal, require
from aew.engine.seams import GuardRegistration
from aew.errors import DependencyUnsatisfied, GateUnsatisfied, GitError, IllegalTransition, NotFound, UsageError
from aew.knowledge.records import KIND_PREFIX, format_id, plan_record, work_unit_record
from aew.util import glob_any, sha256_file, sha256_text, utc_now
from aew.workspace import git

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import ArchivePort, CoordinationPort, InvocationsPort, RolesPort, WorkUnitsPort
    from aew.engine.seams import GuardTable, StateHooks

RECORD_NAME = {"ticket": "ticket.md", "story": "story.md", "epic": "epic.md"}
PARENT_KINDS = H.PARENT_KINDS
# Ticket states in which a new accepted plan may be adopted (M1); parents accept plans in any non-terminal state.
PLAN_ACCEPT_TICKET_STATES = {"BLOCKED", "READY", "REPLAN_REQUIRED"}


class WorkUnits:
    """The work graph's core: unit lookup, the single state-change point (its hooks are explicit), guard resolution by
    unit kind, plan and dispatch bindings, and the readiness/derivation pass every Lead commit runs."""

    def __init__(self, k: Kernel, *, hooks: StateHooks, guards: GuardTable, archive: ArchivePort) -> None:
        self.k = k
        self.hooks = hooks
        self.guards = guards
        self.archive = archive

    def before_commit(self, ctx: TxnContext) -> None:
        """Keep BLOCKED/READY and the derived Story/Epic state consistent with the durable graph inside every
        Lead commit (WC §8: parent state is derived, never hand-maintained)."""
        at = utc_now()
        with profile.phase("derive"):
            derived = H.recompute_parents(ctx.state, at=at)
        changed = recompute_readiness(ctx.state, repo_root=self.k.repo_root, base_commit=self.k.authoritative_commit(),
                                      plan_problem=self.plan_binding_problem)
        with profile.phase("derive"):
            derived += [w for w in H.recompute_parents(ctx.state, at=at) if w not in derived]
        if changed:
            ctx.refs.extend(f"readiness:{wid}" for wid in changed)
        if derived:
            ctx.refs.extend(f"derived:{wid}" for wid in derived)

    @staticmethod
    def accepted_plan_ref(unit: dict[str, Any]) -> dict[str, Any] | None:
        plan = unit.get("plan") or {}
        return {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan.get("accepted") else None

    def ancestor_plan_snapshot(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """Every ancestor's accepted plan (or None): what a newly accepted plan is bound to."""
        return {anc: self.accepted_plan_ref(state["work"][anc]) for anc in H.ancestors(state, work_id)}

    def plan_binding_problem(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        """Why a unit's accepted plan no longer holds under its ancestors' plans (fail closed), or None.

        A plan is bound to every ancestor's accepted plan *as it was* at acceptance, including "none".
        Any later change (superseding, or an ancestor's first acceptance) makes it stale until the Lead
        reconfirms or replans; a move invalidates the binding outright (operator review 2026-09-27).
        """
        unit = state["work"][work_id]
        plan = unit.get("plan") or {}
        if not plan.get("accepted"):
            return None
        if plan.get("bindings_invalidated"):
            return {"reason": plan["bindings_invalidated"]}
        recorded = plan.get("ancestor_plans") or {}
        changed = {}
        for anc, current in self.ancestor_plan_snapshot(state, work_id).items():
            if recorded.get(anc) != current:
                changed[anc] = {"bound": recorded.get(anc), "current": current}
        return {"reason": "an ancestor's accepted plan changed after this plan was accepted",
                "ancestors": changed} if changed else None

    def dispatch_binding_problem(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        """Why a started Ticket's attempt no longer matches its effective dependencies (M2 review B2), or None."""
        return deps.dispatch_binding_problem(state, work_id, repo_root=self.k.repo_root)

    def unit(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """A hot unit, to act on. Finished work is archived (ADR-0011) and never changes: asking to act on it is refused
        as it was before archival, as an illegal transition of a finished unit."""
        unit = state["work"].get(work_id)
        if unit is None:
            archived = self.archive.archived_unit(state, work_id)
            if archived is None:
                raise NotFound(f"no work unit {work_id}")
            raise IllegalTransition(f"{work_id} is {archived['state']}; finished work is archived and does not change "
                                    f"(`aew history show {work_id}`)", work_id=work_id, state=archived["state"],
                                    archived=True)
        return unit

    def view(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """A unit to read: hot, or its archived record as it stands now (moves applied, R3)."""
        unit = state["work"].get(work_id)
        if unit is not None:
            return unit
        archived = self.archive.archived_unit(state, work_id)
        if archived is None:
            raise NotFound(f"no work unit {work_id}")
        return archived

    def set_state(self, unit: dict[str, Any], to: str, reason: str | None, *,
                  state: dict[str, Any]) -> dict[str, str]:
        """The single place a work unit's state changes (so cross-state effects cannot be skipped).

        ``state`` is the transaction's control state: cross-state effects may revoke credentials.
        """
        change = {"from": unit["state"], "to": to}
        self.hooks.run_before(unit, change)
        unit["state"] = to
        unit["state_reason"] = reason
        unit.setdefault("history", []).append({**change, "at": utc_now(), "reason": reason})
        self.hooks.run_after(state, unit, change, reason)
        return change

    def check_guard(self, name: str | None, ctx: TxnContext, work_id: str, unit: dict[str, Any], to: str) -> None:
        if not name:
            return
        self.guards.resolve(name, unit)(ctx, work_id, unit, to)

    # ---- `work.transition`'s guard as a query (M4-E E4; aew.engine.guards): the table part, then the rule's guard

    def transition_rule_query(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """The transition table's part of a Lead transition to ``args["to"]``: the unit (hot, a Ticket), the rule that
        permits the edge through ``work transition``, and its reason. It records the rule as ``found["rule"]``."""
        to, reason = args.get("to"), args.get("reason")

        def check() -> None:
            unit = self.unit(state, work_id)
            if unit["kind"] != "ticket":
                raise IllegalTransition("Story/Epic state is derived from child work (WC §8); the Lead closes one "
                                        "with `aew work close` and cancels one with `aew work cancel`")
            rule = transitions.check(unit["state"], str(to), "transition")
            if rule.reason_required and not (reason and reason.strip()):
                raise UsageError(f"{unit['state']} -> {to} requires --reason")
            require(self.state_change_query(unit, {"from": unit["state"], "to": str(to)}))  # the state hooks' refusal
            args.setdefault("found", {})["rule"] = rule

        return checked(check)

    def state_change_query(self, unit: dict[str, Any], change: dict[str, str]) -> Any:
        """Whether ``set_state`` would refuse ``change`` to ``unit`` (a ``before`` hook's blocker), or None."""
        return self.hooks.query_before(unit, change)

    def transition_query(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """``work.transition``'s whole guard: the table part, then the rule's named guard for the unit's kind, which is
        ``NotQueryable`` (UNKNOWN) where that guard has no query form."""
        found = self.transition_rule_query(state, work_id, args)
        if found is not None:
            return found
        rule = args["found"]["rule"]
        if not rule.guard:
            return None
        query = self.guards.query_for(rule.guard, state["work"][work_id])
        return NotQueryable(rule.guard) if query is None else query(state, work_id, args)

    def guard_registrations(self) -> list[GuardRegistration]:
        """The Lead-transition guards that do not depend on evidence gates, for every unit kind."""
        return [GuardRegistration("implementer_active", self._guard_implementer_active,
                                  query=self._query_implementer_active),
                GuardRegistration("findings_recorded", self._guard_findings_recorded),
                GuardRegistration("returning_from_escalation", self._guard_returning_from_escalation),
                GuardRegistration("not_beyond_interrupted_phase", self._guard_not_beyond_interrupted_phase)]

    @staticmethod
    def _query_implementer_active(state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """ASSIGNED -> RUNNING: the Ticket's implementer invocation is active (M4-E E4: its query form)."""
        unit = state["work"][work_id]
        inv = state["invocations"].get(unit.get("implementer_invocation") or "")
        if not inv or inv["status"] != "active":
            return refusal(GateUnsatisfied(f"{work_id} has no active implementer invocation"))
        return None

    def _guard_implementer_active(self, ctx, work_id, unit, to) -> None:
        require(self._query_implementer_active(ctx.state, work_id, {"to": to}))

    def _guard_findings_recorded(self, ctx, work_id, unit, to) -> None:
        # WC §8: REVIEW_FAILED -> RUNNING requires recorded findings (new ones, or earlier ones still open).
        reviews = [e for e in unit.get("evidence", []) if e["kind"] == "review"]
        still_open = [f for f in unit.get("findings", []) if f["required"] and f["status"] == "open"]
        if not still_open and not (reviews and reviews[-1].get("findings")):
            raise GateUnsatisfied(f"{work_id}: REVIEW_FAILED -> RUNNING requires recorded review findings")

    def _guard_returning_from_escalation(self, ctx, work_id, unit, to) -> None:
        origin = unit.get("escalated_from")
        if origin is None or transitions.PHASE_ORDER.get(to, 99) > transitions.PHASE_ORDER.get(origin, -1):
            raise GateUnsatisfied(f"{work_id} may return from escalation only to {origin} or an earlier phase")

    def _guard_not_beyond_interrupted_phase(self, ctx, work_id, unit, to) -> None:
        origin = unit.get("interrupted_from")
        if origin is None or transitions.PHASE_ORDER.get(to, 99) > transitions.PHASE_ORDER.get(origin, -1):
            raise GateUnsatisfied(
                f"{work_id} was interrupted in {origin}; reconciliation may not move it beyond that phase "
                "(success is never inferred from a prior invocation)"
            )

    def check_parent(self, state: dict[str, Any], kind: str, parent: str) -> None:
        parent_unit = self.view(state, parent)  # a closed parent is archived: refused below as before
        if parent_unit["kind"] not in PARENT_KINDS[kind]:
            raise UsageError(f"a {kind} cannot have a {parent_unit['kind']} parent")
        if parent_unit["state"] in H.TERMINAL:
            raise IllegalTransition(f"{parent} is {parent_unit['state']}; a closed or cancelled parent takes no new "
                                    "children (create a new unit instead)")

    def parse_edges(self, state: dict[str, Any], specs: list[str]) -> list[dict[str, str]]:
        """Edges may point at Tickets (M1 kinds) or at Stories/Epics (satisfied when the parent is DONE)."""
        edges: list[dict[str, str]] = []
        for spec in specs:
            dep_id, _, dep_kind = spec.partition(":")
            up = H.upstream(state, dep_id)
            if up is None:  # an edge to an archived unit: keep the facts it needs hot from now on (R4)
                facts = self.archive.facts_from_cold(state, dep_id)
                if facts is None:
                    raise NotFound(f"no work unit {dep_id}")
                state.setdefault("archived_refs", {})[dep_id] = {**facts, "refs": 0}
                up = H.upstream(state, dep_id)
                if up is None:
                    raise NotFound(f"no work unit {dep_id}")
            if H.is_parent(up):
                dep_kind = dep_kind or "mutating"  # conservative: descendants' integrated outputs must be in the base
            else:
                dep_kind = dep_kind or ("mutating" if up["mutating"] else "evidence")
            if dep_kind not in {"mutating", "evidence"}:
                raise UsageError(f"dependency kind must be mutating or evidence, got {dep_kind}")
            if dep_kind == "mutating" and not H.is_parent(up) and not up["mutating"]:
                raise UsageError(f"{dep_id} is not mutating; use an evidence dependency")
            if any(e["id"] == dep_id for e in edges):
                raise UsageError(f"duplicate dependency on {dep_id}")
            edges.append({"id": dep_id, "kind": dep_kind})
        return edges

    @staticmethod
    def refuse_cycles(state: dict[str, Any]) -> None:
        cycle = H.find_cycle(state)
        if cycle:
            raise UsageError("this change would create a dependency cycle (including inherited edges and parents "
                             "waiting on their children): " + " -> ".join(cycle), cycle=cycle)

    def propose(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], *, body: str, reason: str | None,
                affected_paths: list[str] | None, assurance: dict[str, list[str]],
                author: dict[str, Any] | None = None,
                source_evidence: dict[str, Any] | None = None) -> tuple[str, int]:
        """Write plan revision N+1 (proposed). Only the Lead's plan.accept moves the accepted pointer."""
        revision, supersedes, text, path = self.plan_draft(
            work_id, unit, body=body, reason=reason, affected_paths=affected_paths, assurance=assurance,
            author=author or {"role": "lead", "session_label": ctx.actor.get("session_label"),
                              "generation": ctx.actor["generation"]},
            source_evidence=source_evidence)
        ctx.session.write(path, text)
        ctx.refs.append(path)
        unit["plans"].append({"revision": revision, "path": path, "sha256": sha256_text(text),
                              "supersedes": supersedes, "status": "proposed", "assurance": assurance})
        return path, revision

    @staticmethod
    def plan_draft(work_id: str, unit: dict[str, Any], *, body: str, reason: str | None,
                   affected_paths: list[str] | None, assurance: dict[str, list[str]], author: dict[str, Any],
                   source_evidence: dict[str, Any] | None = None) -> tuple[int, int | None, str, str]:
        """Plan revision N+1 of ``unit`` as it would be written, changing nothing: (revision, the accepted revision it
        supersedes, its record text, its path). A revision that supersedes an accepted plan states its reason, and
        the record matches the plan schema."""
        revision = len(unit["plans"]) + 1
        supersedes = (unit.get("plan") or {}).get("accepted")
        if supersedes and not reason:
            raise UsageError("a plan revision that supersedes an accepted plan must state its reason")
        record = plan_record(
            work_unit=work_id, revision=revision, created_at=utc_now(), author=author,
            body=body, supersedes=supersedes, reason=reason, affected_paths=affected_paths,
            source_evidence=source_evidence, assurance=assurance,
        )
        return revision, supersedes, record.render(), f"work/{work_id}/plan-v{revision}.md"

    @staticmethod
    def rollup(state: dict[str, Any], work_id: str) -> dict[str, Any]:
        """Derived Story/Epic state from child work (WC §8: never hand-maintained)."""
        counts: dict[str, int] = {}
        stack = [work_id]
        while stack:
            current = stack.pop()
            for cid, child in state["work"].items():
                if child.get("parent") == current:
                    if child["kind"] == "ticket":
                        counts[child["state"]] = counts.get(child["state"], 0) + 1
                    else:
                        stack.append(cid)
        archived = H.archived_summary(state["work"][work_id])  # every finished Ticket archived below it (R3)
        for st, n in (("DONE", archived["done_tickets_subtree"]), ("CANCELLED", archived["cancelled_tickets_subtree"])):
            if n:
                counts[st] = counts.get(st, 0) + n
        total = sum(counts.values())
        done = counts.get("DONE", 0) + counts.get("CANCELLED", 0)
        derived = "EMPTY" if total == 0 else ("CHILDREN_COMPLETE" if done == total else "IN_PROGRESS")
        return {"derived_state": derived, "children_by_state": counts,
                "note": "children complete does not prove parent acceptance (WC §8)"}

    def completion_sha(self, state: dict[str, Any], work_id: str) -> str | None:
        unit = state["work"][work_id]
        if unit.get("completion_sha256"):
            return unit["completion_sha256"]
        rec = unit.get("completion_record")
        return sha256_file(self.k.aew_root / rec) if rec else None

    def require_plan_binding(self, state: dict[str, Any], work_id: str) -> None:
        """No executor starts under an accepted plan whose ancestor plans changed since (ADR-0007, fail closed)."""
        problem = self.plan_binding_problem(state, work_id)
        if problem:
            raise GateUnsatisfied(f"{work_id}'s accepted plan is stale under its ancestors' current plans; "
                                  f"`aew plan reconfirm {work_id} --reason ...` or a new plan revision first",
                                  binding=problem)

    def require_dispatch_binding(self, state: dict[str, Any], work_id: str) -> None:
        """No executor joins an attempt dispatched for other dependencies than the Ticket now has (M2 review B2)."""
        problem = self.dispatch_binding_problem(state, work_id)
        if problem:
            raise DependencyUnsatisfied(f"{work_id}'s attempt was dispatched with other dependencies than it now has; "
                                        "a new dispatch is required (REPLAN_REQUIRED and a plan revision, or "
                                        "`aew work redispatch` for a non-mutating Ticket)", dispatch_binding=problem)



class WorkCommands:
    """Lead commands on work units and plans: create, propose, accept, transition, reconcile, show, list."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, roles: RolesPort, invocations: InvocationsPort,
                 archive: ArchivePort, coordination: CoordinationPort) -> None:
        self.k = k
        self.units = units
        self.roles = roles
        self.invocations = invocations
        self.archive = archive
        self.coordination = coordination

    def work_create(
        self,
        *,
        token: str,
        expect_rev: int,
        kind: str,
        title: str,
        risk_class: int,
        mutating: bool | None = None,
        parent: str | None = None,
        depends_on: list[str] | None = None,
        scope_paths: list[str] | None = None,
        goal_backwards: list[str] | None = None,
        contract: list[str] | None = None,
        mandatory_gates: list[str] | None = None,
        min_descendant_class: int | None = None,
        rationale: str | None = None,
        external_refs: list[str] | None = None,
        body: str = "",
        card: str | None = None,
        promoted_from: str | None = None,
        acceptance_checks: list[str] | None = None,
        acceptance_inputs: list[str] | None = None,
        class0_assertions: list[str] | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {
            "kind": kind, "title": title, "risk_class": risk_class, "mutating": mutating, "parent": parent,
            "depends_on": depends_on, "scope_paths": scope_paths, "goal_backwards": goal_backwards,
            "contract": contract, "mandatory_gates": mandatory_gates, "min_descendant_class": min_descendant_class,
            "rationale": rationale, "external_refs": external_refs, "body": body, "card": card,
            "promoted_from": promoted_from, "acceptance_checks": acceptance_checks,
            "acceptance_inputs": acceptance_inputs, "class0_assertions": class0_assertions}
        self._check_create_arguments(args)  # before the transaction, as always: a malformed request needs no state
        with self.k.lead_txn(token, expect_rev, "work.create") as ctx:
            # The guard's query (M4-E E4), then the same draft for real: the unit, its record and its counter.
            require(self.create_query(ctx.state, None, args))
            work_id, unit, text = self._draft_unit(ctx.state, args, ctx.actor)
            path = unit["record"]
            ctx.session.write(path, text)
            ctx.refs.append(path)
            ctx.summary = f"created {kind} {work_id}: {title}"
            self.units.before_commit(ctx)
        out = {"ok": True, "id": work_id, "record": path, "revision": ctx.session.committed_revision}
        unmatched = self._unmatched_scope(scope_paths or []) if kind == "ticket" and unit["mutating"] else []
        if unmatched:
            out["warnings"] = [f"scope glob {g!r} matches no file in the project: fine if the Ticket creates it, "
                               "otherwise a change there needs a scope that names it" for g in unmatched]
        return out

    # ---- `work.create`'s guard as a query (M4-E E4; aew.engine.guards)

    def create_query(self, state: dict[str, Any], work_id: str | None, args: dict[str, Any]) -> Any:
        """``work.create`` with ``args`` (the request's fields): the request is well formed (the argument checks and
        the scope lint, M3-D9), and drafting the unit on a copy of ``state`` succeeds (its parent takes children, its
        dependencies exist, no cycle, its record matches the work-unit schema, its card fills the execute slot). It
        records the unit it would create as ``found["work_id"]`` and ``found["unit"]``; ``work_id`` is unused."""
        def check() -> None:
            self._check_create_arguments(args)
            lead = state.get("lead") or {}
            actor = {"kind": "lead", "session_label": lead.get("session_label"), "generation": lead.get("generation")}
            scratch = {**state, "work": dict(state["work"]), "counters": dict(state.get("counters") or {}),
                       "archived_refs": dict(state.get("archived_refs") or {})}
            wid, unit, _text = self._draft_unit(scratch, args, actor)
            args.setdefault("found", {}).update(work_id=wid, unit=unit)

        return checked(check)

    @staticmethod
    def _check_create_arguments(a: dict[str, Any]) -> None:
        kind, risk_class, scope_paths = a.get("kind"), a.get("risk_class"), a.get("scope_paths")
        acceptance_checks, acceptance_inputs = a.get("acceptance_checks"), a.get("acceptance_inputs")
        if kind not in RECORD_NAME:
            raise UsageError("kind must be ticket, story or epic")
        title = a.get("title")
        if not isinstance(title, str) or not title.strip():  # the query is a public answer (PR #170 review, 2)
            raise UsageError("a unit needs a title that is not blank")
        if not isinstance(risk_class, int) or not 0 <= risk_class <= 4:
            raise UsageError("risk class must be 0..4")
        if a.get("min_descendant_class") is not None and not a.get("rationale"):
            raise UsageError("a minimum descendant class requires a recorded rationale (WC §7.4)")
        if (acceptance_checks or acceptance_inputs) and kind != "ticket":
            raise UsageError("acceptance checks and inputs belong to a Ticket; a Story's or Epic's acceptance is its "
                             "children and its own gates")
        if acceptance_checks and kind == "ticket" and a.get("mutating") is False:
            raise UsageError(
                "--acceptance-check gates a mutating Ticket's change (Class 0 amendment, section 9 item 4); a "
                "non-mutating Ticket changes no source, so the check would be recorded and never run. State what its "
                "evidence must show in --goal or --contract instead", acceptance_checks=acceptance_checks)
        if a.get("class0_assertions") and risk_class != 0:
            raise UsageError("--class0-assert records the Lead's Class 0 eligibility assertions; it applies only "
                             "with --class 0")
        joined = [s for s in scope_paths or [] if "," in s]
        # M3-D9: several globs given as one value would match nothing, and every change would be out of scope.
        if joined:
            raise UsageError(f"scope {joined[0]!r} is one glob containing a comma, which is almost certainly several "
                             "globs: give one glob per --scope and repeat --scope for each",
                             scope=joined)

    def _draft_unit(self, state: dict[str, Any], a: dict[str, Any],
                    actor: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
        """Create the unit in ``state`` (the transaction's, or the query's copy): its id from the counter, its record
        text and its control entry, checked against the graph. Returns (id, unit, record text)."""
        kind, title, risk_class, parent = a["kind"], a["title"], a["risk_class"], a.get("parent")
        mutating, min_descendant_class = a.get("mutating"), a.get("min_descendant_class")
        if parent is not None:
            self.units.check_parent(state, kind, parent)
        edges = self.units.parse_edges(state, a.get("depends_on") or [])
        state["counters"][kind] = state["counters"].get(kind, 0) + 1
        work_id = format_id(KIND_PREFIX[kind], state["counters"][kind])
        is_mutating = (kind == "ticket") if mutating is None else (mutating and kind == "ticket")
        policy = None
        if kind != "ticket" and (a.get("mandatory_gates") or min_descendant_class is not None):
            policy = {"mandatory_gates": list(a.get("mandatory_gates") or []),
                      "min_descendant_class": min_descendant_class, "rationale": a.get("rationale")}
        record = work_unit_record(
            unit_id=work_id, kind=kind, title=title, created_at=utc_now(),
            created_by={k: actor[k] for k in ("kind", "session_label", "generation")},
            risk_class=risk_class, mutating=is_mutating, parent=parent, scope_paths=a.get("scope_paths"),
            goal_backwards=a.get("goal_backwards"), contract=a.get("contract"), policy=policy,
            external_refs=a.get("external_refs"), body=a.get("body") or "", promoted_from=a.get("promoted_from"),
            acceptance_checks=a.get("acceptance_checks"), acceptance_inputs=a.get("acceptance_inputs"),
            class0_assertions=a.get("class0_assertions"),
        )
        text = record.render()
        path = f"work/{work_id}/{RECORD_NAME[kind]}"
        unit: dict[str, Any] = {
            "kind": kind, "title": title, "record": path, "record_sha256": sha256_text(text),
            "parent": parent, "state": "PLANNING" if kind != "ticket" else "BLOCKED", "state_reason": "created",
            "risk_class": risk_class, "mutating": is_mutating, "depends_on": edges,
            "policy": policy, "created_at": utc_now(), "plan": None, "plans": [],
        }
        if kind == "ticket":
            unit.update(blocked_by=[{"kind": "plan_not_accepted"}], workspace=None, invocations=[],
                        implementer_invocation=None, evidence=[], classifications=[], waivers=[],
                        integration=None)
        if a.get("promoted_from"):
            unit["promoted_from"] = a["promoted_from"]
        state["work"][work_id] = unit
        self.units.refuse_cycles(state)
        if a.get("card"):
            chosen = self.roles.role_catalog().get(a["card"])
            self.roles.slot_ok(unit, "execute", chosen)
            unit["role_plan"] = {"execute": [{"card": chosen.id, "version": chosen.meta.get("version"),
                                              "selected_by": "lead", "pinned": False}],
                                 "review": [], "verify": [], "forbidden": []}
        return work_id, unit, text

    def _unmatched_scope(self, scope_paths: list[str]) -> list[str]:
        """The scope globs that match no file at the authoritative commit (M3 dogfood report §6.6, E10: a Lead that
        could not look at the project guessed seven globs, none of them the code's directory, and nothing said so).
        A Ticket's scope is fixed once it exists, so this is said at creation; it is a warning, not a refusal, since
        a Ticket may create new directories."""
        commit = self.k.authoritative_commit()
        if not scope_paths or not commit:
            return []
        try:
            files = git.out("ls-tree", "-r", "--name-only", commit, cwd=self.k.repo_root).splitlines()
        except GitError:
            return []
        return [g for g in scope_paths if not any(glob_any(f, [g]) for f in files)]

    def work_reclassify(self, *, token: str, expect_rev: int, work_id: str, risk_class: int,
                        reason: str) -> dict[str, Any]:
        """Raise a unit's risk class (WC §7.4: classification may increase whenever evidence exposes more risk),
        as a recorded decision. Never below an inherited minimum class; lowering a class is not offered here. The
        gates follow the new class at once, and inherited gates stay required."""
        if not (reason and reason.strip()):
            raise UsageError("a reclassification needs the reason the class goes up")
        if not 0 <= risk_class <= 4:
            raise UsageError("risk class must be 0..4")
        with self.k.lead_txn(token, expect_rev, "work.reclassify", reason=reason) as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            if unit["state"] in transitions.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}; a finished unit keeps its class")
            old = unit["risk_class"]
            if risk_class <= old:
                raise UsageError(f"{work_id} is class {old}: reclassification raises the class (lowering it is a "
                                 "demotion, which needs its own recorded decision and is not offered here)",
                                 current=old)
            floors = [(state["work"][a].get("policy") or {}).get("min_descendant_class")
                      for a in H.ancestors(state, work_id)]
            floor = max([f for f in floors if f is not None], default=None)
            if floor is not None and risk_class < floor:
                raise UsageError(f"an ancestor requires at least class {floor} for {work_id}: choose class {floor} or "
                                 "above", floor=floor)
            # Why a seemingly tiny Ticket became Class 2 stays answerable: both classes, the inherited minimum at the
            # time, the reason, and the actor (with the Lead generation) are on the record (designer, 2026-10-03).
            change = {"from_class": old, "to_class": risk_class, "effective_minimum_at_decision": floor}
            decision = self.k.new_decision(ctx, "reclassification", f"{work_id} class {old} -> {risk_class}",
                                           work_unit=work_id, reason=reason, reclassification=change)
            unit["risk_class"] = risk_class
            unit.setdefault("history", []).append(
                {"from": unit["state"], "to": unit["state"], "at": utc_now(), "event": "reclassified",
                 "reason": f"class {old} -> {risk_class} ({decision}): {reason}", **change,
                 "decided_by": {k: ctx.actor.get(k) for k in ("kind", "session_label", "generation")}})
            ctx.summary = f"{work_id} reclassified: class {old} -> {risk_class}"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, **change, "decision": decision,
                "revision": ctx.session.committed_revision}

    def plan_propose(self, *, token: str, expect_rev: int, work_id: str, body: str,
                     reason: str | None = None, affected_paths: list[str] | None = None,
                     review: list[str] | None = None, verify: list[str] | None = None,
                     no_assurance: bool = False) -> dict[str, Any]:
        if not body.strip():
            raise UsageError("plan body is empty")
        args: dict[str, Any] = {"body": body, "reason": reason, "affected_paths": affected_paths, "review": review,
                                "verify": verify, "no_assurance": no_assurance}
        with self.k.lead_txn(token, expect_rev, "plan.propose", reason=reason) as ctx:
            require(self.propose_query(ctx.state, work_id, args))  # the guard (M4-E E4), then the write
            unit = ctx.state["work"][work_id]
            assurance = args["found"]["assurance"]
            path, revision = self.units.propose(ctx, work_id, unit, body=body, reason=reason,
                                           affected_paths=affected_paths, assurance=assurance)
            ctx.summary = f"{work_id} plan v{revision} proposed"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "revision_number": revision, "path": path,
                "revision": ctx.session.committed_revision}

    def propose_query(self, state: dict[str, Any], work_id: str, args: dict[str, Any]) -> Any:
        """``plan.propose`` (M4-E E4: its guard as a query): a non-empty body, for a hot unit that is not finished,
        with its assurance declared (cards that fill their slots and are not forbidden, or ``none``), and a revision
        whose record is valid (one that supersedes an accepted plan states its reason). It records the resolved
        assurance as ``found["assurance"]``."""
        def check() -> None:
            body = args.get("body") or ""
            if not body.strip():
                raise UsageError("plan body is empty")
            unit = self.units.unit(state, work_id)
            if unit["state"] in transitions.TERMINAL:
                raise IllegalTransition(f"{work_id} is {unit['state']}")
            assurance = self.roles.resolve_plan_assurance(unit, review=args.get("review"), verify=args.get("verify"),
                                                          none=bool(args.get("no_assurance")))
            lead = state.get("lead") or {}
            self.units.plan_draft(work_id, unit, body=body, reason=args.get("reason"),
                                  affected_paths=args.get("affected_paths"), assurance=assurance,
                                  author={"role": "lead", "session_label": lead.get("session_label"),
                                          "generation": lead.get("generation")})
            args.setdefault("found", {})["assurance"] = assurance

        return checked(check)

    def plan_accept(self, *, token: str, expect_rev: int, work_id: str, revision: int) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "plan.accept") as ctx:
            unit = self.units.unit(ctx.state, work_id)
            if H.is_parent(unit):
                allowed = (set(H.PARENT_STATES) - H.TERMINAL) | {"OPEN"}
            else:
                allowed = PLAN_ACCEPT_TICKET_STATES
            if unit["state"] not in allowed:
                raise IllegalTransition(
                    f"{work_id} is {unit['state']}; move it to REPLAN_REQUIRED before changing the accepted plan",
                )
            entry = next((p for p in unit["plans"] if p["revision"] == revision), None)
            if entry is None:
                raise NotFound(f"{work_id} has no plan revision {revision}")
            if entry["status"] != "proposed":
                raise IllegalTransition(f"plan v{revision} is {entry['status']}")
            # A revision replaces only the plan it was proposed against: accepting an older proposal would rebind
            # its assurance over a newer plan's, and skip the reason a supersession needs (M3 review, B1).
            current = (unit.get("plan") or {}).get("accepted")
            if entry.get("supersedes") != current:
                against = f"plan v{entry['supersedes']}" if entry.get("supersedes") else "no accepted plan"
                raise IllegalTransition(f"plan v{revision} was proposed against {against}, but plan v{current} is "
                                        "accepted now; propose a new revision to change it")
            for p in unit["plans"]:
                if p["status"] == "accepted":
                    p["status"] = "superseded"
            entry["status"] = "accepted"
            unit["plan"] = {"accepted": revision, "path": entry["path"], "sha256": entry["sha256"],
                            "ancestor_plans": self.units.ancestor_plan_snapshot(ctx.state, work_id)}
            # The plan's declared review and verification become required gates (UAT 2026-09-30).
            self.roles.bind_plan_assurance(unit, revision, entry.get("assurance"))
            if H.is_parent(unit) and not unit.get("baseline_commit"):
                unit["baseline_commit"] = self.k.authoritative_commit()
            decision = self.k.new_decision(ctx, "plan_acceptance", f"{work_id} plan v{revision} accepted",
                                         work_unit=work_id, evidence_refs=[entry["path"]])
            if unit["state"] == "REPLAN_REQUIRED":
                # Work done under the superseded plan never continues implicitly: the old attempt's workspace
                # stops being live and its invocations are cancelled; the next assignment starts fresh (review M2).
                self.invocations.release_workspace(ctx, unit, f"replanned: plan v{revision} accepted")
                blockers = readiness_blockers(ctx.state, unit, repo_root=self.k.repo_root,
                                              base_commit=self.k.authoritative_commit(), work_id=work_id,
                                              plan_problem=self.units.plan_binding_problem)
                to = "BLOCKED" if blockers else "READY"
                transitions.check("REPLAN_REQUIRED", to, "plan.accept")
                self.units.set_state(unit, to, f"plan v{revision} accepted", state=ctx.state)
            ctx.summary = f"{work_id} plan v{revision} accepted ({decision})"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "accepted": revision, "decision": decision,
                "revision": ctx.session.committed_revision}

    def work_transition(self, *, token: str, expect_rev: int, work_id: str, to: str,
                        reason: str | None = None) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "work.transition", reason=reason) as ctx:
            # The guard's query, then the rule's guard (its own query first, then its effects): M4-E E4.
            args: dict[str, Any] = {"to": to, "reason": reason}
            require(self.units.transition_rule_query(ctx.state, work_id, args))
            unit = ctx.state["work"][work_id]
            frm = unit["state"]
            rule = args["found"]["rule"]
            self.units.check_guard(rule.guard, ctx, work_id, unit, to)
            if to == "ESCALATED":
                unit["escalated_from"] = frm
            if frm == "ESCALATED":
                unit.pop("escalated_from", None)
            change = self.units.set_state(unit, to, reason, state=ctx.state)
            decision = None
            if to == "CANCELLED":
                decision = self.k.new_decision(ctx, "cancellation", f"{work_id} cancelled", work_unit=work_id,
                                             resulting_transition=change, reason=reason)
                self.invocations.release_workspace(ctx, unit, "cancelled")
            elif to == "RUNNING" and transitions.PHASE_ORDER.get(frm, 0) > transitions.PHASE_ORDER["RUNNING"]:
                decision = self.k.new_decision(ctx, "state_regression", f"{work_id} returned to RUNNING from {frm}",
                                             work_unit=work_id, resulting_transition=change, reason=reason)
            ctx.summary = f"{work_id} {frm} -> {to}"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "from": frm, "to": to, "decision": decision,
                "revision": ctx.session.committed_revision}

    def work_reconcile(self, *, token: str, expect_rev: int, work_id: str, to: str, reason: str,
                       inspection: dict[str, Any] | None = None) -> dict[str, Any]:
        """INTERRUPTED -> an earlier-or-equal phase, after the Lead inspected workspace and artifacts."""
        with self.k.lead_txn(token, expect_rev, "work.reconcile", reason=reason) as ctx:
            unit = self.units.unit(ctx.state, work_id)
            frm = unit["state"]
            rule = transitions.check(frm, to, "reconcile")
            if not (reason and reason.strip()):
                raise UsageError("reconciliation requires --reason describing what was inspected")
            self.units.check_guard(rule.guard, ctx, work_id, unit, to)
            inspection = inspection or self.invocations.inspect_workspace(unit)
            change = self.units.set_state(unit, to, reason, state=ctx.state)
            unit.pop("interrupted_from", None)
            decision = self.k.new_decision(
                ctx, "reconciliation", f"{work_id} reconciled from INTERRUPTED to {to}", work_unit=work_id,
                resulting_transition=change, reason=reason,
                body="Inspection at reconciliation:\n\n" + "\n".join(f"- {k}: {v}" for k, v in inspection.items()),
            )
            ctx.summary = f"{work_id} reconciled -> {to}"
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "to": to, "decision": decision, "inspection": inspection,
                "revision": ctx.session.committed_revision}

    def work_show(self, work_id: str) -> dict[str, Any]:
        """One unit, hot or archived (its record as it stands now, R7), with its children: hot ones, and archived ones
        found through the index."""
        state = self.k.store.read()
        unit = self.units.view(state, work_id)
        record_path = self.k.aew_root / unit["record"]
        children = sorted({k for k, v in state["work"].items() if v.get("parent") == work_id}
                          | set(self.archive.archived_child_ids(state, work_id)))
        out = {"id": work_id, "revision": state["revision"], "control": unit,
               "record": record_path.read_text(encoding="utf-8") if record_path.exists() else None,
               "allowed_transitions": transitions.allowed_from(unit["state"]),
               "children": children,
               "rollup": self.units.rollup(state, work_id) if unit["kind"] != "ticket" and work_id in state["work"]
               else None}
        # F9-A (plan D-24, D-31): the unit's coordination threads, only while the switch is on or a thread exists, so
        # a project that never enabled messaging shows exactly what it showed before. Display only: nothing here is
        # read by a gate or a transition.
        threads = self.coordination.unit_threads(state, work_id, unit)
        if threads is not None:
            out["coordination"] = threads
        return out

    def work_list(self, *, state_filter: str | None = None) -> dict[str, Any]:
        """The hot units, and finished ones: the most recent (bounded) when unfiltered, and every archived unit in a
        finished state when that state is asked for (an explicit history query, proportional to its answer; R7)."""
        state = self.k.store.read()
        items = [
            {"id": wid, "kind": u["kind"], "state": u["state"], "title": u["title"], "parent": u.get("parent"),
             "risk_class": u["risk_class"], "blocked_by": u.get("blocked_by", [])}
            for wid, u in sorted(state["work"].items())
            if state_filter is None or u["state"] == state_filter
        ]
        if state_filter in transitions.TERMINAL:
            hot = {i["id"] for i in items}
            items += [{"id": e["id"], "kind": e.get("unit_kind"), "state": e["state"], "title": e.get("title"),
                       "parent": e.get("parent"), "archived": True}
                      for e in self.archive.archived_units(state, state_filter) if e["id"] not in hot]
            items.sort(key=lambda i: i["id"])
        elif state_filter is None:
            items += [{**r, "archived": True} for r in state.get("recent", []) if r["id"] not in state["work"]]
            items.sort(key=lambda i: i["id"])
        return {"revision": state["revision"], "items": items}
