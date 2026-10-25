"""The state-machine families of the generated reference (STG-12 S12-2, family 5): ``transitions``, ``states``,
``guards``, ``reason-rules``, ``configuration-states`` and ``usage-live-states``
(``tools/reference_families/machines.py``).

Each family's records are held to the registry they are read from, in both directions: a static enumeration that feeds
a label is asserted equal to the registry it models. The family is built in memory (the generated directory is read by
``tests/unit/test_reference.py``'s check, which holds it to the same build). The planted controls of the rules that
place an unresolved item are in ``tests/unit/test_reference_machine_controls.py``, and the reading of the state-write
sites over the engine, by two independent detectors, in ``tests/integration/test_reference_machine_writes.py``.

The heavy lanes run this because it imports the engine: a pull request that changes a state table changes ``src`` and so
runs the full gate.
"""

from __future__ import annotations

import ast
import importlib
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from aew.engine import hierarchy
from aew.engine import transitions as T
from aew.engine.api import Engine
from aew.engine.seams import KINDS
from aew.errors import IllegalTransition
from aew.harness import usage_live

ROOT = Path(__file__).resolve().parents[2]


def _tool_modules():
    """The generator's family modules, with ``tools/`` on the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, machines
    finally:
        sys.path.remove(here)
    return common, machines


C, M = _tool_modules()
CTX = C.Context(ROOT)


@cache
def built() -> Any:
    return M.build(CTX)


def records(family: str) -> dict[str, dict[str, Any]]:
    return {r.key: r.as_json() for r in built().records if r.family == family}


# ---------------------------------------------------------------------------------------- the Ticket machine

def test_the_transition_records_are_the_rules_both_ways():
    """One record per edge of ``RULES`` and no other, each with the rule's own fields."""
    found = records("transitions")
    assert set(found) == {f"{frm}->{to}" for frm, to in T.RULES}
    for (frm, to), rule in T.RULES.items():
        r = found[f"{frm}->{to}"]
        want = {"from": frm, "to": to, "via": rule.via, "reason_required": rule.reason_required, "guard": rule.guard}
        if rule.also:
            want["also"] = list(rule.also)
        assert r["fact"] == want, (frm, to)
        assert (r["anchor"]["module"], r["anchor"]["symbol"], r["basis"]) == ("aew.engine.transitions", "RULES",
                                                                             "enumerated")
        assert r["coverage"]["label"] in ("complete-by-construction", "lower-bound")
        if rule.also:  # a list fact says how complete it is
            assert r["fact_coverage"]["also"]["label"] == "complete-by-construction"
        else:
            assert "fact_coverage" not in r


def test_the_table_accepts_exactly_its_edges_for_the_operations_it_names():
    """The registry the records are read from does what the records say: ``check`` allows an edge by its operation (or
    one of its ``also``) and refuses every other pair and operation."""
    vias = {v for r in T.RULES.values() for v in (r.via, *r.also)}
    for frm in T.STATES:
        for to in T.STATES:
            for via in sorted(vias):
                rule = T.RULES.get((frm, to))
                if rule is not None and via in (rule.via, *rule.also):
                    assert T.check(frm, to, via) is rule
                else:
                    with pytest.raises(IllegalTransition):
                        T.check(frm, to, via)


def test_an_edge_is_lower_bound_exactly_when_an_unchecked_site_can_take_it():
    """The label follows the declared sites: an edge is complete unless an unchecked Ticket site performs its operation
    and, where the site's owner names the states it can take an edge from, leaves one of them."""
    sources = M.site_sources(M.SITES)
    for key, r in records("transitions").items():
        frm, _ = key.split("->")
        rule = T.RULES[tuple(key.split("->"))]
        reachable = any(site.kind == M.TICKET and {rule.via, *rule.also} & set(site.vias)
                        and (name not in sources or frm in sources[name])
                        for name, site in M.SITES.items())
        assert (r["coverage"]["label"] == "lower-bound") is reachable, key
        if reachable:
            assert r["coverage"]["unresolved"], key
        else:
            assert r["coverage"]["registry"] == "aew.engine.transitions:RULES" and r["coverage"]["check"], key


