"""The Lead's system, guide and next-step text use the live catalog and transition rules (E130, E231)."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew import roles
from aew.engine import gates as G
from aew.engine import guide, resume_ops
from aew.engine import transitions as T
from aew.engine.evidence_ops import Gates
from aew.engine.harness_ops import Harness
from aew.engine.resume_ops import Resume
from aew.harness.contract import wake_guidance
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import contract, lead_text
from aew.surface import projection as surface
from aew.surface.context import NORMAL, RECOVERY

PLANTED = "zz_planted"
# A single backticked word: in what a Lead reads, a tool, one of its arguments, or a word listed below.
WORD = re.compile(r"`([a-z][a-z_]*)`")
# The backticked words that are neither a tool nor a tool's argument, each with what it is (#331 review F2). Any other
# backticked word fails the guard: a tool renamed or removed in the catalog, with its old name left in the prose or in
# an engine hint, is caught here, whatever its name.
NOT_TOOLS = {
    "aew": "the command",
    "none": "an assurance (`--assurance none`)",
    "planner": "a card", "researcher": "a card", "verifier": "a role",
    "checks": "a policy file's key", "max_publish_paths": "a policy key", "mutating_concurrency": "a policy key",
    "replace_gate": "a policy key", "coordination_store": "a policy key", "launch": "a policy key",
    "integration_attempt": "a record's field", "projection": "a result's field", "revision": "a result's field",
    "seat": "a field of `aew opencode`'s result: how the Lead seat stands, and the step that goes with it",
    "metadata": "a filesystem term", "chmod": "an operating-system command", "chown": "an operating-system command",
    "diff": "a git command", "log": "a git command", "show": "a git command",
    "read": "OpenCode's own tool, not AEW's", "skill": "OpenCode's own tool, not AEW's",
    "use_when": "a role card's field",
    "why": "a wait result's field: why it returned (E122)",
    "messages": "a wait/wake result's verified worker bodies, data rather than instructions",
    "last_test": "a field of a run's progress digest, which a wait returns (steering design §2)",
    "last_message": "a field of a run's progress digest: the worker's last words, as data (steering design r4 §6)",
    "loop": "a field of a push wake: the steering loop's stop a `loop_waiting` wake is about (A-58 CL-R07)",
    **{key: "what marks a kind of wait return, a key of the wake guidance (E122)" for key in wake_guidance()},
}
# Where the engine's and the surface's words to a Lead are written: every string in these, docstrings aside.
WORDS_IN = ("src/aew/engine", "src/aew/surface", "src/aew/harness/opencode")
ROOT = Path(__file__).resolve().parents[2]
FULL = T.Fit(review=True, verification=True, last_review=True, last_verification=True)


def rendered() -> str:
    return lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)


def test_the_lead_quotes_recorded_coverage_and_the_generated_guide_matches():
    text = guide.render_section("finished-work", DEFAULT_GATES)
    assert "quote AEW's recorded coverage" in text and "never compose coverage yourself or drop its unknowns" in text
    assert "coverage not recorded" in text.lower() and "validated within its scope" in text.lower()
    documented = (ROOT / "docs/guides/lead-guide.md").read_text(encoding="utf-8")
    assert documented.startswith("<!-- Generated:")
    assert documented.partition("-->\n\n")[2] == rendered()


def system_text() -> str:
    """What a Lead's TUI is given: the system text with the guide appended."""
    return projection.lead_config(rendered())["agents"][projection.LEAD_AGENT]["system"]


def plant(monkeypatch: pytest.MonkeyPatch, name: str = PLANTED, **kw: Any) -> None:
    row = contract.Tool(name, kw.pop("kind", contract.STAGE), contract.MECHANICAL, "A planted tool.",
                        {"type": "object", "properties": {}, "additionalProperties": False}, **kw)
    monkeypatch.setitem(contract.TOOLS, name, row)


def stage_named(text: str) -> list[str]:
    """The catalog's tools ``text`` names, any profile."""
    return [w for w in WORD.findall(text) if w in contract.TOOLS or w.startswith("zz_")]


def known_words() -> set[str]:
    normal = contract.exposed(NORMAL)
    return ({t.name for t in normal} | {a for t in normal for a in t.input_schema.get("properties") or {}}
            | set(NOT_TOOLS) | set(DEFAULT_CHECKS["checks"]) | set(G.VERIFICATION_GATES)
            | set(roles.builtin_cards()))  # a card's id, which the staffing line names (E127)


