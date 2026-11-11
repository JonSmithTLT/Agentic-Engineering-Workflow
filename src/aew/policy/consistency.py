"""Cross-file consistency of the effective policy (operator decision P0, UAT 2026-09-30).

Each policy file is validated against its own schema when it is read. This checks what no single schema can: that
the files agree with each other and with what the engine can evaluate. A contradiction otherwise surfaces only as a
gate that can never be satisfied (the Q7 shakedown: ``gates.yaml`` required a check ``unit`` that ``checks.yaml`` no
longer defined, and every mutating Ticket blocked with ``unit`` MISSING and no explanation).

``problems`` is pure: it takes the parsed files and the role catalogue's facts (``gates.Catalogue``), and returns one
plain sentence per contradiction, naming the file, the entry and the consequence. Whether a gate can be satisfied on a
unit type is ``gates.unsatisfiable``, the evaluators' own dispatch (ITEMS 55, designer decision 1): there is no list
of gate names here. A path table's or review trigger's suffix is judged as ``work create`` judges one, against the
catalogue's checks defined and configured (addendum 1; review F3).
"""

from __future__ import annotations

from typing import Any

from aew.engine import gates as G
from aew.policy import validation as V

PATH_TABLES = (("risk_paths", G.MUTATING), ("non_mutating_paths", G.NON_MUTATING), ("parent_paths", G.PARENT))


def problems(gates: dict[str, Any], checks: dict[str, Any], catalogue: G.Catalogue,
             guardrails: dict[str, Any] | None = None) -> list[str]:
    out: list[str] = []
    defined = set(checks.get("checks") or {})
    for where, ids in (("local_checks", gates.get("local_checks") or []),
                       ("post_integration.checks", (gates.get("post_integration") or {}).get("checks") or [])):
        for check_id in ids:
            if check_id not in defined:
                out.append(f"policy/gates.yaml {where} names check `{check_id}`, which policy/checks.yaml does not "
                           f"define: every gate that needs it stays MISSING. Define it in checks.yaml or remove it "
                           f"from {where}.")
    for table, utype in PATH_TABLES:
        paths = gates.get(table) or {}
        first_required: dict[str, str] = {}
        for cls in sorted(paths, key=int):
            path = paths[cls] or []
            present = set(path)
            for gate, lower in first_required.items():
                if gate not in present:
                    out.append(f"policy/gates.yaml {table}[{cls}] lacks gate `{gate}`, which {table}[{lower}] "
                               f"requires: raising a unit to class {cls} would drop it.")
            for gate in path:
                first_required.setdefault(gate, cls)
                if gate == "local_checks" and utype == G.MUTATING:
                    continue  # its ids are judged above, where the list is
                found = G.unsatisfiable(gate, utype, catalogue)
                if found is not None:
                    out.append(f"policy/gates.yaml {table}[{cls}] requires gate `{gate}`, but {found.why}: nothing "
                               f"can satisfy it, so those units ({utype}) can never complete.")
    # A guardrail's review trigger names a gate as well (``guardrails.evaluate``): a card, or a specialty.
    for trigger in (guardrails or {}).get("review_triggers") or []:
        gate = (f"{G.REVIEW_CARD_PREFIX}{trigger['card']}" if trigger.get("card")
                else f"{G.REVIEW_GATES_PREFIX}{trigger['name']}")
        found = G.unsatisfiable(gate, G.MUTATING, catalogue)
        if found is not None:
            out.append(f"policy/guardrails.yaml review_triggers `{trigger['name']}` requires gate `{gate}`, but "
                       f"{found.why}: a change it matches can never complete.")
    out += [f"policy/gates.yaml {p}" for p in V.policy_problems(gates)]
    for gate in gates.get("waivable_gates") or []:
        found = [G.unsatisfiable(gate, utype, catalogue) for utype in G.UNIT_TYPES]
        if all(f is not None for f in found):
            known = next((f for f, utype in zip(found, G.UNIT_TYPES, strict=True) if G.gate_kind(gate, utype)), None)
            out.append(f"policy/gates.yaml waivable_gates lists `{gate}`, which " + (
                "is not a gate AEW evaluates." if known is None else f"can never be satisfied: {known.why}."))
    return out
