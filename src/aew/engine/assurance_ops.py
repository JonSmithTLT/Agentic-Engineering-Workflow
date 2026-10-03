"""The M4-A assurance guards of the dispatch predicate: protected conditions, hard triggers, Class 0 eligibility.

They apply only where a dispatch grants mutation (an implementer for a mutating Ticket, by assignment, by a new
implementer invocation, or by a harness run holding an implementer's credential). The checks themselves are the pure
functions in ``aew.engine.assurance``; this collaborator gathers their inputs: the Ticket's record, its accepted plan,
the project's policy and the files tracked at the source commit the dispatch uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aew.engine import assurance as A
from aew.engine import gates as G
from aew.engine.dispatch import Blocker, GuardRegistration
from aew.errors import GitError
from aew.knowledge.records import read_record
from aew.workspace import git

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import GatesPort


class Assurance:
    def __init__(self, k: Kernel, *, gates: GatesPort) -> None:
        self.k = k
        self.gates = gates

    def dispatch_guards(self) -> list[GuardRegistration]:
        return [GuardRegistration("protected.overlap", self.guard_protected),
                GuardRegistration("assurance.triggers", self.guard_triggers),
                GuardRegistration("class0.eligible", self.guard_class0)]

    # ---- inputs

    @staticmethod
    def grants_mutation(state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> bool:
        unit = state["work"][work_id]
        return unit["kind"] == "ticket" and bool(unit.get("mutating")) and facts.get("archetype") == "implementer"

    def _inputs(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> dict[str, Any]:
        """The Ticket's record, plan, policy and tracked files, gathered once per decision."""
        if "assurance_inputs" in facts:
            return facts["assurance_inputs"]
        unit = state["work"][work_id]
        meta = self.gates.record_meta(unit)
        commit = facts.get("base") or (unit.get("workspace") or {}).get("base_commit") \
            or self.k.authoritative_commit()
        try:
            files = git.out("ls-tree", "-r", "--name-only", commit, cwd=self.k.repo_root).splitlines() if commit else []
        except GitError:
            files = []
        plan = unit.get("plan") or {}
        affected: list[str] = []
        if plan.get("path"):
            affected = list(read_record(self.k.aew_root / plan["path"], "plan").meta.get("affected_paths") or [])
        guardrails, checks = self.k.policy("guardrails"), self.k.policy("checks")
        lint = A.plan_lint(meta=meta, affected=affected, guardrails=guardrails, checks=checks,
                           mutating=bool(unit.get("mutating")))
        found = {"meta": meta, "files": files, "guardrails": guardrails, "checks": checks, "lint": lint,
                 "scope": list((meta.get("scope") or {}).get("paths") or []),
                 "obligations": G.effective_obligations(state, work_id, self.k.policy("gates"))}
        facts["assurance_inputs"] = found
        facts["digests"]["plan"] = {"revision": plan.get("accepted"), "sha256": plan.get("sha256")}
        facts["digests"]["source"] = commit
        return found

    # ---- guards

    def guard_protected(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> list[Blocker] | None:
        if not self.grants_mutation(state, work_id, facts):
            return None
        i = self._inputs(state, work_id, facts)
        out = []
        overlap = A.protected_overlap(i["scope"], i["guardrails"], i["files"])
        if overlap:
            out.append(Blocker("PROTECTED_CONDITION_OVERLAP",
                               f"the scope {i['scope']} includes protected path(s) {overlap[:5]}: narrow the scope, or "
                               "change the protection in policy/guardrails.yaml as its own decision",
                               {"paths": overlap, "scope": i["scope"]}))
        out += [Blocker(x["code"], x["message"], {k: v for k, v in x.items() if k not in {"code", "message",
                                                                                         "severity"}})
                for x in i["lint"] if x["severity"] == "error"]
        return out

    def guard_triggers(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> None:
        """Deterministic hard triggers (v0.4 §22): recorded as obligations, never a refusal on their own."""
        if not self.grants_mutation(state, work_id, facts):
            return None
        i = self._inputs(state, work_id, facts)
        inputs = list(((i["meta"].get("acceptance") or {}).get("inputs")) or [])
        in_scope = A.acceptance_inputs_in_scope(i["scope"], inputs, i["files"])
        if in_scope:
            facts["obligations"].append({"code": "ACCEPTANCE_INPUT_IN_SCOPE", "paths": in_scope,
                                         "obligation": "premise-sensitive assurance (v0.4 §22)"})
        elevated = A.inherited_elevation(i["obligations"])
        if elevated:
            facts["obligations"].append({"code": "INHERITED_ELEVATED_OBLIGATION", **elevated,
                                         "obligation": "the inherited gates and class floor apply"})
        for x in i["lint"]:
            if x["severity"] == "warning":
                facts["obligations"].append({"code": x["code"], "message": x["message"]})
        return None

    def guard_class0(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> list[Blocker] | None:
        """Class 0 requested (the Ticket's own class): eligibility, or a refusal with every reason (never a silent
        reclassification; the Lead chooses a stronger class with `aew work reclassify`). An inherited elevated
        obligation, a parent's non-waivable gate or minimum class, makes Class 0 ineligible (operator/designer,
        2026-10-03)."""
        if not self.grants_mutation(state, work_id, facts) or state["work"][work_id]["risk_class"] != 0:
            return None
        i = self._inputs(state, work_id, facts)
        triggers = [o for o in facts["obligations"]
                    if o["code"] in {"ACCEPTANCE_INPUT_IN_SCOPE", "INHERITED_ELEVATED_OBLIGATION"}]
        found = A.class0_blockers(meta=i["meta"], files=i["files"], guardrails=i["guardrails"], checks=i["checks"],
                                  triggers=triggers, lint=i["lint"])
        return [Blocker(x["code"], x["message"] + " (Class 0 is refused, not reclassified: raise the class with "
                                                  f"`aew work reclassify {work_id} --class N --reason ...`, or make "
                                                  "the Ticket eligible)", x.get("details") or {})
                for x in found]
