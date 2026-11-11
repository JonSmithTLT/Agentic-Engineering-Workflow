"""Subjects shown for approvals and compared by their committing transactions."""
from __future__ import annotations

import json
from typing import Any

from aew.errors import ApprovalSubjectChanged
from aew.util import sha256_text


def digest(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def compare(op: str, subject: str, expected: str | None, current: str | None, *,
            next_step: str = "Read the subject again and decide anew.", **details: Any) -> None:
    if expected != current:
        raise ApprovalSubjectChanged(
            f"{op}: {subject} changed since approval (expected {expected}, current {current}). {next_step}",
            op=op, subject=subject, expected=expected, current=current, next_step=next_step, **details,
        )


def execution_record_digest(record: dict[str, Any]) -> str:
    return digest({"id": record["id"], "sha256": record["sha256"]})


def closeout_digest(snapshot: dict[str, Any]) -> str:
    return digest({"children_digest": snapshot["children_digest"], "base_revision": snapshot["base_revision"]})


def cascade_digest(work_id: str, descendants: list[str]) -> str:
    return digest({"parent": work_id, "descendants": sorted(descendants)})


def input_subject(evidence_id: str, sha256: str, commit: str | None) -> dict[str, Any]:
    value = {"evidence": evidence_id, "sha256": sha256, "commit": commit}
    return {"subject": value, "digest": digest(value)}


def failure_digest(unit: dict[str, Any], evidence_id: str | None) -> str:
    sha = next((r["sha256"] for r in unit.get("evidence", []) if r["id"] == evidence_id), None)
    return digest({"id": evidence_id, "sha256": sha})


def failure_ref(op: str, unit: dict[str, Any], evidence_id: str | None, binding: str | None) -> str | None:
    if binding is None:
        return evidence_id
    compare(op, evidence_id or "verification failure", binding, failure_digest(unit, evidence_id))
    return f"{evidence_id}@record:{binding}"


def gate_digest(context: dict[str, Any], gate: str) -> str:
    return digest({"gate": gate, "snapshot": context["snapshot"], "obligations": context["obligations"],
                   "result": context["gates"].get(gate)})


def command(op: str, work_id: str, revision: int, binding: str, *options: str) -> list[str]:
    """The relay arguments carry the digest from the same read as the revision."""
    route = {"input.acknowledge": "work acknowledge-input", "waive": "gate waive"}.get(op, op.replace(".", " "))
    return [*route.split(), work_id, *options, "--expect-rev", str(revision), "--approval-digest", binding]
