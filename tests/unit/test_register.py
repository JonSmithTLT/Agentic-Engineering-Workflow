"""The future-work register is structured data (E30): `docs/implementation/future-work.yaml` is the source and
`future-work.md` the rendered view, kept identical by `tools/register.py`. Every row has a unique id and every open
row outside the gates and questions tables starts its target column with one of the register's own targets.
The file keeps nothing that every change edits: no change log in the preamble, and §Closed in id order, so concurrent
register changes merge."""

from __future__ import annotations

import copy
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
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


def test_a_cell_written_over_several_lines_round_trips_and_one_that_would_split_its_row_is_reported():
    """Each row is a block (a heading, then one paragraph per cell) so that changes to neighbouring rows merge: a cell
    may run over several lines, but a blank line inside it, or a heading cell over two lines, would split the block."""
    data = copy.deepcopy(DATA)
    data["sections"][1]["rows"][0]["Notes"] = "first line\nsecond line"
    assert register.parse_markdown(register.render_markdown(data)) == data
    assert register.problems(data) == []
    data["sections"][1]["rows"][0]["Notes"] = "one paragraph\n\nanother"
    assert any("holds a blank line" in p for p in register.problems(data))
    data = copy.deepcopy(DATA)
    data["sections"][1]["rows"][0]["#"] = "F3\nF4"
    assert any("one non-empty line" in p for p in register.problems(data))


def test_a_cell_or_item_field_ending_in_newlines_is_settled_by_render():
    """A YAML literal block (`Notes: |`) ends in a newline, which the page cannot carry; two or more made `dump` write a
    keep-chomping scalar that grew on every render. `render` strips them, so the page parses back exactly and a second
    render changes nothing (review of PR #151, 4)."""
    data = copy.deepcopy(DATA)
    data["sections"][1]["rows"][0]["Notes"] = yaml.safe_load("v: |\n  first line\n  second line\n")["v"]
    data["sections"][1]["rows"][1]["Work"] += "\n\n\n"
    settled = register.normalize(data)
    assert settled["sections"][1]["rows"][0]["Notes"] == "first line\nsecond line"
    assert register.parse_markdown(register.render_markdown(settled)) == settled
    assert register.dump(register.normalize(yaml.safe_load(register.dump(settled)))) == register.dump(settled)
    due = copy.deepcopy(DUE)
    due["items"][-1]["what"] = "x\n\n"
    text = register.dump(register.normalize_due(due))
    assert yaml.safe_load(text)["items"][-1]["what"] == "x"
    assert register.dump(register.normalize_due(yaml.safe_load(text))) == text


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
    assert key("Q14") < key("STG-05") < key("STG-12") < key("U1")  # a build stage sorts by its letters, then its number


def test_a_build_stage_is_an_id_in_exactly_one_form():
    """One row per build stage of the architecture map, named as the map names it (designer, D-CS1-12)."""
    assert all(register.ID_RE.match(i) for i in ("F2", "F15.5", "STG-05", "STG-12"))
    assert not any(register.ID_RE.match(i) for i in ("STG-5", "STG-005", "STG05", "STGX-05", "stg-05", "F-2"))
    assert {"STG-03", "STG-05", "STG-12", "STG-13", "STG-15"} <= {r["id"] for r in register.rows(DATA)}
    assert all(r["target"] == "Stage" for r in register.rows(DATA) if (r["id"] or "").startswith("STG-"))


def test_a_hold_group_is_an_id_in_exactly_one_form():
    """One row per adopted position, named by its number (``HOLD-09`` for A-09): the register rebaseline, 2026-10-24."""
    assert all(register.ID_RE.match(i) for i in ("HOLD-02", "HOLD-21"))
    assert not any(register.ID_RE.match(i) for i in ("HOLD-2", "HOLD-002", "HOLD02", "hold-02", "HOLDS-02"))
    assert register.id_key("F99") < register.id_key("HOLD-02") < register.id_key("HOLD-21") < register.id_key("O1")
    groups = [r for r in register.rows(DATA) if (r["id"] or "").startswith("HOLD-")]
    assert groups and all(r["target"] == "After the trace" for r in groups)


def test_a_row_outside_the_gates_is_headed_by_its_id_or_a_labelled_one():
    """A heading that is not an id would render, yet get no pointer, no note and no place in the id order: a near miss
    of a stage id (``STG-6``, ``STG05``) or of a letter-number one (``F-2``) is refused by ``problems``, not left to be
    found by the one who looks for the pointer (review of #240, m2). The closed rows that carry a label and the Gate
    rows stay, and so do the §1 gates, whose first cell is their name."""
    labelled = {"E33 (part)", "Q9 (decisions)", "Q9 (reconciliation)", "Gate"}
    heads = {next(iter(r.values())) for s in DATA["sections"] if s["number"] != 1 for r in s["rows"]}
    assert labelled <= heads and register.problems(DATA) == []
    near_misses = ("STG-6", "STG-5", "STG-005", "STG05", "STGX-05", "stg-05", "F-2", "F2 ()", "Q9(x)", "Q9 (a) (b)",
                   "HOLD-2", "HOLD-002", "HOLD02", "hold-02")
    for number, closed in ((2, False), (None, True)):
        for head in near_misses:
            data = copy.deepcopy(DATA)
            section = next(s for s in data["sections"] if s["title"].startswith("Closed") == closed
                           and (closed or s["number"] == number))
            row = dict(section["rows"][-1])
            row[section["columns"][0]] = head
            section["rows"].append(row)
            found = register.problems(register.normalize(data))
            assert [p for p in found if repr(head) in p] == found and len(found) == 1, (number, head, found)


