"""The Engine's composition (register E5): explicit collaborators instead of mixins.

These pin the architecture, not behaviour: the facade is the only class with an Engine identity, every
collaborator receives its dependencies through its constructor and never the Engine, nothing dispatches
behaviour through ``super()`` or ``getattr``, and the seams between collaborators (state hooks, guards by unit
kind, gate contexts by kind, transaction finalizers) are filled in one documented order.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from aew.engine import api, seams
from aew.engine.api import Engine
from aew.engine.base import Kernel
from aew.engine.seams import KINDS, MUTATING, NON_MUTATING, PARENT, GuardTable, kind_of

ENGINE_DIR = Path(api.__file__).parent
COLLABORATOR_ATTRS = ("_units", "_roles", "_invocations", "_inputs", "_packs", "_gates", "_work", "_assignment",
                      "_nm", "_hierarchy", "_evidence", "_integration", "_harness", "_lead", "_views", "_resume",
                      "_project")


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    return Engine(tmp_path, tmp_path / ".aew")  # construction touches no file


def collaborators(engine: Engine) -> dict[str, object]:
    return {name: getattr(engine, name) for name in COLLABORATOR_ATTRS}


def named(bound) -> str:
    return f"{type(bound.__self__).__name__}.{bound.__func__.__name__}"


def test_the_engine_is_a_facade_over_a_kernel_and_collaborators(engine):
    assert Engine.__mro__ == (Engine, object)
    assert isinstance(engine._k, Kernel)
    for name, collaborator in collaborators(engine).items():
        assert type(collaborator).__mro__ == (type(collaborator), object), name
        assert collaborator.k is engine._k, name


def test_the_facade_exposes_the_kernel_attributes_adapters_use(engine, tmp_path):
    assert engine.store is engine._k.store
    assert engine.repo_root == tmp_path.resolve() and engine.aew_root == (tmp_path / ".aew").resolve()


def test_no_collaborator_holds_the_engine(engine):
    for name, collaborator in collaborators(engine).items():
        for attr, value in vars(collaborator).items():
            assert not isinstance(value, Engine), f"{name}.{attr} holds the Engine"
        annotations = [str(p.annotation) for p in inspect.signature(type(collaborator).__init__).parameters.values()]
        assert not any("Engine" in a for a in annotations), name


def test_every_collaborator_dependency_is_a_constructor_parameter(engine):
    """A collaborator reaches another only through what its constructor declares (no back-door wiring)."""
    instances = set(map(id, collaborators(engine).values())) | {id(engine._k)}
    for name, collaborator in collaborators(engine).items():
        declared = set(inspect.signature(type(collaborator).__init__).parameters) - {"self"}
        held = {attr for attr, value in vars(collaborator).items() if id(value) in instances}
        assert held <= declared, (name, held - declared)


def test_only_the_composition_root_imports_the_facade():
    for path in sorted(ENGINE_DIR.glob("*.py")):
        if path.name == "api.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "aew.engine.api", path.name
                assert "Engine" not in {a.name for a in node.names}, path.name


def test_no_behaviour_is_dispatched_through_super_or_getattr_on_self():
    for path in sorted(ENGINE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "super", f"{path.name}:{node.lineno}"
                if node.func.id == "getattr" and node.args:
                    target = node.args[0]
                    assert not (isinstance(target, ast.Name) and target.id == "self"), f"{path.name}:{node.lineno}"


def test_state_hooks_run_in_their_documented_order(engine):
    hooks = engine._units.hooks
    assert [named(h) for h in hooks.before] == ["Integration.before_state_change"]
    # A terminal unit's invocations end first; then a Ticket leaving COMMIT_READY retires its candidate.
    assert [named(h) for h in hooks.after] == ["Invocations.on_state_change", "Integration.on_state_change"]


GENERAL = {"implementer_active": "WorkUnits", "findings_recorded": "WorkUnits",
           "returning_from_escalation": "WorkUnits", "not_beyond_interrupted_phase": "WorkUnits",
           "ready_for_review": "Gates", "ready_for_verification_without_review": "Gates",
           "commit_ready_without_review_or_verification": "Gates", "review_current": "Gates",
           "commit_ready_without_verification": "Gates", "all_gates_current": "Gates",
           "evidence_only_complete": "NonMutating"}
NON_MUTATING_OWN = {"implementer_active", "ready_for_review", "ready_for_verification_without_review",
                    "review_current", "commit_ready_without_review_or_verification",
                    "commit_ready_without_verification", "all_gates_current"}


def test_the_guard_table_is_explicit_per_unit_kind(engine):
    table = {key: named(guard) for key, guard in engine._units.guards.table().items()}
    expected = {}
    for name, owner in GENERAL.items():
        for kind in KINDS:
            own = kind == NON_MUTATING and name in NON_MUTATING_OWN
            expected[(name, kind)] = f"{'NonMutating' if own else owner}._guard_{name}"
    assert table == expected


def test_an_unknown_guard_is_refused_and_a_double_registration_is_an_error():
    from aew.errors import GateUnsatisfied

    guards = GuardTable()
    with pytest.raises(GateUnsatisfied, match="guard nope is not available"):
        guards.resolve("nope", {"kind": "ticket", "mutating": True})
    guards.register("g", lambda *a: None)
    with pytest.raises(ValueError):
        guards.register("g", lambda *a: None, (MUTATING,))
    guards.register("g", lambda *a: None, (MUTATING,), replace=True)


def test_gate_contexts_of_evidence_only_kinds_come_from_their_owners(engine):
    contexts = engine._gates.contexts
    assert named(contexts.get(NON_MUTATING)) == "NonMutating.evidence_gate_context"
    assert named(contexts.get(PARENT)) == "Hierarchy.evidence_gate_context"


def test_unit_kinds():
    assert kind_of({"kind": "ticket", "mutating": True}) == MUTATING
    assert kind_of({"kind": "ticket", "mutating": False}) == NON_MUTATING
    assert kind_of({"kind": "story"}) == kind_of({"kind": "epic"}) == PARENT


def test_transaction_finalizers_start_empty(engine):
    assert engine._k.finalizers.steps == []  # ADR-0011's archival attaches here
    assert isinstance(engine._k.finalizers, seams.TxnFinalizers)
