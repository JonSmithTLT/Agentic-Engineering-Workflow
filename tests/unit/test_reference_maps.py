"""The module page and the two maps of the generated reference (STG-12 S12-2, family 7 and the maps), planted.

``modules.page`` is drawn from the module records, ``pages.data_flow_page`` and ``pages.state_maps_page`` from an index
alone (``tools/reference_families/pages.py``): the planted index here is a dict of the shape ``build_index`` returns, so
the tests read no repository file. What the live tree gives is held by ``tests/unit/test_reference.py`` (the committed
reference is what the code gives) and the guarantees about the tree by the family tests.
"""

from __future__ import annotations

import copy
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, modules, pages
    finally:
        sys.path.remove(here)
    return common, modules, pages


C, M, P = _tools()


def table(text: str, heading: str) -> dict[str, list[str]]:
    """The rows of the table under a heading (a regular expression), by first cell, each as the cells after it."""
    start = re.search(rf"^## {heading}$", text, re.M)
    assert start, heading
    section = text[start.end():].split("\n## ", 1)[0]
    return {cells[0]: cells[1:] for cells in ([c.strip() for c in ln.strip("|").split("|")]
                                                for ln in section.splitlines() if ln.startswith("| `"))}


def chart(text: str) -> list[str]:
    return [ln.strip() for ln in text.split("```mermaid\n", 1)[1].split("```", 1)[0].splitlines()]


# ---------------------------------------------------------------------------------------------------- the module page

def module(name: str, *imports: str, package: bool = False, unresolved: tuple[dict, ...] = ()) -> Any:
    return M.Module(name, name.replace(".", "/") + ".py", package, tuple(imports), unresolved)


MODS = [
    module("aew", package=True),
    module("aew.util"),
    module("aew.engine", package=True),
    module("aew.engine.base", "aew.util"),
    module("aew.engine.store", "aew.engine.base", "aew.util"),
    module("aew.cli", "aew.engine.store", package=True),
    module("aew.cli.main", "aew.engine.store", "aew.util", unresolved=(
        C.unresolved_item("aew.cli.main", "load", "importlib.import_module with a computed module name"),)),
]
GROUPS = {"aew": ["aew", "aew.util"], "aew.cli": ["aew.cli", "aew.cli.main"],
          "aew.engine": ["aew.engine", "aew.engine.base", "aew.engine.store"]}


def by_module(text: str) -> dict[str, list[str]]:
    """Every module's row of every group table: [imports, imported by]."""
    found = {}
    for heading in re.findall(r"^## (`aew[\w.]*` \(\d+\))$", text, re.M):
        found.update(table(text, re.escape(heading)))
    return {name.strip("`"): cells for name, cells in found.items()}


def test_a_module_is_listed_under_its_second_level_package_or_the_top():
    packages = frozenset(m.name for m in MODS if m.is_package)
    assert {m.name: M.group_of(m.name, packages) for m in MODS} == {
        name: g for g, names in GROUPS.items() for name in names}


def test_a_modules_row_lists_its_imports_and_its_importers_and_says_so_when_it_has_none():
    rows = by_module(M.page(MODS))
    assert rows["aew.engine.store"] == ["`aew.engine.base`, `aew.util`", "`aew.cli`, `aew.cli.main`"]
    assert rows["aew.util"] == ["-", "`aew.cli.main`, `aew.engine.base`, `aew.engine.store`"]
    assert rows["aew"] == ["-", "-"], "no edge in either direction says so in both columns"


def test_the_importers_of_a_module_are_the_inverse_of_its_imports():
    rows = by_module(M.page(MODS))
    assert set(rows) == {m.name for m in MODS}

    def names(cell: str) -> list[str]:
        return [] if cell == "-" else [n.strip("`") for n in cell.split(", ")]

    for name, (imports, importers) in rows.items():
        assert names(importers) == sorted(x for x, (theirs, _) in rows.items() if name in names(theirs)), name
        assert names(imports) == sorted(set(names(imports)))


