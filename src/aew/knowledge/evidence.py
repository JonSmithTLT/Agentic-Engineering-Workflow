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
from typing import Any, cast

from aew import profile
from aew.errors import IntegrityError, PermissionDenied, ValidationFailed
from aew.schemas import validate, validate_property
from aew.util import parse_frontmatter, render_frontmatter, sha256_file, sha256_text

# E160 (SYS-43; the designer's decision of 2026-11-06 on planner staffing and the plan assessor, Q2): the plan
# assessment, a record kind of the reviewer archetype that challenges an accepted plan revision: a requirement trace,
# the premises challenged, and findings. The schema holds its producer to this archetype. Only an invocation the
# assessor entrypoint (`aew plan assess`, E160 slice 2) dispatched submits one: its scope is ``ASSESSMENT_SCOPE``, and
# a reviewer dispatched to review a change never may (``kinds_for``). The entrypoint's default card is
# ``ASSESSOR_CARD``; any card of the archetype that lists the kind among its outputs may be named instead.
PLAN_ASSESSMENT = "plan_assessment"
ASSESSOR_ARCHETYPE = "reviewer"
ASSESSMENT_SCOPE = "plan_assessment"
ASSESSOR_CARD = "plan_assessor"
# The invocation scopes that hold their own read-only observation of the source (ADR-0008): a non-mutating Ticket's
# executor and its reviewers and verifiers, a parent's acceptance roles, and a plan assessor.
OBSERVER_SCOPES = frozenset({"observation", "parent", ASSESSMENT_SCOPE})

ROLE_KINDS = {
    "implementer": {"implementation_report"},
    "reviewer": {"review", PLAN_ASSESSMENT},  # a plan assessment only at its own scope (``kinds_for``)
    "verifier": {"verification"},
    # Non-mutating execute records (ADR-0008): each read-only archetype writes exactly one kind.
    "investigator": {"discovery_record"},
    "researcher": {"research_record"},
    "planner": {"plan_proposal"},
}
# The record a non-mutating executor of each archetype must produce (the pinned output contract).
EXECUTE_KIND = {"investigator": "discovery_record", "researcher": "research_record", "planner": "plan_proposal"}
EXECUTE_KINDS = frozenset(EXECUTE_KIND.values())
SHORT = {"implementation_report": "impl", "review": "review", "verification": "verify", "check_result": "check",
         "discovery_record": "discovery", "research_record": "research", "plan_proposal": "proposal",
         PLAN_ASSESSMENT: "assess"}

# Fields the engine owns. A submission containing any of them is rejected rather than
# silently overwritten, so forged bindings or control decisions are visible failures.
ENGINE_OWNED = {"schema", "id", "kind", "work_unit", "created_at", "evaluated_snapshot", "plan_revision",
                "seq", "integrity", "sealed_by", "attempt", "subject",
                "coordination_inputs"}  # the Lead messages it had (F9-A plan D-35)
# Producer fields the engine records from control state (ADR-0010): identity, the pinned execution, and
# the credential and harness run that presented the submission. A submitter may only *declare* the rest.
ENGINE_OWNED_PRODUCER = {"kind", "role", "invocation", "role_card", "execution_profile", "run", "credential",
                         "validation_run"}
DECLARED_PRODUCER = {"model", "provider", "harness"}
# Reserved for per-card output contracts (ADR-0006, post-M1): a card-declared contract name and a
# payload validated against that contract's schema. Rejected until contracts are implemented.
RESERVED_FOR_CONTRACTS = {"contract", "payload"}
CONTROL_FIELDS = {"state", "next_state", "transition", "classification", "remediation", "decision",
                  "waiver", "waivers", "lead", "accepted_plan", "completion"}
SUBMITTER_KEYS = {
    "implementation_report": {"claim", "result", "producer", "method", "evidence", "implementation"},
    "review": {"claim", "producer", "method", "evidence", "review"},
    "verification": {"claim", "producer", "method", "evidence", "verification"},
    "discovery_record": {"claim", "result", "producer", "method", "evidence", "discovery"},
    "research_record": {"claim", "result", "producer", "method", "evidence", "research"},
    "plan_proposal": {"claim", "result", "producer", "method", "evidence", "proposal"},
    # No ``result``: the engine derives it from the findings, as it does a review's.
    PLAN_ASSESSMENT: {"claim", "producer", "method", "evidence", "assessment"},
}


