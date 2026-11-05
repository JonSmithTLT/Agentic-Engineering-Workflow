"""The Lead's text names its typed tools, derived from the catalog, and nobody keeps it up to date by hand (E130).

The operator, 2026-11-04: "are we going to have to manually keep the system text up to date?" Eight real sessions showed
63% of the screen in shell tails, while a typed call is one row, and everything the Lead read pointed it at the shell.
These tests are the answer: the system text's tools are `contract.TOOLS`' for the normal profile, a step a stage covers
is led by that stage, and the shell stays the named way where no stage covers a step. A planted catalog row moves the
text with no other edit. What is still hand-written is the prose, listed in the pull request.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from typing import Any

import pytest

from aew.engine import guide, resume_ops
from aew.engine import transitions as T
from aew.engine.harness_ops import Harness
from aew.engine.resume_ops import Resume
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import availability as SA
from aew.surface import contract, lead_text
from aew.surface.context import NORMAL, RECOVERY

PLANTED = "zz_planted"
# The text's name for a typed tool: only these prefixes name tools, and the arguments they take are not spelled so.
TOOL_NAME = re.compile(r"`((?:ticket|integration|harness|zz)_[a-z_]+)`")


def rendered() -> str:
    return lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)


def system_text() -> str:
    """What a Lead's TUI is given: the system text with the guide appended."""
    return projection.lead_config(rendered())["agents"][projection.LEAD_AGENT]["system"]


def plant(monkeypatch: pytest.MonkeyPatch, name: str = PLANTED, **kw: Any) -> None:
    row = contract.Tool(name, kw.pop("kind", contract.STAGE), contract.MECHANICAL, "A planted tool.",
                        {"type": "object", "properties": {}, "additionalProperties": False}, **kw)
    monkeypatch.setitem(contract.TOOLS, name, row)


def steps(text: str) -> dict[str, str]:
    """Each numbered step of the mutating path, by what leads it."""
    section = text.split("## A mutating Ticket, step by step", 1)[1].split("Each state and the moves", 1)[0]
    found = re.split(r"^\d+\. ", section, flags=re.MULTILINE)[1:]
    return {step.split(":", 1)[0]: step for step in found}


def state_row(text: str, state: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"- **{state}** → "))


def covered(stages: tuple[guide.Stage, ...]) -> list[tuple[guide.Move, guide.Stage]]:
    return [(m, s) for m in guide.PATH if (s := guide._covering(stages, m)) is not None]


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


# --------------------------------------------------------------------------------------- the stage leads what it covers


def test_a_step_a_stage_covers_is_led_by_that_stage_and_its_shell_command_follows():
    stages, found = lead_text.stages(), steps(rendered())
    moves = covered(stages)
    assert {s.tool for _, s in moves} == set(SA.STAGES)
    for move, stage in moves:
        step = found[f"`{stage.tool}`"]
        assert step.index(stage.description) < step.index("Shell fallback:")
        assert move.shell in step.split("Shell fallback:", 1)[1], (stage.tool, move.shell)
        assert move.shell not in step.split("Shell fallback:", 1)[0], (stage.tool, move.shell)


def test_every_stage_step_is_on_the_path_so_no_stage_is_left_out_of_the_guide():
    """A migrated stage whose step the path does not know would keep its shell command as the lead, silently. A launch
    is its dispatch's own run: no move of its own."""
    path = {(m.primitive, m.qualifier) for m in guide.PATH}
    for stage in lead_text.stages():
        if stage.tool in SA.STAGES:
            missing = [s for s in stage.steps if (s.primitive, s.qualifier) not in path
                       and s.primitive != "dispatch.launch"]
            assert not missing, (stage.tool, missing)


def test_a_stage_planted_over_a_move_no_stage_covers_takes_it_over_with_no_other_edit(monkeypatch):
    """The other half of the guard: no second table says which tool takes which step. `plan.accept` has no stage today;
    planting one moves the step to it, the shell command becoming its fallback."""
    shell = next(m.shell for m in guide.PATH if m.primitive == "plan.accept")
    assert steps(rendered())["Accept the plan"].startswith(f"Accept the plan: {shell}")
    plant(monkeypatch, expands_to=("plan.accept",))
    now = steps(rendered())
    assert "Accept the plan" not in now
    assert shell in now[f"`{PLANTED}`"].split("Shell fallback:", 1)[1]


def test_a_move_a_stage_starts_at_names_it_and_one_it_passes_through_does_not():
    """A stage takes a Ticket only from its first step's state: step 1 of E130 measured the refusal from a later one
    ("T-0001 is REVIEW_PASSED, not REVIEW_PENDING"). So the states a stage only passes through keep the command."""
    text = rendered()
    named = {"READY": "ticket_start", "RUNNING": "ticket_request_review",
             "REVIEW_PENDING": "ticket_request_verification", "VERIFY_PENDING": "ticket_prepare",
             "COMMIT_READY": "integration_publish"}
    for state, tool in named.items():
        assert f"`{tool}`" in state_row(text, state)
    for state in ("ASSIGNED", "REVIEW_PASSED", "REVIEW_FAILED", "VERIFIED", "VERIFICATION_INCONCLUSIVE"):
        row = state_row(text, state)
        assert not TOOL_NAME.search(row) and guide.TRANSITION in row, row


