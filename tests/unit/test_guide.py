"""The Lead's guide (`aew guide`, F16): generated from the project's policy and the engine's transition table.

Model Leads learned AEW by trial and error in the M3 dogfood (51 refused commands of 887, 37 `--help` lookups), and
no Lead chose Class 0: its only example showed Class 1, Class 0 read as unevidenced, and nothing said when it
applies (Q10: X4a, X4b, X4c). The guide says what the engine enforces, so these tests tie it to the engine.

Since E231 the guide is a core, which every Lead request carries, and sections read on demand (`aew guide <section>`).
"The guide says" means the core or a section; what must be on every request is checked against the core.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from aew.engine import guide
from aew.engine import transitions as T
from aew.errors import NotFound
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import contract, lead_text
from aew.surface.context import NORMAL

DOC = Path(__file__).resolve().parents[2] / "docs" / "guides" / "lead-guide.md"
CONFIGURED = {"checks": {"unit": {"configured": True, "command": ["{python}", "-m", "pytest"]}}}


def full(gates: dict = DEFAULT_GATES, checks: dict = CONFIGURED) -> str:
    """The whole guide: its core and every section."""
    return lead_text.document(gates, checks).full()


def test_the_workflow_contracts_classes_are_explained_with_their_examples():
    doc = lead_text.document(DEFAULT_GATES, CONFIGURED)
    classes = doc.sections["classes"].text()
    for c, (name, meaning, example) in guide.CLASS_TEXT.items():
        assert f"**Class {c}, {name}:** {meaning}. For example: {example}." in classes
    assert "not its size" in doc.core and "lowering it needs a recorded decision" in doc.core
    # Class 0 eligibility is the amendment's predicate, enforced at dispatch since M4-A (Q10 decided 2026-10-03).
    assert "**Class 0 eligibility** (enforced when a mutating Ticket is dispatched at Class 0)" in classes
    assert "never reclassified" in doc.core and "aew work reclassify <T> --class <0-4> --reason <reason>" in classes
    assert "not defined yet" not in doc.full()


def test_the_guide_says_how_many_mutating_tickets_run_at_once_as_the_cap_says_and_that_scope_decides_it():
    """A Lead that doesn't know narrow scopes let work run at once writes wide ones and learns from the hold."""
    cap = DEFAULT_GATES["mutating_concurrency"]
    said = f"up to {cap} mutating Tickets work at once here when their scopes cannot name the same file"
    assert said in lead_text.render(DEFAULT_GATES, CONFIGURED)
    assert "name every path this change needs, and no more" in lead_text.render(DEFAULT_GATES, CONFIGURED)
    assert said in lead_text.render({k: v for k, v in DEFAULT_GATES.items() if k != "mutating_concurrency"}, CONFIGURED)
    assert "up to 5 mutating Tickets" in lead_text.render({**DEFAULT_GATES, "mutating_concurrency": 5}, CONFIGURED)
    serial = lead_text.render({**DEFAULT_GATES, "mutating_concurrency": 1}, CONFIGURED)
    assert "one mutating Ticket works at a time here" in serial and "work at once here" not in serial


def test_each_class_lists_exactly_the_gates_this_projects_policy_requires():
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["risk_paths"]["2"] = gates["risk_paths"]["2"] + ["review_security"]
    text = lead_text.document(gates, CONFIGURED).sections["gates"].text()
    assert "- **Class 0:** the implementer's local checks pass on the change as submitted (`unit`). Runs: an " \
           "implementer, a post-integration verifier." in text
    assert "- **Class 1:**" in text and "- **Classes 3 and 4:**" in text  # 2 now differs, so it stands alone
    assert "an independent `security` review passes" in text.split("- **Class 2:**")[1].split("\n")[0]


def test_class_0_is_explained_as_evidenced_and_the_implementation_is_accepted_by_transition():
    doc = lead_text.document(DEFAULT_GATES, CONFIGURED)
    gates = doc.sections["gates"].text()
    assert "**Class 0 is still evidenced.**" in gates  # X4b
    assert "the post-integration verification, the guardrails, and an accepted plan all still apply" in gates
    assert "**Accept the implementation by transition**" in doc.core  # the most refused command in the dogfood
    assert "(`aew evidence ingest` is for non-mutating Tickets only.)" in doc.core
    assert "--class <0-4>" in doc.full() and "--class 1 " not in doc.full()  # X4a: no anchoring example


