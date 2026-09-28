"""What AEW projects into OpenCode V2: one run's agent, or the Lead's TUI (ADR-0009).

Everything here is derived from pinned AEW state (the launch contract) and is deterministic, so the
exact projection can be printed (`aew harness config opencode`) and golden-tested. Nothing here is
authority: OpenCode permissions are defense in depth, and the engine enforces every AEW operation
(ADR-0005, ADR-0006). Harness permissions are never a secret boundary: credential custody is (§2.3).

Invocation runs:

* one primary agent (``aew``) whose system text states the AEW rules; the model is pinned on the
  session, on the agent, and on OpenCode's auxiliary agents (title, summary, compaction);
* every permission rule is ``allow`` or ``deny`` (an unanswered ``ask`` blocks a V2 session forever);
  anything not named is denied; ``subagent``, ``question`` and ``external_directory`` are always denied,
  except the run's own private OpenCode output directories (V2 saves long tool output there and points the
  model at it); ``.env`` files are not readable (V2's own default asks; ``.env.example`` stays readable);
  ``edit`` only for implementers; web access only for cards that request documentation lookup;
  ``skill`` only for skills the harness actually provides for the card (none in M3: they are reported
  as unavailable, WC §16.10);
* no project configuration, no compatibility plugin (``~/.claude``/``~/.agents`` skills), no LSP or
  formatter downloads, no snapshots, no sharing, no updates.

The Lead's TUI (``aew opencode``) gets the ``aew-lead`` agent and the ``/aew-*`` commands. The operator
is present there, so unlisted actions ``ask``; editing and subagents are denied. Command templates run
only fixed read commands as inline shell (V2 runs those outside the permission flow).
"""

from __future__ import annotations

from typing import Any

from aew.harness.contract import LaunchContract

AGENT = "aew"
LEAD_AGENT = "aew-lead"
AUXILIARY_AGENTS = ("title", "summary", "compaction")
COMPATIBILITY_PLUGIN = "-opencode.config.compatibility"
MUTATING_ROLES = frozenset({"implementer"})
WEB_CAPABILITIES = frozenset({"documentation_lookup"})
ALWAYS_DENIED = ("subagent", "question", "external_directory")


def rule(action: str, effect: str, resource: str = "*") -> dict[str, str]:
    return {"action": action, "resource": resource, "effect": effect}


# ---------------------------------------------------------------------------------------------- invocation runs


def model_ref(profile: dict[str, Any]) -> dict[str, str]:
    """The session's ``model`` (``Model.Ref``): provider, model and the effort as OpenCode's variant."""
    ref = {"providerID": str(profile["provider"]), "id": str(profile["model"])}
    if profile.get("effort"):
        ref["variant"] = str(profile["effort"])
    return ref


def config_model(profile: dict[str, Any]) -> dict[str, str]:
    """The same pin in the config schema's spelling (``Config.AgentEncoded.model``)."""
    ref = {"providerID": str(profile["provider"]), "model": str(profile["model"])}
    if profile.get("effort"):
        ref["variant"] = str(profile["effort"])
    return ref


def skills(contract: LaunchContract, provided: frozenset[str] = frozenset()) -> dict[str, list[str]]:
    requested = sorted(set(contract.extra.get("card_skills") or []))
    return {"requested": requested, "exposed": [s for s in requested if s in provided],
            "unavailable": [s for s in requested if s not in provided]}


def permissions(contract: LaunchContract, exposed_skills: list[str],
                private_dirs: tuple[str, ...] = ()) -> list[dict[str, str]]:
    """The complete ordered rule set (last match wins). Sent on session create, where it is applied last.

    ``private_dirs``: path patterns of the run's own OpenCode output (tool output, shell output, temp files),
    the only external directories the agent may read."""
    capabilities = set(contract.extra.get("card_capabilities") or [])
    web = "allow" if capabilities & WEB_CAPABILITIES else "deny"
    rules = [rule("*", "deny")]  # anything not named below does not exist for the agent
    rules += [rule(action, "allow") for action in ("read", "glob", "grep", "shell")]
    rules += [rule("read", "deny", "*.env"), rule("read", "deny", "*.env.*"), rule("read", "allow", "*.env.example")]
    rules.append(rule("edit", "allow" if contract.role in MUTATING_ROLES else "deny"))
    rules += [rule("webfetch", web), rule("websearch", web), rule("skill", "deny")]
    rules += [rule("skill", "allow", name) for name in exposed_skills]
    rules += [rule(action, "deny") for action in ALWAYS_DENIED]  # after the rest, so nothing above reopens them
    rules += [rule("external_directory", "allow", pattern) for pattern in private_dirs]
    return rules


