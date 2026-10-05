"""The future-work register is structured data (E30): `docs/implementation/future-work.yaml` is the source and
`future-work.md` the rendered view, kept identical by `tools/register.py`. Every row has a unique id and every open
row outside the gates and questions tables starts its target column with one of the register's own targets.
The file keeps nothing that every change edits: no change log in the preamble, and §Closed in id order, so concurrent
register changes merge."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("register", ROOT / "tools" / "register.py")
assert _spec is not None and _spec.loader is not None
register = importlib.util.module_from_spec(_spec)
sys.modules["register"] = register
_spec.loader.exec_module(register)

DATA = yaml.safe_load(register.YAML.read_text(encoding="utf-8"))


def test_the_markdown_is_what_the_yaml_renders():
    assert DATA["schema"] == register.SCHEMA
    rendered = register.render_markdown(DATA)
    assert rendered == register.MD.read_text(encoding="utf-8"), (
        "docs/implementation/future-work.md is not rendered from future-work.yaml: edit the YAML and run "
        "`python tools/register.py render`")


def test_the_yaml_round_trips_through_the_markdown():
    """Parsing the rendered markdown gives back the same data, so either file could be reconstructed from the other."""
    assert register.parse_markdown(register.render_markdown(DATA)) == DATA


def test_ids_are_unique_and_open_rows_carry_a_target():
    assert register.problems(DATA) == []


def test_every_section_has_the_columns_its_rows_use():
    for section in DATA["sections"]:
        for row in section["rows"]:
            assert list(row) == section["columns"], f"§{section['number']}: {next(iter(row.values()))}"


def test_the_yaml_is_normalized():
    """What `render` would write is what is committed: §Closed in id order and the dumper's layout, so `check` and this
    test agree and a merge is resolved in one place."""
    assert register.dump(register.normalize(copy.deepcopy(DATA))) == register.YAML.read_text(encoding="utf-8"), (
        "docs/implementation/future-work.yaml is not normalized: run `python tools/register.py render`")


def test_ids_sort_naturally():
    key = register.id_key
    assert key("E8") < key("E10") < key("E100")
    assert key("F20") < key("F20.1") < key("F20.2") < key("F20.10") < key("F21")
    assert key("E39") < key("F1") < key("O1") < key("Q1") < key("U1")  # letters first, as the register numbers them
    assert key("Q9") < key("Q9 (decisions)") < key("Q9 (reconciliation)") < key("Q10")
    assert key("Gate") > key("U99")  # anything that is not an id sorts after every id


def test_closed_rows_are_gates_first_then_id_order_and_an_appended_row_is_reported():
    closed = next(s for s in DATA["sections"] if s["title"].startswith("Closed"))
    ids = [next(iter(r.values())) for r in closed["rows"]]
    gates = [i for i in ids if i == "Gate"]
    assert ids[:len(gates)] == gates, "the Gate rows come first"
    rest = ids[len(gates):]
    assert rest == sorted(rest, key=register.id_key) and "Gate" not in rest
    # a row appended in closing order (where every change used to append) is a problem until render sorts it
    data = copy.deepcopy(DATA)
    section = next(s for s in data["sections"] if s["title"].startswith("Closed"))
    section["rows"].append({c: ("E0" if c == "#" else "x") for c in section["columns"]})  # an id nobody uses
    assert any("not in id order" in p for p in register.problems(data))
    assert register.problems(register.normalize(data)) == []
    assert next(iter(register.normalize(data)["sections"][-1]["rows"][len(gates)].values())) == "E0"


def test_a_change_log_in_the_preamble_is_reported():
    """The 'Last updated' line that every change edited (and every pair of changes conflicted on) must not return."""
    assert "Last updated" not in DATA["preamble"]
    data = copy.deepcopy(DATA)
    data["preamble"] += "\n\n*Last updated: 2026-10-05 (something).*"
    assert any("change log" in p for p in register.problems(data))