def test_the_interrupt_sites_edges_are_the_phases_that_can_wait_on_an_invocation():
    """The one writer of INTERRUPTED takes an edge only from a state its owner names (``PHASE_DRIVERS``, read from the
    owner), and that is the set of ``interrupt`` edges the records place it on. Held both ways: every state the owner
    names is the source of an ``interrupt`` edge, and ``Lead._phase_waits_on`` -- the only gate to the write -- is false
    for every other source of one, over every role, scope and integration status, for a mutating and a non-mutating
    Ticket (synthetic units and invocations only)."""
    import itertools

    from aew.engine.lead_ops import PHASE_DRIVERS, Lead

    interrupt_sources = {frm for (frm, _), rule in T.RULES.items() if rule.via == "interrupt"}
    assert set(PHASE_DRIVERS) <= interrupt_sources, "PHASE_DRIVERS names a state with no interrupt edge"
    roles = ("implementer", "reviewer", "verifier", "executor", "investigator", "researcher", "planner")
    scopes = ("ticket", "integration", "observation", None)

    def waits(state: str) -> bool:
        for mutating, role, scope, status in itertools.product((True, False), roles, scopes, ("prepared", None)):
            unit = {"kind": "ticket", "state": state, "mutating": mutating, "execution": {"attempt": 1},
                    "integration": {"status": status}}
            if Lead._phase_waits_on(unit, {"role": role, "scope": scope, "attempt": 1}):
                return True
        return False

    assert {s for s in interrupt_sources if waits(s)} == set(PHASE_DRIVERS)
    site = M.SITES[("aew.engine.lead_ops", "Lead._interrupt_invocations")]
    assert site.sources_from == ("aew.engine.lead_ops", "PHASE_DRIVERS")
    carrying = {key for key, r in records("transitions").items()
                if any(i["symbol"] == "Lead._interrupt_invocations" for i in r["coverage"].get("unresolved", []))}
    assert carrying == {f"{frm}->{to}" for (frm, to), rule in T.RULES.items()
                        if rule.via == "interrupt" and frm in PHASE_DRIVERS}


def test_the_state_records_are_the_state_table_both_ways():
    found = records("states")
    assert set(found) == set(T.STATES)
    endpoints = {s for edge in T.RULES for s in edge}
    assert endpoints == set(T.STATES), "an edge names a state STATES lacks, or a state has no edge"
    assert set(T.TERMINAL) <= set(T.STATES) and set(T.PHASE_ORDER) <= set(T.STATES)
    for state, r in found.items():
        assert r["fact"] == {"state": state, "terminal": state in T.TERMINAL, "phase": T.PHASE_ORDER.get(state)}
        assert (r["anchor"]["module"], r["anchor"]["symbol"]) == ("aew.engine.transitions", "STATES")


def schema_enum() -> list[str]:
    from aew import schemas

    return schemas.schema("control")["$defs"]["work_unit"]["properties"]["state"]["enum"]


def test_the_control_schemas_state_enum_is_the_tickets_and_the_parents():
    """The schema is a second description of a unit's states. It admits the Ticket states, the Story/Epic phases and one
    state more; that one is named in the records' unresolved items, so the day the schema or a table changes it is a
    difference a reviewer sees. The enum is held to the tables in both directions."""
    enum = set(schema_enum())
    assert set(T.STATES) <= enum and set(hierarchy.PARENT_STATES) <= enum
    assert enum - set(T.STATES) - set(hierarchy.PARENT_STATES) == {"OPEN"}
    items = next(iter(records("states").values()))["coverage"]["unresolved"]
    assert any("also admits OPEN" in i["why"] for i in items)
    assert any(i["symbol"] == "PARENT_STATES" for i in items)


# ---------------------------------------------------------------------------------------- guards and reason rules

def test_the_guard_records_are_the_registered_guards_the_rules_name(tmp_path):
    """The names the rules use, the guards registered in a fresh Engine and the records are one set; each record's
    evaluators are that Engine's table for the name."""
    engine = Engine(tmp_path, tmp_path / ".aew")  # construction touches no file
    table = engine._units.guards.table()
    queries = engine._units.guards.queries()
    named = {r.guard for r in T.RULES.values() if r.guard}
    registered = {name for name, _kind in table}
    assert named == registered, "a rule names an unregistered guard, or a registered guard no rule names"
    found = records("guards")
    assert set(found) == named
    for name, r in found.items():
        evaluators = [
            {"kind": kind, "module": fn.__module__, "symbol": fn.__qualname__, "query": (name, kind) in queries}
            for kind in KINDS if (fn := getattr(table.get((name, kind)), "__func__", None)) is not None]
        assert r["fact"] == {"name": name, "evaluators": evaluators}
        assert r["fact_coverage"]["evaluators"]["label"] == r["coverage"]["label"] == "complete-by-construction"
        assert (r["anchor"]["module"], r["anchor"]["symbol"]) == (evaluators[0]["module"], evaluators[0]["symbol"])


def test_the_reason_rules_are_the_flagged_edges_both_ways():
    found = records("reason-rules")
    flagged = {f"{frm}->{to}": rule for (frm, to), rule in T.RULES.items() if rule.reason_required}
    assert set(found) == set(flagged)
    for key, rule in flagged.items():
        assert found[key]["fact"] == {"from": key.split("->")[0], "to": key.split("->")[1], "via": rule.via}
        assert found[key]["coverage"]["label"] == "complete-by-construction"


# ---------------------------------------------------------------------------------------- the other two machines

@pytest.mark.parametrize(("family", "module"), [("configuration-states", "aew.engine.configuration"),
                                                ("usage-live-states", "aew.harness.usage_live")])
