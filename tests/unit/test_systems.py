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
                  systems.CLAIM_FIELDS, systems.LISTS, systems.TEXTS, systems.HOLD_REFUSED, systems.ALLOWANCE_FIELDS,
                  systems.HAND_WIRED):
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
                  remaining=[{"slice": "E2: the work", "row": "E2", "estimate": "1 PR"}],  # partly built, so work left
                  evidence=["E2 on the Now list", "designer-decisions-2026-11-06.md item 3", "#12 is two digits",
                            "future-work.yaml (row E2)"]),
        ],
    }


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for name in ("docs/design/a.md", "src/pkg/a.py", "src/pkg/b.py", "src/aew/policy/execution.py",
                 "src/aew/knowledge/manifest.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x\n")
    (tmp_path / "src" / "empty").mkdir()
    return tmp_path


@pytest.fixture
def own(tree: Path) -> Any:
    return systems.Owners(root=tree, rows=frozenset({"E1", "E2", "E3", "E4", "F1", "F9", "HOLD-01", "HOLD-02"}),
                          open_rows=frozenset({"E1", "E2", "E3", "E4", "HOLD-01"}),
                          now_rows=frozenset({"E1", "E2", "E3"}), records=frozenset({"modules:pkg.a", "modules:pkg.b"}),
                          gate_defaults={"mutating_concurrency": 2, "local_checks": ["unit"]},
                          string_switches={("maps", "pack_slices"): ("off", "structural"),
                                           ("coordination", "messaging"): ("disabled", "enabled")})


def found(own: Any, change: Callable[[dict[str, Any]], Any] | None = None, *, text: Callable[[str], str] | None = None,
          header: str = "", stale_page: bool = False) -> list[Any]:
    data = copy.deepcopy(board())
    page = own.root / systems.MARKDOWN
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(systems.render_markdown(data, own.now_order), encoding="utf-8", newline="\n")
    if change is not None:
        change(data)
    if not stale_page and not systems.schema_problems(data):
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


def checked_switch(**fields):
    return {"key": "maps.pack_slices", "default": "off", "default_evidence": systems.SWITCH_SOURCE, **fields}


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
    "a default differs from its table": ("default", _set("SYS-01", "switch", checked_switch(default="structural"))),
    "on_by_default disagrees with the pair": ("on_by_default", lambda d: (
        sys_(d, "SYS-01").update(switch=checked_switch()), sys_(d, "SYS-01")["state"].update(on_by_default=True))),
    "an unknown wired prefix": ("wired", _set("SYS-01", "state.wired", ["api:x"])),
    "a closed non-hold slice": ("stale_slice", _set("SYS-01", "remaining", [
        {"slice": "closed work", "row": "F1", "estimate": "1 PR"}])),
    "a count above the limit": ("wip", lambda d: d.update(wip_limit=1)),
    "a stale allowance": ("allowance", lambda d: d.update(wip_allowance={
        "count": 14, "operator": "I allow 14 systems", "date": "2026-11-10"})),
    "table evidence on a hand-kept key": ("default", _set("SYS-01", "switch.default_evidence", systems.SWITCH_SOURCE)),
    # the operator's sign-off, and the lag rule (the operator, 2026-11-10)
    "a malformed sign-off": ("schema", _set("SYS-01", "signoff", {"date": "2026-11-10"})),
    "on_and_used without a sign-off": ("signoff", _set("SYS-01", "state.board_state", "on_and_used")),
    "a sign-off on another state": ("signoff", _set("SYS-01", "signoff", {"date": "2026-11-10", "words": "ok"})),
    "a zero-slice partly built system": ("lag", _set("SYS-02", "remaining", [])),
}


