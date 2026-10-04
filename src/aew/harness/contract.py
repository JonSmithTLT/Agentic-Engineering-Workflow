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
                    "(docs/design/execution-workspace-and-isolation-design-v0.1.md)")

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

# Any AEW credential string. Custody scans look for it in every file a run leaves behind.
CREDENTIAL_RE = re.compile(r"aew1\.tk_[0-9a-f]{16}\.[A-Za-z0-9_-]{20,}")


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
