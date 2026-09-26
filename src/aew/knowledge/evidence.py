"""Engineering evidence records (WC §9.7-9.9; KC §7.3, §11).

Evidence is immutable and attributable: what / who / when / against / how /
result / evidence. The producing role owns the *content*; the engine owns the
binding fields (identity, producer, evaluated snapshot, plan revision, time,
sequence) and never takes them from the submitter. Each record carries an
``integrity`` hash over its content so edits after creation are detected.
Staleness is computed at gate evaluation and never written back: historical
evidence stays byte-identical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.errors import IntegrityError, PermissionDenied, ValidationFailed
from aew.schemas import validate
from aew.util import parse_frontmatter, render_frontmatter, sha256_file, sha256_text

ROLE_KINDS = {
    "implementer": {"implementation_report"},
    "reviewer": {"review"},
    "verifier": {"verification"},
}
SHORT = {"implementation_report": "impl", "review": "review", "verification": "verify", "check_result": "check"}

# Fields the engine owns. A submission containing any of them is rejected rather than
# silently overwritten, so forged bindings or control decisions are visible failures.
ENGINE_OWNED = {"schema", "id", "kind", "work_unit", "created_at", "evaluated_snapshot", "plan_revision",
                "seq", "integrity", "sealed_by"}
# Reserved for per-card output contracts (ADR-0006, post-M1): a card-declared contract name and a
# payload validated against that contract's schema. Rejected until contracts are implemented.
RESERVED_FOR_CONTRACTS = {"contract", "payload"}
CONTROL_FIELDS = {"state", "next_state", "transition", "classification", "remediation", "decision",
                  "waiver", "waivers", "lead", "accepted_plan", "completion"}
SUBMITTER_KEYS = {
    "implementation_report": {"claim", "result", "producer", "method", "evidence", "implementation"},
    "review": {"claim", "producer", "method", "evidence", "review"},
    "verification": {"claim", "producer", "method", "evidence", "verification"},
}


def evidence_dir(aew_root: Path, work_id: str) -> Path:
    return aew_root / "evidence" / work_id


def seal(meta: dict[str, Any], body: str) -> str:
    meta = {k: v for k, v in meta.items() if k != "integrity"}
    meta["sealed_by"] = "aew-engine"
    meta["integrity"] = sha256_text(render_frontmatter(meta, body))
    validate("evidence", meta, source=meta["id"])
    return render_frontmatter(meta, body)


def read(path: Path) -> tuple[dict[str, Any], str]:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"), source=str(path))
    validate("evidence", meta, source=str(path))
    claimed = meta.get("integrity")
    unsealed = {k: v for k, v in meta.items() if k != "integrity"}
    if not claimed or sha256_text(render_frontmatter(unsealed, body)) != claimed:
        raise IntegrityError(f"evidence {path.name} was modified after it was recorded")
    return meta, body


def scan(aew_root: Path, work_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """All sealed evidence for a work unit in recording order, plus integrity problems found."""
    directory = evidence_dir(aew_root, work_id)
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    if not directory.is_dir():
        return records, problems
    for path in sorted(directory.glob("*.md")):
        try:
            meta, _ = read(path)
        except (IntegrityError, ValidationFailed) as exc:
            problems.append(f"{path.name}: {exc.message}")
            continue
        meta["_path"] = str(path.relative_to(aew_root)).replace("\\", "/")
        meta["_sha256"] = sha256_file(path)
        records.append(meta)
    records.sort(key=lambda m: m.get("seq", 0))
    return records, problems


def next_seq(aew_root: Path, work_id: str) -> int:
    directory = evidence_dir(aew_root, work_id)
    return 1 + (len(list(directory.glob("*.md"))) if directory.is_dir() else 0)


def check_submission(role: str, kind: str, meta: dict[str, Any]) -> None:
    if kind not in ROLE_KINDS.get(role, set()):
        raise PermissionDenied(f"role {role} may not submit {kind} evidence", role=role, kind=kind)
    control = sorted(CONTROL_FIELDS & meta.keys())
    if control:
        raise PermissionDenied(
            "evidence may not carry control decisions; the Lead owns state transitions and "
            "verification-failure classification", fields=control)
    owned = sorted(ENGINE_OWNED & meta.keys())
    if owned:
        raise ValidationFailed("these fields are recorded by the engine and may not be supplied", fields=owned)
    reserved = sorted(RESERVED_FOR_CONTRACTS & meta.keys())
    if reserved:
        raise ValidationFailed("per-card output contracts are not implemented yet (reserved fields)", fields=reserved)
    unknown = sorted(meta.keys() - SUBMITTER_KEYS[kind])
    if unknown:
        raise ValidationFailed(f"unexpected fields for {kind}", fields=unknown)
    producer = meta.get("producer") or {}
    if set(producer) - {"model", "provider", "harness"}:
        raise ValidationFailed("producer may only declare model, provider and harness")