def test_every_rule_has_a_planted_case():
    rules = {"schema", "generated", "design", "register", "remaining", "as_built", "touches", "switch",
             "depends_on", "owner", "unowned", "hold", "lint", "public", "rendered", "default", "on_by_default",
             "wired", "stale_slice", "wip", "allowance", "signoff", "lag"}
    assert {rule for rule, _ in PLANTED.values()} == rules


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_a_planted_case_is_reported_by_the_rule_it_breaks(own, case):
    rule, change = PLANTED[case]
    problems = found(own, change, stale_page=rule == "rendered")
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
        systems.ENUMS[("recommendation",)], 1)]
    by_rec = {e["recommendation"]: e for e in data["systems"]}
    more = entry(f"SYS-{len(data['systems']) + 1:02}", remaining=[
        {"slice": str(n), "row": "row owed", "estimate": "1 PR"} for n in range(3)])
    data["systems"].append(more)
    by_rec["finish"]["decision"] = "operator: choose"
    by_rec["switch_on"]["decision"] = "decided: yes"
    chosen = systems.views(data, {})
    assert {k: [e["id"] for e in v] for k, v in chosen.items()} == {
        "soon": sorted(by_rec[r]["id"] for r in ("finish", "switch_on")), "more": [more["id"]],
        "questions": [by_rec["finish"]["id"]], "done": [by_rec["done"]["id"]],
        "not_counted": sorted(by_rec[r]["id"] for r in ("freeze", "cut", "keep"))}
    partition = [e["id"] for k in ("soon", "more", "done", "not_counted") for e in chosen[k]]
    assert sorted(partition) == sorted(e["id"] for e in data["systems"])
    text = systems.render_markdown(data, {})
    assert f"**Decided:** 1 — {by_rec['switch_on']['id']}" in text
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
    assert "**Own slices left:** 1 — own (E1) — **Next:** own — E1 — 2 PRs" in rendered
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


# ------------------------------------------------------------------ the operator's sign-off (the operator, 2026-11-10)

SIGNOFF = {"date": "2026-11-10", "words": "tested it, signed off"}


def _state(sid: str, state: str, **fields: Any) -> Callable[[dict[str, Any]], None]:
    def change(data: dict[str, Any]) -> None:
        sys_(data, sid)["state"]["board_state"] = state
        sys_(data, sid).update(fields)
    return change


@pytest.mark.parametrize("rec", ["finish", "switch_on"])
def test_a_system_awaiting_signoff_is_not_counted_toward_the_limit(rec):
    data = board()
    data["wip_limit"] = 1
    for e in data["systems"]:
        e["recommendation"] = rec
    assert systems.counted_systems(data) == ["SYS-01", "SYS-02"]
    data["systems"][1]["state"]["board_state"] = systems.AWAITING
    assert systems.counted_systems(data) == ["SYS-01"] and systems.limit_problems(data) == []


def test_on_and_used_without_the_operators_signoff_is_refused(own):
    [problem] = found(own, _state("SYS-01", "on_and_used"))
    assert (problem.check, problem.where) == ("signoff", "SYS-01")
    assert "no sign-off" in problem.text and "awaiting_signoff" in problem.text
    assert found(own, _state("SYS-01", "on_and_used", signoff=dict(SIGNOFF))) == []


@pytest.mark.parametrize("state", [s for s in systems.ENUMS[("state", "board_state")] if s != "on_and_used"])
def test_a_signoff_on_any_state_but_on_and_used_is_refused(state):
    data = board()
    data["systems"][0]["state"]["board_state"] = state
    data["systems"][0]["signoff"] = dict(SIGNOFF)
    [problem] = systems.signoff_problems(data)
    assert problem.where == "SYS-01" and state in problem.text and "remove the sign-off" in problem.text


@pytest.mark.parametrize("signoff", [{"date": "2026-11-10"}, {"words": "yes"}, "yes", {**SIGNOFF, "by": "x"},
                                     {**SIGNOFF, "words": " "}, {**SIGNOFF, "date": "2026-02-30"},
                                     {**SIGNOFF, "date": "10 Nov 2026"}])
def test_a_malformed_signoff_is_refused_by_the_schema(signoff):
    data = board()
    data["systems"][0].update(state={**data["systems"][0]["state"], "board_state": "on_and_used"}, signoff=signoff)
    assert any("signoff" in p.text for p in systems.schema_problems(data))


def test_signoff_words_are_exempt_from_lint_but_never_from_the_public_guard(own):
    words = {"date": "2026-11-10", "words": "Now 5 is fine, #123 too"}
    assert found(own, _state("SYS-01", "on_and_used", signoff=words)) == []
    private = {**words, "words": words["words"] + " AEW-plans/x"}
    assert {p.check for p in found(own, _state("SYS-01", "on_and_used", signoff=private))} == {"public"}


