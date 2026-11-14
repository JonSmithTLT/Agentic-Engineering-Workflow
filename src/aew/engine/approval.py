"""Subjects shown for approvals and compared by their committing transactions."""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew.errors import ChangedSinceRead
from aew.util import sha256_text


def digest(value: Any) -> str:
    return sha256_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def prior(op: str, subject: str, field: str, expected: str | None, current: str, *,
          root: Path, state: dict[str, Any], event: Callable[[dict[str, Any]], bool] | None = None,
          record: str | None = None) -> None:
    if expected is None or expected == current:
        return
    if record is None and event is not None:
        from aew.engine.outbox import LogView

        since = (state.get("outbox") or {}).get("since")
        if since is not None:
            log = LogView(root, since)
            for revision in range(state["revision"], since - 1, -1):
                if any(event(row) for row in log.events(log.record(revision)) or ()):
                    record = f"control revision {revision}"
                    break
    refuse_change(op, subject, field, expected, current, changed_by=record,
                  next_step="Read the current value before deciding whether to try again.")


def parent_value(unit: dict[str, Any]) -> str:
    return unit.get("parent") or "none"


def promotion_value(unit: dict[str, Any]) -> str:
    return f"{unit['kind']}:{parent_value(unit)}"


def run_value(invocation: dict[str, Any]) -> str:
    runs = invocation.get("runs") or []
    return runs[-1]["run"] if runs else "none"


def override_value(state: dict[str, Any]) -> str:
    return ((state.get("steering") or {}).get("override") or {}).get("record") or "none"


def role_plan_digest(unit: dict[str, Any]) -> str:
    plan = unit.get("role_plan") or {}
    return digest({slot: plan.get(slot, []) for slot in ("execute", "review", "verify", "forbidden")})


def bound_argv(argv: tuple[str, ...], revision: int, value: str) -> list[str]:
    return [*argv, "--expect-rev", str(revision), "--prior-value", value]


def refuse_change(op: str, subject: str, field: str, expected: Any, current: Any, *,
                  changed_by: Any = None, next_step: str, **details: Any) -> None:
    change = f" Changed by {changed_by}." if changed_by is not None else ""
    raise ChangedSinceRead(
        f"{op}: {subject}'s {field} changed since read (expected {expected}, current {current}).{change} {next_step}",
        op=op, subject=subject, field=field, expected=expected, current=current,
        changed_by=changed_by, next_step=next_step, **details,
    )


def compare(op: str, subject: str, expected: str | None, current: str | None, *,
            next_step: str = "Read the subject again and decide anew.", **details: Any) -> None:
    if expected != current:
        refuse_change(op, subject, "approval subject", expected, current, next_step=next_step, **details)


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
