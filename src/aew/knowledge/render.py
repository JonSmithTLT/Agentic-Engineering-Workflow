"""Derived human-readable projections of committed control state.

``state/CURRENT.md`` (KC §8.7) and ``state/HANDOFF.md`` (KC §8.8) are rendered
from control state after every commit. They are views, never authorities; the
work graph in control state is the canonical to-do source (WC §8.3, KC §18).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

GROUPS = [
    ("NOW", {"ASSIGNED", "RUNNING"}),
    ("REVIEW", {"REVIEW_PENDING", "REVIEW_FAILED", "REVIEW_PASSED"}),
    ("VERIFY", {"VERIFY_PENDING", "VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE", "VERIFIED"}),
    ("INTEGRATION", {"COMMIT_READY"}),
    ("READY", {"READY"}),
    ("BLOCKED", {"BLOCKED"}),
    ("ATTENTION", {"INTERRUPTED", "REPLAN_REQUIRED", "ESCALATED"}),
    ("DONE", {"DONE"}),
    ("CANCELLED", {"CANCELLED"}),
]


def _blocker_text(unit: dict[str, Any]) -> str:
    parts = []
    for b in unit.get("blocked_by") or []:
        if b.get("kind") == "dependency":
            parts.append(f"{b['id']} ({b['reason']}" + (f", via {b['inherited_from']}" if b.get("inherited_from") else "")
                         + ")")
        else:
            parts.append(b.get("kind", "?"))
    return " -> " + ", ".join(parts) if parts else ""


def work_graph_lines(state: dict[str, Any]) -> list[str]:
    tickets = {k: v for k, v in state["work"].items() if v["kind"] == "ticket"}
    lines: list[str] = []
    for title, states in GROUPS:
        members = sorted(k for k, v in tickets.items() if v["state"] in states)
        if not members:
            continue
        lines.append(title)
        for wid in members:
            unit = tickets[wid]
            extra = ""
            ws = unit.get("workspace")
            if ws and unit["state"] in {"ASSIGNED", "RUNNING"}:
                extra = f" @ {ws['id']}"
            if unit["state"] == "BLOCKED":
                extra = _blocker_text(unit)
            label = unit["state"] if title not in {"READY", "BLOCKED", "DONE"} else ""
            lines.append(f"  {wid} {label}{extra}  {unit['title']}".replace("  ", " ", 1).rstrip())
    return lines or ["(no Tickets)"]


def render_current(state: dict[str, Any], project_name: str) -> str:
    lead = state["lead"]
    lines = [
        f"# CURRENT — {project_name}",
        "",
        f"<!-- generated from state/control.yaml revision {state['revision']}; do not edit -->",
        "",
        f"- Control revision: {state['revision']}",
        f"- Lead authority: {lead['status']} (generation {lead['generation']}"
        + (f", session {lead['session_label']}" if lead.get("session_label") else "")
        + ")",
    ]
    active = [
        (wid, u) for wid, u in sorted(state["work"].items())
        if u["kind"] == "ticket" and u["state"] not in {"DONE", "CANCELLED", "BLOCKED", "READY"}
    ]
    if active:
        lines.append("- Active work:")
        for wid, u in active:
            plan = u.get("plan") or {}
            lines.append(
                f"  - {wid} [{u['state']}] class {u['risk_class']}, plan "
                f"{('v' + str(plan['accepted'])) if plan.get('accepted') else 'not accepted'}: {u['title']}"
            )
    parents = [(wid, u) for wid, u in sorted(state["work"].items())
               if u["kind"] != "ticket" and u["state"] not in {"DONE", "CANCELLED"}]
    if parents:
        lines.append("- Active Epics/Stories:")
        for wid, u in parents:
            attention = f" — attention: {'; '.join(u['attention'])}" if u.get("attention") else ""
            lines.append(f"  - {wid} [{u['state']}] {u['kind']}: {u['title']}{attention}")
    finished = finished_summary(state)
    if finished:
        lines.append(f"- Finished work (archived): {finished['done']} done, {finished['cancelled']} cancelled; "
                     f"the full history: `{finished['history']}`")
        for r in finished["recent"]:
            lines.append(f"  - {r['id']} [{r['state']}] {r['kind']}: {r['title']}")
    if state.get("next_action"):
        lines.append(f"- Lead's next action: {state['next_action']}")
    lines += ["", "## Work graph", "", "```text", *work_graph_lines(state), "```", ""]
    return "\n".join(lines)


def finished_summary(state: dict[str, Any]) -> dict[str, Any] | None:
    """Archived work, bounded (ADR-0011; operator 2026-10-01): counts, the most recent units, the history path."""
    counts = (state.get("cold") or {}).get("archived") or {}
    if not (counts.get("done") or counts.get("cancelled")):
        return None
    recent = [r for r in state.get("recent", []) if r["id"] not in state["work"]]
    return {"done": counts.get("done", 0), "cancelled": counts.get("cancelled", 0), "recent": recent[::-1],
            "history": "aew history list"}


def views(state: dict[str, Any], project_name: str, aew_root: Path) -> dict[str, str]:
    out = {"state/CURRENT.md": render_current(state, project_name)}
    latest = state.get("latest_handoff")
    if latest:
        record = aew_root / latest
        if record.exists():
            text = record.read_text(encoding="utf-8")
            out["state/HANDOFF.md"] = (
                f"<!-- generated copy of {latest} (control revision {state['revision']}); do not edit -->\n"
                + text
            )
    return out
