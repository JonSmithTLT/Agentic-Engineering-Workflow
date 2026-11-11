"""How work flows in AEW, rendered for a Lead from the project's own policy (F16; M3 audit X4).

Model Leads learned AEW by trial and error: 51 of 887 ``aew`` commands refused in the M3 dogfood, 37 ``--help``
lookups, and no Lead ever chose Class 0 (the only example showed Class 1, and Class 0 read as unevidenced). This guide
states AEW's rules, not judgement: the Workflow Contract's risk classes (WC §7.4, §7.5), what each class requires in
*this* project (its gates policy), what every class still guarantees, the Ticket lifecycle and the way to take each
step (the engine's transition table, and the typed stages handed in). It is generated, so it says what the engine
enforces and cannot drift. When Class 0 applies is the Class 0 amendment's eligibility predicate, enforced at dispatch
since M4-A (Q10, decided 2026-10-03).

Which tool takes a step is never written here (E130; the operator, 2026-11-04: derive, don't restate). ``PATH`` is the
order of a mutating Ticket's moves, with the shell command for each; the caller hands in the stages
(:func:`aew.surface.lead_text.stages`, since the engine never imports the surface), and a step a stage covers renders
that tool first, with the shell command as its fallback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, NamedTuple

from aew.engine import transitions as T
from aew.harness.contract import CREATE_TICKET, EXPECT_REV, HELD_SEAT_IN_A_GUIDE

CLASS_TEXT = {  # WC §7.4 definitions and §7.4 examples, verbatim in substance
    "0": ("eligible mechanical work", "work for which the Class 0 eligibility predicate holds (below)",
          "a mechanical edit, or a behaviour fix whose acceptance is a deterministic check"),
    "1": ("routine engineering", "ownership and design are understood; bounded normal work",
          "several straightforward related Tickets in a Story"),
    "2": ("substantial brownfield", "meaningful codebase understanding or cross-component effects are required",
          "even a tiny diff on a public ABI or a security boundary"),
    "3": ("architectural/high-risk", "ownership, security, compatibility or design choices need explicit resolution",
          "a bounded objective with architectural ambiguity"),
    "4": ("frontier", "normal workflow cannot confidently resolve the design or root cause, or repeated attempts fail "
          "without new evidence", "a cross-layer feature or unresolved architecture"),
}

GATE_TEXT = {
    "accepted_plan": "an accepted plan",
    "local_checks": "the implementer's local checks pass on the change as submitted ({checks})",
    "self_review": "the implementer's report includes its self-review",
    "review_r1": "an independent reviewer (a fresh context that never saw the implementer's conversation) passes it",
    "verification_goal_backwards": "an independent verifier confirms every goal is observably met",
    "verification_contract": "an independent verifier confirms every contract clause",
    "execute_record": "the executor's record (discovery, research or plan proposal) is ingested",
    "children_complete": "every child is DONE or CANCELLED",
}

# Forward moves only: cancelling, escalating, replanning and interrupting are decisions, described separately.
LIFECYCLE = ("READY", "ASSIGNED", "RUNNING", "REVIEW_PENDING", "REVIEW_PASSED", "REVIEW_FAILED", "VERIFY_PENDING",
             "VERIFIED", "VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE", "COMMIT_READY")


class StageStep(NamedTuple):
    primitive: str
    qualifier: str | None = None  # what tells it from another step of its primitive: a target state, a role, a scope
    optional: bool = False  # planned only for some calls or states


class Stage(NamedTuple):
    """A typed tool that commits workflow steps, as the catalog states it."""

    tool: str
    description: str
    steps: tuple[StageStep, ...]
    starts: Mapping[str, int] = MappingProxyType({})  # a state past its first steps -> the step it starts at there

    def entries(self) -> tuple[StageStep, ...]:
        """The steps a call can start at: its first required step, and any optional step before it. Only these move a
        Ticket from where it stands: a later step's state is one the stage itself passes through, and a Ticket left
        there has no stage to call."""
        out: list[StageStep] = []
        for step in self.steps:
            out.append(step)
            if not step.optional:
                break
        return tuple(out)


# The word the path and the moves use for the one command most of them share (the section's opening spells it out): it
# goes on every model request, and the full command would be printed 20 times. Plain, not in backticks: in this text a
# backticked word is a tool (#331 review N2).
TRANSITION = "transition"
# A move the table requires a reason for, said once per move and spelled out once (#331 review F8: printed bare, each
# such move is refused).
WITH_REASON = "with a reason"


def _command(via: str, to: str = "<STATE>") -> str:
    """The engine's own command for an operation (``transitions._COMMANDS``), never a copy of it (#331 review F3)."""
    return f"`{T._COMMANDS[via].format(w='<T>', to=to)}`"


