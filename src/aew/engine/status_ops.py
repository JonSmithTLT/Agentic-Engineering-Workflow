"""Read-only projections: ``aew status`` (WC §8.3, KC §18)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine.base import EngineBase
from aew.errors import NotFound
from aew.knowledge.render import work_graph_lines
from aew.util import sha256_file


class StatusOps(EngineBase):
    def contradictions(self, state: dict[str, Any]) -> list[str]:
        """Detected inconsistencies the Lead must resolve rather than silently pick a side (KC §15.1)."""
        found = []
        if not self.manifest_pin_ok(state):
            found.append("project.yaml does not match its pinned hash (modified outside AEW)")
        for wid, unit in sorted(state["work"].items()):
            record = self.aew_root / unit["record"]
            if sha256_file(record) != unit["record_sha256"]:
                found.append(f"{wid}: record {unit['record']} was modified or removed outside AEW")
            plan = unit.get("plan") or {}
            if plan.get("accepted"):
                if sha256_file(self.aew_root / plan["path"]) != plan["sha256"]:
                    found.append(f"{wid}: accepted plan v{plan['accepted']} was modified outside AEW")
            ws = unit.get("workspace")
            if ws and unit["state"] not in {"DONE", "CANCELLED"} and ws.get("status") == "active":
                if not Path(ws["path"]).exists():
                    found.append(f"{wid}: workspace {ws['id']} is missing at {ws['path']}")
        for inv_id, inv in sorted(state["invocations"].items()):
            if inv["status"] == "active" and state["lead"]["status"] == "vacant":
                found.append(f"{inv_id}: active invocation but no Lead holds authority")
        return found

    def status(self, work_id: str | None = None) -> dict[str, Any]:
        state = self.store.read()
        if work_id:
            unit = state["work"].get(work_id)
            if unit is None:
                raise NotFound(f"no work unit {work_id}")
            return {"revision": state["revision"], "work_unit": dict(unit, id=work_id)}
        lead = state["lead"]
        return {
            "project": {"id": self.project_id, "name": self.manifest["project"]["name"]},
            "revision": state["revision"],
            "lead": {"status": lead["status"], "generation": lead["generation"],
                     "session_label": lead.get("session_label")},
            "work_graph": work_graph_lines(state),
            "work": {wid: {"state": u["state"], "kind": u["kind"], "title": u["title"],
                           "blocked_by": u.get("blocked_by", [])}
                     for wid, u in sorted(state["work"].items())},
            "active_invocations": sorted(i for i, inv in state["invocations"].items() if inv["status"] == "active"),
            "next_actions": self.next_actions(state),
            "contradictions": self.contradictions(state),
        }

    def next_actions(self, state: dict[str, Any]) -> list[str]:
        return []

    def render_status(self, report: dict[str, Any]) -> str:
        if "work_unit" in report:
            unit = report["work_unit"]
            return "\n".join(f"{k}: {v}" for k, v in unit.items())
        lead = report["lead"]
        lines = [
            f"Project: {report['project']['name']} ({report['project']['id']})",
            f"Control revision: {report['revision']}",
            f"Lead authority: {lead['status']} (generation {lead['generation']}"
            + (f", {lead['session_label']}" if lead.get("session_label") else "") + ")",
            "",
            *report["work_graph"],
        ]
        if report["next_actions"]:
            lines += ["", "Next actions", *(f"  {a}" for a in report["next_actions"])]
        if report["contradictions"]:
            lines += ["", "CONTRADICTIONS (resolve before proceeding)", *(f"  ! {c}" for c in report["contradictions"])]
        return "\n".join(lines)