@pytest.mark.parametrize("state", systems.BUILDING)
def test_the_lag_check_fires_for_a_zero_slice_building_system(own, state):
    [problem] = found(own, lambda d: (_set("SYS-02", "remaining", [])(d), _state("SYS-02", state)(d)))
    assert (problem.check, problem.where) == ("lag", "SYS-02")
    assert problem.text == (f"SYS-02 has no own slices left but is still {state}: move it to awaiting_signoff, or to "
                            "on_and_used with the operator's sign-off")


def test_a_slice_riding_on_another_systems_row_leaves_no_own_slice(own):
    """The lag rule counts own slices, as the board does: a slice on another system's row is that system's work."""
    rider = [{"slice": "rides on SYS-01's E1", "row": "E1", "estimate": "inside SYS-01's"}]
    assert {p.check for p in found(own, _set("SYS-02", "remaining", rider))} == {"lag"}


@pytest.mark.parametrize("rec", ["freeze", "cut", "keep"])
def test_the_lag_check_spares_a_frozen_cut_or_kept_system(own, rec):
    assert found(own, lambda d: (_set("SYS-02", "remaining", [])(d), _set("SYS-02", "recommendation", rec)(d))) == []


@pytest.mark.parametrize("state", ["awaiting_signoff", "designed_only"])
def test_the_lag_check_spares_a_zero_slice_system_out_of_the_building_states(own, state):
    assert found(own, lambda d: (_set("SYS-02", "remaining", [])(d), _state("SYS-02", state)(d))) == []


def test_the_totals_list_the_systems_waiting_on_the_operators_signoff():
    data = board()
    text = systems.render_markdown(data, {})
    assert "**Waiting on your sign-off:** 0 — none\n" in text
    assert "**awaiting_signoff (built, awaiting your sign-off):** 0 — none\n" in text
    for e in data["systems"]:
        e["state"]["board_state"] = systems.AWAITING
    text = systems.render_markdown(data, {})
    assert "**Waiting on your sign-off:** 2 — SYS-01, SYS-02\n" in text
    assert "**awaiting_signoff (built, awaiting your sign-off):** 2 — SYS-01, SYS-02\n" in text
    assert "**Limit's count / wip_limit:** 0 / 12 — none" in text


