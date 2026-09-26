"""Bounded context packs and launch contracts (WC §10.1, §15.4; KC §15).

A pack is assembled only from durable artifacts, so a replacement subagent can be
launched without anyone's conversational history. Packs are deterministic
functions of recorded inputs: the diff is regenerated from the snapshot's git
tree id, and evidence is limited to what existed when the invocation was
created. The credential never appears in a pack; the Lead supplies it in the
spawn prompt.

Independence (WC §10.1): the reviewer pack excludes implementer reasoning. Only
the structured facts of the implementation report (files changed, checks run,
declared deviations) are included, and the verifier pack labels them as claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aew.util import dump_yaml

TOKEN_PLACEHOLDER = "<AEW_INVOCATION_TOKEN: supplied by the Lead in the spawn prompt; never written to disk>"

OUTPUT_TEMPLATES = {
    "implementer": ("implementation_report", {
        "claim": "<one line: what is now implemented>",
        "result": "pass  # or: blocked",
        "producer": {"model": "<model>", "harness": "<harness>"},
        "implementation": {
            "files_changed": ["<path>"],
            "checks_run": ["<check evidence ids from `aew check run`>"],
            "deviations": ["<any deviation from the accepted plan, or empty>"],
            "unexpected_findings": [],
            "self_review": {"completed": True, "notes": "<scope drift, error paths, stale tests, TODOs checked>"},
        },
    }),
    "reviewer": ("review", {
        "claim": "<one line>",
        "producer": {"model": "<model>"},
        "review": {
            "independence": "R1",
            "disposition": "pass  # or: changes_required",
            "findings": [{"id": "F1", "severity": "blocker|major|minor|observation", "summary": "<finding>",
                          "location": "<path:line>", "required": True}],
            "resolved_findings": ["<ids of earlier findings this change resolves>"],
        },
    }),
    "verifier": ("verification", {
        "claim": "<one line>",
        "producer": {"model": "<model>"},
        "verification": {
            "scope": "<ticket|integration>",
            "claims": [
                {"type": "goal_backwards", "claim": "<observable outcome>", "result": "pass|fail|inconclusive|blocked",
                 "checks": ["<check evidence ids you ran>"]},
                {"type": "contract", "claim": "<conformance statement>", "result": "pass|fail|inconclusive|blocked",
                 "checks": ["<ids>"]},
            ],
            "suspected_cause": "<optional; never a remediation decision>",
        },
    }),
}
OUTPUT_TEMPLATES["specialist"] = OUTPUT_TEMPLATES["reviewer"]


@dataclass
class PackInputs:
    invocation_id: str
    role: str
    role_def: dict[str, Any]
    work_id: str
    title: str
    scope: str
    specialty: str | None
    workspace: str
    snapshot: dict[str, Any]
    record_meta: dict[str, Any]
    record_body: str
    plan: dict[str, Any] | None
    plan_text: str
    guardrails_text: str
    checks: dict[str, Any]
    authority: list[dict[str, Any]]
    diff: str = ""
    diffstat: str = ""
    check_results: list[dict[str, Any]] = field(default_factory=list)
    implementation_summary: dict[str, Any] | None = None
    open_findings: list[dict[str, Any]] = field(default_factory=list)
    failure_evidence: dict[str, Any] | None = None


def _bullets(items: list[str]) -> list[str]:
    return [f"- {i}" for i in items] or ["- (none)"]


def _launch_contract(p: PackInputs) -> list[str]:
    kind, template = OUTPUT_TEMPLATES.get(p.role, (None, None))
    snap = p.snapshot
    lines = [
        f"# AEW launch contract — {p.invocation_id} ({p.role}{'/' + p.specialty if p.specialty else ''})",
        "",
        "This package is your complete, bounded context. It was assembled from durable project artifacts;",
        "you do not need, and must not rely on, anyone's conversation history.",
        "",
        "## Contract",
        "",
        f"- Role: **{p.role}** — authority: " + "; ".join(p.role_def["authority"]),
        f"- Work unit: **{p.work_id}** — {p.title}",
        f"- Scope: {p.scope}",
        f"- Workspace: `{p.workspace}`",
        f"- Evaluated snapshot: base `{snap.get('base_revision')}`, inputs `{snap['relevant_inputs_fingerprint']}`,"
        f" workspace `{snap['workspace_id']}`",
        f"- Accepted plan: " + (f"v{p.plan['accepted']} (sha256 {p.plan['sha256'][:12]}…)" if p.plan else "none"),
        "- Required knowledge (included below): " + ", ".join(p.role_def["context"]["knowledge"]),
        "- Capabilities: " + (", ".join(p.role_def.get("capabilities", [])) or "none"),
        "",
        "### Responsibilities",
        *_bullets(p.role_def["responsibilities"]),
        "",
        "### Allowed",
        *_bullets(p.role_def["allowed_operations"]),
        "",
        "### Prohibited",
        *_bullets(p.role_def["prohibited"]),
        "",
        "### Credential and writeback",
        "",
        f"Set `AEW_INVOCATION_TOKEN={TOKEN_PLACEHOLDER}` for every `aew` command below.",
        f"Run commands from the workspace: `aew -C \"{p.workspace}\" ...`",
    ]
    if "check.run" in " ".join(p.role_def["allowed_operations"]) or p.role in {"implementer", "verifier"}:
        lines.append("- Run a check: `aew check run <check-id>` (records sealed evidence bound to the snapshot)")
    if kind:
        lines += [
            f"- Write back: `aew submit --kind {kind} --file <your-report.md>`",
            "",
            "Report format (YAML frontmatter + Markdown body):",
            "",
            "```markdown",
            "---",
            dump_yaml(template).rstrip(),
            "---",
            "<Markdown body>",
            "```",
        ]
    lines += ["", "### Completion criteria", ""]
    if p.role == "implementer":
        lines += _bullets(["the accepted plan is implemented within scope",
                           "required local checks pass on the final snapshot (`aew check run`)",
                           "an implementation report with a completed self-review is submitted"])
    elif p.role in {"reviewer", "specialist"}:
        lines += _bullets(["every finding has a severity and says whether a change is required",
                           "earlier open findings are marked resolved or remain open",
                           "a review is submitted; do not fix anything yourself"])
    elif p.role == "verifier":
        lines += _bullets(["each acceptance criterion is demonstrated by evidence you produced",
                           "goal-backwards and contract claims are both reported" if p.scope == "ticket"
                           else "post-integration checks are re-run on the integrated candidate",
                           "failures are reported with evidence; the Lead decides what happens next"])
    return lines


def _requirement(p: PackInputs) -> list[str]:
    acceptance = p.record_meta.get("acceptance") or {}
    return [
        "## Requirement",
        "",
        f"**{p.work_id} — {p.title}** (risk class {p.record_meta.get('initial_risk_class')})",
        "",
        p.record_body.strip() or "(no additional description)",
        "",
        "Goal-backwards acceptance criteria:",
        *_bullets(acceptance.get("goal_backwards", [])),
        "",
        "Contract criteria:",
        *_bullets(acceptance.get("contract", [])),
        "",
        "Ticket scope (allowed change paths): " + (", ".join((p.record_meta.get("scope") or {}).get("paths", []))
                                                   or "not restricted"),
    ]


def _authority(p: PackInputs) -> list[str]:
    lines = ["## Governing authority (accepted)", ""]
    lines += [f"- `{a['path']}` ({a['class']}, decision {a['decision']})" for a in p.authority] or [
        "- none accepted yet (candidates discovered at init are not authority)"]
    return lines


def _checks(p: PackInputs) -> list[str]:
    lines = ["## Available checks", "", "- `guardrails` (built-in): protected/generated paths and Ticket scope"]
    for cid, cfg in sorted(p.checks.items()):
        state = "configured" if cfg.get("configured") else "NOT configured (blocks gates)"
        lines.append(f"- `{cid}` ({state}): {cfg.get('description', '')}")
    return lines


def _findings(p: PackInputs) -> list[str]:
    lines = ["## Open review findings", ""]
    lines += [f"- `{f['id']}` [{f['severity']}{', required' if f['required'] else ''}] {f['summary']}"
              + (f" ({f['location']})" if f.get("location") else "") for f in p.open_findings] or ["- none"]
    return lines


def _check_results(p: PackInputs) -> list[str]:
    lines = ["## Check results on this snapshot", ""]
    lines += [f"- `{c['id']}`: check `{c['check_id']}` → **{c['result']}** (exit {c['exit_code']}; log `{c['log']}`)"
              for c in p.check_results] or ["- none recorded for this snapshot"]
    return lines


def render(p: PackInputs) -> str:
    out = _launch_contract(p)
    out += ["", *_requirement(p)]
    if p.role != "verifier":
        out += ["", "## Accepted plan", "", p.plan_text.strip() or "(no accepted plan)"]
    out += ["", "## Guardrails (policy/guardrails.yaml)", "", "```yaml", p.guardrails_text.rstrip(), "```"]
    out += ["", *_authority(p)]
    if p.role in {"implementer", "verifier"}:
        out += ["", *_checks(p)]
    if p.role == "implementer" and p.failure_evidence:
        fe = p.failure_evidence
        out += ["", "## Failure evidence to address (classified LOCAL_IMPLEMENTATION_DEFECT by the Lead)", "",
                f"- Verification `{fe['id']}` result: {fe['result']}",
                *[f"- claim [{c['type']}] {c['claim']}: {c['result']}" for c in fe.get("claims", [])],
                f"- Verifier's suspected cause: {fe.get('suspected_cause') or 'not stated'}"]
    if p.role in {"implementer", "reviewer", "specialist", "verifier"}:
        out += ["", *_findings(p)]
    if p.role in {"reviewer", "specialist"}:
        s = p.implementation_summary or {}
        out += ["", "## Implementation facts (structured fields only; implementer reasoning is excluded)", "",
                "- Files changed: " + (", ".join(s.get("files_changed", [])) or "not reported"),
                "- Checks run: " + (", ".join(s.get("checks_run", [])) or "not reported"),
                "- Declared deviations from plan: " + ("; ".join(s.get("deviations", [])) or "none declared"),
                "- Unexpected findings: " + ("; ".join(s.get("unexpected_findings", [])) or "none declared")]
        out += ["", *_check_results(p)]
        out += ["", "## Review scope", "",
                f"Review the complete change below{' for ' + p.specialty + ' concerns' if p.specialty else ''}: "
                "correctness, ownership, error/cleanup paths, compatibility, security, test adequacy and "
                "unnecessary scope."]
        out += ["", "## Change under review", "", "```diff", p.diff.rstrip() or "(empty diff)", "```"]
    if p.role == "verifier":
        s = p.implementation_summary or {}
        out += ["", "## Implementation revision", "", "```text", p.diffstat.rstrip() or "(no changes)", "```", "",
                "Implementer claims (NOT evidence — establish each outcome yourself):",
                *_bullets([f"files changed: {', '.join(s.get('files_changed', [])) or 'not reported'}",
                           f"checks run: {', '.join(s.get('checks_run', [])) or 'not reported'}"])]
    out.append("")
    return "\n".join(out)
