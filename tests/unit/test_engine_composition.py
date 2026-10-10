"""The Engine's composition (register E5): explicit collaborators instead of mixins.

These pin the architecture, not behaviour: the facade is the only class with an Engine identity, every
collaborator receives its dependencies through its constructor, typed by a narrow port (``ports``), and never the
Engine, nothing dispatches behaviour through ``super()`` or ``getattr``, the unit's kind selects code only through
the ``KindRegistry``, and the seams between collaborators (state hooks, guards by unit kind, kind operations,
transaction finalizers) are filled in one documented order.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from aew.engine import api, ports, seams
from aew.engine.api import Engine
from aew.engine.base import Kernel
from aew.engine.seams import (
    KIND_OPERATIONS,
    KINDS,
    MUTATING,
    NON_MUTATING,
    PARENT,
    GuardTable,
    KindRegistry,
    kind_of,
)

ENGINE_DIR = Path(api.__file__).parent
COLLABORATOR_ATTRS = ("_units", "_roles", "_invocations", "_inputs", "_packs", "_gates", "_work", "_assignment",
                      "_nm", "_hierarchy", "_evidence", "_integration", "_harness", "_lead", "_views", "_resume",
                      "_project", "_archive", "_history", "_migration", "_dispatch", "_assurance", "_queue",
                      "_coordination")


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


def test_every_before_hook_is_a_query_the_guard_queries_ask(engine):
    """PR #170 review, finding 1: a `before` hook is a pure refusal that answers (a blocker or None) and never raises,
    so the guard queries can ask it (`WorkUnits.state_change_query`) and a new hook cannot bypass them."""
    from aew.engine.dispatch import Blocker

    units = [{"kind": "ticket", "mutating": True, "state": s, "integration": i}
             for s in ("RUNNING", "COMMIT_READY") for i in (None, {"status": "prepared"}, {"status": "publishing"})]
    for hook in engine._units.hooks.before:
        for unit in units:
            for to in ("RUNNING", "CANCELLED", "DONE"):
                found = hook(dict(unit), {"from": unit["state"], "to": to})
                assert found is None or (isinstance(found, Blocker) and found.error is not None), named(hook)
    publishing = {"kind": "ticket", "mutating": True, "state": "COMMIT_READY", "integration": {"status": "publishing"}}
    found = engine._units.state_change_query(publishing, {"from": "COMMIT_READY", "to": "RUNNING"})
    assert found is not None and found.code == "ILLEGAL_TRANSITION"


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


KIND_TABLE = {
    ("gate_context", MUTATING): "Gates._ticket_gate_context",
    ("gate_context", NON_MUTATING): "NonMutating.evidence_gate_context",
    ("gate_context", PARENT): "Hierarchy.evidence_gate_context",
    ("invoke", MUTATING): "EvidenceCommands._invoke_ticket",
    ("invoke", NON_MUTATING): "NonMutating.invoke_evidence_unit",
    ("invoke", PARENT): "Hierarchy.invoke_evidence_unit",
    ("ingest", MUTATING): "EvidenceCommands._ingest_ticket_report",
    ("ingest", NON_MUTATING): "NonMutating.ingest_evidence_unit_report",
    ("ingest", PARENT): "Hierarchy.ingest_evidence_unit_report",
    ("classify_verification", MUTATING): "EvidenceCommands._classify_ticket_verification",
    ("classify_verification", NON_MUTATING): "EvidenceCommands._classify_ticket_verification",
    ("classify_verification", PARENT): "Hierarchy.classify_parent_verification",
    ("next_actions", MUTATING): "Resume._ticket_next_actions",
    ("next_actions", NON_MUTATING): "Resume._nm_ticket_next_actions",
    ("next_actions", PARENT): "Resume._parent_actions",
}


def test_every_kind_operation_has_one_registered_handler_per_kind(engine):
    kinds = engine._gates.kinds
    assert kinds is engine._evidence.kinds is engine._resume.kinds
    assert {key: named(handler) for key, handler in kinds.table().items()} == KIND_TABLE
    assert set(KIND_TABLE) == {(op, kind) for op in KIND_OPERATIONS for kind in KINDS}


def test_the_kind_registry_refuses_gaps_duplicates_and_unknowns():
    kinds = KindRegistry()
    kinds.register("gate_context", MUTATING, lambda *a: None)
    with pytest.raises(ValueError, match="already registered"):
        kinds.register("gate_context", MUTATING, lambda *a: None)
    with pytest.raises(ValueError, match="unknown kind operation"):
        kinds.register("nope", MUTATING, lambda *a: None)
    with pytest.raises(ValueError, match="unknown unit kind"):
        kinds.register("gate_context", "nope", lambda *a: None)
    with pytest.raises(ValueError, match="without a handler"):
        kinds.require_complete()


def test_evidence_only_entry_points_resolve_a_parent_or_else_the_non_mutating_handler(engine):
    kinds = engine._gates.kinds
    for unit, owner in (({"kind": "story"}, "Hierarchy"), ({"kind": "ticket", "mutating": False}, "NonMutating"),
                        ({"kind": "ticket", "mutating": True}, "NonMutating")):
        assert named(kinds.resolve_evidence_only("invoke", unit)).startswith(owner + ".")


def test_only_the_kind_registry_selects_code_by_unit_kind():
    """``kind_of`` is called only by the seams, and the per-call routing helpers it replaced are gone."""
    for path in sorted(ENGINE_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for removed in ("_is_parent_id", "_is_evidence_unit_id", "KindGateContexts"):
            assert removed not in source, f"{path.name} still uses {removed}"
        if path.name == "seams.py":
            continue
        tree = ast.parse(source)
        calls = [n.lineno for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "kind_of"]
        assert not calls, f"{path.name}:{calls} selects by kind outside the KindRegistry"


# ---------------------------------------------------------------- narrow ports

PORTS = {name: cls for name, cls in vars(ports).items() if name.endswith("Port") and inspect.isclass(cls)}
SEAM_TYPES = {"hooks": "StateHooks", "guards": "GuardTable", "kinds": "KindRegistry"}


def port_members(port: type) -> set[str]:
    return {n for n in vars(port) if not n.startswith("_")} | set(getattr(port, "__annotations__", {}))


def dependencies(collaborator: object) -> dict[str, str]:
    """Each constructor dependency of a collaborator and its declared type, as written."""
    params = inspect.signature(type(collaborator).__init__).parameters
    return {name: str(p.annotation) for name, p in params.items() if name not in ("self", "k")}


def test_every_collaborator_dependency_is_typed_by_a_port_or_a_seam(engine):
    for name, collaborator in collaborators(engine).items():
        for param, annotation in dependencies(collaborator).items():
            expected = SEAM_TYPES.get(param)
            assert annotation == expected if expected else annotation in PORTS, (name, param, annotation)


def test_a_collaborator_uses_of_each_dependency_only_what_its_port_declares(engine):
    used_per_port: dict[str, set[str]] = {p: set() for p in PORTS}
    for name, collaborator in collaborators(engine).items():
        deps = {param: annotation for param, annotation in dependencies(collaborator).items() if annotation in PORTS}
        tree = ast.parse(inspect.getsource(type(collaborator)))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
                    and isinstance(node.value.value, ast.Name) and node.value.value.id == "self"
                    and node.value.attr in deps):
                port = deps[node.value.attr]
                assert node.attr in port_members(PORTS[port]), f"{name} uses {node.attr}, which {port} does not declare"
                used_per_port[port].add(node.attr)
    for port, used in used_per_port.items():
        assert port_members(PORTS[port]) == used, f"{port} declares members no collaborator uses"


def test_ports_are_public_and_every_implementation_matches_them(engine):
    for collaborator in collaborators(engine).values():
        for param, annotation in dependencies(collaborator).items():
            if annotation not in PORTS:
                continue
            port, implementation = PORTS[annotation], getattr(collaborator, param)
            for member in port_members(port):
                assert not member.startswith("_"), (annotation, member)
                assert hasattr(implementation, member), (annotation, member)
                if callable(getattr(port, member, None)):
                    want = inspect.signature(getattr(port, member))
                    have = inspect.signature(getattr(type(implementation), member))
                    assert str(have) == str(want), (annotation, member, str(have), str(want))


def test_unit_kinds():
    assert kind_of({"kind": "ticket", "mutating": True}) == MUTATING
    assert kind_of({"kind": "ticket", "mutating": False}) == NON_MUTATING
    assert kind_of({"kind": "story"}) == kind_of({"kind": "epic"}) == PARENT


def test_the_transaction_finalizers_are_the_dispatch_check_then_archival(engine):
    assert isinstance(engine._k.finalizers, seams.TxnFinalizers)
    # M4-E E3: a stage step is judged by its journal first (STALE_POLICY, a stale owner); M4-A: no invocation or run
    # commits without a dispatch decision; M4-D: the queue follows its Tickets (before
    # archival, so a retired entry leaves with its unit); M4-D5: every terminal validation run gets its immutable
    # record (before archival, so a retired candidate's run is recorded before the unit leaves); then ADR-0011 R6.
    assert [named(step) for step in engine._k.finalizers.steps] == [
        "StageIntents.finalize", "Dispatch.finalize", "Queue.finalize", "Validation.finalize", "UsageCopy.finalize",
        "Coordination.finalize", "Archive.finalize"]
    assert named(engine._k.archived_credential) == "Archive.archived_credential"  # R7


# The finalizers that can end an invocation: the queue's retires an entry and ends its custodian and the custodian's
# children (M4-D). A later one that can (F4 S4b's generation-change step, E6a) is added here and placed before the seal.
ENDS_INVOCATIONS = ("Queue.finalize",)


def test_the_seal_finalizer_runs_after_every_finalizer_that_can_end_an_invocation_and_before_archival(engine):
    """F9-A plan D-16 (N1): the coordination seal runs after every finalizer that can end an invocation, so it sees
    every ending, and immediately before archival, so the seal's pointer is on its unit when archival bundles it. The
    store's commit check seals through the same function (R3), injected by the composition root."""
    order = [named(step) for step in engine._k.finalizers.steps]
    seal = order.index("Coordination.finalize")
    assert order[seal + 1] == "Archive.finalize" and seal + 2 == len(order)
    assert all(order.index(name) < seal for name in ENDS_INVOCATIONS)
    assert named(engine._k.store.seal) == "Coordination.seal_ending"
