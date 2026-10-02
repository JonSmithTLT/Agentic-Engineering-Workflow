"""Context-pack assembly for invocations (WC §15.4; KC §15). Packs are rebuildable local data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aew import roles
from aew.engine.archive_ops import reference_summary
from aew.engine.base import TxnContext
from aew.errors import IntegrityError, NotFound
from aew.knowledge import context as ctxmod
from aew.knowledge import evidence as E
from aew.knowledge.records import read_record
from aew.util import atomic_write, parse_frontmatter, sha256_file, sha256_text
from aew.workspace import git

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import ArchivePort, WorkUnitsPort

AEW_EXCLUDE = ":(exclude).aew"


class ContextPacks:
    """Context packs for invocations (WC §15.4; KC §15). Packs are rebuildable local data."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, archive: ArchivePort) -> None:
        self.k = k
        self.units = units
        self.archive = archive

    def _hierarchy_context(self, state: dict[str, Any], wid: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        from aew.engine import gates as G
        from aew.engine import hierarchy as H

        chain = []
        for anc in reversed(H.ancestors(state, wid)):
            a = state["work"][anc]
            meta = read_record(self.k.aew_root / a["record"], "work-unit").meta
            chain.append({"id": anc, "kind": a["kind"], "title": a["title"], "risk_class": a["risk_class"],
                          "plan": (a.get("plan") or {}).get("accepted"),
                          "goal_backwards": (meta.get("acceptance") or {}).get("goal_backwards", [])})
        obligations = G.effective_obligations(state, wid, {"risk_paths": {str(c): [] for c in range(5)}})
        return chain, {"non_waivable": obligations["non_waivable"], "floor": obligations["floor"]}

    def _input_summaries(self, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for i in inputs:
            ev = next((e for e in E.scan(self.k.aew_root, i["from"])[0] if e["id"] == i["id"]), None)
            summary: list[str] = []
            if ev:
                d, r, pr = ev.get("discovery") or {}, ev.get("research") or {}, ev.get("proposal") or {}
                summary += [f"fact: {f['statement']}" for f in d.get("facts", [])]
                summary += [f"hypothesis: {h['statement']}" for h in d.get("hypotheses", [])]
                summary += [f"conclusion: {c}" for c in r.get("conclusions", [])]
                summary += [f"subject: {s.get('name')} {s.get('version') or ''} ({s.get('source')})" for s in r.get("subjects", [])]
                if pr:
                    summary += [f"objective: {pr.get('objective')}", f"approach: {pr.get('approach')}"]
            out.append({**i, "summary": summary})
        return out

    def _m2_pack_extras(self, state: dict[str, Any], inv: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
        """Hierarchy, inputs, record under review and child outputs (ADR-0007/0008). Deterministic."""
        from aew.engine import hierarchy as H

        wid = inv["work_unit"]
        extras: dict[str, Any] = {}
        chain, inherited = self._hierarchy_context(state, wid)
        extras["hierarchy"] = chain
        extras["inherited"] = inherited if (inherited["non_waivable"] or inherited["floor"] is not None) else None
        extras["inputs"] = self._input_summaries(inv.get("inputs") or [])
        execution = unit.get("execution") or {}
        if inv["role"] in {"investigator", "researcher", "planner"}:
            extras["expected_kind"] = execution.get("expected_kind")
            extras["attempt"] = inv.get("attempt")
        if inv.get("subject"):
            s = inv["subject"]
            ev = next((e for e in E.scan(self.k.aew_root, wid)[0] if e["id"] == s["id"]), None)
            if ev:
                content = {k: ev[k] for k in ("claim", "result", "discovery", "research", "proposal") if k in ev}
                _, body = parse_frontmatter((self.k.aew_root / ev["_path"]).read_text(encoding="utf-8"))
                from aew.util import dump_yaml
                extras["subject"] = {"id": s["id"], "sha256": s["sha256"], "kind": ev["kind"],
                                     "content": dump_yaml(content),
                                     "body": body, "observed_commit": ev["evaluated_snapshot"]["base_revision"]}
        if inv.get("scope") == "parent":
            baseline = unit.get("baseline_commit")
            commit = (inv.get("observation") or {}).get("commit")
            children = []
            kids = sorted([(cid, state["work"][cid]) for cid in H.children(state, wid)]
                          + self.archive.archived_children(state, wid))  # archived children, for this review only
            for cid, c in kids:
                entry = {"id": cid, "kind": c["kind"], "title": c["title"], "state": c["state"],
                         "completion_record": c.get("completion_record"),
                         "completion_sha256": self.units.completion_sha(state, cid) if cid in state["work"]
                         else c.get("completion_sha256")}
                rec = (c.get("execution") or {}).get("record")
                if rec and c["state"] == "DONE":
                    entry["record"] = rec["id"]
                integrated = (c.get("integration") or {}).get("commit") if c["state"] == "DONE" else None
                if integrated:
                    entry["integrated_commit"] = integrated
                    args = ("diff", "--no-color", "--no-renames") if inv["role"] == "reviewer" \
                        else ("diff", "--stat", "--no-renames")
                    entry["diff"] = git.git(*args, f"{integrated}^1", integrated, "--", ".", AEW_EXCLUDE,
                                            cwd=self.k.repo_root).stdout.decode("utf-8", "replace")
                    if baseline and git.is_ancestor(integrated, baseline, cwd=self.k.repo_root):
                        entry["before_baseline"] = True  # already in the baseline: absent from baseline..A
                children.append(entry)
            extras["children"] = children
            if baseline and commit:  # rendered even when empty: that is when it would hide a child's change
                extras["aggregate_diffstat"] = git.out("diff", "--stat", "--no-renames", baseline, commit, "--", ".",
                                                       AEW_EXCLUDE, cwd=self.k.repo_root)
        return extras

    def _history_refs(self, state: dict[str, Any], inv: dict[str, Any]) -> list[dict[str, Any]]:
        """The historical records the Lead loaded for this invocation's unit before it was dispatched (pinned on the
        invocation), each read and verified against its pinned hash (ADR-0011 invariant 14)."""
        out = []
        for ref in inv.get("history_refs") or []:
            entries = [e for e in self.archive.index(state).by_id(ref["id"]) if e["sha256"] == ref["sha256"]]
            if not entries:
                raise IntegrityError(f"loaded historical record {ref['id']}@{ref['sha256'][:12]} is not in the history")
            out.append({**ref, "content": reference_summary(entries[-1], self.archive.record(entries[-1]))})
        return out

    @staticmethod
    def _history_sources(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"name": f"history:{r['id']}", "path": None, "sha256": r["sha256"], "trust": r["source"],
                 "reference": True} for r in refs]

    def pack_inputs(self, state: dict[str, Any], inv_id: str) -> tuple[ctxmod.PackInputs, list[dict[str, Any]]]:
        inv = state["invocations"][inv_id]
        if inv.get("scope") in {"observation", "parent"}:
            return self._m2_pack_inputs(state, inv_id)
        role, wid = inv["role"], inv["work_unit"]
        unit = state["work"][wid]
        role_def = roles.archetype(role)
        card = inv.get("card") or None
        record = read_record(self.k.aew_root / unit["record"], "work-unit")
        plan = unit.get("plan")
        plan_text = ""
        if plan:
            _, plan_text = parse_frontmatter((self.k.aew_root / plan["path"]).read_text(encoding="utf-8"))
        guard_path = self.k.aew_root / self.k.manifest["policy"]["guardrails"]
        checks_path = self.k.aew_root / self.k.manifest["policy"]["checks"]
        snapshot = inv["snapshot"]
        cutoff = inv.get("evidence_seq_cutoff", 0)
        evidence = [e for e in E.scan(self.k.aew_root, wid)[0] if e.get("seq", 0) <= cutoff]
        history = self._history_refs(state, inv)
        fp = snapshot["relevant_inputs_fingerprint"]
        tree = fp.split(":", 1)[1]
        base = (unit.get("integration") or {}).get("base") if inv.get("scope") == "integration" \
            else (unit.get("workspace") or {}).get("base_commit")
        on_snapshot = [e for e in evidence if e["evaluated_snapshot"]["relevant_inputs_fingerprint"] == fp]
        impl = [e for e in on_snapshot if e["kind"] == "implementation_report"]
        summary = None
        if impl:
            i = impl[-1].get("implementation") or {}
            summary = {k: i.get(k, []) for k in ("files_changed", "checks_run", "deviations", "unexpected_findings")}
        failure = None
        if role == "implementer" and unit.get("failure_evidence"):
            fe = next((e for e in evidence if e["id"] == unit["failure_evidence"]), None)
            if fe:
                failure = {"id": fe["id"], "result": fe["result"],
                           "claims": fe["verification"]["claims"],
                           "suspected_cause": fe["verification"].get("suspected_cause")}
        diff = diffstat = ""
        if base and role == "reviewer":
            diff = git.git("diff", "--no-color", "--no-renames", base, tree, "--", ".", AEW_EXCLUDE,
                           cwd=self.k.repo_root).stdout.decode("utf-8", "replace")
        if base and role == "verifier":
            diffstat = git.out("diff", "--stat", "--no-renames", base, tree, "--", ".", AEW_EXCLUDE,
                               cwd=self.k.repo_root)
        inputs = ctxmod.PackInputs(
            invocation_id=inv_id, role=role, role_def=role_def, work_id=wid, title=unit["title"],
            scope=inv.get("scope", "ticket"), specialty=inv.get("specialty"), workspace=inv["workspace"],
            snapshot=snapshot, record_meta=record.meta, record_body=record.body, plan=plan, plan_text=plan_text,
            guardrails_text=guard_path.read_text(encoding="utf-8"), checks=self.k.policy("checks")["checks"],
            authority=self.k.manifest["authority"]["accepted"], diff=diff, diffstat=diffstat,
            check_results=[{"id": e["id"], "check_id": e["check"]["check_id"], "result": e["result"],
                            "exit_code": e["check"]["exit_code"], "log": (e.get("evidence") or [{}])[0].get("path")}
                           for e in on_snapshot if e["kind"] == "check_result"],
            implementation_summary=summary,
            open_findings=[f for f in unit.get("findings", []) if f["status"] == "open"],
            failure_evidence=failure,
            card=(card or {}).get("content"),
            history=history,
            **{k: v for k, v in self._m2_pack_extras(state, inv, unit).items() if k in {"hierarchy", "inherited",
                                                                                        "inputs"}},
        )
        sources = [
            {"name": f"archetype:{role}", "path": f"aew/roles/archetypes/{role}.yaml", "sha256": None},
            {"name": f"role_card:{(card or {}).get('id')}", "path": (card or {}).get("path"),
             "sha256": (card or {}).get("sha256"), "version": (card or {}).get("version")},
            {"name": "current_ticket", "path": unit["record"], "sha256": unit["record_sha256"]},
            {"name": "accepted_plan", "path": plan["path"] if plan else None,
             "sha256": plan["sha256"] if plan else None},
            {"name": "guardrails", "path": self.k.manifest["policy"]["guardrails"], "sha256": sha256_file(guard_path)},
            {"name": "checks", "path": self.k.manifest["policy"]["checks"], "sha256": sha256_file(checks_path)},
            {"name": "snapshot", "path": None, "sha256": None, "base": base, "tree": fp},
            *[{"name": f"evidence:{e['id']}", "path": e["_path"], "sha256": e["_sha256"]} for e in on_snapshot],
            *self._history_sources(history),
        ]
        return inputs, sources

    def _m2_pack_inputs(self, state: dict[str, Any], inv_id: str) -> tuple[ctxmod.PackInputs, list[dict[str, Any]]]:
        """Packs for read-only invocations: executors of non-mutating Tickets, reviewers/verifiers of their
        records, and parent (Story/Epic) acceptance reviewers/verifiers."""
        inv = state["invocations"][inv_id]
        role, wid = inv["role"], inv["work_unit"]
        unit = state["work"][wid]
        card = inv.get("card") or None
        record = read_record(self.k.aew_root / unit["record"], "work-unit")
        plan = unit.get("plan")
        plan_text = ""
        if plan:
            _, plan_text = parse_frontmatter((self.k.aew_root / plan["path"]).read_text(encoding="utf-8"))
        guard_path = self.k.aew_root / self.k.manifest["policy"]["guardrails"]
        checks_path = self.k.aew_root / self.k.manifest["policy"]["checks"]
        extras = self._m2_pack_extras(state, inv, unit)
        history = self._history_refs(state, inv)
        inputs = ctxmod.PackInputs(
            invocation_id=inv_id, role=role, role_def=roles.archetype(role), work_id=wid, title=unit["title"],
            scope=inv.get("scope"), specialty=inv.get("specialty"), workspace=inv["workspace"],
            snapshot=inv["snapshot"], record_meta=record.meta, record_body=record.body, plan=plan, plan_text=plan_text,
            guardrails_text=guard_path.read_text(encoding="utf-8"), checks=self.k.policy("checks")["checks"],
            authority=self.k.manifest["authority"]["accepted"],
            open_findings=[f for f in unit.get("findings", []) if f["status"] == "open"],
            card=(card or {}).get("content"), history=history, **extras)
        sources = [
            {"name": f"archetype:{role}", "path": f"aew/roles/archetypes/{role}.yaml", "sha256": None},
            {"name": f"role_card:{(card or {}).get('id')}", "path": (card or {}).get("path"),
             "sha256": (card or {}).get("sha256"), "version": (card or {}).get("version")},
            {"name": "current_work", "path": unit["record"], "sha256": unit["record_sha256"]},
            {"name": "accepted_plan", "path": plan["path"] if plan else None,
             "sha256": plan["sha256"] if plan else None},
            {"name": "guardrails", "path": self.k.manifest["policy"]["guardrails"], "sha256": sha256_file(guard_path)},
            {"name": "checks", "path": self.k.manifest["policy"]["checks"], "sha256": sha256_file(checks_path)},
            {"name": "observation", "path": None, "sha256": None,
             "commit": (inv.get("observation") or {}).get("commit"),
             "tree": inv["snapshot"]["relevant_inputs_fingerprint"]},
            *[{"name": f"ancestor:{a['id']}", "path": state["work"][a["id"]]["record"],
               "sha256": state["work"][a["id"]]["record_sha256"]} for a in extras["hierarchy"]],
            *[{"name": f"input:{i['id']}", "path": None, "sha256": i["sha256"], "freshness": i["freshness"]}
              for i in extras["inputs"]],
            *([{"name": f"subject:{inv['subject']['id']}", "path": None, "sha256": inv["subject"]["sha256"]}]
              if inv.get("subject") else []),
            *[{"name": f"child:{c['id']}", "path": c.get("completion_record"), "sha256": c.get("completion_sha256")}
              for c in extras.get("children", [])],
            *self._history_sources(history),
        ]
        return inputs, sources

    def pack_rel(self, inv_id: str) -> str:
        return f"local/packs/{inv_id}/pack.md"

    def build_pack(self, ctx: TxnContext, inv_id: str) -> None:
        inv = ctx.state["invocations"][inv_id]
        inv["evidence_seq_cutoff"] = E.next_seq(self.k.aew_root, inv["work_unit"]) - 1
        refs = (ctx.state["work"].get(inv["work_unit"]) or {}).get("history_refs")
        if refs:  # pinned per invocation: a later load changes later packs only, and a regenerated pack matches
            inv["history_refs"] = [dict(r) for r in refs]
        inputs, sources = self.pack_inputs(ctx.state, inv_id)
        text = ctxmod.render(inputs)
        rel = self.pack_rel(inv_id)
        atomic_write(self.k.aew_root / rel, text)  # rebuildable local data, not control state
        inv["pack"] = {"path": rel, "sha256": sha256_text(text), "sources": sources}

    def context_pack(self, inv_id: str) -> dict[str, Any]:
        """Regenerate an invocation's pack from durable state (e.g. after local/ was deleted)."""
        state = self.k.store.read()
        if inv_id not in state["invocations"]:  # a completed invocation of archived work: its pack, regenerated (R7)
            state = self.archive.rehydrate_invocation(state, inv_id) or state
        inv = state["invocations"].get(inv_id)
        if inv is None:
            raise NotFound(f"no invocation {inv_id}")
        inputs, _ = self.pack_inputs(state, inv_id)
        text = ctxmod.render(inputs)
        rel = self.pack_rel(inv_id)
        atomic_write(self.k.aew_root / rel, text)
        recorded = (inv.get("pack") or {}).get("sha256")
        return {"ok": True, "invocation": inv_id, "path": str(self.k.aew_root / rel), "sha256": sha256_text(text),
                "matches_recorded": recorded == sha256_text(text)}

    def context_show(self, inv_id: str) -> str:
        path = self.k.aew_root / self.pack_rel(inv_id)
        if not path.exists():
            self.context_pack(inv_id)
        return path.read_text(encoding="utf-8")
