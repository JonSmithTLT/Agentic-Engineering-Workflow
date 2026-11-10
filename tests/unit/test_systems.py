"""The build board's data and its check, ``tools/systems.py check`` (register: the systems generator, PR 1).

CI runs the check here, in the fast lane, against this checkout: the committed board must hold to the register, the
as-built reference rendered in memory, and the tree. Every rule of the check then has its planted cases on synthetic
data (a board, a tree and its owners built in a temporary directory, never the repository's documents): the right
case passes, and each wrong or missing case is reported by the rule it breaks, so a rule that stopped checking fails
here.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from collections.abc import Callable
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import reference_render
import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("systems_tool", ROOT / "tools" / "systems.py")
assert _spec is not None and _spec.loader is not None
systems = importlib.util.module_from_spec(_spec)
sys.modules["systems_tool"] = systems
_spec.loader.exec_module(systems)


@cache
def owners_at_head() -> Any:
    """The committed board's owners: the register, and the as-built reference rendered in memory. ``systems.owners``
    renders it as ``tools/systems.py check`` does; here the render is the one made once per process for every module
    that reads it (``tests/helpers``), not a second one of the same tree."""
    files = reference_render.rendered()  # before the patch: the helper renders through the same module
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(systems._tool("reference"), "render_files", lambda root: files if root == ROOT
                      else pytest.fail(f"the board's owners were read from {root}, not this checkout"))
        return systems.owners(ROOT)


# ------------------------------------------------------------------------------------------ the CI check

def test_the_committed_board_holds_to_its_owners():
    """The check CI runs. A failure names each problem, the rule it breaks and how to settle it."""
    found = systems.check(ROOT, owners_at_head())
    assert found == [], "\n".join(map(str, found))


def test_the_owners_read_at_head_are_the_registers_and_the_references():
    own = owners_at_head()
    assert own.now_rows and own.now_rows <= own.open_rows <= own.rows
    assert not any(systems.HOLD_RE.match(r) for r in own.now_rows)
    assert own.records and all(":" in r for r in own.records)


def test_the_check_runs_on_this_checkout_and_the_command_line_says_so(monkeypatch, capsys):
    with pytest.raises(SystemExit) as stop:
        systems.main(["--help"])
    assert stop.value.code == 0 and "check" in capsys.readouterr().out
    monkeypatch.setattr(systems, "check", lambda: [])
    assert systems.main(["check"]) == 0
    monkeypatch.setattr(systems, "check", lambda: [systems.Problem("lint", "SYS-01", "x")])
    assert systems.main(["check"]) == 1 and "[lint] SYS-01: x" in capsys.readouterr().err

    def unreadable() -> list[Any]:
        raise systems.SystemsError("no register")

    monkeypatch.setattr(systems, "check", unreadable)
    assert systems.main(["check"]) == 2 and "no register" in capsys.readouterr().err


def test_the_hand_listed_tables_have_distinct_keys():
    fields = systems.REQUIRED + systems.OPTIONAL
    assert len(set(fields)) == len(fields)
    assert not set(systems.GENERATED) & set(fields)
    for table in (systems.TOP_FIELDS, systems.STATE_FIELDS, systems.SWITCH_FIELDS, systems.SLICE_FIELDS,
                  systems.CLAIM_FIELDS, systems.LISTS, systems.TEXTS, systems.HOLD_REFUSED):
        assert len(set(table)) == len(table), table
    for allowed in systems.ENUMS.values():
        assert len(set(allowed)) == len(allowed), allowed


# ------------------------------------------------------------------------------------------ planted cases

def entry(sid: str, **fields: Any) -> dict[str, Any]:
    base = {
        "id": sid, "name": f"System {sid}", "purpose": "one plain line",
        "serves_claims": {"closing_works": [], "extra": []}, "serves_pending": [],
        "design": ["docs/design/a.md"], "register": [], "as_built": [], "touches": ["src/pkg/*.py"],
        "depends_on": [],
        "state": {"board_state": "partly_built", "built": "partly", "wired": [], "on_by_default": False,
                  "used_in_default_flow": "no"},
        "finish_line": "built, wired, on and used", "remaining": [], "decision": "none",
        "recommendation": "finish", "who": "Lead", "reason": "one line", "evidence": ["src/pkg/a.py:1"],
    }
    base.update(fields)
    return base


def board() -> dict[str, Any]:
    """The right case: two systems that hold to every rule, one unowned Now row, and a hold named only as pending."""
    return {
        "schema": systems.SCHEMA, "wip_limit": 12,
        "unowned": {"E3": "a milestone gate, not a system"},
        "systems": [
            entry("SYS-01", register=["E1", "F1"], as_built=["modules:pkg.a"], serves_pending=["HOLD-01"],
                  serves_claims={"closing_works": ["W-1, the first work"], "extra": []},
                  remaining=[{"slice": "E1: the rest", "row": "E1", "estimate": "1 PR (estimate)"},
                             {"slice": "held work", "row": "HOLD-01", "estimate": "not sized"},
                             {"slice": "a new slice", "row": systems.ROW_OWED, "estimate": "1 PR"}],
                  switch={"key": "a.b", "default": "off", "default_evidence": "src/pkg/a.py:1 (the default)",
                          "owner": "operator", "turning_on_changes": "one line"}),
            entry("SYS-02", register=["E2"], depends_on=["SYS-01"], serves_pending=["HOLD-01"],
                  evidence=["E2 on the Now list", "designer-decisions-2026-11-06.md item 3", "#12 is two digits",
                            "future-work.yaml (row E2)"]),
        ],
    }


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for name in ("docs/design/a.md", "src/pkg/a.py", "src/pkg/b.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x\n")
    (tmp_path / "src" / "empty").mkdir()
    return tmp_path


@pytest.fixture
def own(tree: Path) -> Any:
    return systems.Owners(root=tree, rows=frozenset({"E1", "E2", "E3", "E4", "F1", "F9", "HOLD-01", "HOLD-02"}),
                          open_rows=frozenset({"E1", "E2", "E3", "E4", "HOLD-01"}),
                          now_rows=frozenset({"E1", "E2", "E3"}), records=frozenset({"modules:pkg.a", "modules:pkg.b"}))


def found(own: Any, change: Callable[[dict[str, Any]], Any] | None = None, *, text: Callable[[str], str] | None = None,
          header: str = "") -> list[Any]:
    data = copy.deepcopy(board())
    page = own.root / systems.MARKDOWN
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(systems.render_markdown(data, own.now_order), encoding="utf-8", newline="\n")
    if change is not None:
        change(data)
    if not systems.schema_problems(data) and sys_(data, "SYS-01")["name"] != "Changed name":
        page.write_text(systems.render_markdown(data, own.now_order), encoding="utf-8", newline="\n")
    body = header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=118)
    return systems.problems(text(body) if text else body, own)


def sys_(data: dict[str, Any], sid: str) -> dict[str, Any]:
    return next(e for e in data["systems"] if e["id"] == sid)


def test_the_right_case_has_no_problem(own):
    assert found(own) == []


def _set(sid: str, path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def change(data: dict[str, Any]) -> None:
        target = sys_(data, sid)
        *parents, last = path.split(".")
        for key in parents:
            target = target[key]
        target[last] = value
    return change


def _drop(sid: str, key: str) -> Callable[[dict[str, Any]], None]:
    return lambda data: sys_(data, sid).pop(key)


PLANTED: dict[str, tuple[str, Callable[[dict[str, Any]], Any]]] = {
    # schema: the shape, the enums, distinct ids
    "a required field missing": ("schema", _drop("SYS-01", "finish_line")),
    "an unknown field": ("schema", _set("SYS-01", "priority_note", "x")),
    "an enum value outside its list": ("schema", _set("SYS-01", "state.board_state", "half_done")),
    "a recommendation outside its list": ("schema", _set("SYS-01", "recommendation", "maybe")),
    "an id that is not SYS-NN": ("schema", _set("SYS-02", "id", "SYS-2")),
    "two entries with one id": ("schema", _set("SYS-02", "id", "SYS-01")),
    "a slice missing its row": ("schema", lambda d: sys_(d, "SYS-01")["remaining"][0].pop("row")),
    "a list field that is text": ("schema", _set("SYS-01", "register", "E1")),
    "the wrong schema": ("schema", lambda d: d.update(schema="aew/systems/v0")),
    "no unowned mapping": ("schema", lambda d: d.update(unowned=["E3"])),
    # generated: a derived field stored
    "serves stored in an entry": ("generated", _set("SYS-01", "serves", ["R-1"])),
    "serves_derivation stored": ("generated", _set("SYS-01", "serves_derivation", "by works")),
    "counts stored at the top": ("generated", lambda d: d.update(counts={"partly_built": 1})),
    # ported existence checks
    "a design path that is no file": ("design", _set("SYS-01", "design", ["docs/design/missing.md"])),
    "a design path outside docs/": ("design", _set("SYS-01", "design", ["src/pkg/a.py"])),
    "a register id the register lacks": ("register", _set("SYS-01", "register", ["E1", "F1", "E99"])),
    "a pending hold the register lacks": ("register", _set("SYS-01", "serves_pending", ["HOLD-01", "HOLD-99"])),
    "a pending id that is not a hold": ("register", _set("SYS-01", "serves_pending", ["HOLD-01", "F9"])),
    "a remaining row the register lacks": ("remaining", lambda d: sys_(d, "SYS-01")["remaining"][0].update(row="E98")),
    "an as_built record the reference lacks": ("as_built", _set("SYS-01", "as_built", ["modules:pkg.zz"])),
    "a touches glob that matches nothing": ("touches", _set("SYS-01", "touches", ["src/nothing/**"])),
    "a touches glob that matches only a directory": ("touches", _set("SYS-01", "touches", ["src/empty"])),
    "a touches glob that leaves the tree": ("touches", _set("SYS-01", "touches", ["../*/src/pkg/a.py"])),
    "an empty touches glob": ("touches", _set("SYS-01", "touches", [""])),  # review of #346, n3: was a ValueError
    "a switch whose evidence names no file": ("switch", _set("SYS-01", "switch.default_evidence", "src/x.py:3")),
    "a dependency on an unknown system": ("depends_on", _set("SYS-02", "depends_on", ["SYS-09"])),
    "a dependency cycle": ("depends_on", _set("SYS-01", "depends_on", ["SYS-02"])),
    # one owner per fact
    "an as_built record in two systems": ("owner", _set("SYS-02", "as_built", ["modules:pkg.a"])),
    "a register row in two systems": ("owner", _set("SYS-02", "register", ["E2", "F1"])),
    "a closing work in two systems": ("owner", _set("SYS-02", "serves_claims.closing_works", ["W-1, the first work"])),
    # ownership the other way
    "a Now row owned by none and not listed": ("unowned", _set("SYS-02", "register", [])),
    "an unowned row a system owns": ("unowned", lambda d: d["unowned"].update(E2="stale")),
    "an unowned row that is closed": ("unowned", lambda d: d["unowned"].update(F9="closed long ago")),
    "an unowned row with no reason": ("unowned", lambda d: d["unowned"].update(E3="")),
    # no claimed hold
    "a hold in register": ("hold", _set("SYS-02", "register", ["E2", "HOLD-01"])),
    "a hold as a claimed closing work": ("hold", _set("SYS-02", "serves_claims.closing_works",
                                                       ["HOLD-01, the dashboard hold"])),
    "a slice whose row is a closed hold": ("hold", _set("SYS-02", "remaining",
                                                        [{"slice": "held work", "row": "HOLD-02", "estimate": "e"}])),
    "a closed hold pending": ("hold", _set("SYS-02", "serves_pending", ["HOLD-01", "HOLD-02"])),  # #346 review, m2
    # the lint, one pattern per case, in different hand-kept fields
    "a Now position in purpose": ("lint", _set("SYS-01", "purpose", "the next step (Now 5)")),
    "a Now item in who": ("lint", _set("SYS-01", "who", "Lead (Now item 12)")),
    "a pull request number in reason": ("lint", _set("SYS-01", "reason", "merged as #339")),
    "a register line in evidence": ("lint", _set("SYS-01", "evidence", ["future-work.yaml:154 (F19)"])),
    "a pull request number in a slice": ("lint", lambda d: sys_(d, "SYS-01")["remaining"][0].update(slice="see #340")),
    "a Now position in decision": ("lint", _set("SYS-01", "decision", "decided at Now 3")),
    "a Now position in finish_line": ("lint", _set("SYS-01", "finish_line", "done when Now 4 lands")),
    "a Now position in an unowned reason": ("lint", lambda d: d["unowned"].update(E3="the gate, Now 3")),
    # the public-text guard
    "a private plans path": ("public", _set("SYS-01", "evidence", ["AEW-plans/board/BOARD.md:3"])),
    "a private reviews path": ("public", _set("SYS-01", "reason", "see AEW-reviews/x-123/REVIEW.md")),
    "the design workspace's path": ("public", _set("SYS-01", "reason", "AEW-architecture-workspace/decisions/x.md")),
    "the Lead's private list": ("public", _set("SYS-01", "reason", "ITEMS 55 gate items")),
    "a Windows absolute path": ("public", _set("SYS-01", "evidence", ["C:/work/aew/src/pkg/a.py:1"])),
    "a POSIX absolute path": ("public", _set("SYS-01", "evidence", ["/home/someone/aew/src/pkg/a.py:1"])),
    "a stale rendered page": ("rendered", _set("SYS-01", "name", "Changed name")),
}


def test_every_rule_has_a_planted_case():
    rules = {"schema", "generated", "design", "register", "remaining", "as_built", "touches", "switch",
             "depends_on", "owner", "unowned", "hold", "lint", "public", "rendered"}
    assert {rule for rule, _ in PLANTED.values()} == rules


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_a_planted_case_is_reported_by_the_rule_it_breaks(own, case):
    rule, change = PLANTED[case]
    problems = found(own, change)
    assert rule in {p.check for p in problems}, (case, [str(p) for p in problems])


def test_the_public_guard_reads_the_comments_and_the_bytes(own):
    assert {p.check for p in found(own, header="# from AEW-plans/build-board/BOARD.md\n")} == {"public"}
    assert {p.check for p in found(own, text=lambda t: t.replace("\n", "\r\n"))} == {"public"}
    assert found(own, header="# cited by file name: BOARD.md, designer-decisions-2026-11-06.md\n") == []


def test_what_the_rules_allow_stays_allowed(own):
    """The rules' edges, each a right case: a hold as a slice's row or in two systems' serves_pending (rule 4 exempts
    holds), a slice whose row is still to be filed, and the cites the lint points to instead."""
    assert found(own, _set("SYS-02", "remaining", [{"slice": "s", "row": "HOLD-01", "estimate": "e"}])) == []
    assert found(own, _set("SYS-02", "reason", "E2 is on the Now list; it rides on E1 (src/pkg/a.py, a.f)")) == []
    assert found(own, _set("SYS-02", "touches", ["src/pkg/a.py", "src/**/b.py"])) == []
    # a trailing ** matches the files below it on every supported Python (review of #346, B1: Path.glob before 3.13
    # matched only directories, so the committed board failed on Linux CI's 3.11)
    assert found(own, _set("SYS-02", "touches", ["src/**", "src/pkg/**", "docs/**"])) == []


def test_a_problem_names_the_row_and_how_to_settle_it(own):
    [unowned] = found(own, _set("SYS-02", "register", []))
    assert unowned.where == "E2" and "register" in unowned.text and "unowned:" in unowned.text
    [stale] = found(own, lambda d: d["unowned"].update(E2="stale"))
    assert stale.where == "E2" and "SYS-02" in stale.text and "remove" in stale.text
    [closed] = found(own, _set("SYS-02", "remaining", [{"slice": "held work", "row": "HOLD-02", "estimate": "e"}]))
    assert closed.where == "SYS-02" and "held work" in closed.text and "HOLD-02" in closed.text
    assert "member row" in closed.text
    [pending] = found(own, _set("SYS-02", "serves_pending", ["HOLD-02"]))
    assert pending.where == "SYS-02" and "serves_pending" in pending.text and "HOLD-02" in pending.text
    [empty] = found(own, _set("SYS-01", "touches", [""]))
    assert empty.where == "SYS-01" and "empty glob" in empty.text
    [cycle] = found(own, _set("SYS-01", "depends_on", ["SYS-02"]))
    assert cycle.text == "a cycle: SYS-01 -> SYS-02 -> SYS-01"


def test_a_repeated_key_or_broken_yaml_cannot_be_checked(own):
    with pytest.raises(systems.SystemsError):
        found(own, text=lambda t: t.replace("wip_limit: 12", "wip_limit: 12\nwip_limit: 13"))
    with pytest.raises(systems.SystemsError):
        found(own, text=lambda t: t + "\n  - [unclosed\n")


def test_the_check_is_deterministic(own):
    """The same input gives the same problems in the same order, whatever order the rules found them in."""
    def everything(data: dict[str, Any]) -> None:
        for _, change in PLANTED.values():
            try:
                change(data)
            except (KeyError, StopIteration, TypeError, AttributeError):
                pass
    first, second = found(own, everything), found(own, everything)
    assert first == second and len(first) > 20
    assert first == sorted(first, key=lambda p: (p.check, p.where, p.text))


def test_views_partition_and_questions_cross_the_partition():
    data = board()
    data["systems"] = [entry(f"SYS-{n:02}", recommendation=rec) for n, rec in enumerate(
        ("finish", "finish", "switch_on", "done", "freeze", "cut", "keep"), 1)]
    data["systems"][1]["remaining"] = [{"slice": str(n), "row": "row owed", "estimate": "1 PR"}
                                        for n in range(3)]
    data["systems"][0]["decision"] = "operator: choose"
    data["systems"][2]["decision"] = "decided: yes"
    chosen = systems.views(data, {})
    assert {k: [e["id"] for e in v] for k, v in chosen.items()} == {
        "soon": ["SYS-01", "SYS-03"], "more": ["SYS-02"], "questions": ["SYS-01"],
        "done": ["SYS-04"], "not_counted": ["SYS-05", "SYS-06", "SYS-07"]}
    partition = [e["id"] for k in ("soon", "more", "done", "not_counted") for e in chosen[k]]
    assert sorted(partition) == sorted(e["id"] for e in data["systems"])
    text = systems.render_markdown(data, {})
    assert "**Decided:** 1 — SYS-03" in text
    data["systems"] = []
    assert all(not v for v in systems.views(data, {}).values())
    assert "**Decided:** 0 — none" in systems.render_markdown(data, {})
    assert len({k for k, _, _ in systems.VIEWS}) == len(systems.VIEWS)


@pytest.mark.parametrize("count", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("recommendation", ["finish", "switch_on"])
def test_soon_slice_boundary(count, recommendation):
    data = board()
    e = data["systems"][0]
    e["recommendation"] = recommendation
    e["remaining"] = [{"slice": "s", "row": "E1", "estimate": "e"}] * count
    chosen = systems.views(data, {})
    assert (e in chosen["soon"]) == (recommendation == "switch_on" or count <= 2)
    assert (e in chosen["more"]) == (recommendation == "finish" and count > 2)


def test_priority_and_slices_ignore_riders_and_sort_ties_by_id(own):
    data = board()
    a, b = data["systems"]
    a["remaining"] = [{"slice": "rides on SYS-02's E2", "row": "E2", "estimate": "not its estimate"},
                      {"slice": "own", "row": "E1", "estimate": "2 PRs"}]
    supplied = replace(own, now_order={"E2": 1, "E1": 4})
    assert systems.priority(a, supplied.now_order) == 4
    assert systems.own_slices(a, data) == [a["remaining"][1]]
    assert [e["id"] for e in systems.views(data, supplied.now_order)["soon"]] == ["SYS-02", "SYS-01"]
    assert systems.priority(a, {"E2": 1}) is None
    assert [e["id"] for e in systems.views(data, {"E2": 1})["soon"]] == ["SYS-02", "SYS-01"]
    data["systems"].reverse()
    assert [e["id"] for e in systems.views(data, {"E1": 1, "E2": 1})["soon"]] == ["SYS-01", "SYS-02"]
    rendered = systems.render_markdown(data, supplied.now_order)
    assert "**Own slices left:** 1 — **Next:** own — E1 — 2 PRs" in rendered
    assert "**Switch:** a.b" in rendered and "**Who:** Lead" in rendered
    assert "**Now:** not on the Now list" in systems.render_markdown(data, {})


@pytest.mark.parametrize("state", systems.ENUMS[("state", "board_state")])
@pytest.mark.parametrize("rec", systems.ENUMS[("recommendation",)])
def test_the_limit_count_is_format_rule_one(state, rec):
    data = board()
    data["systems"] = [entry("SYS-01", recommendation=rec)]
    data["systems"][0]["state"]["board_state"] = state
    expected = state in ("partly_built", "built_off", "built_not_wired", "staged") and rec in ("finish", "switch_on")
    assert systems.counted_systems(data) == (["SYS-01"] if expected else [])


def board_copy(root, data=None):
    data = board() if data is None else data
    path = root / systems.SYSTEMS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    register = {"sections": [{"number": 1, "intro": "| 1 | closed: F1 | closed |\n| 2 | E2 | second |\n"
                             "| 3 | E1 | first |\n| 4 | E1 | again |", "rows": []}]}
    (root / systems.REGISTER).write_text(yaml.safe_dump(register), encoding="utf-8", newline="\n")
    return data


def test_render_is_deterministic_public_and_compared_byte_for_byte(tmp_path):
    data = board_copy(tmp_path)
    assert systems.now_order(tmp_path) == {"E2": 2, "E1": 3}
    assert systems.priority(data["systems"][0], systems.now_order(tmp_path)) == 3  # closed F1 contributes nothing
    assert systems.rendered_problems(tmp_path, data, systems.now_order(tmp_path))[0].check == "rendered"
    systems.render(tmp_path)
    first = (tmp_path / systems.MARKDOWN).read_bytes()
    systems.render(tmp_path)
    assert (tmp_path / systems.MARKDOWN).read_bytes() == first
    assert b"\r" not in first and systems.public_problems(first.decode()) == []
    assert systems.rendered_problems(tmp_path, data, systems.now_order(tmp_path)) == []
    (tmp_path / systems.MARKDOWN).write_bytes(first.replace(b"\n", b"\r\n"))
    assert "render`" in systems.rendered_problems(tmp_path, data, systems.now_order(tmp_path))[0].text
    systems.render(tmp_path)
    assert systems.rendered_problems(tmp_path, data, systems.now_order(tmp_path)) == []


def test_show_known_unknown_and_cli_write_nothing(tmp_path, monkeypatch, capsys):
    data = board_copy(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    shown = yaml.safe_load(systems.show("SYS-01", tmp_path))
    assert shown.pop("priority") == 3 and shown == data["systems"][0]
    assert systems.show("SYS-99", tmp_path) is None
    real_show = systems.show
    monkeypatch.setattr(systems, "show", lambda sid: real_show(sid, tmp_path))
    assert systems.main(["show", "SYS-01"]) == 0
    assert yaml.safe_load(capsys.readouterr().out)["priority"] == 3
    assert systems.main(["show", "SYS-99"]) == 1
    assert "unknown system id" in capsys.readouterr().err
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_render_command_uses_the_existing_renderer(tmp_path, monkeypatch, capsys):
    board_copy(tmp_path)
    real_render = systems.render
    monkeypatch.setattr(systems, "render", lambda: real_render(tmp_path))
    assert systems.main(["render"]) == 0
    assert systems.MARKDOWN in capsys.readouterr().out
    assert (tmp_path / systems.MARKDOWN).exists()


def test_register_render_refreshes_board_and_check_reports_staleness(tmp_path, monkeypatch, capsys):
    import shutil

    register = systems._tool("register")
    for path in register._paths(ROOT):
        dest = tmp_path / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    board_path = tmp_path / systems.SYSTEMS
    board_path.write_text(yaml.safe_dump(board()), encoding="utf-8", newline="\n")
    page = tmp_path / systems.MARKDOWN
    page.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr(systems, "owners", lambda *a: pytest.fail("render must not read reference owners"))
    monkeypatch.setattr(systems, "check", lambda *a: pytest.fail("render must not call check"))
    assert register.render(tmp_path) == []
    expected = systems.render_markdown(board(), systems.now_order(tmp_path))
    assert page.read_bytes() == expected.encode()
    for name, value in zip(("YAML", "MD", "DUE_YAML", "DUE_MD"), register._paths(tmp_path), strict=True):
        monkeypatch.setattr(register, name, value)
    monkeypatch.setattr(register, "ROOT", tmp_path)
    monkeypatch.setattr(register, "source_problems", lambda *a: [])
    monkeypatch.setattr(register, "note_files", lambda: [])
    page.write_text("stale\n", encoding="utf-8")
    assert register.main(["check"]) == 1
    assert systems.MARKDOWN in capsys.readouterr().out
    assert register.render(tmp_path) == []
    assert register.main(["check"]) == 0
