"""Project manifest (KC §6), logical-name resolution (KC §14) and init templates.

The manifest is a resolver/index. It does not make what it references
authoritative: only ``authority.accepted`` entries (accepted by a Lead/operator
decision) are project authority; ``authority.candidates`` are discoveries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.errors import NotFound
from aew.schemas import validate
from aew.util import dump_yaml, read_yaml

AEW_DIR = ".aew"
MANIFEST = "project.yaml"

# Logical knowledge names -> manifest keys (KC §14). Roles request these names,
# never physical paths, so layouts can change without changing role behavior.
KNOWLEDGE_NAMES = ("project_overview", "open_questions", "architecture_map", "codebase_map", "ownership_map", "glossary")

DEFAULT_GATES: dict[str, Any] = {
    "schema": "aew/gates/v1",
    "mutating_concurrency": 1,
    "local_checks": ["unit"],
    "risk_paths": {
        "0": ["local_checks"],
        "1": ["accepted_plan", "local_checks", "self_review", "review_r1",
              "verification_goal_backwards", "verification_contract"],
        "2": ["accepted_plan", "local_checks", "self_review", "review_r1",
              "verification_goal_backwards", "verification_contract"],
        "3": ["accepted_plan", "local_checks", "self_review", "review_r1",
              "verification_goal_backwards", "verification_contract"],
        "4": ["accepted_plan", "local_checks", "self_review", "review_r1",
              "verification_goal_backwards", "verification_contract"],
    },
    "post_integration": {"verification": True, "checks": ["unit"]},
    "waivable_gates": [],
}

DEFAULT_CHECKS: dict[str, Any] = {
    "schema": "aew/checks/v1",
    "checks": {
        "unit": {
            "configured": False,
            "command": None,
            "cwd": ".",
            "timeout_s": 900,
            "description": "Focused/unit test command. Not guessed at init: configure it, "
                           "or gates that need it stay blocked.",
        }
    },
    "baseline_failures": [],
}

DEFAULT_GUARDRAILS: dict[str, Any] = {
    "schema": "aew/guardrails/v1",
    "protected_paths": [],
    "generated_paths": [],
    "ticket_scope_enforcement": True,
    "review_triggers": [],
    "dependency_rules": [],
    "notes": "The AEW knowledge root (.aew/**) is always protected. dependency_rules are "
             "representable in M1; deterministic enforcement is Designed.",
}


def default_manifest(project_id: str, name: str, branch: str, workspaces_root: str) -> dict[str, Any]:
    manifest = {
        "schema": "aew/project/v1",
        "project": {"id": project_id, "name": name, "profile": "base"},
        "repository": {"root": "..", "vcs": "git", "authoritative_branch": branch},
        "workspaces": {"root": workspaces_root},
        "knowledge": {
            "project_overview": "knowledge/PROJECT.md",
            "open_questions": "knowledge/OPEN-QUESTIONS.md",
            "architecture_map": None,
            "codebase_map": None,
            "ownership_map": None,
            "glossary": None,
        },
        "control_state": {
            "control": "state/control.yaml",
            "current": "state/CURRENT.md",
            "handoff": "state/HANDOFF.md",
        },
        "records": {"work": "work/", "evidence": "evidence/", "decisions": "decisions/"},
        "policy": {
            "guardrails": "policy/guardrails.yaml",
            "checks": "policy/checks.yaml",
            "gates": "policy/gates.yaml",
        },
        "fingerprint": {"include_ignored": [], "exclude": []},
        "roles": {"catalog": "roles/"},
        "authority": {"accepted": [], "candidates": []},
    }
    validate("project", manifest, source="default manifest")
    return manifest


def render_manifest(manifest: dict[str, Any]) -> str:
    header = (
        "# AEW project manifest (KC §6). Resolver/index only: referencing a source here does not\n"
        "# make it authoritative. authority.accepted changes only through `aew authority accept`.\n"
        "# The engine pins this file's hash; adopt manual edits with `aew manifest adopt`.\n"
    )
    return header + dump_yaml(manifest)


def load_manifest(aew_root: Path) -> dict[str, Any]:
    path = aew_root / MANIFEST
    if not path.exists():
        raise NotFound(f"manifest not found: {path}")
    manifest = read_yaml(path)
    validate("project", manifest, source=str(path))
    return manifest


def resolve_knowledge(manifest: dict[str, Any], aew_root: Path, name: str) -> Path | None:
    rel = manifest.get("knowledge", {}).get(name)
    return (aew_root / rel) if rel else None


def project_overview_template(name: str) -> str:
    return f"""# {name} — project overview

Orientation only (KC §8.1); this is not a replacement for project contracts.
Fields left as `UNKNOWN` have not been established. Record them from evidence;
do not guess.

## What is this project?
UNKNOWN

## What problem does it solve?
UNKNOWN

## Major components
UNKNOWN

## Assumed environment
UNKNOWN

## Authoritative documents
Accepted authority is listed in `project.yaml` (`authority.accepted`). Candidates
discovered at init are awaiting a Lead or operator decision.

## High-level constraints
UNKNOWN
"""


def open_questions_template() -> str:
    return """# Open questions

Unresolved questions that future work must not treat as settled facts (KC §8.10).

"""


def roles_readme() -> str:
    return """# Project role catalog

Project-defined Role cards (`schema: aew/role/v1`) live here, one YAML file per card.
A card extends exactly one AEW archetype (implementer, reviewer, verifier, investigator,
researcher, planner) and may add purpose, advisory `use_when` guidance, responsibilities,
skills, capabilities, required knowledge and outputs, or narrow permissions via `restrict`.
Cards can never widen their archetype's authority; `aew role validate` checks every file.
Card ids must be unique across the built-in deck and this catalog.
"""
