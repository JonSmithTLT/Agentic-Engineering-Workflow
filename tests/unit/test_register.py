"""The future-work register is structured data (E30): `docs/implementation/future-work.yaml` is the source and
`future-work.md` the rendered view, kept identical by `tools/register.py`. Every row has a unique id and every open
row outside the gates and questions tables starts its target column with one of the register's own targets.
The file keeps nothing that every change edits: no change log in the preamble, and §Closed in id order, so concurrent
register changes merge."""

from __future__ import annotations

import copy
import importlib.util
import os
import subprocess
import sys
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
    q11 = next(r for r in questions["rows"] if r["#"] == "Q11")
    questions["rows"].remove(q11)
    closed["rows"].append({c: "x" for c in closed["columns"]} | {closed["columns"][0]: "Q11"})
    problems = register.due_problems(data, DUE)
    assert any("Q11 is closed" in p for p in problems), problems
    due = copy.deepcopy(DUE)
    due["items"][0]["blocks"] = ["F2"]  # closed in M4-B
    assert any("blocks F2, which is closed" in p for p in register.due_problems(DATA, due))


def test_every_open_question_and_designer_row_has_an_item():
    due = copy.deepcopy(DUE)
    due["items"] = [i for i in due["items"] if i["row"] not in {"Q14", "U10"}]
    problems = register.due_problems(DATA, due)
    assert any("Q14 is an open question with no item" in p for p in problems), problems
    assert any("U10 waits for the designer" in p for p in problems), problems


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
    one (F6 waits for Q4's decision)."""
    due = copy.deepcopy(DUE)
    q14 = next(i for i in due["items"] if i["row"] == "Q14")
    due["items"].remove(q14)
    next(i for i in due["items"] if i["row"] == "Q11")["blocks"].append("Q14")
    assert any("Q14 is an open question with no item of its own" in p for p in register.due_problems(DATA, due))
    assert not any("F6" in p for p in register.due_problems(DATA, DUE))  # blocked by Q4's item


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
    assert register.DUE_ORDER.index("M4-D") < register.DUE_ORDER.index("Gate: before F15.2 ships") \
        < register.DUE_ORDER.index("M4-E")  # docs/README.md's order (review, 3)


def test_an_incomplete_item_still_counts_as_its_rows_item():
    """PR #104 re-review, B: the missing field is the one problem; the question is not also reported as uncovered."""
    due = copy.deepcopy(DUE)
    next(i for i in due["items"] if i["row"] == "Q11").pop("what")
    problems = register.due_problems(DATA, due)
    assert any("(Q11): missing what" in p for p in problems) and not any("Q11 is an open question" in p
                                                                         for p in problems), problems


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
