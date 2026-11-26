"""V-01's burn-down plan (docs/implementation/v01-burn-down.md) stays true to what it maps.

The breach categories come from the ledger's and the oracle's own definitions (`vertical/ledger.py`,
`vertical/oracle.py`), never a hand list, so a category either module adds needs an entry in the plan's table before
this passes. Each step's state comes from the oracle's derivation. Each row's state is the register's
(`tools/register.py`, the owner of the row grammar and of what is open), so a cluster cannot stay open on a row that
closed, nor be marked done on an open one. The operator asked on 2026-11-26 for a check that keeps the plan from
going stale.

Limits: it reads the ledger's and the oracle's categories, not the case-specific checks of
`tests/acceptance/test_vertical_path.py` (V2's must-holds, V3's diagnosis, the #213 autopsy's own assertions); those are
named in the clusters' cells, which it does not read. ``HARNESS_FAULTS`` are left out: they are never product results
(vertical-uat.md §5). A cluster's state is read only against its rows being open or closed: ``open`` and ``in flight
(#N)`` are the same here and the pull request a state names is never read, so a fix that merges without closing its row
leaves its cluster not done and nothing fails. A category's clusters are checked only for existing, except a step's,
where one must not be done: a counter's entry can go on naming a done cluster. A cluster's rows are the backticked ids
of its Rows cell: an id written without backticks, or elsewhere on the page, is not checked (review of #601, m3, n3)."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from vertical import ledger as L
from vertical import oracle as O

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "implementation" / "v01-burn-down.md"

_spec = importlib.util.spec_from_file_location("register", ROOT / "tools" / "register.py")
assert _spec and _spec.loader
register = importlib.util.module_from_spec(_spec)
sys.modules["register"] = register
_spec.loader.exec_module(register)

CLUSTER = re.compile(r"\*\*(C\d+)\*\*")
CLUSTER_ID = re.compile(r"\bC\d+\b")
TICKED = re.compile(r"`([^`]+)`")
STATES = ("open", "in flight", "done")


def table_after(text: str, heading: str) -> list[dict[str, str]]:
    """The rows of the first Markdown table after ``heading``, each by its header's names."""
    lines = text[text.index(heading):].splitlines()
    rows: list[list[str]] = []
    for line in lines[1:]:
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows:
            break
    header, body = rows[0], rows[2:]
    assert all(len(r) == len(header) for r in body), f"a row of the table after {heading!r} has the wrong cell count"
    return [dict(zip(header, r, strict=True)) for r in body]


def derived_categories() -> set[tuple[str, str]]:
    """Every breach the ledger or the oracle can report, by kind: each counter, each hard limit, V1's decision
    comparison, whether a result reached the operator, each way the Lead's session ends, and each of V01-01's steps
    (a step that has not landed is an operator fallback or a missing driver)."""
    return ({("counter", c) for c in L.COUNTERS} | {("hard limit", h) for h in L.HARD_LIMITS}
            | {("decisions", "V1_DECISIONS")} | {("result", L.RESULT_REACHED)}
            | {("lead ending", e) for e in L.LEAD_ENDINGS} | {("step", s.key) for s in O.STEPS})


def plan(text: str) -> tuple[dict[str, dict[str, str]], dict[tuple[str, str], list[str]]]:
    """The plan's clusters (id to cells) and its categories ((kind, name) to the cluster ids it names)."""
    clusters = {}
    for row in table_after(text, "## The clusters"):
        m = CLUSTER.match(row["Cluster"])
        assert m, f"a cluster's first cell starts with its bold id: {row['Cluster']!r}"
        clusters[m.group(1)] = row
    categories = {}
    for row in table_after(text, "## The breach categories"):
        names = TICKED.findall(row["Category"])
        assert len(names) == 1, f"a category's cell names it once, in backticks: {row['Category']!r}"
        categories[(row["Kind"], names[0])] = CLUSTER_ID.findall(row["Clusters"])
    return clusters, categories


def state(row: dict[str, str]) -> str:
    return next((s for s in STATES if row["State"].startswith(s)), "")


def coverage_problems(derived: set[tuple[str, str]], clusters: dict[str, dict[str, str]],
                      categories: dict[tuple[str, str], list[str]], not_landed: set[str]) -> list[str]:
    out = [f"{kind} {name}: the ledger or the oracle defines it, and the plan's categories table has no entry"
           for kind, name in sorted(derived - categories.keys())]
    out += [f"{kind} {name}: the plan has an entry the ledger and the oracle no longer define"
            for kind, name in sorted(categories.keys() - derived)]
    out += [f"{kind} {name}: names {c}, which the clusters table does not have"
            for (kind, name), cs in sorted(categories.items()) for c in cs if c not in clusters]
    for key in sorted(not_landed):
        owners = [c for c in categories.get(("step", key), []) if c in clusters and state(clusters[c]) != "done"]
        if not owners:
            out.append(f"step {key}: the oracle derives it as not landed, and the plan names no open cluster for it")
    return out