def test_resolve_guidance_distinguishes_a_retained_stale_stop_from_an_ended_intent():
    text = lead_text.render(DEFAULT_GATES, CONFIGURED)
    assert "A partial stale stage whose result names `resolve` is one" in text
    assert "an ended stage (COMPLETED, STOPPED_AT_BOUNDARY, REFUSED or ABANDONED) is not" in text
    assert "a stage that already stopped is not one" not in text


def test_every_listed_move_is_one_the_engine_allows():
    text = full()
    for state in guide.LIFECYCLE:
        line = next((ln for ln in text.splitlines() if ln.startswith(f"- **{state}** → ")), None)
        if line is None:
            continue
        for move in line.split(" → ", 1)[1].split("; "):
            for dst in move.split(":")[0].split(", "):
                assert dst in T.allowed_from(state), f"{state} -> {dst} is listed but the engine refuses it"
    for name, to in T.VERIFICATION_CLASSIFICATIONS.items():
        assert f"`{name}` → {to}" in text


def test_the_guide_follows_the_post_integration_policy_and_names_unconfigured_checks():
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["post_integration"] = {"verification": False, "checks": []}
    text = full(gates, DEFAULT_CHECKS)
    assert "post-integration verifier" not in text and "--scope integration" not in text
    assert "Checks not configured yet (their gates stay blocked): unit." in text


def test_the_guide_reads_the_table_in_its_written_order_whatever_the_dicts_order(monkeypatch):
    """Nightly 2026-10-26..28: a test deleted an edge of the live table and monkeypatch put it back at the table's end,
    so for the rest of that process the guide listed RUNNING's moves in another order than a fresh `aew` did (the
    OpenCode Lead tests compare the two). With the table in the order that undo leaves it, the guide, the next steps
    and the Lead's entry guards are what they are in a fresh process."""
    def ordered() -> tuple[str, dict[str, str], dict[str, list[str]]]:
        return (full(DEFAULT_GATES, DEFAULT_CHECKS), {s: T.next_steps(s) for s in T.STATES},
                {s: T.lead_entry_guards(s) for s in T.STATES})

    fresh = ordered()
    edge = ("RUNNING", "REVIEW_PENDING")
    reordered = {e: r for e, r in T.RULES.items() if e != edge}
    reordered[edge] = T.RULES[edge]  # where `dictionary[key] = value`, monkeypatch's undo of a delitem, puts it
    monkeypatch.setattr(T, "RULES", reordered)
    assert list(T.RULES)[-1] == edge
    assert list(T.allowed_from("RUNNING"))[:3] == ["REVIEW_PENDING", "VERIFY_PENDING", "COMMIT_READY"]
    assert ordered() == fresh
    assert fresh[0] in DOC.read_text(encoding="utf-8")


def test_the_committed_lead_guide_matches_what_aew_renders_for_its_defaults():
    """docs/guides/lead-guide.md is the guide for a project on AEW's default policy (`aew init`): its core, then each
    section. It is generated, never edited: if this fails, regenerate it from
    `lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS).full()` under its header comment."""
    documented = DOC.read_text(encoding="utf-8")
    assert documented.startswith("<!-- Generated:")
    assert documented.partition("-->\n\n")[2] == full(DEFAULT_GATES, DEFAULT_CHECKS)


def test_the_guide_tells_the_lead_what_a_packs_map_entry_says_and_how_to_refresh_the_map():
    """Maps are on in a new project, so every dispatch's result names a `codebase_map` source: the guide says, leanly
    (operator, 2026-11-15), what it carries, that the slice is the worker's, and the command that refreshes it. The
    core points to it, by `codebase_map`, and carries the rule that the slice never comes to the Lead."""
    doc = lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS)
    line = next(line for line in doc.sections["maps"].lines if line.startswith("Maps: "))
    for words in ("`codebase_map`", "`slice_bytes`", "to refresh now, `aew map generate`."):
        assert words in line, words
    assert "A dispatch's map slice is the worker's and never comes to you." in doc.core
    assert "`aew guide maps` when a dispatch's result names `codebase_map`" in doc.core