def stray_arguments(text: str) -> list[str]:
    """The arguments ``text`` names that no tool it names takes: a word the guard knows as some tool's argument can
    still be stale for the tool beside it (the review's G9, an argument renamed on one tool and kept by another)."""
    words = WORD.findall(text)
    taken = {a for w in words if w in contract.TOOLS for a in contract.TOOLS[w].input_schema.get("properties") or {}}
    every = {a for t in contract.exposed(NORMAL) for a in t.input_schema.get("properties") or {}}
    return [w for w in words if w in every and w not in contract.TOOLS and w not in taken]


def lead_texts() -> dict[str, str]:
    """What a Lead reads as written: the system text with the guide, and each command's template."""
    return {"system": system_text(),
            **{section: guide.render_section(section, DEFAULT_GATES) for section in guide.SECTIONS},
            **{f"/{k}": v["template"] for k, v in projection.LEAD_COMMANDS.items()}}


def engine_words() -> dict[str, set[str]]:
    """Each backticked word in the engine's and the surface's strings, with where: its hints, refusals and messages."""
    out: dict[str, set[str]] = {}
    for top in WORDS_IN:
        for path in sorted((ROOT / top).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docs = {id(n.body[0].value) for n in ast.walk(tree)
                    if isinstance(n, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and n.body
                    and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    for word in WORD.findall(node.value):
                        out.setdefault(word, set()).add(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    return out


# ------------------------------------------------------------------------------------------- the tool list is derived


def test_every_normal_tool_is_named_in_what_the_lead_is_given():
    text = system_text()
    assert len(contract.exposed(NORMAL)) >= 15
    for t in contract.exposed(NORMAL):
        assert f"`{t.name}`" in text, t.name


def test_the_system_text_says_nothing_of_stages_still_to_come():
    assert "Until typed stages arrive" not in system_text()
    assert projection.lead_tools_text() in projection.LEAD_SYSTEM


@pytest.mark.parametrize("kind", contract.KINDS)
def test_a_tool_added_to_the_catalog_is_named_with_no_other_edit(monkeypatch, kind):
    """The guard's plant: a new normal-profile row of any kind is in the line of tools, so a hand-written list, or a
    grouping that drops a kind, fails here."""
    assert PLANTED not in projection.lead_tools_text()
    plant(monkeypatch, kind=kind)
    assert f"`{PLANTED}`" in projection.lead_tools_text()


def test_the_list_follows_the_catalog_when_a_tool_goes(monkeypatch):
    monkeypatch.setattr(contract, "TOOLS", {k: t for k, t in contract.TOOLS.items() if k != "work_show"})
    assert "`work_show`" not in projection.lead_tools_text()


# ---------------------------------------------------------------------------- no tool the profile does not have


def test_the_text_names_no_tool_the_normal_profile_lacks():
    names = {t.name for t in contract.exposed(NORMAL)}
    text = system_text()
    assert set(stage_named(text)) <= names
    for t in contract.TOOLS.values():
        if t.name not in names:
            assert f"`{t.name}`" not in text, t.name


def test_every_backticked_name_a_lead_reads_is_a_tool_an_argument_or_a_listed_word():
    """#331 review F2: the guard reads every backticked word, not a few prefixes, so `status` or `resume` left in the
    prose after a rename fails here too."""
    known = known_words()
    for name, text in lead_texts().items():
        assert sorted(set(WORD.findall(text)) - known) == [], name


def test_every_backticked_name_in_the_engines_words_is_a_tool_an_argument_or_a_listed_word():
    """The hints, refusals and messages the engine and the surface write for a Lead: the same check, on their source."""
    found = engine_words()
    assert {"harness_wait", "integration_publish", "resolve"} <= set(found)  # the scan reads them
    unknown = {w: sorted(where) for w, where in found.items() if w not in known_words()}
    assert unknown == {}


@pytest.mark.parametrize("name", ["status", "resume", "work_show", "checkpoint", "resolve", "harness_wait",
                                  "integration_publish"])
def test_a_tool_renamed_in_the_catalog_with_its_old_name_left_fails_the_guard(monkeypatch, name):
    """The rename the review drove: the catalog moves, the prose and hints keep the old name."""
    row = contract.TOOLS[name]
    renamed = {k: (t._replace(name=f"{k}_renamed") if k == name else t) for k, t in contract.TOOLS.items()}
    monkeypatch.setattr(contract, "TOOLS", renamed)
    assert row.name not in known_words()
    left = [w for text in lead_texts().values() for w in WORD.findall(text)] + list(engine_words())
    assert name in left


def test_an_argument_a_lead_command_names_is_taken_by_a_tool_it_names():
    for name, command in projection.LEAD_COMMANDS.items():
        assert stray_arguments(command["template"]) == [], name


def test_an_argument_renamed_on_one_tool_with_its_old_name_left_beside_it_fails_the_guard(monkeypatch):
    """`verification_evidence` is `ticket_prepare`'s argument too, so the word guard alone still knows it."""
    row = contract.TOOLS["integration_publish"]
    props = {("integration_report" if k == "verification_evidence" else k): v
             for k, v in row.input_schema["properties"].items()}
    monkeypatch.setitem(contract.TOOLS, "integration_publish",
                        row._replace(input_schema={**row.input_schema, "properties": props}))
    assert "verification_evidence" in known_words()
    hint = resume_with()._integration_verifier(integration_state(report="EV-3"), "T-0007")
    assert stray_arguments(hint) == ["verification_evidence"]


def test_an_argument_renamed_in_the_catalog_with_its_old_name_left_fails_the_guard(monkeypatch):
    def renamed(row: contract.Tool) -> contract.Tool:
        props = {("verification_report" if k == "verification_evidence" else k): v
                 for k, v in (row.input_schema.get("properties") or {}).items()}
        return row._replace(input_schema={**row.input_schema, "properties": props})

    monkeypatch.setattr(contract, "TOOLS", {k: renamed(t) for k, t in contract.TOOLS.items()})
    assert "verification_evidence" not in known_words()
    assert "verification_evidence" in engine_words()


def test_a_recovery_or_designed_row_never_reaches_the_normal_text(monkeypatch):
    plant(monkeypatch, "zz_recovery", profiles=(RECOVERY,), expands_to=("plan.accept",))
    plant(monkeypatch, "zz_designed", status=contract.DESIGNED, expands_to=("plan.accept",))
    text = projection.lead_tools_text() + rendered()
    assert "zz_recovery" not in text and "zz_designed" not in text
    assert "zz_recovery" in {s.tool for s in lead_text.stages(RECOVERY)}


def test_every_lead_command_is_named_aew_so_no_name_collides_with_a_harnesss_own():
    """The operator, 2026-11-08: a bare name can collide with a harness's own command, and the name would then differ
    per harness."""
    assert [name for name in projection.LEAD_COMMANDS if not name.startswith("aew-")] == []


def test_every_document_listing_the_lead_commands_lists_them_all():
    """A second place a list went stale in one pull request: any document naming the handoff command names them all."""
    docs = Path(__file__).resolve().parents[2] / "docs"
    found = [p for p in docs.rglob("*.md") if not {"archive", "contracts"} & set(p.relative_to(docs).parts)
             and "`/aew-handoff`" in p.read_text(encoding="utf-8")]
    assert found
    for path in found:
        text = path.read_text(encoding="utf-8")
        assert [n for n in projection.LEAD_COMMANDS if f"`/{n}" not in text] == [], path


def test_a_lead_command_template_names_only_real_tools_and_takes_no_stage_step_from_the_shell():
    names = {t.name for t in contract.exposed(NORMAL)}
    for name, command in projection.LEAD_COMMANDS.items():
        template = command["template"]
        assert set(stage_named(template)) <= names, name
        # a fixed read is the only inline shell a template may run (ADR-0009): no stage step comes from the shell
        assert re.findall(r"!`([^`]*)`", template) == (["aew usage show"] if name == "aew-usage" else []), name
    assert "`ticket_draft`" in projection.LEAD_COMMANDS["aew-ticket"]["template"]
    assert "`checkpoint`" in projection.LEAD_COMMANDS["aew-handoff"]["template"]


# ---------------------------------------------------------------------------------------------- the data handed over


def test_a_stages_entries_start_at_its_first_required_step():
    """`ticket_start` starts at its assignment; `integration_publish`'s steps are all state-dependent, so each can be
    where it starts (`ticket_prepare` and the rest always start at their first)."""
    by_tool = {s.tool: s for s in lead_text.stages()}
    assert [s.primitive for s in by_tool["ticket_start"].entries()] == ["work.assign"]
    assert [s.primitive for s in by_tool["ticket_prepare"].entries()] == ["verify.ingest"]
    assert "integrate.publish" in {s.primitive for s in by_tool["integration_publish"].entries()}


def test_a_transition_step_says_its_target_and_a_dispatch_says_its_role_or_scope():
    by_tool = {s.tool: s for s in lead_text.stages()}
    assert ("work.transition", "REVIEW_PENDING") in {(s.primitive, s.qualifier)
                                                     for s in by_tool["ticket_request_review"].steps}
    assert ("invoke.create.mutating", "reviewer") in {(s.primitive, s.qualifier)
                                                      for s in by_tool["ticket_request_review"].steps}
    assert ("invoke.create.mutating", "integration") in {(s.primitive, s.qualifier)
                                                         for s in by_tool["ticket_prepare"].steps}


# --------------------------------------------------------------------------- the engine's own words: the one mirror


def derived_stage_at(stages: tuple[guide.Stage, ...]) -> dict[tuple[str, str], str]:
    """Each edge of the transition table that a stage's entry step takes, from the catalog."""
    out = {}
    for (src, dst), rule in T.edges():
        stage = guide._edge_stage(stages, src, dst, rule.via)
        if stage is not None and src in guide.LIFECYCLE:
            out[src, dst] = stage.tool
    return out


def test_the_engines_mirror_of_the_stages_is_the_catalogs_both_ways():
    """The one thing hand-kept (E130): the engine never imports the surface, so its refusals and hints read this table.
    It cannot go stale silently: an edge only one side has fails here, whichever side moved."""
    derived = derived_stage_at(lead_text.stages())
    assert set(T.STAGE_AT) - set(derived) == set(), "the mirror names an edge no stage's entry step takes"
    assert set(derived) - set(T.STAGE_AT) == set(), "a stage takes an edge the mirror lacks: add it to T.STAGE_AT"
    assert T.STAGE_AT == derived


def test_a_stage_planted_at_an_edge_fails_the_mirror_until_it_is_added(monkeypatch):
    plant(monkeypatch, expands_to=("verify.classify",))
    assert ("VERIFICATION_FAILED", "RUNNING") in derived_stage_at(lead_text.stages())
    assert derived_stage_at(lead_text.stages()) != T.STAGE_AT


def test_a_refusal_names_the_stage_first_where_one_takes_the_move():
    """What a Lead reads at the moment it decides: the stage, then the command that is its fallback."""
    text = T.next_steps("REVIEW_PENDING", "T-0007", FULL)
    assert text.index("`ticket_request_verification`") < text.index("`aew review ingest T-0007")
    for edge, tool in T.STAGE_AT.items():
        if T.stage_for(*edge, FULL):
            assert f"`{tool}`, or `aew " in T.next_steps(edge[0], "T-0007", FULL), edge


def test_a_ticket_past_review_is_sent_to_the_stage_its_class_requires():
    """E133: from REVIEW_PASSED, `ticket_prepare` skips the verification phase, so it is named only for a class that
    requires none, and `ticket_request_verification` only for one that does."""
    assert T.stage_for("REVIEW_PASSED", "VERIFY_PENDING", FULL) == "ticket_request_verification"
    assert T.stage_for("REVIEW_PASSED", "COMMIT_READY", FULL) is None
    none_required = FULL._replace(verification=False)
    assert T.stage_for("REVIEW_PASSED", "VERIFY_PENDING", none_required) is None
    assert T.stage_for("REVIEW_PASSED", "COMMIT_READY", none_required) == "ticket_prepare"


def test_a_step_only_a_later_start_skips_is_not_optional_so_no_other_state_starts_there():
    """E133: `ticket_prepare`'s report step is skipped from VERIFIED, and that does not make RUNNING -> COMMIT_READY
    its move."""
    stages = lead_text.stages()
    assert guide._edge_stage(stages, "VERIFIED", "COMMIT_READY", "transition").tool == "ticket_prepare"
    assert guide._edge_stage(stages, "RUNNING", "COMMIT_READY", "transition") is None
    assert guide._edge_stage(stages, "RUNNING", "VERIFY_PENDING", "transition") is None


def test_a_verifier_mode_decision_names_the_publish_with_its_report_and_candidate(monkeypatch):
    """E133: after the integration verifier reports, the typed publish takes the report: the decision carries everything
    the stage requires, and names only a command where the stage is no whole step."""
    part: dict[str, Any] = {"state": "COMMIT_READY", "revision": 3, "decisions": [],
                            "unit": {"integration": {"status": "prepared", "candidate": "C-1"}}}
    surface._ticket_actions(part, "T-0007", 3)
    monkeypatch.setattr(surface, "_reports", lambda *a: ["EV-9"])
    monkeypatch.setattr(surface, "_items", lambda *a, **kw: [])
    monkeypatch.setattr(surface.SA, "stage_availability", lambda *a, **kw: {"availability": "AVAILABLE"})
    engine = SimpleNamespace(stage_fit=lambda state, wid: FULL, store=SimpleNamespace(current=dict))
    [decision] = surface._decisions(engine, part, "T-0007", [], [])
    assert decision["decision"] == "PUBLISH", "named for what its tool does"
    assert decision["tool"] == "integration_publish" and decision["availability"] == "AVAILABLE"
    assert decision["arguments"] == {"expect_rev": 3, "work_id": "T-0007", "verification_evidence": "EV-9",
                                     "prepared_candidate": "C-1"}
    required = contract.tool("integration_publish").input_schema["required"]
    assert set(required) <= set(decision["arguments"])
    engine.stage_fit = lambda state, wid: None
    [command] = surface._decisions(engine, part, "T-0007", [], [])
    assert command["tool"] is None and command["arguments"] is None and "EV-9" in command["cli_fallback"]


@pytest.mark.parametrize("state", ["ASSIGNED", "REVIEW_FAILED"])
def test_a_refusal_in_a_state_no_stage_starts_from_names_only_the_command(state):
    text = T.next_steps(state, "T-0007", FULL)
    assert "`aew work transition T-0007" in text and not stage_named(text)


@pytest.mark.parametrize("state", sorted({frm for frm, _ in T.STAGE_AT}))
def test_a_refusal_that_knows_no_mutating_ticket_names_no_stage(state):
    """#331 review F1: a non-mutating Ticket's refusal, or one whose unit the caller does not know, gives commands."""
    assert not stage_named(T.next_steps(state, "T-0007"))
    assert "`aew " in T.next_steps(state, "T-0007")


@pytest.mark.parametrize(("frm", "dst", "missing"), [("RUNNING", "REVIEW_PENDING", "review"),
                                                     ("REVIEW_PENDING", "REVIEW_PASSED", "verification"),
                                                     ("REVIEW_PENDING", "REVIEW_PASSED", "last_review"),
                                                     ("VERIFY_PENDING", "VERIFIED", "last_verification")])
def test_a_stage_is_named_only_where_the_class_requires_what_it_launches(frm, dst, missing):
    """#331 review F1: `ticket_request_verification` on a class with no verification launches a verifier nobody
    required; with another review still due, it stops after its ingest."""
    assert T.stage_for(frm, dst, FULL) == T.STAGE_AT[frm, dst]
    assert T.stage_for(frm, dst, FULL._replace(**{missing: False})) is None
    assert not stage_named(T.next_steps(frm, "T-0007", FULL._replace(**{missing: False})).split(f"{dst} by ")[1])


@pytest.mark.parametrize("unit", [{"kind": "ticket", "mutating": False}, {"kind": "story"}, {}])
def test_the_gates_fit_no_stage_to_a_non_mutating_ticket_or_a_parent(unit):
    """#331 review F1: whatever its gates, a non-mutating Ticket or a parent has no stage; the gates are not read."""
    gates = Gates.__new__(Gates)
    gates.gate_context = lambda state, wid: pytest.fail("read the gates")  # type: ignore[method-assign]
    assert gates.stage_fit({"work": {"T-0007": unit}}, "T-0007") is None


@pytest.mark.parametrize(("frm", "dst"), [("READY", "ASSIGNED"), ("COMMIT_READY", "DONE")])
def test_a_stage_that_needs_no_gates_is_named_without_reading_them(frm, dst):
    """The control-plane scale guard (`test_no_command_does_per_unit_work`): `status` names `ticket_start` for every
    READY Ticket, so naming it must read no Ticket's evidence."""
    gates = Gates.__new__(Gates)
    gates.gate_context = lambda state, wid: pytest.fail("read the gates")  # type: ignore[method-assign]
    state = {"work": {"T-0007": {"kind": "ticket", "mutating": True}}}
    assert gates.stage_for(state, "T-0007", frm, dst) == T.STAGE_AT[frm, dst]


def test_a_stage_that_needs_the_gates_reads_them_and_follows_the_fit():
    gates = Gates.__new__(Gates)
    gates.stage_fit = lambda state, wid: FULL._replace(verification=False)  # type: ignore[method-assign]
    state = {"work": {"T-0007": {"kind": "ticket", "mutating": True}, "T-0008": {"kind": "ticket", "mutating": False}}}
    assert gates.stage_for(state, "T-0007", "REVIEW_PENDING", "REVIEW_PASSED") is None
    assert gates.stage_for(state, "T-0007", "VERIFY_PENDING", "VERIFIED") == "ticket_prepare"
    assert gates.stage_for(state, "T-0008", "READY", "ASSIGNED") is None


def test_the_gates_fit_reads_what_the_class_requires_and_what_is_still_due():
    gates = Gates.__new__(Gates)
    gc = {"obligations": {"gates": ["review_r1", "review_security", "verification_goal_backwards",
                                    "verification_contract", "verify_card:extra"]},
          "gates": {"review_r1": {"status": "MISSING"}, "review_security": {"status": "CURRENT"},
                    "verification_goal_backwards": {"status": "MISSING"},
                    "verification_contract": {"status": "MISSING"},
                    "verify_card:extra": {"status": "CURRENT"}}}
    gates.gate_context = lambda state, wid: gc  # type: ignore[method-assign]
    state = {"work": {"T-0007": {"kind": "ticket", "mutating": True}}}
    assert gates.stage_fit(state, "T-0007") == T.Fit(review=True, verification=True, last_review=True,
                                                     last_verification=True)  # one review, one verifier still due
    gc["gates"]["review_security"]["status"] = gc["gates"]["verify_card:extra"]["status"] = "MISSING"
    assert gates.stage_fit(state, "T-0007") == T.Fit(review=True, verification=True, last_review=False,
                                                     last_verification=False)


@pytest.mark.parametrize(("frm", "dst"), [(frm, "RUNNING") for frm in ("REVIEW_PENDING", "REVIEW_PASSED",
                                                                       "VERIFY_PENDING", "VERIFIED",
                                                                       "VERIFICATION_INCONCLUSIVE", "COMMIT_READY")]
                         + [("VERIFICATION_INCONCLUSIVE", "VERIFY_PENDING")])
def test_a_move_that_requires_a_reason_is_printed_with_one(frm, dst):
    """#331 review F8: each of these is refused without `--reason`, and the guide and the refusals printed it bare."""
    assert T.RULES[frm, dst].reason_required
    assert "--reason <reason>" in T.command(frm, dst, "T-0007")
    assert f"`aew work transition T-0007 --to {dst} --reason <reason> " in T.next_steps(frm, "T-0007")
# ---------------------------------------------------------------------------------------- the hints a projection shows


def gates_with(fit: T.Fit | None = FULL, **more: Any) -> SimpleNamespace:
    """The gates as the hints read them, with a fit decided by the test (``Gates.stage_for`` is tested on its own)."""
    return SimpleNamespace(stage_for=lambda state, wid, frm, dst: T.stage_for(frm, dst, fit), **more)


def resume_with(fit: T.Fit | None = FULL) -> Resume:
    resume = Resume.__new__(Resume)
    resume.gates = gates_with(fit)  # type: ignore[assignment]
    return resume


def actions(unit_state: str, *, submitted: tuple[str, ...] = (), fit: T.Fit | None = FULL) -> list[str]:
    resume = resume_with(fit)
    resume._submitted = lambda state, wid, unit, kind: list(submitted)  # type: ignore[method-assign]
    return resume._ticket_actions({"invocations": {}}, "T-0007", {"state": unit_state, "invocations": []})


@pytest.mark.parametrize(("state", "edge"), [("READY", ("READY", "ASSIGNED")),
                                             ("REVIEW_PENDING", ("REVIEW_PENDING", "REVIEW_PASSED")),
                                             ("VERIFY_PENDING", ("VERIFY_PENDING", "VERIFIED"))])
def test_a_hint_leads_with_the_stage_and_keeps_the_command(state, edge):
    [hint] = actions(state, submitted=("EV-1",))
    tool = T.STAGE_AT[edge]
    assert f"`{tool}`" in hint and tool in {s.tool for s in lead_text.stages()}
    assert hint.index(f"`{tool}`") < hint.index("`aew ")


@pytest.mark.parametrize(("state", "fit"), [("REVIEW_PENDING", None), ("VERIFY_PENDING", None),
                                            ("REVIEW_PENDING", FULL._replace(verification=False)),
                                            ("REVIEW_PENDING", FULL._replace(last_review=False)),
                                            ("VERIFY_PENDING", FULL._replace(last_verification=False))])
def test_a_hint_names_no_stage_that_is_not_a_whole_step_for_this_ticket(state, fit):
    """#331 review F1, the twins: a non-mutating Ticket (no fit), a class with no verification, and another report
    still due. Each gets the command alone, which was right before E130."""
    [hint] = actions(state, submitted=("EV-1",), fit=fit)
    assert "`aew " in hint and not stage_named(hint), hint


def test_a_validated_candidates_hint_leads_with_the_publish_stage_and_names_the_candidate(monkeypatch):
    """#331 review F6: the stage requires the candidate, so the hint names it."""
    monkeypatch.setattr(resume_ops.V, "obligation", lambda *a: {"mode": "verifier"})
    resume = resume_with()
    resume.k = SimpleNamespace(policy=lambda name: {})
    resume._queue_wait = lambda state, wid: None  # type: ignore[method-assign]
    unit = {"state": "COMMIT_READY", "invocations": [], "integration": {"status": "validated", "candidate": "C-1"}}
    state = {"invocations": {}, "work": {"T-0007": unit}}
    [hint] = resume._ticket_actions(state, "T-0007", unit)
    assert hint.index("`integration_publish`") < hint.index("`aew integrate publish`")
    assert "C-1 as `prepared_candidate`" in hint and stray_arguments(hint) == []


def after_implementation(state: str, *, review: bool, verification: bool = True) -> str:
    harness = Harness.__new__(Harness)
    harness.gates = gates_with(  # type: ignore[assignment]
        FULL._replace(review=review, verification=verification), gate_context=lambda state, wid: {},
        review_gates=lambda gc: review, verification_gates=lambda gc: verification)
    return harness.after_implementation({"work": {"T-0007": {"state": state}}}, "T-0007")


def test_a_finished_implementation_names_the_review_stage_only_where_review_is_next():
    """Only RUNNING -> REVIEW_PENDING has a stage: `ticket_request_review` refuses a Ticket whose class needs none."""
    text = after_implementation("RUNNING", review=True)
    assert text.index("`ticket_request_review`") < text.index("--to REVIEW_PENDING")
    assert not stage_named(after_implementation("RUNNING", review=False))
    assigned = after_implementation("ASSIGNED", review=True)  # the stage starts at RUNNING: that step comes first
    assert assigned.index("--to RUNNING") < assigned.index("`ticket_request_review`")


def integration_state(*, report: str | None = None, verifier: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"work": "T-0007", "state": "VALIDATED" if report else "LEASED"}
    if report:
        entry["validated"] = {"report": report}
    invocations = {verifier: {"custodian": "INV-C", "scope": "integration", "status": "active"}} if verifier else {}
    lease = None if report else {"custodian": "INV-C", "entry": "Q-1"}
    return {"queue": {"entries": {"Q-1": entry}, "lease": lease}, "invocations": invocations,
            "work": {"T-0007": {"integration": {"status": "prepared", "candidate": "C-1"}}}}


def test_after_ticket_prepare_the_hint_never_dispatches_the_verifier_it_launched():
    """The scripted Lead followed `aew invoke create --scope integration` right after the stage had launched it, and was
    refused (LEASE_NOT_HELD). A running verifier says wait, a clean report says publish with it; both name the
    candidate the stage requires (#331 review F6)."""
    running = resume_with()._integration_verifier(integration_state(verifier="INV-9"), "T-0007")
    assert "INV-9" in running and "`harness_wait`" in running and "aew invoke create" not in running
    clean = resume_with()._integration_verifier(integration_state(report="EV-3"), "T-0007")
    assert "EV-3 as `verification_evidence`" in clean and "`integration_publish`" in clean
    assert "aew invoke create" not in clean
    assert "C-1 as `prepared_candidate`" in running and "C-1 as `prepared_candidate`" in clean
    assert stray_arguments(running) == stray_arguments(clean) == []


def test_the_running_verifiers_hint_holds_once_its_run_has_ended():
    """#331 review F7: between the run's end and the custodian's routing, "is verifying" sat beside "ended with
    evidence". The hint says what holds in both."""
    running = resume_with()._integration_verifier(integration_state(verifier="INV-9"), "T-0007")
    assert "is verifying" not in running and "once its run has ended" in running


def test_a_candidate_prepared_from_the_shell_is_still_told_to_dispatch_its_verifier():
    """`aew integrate prepare` launches no verifier, so the lease is held and the dispatch is the next step."""
    hint = resume_with()._integration_verifier(integration_state(), "T-0007")
    assert "aew invoke create T-0007 --scope integration --launch" in hint


def harness_with(fit: T.Fit | None = FULL) -> Harness:
    harness = Harness.__new__(Harness)
    harness.gates = gates_with(fit)  # type: ignore[assignment]
    return harness


@pytest.mark.parametrize(("role", "scope", "tool"), [("reviewer", "ticket", "ticket_request_verification"),
                                                     ("verifier", "ticket", "ticket_prepare"),
                                                     ("verifier", "integration", "integration_publish")])
def test_a_finished_runs_message_leads_with_the_stage_that_accepts_its_report(role, scope, tool):
    state = {"work": {"T-0007": {"kind": "ticket", "mutating": True}}}
    message = harness_with()._after_run(state, {"work_unit": "T-0007", "role": role, "scope": scope},
                                        [{"id": "EV-3", "kind": "review" if role == "reviewer" else "verification"}])
    assert message.index(f"`{tool}`") < message.index("`aew ")


@pytest.mark.parametrize("fit", [None, FULL._replace(verification=False), FULL._replace(last_review=False)])
def test_a_finished_review_names_no_stage_that_is_not_a_whole_step_for_this_ticket(fit):
    """#331 review F1's end-of-run twin: a reviewer's report on a Ticket where `ticket_request_verification` does not
    fit names the ingest alone."""
    state = {"work": {"T-0007": {"kind": "ticket", "mutating": True}}}
    message = harness_with(fit)._after_run(state, {"work_unit": "T-0007", "role": "reviewer", "scope": "ticket"},
                                           [{"id": "EV-3", "kind": "review"}])
    assert "`aew review ingest T-0007" in message and not stage_named(message)


def decisions_offered(fit: T.Fit | None) -> dict[str, Any]:
    part: dict[str, Any] = {"state": None, "unit": {"integration": {"status": "validated", "candidate": "C-1"}},
                            "decisions": []}
    out = {}
    for state in ("REVIEW_PENDING", "VERIFY_PENDING", "COMMIT_READY"):
        part.update(state=state, decisions=[])
        surface._ticket_actions(part, "T-0007", 3)
        [decision] = part["decisions"]
        out[state] = surface._fitting(decision, fit)
    return out


def test_a_decision_offers_its_stage_only_where_it_is_a_whole_step_for_this_ticket():
    """#331 review F1's surface twin: the decisions `status` lists name the same stages the hints do."""
    full = decisions_offered(FULL)
    assert [d["tool"] for d in full.values()] == ["ticket_request_verification", "ticket_prepare",
                                                  "integration_publish"]
    nm = decisions_offered(None)  # a non-mutating Ticket: the commands alone
    assert all(d["tool"] is None and not d.get("arguments") and d["cli"] for d in nm.values())
    no_verification = decisions_offered(FULL._replace(verification=False))
    assert no_verification["REVIEW_PENDING"]["tool"] is None and no_verification["REVIEW_PENDING"]["argument"] is None
    assert no_verification["COMMIT_READY"]["tool"] == "integration_publish"


def test_a_parents_or_non_mutating_report_names_no_stage():
    for unit, role in (({"kind": "story"}, "reviewer"), ({"kind": "ticket", "mutating": False}, "investigator")):
        message = harness_with(None)._after_run({"work": {"S-1": unit}}, {"work_unit": "S-1", "role": role},
                                                [{"id": "EV-3", "kind": "review"}])
        assert not stage_named(message), message