def state_problems(clusters: dict[str, dict[str, str]], known: set[str], open_rows: set[str]) -> list[str]:
    out = []
    for cid, row in sorted(clusters.items()):
        if not state(row):
            out.append(f"{cid}: its state {row['State']!r} is none of {', '.join(STATES)}")
        ids = TICKED.findall(row["Rows"])
        if not ids:
            out.append(f"{cid}: it names no register row")
        for rid in ids:
            if not register.ID_RE.match(rid) or rid not in known:
                out.append(f"{cid}: names {rid!r}, which is not a row of the register")
            elif state(row) == "done" and rid in open_rows:
                out.append(f"{cid}: is marked done while its row {rid} is open")
            elif state(row) in ("open", "in flight") and rid not in open_rows:
                out.append(f"{cid}: is still {state(row)} while its row {rid} is closed: mark the cluster done, or "
                           "name the row that now holds what remains")
    return out


def register_ids() -> tuple[set[str], set[str]]:
    data = register.load()

    def ids(open_only: bool) -> set[str]:
        return {r["id"] for r in register.rows(data, open_only=open_only) if r["id"] and r["id"] != "Gate"}
    return ids(False), ids(True)


def not_landed_steps() -> set[str]:
    return {r["key"] for r in O.derive() if not O.landed(r["state"])}


def test_every_breach_category_the_ledger_and_the_oracle_define_has_an_entry_and_every_unlanded_step_an_open_cluster():
    clusters, categories = plan(DOC.read_text(encoding="utf-8"))
    assert coverage_problems(derived_categories(), clusters, categories, not_landed_steps()) == []


def test_no_cluster_stays_open_on_a_closed_row_or_is_done_on_an_open_one():
    clusters, _ = plan(DOC.read_text(encoding="utf-8"))
    known, open_rows = register_ids()
    assert state_problems(clusters, known, open_rows) == []


# ---------------------------------------------------------------------------------------------- planted


def _planted() -> tuple[dict[str, dict[str, str]], dict[tuple[str, str], list[str]]]:
    clusters = {"C1": {"Rows": "`E1`", "State": "open"}, "C2": {"Rows": "`E2`, `STG-14`", "State": "done"}}
    categories = {("counter", "a"): ["C1"], ("step", "open"): ["C1"], ("step", "init"): []}
    return clusters, categories


def test_a_category_the_ledger_adds_or_drops_fails_until_the_plan_has_it():
    clusters, categories = _planted()
    derived = {("counter", "a"), ("step", "open"), ("step", "init")}
    assert coverage_problems(derived, clusters, categories, {"open"}) == []
    added = coverage_problems(derived | {("counter", "b")}, clusters, categories, {"open"})
    assert added == ["counter b: the ledger or the oracle defines it, and the plan's categories table has no entry"]
    dropped = coverage_problems(derived - {("counter", "a")}, clusters, categories, {"open"})
    assert dropped == ["counter a: the plan has an entry the ledger and the oracle no longer define"]
    unknown = coverage_problems(derived, clusters, {**categories, ("counter", "a"): ["C9"]}, {"open"})
    assert unknown == ["counter a: names C9, which the clusters table does not have"]


def test_an_unlanded_step_whose_only_cluster_is_done_fails():
    clusters, categories = _planted()
    derived = set(categories)
    assert coverage_problems(derived, clusters, {**categories, ("step", "open"): ["C2"]}, {"open"}) == [
        "step open: the oracle derives it as not landed, and the plan names no open cluster for it"]
    assert coverage_problems(derived, clusters, categories, {"open", "init"}) == [
        "step init: the oracle derives it as not landed, and the plan names no open cluster for it"]


def test_a_closed_row_under_an_open_cluster_an_open_row_under_a_done_one_and_an_unknown_row_fail():
    clusters, _ = _planted()
    known = {"E1", "E2", "STG-14"}
    assert state_problems(clusters, known, open_rows={"E1"}) == []
    assert state_problems(clusters, known, open_rows=set()) == [
        "C1: is still open while its row E1 is closed: mark the cluster done, or name the row that now holds what "
        "remains"]
    assert state_problems(clusters, known, open_rows={"E1", "STG-14"}) == [
        "C2: is marked done while its row STG-14 is open"]
    in_flight = {**clusters, "C1": {"Rows": "`E1`, `E9`", "State": "in flight (#597)"}}
    assert state_problems(in_flight, known, open_rows={"E1"}) == ["C1: names 'E9', which is not a row of the register"]
    assert state_problems({"C3": {"Rows": "none", "State": "later"}}, known, set()) == [
        "C3: its state 'later' is none of open, in flight, done", "C3: it names no register row"]