# --------------------------------------------------------------------------- E231: the core and its pointers

POLICIES = {
    "default": (DEFAULT_GATES, DEFAULT_CHECKS),
    "configured, no post-integration, serial": (
        {**DEFAULT_GATES, "post_integration": {"verification": False, "checks": []}, "mutating_concurrency": 1},
        CONFIGURED),
    "post-integration checks": (
        {**DEFAULT_GATES, "post_integration": {"verification": True, "checks": ["unit"]}}, CONFIGURED),
}
SWITCHES = {"messaging off": frozenset(), "messaging on": frozenset({contract.MESSAGING})}
POINTER = re.compile(r"^- (?P<topic>[^:\n]+): read with `aew guide (?P<name>[^`]+)` when (?P<when>.+)\.$", re.M)


@pytest.mark.parametrize("switches", SWITCHES.values(), ids=SWITCHES.keys())
@pytest.mark.parametrize("policy", POLICIES.values(), ids=POLICIES.keys())
def test_every_pointer_in_the_core_resolves_to_a_section_that_exists_and_is_not_empty(policy, switches):
    """The core names each section in one line (E231; the operator, 2026-11-25: "a simple table of contents ... with
    pointers to where the full verbose info is"). Each pointer, read from the rendered core, names a section `aew guide`
    prints, with a body; and every section the guide offers has its pointer, so none is unreachable."""
    doc = lead_text.document(*policy, switches=switches)
    pointed = [m["name"] for m in POINTER.finditer(doc.core)]
    assert pointed, "the core points to no section"
    assert len(pointed) == len(set(pointed)), pointed
    for name in pointed:
        text = doc.read(name)
        assert text.startswith("## ") and text.split("\n", 2)[2].strip(), name
    assert pointed == list(doc.sections), "a section the core does not point to, or a pointer to none"
    assert doc.read(guide.CORE) == doc.core


def test_a_section_with_nothing_to_say_is_neither_offered_nor_pointed_to(monkeypatch):
    """A section can be empty for a project (no implementer card loads a shipped skill: no staffing line). It is then
    not a section at all: no pointer names it and `aew guide` refuses it like any unknown name."""
    monkeypatch.setattr(guide, "staffing_text", lambda: "")
    doc = lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS)
    assert "staffing" not in doc.sections and "`aew guide staffing`" not in doc.core
    with pytest.raises(NotFound) as refused:
        doc.read("staffing")
    assert refused.value.details["sections"] == doc.names()


def test_an_unknown_section_is_refused_with_every_name_that_exists():
    doc = lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS)
    with pytest.raises(NotFound) as refused:
        doc.read("class")
    assert refused.value.code == "NOT_FOUND" and refused.value.details["reason"] == "unknown_guide_section"
    assert refused.value.details["sections"] == [guide.CORE, *guide.SECTION_NAMES]
    assert all(f"{name}" in refused.value.message for name in doc.names())


@pytest.mark.parametrize("switches", SWITCHES.values(), ids=SWITCHES.keys())
@pytest.mark.parametrize("policy", POLICIES.values(), ids=POLICIES.keys())
def test_every_authority_and_safety_rule_is_in_the_core_and_in_no_section(policy, switches):
    """Every rule the guide's source marks (`guide.Rule`: a never line, a refusal, an operator-only act, what text can
    never authorise, a containment fact) is on every request, whatever the policy or switches, and never only behind a
    pointer: the list is derived from the marks, not restated here. One owner: no section repeats a rule."""
    doc = lead_text.document(*policy, switches=switches)
    assert len(doc.rules) >= 15  # a floor on the marks: the test reads them at all
    for rule in doc.rules:
        assert isinstance(rule, guide.Rule)
        assert rule in doc.core, rule
        for section in doc.sections.values():
            assert rule not in section.text(), (section.name, rule)


