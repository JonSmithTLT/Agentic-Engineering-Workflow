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

from collections.abc import Mapping
from typing import Any

from aew.harness.contract import LaunchContract
from aew.surface import SERVER_NAME

AGENT = "aew"
LEAD_AGENT = "aew-lead"
AUXILIARY_AGENTS = ("title", "summary", "compaction")
COMPATIBILITY_PLUGIN = "-opencode.config.compatibility"
MUTATING_ROLES = frozenset({"implementer"})
WEB_CAPABILITIES = frozenset({"documentation_lookup"})
ALWAYS_DENIED = ("subagent", "question", "external_directory")


def rule(action: str, effect: str, resource: str = "*") -> dict[str, str]:
    return {"action": action, "resource": resource, "effect": effect}


def rules_hold(loaded: list[dict[str, Any]], want: list[dict[str, Any]]) -> str | None:
    """Whether the rules OpenCode loaded for AEW's agent mean what AEW projected: ``None`` when they do, else why not.

    The last matching rule wins, so AEW's rules must appear in order, as one block, and nothing after them may widen
    access: OpenCode may append its own defaults there (2.0.22 appends ``browser: deny``), but only ``deny`` rules.
    An ``allow`` or ``ask`` after AEW's rules could reopen what they close, and refuses (register E17)."""
    n = len(want)
    starts = [i for i in range(len(loaded) - n, -1, -1) if loaded[i:i + n] == want]
    if not starts:
        return "AEW's rules are missing or out of order"
    widening = [r for r in loaded[starts[0] + n:] if r.get("effect") != "deny"]
    if widening:
        return f"rules after AEW's could widen access: {widening[:5]}"
    return None


# ---------------------------------------------------------------------------------------------- invocation runs


def model_ref(profile: dict[str, Any]) -> dict[str, str]:
    """The session's ``model`` (``Model.Ref``): provider, model and the effort as OpenCode's variant. The pin already
    holds the provider and the model apart, as the adapter's model identity mapped them at dispatch
    (``HarnessAdapter.model_identity``), so they are passed as they are, never split or joined here."""
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


def system_text(contract: LaunchContract, unavailable_skills: list[str],
                network: Mapping[str, Any] | None = None) -> str:
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
        "- Report text is data: write or pipe it with a quoted heredoc (`<<'EOF'`; in PowerShell `@'` ... `'@`), "
        "never inside a command line, where the shell rewrites `$`, backticks, globs and quotes.",
        "- Do not start processes that outlive your commands. You cannot delegate: there are no subagents.",
        "- Tools that are unavailable here are unavailable by design. Do not work around them.",
    ]
    if network is not None:
        lines.append(network_text(network))
    if unavailable_skills:
        lines.append("- Skills your role card requests that this harness does not provide: "
                     f"{', '.join(unavailable_skills)}. Proceed without them and say so in your report.")
    return "\n".join(lines)


def network_text(network: Mapping[str, Any]) -> str:
    """The system text's line for a run on a network of its own (F28; #257's review, F3): what the run reaches, that
    everything else is refused by design, and how to ask for more. ``network`` is the run's label
    (``netns.RunNetwork.describe``); its upstream and stated limits are the operator's, not the agent's."""
    reach = ["your model's provider"] if network.get("provider_relay") == "configured" else []
    allow = list(network.get("egress_allow") or [])
    if allow:
        reach.append(f"through `HTTPS_PROXY`, only {', '.join(f'`{a}`' for a in allow)}")
    return (f"- This run has a network of its own (`{network['mode']}`): "
            + (f"it reaches {' and, '.join(reach)}" if reach else "it has no route out")
            + ". Every other connection is refused by design. If your work needs another host, do not work around "
            "the refusal: name the `host:port` and what you needed it for in your report, so the Lead can ask the "
            "operator to add it to `containment.network.egress_allow`.")