def test_the_small_machines_are_their_state_tuples_both_ways(family, module):
    owner = importlib.import_module(module)
    found = records(family)
    assert set(found) == set(owner.STATES)
    for i, state in enumerate(owner.STATES):
        r = found[state]
        assert r["fact"] == {"state": state, "position": i, "exits": []}
        assert (r["anchor"]["module"], r["anchor"]["symbol"], r["basis"]) == (module, "STATES", "enumerated")
        # an empty list found by a detector never means none: the edge table is missing, and the record says so
        assert r["fact_coverage"]["exits"]["label"] == "lower-bound"
        assert [i["why"] for i in r["fact_coverage"]["exits"]["unresolved"]] == [
            "no edge table: how a state follows another is not recorded in a table, so no exit is enumerated"]


def test_a_second_state_tuple_of_a_machines_module_is_an_unresolved_item_of_its_records():
    config = records("configuration-states")
    assert {r["coverage"]["label"] for r in config.values()} == {"complete-by-construction"}
    assert [n for n in vars(importlib.import_module("aew.engine.configuration")) if n.endswith("STATES")] == ["STATES"]
    live = records("usage-live-states")
    assert {r["coverage"]["label"] for r in live.values()} == {"lower-bound"}
    items = next(iter(live.values()))["coverage"]["unresolved"]
    assert [(i["symbol"], i["why"]) for i in items] == [
        ("PROMPT_STATES", f"a second state set of this module ({', '.join(usage_live.PROMPT_STATES)}) is not recorded")]


# ---------------------------------------------------------------------- the configuration states, by a second reading

def configuration_tree() -> ast.Module:
    tree = CTX.sources()["aew.engine.configuration"].tree
    assert tree is not None
    return tree


def test_the_configuration_state_constants_are_the_states_in_order():
    """``STATES`` is the constants the module defines, in the order it lists them: read from the source, not from the
    tuple the generator reads. Every constant of the group is a state and every state one."""
    from aew.engine import configuration as K

    constants: dict[str, str] = {}
    listed: list[str] = []
    for node in configuration_tree().body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
            continue
        target, value = node.targets[0], node.value
        if isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple) and "MANIFEST_DRIFTED" in ast.unparse(target):
            names = [n.id for n in target.elts if isinstance(n, ast.Name)]
            values = [c.value for c in value.elts if isinstance(c, ast.Constant)]
            constants = dict(zip(names, values, strict=True))
        elif isinstance(target, ast.Name) and target.id == "STATES" and isinstance(value, ast.Tuple):
            listed = [n.id for n in value.elts if isinstance(n, ast.Name)]
    assert constants and listed
    assert set(constants) == set(listed) and all(name == value for name, value in constants.items())
    assert [constants[name] for name in listed] == list(K.STATES)


def returned_states(fn: ast.FunctionDef, module: Any) -> set[str]:
    """The first element of every tuple a function returns, a conditional expression read on both of its branches: a
    name of the module (its value) or a literal."""
    found: set[str] = set()

    def take(node: ast.expr) -> None:
        if isinstance(node, ast.IfExp):
            take(node.body)
            take(node.orelse)
        elif isinstance(node, ast.Name):
            found.add(getattr(module, node.id))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)

    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple) and node.value.elts:
            take(node.value.elts[0])
    return found


def test_every_document_state_configuration_returns_is_in_states():
    """The states ``configuration`` gives a document are the states it lists. Read two ways: the source of the function
    that decides a policy document's state (every state it can return), and running it over every combination of pins,
    pin, bytes and validity. The manifest level's state is set where the documents are listed, not by that function."""
    from aew.engine import configuration as K
    from aew.util import sha256_bytes

    fn = next(n for n in ast.walk(configuration_tree()) if isinstance(n, ast.FunctionDef) and n.name == "_policy_state")
    by_source = returned_states(fn, K)
    assert by_source and by_source <= set(K.STATES), sorted(by_source - set(K.STATES))
    pins: list[dict[str, Any] | None] = [None, {}, {"p": None}, {"p": "not-the-digest"}, {"p": sha256_bytes(b"x")}]
    by_running = {K._policy_state(p, "p", raw, valid)[0] for p in pins for raw in (None, b"x", b"y")
                  for valid in (None, True, False)}
    assert by_running <= set(K.STATES), sorted(by_running - set(K.STATES))
    assert by_running == by_source == set(K.STATES) - {K.MANIFEST_DRIFTED}


def test_the_other_machines_whose_state_key_a_declared_site_writes_are_named_in_the_states_records():
    """Every machine the declared sites write a ``["state"]`` key for (a queue entry, a validation run, a field value)
    is an unresolved item of the ``states`` records, anchored at a site that writes it; the copies are not machines."""
    machines = {site.what for site in M.SITES.values() if site.kind == M.OTHER}
    assert machines == {"an integration queue entry's state", "a validation run's state",
                        "a projected field value's state"}
    items = next(iter(records("states").values()))["coverage"]["unresolved"]
    named = {i["why"] for i in items if "another machine" in i["why"]}
    assert len(named) == len(machines)
    for what in machines:
        assert any(f"({what})" in why for why in named), what
    anchors = {(i["module"], i["symbol"]) for i in items if "another machine" in i["why"]}
    assert anchors <= {key for key, site in M.SITES.items() if site.kind == M.OTHER}