def private_output_dirs(state_dir: str, sep: str, *, scratch: str = "") -> tuple[str, ...]:
    """Where OpenCode V2 keeps a run's tool output, shell output and temporary files, given AEW's private XDG and
    TEMP layout (the same patterns V2's own defaults allow), and the run's scratch directory (the contract's)."""
    data = sep.join([state_dir, "xdg-data", "opencode"])
    dirs = (sep.join([data, "tool-output", "*"]), sep.join([data, "shell", "*", "*"]),
            sep.join([state_dir, "tmp", "opencode", "*"]))
    return dirs + ((sep.join([scratch, "*"]),) if scratch else ())


def system_text(contract: LaunchContract, unavailable_skills: list[str]) -> str:
    card = (contract.card or {}).get("id") or contract.role
    edit = ("You may edit files in the workspace." if contract.role in MUTATING_ROLES
            else "You must not modify any file: your role is read-only.")
    lines = [
        f"You are an AEW bounded {contract.role} (role card {card}) for work unit {contract.work_unit}: "
        f"invocation {contract.invocation}, run {contract.run}.",
        "The first message is your AEW launch contract. It is authoritative; this OpenCode session is disposable "
        "and nothing in it is AEW state.",
        "- Act on AEW only with the `aew` command, which is already connected to AEW for this run. No credential "
        "exists here and none is needed.",
        "- Only submitted AEW evidence counts. Ending your turn without `aew submit` records nothing.",
        f"- Work only in {contract.workspace}. {edit}",
        (f"- Write reports and any other file you need outside the workspace only in your private scratch directory "
         f"{contract.scratch} (`AEW_SCRATCH`), never anywhere else; or pipe a report: "
         "`aew submit --kind <kind> --file -`." if contract.scratch else
         "- Write report files outside the workspace, or pipe them: `aew submit --kind <kind> --file -`."),
        "- Do not start processes that outlive your commands. You cannot delegate: there are no subagents.",
        "- Tools that are unavailable here are unavailable by design. Do not work around them.",
    ]
    if unavailable_skills:
        lines.append("- Skills your role card requests that this harness does not provide: "
                     f"{', '.join(unavailable_skills)}. Proceed without them and say so in your report.")
    return "\n".join(lines)


def invocation_config(contract: LaunchContract, *, provided_skills: frozenset[str] = frozenset(),
                      private_dirs: tuple[str, ...] = ()) -> dict[str, Any]:
    """``OPENCODE_CONFIG_CONTENT`` for one run's private server."""
    skill = skills(contract, provided_skills)
    rules = permissions(contract, skill["exposed"], private_dirs)
    profile = contract.execution_profile
    agent: dict[str, Any] = {"mode": "primary", "description": f"AEW {contract.role} for {contract.invocation}",
                             "model": config_model(profile), "system": system_text(contract, skill["unavailable"]),
                             "permissions": rules}
    if profile.get("max_steps"):
        agent["steps"] = int(profile["max_steps"])
    agents: dict[str, Any] = {AGENT: agent}
    for name in AUXILIARY_AGENTS:  # any auxiliary model call uses the pinned model too
        agents[name] = {"model": config_model(profile)}
    return {"snapshots": False, "update": "disable", "share": "disabled", "plugins": [COMPATIBILITY_PLUGIN],
            "lsp": False, "formatter": False, "default_agent": AGENT, "permissions": rules, "agents": agents}


def session_body(contract: LaunchContract, directory: str, rules: list[dict[str, str]]) -> dict[str, Any]:
    """``POST /api/session``. The metadata is correlation only: nothing reads it as authority."""
    return {"title": f"AEW {contract.run} ({contract.role}, {contract.work_unit})", "agent": AGENT,
            "model": model_ref(contract.execution_profile), "location": {"directory": directory},
            "permissions": rules, "metadata": {"aew_invocation": contract.invocation, "aew_run": contract.run,
                                               "aew_work_unit": contract.work_unit}}


# ---------------------------------------------------------------------------------------------- the Lead's TUI