def test_a_target_is_read_as_the_longest_register_target_it_starts_with():
    """``TARGET_RE`` is derived from ``TARGETS``, the longest name first and nothing ending a match: a target that
    starts another (``M4`` and ``M4 candidate`` before the rebaseline) is read as the longer one, and a target followed
    by more bold text (``**V-01, I-6.**``) still reads as the target (review of #240, m3)."""
    def read(cell: str) -> str | None:
        m = register.TARGET_RE.match(cell)
        return m.group(1) if m else None

    named = [t for t in register.TARGETS if t != "Gate"]
    assert [read(f"**{t}.** x") for t in named] == named
    assert read("**Gate: before internal alpha** (§1)") == "Gate: before internal alpha"
    assert all(read(f"**{longer}.** x") == longer for longer in named for shorter in named
               if longer != shorter and longer.startswith(shorter))
    assert read("**V-01, I-6.** x") == "V-01" and read("**Now**: x") == "Now"
    assert read("**Gate.** x") is None and read("Now. x") is None
    assert read("**M4.** x") is None and read("**M4 candidate.** x") is None  # gone with the rebaseline
    for target in named:  # the reader and a plain prefix test agree on every open row
        starting = sum(row[s["target_column"]].startswith(f"**{target}") for s in DATA["sections"]
                       if s.get("target_column") and not s["title"].startswith("Closed") for row in s["rows"])
        assert starting == sum(r["target"] == target for r in register.rows(DATA)), target


def test_the_preambles_target_table_names_the_register_targets():
    """The preamble tells the reader the targets; ``TARGETS`` is what the tool reads. ``Gate: …`` stands for ``Gate``
    (review of #240, m3: a target added to one and forgotten in the other was caught by nothing)."""
    cells = [line.split("|")[1] for line in DATA["preamble"].splitlines() if line.startswith("| **")]
    named = ["Gate" if n.startswith("Gate:") else n for cell in cells for n in re.findall(r"\*\*(.+?)\*\*", cell)]
    assert sorted(named) == sorted(register.TARGETS)


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


# The rebaseline left no open question (§4 is empty) and no row targeted **Designer**, so the rules about them are
# proved on a copy of the register with one of each planted: Q99, a question, and E999, a Designer row.
QUESTION, DESIGNER_ROW = "Q99", "E999"


def _with_a_question_and_a_designer_row() -> dict[str, Any]:
    data = copy.deepcopy(DATA)
    questions = next(s for s in data["sections"] if s["number"] == 4)
    questions["rows"].append({"#": QUESTION, "Question": "x", "Owner": "designer", "Source": "x"})
    follow_ups = next(s for s in data["sections"] if s["number"] == 6)
    follow_ups["rows"].append({"#": DESIGNER_ROW, "Work": "x", "Source": "x", "When": "**Designer**: x", "Notes": ""})
    return register.normalize(data)


def _item(row: str, **extra: Any) -> dict[str, Any]:
    return {"row": row, "needs": "decision", "owner": "designer", "due": "Unscheduled", "what": "x"} | extra


def test_an_item_goes_stale_when_its_row_or_a_blocked_row_closes():
    data = copy.deepcopy(DATA)
    closed = next(s for s in data["sections"] if s["title"].startswith("Closed"))
    follow_ups = next(s for s in data["sections"] if s["number"] == 6)
    e72 = next(r for r in follow_ups["rows"] if r["#"] == "E72")
    follow_ups["rows"].remove(e72)
    closed["rows"].append({c: "x" for c in closed["columns"]} | {closed["columns"][0]: "E72"})
    problems = register.due_problems(data, DUE)
    assert any("E72 is closed" in p for p in problems), problems
    due = copy.deepcopy(DUE)
    due["items"][0]["blocks"] = ["F2"]  # closed in M4-B
    assert any("blocks F2, which is closed" in p for p in register.due_problems(DATA, due))


def test_every_open_question_and_designer_row_has_an_item():
    data, due = _with_a_question_and_a_designer_row(), copy.deepcopy(DUE)
    problems = register.due_problems(data, due)
    assert any(f"{QUESTION} is an open question with no item" in p for p in problems), problems
    assert any(f"{DESIGNER_ROW} waits for the designer" in p for p in problems), problems
    due["items"] = register.normalize_due({"items": [*due["items"], _item(QUESTION), _item(DESIGNER_ROW)]})["items"]
    assert register.due_problems(data, due) == []


def test_an_item_names_a_known_due_point_owner_and_need():
    due = copy.deepcopy(DUE)
    due["items"][0] |= {"due": "next week", "owner": "someone", "needs": "vibes"}
    problems = " ".join(register.due_problems(DATA, due))
    assert "due is one of" in problems and "owner is one of" in problems and "needs is one of" in problems


def test_the_view_lists_the_soonest_first():
    owed = register.render_due(DUE).split("## Owed, soonest first")[1].split("## Blocked")[0]
    dues = [line.removeprefix("**Due by:** ").split(" · ")[0] for line in owed.splitlines()
            if line.startswith("**Due by:** ")]
    order = [register.DUE_ORDER.index(d) for d in dues]
    assert len(dues) == len(DUE["items"]) and order == sorted(order)


def test_a_question_needs_its_own_item_and_a_blocked_designer_row_waits_for_its_blocker():
    """PR #104 review, 1: an open question is covered only by its own item; a **Designer** row may instead be blocked by
    one (F6 waited for Q4's decision)."""
    data, due = _with_a_question_and_a_designer_row(), copy.deepcopy(DUE)
    other = next(i for i in due["items"] if i["row"] == "E4")
    other["blocks"] = [QUESTION]  # another item blocking the question is no item of the question's own
    assert any(f"{QUESTION} is an open question with no item of its own" in p for p in register.due_problems(data, due))
    other.pop("blocks")
    due["items"] = register.normalize_due({"items": [*due["items"], _item(QUESTION, blocks=[DESIGNER_ROW])]})["items"]
    assert register.due_problems(data, due) == []  # the Designer row is blocked by the question's item