def test_the_packages_table_lists_the_other_groups_each_imports_from_and_is_imported_by():
    text = M.page(MODS)
    assert table(text, "Packages") == {
        "`aew`": ["2", "-", "`aew.cli`, `aew.engine`"],
        "`aew.cli`": ["2", "`aew`, `aew.engine`", "-"],
        "`aew.engine`": ["3", "`aew`", "`aew.cli`"]}
    edges = sum(len(m.imports) for m in MODS)
    assert f"{len(MODS)} modules in {len(GROUPS)} groups, {edges} import edges." in text


def test_a_dynamic_import_the_graph_cannot_follow_is_listed_and_none_says_so():
    assert "- `aew.cli.main:load`: importlib.import_module with a computed module name" in M.page(MODS)
    none = M.page([m for m in MODS if not m.unresolved]).rstrip()
    assert none.endswith("## Dynamic imports this graph cannot follow\n\nNone.")


def test_the_module_page_is_the_same_whatever_order_the_modules_come_in():
    assert M.page(MODS) == M.page(list(reversed(MODS)))


# ---------------------------------------------------------------------------------------------------- the data-flow map

def rec(family: str, fact: dict, label: str = "lower-bound", **more) -> dict:
    return {"family": family, "fact": fact, "coverage": {"label": label}, **more}


def writer(module_: str, symbol: str, *entry_points: str) -> dict:
    return {"module": module_, "symbol": symbol, "entry_points": list(entry_points), "entry_kinds": [],
            "mechanism": "direct", "via": []}


def layout(prefix: str, readers: Sequence[tuple[str, str]] = (), **flags) -> dict:
    return rec("layout", {"prefix": prefix, "readers": [{"module": m, "symbol": s} for m, s in readers],
                          "store": False, "masked_by_containment": False, "git_ignored": False, **flags})


def planted() -> dict:
    """Two processes; `state` (the store), `local` (masked) and `docs`; a write of each reach, a read joined through a
    writer item, one through a lock-free member and one that joins nothing; the writes outside and unplaced."""
    return {"records": {
        "entry-points:aew": rec("entry-points", {"entry_point": "aew", "kind": "store_writer", "reason": "the CLI"}),
        "entry-points:aew dash": rec("entry-points", {"entry_point": "aew dash", "kind": "non_writer",
                                                       "reason": "the reader"}),
        "layout:state": layout("state", [("m.reads", "viaLockFree"), ("m.cold", "nobody")], store=True),
        "layout:state/log": layout("state/log", [("m.cold", "nobody")], store=True),
        "layout:local": layout("local", [("m.writes", "put")], masked_by_containment=True, git_ignored=True),
        "layout:docs": layout("docs"),
        "writers:state": rec("writers", {"prefix": "state", "writers": [writer("m.writes", "commit", "aew")]}),
        "writers:local": rec("writers", {"prefix": "local", "writers": [
            writer("m.writes", "put", "aew", "aew dash"), writer("m.hidden", "stash")]}),
        "writers:outside:m.o:f:open": rec("writers", {"mechanism": "direct", "primitive": "open", "root": "elsewhere"}),
        "writers:unresolved:m.u:g:open": rec("writers", {"mechanism": "direct", "primitive": "open", "reason": "x"}),
        "concurrency:lock-free:m.reads:viaLockFree": rec("concurrency", {
            "module": "m.reads", "symbol": "viaLockFree", "entry_points": ["aew dash"]}),
    }}


def test_a_write_is_an_entry_points_pair_with_an_entry_and_each_edge_counts_its_functions():
    lines = chart(P.data_flow_page(planted()))
    assert 'proc_aew -->|"1 function"| path_state' in lines
    assert 'proc_aew -->|"1 function"| path_local' in lines and 'proc_aew_dash -->|"1 function"| path_local' in lines
    assert 'no_writer -->|"1 function"| path_local' in lines, "a writer item with no entry point is drawn, apart"
    assert not any(ln.startswith("no_writer") and "path_state" in ln for ln in lines)