def test_a_moves_stage_is_one_the_engine_lets_it_start_from():
    """Each edge the table gives a stage is that stage's entry step, by the transition table's own operation."""
    stages = lead_text.stages()
    for state in guide.LIFECYCLE:
        for dst, via in contract_edges(state):
            stage = guide._edge_stage(stages, state, dst, via)
            if stage is None:
                continue
            primitive = guide._PRIMITIVE_OF.get(via, via)
            entries = {s.primitive for s in stage.entries()}
            assert primitive in entries or f"{primitive}.integration" in entries, (state, dst, stage.tool)


def contract_edges(state: str) -> list[tuple[str, str]]:
    return list(T.allowed_from(state).items())


# ---------------------------------------------------------------------------------------------- the fallback stays


def test_a_move_no_stage_covers_is_led_by_its_shell_command():
    stages, text = lead_text.stages(), rendered()
    found = steps(text)
    alone = [m for m in guide.PATH if guide._covering(stages, m) is None]
    assert [m.primitive for m in alone] == ["plan.accept"]
    for move in alone:
        assert found[move.label].startswith(f"{move.label}: {move.shell}")
    assert found["Accept the plan"].startswith("Accept the plan: `aew plan accept <T> --revision <n> ")
    assert "aew verify classify <T> --as <CLASS>" in state_row(text, "VERIFICATION_FAILED")


def test_with_no_stages_every_step_is_the_shell_commands_alone():
    text = guide.render(DEFAULT_GATES, DEFAULT_CHECKS, ())
    assert "Shell fallback" not in text
    for move in guide.PATH:
        assert move.shell and move.shell in text, move.primitive


def test_the_shell_for_what_no_stage_reaches_is_named():
    """Step 1's list: a path without review or verification, rework, a classification, a parent's close and a
    non-mutating dispatch have no stage."""
    text = rendered()
    for command in ("aew work transition <T> --to <STATE>", "aew integrate prepare <T>",
                    "aew invoke create <T> --role implementer --launch", "aew verify classify <T>",
                    "aew work close <S>", "aew work dispatch <T> --launch"):
        assert command in text, command


# ---------------------------------------------------------------------------- no tool the profile does not have


def test_the_text_names_no_tool_the_normal_profile_lacks():
    names = {t.name for t in contract.exposed(NORMAL)}
    text = system_text()
    assert set(TOOL_NAME.findall(text)) <= names
    for t in contract.TOOLS.values():
        if t.name not in names:
            assert f"`{t.name}`" not in text, t.name


def test_a_recovery_or_designed_row_never_reaches_the_normal_text(monkeypatch):
    plant(monkeypatch, "zz_recovery", profiles=(RECOVERY,), expands_to=("plan.accept",))
    plant(monkeypatch, "zz_designed", status=contract.DESIGNED, expands_to=("plan.accept",))
    text = projection.lead_tools_text() + rendered()
    assert "zz_recovery" not in text and "zz_designed" not in text
    assert "zz_recovery" in {s.tool for s in lead_text.stages(RECOVERY)}


def test_a_lead_command_template_names_only_real_tools_and_takes_no_stage_step_from_the_shell():
    names = {t.name for t in contract.exposed(NORMAL)}
    # the command each covered move's shell form opens with, e.g. `aew work create`
    covered_shell = {" ".join(re.sub(r"^`+(sh\n)?", "", m.shell).split()[:3]) for m, _ in
                     covered(lead_text.stages()) if m.primitive != "work.transition"}
    assert "aew work create" in covered_shell
    for name, command in projection.LEAD_COMMANDS.items():
        template = command["template"]
        assert set(TOOL_NAME.findall(template)) <= names, name
        assert "!`" not in template, name
        for shell in covered_shell:
            assert shell not in template, (name, shell)
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


def test_the_guide_for_a_project_is_rendered_with_the_stages():
    seen: list[Any] = []

    class Engine:
        def lead_guide(self, stages: Any) -> str:
            seen.append(stages)
            return "text"

    assert lead_text.guide_for(Engine()) == "text"
    assert seen == [lead_text.stages()]


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
    text = T.next_steps("REVIEW_PENDING", "T-0007")
    assert text.index("`ticket_request_verification`") < text.index("`aew review ingest T-0007")
    for edge, tool in T.STAGE_AT.items():
        assert f"`{tool}`, or `aew " in T.next_steps(edge[0], "T-0007"), edge


