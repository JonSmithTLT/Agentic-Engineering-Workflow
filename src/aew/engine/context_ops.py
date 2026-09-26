"""Context-pack assembly for invocations (WC §15.4; KC §15). Packs are rebuildable local data."""

from __future__ import annotations

from typing import Any

from aew import roles
from aew.engine.base import TxnContext
from aew.engine.evidence_ops import EvidenceOps
from aew.errors import NotFound
from aew.knowledge import context as ctxmod
from aew.knowledge import evidence as E
from aew.knowledge.records import read_record
from aew.util import atomic_write, parse_frontmatter, sha256_file, sha256_text
from aew.workspace import git

AEW_EXCLUDE = ":(exclude).aew"


class ContextOps(EvidenceOps):
    def _pack_inputs(self, state: dict[str, Any], inv_id: str) -> tuple[ctxmod.PackInputs, list[dict[str, Any]]]:
        inv = state["invocations"][inv_id]
        role, wid = inv["role"], inv["work_unit"]
        unit = state["work"][wid]
        role_def = roles.archetype(role)
        card = inv.get("card") or None
        record = read_record(self.aew_root / unit["record"], "work-unit")
        plan = unit.get("plan")
        plan_text = ""
        if plan:
            _, plan_text = parse_frontmatter((self.aew_root / plan["path"]).read_text(encoding="utf-8"))
        guard_path = self.aew_root / self.manifest["policy"]["guardrails"]
        checks_path = self.aew_root / self.manifest["policy"]["checks"]
        snapshot = inv["snapshot"]
        cutoff = inv.get("evidence_seq_cutoff", 0)
        evidence = [e for e in E.scan(self.aew_root, wid)[0] if e.get("seq", 0) <= cutoff]
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
                           cwd=self.repo_root).stdout.decode("utf-8", "replace")
        if base and role == "verifier":
            diffstat = git.out("diff", "--stat", "--no-renames", base, tree, "--", ".", AEW_EXCLUDE, cwd=self.repo_root)
        inputs = ctxmod.PackInputs(
            invocation_id=inv_id, role=role, role_def=role_def, work_id=wid, title=unit["title"],
            scope=inv.get("scope", "ticket"), specialty=inv.get("specialty"), workspace=inv["workspace"],
            snapshot=snapshot, record_meta=record.meta, record_body=record.body, plan=plan, plan_text=plan_text,
            guardrails_text=guard_path.read_text(encoding="utf-8"), checks=self.policy("checks")["checks"],
            authority=self.manifest["authority"]["accepted"], diff=diff, diffstat=diffstat,
            check_results=[{"id": e["id"], "check_id": e["check"]["check_id"], "result": e["result"],
                            "exit_code": e["check"]["exit_code"], "log": (e.get("evidence") or [{}])[0].get("path")}
                           for e in on_snapshot if e["kind"] == "check_result"],
            implementation_summary=summary,
            open_findings=[f for f in unit.get("findings", []) if f["status"] == "open"],
            failure_evidence=failure,
            card=(card or {}).get("content"),
        )
        sources = [
            {"name": f"archetype:{role}", "path": f"aew/roles/archetypes/{role}.yaml", "sha256": None},
            {"name": f"role_card:{(card or {}).get('id')}", "path": (card or {}).get("path"),
             "sha256": (card or {}).get("sha256"), "version": (card or {}).get("version")},
            {"name": "current_ticket", "path": unit["record"], "sha256": unit["record_sha256"]},
            {"name": "accepted_plan", "path": plan["path"] if plan else None, "sha256": plan["sha256"] if plan else None},
            {"name": "guardrails", "path": self.manifest["policy"]["guardrails"], "sha256": sha256_file(guard_path)},
            {"name": "checks", "path": self.manifest["policy"]["checks"], "sha256": sha256_file(checks_path)},
            {"name": "snapshot", "path": None, "sha256": None, "base": base, "tree": fp},
            *[{"name": f"evidence:{e['id']}", "path": e["_path"], "sha256": e["_sha256"]} for e in on_snapshot],
        ]
        return inputs, sources

    def _pack_rel(self, inv_id: str) -> str:
        return f"local/packs/{inv_id}/pack.md"

    def build_pack(self, ctx: TxnContext, inv_id: str) -> None:
        inv = ctx.state["invocations"][inv_id]
        inv["evidence_seq_cutoff"] = E.next_seq(self.aew_root, inv["work_unit"]) - 1
        inputs, sources = self._pack_inputs(ctx.state, inv_id)
        text = ctxmod.render(inputs)
        rel = self._pack_rel(inv_id)
        atomic_write(self.aew_root / rel, text)  # rebuildable local data, not control state
        inv["pack"] = {"path": rel, "sha256": sha256_text(text), "sources": sources}

    def context_pack(self, inv_id: str) -> dict[str, Any]:
        """Regenerate an invocation's pack from durable state (e.g. after local/ was deleted)."""
        state = self.store.read()
        inv = state["invocations"].get(inv_id)
        if inv is None:
            raise NotFound(f"no invocation {inv_id}")
        inputs, _ = self._pack_inputs(state, inv_id)
        text = ctxmod.render(inputs)
        rel = self._pack_rel(inv_id)
        atomic_write(self.aew_root / rel, text)
        recorded = (inv.get("pack") or {}).get("sha256")
        return {"ok": True, "invocation": inv_id, "path": str(self.aew_root / rel), "sha256": sha256_text(text),
                "matches_recorded": recorded == sha256_text(text)}

    def context_show(self, inv_id: str) -> str:
        path = self.aew_root / self._pack_rel(inv_id)
        if not path.exists():
            self.context_pack(inv_id)
        return path.read_text(encoding="utf-8")
