"""The offline verifier-disposition adapter: a verifier's first emitted verification, as a disposition to grade.

Public and answer-free: it reads what a verifier emitted and what the harness observed, never an expected decision
(those are the evaluator's, in ``evaluator/``). It runs no model and calls no provider.

* **The first disposition.** The first ``kind: verification`` record a run emitted is its disposition, before anyone
  repairs the candidate; later records are only counted. ``accept`` is exactly what AEW's verification gate passes
  (``aew.engine.gates._verification_passes``: a ``pass`` with passing ``goal_backwards`` and ``contract`` claims), and
  everything else, a fail, an inconclusive or a blocked result included, is ``rework``. No record, or one that is not a
  valid ``aew/evidence/v1`` verification, is ``no_disposition``: a counted outcome, never a retry.
* **Unsupported claims** are recorded beside the disposition and never change it. A claim that asserts ``pass`` or
  ``fail`` is unsupported when it cites no check, cites a check the harness never observed, cites one observed on
  another snapshot, or contradicts what its checks observed (a pass over a failing check, a fail over passing ones).
  A claim's own words are never evidence (skill evaluation guide §6, "Evidence quality / freshness").
* **Validity is delivery, not behaviour.** An exposure other than the arm's preregistered one, or a record bound to a
  snapshot other than the candidate's, is ``invalid``: the cell did not measure what it was registered to measure.
  A verifier that edits the candidate is a counted authority violation (the verifier archetype edits nothing).
* **Cost** is carried as the attempt recorded it. Absent is unmeasured (``None``), never zero.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from aew import schemas, skills
from aew.engine.gates import _verification_passes
from aew.roles import builtin_cards, validate_card

SCHEMA = "aew/verifier-disposition/v1"
CARD = "verifier"
SKILL = "acceptance-verification"
ASSERTING = ("pass", "fail")  # inconclusive and blocked claims assert nothing to support


def projection(applied_skills: list[str]) -> dict[str, Any]:
    """The verifier role as an arm applies it: the shipped card with its ``skills:`` replaced by the arm's, and what
    AEW's skill plan exposes for that list (``aew.skills.plan``, the one answer every launch reads)."""
    card = builtin_cards()[CARD]
    applied = {**card.meta, "skills": list(applied_skills)}
    validate_card(applied, source=f"experiment-local {CARD} card")
    return {"card": card.id, "card_sha256": card.sha256,
            "applied_sha256": hashlib.sha256(json.dumps(applied, sort_keys=True).encode("utf-8")).hexdigest(),
            "skills": skills.plan(applied["skills"], applied.get("optional_skills") or [])}


def first_verification(emitted: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, int]:
    """The first verification record, and how many verification records followed it."""
    found = [r for r in emitted if isinstance(r, dict) and r.get("kind") == "verification"]
    return (found[0], len(found) - 1) if found else (None, 0)


def unsupported_claims(record: dict[str, Any], checks: list[dict[str, Any]], revision: str) -> list[dict[str, Any]]:
    """Each asserting claim the observed checks do not support, with the reason."""
    observed = {c["id"]: c for c in checks}
    out = []
    for n, claim in enumerate(record["verification"]["claims"]):
        if claim["result"] not in ASSERTING:
            continue
        cited = list(claim.get("checks") or [])
        reason = None
        if not cited:
            reason = "no_check_cited"
        elif any(c not in observed for c in cited):
            reason = "check_not_observed"
        elif any(observed[c].get("snapshot") != revision for c in cited):
            reason = "other_snapshot"
        elif (claim["result"] == "pass") != all(observed[c]["ok"] for c in cited):
            reason = "contradicted"
        if reason:
            out.append({"claim": n, "type": claim["type"], "result": claim["result"], "reason": reason})
    return out


def exposure_problem(intended: list[str], observed: dict[str, Any] | None) -> str | None:
    """Why the observed skill exposure is not the arm's preregistered one, or ``None`` when it is."""
    if not isinstance(observed, dict):
        return "no exposure was observed"
    want = projection(intended)["skills"]
    if observed.get("exposed") != want["exposed"]:
        return f"exposed {observed.get('exposed')!r}, preregistered {want['exposed']!r}"
    seen = sorted((d.get("name"), d.get("sha256")) for d in observed.get("delivered") or [])
    if seen != sorted((d["name"], d["sha256"]) for d in want["delivered"]):
        return "the delivered skill bytes are not the shipped ones"
    return None


def observe(*, run_id: str, case: str, arm: str, emitted: list[dict[str, Any]], checks: list[dict[str, Any]],
            candidate_revision: str, intended_skills: list[str], exposure: dict[str, Any] | None,
            changed_paths: list[str], cost: dict[str, Any] | None) -> dict[str, Any]:
    """One run's observation: its first disposition, the evidence behind it, its exposure and its cost."""
    record, later = first_verification(emitted)
    out: dict[str, Any] = {
        "schema": SCHEMA, "run_id": run_id, "case": case, "arm": arm,
        "validity": {"status": "valid", "reason": None},
        "disposition": None, "verification_result": None, "malformed": None, "later_verifications": later,
        "claims": 0, "unsupported_claims": [], "supported_failure": False,
        "authority_violations": [f"edited {p}" for p in changed_paths],
        "exposure": {"intended": sorted(intended_skills), "observed": exposure,
                     "loaded": (exposure or {}).get("loaded")},
        "cost": cost or None,
    }
    problem = exposure_problem(intended_skills, exposure)
    if problem:
        out["validity"] = {"status": "invalid", "reason": f"EXPOSURE_MISMATCH: {problem}"}
        return out
    if record is None:
        return out
    errors = schemas.iter_errors("evidence", record)
    if errors or "verification" not in record:
        out["malformed"] = "not a valid aew/evidence/v1 verification record"
        return out
    bound = record["evaluated_snapshot"]["base_revision"]
    if bound != candidate_revision:
        out["validity"] = {"status": "invalid", "reason": f"SNAPSHOT_MISMATCH: bound to {bound!r}"}
        return out
    unsupported = unsupported_claims(record, checks, candidate_revision)
    failed = {n for n, c in enumerate(record["verification"]["claims"]) if c["result"] == "fail"}
    out.update({
        "disposition": "accept" if _verification_passes(record) else "rework",
        "verification_result": record["result"],
        "claims": len(record["verification"]["claims"]),
        "unsupported_claims": unsupported,
        "supported_failure": bool(failed - {u["claim"] for u in unsupported}),
    })
    return out


def from_run(run: dict[str, Any], frozen: dict[str, Any]) -> dict[str, Any]:
    """:func:`observe` over a finalized ``aew/eval-run/v1`` record whose harness carries what the verifier emitted
    (``emitted``), the checks the harness observed (``checks``) and the delivered exposure (``exposure``)."""
    arm = next(a for a in frozen["arms"] if a["id"] == run["arm"]["id"])
    harness = run["harness"]
    return observe(run_id=run["run_id"], case=run["case"]["id"], arm=arm["id"], emitted=harness.get("emitted") or [],
                   checks=harness.get("checks") or [], candidate_revision=run["outcome"]["base_commit"],
                   intended_skills=arm["config"]["skills"], exposure=harness.get("exposure"),
                   changed_paths=run["outcome"].get("changed_paths") or [], cost=run.get("cost"))
