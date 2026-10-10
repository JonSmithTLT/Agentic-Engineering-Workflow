"""The maps and history search change note against the contract (register F20.8; the note's §3.3).

Appendix A must compile and, merged into contract 0.1.2, pass the compatibility check with every 0.1.2 path covered.
Against the accepted contract, the note's status line sets the mode: one-way before adoption (any amendment of the
additions passes), strict at the adopted version (the note and the contract cannot drift apart), and for a later
minor version the compatibility check over what was served at adoption. The unit cases below run each mode on scratch
notes and scratch contracts; the real note and the real contract are the first test.
"""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest
from dashboard_contract import ROOT, adopted, appendix, base_contract, note_problems, note_text, proposed

from aew.dashboard import contract as CT
from aew.dashboard.contract import Contract
from aew.dashboard.contract import compile_problems as compiles

MAPS = {"/maps", "/maps/structural", "/maps/structural/{root}", "/maps/structural/{root}/inputs", "/maps/diff"}
# The status bullet: its first line and its indented continuation lines.
STATUS_BULLET = re.compile(r"^- \*\*Status:\*\*.*\n(?:  .*\n)*", re.M)


def test_the_note_agrees_with_the_accepted_contract():
    accepted = Contract(ROOT / CT.CONTRACT_REL).document
    assert note_problems(note_text(), accepted, base_contract()) == []


def test_the_appendix_compiles_and_only_adds_to_0_1_2():
    base = base_contract()
    blocks = appendix(note_text())
    assert blocks, "the note's appendix holds the additions as fenced YAML"
    mine = proposed(note_text(), base)
    assert compiles(mine) == []
    assert CT.compatibility(base, mine, set(base["paths"])) == []
    assert mine["info"]["version"] == "0.1.3" and CT.in_series(mine["info"]["version"])
    for name in ("MapsResponse", "StructuralListResponse", "StructuralDetailResponse", "StructuralInputsResponse",
                 "MapDiffResponse", "HistorySearchResponse"):
        assert mine["components"]["schemas"][name]["properties"]["schema_version"]["const"] == "0.1.3", name
    caps = mine["components"]["schemas"]["Capabilities"]["properties"]
    assert caps["maps"]["$ref"] == caps["history_search"]["$ref"] == CT.CAPABILITY_REF


def test_every_count_the_appendix_types_is_within_javascripts_exact_integers():
    """p1: every integer a maps or search response carries is bounded by 2^53 - 1, so the UI never sees a value it
    cannot represent exactly."""
    base = base_contract()
    mine = proposed(note_text(), base)
    new = {n: s for n, s in mine["components"]["schemas"].items() if n not in base["components"]["schemas"]}

    def integers(node: Any) -> list[dict[str, Any]]:
        if isinstance(node, dict):
            found = [node] if node.get("type") == "integer" else []
            return found + [i for v in node.values() for i in integers(v)]
        if isinstance(node, list):
            return [i for v in node for i in integers(v)]
        return []

    for schema in integers(new):
        assert schema.get("maximum", 2**53) <= 2**53 - 1 and schema.get("minimum", -1) >= 0, schema


def test_the_note_records_the_adoption_and_every_route_served_since():
    """The adopted line names the adopted version and every added route this server serves (S2 serves the search; S1
    adds the maps routes when it serves them), so a later minor version must keep each of them equal."""
    from aew.dashboard.server import CONDITIONAL_ROUTES, ROUTES

    line = adopted(note_text())
    assert line is not None and line[0] == "0.1.3"
    added = set(proposed(note_text(), base_contract())["paths"]) - set(base_contract()["paths"])
    assert set(line[2]) == added & (set(ROUTES) | CONDITIONAL_ROUTES)
    assert "/history/search" in line[2]


# ---------------------------------------------------------------------------------------------- the modes

@pytest.fixture(scope="module")
def base() -> dict[str, Any]:
    return base_contract()


@pytest.fixture(scope="module")
def v013(base) -> dict[str, Any]:
    return proposed(note_text(), base)


def adopt(text: str, version: str = "0.1.3", routes: set[str] = MAPS) -> str:
    """A scratch note whose status bullet records an adoption, as the first slice to serve a route writes it."""
    served = ", ".join(f"`{r}`" for r in sorted(routes))
    line = f"- **Status:** as adopted in contract `{version}` at `0123456789ab`; served at adoption: {served}.\n"
    return STATUS_BULLET.sub(lambda _: line, text, count=1)


def unadopted(text: str) -> str:
    """A scratch note as it stood before adoption: its whole status bullet without an adopted line."""
    return STATUS_BULLET.sub(lambda _: "- **Status:** proposed; Appendix A is not adopted yet.\n", text, count=1)


def amended(base: dict[str, Any], mutate) -> dict[str, Any]:
    out = copy.deepcopy(base)
    mutate(out)
    return out


def renamed_parameter_added_field_renamed_path(doc: dict[str, Any]) -> None:
    """W1's amendments of the additions: a renamed parameter, an added field and a renamed path."""
    for method in ("get", "head"):
        for param in doc["paths"]["/maps"][method]["parameters"]:
            if param["name"] == "against":
                param["name"] = "compare_to"
    doc["components"]["schemas"]["MapsOverview"]["properties"]["generated_by"] = {"type": "string"}
    doc["paths"]["/maps/compare"] = doc["paths"].pop("/maps/diff")


