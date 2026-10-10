"""Ticket field-group canonicalization and live digests (register F4, slice S1; E19-B §2.3, §2.4; plan §3.3, §3.4;
ADR-0016 §1). E19-B §12 oracle cases 4, 6, 7, 8 and 30 (plan §7)."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from importlib import resources
from typing import Any

import pytest

from aew.engine import gates
from aew.engine import ticket_fields as TF
from aew.errors import IntegrityError, UsageError
from aew.knowledge.records import Record, work_unit_record
from aew.util import sha256_text

GOAL = "subtract(a, b) returns a - b"
CONTRACT = "subtract is exported from calc"
NBSP, ACUTE, E_ACUTE = "\N{NO-BREAK SPACE}", "\N{COMBINING ACUTE ACCENT}", "\N{LATIN SMALL LETTER E WITH ACUTE}"


def record_text(*, title: str = "Add subtract()", goal: list[str] | None = None, contract: list[str] | None = None,
                body: str = "Implement subtract.\n", class0: list[str] | None = None, risk_class: int = 1,
                parent: str | None = "S-0001", external_refs: list[str] | None = None,
                scope_paths: list[str] | None = None, checks: list[str] | None = None,
                inputs: list[str] | None = None) -> str:
    return work_unit_record(
        unit_id="T-0001", kind="ticket", title=title, created_at="2026-10-09T00:00:00Z",
        created_by={"kind": "lead", "session_label": "lead", "generation": 1}, risk_class=risk_class, mutating=True,
        parent=parent, scope_paths=["src/calc/*.py"] if scope_paths is None else scope_paths,
        goal_backwards=[GOAL] if goal is None else goal,
        contract=[CONTRACT] if contract is None else contract, body=body, class0_assertions=class0,
        external_refs=external_refs, acceptance_checks=["unit"] if checks is None else checks,
        acceptance_inputs=["tests/data/*.csv"] if inputs is None else inputs,
    ).render()


def world(text: str, *, edges: list[dict[str, str]] | None = None, story_edges: list[dict[str, str]] | None = None,
          floor: int | None = None, story_gates: list[str] | None = None, risk_class: int = 1,
          rationale: str | None = None) -> dict[str, Any]:
    story_policy = {"mandatory_gates": list(story_gates or []), "min_descendant_class": floor, "rationale": rationale}
    return {"work": {
        "E-0001": {"kind": "epic", "title": "Calc", "parent": None, "state": "PLANNING", "risk_class": 1,
                   "mutating": False, "depends_on": [], "policy": None},
        "S-0001": {"kind": "story", "title": "Arithmetic", "parent": "E-0001", "state": "PLANNING", "risk_class": 1,
                   "mutating": False, "depends_on": list(story_edges or []), "policy": story_policy},
        "T-0001": {"kind": "ticket", "title": "Add subtract()", "record": "work/T-0001/ticket.md",
                   "record_sha256": sha256_text(text), "parent": "S-0001", "state": "BLOCKED", "risk_class": risk_class,
                   "mutating": True, "depends_on": list(edges or []), "policy": None,
                   "created_at": "2026-10-09T00:00:00Z", "plan": None, "plans": []},
    }}


def digests(text: str | None = None, **kw: Any) -> TF.Digests:
    text = record_text() if text is None else text
    return TF.live_digests(world(text, **kw), "T-0001", text)


def changed(a: TF.Digests, b: TF.Digests) -> frozenset[str]:
    return TF.changed_groups(a, b)


# ---------------------------------------------------------------------------------------------- canonicalization


@pytest.mark.parametrize("variant", ["crlf", "cr", "nfc", "trailing_space", "trailing_tab"])
def test_canonicalization_is_exactly_the_v1_set(variant: str):
    authored, folded = {
        "crlf": ("returns a - b\r\nfor all ints", "returns a - b\nfor all ints"),
        "cr": ("returns a - b\rfor all ints", "returns a - b\nfor all ints"),
        "nfc": (f"cafe{ACUTE} receipts", f"caf{E_ACUTE} receipts"),
        "trailing_space": ("returns a - b   \nfor all ints ", "returns a - b\nfor all ints"),
        "trailing_tab": ("returns a - b\t\t\nfor all ints\t", "returns a - b\nfor all ints"),
    }[variant]
    assert authored != folded and TF.canonical_text(authored) == folded
    assert digests(record_text(goal=[authored])) == digests(record_text(goal=[folded]))
    # The body and the title fold the same way, in their own groups.
    assert changed(digests(record_text(body=authored)), digests(record_text(body=folded))) == set()
    assert changed(digests(record_text(title=authored)), digests(record_text(title=folded))) == set()


@pytest.mark.parametrize("before,after", [
    pytest.param("Returns a - b", "returns a - b", id="case"),
    pytest.param("returns a - b.", "returns a - b", id="punctuation"),
    pytest.param("returns a - b\n\nfor all ints", "returns a - b\nfor all ints", id="blank_line"),
    pytest.param("returns a  - b", "returns a - b", id="interior_spaces"),
    pytest.param("  returns a - b", "returns a - b", id="leading_spaces"),
    pytest.param("returns a minus b", "returns a - b", id="wording"),
    pytest.param("returns a - b\n", "returns a - b", id="final_newline"),
    pytest.param(f"returns a - b{NBSP}", "returns a - b", id="trailing_no_break_space"),
    pytest.param("\N{LATIN SMALL LIGATURE FI}nds a - b", "finds a - b", id="compatibility_form"),
])
def test_wording_case_punctuation_blank_lines_and_interior_spaces_change_the_digest(before: str, after: str):
    assert TF.canonical_text(before) != TF.canonical_text(after)
    assert changed(digests(record_text(goal=[before])), digests(record_text(goal=[after]))) == {"acceptance"}
    # The body likewise, wherever the stored bytes differ (the record writer ends every body with a newline).
    stored = record_text(body=before), record_text(body=after)
    assert changed(digests(stored[0]), digests(stored[1])) == ({"acceptance"} if stored[0] != stored[1] else set())
    assert changed(digests(record_text(body=f"x\n{before}\n")), digests(record_text(body=f"x\n{after}\n"))) == {
        "acceptance"}


@pytest.mark.parametrize("rule", ["class0_dedup_sort", "edges_dedup_sort"])
def test_the_set_rules_collide_only_what_they_declare(rule: str):
    if rule == "class0_dedup_sort":
        a = ["transformation_clear", "inputs_complete"]
        b = ["inputs_complete", "transformation_clear", "inputs_complete"]
        assert TF.canonical(a, "sorted_set") == TF.canonical(b, "sorted_set")
        same = record_text(class0=a, risk_class=0), record_text(class0=b, risk_class=0)
        assert changed(digests(same[0], risk_class=0), digests(same[1], risk_class=0)) == set()
        # Only duplicates and order collide: a different set is a different gate_set.
        fewer = record_text(class0=["inputs_complete"], risk_class=0)
        assert changed(digests(same[0], risk_class=0), digests(fewer, risk_class=0)) == {"gate_set"}
    else:
        x, y = {"id": "T-0007", "kind": "mutating"}, {"id": "T-0003", "kind": "evidence"}
        base = digests(edges=[x, y])
        assert changed(base, digests(edges=[y, x])) == set()
        assert changed(base, digests(edges=[x], story_edges=[y, x])) == set()
        assert changed(base, digests(edges=[x, {"id": "T-0003", "kind": "mutating"}])) == {"dependencies"}
        assert changed(base, digests(edges=[x])) == {"dependencies"}
    # No other list is a set: order and repetition stay significant everywhere else.
    goals = [GOAL, "subtract handles negatives"]
    assert changed(digests(record_text(goal=goals)), digests(record_text(goal=goals[::-1]))) == {"acceptance"}
    assert changed(digests(record_text(goal=goals)), digests(record_text(goal=goals + goals[:1]))) == {"acceptance"}


def test_moving_an_acceptance_condition_into_the_title_or_notes_changes_the_acceptance_digest():
    condition = "subtract handles negatives"
    base_text = record_text(contract=[CONTRACT, condition])
    base = digests(base_text)
    moved = {
        "title": record_text(contract=[CONTRACT], title=f"Add subtract(); {condition}"),
        "body": record_text(contract=[CONTRACT], body=f"Implement subtract.\n{condition}\n"),
        "external_refs": record_text(contract=[CONTRACT], external_refs=[condition]),
        "notes": record_text(contract=[CONTRACT]).replace("mutating: true\n", f"mutating: true\nnotes: {condition}\n"),
    }
    for where, text in moved.items():
        assert "acceptance" in changed(base, digests(text)), where
    # The title is presentation (non-material), so the material change is the acceptance one the move removed.
    assert TF.material(changed(base, digests(moved["title"]))) == {"acceptance"}


def test_a_registry_move_counts_as_changed_in_both_groups():
    doc = json.loads(resources.files("aew.schemas").joinpath("ticket-field-registry.v1.json").read_text("utf-8"))
    v1 = TF.registry_from_doc(doc)
    v2_doc = copy.deepcopy(doc)
    v2_doc.update(version=2, predecessor=v1.identity,
                  moves=[{"field": "record:external_refs", "from": "acceptance", "to": "card"}])
    for f in v2_doc["record"]:
        if f["field"] == "external_refs":
            f["group"] = "card"
    v2 = TF.registry_from_doc(v2_doc)
    known = {v1.identity: v1, v2.identity: v2}
    text = record_text()
    state = world(text)
    old, new = (TF.live_digests(state, "T-0001", text, registry=r) for r in (v1, v2))
    assert TF.changed_groups(old, new, registries=known) >= {"acceptance", "card"}
    # The rule holds whatever the digests say, in either direction, and it is the move's groups only.
    same = {g: "0" * 64 for g in v1.groups}
    before, after = TF.Digests(v1.identity, same), TF.Digests(v2.identity, same)
    assert TF.changed_groups(before, after, registries=known) == {"acceptance", "card"}
    assert TF.changed_groups(after, before, registries=known) == {"acceptance", "card"}
    # A declared move counts even where the two versions hash the field in the same groups.
    v2_same = copy.deepcopy(doc)
    v2_same.update(version=2, predecessor=v1.identity,
                   moves=[{"field": "record:external_refs", "from": "card", "to": "acceptance"}])
    declared = TF.registry_from_doc(v2_same)
    assert TF.changed_groups(before, TF.Digests(declared.identity, same),
                             registries={v1.identity: v1, declared.identity: declared}) == {"acceptance", "card"}
    # A registry with no known lineage to the other: every group counts as changed.
    assert TF.changed_groups(before, after, registries={v2.identity: v2}) == set(v1.groups)
    assert TF.changed_groups(before, TF.Digests(v1.identity, same)) == set()


def test_dependencies_in_control_state_and_inherited_edges_are_one_group():
    x, y = {"id": "T-0007", "kind": "mutating"}, {"id": "T-0003", "kind": "evidence"}
    own = digests(edges=[x])
    # The same edge, declared on the Ticket or inherited from its Story: one dependency set, one digest (m4).
    assert changed(own, digests(story_edges=[x])) == set()
    # An ancestor's new edge changes the Ticket's dependencies, and nothing else of it (N6).
    assert changed(own, digests(edges=[x], story_edges=[y])) == {"dependencies"}
    payload = TF.group_payloads(world(record_text(), edges=[x], story_edges=[y]), "T-0001", record_text())
    assert payload["dependencies"] == {"derived:effective_edges": [y, x]}


def test_gate_set_follows_the_effective_obligations():
    text = record_text()
    base = digests()
    assert changed(base, digests(floor=3)) == {"gate_set"}  # a floor raises the effective class
    assert changed(base, digests(floor=1)) == {"gate_set"}  # a floor at the Ticket's own class is still an obligation
    assert changed(base, digests(story_gates=["security_review"])) == {"gate_set"}
    assert changed(base, digests(risk_class=2)) == {"gate_set"}  # work reclassify
    # A Story's rationale is its own record, not an obligation the Ticket inherits.
    assert changed(base, digests(rationale="payments code")) == set()
    state = world(text, floor=3, story_gates=["security_review", "security_review"])
    payload = TF.group_payloads(state, "T-0001", text)["gate_set"]
    obligations = gates.effective_obligations(state, "T-0001", {"risk_paths": {"3": []}})
    assert payload["derived:effective_class"] == obligations["effective_class"] == 3
    assert payload["derived:class_floor"] == obligations["floor"] == 3
    assert payload["derived:inherited_mandatory_gates"] == obligations["non_waivable"] == ["security_review"]


# Fixed vectors: computed once and pinned, so the same inputs give the same bytes on every platform and Python.
VECTOR_TEXT = f"Returns  a{NBSP}- b \r\ncafe{ACUTE}\t\rDone.\n"
VECTOR_CANONICAL = f"Returns  a{NBSP}- b\ncaf{E_ACUTE}\nDone.\n"
VECTOR_PAYLOAD = {"record:title": f"T{E_ACUTE}st", "derived:effective_edges": [{"id": "T-0002", "kind": "evidence"}],
                  "control:risk_class": 2, "record:class0_assertions": None}
VECTOR_PAYLOAD_JSON = (b'{"control:risk_class":2,"derived:effective_edges":[{"id":"T-0002","kind":"evidence"}],'
                       b'"record:class0_assertions":null,"record:title":"T\\u00e9st"}')
VECTOR_PAYLOAD_DIGEST = "cc174d60511593500bc3cb1b7e82f830f0490cd20a8ff80f2710be68747766b7"
VECTOR_DIGESTS = {
    "acceptance": "29008922474362fd8942b101b3007577571f02a04fbe5590b73eea7a67d94c70",
    "card": "acc03389ea01f78fd1fa3dff46b5aa6cd69a9411af83abe70839d888c04d2ba5",
    "check_definition": "7a7dee86fd74df27b1870de84bc483b9498882d24fa9094aea9c2ae3abeb2e37",
    "dependencies": "7f485b4dc214054d836176099903a16aaccff65dd0c437f04787f32fd896f84a",
    "gate_set": "834116fdb82bfaf8a396a013b7ed02b08dc598170ab4a79104b40ac93d0509e7",
    "kind": "5b48c10c4491d4b413dec0e88c57dc53c97c20050c20e00d0aead6585c273f93",
    "parent": "ef044331ae4e60709a32b9323d3060a012366936738f04e565241304cc2461a0",
    "scope": "7f2b361a63a9543352dbb25321390b5dcde6a38b768687769ed13a3c2c529f5d",
    "staffing": "6592665325b0cfe477769e8065061312dddda4aacd4d9e2c65090b7dd26ab391",
}


def test_digests_are_platform_independent():
    assert TF.canonical_text(VECTOR_TEXT) == VECTOR_CANONICAL
    assert TF.canonical_json(VECTOR_PAYLOAD) == VECTOR_PAYLOAD_JSON
    # The digest construction itself, recomputed here from the plan's definition (§3.4), not from the module.
    assert hashlib.sha256(b"aew/tfg/v1:card\n" + VECTOR_PAYLOAD_JSON).hexdigest() == VECTOR_PAYLOAD_DIGEST
    assert TF.group_digest("card", VECTOR_PAYLOAD) == VECTOR_PAYLOAD_DIGEST
    text = record_text(goal=[GOAL, "caf\N{LATIN SMALL LETTER E WITH ACUTE}  receipts"], class0=None)
    got = digests(text, edges=[{"id": "T-0007", "kind": "mutating"}], floor=2, story_gates=["security_review"])
    assert dict(got.groups) == VECTOR_DIGESTS
    # The record as stored with CRLF line endings is the same Ticket.
    crlf = text.replace("\n", "\r\n")
    again = digests(crlf, edges=[{"id": "T-0007", "kind": "mutating"}], floor=2, story_gates=["security_review"])
    assert dict(again.groups) == VECTOR_DIGESTS


def test_digests_are_over_the_record_control_state_pins():
    text = record_text()
    state = world(text)
    with pytest.raises(IntegrityError) as err:
        TF.live_digests(state, "T-0001", record_text(goal=["something else"]))
    assert err.value.details["reason"] == "RECORD_MISMATCH"
    with pytest.raises(UsageError):
        TF.live_digests(state, "S-0001", text)


def test_only_the_declared_groups_are_material():
    reg = TF.load_registry()
    assert TF.material(reg.groups) == {"acceptance", "check_definition", "scope", "gate_set", "dependencies", "kind"}
    assert TF.material({"card", "staffing"}) == set()
    assert TF.material({"card"}, card_acceptance_bearing=True) == {"card"}
    assert TF.material({"a_group_this_registry_lacks"}) == {"a_group_this_registry_lacks"}  # fail closed


# ---------------------------------------------------------------------------------------------- review F2, F3, F4


@pytest.mark.parametrize("field,group", [
    pytest.param("scope_paths", "scope", id="scope.paths"),
    pytest.param("inputs", "check_definition", id="acceptance.inputs"),
    pytest.param("checks", "check_definition", id="acceptance.checks"),
])
@pytest.mark.parametrize("authored,folded", [
    pytest.param("src/*.py ", "src/*.py", id="trailing_space"),
    pytest.param("src/a\r\nb.py", "src/a\nb.py", id="crlf"),
    pytest.param(f"src/cafe{ACUTE}.py", f"src/caf{E_ACUTE}.py", id="nfd"),
])
def test_paths_globs_and_check_ids_hash_exactly(field: str, group: str, authored: str, folded: str):
    """ADR-0016 §1.2 (TRV-04): paths, globs and check ids are exact. The text set would fold each pair below into one
    value, so two different scopes or check definitions could collide (review F4)."""
    assert TF.canonical_text(authored) == TF.canonical_text(folded)
    def text(value: str) -> str:
        if field == "scope_paths":
            return record_text(scope_paths=[value])
        return record_text(inputs=[value]) if field == "inputs" else record_text(checks=[value])

    texts = text(authored), text(folded)
    assert changed(digests(texts[0]), digests(texts[1])) == {group}
    ref = {"scope_paths": "record:scope.paths", "inputs": "record:acceptance.inputs",
           "checks": "record:acceptance.checks"}[field]
    assert TF.group_payloads(world(texts[0]), "T-0001", texts[0])[group][ref] == [authored]


def registry_v1_doc() -> dict[str, Any]:
    return json.loads(resources.files("aew.schemas").joinpath("ticket-field-registry.v1.json").read_text("utf-8"))


def control_field(doc: dict[str, Any], name: str) -> dict[str, Any]:
    return next(f for f in doc["control"] if f["field"] == name)


@pytest.mark.parametrize("change,expected", [
    pytest.param("card_material", {"card"}, id="materiality_only"),
    pytest.param("staffing_material", {"staffing"}, id="materiality_of_another_group"),
    pytest.param("carried_obligations_regrouped", {"gate_set", "dependencies"}, id="carried_obligations_regrouped"),
    # carried_obligations, also hashed through the edges, follows them, so its gate_set counts too.
    pytest.param("depends_on_regrouped", {"dependencies", "parent", "gate_set"}, id="depends_on_regrouped"),
    pytest.param("depends_on_via_changed", {"dependencies", "gate_set"}, id="depends_on_hashed_through_other_values"),
    pytest.param("provenance_changed", {"acceptance"}, id="provenance_changed"),
    pytest.param("unassigned_changed", {"acceptance", "scope"}, id="unassigned_changed"),
    pytest.param("checks_rule_changed", {"check_definition"}, id="rule_changed"),
    pytest.param("key_leaves_bookkeeping", {"acceptance"}, id="bookkeeping_changed"),
])
def test_a_registry_change_counts_as_changed_without_a_declared_move(change: str, expected: set[str]):
    """Review F2 (E19-B §2.3): the affected groups come from comparing the two registry versions, not only from the
    moves a version declares. Each synthetic version 2 below declares no move, and the digests are equal."""
    doc = registry_v1_doc()
    v1 = TF.registry_from_doc(doc)
    v2_doc = copy.deepcopy(doc)
    v2_doc.update(version=2, predecessor=v1.identity, moves=[])
    if change == "card_material":
        v2_doc["groups"]["card"]["material"] = True
    elif change == "staffing_material":
        v2_doc["groups"]["staffing"]["material"] = True
    elif change == "carried_obligations_regrouped":  # no longer hashed through the edges, so out of dependencies
        control_field(v2_doc, "carried_obligations").update(
            also=[], via=["effective_class", "class_floor", "inherited_mandatory_gates"])
    elif change == "depends_on_regrouped":  # with the derived value it is hashed through (review R1)
        control_field(v2_doc, "depends_on")["group"] = "parent"
        next(f for f in v2_doc["derived"] if f["field"] == "effective_edges")["group"] = "parent"
        control_field(v2_doc, "carried_obligations")["also"] = ["parent"]
    elif change == "depends_on_via_changed":  # it now feeds gate_set too, so it must also sit there (review R1)
        control_field(v2_doc, "depends_on").update(via=["effective_edges", "effective_class"], also=["gate_set"])
    elif change == "provenance_changed":  # a record key leaves the unassigned group
        v2_doc["provenance"].append("source")
    elif change == "unassigned_changed":
        v2_doc["unassigned"] = "scope"
    elif change == "checks_rule_changed":
        next(f for f in v2_doc["record"] if f["field"] == "acceptance.checks")["rule"] = "text_list"
    else:
        v2_doc["bookkeeping"].remove("attempts")
    v2 = TF.registry_from_doc(v2_doc)
    known = {v1.identity: v1, v2.identity: v2}
    same = {g: "0" * 64 for g in v1.groups}
    before, after = TF.Digests(v1.identity, same), TF.Digests(v2.identity, same)
    assert TF.changed_groups(before, after, registries=known) == expected
    assert TF.changed_groups(after, before, registries=known) == expected
    # Through an intermediate version that changes nothing, the step's change still counts.
    v3_doc = copy.deepcopy(v2_doc)
    v3_doc.update(version=3, predecessor=v2.identity)
    v3 = TF.registry_from_doc(v3_doc)
    known[v3.identity] = v3
    assert TF.changed_groups(before, TF.Digests(v3.identity, same), registries=known) == expected


def record_with(extra: dict[str, Any]) -> str:
    record = work_unit_record(
        unit_id="T-0001", kind="ticket", title="Add subtract()", created_at="2026-10-09T00:00:00Z",
        created_by={"kind": "lead", "session_label": "lead", "generation": 1}, risk_class=1, mutating=True,
        parent="S-0001", scope_paths=["src/calc/*.py"], goal_backwards=[GOAL], contract=[CONTRACT])
    return Record({**record.meta, **extra}, record.body).render()


@pytest.mark.parametrize("value,text", [
    pytest.param(dt.date(2026, 10, 9), "2026-10-09", id="date"),
    pytest.param(dt.datetime(2026, 10, 9, 12, 30, tzinfo=dt.UTC), "2026-10-09T12:30:00+00:00",
                 id="timestamp"),
])
def test_a_yaml_date_never_hashes_like_its_text(value: Any, text: str):
    """Review F3 (E19-B §2.4): a date in an unclassified field is tagged, so it cannot collide with the same text, and
    an authored mapping cannot spell the tag (a key starting with ``$`` is escaped with one more ``$``)."""
    assert TF.canonical(value, "exact") != TF.canonical(text, "exact")
    tag = f"${type(value).__name__}"
    assert TF.canonical(value, "exact") == {tag: text}
    assert TF.canonical(value, "exact") != TF.canonical({tag: text}, "exact")
    assert TF.canonical({"$date": "x", "$$date": "y"}, "exact") == {"$$date": "x", "$$$date": "y"}
    texts = record_with({"due": value}), record_with({"due": text}), record_with({"due": {tag: text}})
    got = [digests(t) for t in texts]
    payload = TF.group_payloads(world(texts[0]), "T-0001", texts[0])["acceptance"]
    assert payload['record:?["due"]'] == {tag: text}  # the record reads back as a YAML date, and is tagged
    assert changed(got[0], got[1]) == {"acceptance"}
    assert changed(got[0], got[2]) == {"acceptance"}
