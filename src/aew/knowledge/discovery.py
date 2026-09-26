"""Candidate-authority discovery for ``aew init`` (WC §15.7, KC §19; plan review §4).

Discovery never confers authority. Filesystem location alone does not make a
README or docs directory normative: it may be stale, generated, historical or
non-normative. Each hit becomes a *candidate* with a suggested class, a
confidence and the reason it was detected. Only a Lead/operator decision
(``aew authority accept``) moves a candidate into ``authority.accepted``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# (relative path, is_dir, suggested class, confidence, reason)
RULES: list[tuple[str, bool, str, str, str]] = [
    ("docs/adr", True, "decisions", "high", "conventional ADR directory"),
    ("docs/adrs", True, "decisions", "high", "conventional ADR directory"),
    ("docs/decisions", True, "decisions", "high", "decision-record directory"),
    ("adr", True, "decisions", "high", "conventional ADR directory"),
    ("adrs", True, "decisions", "high", "conventional ADR directory"),
    ("doc/adr", True, "decisions", "high", "conventional ADR directory"),
    ("docs/contracts", True, "contracts", "high", "explicit contracts directory"),
    ("contracts", True, "contracts", "high", "explicit contracts directory"),
    ("docs/specs", True, "contracts", "medium", "specification directory (may include drafts)"),
    ("docs/spec", True, "contracts", "medium", "specification directory (may include drafts)"),
    ("schema", True, "schemas", "medium", "schema directory"),
    ("schemas", True, "schemas", "medium", "schema directory"),
    ("docs/schema", True, "schemas", "medium", "schema directory"),
    ("ARCHITECTURE.md", False, "orientation", "medium", "architecture overview document"),
    ("README.md", False, "orientation", "low", "README: orientation, may be stale or non-normative"),
    ("README.rst", False, "orientation", "low", "README: orientation, may be stale or non-normative"),
    ("README", False, "orientation", "low", "README: orientation, may be stale or non-normative"),
    ("docs", True, "orientation", "low", "documentation directory: mixed normative/historical content"),
    ("doc", True, "orientation", "low", "documentation directory: mixed normative/historical content"),
    ("CONTRIBUTING.md", False, "orientation", "low", "contribution guide"),
    ("src", True, "source", "medium", "conventional source directory"),
    ("lib", True, "source", "medium", "conventional source directory"),
]


def discover_candidates(repo_root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for rel, is_dir, klass, confidence, reason in RULES:
        path = repo_root / rel
        if (is_dir and path.is_dir()) or (not is_dir and path.is_file()):
            candidates.append({
                "id": f"C-{len(candidates) + 1:03d}",
                "path": rel + ("/" if is_dir else ""),
                "suggested_class": klass,
                "confidence": confidence,
                "reason": reason,
                "status": "proposed",
            })
    return candidates


def open_questions_for(candidates: list[dict[str, Any]]) -> str:
    lines = ["## Authority classification pending (from `aew init`)", ""]
    if not candidates:
        lines.append("- No conventional authority sources were detected. Identify the project's contracts, "
                     "decision records and schemas, then register them.")
    for c in candidates:
        lines.append(
            f"- {c['id']} `{c['path']}`: suggested **{c['suggested_class']}** ({c['confidence']} confidence; "
            f"{c['reason']}). Accept with `aew authority accept {c['id']} --class <class>` or reject with "
            f"`aew authority reject {c['id']}`."
        )
    lines += ["", "## Unknown project knowledge", "",
              "- Project overview, architecture, ownership and build/test commands are not yet established "
              "(see knowledge/PROJECT.md and policy/checks.yaml).", ""]
    return "\n".join(lines)