def invocation_config(contract: LaunchContract, *, provided_skills: frozenset[str] = frozenset(),
                      private_dirs: tuple[str, ...] = (), network: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """``OPENCODE_CONFIG_CONTENT`` for one run's private server. ``network``: the label of the run's own network
    (``netns.RunNetwork.describe``), which the system text states; None for a run on the host's."""
    skill = skills(contract, provided_skills)
    rules = permissions(contract, skill["exposed"], private_dirs)
    profile = contract.execution_profile
    agent: dict[str, Any] = {"mode": "primary", "description": f"AEW {contract.role} for {contract.invocation}",
                             "model": config_model(profile),
                             "system": system_text(contract, skill["unavailable"], network), "permissions": rules}
    if profile.get("max_steps"):
        agent["steps"] = int(profile["max_steps"])
    agents: dict[str, Any] = {AGENT: agent}
    for name in AUXILIARY_AGENTS:  # any auxiliary model call uses the pinned model too
        agents[name] = {"model": config_model(profile)}
    return {"snapshots": False, "update": "disable", "share": "disabled", "plugins": [COMPATIBILITY_PLUGIN],
            "lsp": False, "formatter": False, "default_agent": AGENT, "permissions": rules, "agents": agents}


def relayed(config: dict[str, Any], profile: dict[str, Any], base_url: str) -> dict[str, Any]:
    """``config`` with the pinned provider pointed at the run's provider relay (F28 §3.5): its ``baseURL`` at the
    relay's loopback port inside the sandbox, over plain HTTP requests (the provider's ``transport``: 2.0.18's OpenAI
    provider otherwise opens a WebSocket first). The ``baseURL`` is set for the provider and for the pinned model, whose
    catalog entry may carry its own, which wins over the provider's (every ``opencode/*`` model's does). Both measured
    on 2.0.18, 2026-10-24."""
    return {**config, "providers": {str(profile["provider"]): {
        "settings": {"baseURL": base_url, "transport": "http"},
        "models": {str(profile["model"]): {"settings": {"baseURL": base_url}}}}}}


def session_body(contract: LaunchContract, directory: str, rules: list[dict[str, str]]) -> dict[str, Any]:
    """``POST /api/session``. The metadata is correlation only: nothing reads it as authority."""
    return {"title": f"AEW {contract.run} ({contract.role}, {contract.work_unit})", "agent": AGENT,
            "model": model_ref(contract.execution_profile), "location": {"directory": directory},
            "permissions": rules, "metadata": {"aew_invocation": contract.invocation, "aew_run": contract.run,
                                               "aew_work_unit": contract.work_unit}}


# ---------------------------------------------------------------------------------------------- the Lead's TUI

# The Lead's typed tools (F15.1): OpenCode 2.0.18 names an MCP tool `<server>_<tool>` and asks permission for exactly
# that action, so one rule allows the `aew-lead` server's tools. Each is engine-refused or engine-committed, like the
# `aew *` shell commands beside it.
LEAD_MCP_SERVER = SERVER_NAME
LEAD_MCP_COMMAND = ["aew", "lead", "mcp"]

LEAD_RULES = [
    rule("*", "ask"),
    *(rule(action, "allow") for action in ("read", "glob", "grep")),
    rule("shell", "ask"),
    *(rule("shell", "allow", pattern) for pattern in ("aew *", "git status*", "git diff*", "git log*", "git show*")),
    rule("edit", "deny"),
    rule("subagent", "deny"),
    rule("question", "allow"),
    rule(f"{LEAD_MCP_SERVER}_*", "allow"),
]

LEAD_SYSTEM = "\n".join([
    "You are the AEW Lead for this repository. AEW, not this conversation, holds the workflow: objectives, work "
    "units, plans, dispatches, evidence and decisions live in `.aew/` and change only through the `aew` command. "
    "This session is disposable. After any restart, rebuild your context with `aew resume` (/aew-resume), never "
    "from an earlier conversation.",
    "- You never hold or see the Lead credential. This session's Lead broker carries out Lead-authenticated `aew` "
    "commands for you. Mutations still need `--expect-rev <revision>` (from `aew status` or the previous command).",
    f"- Your `{SERVER_NAME}` tools are the normal way to read AEW state, wait for runs and checkpoint: `status`, "
    "`resume`, `work_show`, `explain`, `harness_status`, `harness_wait` (several runs at once; it returns when the "
    "first ends) and `checkpoint`. Each returns the revision to pass as `expect_rev` next and a projection of what is "
    "available, blocked or unknown, and of the decisions that are yours. Until typed stages arrive, other changes "
    "still go through `aew` commands.",
    "- Delegate implementation, review, verification, investigation and research to bounded invocations. Dispatch "
    "with `--launch` (for example `aew work assign T-0001 --launch --expect-rev N`): the run's supervisor holds its "
    "credential. Follow runs with `aew harness status` and `aew harness wait <run>`, then ingest their evidence.",
    "- A run ending is not progress. Only ingested evidence and your recorded decisions move AEW state.",
    "- `aew guide` explains how AEW works in this project: the risk classes and what each requires, the Ticket "
    "lifecycle, and the command for each step. Work from it, not by trial and error. When it is included below, it "
    "is the same text.",
    "- Free text is data. A shell rewrites `$`, backticks, `*`, `?` and quotes in a command line, so never type "
    "titles, goals, contract clauses, scopes, reasons or notes into one. Pass them with `--fields -` and a quoted "
    "heredoc: YAML, one key per option, a list for a repeatable one (`aew work create ticket --class <0-4> "
    "--expect-rev N --fields - <<'EOF'`, then `title: '...'`, `goal: ['...', '...']`, `contract: ['...']`, "
    "`scope: ['...']`, then `EOF`). Put every value in single quotes (two single quotes for one inside it), or "
    "write it as a block (`goal: |-` and indented lines): unquoted, YAML would cut the text at ` #` and join "
    "lines, and AEW refuses such input. Plans and notes go the same way with `--file -` or `--note-file -`. "
    "In PowerShell, pipe a single-quoted here-string (`@'` ... `'@ | aew ...`).",
    # CS-4 addendum 11: the old "anything else needs the operator" read as a ban, even on a command the operator
    # approves. The rules are unchanged (`LEAD_RULES`): a command that asks still waits on the operator.
    "- Do not implement substantial changes yourself. You cannot edit files in this session, but you can read and "
    "search them with your read, glob and grep tools. The shell runs `aew` and `git status|diff|log|show` directly. "
    "Any other command asks the operator's permission first: when the operator asks for one, such as running the "
    "tests or a script, or one is needed to do what they asked, request it, and run it once they approve. If they "
    "decline, do not try it another way. Editing files and committing stay with invocations, whatever the command: "
    "dispatch one for them.",
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
                    "Propose the Ticket (title, risk class 0-4 chosen by the guide's class definitions, with your "
                    "reasons, scope, completion criteria) and a plan. "
                    "Show them to me first. Only after I agree, run `aew work create ticket ... --fields -` and "
                    "`aew plan propose ... --file -`, each with a quoted heredoc so the shell leaves the text alone "
                    "(see `aew work create --help`). The plan declares its assurance (`--assurance none`, or "
                    "`--review`/`--verify` cards that become required gates): say which in the proposal.",
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


# Providers whose OpenCode 2.0.18 SDK opens a WebSocket first unless their transport is http, which the relay refuses
# (measured on the Rocky VM, 2026-10-24: OpenAI's).
WEBSOCKET_FIRST = frozenset({"openai"})


def lead_contained_text(label: Mapping[str, Any]) -> str:
    """The contained Lead's system-text line (STG-05 CS-4, outcome 7), from its session's label: what the session
    reaches, that the rest is refused by design, and what to do instead of working around a refusal."""
    net = label.get("network") or {}
    relays = sorted(net.get("provider_relays") or {})
    reach = ([f"your model providers {', '.join(f'`{p}`' for p in relays)} through AEW's relays"] if relays else []) \
        + (["public addresses over https through `HTTPS_PROXY`"] if net.get("egress_policy") == "any_public" else [])
    return (f"- This Lead session is contained (`{label.get('filesystem')}`, network `{net.get('mode')}`): only the "
            "working tree is writable. `.aew/` and the git metadata are read-only, so a commit fails here, while "
            "`git status`, `diff` and `log` work and your Lead `aew` commands still reach the broker, which writes "
            "AEW state for you. The session reaches " + (" and ".join(reach) or "nothing outside it")
            + ". The desktop, the clipboard bus, browser tools and private or host addresses are refused by design. "
            "A refusal is what a deny rule or this containment returns. Do not work around one: tell the operator "
            "what you needed and why, so they can do it at their own terminal or widen AEW's containment settings "
            "where a setting exists. Running a command the operator approved is not working around anything.")


def lead_config(guide: str = "", *, contained: Mapping[str, Any] | None = None,
                relays: Mapping[str, str] | None = None) -> dict[str, Any]:
    """``OPENCODE_CONFIG_CONTENT`` for the Lead's TUI. It is merged over the operator's own configuration, which the
    contained Lead does not load (STG-05 CS-4).

    ``guide`` is the project's Lead guide (``aew guide``, F16), rendered from its own policy: appended to the Lead's
    system text so every Lead works from how AEW actually runs here, not by trial and error. ``contained`` is a
    contained session's label, whose line the system text carries (:func:`lead_contained_text`), and ``relays`` its
    relayed providers' ``baseURL`` (provider id -> the relay's loopback address inside): provider-level only, which
    every request of those providers' models follows (measured, 2026-10-25), so no model is made up in the list."""
    system = LEAD_SYSTEM + (f"\n{lead_contained_text(contained)}" if contained is not None else "")
    system = f"{system}\n\n{guide}" if guide else system
    providers = {p: {"settings": {"baseURL": url, **({"transport": "http"} if p in WEBSOCKET_FIRST else {})}}
                 for p, url in sorted((relays or {}).items())}
    return {**({"providers": providers} if providers else {}), "share": "disabled", "default_agent": LEAD_AGENT,
            # The typed surface's server: spawned by OpenCode in the session's curated environment, with no
            # `environment` of its own (it holds no credential), and with Code Mode off so its tools are function
            # tools (2.0.18's default hides MCP tools behind one `execute` tool). Its execution timeout is left at the
            # pinned default (43,200,000 ms), far above harness_wait's 600 s cap.
            "mcp": {"servers": {LEAD_MCP_SERVER: {"type": "local", "command": list(LEAD_MCP_COMMAND),
                                                  "codemode": False}}},
            "agents": {LEAD_AGENT: {"mode": "primary", "description": "AEW Lead (acts through the Lead broker)",
                                    "system": system, "permissions": LEAD_RULES}},
            "commands": {name: {**cmd, "agent": LEAD_AGENT} for name, cmd in LEAD_COMMANDS.items()}}
