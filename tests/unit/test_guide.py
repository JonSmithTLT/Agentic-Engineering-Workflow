"""The Lead's guide (`aew guide`, F16): generated from the project's policy and the engine's transition table.

Model Leads learned AEW by trial and error in the M3 dogfood (51 refused commands of 887, 37 `--help` lookups), and
no Lead chose Class 0: its only example showed Class 1, Class 0 read as unevidenced, and nothing said when it
applies (Q10: X4a, X4b, X4c). The guide says what the engine enforces, so these tests tie it to the engine.
"""

from __future__ import annotations

import copy
from pathlib import Path

from aew.engine import guide
from aew.engine import transitions as T
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES

DOC = Path(__file__).resolve().parents[2] / "docs" / "implementation" / "lead-guide.md"
CONFIGURED = {"checks": {"unit": {"configured": True, "command": ["{python}", "-m", "pytest"]}}}


def test_the_workflow_contracts_classes_are_explained_with_their_examples():
    text = guide.render(DEFAULT_GATES, CONFIGURED)
    for c, (name, meaning, example) in guide.CLASS_TEXT.items():
        assert f"**Class {c}, {name}:** {meaning}. For example: {example}." in text
    assert "not its size" in text and "lowering it needs a recorded decision" in text
    # Class 0 eligibility is the amendment's predicate, enforced at dispatch since M4-A (Q10 decided 2026-10-03).
    assert "**Class 0 eligibility** (enforced when a mutating Ticket is dispatched at Class 0)" in text
    assert "never reclassified" in text and "aew work reclassify <T> --class N --reason" in text
    assert "not defined yet" not in text


def test_each_class_lists_exactly_the_gates_this_projects_policy_requires():
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["risk_paths"]["2"] = gates["risk_paths"]["2"] + ["review_security"]
    text = guide.render(gates, CONFIGURED)
    assert "- **Class 0:** the implementer's local checks pass on the change as submitted (`unit`). Runs: an " \
           "implementer, a post-integration verifier." in text
    assert "- **Class 1:**" in text and "- **Classes 3 and 4:**" in text  # 2 now differs, so it stands alone
    assert "an independent `security` review passes" in text.split("- **Class 2:**")[1].split("\n")[0]


def test_class_0_is_explained_as_evidenced_and_the_implementation_is_accepted_by_transition():
    text = guide.render(DEFAULT_GATES, CONFIGURED)
    assert "**Class 0 is still evidenced.**" in text  # X4b
    assert "the post-integration verification, the guardrails, and an accepted plan all still apply" in text
    assert "**Accept the implementation by transition**" in text  # the most refused command in the dogfood
    assert "(`aew evidence ingest` is for non-mutating Tickets only.)" in text
    assert "--class <0-4>" in text and "--class 1 " not in text  # X4a: no anchoring example


def test_every_listed_move_is_one_the_engine_allows():
    text = guide.render(DEFAULT_GATES, CONFIGURED)
    for state in guide.LIFECYCLE:
        line = next((ln for ln in text.splitlines() if ln.startswith(f"- **{state}** → ")), None)
        if line is None:
            continue
        for move in line.split(" → ", 1)[1].split("; "):
            dst = move.split(":")[0]
            assert dst in T.allowed_from(state), f"{state} -> {dst} is listed but the engine refuses it"
    for name, to in T.VERIFICATION_CLASSIFICATIONS.items():
        assert f"`{name}` → {to}" in text


def test_the_guide_follows_the_post_integration_policy_and_names_unconfigured_checks():
    gates = copy.deepcopy(DEFAULT_GATES)
    gates["post_integration"] = {"verification": False, "checks": []}
    text = guide.render(gates, DEFAULT_CHECKS)
    assert "post-integration verifier" not in text and "--scope integration" not in text
    assert "Checks not configured yet (their gates stay blocked): unit." in text


def test_the_committed_lead_guide_matches_what_aew_renders_for_its_defaults():
    """docs/implementation/lead-guide.md is the guide for a project on AEW's default policy (`aew init`). It is
    generated, never edited: if this fails, regenerate it from `guide.render(DEFAULT_GATES, DEFAULT_CHECKS)`."""
    assert guide.render(DEFAULT_GATES, DEFAULT_CHECKS) in DOC.read_text(encoding="utf-8")
