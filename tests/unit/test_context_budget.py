"""Context packs reserve context in a fixed order (E29; architecture review response §10; recall and routing
design v0.3 §21): constraints, then work, authority and guardrails, then source and evidence, then optional recall.
A lower tier is cut first and a higher one never, and every cut is written into the pack."""

from __future__ import annotations

import random
import re
from typing import Any

import pytest

from aew import roles
from aew.knowledge import context as ctx

SNAPSHOT = {"relevant_inputs_fingerprint": "tree:abc123", "workspace_id": "ws-1", "base_revision": "b" * 40}
GUARDRAIL_MARK = "GUARDRAIL-MARK-never-cut"
CONSTRAINT_MARK = "Prohibited"
RECALL_MARK = "HISTORY-RECORD-BODY"


def inputs(role: str = "reviewer", *, diff_lines: int = 0, history: int = 0, scope: str = "ticket",
           **over) -> ctx.PackInputs:
    base: dict[str, Any] = dict(
        invocation_id="INV-1", role=role, role_def=roles.archetype(role), work_id="T-1", title="Add subtract",
        scope=scope, specialty=None, workspace="C:/ws/T-1", snapshot=SNAPSHOT,
        record_meta={"initial_risk_class": 1, "acceptance": {"goal_backwards": ["subtract works"],
                                                               "contract": ["no regressions"]},
                     "scope": {"paths": ["src/**"]}},
        record_body="Add a subtract function.", plan={"accepted": 1, "sha256": "f" * 64},
        plan_text="Implement subtract in calc.py.",
        guardrails_text=f"protected:\n  - {GUARDRAIL_MARK}\n", checks={"unit": {"configured": True,
                                                                              "description": "unit tests"}},
        authority=[{"path": "docs/design.md", "class": "design", "decision": "D-1"}],
        diff="\n".join(f"+line {i} of the change" for i in range(diff_lines)) if diff_lines else "",
        diffstat=" calc.py | 2 +-", implementation_summary={"files_changed": ["calc.py"], "checks_run": ["unit"]},
        check_results=[{"id": f"E-{i}", "check_id": "unit", "result": "pass", "exit_code": 0, "log": f"l{i}.txt"}
                       for i in range(3)],
        open_findings=[{"id": "F1", "severity": "major", "required": True, "summary": "off by one",
                        "location": "calc.py:3"}],
        history=[{"id": f"H-{i}", "sha256": f"{i:x}" * 64, "kind": "review", "source": "audited history",
                  "reason": "similar change", "content": f"{RECALL_MARK} {i}\n" + "x: y\n" * 40}
                 for i in range(history)],
    )
    base.update(over)
    return ctx.PackInputs(**base)


ALL_ROLES = ["implementer", "reviewer", "verifier", "investigator", "researcher", "planner"]


def everything(role: str) -> ctx.PackInputs:
    """A pack with every optional part present, so that every section the role can have exists."""
    return inputs(role, diff_lines=300, history=6,
                  hierarchy=[{"kind": "story", "id": "S-1", "title": "A story", "risk_class": 1, "plan": 1,
                              "goal_backwards": ["the story works"]}],
                  inherited={"non_waivable": ["review"], "floor": 1},
                  inputs=[{"id": "R-1", "kind": "research_record", "from": "T-0", "freshness": "FRESH",
                           "basis": "same tree", "summary": [{"conclusion": "a finding"}],
                           # what the record left open (E198): a section of its own for a role that produces the work
                           "open": ctx.open_items({"research": {"uncertainties": ["is it stable?", "which version?"],
                                                                "constraints": ["needs 3.11"]}})}],
                  failure_evidence={"id": "V-1", "result": "fail", "claims": [
                      {"type": "contract", "claim": "c", "result": "fail"}], "suspected_cause": "off by one"},
                  card={"display_name": "Reviewer", "role": role, "version": 1, "extends": role,
                        "purpose": "Reviews.", "responsibilities": ["review it"], "skills": [],
                        "required_capabilities": [], "optional_capabilities": [], "outputs": [],
                        "use_when": []})


# ---------------------------------------------------------------------------------------------- the invariant

@pytest.mark.parametrize("role", ALL_ROLES)
def test_a_pack_without_a_budget_is_unchanged_and_has_no_notice(role):
    pack = ctx.assemble(everything(role))
    assert pack.text == ctx.render(everything(role)) and pack.truncations == () and "Context budget" not in pack.text
    assert pack.budget is None and not pack.over_budget


@pytest.mark.parametrize("role", ALL_ROLES)
def test_a_budget_the_pack_fits_in_changes_nothing(role):
    plain = ctx.render(everything(role))
    assert ctx.assemble(everything(role), len(plain)).text == plain
    assert ctx.assemble(everything(role), len(plain) + 5000).text == plain


