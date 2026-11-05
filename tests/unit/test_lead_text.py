"""The Lead's text names its typed tools, derived from the catalog, and nobody keeps it up to date by hand (E130).

The operator, 2026-11-04: "are we going to have to manually keep the system text up to date?" Eight real sessions showed
63% of the screen in shell tails, while a typed call is one row, and everything the Lead read pointed it at the shell.
These tests are the answer: the system text's tools are `contract.TOOLS`' for the normal profile, a step a stage covers
is led by that stage, and the shell stays the named way where no stage covers a step. A planted catalog row moves the
text with no other edit. What is still hand-written is the prose, listed in the pull request.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from aew.engine import gates as G
from aew.engine import guide, resume_ops
from aew.engine import transitions as T
from aew.engine.harness_ops import Harness
from aew.engine.resume_ops import Resume
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import availability as SA
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
    "metadata": "a filesystem term", "chmod": "an operating-system command", "chown": "an operating-system command",
    "diff": "a git command", "log": "a git command", "show": "a git command",
    "read": "OpenCode's own tool, not AEW's",
}
# Where the engine's and the surface's words to a Lead are written: every string in these, docstrings aside.
WORDS_IN = ("src/aew/engine", "src/aew/surface", "src/aew/harness/opencode")
ROOT = Path(__file__).resolve().parents[2]
FULL = T.Fit(review=True, verification=True, last_review=True, last_verification=True)


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


def way_of(text: str, state: str, dst: str) -> str:
    """How the guide's table says to take ``state -> dst``."""
    for group in state_row(text, state).split(" → ", 1)[1].split("; "):
        dsts, way = group.split(": ", 1)
        if dst in dsts.split(", "):
            return way
    raise AssertionError((state, dst))


def covered(stages: tuple[guide.Stage, ...]) -> list[tuple[guide.Move, guide.Stage]]:
    return [(m, s) for m in guide.PATH if (s := guide._covering(stages, m)) is not None]


def stage_named(text: str) -> list[str]:
    """The catalog's tools ``text`` names, any profile."""
    return [w for w in WORD.findall(text) if w in contract.TOOLS or w.startswith("zz_")]


def known_words() -> set[str]:
    normal = contract.exposed(NORMAL)
    return ({t.name for t in normal} | {a for t in normal for a in t.input_schema.get("properties") or {}}
            | set(NOT_TOOLS) | set(DEFAULT_CHECKS["checks"]) | set(G.VERIFICATION_GATES))


def lead_texts() -> dict[str, str]:
    """What a Lead reads as written: the system text with the guide, and each command's template."""
    return {"system": system_text(), **{f"/{k}": v["template"] for k, v in projection.LEAD_COMMANDS.items()}}


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


def test_the_system_text_teaches_no_step_a_stage_covers_from_the_shell():
    """#331 review F4: `LEAD_SYSTEM` printed `aew work create` as the way a title gets in, on every request and again in
    the guide's first step. It points at the guide instead; the guide keeps the command as the step's fallback."""
    for move, _stage in covered(lead_text.stages()):
        command = re.sub(r"^`+(sh\n)?", "", move.shell).split(" <", 1)[0]
        if command.startswith("aew "):
            assert command not in projection.LEAD_SYSTEM, command


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
        assert not stage_named(row) and guide.TRANSITION in row, row


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
                                  "ticket_prepare", "integration_publish"])
def test_a_tool_renamed_in_the_catalog_with_its_old_name_left_fails_the_guard(monkeypatch, name):
    """The rename the review drove: the catalog moves, the prose and hints keep the old name."""
    row = contract.TOOLS[name]
    renamed = {k: (t._replace(name=f"{k}_renamed") if k == name else t) for k, t in contract.TOOLS.items()}
    monkeypatch.setattr(contract, "TOOLS", renamed)
    assert row.name not in known_words()
    left = [w for text in lead_texts().values() for w in WORD.findall(text)] + list(engine_words())
    assert name in left


def test_an_argument_renamed_in_the_catalog_with_its_old_name_left_fails_the_guard(monkeypatch):
    def renamed(row: contract.Tool) -> contract.Tool:
        props = {("verification_report" if k == "verification_evidence" else k): v
                 for k, v in (row.input_schema.get("properties") or {}).items()}
        return row._replace(input_schema={**row.input_schema, "properties": props})

    monkeypatch.setattr(contract, "TOOLS", {k: renamed(t) for k, t in contract.TOOLS.items()})
    assert "verification_evidence" not in known_words()
    assert "verification_evidence" in WORD.findall(system_text())


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
        assert set(stage_named(template)) <= names, name
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
    text = T.next_steps("REVIEW_PENDING", "T-0007", FULL)
    assert text.index("`ticket_request_verification`") < text.index("`aew review ingest T-0007")
    for edge, tool in T.STAGE_AT.items():
        assert f"`{tool}`, or `aew " in T.next_steps(edge[0], "T-0007", FULL), edge


@pytest.mark.parametrize("state", ["ASSIGNED", "REVIEW_PASSED", "REVIEW_FAILED", "VERIFIED"])
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


@pytest.mark.parametrize(("frm", "dst"), [(frm, "RUNNING") for frm in ("REVIEW_PENDING", "REVIEW_PASSED",
                                                                       "VERIFY_PENDING", "VERIFIED",
                                                                       "VERIFICATION_INCONCLUSIVE", "COMMIT_READY")]
                         + [("VERIFICATION_INCONCLUSIVE", "VERIFY_PENDING")])
def test_a_move_that_requires_a_reason_is_printed_with_one(frm, dst):
    """#331 review F8: each of these is refused without `--reason`, and the guide and the refusals printed it bare."""
    assert T.RULES[frm, dst].reason_required
    assert "--reason <reason>" in T.command(frm, dst, "T-0007")
    assert f"`aew work transition T-0007 --to {dst} --reason <reason> " in T.next_steps(frm, "T-0007")
    text = rendered()
    assert way_of(text, frm, dst) == f"{guide.TRANSITION} {guide.WITH_REASON}"
    assert f'"{guide.WITH_REASON}" adds `--reason <reason>`' in text


def test_a_moves_shell_is_the_engines_own_command():
    """#331 review F3: a step's shell fallback is the transition table's command, never a copy that can drift."""
    via_of = {"plan.accept": "plan.accept", "work.assign": "assign", "review.ingest": "review.ingest",
              "verify.ingest": "verify.ingest", "verify.ingest.integration": "verify.ingest",
              "integrate.publish": "integrate.publish"}
    for move in guide.PATH:
        if move.primitive in via_of:
            assert move.shell == f"`{T._COMMANDS[via_of[move.primitive]].format(w='<T>', to='<STATE>')}`", move


# ---------------------------------------------------------------------------------------- the hints a projection shows


def resume_with(fit: T.Fit | None = FULL) -> Resume:
    resume = Resume.__new__(Resume)
    resume.gates = SimpleNamespace(stage_fit=lambda state, wid: fit)  # type: ignore[assignment]
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
    assert "C-1 as `prepared_candidate`" in hint


def after_implementation(state: str, *, review: bool, verification: bool = True) -> str:
    harness = Harness.__new__(Harness)
    harness.gates = SimpleNamespace(  # type: ignore[assignment]
        gate_context=lambda state, wid: {}, review_gates=lambda gc: review, verification_gates=lambda gc: verification,
        stage_fit=lambda state, wid: FULL._replace(review=review, verification=verification))
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
    harness.gates = SimpleNamespace(stage_fit=lambda state, wid: fit)  # type: ignore[assignment]
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