class Move(NamedTuple):
    """One move on a mutating Ticket's path: its shell command, which is its fallback when a stage covers it."""

    primitive: str
    qualifier: str | None
    shell: str
    label: str = ""  # what the move is, where no stage names it
    note: str = ""  # goes with the move, wherever a stage's coverage puts it
    post_verify: bool = False  # only where a post-integration verifier is required


# Filled in per project, since it reads the policy's cap (`_scope_rule`): `PATH` is a constant.
SCOPE_RULE = "<scope rule>"


def _scope_rule(cap: int) -> str:
    """What a Ticket's scope decides. Above a cap of 1 it also decides what runs beside the Ticket (E151's launch
    conflict check compares scopes), so a Lead that gives every Ticket the whole tree runs them one at a time."""
    if cap <= 1:
        return ("Its scope is fixed once the Ticket exists, so give every path the change may touch; one mutating "
                "Ticket works at a time here.")
    return (f"Its scope is fixed once the Ticket exists, and up to {cap} mutating Tickets work at once here when their "
            "scopes cannot name the same file: name every path this change needs, and no more.")


def _transition(to: str, note: str = "") -> Move:
    return Move("work.transition", to, f"{TRANSITION} to {to}", label=f"Move it to {to}", note=note)


# The path, in order.
PATH = (
    Move("work.create", None, CREATE_TICKET, label="Create the Ticket",
         note=f"{SCOPE_RULE} Creation warns about a scope glob that matches no file. A Class 0 Ticket's assertions and "
              "acceptance check take the shell command."),
    Move("plan.propose", None, f"`aew plan propose <T> --file - --assurance none {EXPECT_REV}` (the plan in a quoted "
                               "heredoc)", label="Propose the plan",
         note="Every plan declares its assurance: none, or the review and verification cards (in the shell "
              "`--assurance none`, or `--review default` and/or `--verify default`) when the plan relies on one beyond "
              "the class path. Accepting the plan makes them required gates; a review promised only in the plan's text "
              "binds nothing."),
    Move("plan.accept", None, _command("plan.accept"), label="Accept the plan",
         note="The Ticket becomes READY when its plan is accepted and its dependencies are satisfied."),
    Move("work.assign", None, _command("assign"), label="Start the implementer"),
    _transition("RUNNING", note="Follow a run as its launch's next step says: the turn's end where AEW wakes you, "
                                "or else `harness_wait`, which blocks until a run ends or needs you. Do not poll."),
    _transition("REVIEW_PENDING", note=(
        "Once the implementer's report and checks are in, this accepts the implementation. **Accept the implementation "
        f"by transition**, not by ingesting it: where the class requires no review, {TRANSITION} to VERIFY_PENDING if "
        "it requires only verification, or to COMMIT_READY if it requires neither. (`aew evidence ingest` is for "
        "non-mutating Tickets only.)")),
    Move("invoke.create.mutating", "reviewer", f"`aew invoke create <T> --role reviewer --launch {EXPECT_REV}`",
         label="Dispatch the reviewer"),
    Move("review.ingest", None, _command("review.ingest"), label="Accept the review",
         note="Name the report `status` lists, not a run. Where the class requires no verification, `ticket_prepare` "
              "takes it from here, with no report."),
    _transition("VERIFY_PENDING"),
    Move("invoke.create.mutating", "verifier", f"`aew invoke create <T> --role verifier --launch {EXPECT_REV}`",
         label="Dispatch the verifier"),
    Move("verify.ingest", None, _command("verify.ingest"), label="Accept the verification"),
    _transition("COMMIT_READY"),
    Move("integrate.prepare", None, f"`aew integrate prepare <T> {EXPECT_REV}`", label="Prepare the candidate",
         note="On a class path with no verification, `ticket_prepare` takes it from REVIEW_PASSED, with no report."),
    Move("invoke.create.mutating", "integration", f"`aew invoke create <T> --scope integration --launch {EXPECT_REV}`",
         label="Dispatch the integration verifier", post_verify=True),
    Move("verify.ingest.integration", None, _command("verify.ingest"), label="Accept the integration verification",
         post_verify=True, note="Name the integration verifier's report in `verification_evidence`, once its run has "
                                "ended."),
    Move("integrate.publish", None, _command("integrate.publish"), label="Publish",
         note="Name the candidate `status` shows in `prepared_candidate`. It is refused until the candidate is "
              "validated. It takes the Ticket to DONE."),
)