def test_a_malformed_item_is_named_never_a_crash():
    """PR #104 review, 2: the renderer tolerates what the check refuses, so `check` names the problem."""
    due = copy.deepcopy(DUE)
    due["items"][0] = {"row": "Q11", "due": "soon"}
    text = register.render_due(due)
    assert "**Due by:** soon ·" in text
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
    order = [register.DUE_ORDER.index(d) for d in ("Now", "Contained", "V-01", "Gate: before internal alpha",
                                                   "Internal alpha", "After the trace", "Evaluation", "Unscheduled")]
    assert order == list(range(len(register.DUE_ORDER)))  # future-work.md §1's order, then the open-ended targets


def test_an_incomplete_item_still_counts_as_its_rows_item():
    """PR #104 re-review, B: the missing field is the one problem; the question is not also reported as uncovered."""
    data, due = _with_a_question_and_a_designer_row(), copy.deepcopy(DUE)
    due["items"] = register.normalize_due({"items": [*due["items"], _item(QUESTION), _item(DESIGNER_ROW)]})["items"]
    next(i for i in due["items"] if i["row"] == QUESTION).pop("what")
    problems = register.due_problems(data, due)
    assert any(f"({QUESTION}): missing what" in p for p in problems) and not any(
        f"{QUESTION} is an open question" in p for p in problems), problems


def test_check_names_only_what_is_out_of_step(monkeypatch, capsys):
    """PR #104 re-review, A: a decisions-due problem never claims the register's markdown is stale."""
    due = copy.deepcopy(DUE)
    due["items"][0]["due"] = "M4-I"
    monkeypatch.setattr(register, "load_due", lambda: due)
    assert register.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "due is one of" in out and "future-work.md differs" not in out, out


# A cell's text survives the YAML round trip. render rewrites the YAML from what it parsed, so what parsing drops or
# retypes is lost for good: "by #224" became "by" (review of #225, T1), and the re-review found five more ways (U1).
# render refuses and check reports instead (register.text_problems: lost_text on the raw tokens, strict_problems on
# the parsed values). Each case: the text, then how many problems lost_text and strict_problems each name.
LOST = {
    "kept: quoted": ("Source: 'added by #224'\n", 0, 0),
    "kept: no hash": ("Source: added by pull request 224\n", 0, 0),
    "kept: a hash inside a word": ("Source: see a#b\n", 0, 0),
    "kept: a block cell": ("Source: >-\n  added by #224\n", 0, 0),
    "kept: a section number": ("sections:\n- number: 6\n  title: Follow-ups\n", 0, 0),
    "comment": ("Source: added by #224\n", 1, 0),
    "comment on a later line": ("Work: 'quoted # stays'\nSource: plain\n  continued # lost\n", 1, 0),
    "anchor": ("Source: &ref see the record\n", 1, 0),
    "anchor and alias": ("Work: &w see\nSource: *w\n", 2, 0),
    "tag": ("Source: !!str see the record\n", 1, 0),
    "double-quoted escape": ('Source: "C:\\new folder"\n', 1, 0),
    "double-quoted line break": ('Source: "C:\n  new folder"\n', 1, 0),
    "repeated key": ("Notes: first\nNotes: second\n", 0, 1),
    "YAML 1.1 boolean": ("What: no\n", 0, 1),
    "null": ("What: ~\n", 0, 1),
    "float": ("Due: 1.10\n", 0, 1),
    "octal-looking": ("Due: 012\n", 0, 1),
    "date": ("Due: 2026-10-12\n", 0, 1),
    "a key that is not text": ("no: x\n", 0, 1),
}


@pytest.mark.parametrize("case", sorted(LOST))
def test_text_a_render_would_lose_or_change_is_named(case):
    text, raw, parsed = LOST[case]
    assert len(register.lost_text(text, "f.yaml")) == raw, register.lost_text(text, "f.yaml")
    assert len(register.strict_problems(text, "f.yaml")) == parsed, register.strict_problems(text, "f.yaml")
    assert len(register.text_problems(text, "f.yaml")) == raw + parsed


def test_a_comment_is_named_by_its_line():
    assert [p.split(":")[1] for p in register.lost_text(LOST["comment on a later line"][0], "f.yaml")] == ["3"]


E79_SOURCE = "    Source: Designer ruling, 2026-10-12, C3 (approved with amendment)\n"
PLANTED = {  # the re-review's five ways a render lost text (U1), and T1's comment, each in E79's Source
    "comment": E79_SOURCE[:-1] + " by #224\n",
    "anchor": "    Source: &ref Designer ruling C3 anchored\n",
    "tag": "    Source: !!str Designer ruling C3 tagged\n",
    "repeated key": E79_SOURCE + "    Source: Designer ruling C3 second\n",
    "YAML 1.1 boolean": "    Source: no\n",
    "double-quoted escape": '    Source: "see C:\\new folder"\n',
}


PLANTED.update({  # V1: what the dumper can only write double-quoted, which the next render would refuse
    "tab": "    Source: 'Designer ruling,\tC3'\n",
    "byte-order mark": "    Source: 'Designer ruling,﻿C3'\n",
    "noncharacter": "    Source: 'Designer ruling, C3\U0010ffff'\n",
    "space before a line break": "    Source: |-\n      Designer ruling, \n      C3\n",
})
ACCEPTED = {  # special to the reader or the emitter, yet written back unchanged: render twice is stable
    "line separator": "    Source: 'Designer ruling, C3'\n",
    "non-ASCII": "    Source: 'Designer ruling — C3, café 设计 🙂'\n",
    "hash in quotes": "    Source: 'Designer ruling, C3 by #224'\n",
    "line break before a space": "    Source: |-\n      Designer ruling,\n       C3\n",
    "leading and trailing space": "    Source: ' Designer ruling, C3 '\n",
}