def test_every_section_is_in_exactly_one_tier_and_the_tiers_read_in_priority_order():
    parts = ctx.sections(everything("reviewer"))
    names = [s.name for s in parts]
    assert len(names) == len(set(names))
    by_tier = {t: {s.name for s in parts if s.tier == t} for t in (1, 2, 3, 4)}
    assert {"contract", "role-card", "review-scope"} <= by_tier[ctx.CONSTRAINTS]
    assert {"requirement", "accepted-plan", "guardrails", "authority", "open-findings"} <= by_tier[ctx.WORK]
    assert {"change", "check-results", "implementation-facts"} <= by_tier[ctx.EVIDENCE]
    assert by_tier[ctx.RECALL] == {"history"}
    assert sum(len(v) for v in by_tier.values()) == len(names)


def test_an_over_budget_reviewer_pack_keeps_constraints_and_guardrails_and_cuts_the_lowest_tier_first():
    p = everything("reviewer")
    pack = ctx.assemble(p, 6000)
    plain = ctx.render(p)
    assert len(plain) > 6000 > ctx.assemble(p, None).mandatory_size and len(pack.text) <= 6000
    # Constraints and guardrails intact:
    for sec in ctx.sections(p):
        if sec.tier in ctx.MANDATORY_TIERS:
            assert "\n".join(ctx._whole(sec)) in pack.text, sec.name
    assert GUARDRAIL_MARK in pack.text and CONSTRAINT_MARK in pack.text
    # The lowest tier is gone first (optional recall) and the evidence is cut next (the diff, last in its tier):
    cut = {c.section: c for c in pack.truncations}
    assert cut["history"].dropped_entirely and cut["history"].tier == "optional recall"
    assert RECALL_MARK not in pack.text
    assert "change" in cut and cut["change"].kept < cut["change"].of
    assert "+line 0 of the change" in pack.text and "+line 299 of the change" not in pack.text


