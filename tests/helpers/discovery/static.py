"""D2's static texts (discovery-layer spec v3.4, §2.1, F2): the rules applied without tests, to every text a reader
meets before any command runs. The scan is cheap and complete, so it runs on every pull request.

The texts: ``LEAD_SYSTEM`` and the Lead's commands, the rendered ``aew guide`` (from the policy ``aew init`` writes),
the operator guides (the quickstart among them), and every pack template (the launch contract each role is given,
rendered from synthetic inputs). The typed surface's own arguments are checked by O-SECRET as well.

The guides are passed in by the caller (``guides``: their repository path to their text), so the documentation a scan
reads is named only where it runs: the ``discovery`` lane and the fast lane's tests, which every tier runs.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

from discovery import rules
from discovery.rules import MODEL, OPERATOR, Finding

GUIDES_GLOB = "*.md"  # every operator guide, under the guides directory the caller names
STATIC = "static:"


def read_guides(directory: Path, prefix: str) -> dict[str, str]:
    """``{"<prefix>/<name>.md": text}`` for every guide in ``directory``."""
    return {f"{prefix}/{p.name}": p.read_text(encoding="utf-8") for p in sorted(directory.glob(GUIDES_GLOB))}


def lead_system_text() -> str:
    """What the Lead's TUI is given as its system text: ``LEAD_SYSTEM`` with the rendered guide appended."""
    from aew.harness.opencode import projection

    return projection.lead_config(rendered_guide())["agents"][projection.LEAD_AGENT]["system"]


def rendered_guide() -> str:
    from aew.engine import guide
    from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES

    return guide.render(DEFAULT_GATES, DEFAULT_CHECKS)


def pack_templates() -> Iterator[tuple[str, str]]:
    """Each role's pack, rendered from synthetic inputs (one per role that has a report template)."""
    from aew import roles
    from aew.knowledge import context as ctx

    snapshot = {"relevant_inputs_fingerprint": "tree:0", "workspace_id": "ws-0", "base_revision": "0" * 40}
    acceptance = {"goal_backwards": ["a goal"], "contract": ["a clause"]}
    for role in sorted(ctx.OUTPUT_TEMPLATES):
        inputs = ctx.PackInputs(
            invocation_id="INV-1", role=role, role_def=roles.archetype(role), work_id="T-0001", title="a title",
            scope="ticket", specialty=None, workspace="/ws/T-0001", snapshot=snapshot,
            record_meta={"initial_risk_class": 1, "acceptance": acceptance, "scope": {"paths": ["src/**"]}},
            record_body="a body", plan={"accepted": 1, "sha256": "0" * 64}, plan_text="a plan",
            guardrails_text="", checks={"unit": {"configured": True, "description": "unit tests"}}, authority=[])
        yield role, ctx.render(inputs)


def texts(guides: Mapping[str, str]) -> Iterator[tuple[str, str, str]]:
    """``(source, plane, text)`` for every static text."""
    from aew.harness.opencode.projection import LEAD_COMMANDS, LEAD_SYSTEM

    yield "lead-system", MODEL, LEAD_SYSTEM
    for name, command in sorted(LEAD_COMMANDS.items()):
        yield f"lead-command:{name}", MODEL, command["template"]
    yield "guide", MODEL, rendered_guide()
    for source, text in sorted(guides.items()):
        yield source, OPERATOR, text
    for role, text in pack_templates():
        yield f"pack:{role}", MODEL, text


def scan(guides: Mapping[str, str]) -> list[Finding]:
    """Every static finding. A static key names its source and the suggested input (or the O-SECRET ask), so a new
    violation in a text that already has one is still new."""
    findings: list[Finding] = []
    for source, plane, text in texts(guides):
        out = rules.Output(site=source, plane=plane, text=text)
        for s in rules.suggestions(out):
            line = " ".join(s.text.split())
            findings.extend(Finding(rule, f"{STATIC}{source}|{line}", why) for rule, why in rules.judge(s))
        for problem in rules.o_secret(text, plane):
            findings.append(Finding("O-SECRET", f"{STATIC}{source}|{problem}", problem))
    missing = rules.o_env(lead_system_text())
    if missing:
        findings.append(Finding("O-ENV", f"{STATIC}lead-system+guide", "missing: " + ", ".join(missing)))
    findings.extend(rules.tool_argument_secrets())
    return rules.dedupe(findings)