def test_a_read_is_drawn_only_where_a_record_reaches_the_reading_function_from_an_entry_point():
    lines = chart(P.data_flow_page(planted()))
    assert 'path_local -.->|"1 function"| proc_aew' in lines, "m.writes.put is reached from `aew` by its writer item"
    assert 'path_local -.->|"1 function"| proc_aew_dash' in lines
    assert 'path_state -.->|"1 function"| proc_aew_dash' in lines, "m.reads.viaLockFree: a lock-free member"
    assert 'path_state -.->|"1 function"| no_reader' in lines, "m.cold.nobody joins nothing, once for two sub-entries"
    assert 'path_state -.->|"1 function"| proc_aew' not in lines


def test_the_entries_are_grouped_by_what_the_layout_says_of_them_and_a_sub_entry_is_drawn_under_its_top():
    box = "\n".join(chart(P.data_flow_page(planted())))
    assert re.search(r'subgraph group_store\["the control store"\]\n\s*path_state\["state"\]\n\s*end', box)
    assert re.search(r'subgraph group_masked\["masked from a contained run"\]\n\s*path_local\["local"\]\n\s*end', box)
    assert re.search(r'subgraph group_other\["other entries of \.aew"\]\n\s*path_docs\["docs"\]\n\s*end', box)
    assert "path_state_log" not in box, "`state/log` is under `state`: the map is drawn by the top-level entry"


def test_what_is_not_drawn_is_counted_from_the_records_and_the_boundaries_no_record_states_are_said():
    text = P.data_flow_page(planted())
    assert "Writes by functions the call graph attributes to no entry point: 1 (entry, function) pairs" in text
    assert "Reads by functions no record reaches from an entry point: 1 (entry, function) pairs" in text
    assert "1 write sites outside `.aew` and 1 write sites this reading could not place" in text
    assert "The bridge and the network. No record attributes" in text
    rows = table(text, "Entries of `.aew`")
    assert rows["`local`"] == ["masked from a contained run", "`aew` (1), `aew dash` (1)",
                               "`aew` (1), `aew dash` (1)", "1", "0"]
    assert rows["`state`"] == ["the control store", "`aew` (1)", "`aew dash` (1)", "0", "1"]
    assert rows["`docs`"] == ["other entries of .aew", "-", "-", "0", "0"]


def test_the_data_flow_page_is_a_function_of_the_index_alone_and_the_same_in_any_record_order():
    index = planted()
    before = copy.deepcopy(index)
    shuffled = {"records": dict(reversed(list(index["records"].items())))}
    assert P.data_flow_page(index) == P.data_flow_page(shuffled)
    assert index == before


def test_a_record_the_map_cannot_read_is_refused_and_never_dropped():
    index = planted()
    index["records"]["writers:state"]["fact"]["writers"][0]["entry_points"] = ["aew gone"]
    with pytest.raises(C.ReferenceError, match="no `entry-points` record names"):
        P.data_flow_page(index)
    index = planted()
    index["records"]["writers:stray"] = rec("writers", {"mechanism": "direct", "primitive": "open"})
    with pytest.raises(C.ReferenceError, match="does not read"):
        P.data_flow_page(index)


def test_two_names_that_make_one_diagram_id_are_refused_and_not_merged():
    index = planted()
    index["records"]["entry-points:aew-dash"] = rec("entry-points", {"entry_point": "aew-dash", "kind": "non_writer",
                                                                      "reason": "x"})
    with pytest.raises(C.ReferenceError, match="make the diagram id 'proc_aew_dash'"):
        P.data_flow_page(index)


def test_a_label_cannot_close_a_quoted_label():
    assert P._label('a "b"\nc') == "a #quot;b#quot; c"


# ------------------------------------------------------------------------------------------------ the state maps

def state(name: str, **more) -> dict:
    return rec("states", {"state": name, "phase": 0, "terminal": False, **more}, "complete-by-construction")


def edge(a: str, b: str, via: str = "transition", guard=None, reason=False, label="complete-by-construction",
         **more) -> dict:
    fact = {"from": a, "to": b, "via": via, "guard": guard, "reason_required": reason, **more}
    return rec("transitions", fact, label)


def exits_item(why: str) -> dict:
    return {"exits": {"label": "lower-bound", "unresolved": [{"module": "m", "symbol": "S", "why": why}]}}


