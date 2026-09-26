"""Deterministic guardrail enforcement against a Ticket's change set (WC §16.15; KC §8.11).

M1 enforces: the AEW knowledge root (always), protected paths, generated-file
paths, and the Ticket's declared scope. Path-based review triggers add required
review gates. Dependency-direction rules are representable but not enforced (Designed).
"""

from __future__ import annotations

from typing import Any

from aew.util import glob_any

ALWAYS_PROTECTED = [".aew/**"]


def evaluate(changed: list[str], policy: dict[str, Any], scope_paths: list[str]) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    protected = ALWAYS_PROTECTED + list(policy.get("protected_paths", []))
    generated = list(policy.get("generated_paths", []))
    enforce_scope = policy.get("ticket_scope_enforcement", True) and bool(scope_paths)
    for path in sorted(changed):
        if glob_any(path, protected):
            violations.append({"path": path, "rule": "protected_path",
                               "detail": "this path may not be modified by a Ticket"})
        elif glob_any(path, generated):
            violations.append({"path": path, "rule": "generated_path",
                               "detail": "generated file; change its source/generator instead"})
        elif enforce_scope and not glob_any(path, scope_paths):
            violations.append({"path": path, "rule": "outside_ticket_scope",
                               "detail": f"not within the Ticket's declared scope {scope_paths}"})
    triggered = sorted({
        f"review_{t['name']}" for t in policy.get("review_triggers", [])
        if any(glob_any(p, t["paths"]) for p in changed)
    })
    return {"violations": violations, "triggered_gates": triggered, "changed_paths": sorted(changed),
            "unenforced": ["dependency_rules"] if policy.get("dependency_rules") else []}
