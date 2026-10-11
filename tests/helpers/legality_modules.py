"""The modules that decide legality, for static boundary tests (CWR §11; F9 invariant 1; M4-E amendment 1, nit 6).

Paths relative to ``src/aew``: legality and authority, gates, transitions, dispatch, plan assurance and its plan lint,
the scope lint (``work_ops``), evidence acceptance, the guards and the stage journal, integration and publication, and
the typed surface's availability and classification, plus every module of the ``aew/policy`` package
(:func:`legality_modules`). The F9 boundary test (``tests/integration/test_coordination_store.py``) checks the same
engine and knowledge set."""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "aew"

LEGALITY_MODULES = (
    "engine/authority.py", "engine/dependencies.py", "engine/dispatch.py", "engine/freshness.py", "engine/gates.py",
    "engine/guards.py", "engine/hierarchy.py", "engine/transitions.py", "engine/evidence_ops.py",
    "engine/workspace_ops.py", "engine/work_ops.py", "engine/hierarchy_ops.py", "engine/nonmutating_ops.py",
    "engine/integration_ops.py", "engine/queue_ops.py", "engine/validation_ops.py", "engine/assurance.py",
    "engine/assurance_ops.py", "engine/stage_intents.py", "knowledge/evidence.py", "surface/availability.py",
    "surface/classify.py",
)


def legality_modules() -> list[Path]:
    """Every legality module's file: the named ones and the whole policy package."""
    return [SRC / rel for rel in LEGALITY_MODULES] + sorted((SRC / "policy").glob("*.py"))