def machines() -> dict:
    return {"records": {
        "states:NEW": state("NEW", phase=0), "states:RUN": state("RUN", phase=1),
        "states:DONE": state("DONE", phase=2, terminal=True), "states:LOST": state("LOST", phase=None),
        "transitions:NEW->RUN": edge("NEW", "RUN", guard="ready"),
        "transitions:RUN->DONE": edge("RUN", "DONE", via="verify.ingest", also=["integrate.validate"]),
        "transitions:RUN->LOST": edge("RUN", "LOST", reason=True, label="lower-bound"),
        "configuration-states:ABSENT": rec("configuration-states", {"state": "ABSENT", "position": 0, "exits": []},
                                           fact_coverage=exits_item("no edge table: planted")),
        "configuration-states:SEEN": rec("configuration-states", {"state": "SEEN", "position": 1, "exits": []}),
        "usage-live-states:live": rec("usage-live-states", {"state": "live", "position": 0, "exits": []}),
    }}


def sections(text: str) -> dict[str, str]:
    return {h: body for h, body in re.findall(r"^## (.+)\n((?:.|\n)*?)(?=^## |\Z)", text, re.M)}


def test_the_ticket_machine_draws_every_state_every_edge_with_its_label_and_its_terminal_states():
    body = sections(P.state_maps_page(machines()))["Ticket"]
    lines = chart(body)
    assert 'state "NEW" as st_new' in lines and 'state "LOST" as st_lost' in lines
    assert "st_done --> [*]" in lines and "st_run --> [*]" not in lines, "only a terminal state is closed"
    assert "st_new --> st_run : transition [ready]" in lines, "the guard follows the operation"
    assert "st_run --> st_done : verify.ingest / integrate.validate" in lines, "the other operations the code names"
    assert "st_run --> st_lost : transition (reason)" in lines, "an edge that needs a reason says so"
    assert "4 states, 3 edges: 2 complete-by-construction, 1 lower-bound." in body


def test_a_machine_with_no_edge_table_is_drawn_as_its_states_alone_and_says_why_from_its_record():
    text = P.state_maps_page(machines())
    config = sections(text)["Configuration document"]
    assert chart(config) == ["stateDiagram-v2", "direction LR", 'state "ABSENT" as st_absent',
                             'state "SEEN" as st_seen']
    assert 'The records say "no edge table: planted", so no edge is drawn.' in config
    assert "No edge is drawn." in sections(text)["Live usage"], "a record with no reason still draws no edge"


def test_a_state_with_an_exit_or_an_edge_to_no_state_is_refused_and_never_dropped():
    index = machines()
    index["records"]["usage-live-states:live"]["fact"]["exits"] = ["final"]
    with pytest.raises(C.ReferenceError, match="has exits, which are not drawn"):
        P.state_maps_page(index)
    index = machines()
    index["records"]["transitions:NEW->GONE"] = edge("NEW", "GONE")
    with pytest.raises(C.ReferenceError, match="has a state no record has"):
        P.state_maps_page(index)
    index = machines()
    del index["records"]["configuration-states:ABSENT"], index["records"]["configuration-states:SEEN"]
    with pytest.raises(C.ReferenceError, match="no `configuration-states` record"):
        P.state_maps_page(index)


def test_the_state_maps_are_the_same_in_any_record_order_and_never_change_the_index_they_read():
    index = machines()
    before = copy.deepcopy(index)
    shuffled = {"records": dict(reversed(list(index["records"].items())))}
    assert P.state_maps_page(index) == P.state_maps_page(shuffled)
    assert index == before


# ------------------------------------------------------------------------------------------------ the whole reference

def test_the_two_maps_and_the_module_page_are_in_the_readmes_listing_of_the_pages():
    text = P.readme({"counts": {}}, {"modules.md": "# Modules\n", P.DATA_FLOW: "# Data flow\n",
                                     P.STATE_MAPS: "# State transition maps\n"})
    assert "- [modules.md](modules.md): Modules" in text and f"- [{P.DATA_FLOW}]({P.DATA_FLOW}): Data flow" in text
    assert f"- [{P.STATE_MAPS}]({P.STATE_MAPS}): State transition maps" in text