def test_one_way_before_adoption_any_amendment_of_the_additions_passes(base, v013):
    text = unadopted(note_text())
    assert note_problems(text, base, base) == []  # W1 not applied yet: the contract is still 0.1.2
    assert note_problems(text, v013, base) == []  # W1 as written
    assert note_problems(text, amended(v013, renamed_parameter_added_field_renamed_path), base) == []


def test_one_way_before_adoption_a_changed_0_1_2_shape_still_fails(base, v013):
    def change(doc: dict[str, Any]) -> None:
        doc["components"]["schemas"]["Work"]["properties"]["extra"] = {"type": "string"}

    problems = note_problems(unadopted(note_text()), amended(v013, change), base)
    assert any("contract against 0.1.2" in p and "Work" in p for p in problems), problems


def test_an_appendix_that_changes_a_0_1_2_shape_fails_on_its_own(base, v013):
    text = note_text().replace("```yaml\ninfo:", "```yaml\ncomponents:\n  schemas:\n    Reason:\n      maxProperties: 2"
                               "\n```\n\n```yaml\ninfo:", 1)
    problems = note_problems(text, v013, base)
    assert any(p.startswith("appendix:") and "Reason" in p for p in problems), problems


def test_strict_at_the_adopted_version_a_mismatch_fails(base, v013):
    text = adopt(note_text())
    assert adopted(text) == ("0.1.3", "0123456789ab", sorted(MAPS))
    assert note_problems(text, v013, base) == []
    drifted = amended(v013, renamed_parameter_added_field_renamed_path)
    assert note_problems(text, drifted, base) == [
        "contract 0.1.3 differs from the note's appendix, which it adopted"]


def test_strict_mode_ignores_descriptions(base, v013):
    def reword(doc: dict[str, Any]) -> None:
        doc["components"]["schemas"]["MapSummary"]["description"] = "reworded by the web developer"

    assert note_problems(adopt(note_text()), amended(v013, reword), base) == []


def later(v013: dict[str, Any], mutate) -> dict[str, Any]:
    def bump(doc: dict[str, Any]) -> None:
        doc["info"]["version"] = "0.1.4"
        mutate(doc)

    return amended(v013, bump)


def test_a_later_version_that_only_adds_paths_passes_without_a_note_edit(base, v013):
    def add(doc: dict[str, Any]) -> None:
        doc["paths"]["/maps/semantic"] = copy.deepcopy(doc["paths"]["/maps"])

    assert note_problems(adopt(note_text()), later(v013, add), base) == []


def test_a_later_version_adding_an_optional_property_to_a_served_maps_response_fails(base, v013):
    def add(doc: dict[str, Any]) -> None:
        doc["components"]["schemas"]["MapsOverview"]["properties"]["note"] = {"type": "string"}

    problems = note_problems(adopt(note_text()), later(v013, add), base)
    assert "contract against 0.1.3: #/components/schemas/MapsOverview changed" in problems


def test_a_later_version_may_change_history_search_while_it_was_pending_at_adoption(base, v013):
    def change(doc: dict[str, Any]) -> None:
        doc["components"]["schemas"]["HistorySearch"]["properties"]["ranked"] = {"type": "boolean"}
        doc["components"]["schemas"]["HistorySearch"]["required"].append("ranked")

    assert note_problems(adopt(note_text()), later(v013, change), base) == []
    served = adopt(note_text(), routes=MAPS | {"/history/search"})  # once S2 has appended it, it is held equal
    assert "contract against 0.1.3: #/components/schemas/HistorySearch changed" in note_problems(
        served, later(v013, change), base)


def test_a_later_version_changing_a_field_of_a_served_maps_schema_fails(base, v013):
    def change(doc: dict[str, Any]) -> None:
        doc["components"]["schemas"]["MapSummary"]["properties"]["selected"] = {"type": "string"}

    problems = note_problems(adopt(note_text()), later(v013, change), base)
    assert "contract against 0.1.3: #/components/schemas/MapSummary changed" in problems


def test_a_later_version_changing_a_schema_shared_by_a_served_and_a_pending_route_fails(base, v013):
    """``ReferenceLabel`` labels both the maps responses (served at adoption) and the search (pending): reachable from
    a served route, so it is held equal even though the pending route alone could change it."""
    shared = {"ReferenceLabel", "BoundedCount"}
    reach = {n for n in shared if f"#/components/schemas/{n}" in str(v013["components"]["schemas"]["MapsOverview"])}
    assert reach == shared and all(
        f"#/components/schemas/{n}" in str(v013["components"]["schemas"]["HistorySearch"]) for n in shared)

    def change(doc: dict[str, Any]) -> None:
        doc["components"]["schemas"]["ReferenceLabel"]["maxLength"] = 200

    problems = note_problems(adopt(note_text()), later(v013, change), base)
    assert "contract against 0.1.3: #/components/schemas/ReferenceLabel changed" in problems


def test_a_contract_older_than_the_adopted_version_fails(base, v013):
    older = amended(v013, lambda doc: doc["info"].__setitem__("version", "0.1.2"))
    problems = note_problems(adopt(note_text()), older, base)
    assert "contract 0.1.2 is older than the adopted 0.1.3" in problems


def test_prose_that_describes_the_adopted_line_is_not_an_adoption():
    """Only the status bullet counts: §3.3 quotes the line's form without adopting anything."""
    before = unadopted(note_text())
    assert "as adopted in contract `<V>` at `<sha>`" in before
    assert adopted(before) is None