def board_copy(root, data=None):
    data = board() if data is None else data
    path = root / systems.SYSTEMS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8", newline="\n")
    register = {"sections": [{"number": 1, "title": "Now", "intro": "| 1 | closed: F1 | closed |\n| 2 | E2 | second |\n"
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


@pytest.mark.parametrize("command", ["check", "render", "show"])
def test_command_errors_name_the_requested_verb(command, monkeypatch, capsys):
    def unreadable(*args):
        raise systems.SystemsError("invalid board")

    monkeypatch.setattr(systems, command, unreadable)
    assert systems.main([command, *(["SYS-01"] if command == "show" else [])]) == 2
    assert capsys.readouterr().err == f"cannot {command} {systems.SYSTEMS}: invalid board\n"


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


@pytest.mark.parametrize("change", [
    {"default": "structural"}, {"key": "maps.pack_slice"}, {"default_evidence": "src/aew/policy/execution.py:148"},
])
def test_wrong_switch_facts_name_the_table_and_fix(own, change):
    data = board()
    data["systems"][0]["switch"] = checked_switch(**change)
    found = systems.switch_problems(data, own)
    assert found and all(p.check == "default" and p.where == "SYS-01" for p in found)
    assert all(systems.SWITCH_SOURCE in p.text for p in found)


@pytest.mark.parametrize("missing", ["default", "default_evidence"])
def test_missing_checked_switch_facts_are_refused(own, missing):
    data = board()
    switch = checked_switch()
    switch.pop(missing)
    data["systems"][0]["switch"] = switch
    assert systems.switch_problems(data, own)[0].check == "default"


def test_scalar_gate_string_comparison_suffix_and_non_scalar_refusal(own):
    data = board()
    e = data["systems"][0]
    e["switch"] = {"key": "gates.mutating_concurrency (new projects)", "default": "2",
                   "default_evidence": systems.GATE_SOURCE}
    assert systems.switch_problems(data, own) == []  # code holds an int, data holds text
    e["switch"]["default"] = "3"
    assert systems.switch_problems(data, own)[0].check == "default"
    e["switch"]["key"] = "gates.local_checks"
    assert "not a scalar" in systems.switch_problems(data, own)[0].text
    e["switch"]["key"] = "gates.missing"
    assert "fix the key" in systems.switch_problems(data, own)[0].text
    e["switch"] = checked_switch(key="maps.pack_slices (execution policy)")
    assert systems.switch_problems(data, own) == []


@pytest.mark.parametrize("value", ["word", 2, 1.5, True, None])
def test_each_scalar_gate_default_compares_as_text(own, value):
    data = board()
    data["systems"][0]["switch"] = {"key": "gates.sample", "default": str(value),
                                   "default_evidence": systems.GATE_SOURCE}
    own = replace(own, gate_defaults={"sample": value})
    assert systems.switch_problems(data, own) == []


@pytest.mark.parametrize("value", [["unit"], {"checks": ["unit"]}])
def test_non_scalar_gate_defaults_are_not_switches(own, value):
    data = board()
    data["systems"][0]["switch"] = {"key": "gates.sample", "default": str(value),
                                   "default_evidence": systems.GATE_SOURCE}
    own = replace(own, gate_defaults={"sample": value})
    assert "not a scalar" in systems.switch_problems(data, own)[0].text


@pytest.mark.parametrize("values, on", [(('off', 'on'), False), (('on', 'off'), True),
                                       (('disabled', 'enabled'), False), (('enabled', 'disabled'), True)])
def test_off_on_pairs_check_the_boolean_in_both_directions(own, values, on):
    data = board()
    data["systems"][0]["switch"] = checked_switch(default=values[0])
    data["systems"][0]["state"]["on_by_default"] = on
    own = replace(own, string_switches={("maps", "pack_slices"): values})
    assert systems.switch_problems(data, own) == []
    data["systems"][0]["state"]["on_by_default"] = not on
    [problem] = systems.switch_problems(data, own)
    assert problem.check == "on_by_default"


def test_non_binary_switch_is_checked_without_inventing_an_on_state(own):
    data = board()
    data["systems"][0]["switch"] = checked_switch(default="compact")
    own = replace(own, string_switches={("maps", "pack_slices"): ("compact", "standard")})
    assert systems.switch_problems(data, own) == []


def test_every_table_namespace_is_checked_and_other_namespaces_remain_hand_kept(own):
    own = replace(own, string_switches={("future_block", "feature"): ("off", "on")})
    for key in ("future_block.feature", "future_block.typo", "gates.mutating_concurrency"):
        assert systems.switch_source({"key": key}, own.string_switches)
    for key in ("containment.mode", "steering.mode", "policy.pricing", 'MODES["O-CMD"]'):
        data = board()
        data["systems"][0]["switch"] = {"key": key, "default": "hand-kept"}
        assert systems.switch_source(data["systems"][0]["switch"], own.string_switches) is None
        assert systems.switch_problems(data, own) == []
    data = systems.read_board(ROOT)
    real = owners_at_head()
    assert systems.switch_problems(data, real) == []
    for e in data["systems"]:
        if "switch" not in e:
            continue
        key = e["switch"]["key"].split(" ", 1)[0]
        checked = systems.switch_source(e["switch"], real.string_switches)
        assert bool(checked) == (key.startswith("gates.") or key.split(".", 1)[0]
                                 in {block for block, _ in real.string_switches})
        if checked:
            assert e["switch"]["default_evidence"] == checked


@pytest.mark.parametrize("evidence", [systems.GATE_SOURCE, systems.SWITCH_SOURCE])
def test_hand_kept_switch_cannot_claim_either_code_table(own, evidence):
    data = board()
    data["systems"][0]["switch"] = {"key": "steering.mode", "default": "absent", "default_evidence": evidence}
    [problem] = systems.switch_problems(data, own)
    assert problem.check == "default" and "hand-kept" in problem.text and "replace default_evidence" in problem.text
    data["systems"][0]["switch"]["default_evidence"] = "src/pkg/a.py:1"
    assert systems.switch_problems(data, own) == []


def test_renderer_labels_planted_evidence_without_importing_policy_tables(own, monkeypatch):
    data = board()
    data["systems"][0]["switch"] = checked_switch(key="planted.feature")
    own = replace(own, string_switches={("planted", "feature"): ("off", "on")})
    assert systems.switch_problems(data, own) == []
    monkeypatch.setattr(systems, "code_tables", lambda *args: pytest.fail("render must not import policy tables"))
    text = systems.render_markdown(data, {})
    assert f"**Switch:** planted.feature — default: off — checked against {systems.SWITCH_SOURCE}" in text
    assert "**Switch defaults not read from the code:** 0 — none\n" in text
    assert "**Hand-kept wiring (no reference record):** 0 — none\n" in text
    assert not any(line.endswith(" — ") for line in text.splitlines())


@pytest.mark.parametrize("claim, record", [("cli:command", "cli-commands:command"),
                                         ("dashboard:/route/{id}", "dashboard-routes:/route/{id}"),
                                         ("tool:explain", "tools:explain")])
def test_wired_claims_require_their_own_reference_family(own, claim, record):
    data = board()
    data["systems"][0]["state"]["wired"] = [claim]
    assert systems.wired_problems(data, replace(own, records=frozenset({record}))) == []
    [problem] = systems.wired_problems(data, own)
    assert problem.check == "wired" and record in problem.text and "correct or remove" in problem.text


def test_hand_kept_wiring_is_allowed_but_unknown_prefixes_are_not(own):
    data = board()
    data["systems"][0]["state"]["wired"] = ["lead_text", "pack"]
    assert systems.wired_problems(data, own) == []
    data["systems"][0]["state"]["wired"] = ["lead_text:made_up", "unknown:route", "cli:"]
    assert len(systems.wired_problems(data, own)) == 3
    data["systems"][0]["state"]["wired"] = []
    assert systems.wired_problems(data, own) == []


def test_stale_slices_keep_the_hold_rule_as_the_single_reporter(own):
    data = board()
    assert systems.stale_slice_problems(data, own) == []
    data["systems"][0]["remaining"] = [{"slice": "done", "row": "F1", "estimate": "e"}]
    [problem] = systems.stale_slice_problems(data, own)
    assert problem.check == "stale_slice" and "F1" in problem.text and "row owed" in problem.text
    data["systems"][0]["remaining"][0]["row"] = "E1"
    assert systems.stale_slice_problems(data, own) == []
    problems = found(own, _set("SYS-02", "remaining", [{"slice": "held", "row": "HOLD-02", "estimate": "e"}]))
    assert [p.check for p in problems] == ["hold"]


@pytest.mark.parametrize("count, cap, rule", [(0, None, None), (1, None, None), (2, None, None),
                                          (3, None, "wip"), (3, 3, None), (4, 3, "wip"),
                                          (1, 3, "allowance"), (2, 3, "allowance")])
def test_wip_limit_and_allowance_boundaries(count, cap, rule):
    data = board()
    data["wip_limit"] = 2
    data["systems"] = [entry(f"SYS-{n:02}") for n in range(1, count + 1)]
    if cap is not None:
        data["wip_allowance"] = {"count": cap, "operator": "I allow this", "date": "2026-11-10"}
    problems = systems.limit_problems(data)
    assert [p.check for p in problems] == ([rule] if rule else [])
    if rule == "wip":
        assert all(e["id"] in problems[0].text for e in data["systems"])
        if cap is not None:
            assert f"exceeds the operator's allowance of {cap} (wip_limit 2)" in problems[0].text
            assert "revised" in problems[0].text
        data["wip_allowance"] = {"count": count, "operator": "I approve the revised cap", "date": "2026-11-10"}
        assert systems.limit_problems(data) == []


@pytest.mark.parametrize("changes", [{"count": 12}, {"count": 11}, {"count": True}, {"count": "14"},
                                     {"operator": ""}, {"operator": "   "}, {"date": "2026-02-30"},
                                     {"date": "2026-1-10"}, {"date": None}, {"unexpected": "x"}])
def test_malformed_allowance_schema(changes):
    data = board()
    data["wip_allowance"] = {"count": 14, "operator": "I allow 14", "date": "2026-11-10", **changes}
    assert any(p.where == "wip_allowance" for p in systems.schema_problems(data))


def test_allowance_date_must_be_quoted_and_all_fields_present():
    data = board()
    data["wip_allowance"] = {"count": 14, "operator": "I allow 14", "date": "2026-11-10"}
    assert systems.schema_problems(data) == []
    text = yaml.safe_dump(data).replace("'2026-11-10'", "2026-11-10")
    assert any("quoted" in p.text for p in systems.schema_problems(systems.load(text)))
    for key in systems.ALLOWANCE_FIELDS:
        broken = copy.deepcopy(data)
        broken["wip_allowance"].pop(key)
        assert systems.schema_problems(broken)


def test_operator_words_are_exempt_from_lint_but_never_from_the_public_guard(own):
    def allowance(data):
        data.update(wip_limit=1, wip_allowance={"count": 2, "operator": "I allow Now 5 and #123 until done",
                                              "date": "2026-11-10"})

    assert found(own, allowance) == []

    def private(data):
        allowance(data)
        data["wip_allowance"]["operator"] += " AEW-plans/private"

    assert "public" in {p.check for p in found(own, private)}


def test_render_labels_hand_kept_facts_and_prints_allowance_words_and_date():
    data = board()
    data["wip_allowance"] = {"count": 14, "operator": "I allow 14 until the session closes", "date": "2026-11-10"}
    data["systems"][0]["state"]["wired"] = ["lead_text", "pack"]
    text = systems.render_markdown(data, {})
    assert "**Switch defaults not read from the code:** 1 — SYS-01" in text
    assert "a.b" in text and "**Hand-kept wiring (no reference record):** 1 — SYS-01" in text
    assert "SYS-01: lead_text, pack" in text
    allowance = next(line for line in text.splitlines() if line.startswith("**Operator allowance:**"))
    assert all(word in allowance for word in ("14", "2026-11-10", data["wip_allowance"]["operator"]))
    assert "SYS-01" not in allowance and "SYS-02" not in allowance
    assert "only the cap and staleness are checked; the words' conditions are not checked" in allowance
    assert "re-runs `python tools/systems.py check` against current main" in text
    assert systems.public_problems(text) == []


def test_allowance_conditions_are_labelled_not_interpreted():
    data = board()
    data["wip_limit"] = 2
    data["systems"] = [entry(f"SYS-{n:02}") for n in range(1, 5)]
    data["wip_allowance"] = {"count": 4, "operator": "No new starts; lapses when SYS-01 and SYS-02 close",
                             "date": "2026-11-10"}
    for closed in (1, 2):  # swap at cap, or a start after the named lapse, both remain numerically covered
        changed = copy.deepcopy(data)
        for e in changed["systems"][:closed]:
            e["recommendation"] = "done"
        changed["systems"].append(entry("SYS-05"))
        assert systems.limit_problems(changed) == []
        text = systems.render_markdown(changed, {})
        allowance = next(line for line in text.splitlines() if line.startswith("**Operator allowance:**"))
        assert "the words' conditions are not checked" in allowance
        assert "SYS-03" not in allowance and "SYS-04" not in allowance and "SYS-05" not in allowance


def test_request_economy_tracks_the_leads_existing_open_row():
    data, own = systems.read_board(ROOT), owners_at_head()
    e = sys_(data, "SYS-06")
    slices = [s for s in e["remaining"] if "request-economy" in s["slice"]]
    assert len(slices) == 1 and slices[0]["row"] == "E162" and "E162" in own.open_rows
    assert all(s["row"] != "E139" for s in e["remaining"])


def test_unreadable_code_or_reference_is_exit_two_not_no_problem(monkeypatch, tmp_path, capsys):
    import builtins

    importer = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "aew.knowledge.manifest":
            raise ImportError("table unavailable")
        return importer(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", missing)
        with pytest.raises(systems.SystemsError, match="table unavailable"):
            systems.code_tables(ROOT)
        assert systems.main(["check"]) == 2
        assert "table unavailable" in capsys.readouterr().err
    with pytest.raises(systems.SystemsError, match="this checkout"):
        systems.code_tables(tmp_path)
    reference = systems._tool("reference")

    def unreadable(root):
        raise ImportError("reference unavailable")

    monkeypatch.setattr(reference, "render_files", unreadable)
    with pytest.raises(systems.SystemsError, match="reference unavailable"):
        systems.reference_records(ROOT)


def test_owners_read_the_tables_after_the_reference(tmp_path, monkeypatch):
    board_copy(tmp_path)
    order = []

    def reference(root):
        order.append("reference")
        return frozenset()

    def tables(root):
        order.append("tables")
        raise systems.SystemsError("tables unavailable")

    monkeypatch.setattr(systems, "reference_records", reference)
    monkeypatch.setattr(systems, "code_tables", tables)
    with pytest.raises(systems.SystemsError, match="tables unavailable"):
        systems.owners(tmp_path)
    assert order == ["reference", "tables"]