@pytest.mark.parametrize("state", ["ASSIGNED", "REVIEW_PASSED", "REVIEW_FAILED", "VERIFIED"])
def test_a_refusal_in_a_state_no_stage_starts_from_names_only_the_command(state):
    text = T.next_steps(state, "T-0007")
    assert "`aew work transition T-0007" in text and not TOOL_NAME.search(text)


# ---------------------------------------------------------------------------------------- the hints a projection shows


def actions(unit_state: str, *, submitted: tuple[str, ...] = ()) -> list[str]:
    resume = Resume.__new__(Resume)
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


def test_a_validated_candidates_hint_leads_with_the_publish_stage(monkeypatch):
    monkeypatch.setattr(resume_ops.V, "obligation", lambda *a: {"mode": "verifier"})
    resume = Resume.__new__(Resume)
    resume.k = SimpleNamespace(policy=lambda name: {})
    resume._queue_wait = lambda state, wid: None  # type: ignore[method-assign]
    unit = {"state": "COMMIT_READY", "invocations": [], "integration": {"status": "validated"}}
    [hint] = resume._ticket_actions({"invocations": {}}, "T-0007", unit)
    assert hint.index("`integration_publish`") < hint.index("`aew integrate publish`")


def after_implementation(state: str, *, review: bool, verification: bool = True) -> str:
    harness = Harness.__new__(Harness)
    harness.gates = SimpleNamespace(gate_context=lambda state, wid: {}, review_gates=lambda gc: review,  # type: ignore[assignment]
                                    verification_gates=lambda gc: verification)
    return harness.after_implementation({"work": {"T-0007": {"state": state}}}, "T-0007")


def test_a_finished_implementation_names_the_review_stage_only_where_review_is_next():
    """Only RUNNING -> REVIEW_PENDING has a stage: `ticket_request_review` refuses a Ticket whose class needs none."""
    text = after_implementation("RUNNING", review=True)
    assert text.index("`ticket_request_review`") < text.index("--to REVIEW_PENDING")
    assert not TOOL_NAME.search(after_implementation("RUNNING", review=False))
    assigned = after_implementation("ASSIGNED", review=True)  # the stage starts at RUNNING: that step comes first
    assert assigned.index("--to RUNNING") < assigned.index("`ticket_request_review`")


def integration_state(*, report: str | None = None, verifier: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"work": "T-0007", "state": "VALIDATED" if report else "LEASED"}
    if report:
        entry["validated"] = {"report": report}
    invocations = {verifier: {"custodian": "INV-C", "scope": "integration", "status": "active"}} if verifier else {}
    lease = None if report else {"custodian": "INV-C", "entry": "Q-1"}
    return {"queue": {"entries": {"Q-1": entry}, "lease": lease}, "invocations": invocations}


def test_after_ticket_prepare_the_hint_never_dispatches_the_verifier_it_launched():
    """The scripted Lead followed `aew invoke create --scope integration` right after the stage had launched it, and was
    refused (LEASE_NOT_HELD). A running verifier says wait, a clean report says publish with it."""
    running = Resume._integration_verifier(integration_state(verifier="INV-9"), "T-0007")
    assert "INV-9" in running and "`harness_wait`" in running and "aew invoke create" not in running
    clean = Resume._integration_verifier(integration_state(report="EV-3"), "T-0007")
    assert "EV-3" in clean and "`integration_publish`" in clean and "`verification_evidence`" in clean
    assert "aew invoke create" not in clean


def test_a_candidate_prepared_from_the_shell_is_still_told_to_dispatch_its_verifier():
    """`aew integrate prepare` launches no verifier, so the lease is held and the dispatch is the next step."""
    hint = Resume._integration_verifier(integration_state(), "T-0007")
    assert "aew invoke create T-0007 --scope integration --launch" in hint


@pytest.mark.parametrize(("role", "scope", "tool"), [("reviewer", "ticket", "ticket_request_verification"),
                                                     ("verifier", "ticket", "ticket_prepare"),
                                                     ("verifier", "integration", "integration_publish")])
def test_a_finished_runs_message_leads_with_the_stage_that_accepts_its_report(role, scope, tool):
    state = {"work": {"T-0007": {"kind": "ticket", "mutating": True}}}
    message = Harness._after_run(Harness.__new__(Harness), state, {"work_unit": "T-0007", "role": role, "scope": scope},
                                 [{"id": "EV-3", "kind": "review" if role == "reviewer" else "verification"}])
    assert message.index(f"`{tool}`") < message.index("`aew ")


def test_a_parents_or_non_mutating_report_names_no_stage():
    for unit, role in (({"kind": "story"}, "reviewer"), ({"kind": "ticket", "mutating": False}, "investigator")):
        message = Harness._after_run(Harness.__new__(Harness), {"work": {"S-1": unit}},
                                     {"work_unit": "S-1", "role": role}, [{"id": "EV-3", "kind": "review"}])
        assert not TOOL_NAME.search(message), message