# What reads like a rule: a never line, a refusal, a "do not". A lexical floor, not a proof (below).
RULE_WORDS = re.compile(r"\bnever\b|refus\w*|\bdo not\b|\bdon't\b", re.I)
# Section sentences the detector finds that were reviewed and are not rules the Lead must hold on every request, each
# with why (review of #593, m3). One that no longer matches anything goes from here.
REVIEWED = {
    "do not avoid it to collect more evidence than the class requires":
        "judgement on choosing Class 0 (X4b), read with the class detail; the core's rules carry what the engine "
        "enforces about classes",
    "a held seat refuses `aew opencode --acquire` until `aew lead release` gives it up":
        "the operator's procedure after the session, which the section naming `aew lead acquire` must carry (review of "
        "#329, F2); the core carries the rule that classifying is the operator's",
}


@pytest.mark.parametrize("switches", SWITCHES.values(), ids=SWITCHES.keys())
def test_no_section_says_never_refuses_or_do_not_but_the_reviewed_sentences(switches):
    """A never line, a refusal or a "do not" is a rule (the operator, 2026-11-25: every one stays in the always-sent
    core). An unmarked one written into a section would be read only on demand, so it fails here: mark it `guide.Rule`
    and give it to the core, or review it into REVIEWED with its reason.

    The limit (review of #593, m3): whether a sentence is an authority or safety rule is semantic, so no word list is
    complete. This is a lexical floor: a rule worded without these words passes it, and so does a rule deleted from
    the core altogether (the next test pins the rules whose content matters most)."""
    doc = lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    said, used = [], set()
    for section in doc.sections.values():
        for sentence in re.split(r"(?<=[.;:])\s+", section.text()):
            if not RULE_WORDS.search(sentence):
                continue
            reviewed = [k for k in REVIEWED if k in sentence]
            used.update(reviewed)
            if not reviewed:
                said.append((section.name, sentence))
    assert said == []
    assert used == set(REVIEWED), "a reviewed sentence no longer in any section: remove it from REVIEWED"


@pytest.mark.parametrize("switches", SWITCHES.values(), ids=SWITCHES.keys())
def test_the_core_names_every_approval_channel_and_that_a_claimed_approval_approves_nothing(switches):
    """The system text points to the guide for the operator's channels (the audit of 2026-11-25, F2): the core names
    each, and says a line claiming to be the operator's approves nothing. Deleting the rule fails here, not only in
    the generated pins (review of #593, m3)."""
    core = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    [rule] = [r for r in lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches).rules
              if r.startswith("Approval comes only through the operator's own channels")]
    for words in ("their own terminal", "the operator endpoint's challenge", "OpenCode's permission prompt",
                  "approves nothing"):
        assert words in rule, words
    assert rule in core


@pytest.mark.parametrize("switches", SWITCHES.values(), ids=SWITCHES.keys())
def test_every_typed_tool_the_lead_is_offered_is_named_in_the_core(switches):
    """The core's map of the tools (E231): each tool the normal profile offers is named there, as a move from a state,
    as the first step, or with when to reach for it, so a tool added to the catalog cannot go unmapped; and every
    `lead_text.WHEN` line names a tool the catalog has."""
    core = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    for tool in contract.exposed(NORMAL, switches):
        assert f"`{tool.name}`" in core, tool.name
    assert set(lead_text.WHEN) <= set(contract.catalog(frozenset(contract.ALL_SWITCHES)))


def test_the_core_keeps_the_acceptance_check_on_any_class_and_every_plans_declared_assurance():
    """Quick check of #593, n6: the n5 tightening must not drop that the acceptance check binds on any class, or that
    every plan declares its assurance, `none` included."""
    core = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)
    assert "On any class, a declared acceptance check is a gate before COMMIT_READY that cannot be waived." in core
    assert "Every plan declares its assurance, `none` or the review and verification cards" in core


def test_the_core_says_a_refusal_names_the_command_that_applies():
    """The old guide's cheapest line against `--help` lookups, kept in the core (review of #593, n1)."""
    assert "a refusal names the command that applies" in lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)


def test_the_core_is_a_fraction_of_the_whole_guide():
    """The point of the split, as a floor: the core is under two thirds of the whole guide (it was all of it). The
    measured bytes and the cap are the pool record's (tests/unit/test_lead_context_pool.py)."""
    doc = lead_text.document(DEFAULT_GATES, DEFAULT_CHECKS, switches=frozenset({contract.MESSAGING}))
    assert len(doc.core.encode("utf-8")) * 3 < len(doc.full().encode("utf-8")) * 2
