"""Cross-file consistency of the effective policy (operator decision P0, UAT 2026-09-30).

Each policy file is validated against its own schema when it is read. This checks what no single schema can: that
the files agree with each other and with what the engine can evaluate. A contradiction otherwise surfaces only as a
gate that can never be satisfied (the Q7 shakedown: ``gates.yaml`` required a check ``unit`` that ``checks.yaml`` no
longer defined, and every mutating Ticket blocked with ``unit`` MISSING and no explanation).

``problems`` is pure: it takes the parsed files and the reviewer specialties of the role catalog, and returns one
plain sentence per contradiction, naming the file, the entry and the consequence.
"""

from __future__ import annotations

from typing import Any

# The gates each unit type has an evaluator for (engine/gates.py, nonmutating_ops, hierarchy_ops).
MUTATING = {"accepted_plan", "local_checks", "self_review", "review_r1", "verification_goal_backwards",
            "verification_contract"}
NON_MUTATING = {"accepted_plan", "execute_record", "review_r1", "verification_goal_backwards",
                "verification_contract"}
PARENT = {"accepted_plan", "children_complete", "review_r1", "verification_goal_backwards", "verification_contract"}
PATH_TABLES = (("risk_paths", "mutating Tickets", MUTATING), ("non_mutating_paths", "non-mutating Tickets",
                                                                NON_MUTATING),
               ("parent_paths", "Stories and Epics", PARENT))


def problems(gates: dict[str, Any], checks: dict[str, Any], specialties: set[str]) -> list[str]:
    out: list[str] = []
    defined = set((checks.get("checks") or {}))
    for where, ids in (("local_checks", gates.get("local_checks") or []),
                       ("post_integration.checks", (gates.get("post_integration") or {}).get("checks") or [])):
        for check_id in ids:
            if check_id not in defined:
                out.append(f"policy/gates.yaml {where} names check `{check_id}`, which policy/checks.yaml does not "
                           f"define: every gate that needs it stays MISSING. Define it in checks.yaml or remove it "
                           f"from {where}.")
    for table, label, known in PATH_TABLES:
        for cls, path in sorted((gates.get(table) or {}).items()):
            for gate in path or []:
                if gate in known:
                    continue
                if gate.startswith("review_") and gate[len("review_"):] in specialties:
                    continue
                why = (f"no reviewer card has specialty `{gate[len('review_'):]}`"
                       if gate.startswith("review_") else f"AEW has no evaluator for it on {label}")
                out.append(f"policy/gates.yaml {table}[{cls}] requires gate `{gate}`, but {why}: nothing can satisfy "
                           "it, so those units can never complete.")
    all_known = MUTATING | NON_MUTATING | PARENT
    for gate in gates.get("waivable_gates") or []:
        if gate not in all_known and not (gate.startswith("review_") and gate[len("review_"):] in specialties):
            out.append(f"policy/gates.yaml waivable_gates lists `{gate}`, which is not a gate AEW evaluates.")
    return out
