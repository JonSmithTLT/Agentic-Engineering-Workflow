"""The planted controls of the state-machine families of the generated reference (STG-12 S12-2, family 5).

``tools/reference_families/machines.py`` places an unresolved item on the edges an unchecked state write can take,
from a declared table held to the detector in both directions. Every rule has its planted right case, wrong case and
missing case, so a rule that stopped working would fail. That the records equal the registries they are read from is
in ``tests/integration/test_reference_machines.py``, and the two detectors over the engine in
``tests/integration/test_reference_machine_writes.py``. """

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from aew.engine import transitions as T

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reference_tool_machine_controls", ROOT / "tools" / "reference.py")
assert _spec is not None and _spec.loader is not None
reference = importlib.util.module_from_spec(_spec)
sys.modules["reference_tool_machine_controls"] = reference
_spec.loader.exec_module(reference)
C, _PAGES, FAMILIES = reference._families()
M = next(f for f in FAMILIES if f.__name__.endswith("machines"))
W = sys.modules["reference_families.machines_writes"]
CTX = C.Context(ROOT)  # the sources are parsed once for every test that builds the family


@cache
def committed_index() -> dict[str, Any]:
    """The committed index; ``test_reference.py`` holds the committed directory to what the code gives."""
    return json.loads(reference._on_disk(reference.OUT)["index.json"])


def site(module: str, symbol: str, form: str = "set_state", checked: bool = False):
    return W.StateWrite(module, symbol, form, checked)


# ---------------------------------------------------------------------------------------- the declared sites

def test_only_a_write_with_no_check_in_its_function_is_unchecked():
    sites = [site("m", "a", checked=True), site("m", "b"), site("m", "b", "assign"), site("m", "c", "assign")]
    assert M.unchecked_sites(sites) == {("m", "b"): {"set_state", "assign"}, ("m", "c"): {"assign"}}


def test_a_declared_site_the_reading_does_not_find_is_a_problem_and_a_found_one_is_not():
    table = {("m", "f"): M.Site(M.TICKET, ("transition",), "does a thing")}
    assert M.site_problems({("m", "f"): {"assign"}}, table, {"transition"}) == []  # right
    wrong = M.site_problems({}, table, {"transition"})  # the entry's site is gone
    assert len(wrong) == 1 and "m:f" in wrong[0] and "finds no such site" in wrong[0]
    assert M.site_problems({("m", "f"): {"assign"}}, table, {"assign"})  # its via is no operation of RULES
    no_via = {("m", "f"): M.Site(M.TICKET, (), "x")}
    assert M.site_problems({("m", "f"): {"assign"}}, no_via, {"assign"})  # a Ticket site with no via at all
    assert M.site_problems({("m", "other"): {"assign"}}, table, {"transition"})  # missing: the entry matches nothing


def test_an_unchecked_site_lands_on_the_edges_of_its_operations_and_an_unknown_one_on_every_edge():
    found = {("m", "f"): {"assign"}, ("m", "g"): {"set_state"}}
    table = {("m", "f"): M.Site(M.TICKET, ("assign",), "assigns it")}
    on_assign = M.edge_unresolved({"assign"}, found, table)
    on_other = M.edge_unresolved({"transition"}, found, table)
    assert [(i["module"], i["symbol"]) for i in on_assign] == [("m", "f"), ("m", "g")]  # right, and the unknown one
    assert [(i["module"], i["symbol"]) for i in on_other] == [("m", "g")]  # wrong operation: only the unknown one
    assert "not a site this reading knows" in on_other[0]["why"] and "calls set_state" in on_other[0]["why"]
    assert "assigns the unit's state" in on_assign[0]["why"] and "(operation assign)" in on_assign[0]["why"]
    assert M.edge_unresolved({"assign"}, {}, table) == []  # missing: no unchecked site, nothing unresolved


@pytest.mark.parametrize("kind", [M.PARENTS, M.PRIMITIVE, M.OTHER, M.COPY])
def test_an_unchecked_site_that_is_not_a_ticket_edge_is_declared_but_unresolved_on_no_edge(kind):
    found = {("m", "f"): {"assign"}}
    table = {("m", "f"): M.Site(kind, (), "is not the Ticket machine")}
    assert M.site_problems(found, table, {"assign"}) == []
    assert M.edge_unresolved({"assign"}, found, table) == []