@pytest.mark.parametrize("case", sorted(ACCEPTED))
def test_what_render_writes_the_next_render_accepts_unchanged(tmp_path, case):
    """V1, the class: a validator paired with a generator passes the generator's own output."""
    _register_copy(tmp_path)
    source = tmp_path / register.YAML.relative_to(register.ROOT)
    text = source.read_text(encoding="utf-8")
    source.write_text(text.replace(E79_SOURCE, ACCEPTED[case]), encoding="utf-8", newline="\n")
    assert register.render(tmp_path) == []
    once = source.read_bytes()
    assert register.render(tmp_path) == [] and source.read_bytes() == once


def test_every_authorable_value_is_refused_or_written_so_the_next_render_accepts_it():
    """The emitter's special cases, enumerated (PyYAML's analyze_scalar): every C0 and C1 control, DEL, the byte-order
    mark, the noncharacters, and a space on either side of each line break. A value an author can write (it loads from
    a single-quoted or block cell) is refused by strict_problems, or its dump passes text_problems."""
    breaks = ["\n", "\x85", " ", " "]
    specials = [chr(c) for c in [*range(0x100), 0x2028, 0x2029, 0xFEFF, 0xFFFD, 0xFFFE, 0xFFFF, 0x10FFFE, 0x10FFFF]]
    specials += [" " + b for b in breaks] + [b + " " for b in breaks]
    checked = 0
    for s in specials:
        value = f"a{s}b"
        for authored in (f"k: '{value}'\n", "k: |-\n  " + value.replace("\n", "\n  ") + "\n"):
            try:
                if yaml.safe_load(authored)["k"] != value:
                    continue
            except yaml.YAMLError:
                continue  # the reader refuses it, loudly
            checked += 1
            if not register.strict_problems(authored, "f.yaml"):
                written = register.dump({"k": value})
                assert register.text_problems(written, "f.yaml") == [], (repr(value), written)
                assert yaml.safe_load(written)["k"] == value, repr(value)
    assert checked > 200


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_render_refuses_each_way_of_losing_text_and_writes_nothing(tmp_path, case):
    """Through the real render, on a copy of the register: each planted cell is named, and every file stays
    byte-identical."""
    _register_copy(tmp_path)
    source = tmp_path / register.YAML.relative_to(register.ROOT)
    shared = [tmp_path / p.relative_to(register.ROOT) for p in (register.YAML, register.MD, register.DUE_YAML,
                                                                 register.DUE_MD)]
    text = source.read_text(encoding="utf-8")
    assert text.count(E79_SOURCE) == 1, "the planted cell's anchor (E79's Source) moved"
    source.write_text(text.replace(E79_SOURCE, PLANTED[case]), encoding="utf-8", newline="\n")
    before = [p.read_bytes() for p in shared]
    refused = register.render(tmp_path)
    assert refused and all(p.startswith("docs/implementation/future-work.yaml") for p in refused), refused
    assert [p.read_bytes() for p in shared] == before


def test_render_refuses_to_drop_authored_text_and_check_names_it(tmp_path, monkeypatch, capsys):
    """Planted in a copy of the register: an unquoted " #" leaves every file byte-identical and is named; the same text
    quoted renders and reaches the page."""
    _register_copy(tmp_path)
    source = tmp_path / register.YAML.relative_to(register.ROOT)
    shared = [tmp_path / p.relative_to(register.ROOT) for p in (register.YAML, register.MD, register.DUE_YAML,
                                                                 register.DUE_MD)]
    text = source.read_text(encoding="utf-8")
    anchor = E79_SOURCE
    assert text.count(anchor) == 1, "the planted cell's anchor (E79's Source) moved"
    source.write_text(text.replace(anchor, anchor[:-1] + " by #224\n"), encoding="utf-8", newline="\n")
    before = [p.read_bytes() for p in shared]
    refused = register.render(tmp_path)
    assert len(refused) == 1 and "future-work.yaml:" in refused[0] and "#224" in refused[0], refused
    assert [p.read_bytes() for p in shared] == before
    planted = register.source_problems(tmp_path)
    assert planted == refused
    quoted = "    Source: 'Designer ruling, 2026-10-12, C3 (approved with amendment) by #224'\n"
    source.write_text(text.replace(anchor, quoted), encoding="utf-8", newline="\n")
    assert register.render(tmp_path) == []
    assert "C3 (approved with amendment) by #224" in shared[1].read_text(encoding="utf-8")
    monkeypatch.setattr(register, "source_problems", lambda root=register.ROOT: planted)  # check reports them
    capsys.readouterr()
    assert register.main(["check"]) == 1
    assert "is a YAML comment, which render drops" in capsys.readouterr().out


def test_the_register_holds_no_text_a_render_would_lose():
    assert register.source_problems() == []


# ------------------------------------------------------------------------------------------------------- later notes
# A note on a row is a file of its own, notes.d/<row id>/<YYYY-MM-DD>-<branch slug>.md, never an edit of the row's
# Notes cell: two changes appending to one cell conflict whatever the layout (tools/register.py, *Later notes*).

NOTE = "A later note.\n"


def _notes(*paths: str, text: str = NOTE) -> list[tuple[str, str | None]]:
    return [(p, text) for p in paths]