# The engine's name for an edge's operation -> the primitive it runs (`Rule.via` predates the primitives' ids).
_PRIMITIVE_OF = {"assign": "work.assign", "transition": "work.transition"}


def _covering(stages: Sequence[Stage], move: Move) -> Stage | None:
    """The first stage with this move among its steps (a dispatch two stages share is the earlier one's on the path:
    the later one repeats it only after a rebuild)."""
    for stage in stages:
        if any((s.primitive, s.qualifier) == (move.primitive, move.qualifier) for s in stage.steps):
            return stage
    return None


def _joined(shells: list[str]) -> str:
    """Shell commands in the order they run. A fenced one (`work.create`'s) keeps its own lines."""
    out = ""
    for shell in shells:
        if shell.startswith("```"):
            out += f"\n\n{shell}\n\n   "
        else:
            out += ("" if not out else "then " if out.endswith("   ") else ", then ") + shell
    return out


def _steps_text(stages: Sequence[Stage], post_verify: bool, cap: int) -> list[str]:
    """The path's numbered steps: consecutive moves one stage covers are one step, led by that tool with its shell
    commands as the fallback; consecutive moves no stage covers are a step of their own, led by the shell command."""
    groups: list[tuple[Stage | None, list[Move]]] = []
    for move in PATH:
        if move.post_verify and not post_verify:
            continue
        stage = _covering(stages, move)
        # A move no stage covers stands alone: each is its own decision, with its own label.
        if groups and stage is not None and groups[-1][0] == stage:
            groups[-1][1].append(move)
        else:
            groups.append((stage, [move]))
    out = []
    for n, (stage, moves) in enumerate(groups, start=1):
        notes = " ".join(m.note for m in moves if m.note).replace(SCOPE_RULE, _scope_rule(cap))
        shells = _joined([m.shell for m in moves])
        gap = "" if shells.startswith("\n") else " "  # a fenced command opens on its own line
        if stage is None:
            out.append(f"{n}. {moves[0].label}:{gap}{shells}." + (f" {notes}" if notes else ""))
        else:
            out.append(f"{n}. `{stage.tool}`: {stage.description}" + (f" {notes}" if notes else "")
                       + f" Shell fallback:{gap}{shells}.")
    return out


