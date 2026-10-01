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
    fired = [t for t in policy.get("review_triggers", []) if any(glob_any(p, t["paths"]) for p in changed)]
    # A trigger naming a card requires that card (policy-selected); otherwise any reviewer card
    # whose specialty matches the trigger name satisfies review_<name>.
    triggered = sorted({f"review_card:{t['card']}" if t.get("card") else f"review_{t['name']}" for t in fired})
    return {"violations": violations, "triggered_gates": triggered,
            "triggered": [{"name": t["name"], "card": t.get("card")} for t in fired],
            "changed_paths": sorted(changed),
            "unenforced": ["dependency_rules"] if policy.get("dependency_rules") else []}


_RULE_TEXT = {"outside_ticket_scope": "is outside the Ticket's scope", "protected_path": "is a protected path",
              "generated_path": "is a generated file (change its source instead)"}


def describe(violations: list[dict[str, str]], limit: int = 3) -> str:
    """The violations in words: ``calc/core.py is outside the Ticket's scope; ...`` (at most ``limit`` named)."""
    words = [f"{v['path']} {_RULE_TEXT.get(v['rule'], v['rule'])}" for v in violations[:limit]]
    more = len(violations) - limit
    return "; ".join(words) + (f"; and {more} more" if more > 0 else "")


def scope_remedy(work_id: str) -> str:
    """What a Lead can do about a change outside its Ticket's scope (M3 dogfood report §6.6, E9)."""
    return (f"A Ticket's scope is fixed when it is created: if the scope is wrong, cancel this Ticket "
            f"(`aew work transition {work_id} --to CANCELLED --reason ...`) and create one with the scope the change "
            "needs; if the change strayed outside it, have the implementer undo that part")
