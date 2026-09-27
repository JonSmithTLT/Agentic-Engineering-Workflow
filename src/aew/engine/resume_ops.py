"""Lead reconstruction (`aew resume`), deterministic next actions, and checkpoints (WC §15.5; KC §15.1, §12.4).

A new Lead session rebuilds its context *only* from durable artifacts, in the
Knowledge Contract §15.1 order, and is shown the contradictions it must resolve
instead of silently choosing one artifact over another. Resume is read-only: it
never assumes authority; transfer requires a handoff or an operator-authorized
takeover.
"""

from __future__ import annotations

from typing import Any

from aew import SPEC_SET
from aew.engine import gates as G
from aew.engine import hierarchy as H
from aew.engine.dependencies import dependency_blockers
from aew.engine.hierarchy_ops import HierarchyOps
from aew.engine.nonmutating_ops import is_nm_ticket
from aew.errors import AEWError
from aew.knowledge import evidence as E
from aew.knowledge.manifest import MANIFEST
from aew.util import parse_frontmatter

RESUME_ORDER = [
    "project_manifest", "control_state", "active_work", "accepted_plans", "latest_handoff",
    "open_review_findings", "verification_failures", "authority_and_guardrails", "derived_knowledge",
    "next_actions",
]


class ResumeOps(HierarchyOps):
    # ------------------------------------------------------------------ next actions

    def next_actions(self, state: dict[str, Any]) -> list[str]:
        actions: list[str] = []
        lead = state["lead"]
        if lead["status"] == "vacant":
            actions.append("acquire Lead authority: `aew lead acquire --expect-rev N`")
        elif lead["status"] == "handoff_pending":
            actions.append("a Lead handoff is pending: the successor runs `aew lead handoff accept`")
        if any(c["status"] == "proposed" for c in self.manifest["authority"]["candidates"]):
            actions.append("classify authority candidates: `aew authority list`, then accept/reject")
        try:
            unconfigured = [k for k, v in self.policy("checks")["checks"].items() if not v.get("configured")]
            if unconfigured:
                actions.append(f"configure checks {unconfigured} in policy/checks.yaml (gates needing them stay blocked)")
        except AEWError:
            actions.append("fix invalid policy/checks.yaml")
        for wid, u in sorted(state["work"].items()):
            if u["kind"] != "ticket":
                actions.extend(f"{wid}: {a}" for a in self._parent_actions(state, wid, u))
                continue
            if is_nm_ticket(u):
                actions.extend(f"{wid}: {a}" for a in self._nm_ticket_actions(state, wid, u))
            else:
                actions.extend(f"{wid}: {a}" for a in self._ticket_actions(state, wid, u))
            actions.extend(f"{wid}: {a}" for a in self._common_actions(state, wid, u))
        actions.extend(f"{h['work_unit']}: {h['action']}" for h in self.harness_resume(state))
        return actions

    def harness_resume(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """The latest harness run of every active invocation that has runs (ADR-0009; empty without runs).

        Local telemetry, never read by a gate. A harness that ended, crashed or was lost changes no AEW state and
        is not an interruption (M3-B1): the invocation keeps its authority and is relaunched or cancelled."""
        from aew.harness import contract as K
        from aew.harness import runlog

        out = []
        for inv_id, inv in sorted(state["invocations"].items()):
            if inv["status"] != "active" or not inv.get("runs"):
                continue
            run = inv["runs"][-1]["run"]
            status, record = runlog.observed_status(runlog.run_dir(self.aew_root, run))
            evidence = sorted(e["id"] for e in E.scan(self.aew_root, inv["work_unit"])[0]  # the store, not the record
                              if e["producer"].get("run") == run)
            if status in (K.STARTING, K.RUNNING):
                action = f"{run} is running for {inv_id}: follow it with `aew harness wait {run}`"
            elif status == K.ENDED_WITH_EVIDENCE:
                action = f"{run} ended with evidence {', '.join(evidence)}: ingest it (the run itself decides nothing)"
            else:
                action = (f"{inv_id} has no live run ({run}: {status}): relaunch it with `aew harness launch {inv_id} "
                          f"--expect-rev N` (its credential rotates) or cancel it with `aew invoke cancel {inv_id}`")
            out.append({"invocation": inv_id, "work_unit": inv["work_unit"], "role": inv["role"], "run": run,
                        "status": status, "reason": (record or {}).get("reason"), "evidence": evidence,
                        "action": action})
        return out

    def _common_actions(self, state: dict[str, Any], wid: str, u: dict[str, Any]) -> list[str]:
        """Plan bindings and stale inputs, for every Ticket (ADR-0007/0008)."""
        out = []
        if u["state"] in H.TERMINAL:
            return out
        if self.plan_binding_problem(state, wid):
            out.append(f"an ancestor's plan changed after this plan was accepted: `aew plan reconfirm {wid}` or a "
                       "new plan revision")
        if self.dispatch_binding_problem(state, wid):
            out.append("this attempt was dispatched with other dependencies than the Ticket now has: a new dispatch "
                       "is required (REPLAN_REQUIRED and a plan revision, or `aew work redispatch` if non-mutating)")
        if u["state"] in {"READY", "ASSIGNED", "RUNNING"}:
            for i in self.input_status(state, wid):
                if i["blocks_dispatch"]:
                    out.append(f"input {i['id']} from {i['from']} is {i['freshness']}: the next executor dispatch "
                               f"is refused until it is refreshed or acknowledged (`aew work acknowledge-input {wid} "
                               f"--input {i['id']} --from {i['from']} --reason ...`)")
        return out

    def _nm_ticket_actions(self, state: dict[str, Any], wid: str, u: dict[str, Any]) -> list[str]:
        st = u["state"]
        execution = u.get("execution") or {}
        executor = state["invocations"].get(execution.get("invocation") or "", {})
        if st in {"BLOCKED", "REVIEW_PENDING", "REVIEW_FAILED", "REVIEW_PASSED", "VERIFY_PENDING",
                  "VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE", "INTERRUPTED", "REPLAN_REQUIRED", "ESCALATED"}:
            actions = self._ticket_actions(state, wid, u)
            if st == "REVIEW_PASSED":
                actions = ["advance to VERIFY_PENDING, or accept the record (`aew work accept`) if no verification applies"]
            if st == "VERIFIED":
                actions = ["accept the record (`aew work accept`)"]
            if st == "INTERRUPTED":
                actions.append("then start a new attempt (`aew work redispatch`)")
            return actions
        if st == "READY":
            return ["dispatch it (`aew work dispatch`); the executor card is pinned with its output kind"]
        if st == "ASSIGNED":
            return [f"launch executor {execution.get('invocation')} (attempt {execution.get('attempt')}, "
                    f"{execution.get('expected_kind')}) from its pack, then move to RUNNING"]
        if st == "RUNNING":
            if execution.get("record"):
                gc = self.gate_context(state, wid)
                unmet = G.unmet(gc["gates"]) | ({"accepted_plan": G.STALE} if gc.get("plan_binding") else {})
                if unmet:
                    return [f"record {execution['record']['id']} ingested; unmet gates {unmet}"]
                return ["advance to review/verification, or accept the record (`aew work accept`)"]
            if executor.get("status") == "active":
                pending = self._submitted(state, wid, u, execution.get("expected_kind") or "")
                if pending:
                    return [f"ingest record {e} (`aew evidence ingest`)" for e in pending]
                return [f"executor {execution['invocation']} (attempt {execution['attempt']}) in progress"]
            return ["no live executor for the current attempt: start a new one (`aew work redispatch --reason ...`)"]
        if st == "VERIFIED":
            return ["accept the record (`aew work accept`)"]
        return []

    def _parent_actions(self, state: dict[str, Any], wid: str, u: dict[str, Any]) -> list[str]:
        st = u["state"]
        out = list(f"attention: {a}" for a in u.get("attention", []))
        if st in H.TERMINAL:
            return []
        if self.plan_binding_problem(state, wid):
            out.append(f"an ancestor's plan changed after this plan was accepted: `aew plan reconfirm {wid}`")
        if st in {"PLANNING", "OPEN"}:
            out.append("plan it and create its children (`aew plan propose/accept`, `aew work create --parent`)")
        elif st == "IN_PROGRESS" and u.get("blocked_descendants"):
            out.append("every open descendant is BLOCKED: check their dependencies")
        elif st == "ACCEPTANCE_PENDING":
            try:
                gc = self.gate_context(state, wid)
            except AEWError as exc:
                return out + [f"cannot evaluate parent gates: {exc.message}"]
            unmet = G.unmet(gc["gates"]) | ({"accepted_plan": G.STALE} if gc.get("plan_binding") else {})
            waiting = dependency_blockers(state, u, repo_root=self.repo_root, base_commit=self.authoritative_commit(),
                                          work_id=wid)
            if (u.get("parent_verification") or {}).get("awaiting_classification"):
                out.append(f"classify the failed parent verification (`aew verify classify {wid}`)")
            elif waiting:  # acceptance is a downstream assignment: review, verification and closeout all wait
                pass
            elif unmet:
                out.append(f"all children are DONE/CANCELLED; satisfy parent gates {unmet} "
                           f"(`aew invoke create {wid} --role reviewer|verifier`, ingest)")
            elif gc["open_required_findings"]:
                out.append("resolve parent-level findings before closeout")
            else:
                out.append(f"all parent gates are CURRENT: close it (`aew work close {wid}`)")
            out += [f"waiting on {b['id']} ({b['reason']}) before its acceptance review, verification and closeout"
                    for b in waiting]
        return out

    def _submitted(self, state: dict[str, Any], wid: str, u: dict[str, Any], kind: str) -> list[str]:
        """Evidence submitted by active invocations but not yet ingested by the Lead."""
        ingested = {e["id"] for e in u.get("evidence", [])}
        active = {i for i in u.get("invocations", []) if state["invocations"][i]["status"] == "active"}
        records, _ = E.scan(self.aew_root, wid)
        return [e["id"] for e in records
                if e["kind"] == kind and e["producer"]["invocation"] in active and e["id"] not in ingested]

    def _ticket_actions(self, state: dict[str, Any], wid: str, u: dict[str, Any]) -> list[str]:
        st = u["state"]
        active = [i for i in u.get("invocations", []) if state["invocations"][i]["status"] == "active"]
        if st == "BLOCKED":
            out = []
            for b in u.get("blocked_by", []):
                if b["kind"] == "plan_not_accepted":
                    out.append("propose and accept a plan (`aew plan propose/accept`)")
                elif b["kind"] == "plan_binding_stale":
                    out.append(f"an ancestor's plan changed: `aew plan reconfirm {wid}` or a new plan revision")
                else:
                    out.append(f"waiting on {b['id']} ({b['reason']})")
            return out
        if st == "READY":
            return ["staff it (`aew work roles` / `aew work staff`), then `aew work assign`"]
        if st == "ASSIGNED":
            return [f"launch the implementer from its pack ({u.get('implementer_invocation')}), then move to RUNNING"]
        if st == "RUNNING":
            if u.get("implementer_invocation") in active:
                return [f"implementer {u['implementer_invocation']} in progress; when its report and checks are in, "
                        "advance to REVIEW_PENDING"]
            return ["dispatch a fresh implementer (`aew invoke create`)"]
        if st == "REVIEW_PENDING":
            pending = self._submitted(state, wid, u, "review")
            if pending:
                return [f"ingest review {e} (`aew review ingest`)" for e in pending]
            if active:
                return [f"review in progress ({', '.join(active)})"]
            return ["dispatch the next planned reviewer card (`aew invoke create`)"]
        if st == "REVIEW_FAILED":
            return ["return to RUNNING and dispatch an implementer with the findings"]
        if st == "REVIEW_PASSED":
            return ["advance to VERIFY_PENDING (or COMMIT_READY if no verification is required)"]
        if st == "VERIFY_PENDING":
            pending = self._submitted(state, wid, u, "verification")
            if pending:
                return [f"ingest verification {e} (`aew verify ingest`)" for e in pending]
            if active:
                return [f"verification in progress ({', '.join(active)})"]
            return ["dispatch the next planned verifier card (`aew invoke create`)"]
        if st == "VERIFICATION_FAILED":
            return ["classify the failure (Lead only): `aew verify classify --as ...`"]
        if st == "VERIFICATION_INCONCLUSIVE":
            return ["resolve the environment/evidence blocker, then return to VERIFY_PENDING"]
        if st == "VERIFIED":
            return ["advance to COMMIT_READY"]
        if st == "COMMIT_READY":
            status = (u.get("integration") or {}).get("status")
            return [{
                None: "integrate: `aew integrate prepare`",
                "discarded": "integrate: `aew integrate prepare`",
                "stale_candidate": "the candidate is stale: `aew integrate prepare` again, then revalidate",
                "conflict": "integration conflict: return to RUNNING (rebase) or REPLAN_REQUIRED",
                "prepared": "dispatch post-integration verification (`aew invoke create --scope integration`)",
                "validation_inconclusive": "resolve the post-integration verification blocker and re-verify",
                "validated": "publish: `aew integrate publish`",
                "publishing": "an interrupted publish: `aew integrate reconcile`",
            }.get(status, f"integration status {status}")]
        if st == "INTERRUPTED":
            return [f"inspect workspace/artifacts and reconcile (interrupted in {u.get('interrupted_from')}); "
                    "success is never assumed"]
        if st == "REPLAN_REQUIRED":
            return ["propose and accept a new plan revision"]
        if st == "ESCALATED":
            return ["record the escalation outcome and return the Ticket"]
        return []

    # ------------------------------------------------------------------ resume

    def _plan_brief(self, u: dict[str, Any]) -> dict[str, Any] | None:
        plan = u.get("plan")
        if not plan:
            return None
        _, body = parse_frontmatter((self.aew_root / plan["path"]).read_text(encoding="utf-8"))
        return {"revision": plan["accepted"], "path": plan["path"], "sha256": plan["sha256"], "text": body.strip()}

    def _freshness(self, name: str, rel: str | None) -> dict[str, Any]:
        if not rel:
            return {"name": name, "path": None, "freshness": "UNAVAILABLE", "detail": "not generated"}
        path = self.aew_root / rel
        if not path.exists():
            return {"name": name, "path": rel, "freshness": "UNAVAILABLE", "detail": "missing"}
        try:
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except AEWError:
            meta = {}
        source = meta.get("source_revision")
        if not source:
            return {"name": name, "path": rel, "freshness": "AUTHORED", "detail": "maintained by people, not derived"}
        current = self.authoritative_commit()
        return {"name": name, "path": rel, "freshness": "CURRENT" if source == current else "STALE",
                "source_revision": source, "authoritative_revision": current}

    def resume(self) -> dict[str, Any]:
        state = self.store.read()
        lead = state["lead"]
        work = []
        findings = []
        failures = []
        for wid, u in sorted(state["work"].items()):
            entry: dict[str, Any] = {"id": wid, "kind": u["kind"], "title": u["title"], "state": u["state"],
                                     "risk_class": u["risk_class"], "parent": u.get("parent"),
                                     "depends_on": u.get("depends_on", []), "blocked_by": u.get("blocked_by", [])}
            if u["kind"] == "ticket":
                gc = None
                if u["state"] not in {"DONE", "CANCELLED"}:
                    try:
                        gc = self.gate_context(state, wid)
                    except AEWError:
                        gc = None
                entry.update(
                    accepted_plan=self._plan_brief(u),
                    role_plan={k: v for k, v in self.effective_role_plan(state, wid, gc)["effective"].items()},
                    workspace={k: u["workspace"][k] for k in ("id", "path", "base_commit", "status")}
                    if u.get("workspace") else None,
                    active_invocations=[{"id": i, "role": state["invocations"][i]["role"],
                                         "card": (state["invocations"][i].get("card") or {}).get("id")}
                                        for i in u.get("invocations", [])
                                        if state["invocations"][i]["status"] == "active"],
                    integration=(u.get("integration") or {}).get("status"),
                    completion_record=u.get("completion_record"),
                    unmet_gates=G.unmet(gc["gates"]) if gc and gc["snapshot"] else None,
                )
                findings += [dict(f, work_unit=wid) for f in u.get("findings", []) if f["status"] == "open"]
                if u["state"] in {"VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE"} or \
                        (u.get("integration") or {}).get("status") == "validation_failed":
                    failures.append({"work_unit": wid, "state": u["state"],
                                     "evidence": (u.get("last_verification") or {}).get("evidence"),
                                     "classifications": u.get("classifications", [])})
                if is_nm_ticket(u):
                    entry["execution"] = u.get("execution")
                    entry["attempts"] = u.get("attempts", 0)
                entry["plan_binding"] = self.plan_binding_problem(state, wid)
                entry["dispatch_binding"] = self.dispatch_binding_problem(state, wid)
                if u["state"] not in H.TERMINAL:
                    entry["inputs"] = self.input_status(state, wid)
                if u.get("input_acknowledgements"):
                    entry["input_acknowledgements"] = u["input_acknowledgements"]
            else:
                entry["rollup"] = self.rollup(state, wid)
                entry.update(accepted_plan=self._plan_brief(u), attention=u.get("attention", []),
                             blocked_descendants=u.get("blocked_descendants", False),
                             children=H.children(state, wid), closeout=u.get("closeout"),
                             cancellation=u.get("cancellation"), plan_binding=self.plan_binding_problem(state, wid))
                findings += [dict(f, work_unit=wid) for f in u.get("findings", []) if f["status"] == "open"]
            work.append(entry)
        latest = state.get("latest_handoff")
        handoff = None
        if latest and (self.aew_root / latest).exists():
            handoff = {"path": latest, "text": (self.aew_root / latest).read_text(encoding="utf-8")}
        holder = f"generation {lead['generation']}" + (f" ({lead['session_label']})" if lead.get("session_label") else "")
        guidance = {
            "vacant": "No Lead holds authority: acquire it with `aew lead acquire`.",
            "handoff_pending": "A cooperative handoff is pending; the successor accepts with the offer secret.",
        }.get(lead["status"], (
            f"Lead authority is held by {holder}. This session must not act as Lead unless authority is "
            "transferred: a cooperative `aew lead handoff accept`, or — if the previous session is lost — an "
            "operator-authorized `aew lead takeover` run by the operator at an interactive terminal."))
        catalog = self.role_catalog()
        return {
            "order": RESUME_ORDER,
            "spec_set": SPEC_SET,
            "project": {"id": self.project_id, "name": self.manifest["project"]["name"], "manifest": MANIFEST},
            "control": {"revision": state["revision"], "last_transition": state["last_transition"]},
            "lead": {"status": lead["status"], "generation": lead["generation"],
                     "session_label": lead.get("session_label"), "holder_reachable": "unknown"},
            "authority_guidance": guidance,
            "work": work,
            "latest_handoff": handoff,
            "open_review_findings": findings,
            "verification_failures": failures,
            "accepted_authority": self.manifest["authority"]["accepted"],
            "authority_candidates_pending": [c for c in self.manifest["authority"]["candidates"]
                                             if c["status"] == "proposed"],
            "guardrails": self.manifest["policy"]["guardrails"],
            "derived_knowledge": [self._freshness(n, r) for n, r in sorted(self.manifest["knowledge"].items())],
            "role_catalog": [{"id": c.id, "display_name": c.meta["display_name"], "extends": c.archetype,
                              "use_when": c.meta.get("use_when", [])}
                             for c in sorted(catalog.cards.values(), key=lambda c: c.id)],
            "role_catalog_problems": catalog.problems,
            "tree": self.work_tree()["lines"],
            "lead_note": state.get("next_action"),
            "next_actions": self.next_actions(state),
            "contradictions": self.contradictions(state) + [f"evidence: {p}" for u in state["work"]
                                                            for p in E.scan(self.aew_root, u)[1]],
            **({"harness_runs": runs} if (runs := self.harness_resume(state)) else {}),
        }

    def render_resume(self, r: dict[str, Any]) -> str:
        lines = [f"# AEW resume — {r['project']['name']} (control revision {r['control']['revision']})", "",
                 f"Lead: {r['lead']['status']} (generation {r['lead']['generation']})", r["authority_guidance"], ""]
        if r.get("tree"):
            lines += ["## Hierarchy", "", "```text", *r["tree"], "```", ""]
        lines.append("## Work")
        for w in r["work"]:
            lines.append(f"- {w['id']} [{w['state']}] {w['title']}")
            if w.get("role_plan"):
                staffed = "; ".join(f"{slot}: {', '.join(e['card'] for e in es) or '-'}"
                                    for slot, es in w["role_plan"].items())
                lines.append(f"    roles: {staffed}")
            if w.get("unmet_gates"):
                lines.append(f"    unmet gates: {w['unmet_gates']}")
        if r["open_review_findings"]:
            lines += ["", "## Open review findings", *(f"- {f['id']} [{f['severity']}] {f['summary']}"
                                                       for f in r["open_review_findings"])]
        if r["verification_failures"]:
            lines += ["", "## Verification failures / blockers", *(f"- {f['work_unit']}: {f['state']}"
                                                                   for f in r["verification_failures"])]
        if r.get("harness_runs"):
            lines += ["", "## Harness runs (local telemetry; a run decides nothing)",
                      *(f"- {h['run']} ({h['invocation']}, {h['role']}, {h['work_unit']}): {h['status']}"
                        + (f" — {h['reason']}" if h.get("reason") else "") for h in r["harness_runs"])]
        lines += ["", "## Next actions", *(f"- {a}" for a in r["next_actions"] or ["(none)"])]
        if r["lead_note"]:
            lines += ["", f"Lead's note: {r['lead_note']}"]
        if r["contradictions"]:
            lines += ["", "## CONTRADICTIONS (resolve before proceeding)", *(f"- {c}" for c in r["contradictions"])]
        return "\n".join(lines)

    # ------------------------------------------------------------------ checkpoint

    def checkpoint(self, *, token: str, expect_rev: int, note: str = "", next_action: str | None = None) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "checkpoint") as ctx:
            if next_action is not None:
                ctx.state["next_action"] = next_action or None
            path = self._write_handoff(ctx, note, [])
            ctx.summary = f"checkpoint {path}"
        return {"ok": True, "checkpoint": path, "revision": ctx.session.committed_revision}

    def status(self, work_id: str | None = None) -> dict[str, Any]:  # adds role catalog health
        out = super().status(work_id)
        if work_id is None:
            out["role_catalog_problems"] = self.role_catalog().problems
        return out

