"""The personal alpha's scripted gate, evaluated beside the strict vertical."""
from __future__ import annotations

import json
from typing import Any

from aew.harness.models import free_model_id
from aew.kit.receipt import FIELDS
from vertical import oracle
from vertical.ledger import (
    CONTAINMENT_MINIMUM,
    ENFORCED_PLATFORMS,
    HELD,
    LABEL_ORDER,
    LEAD,
    RESULT_REACHED,
    V1_DECISIONS,
    WINDOWS_UNQUALIFIED,
    WORKERS,
)

OPERATOR_COUNTERS = ("credentials", "env_vars", "raw_yaml", "revisions", "manifest_adopts", "takeovers",
                     "seat_operations")
FRESH = "V1"
FORCED = "V2-forced-mid-stage"
PREFLIGHT = (
    "V3-check-changes-snapshot", "V3-model-id-provider-prefix", "V3-model-not-listed", "V3-provider-env-unset",
)
COMMON_LIMITS = ("publish_needs_decision", "containment")
LIMIT_PROBES = {
    FRESH: COMMON_LIMITS,
    FORCED: COMMON_LIMITS,
    "V1-evidence-mismatch": (*COMMON_LIMITS, "evidence_mismatch"),
    "V1-semantic-conflict": (*COMMON_LIMITS, "semantic_conflict"),
}


def fallback_problems(ledger: dict[str, Any], excuses: list[str]) -> list[str]:
    steps = {step["key"]: step for step in ledger["steps"]}
    problems = []
    for observation in ledger["observations"]:
        name = observation.get("step")
        if observation["kind"] == "no_driver":
            problems.append(f"{name}: landed step has no driver")
        if observation["kind"] != "fallback":
            continue
        step = steps.get(observation.get("oracle_key"))
        holds = step.get("held_by", ()) if step else ()
        if step and not oracle.landed(step["state"]) and "G3" in holds:
            excuses.append(f"Excused G3 fallback: {name} (step {step['step']} {step['key']}; "
                           f"held by {', '.join(holds)})")
        else:
            problems.append(f"Unexcused fallback: {name}")
    return problems


def result_problems(ledger: dict[str, Any]) -> list[str]:
    result = next((o for o in ledger["observations"] if o["kind"] == RESULT_REACHED), {})
    if result.get("asked") is not True or result.get("reached") is not True:
        return ["no result reached the operator"]
    return result.get("problems", ["result contents were not checked"])


def fresh_problems(ledger: dict[str, Any], excuses: list[str]) -> list[str]:
    problems = fallback_problems(ledger, excuses) + result_problems(ledger)
    decisions = tuple(decision["label"] for decision in ledger["decisions"])
    if decisions != V1_DECISIONS:
        problems.append(f"operator decisions {list(decisions)} (must be exactly {list(V1_DECISIONS)})")
    for name in OPERATOR_COUNTERS:
        count = ledger["counts"].get(name)
        threshold = ledger["thresholds"].get(name)
        if count is None or threshold is None:
            problems.append(f"{name}: counter or threshold missing")
        elif count > threshold:
            problems.append(f"{name} = {count} (must be at most {threshold})")
    return problems


def summary(rows: list[dict[str, Any]], *, platform: str, strict_pass: str) -> str:
    """Render the scripted alpha checks. The report's strict outcome still comes from pytest."""
    scenarios = {
        ledger["scenario"]: (ledger, row["outcome"])
        for row in rows
        if (ledger := row["ledger"]) and ledger.get("measured") and ledger.get("steering") is False
    }
    problems: list[str] = []
    excuses: list[str] = []
    for scenario, limits in LIMIT_PROBES.items():
        if scenario not in scenarios:
            problems.append(f"{scenario}: no measured ledger")
            continue
        ledger, _ = scenarios[scenario]
        for name in limits:
            outcome = ledger["hard_limits"].get(name, {}).get("outcome", "not observed")
            if outcome != HELD:
                problems.append(f"{scenario}: hard limit {name}: {outcome}")
        if scenario == FRESH:
            problems.extend(f"{scenario}: {problem}" for problem in fresh_problems(ledger, excuses))
        elif scenario == FORCED:
            problems.extend(f"{scenario}: {problem}" for problem in result_problems(ledger))
    for scenario in PREFLIGHT:
        if scenario not in scenarios or scenarios[scenario][1] != strict_pass:
            problems.append(f"{scenario}: strict preflight pass not observed")
    return verdict_text(problems, excuses, platform=platform)


def verdict_text(problems: list[str], excuses: list[str], *, platform: str) -> str:
    qualification = [] if platform in ENFORCED_PLATFORMS else [WINDOWS_UNQUALIFIED]
    status = "FAIL" if problems else "PASS"
    return "\n".join([*qualification, f"Alpha scripted gate: {status}", *problems, *excuses])


def receipt_lines(receipt: dict[str, Any] | None) -> list[str]:
    """Read the operator's receipt beside the scripted verdict."""
    if receipt is None:
        return ["Alpha receipt: NOT RECORDED (a real-model run the operator starts, per event)"]
    if receipt.get("kind") != "real":
        return ["Alpha receipt: DRY RUN, not the receipt"]

    header = receipt.get("header") or {}
    platform = header.get("platform")
    lines = ["Alpha receipt: RECORDED"]
    if platform == "win32":
        lines.append(WINDOWS_UNQUALIFIED)
    lines.append(f"header: {json.dumps(header)}")
    for field in FIELDS:
        value = receipt.get(field)
        lines.append(f"{field}: {json.dumps(value) if value is not None else 'not recorded'}")
    for name in ("workers_model", "lead_model"):
        model = header.get(name)
        if isinstance(model, str) and (reason := free_model_id(model)):
            lines.append(f"{name}: {reason}")
    lines.append(f"free: {header.get('free') or 'not ruled out (id rule only; catalog not read)'}")

    minimum = CONTAINMENT_MINIMUM.get(platform, {})
    labels = receipt.get("containment")
    if isinstance(labels, dict):
        for role, recorded in ((WORKERS, list((labels.get("workers") or {}).values())),
                               (LEAD, labels.get("lead") or [])):
            required = minimum.get(role)
            if required is not None:
                for label in recorded or [None]:
                    if label not in LABEL_ORDER or LABEL_ORDER.index(label) < LABEL_ORDER.index(required):
                        lines.append(f"{role}: {label or 'no label'} below containment minimum {required}")
    lines.append("Other receipt fields: no bar (set after the first receipt)")
    return lines