def plan_binding(plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """The ``plan_revision`` binding every record carries: the unit's accepted plan revision and its sha256, or None
    while it has none. The one owner of its shape: records are bound with it and compared against it."""
    return {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None


def evidence_dir(aew_root: Path, work_id: str) -> Path:
    return aew_root / "evidence" / work_id


def seal(meta: dict[str, Any], body: str) -> str:
    meta = {k: v for k, v in meta.items() if k != "integrity"}
    meta["sealed_by"] = "aew-engine"
    meta["integrity"] = sha256_text(render_frontmatter(meta, body))
    validate("evidence", meta, source=meta["id"])
    return render_frontmatter(meta, body)


def read(path: Path) -> tuple[dict[str, Any], str]:
    return parse_sealed(path.read_text(encoding="utf-8"), str(path), path.name)


def parse_sealed(text: str, source: str, name: str | None = None) -> tuple[dict[str, Any], str]:
    """A sealed evidence record's metadata and body: schema-valid, and its integrity seal still over its content."""
    meta, body = parse_frontmatter(text, source=source)
    validate("evidence", meta, source=source)
    claimed = meta.get("integrity")
    unsealed = {k: v for k, v in meta.items() if k != "integrity"}
    if not claimed or sha256_text(render_frontmatter(unsealed, body)) != claimed:
        raise IntegrityError(f"evidence {name or source} was modified after it was recorded")
    return meta, body


def scan(aew_root: Path, work_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """All sealed evidence for a work unit in recording order, plus integrity problems found."""
    profile.count("scan")
    with profile.phase("scan"):
        return _scan(aew_root, work_id)


def _scan(aew_root: Path, work_id: str) -> tuple[list[dict[str, Any]], list[str]]:
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
    profile.count("scan_files", len(records) + len(problems))
    records.sort(key=lambda m: m.get("seq", 0))
    return records, problems


def next_seq(aew_root: Path, work_id: str) -> int:
    directory = evidence_dir(aew_root, work_id)
    return 1 + (len(list(directory.glob("*.md"))) if directory.is_dir() else 0)


# What a submitted report's `result` may be, narrower than the schema's enum, with what a value means where it needs
# saying. The refusals and the packs' report formats both read these.
IMPLEMENTATION_RESULTS: dict[str, str | None] = {"pass": "complete", "blocked": None}
RECORD_RESULTS: dict[str, str | None] = {"pass": "the question is answered", "blocked": None, "inconclusive": None}


def one_of(values: dict[str, str | None]) -> str:
    """``pass (complete) or blocked``: a report field's allowed values, in prose."""
    words = [f"{value} ({means})" if means else value for value, means in values.items()]
    return ", ".join(words[:-1]) + " or " + words[-1]


def kinds_for(role: str, scope: str | None) -> set[str]:
    """The evidence kinds an invocation of ``role`` dispatched at ``scope`` may submit: its archetype's, where a plan
    assessment belongs to the assessor's scope alone. So a plan-assessor dispatch submits a plan assessment and nothing
    else, and a reviewer of a change never submits one (E160 slice 2). The one owner of what a run is expected to
    produce, too (``harness_ops.expected_kinds``)."""
    kinds = set(ROLE_KINDS.get(role, set()))
    if role == ASSESSOR_ARCHETYPE and scope == ASSESSMENT_SCOPE:
        return kinds & {PLAN_ASSESSMENT}
    return kinds - {PLAN_ASSESSMENT}


def check_submission(role: str, kind: str, meta: dict[str, Any], *, scope: str | None = None) -> None:
    if kind not in ROLE_KINDS.get(role, set()):
        raise PermissionDenied(f"role {role} may not submit {kind} evidence", role=role, kind=kind)
    if kind not in kinds_for(role, scope):
        if kind == PLAN_ASSESSMENT:
            raise PermissionDenied(
                "only an invocation dispatched to assess the accepted plan may submit a plan assessment; this one was "
                f"dispatched at scope {scope!r}. A plan assessor is dispatched with the plan assess command, never as "
                "a reviewer of a change",
                reason="not_a_plan_assessment_dispatch", role=role, kind=kind, scope=scope)
        raise PermissionDenied(
            f"this invocation was dispatched to assess the accepted plan: it submits a {PLAN_ASSESSMENT} "
            f"(`aew submit --kind {PLAN_ASSESSMENT} --file <file>`), not {kind} evidence",
            reason="plan_assessment_dispatch", role=role, kind=kind, scope=scope)
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
    owned = sorted(ENGINE_OWNED_PRODUCER & set(producer))
    if owned:
        raise ValidationFailed("these producer fields are recorded by the engine and may not be supplied",
                               fields=[f"producer.{k}" for k in owned])
    if set(producer) - DECLARED_PRODUCER:
        raise ValidationFailed("producer may only declare model, provider and harness")


def plan_assessment_binding(work_id: str, plan: dict[str, Any] | None, submitted: dict[str, Any]) -> dict[str, Any]:
    """The engine's part of a plan assessment of ``work_id``, whose accepted plan is ``plan``: the submitted
    ``assessment`` checked, its blocker and major findings made required, and the ``result`` they give. The
    ``plan_revision`` binding is the one every record carries (``plan_binding``), set by the submission path; the schema
    refuses a plan assessment without it. E160 slice 2's submission path calls this, as it does the review checks.

    Refused, with ``reason`` in the details: no accepted plan (``no_accepted_plan``: there is nothing to assess), a
    finding id used twice (``duplicate_finding``), and a gap left silent (``gap_without_finding``): a requirement the
    plan covers only in part or not at all, or a premise that fails, must cite a finding of this assessment."""
    if plan_binding(plan) is None:
        raise ValidationFailed(f"{work_id} has no accepted plan revision to assess; a plan assessment challenges the "
                               "accepted revision, so accept a plan first", reason="no_accepted_plan", work_id=work_id)
    raw = submitted.get("assessment")
    # ``required`` defaults as a review's does, before the shape is checked; findings that are missing or not a list
    # reach the schema as they are, and are refused there.
    if isinstance(raw, dict) and isinstance(raw.get("findings"), list):
        raw = {**raw, "findings": [{"required": False, **f} if isinstance(f, dict) else f for f in raw["findings"]]}
    validate_property("evidence", "assessment", raw, source="submission")
    assessment = cast(dict[str, Any], raw)  # the schema requires an object; it is already a fresh copy
    ids = [f["id"] for f in assessment["findings"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValidationFailed(f"finding id(s) {', '.join(duplicates)} are used more than once; give each finding its "
                               "own id", reason="duplicate_finding", findings=duplicates)
    silent = [f"requirement {t['requirement']!r} ({t['status']})" for t in assessment["requirement_trace"]
              if t["status"] != "covered" and t.get("finding") not in ids]
    silent += [f"premise {p['premise']!r} (fails)" for p in assessment["premises_challenged"]
               if p["outcome"] == "fails" and p.get("finding") not in ids]
    if silent:
        raise ValidationFailed(f"a gap needs a finding: {'; '.join(silent)} cite(s) no finding of this assessment; "
                               "name the finding's id in its `finding` field", reason="gap_without_finding",
                               gaps=silent)
    for f in assessment["findings"]:
        if f["severity"] in {"blocker", "major"}:
            f["required"] = True
    failed = any(f["required"] for f in assessment["findings"])
    return {"assessment": assessment, "result": "fail" if failed else "pass"}


def counting_assessment(records: list[dict[str, Any]], plan: dict[str, Any] | None) -> dict[str, Any] | None:
    """The plan assessment that counts for the accepted revision ``plan``: of the sealed records ``scan`` returns, the
    first one recorded that is bound to that revision and its sha256, or None. One counts per revision: a later
    assessment of the same revision is history and never replaces it (no assessor shopping), and one bound to another
    revision, or to the same number with another digest, never counts for this one."""
    binding = plan_binding(plan)
    if binding is None:
        return None
    bound = [r for r in records if r.get("kind") == PLAN_ASSESSMENT and r.get("plan_revision") == binding]
    return min(bound, key=lambda r: r.get("seq", 0), default=None)
