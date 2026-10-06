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
    section["rows"].append({c: ("A0" if c == "#" else "x") for c in section["columns"]})  # unused, sorts first
    assert any("not in id order" in p for p in register.problems(data))
    assert register.problems(register.normalize(data)) == []
    assert next(iter(register.normalize(data)["sections"][-1]["rows"][len(gates)].values())) == "A0"


def test_a_change_log_in_the_preamble_is_reported():
    """The 'Last updated' line that every change edited (and every pair of changes conflicted on) must not return."""
    assert "Last updated" not in DATA["preamble"]
    data = copy.deepcopy(DATA)
    data["preamble"] += "\n\n*Last updated: 2026-10-05 (something).*"
    assert any("change log" in p for p in register.problems(data))


def test_gate_rows_sort_by_the_column_named_closed_wherever_it_is():
    section = {"title": "Closed", "columns": ["#", "By", "Closed", "Was"], "rows": [
        {"#": "Gate", "By": "b", "Closed": "2026-10-05", "Was": "later"},
        {"#": "E2", "By": "b", "Closed": "2026-10-03", "Was": "x"},
        {"#": "Gate", "By": "b", "Closed": "2026-10-01", "Was": "earlier"},
    ]}
    assert [r["Was"] for r in register.closed_order(section)] == ["earlier", "later", "x"]


def test_a_clean_merge_that_leaves_closed_unsorted_is_still_caught():
    """Two branches that each appended a closed row merge without conflict, unsorted and with a stale markdown; only
    `check` (and CI) catch that, so `render` runs after every sync, not only after a conflict."""
    data = copy.deepcopy(DATA)
    section = next(s for s in data["sections"] if s["title"].startswith("Closed"))
    section["rows"] += [{c: ("U0" if c == "#" else "x") for c in section["columns"]},
                        {c: ("E0" if c == "#" else "x") for c in section["columns"]}]
    assert register.dump(data) != register.dump(register.normalize(copy.deepcopy(data)))
    assert any("not in id order" in p for p in register.problems(data))


# ------------------------------------------------------------------------------------------------------- decisions due

DUE = yaml.safe_load(register.DUE_YAML.read_text(encoding="utf-8"))


def test_the_decisions_due_view_is_what_its_yaml_renders_and_is_current():
    """The operator asked for one place that says what decisions are due by when and what they block (2026-10-06):
    `decisions-due.md` is rendered from its YAML, and every item still points at an open register row."""
    assert register.render_due(DUE) == register.DUE_MD.read_text(encoding="utf-8"), (
        "docs/implementation/decisions-due.md is not rendered from decisions-due.yaml: run "
        "`python tools/register.py render`")
    assert register.due_problems(DATA, DUE) == []


def test_an_item_goes_stale_when_its_row_or_a_blocked_row_closes():
    data = copy.deepcopy(DATA)
    closed = next(s for s in data["sections"] if s["title"].startswith("Closed"))
    questions = next(s for s in data["sections"] if s["number"] == 4)
    q12 = next(r for r in questions["rows"] if r["#"] == "Q12")
    questions["rows"].remove(q12)
    closed["rows"].append({c: "x" for c in closed["columns"]} | {closed["columns"][0]: "Q12"})
    problems = register.due_problems(data, DUE)
    assert any("Q12 is closed" in p for p in problems), problems
    due = copy.deepcopy(DUE)
    due["items"][0]["blocks"] = ["F2"]  # closed in M4-B
    assert any("blocks F2, which is closed" in p for p in register.due_problems(DATA, due))


def test_every_open_question_and_designer_row_has_an_item():
    due = copy.deepcopy(DUE)
    due["items"] = [i for i in due["items"] if i["row"] not in {"Q7", "U10"}]
    problems = register.due_problems(DATA, due)
    assert any("Q7 is an open question with no item" in p for p in problems), problems
    assert any("U10 waits for the designer" in p for p in problems), problems


def test_an_item_names_a_known_due_point_owner_and_need():
    due = copy.deepcopy(DUE)
    due["items"][0] |= {"due": "next week", "owner": "someone", "needs": "vibes"}
    problems = " ".join(register.due_problems(DATA, due))
    assert "due is one of" in problems and "owner is one of" in problems and "needs is one of" in problems


def test_the_view_lists_the_soonest_first():
    owed = register.render_due(DUE).split("## Owed, soonest first")[1].split("## Blocked")[0]
    dues = [line.split(" | ")[0].removeprefix("| ") for line in owed.splitlines() if line.startswith("| ")][1:]
    order = [register.DUE_ORDER.index(d) for d in dues]
    assert len(dues) == len(DUE["items"]) and order == sorted(order)


def test_a_question_needs_its_own_item_and_a_blocked_designer_row_waits_for_its_blocker():
    """PR #104 review, 1: an open question is covered only by its own item; a **Designer** row may instead be blocked by
    one (F6 waits for Q4's decision)."""
    due = copy.deepcopy(DUE)
    q14 = next(i for i in due["items"] if i["row"] == "Q14")
    due["items"].remove(q14)
    next(i for i in due["items"] if i["row"] == "Q12")["blocks"].append("Q14")
    assert any("Q14 is an open question with no item of its own" in p for p in register.due_problems(DATA, due))
    assert not any("F6" in p for p in register.due_problems(DATA, DUE))  # blocked by Q4's item


def test_a_malformed_item_is_named_never_a_crash():
    """PR #104 review, 2: the renderer tolerates what the check refuses, so `check` names the problem."""
    due = copy.deepcopy(DUE)
    due["items"][0] = {"row": "Q12", "due": "soon"}
    text = register.render_due(due)
    assert "| soon |" in text
    assert any("missing needs, owner, what" in p for p in register.due_problems(DATA, due))


def test_items_stay_in_order_and_one_row_has_one_item():
    """PR #104 review, 4: items are kept in (due, row) order, like §Closed, so concurrent additions land apart; a merge
    that leaves two items for one row is refused."""
    assert DUE["items"] == sorted(DUE["items"], key=register.due_key)
    due = copy.deepcopy(DUE)
    due["items"].append(copy.deepcopy(due["items"][0]))
    problems = register.due_problems(DATA, due)
    assert any("not in (due, row) order" in p for p in problems), problems
    due = register.normalize_due(due)
    assert any(f"{due['items'][0]['row']} has 2 items" in p for p in register.due_problems(DATA, due))
    assert register.DUE_ORDER.index("M4-D") < register.DUE_ORDER.index("Gate: before F15.2 ships") \
        < register.DUE_ORDER.index("M4-E")  # docs/README.md's order (review, 3)
