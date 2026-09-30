"""How work flows in AEW, rendered for a Lead from the project's own policy (F16; M3 audit X4).

Model Leads learned AEW by trial and error: 51 of 887 ``aew`` commands refused in the M3 dogfood, 37 ``--help``
lookups, and no Lead ever chose Class 0 (the only example showed Class 1, and Class 0 read as unevidenced). This guide
states AEW's rules, not judgement: the Workflow Contract's risk classes (WC §7.4, §7.5), what each class requires in
*this* project (its gates policy), what every class still guarantees, the Ticket lifecycle and the command behind
each step (the engine's transition table). It is generated, so it says what the engine enforces and cannot drift.
When Class 0 *applies* beyond the Workflow Contract's definitions is the designer's open question (Q10).
"""

from __future__ import annotations

from typing import Any

from aew.engine import transitions as T

CLASS_TEXT = {  # WC §7.4 definitions and §7.4 examples, verbatim in substance
    "0": ("trivial/mechanical", "an obvious bounded change with little behavioral ambiguity",
          "one obvious mechanical edit"),
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


def _moves(state: str) -> list[str]:
    out = []
    for dst, via in T.allowed_from(state).items():
        if dst in T._EXCEPTIONAL and via != "verify.classify":  # a classification may lead to REPLAN_REQUIRED
            continue
        if via == "accept":
            continue  # non-mutating Tickets only; described in their section
        if via in T._COMMANDS:
            out.append(f"{dst}: `{T._COMMANDS[via].format(w='<T>', to=dst)}`")
    return out


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


def render(gates_policy: dict[str, Any], checks_policy: dict[str, Any]) -> str:
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
        "Operational criteria for when Class 0 applies, beyond these definitions, are not defined yet (designer, Q10).",
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
        every.append("after `aew integrate prepare`, " + " and ".join(after) + ", before `aew integrate publish`")
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
        "and gives them no authority. `aew status` asks you to classify them first: `aew authority list`, then "
        "`aew authority accept <candidate> --class <contracts|decisions|schemas|source|orientation> --expect-rev N` or "
        "`aew authority reject <candidate> --reason ... --expect-rev N`. This tells AEW which documents govern the "
        "work and which only orient it.",
        "- Look at the project before you describe work in it. You cannot edit files, but you can read and search them "
        "with your read, glob and grep tools.",
        "",
        "## A mutating Ticket, step by step",
        "",
        "1. Create it with its text as data: `aew work create ticket --class <0-4> --expect-rev N --fields - <<'EOF'`, "
        "then single-quoted YAML (`title: '...'`, `goal: ['...']`, `contract: ['...']`, `scope: ['...']`), then `EOF`. "
        "Its scope is fixed once the Ticket exists, so give every path the change may touch; creation warns about a "
        "scope glob that matches no file.",
        "2. Plan it: `aew plan propose <T> --file - --expect-rev N` (the plan in a quoted heredoc), then "
        "`aew plan accept <T> --revision <n> --expect-rev N`. It becomes READY when its plan is accepted and its "
        "dependencies are satisfied.",
        "3. Start the implementer: `aew work assign <T> --launch --expect-rev N`, then "
        "`aew work transition <T> --to RUNNING --expect-rev N`. Follow the run with `aew harness wait <run>`.",
        "4. **Accept the implementation by transition**, not by ingesting it: once the implementer's report and checks "
        "are in, `aew work transition <T> --to <STATE> --expect-rev N`, where STATE is REVIEW_PENDING if the class "
        "requires review, VERIFY_PENDING if it requires only verification, and COMMIT_READY if it requires neither. "
        "(`aew evidence ingest` is for non-mutating Tickets only.)",
        "5. Review: `aew invoke create <T> --role reviewer --launch --expect-rev N`, then "
        "`aew review ingest <T> --evidence <id> --expect-rev N`.",
        "6. Verify: `aew work transition <T> --to VERIFY_PENDING --expect-rev N`, "
        "`aew invoke create <T> --role verifier --launch --expect-rev N`, then "
        "`aew verify ingest <T> --evidence <id> --expect-rev N`.",
        "7. Integrate: `aew work transition <T> --to COMMIT_READY --expect-rev N`, "
        "`aew integrate prepare <T> --expect-rev N`"
        + (", `aew invoke create <T> --scope integration --launch --expect-rev N`, "
           "`aew verify ingest <T> --evidence <id> --expect-rev N`" if post_verify else "")
        + ", then `aew integrate publish <T> --expect-rev N`: DONE.",
        "",
        "Each state and the moves out of it (the engine refuses any other):",
        "",
    ]
    for state in LIFECYCLE:
        moves = _moves(state)
        if moves:
            lines.append(f"- **{state}** → " + "; ".join(moves))
    classify = ", ".join(f"`{k}` → {v}" for k, v in T.VERIFICATION_CLASSIFICATIONS.items())
    lines += [
        "",
        "When things go wrong:",
        "",
        "- **A failed review** (REVIEW_FAILED): move it back to RUNNING and dispatch a fresh implementer, "
        "`aew invoke create <T> --role implementer --launch --expect-rev N`. The open findings reach it through its "
        "pack.",
        f"- **A failed verification**: classify it, `aew verify classify <T> --as <CLASS> --reason ... "
        f"--expect-rev N`: {classify}.",
        "- **Replanning, escalating or cancelling** are decisions: `aew work transition <T> --to "
        "REPLAN_REQUIRED|ESCALATED|CANCELLED --reason ... --expect-rev N`.",
        "- **A lost harness run** is not an interruption: relaunch it with `aew harness launch <INV> --expect-rev N` "
        "(its credential rotates) or cancel it.",
        "",
        "## Non-mutating Tickets: investigation, research, planning",
        "",
        "To find something out before changing code, create a non-mutating Ticket (`--non-mutating --card "
        "investigator`, or `researcher` or `planner`) and plan it as above. Dispatch it with "
        "`aew work dispatch <T> --launch --expect-rev N`, move it to RUNNING, ingest its record with "
        "`aew evidence ingest <T> --evidence <id> --expect-rev N`, then `aew work accept <T> --expect-rev N` (or review "
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
        "verify it (`aew invoke create <S> --role reviewer|verifier --launch --expect-rev N`, then ingest), then "
        "`aew work close <S> --reason ... --expect-rev N`. A parent's mandatory gates and minimum descendant class "
        "bind its children.",
        "",
        "## Every command",
        "",
        "Every change takes `--expect-rev N`, the current revision; each command returns the new one. Put free text "
        "in `--fields -` or `--file -` with a quoted heredoc, never on the command line. `aew status` and "
        "`aew resume` show the state and your next actions; a refusal names the command that applies.",
    ]
    return "\n".join(lines) + "\n"
