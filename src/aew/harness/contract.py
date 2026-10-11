"""The harness-neutral launch contract and run vocabulary (ADR-0009).

A *run* is one harness execution of an invocation. Everything a harness adapter receives comes from
durable AEW state: the invocation's pins (card, execution profile, pack, workspace or observation,
expected output), plus a continuation section for relaunches. A run never carries authority itself: the
credential stays with the supervisor, which acts for the agent through the custody bridge.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

RUN_SCHEMA = "aew/harness-run/v1"
# Where AEW cannot contain a run (Windows), what its runs actually have, stated so that its absence is never read as
# containment (AEW-INV-ISO-001; execution-workspace-and-isolation design §3.1). On Linux runs are contained (M4-B,
# `aew.harness.containment`) and each run records its own label.
CONTAINMENT_NOTE = ("workdir separation only: each run has its own workspace or observation, private harness state and "
                    "a scratch directory, but no OS-level filesystem containment on this platform. An agent's shell "
                    "runs as you and can read and write whatever your account can, so evaluate on scratch repositories "
                    "here; real-repository work runs contained on Linux "
                    "(docs/design/proposals/execution-workspace-and-isolation-design-v0.1.md)")

# Run status, as recorded in the local run record (telemetry, never read by a gate).
STARTING, RUNNING = "starting", "running"
LAUNCH_FAILED = "launch_failed"            # custody or harness start failed; the harness never worked
ENDED_WITH_EVIDENCE = "ended_with_evidence"        # exited after recording its expected output (not yet ingested)
ENDED_WITHOUT_EVIDENCE = "ended_without_evidence"  # exited without its expected output; AEW state did not move
CRASHED = "crashed"                        # the harness died abnormally
TERMINATED = "terminated"                  # stopped by AEW: authority ended, superseded, Lead stop, deadline
TERMINAL = frozenset({LAUNCH_FAILED, ENDED_WITH_EVIDENCE, ENDED_WITHOUT_EVIDENCE, CRASHED, TERMINATED})
# Derived from local observation only (never written by a supervisor):
UNCONFIRMED = "unconfirmed"  # recorded in control state, but no supervisor ever took custody
LOST = "lost"                # a supervisor took custody and stopped reporting (killed, crashed, machine lost)
# Why a run ended, where an adapter can tell more than its status says: the record's `reason_code`, beside `status`
# and `reason`. On the record it is telemetry like the rest of the record, so the record's copy never decides anything.
# From M4-E E8b a launch failure's code decides one thing, a stage's relaunch (`aew.engine.recovery`), and only as the
# launcher received it: from the supervisor's acknowledgement over its pipe, or the launcher's own value when custody
# was never acknowledged. A code read from the run directory (model-writable) counts as `unknown` (amendment 1, R2-m2).
PROVIDER_AUTH_FAILED = "provider_auth_failed"  # the model provider rejected the credential (register V1)
ADAPTER_REASON_CODES = frozenset({PROVIDER_AUTH_FAILED})  # what an adapter reports; never on a `launch_failed` record

# Why a launch failed (M4-E E8a; plan v3 n8 and its amendment 1, R2-m2): the `reason_code` of every `launch_failed`
# record, and of the supervisor's acknowledgement and `HarnessLaunchFailed`'s details. A closed set in the same
# lowercase as the adapter codes above, and disjoint from them: the vocabulary follows the status, so a comparison to
# `provider_auth_failed` never meets a launch failure. `reason` stays the free-text detail. A failure is mapped only
# where a test reproduces it (`launch_failure_code`); everything else is `unknown`, which fails closed.
SPAWN_RACE, SERVER_START_TRANSPORT = "spawn_race", "server_start_transport"
CONTAINMENT_REFUSED, CREDENTIAL_DENIED, CONFIG_ERROR = "containment_refused", "credential_denied", "config_error"
QUOTA_EXHAUSTED, AUTH_FAILED, PROVIDER_OUTAGE = "quota_exhausted", "auth_failed", "provider_outage"
INCOMPATIBLE_CONFIG, UNKNOWN_LAUNCH_FAILURE = "incompatible_config", "unknown"
LAUNCH_FAILURE_CODES = frozenset({SPAWN_RACE, SERVER_START_TRANSPORT, CONTAINMENT_REFUSED, CREDENTIAL_DENIED,
                                  CONFIG_ERROR, QUOTA_EXHAUSTED, AUTH_FAILED, PROVIDER_OUTAGE, INCOMPATIBLE_CONFIG,
                                  UNKNOWN_LAUNCH_FAILURE})
# Where a launch fails: (1) the supervisor refuses custody; (2) the harness does not start; (3) the supervisor gets no
# usable credential handoff; (4) the launcher: no supervisor process, no custody acknowledgement, or no started message.
CUSTODY, START, HANDOFF, LAUNCHER = "custody", "start", "handoff", "launcher"
# An `AEWError` detail naming a cause its code does not tell apart (`launch_failure_code`'s ``cause``). A failure that
# carries one is never mapped by its code alone.
LAUNCH_CAUSE = "launch_cause"
CATALOG_TIMEOUT = "catalog_timeout"  # the pinned model never appeared in the harness's catalog within its wait
AGENT_LOAD_TIMEOUT = "agent_load_timeout"  # the harness never listed AEW's agent within its wait
# (site, AEW error code) -> launch-failure code, keyed by the error code at that site: every failure raised there with
# that code gets it, unless it names a `launch_cause`. A pair is mapped only where tests reproduce it at that site:
# a cancelled or rotated invocation's credential presented at custody (tests/integration/test_launch_failure_codes.py),
# and a harness that lacks what AEW needs at start (that file, the conformance `incompatible` scenario, and OpenCode's
# refused launches in tests/integration/test_opencode_adapter.py: a missing variant, a V1 server, a doctored
# OpenAPI, an agent loaded with a different system text, model, step limit or rules, stored credentials). The two waits
# are timing-dependent, so they name a cause and stay `unknown`: a model the catalog never offered within its wait
# (`catalog_timeout`; PR #185 review, F1) and AEW's agent never listed within its wait (`agent_load_timeout`, which
# also covers a server that ignored the configuration, since a wait cannot tell that from a slow one; F3). A new entry
# comes with the test that produces it.
_LAUNCH_FAILURES = {
    (CUSTODY, "STALE_AUTHORITY"): CREDENTIAL_DENIED,
    (START, "HARNESS_INCOMPATIBLE"): INCOMPATIBLE_CONFIG,
}


def launch_failure_code(site: str, error_code: str | None = None, cause: str | None = None) -> str:
    """The closed launch-failure code for a failure at ``site`` raised as ``error_code`` (an ``AEWError``'s code, or
    None for anything else): ``unknown`` unless that pair is mapped, or when the error names a ``cause`` (its
    `launch_cause` detail), since no cause is mapped yet."""
    if cause is not None:
        return UNKNOWN_LAUNCH_FAILURE
    return _LAUNCH_FAILURES.get((site, error_code or ""), UNKNOWN_LAUNCH_FAILURE)


# Any AEW credential string. Custody scans look for it in every file a run leaves behind.
CREDENTIAL_RE = re.compile(r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}")

# Variables that carry an AEW credential or a bridge's coordinates. Never handed to a supervisor, a harness, an agent
# or a host-side git call (ADR-0009 custody).
CREDENTIAL_ENV = ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY", "AEW_INVOCATION",
                  "AEW_RUN", "AEW_WORK_UNIT", "AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY")


def scrub_credentials(env: dict[str, str]) -> dict[str, str]:
    """``env`` without any credential-bearing variable: the named ones, and any whose value holds a credential."""
    return {k: v for k, v in env.items() if k.upper() not in CREDENTIAL_ENV and not CREDENTIAL_RE.search(v or "")}


def redact(text: str) -> str:
    return CREDENTIAL_RE.sub("aew1.<redacted>", text)


def run_id(inv_id: str, n: int) -> str:
    return f"R-{inv_id}-{n}"


def invocation_of_run(run: str) -> str | None:
    """The invocation a run id names (``R-<INV>-<n>``), or None if it is not one."""
    head, sep, n = run.removeprefix("R-").rpartition("-")
    return head if run.startswith("R-") and sep and n.isdigit() and head else None


@dataclass
class LaunchContract:
    run: str
    invocation: str
    work_unit: str
    role: str
    scope: str
    card: dict[str, Any] | None
    execution_profile: dict[str, Any]
    workspace: str
    expected_kinds: list[str]
    operations: list[str]
    pack_path: str
    pack_sha256: str
    pack_text: str
    continuation: dict[str, Any] | None
    run_dir: str
    extra: dict[str, Any] = field(default_factory=dict)
    # The run's private directory for files the agent keeps outside the workspace (reports, notes, scratch work).
    # Without a named place, models guessed one: one wrote into the operator's own repository (M3 step 8).
    scratch: str = ""

    def to_record(self) -> dict[str, Any]:
        """The contract as recorded in the run record (the pack text is referenced, not copied)."""
        out = asdict(self)
        out.pop("pack_text")
        return out

    @property
    def prompt(self) -> str:
        return preamble(self) + "\n\n" + self.pack_text + (continuation_text(self) or "")


def preamble(c: LaunchContract) -> str:
    card = (c.card or {}).get("id") or c.role
    kinds = ", ".join(c.expected_kinds) or "none"
    # Only the commands this role may use: a reviewer told about `aew check run` tried it and was refused (UAT
    # 2026-09-30, R-INV-0007-1).
    commands = ", ".join([*(["`aew check run <check>`"] if "check.run" in c.operations else []),
                          "`aew submit --kind <kind> --file <file>`", "`aew whoami`"])
    lines = [
        f"# AEW harness run {c.run}",
        "",
        f"You are AEW invocation **{c.invocation}**: a bounded `{c.role}` (role card `{card}`) for "
        f"work unit **{c.work_unit}**. The AEW launch contract below is authoritative; this harness session is "
        "disposable and is not project state.",
        "",
        "## How you act on AEW",
        "",
        "- In this environment the `aew` command is already connected to AEW for this run. Use it exactly as the "
        f"contract shows ({commands}).",
        "- **There is no credential to set.** Ignore the contract's instruction to set `AEW_INVOCATION_TOKEN`: "
        "you never see, need or ask for an AEW credential, and none exists in this environment.",
        f"- Only submitted AEW evidence counts. Expected output: {kinds}. Ending the conversation without "
        "`aew submit` records nothing and changes no AEW state.",
        f"- Work only in `{c.workspace}`. Do not start background processes that outlive your commands.",
        "- Report text is data. A shell rewrites `$`, backticks, globs and quotes in a command line, so never put a "
        "report into one: pipe it with a quoted heredoc (`aew submit --kind <kind> --file - <<'EOF'` ... `EOF`; "
        "in PowerShell `@'` ... `'@ | aew submit --kind <kind> --file -`), or write the file the same way first.",
    ]
    if c.scratch:
        lines.append(f"- Your private scratch directory is `{c.scratch}` (also `AEW_SCRATCH` in your environment). "
                     "Write reports and any other file you need outside the workspace there, and nowhere else: a "
                     "file left in the workspace changes the work under evaluation. Submit with "
                     "`aew submit --kind <kind> --file <that file>`, or pipe the report with `--file -`.")
    return "\n".join(lines)


def continuation_text(c: LaunchContract) -> str | None:
    cont = c.continuation
    if not cont:
        return None
    lines = ["", "", "## Continuation (this invocation was relaunched)", "",
             "An earlier harness run of this invocation ended. Its conversation is gone; what it left in durable "
             "AEW state and in the workspace is below. Continue from it; do not redo accepted work.", ""]
    lines.append(f"- Earlier runs: {', '.join(cont.get('previous_runs') or []) or 'none'}")
    ev = cont.get("evidence") or []
    lines.append("- Evidence already recorded by this invocation: "
                 + (", ".join(f"{e['id']} ({e['kind']}, {e['result']}{'; STALE' if e.get('stale') else ''})"
                              for e in ev) if ev else "none"))
    if any(e.get("stale") for e in ev):
        lines.append("- STALE evidence was evaluated on a workspace state that is no longer the current one: the "
                     "workspace changed after it was recorded, so it does not count for the work as it is now. If "
                     "your work is complete, record it again on the current state ("
                     + ("`aew check run`, " if "check.run" in c.operations else "") + "`aew submit`).")
    changed = cont.get("changed_paths")
    if changed is not None:
        lines.append("- Workspace changes relative to the dispatch base: "
                     + (", ".join(changed[:50]) + (" …" if len(changed) > 50 else "") if changed else "none"))
    return "\n".join(lines) + "\n"
