"""Durable records: Epic/Story/Ticket, plan revisions, decisions (Markdown + YAML frontmatter).

Records are descriptive and immutable once referenced by committed control state;
the engine pins each one's sha256. Mutable control fields (state, current risk
class, accepted-plan pointer) live only in control state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew.schemas import validate
from aew.util import parse_frontmatter, render_frontmatter

KIND_PREFIX = {"ticket": "T", "story": "S", "epic": "E"}


@dataclass(frozen=True)
class Record:
    meta: dict[str, Any]
    body: str

    def render(self) -> str:
        return render_frontmatter(self.meta, self.body)


def format_id(prefix: str, number: int) -> str:
    return f"{prefix}-{number:04d}"


def work_unit_record(
    *,
    unit_id: str,
    kind: str,
    title: str,
    created_at: str,
    created_by: dict[str, Any],
    risk_class: int,
    mutating: bool,
    parent: str | None = None,
    scope_paths: list[str] | None = None,
    goal_backwards: list[str] | None = None,
    contract: list[str] | None = None,
    policy: dict[str, Any] | None = None,
    external_refs: list[str] | None = None,
    body: str = "",
    promoted_from: str | None = None,
) -> Record:
    meta: dict[str, Any] = {
        "schema": "aew/work-unit/v1",
        "id": unit_id,
        "kind": kind,
        "title": title,
        "parent": parent,
        "external_refs": list(external_refs or []),
        "created_at": created_at,
        "created_by": created_by,
        "initial_risk_class": risk_class,
        "mutating": mutating,
        "scope": {"paths": list(scope_paths or [])},
        "acceptance": {"goal_backwards": list(goal_backwards or []), "contract": list(contract or [])},
    }
    if policy:
        meta["policy"] = policy
    if promoted_from:
        meta["promoted_from"] = promoted_from
    validate("work-unit", meta, source=unit_id)
    return Record(meta, body)


def plan_record(
    *,
    work_unit: str,
    revision: int,
    created_at: str,
    author: dict[str, Any],
    body: str,
    supersedes: int | None = None,
    reason: str | None = None,
    affected_paths: list[str] | None = None,
    source_evidence: dict[str, Any] | None = None,
    assurance: dict[str, list[str]] | None = None,
) -> Record:
    meta = {
        "schema": "aew/plan/v1",
        "work_unit": work_unit,
        "revision": revision,
        "supersedes": supersedes,
        "reason": reason,
        "created_at": created_at,
        "author": author,
        "affected_paths": list(affected_paths or []),
    }
    if source_evidence:
        meta["source_evidence"] = source_evidence
    if assurance is not None:
        meta["assurance"] = assurance
    validate("plan", meta, source=f"{work_unit} plan v{revision}")
    return Record(meta, body)


def decision_record(
    *,
    decision_id: str,
    decision_type: str,
    decided_by: dict[str, Any],
    at: str,
    summary: str,
    work_unit: str | None = None,
    classification: str | None = None,
    evidence_refs: list[str] | None = None,
    resulting_transition: dict[str, Any] | None = None,
    reason: str | None = None,
    body: str = "",
) -> Record:
    meta = {
        "schema": "aew/decision/v1",
        "id": decision_id,
        "type": decision_type,
        "work_unit": work_unit,
        "decided_by": decided_by,
        "at": at,
        "summary": summary,
        "classification": classification,
        "evidence_refs": list(evidence_refs or []),
        "resulting_transition": resulting_transition,
        "reason": reason,
    }
    validate("decision", meta, source=decision_id)
    return Record(meta, body)


def read_record(path: Path, schema: str) -> Record:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"), source=str(path))
    validate(schema, meta, source=str(path))
    return Record(meta, body)
