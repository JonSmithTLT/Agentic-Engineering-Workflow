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


# ---------------------------------------------------------------------------------------- a site narrowed to sources

NARROW = {("m", "f"): M.Site(M.TICKET, ("interrupt",), "interrupts it", ("m", "DRIVERS"))}


def test_a_narrowed_site_lands_only_on_the_edges_that_leave_a_source_its_owner_names():
    found = {("m", "f"): {"assign"}}
    sources = {("m", "f"): frozenset({"RUNNING", "ASSIGNED"})}
    on_source = M.edge_unresolved({"interrupt"}, found, NARROW, "RUNNING", sources)  # right: an edge it can take
    off_source = M.edge_unresolved({"interrupt"}, found, NARROW, "VERIFIED", sources)  # wrong: one it cannot
    other_via = M.edge_unresolved({"transition"}, found, NARROW, "RUNNING", sources)  # wrong: another operation
    unspecified = M.edge_unresolved({"interrupt"}, found, NARROW, None, sources)  # missing the source: not narrowed
    assert [i["symbol"] for i in on_source] == ["f"] and "from a key of DRIVERS" in on_source[0]["why"]
    assert off_source == [] and other_via == [] and len(unspecified) == 1


def test_an_unknown_site_is_unresolved_on_every_edge_even_with_a_narrowed_site_beside_it():
    found = {("m", "f"): {"assign"}, ("m", "g"): {"set_state"}}
    sources = {("m", "f"): frozenset({"RUNNING"})}
    off = M.edge_unresolved({"interrupt"}, found, NARROW, "VERIFIED", sources)
    assert [i["symbol"] for i in off] == ["g"]


def test_the_owner_naming_a_state_the_table_has_no_edge_from_is_a_problem():
    edges = {("RUNNING", "INTERRUPTED"): {"interrupt"}, ("RUNNING", "CANCELLED"): {"transition"}}
    sources = {("m", "f"): frozenset({"RUNNING"})}
    assert M.source_problems(NARROW, sources, edges) == []  # right
    wrong = M.source_problems(NARROW, {("m", "f"): frozenset({"RUNNING", "VERIFIED"})}, edges)  # a state with no edge
    assert len(wrong) == 1 and "VERIFIED" in wrong[0] and "no interrupt edge from VERIFIED" in wrong[0]
    assert M.source_problems(NARROW, {("m", "f"): frozenset({"RUNNING"})}, {("RUNNING", "CANCELLED"): {"transition"}})
    not_narrowed = {("m", "f"): M.Site(M.TICKET, ("interrupt",), "x")}
    assert M.source_problems(not_narrowed, {}, edges) == []  # missing: a site with no sources has nothing to check


def test_a_registry_that_names_the_sources_is_read_from_its_owner_and_must_be_a_mapping():
    owner = ("aew.engine.lead_ops", "PHASE_DRIVERS")
    table = {("aew.engine.lead_ops", "f"): M.Site(M.TICKET, ("interrupt",), "x", owner)}
    from aew.engine.lead_ops import PHASE_DRIVERS

    assert M.site_sources(table) == {("aew.engine.lead_ops", "f"): frozenset(PHASE_DRIVERS)}
    not_a_mapping = {("aew.engine.lead_ops", "f"): M.Site(M.TICKET, ("interrupt",), "x",
                                                         ("aew.engine.lead_ops", "ACTIVE_INVOCATION_STATES"))}
    with pytest.raises(C.ReferenceError, match="is not a mapping"):
        M.site_sources(not_a_mapping)
    missing = {("aew.engine.lead_ops", "f"): M.Site(M.TICKET, ("interrupt",), "x", ("aew.engine.lead_ops", "NOPE"))}
    with pytest.raises(C.ReferenceError, match="is not a mapping"):
        M.site_sources(missing)


# ---------------------------------------------------------------------------------------- the other machines

def test_the_machines_whose_state_key_a_declared_site_writes_are_named_once_each_at_their_first_site():
    table = {("m", "a"): M.Site(M.OTHER, (), "a queue entry's state"),
             ("m", "b"): M.Site(M.OTHER, (), "a queue entry's state"),
             ("n", "c"): M.Site(M.OTHER, (), "a run's state"), ("n", "d"): M.Site(M.COPY, (), "a copy"),
             ("n", "e"): M.Site(M.TICKET, ("assign",), "assigns")}
    found = {key: {"assign"} for key in table}
    items = M.other_machine_items(found, table)
    assert [(i["module"], i["symbol"]) for i in items] == [("m", "a"), ("n", "c")]
    assert "a queue entry's state" in items[0]["why"] and "are in no table this reading reads" in items[0]["why"]
    assert M.other_machine_items({("m", "a"): {"assign"}}, {}) == []  # missing: a site the table does not know
    assert M.other_machine_items({}, table) == []  # missing: no unchecked write at all


def test_a_machine_with_no_check_cited_claims_nothing_and_one_with_a_second_state_set_is_lower_bound():
    quiet = M._small("planted-states", "aew.engine.configuration", ())
    assert {r.coverage["label"] for r in quiet} == {"unknown"}  # configuration holds no second tuple; no check is cited
    cited = M._small("planted-states", "aew.engine.configuration", ("tests/integration/x.py::t",))
    assert {r.coverage["label"] for r in cited} == {"complete-by-construction"}
    live = M._small("planted-states", "aew.harness.usage_live", ("tests/integration/x.py::t",))
    assert {r.coverage["label"] for r in live} == {"lower-bound"}  # PROMPT_STATES, a second tuple of the module


# ---------------------------------------------------------------------------------------- the guard table

def test_an_engine_that_no_longer_holds_its_guard_table_is_a_refusal_naming_where_it_was(monkeypatch):
    import aew.engine.api as api

    class Bare:
        def __init__(self, repo_root: Any, aew_root: Any) -> None:
            self.repo_root = repo_root

    monkeypatch.setattr(api, "Engine", Bare)
    with pytest.raises(C.ReferenceError, match="no longer holds its guard table at _units.guards"):
        M.guard_table()
    monkeypatch.undo()
    table, queries = M.guard_table()  # the right case: the real Engine gives its table
    assert table and isinstance(queries, dict)