def test_the_build_refuses_a_declared_site_the_code_no_longer_has(monkeypatch):
    monkeypatch.setattr(M, "SITES", {**M.SITES, ("aew.engine.gone", "Gone.f"): M.Site(M.OTHER, (), "no longer there")})
    with pytest.raises(C.ReferenceError, match="aew.engine.gone:Gone.f.*finds no such site"):
        M.build(CTX)


def test_a_declared_site_the_build_does_not_know_lands_on_every_edge(monkeypatch):
    """The missing case of the table: with a real site undeclared, the build still succeeds and says so on every edge,
    including the edges of operations no declared site performs."""
    table = {k: v for k, v in M.SITES.items() if k != ("aew.engine.lead_ops", "Lead._interrupt_invocations")}
    monkeypatch.setattr(M, "SITES", table)
    edges = [r for r in M.build(CTX).records if r.family == M.TRANSITIONS]
    assert len(edges) == len(T.RULES)
    for r in edges:
        assert r.coverage["label"] == "lower-bound", r.id
        assert any(i["symbol"] == "Lead._interrupt_invocations" and "not a site this reading knows" in i["why"]
                   for i in r.coverage["unresolved"]), r.id


def test_every_declared_site_is_a_function_the_package_has():
    """A table entry that names no function could not be held to the code by its absence from the detector's output."""
    sources = CTX.sources()
    for (module, symbol), declared in M.SITES.items():
        tree = sources[module].tree
        assert tree is not None
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert symbol.split(".")[-1] in names, (module, symbol)
        assert declared.kind in (M.TICKET, M.PARENTS, M.PRIMITIVE, M.OTHER, M.COPY)


# ---------------------------------------------------------------------------------------- the unreadable inputs

def test_a_state_only_the_schema_admits_is_named_and_one_it_lacks_is_unreadable_not_silent(monkeypatch):
    real = M.schema_state_enum()
    assert real is not None
    monkeypatch.setattr(M, "schema_state_enum", lambda: [*real, "NEWLY_ADMITTED"])
    state = next(r for r in M.build(CTX).records if r.family == M.STATES)
    assert any("NEWLY_ADMITTED" in i["why"] and "OPEN" in i["why"] for i in state.coverage["unresolved"])
    monkeypatch.setattr(M, "schema_state_enum", lambda: None)
    state = next(r for r in M.build(CTX).records if r.family == M.STATES)
    assert any("not where this reading looks" in i["why"] for i in state.coverage["unresolved"])


def test_a_guard_a_rule_names_that_nothing_registers_is_a_record_with_its_unresolved_item(monkeypatch):
    real = M.guard_table()[0]
    monkeypatch.setattr(M, "guard_table", lambda: ({k: v for k, v in real.items() if k[0] != "findings_recorded"}, {}))
    record = next(r for r in M.build(CTX).records if r.id == "guards:findings_recorded")
    assert record.coverage["label"] == "lower-bound" and record.fact == {"name": "findings_recorded", "evaluators": []}
    assert record.fact_coverage is not None and record.fact_coverage["evaluators"]["unresolved"]


# ---------------------------------------------------------------------------------------- the committed records

def test_the_committed_unchecked_sites_are_on_the_edges_and_in_the_gaps():
    """What the committed index says of the unchecked writes: each declared Ticket site is an unresolved item of an
    edge of its operation, and the gaps summary holds exactly those items (nothing lives only in gaps)."""
    index = committed_index()
    gaps = {(g["module"], g["symbol"]) for g in index["gaps"] if g["family"] == M.TRANSITIONS}
    declared = {key for key, s in M.SITES.items() if s.kind == M.TICKET}
    assert gaps == declared
    for rid, r in index["records"].items():
        if r["family"] == M.TRANSITIONS and r["coverage"]["label"] == "lower-bound":
            assert {(i["module"], i["symbol"]) for i in r["coverage"]["unresolved"]} <= declared, rid
