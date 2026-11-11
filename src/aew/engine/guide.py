"""The Lead guide and its on-demand sections, rendered from the project policy (F16, E130, E231)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Any, NamedTuple

from aew.harness.contract import EXPECT_REV, HELD_SEAT_IN_A_GUIDE

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


def _scope_rule(cap: int) -> str:
    """What a Ticket's scope decides. Above a cap of 1 it also decides what runs beside the Ticket (E151's launch
    conflict check compares scopes), so a Lead that gives every Ticket the whole tree runs them one at a time."""
    if cap <= 1:
        return ("Its scope is fixed once the Ticket exists, so give every path the change may touch; one mutating "
                "Ticket works at a time here.")
    return (f"Its scope is fixed once the Ticket exists, and up to {cap} mutating Tickets work at once here when their "
            "scopes cannot name the same file: name every path this change needs, and no more.")


# The engine's name for an edge's operation -> the primitive it runs (`Rule.via` predates the primitives' ids).
_PRIMITIVE_OF = {"assign": "work.assign", "transition": "work.transition"}


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


def render(gates_policy: dict[str, Any], checks_policy: dict[str, Any]) -> str:
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
        "## A mutating Ticket's life",
        "",
        "Create a scoped Ticket and accept its plan, then dispatch the implementer. Accept the implementation by "
        "transition once its report and checks are in. When the gates require review or verification, dispatch the "
        "independent roles and accept their reports. Prepare the integration candidate, pass the required checks "
        "and verification, then publish it. Follow each result's next step. "
        "Use `status` or `resume` to recover your place. "
        + _scope_rule(mutating_cap(gates_policy)),
        "",
        "## Read when needed",
        "",
        "| Read | When |",
        "| --- | --- |",
        *(f"| `aew lead guide {name}` | {when} |" for name, (when, _) in SECTIONS.items()),
    ]
    return "\n".join(lines) + "\n"


def _first_ticket(_gates_policy: dict[str, Any]) -> str:
    return "\n".join((
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
        staffing_text(),
    )).rstrip() + "\n"


def _non_mutating(gates_policy: dict[str, Any]) -> str:
    lines = [
        "## Non-mutating Tickets: investigation, research, planning",
        "",
        "To find something out before changing code, create a non-mutating Ticket (`--non-mutating --card "
        "investigator`, or `researcher` or `planner`) and accept its plan. Dispatch it with "
        f"`aew work dispatch <T> --launch {EXPECT_REV}`, move it to RUNNING, ingest its record with "
        f"`aew evidence ingest <T> --evidence <id> {EXPECT_REV}`, then `aew work accept <T> {EXPECT_REV}` "
        "(or review "
        "and verify it first, if its class requires that). It never changes code and never integrates.",
    ]
    nm = gates_policy.get("non_mutating_paths") or {}
    if nm:
        checks = ", ".join(f"`{c}`" for c in gates_policy.get("local_checks") or []) or "none configured"
        lines += ["", "Its gates in this project: " + "; ".join(
            f"{label}: " + (", ".join(_gate(g, checks) for g in gates) or "none") for label, gates in _grouped(nm))
            + "."]
    return "\n".join(lines) + "\n"


def _stories_and_epics(_gates_policy: dict[str, Any]) -> str:
    return "\n".join((
        "## Stories and Epics",
        "",
        "A parent's state is derived from its children: `aew work transition` never moves it. Plan it, create its "
        "children with `--parent`, and when every child is DONE or CANCELLED it waits for acceptance: review and "
        f"verify it (`aew invoke create <S> --role reviewer|verifier --launch {EXPECT_REV}`, then ingest), then "
        f"`aew work close <S> --reason <reason> {EXPECT_REV}`. A parent's mandatory gates and minimum descendant class "
        "bind its children. An Epic closes only once the history is audited through the current root: "
        f"`aew history audit {EXPECT_REV}` first.",
    )) + "\n"


def _finished_work(_gates_policy: dict[str, Any]) -> str:
    return "\n".join((
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
    )) + "\n"


SECTIONS: dict[str, tuple[str, Callable[[dict[str, Any]], str]]] = {
    "first-ticket": ("Before creating the first Ticket in a project.", _first_ticket),
    "stories-and-epics": ("When grouping work or closing a parent.", _stories_and_epics),
    "finished-work": ("When reporting, finding or recalling completed work.", _finished_work),
    "non-mutating": ("When planning an investigation, research or a plan-only Ticket.", _non_mutating),
}


def render_section(section: str, gates_policy: dict[str, Any]) -> str:
    return SECTIONS[section][1](gates_policy)