LEAD_RULES = [
    rule("*", "ask"),
    *(rule(action, "allow") for action in ("read", "glob", "grep")),
    rule("shell", "ask"),
    *(rule("shell", "allow", pattern) for pattern in ("aew *", "git status*", "git diff*", "git log*", "git show*")),
    rule("edit", "deny"),
    rule("subagent", "deny"),
    rule("question", "allow"),
]

LEAD_SYSTEM = "\n".join([
    "You are the AEW Lead for this repository. AEW, not this conversation, holds the workflow: objectives, work "
    "units, plans, dispatches, evidence and decisions live in `.aew/` and change only through the `aew` command. "
    "This session is disposable. After any restart, rebuild your context with `aew resume` (/aew-resume), never "
    "from an earlier conversation.",
    "- You never hold or see the Lead credential. This session's Lead broker carries out Lead-authenticated `aew` "
    "commands for you. Mutations still need `--expect-rev <revision>` (from `aew status` or the previous command).",
    "- Delegate implementation, review, verification, investigation and research to bounded invocations. Dispatch "
    "with `--launch` (for example `aew work assign T-0001 --launch --expect-rev N`): the run's supervisor holds its "
    "credential. Follow runs with `aew harness status` and `aew harness wait <run>`, then ingest their evidence.",
    "- A run ending is not progress. Only ingested evidence and your recorded decisions move AEW state.",
    "- Do not implement substantial changes yourself. You cannot edit files in this session.",
    "- Lead acquisition, handoff, takeover and release are the operator's actions at their own terminal. They are "
    "refused here.",
    "- Report contradictions between artifacts to the operator. Never resolve them silently.",
])

LEAD_COMMANDS: dict[str, dict[str, str]] = {
    "aew-resume": {
        "description": "AEW: rebuild the Lead's context from durable state",
        "template": "Rebuild your AEW Lead context from durable state. Output of `aew resume`:\n\n!`aew resume`\n\n"
                    "Summarize the objective, active work and in-flight runs, anything blocked or interrupted, and "
                    "the single next Lead action you propose. Do not change anything yet.",
    },
    "aew-status": {
        "description": "AEW: work, Lead authority and harness runs",
        "template": "Output of `aew status`:\n\n!`aew status`\n\nOutput of `aew harness status`:\n\n"
                    "!`aew harness status`\n\nSummarize what is running, which runs ended with evidence waiting to be "
                    "ingested, which ended without evidence, and anything lost. Propose next actions; do not act yet.",
    },
    "aew-ticket": {
        "description": "AEW: draft a Ticket and plan for an objective",
        "template": "Draft an AEW Ticket for this objective: $ARGUMENTS\n\nCurrent AEW status:\n\n!`aew status`\n\n"
                    "Propose the Ticket (title, risk class 0-4 with reasons, scope, completion criteria) and a plan. "
                    "Show them to me first. Only after I agree, run `aew work create ticket ...` and "
                    "`aew plan propose ...` (see `aew work create --help`).",
    },
    "aew-next": {
        "description": "AEW: take the next Lead action on one work unit",
        "template": "Take exactly one next Lead action on AEW work unit: $ARGUMENTS\n\nCurrent AEW status:\n\n"
                    "!`aew status`\n\nFirst run `aew work show <id>` and `aew harness status` for it. Then do the "
                    "one next step: dispatch with --launch, wait for a run, ingest its evidence, or record a "
                    "transition or decision. Explain what you did and what comes after.",
    },
    "aew-handoff": {
        "description": "AEW: checkpoint for a Lead handoff",
        "template": "Prepare a Lead handoff. Output of `aew resume`:\n\n!`aew resume`\n\nWrite a checkpoint note "
                    "(state, in-flight runs, open decisions, next action) and record it with "
                    "`aew checkpoint --note-file - --next \"...\" --expect-rev N`. Then tell me that the handoff "
                    "itself (`aew lead handoff offer`) is mine to run at my own terminal.",
    },
}


def lead_config() -> dict[str, Any]:
    """``OPENCODE_CONFIG_CONTENT`` for the Lead's TUI. It is merged over the operator's own configuration."""
    return {"share": "disabled", "default_agent": LEAD_AGENT,
            "agents": {LEAD_AGENT: {"mode": "primary", "description": "AEW Lead (acts through the Lead broker)",
                                    "system": LEAD_SYSTEM, "permissions": LEAD_RULES}},
            "commands": {name: {**cmd, "agent": LEAD_AGENT} for name, cmd in LEAD_COMMANDS.items()}}