def _edge_stage(stages: Sequence[Stage], state: str, dst: str, via: str) -> Stage | None:
    """The stage a Ticket in ``state`` calls to take this edge: its entry step is the edge. A failed integration report
    is the one edge whose report is the integration verifier's."""
    primitive = _PRIMITIVE_OF.get(via, via)
    if via == "verify.ingest" and state == "COMMIT_READY":
        primitive = "verify.ingest.integration"
    qualifier = dst if via == "transition" else None
    for stage in stages:
        entries = (stage.steps[stage.starts[state] - 1],) if state in stage.starts else stage.entries()
        if any((s.primitive, s.qualifier) == (primitive, qualifier) for s in entries):
            return stage
    return None


def _gate(name: str, checks: str) -> str:
    if name in GATE_TEXT:
        return GATE_TEXT[name].format(checks=checks)
    if name.startswith("review_"):
        return f"an independent `{name[len('review_'):]}` review passes"
    if name.startswith("verification_"):
        return f"an independent verification (`{name[len('verification_'):]}`) passes"
    return f"gate `{name}`"


def _roles(gates: list[str], post_verification: bool) -> str:
    roles = ["an implementer"]
    if any(g.startswith("review") for g in gates):
        roles.append("a reviewer")
    if any(g.startswith("verification") for g in gates):
        roles.append("a verifier")
    if post_verification:
        roles.append("a post-integration verifier")
    return ", ".join(roles)


def _moves(state: str, stages: Sequence[Stage]) -> list[str]:
    """The moves out of ``state``, each by the way to take it, and those sharing a way as one entry: its tool,
    :data:`TRANSITION`, or its shell command."""
    ways: dict[str, list[str]] = {}
    for dst, via in T.allowed_from(state).items():
        if dst in T._EXCEPTIONAL and via != "verify.classify":  # a classification may lead to REPLAN_REQUIRED
            continue
        if via == "accept":
            continue  # non-mutating Tickets only; described in their section
        if via in T._COMMANDS:
            stage = _edge_stage(stages, state, dst, via)
            # An edge that requires a reason says so: the bare form is refused (#331 review F8).
            reason = f" {WITH_REASON}" if T.RULES[state, dst].reason_required else ""
            way = (f"`{stage.tool}`" if stage else f"{TRANSITION}{reason}" if via == "transition"
                   else f"`{T.command(state, dst)}`")
            ways.setdefault(way, []).append(dst)
    return [f"{', '.join(dsts)}: {way}" for way, dsts in ways.items()]