def test_every_row_with_an_id_points_to_its_notes_and_the_pointer_round_trips():
    page = register.render_markdown(DATA)
    ids = [r["id"] for r in register.rows(DATA, open_only=False) if r["id"] and r["id"] != "Gate"]
    assert ids and all(register.pointer(rid) in page for rid in ids)
    assert page.count("*Later notes: `notes.d/") == len(ids)
    assert register.parse_markdown(page) == DATA


def _register_copy(root: Path) -> None:
    for path in (register.YAML, register.MD, register.DUE_YAML, register.DUE_MD):
        target = root / path.relative_to(register.ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def test_adding_a_note_leaves_every_rendered_and_source_file_byte_identical(tmp_path):
    """The whole point: a note touches no shared file, so two changes noting the same row cannot conflict on one."""
    _register_copy(tmp_path)
    register.render(tmp_path)
    shared = [tmp_path / p.relative_to(register.ROOT) for p in (register.YAML, register.MD, register.DUE_YAML,
                                                                 register.DUE_MD)]
    before = [p.read_bytes() for p in shared]
    note = tmp_path / register.NOTES.relative_to(register.ROOT) / "F19" / "2026-10-10-impl-x.md"
    note.parent.mkdir(parents=True)
    note.write_text(NOTE, encoding="utf-8", newline="\n")
    register.render(tmp_path)
    assert [p.read_bytes() for p in shared] == before
    assert register.note_files(tmp_path) == [("F19/2026-10-10-impl-x.md", NOTE)]


def test_show_prints_the_row_its_item_and_its_notes_oldest_first():
    files = _notes("F19/2026-10-10-b-branch.md", "F19/2026-09-30-z-branch.md", "F20/2026-10-01-other.md")
    files[0] = (files[0][0], "Second.\n")
    files[1] = (files[1][0], "First.\n")
    shown = register.show(DATA, DUE, "F19", files)
    assert shown is not None
    assert shown.startswith("## 2. ") and "\n### F19\n" in shown and "**Work:** One evaluation program" in shown
    assert "#### Later notes (notes.d/F19/): 2" in shown and "A later note." not in shown
    assert shown.index("2026-09-30-z-branch.md") < shown.index("First.") < shown.index("2026-10-10-b-branch.md") < \
        shown.index("Second.")
    item = next(i for i in DUE["items"])
    assert "**Decision due:**" in (register.show(DATA, DUE, item["row"], []) or "")
    assert register.show(DATA, DUE, "F99999", files) is None


def test_show_from_the_command_line_and_an_unknown_row(capsys):
    assert register.main(["show", "E30"]) == 0
    out = capsys.readouterr().out
    assert "### E30" in out and "2026-10-10-tools-register-fragments.md" in out
    assert register.main(["show", "Z1"]) == 1
    assert "not in the register" in capsys.readouterr().err


def test_the_real_notes_are_well_formed():
    assert register.note_problems(DATA, register.note_files()) == []


def test_a_note_for_a_row_the_register_does_not_have_is_refused():
    problems = register.note_problems(DATA, _notes("F99999/2026-10-10-x.md", "f19/2026-10-10-y.md",
                                                   "F19/sub/2026-10-10-x.md", "2026-10-10-x.md"))
    assert sum("is not in the register" in p for p in problems) == 2, problems  # F99999, and f19 (ids are exact)
    assert sum("a note is notes.d/<row id>/" in p for p in problems) == 2, problems  # nested, and no row directory


def test_a_malformed_note_is_refused():
    cases = {
        "F19/2026-10-10-Upper.md": register.SLUG_RULE,
        "F19/2026-10-10-x.txt": register.SLUG_RULE,
        "F19/2026-13-40-x.md": "is not a date",
        "F19/2026-10-10-trailing-.md": register.SLUG_RULE,
        "F19/2026-10-10-a--b.md": register.SLUG_RULE,
    }
    for path, why in cases.items():
        assert any(why in p for p in register.note_problems(DATA, _notes(path))), path
    texts = {"": "empty", "  \n": "empty", "no newline": "does not end with a newline",
             "<<<<<<< ours\na\n=======\nb\n>>>>>>> theirs\n": "conflict markers"}
    for text, why in texts.items():
        assert any(why in p for p in register.note_problems(DATA, [("F19/2026-10-10-x.md", text)])), text
    assert any("not UTF-8" in p for p in register.note_problems(DATA, [("F19/2026-10-10-x.md", None)]))
    assert register.note_problems(DATA, [("README.md", "anything"), ("F19/2026-10-10-x.md", NOTE)]) == []


def test_duplicate_names_and_a_note_added_twice_are_refused():
    """A name that differs from another only in case is one file on Windows and macOS but two in git on Linux; a note
    whose text repeats another of the same row is one note added twice (a branch renamed and its note re-added)."""
    problems = register.note_problems(DATA, [("F19/2026-10-10-x.md", "A.\n"), ("F19/2026-10-10-X.md", "B.\n")])
    assert any("differ only in case" in p for p in problems), problems
    problems = register.note_problems(DATA, [("F19/2026-10-10-a.md", "Same.\n"), ("F19/2026-10-11-b.md", "Same.\n")])
    assert problems == ["notes.d/F19/2026-10-11-b.md: the same note as notes.d/F19/2026-10-10-a.md; keep one"]
    assert register.note_problems(DATA, [("F19/2026-10-10-a.md", "Same.\n"), ("F20/2026-10-10-a.md", "Same.\n")]) == []


def test_check_refuses_a_bad_note(monkeypatch, capsys):
    monkeypatch.setattr(register, "note_files", lambda root=register.ROOT: _notes("F99999/2026-10-10-x.md"))
    assert register.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "F99999 is not in the register" in out and "future-work.md differs" not in out, out


def test_the_slug_rule_is_one_function_and_every_slug_it_makes_is_a_valid_name():
    assert register.slug("impl/F9a_MS3") == "impl-f9a-ms3"
    assert register.slug("--feat//a_-b--") == "feat-a-b"
    for branch in ("impl/f9a-ms3", "Fix/X", "tools/register-fragments", "a__b", "x.y/z"):
        assert register.NOTE_NAME_RE.match(f"2026-10-10-{register.slug(branch)}.md"), branch


def _head(name: str) -> Any:
    """A stand-in for `git symbolic-ref --short HEAD` answering ``name``, or failing as on a detached HEAD."""
    detached = name == "HEAD"
    return lambda root, *args: subprocess.CompletedProcess(args, int(detached), "" if detached else f"{name}\n", "")


def test_note_reads_the_branch_of_a_real_checkout(tmp_path):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(tmp_path / "none")}
    subprocess.run(["git", "init", "-q", "-b", "impl/Real_Branch", str(tmp_path)], check=True, env=env,
                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    path, said = register.new_note(DATA, "E30", None, register.date(2026, 10, 10), tmp_path)
    assert said == "docs/implementation/notes.d/E30/2026-10-10-impl-real-branch.md" and path is not None


def test_note_creates_the_branchs_note_and_refuses_a_second_or_an_unknown_row(tmp_path, monkeypatch):
    """`note` derives the path from the checked-out branch, so authors never spell the slug by hand."""
    monkeypatch.setattr(register, "_git", _head("impl/F9a_MS3"))
    path, said = register.new_note(DATA, "F19", None, register.date(2026, 10, 10), tmp_path)
    assert path is not None and said == "docs/implementation/notes.d/F19/2026-10-10-impl-f9a-ms3.md"
    assert path.read_text(encoding="utf-8") == ""
    again, said = register.new_note(DATA, "F19", None, register.date(2026, 10, 10), tmp_path)
    assert again is None and "exists" in said and "add to it" in said
    missing, said = register.new_note(DATA, "F99999", None, register.date(2026, 10, 10), tmp_path)
    assert missing is None and "not in the register" in said
    assert register.note_problems(DATA, register.note_files(tmp_path)) == [
        "notes.d/F19/2026-10-10-impl-f9a-ms3.md: empty"]  # written by the author before `check` passes


def test_note_on_a_detached_head_needs_the_branch_named(tmp_path, monkeypatch):
    monkeypatch.setattr(register, "_git", _head("HEAD"))
    path, said = register.new_note(DATA, "F19", None, register.date(2026, 10, 10), tmp_path)
    assert path is None and "detached HEAD" in said and "--slug" in said
    path, said = register.new_note(DATA, "F19", "review/pr-195", register.date(2026, 10, 10), tmp_path)
    assert said == "docs/implementation/notes.d/F19/2026-10-10-review-pr-195.md"
    path, said = register.new_note(DATA, "F19", "///", register.date(2026, 10, 10), tmp_path)
    assert path is None and "empty slug" in said


@pytest.mark.parametrize("which", ["YAML", "DUE_YAML"])
def test_the_register_reads_the_same_with_libyaml_and_the_pure_python_reader(which):
    """The tool reads with libyaml where PyYAML has it (#232): on the real files both readers give the same tokens and
    the same data, so `check` judges them the same either way. A plain token's style is '' from libyaml and None from
    the pure reader. They differ only on inputs the files do not hold (review of #232, F4: a trailing tab, a byte-order
    mark inside the text, the wording of a parse error), which the comment at `_SafeLoader` records."""
    text = getattr(register, which).read_text(encoding="utf-8")

    def tokens(loader: Any) -> list[tuple[Any, ...]]:
        return [(type(t).__name__, t.start_mark.index, t.end_mark.index, getattr(t, "value", None),
                 getattr(t, "style", None) or None) for t in yaml.scan(text, Loader=loader)]

    assert tokens(register._SafeLoader) == tokens(yaml.SafeLoader)
    assert yaml.load(text, Loader=register._SafeLoader) == yaml.load(text, Loader=yaml.SafeLoader)  # noqa: S506


# ------------------------------------------------------------------------------------------------------- the rebaseline
# The register rebaseline (operator, 2026-10-24; the designer's record is in the design workspace at b598fdc) gave every
# open row and every decisions-due item of the register at ``register_commit`` one disposition. The file is committed
# beside the register, and these checks pin it to the register in both directions: nothing open at that commit lacks a
# disposition, no disposition names a row that was not open, and the register carries out what each one says.

DISPOSITIONS = register.YAML.with_name("register-rebaseline-dispositions.yaml")
CITATION = "(register rebaseline, design workspace `b598fdc`)"
REBASELINE_DAY = "2026-10-24"


def _dispositions() -> dict[str, Any]:
    return yaml.load(DISPOSITIONS.read_text(encoding="utf-8"), Loader=register._StrictLoader)  # noqa: S506 - a SafeLoader


def _ids(data: dict[str, Any], *, open_only: bool) -> dict[str, str]:
    """Every row with an id, to the title of the section it is in."""
    titles = {s["number"]: s["title"] for s in data["sections"]}
    return {r["id"]: titles[r["section"]] for r in register.rows(data, open_only=open_only)
            if r["id"] and r["id"] != "Gate"}


def base_problems(disp: dict[str, Any], base: dict[str, Any], base_due: dict[str, Any]) -> list[str]:
    """What is wrong between the dispositions and the register as it was at ``register_commit``."""
    out: list[str] = []
    open_rows = _ids(base, open_only=True)
    rows, groups, new_rows = disp["rows"], disp["groups"], disp["new_rows"]
    out += [f"{rid} was open at the base and has no disposition" for rid in sorted(open_rows.keys() - rows.keys())]
    out += [f"{rid} has a disposition but was not an open row at the base"
            for rid in sorted(rows.keys() - open_rows.keys())]
    for rid, d in rows.items():
        if rid in open_rows and d.get("section") != open_rows[rid]:
            out.append(f"{rid}: its disposition says {d.get('section')!r}, the base has it in {open_rows[rid]!r}")
        kind = d.get("disposition")
        if kind not in ("close", "absorb", "hold", "keep"):
            out.append(f"{rid}: {kind!r} is not a disposition")
        elif kind == "close" and not d.get("by"):
            out.append(f"{rid}: a close with no `by`")
        elif kind in ("absorb", "hold") and not d.get("into"):
            out.append(f"{rid}: {kind} with no `into`")
        elif kind == "keep" and d.get("target") not in register.TARGETS:
            out.append(f"{rid}: keep with the target {d.get('target')!r}, which is not a register target")
        if kind == "hold" and d.get("into") not in groups:
            out.append(f"{rid}: held in {d.get('into')}, which the file does not define")
        if kind == "absorb" and d.get("into") not in open_rows.keys() | new_rows.keys():
            out.append(f"{rid}: absorbed into {d.get('into')}, which is neither an open row nor a new one")
    held = [m for g in groups.values() for m in g["members"]]
    out += [f"{m} is a member of two groups" for m in sorted({m for m in held if held.count(m) > 1})]
    for g, info in groups.items():
        if not register.ID_RE.match(g) or not g.startswith("HOLD-"):
            out.append(f"{g} is not a hold group id")
        listed = {m for m in info["members"] if rows.get(m, {}).get("disposition") == "hold"
                  and rows[m].get("into") == g}
        out += [f"{g} lists {m}, whose disposition does not hold it there"
                for m in sorted(set(info["members"]) - listed)]
    out += [f"{rid} is held in {d['into']}, which does not list it" for rid, d in rows.items()
            if d.get("disposition") == "hold" and rid not in groups.get(d.get("into"), {}).get("members", [])]
    out += [f"new row {rid} was already a row at the base" for rid in sorted(new_rows.keys() & open_rows.keys())]
    due_rows = {item["row"] for item in base_due["items"]}
    fates = disp["decisions_due"]
    out += [f"the decisions-due item of {r} has no fate" for r in sorted(due_rows - fates.keys())]
    out += [f"a fate for {r}, which had no decisions-due item at the base" for r in sorted(fates.keys() - due_rows)]
    for r, fate in fates.items():
        kept = str(fate.get("fate")).startswith("keep:")
        if fate.get("fate") != "drop" and not (kept and fate["fate"].removeprefix("keep:") in register.DUE_ORDER
                                                and rows.get(r, {}).get("disposition") == "keep"):
            out.append(f"{r}: the fate {fate.get('fate')!r} is neither `drop` nor `keep:<due point>` on a kept row")
    out += [f"the Now list names {n.get('row')}, which is not a row" for n in disp["now"]
            if n.get("row") not in open_rows.keys() | new_rows.keys()]
    return out


def head_problems(disp: dict[str, Any], head: dict[str, Any]) -> list[str]:
    """What is wrong between the dispositions and the register as it stands: each one carried out, and nothing closed in
    the rebaseline's forms without one. A kept row may have changed since (it may even be closed), so it is only
    required to exist."""
    out: list[str] = []
    every = _ids(head, open_only=False)
    closed = {r["#"]: r for s in head["sections"] if s["title"].startswith("Closed") for r in s["rows"]}
    rows = disp["rows"]
    for rid, d in rows.items():
        kind = d["disposition"]
        if rid not in every:
            out.append(f"{rid} (disposition {kind}) is not in the register")
        elif kind != "keep":
            row = closed.get(rid)
            if row is None:
                out.append(f"{rid}: {kind}, but the row is still open")
                continue
            by = row["By"]
            if row["Closed"] != REBASELINE_DAY:
                out.append(f"{rid}: closed on {row['Closed']}, not on the rebaseline's day")
            if kind == "close" and not (by.startswith(d["by"]) and by.endswith(CITATION)
                                        and (not d.get("note") or d["note"] in by)):
                out.append(f"{rid}: its By is not the disposition's by, its note and the citation: {by[:80]!r}")
            if kind == "absorb" and by != f"absorbed into {d['into']}":
                out.append(f"{rid}: its By is {by[:80]!r}, not 'absorbed into {d['into']}'")
            if kind == "hold" and by != f"held in {d['into']}":
                out.append(f"{rid}: its By is {by[:80]!r}, not 'held in {d['into']}'")
        if kind in ("absorb", "hold") and d["into"] not in every:
            out.append(f"{rid}: {d['into']} is not in the register")
    out += [f"{g} (a hold group) is not in the register" for g in disp["groups"] if g not in every]
    out += [f"{r} (a new row) is not in the register" for r in disp["new_rows"] if r not in every]
    out += [f"the Now list names {n['row']}, which is not in the register" for n in disp["now"]
            if n["row"] not in every]
    for rid, row in closed.items():
        by = row["By"]
        if rid not in rows and (by.startswith(("held in HOLD-", "absorbed into ")) or by.endswith(CITATION)):
            out.append(f"{rid} was closed in the rebaseline's form but has no disposition")
    return out


@pytest.fixture(scope="module")
def at_the_base() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """The dispositions with the register and decisions-due as they were at ``register_commit``. Like the frozen-tag
    check of ``test_spec_pin``, it needs the history: CI's core jobs fetch it all, and a shallow clone skips."""
    disp = _dispositions()
    commit = disp["register_commit"]
    if shutil.which("git") is None or not (register.ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    if register._git(register.ROOT, "cat-file", "-e", f"{commit}^{{commit}}").returncode:
        pytest.skip(f"commit {commit[:8]} is not in this clone (a shallow clone)")
    shown = [register._git(register.ROOT, "show", f"{commit}:{p.relative_to(register.ROOT).as_posix()}")
             for p in (register.YAML, register.DUE_YAML)]
    assert all(s.returncode == 0 for s in shown), [s.stderr for s in shown]
    return disp, register._load(shown[0].stdout), register._load(shown[1].stdout)


def test_every_open_row_at_the_rebaselines_base_has_one_disposition_and_every_disposition_names_one(at_the_base):
    disp, base, base_due = at_the_base
    assert base_problems(disp, base, base_due) == []


def test_the_register_carries_out_every_disposition():
    assert head_problems(_dispositions(), register.load()) == []


def test_the_dispositions_are_the_designers_counts():
    """SUMMARY.md of the record: 21 closed outright, 9 absorbed, 125 held in 16 groups, 38 kept; three stage rows;
    24 decisions-due items, of which 3 stay."""
    disp = _dispositions()
    kinds = Counter(d["disposition"] for d in disp["rows"].values())
    assert (kinds["close"], kinds["absorb"], kinds["hold"], kinds["keep"], len(disp["rows"])) == (21, 9, 125, 38, 193)
    assert len(disp["groups"]) == 16 and sum(len(g["members"]) for g in disp["groups"].values()) == 125
    assert sorted(disp["new_rows"]) == ["STG-03", "STG-13", "STG-15"]
    fates = Counter(f["fate"] for f in disp["decisions_due"].values())
    assert (fates["drop"], len(disp["decisions_due"])) == (21, 24)
    assert {i["row"] for i in DUE["items"]} == {r for r, f in disp["decisions_due"].items()
                                                 if f["fate"].startswith("keep:")}
    assert disp["targets"] == list(register.TARGETS) and disp["due_order"] == list(register.DUE_ORDER)


def test_the_now_list_on_the_page_is_the_dispositions_in_order():
    """§1's table is the designer's prose and the file's `now` the same list as data: the same rows in the same order
    (the first row id of each line)."""
    intro = DATA["sections"][0]["intro"]
    table = [line.split("|")[2].strip().split(",")[0] for line in intro.splitlines() if re.match(r"\| \d+ \|", line)]
    assert table == [n["row"] for n in _dispositions()["now"]]


def test_the_pin_names_a_missing_a_stray_and_an_undefined_disposition(at_the_base):
    """The pin bites: a row left without a disposition, a disposition for a row that was never open, a hold in an
    undefined group, a group that drops its member and an item left without a fate are each named."""
    disp, base, base_due = at_the_base
    follow_ups = "Engineering follow-ups (the M3 audits)"
    mutations = {
        "was open at the base and has no disposition": lambda d: d["rows"].pop("E3"),
        "was not an open row at the base": lambda d: d["rows"].update(
            {"E9999": {"section": follow_ups, "disposition": "keep", "target": "Unscheduled"}}),
        "which the file does not define": lambda d: d["rows"]["D2"].update(into="HOLD-99"),
        "which does not list it": lambda d: d["groups"]["HOLD-17"]["members"].remove("D2"),
        "has no fate": lambda d: d["decisions_due"].pop("E72"),
        "which had no decisions-due item": lambda d: d["decisions_due"].update({"F1": {"fate": "drop"}}),
        "is not a register target": lambda d: d["rows"]["E3"].update(target="M4"),
    }
    for expected, mutate in mutations.items():
        changed = copy.deepcopy(disp)
        mutate(changed)
        found = base_problems(changed, base, base_due)
        assert any(expected in p for p in found), (expected, found)
    assert base_problems(disp, base, base_due) == []


def test_the_pin_names_a_disposition_the_register_does_not_carry_out():
    """The register side bites too: a By that is not the disposition's, a closed row taken out, a row closed in the
    rebaseline's form that has no disposition, and a row still open."""
    disp, head = _dispositions(), register.load()

    def closed_of(data: dict[str, Any]) -> dict[str, Any]:
        return next(s for s in data["sections"] if s["title"].startswith("Closed"))

    for rid, by, expected in (("F40", "something else", "its By is not"),
                              ("F9", "held in HOLD-02", "not 'held in HOLD-09'"),
                              ("D3", "absorbed into F12", "not 'absorbed into STG-15'")):
        changed = copy.deepcopy(head)
        next(r for r in closed_of(changed)["rows"] if r["#"] == rid)["By"] = by
        assert any(expected in p for p in head_problems(disp, changed)), (rid, head_problems(disp, changed))
    changed = copy.deepcopy(head)
    closed_of(changed)["rows"].append({"#": "E9999", "Was": "x", "Closed": REBASELINE_DAY, "By": "held in HOLD-02"})
    assert any("E9999 was closed in the rebaseline's form but has no disposition" in p
               for p in head_problems(disp, changed))
    changed = copy.deepcopy(head)
    closed_of(changed)["rows"] = [r for r in closed_of(changed)["rows"] if r["#"] != "F40"]
    assert any("F40 (disposition close) is not in the register" in p for p in head_problems(disp, changed))
    still_open = {"rows": {"E3": {"disposition": "close", "by": "x"}}, "groups": {}, "new_rows": {}, "now": []}
    assert "E3: close, but the row is still open" in head_problems(still_open, head)  # E3 is a kept row