def test_recall_goes_before_evidence_and_evidence_before_the_mandatory_tiers():
    p = everything("reviewer")
    full = ctx.render(p)
    mandatory = ctx.assemble(p, 1).mandatory_size
    evidence = sum(s.size() for s in ctx.sections(p) if s.tier == ctx.EVIDENCE)
    recall = sum(s.size() for s in ctx.sections(p) if s.tier == ctx.RECALL)
    assert len(full) == mandatory + evidence + recall
    # Room for the mandatory tiers, all the evidence and the notice, and one historical record: only recall is
    # touched, and only its tail.
    parts = ctx.sections(p)
    lower = [x for x in parts if x.tier not in ctx.MANDATORY_TIERS]
    history = next(x for x in parts if x.name == "history")
    one = ctx.Section("h", 4, history.head, history.units[:1]).size()
    tight = ctx.assemble(p, mandatory + evidence + one + ctx._notice_bound(10_000, lower, mandatory) + 100)
    assert {c.tier for c in tight.truncations} == {"optional recall"}
    assert RECALL_MARK + " 0" in tight.text and RECALL_MARK + " 2" not in tight.text
    assert "omitted by the context budget" in tight.text
    # Room for the mandatory tiers and half the evidence: all recall is gone, the evidence is cut, nothing else is.
    half = ctx.assemble(p, mandatory + evidence // 2 + 1500)
    tiers = {c.tier for c in half.truncations}
    assert tiers == {"source and evidence", "optional recall"}
    assert [c for c in half.truncations if c.tier == "optional recall"][0].dropped_entirely
    # Not even the evidence fits beside the mandatory tiers: it is dropped too, the mandatory tiers are still whole.
    bare = ctx.assemble(p, mandatory)
    assert bare.over_budget and {c.tier for c in bare.truncations} == {"source and evidence", "optional recall"}
    assert all(c.dropped_entirely for c in bare.truncations)
    assert GUARDRAIL_MARK in bare.text and "constraints and the work, authority and guardrails alone" in bare.text


def test_the_notice_says_what_was_cut_and_where():
    p = everything("reviewer")
    text = ctx.assemble(p, 6000).text
    notice = text.split("## Context budget notice")[1].split("\n## ")[0]
    assert "context budget of 6000 characters" in notice and "NOT absent from the project" in notice
    assert "- history (optional recall): omitted entirely; omitted: history:H-0@000000000000" in notice
    assert re.search(r"- change \(source and evidence\): kept \d+ of \d+ lines", notice)
    assert re.search(r"\[… \d+ more lines omitted by the context budget\]", text)
    # The notice follows the launch contract, before anything the agent works from.
    assert text.index("## Context budget notice") < text.index("## Requirement")


def test_a_cut_inside_a_code_fence_closes_it():
    p = inputs("reviewer", diff_lines=500, check_results=[], open_findings=[], implementation_summary={})
    parts = ctx.sections(p)
    mandatory = ctx.assemble(p, 1).mandatory_size
    lower = [x for x in parts if x.tier not in ctx.MANDATORY_TIERS]
    pack = ctx.assemble(p, mandatory + ctx._notice_bound(10_000, lower, mandatory) + 900)
    text = pack.text
    assert any(c.section == "change" and 0 < c.kept < c.of for c in pack.truncations)
    diff_part = text[text.index("## Change under review"):]
    assert diff_part.count("```") % 2 == 0  # the fence opened for the diff is closed before the marker
    assert diff_part.index("```diff") < diff_part.index("more lines omitted") and "\n```\n[…" in diff_part


def test_historical_records_are_kept_or_omitted_whole():
    p = inputs("implementer", history=8)
    history = next(x for x in ctx.sections(p) if x.name == "history")
    two = ctx.Section("h", 4, history.head, history.units[:2]).size()
    mandatory = ctx.assemble(p, 1).mandatory_size
    lower = [x for x in ctx.sections(p) if x.tier not in ctx.MANDATORY_TIERS]
    pack = ctx.assemble(p, mandatory + two + ctx._notice_bound(10_000, lower, mandatory) + 100)
    (cut,) = pack.truncations
    assert cut.section == "history" and cut.kept == 2 and cut.of == 8
    assert cut.omitted == tuple(f"history:H-{i}@{(f'{i:x}' * 64)[:12]}" for i in range(2, 8))
    for i in range(8):  # no half-record: a record is whole or absent
        assert (f"{RECALL_MARK} {i}\n" in pack.text) == (i < 2)
    assert pack.text.count("x: y") == 2 * 40
    assert ctx._open_fence(pack.text.split("\n")) is None


def test_a_truncated_pack_is_deterministic():
    p = everything("verifier")
    assert ctx.render(p, 4000) == ctx.render(everything("verifier"), 4000)


def test_a_missing_optional_part_leaves_no_empty_section():
    pack = ctx.assemble(inputs("implementer"), 100000)
    assert not any(s.tier == ctx.RECALL for s in ctx.sections(inputs("implementer")))
    assert "Historical reference context" not in pack.text


def recovery(role: str = "implementer", paths: int = 3) -> dict[str, Any]:
    """A replacement's pinned observation, as ``ContextPacks.recovery`` builds it; only an implementer's has the
    workspace. A role outside ``RECOVERY_ROLES`` gets no section from it."""
    out: dict[str, Any] = {
        "predecessor": "INV-0", "role": role, "scope": "ticket", "status": "interrupted", "workspace_id": "ws-1",
        "reason": ctx.bounded_text("Lead takeover"),
        "evidence": ctx.recovery_evidence([{"id": "E-9", "kind": "check_result"}])}
    if role == "implementer":
        listed = [{"path": ctx.bounded_text(f"src/m{i:03}.py"), "untracked": True} for i in range(paths)]
        out["workspace"] = {"id": "ws-1", "base": "b" * 40, "staged": 0, "deleted": 0, "untracked": paths,
                            "paths": ctx.bounded(listed, ctx.RECOVERY_MAX_PATHS)}
    return out


@pytest.mark.parametrize("role", sorted(ctx.RECOVERY_ROLES))
def test_room_a_whole_section_could_not_use_never_funds_a_lower_tier(role):
    """Review of #621, its observation on #614: the recovery section is kept or omitted whole, and across a band of
    budgets it was omitted while the room it left funded a historical record, so evidence was given up before recall.
    At every budget: a historical record is in the pack only when nothing of the source and evidence was cut."""
    p = inputs(role, history=1, scope="ticket" if role == "implementer" else "observation", recovery=recovery(role))
    parts = ctx.sections(p)
    assert {"recovery", "history"} <= {s.name for s in parts}
    mandatory, total = ctx.assemble(p).mandatory_size, sum(s.size() for s in parts)
    seen = set()
    for budget in range(mandatory, total + 1):
        pack = ctx.assemble(p, budget)
        evidence_cut = any(c.tier == "source and evidence" for c in pack.truncations)
        seen.add((evidence_cut, RECALL_MARK in pack.text))
        assert not (evidence_cut and RECALL_MARK in pack.text), budget
        assert "## Recovery reference" in pack.text or "- recovery (source and evidence): omitted entirely" in pack.text
    assert seen == {(True, False), (False, False), (False, True)}


# ------------------------------------------------------------------------------------------------- a property

def random_inputs(rng: random.Random) -> ctx.PackInputs:
    role = rng.choice(ALL_ROLES)
    p = everything(role)
    p.diff = "\n".join(f"+{'x' * rng.randint(0, 80)}" for _ in range(rng.choice([0, 1, 20, rng.randint(1, 400)])))
    p.diffstat = "\n".join(f" f{i}.py | {i}" for i in range(rng.randint(0, 50)))
    p.record_body = "body line\n" * rng.randint(0, 60)
    p.plan_text = "plan line\n" * rng.randint(0, 80)
    p.guardrails_text = f"{GUARDRAIL_MARK}\n" + "rule: x\n" * rng.randint(0, 40)
    p.history = [dict(h, content=h["content"] + "y: z\n" * rng.randint(0, 100))
                 for h in p.history[:rng.randint(0, 3)]]
    p.check_results = p.check_results * rng.randint(0, 30)
    p.open_findings = p.open_findings * rng.randint(0, 6)
    p.inputs = [dict(i, open=ctx.open_items({"research": {
        "uncertainties": [f"doubt {'y' * rng.randint(0, 300)}"] * rng.randint(0, 14),
        "constraints": ["a limit"] * rng.randint(0, 3)}})) for i in p.inputs]
    if rng.random() < 0.5:  # a replacement's recovery section (register F36): kept or omitted whole
        p.recovery = recovery(role, paths=rng.randint(0, 40))
    return p


@pytest.mark.parametrize("seed", range(40))
def test_random_sections_and_budgets_never_cut_a_higher_tier_before_a_lower_one(seed):
    rng = random.Random(seed)
    for _ in range(25):
        p = random_inputs(rng)
        parts = ctx.sections(p)
        mandatory = sum(s.size() for s in parts if s.tier in ctx.MANDATORY_TIERS)
        full = sum(s.size() for s in parts)
        budget = rng.choice([1, mandatory // 2, mandatory, mandatory + rng.randint(0, 3000),
                             rng.randint(mandatory, full + 500)])
        pack = ctx.assemble(p, budget)
        text = pack.text
        # 1. The mandatory tiers are always whole, whatever the budget.
        for s in parts:
            if s.tier in ctx.MANDATORY_TIERS:
                assert "\n".join(ctx._whole(s)) in text, (seed, budget, s.name)
        # 2. Within the budget unless the mandatory tiers and the notice alone exceed it, and then nothing optional
        #    survives; with no truncation there is no notice and the pack is the full pack.
        if pack.truncations:
            assert "## Context budget notice" in text
            assert len(text) <= budget or pack.over_budget
            if pack.over_budget:
                assert all(c.dropped_entirely for c in pack.truncations if c.tier != "work, authority and guardrails")
        else:
            assert text == ctx.render(p) and full <= budget
        # 3. The order of cuts follows the tiers: evidence is cut only once all optional recall is given up.
        cut_tiers = {c.tier for c in pack.truncations}
        assert "work, authority and guardrails" not in cut_tiers and "constraints" not in cut_tiers
        if "source and evidence" in cut_tiers:
            recall = {x.name for x in parts if x.tier == ctx.RECALL}
            assert {c.section for c in pack.truncations if c.dropped_entirely} >= recall, (seed, budget)
        # 3a. A section that is kept or omitted whole (review of #621): a record's open questions are whole lists, so
        #     no count is shown without its items and no heading without one; an implementer's failure evidence is
        #     funded before them, and in these packs, whose failure evidence has only short lines, is whole while they
        #     are kept (within a tier a cut section still leaves its room to later ones: register F36's note of
        #     2026-11-26); and a recovery section is never there in part.
        lines = text.split("\n")
        for s in parts:
            if s.name == "open-questions":
                whole = [unit for unit in s.units if unit[0] in lines]
                assert all("\n".join(unit) in text for unit in whole), (seed, budget)
                assert whole == s.units[:len(whole)] and (s.head[1] in lines) == bool(whole), (seed, budget)
                if whole:
                    assert "failure-evidence" not in {c.section for c in pack.truncations}, (seed, budget)
            if s.name == "recovery":
                assert all(line in lines for line in s.head) or s.head[1] not in lines, (seed, budget)
        # 4. What the notice lists is exactly what the structured record lists.
        for c in pack.truncations:
            assert f"- {c.section} ({c.tier}): " in text
        # 5. Fences stay balanced in what was kept of the cut sections.
        assert text.count("\n```") >= 0 and ctx._open_fence(text.split("\n")) is None, (seed, budget)
        # 6. Deterministic.
        assert ctx.render(p, budget) == text