def _grouped(paths: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """Consecutive classes with the same gates, as one entry each ("Classes 1 to 4")."""
    groups: list[tuple[list[str], list[str]]] = []
    for c in ("0", "1", "2", "3", "4"):
        gates = list(paths.get(c) or [])
        if groups and groups[-1][1] == gates:
            groups[-1][0].append(c)
        else:
            groups.append(([c], gates))
    out = []
    for classes, gates in groups:
        label = (f"Class {classes[0]}" if len(classes) == 1 else f"Classes {classes[0]} and {classes[1]}"
                 if len(classes) == 2 else f"Classes {classes[0]} to {classes[-1]}")
        out.append((label, gates))
    return out


def staffing_text() -> str:
    """Which implementer card to staff, so a language card's skills load (the designer's ruling of 2026-11-04, §6: the
    Lead had only the cards' ``use_when``). Derived, never a list here: from the built-in implementer cards whose
    ``skills:`` AEW ships, each with its first ``use_when``, and the archetype's default card with the shipped skills
    its run is offered (``optional_skills``). Empty when no card has a shipped skill."""
    from aew import roles, skills

    shipped = skills.shipped()
    cards = sorted((c for c in roles.builtin_cards().values() if c.archetype == "implementer"), key=lambda c: c.id)
    loads = [(c, [s for s in c.meta.get("skills") or [] if s in shipped]) for c in cards]
    loads = [(c, names) for c, names in loads if names and c.meta.get("use_when")]
    if not loads:
        return ""
    picks = "; ".join(f"`{c.id}` when {c.meta['use_when'][0]}, so its run loads {', '.join(f'`{n}`' for n in names)}"
                      for c, names in loads)
    default = roles.builtin_cards().get(roles.default_card("implementer") or "")
    offered = [s for s in (default.meta.get("optional_skills") or []) if s in shipped] if default else []
    rest = (f" Otherwise the default, `{default.id}`, whose run may load "
            f"{' or '.join(f'`{n}`' for n in offered)} when its task matches." if default and offered else "")
    return ("Staff the implementer by the change's language, with the Ticket's `card` (`aew role list` shows each "
            f"card's `use_when` and skills): {picks}.{rest}")


def render(gates_policy: dict[str, Any], checks_policy: dict[str, Any], stages: Sequence[Stage]) -> str:
    from aew.engine.workspace_ops import mutating_cap  # local: its imports reach the harness, which reaches this text

    paths = gates_policy.get("risk_paths") or {}
    local = gates_policy.get("local_checks") or []
    checks = ", ".join(f"`{c}`" for c in local) or "none configured"
    post = gates_policy.get("post_integration") or {}
    post_verify, post_checks = bool(post.get("verification")), list(post.get("checks") or [])
    unconfigured = [k for k, v in (checks_policy.get("checks") or {}).items() if not v.get("configured")]
    lines = [
        "# How work gets done in AEW: the Lead's guide",
        "",
        "Generated by `aew guide` from this project's policy and AEW's own rules, so it says what the engine enforces. "
        "Read it before you create or classify work.",
        "",
        "## Who does what",
        "",
        "- **You, the Lead,** turn the objective into Tickets (and Stories and Epics when work has structure), write "
        "and accept plans, choose each Ticket's risk class, dispatch bounded roles, ingest their evidence and make "
        "every decision. You never implement, and you never submit evidence.",
        "- **Bounded roles** do the work, each in its own run with its own credential and context: an implementer "
        "changes code in its own workspace; a reviewer and a verifier judge it independently; an investigator, "
        "researcher or planner answers a question without changing code.",
        "- **Only your recorded actions move state.** A run ending is not progress: its evidence counts once you "
        "ingest it or take the transition that accepts it, and every gate is checked by the engine, not by you.",
        "",
        "## Choosing a risk class",
        "",
        "A risk class is about the change's surface and ambiguity, not its size (WC §7.4). A class sets the minimum "
        "ceremony; it is not a statement of how careful you are.",
        "",
    ]
    for c in ("0", "1", "2", "3", "4"):
        name, meaning, example = CLASS_TEXT[c]
        lines.append(f"- **Class {c}, {name}:** {meaning}. For example: {example}.")
    lines += [
        "",
        "Rules (WC §7.4): classify each unit by its own change surface, ambiguity and risk. A class may go up whenever "
        "evidence exposes more risk; lowering it needs a recorded decision with its reason. A parent's mandatory gates "
        "and minimum descendant class still apply to its children. Say in the plan why you chose the class.",
        "",
        "**Class 0 eligibility** (enforced when a mutating Ticket is dispatched at Class 0): a bounded scope (it "
        "matches tracked files, no glob starts with `**`, and it covers at most 50 tracked files and, in a tree of "
        "40 files or more, a quarter of the tree; the gates policy's `class0` can change these bounds); a goal "
        "(`--goal`) and an acceptance check "
        "that is a configured project check (`--acceptance-check`, mutating Tickets only; on any class, a declared "
        "acceptance check is a gate the Ticket must pass before COMMIT_READY, and it cannot be waived); no "
        "acceptance input inside the scope; no protected path in the scope; no review "
        "trigger (security, trust, persistence, compatibility) reached by the scope; no inherited elevated "
        "obligation (a parent's minimum class or non-waivable gate); a clean `aew plan lint` (a warning counts, "
        "such as an affected path outside the scope); and your three "
        "recorded assertions, made at creation with `--class0-assert transformation_clear --class0-assert "
        "inputs_complete --class0-assert no_consequential_boundary`. A Class 0 Ticket that is not eligible is refused "
        "with every reason (`explain` shows them), never reclassified: raise its class yourself with "
        f"`aew work reclassify <T> --class <0-4> --reason <reason> {EXPECT_REV}` (at least any inherited minimum; the "
        "inherited gates stay required), or make it eligible.",
        "",
        "## What each class requires in this project",
        "",
        "Before a mutating Ticket can reach COMMIT_READY, the engine requires:",
        "",
    ]
    for label, gates in _grouped(paths):
        required = "; ".join(_gate(g, checks) for g in gates) or "no gate beyond the ones every class has"
        lines.append(f"- **{label}:** {required}. Runs: {_roles(gates, post_verify)}.")
    every = [
        "every Ticket needs an accepted plan before it becomes READY (for a Class 0 Ticket a short plan is enough)",
        "guardrails apply to every class: a change outside the Ticket's scope or on a protected path blocks it",
        "gates and guardrails are checked on the exact snapshot being accepted: evidence for an earlier state of the "
        "work is STALE and satisfies nothing",
    ]
    if post_verify or post_checks:
        after = []
        if post_verify:
            after.append("a post-integration verifier checks the integrated result")
        if post_checks:
            after.append("checks " + ", ".join(f"`{c}`" for c in post_checks) + " pass on it")
        every.append("after the candidate is prepared, " + " and ".join(after) + ", before it is published")
    lines += ["", "For every class:", ""] + [f"- {e};" for e in every[:-1]] + [f"- {every[-1]}."]
    zero = list(paths.get("0") or [])
    guarantees = [_gate(g, checks) for g in zero]
    if post_verify:
        guarantees.append("the post-integration verification")
    lines += [
        "",
        "**Class 0 is still evidenced.** It skips the independent review and the Ticket verification, not evidence: "
        + ("; ".join(guarantees) + ", " if guarantees else "")
        + "the guardrails, and an accepted plan all still apply. Choose it when the change fits Class 0's definition, "
        "not to save effort, and do not avoid it to collect more evidence than the class requires.",
    ]
    if unconfigured:
        lines += ["", f"Checks not configured yet (their gates stay blocked): {', '.join(unconfigured)}."]
    lines += [
        "",
        "## Before the first Ticket",
        "",
        "- `aew init` lists documents that may govern the work (a README, contracts, schemas) as authority candidates, "
        "and gives them no authority. Classifying them is the operator's decision, made at their own terminal (`aew "
        "authority accept` and `aew authority reject` are refused in your session): `aew authority list` shows them. "
        "This tells AEW which documents govern the work and which only orient it, and it blocks nothing. On a session "
        "started with `aew opencode --acquire`, don't ask during the session: classifying needs a credential that path "
        "never shows, and a takeover would turn you read-only. The operator classifies after you exit, at their own "
        "terminal: they take the seat with `aew lead acquire`, or with `aew lead takeover` if your exit left it held, "
        f"and then classify. {HELD_SEAT_IN_A_GUIDE}.",
        "- Look at the project before you describe work in it. You cannot edit files, but you can read and search them "
        "with your read, glob and grep tools.",
        "",
        "## A mutating Ticket, step by step",
        "",
        "Where a step names a tool, use it: it does the whole step, and returns the revision for your next "
        "`expect_rev`. Don't run part of a step from the shell first: the tool starts at the step's first state and "
        "refuses a Ticket already past it. If a tool stops partway, what it committed stands: read `status`, then take "
        "the Ticket's move below. A report that fails stops its tool once it is recorded: that is how a failed report "
        "is recorded. "
        "Use the shell command where a step names no tool, or where a tool refuses. Below, "
        f"\"{TRANSITION}\" means {_command('transition')}, and \"{WITH_REASON}\" adds `--reason <reason>`.",
        "",
        *([staffing, ""] if (staffing := staffing_text()) else []),
        *_steps_text(stages, post_verify, mutating_cap(gates_policy)),
        "",
        "Each state and the moves out of it (the engine refuses any other):",
        "",
    ]
    for state in LIFECYCLE:
        moves = _moves(state, stages)
        if moves:
            lines.append(f"- **{state}** → " + "; ".join(moves))
    classify = ", ".join(f"`{k}` → {v}" for k, v in T.VERIFICATION_CLASSIFICATIONS.items())
    lines += [
        "",
        "When things go wrong:",
        "",
        "- **`resolve`** settles only what `resume` or a decision lists; a stage that already stopped is not one.",
        "- **A failed review** (REVIEW_FAILED): move it back to RUNNING and dispatch a fresh implementer, "
        f"`aew invoke create <T> --role implementer --launch {EXPECT_REV}`. The open findings reach it through its "
        "pack.",
        f"- **A failed verification**: classify it, {_command('verify.classify')}: {classify}.",
        "- **Replanning, escalating or cancelling** are decisions: `aew work transition <T> --to "
        f"REPLAN_REQUIRED|ESCALATED|CANCELLED --reason <reason> {EXPECT_REV}`.",
        "- **A lost harness run** is not an interruption: relaunch it with `aew harness launch <invocation from aew "
        f"harness status> {EXPECT_REV}` (its credential rotates) or cancel it.",
        "",
        "## Non-mutating Tickets: investigation, research, planning",
        "",
        "To find something out before changing code, create a non-mutating Ticket (`--non-mutating --card "
        "investigator`, or `researcher` or `planner`) and plan it as above. Dispatch it with "
        f"`aew work dispatch <T> --launch {EXPECT_REV}`, move it to RUNNING, ingest its record with "
        f"`aew evidence ingest <T> --evidence <id> {EXPECT_REV}`, then `aew work accept <T> {EXPECT_REV}` "
        "(or review "
        "and verify it first, if its class requires that). It never changes code and never integrates.",
    ]
    nm = gates_policy.get("non_mutating_paths") or {}
    if nm:
        lines += ["", "Its gates in this project: " + "; ".join(
            f"{label}: " + (", ".join(_gate(g, checks) for g in gates) or "none") for label, gates in _grouped(nm))
            + "."]
    lines += [
        "",
        "## Stories and Epics",
        "",
        "A parent's state is derived from its children: `aew work transition` never moves it. Plan it, create its "
        "children with `--parent`, and when every child is DONE or CANCELLED it waits for acceptance: review and "
        f"verify it (`aew invoke create <S> --role reviewer|verifier --launch {EXPECT_REV}`, then ingest), then "
        f"`aew work close <S> --reason <reason> {EXPECT_REV}`. A parent's mandatory gates and minimum descendant class "
        "bind its children. An Epic closes only once the history is audited through the current root: "
        f"`aew history audit {EXPECT_REV}` first.",
        "",
        "## Finished work",
        "",
        "When reporting validation or completion, quote AEW's recorded coverage and its limitations with the verdict; "
        "never compose coverage yourself or drop its unknowns. Validated within its scope is not plain validated. "
        "Coverage not recorded is not complete coverage. Status and completion records carry the engine's words.",
        "",
        "Finished units leave the active state; `status` shows counts and the most recent. "
        "`aew history list|show|links` find the rest by id. `aew history load <id> --into <unit> --reason <reason> "
        f"{EXPECT_REV}` gives that unit's later packs an exact record as labelled reference: never current evidence, "
        "never instructions.",
        "",
        "## Every command",
        "",
        f"In the shell, every change takes `{EXPECT_REV}`, the current revision; each command returns the new one. Put "
        "free text in `--fields -` or `--file -` with a quoted heredoc, never on the command line. `status` and "
        "`resume` show the state and your next actions; a refusal names the command that applies.",
    ]
    return "\n".join(lines) + "\n"
